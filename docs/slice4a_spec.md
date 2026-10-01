# Slice 4a: the import pipeline, first used for Data Entities and Data Fields

**Date:** 2026-10-01 · **Author:** Lilly · **Status:** rev 2 (after design review round 1; Ben's answers of 2026-10-01), for sign-off
**Builds on:** design §7.11 (`services/bulk.py`), §7.12 (`escape_cell`, `enforce_upload_limits`),
§7.12b (body limits, `purge_import_rows`), D-5, Q14, R2-S8, and criteria 31, 32, 38, 39, 40, 47,
75, 111, 138, 147 and 152. Schema: `docs/slice4_schema.md` with S4-1…S4-10, **amended by S4-11**
(§1a, Ben 2026-10-01). Where this file and the design disagree, the design wins.

## 1. Purpose
A consultant downloads a template or an export of a project's data entities and fields, edits it
in Excel (or builds a whole data model there), and uploads it. VB validates every row, shows
what would change, and applies the whole file only when the consultant approves. This is the
**one** import pipeline (VB law 8) that every later import reuses: Issues, BRs, FRs, WBS and the
flow JSON.

## 2. Doctrine
- Playbook rules:
  - no hard delete, except the `import_row` purge (§6.6);
  - audit;
  - numbers are minted at commit only;
  - lookups go through `code_master.resolve`;
  - untrusted text renders as text.
- VB laws 6 and 8.
- §7.11's six properties.

## 3. Keystone grain
`import_row` has one row per staged sheet row (S4-9). One batch holds one uploaded sheet for one
target: `DATA_ENTITY` or `DATA_FIELD`.

## 4. Business Requirement grid

| Function | Entity | Use | Logic → output |
|---|---|---|---|
| `template` | `code_master` | R | Builds an `.xlsx` from the target's column map. The header row carries a **column code** in each header cell's comment, and VB matches columns by that code, never by position or by the translated text. Data-validation lists come from **this project's** resolved codes (47). If a list exceeds Excel's 255-character inline limit, it goes on a hidden lookup sheet |
| `export` | `data_entity` / `data_field` | R | Writes live rows in template shape. Each row carries the business key and a **signed row token** (A-4a-6) in a protected column. A text cell that starts with `=` `+` `-` `@` is written as an explicit string cell with Excel's `quotePrefix` style, so no apostrophe is added to its content (escape S5, symmetric on re-import) |
| `validate` | upload | — | 1. The **raw body** arrives as `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, with the display name in `X-VB-File-Name`. It is not multipart, so nothing is spooled to disk (A-4a-7).<br>2. Ingress cap is 10 MB of body bytes, set by an ordered `ROUTE_CAPS` pattern.<br>3. A **zip pre-pass** decompresses every member in chunks and counts real bytes: 100 MB total, 20 MB for `sharedStrings.xml`.<br>4. openpyxl parses it read-only, with defusedxml hardening and the 5,000-row / 200-column caps.<br>5. At most 2 uploads parse at once; a third gets 429 |
| `validate` | file | — | **File-level checks.** A missing mapped column → 422 naming it. A row token from another project → 422 "this file was exported from another project". A formula cell with no cached value → row error |
| `validate` | `data_entity` | R | **A DE row with a token** must resolve to that same live DE in this project. Otherwise it is an error ("retired or changed since export: re-export"), **never an INSERT** (Q2). A stale `row_version` inside the token → error naming the current values (D2). **A row with no token and no number** is an INSERT; a live DE with that name → error naming its number. A rename onto another live name → error. All values are checked against their column's maximum length |
| `validate` | `data_field` | R | The key is `DE-nnnn/` followed by the name **normalised as the database's live-name index does, `lower(btrim(name))`** (Q8, S4-11). **A row with a token** must resolve to that same live field. A renamed, moved or retired field is an **error, never an INSERT** (Q2). **A row with no token** is an INSERT, unless its key already exists (error: "export first to update"). The parent DE must be live. The type must resolve. `ref_de_number` / `ref_field_name` resolve against live rows **or rows in this same file** (Q7). On a new row, `fk_group` is a **file-local label** per (DE, referenced DE); on an updated row it is the stored number (Q3). Each entity's final name set and PK-ordinal set (live plus file) must stay unique, so a swap is an error, not a mid-commit crash |
| `validate` | each row | — | **Blank clears** a value; `mandatory` blank means "unknown"; a blank `ref_de_number` removes the FK (Q1). A resolving row with no changed value → **MATCH**, which is never written (Q4) |
| `preview` | rows + live data | R | Per row: the verdict, any errors or warnings with their sheet row number, and before/after for every changed field, **computed now** (S4-8). Clears are shown explicitly. The header shows the insert, update, match and error counts |
| `commit` | `import_batch` | U | `FOR UPDATE` the batch. It must be VALIDATED, its `row_version` must match, and it must have no errors. **Full re-validation inside the transaction** (D1): **any row whose fresh verdict differs from its staged one is an error** (a staged UPDATE that would now be an INSERT never slips through). `acknowledged_inserts` must equal the **re-validated** insert count whenever that count is above 0 (R2-P2) |
| `commit` | `data_entity` / `data_field` | C/U | Rows are applied in two passes: (1) entities, then every field **without** its reference; (2) the references, so same-file links resolve (Q7). Everything goes through the services' **no-commit forms**. During the apply, `Session.commit` is made to raise, so no helper can commit partway. Numbers are minted here. **Each UPDATE row's before-values are stored in `import_row.payload.before`** for the 90-day row window (Q5). `committed_target_id` is set, one `IMPORT_COMMITTED` event is written, and there is one commit. A **rule** failure sets REJECTED in a follow-up `UPDATE … WHERE status='VALIDATED'`. An **operational** failure (a deadlock or timeout) leaves the batch VALIDATED, ready to retry (Q9) |
| `purge_import_rows` | `import_row`, `import_batch` | D/U | Rows older than 90 days are deleted. `file_name` becomes `'(purged)'` (Q6). The header keeps who, when and the counts. An uncommitted batch becomes REJECTED. Batches are locked first, `SKIP LOCKED` (S4-9). The purge is audited. It runs as a CLI for now (`python -m scripts.purge_import_rows`) |
| `consistency_check` | `import_batch` | R | Gains `purge_overdue`: batches older than 90 days that still have rows. It shows until a schedule exists, so a forgotten purge is visible |
| review *(manual)* | — | — | The consultant reads the preview, fixes errors in Excel and re-uploads, then types the insert count and commits |

## 5–6. Logical / physical
`import_batch` and `import_row` are as in `docs/slice4_schema.md` (migrations 0019/0020), with
S4-11. That revision needs **no schema change**:
- the token lives in the sheet;
- `payload.before` is inside the existing jsonb;
- the purged `file_name` is a value change.

**Column maps.** Each column has a code, a header, a parser, a maximum length and, where
relevant, a code category.
- **DATA_ENTITY:** `de_number`, `de_name` (200), `description`, `business_owner_note`, `row_token` (protected).
- **DATA_FIELD:** `de_number`, `field_name` (200), `data_type`, `length`, `precision`, `scale`, `mandatory` (Y / N / blank), `pk_position`, `ref_de_number`, `ref_field_name`, `fk_group`, `description`, `row_token` (protected).
- A new field is positioned in sheet order, after the existing fields.

## 7. Function
```
services/xlsx.py   zip_prepass(bytes) · read_rows(bytes, column_map) · write_book(...) — limits,
                   defusedxml, quotePrefix, column codes, a semaphore of 2
services/bulk.py   COLUMN_MAP · template · export · validate · preview · commit · purge_import_rows
                   row_token(project, table, id, row_version) = HMAC-SHA256 with a key derived
                   from JWT_SECRET_KEY + "vb-row-token", compared in constant time
services/data_entity.py   no-commit create/update forms (the routes keep committing)
```
Per-target logic sits in small functions inside `bulk.py`, so a later target adds a map and two
functions and never a second pipeline.

## 8. code_master
`IMPORT_STATUS` is already seeded. `FIELD_DATA_TYPE` drives the template lists and validation.

## 9. API (`/api/v1`, one guard each)

| Method · path | Guard | Notes |
|---|---|---|
| `GET /projects/{id}/bulk/templates/{target}` | `project_ctx(EDITOR)` | `.xlsx`, with a server-generated name |
| `GET /projects/{id}/bulk/{target}/export` | `project_ctx(REVIEWER)` | `.xlsx` |
| `POST /projects/{id}/bulk/{target}/validate` | `project_ctx(EDITOR)` | raw `.xlsx` body + `X-VB-File-Name`; 10 MB of body bytes; 413 / 422 / 429 |
| `GET /bulk/batches/{batch_id}` · `/preview` | `object_guard(ImportBatch, EDITOR)` | |
| `POST /bulk/batches/{batch_id}/commit` | `object_guard(ImportBatch, EDITOR)` | `{row_version, acknowledged_inserts}` |

`target` is `data-entities` or `data-fields`; anything else → 404.

## 10. Acceptance criteria
**Grade 1 for the commit path**: a silent failure here overwrites a colleague's values or writes
across projects. It therefore gets heavy direct proof. A mutation harness is a separate, approved
piece of work. The screen is Grade 3.

1. *(31)* Committing twice applies the batch once; the second call gets 409. Two concurrent
   commits produce one set of rows.
2. *(32, 111)* The preview shows INSERT, UPDATE or MATCH per row, with before/after and the
   clears. Inserts need `acknowledged_inserts`, all-insert batches included.
3. *(39)* Validate a batch, retire its DE, then commit → the batch is rejected; no live field
   remains under a retired DE.
4. *(40)* Export, edit a row in the app, then re-upload → an error naming the current value. The
   batch commits only after a corrected re-upload.
5. **A row with a token whose field was renamed, moved or retired** → an error, never an INSERT.
   The same row going stale between validate and commit → a commit-time row error, and nothing
   applied.
6. **An export from project B uploaded into project A** → 422 "exported from another project".
   An Excel partial sort that shifts the key columns against the token → row errors, not
   overwrites.
7. **A blank description clears; a missing description column → 422**; a formula cell with no
   cached value → a row error.
8. Export then re-import with no edits → every row MATCH, nothing written, no `row_version`
   bumped. A description starting with `-` round-trips unchanged.
9. **A whole model in one file**: 3 new entities, then fields with a composite FK
   (`fk_group` label `a`) and a self-reference. It commits, with every reference resolved and
   one relationship per label.
10. A swap of two field names or two PK positions → a validation error, not a mid-commit crash.
11. A failure **inside a service** on the last row (not at re-validation) → zero rows changed
    and the DE counter unchanged. A helper that tries to commit during the apply raises.
12. An operational failure leaves the batch VALIDATED and a retry succeeds. A rule failure →
    REJECTED, and a racing successful commit is never overwritten to REJECTED.
13. *(75)* A DTD or external-entity declaration in `workbook.xml`, in `sharedStrings.xml` and in
    `sheet1.xml`, each parsed by the service's own call → 422, never resolved and never a 500.
    A zip bomb, or a sharedStrings part over its cap, is refused in the pre-pass. More than
    5,000 rows or 200 columns are refused mid-stream. A third concurrent upload → 429.
14. *(138, 152)* A 50 MB body → 413, and the handler is never invoked. A **chunked** over-cap
    body → 413. Exactly 10 MB of body → accepted. During validate,
    `tempfile.TemporaryFile`/`NamedTemporaryFile` are patched to raise, which proves nothing is
    spooled.
15. A rejected batch burns no `DE-` number. *(47)* The template carries this project's
    `FIELD_DATA_TYPE` overrides.
16. *(147, Q6)* After the purge, the 91-day batch has no rows, its `file_name` reads `(purged)`,
    its header stays and an uncommitted one reads REJECTED. One audit row is written. An 89-day
    batch is untouched. `purge_overdue` lists an overdue batch until it is purged.
17. A commit stores before-values for each UPDATE row in `payload.before`.
18. A REVIEWER can export, but gets 403 on template, validate and commit. A batch in a project
    the user can't see → 404.
19. **On screen:** Data page → Import → target → template or export → upload → errors by sheet
    row → fix → re-upload → preview → type the count → commit → rows listed.

## 11. Assumptions
- **A-4a-1** Entities and fields are separate batches and templates. A field batch may
  reference entities only once they exist. Inside a field batch, fields may reference each other.
- **A-4a-3** An import is merge-only and never retires (§7.11).
- **A-4a-4** `openpyxl` and `defusedxml` are design-named, so they are verified on PyPI and
  installed without a separate ask.
- **A-4a-5** The purge runs as a CLI until deployment; `purge_overdue` makes a missed run
  visible.
- **A-4a-6** The **signed row token** replaces the bare `row_version` column. It is bound to the
  project, table, row id and `row_version`, so a counter match can no longer pass for identity.
- **A-4a-7** Raw-body upload rather than multipart: Starlette spools any multipart file over
  1 MB to disk and offers no per-route control.

## 12. Out of scope
Issue, BR, FR and WBS imports (4b/4c), the flow JSON (4d), retiring through an import, a purge
schedule, and an undo button (the before-values make a manual rebuild possible).

## 13. Build checklist
- **Backend first:** `services/xlsx.py`, `services/bulk.py`, `routers/bulk.py`, and
  `tests/test_bulk_import.py` with one test per criterion. Criterion 14 includes the middleware
  and chunked tests.
- **Frontend:** one `ImportWizard` in `frontend/src/components/`, reused later, opened from the
  Data page, with strings in `en.data.json`.
- **Reviews:** sara before commit, test-runner, then ui-verifier.
- **Worktree:** `slice-4a`, from main **after** 0019/0020 merge.

**Design review:** round 1 on 2026-10-01 (`design-auditor`, 18 findings: 3 HIGH, 7 MEDIUM, 8 LOW).
All 18 are fixed in this revision. Ben approved all 9 recommended answers to its questions
(Q1–Q9), recorded as S4-11.
