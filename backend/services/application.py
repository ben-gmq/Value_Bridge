"""Application landscape (§7.5 application.*, D-8, R2-D11). Spec: docs/slice6b1_spec.md; schema:
docs/slice6b_schema.md §1–§3.

Two links, two lock orders, both SR-5 shaped: an allocation locks the application, then the
solution; an as-is link locks the step, then the application (DR6b-P2). The body-named end is always
fetched scoped to the path owner's project first (404), before any lock or label — the
solution.link / function_requirement pattern.

AS_IS is read from the resolved lifecycle *code*, never a code_id (APP_LIFECYCLE is a system
category, §8). An AS_IS application never delivers a Solution (422), and an allocated one never
moves to AS_IS (409). A TO_BE application as today's support only warns (S6b-4, S6b-5)."""
import re

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from models import Application, ApplicationBfcNode, ApplicationSolution, BfcNode, CodeMaster, Solution
from services import audit, lifecycle
from services.code_master import validate_required_code

EDITABLE = ("application_name", "vendor", "version_label", "description")   # plus code, kind, lifecycle
CODE_RE = re.compile(r"^[A-Z0-9._-]+$")                                      # ck_app_code_chars (S6b-6)


def _code(value: str | None) -> str:
    code = (value or "").strip().upper()
    if not code:
        raise HTTPException(422, "application_code cannot be empty")
    if len(code) > 30:                            # upper() can lengthen ("ß" → "SS") — sara L1
        raise HTTPException(422, "application_code is at most 30 characters")
    if not code.isascii() or not CODE_RE.match(code):
        raise HTTPException(422, "application_code may use only A–Z, 0–9, '.', '_' and '-'")
    return code


def _name(value: str | None) -> str:
    name = (value or "").strip()
    if not name:
        raise HTTPException(422, "application_name cannot be empty")
    return name


def _check_free(db: Session, project_id: int, code: str | None, name: str | None,
                application_id: int | None = None) -> None:
    """The code is never reused (any row, live or retired); the name only among live rows."""
    others = select(Application).where(Application.project_id == project_id)
    if application_id is not None:
        others = others.where(Application.application_id != application_id)
    if code is not None:
        holder = db.scalars(others.where(Application.application_code == code)).first()
        if holder is not None:
            gone = "" if holder.is_active else " (retired)"
            raise HTTPException(409, f"{code} is already used by {holder.application_name}{gone}")
    if name is not None:
        holder = db.scalars(others.where(Application.is_active, func.lower(func.btrim(
            Application.application_name)) == name.lower())).first()
        if holder is not None:
            raise HTTPException(409, f"{holder.application_code} is already called {holder.application_name}")


def _lifecycle_code(db: Session, project_id: int, code: str) -> CodeMaster:
    return validate_required_code(db, project_id, "APP_LIFECYCLE", code, "lifecycle_code")


def _live_steps(db: Session, app: Application) -> list[str]:
    return list(db.scalars(select(BfcNode.hier_code).join(
        ApplicationBfcNode, ApplicationBfcNode.bfc_node_id == BfcNode.bfc_node_id).where(
        ApplicationBfcNode.application_id == app.application_id, ApplicationBfcNode.is_active)
        .order_by(BfcNode.hier_code)))


# ---- the catalogue -----------------------------------------------------------------------------
def list_applications(db: Session, project_id: int, include_retired: bool = False) -> list[tuple]:
    """Each application with its live allocation and as-is step counts."""
    def counts(model):
        return dict(db.execute(select(model.application_id, func.count()).where(
            model.project_id == project_id, model.is_active).group_by(model.application_id)).all())
    sols, steps = counts(ApplicationSolution), counts(ApplicationBfcNode)
    q = select(Application).where(Application.project_id == project_id)
    if not include_retired:
        q = q.where(Application.is_active)
    return [(a, sols.get(a.application_id, 0), steps.get(a.application_id, 0))
            for a in db.scalars(q.order_by(Application.application_code))]


def create_application(db: Session, actor_id: int, project_id: int, code: str, name: str,
                       lifecycle_code: str, kind_code: str | None, fields: dict) -> Application:
    code, name = _code(code), _name(name)
    _check_free(db, project_id, code, name)
    app = Application(project_id=project_id, application_code=code, application_name=name,
                      lifecycle_code_id=_lifecycle_code(db, project_id, lifecycle_code).code_id,
                      app_kind_code_id=(validate_required_code(db, project_id, "APP_KIND", kind_code,
                                                               "app_kind_code").code_id if kind_code else None),
                      created_by=actor_id,
                      **{k: fields[k] for k in EDITABLE if k in fields and k != "application_name"})
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


def update_application(db: Session, actor_id: int, app: Application, row_version: int, sent: dict
                       ) -> tuple[Application, list[dict]]:
    """`sent` holds only what the request carried; `kind_code: None` clears the kind (DR6b-P3)."""
    lifecycle.check_version(app, row_version)
    lifecycle.lock(db, app)                       # FOR UPDATE: serialises with link_solution (R2-D11)
    lifecycle.check_live(app, row_version)
    code = _code(sent["application_code"]) if "application_code" in sent else None
    name = _name(sent["application_name"]) if "application_name" in sent else None
    _check_free(db, app.project_id, code if code != app.application_code else None, name, app.application_id)
    warnings: list[dict] = []
    changed: dict = {}
    if code is not None and code != app.application_code:
        changed["previous_application_code"] = app.application_code
    if "lifecycle_code" in sent and sent["lifecycle_code"] != app.lifecycle_code:
        changed["previous_lifecycle_code"] = app.lifecycle_code
        new = _lifecycle_code(db, app.project_id, sent["lifecycle_code"])
        if new.code == "AS_IS":                   # R2-D11: an allocated application is not as-is only
            allocated = db.scalars(select(ApplicationSolution).where(
                ApplicationSolution.application_id == app.application_id, ApplicationSolution.is_active)).all()
            if allocated:
                names = ", ".join(lifecycle.label(r) for r in allocated)
                raise HTTPException(409, f"{app.application_code} still delivers solutions. Remove these first: {names}")
        if new.code == "TO_BE":                   # S6b-5, DR6b-P1: never silent
            steps = _live_steps(db, app)
            if steps:
                warnings.append({"code": "to_be_supports_steps", "items": steps})
        app.lifecycle_code_id = new.code_id
    if "kind_code" in sent:
        k = sent["kind_code"]
        app.app_kind_code_id = (validate_required_code(db, app.project_id, "APP_KIND", k, "app_kind_code").code_id
                                if k else None)
    if code is not None:
        app.application_code = code
    if name is not None:
        app.application_name = name
    for k in ("vendor", "version_label", "description"):
        if k in sent:
            setattr(app, k, sent[k])
    app.updated_by = actor_id
    db.flush()
    if changed:                                   # DR6b-D1, S6b-6
        audit.record(db, "RECORD_UPDATED", actor_id=actor_id, project_id=app.project_id,
                     target_table="application", target_id=app.application_id,
                     detail={"label": lifecycle.label(app), **changed})
    db.commit()
    db.refresh(app)
    return app, warnings


def restore_application(db: Session, actor_id: int, app: Application) -> Application:
    """DR6b-D2: a live application may have taken the name meanwhile → 409 naming it."""
    lifecycle.lock(db, app)
    if app.is_active:
        raise HTTPException(409, f"{lifecycle.label(app)} is not retired")
    _check_free(db, app.project_id, None, app.application_name, app.application_id)
    lifecycle.restore(db, actor_id, app)
    db.refresh(app)
    return app


# ---- to-be allocation: application → solution --------------------------------------------------
def _scoped(db: Session, model, pk_col, pk: int, project_id: int):
    row = db.scalars(select(model).where(pk_col == pk, model.project_id == project_id)).one_or_none()
    if row is None:
        raise HTTPException(404, "Not found")
    return row


def _live(*rows) -> None:
    for r in rows:
        if not r.is_active:
            raise HTTPException(409, f"{lifecycle.label(r)} is retired. Restore it first.")


def link_solution(db: Session, actor_id: int, sol: Solution, application_id: int,
                  note: str | None) -> ApplicationSolution:
    app = _scoped(db, Application, Application.application_id, application_id, sol.project_id)
    lifecycle.lock_for_share(db, app)             # application, then solution (R2-D11 order)
    lifecycle.lock_for_share(db, sol)
    _live(app, sol)
    if is_as_is_only(app):                        # read after the lock, before any relink (DR6b review)
        raise HTTPException(422, f"{app.application_code} is as-is only, so it cannot deliver a future "
                                 "solution. Mark it To-be or Both first.")
    row = db.scalars(select(ApplicationSolution).where(
        ApplicationSolution.application_id == app.application_id,
        ApplicationSolution.solution_id == sol.solution_id).with_for_update(of=ApplicationSolution)).one_or_none()
    if row is None:
        row = ApplicationSolution(project_id=sol.project_id, application_id=app.application_id,
                                  solution_id=sol.solution_id, allocation_note=note, created_by=actor_id)
        db.add(row)
    elif row.is_active:
        raise HTTPException(409, f"{app.application_code} already delivers {sol.solution_number}")
    else:
        lifecycle.relink(db, actor_id, row, detail={"previous_allocation_note": row.allocation_note})
        row.allocation_note = note
    db.commit()
    db.refresh(row)
    return row


# ---- as-is support: application → process step --------------------------------------------------
def link_step(db: Session, actor_id: int, node: BfcNode, application_id: int,
              note: str | None) -> tuple[ApplicationBfcNode, list[dict]]:
    app = _scoped(db, Application, Application.application_id, application_id, node.project_id)
    lifecycle.lock_for_share(db, node)            # the step, then the application (DR6b-P2, SR-5)
    lifecycle.lock_for_share(db, app)
    _live(node, app)
    if not node.is_process:
        raise HTTPException(422, "Applications support process steps only")
    if node.bfc_set_code != "AS_IS":                     # Q-23: to-be systems come from solutions (D-22, D-8)
        raise HTTPException(422, "Supporting systems are recorded on as-is steps. A to-be step's systems "
                                 "come from its requirement's solutions")
    row = db.scalars(select(ApplicationBfcNode).where(
        ApplicationBfcNode.application_id == app.application_id,
        ApplicationBfcNode.bfc_node_id == node.bfc_node_id).with_for_update(of=ApplicationBfcNode)).one_or_none()
    if row is None:
        row = ApplicationBfcNode(project_id=node.project_id, application_id=app.application_id,
                                 bfc_node_id=node.bfc_node_id, support_note=note, created_by=actor_id)
        db.add(row)
    elif row.is_active:
        raise HTTPException(409, f"{app.application_code} already supports {node.hier_code}")
    else:
        lifecycle.relink(db, actor_id, row, detail={"previous_support_note": row.support_note})
        row.support_note = note
    warnings = [{"code": "to_be_as_is", "items": [app.application_code]}] if app.lifecycle_code == "TO_BE" else []
    db.commit()
    db.refresh(row)
    return row, warnings


# ---- shared link edits ---------------------------------------------------------------------------
NOTE = {ApplicationSolution: "allocation_note", ApplicationBfcNode: "support_note"}


def edit_note(db: Session, actor_id: int, row, row_version: int, note: str | None):
    """S5-3 pattern (S6b Q-8): corrected in place, the previous note kept in the audit."""
    lifecycle.check_live(row, row_version)
    col = NOTE[type(row)]
    if getattr(row, col) == note:
        return row
    previous = getattr(row, col)
    setattr(row, col, note)
    row.updated_by = actor_id
    audit.record(db, "RECORD_UPDATED", actor_id=actor_id, project_id=row.project_id,
                 target_table=row.__table__.name, target_id=lifecycle.pk(row),
                 detail={"label": lifecycle.label(row), f"previous_{col}": previous})
    db.commit()
    db.refresh(row)
    return row


def unlink(db: Session, actor_id: int, row, row_version: int) -> None:
    lifecycle.unlink(db, actor_id, row, row_version)


# ---- lists ---------------------------------------------------------------------------------------
def _alloc(r: ApplicationSolution) -> dict:
    a, s = r.application_row, r.solution_row
    return {"application_solution_id": r.application_solution_id, "application_id": a.application_id,
            "application_code": a.application_code, "application_name": a.application_name,
            "lifecycle_code": a.lifecycle_code, "solution_id": s.solution_id, "solution_number": s.solution_number,
            "solution_name": s.solution_name, "note": r.allocation_note, "row_version": r.row_version}


def _support(r: ApplicationBfcNode) -> dict:
    a, n = r.application_row, r.node_row
    return {"application_bfc_node_id": r.application_bfc_node_id, "application_id": a.application_id,
            "application_code": a.application_code, "application_name": a.application_name,
            "lifecycle_code": a.lifecycle_code, "bfc_node_id": n.bfc_node_id, "hier_code": n.hier_code,
            "node_name": n.node_name, "note": r.support_note, "row_version": r.row_version}


def allocations(db: Session, *, solution_id: int | None = None, application_id: int | None = None) -> list[dict]:
    q = select(ApplicationSolution).where(ApplicationSolution.is_active).options(
        selectinload(ApplicationSolution.application_row), selectinload(ApplicationSolution.solution_row))
    q = q.where(ApplicationSolution.solution_id == solution_id) if solution_id is not None \
        else q.where(ApplicationSolution.application_id == application_id)
    return sorted((_alloc(r) for r in db.scalars(q)), key=lambda d: (d["application_code"], d["solution_number"]))


def supports(db: Session, *, bfc_node_id: int | None = None, application_id: int | None = None) -> list[dict]:
    q = select(ApplicationBfcNode).where(ApplicationBfcNode.is_active).options(
        selectinload(ApplicationBfcNode.application_row), selectinload(ApplicationBfcNode.node_row))
    q = q.where(ApplicationBfcNode.bfc_node_id == bfc_node_id) if bfc_node_id is not None \
        else q.where(ApplicationBfcNode.application_id == application_id)
    return sorted((_support(r) for r in db.scalars(q)), key=lambda d: (d["application_code"], d["hier_code"]))


def as_alloc(r: ApplicationSolution) -> dict:
    return _alloc(r)


def as_support(r: ApplicationBfcNode) -> dict:
    return _support(r)


# ---- consistency_check lines ---------------------------------------------------------------------
def _lifecycle_is(code: str):
    return select(CodeMaster.code_id).where(CodeMaster.category == "APP_LIFECYCLE", CodeMaster.code == code)


def consistency_lines(db: Session, project_id: int | None) -> dict[str, list]:
    def scope(q, model):
        return q.where(model.project_id == project_id) if project_id is not None else q
    appsol = scope(select(ApplicationSolution.application_solution_id).join(
        Application, Application.application_id == ApplicationSolution.application_id).join(
        Solution, Solution.solution_id == ApplicationSolution.solution_id).where(
        ApplicationSolution.is_active, ~(Application.is_active & Solution.is_active)), ApplicationSolution)
    appnode = scope(select(ApplicationBfcNode.application_bfc_node_id).join(
        Application, Application.application_id == ApplicationBfcNode.application_id).join(
        BfcNode, BfcNode.bfc_node_id == ApplicationBfcNode.bfc_node_id).where(
        ApplicationBfcNode.is_active, ~(Application.is_active & BfcNode.is_active)), ApplicationBfcNode)
    as_is = scope(select(ApplicationSolution.application_solution_id).join(
        Application, Application.application_id == ApplicationSolution.application_id).where(
        ApplicationSolution.is_active, Application.lifecycle_code_id.in_(_lifecycle_is("AS_IS"))),
        ApplicationSolution)
    to_be = scope(select(ApplicationBfcNode.application_bfc_node_id).join(
        Application, Application.application_id == ApplicationBfcNode.application_id).where(
        ApplicationBfcNode.is_active, Application.lifecycle_code_id.in_(_lifecycle_is("TO_BE"))),
        ApplicationBfcNode)
    return {
        "appsol_under_inactive": list(db.scalars(appsol)),
        "appnode_under_inactive": list(db.scalars(appnode)),
        "as_is_allocated": list(db.scalars(as_is)),
        "as_is_support_by_to_be": list(db.scalars(to_be)),       # informational (S6b-5)
    }


def support_on_to_be(db: Session, project_id: int | None) -> list[dict]:
    """INFORMATIONAL (Q-23): supporting-system links that sit on to-be steps — made before 7c, when
    there was one chart. The to-be → as-is copy carries them to the as-is chart; then remove these."""
    q = (select(ApplicationBfcNode.application_bfc_node_id, Application.application_code, BfcNode.hier_code)
         .join(Application, Application.application_id == ApplicationBfcNode.application_id)
         .join(BfcNode, BfcNode.bfc_node_id == ApplicationBfcNode.bfc_node_id)
         .where(ApplicationBfcNode.is_active, BfcNode.bfc_set_code == "TO_BE"))
    if project_id is not None:
        q = q.where(ApplicationBfcNode.project_id == project_id)
    return [{"application_bfc_node_id": i, "application_code": a, "hier_code": h}
            for i, a, h in db.execute(q.order_by(BfcNode.hier_code, Application.application_code))]


def is_as_is_only(app: Application) -> bool:
    """APP_LIFECYCLE is a system category (fixed codes, services header): an application in the as-is landscape only."""
    return app.lifecycle_code == "AS_IS"
