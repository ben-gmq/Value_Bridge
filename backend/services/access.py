"""The single visibility guard (§7.8, §9.10, §9.11; D-40, slice7_schema §8.6). Every list and detail
query passes through it; nothing else in the app decides who can see a project.

Admins (`is_platform_admin`) see everything. Every other user sees every live project except a
restricted one they are not a live member of, at the level their kind allows: USER → EDIT,
VIEWER → VIEW, and on a restricted project the lower of that and the membership's level.

A project you cannot see does not exist: that is a 404, never a 403.
"""
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AppUser, Program, Project, ProjectMember

LEVEL_RANK = {"VIEW": 1, "EDIT": 2, "ADMIN": 3}
KIND_CAP = {"USER": "EDIT", "VIEWER": "VIEW"}        # + CLIENT_VIEWER: VIEW with D-43 (§8.7)
NOT_FOUND = "Not found"


@dataclass(frozen=True)
class EffectiveAccess:
    level: str                     # VIEW / EDIT / ADMIN
    via: str                       # PLATFORM_ADMIN / STAFF / MEMBER
    member: ProjectMember | None


ADMIN_ACCESS = EffectiveAccess("ADMIN", "PLATFORM_ADMIN", None)


def rank_ok(level: str, min_level: str) -> bool:
    return LEVEL_RANK[level] >= LEVEL_RANK[min_level]


def _lower(a: str, b: str) -> str:
    return a if LEVEL_RANK[a] <= LEVEL_RANK[b] else b


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
    cap = KIND_CAP[user.user_kind]                       # an unknown kind raises: fails closed
    if p.is_restricted:
        m = live_member(db, p.project_id, user.app_user_id)
        if m is None:
            return None
        return EffectiveAccess(_lower(cap, m.access_level), "MEMBER", m)
    return EffectiveAccess(cap, "STAFF", None)


def require_project(db: Session, user: AppUser, project_id: int, min_level: str,
                    component: str | tuple[str, ...] | None = None) -> EffectiveAccess:
    """404 → 403 → 409, in that fixed order (slice7_schema §5.2)."""
    eff = access_to(db, user, db.get(Project, project_id))
    if eff is None:
        raise HTTPException(404, NOT_FOUND)
    if not rank_ok(eff.level, min_level):
        raise HTTPException(403, "Your access to this project does not allow that")
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
    g = db.get(Program, program_id)
    if user.is_platform_admin:
        if g is None:                                     # M2 — admins get 404s too
            raise HTTPException(404, NOT_FOUND)
        return ADMIN_ACCESS
    if g is None or not g.is_active or program_id not in visible_program_ids(db, user):
        raise HTTPException(404, NOT_FOUND)
    level = KIND_CAP[user.user_kind]
    if not rank_ok(level, min_level):
        raise HTTPException(403, "Your access does not allow that")
    return EffectiveAccess(level, "STAFF", None)
