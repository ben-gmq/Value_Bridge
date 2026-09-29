"""External parties (D-24a). ext_number is minted at save ('EXT' series)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import ExternalEntity
from services import numbering
from services.code_master import validate_required_code
from services import lifecycle


def _kind(db: Session, project_id: int, code: str | None) -> int | None:
    return validate_required_code(db, project_id, "EXTERNAL_ENTITY_KIND", code, "kind_code").code_id \
        if code else None      # kind is optional (a missing kind is a report warning, §5.3); a wrong one is 400


def list_parties(db: Session, project_id: int) -> list[ExternalEntity]:
    return list(db.scalars(select(ExternalEntity).where(ExternalEntity.project_id == project_id,
                                                        ExternalEntity.is_active)
                           .order_by(ExternalEntity.ext_number)))


def create_party(db: Session, actor_id: int, project_id: int, name: str, kind_code: str | None,
                 description: str | None) -> ExternalEntity:
    ext = ExternalEntity(project_id=project_id, ext_number=numbering.next_number(db, project_id, "EXT"),
                         ext_name=name, kind_code_id=_kind(db, project_id, kind_code),
                         description=description, created_by=actor_id)
    db.add(ext)
    db.commit()
    return ext


def update_party(db: Session, actor_id: int, ext: ExternalEntity, row_version: int, fields: dict) -> ExternalEntity:
    lifecycle.check_live(ext, row_version)
    if "ext_name" in fields:
        ext.ext_name = fields["ext_name"]
    if "description" in fields:
        ext.description = fields["description"]
    if "kind_code" in fields:
        ext.kind_code_id = _kind(db, ext.project_id, fields["kind_code"])
    ext.updated_by = actor_id
    db.commit()
    return ext
