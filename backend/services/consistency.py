"""consistency_check (design §7.12, D11): read-only proofs that a rule the database cannot hold
as a CHECK still holds. Each key is one line of the report; an empty list means it holds.

Lines land with the slice that owns their rule. Slice 4a-3 adds `purge_overdue` (A-4a-5): import
batches past their 90-day window that still hold rows, shown until a purge run removes them, so
a forgotten or failing purge is visible while it runs as a CLI with no schedule. Slice 5 adds
`brsol_under_inactive` (DR1-D1) and Slice 6a `fr_under_inactive_solution` (DR6a-D1), both
must-be-empty lines. Slice 10b adds `brfr_under_inactive` (must be empty) and the warning
`fr_solution_outside_its_brs` (D-52, Q-4)."""
from sqlalchemy.orm import Session

from services import (application, components, consistency_data, dfd_rule, function_requirement, import_purge,
                      interface, solution)

# Lines that report an operations lapse, not scope drift: they never count toward the freeze
# gate's has_errors (§7.12), so a forgotten purge run cannot block a baseline (sara M-2).
INFORMATIONAL = frozenset({"purge_overdue", "as_is_support_by_to_be",
                           "as_is_support_on_to_be"})                    # + 7c Q-23   # + 6b-1 S6b-5: shown, never refusing
# Warning lines: shown, and a freeze warns about them, but they never refuse it (4a-R10; Ben,
# 2026-10-09: a baseline with fieldless entities warns and is still allowed).
WARNINGS = frozenset({"entities_without_fields", "entities_keys_only",   # + D-39
                      "fr_solution_outside_its_brs"})                    # + D-52 (slice10b Q-4, DR10b-S3)
# D-38 / S7-3: amber while editing, a REFUSAL at freeze — a process of a chart whose DFD is on with no
# input-or-trigger, or no output data entity (slice7_schema §9.7).
# Slice 8 [Q-12]: live rows in an off component also refuse the freeze, so a component gate never silently
# leaves a live row out of a baseline (slice8_schema §3.2).
# Slice 13b (D-70, DR13-P1): the keys are the chart's RULE elements, read through process_flow.readiness — the same
# reader as the light. A key whose element is off for a chart lists nothing for it.
FREEZE_BLOCKING_WARNINGS = frozenset({"process_missing_input", "process_missing_output", "rows_in_off_component",
                                      "process_missing_data_in", "process_missing_order",
                                      "diagram_missing_external"})


def consistency_check(project_id: int | None, db: Session) -> dict[str, list]:
    """The report for one project, or across every project when project_id is None (operators).
    Argument order is the design's (§7.12). The caller owns access: a route checks
    require_project(…, REVIEWER) first."""
    return {
        "purge_overdue": import_purge.overdue(db, project_id),
        "entities_without_fields": (consistency_data.entities_without_fields(db, project_id)
                                    if project_id is not None else []),
        "entities_keys_only": (consistency_data.entities_keys_only(db, project_id)
                               if project_id is not None else []),
        "brsol_under_inactive": solution.brsol_under_inactive(db, project_id),
        "fr_under_inactive_solution": function_requirement.fr_under_inactive_solution(db, project_id),
        # slice10b §2.3, §6.12: must be empty (refuses the freeze); and the tag-drift warning (never refuses)
        "brfr_under_inactive": function_requirement.brfr_under_inactive(db, project_id),
        "fr_solution_outside_its_brs": function_requirement.fr_solution_outside_its_brs(db, project_id),
        **application.consistency_lines(db, project_id),
        "interface_under_inactive": interface.interface_under_inactive(db, project_id),
        "rows_in_off_component": (components.rows_in_off_component(db, project_id)       # D-37, DR7-P2
                                  if project_id is not None else []),
        **_process_io(db, project_id),
        # slice 13b, must be empty: a chart with no live rule row (DR13-D3 — the readers fail closed to D-38
        # meanwhile), and a rule breaking the cross-row ORDER-needs-data rule a CHECK cannot see
        "project_without_dfd_rule": dfd_rule.without_rule(db, project_id),
        "dfd_rule_invalid": dfd_rule.invalid(db, project_id),
        "as_is_support_on_to_be": application.support_on_to_be(db, project_id),
    }


def _process_io(db: Session, project_id: int | None) -> dict[str, list]:
    """One line per per-process rule element, plus the per-diagram EXTERNAL line, each from the chart's rule."""
    from services import process_flow
    keys = {f"process_{k}": k for k in process_flow.MISSING_KEYS.values()}
    if project_id is None:
        return {**{line: [] for line in keys}, "diagram_missing_external": []}
    gaps = process_flow.missing_io(db, project_id)
    return {**{line: gaps[k] for line, k in keys.items()},
            "diagram_missing_external": process_flow.diagrams_missing_external(db, project_id)}
