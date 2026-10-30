# Slice Control-A — control rules and the control panel, first cut (spec, 2026-10-30)

**Design:** `VB_design.md` §4.13 (`maintain_control_rule`, `control_panel`), §5.3 `CONTROL_RULE`, §5 constraint table
(`control_rule` row), §7.9 (`headline_value` contract), §7.13 (registry, seeded rules, `control_panel`), D-19, SC-7.
**Status:** draft for Ben's approval; design review round 1 done (§10). **Not in this slice:** see §8.

**The plan line** "Control rules + control panel" (4 days) is cut into three vertical slices:
- **Control-A (this spec, ~1.5 days):** the rules table, the four rules the app can measure today on every project,
  editing a rule with a reason, and the control panel.
- **Control-B (~1.5 days, own spec):** `requirement_volatility`, `org_impact_heatmap`, `stakeholder_engagement`,
  `data_migration_map` — each a report tab, its headline, and its seeded rule with numbers Ben signs off then.
- **Control-C (~1 day, own spec):** the FTC house-default screen (platform admin), reset-to-house-default, the
  `fr_unlinked` threshold (function 133), and the remaining registry analyses.
`benefit_gap` and `risk_register` get their rules with the Benefits and Risks modules (Phase 2). Each later slice adds
its rows to the house tier and to existing projects through the seed (as `seed_effort_rate` did in slice 11) — no rule
is seeded before its figure exists, so no guessed threshold is ever copied into a project (review P1).

## 1. Interface (what goes in, what comes out)
- **Input:** a project editor's change to one rule — threshold, escalate value, owning org role, prescribed action,
  escalation path, on/off — with a reason and the row version they read.
- **Output:** the control panel: one row per rule — analysis, measured figure, threshold, escalate value, verdict
  (GREEN / FLAG / ESCALATE / NOT MEASURED with a reason), owner, prescribed action, escalation path, last changed
  (date and who). Below it, one line naming the analyses still to come and the slice that brings each.
- **Validation:** EDIT on the project (404 → 403 order as everywhere); analysis must have a rule on this project (404
  otherwise; unknown code 422); reason must be non-blank (422); stale row version (409); owner must be a live org role
  **of the same project** (422, and the composite FK refuses it at the database); escalate value, when set, must be
  beyond the threshold in the rule's direction (422).
- **Archive:** every change writes `AUDIT_EVENT CONTROL_RULE_CHANGED` (content per Decision D3); the row keeps
  `change_rationale`, `updated_by`, `updated_at`. No hard delete — switching a rule off is `is_enabled = false`. Not
  baselined (design §5.10 row 40). **Verdicts are computed live and not stored** (A-43): the panel answers "what is
  the state now", not "was this project ever red" — a verdict history would be a new write and a design change.
- **Maintenance loop:** the PMO reads the panel at each steering cycle; thresholds are renegotiated with the client
  and every renegotiation is in the audit trail.

## 2. Data (one migration: `0081_control_rule`)
**Grain:** one row per (project × analysis), plus one FTC house-default row per analysis (`project_id IS NULL`).

| Column | Type | Rule |
|---|---|---|
| `control_rule_id` | bigint identity PK | |
| `project_id` | bigint NULL FK project | NULL = house default |
| `analysis_code` | varchar(40) NOT NULL | CHECK in the 17-code registry (§7.13) |
| `comparison` | varchar(10) NOT NULL | CHECK `GT` / `LT` / `PCT_GT` (design list). An operator the code branches on, CHECK-listed like the S11-2 flow kind. `PCT_GT` compares exactly as `GT`; it only says the figure is a percentage. Not editable in this slice |
| `threshold_value` | numeric(12,2) NOT NULL | |
| `escalate_value` | numeric(12,2) NULL | NULL = this rule never escalates |
| `owner_org_role_id` | bigint NULL | composite FK (`owner_org_role_id`, `project_id`) → `org_role (org_role_id, project_id)`; nullable on project rows per Decision D1 |
| `prescribed_action` · `escalation_path` | text | |
| `is_enabled` | bool NOT NULL default true | |
| `is_house_default` | bool NOT NULL | CHECK `is_house_default = (project_id IS NULL)` |
| `change_rationale` | text NULL | CHECK `row_version = 1 OR change_rationale IS NOT NULL` (as `effort_rate`) |
| `agreed_at` | timestamptz NOT NULL | when the row was first set up; never moved by an edit (review D2) |
| + `AuditMixin` | | `created_by` **nullable only on house rows**: CHECK `project_id IS NULL OR created_by IS NOT NULL` — the code_master precedent (Landmine 4), so the house tier can sit in the test library and on a fresh machine before any admin exists (review P3) |

Indexes: `UNIQUE (analysis_code) WHERE project_id IS NULL`; `UNIQUE (project_id, analysis_code) WHERE project_id IS NOT
NULL`. CHECK `project_id IS NOT NULL OR owner_org_role_id IS NULL`. Grants: `vb_app` SELECT/INSERT/UPDATE, no DELETE.
Added to `models/__init__.py`. Not shadowed, not in `freeze_set`. Purge: project rows go with `purge_project`; house
rows are untouched (`purge_run.classify` by `project_id`). `restore_record` keeps excluding it (R2-S5).
**Retiring an org role that owns a rule is refused** (refuse, never cascade) until the rule is re-pointed; a
`lifecycle.LABELS` entry names the analysis in the 409 (review D5).

**The four seeded rules** (house tier, copied into every project; from §7.13's table, for Ben to sign off with this spec):

| `analysis_code` | Unit | Comparison | Flag over | Escalate over | Prescribed action (seeded text) |
|---|---|---|---:|---:|---|
| `priced_diff` | % | PCT_GT | 5 | 10 | Raise a CR to steering; name the displacement |
| `coverage` | count | GT | 0 | — | Assign owner + date per gap; do not pass the gate |
| `solution_matrix` | % | PCT_GT | 70 | 85 | Commission the org/process workstream, or lower the benefit forecast |
| `interface_load` | % | PCT_GT | 25 | 35 | Stand up an integration workstream; book test environments |

**Seeding.**
- `seeds/seed_control_rules.py`: inserts the house rows when missing (no author, never overwrites — after first run
  they are platform-admin data). With `--actor-email <admin>` it also copies any house rule a live project lacks into
  it (idempotent per project × analysis, one `CONTROL_RULES_SEEDED` audit per project naming the codes added). The
  test harness seeds the house rows into its library snapshot. CLAUDE.md gets the first-time line (after
  `seed_code_master`) and a "Control-A deploy" line for existing projects.
- `create_project` copies the house rows **inside its own transaction, before its commit**, as `numbering.seed_all`
  and `seed_rate_card` do (replacing the comment at `services/project.py:93`); its audit detail lists the codes.
  An empty house tier refuses `create_project` with 409 naming the seed.

## 3. Measuring (`services/control.py`, one module; the §7.9 `headline_value` contract)
Every analysis returns `{measured: number | None, unit, reason: str | None, note: str | None}`. `None` + reason = NOT
MEASURED, never 0. Each wraps a report that already exists — no new cross-table SQL:

| Analysis | Headline | NOT MEASURED when |
|---|---|---|
| `priced_diff` | **net** effort growth % = `net_days / base_days × 100`, from the latest **approved** baseline (`baseline.agreed_id`) to live, via `baseline.diff` + `priced`. Added and removed days shown beside it | no approved baseline; EFFORT off; `base_days = 0`; that baseline fails its integrity check (this row only, reason says so — review D4) |
| `coverage` | count of rows on the coverage report's **warning** lines | every warning line is off (no component it needs is on — review D3) |
| `solution_matrix` | `technology_share` % from `reports.solution_matrix` | SOLUTION off; no live non-rejected solution |
| `interface_load` | live FRs whose type behaviour is INTERFACE, as % of live FRs (VB law 5) | FUNCTION_REQUIREMENT off; no live FR |

**Unrated FRs (review D1, Decision D2):** when `unrated_fr_count > 0`, the `priced_diff` row says "N FRs added or
changed are not yet rated", and a verdict that would be GREEN becomes FLAG.

**Verdict:** disabled rule → shown greyed, no verdict. `GT`/`PCT_GT`: ESCALATE if `escalate_value` set and measured >
it; FLAG if measured > threshold; else GREEN. `LT` mirrors with <. Equal to the threshold is GREEN (the seeded wording
is "> 5 %"). The panel is one read-only REPEATABLE READ snapshot, like `diff_for_api`.

## 4. Routes (`routers/control.py`, under `/api/v1`, one guard each)
| Method + path | Guard | Does |
|---|---|---|
| `GET /projects/{id}/control-panel` | `project_ctx(VIEW)` | §3 rows in the seeded-table order, plus the "still to come" list |
| `GET /projects/{id}/control-rules` | `project_ctx(VIEW)` | the rules with `row_version`, for the edit dialog |
| `PATCH /projects/{id}/control-rules/{analysis_code}` | `project_ctx(EDIT)` | §1 validation, update, audit. No `component=`: control is not a component; the path matches no `ROUTE_COMPONENTS` fragment, so criterion 49b passes it as it stands |

PATCH body is a **full replacement** of the editable fields — `threshold_value`, `escalate_value`,
`owner_org_role_id`, `prescribed_action`, `escalation_path`, `is_enabled` (all required; `null` clears the nullable
ones) — plus `change_rationale` and `row_version`. `comparison`, `agreed_at`, `created_by` are server-set (VB law 6).

## 5. Screen — "Control" in the project left rail
`features/control/ControlPanelPage.jsx`, `<Page crumb=…>`, strings in `i18n/en.control.json`, routes in
`app/links.js`, one API function per route in `api/scope.js`. Rows built from `components/kit.jsx`: `Status` for the
verdict (colours from `STATUS_COLOR_MAP`; amber not used — reserved for regret-able actions), the measured figure beside
the threshold, owner ("Owner not named" tag when NULL), action, escalation path, and **"Last changed <date> by <name>"**
(review D2 — never "agreed"). Each row links to its report (Coverage / Solution matrix tabs, Interfaces, Compare
baselines). An Edit button per row (hidden through `useCanEdit`) opens a dialog: number fields, an org-role picker
(live roles of this project), on/off, a required reason; 409 → "someone changed this rule, reload". No mockup exists for
this screen (checked `docs/mockups/`): composed from the kit; nothing faked. Free text renders as text (VB law 9).

## 6. Risk and tests — Grade 2
**Grade 2:** a wrong verdict (a GREEN that should be ESCALATE) reaches a steering decision; correctable once noticed,
and every threshold change is audited. No money moves, no access is granted (standard guards), nothing is destroyed.
Proposed depth — direct tests, no mutation harness:
1. Migration up/down; partial unique indexes; house/owner/author CHECKs; cross-project owner refused by the FK.
2. Seed: house rows once, never overwritten; copied to projects lacking them; re-run is a no-op.
3. `create_project` copies the four rules in its transaction; empty house tier → 409.
4. PATCH: reason required; stale row_version 409; unknown analysis 422; owner from another project 422; escalate on
   the wrong side 422; VIEW-level and VIEWER refused 403; audit row content per D3.
5. Each headline on a small fixture, including every NOT MEASURED reason and the unrated-FR FLAG.
6. Verdicts at each boundary: equal → GREEN, just over → FLAG, over escalate → ESCALATE, escalate NULL never
   escalates, disabled rule shows no verdict.
7. Retiring an owning org role → 409 naming the analysis.
8. Existing guards: `test_route_guards` (49/49b), `test_access::test_no_get_route_leaks_a_restricted_project`.
9. Browser (ui-verifier): panel shows verdicts on a seeded project; edit a threshold so a row flips to FLAG; a VIEW
   user sees no Edit.
**Left uncovered on purpose:** each headline is checked against its source report on one fixture only (the reports
have their own tests); concurrent edits beyond the row_version 409.

## 7. Working assumptions (ASSUMPTION — confirm or correct)
- A1 `priced_diff` measures **net** growth from the latest **approved** baseline (what the client signed).
- A2 `coverage` counts only warning lines, measured continuously (not only at gates): the panel shows now what would
  stop the next gate.
- A3 Rules can be switched off but not removed.
- A4 The panel is visible to everyone who can see the project (VIEW), editing at EDIT (SC-7); no notification on a
  threshold change beyond the audit row and the "last changed" line.

## 8. Not in this slice
House-default editing and reset (Control-C), the analyses without a headline yet (Control-B/C, Phase 2), the
`fr_unlinked` threshold, the program control-status roll-up (Phase 4), the M-tiles on the dashboard, a stored verdict
history. The two piece-b import-preview items (preview opens filtered to errors and warnings; a wrong removal count
shows a red outline with no message) are not touched — this slice does not touch the import screen.

## 9. Decisions for Ben
- **D1 — Can a project's rule exist before its owner is named?** The design says a project rule's owner is NOT NULL
  and that `create_project` copies rules before the client's org chart exists; both cannot hold. Recommend: nullable,
  panel tags "Owner not named", Control-C's coverage line reports it.
- **D2 — Uncosted growth.** New FRs with no rating count 0 days, so growth reads GREEN until estimating. Recommend: a
  GREEN becomes FLAG while any added/changed FR is unrated.
- **D3 — What the audit keeps of the free text.** The audit log can never be corrected; escalation paths usually name
  people. Recommend: numbers, owner id, on/off and the reason in full; the two text fields recorded as "changed" only
  (the slice 14 R7 precedent). The design's §7.13 says full from/to, so this changes the design wording.

## 10. Design review round 1 (design-auditor, 2026-10-30) — dispositions
9 findings (2 HIGH, 3 MEDIUM, 4 LOW), none structural.
- **P1 HIGH** house numbers unstated / some unmeasurable — **fixed**: only the four measurable rules are seeded, with
  numbers in §2 for sign-off; the rest wait for their slice.
- **D1 HIGH** unrated FRs read as 0 % growth — **to Ben** as D2, recommendation in place in §3.
- **P2 MED** "was it ever red" promised but not kept — **fixed**: claim removed; verdict history named as not in scope.
- **P3 MED** house tier vs test harness / fresh machine — **fixed**: nullable author on house rows only, library seed.
- **D2 MED** "agreed" date moved by any edit — **fixed**: `agreed_at` never moves; panel shows "last changed by".
- **S1 MED** free text in append-only audit — **to Ben** as D3.
- **P4 LOW** transaction wording — **fixed** (§2). **D3 LOW** coverage all-off reads 0 — **fixed** (§3).
  **D4 LOW** damaged baseline — **fixed** (§3). **D5 LOW** org-role retire block unlabelled — **fixed** (§2, test 7).
- Also corrected: `ROUTE_COMPONENTS` has no exempt list (§4); PATCH is full replacement (§4).
Round 2 is the re-check of these changes, run once Ben has answered D1–D3.
