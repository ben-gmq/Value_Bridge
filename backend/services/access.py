"""The single visibility guard (§7.8, §9.10, §9.11). Every list and detail query passes through
it; nothing else in the app decides who can see a project.

A project you cannot see does not exist: that is a 404, never a 403.
"""
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AppUser, CodeMaster, Project, UserAccessGrant

PROJECT_ROLE_RANK = {"REVIEWER": 1, "EDITOR": 2, "OWNER": 3}
NOT_FOUND = "Not found"


@dataclass(frozen=True)
class EffectiveGrant:
    role: str                      # OWNER / EDITOR / REVIEWER, or ADMIN
    via: str                       # PROJECT / PROGRAM / PLATFORM_ADMIN
    grant: UserAccessGrant | None


ADMIN_GRANT = EffectiveGrant("ADMIN", "PLATFORM_ADMIN", None)


def live_grant(db: Session, user: AppUser) -> UserAccessGrant | None:
    """The ONE active grant (D-32). The partial unique index guarantees at most one."""
    return db.scalars(
        select(UserAccessGrant).where(UserAccessGrant.app_user_id == user.app_user_id,
                                      UserAccessGrant.is_active)
    ).one_or_none()


def grant_role(db: Session, grant: UserAccessGrant) -> str:
    return db.get(CodeMaster, grant.project_role_code_id).code


def visible_project_ids(db: Session, user: AppUser) -> set[int] | None:
    """None means ALL (platform admin). Program membership is read here, per request, so a
    project moved out of a program disappears from its holders' next request (§7.8)."""
    if user.is_platform_admin:
        return None
    g = live_grant(db, user)
    if g is None:
        return set()
    if g.project_id is not None:
        return {g.project_id}
    return set(db.scalars(select(Project.project_id).where(Project.program_id == g.program_id,
                                                            Project.is_active)))


def _rank_ok(role: str, min_role: str) -> bool:
    return PROJECT_ROLE_RANK[role] >= PROJECT_ROLE_RANK[min_role]


def require_project(db: Session, user: AppUser, project_id: int, min_role: str) -> EffectiveGrant:
    if user.is_platform_admin:
        if db.get(Project, project_id) is None:
            raise HTTPException(404, NOT_FOUND)
        return ADMIN_GRANT
    g = live_grant(db, user)
    p = db.get(Project, project_id)
    if g is None or p is None or not p.is_active:
        raise HTTPException(404, NOT_FOUND)
    if g.project_id == project_id:
        via = "PROJECT"
    elif g.program_id is not None and p.program_id == g.program_id:
        via = "PROGRAM"
    else:
        raise HTTPException(404, NOT_FOUND)
    role = grant_role(db, g)
    if not _rank_ok(role, min_role):
        raise HTTPException(403, "Your role on this project does not allow that")
    return EffectiveGrant(role, via, g)


def require_program(db: Session, user: AppUser, program_id: int, min_role: str) -> EffectiveGrant:
    """Program roll-ups need a PROGRAM grant (or admin). A project grant inside the program
    sees no roll-up (R2-S2)."""
    if user.is_platform_admin:
        return ADMIN_GRANT
    g = live_grant(db, user)
    if g is None or g.program_id != program_id:
        raise HTTPException(404, NOT_FOUND)
    role = grant_role(db, g)
    if not _rank_ok(role, min_role):
        raise HTTPException(403, "Your role on this program does not allow that")
    return EffectiveGrant(role, "PROGRAM", g)
