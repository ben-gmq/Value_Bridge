"""Interface detail and the generated interface list (§7.5 describe_interface, §4.4 interface_list,
D-27, A-55). Spec: docs/slice6b2_spec.md; schema: docs/slice6b_schema.md §4–§7.

The PUT is one transaction: every scope, liveness and code check runs before the first write, the
carried set changes only through the no-commit lifecycle helpers, and it commits once (DR6b2-P3).
The detail row is locked FOR UPDATE and its row_version is bumped on every successful PUT, so a
change to the carried set alone still makes a stale tab's save a 409 (DR6b2-P1).

Only an FR whose type *behaves* as INTERFACE carries detail (criterion 102) — never a code test."""
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from models import Application, CodeMaster, DataEntity, FrInterface, FrInterfaceDataEntity, FunctionRequirement
from schemas.interface import CarriedIn
from services import audit, errors, lifecycle
from services.code_master import validate_required_code

INTERFACE = "INTERFACE"
CODES = (("pattern_code", "pattern_code_id", "INTERFACE_PATTERN"), ("method_code", "method_code_id", "INTERFACE_METHOD"),
         ("frequency_code", "frequency_code_id", "INTERFACE_FREQUENCY"))
AUDITED = ("source_application_id", "target_application_id", "pattern_code_id", "method_code_id",
           "frequency_code_id", "volume_note")


def _stale() -> HTTPException:
    return HTTPException(409, errors.CONFLICT, headers=errors.STALE_HEADERS)


def _live_fr(db: Session, fr: FunctionRequirement, write: bool = True) -> None:
    lifecycle.lock_for_share(db, fr)
    if not fr.is_active:                                   # DR6b2-P4
        raise HTTPException(409, f"{lifecycle.label(fr)} is retired. Restore it first.")
    if write and fr.fr_type_behaviour != INTERFACE:        # behaviour, never the code (102)
        raise HTTPException(422, "Only an interface-type function requirement carries interface detail")


def _scoped(db: Session, model, pk_col, ids: list[int], project_id: int) -> dict[int, object]:
    """Fetched within the FR's project before any lock or label: a foreign or missing id is 404."""
    rows = {getattr(r, pk_col.key): r for r in db.scalars(select(model).where(pk_col.in_(ids),
                                                                                model.project_id == project_id))}
    if len(rows) != len(set(ids)):
        raise HTTPException(404, "Not found")
    return rows


# ---- read ---------------------------------------------------------------------------------------
def read_interface(db: Session, fr: FunctionRequirement) -> dict:
    fi = db.get(FrInterface, fr.fr_id)
    if fi is None:
        return {"described": False, "is_active": False, "row_version": None, "carried": []}
    carried = db.execute(select(FrInterfaceDataEntity, DataEntity).join(
        DataEntity, DataEntity.data_entity_id == FrInterfaceDataEntity.data_entity_id).where(
        FrInterfaceDataEntity.fr_id == fr.fr_id, FrInterfaceDataEntity.is_active).order_by(DataEntity.de_number)).all()
    return {"described": fi.is_active, "is_active": fi.is_active, "row_version": fi.row_version,
            "source_application_id": fi.source_application_id, "target_application_id": fi.target_application_id,
            "source_application_code": fi.source_row.application_code, "target_application_code": fi.target_row.application_code,
            "pattern_code": fi.pattern_code, "method_code": fi.method_code, "frequency_code": fi.frequency_code,
            "volume_note": fi.volume_note,
            "carried": [{"data_entity_id": de.data_entity_id, "de_number": de.de_number, "de_name": de.de_name,
                         "note": c.note} for c, de in carried]}


# ---- describe (PUT) -----------------------------------------------------------------------------
def describe_interface(db: Session, actor_id: int, fr: FunctionRequirement, body) -> dict:
    """`body` is schemas.interface.InterfaceIn: carried items whose `note` was not sent keep theirs."""
    _live_fr(db, fr)
    src, tgt = body.source_application_id, body.target_application_id
    if src == tgt:
        raise HTTPException(422, "Source and target must be different applications")
    wanted = {c.data_entity_id: c for c in body.carried}
    if len(wanted) != len(body.carried):
        raise HTTPException(422, "A data entity is listed twice")                          # DR6b2-D2
    apps = _scoped(db, Application, Application.application_id, [src, tgt], fr.project_id)
    des = _scoped(db, DataEntity, DataEntity.data_entity_id, sorted(wanted), fr.project_id) if wanted else {}
    for row in [apps[i] for i in sorted(apps)] + [des[i] for i in sorted(des)]:            # id order
        lifecycle.lock_for_share(db, row)
        if not row.is_active:
            raise HTTPException(409, f"{lifecycle.label(row)} is retired. Restore it first.")
    codes = {col: (validate_required_code(db, fr.project_id, cat, getattr(body, field), field).code_id
                   if getattr(body, field) else None) for field, col, cat in CODES}
    fi = db.get(FrInterface, fr.fr_id)
    if fi is not None:
        lifecycle.lock(db, fi)                                                             # FOR UPDATE (DR6b2-P1)
        if body.row_version is None or fi.row_version != body.row_version:                 # update / restore (P2)
            raise _stale()
    # ---- every check has passed; the writes start here (DR6b2-P3) ----
    values = {"source_application_id": src, "target_application_id": tgt, "volume_note": body.volume_note, **codes}
    if fi is None:
        fi = new_detail(db, actor_id, fr, values)
    else:
        previous = {k: getattr(fi, k) for k in AUDITED}
        if not fi.is_active:
            fi.is_active, fi.deleted_at, fi.deleted_by = True, None, None
            audit.record(db, "RECORD_RESTORED", actor_id=actor_id, project_id=fi.project_id, target_table="fr_interface",
                         target_id=fi.fr_id, detail={"label": lifecycle.label(fi)})
        for k, v in values.items():
            setattr(fi, k, v)
        changed = {k: previous[k] for k in AUDITED if previous[k] != values[k]}
        if changed:                                                                        # DR6b2-S1
            detail = {f"previous_{k}": v for k, v in changed.items() if k in ("volume_note",)}
            for k in ("source_application_id", "target_application_id"):
                if k in changed:
                    detail[f"previous_{k.split('_')[0]}_application_code"] = db.get(Application, changed[k]).application_code
            for field, col, _ in CODES:
                if col in changed:
                    detail[f"previous_{field}"] = _code_of(db, changed[col])
            audit.record(db, "RECORD_UPDATED", actor_id=actor_id, project_id=fi.project_id, target_table="fr_interface",
                         target_id=fi.fr_id, detail={"label": lifecycle.label(fi), **detail})
        fi.updated_by = actor_id
        flag_modified(fi, "volume_note")                   # always an UPDATE: the version covers the set (P1)
        db.flush()
    _replace_carried(db, actor_id, fi, wanted)
    db.commit()
    db.refresh(fr)
    return read_interface(db, fr)


def _code_of(db: Session, code_id: int | None) -> str | None:
    if code_id is None:
        return None
    return db.get(CodeMaster, code_id).code


def new_detail(db: Session, actor_id: int, fr: FunctionRequirement, values: dict) -> FrInterface:
    """THE one place a new interface detail row is created (sara 11c M1): the PUT and "Create interface FR from these
    flows" both come here. No checks, no commit — the callers have checked liveness and own the transaction."""
    fi = FrInterface(fr_id=fr.fr_id, project_id=fr.project_id, created_by=actor_id, **values)
    db.add(fi)
    db.flush()
    return fi


def create_detail(db: Session, actor_id: int, fr: FunctionRequirement, source_application_id: int,
                  target_application_id: int, carried: dict[int, str | None]) -> FrInterface:
    """A new interface on a new FR with its carried entities and their notes, inside the caller's transaction
    (slice 11c seeding). Shares new_detail and the carried-set writer with the PUT, so both stay identical."""
    fi = new_detail(db, actor_id, fr, {"source_application_id": source_application_id,
                                       "target_application_id": target_application_id})
    _replace_carried(db, actor_id, fi, {de: CarriedIn(data_entity_id=de, note=note) for de, note in carried.items()})
    return fi


def _replace_carried(db: Session, actor_id: int, fi: FrInterface, wanted: dict) -> None:
    rows = {r.data_entity_id: r for r in db.scalars(select(FrInterfaceDataEntity).where(
        FrInterfaceDataEntity.fr_id == fi.fr_id).with_for_update(of=FrInterfaceDataEntity))}
    for de_id, row in rows.items():
        if row.is_active and de_id not in wanted:
            lifecycle.retire_row(db, actor_id, row)
    for de_id in sorted(wanted):
        item, row = wanted[de_id], rows.get(de_id)
        note_sent = "note" in item.model_fields_set
        if row is None:
            db.add(FrInterfaceDataEntity(project_id=fi.project_id, fr_id=fi.fr_id, data_entity_id=de_id,
                                         note=item.note, created_by=actor_id))
        elif not row.is_active:
            lifecycle.relink(db, actor_id, row)
            if note_sent:
                row.note = item.note
        elif note_sent and row.note != item.note:          # S6b2-4: an untouched note is kept
            row.note, row.updated_by = item.note, actor_id
    db.flush()


# ---- remove (DELETE) ----------------------------------------------------------------------------
def remove_interface(db: Session, actor_id: int, fr: FunctionRequirement, row_version: int) -> None:
    """Carried rows retire, then the detail — one write (S6b Q-5), explicit flush order for the guard FK."""
    _live_fr(db, fr, write=False)
    fi = db.get(FrInterface, fr.fr_id)
    if fi is None or not fi.is_active:
        raise HTTPException(409, f"{fr.fr_number} has no interface detail to remove")
    lifecycle.lock(db, fi)
    lifecycle.check_version(fi, row_version)
    at = datetime.now(UTC)                                 # one action, one deleted_at (sara L3)
    for row in db.scalars(select(FrInterfaceDataEntity).where(FrInterfaceDataEntity.fr_id == fi.fr_id,
                                                              FrInterfaceDataEntity.is_active)):
        lifecycle.retire_row(db, actor_id, row, at)
    db.flush()
    lifecycle.retire_row(db, actor_id, fi, at)
    db.commit()


def live_detail_exists(db: Session, fr_id: int) -> bool:
    return db.scalar(select(FrInterface.fr_id).where(FrInterface.fr_id == fr_id, FrInterface.is_active)) is not None


# ---- the generated list -------------------------------------------------------------------------
def interface_list(db: Session, project_id: int, source: int | None = None, target: int | None = None,
                   status: str | None = None) -> dict:
    rows = [dict(r) for r in db.execute(text(
        "SELECT * FROM v_interface_list WHERE project_id = :p ORDER BY interface_number"), {"p": project_id}).mappings()]
    carried: dict[int, list] = {}
    for fr_id, de_number, de_name, note in db.execute(select(
            FrInterfaceDataEntity.fr_id, DataEntity.de_number, DataEntity.de_name, FrInterfaceDataEntity.note).join(
            DataEntity, DataEntity.data_entity_id == FrInterfaceDataEntity.data_entity_id).where(
            FrInterfaceDataEntity.project_id == project_id, FrInterfaceDataEntity.is_active, DataEntity.is_active)
            .order_by(DataEntity.de_number)):
        carried.setdefault(fr_id, []).append({"de_number": de_number, "de_name": de_name, "note": note})
    out, unfilterable = [], 0
    for r in rows:
        r["carried"] = carried.get(r["fr_id"], [])
        missing = [m for m, ok in (("endpoints", r["is_described"]), ("method", bool(r["method_code"])),
                                   ("data_entities", bool(r["carried"]))) if not ok]
        r["missing"], r["is_complete"] = missing, not missing                               # S6b2-1
        if status and r["fulfilment_status_code"] != status:
            continue
        if source is not None or target is not None:
            if not r["is_described"]:
                unfilterable += 1                                                           # S6b2-2
                continue
            if not _pair_matches(r, source, target):
                continue
        out.append(r)
    return {"rows": out, "unfilterable_incomplete": unfilterable}


def _pair_matches(r: dict, source: int | None, target: int | None) -> bool:
    """S6b2-3: direction as stored; a BIDIRECTIONAL interface matches either way round."""
    def fits(s, t):
        return (source is None or s == source) and (target is None or t == target)
    src, tgt = r["source_application_id"], r["target_application_id"]
    return fits(src, tgt) or (r["pattern_code"] == "BIDIRECTIONAL" and fits(tgt, src))


# ---- consistency_check --------------------------------------------------------------------------
def interface_under_inactive(db: Session, project_id: int | None) -> list[dict]:
    """Live detail whose FR or an endpoint is retired; live carried rows whose detail or entity is
    retired. Must be empty."""
    p = "" if project_id is None else "AND fi.project_id = :p"
    q = text(f"""
        SELECT fi.fr_id, NULL::bigint AS data_entity_id FROM fr_interface fi
        JOIN function_requirement fr ON fr.fr_id = fi.fr_id
        JOIN application sa ON sa.application_id = fi.source_application_id
        JOIN application ta ON ta.application_id = fi.target_application_id
        WHERE fi.is_active AND NOT (fr.is_active AND sa.is_active AND ta.is_active) {p}
        UNION ALL
        SELECT fide.fr_id, fide.data_entity_id FROM fr_interface_data_entity fide
        JOIN fr_interface fi ON fi.fr_id = fide.fr_id
        JOIN data_entity de ON de.data_entity_id = fide.data_entity_id
        WHERE fide.is_active AND NOT (fi.is_active AND de.is_active) {p}
        ORDER BY 1, 2""")
    return [dict(r) for r in db.execute(q, {"p": project_id}).mappings()]
