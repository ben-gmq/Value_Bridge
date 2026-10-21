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
                status_behaviour=status.behaviour_code,                 # slice 16: PLANNING is open (0070)
                data_model_depth=data_model_depth, is_restricted=is_restricted,
                created_by=actor.app_user_id)
    db.add(p)
    db.flush()
    numbering.seed_all(db, p.project_id)            # all ten series, same transaction (R2-D14)
    cells = effort.seed_rate_card(db, p.project_id, actor.app_user_id)   # same transaction (§7.10, S6c-1)
    on = components.initial_rows(db, p.project_id, component_codes, actor.app_user_id)   # D-37
    rule = dfd_rule_service.initial_rows(db, p.project_id, dfd_rule, actor.app_user_id)  # D-70 (Q-4), same tx
    # A later slice copies CONTROL_RULE house defaults here (§7.13).
    # D-71: a project created inside a program opens at once to the program's members — restricted or not — so the
    # audit names them (design-auditor; D-62's "no members yet" no longer means "nobody sees it").
    admitted = [{"user_id": r["user"].app_user_id, "level": r["level"]}
                for r in access.who_can_open(db, p)["program_members"]] if program_id else []
    audit.record(db, "PROJECT_CREATED", actor_id=actor.app_user_id, project_id=p.project_id,
                 detail={"program_id": program_id, **cells, "template_code": template_code,
                         "components": on, "data_model_depth": data_model_depth, "dfd_rule": rule,
                         "is_restricted": is_restricted, "program_members_admitted": admitted})
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


# ---- members and restriction (OR-6, slice7_schema §8.3–§8.4; D-71, D-73) ----
# Members and the access list: project ADMIN by route guard — a project admin or a platform admin (D-71 (5)).
# Restriction: PLATFORM by route guard (D-71 (6)). Who can open the project is read only through
# access.who_can_open, so the guard and every list here agree (design-auditor H1).

def _staff(db: Session) -> list[AppUser]:
    return list(db.scalars(select(AppUser).where(AppUser.is_active, ~AppUser.is_platform_admin)
                           .order_by(AppUser.display_name)))


def _share_lock(db: Session, project_id: int) -> None:
    """Member writes and a restriction confirm serialise on the project row (sara 7b L1)."""
    db.execute(select(Project.project_id).where(Project.project_id == project_id).with_for_update(read=True))


def _user_share_lock(db: Session, user_id: int) -> None:
    """A member write and a confirmed change of that user's kind or admin flag serialise on the user row, so the
    change never revives a membership its preview did not show (user_admin._require_confirm, D-71)."""
    db.execute(select(AppUser.app_user_id).where(AppUser.app_user_id == user_id).with_for_update(read=True))


def _person(u: AppUser) -> dict:
    return {"user_id": u.app_user_id, "display_name": u.display_name, "user_kind": u.user_kind}


def _row(m: ProjectMember, u: AppUser, level: str, via: str, also_via_program: str | None = None) -> dict:
    return {**_person(u), "project_member_id": m.project_member_id, "access_level": m.access_level,
            "effective_level": level, "via": via, "member_note": m.member_note, "row_version": m.row_version,
            "also_via_program": also_via_program}


def _member_row(db: Session, m: ProjectMember) -> dict:
    """One member as the Access screen shows it, with the level they hold on the project right now."""
    p = db.get(Project, m.project_id)
    r = next((r for r in access.who_can_open(db, p)["members"]
              if r["member"].project_member_id == m.project_member_id), None) if m.is_active else None   # sara B L2
    u = db.get(AppUser, m.app_user_id)
    if r is None:                                       # a removed row, or one of a switched-off user
        return _row(m, u, m.access_level, "MEMBER")
    return _row(m, u, r["level"], r["via"], r["also_via_program"])


def list_members(db: Session, project: Project) -> list[dict]:
    return [_row(r["member"], r["user"], r["level"], r["via"], r["also_via_program"])
            for r in access.who_can_open(db, project)["members"]]


def _program_row(r: dict) -> dict:
    """A person who opens the project through its program only (D-71): no project_member row to change here."""
    return {**_person(r["user"]), "program_member_id": r["program_member"].program_member_id,
            "access_level": r["program_member"].access_level, "effective_level": r["level"], "via": r["via"],
            "program_code": r["program_code"]}


def member_candidates(db: Session, project: Project) -> list[dict]:
    """The people a project admin may add (D-71 (5)): active staff who are not platform admins and not yet live
    members. Names and kinds only — the full user list stays platform-admin only."""
    taken = set(db.scalars(select(ProjectMember.app_user_id).where(ProjectMember.project_id == project.project_id,
                                                                   ProjectMember.is_active)))
    return [_person(u) for u in _staff(db) if u.app_user_id not in taken]


def _check_level(target: AppUser, access_level: str) -> None:
    """D-71 (7): a VIEWER-kind user is refused above VIEW, never quietly capped."""
    if not access.rank_ok(access.KIND_CAP[target.user_kind], access_level):
        raise HTTPException(422, f"{target.display_name} is a viewer and can only be added as a viewer")


def add_member(db: Session, actor: AppUser, project: Project, user_id: int, access_level: str,
               member_note: str | None) -> ProjectMember:
    _share_lock(db, project.project_id)
    _user_share_lock(db, user_id)
    target = db.get(AppUser, user_id)
    if target is None or not target.is_active:
        raise HTTPException(422, "Choose an active user")
    if target.is_platform_admin:
        raise HTTPException(422, "A platform admin sees every project and needs no membership")
    _check_level(target, access_level)
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
    return m


def change_member_level(db: Session, actor: AppUser, m: ProjectMember, access_level: str,
                        row_version: int) -> ProjectMember:
    """Any project admin may change any member's level, another admin's included, whoever appointed them (D-73)."""
    _share_lock(db, m.project_id)
    _user_share_lock(db, m.app_user_id)
    if not m.is_active:
        raise HTTPException(409, "That membership was already removed")
    if m.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")
    _check_level(db.get(AppUser, m.app_user_id), access_level)
    if m.access_level != access_level:
        old, m.access_level = m.access_level, access_level
        m.updated_by = actor.app_user_id
        audit.record(db, "MEMBER_LEVEL_CHANGED", actor_id=actor.app_user_id, project_id=m.project_id,
                     target_table="project_member", target_id=m.project_member_id,
                     detail={"user_id": m.app_user_id, "from": old, "to": access_level})
    db.commit()
    return m


def remove_member(db: Session, actor: AppUser, m: ProjectMember, row_version: int) -> None:
    """Soft-remove (law 1); never restored — access returns only through add (R2-S5). A project admin may remove
    another admin (D-73), or themselves; a platform admin can always add one back."""
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
    """§8.3 + DR7-D2: preview who loses or gains access AND who keeps it, at the level they will hold (each member
    with the note that explains why), inside the hash; then confirm. Audited."""
    def plan() -> dict:
        w = access.who_can_open(db, project)
        members = {r["user"].app_user_id: r for r in w["members"] if not r["user"].is_platform_admin}
        via_program = {r["user"].app_user_id: r for r in w["program_members"] if not r["user"].is_platform_admin}
        staff = _staff(db)
        keeps, keeps_via_program = [], []
        # DR10c-S1: a kept member whose level is lower behind the wall than in the open (a USER kept at VIEW,
        # e.g. copied from an old grant) is flagged, so the admin raises it before or after confirming.
        for u in staff:
            r, g = members.get(u.app_user_id), via_program.get(u.app_user_id)
            if r is not None:
                pl = r["also_via_program"] and access.live_program_member(db, project.program_id, u.app_user_id)
                level, via = access.level_for(u.user_kind, restricted, r["member"].access_level,
                                              pl.access_level if pl else None)
                drops = (restricted and not project.is_restricted
                         and access.LEVEL_RANK[level] < access.LEVEL_RANK[r["level"]])
                keeps.append({**_row(r["member"], u, level, via, r["also_via_program"]), "level_drops": drops})
            elif g is not None:                       # D-71: a program role keeps them in (design-auditor H1)
                level, via = access.level_for(u.user_kind, restricted, None, g["program_member"].access_level)
                keeps_via_program.append({**_program_row({**g, "level": level, "via": via}),
                                          "level_drops": restricted and not project.is_restricted
                                          and access.LEVEL_RANK[level] < access.LEVEL_RANK[g["level"]]})
        others = [_person(u) for u in staff if u.app_user_id not in members and u.app_user_id not in via_program]
        return {"restricted": restricted, "changed": restricted != project.is_restricted,
                "loses": others if restricted and not project.is_restricted else [],
                "gains": others if not restricted and project.is_restricted else [],
                "keeps": keeps, "keeps_via_program": keeps_via_program}
    preview = plan()
    h = hashlib.sha256(json.dumps(preview, sort_keys=True, default=str).encode()).hexdigest()
    if confirm_hash is None:
        return {**preview, "confirm_hash": h, "applied": False}
    seen_program = project.program_id
    lock_program(db, seen_program)                            # D-71 / design-auditor M2: program, then project
    db.refresh(project, with_for_update=True)                 # sara 7b L1: re-read under the lock
    if project.program_id != seen_program:                    # sara B L1: moved meanwhile — its program is unlocked
        raise HTTPException(409, "Who can see this project changed since the preview. Review it again.")
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
    """Everyone who can open the project, and why (§8.6, D-71). Project admin, by route guard. The access review at
    each freeze reads this (§4.7, D-72)."""
    w = access.who_can_open(db, project)
    return {"is_restricted": project.is_restricted, "admins": [_person(u) for u in w["admins"]],
            "members": [_row(r["member"], r["user"], r["level"], r["via"], r["also_via_program"]) for r in w["members"]],
            "program_members": [_program_row(r) for r in w["program_members"]],
            "staff": w["staff"]}


def lock_program(db: Session, *program_ids: int | None) -> None:
    """The lock order every write that changes who reaches a project through a program follows (D-71; design-auditor
    M2): the program row(s) FOR UPDATE in ascending id, then the project. Program-member writes take the program row
    FOR SHARE, so a member added mid-confirm waits, and the recomputed preview sees it."""
    for pid in sorted({p for p in program_ids if p is not None}):
        db.execute(select(Program.program_id).where(Program.program_id == pid).with_for_update())
