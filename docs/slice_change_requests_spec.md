# Slice Change requests (D-16) — build spec

**Status:** reviewed, two rounds (round 1 design-auditor + apple, round 2 design-auditor; findings and dispositions in
`docs/plans/change_requests_plan_2026-11-03.md` §6), 2026-11-03. Nothing built. **Counted from**
`origin/main` at `c3fb909` (Benefits merged; 1,326 tests passed on that commit). **Sources:** design §4.11, §5
CHANGE_REQUEST / CR_IMPACT / DECISION, §6.1 rows 33–34, §7.13 change control, criteria 63–66, 190, 192; history D-16,
Q3, Q8, Q9, SC-2, SC-7, DR8-P1, DC-1…DC-7, BN-1; `services/baseline.py` (`agreed_id`, `freeze`, `preview`),
`services/decision.py`, `services/benefit.py` (`value_ranking`), `services/components.py`, `services/code_lists.py`,
`services/lifecycle.py`.

**What Ben chose:** raise a change against an agreed baseline (`CR-` numbers), an automatic impact trace, pricing,
and a decision step; an increase needs a cut or a budget record; the decision is written into the decision log.

**Questions for Ben (history §1, CR-1…CR-3), built as recommended unless he says otherwise:** §9.

---

## 1. Requirement grid (entity × function × logic)

| Function | Entity | Use | Logic → output |
|---|---|---|---|
| `raise_change_request` | CHANGE_REQUEST | C | `CR-0001` minted at save from the project's CR series (already seeded). Title, rationale, origin (`CR_ORIGIN`) required. Target = a baseline **read scoped to the URL's project** (another project's → 404) `FOR SHARE`: FROZEN, APPROVED, or the SUPERSEDED one carrying the agreed approval (`agreed_id`, SC-2); else 422 (criteria 63, 190). A target frozen with EFFORT off → 422 ("this baseline carries no prices"). Status DRAFT; raiser = signed-in user (= `created_by`) |
| `update_change_request` | CHANGE_REQUEST | U | Title, rationale, origin; target fixed once raised (point-in-time, §5). **Open only** (DRAFT / ANALYSED / PRICED / DEFERRED); stale `row_version` → 409 |
| `set_cr_seeds` | CR_IMPACT | C/U | **Open only, else 409.** The whole seed list in one PUT: each a live BR or FR read scoped to the project (404 otherwise) with an impact type ADD / MODIFY / REMOVE (CR-1). ADD → **absent** from the target; MODIFY / REMOVE → **present** in it. **An FR already seeded on another open CR, or on an APPROVED CR against the same target, is refused 409 naming it** — otherwise the same live edit is priced twice (R1 auditor M). The seed FRs are locked `FOR UPDATE` before the overlap check, so two CRs seeding one FR at once serialize (R2 auditor L). Saving seeds retires traced rows, clears the four price columns and returns the CR to DRAFT |
| `analyse_cr_impact` | CR_IMPACT | C/U | **Open only, else 409.** "Trace and price", one action. From the seeds, over the **live** working set: BR → BR_FUNCTION_REQUIREMENT → FR; BR → BR_SOLUTION → SOLUTION; FR → its solution; SOLUTION → APPLICATION_SOLUTION → APPLICATION; BR → BR_DATA_ENTITY → DATA_ENTITY; SOLUTION → SOLUTION_PHASE → PHASE; SOLUTION → BENEFIT_SOLUTION → BENEFIT. A part whose component is off is skipped and named. One row per reached object (first route recorded), restored if reached before; rows no longer reached retire. **Computed, never typed** (criterion 64) |
| `price_cr` | CHANGE_REQUEST, CR_IMPACT | U | Inside analyse. **Effort delta = Σ over seed FRs** (Q3's rule, CR-1): ADD → + live `effort_days`; REMOVE → − agreed (frozen) `effort_days`; MODIFY → live − agreed. **Exposure** = Σ agreed `effort_days` of traced, non-seed FRs, beside, never added (Q3). An unrated ADD / MODIFY seed → ANALYSED with the FRs named; all rated → PRICED. Benefit, per impacted benefit, with its unit copied: **value at stake** = \|target − baseline\| × Σ share of its impacted solutions / 100 (BN-1) and **value change** = live value − agreed value; summed **per unit only** (Q9, CR-2). Waves reached; dependency pairs with one end impacted; displacement candidates = `value_ranking`'s bottom quartile per impacted unit. Stamps `priced_at` |
| `decide_cr` | CHANGE_REQUEST, DECISION | U/C | Outcome APPROVED / REJECTED / DEFERRED, meeting date, rationale, alternative rejected (all required). CR locked `FOR UPDATE`, seed FRs read `FOR SHARE`. **APPROVED needs PRICED**, every seed still live and valid, and a re-run of the **seed figures** (effort delta, unrated count) equal to the stored ones — else 409 "the price has moved — trace and price again". Exposure and benefit values that moved are shown as "moved since pricing", not blocking (CR-1; R2 auditor L: traced rows are not locked, so blocking on them would stall a busy project). **APPROVED with delta > 0** must be covered by a cut and/or a budget record (CR-3): a cut = one CR of this project, read scoped, APPROVED, delta < 0, **same target**, not used before (partial UNIQUE settles a race, 409); the budget record (reference, approved by) covers what the cut leaves, `budget_increase_days` computed, never typed. Uncovered → **422** (criterion 65). One transaction writes the DECISION (dimension SCOPE, analysis `priced_diff` when the project has that rule; criterion 66) and the CR's status and `decision_id`. DEFERRED → decidable again, its new decision superseding the deferral's (DC-2); DEFERRED on a DEFERRED CR with nothing changed → 409. APPROVED / REJECTED are final (409) |
| guard on corrections | DECISION | — | A DEC that a CR points at is corrected only through that CR: the generic decision log's correction of it → 409 "correct it on CR-000n" (R1 auditor M) |
| retire / restore | CHANGE_REQUEST | U | Soft delete through `lifecycle`. Open only; a decided CR is evidence and stays |
| `cr_register` | CHANGE_REQUEST | R | Newest first; filter by status, origin, target; delta, exposure, decision number, decider and date (read through the DEC) |
| `correct_cr_decision` | DECISION | C | A decided CR's DEC (wrong date, text or alternative) is corrected only here: a superseding DEC with the **same outcome**, the CR re-pointed to it (R2 auditor M) |
| **unagreed-edit warning** | CR_IMPACT, BASELINE | R | Every seed (BR or FR) of an open, REJECTED or retired-undecided CR whose live row's content hash differs from the target's shadow row, or is missing on one side (an ADD that exists live), listed on the register and as a **warning** in the freeze preview ("CR-0003 was rejected; FR-0012 still carries its change") — the edit is the team's to undo (CR-1, R1 auditor H) |
| M2 tile | CHANGE_REQUEST | R | Project-management dashboard: open / decided counts, net approved effort (slice 12 M2) |

**Out:** applying or reverting a change in the working set (CR-1); linking a CR to the baseline that later carries
it; seeding solutions, applications, entities or waves; CR in reports / PDF / Excel; program roll-up; a CR control
rule (e.g. age of open CRs); a two-person rule on budget records unless Ben picks it (CR-3).

## 2. Logical design

- **Grain.** CHANGE_REQUEST: one row per proposed change to one agreed baseline of one project. CR_IMPACT: one row
  per (change request × impacted object), ever — a seed or a traced object, never both as two rows.
- **Relationships.** PROJECT 1–n CHANGE_REQUEST; BASELINE 1–n CHANGE_REQUEST (target, fixed); CHANGE_REQUEST 1–n
  CR_IMPACT; CR_IMPACT n–1 exactly one of BR / FR / SOLUTION / APPLICATION / DATA_ENTITY / PHASE / BENEFIT;
  CHANGE_REQUEST 0..1–1 DECISION (the latest); CHANGE_REQUEST 0..1–0..1 CHANGE_REQUEST (a cut, used once). Every
  reference is same-project (composite FKs, §5.6).
- **Code lists.** `CR_STATUS` becomes **company-only, pinned, with behaviours** (house pattern of RISK / BENEFIT
  status): DRAFT, ANALYSED → `OPEN`; PRICED → `PRICED`; DEFERRED → `DEFERRED`; APPROVED → `APPROVED`; REJECTED →
  `REJECTED`. Code branches on the behaviour (law 5). `CR_ORIGIN` stays project-overridable. New **`CR_IMPACT_TYPE`**
  (ADD / MODIFY / REMOVE), company-only and pinned — a dropdown, so code_master (law 3).
- **The decided record.** The CR's four price columns are the figures the decider saw; with APPROVED / REJECTED final
  they never change again. Who decided and when are read from the DEC, never copied.
- **Not frozen; reads frozen data.** Neither table is in the freeze set (§6.1 rows 33–34). Pricing reads the target's
  `baseline_function_requirement` and (spec 7+) `baseline_benefit` / `baseline_benefit_solution`; a target before spec
  7 shows "value change not measured against vX.Y", value at stake still shows.
- **Not owned by a BR or step.** Retiring a BR does not retire its CR_IMPACT rows: they are trace evidence, as a risk
  on a step is. `step_retire.OWNED_BY_BR` unchanged; a retired seed shows as retired, and blocks APPROVED.

## 3. Physical design (migrations 0087, 0088 — one per commit, reversible, owner role)

**0087 `change_request`** (+ `CR_STATUS` behaviours, as 0083 / 0085 set theirs) — `change_request_id` identity PK;
`project_id` NOT NULL; `cr_number varchar(20)`, UK `(project_id, cr_number)`; `title varchar(200)` and `rationale
text`, NOT NULL, non-blank; `against_baseline_id` NOT NULL, composite `(against_baseline_id, project_id)` →
`baseline`; `origin_code_id` → code_master with category pinned; `status_code_id` + `status_behaviour` → composite
`(code_id, category, behaviour_code)`; `raised_by_user_id` NOT NULL, CHECK `= created_by`; price columns
`effort_delta_days numeric(9,2)`, `effort_exposed_days numeric(9,2)`, `unrated_fr_count int`, `priced_at timestamptz`
— CHECK all four NULL or all set, written only by the service (law 6); `decision_id` → composite `(decision_id,
project_id)` → `decision` (the latest DEC; it **survives** a deferred CR's return to OPEN, so the next decision
supersedes it — R2 auditor H), CHECK `status_behaviour NOT IN ('APPROVED','REJECTED','DEFERRED') OR decision_id IS
NOT NULL`; `displaces_cr_id`
→ composite self-FK, CHECK `<> change_request_id`, CHECK `IS NULL OR (status_behaviour = 'APPROVED' AND
effort_delta_days > 0)`, partial UNIQUE (each cut once); `budget_increase_days numeric(9,2)` `> 0`,
`budget_reference varchar(200)`, `budget_approved_by varchar(200)` — CHECK all three NULL or set and non-blank, and
`IS NULL OR status_behaviour = 'APPROVED'`; UNIQUE `(change_request_id, project_id)`; AuditMixin (`is_active`,
`row_version`). Indexes: (project, status), target, decision.

**0088 `cr_impact`** — `cr_impact_id` identity PK; `(change_request_id, project_id)` → composite onto
`change_request`; seven nullable typed FKs, each composite `(id, project_id)`, each indexed; CHECK
`num_nonnulls(seven) = 1`; `UNIQUE NULLS NOT DISTINCT (change_request_id, seven)`; `is_seed boolean NOT NULL`;
`impact_type_code_id` → `CR_IMPACT_TYPE`, CHECK `is_seed = (impact_type_code_id IS NOT NULL)`, CHECK `NOT is_seed OR
num_nonnulls(impacted_br_id, impacted_fr_id) = 1`; `reached_via varchar(20)` CHECK `IN ('SEED','BR_FR','BR_SOLUTION',
'FR_SOLUTION','SOLUTION_APP','BR_ENTITY','SOLUTION_WAVE','SOLUTION_BENEFIT')`; `effort_delta_days numeric(9,2)`
CHECK `IS NULL OR (is_seed AND impacted_fr_id IS NOT NULL)`; `agreed_effort_days numeric(9,2)` CHECK `IS NULL OR
impacted_fr_id IS NOT NULL`; `value_unit varchar(40)`, `value_at_stake numeric(16,2)`, `value_change numeric(16,2)`
— CHECK set only when `impacted_benefit_id` is; AuditMixin.

**Grants:** vb_app SELECT / INSERT / UPDATE, no DELETE (law 1). **Purge:** both carry `project_id`, no change.
**Seeds:** `seed_code_master` adds `CR_IMPACT_TYPE`; `code_lists` PINNED / COMPANY_ONLY / BEHAVIOUR_CATEGORIES /
FIXED_BEHAVIOUR gain `CR_STATUS` (and the first two `CR_IMPACT_TYPE`).

## 4. Function design

- **Service** `services/change_request.py` (three-layer rule). `services/decision.py` gains `insert_decision(tx, …)`
  — the same checks, no commit; `record_decision` calls it, and refuses to correct a DEC a CR points at. Retire /
  restore through `lifecycle.RESTORABLE` with an "open only" check.
- **Locks.** Raise reads the target `FOR SHARE` (freeze supersedes `FOR UPDATE` — they serialize). Seeds, analyse and
  decide lock the CR `FOR UPDATE`; decide reads seed FRs `FOR SHARE` and locks the cut CR.
- **Routes** (`routers/change_requests.py`), `component='CHANGE_REQUEST'` on every write (criterion 49b):
  `GET/POST /projects/{id}/change-requests` · `GET/PATCH /change-requests/{id}` · `PUT …/seeds` · `POST …/analyse` ·
  `POST …/decide` (EDIT, SC-7) · `POST …/decision-correction` · `DELETE /change-requests/{id}` · `PATCH …/restore`.
- **Audit:** CR_RAISED, CR_SEEDS_SET, CR_PRICED, CR_DECIDED, CR_RETIRED / RESTORED — numbers, codes and day totals,
  never free text (R7).
- **Screens** (`features/changes/`, `en.changes.json`, kit components; no mockup exists, so composed like Risks):
  register (with the unagreed-edit list); New CR (target defaults to the agreed baseline); CR page — seeds editor,
  "Trace and price", impact table by kind with retired marks, price panel, decide dialog (cut picker of eligible
  CRs, budget fields when not covered; buttons disabled in flight); freeze preview warning; decision page back-link
  to its CR; rail entry; M2 tile. Edit controls through `useCanEdit` / `useComponents`.

## 5. Baselines and hash spec — what changes

**Nothing in the freeze set or the hash spec.** Both tables are live-only (§6.1 rows 33–34): no shadow, no
`freeze_set` entry, `CURRENT_HASH_SPEC` stays 7. Baselines already frozen are untouched and still verify byte for
byte. The slice reads frozen rows of a CR's target, and the freeze **preview** gains one warning line (unagreed
edits); the freeze itself, its gates and what it writes are unchanged. Raise (`FOR SHARE`) and freeze's supersede
(`FOR UPDATE`) serialize. A CR keeps its target when that baseline is later superseded.

## 6. Interface

- **Input:** an editor's CR (title, rationale, origin, target), its seeds, and the decision (outcome, date, rationale,
  alternative, cut, budget record).
- **Output:** the CR with its trace and price; one DECISION per decision; audit events; the M2 tile; the freeze
  preview warning.
- **Validation:** guards (404 → 403 → 409 COMPONENT_OFF) first; then target status, seed validity and overlap, open
  status, price unchanged, cover — refused, never held.
- **Archive:** CR and CR_IMPACT rows kept for the project's life (soft delete only; the latest trace per CR, earlier
  reaches kept as retired rows); decisions append-only; both go with `purge_project` only.
- **Maintenance loop:** the project manager reviews open CRs and the unagreed-edit list at each freeze (the preview
  shows it); a CR age rule is a later control-rule candidate, logged in VB-005.

## 7. Acceptance criteria

1. (63, 190) Raising against the working set or a SUPERSEDED baseline without the agreed approval → 422; another
   project's baseline → 404; FROZEN, APPROVED and the agreed SUPERSEDED one accepted; `CR-0001`, `CR-0002`.
2. A target frozen with EFFORT off → 422. CHANGE_REQUEST off → 409 COMPONENT_OFF on every write.
3. Seeds: ADD on an object in the target, MODIFY / REMOVE on one not in it → 422; another project's object → 404; an
   FR seeded on another open CR → 409.
4. (64) Analyse on a CR seeded with one BR returns its FRs, solutions, applications, data entities, waves and
   benefits, none typed; re-analysing after unlinking a solution retires that row; relinking restores it.
5. Price: ADD 5 d + REMOVE 3 d (agreed) + MODIFY 2→4 d → +4.00; a traced, unseeded 10 d FR → exposure 10.00, not in
   the delta; an unrated ADD FR → ANALYSED with it named.
6. Benefit: benefits in "THB" and "hours" give two unit lines, never one total; a spec-6 target → value change not
   measured.
7. (65) APPROVED +4 d with no cover → 422; with an approved −5 d cut on the same target → 200; that cut on a second
   CR → 409; a cut on another target → 422; −2 d cut + budget record → 200, `budget_increase_days` 2.00; REJECTED
   needs neither.
8. (66) Every decision writes one DECISION (SCOPE, `priced_diff`, the alternative); a refused decide writes none;
   DEFERRED then APPROVED → two DECs, the second superseding the first; correcting a CR's DEC from the decision log →
   409; deciding an APPROVED / REJECTED CR, or seeding / analysing it → 409.
9. Stale price: a seed FR re-rated after pricing → decide 409, nothing written; a traced FR re-rated or a benefit
   changed → decide succeeds, the CR page shows "moved since pricing"; a seed retired after pricing → APPROVED refused.
   A DEFERRED CR re-seeded keeps its DEC, and its next decision supersedes it. `correct_cr_decision` writes a
   superseding DEC with the same outcome.
10. (192) An editor decides; a viewer 403; a non-member of a restricted project 404 on every route (GET-leak test).
11. Retire a decided CR → 409; an open one retires and restores.
12. A REJECTED CR whose seed FR or BR still carries the edit (days or text), or whose ADD FR still exists live, appears in the freeze preview warning and on the register.
13. Browser: raise, seed, trace and price, decide with a cut; the decision log shows the DEC with a link back.

## 8. ASSUMPTIONS

- **A1** Approval does not change the working set (CR-1).
- **A2** Seeds are BRs and FRs only (the design's seeds); the rest is reached.
- **A3** A seed must be live when set; proposing a removal means seeding the FR before retiring it.
- **A4** DEC title "CR-000n <outcome>: <title>"; text = the decider's rationale.
- **A5** One cut per CR (one column, as designed); a cut larger than the increase is used up whole.
- **A6** A target with no `baseline_benefit` rows → value change "not measured".
- **A7** Decided-on date follows DC-4; D2-2 stays open.
- **A8** An object reached by two routes records the first.

## 9. Questions for Ben (one by one, history §1)

- **CR-1 — how a change is stated and priced, and what happens to a rejected edit.** The design says "computed, never
  typed" but not how a new FR is priced before it exists. Recommend: the change is drafted in the working set,
  seeded ADD / MODIFY / REMOVE, priced as working set minus agreed baseline for the seeded FRs only (exposure beside,
  Q3); only the seed figures block an approval when they move; a rejected or undecided edit is listed and warned at
  freeze, and the team undoes it — the app does not. One FR is a seed of one open change at a time (a second change
  to it waits for the first to be decided and frozen).
- **CR-2 — the data design changes this needs** (spec rewritten in the same commit once decided): drop the single
  `benefit_delta_value` (it would add baht to hours, against Q9) for per-unit value at stake and value change on the
  impact rows; impact type becomes a code list (law 3); add the exposure, unrated count, priced-at, budget and status
  behaviour columns; decider and date read from the decision, not copied.
- **CR-3 — what covers an increase, and who may record a budget.** Recommend: one approved net-negative CR on the same
  baseline (used once), a budget record (reference + who approved it) for what remains, or both; any editor may record
  it (SC-7). Alternative: a budget-covered approval must be decided by someone other than the raiser.
