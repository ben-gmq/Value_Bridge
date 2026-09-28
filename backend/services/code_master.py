"""THE single source of truth for code_master resolution (finding D12, §7.12).
A project override shadows the global row of the same category + code."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import CodeMaster


def resolve(db: Session, project_id: int | None, category: str) -> list[CodeMaster]:
    rows = db.scalars(
        select(CodeMaster).where(
            CodeMaster.category == category,
            CodeMaster.is_active,
            (CodeMaster.project_id == project_id) | CodeMaster.project_id.is_(None)
            if project_id is not None else CodeMaster.project_id.is_(None),
        )
    ).all()
    overrides = {r.code for r in rows if r.project_id is not None}
    kept = [r for r in rows if r.project_id is not None or r.code not in overrides]
    return sorted(kept, key=lambda r: (r.sort_order, r.code))


def validate_required_code(db: Session, project_id: int | None, category: str,
                           code: str | None, field_name: str) -> CodeMaster:
    """422 if missing, 400 if not an active code in this scope (scaffold §4)."""
    if not code:
        raise HTTPException(422, f"{field_name} is required")
    for row in resolve(db, project_id, category):
        if row.code == code:
            return row
    raise HTTPException(400, f"{field_name}: '{code}' is not a valid {category} code")
