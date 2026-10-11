"""The one owner of "is this component on for this project" (D-37, D-39, slice7_schema §5).

A project's components are live `project_component` rows. Writes to an off component are refused
with 409 COMPONENT_OFF by `require_on`, which the guard calls (routers/guards.py `component=`) and
services call where the component depends on the body. Switching on and off goes only through
`set_components`: preview first, then confirm, audited, and refused while the component has live
rows (OR-1) or another enabled component needs it (OR-2).
"""
import getpass
import hashlib
import json
import socket

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import (AppUser, ApplicationBfcNode, Application, AuditEvent, BfcNode, BfcNodeExternalFlow,
                    BfcNodeTrigger, BrSolution, CodeMaster, FunctionRequirement, ProcessTrigger, Project,
                    ProjectComponent, ProjectTemplateComponent, Solution)
from services import audit

CATEGORY = "PROJECT_COMPONENT"
ALL = ("SOLUTION", "FUNCTION_REQUIREMENT", "APPLICATION", "EFFORT", "ISSUE", "TO_BE_DFD", "AS_IS",
       "WBS", "BENEFIT", "RISK", "CHANGE_REQUEST")
# OR-2 [Q-3, Q-4]: a component that reads another's tables needs it on. Code facts, not data.
COMPONENT_REQUIRES: dict[str, frozenset[str]] = {
    "EFFORT": frozenset({"FUNCTION_REQUIREMENT"}),
    "BENEFIT": frozenset({"SOLUTION"}),
    "CHANGE_REQUEST": frozenset({"EFFORT"}),
}
# Components with screens today; the rest can be switched on but show "not yet available" (§7 risk 4).
BUILT = frozenset({"SOLUTION", "FUNCTION_REQUIREMENT", "APPLICATION", "EFFORT", "TO_BE_DFD", "AS_IS"})
OFF_HEADERS = {"X-VB-Error": "COMPONENT_OFF"}
DEPTHS = ("KEYS_ONLY", "FULL")
_SAMPLE = 10


def _rows(model, label_col, *extra, step_set: str | None = None):
    """A live-row probe for one table: (count, up to 10 labels). `step_set` keeps step-owned rows of
    one chart only and labels them by their step's code (L8)."""
    def probe(db: Session, project_id: int) -> tuple[int, list[str]]:
        where = (model.project_id == project_id, model.is_active, *extra)
        q = select(func.count()).select_from(model)
        lq = select(label_col)
        if step_set is not None:
            on = BfcNode.bfc_node_id == model.bfc_node_id
            q, lq = q.join(BfcNode, on), select(BfcNode.hier_code).select_from(model).join(BfcNode, on)
            where = (*where, BfcNode.bfc_set_code == step_set)
        n = db.scalar(q.where(*where))
        names = [str(v) for v in db.scalars(lq.where(*where).order_by(lq.selected_columns[0])
                                            .limit(_SAMPLE))] if n else []
        return n, names
    return probe


# OR-1 [Q-6]: what "has live rows" means per component. Unbuilt components have none yet.
COMPONENT_ROWS = {
    "SOLUTION": (_rows(Solution, Solution.solution_number),),
    "FUNCTION_REQUIREMENT": (_rows(FunctionRequirement, FunctionRequirement.fr_number),),
    "APPLICATION": (_rows(Application, Application.application_code),),
    "EFFORT": (_rows(FunctionRequirement, FunctionRequirement.fr_number,
                     FunctionRequirement.complexity_code_id.is_not(None)),),
    # 7c: the to-be DFD's own rows — external flows, trigger links and performers on to-be steps.
    "TO_BE_DFD": (_rows(BfcNodeExternalFlow, None, step_set="TO_BE"),
                  _rows(BfcNodeTrigger, None, step_set="TO_BE"),
                  _rows(BfcNode, BfcNode.hier_code, BfcNode.performer_kind.is_not(None),
                        BfcNode.bfc_set_code == "TO_BE")),
    # the as-is chart itself (D-47): its nodes carry everything else of it
    "AS_IS": (_rows(BfcNode, BfcNode.hier_code, BfcNode.bfc_set_code == "AS_IS"),),
}


# DR7-P2: the component(s) a row needs on before a restore may bring it back live.
ROW_COMPONENTS: dict[type, tuple[str, ...]] = {
    Solution: ("SOLUTION",),
    FunctionRequirement: ("FUNCTION_REQUIREMENT",),
    Application: ("APPLICATION",),
    ApplicationBfcNode: ("APPLICATION", "AS_IS"),
    BrSolution: ("SOLUTION",),
}
DFD_ROWS = (BfcNodeExternalFlow, BfcNodeTrigger)          # their component is their step's chart's DFD


def dfd_component(bfc_set: str) -> str:
    """The component that owns a chart's DFD data: TO_BE_DFD or AS_IS (DR7-D1)."""
    return "AS_IS" if bfc_set == "AS_IS" else "TO_BE_DFD"


def node_dfd_component(node) -> str:
    """Guard resolver (DR7-D1): performer, trigger links and external flows belong to the node's
    chart's DFD component. One definition, imported by every router."""
    return dfd_component(node.bfc_set_code)


def needed_for_rows(rows, bfc_set: str | None = None) -> tuple[str, ...]:
    """Every component the rows about to become live need, including an FR's rating (EFFORT)
    and its solution link (SOLUTION), and a step's DFD rows and performer (its chart's DFD)."""
    out: set[str] = set()
    for r in rows:
        out.update(ROW_COMPONENTS.get(type(r), ()))
        if bfc_set is not None and (isinstance(r, DFD_ROWS) or (isinstance(r, BfcNode) and r.performer_kind)):
            out.add(dfd_component(bfc_set))
        if isinstance(r, BfcNode) and r.bfc_set_code == "AS_IS":
            out.add("AS_IS")
        if isinstance(r, FunctionRequirement):
            if r.complexity_code_id is not None:
                out.add("EFFORT")
            if r.solution_id is not None:
                out.add("SOLUTION")
    return tuple(sorted(out))


# The trigger catalogue serves both DFDs (§12 auditor Q3): its live rows block switching BOTH off.
DFD_CODES = frozenset({"TO_BE_DFD", "AS_IS"})
_catalogue = _rows(ProcessTrigger, ProcessTrigger.trigger_name)


def rows_in_off_component(db: Session, project_id: int) -> list[dict]:
    """INFORMATIONAL consistency line (DR7-P2): live rows of a component that is off — the
    reconciliation for any gating gap. Empty when the guard and the restore checks hold."""
    on = enabled(db, project_id)
    out = []
    if not DFD_CODES & on:
        n, names = _catalogue(db, project_id)
        if n:
            out.append({"component": "TO_BE_DFD", "count": n, "sample": names})
    for code, probes in COMPONENT_ROWS.items():
        if code in on:
            continue
        for probe in probes:
            n, names = probe(db, project_id)
            if n:
                out.append({"component": code, "count": n, "sample": names})
    return out


# ---- reading ------------------------------------------------------------------------------
def _codes(db: Session) -> dict[str, CodeMaster]:
    return {c.code: c for c in db.scalars(select(CodeMaster).where(
        CodeMaster.project_id.is_(None), CodeMaster.category == CATEGORY))}


def enabled(db: Session, project_id: int, lock: bool = False) -> frozenset[str]:
    q = (select(CodeMaster.code).join(ProjectComponent,
                                      ProjectComponent.component_code_id == CodeMaster.code_id)
         .where(ProjectComponent.project_id == project_id, ProjectComponent.is_active))
    if lock:   # FOR SHARE OF project_component only (DR7-S4), in id order like set_components (L1)
        q = q.order_by(ProjectComponent.project_component_id).with_for_update(of=ProjectComponent, read=True)
    return frozenset(db.scalars(q))


def require_on(db: Session, project_id: int, codes: str | tuple[str, ...] | None) -> None:
    """409 COMPONENT_OFF unless every named component is on. Holds FOR SHARE on the rows until the
    request commits, so a write and a switch-off serialise (§5.1)."""
    if not codes:
        return
    wanted = (codes,) if isinstance(codes, str) else tuple(codes)
    on = enabled(db, project_id, lock=True)
    missing = [c for c in wanted if c not in on]
    if missing:
        labels = _codes(db)
        names = ", ".join(labels[c].label if c in labels else c for c in missing)
        raise HTTPException(409, f"{names} {'is' if len(missing) == 1 else 'are'} not used on this "
                                 "project. A platform admin can switch it on in Settings.",
                            headers=OFF_HEADERS)


def closure(codes) -> set[str]:
    out, todo = set(), list(codes)
    while todo:
        c = todo.pop()
        if c not in out:
            out.add(c)
            todo.extend(COMPONENT_REQUIRES.get(c, ()))
    return out


def depth(project: Project) -> str:
    return project.data_model_depth


def template_components(db: Session, template_code: str) -> list[str]:
    t = db.scalars(select(CodeMaster).where(CodeMaster.project_id.is_(None),
                                            CodeMaster.category == "PROJECT_TEMPLATE",
                                            CodeMaster.code == template_code,
                                            CodeMaster.is_active)).one_or_none()
    if t is None:
        raise HTTPException(400, f"template_code: '{template_code}' is not a valid PROJECT_TEMPLATE code")
    return sorted(db.scalars(select(CodeMaster.code).join(
        ProjectTemplateComponent, ProjectTemplateComponent.component_code_id == CodeMaster.code_id).where(
        ProjectTemplateComponent.template_code_id == t.code_id, ProjectTemplateComponent.is_active)))


def templates(db: Session) -> list[dict]:
    rows = db.scalars(select(CodeMaster).where(CodeMaster.project_id.is_(None),
                                               CodeMaster.category == "PROJECT_TEMPLATE",
                                               CodeMaster.is_active).order_by(CodeMaster.sort_order))
    return [{"code": t.code, "label": t.label, "components": template_components(db, t.code)}
            for t in rows]


def catalogue(db: Session) -> list[dict]:
    """Every component, what it needs and whether it has screens — for the create form."""
    return [{"code": c.code, "label": c.label, "enabled": False,
             "requires": sorted(COMPONENT_REQUIRES.get(c.code, ())), "available": c.code in BUILT}
            for c in sorted(_codes(db).values(), key=lambda c: c.sort_order) if c.is_active]


def describe(db: Session, project_id: int) -> list[dict]:
    """Every component with its on/off state and what it needs — the Settings screen."""
    on = enabled(db, project_id)
    return [{"code": c.code, "label": c.label, "enabled": c.code in on,
             "requires": sorted(COMPONENT_REQUIRES.get(c.code, ())),
             "available": c.code in BUILT}
            for c in sorted(_codes(db).values(), key=lambda c: c.sort_order) if c.is_active]


# ---- writing ------------------------------------------------------------------------------
def _validate(wanted) -> set[str]:
    unknown = sorted(set(wanted) - set(ALL))
    if unknown:
        raise HTTPException(400, f"component_codes: unknown {', '.join(unknown)}")
    return set(wanted)


def initial_rows(db: Session, project_id: int, codes, actor_id: int) -> list[str]:
    """create_project: the list must already be closed under COMPONENT_REQUIRES — the UI shows
    what a dependency adds, so the server never adds anything silently (§5.1)."""
    wanted = _validate(codes)
    missing = sorted(closure(wanted) - wanted)
    if missing:
        labels = _codes(db)
        raise HTTPException(422, "These components are needed by the ones chosen: "
                                 + ", ".join(labels[c].label for c in missing))
    labels = _codes(db)
    for c in sorted(wanted):
        db.add(ProjectComponent(project_id=project_id, component_code_id=labels[c].code_id,
                                created_by=actor_id))
    return sorted(wanted)


def _blockers(db: Session, project_id: int, turn_off: set[str], staying: set[str],
              kept: set[str] = frozenset()) -> list[dict]:
    """`kept`: components the admin asked to switch off that a staying component still needs —
    refused with the reason (OR-2, sara M2), never kept on silently."""
    labels = _codes(db)
    out = []
    for c in sorted(kept):
        needers = sorted(k for k in staying if c in COMPONENT_REQUIRES.get(k, ()))
        out.append({"component": c, "reason": "NEEDED_BY", "by": needers,
                    "message": f"{', '.join(labels[n].label for n in needers)} "
                               f"need{'s' if len(needers) == 1 else ''} {labels[c].label}"})
    if DFD_CODES & turn_off and not DFD_CODES & staying:        # both DFD components end up off
        n, names = _catalogue(db, project_id)
        if n:
            out.append({"component": "TO_BE_DFD", "reason": "LIVE_ROWS", "count": n, "sample": names,
                        "message": f"The trigger catalogue still has {n} live trigger{'s' if n != 1 else ''}: "
                                   f"{', '.join(names)}" + (" …" if n > len(names) else "")})
    for c in sorted(turn_off):
        for probe in COMPONENT_ROWS.get(c, ()):
            n, names = probe(db, project_id)
            if n:
                out.append({"component": c, "reason": "LIVE_ROWS", "count": n, "sample": names,
                            "message": f"{labels[c].label} still has {n} live "
                                       f"row{'s' if n != 1 else ''}: {', '.join(names)}"
                                       + (" …" if n > len(names) else "")})
    return out


def set_components(db: Session, actor: AppUser, project: Project, wanted, confirm_hash: str | None) -> dict:
    """Platform admin (route guard). Without a hash: preview, write nothing. With the preview's
    hash: lock, re-check, apply, one audit event, one commit (§5.1, OR-1, OR-2)."""
    wanted = _validate(wanted)
    target = closure(wanted)

    def plan(lock: bool) -> dict:
        on = enabled(db, project.project_id, lock=False)
        if lock:
            db.execute(select(ProjectComponent.project_component_id).where(
                ProjectComponent.project_id == project.project_id)
                .order_by(ProjectComponent.project_component_id).with_for_update())
            on = enabled(db, project.project_id)
        turn_on, turn_off = target - on, on - target
        kept = (on - wanted) & target                  # asked off, still needed by a staying component
        return {"turn_on": sorted(turn_on), "added_by_dependency": sorted(target - wanted - on),
                "turn_off": sorted(turn_off),
                "blockers": _blockers(db, project.project_id, turn_off, target, kept)}

    preview = plan(lock=False)
    h = hashlib.sha256(json.dumps(preview, sort_keys=True).encode()).hexdigest()
    if confirm_hash is None:
        return {**preview, "confirm_hash": h, "applied": False}
    preview = plan(lock=True)
    if hashlib.sha256(json.dumps(preview, sort_keys=True).encode()).hexdigest() != confirm_hash:
        raise HTTPException(409, "The components or their contents changed since the preview. "
                                 "Review it again.")
    if preview["blockers"]:
        raise HTTPException(409, "; ".join(b["message"] for b in preview["blockers"]))
    if not preview["turn_on"] and not preview["turn_off"]:          # nothing to write or audit (L9)
        db.rollback()
        return {**preview, "confirm_hash": confirm_hash, "applied": False}
    labels = _codes(db)
    rows = {r.component_code_id: r for r in db.scalars(select(ProjectComponent).where(
        ProjectComponent.project_id == project.project_id))}
    for c in preview["turn_on"]:
        r = rows.get(labels[c].code_id)
        if r is None:
            db.add(ProjectComponent(project_id=project.project_id, component_code_id=labels[c].code_id,
                                    created_by=actor.app_user_id))
        else:                                       # restore the same row (S1-7)
            r.is_active, r.deleted_at, r.deleted_by = True, None, None
            r.updated_by = actor.app_user_id
    for c in preview["turn_off"]:
        r = rows[labels[c].code_id]
        r.is_active, r.deleted_at, r.deleted_by = False, func.now(), actor.app_user_id
        r.updated_by = actor.app_user_id
    audit.record(db, "PROJECT_COMPONENTS_CHANGED", actor_id=actor.app_user_id,
                 project_id=project.project_id, target_table="project_component",
                 detail={"on": preview["turn_on"], "off": preview["turn_off"],
                         "added_by_dependency": preview["added_by_dependency"]})
    db.commit()
    return {**preview, "confirm_hash": confirm_hash, "applied": True}


def set_depth(db: Session, actor: AppUser, project: Project, value: str, row_version: int) -> Project:
    """D-39 [Q-8]: platform admin, audited, optimistic lock."""
    if value not in DEPTHS:
        raise HTTPException(400, f"data_model_depth: '{value}' is not one of {', '.join(DEPTHS)}")
    if project.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")
    if project.data_model_depth != value:
        old = project.data_model_depth
        project.data_model_depth = value
        project.updated_by = actor.app_user_id
        audit.record(db, "PROJECT_DEPTH_CHANGED", actor_id=actor.app_user_id,
                     project_id=project.project_id, target_table="project",
                     target_id=project.project_id, detail={"from": old, "to": value})
    db.commit()
    return project


def backfill(db: Session, actor_email: str) -> list[dict]:
    """CLI, one-off for the 7a deploy (§5.3, DR7-P1): a project created before 7a — no component row
    at all and no component list in its PROJECT_CREATED audit — gets every component on. A project
    that chose its components (even none) is left alone (sara M1)."""
    actor = db.scalars(select(AppUser).where(func.lower(AppUser.email) == actor_email.strip().lower())).one_or_none()
    if actor is None or not actor.is_active or not actor.is_platform_admin:
        raise SystemExit("--actor-email must be an active platform admin")
    labels = _codes(db)
    missing_codes = [c for c in ALL if c not in labels]
    if missing_codes:
        raise SystemExit(f"Run seeds.seed_code_master first: missing {', '.join(missing_codes)}")
    out = []
    for p in db.scalars(select(Project).order_by(Project.project_id)).all():
        # Only projects created before 7a: no row at all, live or retired. A project created since
        # chose its components, and an admin's switch-off must survive every later run (DR7-P1).
        chose = db.scalar(select(func.count()).select_from(AuditEvent).where(     # sara M1: provenance
            AuditEvent.project_id == p.project_id, AuditEvent.event_type == "PROJECT_CREATED",
            AuditEvent.detail.has_key("components")))
        if chose or db.scalar(select(func.count()).select_from(ProjectComponent).where(
                ProjectComponent.project_id == p.project_id)):
            out.append({"project_id": p.project_id, "added": []})
            continue
        added = list(ALL)
        for c in added:
            db.add(ProjectComponent(project_id=p.project_id, component_code_id=labels[c].code_id,
                                    created_by=actor.app_user_id))
        if added:
            audit.record(db, "PROJECT_COMPONENTS_BACKFILLED", actor_id=actor.app_user_id,
                         project_id=p.project_id, detail={"added": added, "os_user": getpass.getuser(),
                                                          "host": socket.gethostname()})
        db.commit()
        out.append({"project_id": p.project_id, "added": added})
    return out
