"""Clients, projects and access grants (§7.10, D-32). One grant per user, over one scope."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AppUser, Client, CodeMaster, Program, Project, UserAccessGrant
from services import access, audit, numbering
from services.lifecycle import soft_delete
from services.code_master import validate_required_code


# ---- clients --------------------------------------------------------------------------

def list_clients(db: Session) -> list[Client]:
    return list(db.scalars(select(Client).where(Client.is_active).order_by(Client.client_name)))


def create_client(db: Session, actor: AppUser, client_code: str, client_name: str,
                  industry: str | None) -> Client:
    c = Client(client_code=client_code.strip().upper(), client_name=client_name.strip(),
               industry=industry, created_by=actor.app_user_id)
    db.add(c)
    db.flush()
    audit.record(db, "CLIENT_CREATED", actor_id=actor.app_user_id, target_table="client",
                 target_id=c.client_id)
    db.commit()
    return c


# ---- projects -------------------------------------------------------------------------

def get_project(db: Session, project_id: int) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "Not found")
    return p


def _check_dates(start_date, end_date) -> None:
    if start_date and end_date and end_date < start_date:
        raise HTTPException(422, "The end date is before the start date")   # L5


def list_visible_projects(db: Session, user: AppUser) -> list[Project]:
    ids = access.visible_project_ids(db, user)
    q = select(Project).where(Project.is_active).order_by(Project.project_code)
    if ids is not None:
        if not ids:
            return []
        q = q.where(Project.project_id.in_(ids))
    return list(db.scalars(q))


def create_project(db: Session, actor: AppUser, client_id: int, project_code: str,
                   project_name: str, program_id: int | None, start_date, end_date) -> Project:
    """Platform admin only (route guard). Creating a project grants nobody anything (D-32)."""
    client = db.get(Client, client_id)
    if client is None or not client.is_active:
        raise HTTPException(422, "Choose an active client")
    if program_id is not None:
        prog = db.get(Program, program_id)
        if prog is None or not prog.is_active:
            raise HTTPException(422, "Choose an active program")
        if prog.client_id != client_id:
            raise HTTPException(422, "A program's projects belong to its client")
    _check_dates(start_date, end_date)
    status = validate_required_code(db, None, "PROJECT_STATUS", "PLANNING", "status")
    p = Project(client_id=client_id, program_id=program_id,
                project_code=project_code.strip().upper(), project_name=project_name.strip(),
                start_date=start_date, end_date=end_date, status_code_id=status.code_id,
                created_by=actor.app_user_id)
    db.add(p)
    db.flush()
    numbering.seed_all(db, p.project_id)            # all ten series, same transaction (R2-D14)
    # Later slices add here: seed EFFORT_RATE and copy CONTROL_RULE house defaults (§7.13).
    audit.record(db, "PROJECT_CREATED", actor_id=actor.app_user_id, project_id=p.project_id,
                 detail={"program_id": program_id})
    db.commit()
    return p


def update_project(db: Session, actor: AppUser, project: Project, row_version: int,
                   fields: dict) -> Project:
    if project.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")
    _check_dates(fields.get("start_date", project.start_date), fields.get("end_date", project.end_date))
    for k in ("project_name", "start_date", "end_date"):   # program_id is not PATCHable (§9)
        if k in fields:
            setattr(project, k, fields[k])
    project.updated_by = actor.app_user_id
    db.commit()
    return project


# ---- grants ---------------------------------------------------------------------------

def _role(db: Session, project_role_code: str) -> CodeMaster:
    return validate_required_code(db, None, "PROJECT_ROLE", project_role_code, "project_role_code")


def _scope_name(db: Session, g: UserAccessGrant) -> str:
    if g.project_id:
        return f"project {db.get(Project, g.project_id).project_code}"
    return f"program {db.get(Program, g.program_id).program_code}"


def grant_access(db: Session, actor: AppUser, target_user_id: int, project_role_code: str, *,
                 project_id: int | None = None, program_id: int | None = None,
                 row_version: int | None = None) -> UserAccessGrant:
    """Route guards: a project grant needs OWNER on the project — which a program OWNER holds
    for every project in their program (Q16); a program grant needs a platform admin (Q10)."""
    role = _role(db, project_role_code)
    if program_id is not None:                               # L5 — a clear 404, not an FK 409
        prog = db.get(Program, program_id)
        if prog is None or not prog.is_active:
            raise HTTPException(404, "Not found")
    target = db.get(AppUser, target_user_id)
    if target is None or not target.is_active:
        raise HTTPException(422, "Choose an active user")
    if target.is_platform_admin:
        raise HTTPException(422, "A platform admin needs no grant")
    existing = access.live_grant(db, target)
    if existing and existing.project_id == project_id and existing.program_id == program_id:
        if row_version is None:                              # M4 — D-6 on role changes too
            raise HTTPException(422, f"{target.display_name} already has access here. Send the "
                                     "grant's row_version to change their role.")
        if existing.row_version != row_version:
            raise HTTPException(409, "Updated by another user. Please refresh.")
        old = access.grant_role(db, existing)
        existing.project_role_code_id = role.code_id           # a role change, not a 2nd grant
        existing.updated_by = actor.app_user_id
        audit.record(db, "ACCESS_ROLE_CHANGED", actor_id=actor.app_user_id, project_id=project_id,
                     target_table="user_access_grant", target_id=existing.user_access_grant_id,
                     detail={"user_id": target_user_id, "from": old, "to": role.code})
        db.commit()
        return existing
    if existing:
        raise HTTPException(409, f"{target.display_name} already has access to "
                                 f"{_scope_name(db, existing)}. Only a platform admin can "
                                 f"reassign them.")                      # R2-S4
    g = UserAccessGrant(app_user_id=target_user_id, project_id=project_id, program_id=program_id,
                        project_role_code_id=role.code_id, granted_by_user_id=actor.app_user_id,
                        created_by=actor.app_user_id)
    db.add(g)
    db.flush()          # the partial unique index is the backstop against a concurrent grant
    audit.record(db, "ACCESS_GRANTED", actor_id=actor.app_user_id, project_id=project_id,
                 target_table="user_access_grant", target_id=g.user_access_grant_id,
                 detail={"user_id": target_user_id, "program_id": program_id, "role": role.code})
    db.commit()
    return g


def reassign_access(db: Session, actor: AppUser, target_user_id: int, project_role_code: str,
                    rationale: str, *, project_id: int | None = None,
                    program_id: int | None = None) -> UserAccessGrant:
    """Platform admin only. Revoke the user's one grant and issue the new one, atomically."""
    if not rationale.strip():
        raise HTTPException(422, "Moving someone between scopes needs a reason")
    if (project_id is None) == (program_id is None):
        raise HTTPException(422, "Name exactly one project or one program")
    role = _role(db, project_role_code)
    target = db.get(AppUser, target_user_id)
    if target is None or not target.is_active or target.is_platform_admin:
        raise HTTPException(422, "Choose an active, non-admin user")
    old = access.live_grant(db, target)
    old_scope = _scope_name(db, old) if old else None
    if old:
        soft_delete(old, actor.app_user_id)
        db.flush()
    g = UserAccessGrant(app_user_id=target_user_id, project_id=project_id, program_id=program_id,
                        project_role_code_id=role.code_id, granted_by_user_id=actor.app_user_id,
                        created_by=actor.app_user_id)
    db.add(g)
    db.flush()
    audit.record(db, "ACCESS_REASSIGNED", actor_id=actor.app_user_id, project_id=project_id,
                 target_table="user_access_grant", target_id=g.user_access_grant_id,
                 detail={"user_id": target_user_id, "from": old_scope,
                         "to": _scope_name(db, g), "role": role.code, "rationale": rationale})
    db.commit()
    return g


def revoke_access(db: Session, actor: AppUser, grant: UserAccessGrant) -> UserAccessGrant:
    """Soft-revoke, audited (S9), and never restorable (R2-S5)."""
    if not grant.is_active:
        raise HTTPException(409, "That access was already revoked")
    soft_delete(grant, actor.app_user_id)
    audit.record(db, "ACCESS_REVOKED", actor_id=actor.app_user_id, project_id=grant.project_id,
                 target_table="user_access_grant", target_id=grant.user_access_grant_id,
                 detail={"user_id": grant.app_user_id, "program_id": grant.program_id})
    db.commit()
    return grant


def effective_access(db: Session, project: Project) -> list[dict]:
    """Everyone who can open the project, and why (D-32). OWNER or admin, by route guard."""
    out: list[dict] = []
    direct = db.scalars(select(UserAccessGrant).where(UserAccessGrant.project_id == project.project_id,
                                                      UserAccessGrant.is_active))
    for g in direct:
        out.append(_row(db, g, "PROJECT", None))
    if project.program_id:
        prog = db.get(Program, project.program_id)
        via = db.scalars(select(UserAccessGrant).where(UserAccessGrant.program_id == project.program_id,
                                                       UserAccessGrant.is_active))
        for g in via:
            out.append(_row(db, g, "PROGRAM", prog.program_name))
    for u in db.scalars(select(AppUser).where(AppUser.is_platform_admin, AppUser.is_active)):
        out.append({"grant_id": None, "user_id": u.app_user_id, "display_name": u.display_name,
                    "email": u.email, "project_role_code": "ALL", "source": "PLATFORM_ADMIN", "program": None,
                    "granted_at": None, "row_version": None})
    order = {"PROJECT": 0, "PROGRAM": 1, "PLATFORM_ADMIN": 2}
    return sorted(out, key=lambda r: (order[r["source"]], r["display_name"].lower()))


def _row(db: Session, g: UserAccessGrant, source: str, program: str | None) -> dict:
    u = db.get(AppUser, g.app_user_id)
    return {"grant_id": g.user_access_grant_id, "user_id": u.app_user_id,
            "display_name": u.display_name, "email": u.email, "project_role_code": access.grant_role(db, g),
            "source": source, "program": program, "granted_at": g.granted_at,
            "row_version": g.row_version}
