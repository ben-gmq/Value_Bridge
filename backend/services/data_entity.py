"""Data entities and their logical fields (§7.4, D-26, §5.4.17). de_number is minted at save;
fk_group_no is assigned here from the relationship the request names (S1-7)."""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import BfcNode, BrDataEntity, BusinessRequirement, DataEntity, DataField
from services import numbering
from services.code_master import validate_required_code
from services import lifecycle

MAX_FIELDS = 999                  # S1-3 (fields have no hierarchy code)


def list_entities(db: Session, project_id: int, include_retired: bool = False) -> list[DataEntity]:
    q = select(DataEntity).where(DataEntity.project_id == project_id)
    if not include_retired:
        q = q.where(DataEntity.is_active)
    return list(db.scalars(q.order_by(DataEntity.de_number)))


def create_entity(db: Session, actor_id: int, project_id: int, name: str, description: str | None,
                  business_owner_note: str | None) -> DataEntity:
    de = DataEntity(project_id=project_id, de_number=numbering.next_number(db, project_id, "DE"),
                    de_name=name, description=description,
                    business_owner_note=business_owner_note, created_by=actor_id)
    db.add(de)
    db.commit()
    return de


def update_entity(db: Session, actor_id: int, de: DataEntity, row_version: int, fields: dict) -> DataEntity:
    lifecycle.check_live(de, row_version)
    for k in ("de_name", "description", "business_owner_note"):
        if k in fields:
            setattr(de, k, fields[k])
    de.updated_by = actor_id
    db.commit()
    return de


def list_fields(db: Session, de: DataEntity, include_retired: bool = False) -> list[DataField]:
    q = select(DataField).where(DataField.data_entity_id == de.data_entity_id)
    if not include_retired:
        q = q.where(DataField.is_active)
    return list(db.scalars(q.order_by(DataField.is_active.desc(), DataField.seq_no)))


def _apply(db: Session, de: DataEntity, f: DataField, spec: dict) -> None:
    """Validate and set everything but the name and position. `spec` holds only sent keys."""
    if "data_type_code" in spec:
        code = spec["data_type_code"]
        f.data_type_code_id = (validate_required_code(db, de.project_id, "FIELD_DATA_TYPE", code,
                                                      "data_type_code").code_id if code else None)
    for k in ("length_val", "precision_val", "scale_val", "is_mandatory", "description"):
        if k in spec:
            setattr(f, k, spec[k])
    if "is_primary_key" in spec or "pk_ordinal" in spec:
        f.is_primary_key = spec.get("is_primary_key", f.is_primary_key)
        f.pk_ordinal = spec.get("pk_ordinal", f.pk_ordinal) if f.is_primary_key else None
        if f.is_primary_key and f.pk_ordinal is None:
            raise HTTPException(422, "A primary-key field needs its position in the key (pk_ordinal)")
    if "ref_data_entity_id" not in spec and ({"ref_data_field_id", "fk_group"} & spec.keys()):
        raise HTTPException(422, "Send ref_data_entity_id with ref_data_field_id or fk_group")   # L5
    if "ref_data_entity_id" in spec:
        target_id = spec["ref_data_entity_id"]
        if target_id is None:
            f.is_foreign_key, f.ref_data_entity_id, f.ref_data_field_id, f.fk_group_no = False, None, None, None
            return
        target = db.get(DataEntity, target_id)
        if target is None or target.project_id != de.project_id or not target.is_active:
            raise HTTPException(422, "A foreign key points at an active entity in this project")
        ref_field_id = spec.get("ref_data_field_id")
        if ref_field_id is not None:
            rf = db.get(DataField, ref_field_id)
            if rf is None or rf.data_entity_id != target.data_entity_id or not rf.is_active:
                raise HTTPException(422, "The referenced field must belong to the referenced entity")
        group = spec.get("fk_group", "new")
        f.is_foreign_key, f.ref_data_entity_id, f.ref_data_field_id = True, target_id, ref_field_id
        f.fk_group_no = _group_no(db, de, target_id, group, f)


def _group_no(db: Session, de: DataEntity, target_id: int, group, field: DataField) -> int:
    """§5.4.17: 'new' starts a relationship; an existing number extends a composite one."""
    used = set(db.scalars(select(DataField.fk_group_no).where(
        DataField.data_entity_id == de.data_entity_id, DataField.ref_data_entity_id == target_id,
        DataField.is_active, DataField.data_field_id != (field.data_field_id or 0))))
    if group == "new":
        return max(used, default=0) + 1
    if isinstance(group, int) and group in used:
        return group
    raise HTTPException(422, "fk_group must be 'new' or an existing relationship number to that entity")


def create_field(db: Session, actor_id: int, de: DataEntity, name: str, spec: dict) -> DataField:
    if not de.is_active:
        raise HTTPException(409, f"{de.de_number} is retired. Restore it first.")
    last = db.scalar(select(func.max(DataField.seq_no)).where(
        DataField.data_entity_id == de.data_entity_id, DataField.is_active)) or 0
    if last + 1 > MAX_FIELDS:
        raise HTTPException(422, f"An entity holds at most {MAX_FIELDS} fields")
    f = DataField(project_id=de.project_id, data_entity_id=de.data_entity_id, seq_no=last + 1,
                  field_name=name, created_by=actor_id)
    _apply(db, de, f, spec)
    db.add(f)
    db.commit()
    return f


def update_field(db: Session, actor_id: int, f: DataField, row_version: int, name: str | None,
                 spec: dict) -> DataField:
    lifecycle.check_live(f, row_version)
    de = db.get(DataEntity, f.data_entity_id)
    if name is not None:
        f.field_name = name
    _apply(db, de, f, spec)
    f.updated_by = actor_id
    db.commit()
    db.refresh(f)                 # reload the code relationship with the new id
    return f


def restore_field(db: Session, actor_id: int, f: DataField) -> DataField:
    """sara M3: a retired field whose position was taken comes back at the end."""
    def _free(row: DataField) -> None:
        taken = db.scalar(select(func.count()).select_from(DataField).where(
            DataField.data_entity_id == row.data_entity_id, DataField.is_active,
            DataField.seq_no == row.seq_no))
        if taken:
            row.seq_no = (db.scalar(select(func.max(DataField.seq_no)).where(
                DataField.data_entity_id == row.data_entity_id, DataField.is_active)) or 0) + 1
    lifecycle.restore(db, actor_id, f, before_activate=_free)
    return f


def used_by(db: Session, de: DataEntity) -> list[dict]:
    """The entity page's "Used by requirements": one row per live BR, its CRUD letters merged."""
    rows = db.execute(select(BusinessRequirement.br_id, BusinessRequirement.br_number,
                             BfcNode.hier_code, BfcNode.node_name, BrDataEntity.crud_code)
                      .join(BrDataEntity, BrDataEntity.br_id == BusinessRequirement.br_id)
                      .join(BfcNode, BfcNode.bfc_node_id == BusinessRequirement.bfc_node_id)
                      .where(BrDataEntity.data_entity_id == de.data_entity_id, BrDataEntity.is_active,
                             BusinessRequirement.is_active)
                      .order_by(BusinessRequirement.br_number)).all()
    out: dict[int, dict] = {}
    for br_id, number, code, name, crud in rows:
        r = out.setdefault(br_id, {"br_id": br_id, "br_number": number, "hier_code": code,
                                   "node_name": name, "crud": ""})
        r["crud"] = "".join(c for c in "CRUD" if c in r["crud"] + crud)
    return list(out.values())
