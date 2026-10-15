"""Clients, projects, restriction and members (§7.10; D-40, OR-6, slice7_schema §8)."""
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AppUser, Client, Program, Project, ProjectMember
from services import access, audit, components, effort, numbering
from services import dfd_rule as dfd_rule_service
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
                   project_name: str, program_id: int | None, start_date, end_date, *,
                   component_codes, is_restricted: bool, template_code: str | None = None,
                   data_model_depth: str = "FULL", dfd_rule: dict | None = None) -> Project:
    """Platform admin only (route guard). Creating a project grants nobody anything (D-32); it is
    asked whether the project is restricted (§8.10 risk 1), and the answer is audited.
    Its components (D-37) are inserted in the same transaction; the list must be closed under
    their dependencies, and the template is provenance only."""
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
    if data_model_depth not in components.DEPTHS:
        raise HTTPException(400, f"data_model_depth: '{data_model_depth}' is not one of KEYS_ONLY, FULL")
    if template_code is not None:
        components.template_components(db, template_code)          # 400 if unknown
    status = validate_required_code(db, None, "PROJECT_STATUS", "PLANNING", "status")
    p = Project(client_id=client_id, program_id=program_id,
                project_code=project_code.strip().upper(), project_name=project_name.strip(),
                start_date=start_date, end_date=end_date, status_code_id=status.code_id,
                data_model_depth=data_model_depth, is_restricted=is_restricted,
                created_by=actor.app_user_id)
    db.add(p)
    db.flush()
    numbering.seed_all(db, p.project_id)            # all ten series, same transaction (R2-D14)
    cells = effort.seed_rate_card(db, p.project_id, actor.app_user_id)   # same transaction (§7.10, S6c-1)
    on = components.initial_rows(db, p.project_id, component_codes, actor.app_user_id)   # D-37
    rule = dfd_rule_service.initial_rows(db, p.project_id, dfd_rule, actor.app_user_id)  # D-70 (Q-4), same tx
    # A later slice copies CONTROL_RULE house defaults here (§7.13).
    audit.record(db, "PROJECT_CREATED", actor_id=actor.app_user_id, project_id=p.project_id,
                 detail={"program_id": program_id, **cells, "template_code": template_code,
                         "components": on, "data_model_depth": data_model_depth, "dfd_rule": rule,
                         "is_restricted": is_restricted})
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


# ---- members and restriction (OR-6, slice7_schema §8.3–§8.4; admin only by route guard) ----

def _staff(db: Session) -> list[AppUser]:
    return list(db.scalars(select(AppUser).where(AppUser.is_active, ~AppUser.is_platform_admin)
                           .order_by(AppUser.display_name)))


def _live_members(db: Session, project_id: int) -> list[ProjectMember]:
    """Live memberships of active users (sara 7b L8: a deactivated user opens nothing)."""
    return list(db.scalars(select(ProjectMember).join(AppUser, AppUser.app_user_id == ProjectMember.app_user_id)
                           .where(ProjectMember.project_id == project_id, ProjectMember.is_active,
                                  AppUser.is_active)
                           .order_by(ProjectMember.project_member_id)))


def _share_lock(db: Session, project_id: int) -> None:
    """Member writes and a restriction confirm serialise on the project row (sara 7b L1)."""
    db.execute(select(Project.project_id).where(Project.project_id == project_id).with_for_update(read=True))


def _person(u: AppUser) -> dict:
    return {"user_id": u.app_user_id, "display_name": u.display_name, "user_kind": u.user_kind}


def _member_row(db: Session, m: ProjectMember) -> dict:
    u = db.get(AppUser, m.app_user_id)
    return {**_person(u), "project_member_id": m.project_member_id, "access_level": m.access_level,
            "effective_level": access._lower(access.KIND_CAP[u.user_kind], m.access_level),
            "member_note": m.member_note, "row_version": m.row_version}


def list_members(db: Session, project: Project) -> list[dict]:
    return [_member_row(db, m) for m in _live_members(db, project.project_id)]


def add_member(db: Session, actor: AppUser, project: Project, user_id: int, access_level: str,
               member_note: str | None) -> tuple[ProjectMember, list[str]]:
    _share_lock(db, project.project_id)
    target = db.get(AppUser, user_id)
    if target is None or not target.is_active:
        raise HTTPException(422, "Choose an active user")
    if target.is_platform_admin:
        raise HTTPException(422, "A platform admin sees every project and needs no membership")
    if access.live_member(db, project.project_id, user_id) is not None:
        raise HTTPException(409, f"{target.display_name} is already a member of this project")
    m = ProjectMember(project_id=project.project_id, app_user_id=user_id, access_level=access_level,
                      member_note=(member_note or "").strip() or None, created_by=actor.app_user_id)
    db.add(m)
    db.flush()                    # uq_pm_live is the backstop against a concurrent add (→ 409)
    audit.record(db, "MEMBER_ADDED", actor_id=actor.app_user_id, project_id=project.project_id,
                 target_table="project_member", target_id=m.project_member_id,
                 detail={"user_id": user_id, "access_level": access_level})
    db.commit()
    warnings = (["VIEWER_CAPPED"] if access_level == "EDIT" and target.user_kind == "VIEWER" else [])
    return m, warnings


def change_member_level(db: Session, actor: AppUser, m: ProjectMember, access_level: str,
                        row_version: int) -> ProjectMember:
    _share_lock(db, m.project_id)
    if not m.is_active:
        raise HTTPException(409, "That membership was already removed")
    if m.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")
    if m.access_level != access_level:
        old, m.access_level = m.access_level, access_level
        m.updated_by = actor.app_user_id
        audit.record(db, "MEMBER_LEVEL_CHANGED", actor_id=actor.app_user_id, project_id=m.project_id,
                     target_table="project_member", target_id=m.project_member_id,
                     detail={"user_id": m.app_user_id, "from": old, "to": access_level})
    db.commit()
    return m


def remove_member(db: Session, actor: AppUser, m: ProjectMember, row_version: int) -> None:
    """Soft-remove (law 1); never restored — access returns only through add (R2-S5)."""
    _share_lock(db, m.project_id)
    if not m.is_active:
        raise HTTPException(409, "That membership was already removed")
    if m.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")
    soft_delete(m, actor.app_user_id)
    audit.record(db, "MEMBER_REMOVED", actor_id=actor.app_user_id, project_id=m.project_id,
                 target_table="project_member", target_id=m.project_member_id,
                 detail={"user_id": m.app_user_id})
    db.commit()


def set_restriction(db: Session, actor: AppUser, project: Project, restricted: bool,
                    confirm_hash: str | None) -> dict:
    """§8.3 + DR7-D2: preview who loses or gains access AND who keeps it (each member with the note
    that explains why, e.g. a copied grant), inside the hash; then confirm. Audited."""
    def plan() -> dict:
        members = {m.app_user_id: m for m in _live_members(db, project.project_id)}
        staff = _staff(db)
        # DR10c-S1: a kept member whose level is lower behind the wall than in the open (a USER kept at VIEW,
        # e.g. copied from an old grant) is flagged, so the admin raises it before or after confirming.
        def drops(row: dict) -> bool:
            open_level = access.KIND_CAP[row["user_kind"]]
            return (restricted and not project.is_restricted
                    and access.LEVEL_RANK[row["effective_level"]] < access.LEVEL_RANK[open_level])
        keeps = [{**row, "level_drops": drops(row)} for row in
                 (_member_row(db, members[u.app_user_id]) for u in staff if u.app_user_id in members)]
        others = [_person(u) for u in staff if u.app_user_id not in members]
        return {"restricted": restricted, "changed": restricted != project.is_restricted,
                "loses": others if restricted and not project.is_restricted else [],
                "gains": others if not restricted and project.is_restricted else [],
                "keeps": keeps}
    preview = plan()
    h = hashlib.sha256(json.dumps(preview, sort_keys=True, default=str).encode()).hexdigest()
    if confirm_hash is None:
        return {**preview, "confirm_hash": h, "applied": False}
    db.refresh(project, with_for_update=True)                 # sara 7b L1: re-read under the lock
    preview = plan()
    if hashlib.sha256(json.dumps(preview, sort_keys=True, default=str).encode()).hexdigest() != confirm_hash:
        raise HTTPException(409, "Who can see this project changed since the preview. Review it again.")
    if not preview["changed"]:
        db.rollback()
        return {**preview, "confirm_hash": confirm_hash, "applied": False}
    project.is_restricted = restricted
    project.updated_by = actor.app_user_id
    audit.record(db, "PROJECT_RESTRICTED" if restricted else "PROJECT_UNRESTRICTED",
                 actor_id=actor.app_user_id, project_id=project.project_id, target_table="project",
                 target_id=project.project_id,
                 detail={"members": [{"user_id": k["user_id"], "access_level": k["access_level"]}
                                     for k in preview["keeps"]],
                         "loses": [x["user_id"] for x in preview["loses"]],
                         "gains": [x["user_id"] for x in preview["gains"]]})
    db.commit()
    return {**preview, "confirm_hash": confirm_hash, "applied": True}


def effective_access(db: Session, project: Project) -> dict:
    """Everyone who can open the project, and why (§8.6). Admin only, by route guard. The access
    review at each freeze reads this (§4.7)."""
    admins = [_person(u) for u in db.scalars(select(AppUser).where(AppUser.is_platform_admin, AppUser.is_active)
                                             .order_by(AppUser.display_name))]
    members = list_members(db, project)
    if project.is_restricted:
        return {"is_restricted": True, "admins": admins, "members": members, "staff": None}
    staff = _staff(db)
    counts = {k: sum(1 for u in staff if u.user_kind == k) for k in access.KIND_CAP}
    return {"is_restricted": False, "admins": admins, "members": members, "staff": counts}
