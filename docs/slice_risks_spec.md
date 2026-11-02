# Slice Risks — the risk register, promote to an issue, the `risk_register` rule (spec, 2026-11-02)

**Status:** build spec, Ben's answers RK-1…RK-6 (2026-11-02, via Ren: plan Q1–Q6 all (a)). Design review rounds in §12–13.
**Plan:** `docs/plans/risks_plan_2026-11-02.md`. **Design:** §4.10 (functions), §5 RISK, §7.13 (rule thresholds),
criteria 61–62, API table "Phase 2 — risks". **Migration:** 0083 (slot confirmed by Ren, 2026-11-02).

## 1. Purpose
A consultant records what *might* go wrong on the engagement, scores it, names who owns the mitigation and by when,
and — when it happens — turns it into an issue without losing the record that it was foreseen (D-15). The control
panel flags the engagement when an open risk scores 12 or more and escalates at 16.

## 1a. Interface
- **Input:** risks typed on the Risks screen (one at a time); the promote dialog.
- **Output:** the register (ranked by exposure), the risk page, a new issue on promote, one panel row.
- **Validation:** codes from the project's lists; owner, node, solution and wave live in the same project; the score
  is never taken from a request; a promoted risk is read-only.
- **Archive:** each write is an audit event (`RISK_RAISED`, `RISK_UPDATED`, `RISK_MATERIALISED`, retire / restore).
  Risks are live, not frozen in baselines (design §5 table 32).
- **Maintenance loop:** the panel row is reviewed at each steering meeting; the rule's numbers are the client's to
  agree (CB-5), revisited after the first engagement.

## 2. Grain
**One row per risk in one project.** Number `RSK-0001` minted at save (`numbering.next_number('RSK')`; the series
is already seeded by `create_project`).

## 3. Business requirement grid

| Entity | Function | Logic → output |
|---|---|---|
| RISK | `raise_risk` (C) | Title, probability, impact, owner (org role, required), raised date (today unless given, never in the future), optional description, mitigation, target date (not before raised), node, solution, wave. Status starts OPEN. Score derived |
| RISK | `score_risk` (U) | Edit any field above and the status (OPEN / MITIGATING / CLOSED). Score re-derived at save. Stale `row_version` → 409 |
| RISK, ISSUE | `promote_risk_to_issue` (U/C) | Creates the issue (raiser stakeholder, severity, type and an optional issue target date chosen in the dialog — RK-4; title and description copied; the risk's own target date is **not** copied, R1-1), links it, status → MATERIALISED. Risk row stays, read-only, and cannot be retired (R1-2) |
| RISK | `risk_register` (R) | Live risks, open first, ranked by exposure then oldest raised; age in days since raised (closed and materialised risks show no age); filter by status, owner, wave |
| CONTROL_RULE | `risk_register` headline | Highest exposure among live open risks; flag ≥ 12, escalate ≥ 16 (RK-2, RK-5) |

## 4. Logical design
- RISK —< 1 PROJECT; RISK >— 1 ORG_ROLE (owner); RISK >— 0..1 BFC_NODE / SOLUTION / PHASE (wave, RK-3);
  RISK — 0..1 ISSUE (materialised as; one issue per risk at most).
- Probability, impact, status: CODE_MASTER, each carrying a **behaviour**:
  - `RISK_PROBABILITY`, `RISK_IMPACT`: a weight `W1`…`W5` (RK-1). Library: RARE…ALMOST_CERTAIN = W1…W5,
    NEGLIGIBLE…SEVERE = W1…W5. A project may rename, add or hide a level; a new level picks its weight.
  - `RISK_STATUS`: `OPEN` (OPEN, MITIGATING), `CLOSED` (CLOSED), `MATERIALISED` (MATERIALISED). Company-only, like
    every other status list (I-1, W-4); all four codes pinned, their behaviour fixed (R1-4). MITIGATING is open.
- `exposure_score` = weight(probability) × weight(impact), 1–25.

## 5. Physical design (migration 0083)
`risk`: `risk_id` PK identity · `project_id` FK · `risk_number` varchar(20) · `title` varchar(200) non-blank ·
`description` text · `probability_code_id` + computed `probability_category` + `probability_weight` varchar(20) →
composite FK (code_id, category, behaviour_code) · same for `impact_*` · `exposure_score` smallint **generated
stored** `substr(probability_weight,2)::int * substr(impact_weight,2)::int` · `mitigation` text ·
`owner_org_role_id` NOT NULL → (org_role_id, project_id) · `status_code_id` + `status_category` + `status_behaviour`
→ composite FK · `raised_date` date NOT NULL · `target_date` date · `bfc_node_id` / `solution_id` / `phase_id` nullable → (id, project_id) ·
`materialised_issue_id` nullable → (issue_id, project_id), plus the live guard `risk_live` → (issue_id, project_id,
is_active), so a live risk points only at a live issue (issue_br's pattern) · audit columns.
- UK `(project_id, risk_number)`; UK `(risk_id, project_id)`; partial UK `materialised_issue_id` where not null.
- CHECKs: `(status_behaviour = 'MATERIALISED') = (materialised_issue_id IS NOT NULL)`; both weights in `W1`…`W5` on the
  row itself (the score's cast never depends on another table); `target_date >= raised_date`.
- Indexes: `ix_risk_open (project_id, exposure_score DESC) WHERE is_active AND status_behaviour = 'OPEN'`; one per FK.
- `code_master`: `ck_code_behaviour_present` widened to the three categories; `ck_code_risk_weight_behaviour`
  (`W1`…`W5`) and `ck_code_risk_status_behaviour` (OPEN / CLOSED / MATERIALISED). Library rows backfilled by code;
  the upgrade **refuses** on any project-tier `RISK_STATUS` row or hide, or any risk-list code it cannot map
  (0061's pattern). `seed_code_master` carries the same behaviours.
- `control_rule`: `ck_ctl_comparison` widened with `GE` (RK-2).
- Downgrade refuses while any `risk` row or any `GE` rule exists; then drops the table and restores the CHECKs.
- `vb_app`: SELECT / INSERT / UPDATE from default privileges, no DELETE (law 1). Not a shadow (law 2 n/a).

## 6. Function notes
- **Service** `services/risk.py` (three-layer rule). Writes need component `RISK` (409 `COMPONENT_OFF`); promote
  also needs `ISSUE`. Owner, node, solution, wave are read `FOR SHARE` and must be live and in the project (422).
- **Status:** a PATCH may set any code whose behaviour is OPEN or CLOSED; a MATERIALISED-behaviour code only through
  promote (422 — tested by behaviour, not code). A materialised risk refuses retire (409) and every PATCH field except
  its owner, node, solution and wave (R2 NEW-1): its score, codes, dates and text are the evidence it was foreseen
  (R1-2), while what it points at may still be re-pointed so a restructure is never locked.
- **Dates:** the service refuses a target before the raised date and a raised date in the future with 422 on create
  and PATCH (R2 NEW-2), so the CHECK never surfaces as a 500. Its issue is closed, not retired, when it proves a duplicate (the live guard and
  lifecycle both refuse retiring it while the risk lives).
- **Audit (R1-3):** `RISK_RAISED` and `RISK_UPDATED` carry the probability, impact and status codes and the score —
  before and after on an update — so a score talked down before a steering meeting can be reconstructed. Codes and
  numbers only, never title or text (R7).
- **Promote** (`POST /risks/{id}/materialise`, body: `row_version`, `raised_by_stakeholder_id`, `severity_code`,
  `issue_type_code`, optional `target_date`): one transaction — risk locked, `issue.raise_issue(commit=False)` (title
  and description copied; raised today), link set, status MATERIALISED, audit `RISK_MATERIALISED` (ids and numbers only). Twice → 409.
  The Decisions module is not built; when it is, it records the decision (design §7 pseudo-code `record_decision`).
- **Lifecycle:** `Risk` joins `lifecycle.RESTORABLE` and `LABELS` (`"Risk", RSK-0003`). Nothing cascades: a live risk
  blocks retiring its owner role, node, solution, wave or issue (409 naming it), and restoring a risk needs those live
  — the app's standing rule (§7.12). `step_retire` does **not** own a risk: a risk is not part of the step, and design
  §5.4.7 lists `risk.bfc_node_id` as deliberately free of the process guard (a risk may sit on a whole area). So a
  step with a live risk refuses to retire until the risk is re-pointed or retired (SR-4; R1-5).
- **Code lists:** the three code columns are re-pointed on a project override (probability, impact) or named in
  `code_lists.EXCLUDED` (status, company-only). `RISK_PROBABILITY` / `RISK_IMPACT` / `RISK_STATUS` join
  `BEHAVIOUR_CATEGORIES` with their allowed behaviours (a wrong one is a 422); `RISK_STATUS` joins `COMPANY_ONLY` and
  all four codes join `PINNED` (R1-4); the behaviour-fixed check in `code_lists.update_code` widens from
  `ISSUE_STATUS` to `RISK_STATUS` (R2), so no risk status's meaning can change. A behaviour change on any code a risk row holds — live **or retired** — is a
  409, never the foreign key's 500 (apple L1) — counted in the behaviour-change check only, never in `in_use`.
- **Components:** `RISK` joins `components.BUILT` and `COMPONENT_ROWS` (live risks block switching it off).
- **Control (piece C):** `risk_register` joins `HOUSE_RULES` (`EXPOSURE`, `GE`, 12, 16, "Mitigation owner + date;
  steering if unmitigated"), leaves `COMING`; `_breaches` handles `GE` (equal is a breach). Not measured: component
  off (`RISK_OFF`) or no live open risk (`NO_OPEN_RISKS`) — never 0. Figures beside it: open count, open ≥ flag,
  open with no target date. `seed_control_rules` adds it off in running projects (CB-5), on in new ones.

## 7. API (`/api/v1`)

| Route | Guard | Body | Returns |
|---|---|---|---|
| `GET /projects/{project_id}/risks?include_retired=&status=&owner_org_role_id=&phase_id=` | `project_ctx(VIEW)` | — | register rows |
| `POST /projects/{project_id}/risks` | `project_ctx(EDIT, component='RISK')` | risk fields, codes | risk incl. `RSK-`, `exposure_score` |
| `GET /risks/{id}` | `object_guard(Risk, VIEW)` | — | risk + issue number if materialised |
| `PATCH /risks/{id}` | `object_guard(Risk, EDIT, component='RISK')` | `row_version` + fields | risk |
| `POST /risks/{id}/materialise` | `object_guard(Risk, EDIT, component='RISK')` | see §6 | risk + issue |
| `POST /risks/{id}/retire`, `/restore` | as the other restorables | `row_version` | risk |

## 8. Screens
- **Risks** in the left rail under Delivery (hidden when `RISK` is off, `useComponents`). Register as the Issues list:
  number, title, exposure (coloured from the project's `risk_register` rule — caution at flag, error at escalate — and
  **plain while the rule is off**, R1-6), owner, status, wave, age, target. Filters: status, owner, wave; "show retired".
- **Risk page** (`/p/:p/risks/:id`, and `/new`): the form; a "Promote to issue" button (EDIT, `ISSUE` on, not yet
  materialised) opening the dialog; after promote, "Materialised as ISS-0007" linking to the issue, form read-only.
- **Issue page:** "Materialised from RSK-0003" when one points at it.
- **Code lists:** the weight / status behaviour picker for the three lists. Strings in `en.risks.json`.

## 9. Acceptance criteria
1. (61) LIKELY × MAJOR scores higher than POSSIBLE × MODERATE; a score in a body is ignored; changing probability
   re-scores.
2. A project that renames a level, or adds one with weight W4, scores by weight.
3. (62) Promote creates the issue, links it, sets MATERIALISED, the risk row stays; twice → 409; `ISSUE` off → 409 and
   no issue row; a failure after the issue insert leaves neither change; a risk past its target date promotes.
4. A materialised risk refuses retire and any PATCH but owner / node / solution / wave; MATERIALISED cannot be set by
   PATCH; its issue cannot be retired; a raised date after the target is a 422.
4a. The pinned risk statuses' behaviour cannot be changed; a weight change on a code a retired risk holds is a 409.
4b. `RISK_UPDATED` records before / after codes and score.
5. Stale `row_version` → 409; `RISK` off → 409 `COMPONENT_OFF`; a foreign or retired owner / node / solution / wave → 422.
6. Register: open before closed, exposure descending, then oldest; filters work; retired hidden unless asked.
7. Panel: no open risk → not measured; 11 GREEN, 12 FLAG, 16 ESCALATE; CLOSED and MATERIALISED ignored.
8. Seed: the rule arrives off in a running project, on in a new one. 0083 up / down; down refused with a risk row.
9. A live risk blocks retiring its owner role and its issue (409 names RSK-); restore needs its parents live.
10. GET leak test, criterion 49 / 49b, code-lists catalog test, purge test all pass unchanged in shape.

## 10. Grade and tests
**Grade 2** — a wrong score or panel colour reaches a steering meeting; nothing moves money, grants access or destroys
data. Riskiest concern: promote half-failing. ~30 tests, no mutation harness. **Left uncovered:** ageing beyond
"days since raised"; more than 500 risks per project.

## 11. Assumptions
- ~~ASSUMPTION A1~~ replaced in review: ageing counts from `raised_date` (apple L4).
- ASSUMPTION A2: a risk may sit on any live node of the project, to-be or as-is.
- ASSUMPTION A3: the owner is required (the panel's action is "mitigation owner + date").

## 12. Design review round 1 (2026-11-02): apple (2 medium, 4 low) + design-auditor (4 medium, 2 low), no high

| # | Finding | Disposition |
|---|---|---|
| R1-1 | Promote copied an overdue target date into the issue → refused (both reviewers) | **Fixed:** not copied; the dialog takes an optional issue target date |
| R1-2 | Retiring a materialised risk was the only way to retire its issue, and hid the foreseen record (auditor) | **Fixed by default, Ben to confirm:** a materialised risk cannot be retired; its issue is closed, not retired |
| R1-3 | No record of how a score changed (auditor) | **Fixed:** RISK_RAISED / RISK_UPDATED carry codes and score, before / after |
| R1-4 | Risk status behaviours editable → promote 500s or a silent meaning change; no allowed list → 500 (both) | **Fixed:** all four pinned, behaviour fixed; allowed lists in `_behaviour` |
| R1-5 | Plan said step retire leaves a risk live; spec cited a missing section (auditor) | **Fixed:** a live risk blocks step retire; source cited as §5.4.1 |
| R1-6 | Register colours on an un-agreed rule (auditor) | **Fixed:** plain while the rule is off |
| apple L1 | Weight change on a code only a retired risk holds → FK 500 | **Fixed:** counts retired risk rows too → 409 |
| apple L2 | Score cast depends on another table's CHECK | **Fixed:** weight CHECKs on `risk` |
| apple L3 | A live risk could point at a retired issue | **Fixed:** live guard FK `fk_risk_issue_live` |
| apple L4 | Ageing from `created_at` | **Fixed:** `raised_date` |
| Q4 | What if 0083 refuses a project's own code | The refusal names project:code; the operator gives it a weight by hand and re-runs (0061's way) |

## 13. Design review round 2 (final under the cap, 2026-11-02)
R1-1, R1-3, R1-6 and apple L2–L4 hold. Corrected here: R1-4 (the behaviour check itself widens to RISK_STATUS), R1-5
(the citation is §5.4.7), apple L1 (counted in the behaviour check only). New:

| # | Finding | Disposition |
|---|---|---|
| NEW-1 (medium) | With R1-2, a materialised risk could neither be edited nor retired, so its owner role, node, solution and wave could never be retired | **Default built, Ben to decide:** a materialised risk's owner / node / solution / wave stay editable; everything else is fixed and it cannot be retired. Alternative: let it be retired (shown under "show retired") |
| NEW-2 (low) | A raised date moved past the target date → CHECK 500 | **Fixed:** 422 from the service |

Nothing further goes back to the auditor; what remains is settled against the running code.
