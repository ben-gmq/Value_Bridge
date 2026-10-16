"""The single visibility guard (§7.8, §9.10, §9.11; D-40, D-71, slice7_schema §8.6). Every list and detail
query passes through it; nothing else in the app decides who can see a project, or at what level.

Platform admins see everything, at PLATFORM — the one level above ADMIN, never held by a membership; it guards the
FTC-only project settings (D-71 (6)). Every other user's level on a project is the HIGHER of its sources, capped by
their kind (D-71 (4)):
  - STAFF:  the project is open → KIND_BASE (USER → EDIT, VIEWER → VIEW)
  - MEMBER: a live project_member → its level (ADMIN / EDIT / VIEW)
and no source at all (a restricted project they are not a member of) is None → 404. KIND_CAP is the ceiling any
source can lift a kind to (USER → ADMIN, VIEWER → VIEW): never the default (design-auditor H2).

A project you cannot see does not exist: that is a 404, never a 403.
"""
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AppUser, Program, Project, ProjectMember

LEVEL_RANK = {"VIEW": 1, "EDIT": 2, "ADMIN": 3, "PLATFORM": 4}
KIND_BASE = {"USER": "EDIT", "VIEWER": "VIEW"}       # what staff get on an open project (D-40)
KIND_CAP = {"USER": "ADMIN", "VIEWER": "VIEW"}       # the most any source lifts a kind to (D-71); + CLIENT_VIEWER: VIEW
NOT_FOUND = "Not found"


@dataclass(frozen=True)
class EffectiveAccess:
    level: str                     # VIEW / EDIT / ADMIN / PLATFORM
    via: str                       # PLATFORM_ADMIN / MEMBER / STAFF
    member: ProjectMember | None


ADMIN_ACCESS = EffectiveAccess("PLATFORM", "PLATFORM_ADMIN", None)


def rank_ok(level: str, min_level: str) -> bool:
    return LEVEL_RANK[level] >= LEVEL_RANK[min_level]


def _lower(a: str, b: str) -> str:
    return a if LEVEL_RANK[a] <= LEVEL_RANK[b] else b


def level_for(user_kind: str, restricted: bool, member_level: str | None) -> tuple[str, str] | None:
    """(level, via) for a staff user of this kind, on a project open or restricted, with or without a live
    membership; None when they cannot open it. The one place a staff level is computed: access_to and who_can_open
    both call it, so the guard and every list of who can open a project agree (design-auditor H1). An unknown kind
    raises: fails closed."""
    sources = []
    if member_level is not None:
        sources.append((member_level, "MEMBER"))      # first: on a tie the membership is the source shown
    if not restricted:
        sources.append((KIND_BASE[user_kind], "STAFF"))
    if not sources:
        return None
    level, via = max(sources, key=lambda s: LEVEL_RANK[s[0]])
    return _lower(KIND_CAP[user_kind], level), via


def live_member(db: Session, project_id: int, user_id: int) -> ProjectMember | None:
    return db.scalars(select(ProjectMember).where(ProjectMember.project_id == project_id,
                                                  ProjectMember.app_user_id == user_id,
                                                  ProjectMember.is_active)).one_or_none()


def visible_project_ids(db: Session, user: AppUser) -> set[int] | None:
    """None means ALL (platform admin). Restriction and membership are read per request, so
    restricting a project hides it from non-members on their next request."""
    if user.is_platform_admin:
        return None
    open_ = set(db.scalars(select(Project.project_id).where(Project.is_active, ~Project.is_restricted)))
    members = set(db.scalars(select(Project.project_id).join(
        ProjectMember, ProjectMember.project_id == Project.project_id).where(
        ProjectMember.app_user_id == user.app_user_id, ProjectMember.is_active,
        Project.is_active, Project.is_restricted)))
    return open_ | members


def access_to(db: Session, user: AppUser, p: Project | None) -> EffectiveAccess | None:
    """The user's access to one project, or None when they cannot see it."""
    if user.is_platform_admin:
        return ADMIN_ACCESS if p is not None else None
    if p is None or not p.is_active:
        return None
    m = live_member(db, p.project_id, user.app_user_id)
    got = level_for(user.user_kind, p.is_restricted, m.access_level if m else None)
    if got is None:
        return None
    return EffectiveAccess(got[0], got[1], m if got[1] == "MEMBER" else None)


def who_can_open(db: Session, project: Project) -> dict:
    """Everyone who can open the project, with their level and its source (§8.6, D-71; design-auditor H1): the
    platform admins; each live member of an active user with the level they hold now; and, on an open project, the
    staff by kind. The Access list, the member rows, the restriction preview and the freeze access review read this,
    never project_member on their own."""
    admins = list(db.scalars(select(AppUser).where(AppUser.is_platform_admin, AppUser.is_active)
                             .order_by(AppUser.display_name)))
    rows = db.execute(select(ProjectMember, AppUser).join(AppUser, AppUser.app_user_id == ProjectMember.app_user_id)
                      .where(ProjectMember.project_id == project.project_id, ProjectMember.is_active,
                             AppUser.is_active)
                      .order_by(ProjectMember.project_member_id)).all()
    members = []
    for m, u in rows:
        if u.is_platform_admin:          # an admin's old membership is unread while the flag holds
            level, via = "PLATFORM", "PLATFORM_ADMIN"
        else:
            level, via = level_for(u.user_kind, project.is_restricted, m.access_level)
        members.append({"member": m, "user": u, "level": level, "via": via})
    staff = None
    if not project.is_restricted:
        people = db.scalars(select(AppUser).where(AppUser.is_active, ~AppUser.is_platform_admin))
        staff = {k: 0 for k in KIND_BASE}
        for u in people:
            staff[u.user_kind] += 1
    return {"admins": admins, "members": members, "staff": staff}


def require_project(db: Session, user: AppUser, project_id: int, min_level: str,
                    component: str | tuple[str, ...] | None = None, share_lock: bool = True) -> EffectiveAccess:
    """404 → 403 → 409, in that fixed order (slice7_schema §5.2)."""
    eff = access_to(db, user, db.get(Project, project_id))
    if eff is None:
        raise HTTPException(404, NOT_FOUND)
    if not rank_ok(eff.level, min_level):
        raise HTTPException(403, "Your access to this project does not allow that")
    if share_lock and min_level in ("EDIT", "ADMIN"):
        # wave 1g N3: every project write holds the project row FOR KEY SHARE before any row lock or code lookup, so a
        # code-list re-point (FOR UPDATE, services/code_lists) never interleaves with a save that picked a code.
        # KEY SHARE, not SHARE: it still conflicts with the re-point, but not with a plain UPDATE of the project row, so
        # two PATCHes of one project meet at row_version (409), never in a deadlock (sara 1g M1). PLATFORM routes are
        # left out: some of them take the row FOR UPDATE themselves.
        db.execute(select(Project.project_id).where(Project.project_id == project_id)
                   .with_for_update(read=True, key_share=True))          # FOR KEY SHARE
    if component and rank_ok(min_level, "EDIT"):         # writes only, admins too (Q-20)
        from services import components
        components.require_on(db, project_id, component)
    return eff


def visible_program_ids(db: Session, user: AppUser) -> set[int] | None:
    """None means ALL. Staff see a program while at least one of its live projects is visible to
    them, so a program whose every project is restricted from them is hidden (auditor Q2)."""
    if user.is_platform_admin:
        return None
    ids = visible_project_ids(db, user)
    if not ids:
        return set()
    return set(db.scalars(select(Project.program_id).where(Project.project_id.in_(ids),
                                                           Project.program_id.is_not(None))))


def require_program(db: Session, user: AppUser, program_id: int, min_level: str) -> EffectiveAccess:
    """A program level above VIEW comes only from the platform flag (and, with slice B, a program membership) —
    never from the staff default (D-71; design-auditor H2). Seeing a program through its projects is VIEW."""
    g = db.get(Program, program_id)
    if user.is_platform_admin:
        if g is None:                                     # M2 — admins get 404s too
            raise HTTPException(404, NOT_FOUND)
        return ADMIN_ACCESS
    if g is None or not g.is_active or program_id not in visible_program_ids(db, user):
        raise HTTPException(404, NOT_FOUND)
    if not rank_ok("VIEW", min_level):
        raise HTTPException(403, "Your access does not allow that")
    return EffectiveAccess("VIEW", "STAFF", None)
