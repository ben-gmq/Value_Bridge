"""Data-model consistency lines (slice 4a rule 4a-R10), for consistency_check to wire in.

`entities_without_fields` is a WARNING line, never must-be-0: a live entity with no live field —
a half-built model (e.g. a data-model workbook whose fields step has not run yet) is never
invisible. Freezing a baseline warns about these and still allows it (Ben, 2026-10-09)."""
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from models import DataEntity, DataField, Project
from services import components


def entities_without_fields(db: Session, project_id: int) -> list[dict]:
    has_field = exists().where(DataField.data_entity_id == DataEntity.data_entity_id, DataField.is_active)
    rows = db.execute(select(DataEntity.data_entity_id, DataEntity.de_number, DataEntity.de_name)
                      .where(DataEntity.project_id == project_id, DataEntity.is_active, ~has_field)
                      .order_by(DataEntity.de_number)).all()
    return [{"data_entity_id": i, "de_number": n, "de_name": name} for i, n, name in rows]


def entities_keys_only(db: Session, project_id: int) -> list[dict]:
    """D-39: on a FULL-depth project, a live entity whose live fields are all keys (PK or FK) —
    it has keys but no other attributes. Never listed on a KEYS_ONLY project. A WARNING line."""
    project = db.get(Project, project_id)
    if project is None or components.depth(project) != "FULL":       # an unknown id holds nothing
        return []
    has_field = exists().where(DataField.data_entity_id == DataEntity.data_entity_id, DataField.is_active)
    has_attr = exists().where(DataField.data_entity_id == DataEntity.data_entity_id, DataField.is_active,
                              ~DataField.is_primary_key, ~DataField.is_foreign_key)
    rows = db.execute(select(DataEntity.data_entity_id, DataEntity.de_number, DataEntity.de_name)
                      .where(DataEntity.project_id == project_id, DataEntity.is_active, has_field, ~has_attr)
                      .order_by(DataEntity.de_number)).all()
    return [{"data_entity_id": i, "de_number": n, "de_name": name} for i, n, name in rows]
