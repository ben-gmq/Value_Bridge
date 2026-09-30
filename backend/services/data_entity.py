"""Data entities and their logical fields (§7.4, D-26, §5.4.17). de_number is minted at save;
fk_group_no is assigned here from the relationship the request names (S1-7)."""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import BfcNode, BfcNodeDataEntity, BrDataEntity, BusinessRequirement, DataEntity, DataField
from services import diagram_layout, numbering
from services.code_master import validate_required_code
from services import lifecycle
from services.process_flow import _steps_under

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
        # Same target: the field may keep its own relationship number, and does if none is sent.
        own = f.fk_group_no if f.data_field_id and f.ref_data_entity_id == target_id else None
        group = spec.get("fk_group", own if own is not None else "new")
        f.is_foreign_key, f.ref_data_entity_id, f.ref_data_field_id = True, target_id, ref_field_id
        f.fk_group_no = own if own is not None and group == own else _group_no(db, de, target_id, group, f)


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


# ---- the logical ERD (§7.4 generate_erd, D-29, §5.4.17; Slice 3 spec §7 3b) -----------------

def _field_order(f: DataField) -> tuple:
    """PK rows by pk_ordinal, then FK rows, then attributes, the last two by seq_no."""
    if f.is_primary_key:
        return (0, f.pk_ordinal or 0, f.seq_no)
    return (1 if f.is_foreign_key else 2, f.seq_no, 0)


def _area_entity_ids(db: Session, project_id: int, node_id: int) -> set[int]:
    """The entities in the active I/O of the processes under a node (A-S3-7: any active node)."""
    node = db.get(BfcNode, node_id)
    if node is None or node.project_id != project_id or not node.is_active:
        raise HTTPException(404, "Not found")
    step_ids = [node.bfc_node_id] if node.is_process else [s.bfc_node_id for s in _steps_under(db, node)]
    if not step_ids:
        return set()
    return set(db.scalars(select(BfcNodeDataEntity.data_entity_id).where(
        BfcNodeDataEntity.bfc_node_id.in_(step_ids), BfcNodeDataEntity.is_active)))


def generate_erd(db: Session, project_id: int, subject_area_node_id: int | None = None) -> dict:
    """The project's (or one subject area's) entities, their ordered fields, one relationship per
    FK group (data_entity, ref_data_entity, fk_group_no), stubs for groups leaving the area, and
    the saved positions. Nothing is stored; the diagram is exactly as complete as the model."""
    entities = list_entities(db, project_id)
    if subject_area_node_id is not None:
        area = _area_entity_ids(db, project_id, subject_area_node_id)
        entities = [e for e in entities if e.data_entity_id in area]
    in_scope = {e.data_entity_id: e for e in entities}
    fields = list(db.scalars(select(DataField).where(
        DataField.data_entity_id.in_(list(in_scope)), DataField.is_active))) if in_scope else []
    by_de: dict[int, list[DataField]] = {}
    for f in fields:
        by_de.setdefault(f.data_entity_id, []).append(f)

    parent_ids = {f.ref_data_entity_id for f in fields if f.is_foreign_key}
    parents = {d.data_entity_id: d for d in db.scalars(select(DataEntity).where(
        DataEntity.data_entity_id.in_(parent_ids)))} if parent_ids else {}
    ref_ids = {f.ref_data_field_id for f in fields if f.is_foreign_key and f.ref_data_field_id}
    ref_fields = {r.data_field_id: r for r in db.scalars(select(DataField).where(
        DataField.data_field_id.in_(ref_ids)))} if ref_ids else {}

    def _field(f: DataField) -> dict:
        parent = parents.get(f.ref_data_entity_id) if f.is_foreign_key else None
        return {"data_field_id": f.data_field_id, "field_name": f.field_name,
                "data_type_code": f.data_type_code, "is_mandatory": f.is_mandatory,
                "is_primary_key": f.is_primary_key, "pk_ordinal": f.pk_ordinal,
                "is_foreign_key": f.is_foreign_key, "ref_data_entity_id": f.ref_data_entity_id,
                "ref_data_field_id": f.ref_data_field_id, "fk_group_no": f.fk_group_no,
                "ref_de_name": parent.de_name if parent else None, "description": f.description}

    out_entities, relationships, outside_refs = [], [], []
    for de in entities:
        own = sorted(by_de.get(de.data_entity_id, []), key=_field_order)
        pk_set = {f.data_field_id for f in own if f.is_primary_key}
        out_entities.append({"data_entity_id": de.data_entity_id, "de_number": de.de_number,
                             "de_name": de.de_name, "description": de.description,
                             "field_count": len(own), "fields": [_field(f) for f in own],
                             "warnings": [] if pk_set else ["NO_KEY"]})
        groups: dict[tuple[int, int], list[DataField]] = {}
        for f in own:
            if f.is_foreign_key:
                groups.setdefault((f.ref_data_entity_id, f.fk_group_no), []).append(f)
        for (parent_id, group_no), g in groups.items():
            parent = parents[parent_id]
            ids = {f.data_field_id for f in g}
            rel = {"child_data_entity_id": de.data_entity_id, "parent_data_entity_id": parent_id,
                   "parent_de_number": parent.de_number, "parent_de_name": parent.de_name,
                   "fk_group_no": group_no, "label": ", ".join(f.field_name for f in g),
                   "via_fields": [{"data_field_id": f.data_field_id, "field_name": f.field_name,
                                   "ref_data_field_id": f.ref_data_field_id,
                                   "ref_is_key": bool(f.ref_data_field_id in ref_fields
                                                      and (ref_fields[f.ref_data_field_id].is_primary_key
                                                           or ref_fields[f.ref_data_field_id].is_foreign_key)
                                                      and ref_fields[f.ref_data_field_id].is_active)}
                                  for f in g],
                   "parent_cardinality": "1" if all(f.is_mandatory is True for f in g) else "0..1",
                   "child_cardinality": "1" if pk_set and ids == pk_set else "many",
                   "identifying": all(f.is_primary_key for f in g),
                   "retired": not parent.is_active}
            (relationships if parent.is_active and parent_id in in_scope else outside_refs).append(rel)
    return {"scope_key": diagram_layout.PROJECT_SCOPE if subject_area_node_id is None
            else str(subject_area_node_id),
            "entities": out_entities, "relationships": relationships, "outside_refs": outside_refs,
            "layout": diagram_layout.positions(db, project_id, "ERD", subject_area_node_id)}
