# Slice 1e-b — Process-flow file: export and import (`vb-process-flow/2.0`) (spec rev 2, 2026-10-28)

Status: **rev 2 — design review round 1 answered (11 findings: 2 HIGH, 5 MEDIUM, 4 LOW, all taken; §15); Ben's
FI-6…FI-10 folded in. Round 2 of 2 done (§15) — to code.** The signed-off design fixes the contract (`VB_design.md` §7.2b, §7.12a;
D-25, D-36, D-38, D-46, D-55; R2-D1, R2-D5, R2-D13, R2-P1…P4; Q5), the one pipeline (§7.11, VB law 8), the routes
(§9: `GET /process-flow-json/schema`, `POST /projects/{id}/bulk/process-flow/validate`, the shared commit) and the
acceptance criteria (§10: 110–114, 118, 123, 129). Parent spec: `docs/slice1e_imports_spec.md` §7.5. Model: `apple`,
2026-10-28 (grain, migration 0080). Ben's answers of 2026-10-28 are **FI-1…FI-10** (history §3). This spec fixes
what the design leaves to the slice: the 2.0 schema, the staging grain, the migration, the service gaps, the split into
two pieces, and the AI-conversion egress row.

## 1. Purpose
Let a consultant take one parent node's process flow out of VB as a file, edit it (by hand, or turn a slide or a Visio
diagram into one with an approved AI), and bring it back safely — new steps created, matched steps updated, nothing
retired unless replace mode is chosen and the retirements are acknowledged.

## 1a. Interface
- **Input:** a `vb-process-flow/2.0` JSON file (≤ 2 MB), either an export from VB or produced by the AI conversion
  prompt pack; the **anchor node and mode are chosen on screen** (R2-P3).
- **Output:** under the anchor — new and updated process steps (name, description, performer), new BRs for new to-be
  steps, step inputs/outputs, trigger links, external parties and flows; new data entities and catalogue triggers.
  Replace mode also retires the omitted trigger links and step inputs/outputs of the file's steps. One
  `IMPORT_COMMITTED` audit event per batch. Export writes the same format.
- **Validation:** file level first (size, depth, NaN, duplicate keys, the 2.0 schema, format version, anchor live,
  non-process and at level 2–4, `parent` and `mode` equal to the route's) → 422, nothing staged. Then per object
  (§4): errors block the batch, warnings never do. Commit re-validates every row under the batch lock, re-computes the
  RETIRE set (differs → 409), and refuses unless inserts and retirements are acknowledged by count.
- **Archive:** the file is never stored (R2-S8). `import_row` keeps each object's values, verdict, `source_ref`,
  before-values and the ids it wrote for 90 days (Q14); the batch header and audit event stay.
- **AI egress (S2, FI-6):** VB calls no AI (A-51). **Service: Claude Enterprise, under FTC's own account — the only
  one; no Copilot, no personal account** (Ben, 2026-10-28). **The consultant removes personal data before pasting
  anything**; the pack never asks the AI to do it. **Confidentiality:** everything in this tool is treated as
  confidential, much of it under client NDAs (Ben, 2026-10-23), until Ben says otherwise. **Vendor terms — checked (FI-10):**
  Ben checked the Claude Enterprise data terms himself on 2026-10-28; the source is his own check (no vendor document
  quoted). VB may serve the prompt pack **for Claude Enterprise only**; any other service stays out of policy.

  | Service | What is sent | Confidential? | Protection | Vendor terms (source, date) | Default |
  |---|---|---|---|---|---|
  | VB | nothing (A-51) | — | — | — | — |
  | Claude Enterprise (FTC account), used by the consultant outside VB | the client's process diagram content; for an edited export, BR numbers and step text | yes | FTC account only; personal data removed by the consultant first | **checked by Ben, 2026-10-28 — his own check, no vendor document quoted (FI-10)** | the only service |
- **Maintenance loop:** the weekly check's import line (1e-a, P8) covers `PROCESS_FLOW` with no change. Lilly reads it
  weekly; a flow rejection repeated for one reason becomes a BUGLOG entry and, when it is the AI's fault, a prompt-pack
  edit.

## 2. Doctrine
Playbook §9 items 2, 3, 7, 8, 10, 11; VB law 1, 3, 4, 5, 6, 8; design §7.2b, §7.11, §7.12a. **One change to the
design's pseudo-code, not its contract:** the file is checked by a strict Pydantic v2 model (`extra='forbid'`), and the
published JSON Schema is generated from that model (`model_json_schema()`), instead of the `jsonschema` package — one
definition, no new dependency. §7.2b's pseudo-code line is reworded in this commit.

## 3. Keystone grain
`import_row` — **one row per flow-file object of one upload** (apple §1). No new table or column.

| row_kind | One row per… | Verdicts | local_key | business_key | Same object on a second upload |
|---|---|---|---|---|---|
| STEP | file step `/steps/i` | INSERT · UPDATE · MATCH | `key` | `br_number`, else normalised name | BR number (to-be); else normalised name among the anchor's live children |
| PERFORMER *(new)* | step with a `performer` key, `/steps/i/performer` | MATCH only | — | `S1/<kind>:<CODE>` or `S1/AI` | live code; a change shows on the STEP row's UPDATE |
| TRIGGER *(new)* | distinct normalised trigger name, at its first occurrence | INSERT · MATCH | — | normalised name | `uq_ptrg_name_live` |
| STEP_TRIGGER *(new)* | step × trigger, `/steps/i/triggers/j`; RETIRE rows have no path | INSERT · MATCH · RETIRE | — | `S1/<trigger name>` | `uq_bntr_grain` (live or retired → restore) |
| DATA_ENTITY | distinct DE reference, at its first occurrence | INSERT · MATCH | — | `DE-nnnn`, or the normalised name | DE number (`^DE-\d+$` is always a number); else `uq_de_name_live` |
| STEP_IO | step × DE × direction, from `inputs`, `outputs` or implied by an external flow; RETIRE / KEPT have no path | INSERT · MATCH · RETIRE · KEPT | — | `S1/<I\|O>/<DE ref>` | `uq_bnde_grain` (restore on re-link) |
| EXTERNAL_ENTITY | `/external_entities/k` | INSERT · MATCH | `key` | `ext_number`, else normalised name | `ext_number`; else `uq_ext_name_live` |
| EXTERNAL_FLOW | `/steps/i/external_flows/k` | INSERT · MATCH | — | `S1/X1/<dir>/<DE or ->` | `uq_bnef_grain` |

The parent is not a row: `parent.hier_code` and `mode` are checked against the batch's anchor and mode (422 on a
mismatch). A new to-be step's BR is minted by `create_br` at commit and its number written to the STEP row's payload.

## 4. Business rules (the 2.0 file → the database)
The ten rules of §7.2b stand, as rewritten in this commit for FI-1…FI-4. The slice adds:

1. **Schema.** `format` const `vb-process-flow/2.0` (a 1.0 file → "re-export from VB"); `mode` `merge|replace`,
   default merge; `steps` ≥ 1; every object `additionalProperties: false` (so `edges` / `lanes` are refused, D-38);
   `key` `^[A-Za-z0-9_-]{1,40}$`, unique in the file; `name` ≤ 200; `source_ref` ≤ 200; `performer` is `oneOf`
   `{kind: ORG_UNIT|ORG_ROLE|APPLICATION, code}` · `{kind: AI, label}` · `null`; `triggers[].kind` required.
2. **Present, absent, empty (FI-1).** A step that **leaves out** `triggers`, `inputs`, `outputs` or `external_flows`
   says nothing about them: they are left as they are, in both modes. Only an explicit `[]` means "none", and only
   in replace mode does that retire anything.
3. **Performer (FI-2).** A `performer` key that is **absent**, or names an **unknown or inactive** code, keeps the
   step's current performer, with a warning (a new step stays blank). Only `"performer": null` clears it, shown
   before/after. A known performer replaces the current one (D-46); RACI is never touched.
4. **Stale step (FI-3).** A `row_version` that is not the node's current one is an **error on that step only**,
   naming its current name, performer and description (criterion 123). The rest of the file still stages; the preview
   lists every stale step. A batch with any error cannot commit, as for every import.
5. **Names and scope (FI-9).** A file updates **only the anchor's direct children**: a `br_number` whose process
   sits anywhere else is a step error. A step's normalised name must be free among **all** the anchor's live
   children (process or not), as `assert_name_free` checks at commit; a clash is a step error. A 100th child is a
   step error (`MAX_SIBLINGS`).
6. **Anchor.** Live, not a process, at level 2–4 (a child at level 5 is the lowest a process may sit) → else 422.
7. **Triggers.** A matched trigger keeps its live kind; a differing kind in the file is a warning. One new name given
   two kinds in the file is an error on its TRIGGER row.
8. **External parties.** A flow names its party by the file-local `key` of an `external_entities` entry; that entry
   matches by `ext_number`, else by live name, else is created (kind from `EXTERNAL_ENTITY_KIND`). A matched party's
   name and kind are never updated; a differing kind is a warning. A flow's `data_entity` may be a DE number or a name
   (created), as inputs and outputs. An `ext_number` must belong to this project, else an error.
9. **Replace mode (FI-4).** The file's I/O set for a step is its `inputs` ∪ `outputs` ∪ the I/O its own external flows
   imply. Only live I/O and trigger links of the file's **resolved** steps, outside that set, **and only for lists the
   step states** (rule 2), are staged RETIRE — or KEPT with a warning naming the dependent (a BR CRUD or an external
   flow). Steps, BRs, performers, parties, external flows, DEs and catalogue triggers are never retired.
10. **Live links are MATCH.** A link already live is staged MATCH and its writer never called (`trigger.link` and
    `link_external_flow` refuse a live link with 409). A retired link is restored. A restored external flow keeps its
    old label and note.

11. **A BR number needs its version (D1).** A step with a `br_number` and no `row_version` is a step error: "BR
    numbers come only from a VB export — remove it or re-export". The pack tells the AI to write `br_number`,
    `hier_code` and `row_version` as `null` on every step it makes.
12. **Description (FI-8).** A step that leaves out `description` keeps the current text; only an explicit `""` or
    `null` clears it, shown before/after. `name` is required; `description` is optional.
13. **One cleaning, one match (D4).** Every name and reference in the file is cleaned as 1e-a cleans a cell
    (Unicode whitespace and invisible edge characters stripped, inner runs of space collapsed), then matched with
    `bfc.normalise_name` — for steps, data entities, triggers and parties alike. STEP_IO and STEP_TRIGGER are
    de-duplicated on the **resolved** (step, entity or trigger, direction) before staging, keeping the first
    pointer; a repeat is a warning, never a second row. So `DE-0007` and its own name in one list are one link,
    and an input that an external flow also implies is one STEP_IO row.
14. **Version pinned at validate (D2).** Every UPDATE step stores the matched node id and its `row_version` in its
    payload, whether or not the file carried one. At commit a different `row_version` is `RESOLVED_CHANGED` — the
    batch is rejected and nothing is written, so an edit made after the preview is never overwritten.
15. **Updates are confirmed and kept (FI-7, P1).** Commit is refused unless `acknowledged_updates` equals the
    number of UPDATE steps. Each updated step's before name and description go into the `IMPORT_COMMITTED` audit
    event, which is never purged.
16. **What the file did not name (P2).** The preview lists every live process child of the anchor that no file step
    matched, as "not in this file — kept as is". A new step whose cleaned name is close to one of those (same
    tokens in another order, or one token added or dropped) gets a `POSSIBLE_DUPLICATE` warning naming it.
17. **One row_version per call (D6).** Within a step's commit, each service call takes the step's current
    `row_version` after the previous call (1e-a §7.0 P3d), so a step changing description and performer commits.

## 5–6. Logical and physical design
No new table, no new column, no baseline impact (law 2: `import_batch` / `import_row` are not shadowed). Resolved ids,
minted numbers, implied I/O and KEPT dependents live in `payload`, as in 1e-a.

**Migration 0080 (`import_row` constraints; one commit, on `main`, before any 1e-b code; FI-5):**

| Constraint | Change |
|---|---|
| `ck_ir_row_kind` | + `PERFORMER`, `TRIGGER`, `STEP_TRIGGER` |
| `ck_ir_kind_fits_target` (flow list) | + the same three; `STEP_ROLE`, `FLOW_EDGE`, `LANE` stay (S7 Q-32) |
| `ck_ir_retire_kinds` | + `STEP_TRIGGER` |
| `ck_ir_lane_match` → `ck_ir_match_only` | `row_kind NOT IN ('LANE','PERFORMER') OR verdict = 'MATCH'` |
| `ck_ir_target_kind` | `committed_target_id IS NULL OR row_kind NOT IN ('LANE','PERFORMER')` (a performer may be one of three tables; its id lives in the payload) |
| `uq_ir_source_path` | `(import_batch_id, source_path)` → `(import_batch_id, row_kind, source_path)` — a new DE and the input that names it share one pointer |

`models/import_staging.py` (`ROW_KINDS`, `FLOW_ROW_KINDS`) in the same commit. **Reversible, non-destructive:** the
upgrade only widens; the downgrade counts rows of the new kinds or cross-kind duplicate paths and **refuses with a
message**, deleting nothing (Q-21 pattern). Brief lock on a small staging table.

## 7. Functions (`services/flow_import.py`, on the `bulk` pipeline)
- **`schema()`** — the generated JSON Schema, the worked example of §7.2b, and the prompt pack (Markdown, from
  `backend/assets/flow_prompt_pack.md`): first, to the consultant, "Claude Enterprise under FTC's account only" and
  "remove personal data before you paste anything" (FI-6); then the rules of §4 phrased for an AI, including
  rule 11. The pack is served for Claude Enterprise only, whose terms §1a records (FI-10).
- **`export(project_id, anchor_id)`** — the anchor's direct process children in order: per step `key` (`S1`…),
  `br_number` (to-be), `hier_code`, `row_version`, name, `data_processing_desc` as `description`, performer, triggers,
  inputs, outputs, external flows; the parties those flows name, with their `ext_number`. **Every list is written,
  empty as `[]`** (so an export re-imported in replace mode retires nothing). Guard: VIEW on the anchor's DFD component.
- **`validate(...)`** — §7.2b's pseudo-code with §4 above. Its own staging writer fills `source_path`, `local_key`,
  `source_ref` (the sheet writer's `_rows_of` is shaped for sheet rows), sharing the pipeline's batch, counts and lock.
- **Component (P3).** The component is the anchor's chart — `TO_BE_DFD` for a to-be anchor, `AS_IS` for an as-is
  one — derived from `batch.anchor` at both validate and commit, never a fixed value on the Target.
- **Pairing at commit (D5).** A re-checked row is paired with its staged row by `(row_kind, source_path)`, and a
  RETIRE or KEPT row by `payload.target`; never by `sheet_row_no`, which is null on every flow row. The shared
  commit takes `acknowledged_retires` and `acknowledged_updates` (flow only), and the audit carries the real
  `retire_count`.
- **`commit(batch_id, confirm)`** — §7.2b's order, one transaction. **Each writer gets a no-commit form** (as 1e-a
  did): `create_node`, `update_node`, `set_performer`, `create_trigger`, `trigger.link`, `create_party`,
  `link_external_flow`, `ensure_step_io`, `create_entity`, `create_br`. The screen paths keep their commit.
- **Screen.** The process chart's anchor node gets "Export flow" and "Import flow" (the existing `ImportWizard`, with a
  mode picker and the RETIRE / KEPT lists and the replace acknowledgement). Strings in `en.data.json`.

## 8. code_master
No new list. A party's kind is `EXTERNAL_ENTITY_KIND`, resolved through `code_master.resolve`; a trigger's kind
is `TIME|EVENT`, checked by `trigger._check` as on screen. Branching on behaviour, never a code (law 5).

## 9. API
As design §9. Export is `GET /bfc-nodes/{id}/process-flow-json` (object_guard VIEW, as every BFC object route; the
anchor's DFD component checked in `flow_import.check_anchor`, since a guard's component gates writes only) — the
design names the function, not the path. Strings for the export dialog sit with the DFD screen, in `en.processes.json`.

## 10. Acceptance (1e-b)
Design criteria **110, 111, 112, 113, 114, 118, 123, 129**, plus:
1. Export a flow and re-import it unchanged, merge then replace: 0 inserts, 0 updates, 0 retirements both times.
2. (FI-1) Replace, a step with no `triggers` key keeps its three trigger links; the same step with `"triggers": []`
   stages three RETIRE rows.
3. (FI-2) A step with an unknown performer code keeps performer X and warns; `"performer": null` clears it, shown
   before/after.
4. (FI-3) Two of five steps stale: two step errors, both named in the preview; the other three stage; commit refused.
5. (FI-4) Replace, an output named only by the step's own outbound external flow is MATCH, not RETIRE.
6. (FI-5) A new DE named in `/steps/0/inputs/0` stages a DATA_ENTITY and a STEP_IO row at that one pointer.
7. A step named like a live non-process child of the anchor is a step error at validate, never a 409 at commit.
8. Every row that validates clean commits (property test over generated files, as 1e-a N1).
9. A file with `edges` or `lanes`, or `format` 1.0, is 422 with nothing staged.
10. (D1) A step with `br_number` BR-0012 and `row_version` null is a step error; BR-0012's step is unchanged.
11. (FI-9) A `br_number` whose process is a grandchild of the anchor is a step error.
12. (FI-8) A matched step with no `description` key keeps its text; `"description": ""` clears it, shown before/after.
13. (D4) `"Sales order\u00a0"` matches the live "Sales order" (no new DE); `DE-0007` and DE-0007's name in one
    `inputs` list stage one STEP_IO row and a warning.
14. (D2) A colleague edits a matched step after the preview: commit is rejected, the colleague's text stays.
15. (FI-7) Three updated steps: commit refused until `acknowledged_updates = 3`; the audit event holds all three
    before-texts.
16. (P2) A live step "Check credit" and a file step "Check customer credit": the preview lists "Check credit" as
    not in the file and warns `POSSIBLE_DUPLICATE` on the new one.
17. (P3) With `AS_IS` switched off, an as-is anchor's batch is refused at validate and at commit with 409
    COMPONENT_OFF.

## 11. Decisions — FI-1…FI-10 accepted (Ben, 2026-10-28); recorded in history §3. FI-10 closes the Claude
Enterprise vendor terms (§1a). Nothing open.

## 12. Build order and pieces
0. **Migration 0080** on `main`, its own commit (Sara before commit).
1. **Piece (a): export + merge.** Schema download (schema, example and the pack, for Claude Enterprise only — FI-10); export; validate/commit for STEP, PERFORMER,
   TRIGGER, STEP_TRIGGER, DATA_ENTITY, STEP_IO in merge mode. External parties and flows in the file are validated and
   staged MATCH when already live; a **new** party or flow is a row error "added in a later release — add it on
   screen", so an exported file always round-trips. Replace is refused (422) and hidden in the picker.
2. **Piece (b): outside parties and flows + replace.** EXTERNAL_ENTITY / EXTERNAL_FLOW inserts and restores; replace
   mode with RETIRE / KEPT, the in-lock re-computation and the acknowledgement.

Each piece: Sara before commit, its direct tests, one browser pass, full suite before merge.

## 13. Build checklist
**Grade 2** — a wrong flow reaches a client deliverable, and replace mode soft-retires links, but every change is
audited and restorable (soft delete, before-values 90 days). Proof: service tests for every rule in §4 and every §10
item; the property test (§10.8); one browser pass per piece. **Left uncovered on purpose:** files not made by VB or the
pack beyond the schema checks; two batches over one anchor at once (lock and `row_version`, tested in 4a); AI output
quality (the human reads the preview). No harness (not money, access or destruction).

## 14. Out of scope
Edges and lanes (D-38); RACI by file; creating org units, roles or applications from a file; updating an existing
party's name or kind; automatic undo; calling an AI from VB.

## 15. Review log
Round 1 (design-auditor, 2026-10-28) — 11 findings, all taken:
- **D1** (HIGH) a BR number with no version rewrote the wrong step → rule 11.
- **S1** (HIGH) client content to an AI vendor with unknown terms → FI-6, §1a (terms open; the pack waits for them).
- **P1** (MEDIUM) step text overwritten unconfirmed and lost after 90 days → FI-7, rule 15.
- **P2** (MEDIUM) a reworded step duplicates silently → rule 16.
- **D2** (MEDIUM) an edit after preview overwritten → rule 14.
- **D3** (MEDIUM) missing description undefined → FI-8, rule 12.
- **D4** (MEDIUM) two cleanings, double-counted links → rule 13.
- **P3** (LOW) component fixed on the Target → §7 Component.
- **D5** (LOW) commit pairing by sheet row → §7 Pairing.
- **D6** (LOW) row_version between two calls on one step → rule 17.
- **D7** (LOW) a deeper BR match name-checked against the wrong parent → FI-9, rule 5.

Round 2 re-checks these changes only, and is the last.

Round 2 (final, 2026-10-28): 10 of 11 closed; S1 open by Ben's ruling (vendor terms unchecked). Nothing structural.
Taken into the build and tracked against the running code from here:
- **N1** (MEDIUM) withholding the pack withholds its safety rules too → from piece (a) the import dialog and schema
  download state "no client content into any AI until the Claude Enterprise terms are recorded"; the pack asset is
  committed only together with §1a's terms row. Own BUGLOG id. **Satisfied for Claude Enterprise only** by FI-10
  (terms recorded 2026-10-28): the pack ships in piece (a) naming that one service; the warning stays for any other.
- **N2** (LOW) a cleaned name matching two live records → row error naming both. VB-005 line.
- Audit size: one 500-step test of the `IMPORT_COMMITTED` before-text; one event per step if it chokes.
- Text: "kept permanently" means until the project is purged (`purge_run`).
