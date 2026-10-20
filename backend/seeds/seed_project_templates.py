"""Seed the three project templates' components (OR-3, slice7_schema §3). Run from backend/, after
seeds.seed_code_master:  python -m seeds.seed_project_templates
Idempotent: inserts missing (template, component) rows and restores retired ones. Seeds go here via
CLI — never in Alembic (§13)."""
from sqlalchemy import select

from database import SessionLocal
from models import CodeMaster, ProjectTemplateComponent

TEMPLATES: dict[str, tuple[str, ...]] = {
    "REQUIREMENTS_ONLY": ("ISSUE",),
    "DATA_AND_PROCESS": ("TO_BE_DFD", "AS_IS", "APPLICATION", "ISSUE"),
    "FULL_DELIVERY": ("SOLUTION", "FUNCTION_REQUIREMENT", "APPLICATION", "EFFORT", "ISSUE",
                      "TO_BE_DFD", "BENEFIT", "RISK", "CHANGE_REQUEST", "WBS", "PHASING"),
}


def _code(db, category: str, code: str) -> CodeMaster:
    return db.scalars(select(CodeMaster).where(CodeMaster.project_id.is_(None),
                                               CodeMaster.category == category,
                                               CodeMaster.code == code)).one()


def seed(db) -> int:
    added = 0
    for template, components in TEMPLATES.items():
        t = _code(db, "PROJECT_TEMPLATE", template)
        for comp in components:
            c = _code(db, "PROJECT_COMPONENT", comp)
            row = db.scalars(select(ProjectTemplateComponent).where(
                ProjectTemplateComponent.template_code_id == t.code_id,
                ProjectTemplateComponent.component_code_id == c.code_id)).one_or_none()
            if row is None:
                db.add(ProjectTemplateComponent(template_code_id=t.code_id, component_code_id=c.code_id))
                added += 1
            elif not row.is_active:
                row.is_active, row.deleted_at, row.deleted_by = True, None, None
                added += 1
    db.commit()
    return added


if __name__ == "__main__":
    with SessionLocal() as session:
        print(f"project templates: {seed(session)} rows added or restored")
