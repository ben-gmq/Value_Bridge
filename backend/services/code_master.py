"""THE single source of truth for code_master resolution (finding D12, §7.12).
A project override shadows the global row of the same category + code. Writes to the lists: services/code_lists."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import CodeMaster, ProjectCodeVisibility


def resolve(db: Session, project_id: int | None, category: str, for_picker: bool = False) -> list[CodeMaster]:
    """`for_picker` drops the company codes this project hid (wave 1g, G-1). The default — display, validation, the
    application's own lookups — is unfiltered, so a row holding a hidden code still shows and saves it (R5)."""
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
    if for_picker and project_id is not None:
        hidden = hidden_codes(db, project_id, category)
        kept = [r for r in kept if r.code not in hidden]
    return sorted(kept, key=lambda r: (r.sort_order, r.code))


def for_display(db: Session, project_id: int, category: str, for_picker: bool = False) -> list[dict]:
    """The project's codes of a category with `is_hidden` marking the ones it hid — the shape the screens read."""
    hidden = hidden_codes(db, project_id, category)
    return [{c.key: getattr(r, c.key) for c in CodeMaster.__table__.columns} | {"is_hidden": r.code in hidden}
            for r in resolve(db, project_id, category, for_picker=for_picker)]


def hidden_codes(db: Session, project_id: int, category: str) -> set[str]:
    """Codes of `category` this project hid — by code, so an override of a hidden company code is hidden too."""
    return set(db.scalars(select(CodeMaster.code).join(
        ProjectCodeVisibility, ProjectCodeVisibility.code_id == CodeMaster.code_id).where(
        ProjectCodeVisibility.project_id == project_id, ProjectCodeVisibility.is_active,
        CodeMaster.category == category)))


def validate_required_code(db: Session, project_id: int | None, category: str,
                           code: str | None, field_name: str) -> CodeMaster:
    """422 if missing, 400 if not an active code in this scope (scaffold §4)."""
    if not code:
        raise HTTPException(422, f"{field_name} is required")
    for row in resolve(db, project_id, category):
        if row.code == code:
            return row
    raise HTTPException(400, f"{field_name}: '{code}' is not a valid {category} code")
