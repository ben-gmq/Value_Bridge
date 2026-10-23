# Slice 1e — Imports: BR, FR and Issue Excel; the process-flow file (spec, 2026-10-24)

Status: **draft for design review.** The signed-off design already fixes this slice's routes (`VB_design.md` §9,
"Phase 1 — slice 1e"), the one pipeline (§7.11, VB law 8), the flow-file contract (§7.2b; D-25, D-36, D-55; R2-D1,
R2-D5, R2-P1…P4) and its acceptance criteria (§10: 106, 110–114, 117, 118, 123, 124, 133, 134). This spec does not
restate them; it fixes what the design leaves to the slice: the column maps, the per-row checks against today's
services, the order of build, and the calls Ben still has to make (§11).

## 1. Purpose
Let a consultant take a project's requirements, functional requirements and issues out to Excel, work on them with the
client, and bring them back in safely — and (1e-b) do the same for a process flow as a `vb-process-flow/2.0` file.

## 1a. Interface
- **Input:** an `.xlsx` the app itself produced (template or export), edited by a project editor; (1e-b) a
  `vb-process-flow/2.0` JSON file — exported by VB, or converted from a client's notes by Claude / Copilot under FTC's
  own accounts with the prompt pack (D-25, D-36).
- **Output:** for BRs — statement and status updated on existing BRs; for FRs — new and updated FRs, their solution
  tag and new BR links; for issues — new and updated issues and their BR links. Every committed batch is an
  `IMPORT_COMMITTED` audit event. Exports are `.xlsx` in the same shape, every row with its signed row token.
- **Validation:** file-level checks first (the sheet, every column present, size ≤ 10 MB, no token from another
  project) → 422, nothing staged. Then every row is checked and staged with errors (block the batch) and warnings
  (shown, never block). Commit re-checks every row under a lock and refuses unless the insert count is confirmed.
- **Archive:** the file itself is never stored (R2-S8). Each row's parsed values and verdict stay in `import_row` for
  90 days, then are purged (Q14); the batch header and the audit event stay.
- **Maintenance loop:** the preview is the human check on every batch; a rejected batch keeps its per-row errors for
  the person to fix and re-upload. Failed commits are audited (`IMPORT_COMMIT_FAILED`) and show in the audit log.

## 2. Doctrine
Playbook §9 items 2, 3, 7, 8, 10, 11; VB law 1, 3, 5, 6, 8; design §7.11 (pipeline), §5.4.18 (import identity), §7.2b
(flow file), §7.12 (file caps). No deviation is taken.

## 3. Keystone grain
`import_row` — **one row per sheet row (or flow-file object) of one upload**, carrying its verdict
(INSERT / UPDATE / MATCH / RETIRE / KEPT), its errors and warnings. Already built (slice 4a); this slice adds targets,
not tables.

## 4. Business Requirement grid

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `download_template` (BR / FR / ISSUE) | `code_master` | R | the project's resolved lists → dropdowns in the template |
| `export_entity` BR | `business_requirement`, `bfc_node` | R | every live BR: number, its step's `hier_code` and name (read-only), statement, status, row token |
| `export_entity` FR | `function_requirement`, `solution`, `br_function_requirement` | R | every live FR: number, name, type, complexity, solution number, linked BR numbers, description, acceptance note, status, `effort_days` (read-only), row token |
| `export_entity` ISSUE | `issue`, `stakeholder`, `issue_br` | R | every live issue: number, title, description, type, severity, status, raised by (stakeholder name), raised / target dates, linked BR numbers, row token |
| `validate_import` | `import_batch`, `import_row` | C | parse → check each row → stage; **no business table written, no number minted** |
| `commit_import` BR | `business_requirement` | U | statement, status via `business_requirement.update_br` (no-commit form) |
| `commit_import` FR | `function_requirement`, `br_function_requirement` | C/U | `create_fr` / `update_fr` / `effort.rate_fr` (no-commit forms); BR links created by `link_fr` |
| `commit_import` ISSUE | `issue`, `issue_br` | C/U | `raise_issue` / `update_issue` (no-commit forms); BR links by `link_br` |
| (manual) | the spreadsheet | U | the consultant edits with the client; the template's dropdowns keep codes valid |

## 5–6. Logical and physical design
**No new table and no migration for 1e-a.** `import_batch.target_entity` and `import_row.row_kind` already allow
`BUSINESS_REQUIREMENT`, `FUNCTION_REQUIREMENT` and `ISSUE` (slice 4a). **1e-b needs one migration**: the
`vb-process-flow/2.0` row kinds for triggers and external flows (§7.2b says the import adds them in its own migration).
That migration goes to `apple` with the 1e-b detail spec, before any 1e-b code.

## 7. Functions (on `services/bulk.py`; each target = a column map + `validate` + `apply`, as DATA_ENTITY / DATA_FIELD)

### 7.1 BUSINESS_REQUIREMENT target (`business-requirements`)
Columns: `br_number` (key, required), `hier_code` (cross-check), `step_name` (read-only), `br_statement`,
`status_code` (`BR_STATUS` list), `row_token`.
```
validate:
  br_number blank → ERROR "BRs are created with their step — use the flow import to add steps" (R2-D1)
  br_number not a live BR of this project → ERROR; duplicate in the file → ERROR
  token checks exactly as DATA_ENTITY (EXPORT_FIRST, TOKEN_ROW_MISMATCH, ROW_RETIRED, ROW_STALE)
  hier_code given and ≠ the step's current hier_code → ERROR "moved since export: now X, file says Y. Re-export"
  step_name differs from the step's name → WARNING "step names are changed on the chart; ignored"
  status_code a system-set status (frozen etc.) → ERROR, as update_br refuses
  br_statement blank → ERROR (a BR needs its statement)
  all compared values equal → MATCH
apply: update_br(…, commit=False)
```
Requirement lines (D-59) are **not** in the sheet (§11 Q-1).

### 7.2 FUNCTION_REQUIREMENT target (`function-requirements`, component `FUNCTION_REQUIREMENT`)
Columns: `fr_number` (key; blank = new), `fr_name`, `fr_type_code` (`FR_TYPE`), `complexity_code` (`FR_COMPLEXITY`),
`solution_number`, `br_numbers` (comma-separated), `description`, `acceptance_note`, `status_code`
(`FR_FULFILMENT_STATUS`), `effort_days` (export-only), `row_token`.
```
validate:
  as DATA_ENTITY for key / token; fr_name required
  fr_type_code resolves; complexity_code resolves (blank allowed)
  solution_number given → a live SOL- of this project, else ERROR; never creates a solution (D-34)
  br_numbers: each a live BR of this project, else ERROR naming it; none → WARNING "No BR: this FR will not trace" (D-28)
  a solution and BRs both given → the solution must answer one of those BRs, as create_fr / update_fr require
  type change away from INTERFACE behaviour with live interface detail → ERROR (criterion 124)
  complexity set or type changed → a rate-card cell must exist for (type, complexity), else ERROR naming it (R2-D6)
  effort_days differs from stored → WARNING "derived from the rate card; your value was ignored"
apply:
  INSERT → create_fr(commit=False) [first BR as br_id] → link_fr for the other BRs → rate_fr if complexity
  UPDATE → update_fr(no-commit) for name/description/note/status/type/solution → rate_fr if complexity changed
           → link_fr for each BR not yet linked (links are ADD-ONLY, §11 Q-3)
```
Interface detail (source/target application, method, frequency) is **not** imported (§11 Q-2).

### 7.3 ISSUE target (`issues`, component `ISSUE`)
Columns: `issue_number` (key; blank = new), `title`, `description`, `issue_type_code`, `severity_code`,
`status_code` (open statuses only), `raised_by` (stakeholder name), `raised_date`, `target_date`, `br_numbers`,
`row_token`.
```
validate:
  key / token as DATA_ENTITY; title required; raised_date required, ISO date (finding D10)
  raised_by must match exactly ONE live stakeholder of this project (normalised name) — none or several → ERROR
    naming the candidates; NEVER creates a person (finding D6)
  status_code must be an OPEN-behaviour status; a closed status → ERROR "resolve it on the issue screen"
  an existing closed issue whose row changes anything → ERROR "reopen it on the issue screen"
  target_date before raised_date → ERROR
  br_numbers: each a live BR, else ERROR
apply: raise_issue / update_issue (no-commit forms) → link_br for each BR not yet linked (add-only)
```

### 7.4 Shared work
- No-commit forms: `update_br`, `update_fr`, `effort.rate_fr`, `link_fr`, `raise_issue`, `update_issue`, `link_br`
  gain the `commit=False` path `create_fr` already has; the pipeline's "commit made to raise" guard proves none slips.
- Templates and exports reuse `xlsx` and `escape_cell()`; the import screen (`ImportDialog`, slice 4a) gains the three
  targets on the BR, FR and Issue list pages.

### 7.5 1e-b — the process-flow file (after 1e-a; detail spec + apple first)
`GET /process-flow-json/schema` (schema, example, prompt pack), `GET /bfc-nodes/{id}/dfd/export?format=json`,
`POST /projects/{id}/bulk/process-flow/validate` (anchor + mode from the route), commit with `acknowledged_retires` —
exactly §7.2b. Its own short spec fixes the 2.0 JSON Schema (owed since slice 7, design CHECK note) and the migration.

## 8. code_master
No new category. Uses `BR_STATUS`, `FR_TYPE`, `FR_COMPLEXITY`, `FR_FULFILMENT_STATUS`, `ISSUE_TYPE`,
`ISSUE_SEVERITY`, `ISSUE_STATUS` as resolved for the project.

## 9. API
Existing routes, three new `target` values: `GET /projects/{id}/bulk/templates/{target}`,
`GET /projects/{id}/bulk/{target}/export`, `POST …/check`, `POST …/validate`, `GET /bulk/batches/{id}[/preview]`,
`POST /bulk/batches/{id}/commit`, with `target` ∈ `business-requirements`, `function-requirements`, `issues`.
Guards as today (template / validate / commit EDIT, export VIEW); the FR target needs `FUNCTION_REQUIREMENT`, the
issue target `ISSUE` (409 COMPONENT_OFF otherwise). No new route.

## 10. Acceptance (1e-a)
Design criteria 106, 111, 117, 124, 133, 134 hold, plus:
1. Exporting BRs and re-importing the file unchanged gives a batch of all MATCH, 0 inserts, and commits nothing.
2. A BR row with its statement changed updates only that BR; its step, lines and RACI are unchanged.
3. A BR row with a blank BR number, or a number from another project, is an error; nothing is written.
4. An FR row with no FR number and BR-0003, BR-0005 creates one FR linked to both, after the insert count is confirmed.
5. An FR row naming a solution that answers none of its BRs is an error.
6. An FR row that drops a BR it is linked to leaves that link in place (add-only) — and says so in a warning.
7. An issue row whose `raised_by` matches no stakeholder, or two, is an error naming them; no stakeholder is created.
8. An issue row setting a closed status is an error; an issue closed in VB, edited in the file, is an error.
9. With the ISSUE component off, the issue template, export and validate return 409 COMPONENT_OFF.
10. Every exported text cell that starts with `=`, `+`, `-` or `@` opens in Excel as text (escape_cell).

## 11. Decisions for Ben (each tagged; the build takes the recommendation and flags it until he answers)
- **Q-1 ASSUMPTION** — the BR sheet edits the statement and status only; requirement lines (D-59) stay on screen.
  Recommended: yes (lines are many-per-BR; a second sheet is a later slice if wanted).
- **Q-2 ASSUMPTION** — FR interface detail is exported for reading but not imported in 1e-a. The design says "read
  only when the type's behaviour is INTERFACE"; deferring it is a change Ben approves. Recommended: defer.
- **Q-3 ASSUMPTION** — BR links on FR and issue rows are add-only; removing a link is done on screen. Recommended: yes
  (a missing cell must never silently unlink).
- **Q-4 ASSUMPTION** — the issue raiser is matched by stakeholder name and must exist already; the design's "pick or
  create in the preview" is a later improvement. Recommended: yes.

## 12. Out of scope
WBS import (its own slice); requirement-line import; interface-detail import (Q-2); creating steps or BRs from Excel
(the flow file does that); the flow file itself until 1e-b; PDF.

## 13. Build checklist
Grade **2** (wrong rows reach a client deliverable, correctable once noticed; nothing irreversible — every change is an
audited update with its before-values kept 90 days). Proof: service-level tests per target for every check in §7,
the round-trip criteria above, one browser pass of export → edit → validate → commit per target. Edge cases left
uncovered on purpose: Excel files not made by VB beyond the file-level checks; concurrent commits of two batches over
the same rows (the row lock and row_version already cover it, tested in slice 4a).
No migration in 1e-a. Sara before commit (imports are on her list). Full suite before push. Strings via `t()`.
Cross-check run: every grid entity is an existing table; every grid function has pseudocode in §7; every criterion in
§10 traces to §7.1–7.3.
