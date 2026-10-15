"""The DFD — the one process diagram (D-38, D-46, D-47, D-49; slice7_schema §9.7–§9.8).

Order is derived, never stored: B follows A when B reads a data entity A writes. A branch is two
outputs feeding different processes; a loop is a later process writing what an earlier one reads.
The swimlane is the performer. Everything is computed within ONE chart (to-be or as-is): a process
never reads or feeds a process of the other chart.

The arrows of the old process flow (bfc_node_flow) were retired by migration 0045 and are never read.
"""
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from fastapi import HTTPException

from models import (Application, ApplicationBfcNode, ApplicationSolution, BfcNode, BfcNodeDataEntity,
                    BfcNodeExternalFlow, BfcNodeOrgRole, BfcNodeTrigger, BrDataEntity, BrSolution,
                    BusinessRequirement, DataEntity, ExternalEntity, OrgRole, OrgUnit, ProcessTrigger)
from services import components, dfd_rule, diagram_layout


def _ref(n: BfcNode) -> dict:
    return {"bfc_node_id": n.bfc_node_id, "hier_code": n.hier_code, "node_name": n.node_name,
            "bfc_set_code": n.bfc_set_code}


# ---- completeness (D-38, D-49, §9.7) -------------------------------------------------------------

def _has_input():
    return or_(
        exists().where(BfcNodeDataEntity.bfc_node_id == BfcNode.bfc_node_id, BfcNodeDataEntity.is_active,
                       BfcNodeDataEntity.direction == "I"),
        exists().where(BfcNodeExternalFlow.bfc_node_id == BfcNode.bfc_node_id, BfcNodeExternalFlow.is_active,
                       BfcNodeExternalFlow.direction == "I"),
        exists().where(BfcNodeTrigger.bfc_node_id == BfcNode.bfc_node_id, BfcNodeTrigger.is_active))


def _has_output():
    return exists().where(BfcNodeDataEntity.bfc_node_id == BfcNode.bfc_node_id, BfcNodeDataEntity.is_active,
                          BfcNodeDataEntity.direction == "O")


def sets_with_dfd_on(db: Session, project_id: int) -> list[str]:
    """S7-3: the rule applies to a chart only while its DFD component is on."""
    on = components.enabled(db, project_id)
    return [s for s, c in (("TO_BE", "TO_BE_DFD"), ("AS_IS", "AS_IS")) if c in on]


# ---- readiness: the red / yellow / green light (D-68, D-70; slice13_spec §7.1) -------------------------------
# 13b (DR13-P1): ONE reader. The light, the DFD marks, process_completeness, the DFD's gaps, consistency_check and so
# the freeze gate all read the chart's rule (services/dfd_rule.codes, fail-closed) through these predicates.
# Q-13 (S13-1, S13-2): red = a RULE element is missing, so the process blocks the freeze; yellow = every rule element
# is met but a RECOMMENDED one is missing (passes the freeze); green = nothing missing.
STARTED, DATA_IN, DATA_OUT, EXTERNAL, ORDER = (dfd_rule.STARTED, dfd_rule.DATA_IN, dfd_rule.DATA_OUT,
                                               dfd_rule.EXTERNAL, dfd_rule.ORDER)
FIXED_RULE = dfd_rule.FIXED_RULE
READY, PARTIAL, NOT_READY = "READY", "PARTIAL", "NOT_READY"


def _has_data_in():
    return exists().where(BfcNodeDataEntity.bfc_node_id == BfcNode.bfc_node_id, BfcNodeDataEntity.is_active,
                          BfcNodeDataEntity.direction == "I")


def _has_order():
    """Joined to another live process of its chart by the derived order (D-38): it reads a data entity another
    writes, or writes one another reads — the pairs derive_order draws. A one-process chart passes (in _evaluate)."""
    me, other, o = aliased(BfcNodeDataEntity), aliased(BfcNodeDataEntity), aliased(BfcNode)
    return exists().where(me.bfc_node_id == BfcNode.bfc_node_id, me.is_active,
                          other.data_entity_id == me.data_entity_id, other.direction != me.direction,
                          other.is_active, o.bfc_node_id == other.bfc_node_id, o.bfc_node_id != BfcNode.bfc_node_id,
                          o.is_active, o.is_process, o.project_id == BfcNode.project_id,
                          o.bfc_set_code == BfcNode.bfc_set_code)


# Per-process elements. EXTERNAL is per diagram (Q-6, Q-16): never in a process's light.
_ELEMENTS = {STARTED: _has_input, DATA_IN: _has_data_in, DATA_OUT: _has_output, ORDER: _has_order}


def _light(missing: list[str], advised: list[str]) -> str:
    return NOT_READY if missing else PARTIAL if advised else READY


def _evaluate(db: Session, project_id: int, bfc_set: str, rule: tuple[str, ...],
              node_ids: list[int] | None = None) -> list[tuple[BfcNode, list[str], list[str]]]:
    """(process, rule elements it misses, recommended elements it misses) per live process of one chart, in chart
    order. One SQL pass, one EXISTS per element."""
    advise = tuple(e for e in dfd_rule.RECOMMENDED[bfc_set] if e not in rule and e in _ELEMENTS)
    check = tuple(e for e in dfd_rule.ELEMENTS if e in _ELEMENTS and (e in rule or e in advise))
    q = select(BfcNode, *(_ELEMENTS[e]().label(e) for e in check)).where(
        BfcNode.project_id == project_id, BfcNode.is_active, BfcNode.is_process, BfcNode.bfc_set_code == bfc_set)
    if node_ids is not None:
        q = q.where(BfcNode.bfc_node_id.in_(node_ids or [-1]))
    rows = db.execute(q.order_by(BfcNode.hier_code)).all()
    alone = False
    if ORDER in check:
        alone = db.scalar(select(func.count()).select_from(BfcNode).where(
            BfcNode.project_id == project_id, BfcNode.is_active, BfcNode.is_process,
            BfcNode.bfc_set_code == bfc_set)) == 1
    out = []
    for row in rows:
        met = {e: bool(row._mapping[e]) or (e == ORDER and alone) for e in check}
        out.append((row[0], [e for e in rule if e in met and not met[e]], [e for e in advise if not met[e]]))
    return out


def readiness(db: Session, project_id: int, bfc_set: str, node_ids: list[int] | None = None,
              rule: tuple[str, ...] | None = None) -> dict:
    """Per live process of one chart: the rule elements it misses (red: blocks the freeze), the recommended elements
    it misses (yellow), and its light. A chart whose DFD component is off carries no light (S7-3). Retired processes
    are never listed. `rule` overrides the stored rule (the rule preview only). Read-only."""
    rule = dfd_rule.codes(db, project_id, bfc_set) if rule is None else rule
    applies = bfc_set in sets_with_dfd_on(db, project_id)
    out = {"bfc_set_code": bfc_set, "rule_applies": applies, "rule": list(rule),
           "recommended": list(dfd_rule.RECOMMENDED[bfc_set]), "processes": {}}
    if not applies:
        return out
    for n, missing, advised in _evaluate(db, project_id, bfc_set, rule, node_ids):
        out["processes"][n.bfc_node_id] = {"light": _light(missing, advised), "missing": missing, "advised": advised}
    return out


# The freeze-blocking report keys, one per per-process element; today's two keep their names (slice13_schema §2.5).
MISSING_KEYS = {STARTED: "missing_input", DATA_OUT: "missing_output", DATA_IN: "missing_data_in",
                ORDER: "missing_order"}


def missing_io(db: Session, project_id: int, sets: list[str] | None = None,
               node_ids: list[int] | None = None) -> dict[str, list[dict]]:
    """Live processes missing an element of their chart's rule, one list per element — re-expressed over the same
    reader as the light (DR13-P1). Each is a FREEZE_BLOCKING_WARNING: amber while editing, a refusal at freeze
    (D-38, D-70). An element outside the chart's rule lists nothing."""
    sets = sets_with_dfd_on(db, project_id) if sets is None else sets
    out: dict[str, list[dict]] = {k: [] for k in MISSING_KEYS.values()}
    for s in ("TO_BE", "AS_IS"):
        if s not in sets:
            continue
        for n, missing, _advised in _evaluate(db, project_id, s, dfd_rule.codes(db, project_id, s), node_ids):
            for e in missing:
                out[MISSING_KEYS[e]].append(_ref(n))
    return out


def diagrams_missing_external(db: Session, project_id: int, bfc_set: str | None = None,
                              rule: tuple[str, ...] | None = None) -> list[dict]:
    """Q-6 / Q-16: under a rule with EXTERNAL, each listed DFD (D-54: a live non-process node with a live process
    child) must show at least one outside party — a live external flow on any live process below it. Only charts
    whose DFD is on and whose rule has EXTERNAL (`rule` overrides it for `bfc_set`: the rule preview only). Never
    changes a process's light; the DFD list shows it."""
    sets = [s for s in sets_with_dfd_on(db, project_id) if bfc_set is None or s == bfc_set]
    out = []
    for s in ("TO_BE", "AS_IS"):
        if s not in sets or EXTERNAL not in (rule if rule is not None else dfd_rule.codes(db, project_id, s)):
            continue
        nodes = list(db.scalars(select(BfcNode).where(BfcNode.project_id == project_id, BfcNode.is_active,
                                                      BfcNode.bfc_set_code == s).order_by(BfcNode.hier_code)))
        talks = set(db.scalars(select(BfcNodeExternalFlow.bfc_node_id).where(
            BfcNodeExternalFlow.project_id == project_id, BfcNodeExternalFlow.is_active)))
        by_id = {n.bfc_node_id: n for n in nodes}
        parents = {n.parent_bfc_node_id for n in nodes if n.is_process and n.parent_bfc_node_id in by_id
                   and not by_id[n.parent_bfc_node_id].is_process}
        for pid in sorted(parents, key=lambda i: by_id[i].hier_code):
            d = by_id[pid]
            below = [n for n in nodes if n.is_process and n.hier_code.startswith(f"{d.hier_code}.")]
            if not any(n.bfc_node_id in talks for n in below):
                out.append(_ref(d))
    return out


def process_completeness(db: Session, project_id: int, bfc_set: str = "TO_BE") -> dict:
    """§9.7: the gaps of one chart. Each `missing_*` list (one per element of the chart's rule, D-70) and
    `diagram_missing_external` (diagrams, under a rule with EXTERNAL) block a freeze while that chart's DFD is on;
    `no_performer` is a warning only (D-46). `crud_without_io`, `ext_without_io`
    and `live_link_on_retired_step` must be 0 (criteria 93, 148; step retire §4). `step_without_br`
    is to-be only — as-is processes carry no BR (S7-2)."""
    steps = list(db.scalars(select(BfcNode).where(
        BfcNode.project_id == project_id, BfcNode.is_active, BfcNode.is_process,
        BfcNode.bfc_set_code == bfc_set).order_by(BfcNode.hier_code)))
    applies = bfc_set in sets_with_dfd_on(db, project_id)                # once per request (sara L3)
    gaps = missing_io(db, project_id, [bfc_set] if applies else [])
    with_br = set(db.scalars(select(BusinessRequirement.bfc_node_id).where(
        BusinessRequirement.project_id == project_id, BusinessRequirement.is_active)))
    return {
        "bfc_set_code": bfc_set,
        "rule_applies": applies,
        **gaps,
        "diagram_missing_external": diagrams_missing_external(db, project_id, bfc_set) if applies else [],
        "no_performer": [_ref(s) for s in steps if s.performer_kind is None],
        "step_without_br": [_ref(s) for s in steps if bfc_set == "TO_BE" and s.bfc_node_id not in with_br],
        "crud_without_io": _unlicensed(db, project_id, BrDataEntity, BrDataEntity.br_data_entity_id),
        "ext_without_io": _unlicensed(db, project_id, BfcNodeExternalFlow,
                                      BfcNodeExternalFlow.bfc_node_external_flow_id),
        "live_link_on_retired_step": _live_on_retired(db, project_id),
        "readiness": readiness(db, project_id, bfc_set),                 # D-68: the light, per process (one reader)
    }


def _live_on_retired(db: Session, project_id: int) -> list[dict]:
    """Live rows hanging off a retired step — must be empty; the independent proof that a
    step retire never leaves a half state (docs/step_retire_spec.md §4)."""
    retired = select(BfcNode.bfc_node_id).where(BfcNode.project_id == project_id, ~BfcNode.is_active)
    out = []
    for model in (BusinessRequirement, BfcNodeDataEntity, BfcNodeOrgRole, BfcNodeExternalFlow,
                  BfcNodeTrigger, ApplicationBfcNode):
        pk = model.__mapper__.primary_key[0]
        out += [{"table": model.__table__.name, "id": i} for i in db.scalars(
            select(pk).where(model.project_id == project_id, model.is_active,
                             model.bfc_node_id.in_(retired)).order_by(pk))]
    return out


def _unlicensed(db: Session, project_id: int, model, pk) -> list[int]:
    """Live rows naming a data entity with no matching live step I/O row (D-24, R2-D13)."""
    io = exists().where(and_(BfcNodeDataEntity.bfc_node_id == model.bfc_node_id,
                             BfcNodeDataEntity.data_entity_id == model.data_entity_id,
                             BfcNodeDataEntity.direction == model.direction,
                             BfcNodeDataEntity.is_active))
    return list(db.scalars(select(pk).where(model.project_id == project_id, model.is_active,
                                            model.data_entity_id.is_not(None), ~io)))


# ---- the graph (D-21: data, not a picture) -----------------------------------------------------------

def steps_under(db: Session, node: BfcNode) -> list[BfcNode]:
    """The active process steps under a parent node, in the node's own chart — shared by the DFD
    and the ERD's subject area."""
    return list(db.scalars(select(BfcNode).where(
        BfcNode.project_id == node.project_id, BfcNode.bfc_set_code == node.bfc_set_code,
        BfcNode.is_active, BfcNode.is_process,
        BfcNode.hier_code.startswith(f"{node.hier_code}.")).order_by(BfcNode.hier_code)))


def _l1(hier_code: str) -> str:
    return hier_code.split(".", 1)[0]


def _cross_area(db: Session, node: BfcNode, de_ids: set[int]) -> list[int]:
    """A-S3-2: counted across the WHOLE chart, not the frame. W = L1 areas writing the DE ('O'),
    R = L1 areas reading it ('I'); cross-area iff some writer area differs from some reader area."""
    if not de_ids:
        return []
    rows = db.execute(select(BfcNodeDataEntity.data_entity_id, BfcNodeDataEntity.direction, BfcNode.hier_code)
                      .join(BfcNode, BfcNode.bfc_node_id == BfcNodeDataEntity.bfc_node_id)
                      .where(BfcNodeDataEntity.project_id == node.project_id, BfcNodeDataEntity.is_active,
                             BfcNodeDataEntity.data_entity_id.in_(de_ids), BfcNode.bfc_set_code == node.bfc_set_code,
                             BfcNode.is_active, BfcNode.is_process)).all()
    areas: dict[int, dict[str, set[str]]] = {}
    for de_id, direction, hier in rows:
        areas.setdefault(de_id, {"I": set(), "O": set()})[direction].add(_l1(hier))
    return sorted(de_id for de_id, a in areas.items() if any(w != r for w in a["O"] for r in a["I"]))


def derive_order(io: list[BfcNodeDataEntity]) -> list[dict]:
    """B follows A when A writes a DE that B reads (A ≠ B); one row per pair, entities aggregated."""
    writers: dict[int, set[int]] = {}
    readers: dict[int, set[int]] = {}
    for r in io:
        (writers if r.direction == "O" else readers).setdefault(r.data_entity_id, set()).add(r.bfc_node_id)
    pairs: dict[tuple[int, int], set[int]] = {}
    for de, ws in writers.items():
        for a in ws:
            for b in readers.get(de, ()):
                if a != b:
                    pairs.setdefault((a, b), set()).add(de)
    return [{"from_bfc_node_id": a, "to_bfc_node_id": b, "data_entity_ids": sorted(d)}
            for (a, b), d in sorted(pairs.items())]


def rank(ids: list[int], order: list[dict]) -> dict[int, int]:
    """Left-to-right rank: condense the order into strongly connected components (Tarjan, so loops
    are legal and terminate), then rank = longest path from a source component (Q-33)."""
    succ: dict[int, set[int]] = {i: set() for i in ids}
    for o in order:
        succ[o["from_bfc_node_id"]].add(o["to_bfc_node_id"])
    index, low, stack, on, comp, counter = {}, {}, [], set(), {}, [0]

    def strong(v):                                   # iterative Tarjan: no recursion limit on 2,000 steps
        work = [(v, iter(sorted(succ[v])))]
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        while work:
            node, it = work[-1]
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter[0]
                    counter[0] += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(sorted(succ[w]))))
                    break
                if w in on:
                    low[node] = min(low[node], index[w])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    while True:
                        w = stack.pop()
                        on.discard(w)
                        comp[w] = node
                        if w == node:
                            break
    for v in ids:
        if v not in index:
            strong(v)
    csucc: dict[int, set[int]] = {}
    indeg: dict[int, int] = {c: 0 for c in set(comp.values())}
    for a, bs in succ.items():
        for b in bs:
            ca, cb = comp[a], comp[b]
            if ca != cb and cb not in csucc.setdefault(ca, set()):
                csucc[ca].add(cb)
                indeg[cb] += 1
    level = {c: 0 for c in indeg}
    ready = sorted(c for c, d in indeg.items() if d == 0)
    while ready:
        c = ready.pop()
        for d in sorted(csucc.get(c, ())):
            level[d] = max(level[d], level[c] + 1)
            indeg[d] -= 1
            if indeg[d] == 0:
                ready.append(d)
    return {i: level[comp[i]] for i in ids}


def _lanes(db: Session, steps: list[BfcNode]) -> tuple[list[dict], dict[int, str]]:
    """One lane per distinct performer, plus UNASSIGNED; org units by (level, seq), roles by
    (unit, code), applications by code, AI by label (§9.8)."""
    unit_ids = {s.performer_org_unit_id for s in steps if s.performer_org_unit_id}
    role_ids = {s.performer_org_role_id for s in steps if s.performer_org_role_id}
    app_ids = {s.performer_application_id for s in steps if s.performer_application_id}
    roles = {r.org_role_id: r for r in db.scalars(select(OrgRole).where(OrgRole.org_role_id.in_(role_ids)))} if role_ids else {}
    units = {u.org_unit_id: u for u in db.scalars(select(OrgUnit).where(
        OrgUnit.org_unit_id.in_(unit_ids | {r.org_unit_id for r in roles.values()})))} if unit_ids or roles else {}
    apps = {a.application_id: a for a in db.scalars(select(Application).where(
        Application.application_id.in_(app_ids)))} if app_ids else {}
    key_of: dict[int, str] = {}
    lanes: dict[str, dict] = {}
    for s in steps:
        if s.performer_kind == "ORG_UNIT":
            u = units[s.performer_org_unit_id]
            k, lane = f"ORG_UNIT:{u.org_unit_id}", {"kind": "ORG_UNIT", "ref_id": u.org_unit_id,
                                                    "code": u.org_unit_code, "name": u.org_unit_name,
                                                    "sort": (0, u.level_no or 99, u.seq_no or 0, u.org_unit_code)}
        elif s.performer_kind == "ORG_ROLE":
            r = roles[s.performer_org_role_id]
            u = units.get(r.org_unit_id)
            k, lane = f"ORG_ROLE:{r.org_role_id}", {"kind": "ORG_ROLE", "ref_id": r.org_role_id,
                                                    "code": r.org_role_code, "name": r.org_role_name,
                                                    "unit_name": u.org_unit_name if u else None,
                                                    "sort": (1, u.org_unit_code if u else "", r.org_role_code)}
        elif s.performer_kind == "APPLICATION":
            a = apps[s.performer_application_id]
            k, lane = f"APPLICATION:{a.application_id}", {"kind": "APPLICATION", "ref_id": a.application_id,
                                                          "code": a.application_code, "name": a.application_name,
                                                          "sort": (2, a.application_code)}
        elif s.performer_kind == "AI":
            k, lane = f"AI:{s.performer_label}", {"kind": "AI", "ref_id": None, "code": None,
                                                  "name": s.performer_label, "sort": (3, s.performer_label)}
        else:
            k, lane = "UNASSIGNED", {"kind": "UNASSIGNED", "ref_id": None, "code": None, "name": None,
                                     "sort": (9,)}
        key_of[s.bfc_node_id] = k
        lanes.setdefault(k, {"lane_key": k, **lane})
    ordered = sorted(lanes.values(), key=lambda lane: lane.pop("sort") if "sort" in lane else ())
    return ordered, key_of


def _systems(db: Session, node: BfcNode, steps: list[BfcNode]) -> dict[int, list[dict]]:
    """The supporting systems in each box (§9.8): as-is ← application_bfc_node; to-be ← BR →
    br_solution → application_solution, only while SOLUTION and APPLICATION are on (OR-2)."""
    ids = [s.bfc_node_id for s in steps]
    out: dict[int, list[dict]] = {i: [] for i in ids}
    if not ids:
        return out
    if node.bfc_set_code == "AS_IS":
        rows = db.execute(select(ApplicationBfcNode.bfc_node_id, Application).join(
            Application, Application.application_id == ApplicationBfcNode.application_id).where(
            ApplicationBfcNode.bfc_node_id.in_(ids), ApplicationBfcNode.is_active)).all()
    else:
        on = components.enabled(db, node.project_id)
        if not {"SOLUTION", "APPLICATION"} <= on:
            return out
        rows = db.execute(select(BusinessRequirement.bfc_node_id, Application)
                          .join(BrSolution, BrSolution.br_id == BusinessRequirement.br_id)
                          .join(ApplicationSolution, ApplicationSolution.solution_id == BrSolution.solution_id)
                          .join(Application, Application.application_id == ApplicationSolution.application_id)
                          .where(BusinessRequirement.bfc_node_id.in_(ids), BusinessRequirement.is_active,
                                 BrSolution.is_active, ApplicationSolution.is_active)).all()
    for nid, app in rows:
        entry = {"application_id": app.application_id, "application_code": app.application_code,
                 "application_name": app.application_name}
        if entry not in out[nid]:
            out[nid].append(entry)
    for v in out.values():
        v.sort(key=lambda a: a["application_code"])
    return out


def _boundary(db: Session, node: BfcNode, ids: set[int], de_ids: set[int]) -> dict:
    """Stores read in scope and written by a process of the SAME chart outside it (`in`), and the
    reverse (`out`) — drawn as stubs; they replace the old HANDOFF arrows. Never across charts."""
    if not de_ids:
        return {"in": [], "out": []}
    rows = db.execute(select(BfcNodeDataEntity.data_entity_id, BfcNodeDataEntity.direction, BfcNode)
                      .join(BfcNode, BfcNode.bfc_node_id == BfcNodeDataEntity.bfc_node_id)
                      .where(BfcNodeDataEntity.data_entity_id.in_(de_ids), BfcNodeDataEntity.is_active,
                             BfcNode.project_id == node.project_id, BfcNode.bfc_set_code == node.bfc_set_code,
                             BfcNode.is_active, BfcNode.is_process, BfcNode.bfc_node_id.not_in(ids))).all()
    out = {"in": [], "out": []}
    for de, direction, n in rows:
        side = "in" if direction == "O" else "out"           # an outside writer feeds in; an outside reader takes out
        out[side].append({"data_entity_id": de, **_ref(n)})
    for v in out.values():
        v.sort(key=lambda r: (r["data_entity_id"], r["hier_code"]))
    return out


def generate_dfd(db: Session, node: BfcNode) -> dict:
    """§9.8: for a live non-process node of either chart, its process descendants in that chart,
    their performer lanes, stores, external parties, triggers, the flows between them, the derived
    order with a loop-safe rank, the boundary stubs, the completeness gaps and saved positions."""
    if not node.is_active:
        raise HTTPException(409, "This node is retired. Restore it first")
    if node.is_process:
        raise HTTPException(422, "A data flow diagram is drawn for a parent node, not a step")
    steps = steps_under(db, node)
    ids = [s.bfc_node_id for s in steps]

    io = [] if not ids else list(db.scalars(select(BfcNodeDataEntity).where(
        BfcNodeDataEntity.bfc_node_id.in_(ids), BfcNodeDataEntity.is_active)
        .order_by(BfcNodeDataEntity.bfc_node_data_entity_id)))
    ext_rows = [] if not ids else list(db.scalars(select(BfcNodeExternalFlow).where(
        BfcNodeExternalFlow.bfc_node_id.in_(ids), BfcNodeExternalFlow.is_active)
        .order_by(BfcNodeExternalFlow.bfc_node_external_flow_id)))
    trig_rows = [] if not ids else list(db.scalars(select(BfcNodeTrigger).where(
        BfcNodeTrigger.bfc_node_id.in_(ids), BfcNodeTrigger.is_active).order_by(BfcNodeTrigger.bfc_node_trigger_id)))
    de_ids = {r.data_entity_id for r in io} | {x.data_entity_id for x in ext_rows if x.data_entity_id}
    des = {d.data_entity_id: d for d in db.scalars(select(DataEntity).where(
        DataEntity.data_entity_id.in_(de_ids)))} if de_ids else {}
    exts = {x.external_entity_id: x for x in db.scalars(select(ExternalEntity).where(
        ExternalEntity.external_entity_id.in_({r.external_entity_id for r in ext_rows})))} if ext_rows else {}
    trigs = {t.process_trigger_id: t for t in db.scalars(select(ProcessTrigger).where(
        ProcessTrigger.process_trigger_id.in_({r.process_trigger_id for r in trig_rows})))} if trig_rows else {}
    brs = {b.bfc_node_id: b.br_number for b in db.scalars(select(BusinessRequirement).where(
        BusinessRequirement.bfc_node_id.in_(ids), BusinessRequirement.is_active))} if ids else {}

    lanes, lane_of = _lanes(db, steps)
    systems = _systems(db, node, steps)
    order = derive_order(io)
    # DR13-P4, option A: with no derived order in scope (a rule without the data elements, or no data yet), the
    # processes stand left to right in CHART order — seq_no under each parent, in hier_code order. Nothing stored,
    # no arrows drawn; the screen labels it "chart order".
    order_source = "DERIVED" if order else "CHART"
    ranks = rank(ids, order) if order else {i: n for n, i in enumerate(ids)}
    gaps = missing_io(db, node.project_id, [node.bfc_set_code], ids)
    performers = {s.bfc_node_id for s in steps if s.performer_kind}

    covered = {(x.bfc_node_id, x.data_entity_id, x.direction) for x in ext_rows if x.data_entity_id}
    flows = [{"kind": "STORE", "bfc_node_id": r.bfc_node_id, "direction": r.direction,
              "data_entity_id": r.data_entity_id, "external_entity_id": None, "process_trigger_id": None,
              "label": des[r.data_entity_id].de_name,
              "link_id": r.bfc_node_data_entity_id, "row_version": r.row_version}
             for r in io if (r.bfc_node_id, r.data_entity_id, r.direction) not in covered]
    flows += [{"kind": "EXTERNAL", "bfc_node_id": x.bfc_node_id, "direction": x.direction,
               "data_entity_id": x.data_entity_id, "external_entity_id": x.external_entity_id,
               "process_trigger_id": None,
               "label": des[x.data_entity_id].de_name if x.data_entity_id else x.flow_label,
               "link_id": x.bfc_node_external_flow_id, "row_version": x.row_version}
              for x in ext_rows]
    flows += [{"kind": "TRIGGER", "bfc_node_id": t.bfc_node_id, "direction": "I", "data_entity_id": None,
               "external_entity_id": None, "process_trigger_id": t.process_trigger_id,
               "label": trigs[t.process_trigger_id].trigger_name,
               "link_id": t.bfc_node_trigger_id, "row_version": t.row_version} for t in trig_rows]
    return {
        "scope": _ref(node),
        "lanes": lanes,
        "processes": [{**_ref(s), "lane_key": lane_of[s.bfc_node_id], "br_number": brs.get(s.bfc_node_id),
                       "systems": systems[s.bfc_node_id], "rank": ranks[s.bfc_node_id],
                       "data_processing_desc": s.data_processing_desc} for s in steps],
        "stores": [{"data_entity_id": d.data_entity_id, "de_number": d.de_number, "de_name": d.de_name}
                   for d in sorted(des.values(), key=lambda d: d.de_number)],
        "externals": [{"external_entity_id": x.external_entity_id, "ext_number": x.ext_number,
                       "ext_name": x.ext_name} for x in sorted(exts.values(), key=lambda x: x.ext_number)],
        "triggers": [{"process_trigger_id": t.process_trigger_id, "trigger_name": t.trigger_name,
                      "trigger_kind": t.trigger_kind, "schedule_note": t.schedule_note}
                     for t in sorted(trigs.values(), key=lambda t: t.trigger_name.lower())],
        "flows": flows,
        "order": order,
        "order_source": order_source,
        "boundary": _boundary(db, node, set(ids), set(des)),
        "completeness": {**gaps, "no_performer": [_ref(s) for s in steps if s.bfc_node_id not in performers],
                         # D-70: recommended elements outside the rule — information on the warnings panel, never a gap
                         "advised": {i: p["advised"] for i, p in readiness(
                             db, node.project_id, node.bfc_set_code, ids)["processes"].items() if p["advised"]}},
        "cross_area": _cross_area(db, node, set(des)),
        "layout": diagram_layout.positions(db, node.project_id, "DFD", node.bfc_node_id),
    }
