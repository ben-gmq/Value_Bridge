"""Programs (§7.10a, D-32): a header, an access scope and a set of reads. It owns no business
data, so it has no SQL over business tables — roll-ups call the per-project reports."""
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AppUser, Client, Program, Project, UserAccessGrant
from services import access, audit


def get_program(db: Session, program_id: int) -> Program:
    p = db.get(Program, program_id)
    if p is None:
        raise HTTPException(404, "Not found")
    return p


def list_visible_programs(db: Session, user: AppUser) -> list[Program]:
    ids = access.visible_program_ids(db, user)          # M8 — visibility has one owner
    q = select(Program).where(Program.is_active).order_by(Program.program_code)
    if ids is not None:
        if not ids:
            return []
        q = q.where(Program.program_id.in_(ids))
    return list(db.scalars(q))


def create_program(db: Session, actor: AppUser, client_id: int, program_code: str,
                   program_name: str, description: str | None) -> Program:
    client = db.get(Client, client_id)
    if client is None or not client.is_active:
        raise HTTPException(422, "Choose an active client")
    p = Program(client_id=client_id, program_code=program_code.strip().upper(),
                program_name=program_name.strip(), description=description,
                created_by=actor.app_user_id)
    db.add(p)
    db.flush()
    audit.record(db, "PROGRAM_CREATED", actor_id=actor.app_user_id, target_table="program",
                 target_id=p.program_id)
    db.commit()
    return p


def program_projects(db: Session, user: AppUser, program_id: int) -> list[Project]:
    """The roll-up rule (R2-S2): only projects in visible_project_ids(user) ∩ program."""
    ids = access.visible_project_ids(db, user)
    q = select(Project).where(Project.program_id == program_id, Project.is_active)
    if ids is not None:
        q = q.where(Project.project_id.in_(ids or {-1}))
    return list(db.scalars(q.order_by(Project.project_code)))


def _holders(db: Session, program_id: int | None) -> list[dict]:
    if program_id is None:
        return []
    rows = db.scalars(select(UserAccessGrant).where(UserAccessGrant.program_id == program_id,
                                                    UserAccessGrant.is_active))
    return sorted(({"user_id": g.app_user_id, "display_name": db.get(AppUser, g.app_user_id).display_name,
                    "project_role_code": access.grant_role(db, g)} for g in rows), key=lambda r: r["user_id"])


def move_project_program(db: Session, actor: AppUser, project_id: int,
                         target_program_id: int | None, confirm_hash: str | None,
                         expected_from_program_id: int | None = None) -> dict:
    """Platform admin only (Q10). Step 1 (no hash) previews who gains and loses access and
    writes nothing; step 2 applies it only if the preview is unchanged (R2-S3)."""
    p = db.get(Project, project_id)
    if p is None or not p.is_active:
        raise HTTPException(404, "Not found")
    if expected_from_program_id is not None and p.program_id != expected_from_program_id:
        raise HTTPException(404, "Not found")              # M1 — not in THIS program
    t = db.get(Program, target_program_id) if target_program_id else None
    if target_program_id and (t is None or not t.is_active):
        raise HTTPException(422, "Choose an active program")
    if t and t.client_id != p.client_id:
        raise HTTPException(422, "A program's projects belong to its client")
    if (p.program_id or None) == (target_program_id or None):
        raise HTTPException(422, "The project is already there")
    preview = {"project": p.project_code, "from_program_id": p.program_id,
               "to_program_id": target_program_id,
               "gains": _holders(db, target_program_id), "loses": _holders(db, p.program_id)}
    h = hashlib.sha256(json.dumps(preview, sort_keys=True).encode()).hexdigest()
    if confirm_hash is None:
        return {"preview": preview, "preview_hash": h, "applied": False}
    if confirm_hash != h:
        raise HTTPException(409, "Who gains or loses access changed since the preview. "
                                 "Review it again.")
    p.program_id = target_program_id
    p.updated_by = actor.app_user_id
    audit.record(db, "PROJECT_PROGRAM_CHANGED", actor_id=actor.app_user_id, project_id=project_id,
                 detail=preview)
    db.commit()
    return {"preview": preview, "preview_hash": h, "applied": True}
