"""The single visibility guard (§7.8, §9.10, §9.11; D-40, D-71, slice7_schema §8.6). Every list and detail
query passes through it; nothing else in the app decides who can see a project, or at what level.

Platform admins see everything, at PLATFORM — the one level above ADMIN, never held by a membership; it guards the
FTC-only project settings (D-71 (6)). Every other user's level on a project is the HIGHER of its sources, capped by
their kind (D-71 (4)):
  - STAFF:   the project is open → KIND_BASE (USER → EDIT, VIEWER → VIEW)
  - MEMBER:  a live project_member → its level (ADMIN / EDIT / VIEW)
  - PROGRAM: a live program_member of the project's live program → its level, restricted projects included (D-71 (2))
and no source at all (a restricted project they reach by none of them) is None → 404. KIND_CAP is the ceiling any
source can lift a kind to (USER → ADMIN, VIEWER → VIEW): never the default (design-auditor H2).

A project you cannot see does not exist: that is a 404, never a 403.
"""
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AppUser, Program, ProgramMember, Project, ProjectMember, ProjectPurge

LEVEL_RANK = {"VIEW": 1, "EDIT": 2, "ADMIN": 3, "PLATFORM": 4}
KIND_BASE = {"USER": "EDIT", "VIEWER": "VIEW"}       # what staff get on an open project (D-40)
KIND_CAP = {"USER": "ADMIN", "VIEWER": "VIEW"}       # the most any source lifts a kind to (D-71); + CLIENT_VIEWER: VIEW
NOT_FOUND = "Not found"


@dataclass(frozen=True)
class EffectiveAccess:
    level: str                     # VIEW / EDIT / ADMIN / PLATFORM
    via: str                       # PLATFORM_ADMIN / MEMBER / PROGRAM / STAFF
    member: ProjectMember | None


ADMIN_ACCESS = EffectiveAccess("PLATFORM", "PLATFORM_ADMIN", None)


def rank_ok(level: str, min_level: str) -> bool:
    return LEVEL_RANK[level] >= LEVEL_RANK[min_level]


def _lower(a: str, b: str) -> str:
    return a if LEVEL_RANK[a] <= LEVEL_RANK[b] else b


def level_for(user_kind: str, restricted: bool, member_level: str | None,
              program_level: str | None = None) -> tuple[str, str] | None:
    """(level, via) for a staff user of this kind, on a project open or restricted, with or without a live project and
    program membership; None when they cannot open it. The one place a staff level is computed: access_to,
    who_can_open and the user-type preview all call it, so the guard and every list agree (design-auditor H1). On a
    tie the source shown is MEMBER, then PROGRAM, then STAFF. An unknown kind raises: fails closed."""
    sources = []
    if member_level is not None:
        sources.append((member_level, "MEMBER"))
    if program_level is not None:
        sources.append((program_level, "PROGRAM"))
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


def live_program_member(db: Session, program_id: int | None, user_id: int) -> ProgramMember | None:
    """The user's live membership of a LIVE program, or None."""
    if program_id is None:
        return None
    return db.scalars(select(ProgramMember).join(Program, Program.program_id == ProgramMember.program_id).where(
        ProgramMember.program_id == program_id, ProgramMember.app_user_id == user_id, ProgramMember.is_active,
        Program.is_active)).one_or_none()


def visible_project_ids(db: Session, user: AppUser) -> set[int] | None:
    """None means ALL (platform admin). Restriction and both memberships are read per request, so restricting a
    project, removing a member or moving a project hides it on the user's next request."""
    if user.is_platform_admin:
        return None
    open_ = set(db.scalars(select(Project.project_id).where(Project.is_active, ~Project.is_restricted)))
    members = set(db.scalars(select(Project.project_id).join(
        ProjectMember, ProjectMember.project_id == Project.project_id).where(
        ProjectMember.app_user_id == user.app_user_id, ProjectMember.is_active,
        Project.is_active, Project.is_restricted)))
    via_program = set(db.scalars(select(Project.project_id).join(
        Program, Program.program_id == Project.program_id).join(
        ProgramMember, ProgramMember.program_id == Program.program_id).where(
        ProgramMember.app_user_id == user.app_user_id, ProgramMember.is_active, Program.is_active,
        Project.is_active, Project.is_restricted)))
    return open_ | members | via_program


def access_to(db: Session, user: AppUser, p: Project | None) -> EffectiveAccess | None:
    """The user's access to one project, or None when they cannot see it."""
    if user.is_platform_admin:
        return ADMIN_ACCESS if p is not None else None
    if p is None or not p.is_active:
        return None
    m = live_member(db, p.project_id, user.app_user_id)
    g = live_program_member(db, p.program_id, user.app_user_id)
    got = level_for(user.user_kind, p.is_restricted, m.access_level if m else None, g.access_level if g else None)
    if got is None:
        return None
    return EffectiveAccess(got[0], got[1], m if got[1] == "MEMBER" else None)


def who_can_open(db: Session, project: Project) -> dict:
    """Everyone who can open the project, with their level and its source (§8.6, D-71; design-auditor H1): the
    platform admins; each live direct member of an active user, at the level they hold now (direct and program roles
    together), with the program they ALSO hold a role through; each live member of the project's live program who is
    not a direct member; and, on an open project, the staff by kind. The Access list, the member rows, the restriction
    preview and the freeze access review read this, never a membership table on their own."""
    admins = list(db.scalars(select(AppUser).where(AppUser.is_platform_admin, AppUser.is_active)
                             .order_by(AppUser.display_name)))
    program = db.get(Program, project.program_id) if project.program_id else None
    via_program: dict[int, tuple[ProgramMember, AppUser]] = {}
    if program is not None and program.is_active:
        for g, u in db.execute(select(ProgramMember, AppUser).join(AppUser, AppUser.app_user_id == ProgramMember.app_user_id)
                               .where(ProgramMember.program_id == program.program_id, ProgramMember.is_active,
                                      AppUser.is_active).order_by(ProgramMember.program_member_id)).all():
            via_program[u.app_user_id] = (g, u)
    rows = db.execute(select(ProjectMember, AppUser).join(AppUser, AppUser.app_user_id == ProjectMember.app_user_id)
                      .where(ProjectMember.project_id == project.project_id, ProjectMember.is_active,
                             AppUser.is_active)
                      .order_by(ProjectMember.project_member_id)).all()

    def level(u: AppUser, m_level: str | None, g_level: str | None) -> tuple[str, str]:
        if u.is_platform_admin:              # an admin's old memberships are unread while the flag holds
            return "PLATFORM", "PLATFORM_ADMIN"
        return level_for(u.user_kind, project.is_restricted, m_level, g_level)

    members = []
    for m, u in rows:
        g = via_program.get(u.app_user_id)
        lv, via = level(u, m.access_level, g[0].access_level if g else None)
        members.append({"member": m, "user": u, "level": lv, "via": via,
                        "also_via_program": program.program_code if g else None})
    direct = {u.app_user_id for _, u in rows}
    program_members = []
    for uid, (g, u) in via_program.items():
        if uid in direct:
            continue
        lv, via = level(u, None, g.access_level)
        program_members.append({"program_member": g, "user": u, "level": lv, "via": via,
                                "program_code": program.program_code})
    staff = None
    if not project.is_restricted:
        people = db.scalars(select(AppUser).where(AppUser.is_active, ~AppUser.is_platform_admin))
        staff = {k: 0 for k in KIND_BASE}
        for u in people:
            staff[u.user_kind] += 1
    return {"admins": admins, "members": members, "program_members": program_members, "staff": staff}


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
    if min_level != "VIEW":                              # slice 16 Q-73, R17: every write, platform settings included
        require_not_pending(db, project_id)
    if component and rank_ok(min_level, "EDIT"):         # writes only, admins too (Q-20)
        from services import components
        components.require_on(db, project_id, component)
    return eff


PENDING_HEADERS = {"X-VB-Error": "PURGE_PENDING"}


def pending_project_ids(db: Session) -> set[int]:
    """Every project with an open ARCHIVE or DELETE request — for the writes that reach many projects at once."""
    return set(db.scalars(select(ProjectPurge.project_id).where(
        ProjectPurge.purge_kind.in_(("ARCHIVE", "DELETE")), ProjectPurge.executed_at.is_(None),
        ProjectPurge.cancelled_at.is_(None))))


def require_not_pending(db: Session, project_id: int) -> None:
    """Slice 16 (Q-73): while a request to remove this project is open, every write to it is refused (409
    PURGE_PENDING), so the archive file and the purge see a project that no longer changes. Reads still work. Called by
    require_project for every write level, and by the services behind platform-only writes that reach a project."""
    if db.scalar(select(ProjectPurge.project_purge_id).where(
            ProjectPurge.project_id == project_id, ProjectPurge.purge_kind.in_(("ARCHIVE", "DELETE")),
            ProjectPurge.executed_at.is_(None), ProjectPurge.cancelled_at.is_(None)).limit(1)) is not None:
        raise HTTPException(409, "A request to remove this project is open: it cannot be changed until the request "
                                 "is cancelled", headers=PENDING_HEADERS)


def visible_program_ids(db: Session, user: AppUser) -> set[int] | None:
    """None means ALL. Staff see a program while at least one of its live projects is visible to them, or while they
    are a live member of it — so a program admin opens an empty program (design-auditor L3), and a program whose every
    project is restricted from a non-member stays hidden (auditor Q2)."""
    if user.is_platform_admin:
        return None
    ids = visible_project_ids(db, user)
    via_projects = set(db.scalars(select(Project.program_id).where(Project.project_id.in_(ids or {-1}),
                                                                    Project.program_id.is_not(None))))
    mine = set(db.scalars(select(ProgramMember.program_id).where(ProgramMember.app_user_id == user.app_user_id,
                                                                 ProgramMember.is_active)))
    return via_projects | mine


def require_program(db: Session, user: AppUser, program_id: int, min_level: str) -> EffectiveAccess:
    """A program level above VIEW comes only from the platform flag or a live program membership, capped by kind —
    never from the staff default (D-71; design-auditor H2). Seeing a program only through its projects is VIEW."""
    g = db.get(Program, program_id)
    if user.is_platform_admin:
        if g is None:                                     # M2 — admins get 404s too
            raise HTTPException(404, NOT_FOUND)
        return ADMIN_ACCESS
    if g is None or not g.is_active or program_id not in visible_program_ids(db, user):
        raise HTTPException(404, NOT_FOUND)
    pm = live_program_member(db, program_id, user.app_user_id)
    eff = (EffectiveAccess(_lower(KIND_CAP[user.user_kind], pm.access_level), "PROGRAM", None) if pm
           else EffectiveAccess("VIEW", "STAFF", None))
    if not rank_ok(eff.level, min_level):
        raise HTTPException(403, "Your access does not allow that")
    return eff
