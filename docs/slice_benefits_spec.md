# Slice Benefits — the benefit register, value for effort, the `benefit_gap` rule (spec, 2026-11-03)

**Status:** build spec, Ben's answers BN-1…BN-6 (2026-11-03, via Ren: plan decisions 1–3 all (a), "let's do it").
Design review rounds in §13–14. **Plan:** `docs/plans/benefits_plan_2026-11-03.md`. **Design:** §4.9 (functions),
§5 BENEFIT / BENEFIT_SOLUTION, §5.10 rows 30–31, §6.1 freeze set, §7 `value_ranking`, §7.13 `benefit_gap`, criteria
59, 60, 128, 130, A-40, API table "Phase 2 — benefits". **Migrations:** 0085, 0086 (this task holds the claim).
**Hash spec:** 6 → 7.

## 1. Purpose
A consultant records what the engagement is *for* — each quantified benefit, who is accountable for it, and which
solutions deliver how much of it (D-14). The value ranking then names, per unit, the solutions that deliver least
per man-day: the candidates to displace when something new is asked for ("trade, don't add"). The control panel flags
the engagement while any solution carrying effort has no benefit behind it, and escalates above 20 %.

## 1a. Interface
- **Input:** benefits typed on the Benefits screen, one at a time; solution links (solution + contribution %) on the
  benefit page. FR effort is read, never written.
- **Output:** the register; the benefit page with its links; the value ranking (one table per unit); the gap view;
  one control-panel row; the benefits and their links frozen into every baseline taken while BENEFIT is on.
- **Validation:** codes from the project's lists; the accountable org role and every linked solution are live and in
  the same project; target ≠ baseline; contribution 0 < % ≤ 100 and a benefit's live links total ≤ 100; numbers are
  minted, never taken from a request; BENEFIT off → 409 COMPONENT_OFF.
- **Archive:** each write is an audit event (`BENEFIT_CREATED`, `BENEFIT_UPDATED`, `BENEFIT_SOLUTION_LINKED`,
  `BENEFIT_SOLUTION_UNLINKED`, retire / restore) carrying numbers, codes and figures — never name or text (R7). Frozen
  copies live in `baseline_benefit` / `baseline_benefit_solution` for the project's life and in its archive files.
- **Maintenance loop:** the panel row and the ranking are reviewed at each gate / steering meeting; the rule's numbers
  are the client's to agree (CB-5), revisited after the first engagement.

## 2. Grain
- **BENEFIT** — one row per quantified benefit in one project. `BEN-0001` minted at save
  (`numbering.next_number('BEN')`; the series is already seeded by `create_project`).
- **BENEFIT_SOLUTION** — one row per (benefit × solution), ever: unlinking retires the row, linking again restores
  it (and its frozen `source_id`), as `solution_phase` does (S1-7).

## 3. Business requirement grid

| Entity | Function | Logic → output |
|---|---|---|
| BENEFIT | `create_benefit` (C) | Name, type, measure name, measure unit, baseline value, target value, accountable org role — all required (criterion 59); description and realisation date optional. Target ≠ baseline (BN-1). Status starts FORECAST |
| BENEFIT | `update_benefit` (U) | Any field above and the status. Number never editable. Stale `row_version` → 409 |
| BENEFIT | retire / restore (U) | Soft delete through `lifecycle` (law 1). Retire refused while the benefit has live links (409 naming them). Restore needs BENEFIT on |
| BENEFIT_SOLUTION | `link_benefit_solution` (C/U) | Set solution S's share of benefit B to p %, 0 < p ≤ 100. Creates, restores or re-weights the one (B, S) row. The benefit's live links may total at most 100 (BN-2), checked under a lock on the benefit |
| BENEFIT_SOLUTION | unlink (U) | Retires the row; never a DELETE |
| BENEFIT, BENEFIT_SOLUTION, FR | `value_ranking` (R) | §8.1. One ranking per unit; bottom quartile named |
| SOLUTION, BENEFIT_SOLUTION | `benefit_gap_report` (R) | §8.2. Solutions with effort and no live benefit; fragile benefits |
| CONTROL_RULE | `benefit_gap` headline | § 8.3. % of effort-carrying solutions with no benefit; flag > 0, escalate > 20 (BN-4) |
| BASELINE_* | freeze | Both tables frozen while BENEFIT is on (§7) |

## 4. Logical design
- BENEFIT >— 1 PROJECT; BENEFIT >— 1 ORG_ROLE (accountable, mandatory); BENEFIT >—< SOLUTION through
  BENEFIT_SOLUTION, which carries `contribution_pct`. Every reference is same-project (composite FKs).
- **Codes:**
  - `BENEFIT_TYPE` (COST_REDUCTION, REVENUE, PRODUCTIVITY, RISK_REDUCTION, COMPLIANCE, CUSTOMER): a project may
    rename, add or hide, like every type list; re-pointed by `code_lists`.
  - `BENEFIT_STATUS` (FORECAST, COMMITTED, IN_REALISATION, REALISED, ABANDONED): **company-only**, like every status
    list (I-1, W-4), and carries a behaviour (BN-3): ABANDONED → `ABANDONED`, the other four → `LIVE`. All five codes
    pinned (`code_lists.PINNED`), their behaviour fixed. FORECAST and ABANDONED are looked up by value.
- **Value of one link** = |target − baseline| × contribution_pct / 100, in the benefit's unit (A-40 as amended by
  BN-1). **Unit key** = `lower(btrim(measure_unit))` (BN-6); the displayed unit is the most recently edited spelling.
- **Counts toward ranking and gap:** a live benefit whose status behaviour is LIVE, through a live link, to a live
  solution whose status is not REJECTED (pinned, as `effort.summary` reads it).

## 5. Physical design

### 5.1 Migration 0085 — `benefit`, `baseline_benefit`, BENEFIT_STATUS behaviours
1. Refuses (naming `project:code`) while any project-tier BENEFIT_STATUS row or project hide of one exists, or any
   BENEFIT_STATUS code this revision cannot map — 0083's way; nothing is guessed.
2. `code_master`: `ck_code_behaviour_present` widened to `BENEFIT_STATUS`; `ck_code_benefit_status_behaviour`
   (`LIVE` / `ABANDONED`); library rows backfilled by code, idempotent. `seed_code_master` carries the same.
3. `benefit`: `benefit_id` PK identity · `project_id` FK NOT NULL · `benefit_number` varchar(20) NOT NULL ·
   `benefit_name` varchar(200) NOT NULL non-blank · `description` text · `benefit_type_code_id` NOT NULL +
   computed `benefit_type_category` → composite FK (code_id, category) · `measure_name` varchar(200) NOT NULL
   non-blank · `measure_unit` varchar(40) NOT NULL non-blank · `baseline_value`, `target_value` numeric(18,2) NOT NULL ·
   `realisation_date` date · `accountable_org_role_id` NOT NULL → (org_role_id, project_id) · `status_code_id` NOT NULL
   + computed `status_category` + `status_behaviour` varchar(20) → composite FK (code_id, category, behaviour_code) ·
   audit columns.
   - UK `(project_id, benefit_number)`; UK `(benefit_id, project_id)` (target of the link's FKs).
   - CHECK `target_value <> baseline_value` (BN-1); CHECK `status_behaviour IN ('LIVE','ABANDONED')`.
   - Indexes on type, status, accountable role; `ix_benefit_unit (project_id, lower(btrim(measure_unit))) WHERE
     is_active`.
4. `baseline_benefit`: literal DDL as `baseline_shadow.shadow_table()` generates it (law 2) — copied columns, code
   pairs `benefit_type_code/_label`, `status_code/_label`; `immutable_guards_v2`.
5. Downgrade refuses while a baseline at hash spec ≥ 7 exists or either table holds a row; then drops, restores the
   CHECK and clears the BENEFIT_STATUS behaviours.

### 5.2 Migration 0086 — `benefit_solution`, `baseline_benefit_solution`
- `benefit_solution_id` PK identity · `project_id` FK NOT NULL · `benefit_id` → (benefit_id, project_id) ·
  `solution_id` → (solution_id, project_id) · `contribution_pct` numeric(5,2) NOT NULL CHECK `> 0 AND <= 100` · audit
  columns · UNIQUE `(benefit_id, solution_id)` in full · index on `solution_id`.
- Shadow, guards and downgrade as 0085.
- The ≤ 100 total across rows is the service's, under `SELECT … FOR UPDATE` on the benefit row (a CHECK sees one
  row). Every link write takes that lock first.

Both: vb_app SELECT / INSERT / UPDATE from 0001's default privileges, no DELETE (law 1). Both carry `project_id`, so
`purge_run` classifies them unchanged; neither points at a step or BR, so `step_retire` is unchanged. Both reach
main in one merge (S11-6). `models/__init__`, `models/baseline.SHADOWED`, `lifecycle.RESTORABLE` (Benefit only) and
`LABELS` (both; numbers only, R7), `components.COMPONENT_ROWS["BENEFIT"]`, `code_lists` catalog.

## 6. Routes (all under `/api/v1`)

| Method · path | Guard | Body → out |
|---|---|---|
| `GET /projects/{pid}/benefits` | project_ctx VIEW | `include_retired`, `status`, `unit` → list with link total % and linked solution numbers |
| `POST /projects/{pid}/benefits` | project_ctx EDIT, BENEFIT | fields → benefit (201) |
| `GET /benefits/{id}` | object_guard VIEW | → benefit + live links |
| `PATCH /benefits/{id}` | object_guard EDIT, BENEFIT | `row_version` + fields → benefit |
| `DELETE /benefits/{id}?row_version=` | object_guard EDIT, BENEFIT | retire (204) |
| `PATCH /benefits/{id}/restore` | object_guard EDIT, BENEFIT | → benefit |
| `PUT /benefits/{id}/solutions/{sid}` | object_guard EDIT, BENEFIT | `contribution_pct` → link |
| `DELETE /benefits/{id}/solutions/{sid}` | object_guard EDIT, BENEFIT | unlink (204) |
| `GET /solutions/{id}/benefits` | object_guard(Solution) VIEW | the solution's live links (solution page) |
| `GET /projects/{pid}/value-ranking` | project_ctx VIEW | §8.1 |
| `GET /projects/{pid}/benefit-gap` | project_ctx VIEW | §8.2 |

Link routes need SOLUTION on as well (BENEFIT requires it, D-37, so it always is). `PUT` is idempotent: same % twice
writes one audit event.

## 7. Freeze and the hash spec (BN-5)
- `CURRENT_HASH_SPEC` 6 → 7. Registered `since=7`, appended after `solution_dependency` (spec-1…6 order untouched):
  - `benefit` (area `BENEFIT`): hashes `benefit_number, benefit_name, description, benefit_type_code, measure_name,
    measure_unit, baseline_value, target_value, realisation_date, accountable_org_role_id, status_code`; label
    `benefit_number, benefit_name`; ref `accountable_org_role_id → org_role`.
  - `benefit_solution` (area `BENEFIT`): hashes `benefit_id, solution_id, contribution_pct`; refs to `benefit`,
    `solution`.
  - Gates (`components.FREEZE_GATES`): `benefit` ⇐ BENEFIT; `benefit_solution` ⇐ BENEFIT ∧ SOLUTION.
- **No existing entity's hashed list changes.** Baselines at specs 1–6 recompute byte-identical (entities unknown at
  their spec are skipped); their archive files are untouched.
- **Old vs new comparison:** benefit rows list ADDED with `not_frozen_in`, outside every summary (slice11 §5.1,
  built).
- **Within spec 7:** benefit rows are counted in a `benefit_summary` beside `issue_summary`, never in the scope
  summary — a re-forecast benefit is not a scope change (BN-5). The priced diff is untouched.

## 8. Reports

### 8.1 `value_ranking`
For each unit key with at least one counting benefit (§4):
- For each counting solution linked to one: `value` = Σ link values in that unit; `effort` = Σ `effort_days` of live
  FRs tagged to the solution (null `effort_days` counts 0 and the row says "n unrated FRs"); `ratio` = value ÷ effort.
- `ranked`: solutions with effort > 0, by ratio desc, then solution number. **Bottom quartile** = the last
  ⌈n/4⌉ when n ≥ 4, else none marked — "displacement candidate".
- `no_effort`: solutions with value but effort 0 — listed, never ranked or divided.
- Per unit: `unassigned_pct` per benefit under 100 % ("x % of BEN-0003 not assigned to a solution").
- Project lines: `untagged_effort_days` (live FR effort with no solution, §7 note 4); EFFORT off → `effort` is
  "not measured" and nothing is ranked.
- A solution with benefits in two units appears in both, with that unit's value only (A-B4).

### 8.2 `benefit_gap_report`
- `gap`: counting solutions (live, not REJECTED) with effort > 0 and no counting link — number, name, category,
  effort.
- `fragile`: counting benefits whose every counting linked solution is in the TECHNOLOGY category (§4.13) —
  informational, outside the rule.
- `measured` = gap count ÷ effort-carrying counting solutions × 100, two decimals.

### 8.3 `benefit_gap` house rule
`("benefit_gap", "PCT", "PCT_GT", 0, 20, "Challenge at the next gate")` appended to `control.HOUSE_RULES`; `COMING`
becomes empty. Not measured (`reason`) when BENEFIT is off, or no counting solution has effort. Copies into live
projects arrive switched off (CB-5).

## 9. Screens
- Left rail **Benefits** (hidden when BENEFIT is off), area `benefits`, strings in `en.benefits.json`.
- **Register:** number, name, type, unit, baseline → target, accountable role, status, realisation date, linked %;
  filters status and unit; "show retired". New-benefit dialog. Tabs/links to **Value ranking** and **Gap**.
- **Benefit page:** the form; the links table (solution, %, value it carries) with add / change % / remove;
  "x % not assigned"; retire / restore.
- **Value ranking:** one card per unit; table rank, solution, value, effort, ratio, a Tag on the bottom quartile; a
  "no effort rated" list; the untagged-effort line.
- **Gap:** the gap table and the fragile list. The control panel row links here.
- **Solution page:** a read-only "Benefits" list (number, %, value).
- Edit controls through `useCanEdit`; component through `useComponents`. No mockup exists (A-B5).

## 10. Acceptance criteria
1. (crit. 59) No accountable org role → 422; the column is NOT NULL.
2. (crit. 130) Twenty concurrent creates → `BEN-0001`…`BEN-0020`, no 409.
3. (crit. 128) THB and hours → two rankings, no mixed ratio. 100 → 160 at 50 % → 30. 10 → 6 at 100 % → 4 (BN-1).
   Target = baseline → 422 and the CHECK refuses it.
4. (crit. 60) High-value / low-effort above low-value / high-effort; with four solutions the last is a displacement
   candidate.
5. Effort 0 → `no_effort`, not ranked; untagged FR effort is its own line; EFFORT off → not measured.
6. Links totalling over 100 → 409 naming the current total; a solution of another project → 422; a retired solution
   → 422.
7. ABANDONED benefit leaves ranking and gap; a REJECTED solution leaves both; retiring a solution with a live link →
   409 naming `BEN-n ↔ SOL-n`; retiring a benefit with live links → 409.
8. `benefit_gap`: 4 effort-carrying solutions, 1 with no benefit → 25.00 %, escalate. BENEFIT off → not measured.
   Panel "coming" list is empty.
9. Freeze with BENEFIT on → shadows filled; off → zero rows. A spec-6 baseline frozen before 0085 verifies with the
   same digest after it. UPDATE / DELETE on both shadows refused as app and owner.
10. Spec-7 vs spec-7 diff: a changed target counts in `benefit_summary`, not the scope summary. Spec-6 vs spec-7:
    benefits ADDED with `not_frozen_in: "a"`, outside every summary.
11. BENEFIT off → every write 409 COMPONENT_OFF, switching it off with a live benefit refused; non-member → 404
    on every new GET (criterion test covers it).
12. Screens: create, link, rank, gap, component off, VIEW user sees no edit controls.

## 11. Assumptions
- `ASSUMPTION A-B1` `measure_unit` is free text grouped by `lower(btrim())`; the form offers the project's units
  first (BN-6).
- `ASSUMPTION A-B2` Values numeric(18,2); no conversion, discounting or NPV (A-40 open part stands).
- `ASSUMPTION A-B3` The ranking reads today's live FR effort, not a baseline's.
- `ASSUMPTION A-B4` A solution in two units appears in both rankings with that unit's value.
- `ASSUMPTION A-B5` No mockup; screens reuse the Risks register's layout and the kit (D-51).
- `ASSUMPTION A-B6` The house rule arrives switched off in running projects (CB-5), on in new ones.
- `ASSUMPTION A-B7` Bottom quartile is ⌈n/4⌉ of the ranked list, unmarked below four solutions.

## 12. Decisions (Ben 2026-11-03, via Ren — "let's do it")
- **BN-1** Value is |target − baseline| × contribution % / 100; target = baseline is refused (amends A-40).
- **BN-2** A benefit's live contributions total at most 100 %; under 100 shows as not assigned.
- **BN-3** BENEFIT_STATUS gains behaviours LIVE / ABANDONED; abandoned benefits leave ranking and gap.
- **BN-4** `benefit_gap`: PCT_GT, flag > 0 %, escalate > 20 %; REJECTED solutions left out.
- **BN-5** Every benefit field and each contribution % is hashed; benefit changes counted apart from scope.
- **BN-6** Units free text, grouped case-insensitively, picker of the project's units.

## 13. Design review — round 1
*(filled in after apple and design-auditor)*

## 14. Design review — round 2
*(filled in after the re-check)*
