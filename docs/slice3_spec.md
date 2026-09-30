# Slice 3 — DFD, ERD and Mermaid export

**Date:** 2026-09-30 · **Author:** Lilly · **Status:** draft for Ben's sign-off
**Builds on:** `docs/VB_design.md` (signed off 2026-09-28) — §4.1a, §4.3, §7.2a, §7.4, §7.14,
§14.6, criteria 88, 94, 107–109, 137. This file carves the slice and settles only what the
design leaves open. **Where the two disagree, the design wins** and this file is wrong.

## 1. Purpose
Give a consultant the two remaining generated diagrams — the DFD of a chart branch and the
logical ERD of the project or one subject area — on the one shared canvas, plus Mermaid text
of all three diagrams for documents.

## 2. Playbook / doctrine references
`~/.claude/ftc-playbook.md` §9.3 (code_master — nothing new), §9.10 (one owner per rule),
§14 UI patterns; VB law 5, 8 and 9 (`CLAUDE.md`); design §6.6 (roles — no new grant), §14.5
(no `innerHTML`), §14.6 (canvas build rules). **No new deviation.** A-52 (layout is
presentation, not baselined) already covers `diagram_layout`.

## 3. The keystone grain
Nothing new is stored. The slice reads two existing tables and writes one:
- **`bfc_node_data_entity`** — one row per (process step × data entity × direction). The DFD
  is this table drawn without sequence (D-24, D-31).
- **`data_field`** — one row per logical field in one data entity. A **relationship** is the
  set of a DE's active FK fields sharing `(ref_data_entity_id, fk_group_no)` (§5.3 DATA_FIELD).
  The ERD is these groups drawn.
- **`diagram_layout`** (written) — one row per (project × diagram type × scope × object). DFD
  and ERD use the `DFD` and `ERD` types it already allows (S2-6).

## 4. Business Requirement — the grid

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `generate_dfd` | `bfc_node` | R | active process descendants of a parent node (by `hier_code` prefix) → the DFD's processes; a step → 422; a retired node → 409 |
| `generate_dfd` | `bfc_node_data_entity` | R | one flow per active row: `I` store → step, `O` step → store, labelled with the DE name. An `I`/`O` row that an active external flow names with the same DE is drawn **from/to the party instead**; the store is still drawn (§5.3 BFC_NODE_EXTERNAL_FLOW) |
| `generate_dfd` | `bfc_node_external_flow` | R | one party ↔ step flow per active row, labelled with **the DE name, else `flow_label`** (design: "labelled with the DE"; §5.3 keeps `flow_label` for an exchange with no DE), else blank |
| `generate_dfd` | `data_entity` | R | each DE in any in-scope I/O row → one store (cylinder) |
| `generate_dfd` | `external_entity` | R | each party in any in-scope external flow → one square box |
| `generate_dfd` | `bfc_node_data_entity` (project-wide) | R | **cross-area** (design §4.1a, "read in one L1 area and written in another"): with W = the L1 areas holding an active `O` row for the DE and R = those holding an active `I` row, **both counted across the whole project**, the store is cross-area iff `∃ w∈W, r∈R : w ≠ r`. Written but never read → not cross-area. Written and read in both 01 and 02 → cross-area. See A-S3-2 |
| `generate_dfd` | `diagram_layout` | R | saved positions for `('DFD', scope node)` |
| `generate_erd` | `data_entity` | R | active DEs in the project; with a subject area, only those in the active I/O of a process under that node |
| `generate_erd` | `data_field` | R | active fields per DE: PK rows by `pk_ordinal`, then FK rows, then attributes, the last two by `seq_no` (the consultant's order, as on the data page). Per relationship group → `parent_cardinality` `1` if every field in the group `is_mandatory IS TRUE`, else `0..1`; `child_cardinality` `1` if the group's field set = the DE's PK field set, else `many`; `identifying` if every FK field in the group is a PK field. `warnings`: `NO_KEY` when the DE has no PK field |
| `generate_erd` | `data_field` → out-of-scope parent | R | an FK group whose parent is outside the subject area → `outside_refs` (a stub labelled with the parent's `de_number` and name). A retired parent cannot occur: the active FK field blocks the retire (`fk_df_ref_entity`, `lifecycle.active_dependents`). The service still returns it as a `retired` stub rather than crashing (A-S3-4) |
| `generate_erd` | `diagram_layout` | R | saved positions for `('ERD', scope)`, scope = the subject-area node or `project` |
| `save_layout` / `reset_layout` | `diagram_layout` | C/U/D | unchanged Slice 2 routes, now called with `DFD` and `ERD`. `is_collapsed` carries the ERD's "+N more" |
| `export_process_flow` · `export_dfd` · `export_erd` | — (the `generate_*` output) | R | the same graph as Mermaid text; node ids generated (`s{id}`, `d{id}`, `x{id}`), **every label through `render.escape_mermaid()`** (R2-S7) |
| review the diagram *(manual)* | — | — | the consultant compares the DFD with the process flow of the same branch, and the ERD with the data list. They render one set of rows, **with one expected difference**: an I/O row that an external flow covers shows as party → step on the DFD, while the process flow still shows the store. Any other disagreement is a defect. A service test proves the invariant (criterion 5a) |
| paste into a deck *(manual)* | — | — | the consultant copies the Mermaid text into a document. PNG/SVG is out of scope (§12) |

## 5. Logical design
**Not applicable: no entity, attribute or relationship changes.** The logical model is design
§5.3 as made physical by `docs/slice1_schema.md` and `docs/slice2_schema.md`. `apple` is not
re-engaged. The one gap the design names, a **relationship role name** ("ship to", "bill to"),
stays unmodelled. The ERD labels a group with its FK field names instead (A-S3-3).

## 6. Physical design
**No migration.** Every table read is NEEDS-NO-CHANGES. The two queries that need an index
already have one: `data_field (data_entity_id, ref_data_entity_id, fk_group_no) WHERE
is_foreign_key` (design §6.3) and the `uq_dl_object` natural key. `vb_app` grants unchanged.

## 7. Function

### Piece 0 — shared canvas debts (frontend only, lands on `main` first)
Three open VB-005 lines all sit in the shared canvas. Paying them before 3a/3b fork keeps the
two branches from each writing its own version.
```
canvas/layout.js  arrange(autoNodes, pinned):           # sara L7, §14.6
    ELK lays out everything; pinned nodes return to saved x/y;
    placed = pinned boxes; for each unpinned node in ELK order:
        while it overlaps ANY box in `placed` (+ spacing): move it past that box
        — erd / dfd: down the column;  flow: RIGHT within its own lane band, never
          across a band edge (a box in another lane reads as another role's step)
        placed += it                      # bounded: each move clears one box
    Auto-arrange and the push save nothing. Only a drag end saves (§14.6), so arranging never pins
canvas/edges.jsx  LabelledEdge: label omitted when zoom < LOW_ZOOM (an edge has no handles to keep)   # sara L8
app/useCanEdit.js  useCanEdit() -> bool                                   # sara LOW-3, L5
    from /auth/me as the server already resolved it, never by matching grant ids to the
    project in the browser: scope PLATFORM_ADMIN → true; PROJECT / PROGRAM →
    project_role_code in (OWNER, EDITOR); NONE → false. One grant per user (D-32), so the
    user's one role applies to every project they can open
    FlowPage + step panel: no drag, draw, reconnect or Reset for a REVIEWER; step panel hides
    add / edit / remove. The server still refuses; this is presentation only.
```

### 3a — `services/process_flow.generate_dfd(db, node)` (beside `generate_process_flow`)
```
same guards as generate_process_flow: retired → 409, is_process → 422
steps = _steps_under(node);  ids = step ids
io   = active BFC_NODE_DATA_ENTITY for ids
ext  = active BFC_NODE_EXTERNAL_FLOW for ids
covered = {(bfc_node_id, data_entity_id, direction) for x in ext if x.data_entity_id}
flows = [ {kind:'STORE', step, store, direction, label: de_name}
            for r in io if (r.step, r.de, r.dir) not in covered ]
      + [ {kind:'EXTERNAL', step, external, direction, data_entity_id, label: de_name or flow_label}
            for x in ext ]
cross_area = { de in stores : W = L1 areas of active 'O' rows for de (whole project, active steps)
                              R = L1 areas of active 'I' rows for de (same)
                              any(w != r for w in W for r in R) }
return {scope, processes, stores (all DEs in io, plus DEs named by ext), externals,
        flows, cross_area (DE ids), layout: positions('DFD', node)}
# no BFC_NODE_FLOW read. No sequence.
```
Route `GET /bfc-nodes/{id}/dfd` — `object_guard(BfcNode, REVIEWER)`.
Screen `/p/{p}/processes/{nodeId}/dfd` (`links.dfd`), reached by a **Process flow / Data
flow** toggle on the flow page and a "Data flow" link in the node panel. `<ModelCanvas
kind="dfd">`: steps as rounded boxes, stores as cylinders, parties as heavy-border squares,
cross-area stores badged. Drag saves on drag end (Slice 2 path). Auto-arrange and Reset. **No
editing on the DFD.** Clicking a step opens it in the chart, where its I/O is edited. **Table
view**: one row per flow (from, to, data, kind).

### 3b — `services/data_entity.generate_erd(db, project_id, subject_area_node_id=None)`
```
entities = active DE in project
if subject_area_node_id:                       # any active node in the project, else 404
    area_steps = [node] if node.is_process else _steps_under(node)   # the helper excludes node itself
    area = DEs in active I/O of area_steps
    entities = entities ∩ area
fields = active DATA_FIELD of those entities
for each entity: fields ordered PK (pk_ordinal) → FK (seq_no) → attribute (seq_no);
                 warnings = ['NO_KEY'] if no PK field
groups = fields where is_foreign_key, grouped by (data_entity_id, ref_data_entity_id, fk_group_no)
for g in groups:
    rel = {child, parent, fk_group_no, via_field_ids (+ ref_data_field_id each),
           label: ', '.join(field_name),
           parent_cardinality: '1' if all(f.is_mandatory is True) else '0..1',
           child_cardinality:  '1' if set(g) == pk_set(child) and pk_set else 'many',
           identifying: all(f.is_primary_key for f in g)}
    parent active and in scope      → relationships
    parent active, outside scope    → outside_refs (stub: de_number, de_name)
    parent retired                  → outside_refs with retired: true
return {scope_key, entities, relationships, outside_refs,
        layout: positions('ERD', subject_area_node_id or None)}
```
Route `GET /projects/{id}/erd?subject_area={bfc_node_id}` — `project_ctx(REVIEWER)`.
Screen `/p/{p}/data/diagram?area={nodeId}` (`links.erd`), reached from a "Diagram" button on
the data list. It has a subject-area picker (the chart tree, "Whole project" first).
`<ModelCanvas kind="erd">` entity card per §7.14: teal header with `DE-0007` and name, PK rows
(key icon, bold), FK rows (link icon + parent name), attributes. More than 8 attributes
collapse to "+N more" (saved as `collapsed`). Hovering a field shows its description, type and
mandatory flag. Handles are `{s|t}-{L|R}-{fieldId}` and never change (§14.6). A collapsed card
stacks its key handles on the summary row. Crow's-foot SVG markers; solid = identifying,
dashed = not. Stubs are short labelled edges to a ghost box. The `NO_KEY` badge shows on the
card. Click highlights neighbours and dims the rest; double-click opens the entity page.
Minimap, fit, search-to-focus. **Table view**: one row per relationship (child, fields,
parent, cardinality).

**Edge landing (fixed now, because handle ids never change).** Every card also has one
entity-level target handle `t-L-entity`. A relationship field lands on its parent's row handle
`t-L-{ref_data_field_id}` only when `ref_data_field_id` is set **and** that row is a key row
(which stays rendered when the card collapses). Otherwise it lands on `t-L-entity`: a null
parent field is the normal partial model (D-26), and a non-key parent field is hidden in a
collapsed card. **No relationship is ever dropped for want of a handle.**

**Collapse.** No row, or a row with `collapsed` false, means "default by size": collapsed when
there are more than 8 attributes. Every ERD PUT sends each listed card's current `collapsed`
flag, so a drag cannot un-collapse a card. Collapsing a card that was never dragged saves its
current x/y, which pins it. That is stated in the collapse tooltip. The Reset dialog says it
clears collapse choices as well as positions.

**Glyphs: one table for the canvas and for Mermaid.**

| Derived value | Crow's-foot / Mermaid |
|---|---|
| parent `1` | `\|\|` (exactly one) |
| parent `0..1` | `\|o` (zero or one) |
| child `1` | `o\|` (zero or one, A-S3-8) |
| child `many` | `o{` (zero or many, A-S3-8) |
| identifying | solid line; Mermaid `--` |
| not identifying | dashed line; Mermaid `..` |

### 3c — `services/render.py` (new; the one Mermaid label path)
```
escape_mermaid(text):          # design §7.12b, as written there, plus two tightenings
    s = str(text or "")
    s = s[:200]                                        # cap the RAW text first (never cut an entity)
    s = every Unicode Cc / Zl / Zp char (CR, LF, tab, \v, \f, U+0085, U+2028, U+2029) → " "
    s = s.replace("%%", "")
    s = "".join(MERMAID_ENTITY.get(c, c) for c in s)   # §7.12b table incl. ` ( ) ; — ONE pass
    return '"' + s + '"'                               # wrap last
_guard(text): any output line whose first token is click, call, href, %%{init, style,
    classDef, linkStyle or class → log + raise 500 (a renderer bug). Last step of all three
export_process_flow(g): flowchart LR; one subgraph per lane (id l{n}, label escaped);
    s{id}["label"]; -->|"cond"| for conditional; -.-> for HANDOFF; stores d{id}[("label")];
    a start/end event (one end NULL) → e{flow_id}((" ")) circle (one space: Mermaid 11 rejects an empty label — found at build, sara L4); handoff targets outside the
    frame → declared with escaped labels in an `outside` subgraph, as on the canvas
export_dfd(g): flowchart LR; s{id}(["label"]); d{id}[("label")]; x{id}["label"] (square);
    one edge per flow with |"label"|
export_erd(g): erDiagram; entity ids E{de_id} with an escaped display alias
    E7["DE-0007 Customer"]; attribute rows `<type> a_<n> [PK|FK] "<real name, escaped>"`
    (§7.12b: erDiagram takes no quoted attribute names, so Japanese or spaced names live in
    the comment and never collide). <type> is the seeded FIELD_DATA_TYPE **code** only if it
    matches [A-Z_]+, else `unknown`, never a label. One relationship line per group from the
    glyph table in 3b, e.g. `E3 |o..o{ E7 : "ship_to_address_id"`
```
Routes: `GET /bfc-nodes/{id}/process-flow/export?format=mermaid`, `GET
/bfc-nodes/{id}/dfd/export?format=mermaid`, `GET /projects/{id}/erd/export?format=mermaid`
(`&subject_area=`), `text/plain`. Other `format` values → 422. **`format=json` (the flow JSON
file) stays with the import slice.** A **"Copy as Mermaid"** button on each of the three
diagram screens.

## 8. `code_master` categories needed
None. The ERD shows `FIELD_DATA_TYPE` labels through the existing `/code-master` route.

## 9. API surface (all `/api/v1`, all protected, one guard each)

| Method · Path | Guard | Response |
|---|---|---|
| `GET /bfc-nodes/{id}/dfd` | `object_guard(BfcNode, REVIEWER)` | DFD graph (3a) |
| `GET /projects/{id}/erd?subject_area=` | `project_ctx(REVIEWER)` | ERD graph (3b); unknown / other-project / retired area node → 404 |
| `GET /bfc-nodes/{id}/process-flow/export?format=mermaid` | `object_guard(BfcNode, REVIEWER)` | text/plain |
| `GET /bfc-nodes/{id}/dfd/export?format=mermaid` | `object_guard(BfcNode, REVIEWER)` | text/plain |
| `GET /projects/{id}/erd/export?format=mermaid&subject_area=` | `project_ctx(REVIEWER)` | text/plain |
| `GET/PUT/DELETE /projects/{id}/diagram-layouts/{DFD\|ERD}/{scope}` | existing | unchanged |

## 10. Acceptance criteria

**Piece 0**
1. A card placed by hand, then Auto-arrange → **no two cards overlap** (seen in a browser). On
   the flow, a pushed step stays inside its own lane.
2. Zoomed out below 0.45, flow edge labels are hidden (seen).
3. Signed in as a REVIEWER, the flow canvas and step panel show no drag, draw, Reset, add, edit
   or remove controls. As an EDITOR, and as a platform admin, they are all back.

**3a — DFD (Grade 2)**
4. *(design 94)* "Customer" linked as an input to "Receive order" with DE "Sales order" draws
   Customer → Receive order labelled "Sales order". The store "Sales order" is still drawn, and
   that I/O row has no second store → step flow.
5. A step with 2 inputs and 1 output, and no external flows, draws exactly 3 flows in the right
   directions. A retired I/O row draws nothing.
5a. Invariant, over the seeded demo project: every active in-scope I/O row appears exactly once,
    either as a STORE flow or as covered by one or more EXTERNAL flows. The number of EXTERNAL
    flows equals the number of active in-scope external rows. An external flow with both a DE
    and a `flow_label` is labelled with the DE.
6. A DE written under L1 `01` and read under L1 `02` is in `cross_area` on the DFD of `01.x`,
   even though no `02` step is in the frame. A DE only read and written inside one L1 area is
   not. A DE written under `01` and read nowhere is not. A DE written and read under both `01`
   and `02` is.
7. The DFD of a step → 422. The DFD of a retired node → 409. The DFD of a node in a project the
   caller cannot see → 404.
8. A store dragged on the DFD is in the same place after reload. The process flow of the same
   node is unaffected (separate `diagram_type`).
9. The DFD has a table view listing every flow.

**3b — ERD (Grade 2)**
10. *(design 107)* `Shipment Line` holding a composite FK `(order_id, line_no) → Order Line`'s
    two-field PK, both mandatory → **one** relationship with 2 via fields, each landing on its
    own parent PK row, parent `1`.
    Either field optional or unknown → `0..1`.
11. `Order.ship_to_address_id` (group 1) and `Order.bill_to_address_id` (group 2) → Address
    give **two** relationships, labelled with their field names.
12. An FK set equal to the child's PK set → child `1`, identifying. A non-key FK → child
    `many`, not identifying (dashed).
13. *(design 108)* The ERD for L1 `01` shows only DEs read or written by steps under `01`, and
    one labelled stub per FK group leaving the area.
14. A DE with no PK field carries the `NO_KEY` badge and is drawn, not hidden.
14a. `Order.customer_id → Customer` with **no parent field named** draws a line landing on
     Customer's card (the entity handle). An FK naming a non-key parent attribute on a
     **collapsed** parent card also draws. The browser console shows no React Flow
     missing-handle warning.
14b. The subject area set to a single step gives exactly that step's entities.
15. *(design 109)* An entity dragged on the ERD is in the same place after a reload and for a
    second user. Whole-project and subject-area positions are independent. Collapse survives
    reload. Freezing a baseline is unaffected: no `baseline_*` table references
    `diagram_layout`.
16. A card with 12 attributes shows 8 plus "+4 more". The FK lines still land on the right
    rows when it is collapsed. A collapsed card that is then dragged is still collapsed after
    reload.
17. 200 entities with 2,000 fields render and arrange without freezing the tab (seeded
    fixture, seen in a browser).
18. The ERD has a table view listing every relationship.

**3c — Mermaid (Grade 2)**
19. *(design 88)* The process flow export has one `subgraph` per lane and the condition label
    on each conditional edge.
20. *(design 137)* A step named `x"] --> Y[click` and a lane named `%%{init: {"securityLevel":
    "loose"}}%%` export from **all three** exporters as inert quoted labels. No exported line
    begins with `click`, `call`, `href`, `%%{init`, `style`, `classDef`, `linkStyle` or `class`.
    The same test runs against a DE name, a field name and an external party name, and with a
    backtick name, a name containing U+2028, and a 300-character name full of `#`. A renderer
    change that emits a bare `click` line is stopped by `_guard` with a 500 (unit test on the
    guard).
20a. A field named `注文番号` and two fields `顧客ID` / `注文ID` export as distinct `a_<n>` lines
     with their real names in the comments. A field with no data type exports `unknown`.
21. The three exports of the seeded demo project render when pasted into a Mermaid renderer.
    Ben checks this once by hand (A-S3-5).
22. `format=json` → 422 naming the import slice. An export of a node you cannot see → 404.

## 11. Assumptions
- **A-S3-1** The DFD scope is exactly the process-flow scope: a non-process node and its
  process descendants. There is no project-wide DFD. At L1 the DFD may be large, and the
  answer is the same as for the flow: draw a lower node.
- **A-S3-2** **Cross-area is computed project-wide**, with the design's own rule (§4.1a):
  some writing L1 area ≠ some reading L1 area. Inside any one frame every step shares one L1,
  so a frame-only reading would never mark anything.
  *If Ben meant something else, only this one field changes. Nothing is stored.*
- **A-S3-3** The ERD edge label is the FK field names joined, not a role name, because the
  design leaves `DATA_ENTITY_RELATIONSHIP` unmodelled. A role name is a new table and a
  decision for Ben.
- **A-S3-4** An FK to a retired DE cannot occur today, because the retire is blocked. The
  `retired` stub is defensive only and has no acceptance criterion.
- **A-S3-5** "Mermaid output renders" is proven by a structural test (every line is one of
  the shapes the exporter emits, and every label is quoted) plus one manual paste by Ben. A
  Mermaid rendering library is **not** added as a dependency for tests.
- **A-S3-6** The ERD is **read-only** in this slice. Double-click opens the entity page rather
  than a side-panel editor, and drawing an FK is out (see §12). Fields are edited where they
  are edited today.
- **A-S3-8** **The child end never claims a minimum.** Child `1` draws "zero or one" and
  `many` draws "zero or many", because nothing in `DATA_FIELD` says a parent must have a
  child. This applies A-53 ("a diagram must not claim a rule nobody stated") to the child
  side. The design states it for the parent side only. *Ben can overrule it. It is display
  only.*
- **A-S3-7** The subject area may be any active node, not only L1/L2. A step gives the
  entities of that one step, which is harmless and matches what `diagram_layout` already
  accepts.

## 12. Out of scope
- ERD editing on the canvas: draw a line to create an FK, the side-panel field editor (3d,
  later).
- PNG / SVG export. It needs an image library the design does not name, so it is its own ask.
- Flow JSON export / import (`format=json`, D-25): the import-pipeline slice.
- TO-BE `system` on flow boxes (needs APPLICATION).
- A relationship role name (`DATA_ENTITY_RELATIONSHIP`).
- Baselining diagrams (A-52: layout is never frozen).

## 13. Build checklist
- **Order:** piece 0 on `main` → 3a and 3b in parallel worktrees `.worktrees/slice-3-dfd`,
  `.worktrees/slice-3-erd` → merge both → 3c on `.worktrees/slice-3-mermaid`. 3c waits because
  it renders their output.
- **No migration.** If one turns out to be needed, stop: it goes to `main` in order, and to Ben.
- Every route declares one guard. `test_route_guards` must stay green with the new routes.
- Visibility only through `access.require_project` / the guards: 404, never 403.
- No hex outside `theme/brand.js`. Store/entity teal and party colours come from `TOKENS`. All
  strings through `t()` in `en.processes.json` / `en.data.json`.
- Labels render as text: React Flow node content is JSX text, never `innerHTML`.
- Mermaid labels **only** through `render.escape_mermaid()`. There is no second label path.
- Tests at the service layer first: `tests/test_dfd_api.py`, `tests/test_erd_api.py`,
  `tests/test_mermaid_export.py`. test-runner, then ui-verifier, then sara before each merge.
  Her CRITICAL/HIGH are fixed before commit, MEDIUM/LOW go to VB-005 (the recorded
  local-phase deviation).
- Small commits. Full file shown when changed.

**Design review:** round 1 of 2 run 2026-09-30 (`design-auditor`, 14 findings: 3 HIGH,
5 MEDIUM, 6 LOW). All 14 are fixed in this text. Business questions 1, 3, 4 and 6 are answered
from the design. Question 2 is A-S3-8. Question 5 (client names leaving VB in pasted Mermaid)
is a VB-005 line for the pre-client gate.

**Round 2 of 2** (2026-09-30): all 14 closed; 3 new LOWs **tracked, not redrafted** —
VB-005 lines R2-NEW-1 (a stored `collapsed` flag is honoured; only no row means by size),
R2-NEW-2 (stub edges always land on the ghost's `t-L-entity`), R2-NEW-3 (`PK, FK` marker).
The builder applies those three rules. Criterion 5a needs the demo seed to hold a covered I/O
row and an external row with both a DE and a `flow_label`; criterion 21 needs a flow with a
start/end event.

**Cross-check run 2026-09-30:** every grid function has pseudocode in §7 (piece 0 has no
grid row because it reads nothing). Every grid entity is an existing table (§6: no change).
Every acceptance criterion traces to a §7 function. No new table, so no new audit columns.
