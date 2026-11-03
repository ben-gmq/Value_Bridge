# Plan — Benefits (D-14), Phase 2 — 2026-11-03 (awaiting approval)

**For:** Ren / Ben · **By:** Lilly · **Status:** plan only. Nothing built, migrated or seeded.
**Counted from:** `origin/main` at `6e99f81` (Decisions merged; 1,294 tests passed on that commit).
**Sources:** design §4.9, §5 BENEFIT / BENEFIT_SOLUTION, §5.10 rows 30–31, §6.1 freeze set, §7 `value_ranking`,
§7.13 `benefit_gap`, criteria 59, 60, 128, 130, A-40; `services/freeze_set.py`, `services/control.py`,
`services/components.py`, `services/lifecycle.py`, migrations 0065–0067 (waves: the last tables that joined the
freeze set) and 0083 (risks: status behaviours).

**What Ben chose:** a benefit register (`BEN-` numbers), linked to solutions with a contribution %, a
value-for-effort ranking, and the "no benefit yet" check that completes the `benefit_gap` control rule.

---

## 1. Requirement grid (entity × function × logic)

| Function | Entity | Use | Logic → output |
|---|---|---|---|
| `create_benefit` | BENEFIT | C | Number `BEN-0001` minted at save from the project's BEN series (already seeded). Name, type, measure, unit, baseline value, target value, realisation date, accountable org role (required, criterion 59), status (FORECAST on create) |
| `update_benefit` | BENEFIT | U | Same fields; stale `row_version` → 409; number never editable |
| retire / restore | BENEFIT | U | Soft delete (law 1) through `lifecycle.RESTORABLE`. Retiring a benefit with live solution links is refused (409, the links named), as elsewhere |
| `link_benefit_solution` | BENEFIT_SOLUTION | C/U | Set one solution's contribution % to one benefit. Re-linking a retired link restores the same row. Total over a benefit's live links may not pass 100 (Q2) |
| unlink | BENEFIT_SOLUTION | U | Soft delete (`is_active=false`), never a DELETE |
| `value_ranking` | BENEFIT, BENEFIT_SOLUTION, FR | R | One ranking per measure unit. Per solution: value = Σ \|target − baseline\| × contribution % / 100 (Q1); effort = Σ live FR `effort_days` tagged to it; ratio = value ÷ effort. Bottom quartile marked "displacement candidate". Solutions with no rated effort listed apart, never ranked |
| `benefit_gap_report` | SOLUTION, BENEFIT_SOLUTION | R | Solutions carrying effort and no live benefit link → the gap list. Benefits whose every linked solution is TECHNOLOGY → "fragile benefit case" (informational) |
| `benefit_gap` rule | CONTROL_RULE | R | % of effort-carrying solutions with no benefit; flag > 0 %, escalate > 20 % (§7.13, Q4) |
| freeze | BASELINE_BENEFIT, BASELINE_BENEFIT_SOLUTION | C | Both tables frozen with each baseline while BENEFIT is on; zero rows when off |

**Out:** benefit realisation tracking over time (actuals), NPV / discounting / currency conversion (A-40 open),
Excel import / export of benefits, the change-request benefit delta (comes with Change requests), program roll-up.

## 2. Logical design

- **Grain.** BENEFIT: one row per quantified benefit in one project. BENEFIT_SOLUTION: one row per
  (benefit × solution), carrying the contribution % — the fact that is argued about at realisation.
- **Relationships.** PROJECT 1–n BENEFIT; ORG_ROLE 1–n BENEFIT (accountable, mandatory); BENEFIT n–m SOLUTION
  through BENEFIT_SOLUTION. Both ends and the role are in the same project (composite FKs).
- **Code lists.** `BENEFIT_TYPE` (project may override, like other types) and `BENEFIT_STATUS` (company-only, like
  every status list since I-1 / W-4), both already seeded. BENEFIT_STATUS gains a behaviour so code can tell an
  abandoned benefit without naming the code (law 5): FORECAST / COMMITTED / IN_REALISATION / REALISED → `LIVE`,
  ABANDONED → `ABANDONED` (Q3).
- **Delivery switch.** Component BENEFIT (needs SOLUTION, already declared). Writes refuse with 409 COMPONENT_OFF
  when it is off; a project with live benefits cannot switch it off (`COMPONENT_ROWS`).

## 3. Physical design (apple checks it before code)

**Migration 0085 — `benefit` + `baseline_benefit`, and the BENEFIT_STATUS behaviours.**
- `benefit_id` identity PK · `project_id` NOT NULL · `benefit_number` varchar(20) NOT NULL, UK `(project_id,
  benefit_number)` · `benefit_name` varchar(200) not blank · `description` text · `benefit_type_code_id` NOT NULL with
  generated category + composite FK · `measure_name` varchar(200) not blank · `measure_unit` varchar(40) not blank ·
  `baseline_value`, `target_value` numeric(18,2) NOT NULL, CHECK `target_value <> baseline_value` (Q1) ·
  `realisation_date` date · `accountable_org_role_id` NOT NULL, composite FK `(org_role_id, project_id)` ·
  `status_code_id` NOT NULL with category and behaviour carried by composite FK (as `risk`, 0083) · audit columns,
  `row_version` · UK `(benefit_id, project_id)` as the target of the link's composite FK.
- `code_master`: `ck_code_behaviour_present` widened to BENEFIT_STATUS; library rows backfilled by code; refuses,
  naming `project:code`, any BENEFIT_STATUS row it cannot map, or any project-tier BENEFIT_STATUS row.
- Shadow `baseline_benefit`, generated by `services/baseline_shadow` (law 2) with code pairs for type and status;
  `immutable_guards_v2`.
- Downgrade refuses while a spec-7 baseline exists or either table holds a row.

**Migration 0086 — `benefit_solution` + `baseline_benefit_solution`.**
- `benefit_solution_id` identity PK (surrogate, as `solution_phase`) · `project_id` · `benefit_id`, `solution_id`
  composite FKs with `project_id` · `contribution_pct` numeric(5,2) CHECK `> 0 AND <= 100` · audit columns · UNIQUE
  `(benefit_id, solution_id)` in full, so re-linking restores the row and its frozen `source_id`.
- The 100 % cap across rows is kept by the service under a row lock on the benefit (a CHECK sees one row only).
- Shadow and guards as above; same downgrade refusal.

Two migrations because law 10 is one table per migration (waves took three). Both reach main in one merge (S11-6).
vb_app gets SELECT / INSERT / UPDATE from 0001's default privileges, no DELETE. Both tables carry `project_id`, so
`purge_run` needs no change; neither points at a step or a BR, so `step_retire` needs no change.

## 4. The hash-spec change, exactly

- **What changes:** `freeze_set.CURRENT_HASH_SPEC` goes **6 → 7**. Two entities join the freeze set with `since=7`:
  - `benefit` hashes `benefit_number, benefit_name, description, benefit_type_code, measure_name, measure_unit,
    baseline_value, target_value, realisation_date, accountable_org_role_id, status_code` (Q5).
  - `benefit_solution` hashes `benefit_id, solution_id, contribution_pct`.
  - Gates: `benefit` ⇐ BENEFIT; `benefit_solution` ⇐ BENEFIT ∧ SOLUTION. **No existing entity's hashed list
    changes**, and the spec-1 set is untouched (its module assertion stays green).
- **Baselines already frozen (specs 1–6): nothing changes.** The digest, the re-hash check and every read skip an
  entity unknown at a baseline's own spec, so each one recomputes byte-identical to what it stored and still
  verifies. Their archive files are not rewritten.
- **Comparing an old baseline with a new one (or with live):** benefit rows list as added, marked "not frozen in
  v1.x", and are kept out of the scope totals — new structure, not new scope (the slice-11 rule, already built).
- **Freezes after the merge** are spec 7 and carry the benefits whenever BENEFIT is on; their archive files list the
  two new tables.
- **Within spec 7**, benefit changes are counted apart from scope changes, as issues are (Q5).
- **Lock:** until this merges, no other slice may add a migration or touch the hash spec.

## 5. Acceptance criteria

1. (crit. 59) A benefit without an accountable org role is refused (422), and the database refuses it too.
2. Twenty benefits created at once get `BEN-0001`…`BEN-0020`, no gaps, no 409 (crit. 130).
3. (crit. 128) One benefit in THB and one in hours → two rankings, no ratio mixes units. Baseline 100, target 160,
   50 % → value 30. Baseline 10, target 6 (a reduction), 100 % → value 4 (Q1).
4. (crit. 60) A high-value / low-effort solution ranks above a low-value / high-effort one, and the second is named a
   displacement candidate.
5. A solution with no rated effort appears under "no effort rated", never ranked or divided by zero; FR effort with no
   solution tag shows as its own line (§7 note 4).
6. Links over 100 % in total for one benefit → 409 naming the current total. A link across projects is refused.
7. An ABANDONED benefit leaves the ranking and the gap check; retiring a solution with a live link → 409 naming it.
8. `benefit_gap`: 4 effort-carrying solutions, 1 with no benefit → 25 %, escalated. BENEFIT off, or no solution with
   effort → "not measured", never 0. REJECTED solutions are left out. The panel's "coming" line disappears.
9. Freeze with BENEFIT on → both shadows filled; off → zero rows. A spec-6 baseline's digest is unchanged after
   upgrade. A shadow row cannot be updated or deleted as the app or the owner.
10. Writes with BENEFIT off → 409 COMPONENT_OFF; a non-member of a restricted project gets 404 on every new route.
11. Screens: register, benefit page with links, ranking, gap view; Benefits hidden when the component is off; edit
    controls hidden at VIEW.

## 6. Assumptions (the spec carries these as ASSUMPTION tags)

- **A-B1** `measure_unit` stays free text (the design's varchar). Units are grouped trimmed and case-insensitive, and
  the form offers the project's existing units first, so "THB" and "thb" rank together (Q6).
- **A-B2** Values are numeric(18,2): enough for baht and hours; no currency conversion (A-40 stays open).
- **A-B3** Effort for the ranking is today's live FR effort, not a baseline's.
- **A-B4** A solution in two units appears in both rankings with that unit's value only (design §7).
- **A-B5** No mockup exists for these screens; they reuse the Risks register's layout and the kit (D-51). Nothing
  without data behind it is drawn.
- **A-B6** House rule copied into running projects arrives switched off (CB-5); new projects get it on.

## 7. Questions for Ben (recommendation first)

1. **Does a reduction count as value?** The design says target − baseline, so "close books in 6 days, not 10" scores
   −4 and sinks to the bottom. Recommend: value is the size of the change, |target − baseline|, and a benefit whose
   target equals its baseline is refused. This rewrites A-40.
2. **May one benefit's solution shares add up to more than 100 %?** Recommend no: refuse over 100, and show
   "x % not assigned" while under 100. Otherwise one benefit is counted twice.
3. **Do abandoned benefits drop out of the ranking and the gap check?** Recommend yes, through a status behaviour
   (the company-wide status list gains LIVE / ABANDONED, as risk statuses did).
4. **The `benefit_gap` rule:** percent of effort-carrying solutions with no live benefit; flag above 0 %, escalate
   above 20 %; rejected solutions left out. Recommend yes, as §7.13 states.
5. **What a baseline freezes:** recommend all benefit fields including status and each contribution %, with benefit
   changes counted apart from scope changes in a comparison (as issues are).
6. **Units:** free text grouped case-insensitively with a picker of the project's units, or a fixed code list?
   Recommend free text with the picker (no design change).

## 8. Risk grade and test plan

- **Riskiest concern — Grade 1: the baseline fingerprint.** A wrong hash-spec change would make every signed
  baseline fail its check, or let a frozen benefit be altered unseen. Proof: a spec-6 baseline frozen before the
  upgrade recomputes the same digest after it; shadow parity (the existing test reads the database); UPDATE and
  DELETE on both shadows refused as app and owner; old-vs-new comparison keeps benefits out of the scope totals. No
  mutation harness (that is its own task).
- **Grade 2 — ranking, cap and gap rule** (figures a steering committee decides from). Direct tests for criteria
  1–8 above. **Left uncovered on purpose:** a true concurrent race on the 100 % cap (the row lock is tested
  sequentially), and values near numeric(18,2) overflow.
- **Grade 3 — screens.** One path each through ui-verifier: create, link, rank, gap view, component off.
- Fast run between commits covers the baseline, access and control areas (touches the schema and a baseline).
  Full suite (`-m "" -n 6`) on the merged commit before asking for the push, commit named.

## 9. Pieces and days

| Piece | What a person can open and try | Days |
|---|---|---:|
| 0 — Spec + reviews | `docs/slice_benefits_spec.md` from this plan and Ben's answers; apple on §3; design-auditor two rounds | 0.4 |
| A — Register | 0085, model, service, routes, BEN numbers, Benefits in the left rail, register + benefit page, `en.benefits.json` | 0.8 |
| B — Links + freeze | 0086, link / unlink with the cap, links on the benefit page and the solution page, hash spec 7, diff counted apart | 0.6 |
| C — Ranking + gap | `value_ranking`, `benefit_gap` report and house rule, ranking and gap screens, panel row | 0.5 |
| D — Prove + docs | sara (migrations, baselines), full suite, ui-verifier, design + history (BN-n decisions), CLAUDE deploy note | 0.4 |
| **Total** | | **2.7** |

0.2 day over the earlier estimate: counting benefit changes apart in a baseline comparison (Q5) and the status
behaviour (Q3).

**Deploy note (goes in CLAUDE.md):** after `upgrade head` (0085, 0086), run `seeds.seed_code_master` then
`seeds.seed_control_rules --actor-email <admin>` (adds `benefit_gap`; until it runs `create_project` is 409).

## 10. Where it runs

Slot 2. Own databases: `vb_s2ben_db` (dev), `vb_s2ben_test_db` and workers `vb_s2ben_test_db_gw0…5`,
`vb_s2ben_uat_db` for the browser check. API on **8102**, web on **5182** (`VB_API_PORT=8102 VB_WEB_PORT=5182`).
The worktree's `backend/.env` is its own copy; nothing shared is changed. All dropped and stopped by PID at the end.
