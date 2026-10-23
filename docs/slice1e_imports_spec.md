# Slice 1e — Imports: BR, FR and Issue Excel; the process-flow file (spec rev 2, 2026-10-24)

Status: **rev 2 — design review round 1 answered (17 findings: 3 HIGH, 10 MEDIUM, 4 LOW, all taken; §14).** The
signed-off design already fixes this slice's routes (`VB_design.md` §9, "Phase 1 — slice 1e"), the one pipeline
(§7.11, VB law 8), the flow-file contract (§7.2b; D-25, D-36, D-55; R2-D1, R2-D5, R2-P1…P4) and acceptance criteria
(§10: 106, 110–114, 117, 118, 123, 124, 133, 134). This spec does not restate them; it fixes what the design leaves to
the slice: the column maps, the per-row checks against today's services, the build order, and Ben's open calls (§11).

## 1. Purpose
Let a consultant take a project's requirements, functional requirements and issues out to Excel, work on them with the
client, and bring them back in safely — and (1e-b) do the same for a process flow as a `vb-process-flow/2.0` file.

## 1a. Interface
- **Input:** an `.xlsx` the app produced (template or export), edited by a project editor. (1e-b: a
  `vb-process-flow/2.0` JSON file; its AI-conversion path is reviewed with the 1e-b spec, S2.)
- **Output:** BRs — statement and status of existing BRs; FRs — new and updated FRs, solution tag, complexity, and BR
  links added; issues — new and updated open issues and BR links added. Every committed batch is an `IMPORT_COMMITTED`
  audit event and keeps, per row, its before-values **and the link ids it added** (P6). Exports are `.xlsx` in the same
  shape, each row with its signed row token and its signed links-at-export cell (D1).
- **Validation:** file-level checks first (sheet, every column, ≤ 10 MB, ≤ 2,000 rows for these targets (P7), no
  token from another project) → 422, nothing staged. Then each row: errors block the batch, warnings never do. Commit
  re-checks every row under the batch lock, refuses unless the insert count is confirmed, and **a row that validated
  clean with no data change in between always commits** (P3) — every refusal a service can make is checked per row
  first.
- **Archive:** the file is never stored (R2-S8). `import_row` keeps each row's values, verdict, before-values and added
  link ids for 90 days (Q14); the batch header and audit events stay. **Reversing a bad batch** (P6): within 90 days the
  batch's preview lists every row it changed and every link it added; an editor reverses them on screen (unlink,
  retire, edit back). No automatic undo in 1e-a.
- **Maintenance loop** (P8): the weekly archive check (`scripts.weekly_check`, run by IS) adds one line — REJECTED
  batches and `IMPORT_COMMIT_FAILED` events in the last 7 days, per target. Lilly reads it with each weekly report; the
  same target failing twice for the same reason becomes a BUGLOG entry.

## 2. Doctrine
Playbook §9 items 2, 3, 7, 8, 10, 11; VB law 1, 3, 5, 6, 8; design §7.11, §5.4.18, §7.2b, §7.12. No deviation.

## 3. Keystone grain
`import_row` — **one row per sheet row (or flow-file object) of one upload**, with its verdict, errors and warnings.
Built in slice 4a; this slice adds targets, not tables.

## 4. Business Requirement grid

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `download_template` (BR / FR / ISSUE) | `code_master` | R | the project's **picker** lists (hidden codes left out) → dropdowns |
| `export_entity` BR | `business_requirement`, `bfc_node` | R | live BRs: number, step `hier_code` and name (read-only), statement, status, row token |
| `export_entity` FR | `function_requirement`, `solution`, `br_function_requirement`, `fr_interface`, `application` | R | live FRs: number, name, type, complexity, solution, linked BRs (+ signed links-at-export), description, acceptance note, status, `effort_days`, interface source / target app (read-only), row token |
| `export_entity` ISSUE | `issue`, `stakeholder`, `org_unit`, `issue_br` | R | live issues: number, title, description, type, severity, status, raiser name and org unit, dates, linked BRs (+ signed links-at-export), row token |
| `validate_import` | `import_batch`, `import_row` | C | parse → check each row → stage; no business table written, no number minted |
| `commit_import` BR | `business_requirement` | U | statement, status via `update_br` (no-commit) |
| `commit_import` FR | `function_requirement`, `br_function_requirement` | C/U | links → `create_fr` / `update_fr` → `rate_fr` (no-commit), in the §7.2 order |
| `commit_import` ISSUE | `issue`, `issue_br` | C/U | `raise_issue` / `update_issue` (no-commit) → `link_br` |
| `weekly_check` report | `import_batch`, `audit_event` | R | REJECTED / failed batches per target, last 7 days (P8) |
| (manual) | the spreadsheet | U | the consultant edits with the client |

## 5–6. Logical and physical design
**No new table, no migration for 1e-a**: `import_batch.target_entity` and `import_row.row_kind` already allow the three
targets (slice 4a). Added link ids live in the row's existing `payload` JSON. **1e-b needs one migration** (the 2.0 row
kinds, §7.2b) — to `apple` with the 1e-b detail spec, before any 1e-b code.

## 7. Functions (`services/bulk.py`; each target = column map + `validate` + `apply`, as DATA_ENTITY)

### 7.0 Rules for every target (P2, P3, D4)
- **A check that refuses a value runs only on a value the row changes** against the live record (or on a new row).
  An unchanged frozen status, closed status, retired code, hidden code or out-of-scope solution tag already held round-
  trips as MATCH. `apply` passes a field to a service only when it changed.
- **Codes:** a changed or new coded value must be in the project's picker list (`resolve(..., for_picker=True)`);
  an unchanged one already held passes (R5).
- **Lengths** come from the service limits (`max_len` per column), so no over-long cell reaches a service.
- **Stale rows from a freeze** (D6): a stale BR whose only difference is the status now BASELINED says "a baseline was
  frozen since your export — re-export".
- **Re-upload and duplicates** (P1): at validate, a file whose sha256 matches a COMMITTED batch of the same project and
  target is a **file warning** naming its date and committer; each INSERT row whose normalised name + type (FR) or
  title + raised date (issue) matches a live record gets a **POSSIBLE_DUPLICATE** warning naming it; the preview shows
  both above the insert count. After a commit with inserts the screen says "re-export before editing again".
  Warn, not block, pending Ben (§11 Q-6).
- **Links are "BRs to add"** (P5, D1): the `br_numbers` cell is compared against the signed links-at-export cell.
  A BR in the cell and not linked at export is an addition (UPDATE, preview shows "links added: BR-0007"). A BR linked
  at export and missing from the cell is ignored with a warning (add-only, Q-3). A BR linked at export and **unlinked
  on screen since** is a ROW_STALE error naming it — an old file never re-creates a removed link. Duplicates in the
  cell are dropped. The preview never shows a before/after of the whole list.
- **Components** (S1): template and export require the target's component (FR: `FUNCTION_REQUIREMENT`; issue:
  `ISSUE`) → 409 COMPONENT_OFF. Per row: a changed complexity needs `EFFORT`, a set solution needs `SOLUTION` → row
  error naming the component. The two checks move from `routers/scope.py` into `function_requirement` / `effort`, so
  screen and import share them (playbook §10).
- Resolutions (stakeholder, solution, BRs) are pinned at validate (4a-R13); a different resolution at commit is an error.
- Service calls in one row pass the row's **current** `row_version` from call to call (P3d).

### 7.1 BUSINESS_REQUIREMENT target (`business-requirements`)
Columns: `br_number` (key, required), `hier_code` (cross-check), `step_name` (read-only), `br_statement`,
`status_code` (`BR_STATUS`), `row_token`.
```
validate:
  br_number blank → ERROR "BRs are created with their step — use the flow import to add steps" (R2-D1)
  not a live BR of this project, or twice in the file → ERROR
  token checks as DATA_ENTITY
  hier_code given and ≠ step's current hier_code → ERROR "moved since export: now X, file says Y. Re-export"
    (this also catches a row pointing at a summary node: a BR exists only on a process — criterion 106b)
  step_name ≠ the step's name → WARNING "step names change on the chart; ignored"
  changed status_code that is system-set (BASELINED…) → ERROR, as update_br refuses
  br_statement blank → ERROR
  nothing changed → MATCH
apply: update_br(fields changed, status only if changed, commit=False)
```
Requirement lines (D-59) are not in the sheet (Q-1).

### 7.2 FUNCTION_REQUIREMENT target (`function-requirements`, component `FUNCTION_REQUIREMENT`)
Columns: `fr_number` (key; blank = new), `fr_name`, `fr_type_code`, `complexity_code`, `solution_number`,
`br_numbers`, `br_links_at_export` (signed, read-only), `description`, `acceptance_note`, `status_code`,
`effort_days` (read-only), `interface_source_app` and `interface_target_app` (read-only, Q-2), `row_token`.
```
validate (changed values only, §7.0):
  key / token as DATA_ENTITY; fr_name required
  fr_type_code, complexity_code, status_code in the picker lists (§7.0)
  solution_number: a live SOL- of this project (never created, D-34); blank on an existing FR → unchanged (Q-5)
  links = live links ∪ the cell's additions (§7.0); each BR live in this project
  links empty → WARNING "No BR: this FR will not trace" (D-28); no warning for a missing solution (D-52, criterion 133)
  solution set or changed → it must answer at least one BR in `links` (the some-BR rule update_fr applies)
  type changed: away from INTERFACE behaviour with live interface detail → ERROR (criterion 124);
                a rate cell must exist for (new type, CURRENT complexity) — update_fr re-derives on it (P3c)
  complexity changed (or set on a new row): a rate cell for (final type, new complexity), and EFFORT on
  effort_days ≠ stored → WARNING "derived from the rate card; your value was ignored"
  new row with a non-default status → honoured (Q-7)
apply (P3a/b):
  INSERT → create_fr(no solution, br_id = first link, commit=False) → link_fr for the other links
           → update_fr(solution, status if non-default, type unchanged) → rate_fr(complexity)
  UPDATE → link_fr for each addition (record the ids in payload) → update_fr(changed fields, solution if changed,
           type if changed) → rate_fr if complexity changed
```

### 7.3 ISSUE target (`issues`, component `ISSUE`)
Columns: `issue_number` (key; blank = new), `title` (max 200), `description`, `issue_type_code`, `severity_code`,
`status_code`, `raised_by`, `raised_by_org_unit` (D3), `raised_date`, `target_date`, `br_numbers`,
`br_links_at_export` (signed, read-only), `row_token`.
```
validate (changed values only):
  key / token as DATA_ENTITY; title required; raised_date required, ISO date (D10)
  raiser: on UPDATE, a raised_by equal to the current raiser's name (and unit) keeps the current stakeholder id;
          otherwise name + org unit must match exactly ONE live stakeholder → else ERROR naming the candidates;
          never creates a person (D6); the id is pinned
  status_code changed: must be an OPEN-behaviour status (closing is done on the issue screen with a resolution)
  issue closed in VB: status may not change (reopen on screen); title / description edits follow update_issue (Q-8)
  target_date before raised_date → ERROR
  br_numbers: §7.0 link rules against issue_br
  new row with a non-default open status → honoured (Q-7)
apply: raise_issue / update_issue (no-commit, changed fields only) → link_br for each addition (ids in payload)
```

### 7.4 Shared work
- No-commit forms: `update_br`, `update_fr`, `effort.rate_fr`, `link_fr` (with its drift query skipped inside an
  import, P7), `raise_issue`, `update_issue`, `link_br` gain the `commit=False` path `create_fr` has; the pipeline's
  "commit made to raise" guard proves none slips. The SOLUTION / EFFORT component checks move into the services (S1).
- Signed links-at-export: the row token's HMAC over `links|<sorted BR numbers>`, one more protected column.
- The import dialog (slice 4a) gains the three targets on the BR, FR and Issue list pages; the preview shows file
  warnings, POSSIBLE_DUPLICATE warnings and "links added" above the insert count.

### 7.5 1e-b — the process-flow file (after 1e-a; own detail spec, `apple`, and review)
Exactly §7.2b. Its spec fixes the 2.0 JSON Schema, the migration, and the egress row for the AI conversion path
(vendor, plan, retention, Ben's confidentiality answer — S2).

## 8. code_master
No new category: `BR_STATUS`, `FR_TYPE`, `FR_COMPLEXITY`, `FR_FULFILMENT_STATUS`, `ISSUE_TYPE`, `ISSUE_SEVERITY`,
`ISSUE_STATUS`, resolved per project; pickers exclude hidden codes.

## 9. API
Existing routes, three new `target` values (`business-requirements`, `function-requirements`, `issues`):
`GET /projects/{id}/bulk/templates/{target}`, `GET …/bulk/{target}/export`, `POST …/check`, `POST …/validate`,
`GET /bulk/batches/{id}[/preview]`, `POST /bulk/batches/{id}/commit`. Guards: template / validate / commit EDIT,
export VIEW; template and export now also require the target's component (S1). No new route.

## 10. Acceptance (1e-a)
Design criteria 111, 117, 124, 133, 134 hold; 106 holds as "no warning for a missing solution" (D-52 supersedes its
first half, Q-9) and "a row pointing at a summary node is an error" (§7.1). Plus:
1. Export → re-import unchanged gives all MATCH, 0 inserts, nothing written — **on a project with a frozen baseline, a
   closed issue, a retired FR type in use and an FR tagged outside its BRs** (P2).
2. A BR row with its statement changed updates only that BR; its step, lines and RACI are unchanged.
3. A blank BR number, or one from another project, is an error; nothing is written.
4. A new FR row with BR-0003, BR-0005 and SOL-0002 answering only BR-0005 creates one FR linked to both and tagged
   SOL-0002 (P3a). Every row that validates clean commits.
5. A solution answering none of the row's final BRs is an error.
6. An FR row that omits a linked BR keeps the link and warns; an old export listing a BR unlinked on screen since is an
   error naming it (D1); a row only adding BR-0007 is an UPDATE whose preview says "links added: BR-0007".
7. Re-uploading a committed file warns with its date and committer; a new FR row matching a live FR's name and type
   warns POSSIBLE_DUPLICATE (P1).
8. An issue raiser matching no stakeholder, or two in the same unit, is an error; none is created; an unchanged raiser
   round-trips even when a same-named stakeholder exists in another unit (D3).
9. A changed status to a closed one is an error; an unchanged closed issue round-trips.
10. With ISSUE off, the issue template, export and validate return 409 COMPONENT_OFF; with EFFORT off, an FR row
    changing complexity is an error naming EFFORT (S1).
11. A hidden FR type pasted on a new row is an error; an FR already holding it round-trips (D4).
12. A new FR row with status DELIVERED commits with that status (Q-7).
13. A batch of 2,001 rows is refused at file level (P7).
14. Exported text starting with `=`, `+`, `-` or `@` opens in Excel as text.
15. The weekly check prints rejected and failed import batches of the last 7 days per target (P8).

## 11. Decisions for Ben (the build follows the recommendation and flags it until he answers)
- **Q-1** BR sheet: statement and status only; requirement lines stay on screen. *Recommended: yes.*
- **Q-2** FR interface detail: exported read-only (source and target app), not imported in 1e-a. *Recommended: defer.*
- **Q-3** BR links on FR and issue rows are add-only; removal on screen. *Recommended: yes.*
- **Q-4** Issue raiser must already exist (name + org unit); no "pick or create" in the preview yet. *Recommended: yes.*
- **Q-5** A blank solution cell on an existing FR leaves the tag unchanged (the design's "blank clears" would move its
  effort to Unassigned unseen). *Recommended: unchanged; clearing on screen.*
- **Q-6** Re-uploading a committed file, or a likely duplicate row: warn (passable) or block. *Recommended: warn.*
- **Q-7** A status typed on a new FR or issue row is honoured (not dropped). *Recommended: honour.*
- **Q-8** A closed issue's title and description may be edited by file, as on screen (`update_issue`); its status may
  not. *Recommended: follow the screen.*
- **Q-9** Criterion 106's "10 warnings for 10 FRs without a solution" is superseded by D-52 / criterion 133 (no
  solution warning). *Recommended: yes — record in history.*

## 12. Out of scope
WBS import; requirement-line import (Q-1); interface-detail import (Q-2); creating steps or BRs from Excel; automatic
undo of a batch (P6); the flow file until 1e-b; PDF.

## 13. Build checklist
**Grade 2** — wrong rows reach a client deliverable but are correctable (audited updates, before-values and added links
kept 90 days). Proof: service-level tests per target for every check in §7.0–7.3, the §10 round-trips, one browser
pass per target. Left uncovered on purpose: files not made by VB beyond the file-level checks; two batches committing
over the same rows at once (row lock and row_version, tested in 4a). No migration. Sara before commit. Full suite before
push. Strings via `t()`. Cross-check run: every grid entity is an existing table, every grid function has pseudocode,
every §10 item traces to §7.0–7.3 or §1a.

## 14. Review log
Round 1 (design-auditor, 2026-10-24): P1 (HIGH) duplicates on re-upload → §7.0 warnings, Q-6 · P2 (HIGH) round-trip
fails on frozen / closed / retired / out-of-scope → changed-only rule §7.0, criterion 1 · D1 (HIGH) old export
re-creates a removed link → signed links-at-export · P3 per-row checks vs services → apply order, current-complexity
cell, row_version chaining, dedupe, max_len · P4 status on new rows → Q-7 · P5 links preview → "links added" · P6
reversal → added link ids kept, §1a · P7 size → 2,000-row cap, drift query skipped · P8 maintenance → weekly-check line
· D2 blank solution → Q-5 · D3 raiser → keep-if-unchanged, org unit, pin · D4 hidden codes → picker rule · D5 106 vs 133
→ Q-9 · D6 freeze staleness → message · S1 components → per-row and template/export checks, moved into services ·
S2 AI egress → 1e-b spec. Round 2 re-checks these changes only.
