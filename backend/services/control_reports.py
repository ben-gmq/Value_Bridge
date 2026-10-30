"""Control-B analyses (docs/slice_control_b_spec.md §2; design §7.9; CB-1…CB-5, Ben 2026-10-30). Read-only and derived
on every read. Each returns its table AND its headline, so the report tab and the control panel can never disagree.

`headline` is {measured, reason, **figures}: measured None + a reason is NOT MEASURED, never 0 (§7.9)."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import ApplicationBfcNode, BfcNode, BfcNodeDataEntity, BrDataEntity, DataEntity
from services import baseline, components, reports

CHURN = ("ADDED", "CHANGED", "REMOVED")                    # a MOVED (re-order) is not churn
BR, BRL, BFC = "business_requirement", "br_requirement_line", "bfc_node"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _head(measured=None, reason=None, **figures) -> dict:
    return {"measured": measured, "reason": reason, **figures}


# ---- 2.1 requirement volatility (CB-1) -----------------------------------------------------------------------------
def _l1_of(nodes: dict[int, dict], node_id: int | None) -> int | None:
    """The L1 ancestor of a node on ONE side, by that side's own frozen parent ids — an area is its L1 node's id, never
    its hier_code, which renumbers when an area is inserted above it (review R1-D1)."""
    seen = set()
    while node_id in nodes and node_id not in seen:
        seen.add(node_id)
        parent = nodes[node_id]["parent_bfc_node_id"]
        if parent is None:
            return node_id
        node_id = parent
    return None


def _side(db: Session, project_id: int, b) -> dict:
    cache: dict = {}
    lab = baseline._Labeller(db, project_id, b, cache)
    nodes, brs = lab.rows(BFC), lab.rows(BR)
    members: dict[int, set[int]] = {}
    for br_id, r in brs.items():
        area = _l1_of(nodes, r["bfc_node_id"])
        if area is not None:
            members.setdefault(area, set()).add(br_id)
    return {"baseline": b, "nodes": nodes, "brs": brs, "members": members}


def _touched(db: Session, project_id: int, a: dict, b: dict) -> set[int]:
    """BRs added, changed or removed between two sides; a change to one of a BR's requirement lines is a change to the
    BR (sara H2, as baseline._exposed). Lines one side never froze are new structure, not a change."""
    d = baseline.diff(db, project_id, a["baseline"], b["baseline"])
    out = {r["source_id"] for r in d["entities"][BR]["rows"] if r["change"] in CHURN}
    lines = d["entities"].get(BRL, {})
    if not lines.get("not_frozen_in") and lines.get("rows"):
        la = baseline._side_rows(db, project_id, a["baseline"], BRL)
        lb = baseline._side_rows(db, project_id, b["baseline"], BRL)
        for r in lines["rows"]:
            if r["change"] in CHURN:
                row = (la if r["change"] == "REMOVED" else lb).get(r["source_id"])
                if row is not None:
                    out.add(row["br_id"])
    return out


def _churning(a: dict, b: dict, touched: set[int]) -> set[int]:
    """An area churns when a BR under it was added, changed or removed, or when the set of BRs under it differs (a
    sub-tree moved in or out, review round 2 N1). A new area is not churn only if every one of its BRs is new (R1-D2)."""
    out = set()
    for area in a["members"].keys() | b["members"].keys():
        was, now = a["members"].get(area, set()), b["members"].get(area, set())
        if not was:
            if any(br in a["brs"] for br in now):
                out.add(area)
        elif was != now or (was | now) & touched:
            out.add(area)
    return out


def requirement_volatility(db: Session, project_id: int) -> dict:
    """§7.9 requirement_volatility: churning L1 areas per pair of consecutive baselines, in freeze order. Headline =
    the longest current run — consecutive generations ending at the latest baseline in which one area churned."""
    chain = sorted(baseline.list_baselines(db, project_id), key=lambda b: (b.major_no, b.minor_no))
    out = {"generated_at": _now(), "generations": [], "areas": []}
    if len(chain) < 2:
        return {**out, "headline": _head(reason="NO_BASELINE_PAIR", baselines=len(chain))}
    for b in chain:                                       # the whole chain, on the tab and the panel alike (R1-D3)
        if not baseline.verify(db, b):
            return {**out, "headline": _head(reason="BASELINE_DAMAGED", baseline_label=b.version_label)}
    sides = [_side(db, project_id, b) for b in chain]
    gens = [_churning(a, b, _touched(db, project_id, a, b)) for a, b in zip(sides, sides[1:])]
    names: dict[int, dict] = {}
    for s in sides:                                       # the latest side naming an area wins
        for area in s["members"].keys() | {i for i, n in s["nodes"].items() if n["parent_bfc_node_id"] is None
                                            and n["bfc_set_code"] == "TO_BE"}:
            n = s["nodes"][area]
            names[area] = {"bfc_node_id": area, "hier_code": n["hier_code"], "area_name": n["node_name"],
                           "in_latest": s is sides[-1]}
    areas = []
    for area, meta in names.items():
        churned = [area in g for g in gens]
        run = 0
        for c in reversed(churned):
            if not c:
                break
            run += 1
        areas.append({**meta, "churned": churned, "current_run": run})
    areas.sort(key=lambda r: (not r["in_latest"], reports._hier_key(r["hier_code"])))
    longest = max((a["current_run"] for a in areas), default=0)
    return {**out,
            "generations": [{"from_label": a["baseline"].version_label, "to_label": b["baseline"].version_label,
                             "churning": len(g)} for a, b, g in zip(sides, sides[1:], gens)],
            "areas": areas,
            "headline": _head(longest, generations=len(gens),
                              areas_running=sum(1 for a in areas if a["current_run"] == longest and longest))}


# ---- 2.4 data migration map (CB-4) ---------------------------------------------------------------------------------
def _entity_out(e: DataEntity) -> dict:
    return {"data_entity_id": e.data_entity_id, "de_number": e.de_number, "de_name": e.de_name}


def data_migration_map(db: Session, project_id: int) -> dict:
    """§7.9 data_migration_map: for each live entity a live to-be BR uses, the systems holding it today (AS_IS / BOTH
    applications supporting an as-is step that uses it) and the systems it goes to. Headline = entities needing a data
    ownership decision: seen on as-is with no system, or held by two or more."""
    on = components.enabled(db, project_id)
    out = {"generated_at": _now(), "entities": None, "new_data": None, "retiring": None}
    for need in ("AS_IS", "APPLICATION"):
        if need not in on:
            return {**out, "headline": _head(reason=f"{need}_OFF")}
    sc = reports._Scope(db, project_id)
    ents = {e.data_entity_id: e for e in db.scalars(select(DataEntity).where(
        DataEntity.project_id == project_id, DataEntity.is_active))}
    to_be: dict[int, set[int]] = {}
    for br_id, de_id in db.execute(select(BrDataEntity.br_id, BrDataEntity.data_entity_id).where(
            BrDataEntity.project_id == project_id, BrDataEntity.is_active)):
        if br_id in sc.brs and de_id in ents:
            to_be.setdefault(de_id, set()).add(br_id)
    if not to_be:
        return {**out, "headline": _head(reason="NO_TO_BE_ENTITIES")}
    steps = {n.bfc_node_id: n for n in db.scalars(select(BfcNode).where(
        BfcNode.project_id == project_id, BfcNode.is_active, BfcNode.bfc_set_code == "AS_IS", BfcNode.is_process))}
    as_is: dict[int, set[int]] = {}
    for step_id, de_id in db.execute(select(BfcNodeDataEntity.bfc_node_id, BfcNodeDataEntity.data_entity_id).where(
            BfcNodeDataEntity.project_id == project_id, BfcNodeDataEntity.is_active)):
        if step_id in steps and de_id in ents:
            as_is.setdefault(de_id, set()).add(step_id)
    support: dict[int, set[int]] = {}
    for step_id, app_id in db.execute(select(ApplicationBfcNode.bfc_node_id, ApplicationBfcNode.application_id).where(
            ApplicationBfcNode.project_id == project_id, ApplicationBfcNode.is_active)):
        app = sc.apps.get(app_id)
        if step_id in steps and app is not None and app.lifecycle_code in reports.SUPPORTING:
            support.setdefault(step_id, set()).add(app_id)
    answers = sc.answers() if "SOLUTION" in sc.on else None
    app_key = lambda i: sc.apps[i].application_code  # noqa: E731
    rows, new_data = [], []
    for de_id in sorted(to_be, key=lambda i: ents[i].de_number):
        targets = None
        if answers is not None:
            targets = sorted(set().union(*(sc.app_ids_of_sol.get(s, set()) for b, s in answers if b in to_be[de_id])),
                             key=app_key)
        if de_id not in as_is:
            new_data.append(_entity_out(ents[de_id]))
            continue
        sources = sorted(set().union(*(support.get(s, set()) for s in as_is[de_id])), key=app_key)
        state = "NO_SOURCE" if not sources else "CONFLICTING" if len(sources) > 1 else "OK"
        rows.append({**_entity_out(ents[de_id]), "state": state, "as_is_steps": len(as_is[de_id]),
                     "sources": [reports._app_out(sc.apps[i]) for i in sources],
                     "targets": None if targets is None else [reports._app_out(sc.apps[i]) for i in targets]})
    retiring = [_entity_out(ents[i]) for i in sorted(as_is.keys() - to_be.keys(), key=lambda i: ents[i].de_number)]
    figures = {"in_scope": len(to_be), "no_source": sum(1 for r in rows if r["state"] == "NO_SOURCE"),
               "conflicting": sum(1 for r in rows if r["state"] == "CONFLICTING"), "not_seen_on_as_is": len(new_data)}
    out = {**out, "entities": rows, "new_data": new_data, "retiring": retiring}
    if not rows:                                          # the as-is mapping has not started (review R1-S2)
        return {**out, "headline": _head(reason="AS_IS_NOT_MAPPED", **figures)}
    return {**out, "headline": _head(figures["no_source"] + figures["conflicting"], **figures)}
