"""As-is and to-be areas side by side (Q-28, SC-5). The two charts have their own node ids and no provenance (D-47), so
an as-is area and a to-be area are paired only when level, chart code AND normalised name agree; anything else is
unmatched, with its reason, and never set against the other side. The one rule for every report that compares the
charts — `process_volume.summary` and `reports.application_gap` (playbook §10, slice 1f §3.4)."""
from models import BfcNode

SETS = ("AS_IS", "TO_BE")


def norm(name: str | None) -> str:
    """The live-name rule, lower(btrim(...)) (S1-6)."""
    return (name or "").strip().lower()


def pair_areas(areas: dict[str, dict[str, BfcNode]]) -> tuple[list[tuple[str, BfcNode, BfcNode]], list[dict]]:
    """`areas` is {chart: {hier_code: area node}} for one level. Returns the matched (code, as-is, to-be) triples and the
    unmatched areas, each {chart, hier_code, name, reason, other_code}, both in chart-code order."""
    names = {s: {norm(a.node_name): code for code, a in areas[s].items()} for s in SETS}
    matched, unmatched = [], []
    for code in sorted(areas["AS_IS"].keys() | areas["TO_BE"].keys()):
        a, b = areas["AS_IS"].get(code), areas["TO_BE"].get(code)
        if a and b and norm(a.node_name) == norm(b.node_name):
            matched.append((code, a, b))
            continue
        for chart, side, other in (("AS_IS", a, "TO_BE"), ("TO_BE", b, "AS_IS")):
            if side is None:
                continue
            elsewhere = names[other].get(norm(side.node_name))
            # a reorder that swapped two areas reads "probably reordered", not "renamed"
            reason = ("NAME_ELSEWHERE" if elsewhere and elsewhere != code else
                      "CODE_SAME_NAME_DIFFERS" if (a and b) else f"ONLY_{chart}")
            unmatched.append({"chart": chart, "hier_code": code, "name": side.node_name, "reason": reason,
                              "other_code": elsewhere if reason == "NAME_ELSEWHERE" else None})
    return matched, unmatched
