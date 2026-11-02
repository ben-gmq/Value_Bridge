# Slice Decisions — the decision log (spec, 2026-11-02)

**Status:** build spec. Ben's answers DC-1…DC-5 (2026-11-02, via Ren: plan f733f15, all five as recommended). Design
review rounds in §12–13.
**Plan:** `docs/plans/decisions_plan_2026-11-02.md`. **Design:** §4.11 (`record_decision`, `decision_log`), §5.3
DECISION, §6 table 35 and the A-41 row, criterion 78 (66 lands with change requests), API table "Phase 2".
**Migration:** 0084 (granted to this task by Ren, 2026-11-02).

## 1. Purpose
Six months into an engagement nobody remembers why the team chose one option over another. The decision log records
each project decision once — what was decided, when, under which dimension, the analysis it was taken against, and the
alternative rejected (D-17) — and never lets it be edited afterwards. A wrong entry is corrected by recording a new
decision that supersedes it; both stay readable (A-41).

## 1a. Interface
- **Input:** decisions typed on the Decisions screen, one at a time; a correction typed from the decision it corrects.
- **Output:** the decision log (newest first, filter by dimension), the decision page with its correction chain.
- **Validation:** title, decision text and rejected alternative non-blank; dimension from the company's
  `PM_DIMENSION` list; decided-on date not in the future (DC-4); the analysis, when given, is one of this project's
  control rules (DC-3); a correction names a decision of the same project that nothing has corrected yet (DC-2).
  Refused with 422 (bad input), 409 (already corrected), 404 (not visible).
- **Archive:** the row itself is the record — the database refuses UPDATE and DELETE for every role except the scoped,
  approved project purge. Each write is an audit event `DECISION_RECORDED` (numbers and codes only). Not frozen into
  baselines (design §6 table 35).
- **Maintenance loop:** the PMO reads the log at each steering meeting; a correction rate worth watching is visible
  as superseded rows. Reviewed after the first engagement.

## 2. Grain
**One row per recorded decision in one project.** Number `DEC-0001` minted at save (`numbering.next_number('DEC')`;
the series is already seeded by `create_project`). A correction is its own row with its own number.

## 3. Business requirement grid

| Entity | Function | Logic → output |
|---|---|---|
| DECISION | `record_decision` (C) | Title, decision text, alternative rejected, dimension, decided-on date (today unless given, never future), optional analysis code (one of the project's control rules), optional `supersedes_decision_id`. Recorder = the signed-in user (law 6) |
| DECISION | correct (C) | `record_decision` with `supersedes_decision_id`: the target must be in the project and not yet superseded — only the latest in a chain is corrected (DC-2). The old row is untouched |
| DECISION | `decision_log` (R) | All decisions of the project, newest decided-on first, then highest number; filter by dimension; each row shows "superseded by DEC-n" when a later row points at it; option to hide superseded rows |
| DECISION | page (R) | One decision with the decision it supersedes and the one that supersedes it (both as links) |

## 4. Logical design
- DECISION —< 1 PROJECT; DECISION >— 1 CODE_MASTER (`PM_DIMENSION`); DECISION >— 1 APP_USER (recorder);
  DECISION — 0..1 DECISION (supersedes; each decision is superseded by at most one).
- `analysis_code` is a text value from the control-rule registry, not a foreign key: it names *which analysis* was
  read, and stays meaningful if the project's rule is later changed.
- `PM_DIMENSION` becomes **company-only** (no project overrides). A decision cannot be re-pointed to a project's copy
  of a code (the row is immutable), so a project override would split one dimension into two in the filter.

## 5. Physical design (migration 0084)
`decision`: `decision_id` bigint identity PK, **generated always** · `project_id` NOT NULL → project ·
`decision_number` varchar(20) NOT NULL · `title` varchar(200) NOT NULL, non-blank CHECK · `decision_text` text NOT
NULL, non-blank · `alternative_rejected` text NOT NULL, non-blank · `analysis_code` varchar(40) NULL, **format-only
CHECK** `^[a-z0-9_]{1,40}$` (D1-2) · `dimension_code_id` + computed `dimension_category` ('PM_DIMENSION') → composite
FK (code_id, category) on code_master · `decided_on` date NOT NULL, CHECK not after the creation day + 1 (UTC, D1-5) ·
`decided_by_user_id` NOT NULL → app_user, CHECK `= created_by` (D1-1) · `supersedes_decision_id` NULL → composite
`(supersedes_decision_id, project_id)` → `decision(decision_id, project_id)` · `created_at` timestamptz NOT NULL, set
by `trg_decision_stamp` from the database clock (D1-3) · `created_by` NOT NULL → app_user.
- **No** `is_active`, `deleted_at`, `updated_at`, `updated_by`, `row_version` (A-41: exempt from soft delete; nothing
  is ever updated).
- UK `(project_id, decision_number)`; UK `(decision_id, project_id)`; **partial UK `supersedes_decision_id` WHERE NOT
  NULL** (one successor, DC-2); CHECK `supersedes_decision_id <> decision_id`.
- Index `ix_decision_log (project_id, decided_on DESC, decision_id DESC)`; one per FK.
- **Trigger** `trg_decision_immutable` BEFORE UPDATE OR DELETE FOR EACH ROW → new `fn_decision_reject()`: UPDATE always
  raises `restrict_violation`; DELETE passes only when `fn_purge_allows(OLD.project_id)` (0074's one rule), so the
  scoped purge still removes a purged project's decisions (law 1). `fn_reject_modification_purgeable` is not reused:
  it reads `baseline_id`. No TRUNCATE trigger (as the shadows, S8-2). `purge_run.DELETE_GUARDS` names it (D1-4).
- **Grants:** `REVOKE UPDATE, TRUNCATE ON decision FROM vb_app` (it never had DELETE). The app keeps SELECT / INSERT.
- `code_master`: the upgrade **refuses** if any project-tier `PM_DIMENSION` row or hide exists, naming
  `project:code` (0083's pattern); none is expected (no table used the list before).
- Downgrade refuses while any `decision` row exists; then drops the table and function.
- Not a shadow (law 2 n/a); not in `freeze_set`; purge picks the table up by its `project_id` (self-reference
  handled by `purge_run`).

## 6. Function notes
- **Service** `services/decision.py` (three-layer rule). No component (DC-1): `project_ctx(EDIT)` with none, and
  `ROUTE_COMPONENTS` gains no entry. `decided_by_user_id` and `created_by` both come from the JWT user; a body value
  for either, or for the number, is ignored (law 6).
- **Dimension:** resolved by `code_master.resolve` at company tier; a hidden code is refused on create (pickers use
  `options(current)`); an existing decision keeps showing its code's label.
- **Analysis:** must equal the `analysis_code` of one of the project's control-rule rows (switched on or off); any
  other value, or a registry code the project has no rule for, is 422.
- **Correction:** the target is read in the project (404 if not visible / other project — never 403); if a row
  already points at it → 409 "DEC-0003 was already corrected by DEC-0007". A concurrent second correction loses on
  the partial unique index → 409 with the same message (no row lock: `vb_app` has no UPDATE, so `FOR UPDATE` is
  not available, and the index is the guarantee).
- **Date:** `decided_on` after today in ICT (`local_today()`, D1-5) → 422; absent → today (ICT). Whether the meeting
  date is the ICT day or the recorder's own day is put to Ben (D2-2); until then the form pre-fills ICT today.
- **Audit:** `DECISION_RECORDED` with `decision_number`, dimension code, analysis code, superseded number — never
  title or text (R7).
- **Code lists:** `decision.dimension_code_id` named in `code_lists.EXCLUDED` (never re-pointed: immutable);
  `PM_DIMENSION` joins `COMPANY_ONLY`.
- **Lifecycle:** none. Decisions cannot be retired or restored; a decision never blocks retiring anything (it holds no
  FK to a retirable business row other than code_master and app_user).

## 7. API (`/api/v1`)

| Route | Guard | Body | Returns |
|---|---|---|---|
| `GET /projects/{project_id}/decisions?dimension=&include_superseded=` | `project_ctx(VIEW)` | — | log rows incl. `superseded_by_number` |
| `POST /projects/{project_id}/decisions` | `project_ctx(EDIT)` | title, decision_text, alternative_rejected, dimension_code, decided_on?, analysis_code?, supersedes_decision_id? | the decision |
| `GET /decisions/{id}` | `object_guard(Decision, VIEW)` | — | decision + supersedes / superseded-by number and id |

No PATCH, no DELETE, no retire route — by design.

## 8. Screens
- **Decisions** in the left rail under Delivery, always shown. Log as the Risks register: number, decided on, title,
  dimension, analysis, recorded by, "superseded by DEC-n" tag. Filter: dimension; "show superseded" (on by default).
- **Decision page** (`/p/:p/decisions/:id`): read-only view; links to what it supersedes and what supersedes it;
  "Correct this decision" (EDIT, and only when nothing supersedes it) opens the record form prefilled from it with
  `supersedes` set.
- **Record form** (`/p/:p/decisions/new`, `?supersedes=:id`): the fields above; analysis picker lists the project's
  control rules by their label; a warning line "Decisions cannot be edited after saving".
- Strings in `en.decisions.json`.

## 9. Acceptance criteria
1. Record → `DEC-0001`, then `DEC-0002`; `created_by`, `decided_by_user_id`, number in a body are ignored.
2. (78) As `vb_app`, UPDATE and DELETE on `decision` fail (privilege); as `vb_owner`, UPDATE and DELETE fail (trigger);
   the scoped purge of an approved project removes its decisions and no other project's.
3. A correction is a new row pointing at the original; both are returned by the log and the page.
4. Correcting an already-corrected decision → 409 naming both numbers; two concurrent corrections → one 201, one 409.
5. A supersedes id of another project → 404; of an invisible project → 404.
6. Blank title / text / alternative → 422; decided-on tomorrow → 422; absent → today.
7. Dimension of another category, unknown or hidden → 422. Analysis code not among the project's rules → 422.
8. VIEW member POST → 403; non-member of a restricted project → 404 on all three routes.
9. Log: newest first, dimension filter, superseded hidden only when asked; `superseded_by_number` correct.
10. 0084 up / down; down refused with a decision row; up refused with a project-tier `PM_DIMENSION` row.
11. GET leak test, criterion 49 / 49b, code-lists catalog test, purge classification test pass.

## 10. Grade and tests
**Riskiest concern, Grade 1:** a decision row that can be edited or deleted silently destroys the original reasoning,
which cannot be got back. Proof at the database (criterion 2), not only through the API. No mutation harness (its own
task if ever wanted). **Rest Grade 2** (log, validation) and **Grade 3** (screens: one ui-verifier pass).
**Left uncovered:** more than 1,000 decisions per project (no paging); time zone edge of "today".

## 11. Assumptions
- ASSUMPTION A1: the rejected alternative is required for every decision (design: "the field that makes a decision
  log worth reading"); a decision with none writes "None considered".
- ASSUMPTION A2: the recorder is the decider of record (`decided_by_user_id`, as the design); the forum or client
  approver is written into the decision text.
- ASSUMPTION A3: the log shows newest first ("chronological" read as reverse-chronological for a working log).

## 12. Design review round 1 (2026-11-02): apple (3 medium, 5 low) + design-auditor (1 high, 4 medium, 2 low)

| # | Finding | Disposition |
|---|---|---|
| D1-1 | `decided_by_user_id` always equals `created_by` (apple M1) | **Fixed (kept per design):** `ck_decision_decided_by_recorder`; shown as "Recorded by". A separate decider (an org role) is put to Ben (DC-7) |
| D1-2 | A copy of the analysis registry CHECK on an immutable table could never be narrowed, and drifts (apple M2, auditor L) | **Fixed:** format-only CHECK; the service checks the project's rules |
| D1-3 | `created_at` could be backdated by the app (apple M3) | **Fixed:** `trg_decision_stamp` sets it from the database clock |
| D1-4 | The new reject trigger would stop every purge (`DELETE_GUARDS`) (auditor M) | **Fixed:** `fn_decision_reject` joins `purge_run.DELETE_GUARDS`; purge test added |
| D1-5 | "Today" ambiguous across time zones (auditor M) | **Fixed:** `local_today()` (ICT) for default and refusal; DB backstop `ck_decision_not_future` (+1 day, apple L5) |
| D1-6 | Correction target must be read in the URL's project (auditor L) | **Fixed:** read with `project_id = :p` → 404 |
| D1-7 | Double submit makes a permanent duplicate (auditor M) | **Fixed in the form:** one save in flight; an idempotency key is not built (it would add a column) — tracked as a backlog line |
| D1-8 | No way to withdraw a decision recorded by mistake (auditor HIGH) | **Ben's call (DC-6):** built as designed (A-41); options put to him — accept, or an IS-only audited redaction as its own task |
| D1-9 | Confidentiality / archive coverage (auditor M) | **Answered:** decisions are not frozen, so no baseline archive file carries them; the project ARCHIVE run is not built yet — when it is, it must include `decision` |
| apple L1 | BY DEFAULT identity lets a crafted multi-row insert form a cycle | **Fixed:** `GENERATED ALWAYS` |
| apple L2 | Correcting a typo forces a rejected alternative; no "revision vs correction" kind | **Accepted (A1)**; a supersede kind put to Ben as DC-8 (WHENEVER) |
| apple L3 | Design ERD says `decided_at timestamptz` | **Fixed in docs:** design §5.3 and ERD rewritten (DC-4) |
| apple L4 | Law-3 exemption must be explicit; TRUNCATE | **Fixed:** A-41 exemption named; `REVOKE TRUNCATE`; test asserts no UPDATE / DELETE / TRUNCATE |

## 13. Design review round 2 (final under the cap, 2026-11-02): design-auditor (0 high, 1 medium, 3 low) + sara (4 low)

D1-1…D1-6 and apple L1 / L4 hold. Nothing structural. New:

| # | Finding | Disposition |
|---|---|---|
| D2-1 (medium) | D1-7's backlog line was not written; a lost response then a second Save writes a permanent duplicate | **Logged:** VB-005 line, depending on DC-6 |
| D2-2 (low) + sara L1 | The form sends the browser's day, bypassing ICT; Sydney morning → 422, London evening → a day early | **Fixed:** the form pre-fills and caps at the ICT day; the calendar question put to Ben |
| D2-3 (low) | Format CHECK refused digits a future rule code may hold → 500 | **Fixed:** `[a-z0-9_]` |
| D2-4 (low) | Nothing enforces that the future ARCHIVE run includes `decision` | **Logged:** VB-005 line, and an acceptance line for the ARCHIVE slice |
| sara L2 | Chain links and Correct used the URL's project, not the decision's | **Fixed:** the page uses `project_id` from the decision |
| sara L3 | No unsaved-changes guard on the form (as the rest of the app) | **Logged:** VB-005 line |
| sara L4 | `decided_on` without `Mapped[date]` | **Fixed** |

Nothing further goes back to the auditor; what remains is settled against the running code.
