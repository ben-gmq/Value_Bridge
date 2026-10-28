# Slice 1e-b — Process-flow file: export and import (`vb-process-flow/2.0`) (spec rev 1, 2026-10-28)

Status: **rev 1 — for design review round 1.** The signed-off design fixes the contract (`VB_design.md` §7.2b, §7.12a;
D-25, D-36, D-38, D-46, D-55; R2-D1, R2-D5, R2-D13, R2-P1…P4; Q5), the one pipeline (§7.11, VB law 8), the routes
(§9: `GET /process-flow-json/schema`, `POST /projects/{id}/bulk/process-flow/validate`, the shared commit) and the
acceptance criteria (§10: 110–114, 118, 123, 129). Parent spec: `docs/slice1e_imports_spec.md` §7.5. Model: `apple`,
2026-10-28 (grain, migration 0080). Ben's five answers of 2026-10-28 are **FI-1…FI-5** (history §3). This spec fixes
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
- **AI egress (S2):** VB calls no AI (A-51). The consultant pastes client content into **Claude or Microsoft Copilot
  under FTC's own accounts only**, after the pack's first step removes personal data (D-36). ASSUMPTION
  (Ben to confirm, decision 1 of the report): the FTC accounts are business plans whose terms exclude training on
  inputs, with the plan's default retention; the prompt pack names this and the consultant's duty to use only them.
- **Maintenance loop:** the weekly check's import line (1e-a, P8) covers `PROCESS_FLOW` with no change. Lilly reads it
  weekly; a flow rejection repeated for one reason becomes a BUGLOG entry and, when it is the AI's fault, a prompt-pack
  edit.

## 2. Doctrine
Playbook §9 items 2, 3, 7, 8, 10, 11; VB law 1, 3, 4, 5, 6, 8; design §7.2b, §7.11, §7.12a. **One deviation from the
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
5. **Names.** A step's normalised name must be free among **all** the anchor's live children (process or not), as
   `assert_name_free` checks at commit; a clash is a step error. A 100th child is a step error (`MAX_SIBLINGS`).
6. **Anchor.** Live, not a process, at level 2–4 (a child at level 5 is the lowest a process may sit) → else 422.
7. **Triggers.** A matched trigger keeps its live kind; a differing kind in the file is a warning. One new name given
   two kinds in the file is an error on its TRIGGER row.
8. **External parties.** A flow names its party by the file-local `key` of an `external_entities` entry; that entry
   matches by `ext_number`, else by live name, else is created (kind from `EXTERNAL_ENTITY_KIND`). A matched party's
   name and kind are never updated; a differing kind is a warning. A flow's `data_entity` may be a DE number or a name
   (created), as inputs and outputs.
9. **Replace mode (FI-4).** The file's I/O set for a step is its `inputs` ∪ `outputs` ∪ the I/O its own external flows
   imply. Only live I/O and trigger links of the file's **resolved** steps, outside that set, **and only for lists the
   step states** (rule 2), are staged RETIRE — or KEPT with a warning naming the dependent (a BR CRUD or an external
   flow). Steps, BRs, performers, parties, external flows, DEs and catalogue triggers are never retired.
10. **Live links are MATCH.** A link already live is staged MATCH and its writer never called (`trigger.link` and
    `link_external_flow` refuse a live link with 409). A retired link is restored. A restored external flow keeps its
    old label and note.

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
  `backend/assets/flow_prompt_pack.md`): D-36's two services first, then the personal-data removal step, then the
  rules of §4 phrased for an AI.
- **`export(project_id, anchor_id)`** — the anchor's direct process children in order: per step `key` (`S1`…),
  `br_number` (to-be), `hier_code`, `row_version`, name, `data_processing_desc` as `description`, performer, triggers,
  inputs, outputs, external flows; the parties those flows name, with their `ext_number`. **Every list is written,
  empty as `[]`** (so an export re-imported in replace mode retires nothing). Guard: VIEW on the anchor's DFD component.
- **`validate(...)`** — §7.2b's pseudo-code with §4 above. Its own staging writer fills `source_path`, `local_key`,
  `source_ref` (the sheet writer's `_rows_of` is shaped for sheet rows), sharing the pipeline's batch, counts and lock.
- **`commit(batch_id, confirm)`** — §7.2b's order, one transaction. **Each writer gets a no-commit form** (as 1e-a
  did): `create_node`, `update_node`, `set_performer`, `create_trigger`, `trigger.link`, `create_party`,
  `link_external_flow`, `ensure_step_io`, `create_entity`, `create_br`. The screen paths keep their commit.
- **Screen.** The process chart's anchor node gets "Export flow" and "Import flow" (the existing `ImportWizard`, with a
  mode picker and the RETIRE / KEPT lists and the replace acknowledgement). Strings in `en.data.json`.

## 8. code_master
No new list. A party's kind is `EXTERNAL_ENTITY_KIND`, resolved through `code_master.resolve`; a trigger's kind
is `TIME|EVENT`, checked by `trigger._check` as on screen. Branching on behaviour, never a code (law 5).

## 9. API
As design §9. Export is `GET /projects/{id}/bfc-nodes/{node_id}/process-flow-json` (object_guard VIEW, the anchor's
DFD component) — ASSUMPTION: the design names the function, not the path; this path follows the BFC routes.

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

## 11. Decisions — FI-1…FI-5 accepted (Ben, 2026-10-28: "yes to all"); recorded in history §3.

## 12. Build order and pieces
0. **Migration 0080** on `main`, its own commit (Sara before commit).
1. **Piece (a): export + merge.** Schema download and prompt pack; export; validate/commit for STEP, PERFORMER,
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
*(design review round 1 to follow)*
