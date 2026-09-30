"""Saved diagram positions (D-29, D-30, S2-6) — the ONLY writer of DIAGRAM_LAYOUT (§13).

Presentation, not scope: last write wins per object, no row_version, never baselined (A-52).
A PUT upserts only the objects it lists; reset is its own audited hard delete (Q-13). The
request names an object by type + id; the type picks the one typed FK and is never stored.
"""
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from models import BfcNode, BfcNodeFlow, DataEntity, DiagramLayout, ExternalEntity
from models.diagram import DIAGRAM_TYPES
from services import audit

OBJECTS = {                    # request object_type → (typed column, model)
    "STEP": ("bfc_node_id", BfcNode),
    "ENTITY": ("data_entity_id", DataEntity),
    "EXTERNAL": ("external_entity_id", ExternalEntity),
    "EVENT": ("bfc_node_flow_id", BfcNodeFlow),
}
PROJECT_SCOPE = "project"      # the ERD's whole-project scope key → NULL scope


def _scope(db: Session, project_id: int, diagram_type: str, scope_key: str) -> int | None:
    if diagram_type not in DIAGRAM_TYPES:
        raise HTTPException(404, "Not found")
    if scope_key == PROJECT_SCOPE:
        if diagram_type != "ERD":
            raise HTTPException(422, "A process flow or DFD is scoped to a chart node")
        return None
    if not scope_key.isdigit():
        raise HTTPException(404, "Not found")
    node = db.get(BfcNode, int(scope_key))
    if node is None or node.project_id != project_id or not node.is_active:
        raise HTTPException(404, "Not found")
    if diagram_type != "ERD" and node.is_process:           # Q-14: scope validated here, not by FK
        raise HTTPException(422, "A process flow is drawn for a parent node, not a step")
    return node.bfc_node_id


def _where(project_id: int, diagram_type: str, scope_id: int | None):
    scope = DiagramLayout.scope_bfc_node_id.is_(None) if scope_id is None \
        else DiagramLayout.scope_bfc_node_id == scope_id
    return (DiagramLayout.project_id == project_id, DiagramLayout.diagram_type == diagram_type, scope)


def _out(r: DiagramLayout) -> dict:
    kind, col = next((k, c) for k, (c, _) in OBJECTS.items() if getattr(r, c) is not None)
    return {"object_type": kind, "object_id": getattr(r, col), "x": float(r.x), "y": float(r.y),
            "w": float(r.width) if r.width is not None else None,
            "h": float(r.height) if r.height is not None else None, "collapsed": r.is_collapsed}


def positions(db: Session, project_id: int, diagram_type: str, scope_id: int | None) -> list[dict]:
    return [_out(r) for r in db.scalars(select(DiagramLayout).where(*_where(project_id, diagram_type, scope_id))
                                        .order_by(DiagramLayout.diagram_layout_id))]


def get(db: Session, project_id: int, diagram_type: str, scope_key: str) -> list[dict]:
    return positions(db, project_id, diagram_type, _scope(db, project_id, diagram_type, scope_key))


def _check_object(db: Session, project_id: int, diagram_type: str, kind: str, object_id: int) -> str:
    if kind not in OBJECTS:
        raise HTTPException(422, "object_type must be STEP, ENTITY, EXTERNAL or EVENT")
    col, model = OBJECTS[kind]
    if diagram_type == "ERD" and kind != "ENTITY":
        raise HTTPException(422, "An ERD places data entities only")
    if kind == "EVENT" and diagram_type != "PROCESS_FLOW":
        raise HTTPException(422, "Start and end events belong to the process flow")
    obj = db.get(model, object_id)
    if obj is None or obj.project_id != project_id:
        raise HTTPException(422, f"{kind.title()} {object_id} is not in this project")
    if kind == "EVENT" and None not in (obj.from_bfc_node_id, obj.to_bfc_node_id):   # Q-17
        raise HTTPException(422, "Only a start or end event has a marker to place")
    return col


def save(db: Session, actor_id: int, project_id: int, diagram_type: str, scope_key: str,
         items: list[dict]) -> list[dict]:
    """Upsert the listed positions; untouched objects keep theirs (S2-6)."""
    scope_id = _scope(db, project_id, diagram_type, scope_key)
    seen = set()
    for it in items:
        col = _check_object(db, project_id, diagram_type, it["object_type"], it["object_id"])
        if (col, it["object_id"]) in seen:
            raise HTTPException(422, "An object is listed twice")
        seen.add((col, it["object_id"]))
        if it.get("collapsed") and diagram_type != "ERD":
            raise HTTPException(422, "Only an ERD card collapses")
        values = {"project_id": project_id, "diagram_type": diagram_type, "scope_bfc_node_id": scope_id,
                  col: it["object_id"], "x": it["x"], "y": it["y"], "width": it.get("w"),
                  "height": it.get("h"), "is_collapsed": bool(it.get("collapsed")),
                  "created_by": actor_id, "updated_by": actor_id}
        stmt = insert(DiagramLayout).values(**values)
        db.execute(stmt.on_conflict_do_update(constraint="uq_dl_object", set_={
            "x": stmt.excluded.x, "y": stmt.excluded.y, "width": stmt.excluded.width,
            "height": stmt.excluded.height, "is_collapsed": stmt.excluded.is_collapsed,
            "updated_by": stmt.excluded.updated_by}))              # created_by keeps the first placer
    db.commit()
    return positions(db, project_id, diagram_type, scope_id)


def reset(db: Session, actor_id: int, project_id: int, diagram_type: str, scope_key: str) -> int:
    """The one hard delete the app role may run (D-30, §6.6). Audited as a single event."""
    scope_id = _scope(db, project_id, diagram_type, scope_key)
    n = db.execute(delete(DiagramLayout).where(*_where(project_id, diagram_type, scope_id))).rowcount
    audit.record(db, "LAYOUT_RESET", actor_id=actor_id, project_id=project_id,
                 target_table="diagram_layout", target_id=scope_id,
                 detail={"diagram_type": diagram_type, "scope_key": scope_key, "positions": n})
    db.commit()
    return n
