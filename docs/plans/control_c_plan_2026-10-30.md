# Value Bridge — next slice: Control-C plan (2026-10-30)

**For:** Ren / Ben · **By:** Lilly · **Status:** plan only, awaiting approval. Nothing is built, branched or migrated.
**Counted from:** `origin/main` at `923a4e7` (Control-A, B1 and B2 merged).
**Sources:** `docs/VB_remaining_work.md`, `docs/slice_control_a_spec.md` (§0 plan line, Control-C),
`docs/slice_control_b_spec.md` §9, `docs/VB_design.md` §7.9 and §7.13, `backend/services/control.py`, and
`backend/models/control.py`.

---

## 1. What is left, by phase and slice

| Phase | Slice | Days | Blocked by |
|---|---|---:|---|
| **1 Finish the scope core** | **Control-C** (this plan) | 1.5–1.8 | Ben's numbers for two new rules (Q2, Q3); C3 waits for the migration slot (Q4) |
| 1 | ERD saved as SVG (PNG done, function 41) | 0–1.5 | Open question in design history §1 (Q8) |
| **2 Delivery control modules** | Benefits (`BEN-`, value ranking, no-benefit check) | 2.5 | New tables, so the migration slot; spec owed |
| 2 | Change requests (`CR-`, impact trace, pricing, decision) | 4 | Migration slot; spec owed |
| 2 | Risks (`RSK-`, score, promote to an issue) | 2 | Migration slot; spec owed |
| 2 | Decisions (append-only log) | 1.5 | Migration slot; spec owed |
| 2 | WBS import + progress | 3.5 | Migration slot; spec owed |
| **3 Ready for the first client** | Port slice 16's ARCHIVE / DELETE_ARCHIVE runs onto main's `purge_run` ("not here yet") | ~1 | Nothing |
| 3 | Client read-only login + offline viewer | 3 | The login half waits on Ben's sign-in decision (Entra); the viewer does not |
| 3 | Full review pass (Sara at production depth + the VB-005 backlog) | 2 | Gate: Ben goes through the backlog line by line |
| 3 | Azure (Container Apps, private PostgreSQL, Key Vault, roles, purge job, Entra sign-in) | 4 | Azure / Entra access — Ben's, once the app is ready |
| 3 | Restore drill (point-in-time restore) | 1 | The Azure database |
| 3 | Prompt pack sign-off | 0.5 | Ben's review |
| **4 After first client use** | Program roll-ups 2 · Languages 4 · Version comparison screen 3 | 9 | Nothing |
| On hold | DFD redesign (`docs/plans/DFD-REDESIGN-plan.md`) | — | Ben put it on hold |

Already done since the 2026-10-20 plan: the slice 14 Issue screens' browser check, slice 15 waves, slices 16 and 17,
1e Imports (a, b), 1f Reports, and Control-A, B1 and B2.

**Admin steps owed:**
- **After deploy, on every existing database:** run `seeds.seed_control_rules --actor-email <admin>` once. That
  includes Ben's main checkout after he pulls. Without it, `create_project` returns 409.
- Deploy migrations 0068–0081 to Ben's main database.
- Decide whether to drop the leftover Control-B databases: `vb_s2_uat_db`, `vb_s2_test_db` and its four worker
  copies (`_gw0`…`_gw3`).

## 2. Recommendation

**Next slice: Control-C.** Reasons:
- It is the last Phase 1 slice.
- Nothing outside blocks it.
- Pieces C1 and C2 need **no migration**, so it can run alongside a Phase 2 task that holds the migration slot.
- It gives the panel its last measurable rules before the delivery modules start adding their own.

**Alternatives:**
- **Decisions** (1.5 days): the smallest Phase 2 module, but it needs a migration.
- **Risks** (2 days): brings the `risk_register` rule that the panel already lists as coming.
- **ARCHIVE / DELETE_ARCHIVE port** (~1 day): no blockers, but invisible to users until first client use.

## 3. Control-C — scope

**In scope:**
- **Two new analyses** (design §7.9), each with a report tab, a headline figure and a company default rule:
  - `process_change_intensity` — "where change lands".
  - `master_data_candidates`.
- **The FTC company-default screen** for platform admins (`maintain_house_default`, §7.13). It changes future projects
  only; no running engagement moves.
- **Reset a project's rules to the company defaults** (`reset_project_rules_to_house_default`, §7.13), at EDIT.
- **The `fr_unlinked` rule** (function 133), only if Q4 is (a).

**Out of scope:**
- Rules for `application_gap`, `value_ranking`, `issue_dashboard`, `phase_plan` and `consistency_check` (Q6).
- `benefit_gap` and `risk_register`, which come with their Phase 2 modules.
- Verdict history, the M-tiles, and a "confirmed new data" marker on data entities.

## 4. Pieces

### C1 — the two analyses (~0.7 day, ~800 lines)

**`process_change_intensity` ("where change lands"):**
- **What it reads:** live to-be process steps (`is_process`) whose live business requirements carry a live,
  non-rejected solution.
- **Grouping:** rolled up to the top-level (L1) area, keyed by the L1 node's id (never `hier_code`, as CB-1).
- **Table:** per area — changed steps, total steps, and a count per solution category, shown as context only.
- **Headline:** the share of changed steps that sit in the single busiest area (PCT).
- **Not measured:** when no step carries a change, or when there is only one L1 area.
- **Rule:** `PCT_GT`, numbers per Q2.

**`master_data_candidates`:**
- **What it reads:** live data entities used by live to-be requirements in 3 or more distinct L1 areas.
- **Table:** per entity — its areas, its requirements, and its `business_owner_note` (the column already exists).
- **Headline:** how many candidates have no business owner noted (COUNT).
- **Not measured:** when no requirement uses any data entity.
- **Rule:** `GT`, numbers per Q3.

**Both:**
- Added to `services/control_reports.py`, dispatched in `control.headline`, and added to `HOUSE_RULES`.
- Two `GET` routes at `project_ctx(VIEW)`, two Reports tabs, two panel rows, and strings in `en.reports.json` /
  `en.control.json`.
- Rules copied into a running project arrive switched off but are still measured, shown as "not yet agreed" (CB-5).
  New projects get them switched on.
- The CLAUDE.md deploy line gets a Control-C note: run the seed once.

**Grade 2.** A wrong figure would reach a client's steering meeting. Tests:
- Each headline on hand-built data, including a tie between two areas.
- The "not measured" cases, never read as 0.
- Flag and escalate both reached.
- A retired step, requirement, solution or entity is left out; a rejected solution is left out.
- An entity in exactly 2 areas is not a candidate; one in 3 is. An owner note made only of spaces counts as no owner.
- Backfill: the new rules arrive switched off in running projects and switched on in a new project.
- The read-only GET-route leak test still passes (`test_no_get_route_leaks_a_restricted_project`).
- **Deliberately not covered:** weighting by solution category (Q2 keeps every change equal), and timing at the
  design bound beyond one run on the 2,000-requirement fixture.

### C2 — company defaults and reset (~0.8 day, ~700 lines)

**Backend:**
- `GET /control-house-rules` and `PATCH /control-house-rules/{analysis_code}`, guarded by `platform_admin`.
  - The PATCH needs a reason. Its audit entry is `CONTROL_RULE_CHANGED` with no project (Q7). Like CT-3, action and
    escalation text are recorded only as "changed".
  - A stale `row_version` returns 409.
  - A company-default row never takes an owner (the database constraint `ck_ctl_house_no_owner`).
- `POST /projects/{project_id}/control-rules/reset`, guarded by `project_ctx(EDIT)`, needs a reason.
  - It overwrites thresholds, prescribed action and escalation path from the company defaults.
  - It keeps each rule's owner and its on/off state (Q5).
  - It adds any company-default rule the project lacks, switched off.
  - It writes one `CONTROL_RULES_RESET` audit entry (§7.13) with the reason and the codes it changed.

**Frontend:**
- A company-defaults screen, shown only to platform admins.
- A "Reset to FTC defaults" button on the panel for editors, with a reason field and confirmation in amber (an action
  someone may regret).

**Grade 2. The riskiest part is the platform-admin gate.** Tests:
- A staff member, a project ADMIN and an editor are each refused the company-default routes.
- The two routes join `test_project_admin.py`'s list of routes only platform admins can reach.
- `ROUTE_COMPONENTS` and the route-guard criterion stay green.
- A company-default edit leaves every existing project's rules unchanged; a project created afterwards gets the new
  values.
- Reset: a viewer is refused; owners and on/off state are kept; the audit entry is written; a stale version returns
  409; an empty reason returns 422.
- **No mutation harness.** That has to be its own approved task.

### C3 — `fr_unlinked` rule (~0.3 day) — only if Q4 = (a)

- `fr_unlinked` is not in the allowed list `REGISTRY`, and the database constraint `ck_ctl_analysis` refuses it. It
  needs **migration 0082** to add the code to that constraint, reversible, in its own commit. The design §7.13
  registry is updated in the same change.
- **This task may not take a migration.** C3 starts only when Ren confirms the slot is free, and main is merged in
  first.
- **Headline:** live FRs with no live business-requirement link (COUNT), with their effort days beside it.
- **Rule:** `GT`; recommended flag above 0, escalate above 5.
- **Tests:** a test for migration 0082 going up and back down, plus the headline cases.

## 5. Process, ports, databases

- **Spec:** `docs/slice_control_c_spec.md` to the `design-spec` standard, then design-review round 1 and round 2
  (final), then Ben's sign-off.
- **Build:** C1, then C2 (then C3). Each piece gets Sara before its commit, test-runner, and ui-verifier against the
  mockup look. Screenshots go to `Evidence/<date>/control-c/`.
- **Slot 1:** API 8101, web 5181, Vite proxy to `localhost:8101`; databases `vb_s1_uat_db` and `vb_s1_test_db` plus
  its four worker copies (`_gw0`…`_gw3`).
- **Before asking to merge:** merge the latest main, run the full suite (`pytest -m "" -n 4`) on the merged commit
  and name that commit, run frontend lint and build, then fast-forward main.

## 6. Size

| Piece | Days | Lines (approx.) |
|---|---:|---:|
| Spec + two review rounds | 0.3 | — |
| C1 two analyses | 0.7 | 800 |
| C2 company defaults + reset | 0.8 | 700 |
| C3 `fr_unlinked` (if Q4 = a) | 0.3 | 250 |
| **Total** | **1.8 (1.5 without C3)** | |

## 7. Questions for Ben — each with Lilly's recommendation

1. **Is Control-C the next slice?**
   - Recommend **yes**: it closes Phase 1 and needs no migration for C1 and C2.
2. **How should "where change lands" be measured?** Every changed step counts the same (no weighting by solution
   category, as CB-2's "every change weighs the same"), and the headline is the share of changed steps in the busiest
   L1 area.
   - Recommend **flag above 50 %, escalate above 70 %**.
   - Prescribed action: "Check the change workload and the change-management plan for that area before the next gate."
3. **How should "master data candidates" be measured?** The headline counts entities used in 3 or more L1 areas that
   have no business owner noted.
   - Recommend **flag above 0, escalate above 5**.
   - Prescribed action (design §7.9): "Assign a single owner; it becomes a managed cross-workstream dependency."
4. **Should "FRs with no requirement" (`fr_unlinked`) get a rule?**
   - (a) Yes: migration 0082 adds it to the allowed list, built as C3 once the migration slot is free.
   - (b) No: it stays a count on the scope dashboard and in the effort summary, with no threshold.
   - Recommend **(a)**.
5. **What should a reset do?** It overwrites thresholds, prescribed action and escalation path with the company
   defaults. It keeps each rule's owner and whether it is on or off, so it never switches on a rule the client hasn't
   agreed to.
   - Recommend **yes, as described**.
6. **Should the other five analyses get rules?** These are application gap, value ranking, issue dashboard, wave plan
   and the consistency check; the design gives them no thresholds.
   - Recommend **not now**: revisit after the first engagement.
7. **Do edits to the company defaults need a reason and an audit entry,** the same as project rules?
   - Recommend **yes**.
8. **Still open from before:**
   - ERD as SVG: recommend **PNG only for now**, and a vector drawing (~1.5 days) only if a deck needs one.
   - Whether to drop the `vb_s2` databases: recommend **yes**.
   - Azure / Entra access: whenever Ben is ready.
