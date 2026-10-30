# Slice Control-B — four more control analyses (spec draft, 2026-10-30)

**Design:** `VB_design.md` §7.9 (`requirement_volatility`, `org_impact_heatmap`, `stakeholder_engagement`,
`data_migration_map`, the `headline_value` contract), §7.13 (registry, seeded-rule table, `control_panel`), D-19,
acceptance 72–74; Control-A (`slice_control_a_spec.md`, CT-1…CT-4, round 2 Q1).
**Status:** approved by Ben 2026-10-30 (via Ren), *"yes to all five"* — CB-1…CB-5 as recommended (history §3).
Design review round 1 in §11; round 2 in §12. **Not in this slice:** §9.

**What it adds.** Each of the four analyses becomes (1) a report tab under Reports, (2) one headline number, and (3) a
seeded control rule on the panel. After it, the panel's "still to come" line names only `benefit_gap` and
`risk_register` (Phase 2) and Control-C's items.

**No migration.** `control_rule` (0081) already accepts every registry code and both comparisons used here. No new
table, column, shadow or hash-spec bump. Nothing is frozen.

## 1. Interface
- **Input:** none new — the four reports read what the project already holds (baselines, the to-be chart, RACI, org
  chart, stakeholders, issues, data entities, applications). Rule edits go through Control-A's PATCH as they do today.
- **Output:** four report tabs (§4) and four more panel rows, each with figure, threshold, verdict, owner and action.
- **Validation:** the four new GETs are `project_ctx(VIEW)`, 404 for a project you cannot see. A report whose inputs
  are switched off or not yet filled in says so (NOT MEASURED with a reason, never 0).
- **Archive:** reading writes nothing. The seed writes one `CONTROL_RULES_SEEDED` audit per project naming the codes
  added (Control-A). Switching a backfilled rule on is a PATCH: reason required, `CONTROL_RULE_CHANGED`.
- **Maintenance loop:** as Control-A — the PMO reads the panel each steering cycle; thresholds renegotiated with the
  client, every change audited.

## 2. The four analyses — what each measures, and the number Ben signs off
All four follow the §7.9 contract (`{measured, reason, figures}`; `None` + reason = NOT MEASURED). Equal to the
threshold is GREEN, as in Control-A.

### 2.1 `requirement_volatility` — "is any part of the business still being redefined?" (CB-1)
- **Generations:** every pair of consecutive baselines the project has frozen, in freeze order. Live work is not a
  generation (it is unfinished by definition).
- **An area churns in a generation** when at least one of its business requirements was added, changed or removed
  between the two baselines — a change to one of a BR's requirement lines counts as a change to the BR (sara H2, as
  `_exposed` does). A pure re-order (MOVED) is not churn. An added BR in an existing area is churn: the scope there is
  still being discovered.
- **The area** is the BR's L1 ancestor on the to-be chart as frozen in that baseline, **identified by that L1 node's
  own id** (the frozen row's `source_id`) — never by its `hier_code`, which renumbers when an area is inserted above
  it (review R1-D1). A BR that moved area counts in both.
- **A brand-new area is not churn — only if every one of its BRs is ADDED.** An area that received BRs moved from
  elsewhere (a workshop re-carving "Order to Cash" into two) churns from its first generation (review R1-D2).
- **Headline:** the longest **current** run — consecutive generations, ending at the latest baseline, in which one
  area churned. An area that churned early and has been stable since is history, not a warning (the panel answers
  "now", A-43). Unit COUNT.
- **NOT MEASURED:** fewer than two baselines; any baseline in the chain fails its integrity check (named). Tab and
  panel check the whole chain, so they never disagree (review R1-D3).
- **Recommended rule:** flag when **one area has changed at two freezes running** (v1→v2 and v2→v3), escalate at
  **three running** (stored `GT 1` / `GT 2`). Action: "Pull the area out of the current wave; re-run the workshop".

### 2.2 `org_impact_heatmap` — "is one part of the client's organisation carrying too much of the change?" (CB-2)
- **A change** is a live to-be BR with at least one live, non-rejected solution. A unit is **on** a change when it
  holds a role marked Responsible or Accountable on that BR (by RACI behaviour, VB law 5). Consulted / Informed roles
  are shown but not counted — they hear about the change, they do not absorb it.
- **Per org unit** — the unit the role sits in; no roll-up to parents. **Share** = the changes the unit is on ÷ all
  changes, % (review R1-D4: a share of summed roles hid a unit that is on every change behind 25 %). A unit on every
  change reads 100 %.
- **Headline:** the highest share any one org unit carries, %.
- **Two departures from the design, inside CB-2:** (a) a **share** replaces the design table's "top decile" — a top
  10 % always exists, so "flag the top decile" is red on every project, every day; (b) **to-be RACI only** — the
  as-is RACI sits on as-is steps, and the two charts are not linked step to step (D-47), so there is no honest way to
  say which as-is role a solution changes (shown on the tab as context). The design's escalate ("top decile + zero
  issues") moves to `stakeholder_engagement`, which owns silence, so two rows never say the same thing.
- **NOT MEASURED:** SOLUTION off; no change with an R/A role; fewer than two org units hold roles.
- **Recommended rule:** flag when **one org unit is responsible or accountable for more than 40 %** of the changes,
  escalate **over 60 %**. Action: "Dedicated change agent and a capacity check — they are usually the SMEs too".

### 2.3 `stakeholder_engagement` — "is an affected part of the organisation silent?" (CB-3)
- **Voice:** a unit has a voice when a stakeholder in it, **or in its direct parent unit**, has raised at least one
  live issue (any status). A head of department speaks for the teams directly under them; a sponsor at the top of the
  chart does not speak for the whole client (review R1-S1 — inheriting from any level hid every silent unit).
- **Headline:** the share of changes (2.2's figure) of the **most affected unit with no voice**, %. One number that
  carries both of the design's tests: any affected silent unit shows above zero; a heavily affected one shows high.
- **NOT MEASURED:** ISSUE or SOLUTION off; **no issue logged on the project at all** (the log is not in use yet — every
  unit would read as silent, which is not a signal); 2.2 not measured.
- **Recommended rule:** flag when a silent unit is on **more than 10 %** of the changes, escalate **over 25 %**.
  Action: "Interview before sign-off — silence becomes rejection at UAT". Acceptance 73 is tested on a chart of more
  than ten roughly equal units, not assumed.

### 2.4 `data_migration_map` — "do we know where each piece of data comes from?" (CB-4)
- **In scope:** live data entities used by a live to-be BR.
- **Source:** the applications running today (lifecycle AS_IS or BOTH, `reports.SUPPORTING`) that support an as-is
  process step which uses the entity. **Target:** applications reached from the entity's to-be BRs through their
  solutions.
- **Needs a data-ownership decision:** (a) **no source system** — the entity appears on as-is steps, but none of those
  steps runs on a system (the data lives in spreadsheets or on paper today); (b) **conflicting sources** — two or more
  systems hold it today.
- **Listed but not counted:** entities never seen on an as-is step (new data — nothing to migrate), and as-is
  entities no to-be BR uses (retiring — an archive question, not a migration one). The "never seen on as-is" count
  stands beside the figure on the panel and the tab, so a half-done mapping is visible.
- **Headline:** the number of entities needing a decision. Unit COUNT.
- **NOT MEASURED:** AS_IS or APPLICATION off; no data entity used by a to-be BR; **none of the in-scope entities is
  linked to any as-is step yet** — the as-is mapping has not started, and every entity would read as new (R1-S2).
- **Recommended rule:** flag when **any** entity needs a decision, escalate when **more than 5** do (stored `GT 0` /
  `GT 5`). Action: "Data ownership decision before design freeze".

## 3. Services (`services/reports.py` + `services/control.py`)
- Four report functions in `reports.py`, each returning its table **and** its headline, so the tab and the panel can
  never disagree. They read through existing helpers: `baseline.list_baselines` / `diff` / `verify` for volatility;
  the RACI and solution links for impact; `reports.SUPPORTING` for sources. No new cross-project SQL.
- `control.HOUSE_RULES` gains the four rows (panel order: after the Control-A four). `COMING` loses them.
  `headline()` dispatches to them; the registry test (acceptance 74) covers the eight measured codes.
- `panel()` measures a switched-off rule too and gives it no verdict (§6).
- One REPEATABLE READ snapshot, as the panel today. Volatility diffs every baseline pair; its cost is measured once on
  the demo data before merge.

## 4. Routes and screens
| Method + path | Guard | Does |
|---|---|---|
| `GET /projects/{id}/requirement-volatility` | `project_ctx(VIEW)` | areas × generations grid, headline |
| `GET /projects/{id}/org-impact` | `project_ctx(VIEW)` | units with change counts, shares, R/A and C/I roles, headline |
| `GET /projects/{id}/stakeholder-engagement` | `project_ctx(VIEW)` | units with share, issues raised, voice, headline |
| `GET /projects/{id}/data-migration` | `project_ctx(VIEW)` | entity → sources → targets, the decision list, headline |

Four tabs in `features/reports/ReportsPage.jsx`, built from `reportKit.jsx` and `components/kit.jsx`; strings in
`i18n/en.reports.json`; addresses in `app/links.js`; one API function per route in `api/scope.js`. Each panel row
links to its tab. No mockup exists for these tabs (checked `docs/mockups/`): kit only, nothing faked. Names render as
text (VB law 9).

## 5. Seeding
`seeds.seed_control_rules` adds the four house rows (never overwrites) and, with `--actor-email`, copies them into
every live project that lacks them — **arriving switched on or off per CB-5 (§6)**. New projects created after the
deploy get them switched on, as Control-A's four. CLAUDE.md gets one deploy line **per slice** ("Control-B1 deploy",
"Control-B2 deploy"): run the seed with `--actor-email` straight after each deploy, before anyone creates a project
(until it runs, `create_project` refuses with 409 naming the seed — round 2 N4). A project created between the two
deploys is a running project for B2's rules (review R1-P2).

## 6. The on/off question (Control-A round 2 Q1 → CB-5)
Rules copied into engagements already running: switched **on** at once, or **off** until the client agrees the
threshold? Recommendation: **off, but still measured.** The panel shows the figure greyed with no verdict, under
"Not yet agreed with the client" (review R1-P1: a rule that is off and not measured goes quiet on exactly the projects
with the most data). No new column: "not yet agreed" is a rule that is off and never edited (`row_version = 1`); a rule
a person switched off shows "switched off" with who and when. Switching one on is a normal rule edit (reason
required, audited). **This changes Control-A's panel for every switched-off rule: it shows its figure, never a
verdict.**

## 7. Risk and tests — Grade 2
**Grade 2:** a wrong verdict (a silent GREEN) reaches a steering decision; correctable once noticed; no money, access
or data loss. Direct tests, no mutation harness:
1. Volatility: two-generation flag, three-generation escalate, a new all-ADDED area is not churn, a re-carved area with
   moved BRs is, MOVED is not churn, a requirement-line change counts, a BR moving area counts in both, **inserting an
   L1 area above a churning one keeps its run**, the run resets after a quiet generation; < 2 baselines and a damaged
   baseline anywhere in the chain are NOT MEASURED on both tab and panel.
2. Org impact: R/A counted, C/I not; a rejected solution is not a change; a unit on every change reads 100 %; the
   40 / 60 boundaries; one-unit org NOT MEASURED.
3. Stakeholder: a direct-parent stakeholder gives voice to a child, a grandparent does not; zero issues on the project
   → NOT MEASURED; the 10 / 25 boundaries; acceptance 73 on a chart of 11+ units.
4. Data migration: no-source, two-source, new-data and retiring cases; nothing mapped on as-is → NOT MEASURED;
   components off → NOT MEASURED.
5. Panel: a switched-off rule shows its figure and no verdict; "not yet agreed" vs "switched off" by row version.
6. Seed: house rows once; backfill into a live project arrives per CB-5; re-run is a no-op; a new project gets them on;
   `create_project` refuses until the seed has run.
7. Existing guards: `test_route_guards` (49/49b), `test_no_get_route_leaks_a_restricted_project` (covers the 4 GETs).
8. Browser (ui-verifier): each tab on a seeded project; each new panel row shows its verdict and links to its tab; a
   backfilled-off rule greyed under "Not yet agreed with the client".
**Left uncovered on purpose:** volatility's speed with many baselines (measured once, not tested); a half-done as-is
mapping can still under-count "no source" — mitigated by the visible count, closed only by the deferred "confirmed
new data" marker (§9).

## 8. Working assumptions (ASSUMPTION — confirm or correct)
- B1 Volatility counts every frozen baseline, approved or not — a draft that changed an area is still churn.
- B2 Every change weighs the same; no weighting by solution category.
- B3 An issue counts for voice whatever its status, including closed — the unit spoke.

## 9. Not in this slice
House-default editing and reset, `fr_unlinked`, the remaining registry analyses (Control-C); `benefit_gap`,
`risk_register` (Phase 2); a way to mark a data entity "confirmed new data" (needs a column — its own slice); verdict
history; the M-tiles; the two import-screen items on the VB-005 backlog (L3, L5).

## 10. Build plan (for Ren)
Four reports and four tabs in one pass is ~2,500 lines, too big to prove in one honest pass, so **two vertical
slices**, each shippable and testable on its own:
- **Control-B1 (~1 day): `requirement_volatility` + `data_migration_map`** — independent of each other and of the org
  chart. Report functions, routes, two tabs, two house rules, the panel's measured-while-off change, the seed's on/off
  backfill (CB-5). Tests 1, 4, 5, 6, 7; browser check for both.
- **Control-B2 (~1 day): `org_impact_heatmap` + `stakeholder_engagement`** — the second reads the first's shares, so
  they go together. Tests 2, 3, 7; browser check.
Each: build → test-runner fast run → sara → merge latest main → full suite on the merged commit (named) → ui-verifier
→ ask to merge. Estimate: about 2 days, up from the 1.5 the plan line gave.
Ports and databases: API 8102, web 5182, `vb_s2_db`, `vb_s2_test_db` (+ worker copies), created and dropped by this task.

## 11. Design review round 1 (design-auditor, 2026-10-30) — dispositions
9 findings (3 HIGH, 4 MEDIUM, 2 LOW), none structural — all fixed in this draft:
- **R1-P1 HIGH** rules backfilled off are not measured, so they go quiet — **fixed** (§6: measured, greyed, no verdict).
- **R1-D1 HIGH** volatility areas keyed by a code that renumbers — **fixed** (§2.1: the L1 node's id; test 1).
- **R1-S1 HIGH** voice inherited from the top of the chart hides every silent unit — **fixed** (§2.3: direct parent).
- **R1-S2 HIGH** data migration GREEN before the as-is mapping starts — **fixed** (§2.4: NOT MEASURED, and the
  "never seen on as-is" count shown).
- **R1-D2 MED** a re-carved area restarts at zero — **fixed** (§2.1). **R1-D3 MED** panel and tab can disagree on a
  damaged baseline — **fixed** (whole chain in both). **R1-D4 MED** a share of summed roles hides the busiest unit —
  **fixed** (§2.2: share of changes; thresholds 40 / 60 to match). **R1-D5 MED** small charts always flag / acceptance
  73 asserted — **fixed** (fewer than two units NOT MEASURED; test 3 on 11+ units).
- **R1-P2 LOW** one deploy line for two deploys — **fixed** (§5). **R1-S3 LOW** identity and privilege — nothing to fix.
- Its four questions are answered in the spec (two freezes running; added BRs count; no impact roll-up) or put to Ben
  (to-be RACI only, inside CB-2).
