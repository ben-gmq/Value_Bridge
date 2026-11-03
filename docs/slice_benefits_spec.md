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
- **Counts toward ranking and gap:** a live benefit whose status behaviour is LIVE (FORECAST counts — a forecast is
  the business case at this stage), through a live link of any % > 0, to a live solution whose status is not
  REJECTED (pinned, as `effort.summary` reads it). These are **counting** benefits, links and solutions.
- **A solution carries work** when it has at least one live FR, rated or not (R1-H1). It is **fully rated** when every
  one of its live FRs has `effort_days`.
- **Accountable role retired:** refused while a live benefit names it (409 naming `BEN-n`), by `lifecycle`'s generic
  live-child check — as `risk.owner_org_role_id`.
- **Rounding:** values and ratios are computed in `Decimal` and returned to 2 decimals (ROUND_HALF_UP); ranking ties
  break on solution number.

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
- **Live guard (R1-M1, apple M1):** computed `link_live` = `CASE WHEN is_active THEN TRUE END`; FKs
  `(benefit_id, project_id, link_live)` → `benefit (benefit_id, project_id, is_active)` and
  `(solution_id, project_id, link_live)` → `solution (solution_id, project_id, is_active)`, so the database refuses a
  live link under a retired end whatever the timing (`issue_br`'s pattern). Needs `uq_benefit_live_target` (in 0085)
  and `uq_solution_live_target (solution_id, project_id, is_active)` added to `solution` here — a constraint, not a
  column, so `baseline_solution` is unaffected.
- Shadow, guards and downgrade as 0085; the downgrade drops `benefit_solution` (and its shadow) **before**
  `uq_solution_live_target`. `models/solution.py` declares `uq_solution_live_target` so model and database agree.
- The ≤ 100 total across rows is the service's, under `SELECT … FOR UPDATE` on the benefit row (a CHECK sees one
  row). Every link write takes that lock first, then `lock_for_share` on the solution (SR-5), then reads the total
  of the *other* live links. Retiring a benefit locks it `FOR UPDATE` before counting its links.

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
writes one audit event. **`{sid}` that is missing or of another project is 404**, the same answer for both (DR1-S1,
R1-M6); only a retired solution of this project is 409.

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
- **Within spec 7:** `benefit` **and** `benefit_solution` rows are counted in a `benefit_summary` beside
  `issue_summary`, never in the scope summary — a re-forecast benefit or a changed % is not a scope change (BN-5).
  The priced diff is untouched.

## 8. Reports

### 8.1 `value_ranking`
For each unit key with at least one counting benefit (§4):
- For each counting solution linked to one: `value` = Σ link values in that unit; `effort` = Σ `effort_days` of its
  live FRs; `ratio` = value ÷ effort.
- `ranked`: **fully rated** solutions with effort > 0, by ratio desc, then solution number. **Bottom quartile** = the
  last ⌈n/4⌉ when n ≥ 4, else none marked.
- **Displacement candidate** = in the bottom quartile **and** has no counting value in any other unit (apple M2,
  R1-M5). A bottom-quartile row that also delivers elsewhere is marked "low here — also delivers in <units>" with
  those units' values, never tagged a candidate on one unit's evidence.
- `partly_rated`: solutions with value and at least one unrated FR — listed with "n of m FRs rated", never ranked,
  divided or put in the quartile (R1-H1).
- `no_work`: solutions with value and no live FR, or (defensively — rates are > 0 by `ck_effort_rate_days_positive`)
  a total of 0 days — listed, never ranked.
- Per benefit under 100 % on counting links: "x % of BEN-0003 not assigned"; per benefit with links to REJECTED
  solutions: "y % on rejected solutions" (R1-M4).
- Project lines: `untagged_effort_days` (live FR effort with no solution, §7 note 4); **reconciliation** (R1-L1,
  R2-M1) — computed **per solution, once** (never from the per-unit rankings, where a two-unit solution appears
  twice): Σ rated effort of every live solution in four buckets — *with counting value*, *no counting benefit*
  (including solutions whose only links are to ABANDONED benefits), *rejected*, and *untagged* — shown beside
  `effort.summary`'s `total_days + rejected days`, with the difference if any (zero on a correct build). EFFORT or FUNCTION_REQUIREMENT off → effort "not measured" and nothing is ranked.
- A solution with benefits in two units appears in both, with that unit's value only (A-B4).

### 8.2 `benefit_gap_report`
- `gap`: counting solutions that **carry work** (§4) and have no counting link — number, name, category, FR count,
  rated effort.
- `fragile`: counting benefits whose every counting linked solution is in the TECHNOLOGY category (§4.13) —
  informational, outside the rule.
- `measured` = gap count ÷ counting solutions that carry work × 100, two decimals.

### 8.3 `benefit_gap` house rule
`("benefit_gap", "PCT", "PCT_GT", 0, 20, "Challenge at the next gate")` appended to `control.HOUSE_RULES`; `COMING`
becomes empty. Not measured, with its reason, when BENEFIT, FUNCTION_REQUIREMENT or EFFORT is off (R1-M2 — the panel
and the ranking never disagree), or no counting solution carries work. Copies into live projects arrive switched off
(CB-5).

### 8.4 Data leaving the app
No outside service: no model API, connectors or email. Benefit figures are client-confidential; they reach only the
app's own screens and the baseline archive files under `VB_ARCHIVE_DIR`, with the same protection every frozen table has today (slice 16). Nothing new
leaves the instance (R1-M7).

## 9. Screens
- Left rail **Benefits** (hidden when BENEFIT is off), area `benefits`, strings in `en.benefits.json`.
- **Register:** number, name, type, unit, baseline → target, accountable role, status, realisation date, linked %;
  filters status and unit; "show retired". New-benefit dialog. Tabs/links to **Value ranking** and **Gap**.
- **Benefit page:** the form; the links table (solution, %, value it carries) with add / change % / remove;
  "x % not assigned"; retire / restore.
- **Value ranking (R2-M2):** one card per unit, each with: the ranked table (rank, solution, value, effort, ratio), a
  "Displacement candidate" Tag, or "Low here — also delivers in <units>" with those values; a **Partly rated** list
  ("n of m FRs rated", value); a **No work yet** list; per-benefit lines "x % not assigned" and "y % on rejected
  solutions". Below the cards: the untagged-effort line and the reconciliation line (four buckets, the effort
  summary's figure, the difference). EFFORT off: one "effort not measured" notice, values only.
- **Gap:** the gap table and the fragile list. The control panel row links here.
- **Solution page:** a read-only "Benefits" list (number, %, value).
- Edit controls through `useCanEdit`; component through `useComponents`. No mockup exists (A-B5).

## 10. Acceptance criteria
1. (crit. 59) No accountable org role → 422; the column is NOT NULL.
2. (crit. 130) Twenty concurrent creates → `BEN-0001`…`BEN-0020`, no 409.
3. (crit. 128) THB and hours → two rankings, no mixed ratio. 100 → 160 at 50 % → 30. 10 → 6 at 100 % → 4 (BN-1).
   Target = baseline → 422 and the CHECK refuses it.
4. (crit. 60) High-value / low-effort above low-value / high-effort; with four solutions the last is a displacement
   candidate — unless it has value in another unit, when it is marked "also delivers in …" instead.
5. A solution with one rated and twelve unrated FRs is `partly_rated`, not ranked; one with no FR is `no_work`;
   untagged FR effort is its own line; the reconciliation line matches `effort.summary`; EFFORT off → not measured.
6. Links totalling over 100 → 409 naming the current total; a solution of another project, or none → 404; a retired
   solution → 409. A live link under a retired solution is refused by the database even with the service check
   skipped.
7. ABANDONED benefit leaves ranking and gap; a REJECTED solution leaves both; retiring a solution with a live link →
   409 naming `BEN-n ↔ SOL-n`; retiring a benefit with live links → 409.
8. `benefit_gap`: 4 solutions carrying work, 1 with no benefit → 25.00 %, escalate; a solution with only unrated FRs
   and no benefit counts as a gap. BENEFIT, FR or EFFORT off → not measured. Panel "coming" list is empty.
9. Freeze with BENEFIT on → shadows filled; off → zero rows. A spec-6 baseline frozen before 0085 verifies with the
   same digest after it. UPDATE / DELETE on both shadows refused as app and owner.
10. Spec-7 vs spec-7 diff: a changed target counts in `benefit_summary`, not the scope summary. Spec-6 vs spec-7:
    benefits ADDED with `not_frozen_in: "a"`, outside every summary.
11. BENEFIT off → every write 409 COMPONENT_OFF, switching it off with a live benefit refused; non-member → 404
    on every new GET (criterion test covers it).
12. Screens: create, link, rank, gap, component off, VIEW user sees no edit controls; the ranking screen shows the
    partly-rated and no-work lists, the "also delivers in" mark, the not-assigned / on-rejected lines and the
    reconciliation line (difference 0).

## 11. Assumptions
- `ASSUMPTION A-B1` `measure_unit` is free text grouped by `lower(btrim())`; the form offers the project's units
  first (BN-6).
- `ASSUMPTION A-B2` Values numeric(18,2); no conversion, discounting or NPV (A-40 open part stands).
- `ASSUMPTION A-B3` The ranking reads today's live FR effort, not a baseline's.
- `ASSUMPTION A-B4` A solution in two units appears in both rankings with that unit's value.
- `ASSUMPTION A-B5` No mockup; screens reuse the Risks register's layout and the kit (D-51).
- `ASSUMPTION A-B6` The house rule arrives switched off in running projects (CB-5), on in new ones.
- `ASSUMPTION A-B7` Bottom quartile is ⌈n/4⌉ of the ranked list, unmarked below four solutions.
- `ASSUMPTION A-B8` One-off and recurring amounts are told apart only by the unit text ("THB" vs "THB/yr"); the
  form's hint says so. A period field is an open question for Ben (history §1).
- `ASSUMPTION A-B9` The displayed spelling of a unit key is that of the most recently updated benefit
  (`updated_at DESC, benefit_id DESC`).
- `ASSUMPTION A-B10` Benefit names need not be unique; the number identifies a benefit.

## 12. Decisions (Ben 2026-11-03, via Ren — "let's do it")
- **BN-1** Value is |target − baseline| × contribution % / 100; target = baseline is refused (amends A-40).
- **BN-2** A benefit's live contributions total at most 100 %; under 100 shows as not assigned.
- **BN-3** BENEFIT_STATUS gains behaviours LIVE / ABANDONED; abandoned benefits leave ranking and gap.
- **BN-4** `benefit_gap`: PCT_GT, flag > 0 %, escalate > 20 %; REJECTED solutions left out.
- **BN-5** Every benefit field and each contribution % is hashed; benefit changes counted apart from scope.
- **BN-6** Units free text, grouped case-insensitively, picker of the project's units.

## 13. Design review — round 1 (2026-11-03)
apple (schema): 0 HIGH, 3 MEDIUM, 5 LOW. design-auditor: 1 HIGH, 6 MEDIUM, 1 LOW. Nothing structural.

| Id | Finding | Disposition |
|---|---|---|
| R1-H1 | Unrated FRs counted as 0 days: a solution of unrated FRs escapes the gap; a partly-rated one is over-ranked | **Fixed** — "carries work" = any live FR; `partly_rated` never ranked (§4, §8) |
| R1-M1 / apple M1 | Link and solution retire race → live link under a retired solution | **Fixed** — `link_live` guard FKs both ends + `lock_for_share` (§5.2) |
| R1-M2 | Gap rule ignores EFFORT off | **Fixed** — not measured when BENEFIT, FR or EFFORT off (§8.3) |
| R1-M4 | Cap counts links to REJECTED solutions; value vanishes silently | **Fixed** — unassigned over counting links + "on rejected" line (§8.1) |
| R1-M5 / apple M2 | Displacement tag is per unit but reads as a verdict; full effort in each unit | **Fixed** — candidate only with no value elsewhere; "also delivers in …" (§8.1) |
| R1-M6 | Foreign solution id answered 422 | **Fixed** — 404 for missing or foreign (§6) |
| R1-M7 | No data-egress statement | **Fixed** — §8.4 |
| R1-L1 | No reconciliation with `effort.summary` | **Fixed** — reconciliation line (§8.1) |
| apple M3 | Design §5 / ERD say "PK both"; spec uses a surrogate | **Fixed in the build commit** — design §5 and ERD rewritten to the surrogate (needed for `source_id`) |
| apple L1 | Accountable role retire unspecified | **Fixed** — refused while a live benefit names it (§4) |
| apple L2 | Unit spellings; display tie-break; measure reuse | Tie-break A-B9; spellings are BN-6 as decided; a MEASURE entity deferred |
| apple L3 | Cap read after the lock, excluding the row's old % | **Fixed** — §5.2 |
| apple L4 | `benefit_summary` must count link rows too | **Fixed** — §7 |
| apple L5 | No unique live name; `solution.benefit_note` overlap; no `actual_value` | Name: A-B10 (accepted). Overlap and actuals → history §1 open for Ben, not this slice |
| Auditor Q1–Q3 | One-off vs recurring; does FORECAST / 0.01 % count; rounding | A-B8 (open in history §1); FORECAST and any % > 0 count (§4); rounding §4 |

## 14. Design review — round 2 (2026-11-03, final — the cap is two rounds)
design-auditor: 0 CRITICAL, 0 HIGH, 2 MEDIUM, 2 LOW; nothing structural. Closed: R1-H1, R1-M1 (guard FK design
checked against soft delete, restore and lock order), R1-M2, M4, M5, M6, M7.

| Id | Finding | Disposition |
|---|---|---|
| R2-M1 | Reconciliation shows a built-in difference (rejected days outside `total_days`; two-unit solutions counted twice) | **Fixed** — per-solution buckets vs `total_days + rejected` (§8.1) |
| R2-M2 | §9 screens missed the new lists and lines | **Fixed** — §9 and criterion 12 name each |
| R2-L1 | A token link in another unit exempts a solution from displacement | **Accepted, visible** — the other unit's value is shown beside it; the threshold goes to history §1 as a question for Ben, settled against the running screen |
| R2-L2 | Zero-effort fully rated solution; `models/solution.py` not listed | **Fixed** — rates are > 0 by CHECK, 0 days routed to `no_work` anyway; model listed (§5.2) |

What is left open is tracked against the running code, not a third draft (design-review cap).
