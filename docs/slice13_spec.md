# Slice 13: Ben's DFD and process feedback (D-65…D-70) — a ranked panel, a readiness light, a per-project DFD rule, process volume, and connections drawn on the DFD

**Date:** 2026-10-13 · **Author:** Lilly · **Status:** rev 0 — draft for Ben; **nothing here is decided**. D-65…D-70 sit
in `VB_design_history.md` §1 *Open — recorded, not decided*. Each item moves to §3 and the spec text changes only
when Ben rules on it (§13 lists which spec sections each ruling rewrites).
**Builds on:** D-24, D-24a, D-30, D-31, D-38, D-39, D-46, D-47, D-49, D-50, D-52, D-53, D-54, D-55, D-63, D-64, S7-3;
`docs/VB_design.md` §4.1a, §4.3, §7.2a, §7.7, §7.14, §14; **slice 10d** (ranked process panel,
`docs/slice10d_spec.md`), which **merges first** — every panel change here lands in its layout
(`NodePanel.jsx`, `PanelSections.jsx`, `HowItRuns.jsx`). Where this file and the design disagree, the design wins.

---

## 1. Purpose
Ben wants the DFD to be the thing a consultant finishes, not a by-product they discover is incomplete at freeze time:
the delivery items (solutions, FRs) at the top of the panel; on every process, a plain red / yellow / green light that
says whether its DFD can be completed and which fields it still needs; the project — not the code — deciding what
"complete" means; optional volume figures that turn into an FTE estimate for an ROI story; and the option of drawing a
connection on the diagram itself instead of going back to the panel.

## 1a. Interface — input · output · validation · archive · maintenance

| Part | 13a screen | 13b rule | 13c volume | 13d drawing |
|---|---|---|---|---|
| **Input** | none new | an admin ticks the required elements on a project settings screen | an editor types frequency, transactions + unit, minutes on a process | an editor drags from one diagram box to another |
| **Output** | split sections; a light + text label + icon per process; marks on the fields the rule needs | the light, the marks, the DFD warnings panel and the **freeze refusal** all follow the project's rule; the rule is copied onto each frozen baseline | derived annual hours and FTE per process; per-area totals as-is vs to-be | the same step I/O, external-flow and trigger rows the panel writes |
| **Validation** | read-only | the rule must be a valid set (§7.2); a change previews how many processes would fail | numbers ≥ 0 and capped; unit and period are codes; FTE never accepted from a body (VB law 6) | the existing writers' checks (`step_io.ensure_step_io`, `external_entity`, `trigger.link`), components, guards |
| **Archive** | n/a | `PROJECT_DFD_RULE_CHANGED` audit event; rule on the baseline header | values frozen in `baseline_bfc_node`; the FTE basis on the baseline header | the writers' existing audit |
| **Maintenance** | `/impeccable critique` after build | Ben reviews the default set after the first two client projects | the default hours basis reviewed with Ben once a client asks for ROI numbers | none beyond the canvas tests |

## 2. Playbook / doctrine references
`~/.claude/ftc-playbook.md` (audit on every write; codes not labels; no hex outside the theme). VB laws 1 (no hard
delete), 2 (baselines immutable, shadows generated, shadow column in the same migration, freeze set as data), 3 (audit
columns, `row_version`), 5 (branch on behaviour, never a code), 6 (derived values never from a body), 8 (one canvas,
one position saver), 9 (untrusted text as text), 10 (one migration per commit). CLAUDE.md: one guard per route,
`component=` on every project-component write (criterion 49b), `visible_project_ids` on every GET.

## 2a. Sub-slices, by risk

| Sub-slice | Items | Data change | Risk grade | Waits on |
|---|---|---|---|---|
| **13a** | D-66 split; D-68 light + D-69 marks against **today's fixed rule** (D-38: something starts it, and an output data entity) | **none** | 3 — presentation | 10d merged; **no answers needed** (Q-1, Q-2 have recommendations it builds to) |
| **13b** | D-70 per-project rule; light, marks, warnings and freeze driven by it | new rule storage + one baseline-header column → **`apple`** | **1** — changes what blocks a freeze | **Q-3, Q-4, Q-5, Q-6**; 13a |
| **13c** | D-67 volume fields; derived hours and FTE; as-is vs to-be totals | new `bfc_node` columns + shadow columns + two project settings → **`apple`** | **1** for the migration (shadows, hash spec bump), 2 for the screen | **Q-7, Q-8, Q-9, Q-10**; 13a (section placement) |
| **13d** | D-65 drawing connections on the DFD canvas | **none** (one composite route) | 2 — writes through the existing single writer | **Q-11, Q-12**; independent of 13b/13c |

**Order:** 13a → 13b → 13c, with 13d in parallel to any of them. **13b and 13c both add migrations; they are built on
`main` one after the other, never at the same time** (CLAUDE.md "Migrations only on main, in order").

---

## 3. Keystone grain
- **13a, 13d:** none new. The light reads one row per **live process step** (`bfc_node` where `is_process`); a to-be
  process and its BR are 1:1 (D-2), so "the BR's light" and "the process's light" are the same thing.
- **13b:** **one row per (project × required DFD element)** — the project's rule (shape to `apple`, §5).
- **13c:** no new grain: volume is **one set of values per process step** (columns on `bfc_node`, or a 1:1 table —
  `apple`'s call, §5).

## 4. Business Requirement grid

### 4.1 Slice 13a — screen only

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| panel: Solutions section | `BR_SOLUTION`, `SOLUTION` | R (writes unchanged) | **D-66.** Its own collapsed section, count + one-line summary, shown when SOLUTION is on. `BrSolutionTags` unchanged inside. Ranked **first** of the collapsed sections |
| panel: Function requirements section | `BR_FUNCTION_REQUIREMENT`, `FUNCTION_REQUIREMENT` | R (writes unchanged) | **D-66.** Its own section, second, shown when FUNCTION_REQUIREMENT is on, **independently of SOLUTION** (D-52). `BrFrLinks` unchanged inside (its solution picker still needs SOLUTION) |
| `dfd_readiness` | `BFC_NODE`, `BFC_NODE_DATA_ENTITY`, `BFC_NODE_EXTERNAL_FLOW`, `BFC_NODE_TRIGGER` | R | **D-68.** Per live process of a chart whose DFD component is on: the rule's elements (13a: the fixed D-38 pair *started* and *data out*) → each `met` / `missing` → **light**: all met = READY (green), some = PARTIAL (yellow), none = NOT_READY (red). A chart with its DFD off → no light (`rule_applies = false`). Computed from the same predicates as `missing_io`, so the light and the freeze can never disagree |
| tree + panel: light | — | R | **D-68.** Light on each **process row of the function chart** (always visible, not hover-only like the BR chip) and in the **panel header** beside the BR number. Colour **plus** icon **plus** text ("Ready", "Partly", "Not ready"), never colour alone (D-50). Tooltip lists the missing elements. A chart filter "Not ready only". Exact place: **Q-1** |
| DFD index: counts | — | R | Per listed DFD (D-54): "12 ready · 3 partly · 1 not" |
| panel + BR page: marks | — | R | **D-69.** A small "DFD" mark on each field the rule needs (13a: the *Started by* tile and the *Data* tile's in/out; on the BR page the CRUD grid header), with the note "Needed to complete the DFD". Met → the mark shows a tick; missing → the amber dot 10d already uses. The marks are drawn from the rule's element list, so 13b changes them by changing data, not screens |

### 4.2 Slice 13b — the project's DFD rule (D-70)

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `get_dfd_rule` | `PROJECT_DFD_RULE` (name to `apple`) | R | VIEW. The project's required elements, the full catalogue with plain descriptions, which are recommended, and which are locked on (§7.2) |
| `preview_dfd_rule` | rule, `BFC_NODE` + step links | R | ADMIN. For a proposed set: per chart, how many live processes would turn red/yellow/green and how many would **block the next freeze**. No write |
| `set_dfd_rule` | `PROJECT_DFD_RULE`, `PROJECT`, `AUDIT_EVENT` | C/U | ADMIN (platform admin, as D-39 depth — **Q-5**). Body: element codes + `row_version` of the project + preview digest. Validates the set (§7.2), soft-retires dropped rows, inserts/relinks added rows (S1-7), bumps `project.row_version`, audit `PROJECT_DFD_RULE_CHANGED {from, to, would_block}` |
| `dfd_readiness` | as 13a + rule | R | Reads the project's rule instead of the constant. One owner: `process_flow.readiness` |
| `process_completeness` / `consistency_check` | as today + rule | R | The freeze-blocking keys are **the rule's elements**, not a fixed pair. Elements outside the rule are not reported as warnings at all (they would be noise), only as information in the DFD's warnings panel. Still applies only to a chart whose DFD component is on (S7-3) |
| `freeze_baseline` | `BASELINE` | C | Refused on any process missing a **rule** element in a chart whose DFD is on. **Copies the rule onto the header** (as `data_model_depth`), so a baseline says which rule it passed |
| `create_project` | `PROJECT_DFD_RULE` | C | New projects start with the **recommended set** (**Q-4**) |
| migration backfill | `PROJECT_DFD_RULE` | C | Every existing project gets **exactly today's rule** (STARTED + DATA_OUT), so no project's freeze changes on deploy (**Q-4**) |

### 4.3 Slice 13c — process volume and FTE (D-67)

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `set_process_volume` | `BFC_NODE` (or `PROCESS_VOLUME`) | U | EDIT, process nodes only (non-process → 422, as criterion 4), either chart. Fields all optional: how often it runs (`runs_per_period` + `volume_period_code`), transactions per run (`transactions_per_run` + `transaction_unit_code`), minutes per transaction (`minutes_per_transaction`). Codes, never labels. `row_version` checked. Audit `PROCESS_VOLUME_SET {from, to}`. Body never carries hours or FTE (VB law 6 — 422 if it does) |
| `derive_volume` | `BFC_NODE`, `PROJECT`, `CODE_MASTER` | R | Server-side, one owner `services/process_volume.py`: `annual_runs = runs_per_period × periods_per_year(behaviour of volume_period_code)`; `annual_hours = annual_runs × transactions_per_run × minutes_per_transaction / 60`; `fte = annual_hours / (project.working_days_per_year × project.hours_per_working_day)`. Any input missing → `null` with `incomplete: [fields]`. Returned on every read of a process; never stored (**Q-8**) |
| `set_fte_basis` | `PROJECT`, `AUDIT_EVENT` | U | The FTE basis as a project setting with a default (**Q-7**). Audited, `row_version` |
| `volume_summary` | `BFC_NODE` | R | VIEW. Per chart, totals of annual hours and FTE per L1 and L2 area, as-is beside to-be **matched by area code** (`hier_code` prefix) — the time saved per area (**Q-9**). Processes with incomplete volume are counted and listed, never guessed |
| `freeze_baseline` | `BASELINE_BFC_NODE`, `BASELINE` | C | The volume columns are frozen with the node (shadow columns, same migration) and hashed under a new hash spec; the FTE basis is copied onto the header, so a baseline's FTE re-derives byte-identical |
| `maintain_code_master` | `CODE_MASTER` | C/U | New categories `VOLUME_PERIOD` (system, with behaviour) and `TRANSACTION_UNIT` (library + project override), §8 |

### 4.4 Slice 13d — drawing connections on the DFD (D-65)

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| draw store → process / process → store | `BFC_NODE_DATA_ENTITY` | C | Step input / output through the existing `POST /bfc-nodes/{id}/data-entities` → `step_io.link` → **`step_io.ensure_step_io`** (the one writer). Component: the chart's DFD. Already there → "Already on the diagram", no write |
| draw process → empty canvas | `BFC_NODE_DATA_ENTITY`, `DATA_ENTITY` | C | A picker: an existing data entity (searchable by `DE-` number or name), as input or output; **creating a new entity there is Q-12** |
| draw party ↔ process | `BFC_NODE_EXTERNAL_FLOW` (+ step I/O) | C | The existing external-flow route; a small form asks for the data entity (optional) or a flow label, as the panel does. The external-flow service ensures the step I/O (R2-D13) |
| draw trigger → process | `BFC_NODE_TRIGGER` | C | The existing `trigger.link` route |
| draw process → process (a hand-off) | `BFC_NODE_DATA_ENTITY` ×2 | C | **The only new route.** Order stays derived (D-38): the user picks the data entity A hands to B; one transaction writes A's output and B's input through `ensure_step_io`. Both steps live, same project, **same chart** (else 422 "Diagrams never cross charts"). The derived order arrow then appears by itself |
| remove a flow | the same three tables | D (soft) | Click a flow → "Remove this flow" → the existing unlink route. **A step I/O a BR CRUD or an external flow depends on stays (409, the message names them)** — the canvas shows the message and a link to the requirement. No keyboard delete (§7.14) |
| `save_diagram_layout` | `DIAGRAM_LAYOUT` | C/U | A store or party that appears because of a new connection is placed where it was dropped, through `useLayoutSave` (D-30) |
| BR CRUD after drawing | `BR_DATA_ENTITY` | — | **Not written.** Drawing writes step I/O; D-24 runs one way (CRUD → I/O). The CRUD grid shows the I/O with no CRUD as a hint "On the diagram, not in the requirement yet — pick C, R, U or D" (**Q-11**) |

---

## 5. Logical design — to `apple`
Nothing below is modelled by hand; this is the brief `apple` receives.

**13b — `apple` brief.** "A project chooses which DFD elements every process must have before the scope can be
frozen. Elements are a fixed, code-defined list (the code branches on them), each `met` per process by a predicate over
existing rows. One rule per project, changed rarely, by an admin, audited; the rule in force at a freeze must be
recorded with the baseline." Questions for her:
1. **Child table `project_dfd_rule` (project × element code, soft delete, audit columns), mirroring
   `project_component`** — recommended — versus boolean columns on `project`.
2. Elements as a **system `code_master` category `DFD_RULE_ELEMENT`** (labels, sort order, description; `is_system`
   so a project override cannot rename what the code branches on), as `PROJECT_COMPONENT` is.
3. **Baseline record:** a header column on `baseline` (`dfd_rule_codes`, the sorted list, NULL on baselines frozen
   before 13b = "the D-38 rule") — recommended, as `data_model_depth` — versus a frozen entity in the freeze set
   (shadow table, hash spec bump). The rule is a setting, not scope, so it should not appear as a diff row.
4. Whether `project.row_version` or a per-rule version guards concurrent edits.

**13c — `apple` brief.** "Optional volume figures per process step, in both charts: how often it runs (a number per
period), transactions per run with a unit from a master, minutes per transaction. Hours and FTE are derived on read
from these and a project-level FTE basis; never stored, never accepted. Frozen with the process." Questions for her:
1. **Columns on `bfc_node`** (with a CHECK that a non-process row holds none) — recommended, as
   `data_processing_desc` — versus a 1:1 `process_volume` table (cleaner if volume later gains history or scenarios,
   but a new frozen entity and a new step-owned table for `step_retire.OWNED`).
2. Types: `runs_per_period numeric(9,2)`, `transactions_per_run numeric(12,2)`, `minutes_per_transaction
   numeric(9,2)`, each `CHECK (>= 0)`; the two codes as `code_master` FKs with the category-in-key pattern (§5.4.13).
3. FTE basis on `project`: `working_days_per_year smallint NOT NULL DEFAULT 240`, `hours_per_working_day numeric(4,2)
   NOT NULL DEFAULT 8.00` (Q-7), and their copies on `baseline`.
4. Whether `periods_per_year` for `DAY` reads the project's `working_days_per_year` (recommended) or 365.

## 6. Physical design — consequences, for `apple` to confirm

| Sub-slice | Table | NET-NEW / NEEDS-CHANGES | Shadow / baseline consequence (VB law 2) | Component gating |
|---|---|---|---|---|
| 13b | `project_dfd_rule` | NET-NEW (audit columns, soft delete, `row_version`; added to `models/__init__.py`) | **Not shadowed, not in `FREEZE_SET`** — a setting, not scope. No `step_retire.OWNED` entry (points at the project, not a step) | Writes need no project component (it is a project setting); the guard is platform admin. The rule **has effect** only for a chart whose DFD component is on (S7-3) |
| 13b | `baseline` | NEEDS-CHANGES: `+ dfd_rule_codes` (nullable, set at freeze) | A header column, not a shadow; immutability of frozen content unchanged. Old baselines NULL | — |
| 13b | `code_master` seed | `DFD_RULE_ELEMENT` (seed, never Alembic) | — | — |
| 13c | `bfc_node` | NEEDS-CHANGES: `+ runs_per_period, volume_period_code_id, transactions_per_run, transaction_unit_code_id, minutes_per_transaction` (+ category columns if the §5.4.13 pattern) | **`baseline_bfc_node` gets the same columns in the same migration** (parity test `tests/test_baseline.py` reads the database); shadow DDL generated by `services/baseline_shadow.py`, then frozen as literal DDL in the migration, as 0048 did. **Hash:** `freeze_set` `bfc_node` gains a `{3: …}` hashed list, **`CURRENT_HASH_SPEC` 2 → 3**; old baselines re-hash under spec 2 and still verify; the diff already compares per side's spec (`baseline.py` `columns_for` per side). A shadow column's type is **never** ALTERed later (pauses for Ben) — so the types must be right first time; this is why `apple` goes first | `bfc_node` freeze gate unchanged (`AS_IS` for the as-is chart). **No new component recommended** (Q-10): the fields are optional and live in a collapsed section; an as-is write needs AS_IS (existing `dfd_component` rule) |
| 13c | `project` | NEEDS-CHANGES: `+ working_days_per_year, hours_per_working_day` | Not shadowed; **copied onto `baseline`** (`+ fte_working_days, fte_hours_per_day`) so a baseline's FTE re-derives as frozen | — |
| 13c | `code_master` seed | `VOLUME_PERIOD`, `TRANSACTION_UNIT` | — | — |
| 13a, 13d | — | none | none | 13d writes carry `component=` the chart's DFD (TO_BE_DFD / AS_IS), as the panel's writes do; the hand-off route is added to `ROUTE_COMPONENTS` |

Migrations: 13b one (table + header column + backfill of today's rule into every project — reversible: the
downgrade drops the table and the column; **the backfill is data, so it lives in the migration only because the table
is born empty and must match today's behaviour**, recorded as such; the element catalogue is a seed). 13c one
(columns + shadow columns + project/baseline columns; reversible; **destructive on downgrade** — dropping the
shadow columns of frozen baselines loses frozen volume — so the downgrade **pauses for Ben** per law 10).

---

## 7. Function

### 7.1 `services/process_flow.py::readiness` — one owner (13a, widened in 13b)
```
ELEMENTS = {   # code → predicate over one live process; the code is the behaviour (system category)
  STARTED:     a live step input OR a live inbound external flow OR a live trigger link    # D-49, today's "input"
  DATA_IN:     a live step input (a data entity)
  DATA_OUT:    a live step output (a data entity)                                          # today's "output"
  EXTERNAL:    the process has a live external flow  — scope of this element is Q-6
  ORDER:       the process is joined to at least one other process of its chart by the derived order
               (it reads what another writes, or writes what another reads); a chart with one process passes
}
FIXED_RULE = {STARTED, DATA_OUT}            # D-38 today; 13a uses this constant; 13b reads the project's rule

readiness(db, project_id, bfc_set, node_ids=None):
    rule = FIXED_RULE (13a) | project rule (13b)
    if chart's DFD component off → {rule_applies: False}
    per process: met = {e: ELEMENTS[e](p) for e in rule}
       light = READY if all met, NOT_READY if none met, else PARTIAL
    return {rule_applies, rule: [codes], processes: {node_id: {light, missing: [codes]}}}
missing_io(...) and consistency_check are re-expressed over readiness(): a process missing any rule element is a
FREEZE_BLOCKING_WARNING (13b keys: process_missing_<element>; today's two keys keep their names).
```
One SQL pass with `EXISTS` sub-selects per element (as `_has_input` / `_has_output` today); ORDER from the same
pairs `generate_dfd` derives. Exposed on the existing tree read (`bfc.tree` adds `dfd_light` per process row) and on
`GET /projects/{id}/process-completeness` (adds `readiness`). **No new route in 13a.**

### 7.2 `services/dfd_rule.py` (13b)
```
validate(codes):  STARTED always required (a process nothing starts cannot be placed); ORDER requires DATA_IN and
                  DATA_OUT (order is derived from data — option A, §8a); unknown code → 422
preview(project, codes) → per chart {ready, partly, not_ready, would_block}, digest
set(actor, project, codes, row_version, digest): platform admin; 409 on stale row_version or changed digest;
                  soft-retire / relink rows; AUDIT PROJECT_DFD_RULE_CHANGED {from, to, would_block}
```

### 7.3 `services/process_volume.py` (13c)
```
set(actor, node, row_version, fields): node live and is_process (422 otherwise); component = dfd_component(node)
       for an as-is node; codes resolved through code_master.resolve (send codes); ranges checked; body containing
       annual_hours / fte → 422; AUDIT PROCESS_VOLUME_SET
derive(node, basis): periods_per_year by behaviour of volume_period_code: DAY → basis.working_days_per_year,
       WEEK 52, MONTH 12, QUARTER 4, YEAR 1   (branch on behaviour, never on the code — law 5)
summary(project): per area (L1, L2 by hier_code prefix) per chart: Σ hours, Σ FTE, n complete, n incomplete;
       as-is and to-be side by side on matching area codes; unmatched areas listed alone
```

### 7.4 Canvas (13d) — `DfdPage.jsx` + `ModelCanvas` (one canvas, law 8)
`connectable` becomes true for an editor on a live diagram (false for viewers, baselines, a chart whose DFD is off).
`onConnect` classifies the two ends (store / process / party / trigger) and calls the matching API function in
`api/scope.js`; invalid pairs (store → store, party → store, trigger → anything but a process, process across charts)
are refused **in the browser before any call** and again by the server. `onConnectEnd` on empty canvas opens the
data-entity picker. The hand-off route:
```
POST /bfc-nodes/{id}/hand-offs  {to_bfc_node_id, data_entity_id}    object_guard(BfcNode,"EDIT",component=dfd)
    both nodes live processes, same project (404 if not visible), same bfc_set (422)
    ensure_step_io(A, de, "O"); ensure_step_io(B, de, "I"); one commit
```

---

## 8. `code_master` categories needed (seeds in `backend/seeds/`, never Alembic)

| Category | System? | Codes (behaviour) | Sub-slice |
|---|---|---|---|
| `DFD_RULE_ELEMENT` | yes | STARTED, DATA_IN, DATA_OUT, EXTERNAL, ORDER (code = behaviour) | 13b |
| `VOLUME_PERIOD` | yes | DAILY (DAY), WEEKLY (WEEK), MONTHLY (MONTH), QUARTERLY (QUARTER), ANNUAL (YEAR) | 13c |
| `TRANSACTION_UNIT` | no — library + project override | INVOICE, ORDER, CASE, DOCUMENT, RECORD, CALL, PAYMENT, EMPLOYEE, OTHER | 13c |

## 8a. The D-70 conflict — options (not decided)

D-38 says (1) order is derived from data and explicit arrows are retired, and (2) a fixed rule — something starts the
process, and it outputs a data entity — blocks the freeze. D-70 asks for a per-project rule that can allow a DFD
"with no data entities" and lists "forward arrow (order)" as an element.

| | **A. The rule becomes per project; order stays derived from data** (recommended) | **B. Explicit arrows return as a project option** | **C. Keep D-38's rule as a floor; the project can only add to it** |
|---|---|---|---|
| What changes | D-38 (2) becomes the project's rule. A project may drop DATA_IN / DATA_OUT. **ORDER is only selectable with both data elements on**, because order *is* data. A project without data entities still gets a readable diagram: processes are laid out in **chart order** (`seq_no` under each parent — the order the consultant already set), drawn without arrows and labelled "chart order" | `bfc_node_flow` comes back for projects that pick "hand-drawn order": `vb_app` regains INSERT/UPDATE (criterion 83 reverses), its routes return, two sources of order coexist and must be reconciled in every diagram, export and baseline diff | D-38's pair always blocks; the project setting can only make the rule stricter (add DATA_IN, EXTERNAL, ORDER). A DFD with no data entities stays impossible to freeze, as today |
| Ben's "possible but not recommended" | Yes — an admin can choose it; the default and the setting screen recommend the full set | Yes | **No** |
| D-38 "no duplicate" | Kept | **Broken** — Ben's own reason for retiring arrows | Kept |
| Cost / risk | Moderate: one rule table, readiness re-expressed, freeze keys from the rule | High: un-retire a table, grants, routes, diagrams, baselines (`bfc_node_flow` is SELECT-only history today) | Low |
| Recommendation | **Choose A** | Not recommended | Fallback if Ben prefers to keep the freeze floor |

Under any option, a chart whose DFD component is off is never blocked (S7-3, unchanged).

---

## 9. API surface (all under `/api/v1`; each route declares one guard)

| Method · path | Guard | Sub-slice | Notes |
|---|---|---|---|
| `GET /projects/{id}/bfc-tree` (existing) | `project_ctx("VIEW")` | 13a | rows gain `dfd_light`, `dfd_missing` (process rows, DFD on) |
| `GET /projects/{id}/process-completeness` (existing) | `project_ctx("VIEW")` | 13a | gains `readiness` |
| `GET /projects/{id}/dfd-rule` | `project_ctx("VIEW")` | 13b | catalogue + current rule |
| `POST /projects/{id}/dfd-rule/preview` | `platform_admin` | 13b | no write |
| `PUT /projects/{id}/dfd-rule` | `platform_admin` | 13b | `{codes, row_version, preview_digest}` |
| `PATCH /bfc-nodes/{id}/volume` | `object_guard(BfcNode,"EDIT")` (+ `component=` the as-is DFD for an as-is node, per the existing `dfd_component` rule — confirm with criterion 49b) | 13c | body without hours/FTE |
| `PUT /projects/{id}/fte-basis` | `platform_admin` (Q-7) | 13c | |
| `GET /projects/{id}/volume-summary` | `project_ctx("VIEW")` | 13c | via `visible_project_ids` |
| `POST /bfc-nodes/{id}/hand-offs` | `object_guard(BfcNode,"EDIT",component=dfd)` | 13d | the only new 13d route |

Every new GET is covered by `test_no_get_route_leaks_a_restricted_project`; every new write by criterion 49/49b.

---

## 10. Acceptance criteria

**13a**
- A1. On a to-be process with SOLUTION and FUNCTION_REQUIREMENT on, the panel shows two separate sections,
  "Solutions (n)" then "Function requirements (n)", both above External parties, Description and Supporting systems.
- A2. With SOLUTION off and FUNCTION_REQUIREMENT on, only "Function requirements" shows, and an FR can be linked.
- A3. A process with a trigger and an output data entity shows "Ready" with a green icon; with only a trigger,
  "Partly"; with neither, "Not ready" — each with text and icon, readable in greyscale.
- A4. For every process, the light is NOT "Ready" exactly when `process-completeness` lists it in `missing_input` or
  `missing_output` (one source, no disagreement), on a project of ≥ 50 processes.
- A5. With TO_BE_DFD off, no light and no DFD mark shows on any to-be process.
- A6. The *Started by* and *Data* tiles carry a "DFD" mark with the note "Needed to complete the DFD"; it shows a tick
  when met.
- A7. The DFD index shows ready / partly / not-ready counts per diagram that sum to its process count.

**13b**
- B1. A new project's rule is the recommended set; every project existing at deploy has exactly STARTED + DATA_OUT,
  and a freeze that passed the day before deploy still passes.
- B2. Removing DATA_OUT from a project's rule: a process with a trigger and no data turns "Ready", and the freeze is no
  longer refused for it; the audit holds `PROJECT_DFD_RULE_CHANGED` with from, to and the would-block count.
- B3. Adding DATA_IN: the preview names how many processes would block; after saving, the freeze refuses with that list.
- B4. Choosing ORDER without DATA_IN and DATA_OUT returns 422; dropping STARTED returns 422.
- B5. A non-admin `PUT /dfd-rule` returns 403; a non-member of a restricted project gets 404 on the GET.
- B6. A baseline frozen after 13b shows its rule on the header; one frozen before shows "D-38 rule"; both still verify.
- B7. The marks on the panel follow the rule: dropping DATA_IN removes the mark from the data-in half of the Data tile.

**13c**
- C1. A process with 3 runs per week, 40 invoices per run, 6 minutes per invoice, on the default basis, returns
  annual hours 624 and FTE 0.33 (624 / 1,920), computed by the server.
- C2. A body carrying `fte` or `annual_hours` returns 422; a non-process node returns 422; a negative value returns 422.
- C3. With any volume field empty, FTE is `null` and the response names the missing fields.
- C4. Changing the project's FTE basis changes every process's FTE without touching any process row.
- C5. After the 13c migration, the baseline shadow parity test passes; every pre-13c baseline still verifies; a diff
  of a pre-13c baseline against live shows no process as CHANGED merely because volume columns exist.
- C6. A baseline frozen after 13c re-derives the same FTE after the project's basis is changed.
- C7. The volume summary shows as-is and to-be hours per L1 area side by side and lists processes with incomplete
  volume; no process with incomplete volume contributes a number.
- C8. Unit and period send codes; a project override label shows on the screen, the code is stored.

**13d**
- D1. Dragging from a data store to a process creates exactly one step input; the DFD redraws with the flow; the same
  drag again writes nothing and says "Already on the diagram".
- D2. Dragging process A to process B and picking DE-0007 writes A's output and B's input in one transaction; the
  derived order arrow A → B appears; if B's input fails, A's output is not written.
- D3. Removing a flow that a BR's CRUD depends on returns the 409 message naming the BR; nothing is removed.
- D4. A viewer, a frozen baseline view, and a chart with its DFD off cannot start a connection.
- D5. A hand-off between an as-is and a to-be process returns 422; to a process in a project the user cannot see, 404.
- D6. Every row written by drawing is identical to the row the panel writes for the same choice (same table, same
  writer `step_io.ensure_step_io`, same audit).

## 11. Assumptions
- **ASSUMPTION A-13-1:** "BR list" in D-68 means wherever BRs are seen, since D-53 removed the BR list; the light goes
  on the function chart's process rows and the panel (Q-1). *Changes no data.*
- **ASSUMPTION A-13-2:** Ben's *"fully with the external, maybe only with the D"* means "or only with the data
  entities" (as recorded in D-70). *Changes the default set if wrong.*
- **ASSUMPTION A-13-3:** "Process" in Ben's element list is always required (the box exists) and is not a choice.
- **ASSUMPTION A-13-4:** "Number of transactions" is per run and "assumed time" is per transaction (Q-8). **If wrong,
  the columns change — must be settled before `apple` models 13c.**
- **ASSUMPTION A-13-5:** As-is and to-be compare by area code, not process by process; there is no process-to-process
  mapping today (D-47 copy keeps no provenance). *A process mapping would be a new table.*
- **ASSUMPTION A-13-6:** Drawing on the canvas never creates BR CRUD (Q-11).
- **ASSUMPTION A-13-7:** Volume figures are scope and are frozen and diffed (a client signs off an ROI case on them).
  **If Ben says they are working estimates only, they leave the hash and the hash-spec bump disappears.**

## 12. Out of scope
Purpose / Data processing on the panel (still pending with Ben, 10d §11); volume in the flow-file import/export
(`vb-process-flow/2.0` unchanged — a format bump later); a full ROI/benefit model (D-14 BENEFIT component);
performer as a rule element (stays a warning, D-46); reconnecting an existing flow by dragging its end; drawing on the
ERD (exists); creating processes or parties from the canvas; any change to the derived order algorithm.

## 13. Build checklist
- 13a waits for 10d on `main`; build in `.worktrees/slice-13a`, own `backend/.env` and test DB.
- `apple` models 13b and 13c **before any code**; `sara` reviews 13b (freeze, access) and 13c (baselines, migration
  chain) before commit; `design-auditor` round on 13b and 13d.
- Migrations on `main`, in order, one per commit, reversible; 13c's downgrade pauses for Ben. 13b and 13c never at
  the same time.
- Shadow columns generated by `services/baseline_shadow.py`, frozen as literal DDL in the same migration; `freeze_set`
  `bfc_node` list under `since=3`; `CURRENT_HASH_SPEC = 3`; the two module asserts still hold.
- Strings via `t()` in `en.processes.json` / `en.requirements.json` / `en.settings.json`; light colours from
  `STATUS_COLOR_MAP` tokens, never hex; light always with icon + text.
- Tests at the service layer first: readiness = completeness (A4), rule backfill (B1), FTE arithmetic (C1), shadow
  parity + old-baseline verify (C5), hand-off atomicity (D2); then lint + build; ui-verifier at 1440 / 900 / 400 px;
  screenshots to `Evidence/<date>/slice-13x/`.
- **On each ruling, in the same commit:** D-65…D-70 move from `VB_design_history.md` §1 to §3, and the spec is
  rewritten: D-66 → §14.3 panel bullet + D-63 text; D-68/D-69 → §4.3, §14.3; D-70 → §4.1a, §7.2a
  `process_completeness`, §7.7 freeze, criteria 83–94 area, S7-3; D-67 → §4.1, §5.3, §6.1, §8; D-65 → §4.1a, §7.14
  ("connections are not drawn" becomes "drawn connections write the same record"), D-31 wording.

## 14. Cross-check
Every grid entity appears in §5/§6 or is an existing table; every grid function has pseudocode in §7 or is an existing
writer named by file; every criterion traces to a function in §4; the one NET-NEW table (13b) carries audit columns,
soft delete and `row_version`. Run: yes.

---

## 15. Questions for Ben

Plain answers are enough; each has a recommendation, and **"accept all recommendations" is a valid answer.**

| # | Question | Recommendation | Blocks |
|---|---|---|---|
| **Q-1** | There is no list of requirements any more (you moved them into the function chart). Where should the red / yellow / green light go? | On every process line in the function chart, at the top of the process panel, and as counts on the DFD list; plus a "show only not ready" filter. No new list page | nothing (13a builds this unless you say otherwise) |
| **Q-2** | Should Solutions come before Function requirements in the panel, and should both start open? | Solutions first, then Function requirements; both open the first time, then remembered per person (as 10d) | nothing (13a) |
| **Q-3** | Your per-project rule and your earlier rule (arrows come only from the data, and a missing input/output blocks the freeze) pull in different directions. Pick one: **A** — the project chooses its rule, arrows still come only from the data, and a project without data shows its processes in chart order; **B** — hand-drawn arrows come back as an option; **C** — today's rule stays as a minimum and projects can only make it stricter | **A** (§8a) | **13b** |
| **Q-4** | What rule should projects start with? | New projects: the full recommended set (something starts it, data in, data out, joined to the flow). Existing projects keep exactly today's rule, so no freeze changes overnight; an admin can tighten it | **13b** |
| **Q-5** | Who may change a project's DFD rule? | Platform admins only, like the data-model depth setting; everyone sees it | **13b** |
| **Q-6** | "External entity" as a requirement: must **every** process talk to an outside party, or must **each diagram** have at least one outside party? (Most internal steps never touch one.) | Each diagram, not each process; and off by default | **13b** |
| **Q-7** | To turn hours into FTEs we need a working year. Make it a project setting with a default of **240 working days × 8 hours = 1,920 hours**, changeable by an admin? | Yes, 240 × 8 by default; platform admin can change it per project; the value used is stamped on each baseline | **13c** |
| **Q-8** | Is "number of transactions" counted **per run** of the process, and is "time" the minutes **per transaction**? (e.g. runs 3× a week, 40 invoices each time, 6 minutes per invoice) | Yes to both — time per transaction scales with volume, which is what a time-saving case needs | **13c** (must be answered before the data model) |
| **Q-9** | To show time saved, as-is and to-be need matching. Compare by area (same function-chart branch code), or do you need a process-by-process link? | By area for now; a process-to-process link is a later, separate design | **13c** (the summary only; the fields can be built without it) |
| **Q-10** | Should volume be frozen in baselines (so a signed scope carries its ROI figures) and switchable as a project component? | Frozen: yes. Separate on/off component: no — the fields are optional and sit in a collapsed section | **13c** |
| **Q-11** | When someone draws a data flow on the diagram, should the requirement's data use (create/read/update/delete) be filled in automatically? | No — the diagram cannot know whether it is a create or an update. The requirement shows "on the diagram, not in the requirement yet" so the consultant picks | **13d** |
| **Q-12** | When drawing to an empty spot on the diagram, may the consultant create a **new** data entity there, or only pick an existing one? | Allow creating one (it gets its `DE-` number on save), as the flow-file import already does | **13d** |

**Buildable with no answers: 13a** (D-66 split, and the light and marks against today's rule, placed per Q-1/Q-2's
recommendations — a one-line move if Ben differs). 13b needs Q-3…Q-6; 13c needs Q-7…Q-10 (Q-8 before `apple`);
13d needs Q-11, Q-12.
