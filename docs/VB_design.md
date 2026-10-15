# Value Bridge — Design Spec

**App:** Value Bridge (VB) · **For:** Fortience Consulting Inc. — Strategic PMO practice
**Scope of this spec:** MVP — Scope Management & Control
**Status:** the current, integrated spec. Signed off by Ben 2026-09-28; every decision since (D-37…D-70 and the slice rulings) is folded in. **What changed and why** — every decision, review and ruling with its date — is in [`VB_design_history.md`](VB_design_history.md); items raised but not yet decided are listed there too, not here.
**Last integrated:** 2026-10-14 (through S13-2, SC-1…SC-11, SP-1, S10c-2, S11-1, S-T, S-P). Builds on `docs/ASSESSMENT_BRIEF.md`.

---

## 1. Purpose

**Value Bridge is Fortience Consulting's Strategic PMO platform for the full lifecycle of
business transformation** — from current-state assessment, through requirements and
solution definition, into system implementation and benefit realisation. It is the system
of record for what the transformation is, who owns it, what data it moves, and what
changed.

**This MVP delivers Scope Management & Control, and the control framework that makes it
actionable.** It
holds the client's business function chart, the data entities it processes, the business
requirements that fall out of them, the issues raised against those requirements, and the
function requirements a system vendor will later build — and freezes all of it into
versioned, diffable baselines so scope change is evidenced rather than argued.

Scope control is not the prevention of change — projects change, always. It is the ability
to **absorb change deliberately**: see it early, price it, decide, re-baseline. A project
that shows no change is not controlled, it is unexamined. Everything in §4.8–§4.13 exists to
turn a number into an action.

Resource, procurement and detailed schedule management are later increments on the same
spine, not a different product. Everything in §5 is modelled so they attach to it rather
than replace it (§12).

---


**Decision ids.** The text cites decisions by id — D-n (product decisions), S-n (slice rulings), R1-/R2- (review
findings), OR-n, Q-n, A-n. The id is the link to the history file, where the decision is recorded in full.

---

## 2. Playbook / doctrine references

Bound by `~/.claude/ftc-playbook.md` (v1.3). The non-negotiables this design leans on
hardest, by number:

| # | Rule | Where it bites in this app |
|---|---|---|
| §9.1 | `JWT_SECRET_KEY` from env only, no fallback | Scope area 7 (auth) |
| §9.2 | `created_by` from the JWT, never the request body | Every business table; baseline `frozen_by_user_id` likewise |
| §9.3 | All lookups in `code_master`, send the code not the label | FR type, RACI type, issue severity/type/status, org unit level, project component and template |
| §9.7 | Soft delete `is_active = FALSE`, no hard DELETE | All business entities. **Baseline snapshot rows are the exception** — see §11 A-7 |
| §9.8 | **IDs generated at save time only** — never on screen load or preview | Directly governs BR / DE / FR / Issue / SOL / EXT number generation and the BFC `hier_code` (scope areas 1–5) |
| §9.10 | Shared logic in ONE service file | Number generation, the visibility predicate (`services/access.py`) and "is this component on" (`services/components.py`) are each one service, used everywhere |
| §9.11 | Three-layer rule: Router → Service → Model | Visibility filtering lives in the service layer, never in a router |
| §7 | Standardized error handling, `detail` string | 409 on optimistic lock when two consultants edit one BFC node |

Any deviation gets a recorded reason in `docs/PLAYBOOK_DEVIATIONS.md`.

---

## 3. The keystone grain

> **`BUSINESS_REQUIREMENT` — one row per to-be process node.**

A **process node** is the lowest node of its BFC branch (`bfc_node.is_process = TRUE`, D-23). It
sits at level 3, 4 or 5 (A-47), an L5 node is always one (A-54), and it has no children. A project
holds a **to-be** chart and, optionally, an **as-is** chart (`bfc_node.bfc_set_code`, D-47). A
to-be process node → BR is **1:1** (D-2, D-23, S7-2), enforced by the partial `UNIQUE (bfc_node_id)
WHERE is_active`, by a composite FK that accepts only an active process node, and by a generated
`'TO_BE'` column with a composite FK that refuses a BR on an as-is node. As-is processes carry no BR.

Everything downstream anchors here: Function Requirements serve BRs directly (D-52), Solutions
answer BRs, Issues are raised against BRs, Data Entities attach to BRs with a CRUD use (licensed by
the step's own I/O, D-24), a to-be process's RACI is its BR's (D-64), and a baseline freezes the BR
set.

One BR may lead to **many** Function Requirements, and one FR may serve many BRs, through the stored
link `BR_FUNCTION_REQUIREMENT` (D-52). A Solution is optional: an FR may carry one solution tag, which
decides where its effort counts.

Grain of every other table, one sentence each:

| Entity | One row per… |
|---|---|
| `CLIENT` | client organization FTC has engaged with |
| `PROGRAM` | named group of related projects for one client (D-32) — a **roll-up grouping, not a data layer and not an access scope** (D-40): it holds no scope of its own and is never baselined |
| `PROJECT` | transformation project — the scoping key on every business table. Nothing is shared between projects, even within one program (D-32). Carries `is_restricted` (OR-6, D-62), `data_model_depth` (D-39) and the FTE basis — working days per year and hours per working day, 240 × 8 by default (D-67, S13-1) |
| `PROJECT_DFD_RULE` | (project × chart × required DFD element) — what makes a process's DFD complete in that chart; a live row means required, a retired row not (D-70, S13-1) |
| `PROJECT_COMPONENT` | (project × component) switched on for that project — a live row means on, a retired row off (D-37) |
| `PROJECT_TEMPLATE_COMPONENT` | (project template × component) — a global starting set, copied once into `PROJECT_COMPONENT` at project creation (OR-3) |
| `BFC_NODE` | business function at one level (1–5) in one chart (`TO_BE` / `AS_IS`, D-47) of one project. `is_process` marks the lowest node of a branch — a **process node** (L3–L5, D-23), which has no children. A process carries **one performer** (org unit, org role, application or AI, or none yet) and its optional **volume figures** (runs per period, transactions per run with a unit, seconds per transaction, D-67) as columns on the row (D-46) |
| `BFC_NODE_DATA_ENTITY` | (process node × data entity × direction) — *that* data flows into or out of a step. **The one record of a step's I/O** (D-24): the DFD, the flow file and BR CRUD all read it |
| `BFC_NODE_ORG_ROLE` | (**as-is** process node × org role × RACI code) — who does what on an as-is step. A to-be process's roles are its BR's (`BR_ORG_ROLE`, D-64). The code's **behaviour** (RESPONSIBLE, ACCOUNTABLE …) is copied onto the row and FK-verified (Q7) |
| `BFC_NODE_FLOW` | **retired** (D-38): SELECT-only history, no new rows. Order between processes is derived from their inputs and outputs |
| `PROCESS_TRIGGER` | named time or event trigger in one project ("Month-end close", "Customer calls"), shared by both charts (D-49) |
| `BFC_NODE_TRIGGER` | (process node × trigger) — this trigger starts this process (D-49) |
| `EXTERNAL_ENTITY` | party outside the client organisation that exchanges data with the client's process steps (Customer, Bank, Regulator, Supplier), within one project — `EXT-0001` |
| `BFC_NODE_EXTERNAL_FLOW` | (process node × external entity × direction × data entity, nullable) — "Customer → order data → Receive order" |
| `BUSINESS_REQUIREMENT` | **one to-be process node** — 1:1 (D-2, D-23, S7-2). Its BR number is how imports identify the step (R2-D1) |
| `DATA_ENTITY` | logical data entity within one project, shared by both charts (D-47) |
| `DATA_FIELD` | logical field within one data entity. A partial list (keys and key attributes) is normal; type optional (D-26); how much is expected follows the project's data model depth (D-39). FK fields are grouped into relationships by `fk_group_no` |
| `BR_DATA_ENTITY` | (BR × data entity × CRUD) — *what is done* to that data. Direction is generated from CRUD, and the row must be licensed by a matching step I/O row on the BR's node (D-24) |
| `BR_ORG_ROLE` | (BR × org role × RACI code) — the RACI of a to-be process (D-64); behaviour copied as on `BFC_NODE_ORG_ROLE` |
| `BR_REQUIREMENT_LINE` | numbered requirement statement within one BR (`BR-0043.3`), with a kind and an optional MoSCoW priority (D-59, S11-1) |
| `BR_DATA_FIELD` | (BR × data attribute × CRUD) — which attributes the BR uses and how, licensed by the BR's entity-level CRUD row (D-60b, S11-1) |
| `BR_SYSTEM_FLOW` | (BR × data entity × from-application × to-application × kind) — data the BR needs copied from one system to another, as a business statement; the kind is ongoing integration or one-off migration (D-61, S11-1, S11-2) |
| `SOLUTION` | transformation answer within one project, in one of five categories |
| `BR_SOLUTION` | (BR × solution) pairing — which answers address which requirement |
| `FUNCTION_REQUIREMENT` | system function to be built within one project, of one FR type, carrying **zero or one** solution tag (D-27, D-28, D-52) |
| `BR_FUNCTION_REQUIREMENT` | (BR × FR) pairing — which function requirements serve which requirement. **The primary BR → FR mapping** (D-52) |
| `FR_BFC_NODE` | **retired, never built** (SC-3): the BR ↔ FR link (D-52) carries that coverage. No table |
| `FR_INTERFACE` | interface-type FR (behaviour INTERFACE) — its source and target application, pattern, method, frequency. 1:0..1 with the FR; identity is the FR number |
| `FR_INTERFACE_DATA_ENTITY` | (interface FR × data entity) — what one interface carries |
| `APPLICATION` | application or technology in one project's landscape (as-is / to-be / both) |
| `APPLICATION_SOLUTION` | (application × solution) — what delivers this answer (to-be) |
| `APPLICATION_BFC_NODE` | (application × as-is process node) — a system that supports the step's performer today |
| `STAKEHOLDER` | named client-side person in one project (business user or BPO) |
| `ISSUE` | issue raised within one project |
| `ISSUE_BR` | (issue × BR) pairing |
| `ORG_UNIT` | client organizational unit (dept/division/section) within one project |
| `ORG_ROLE` | role played within one client org unit |
| `EFFORT_RATE` | (project × FR type × complexity) → standard man-days — the rate card. **Audited and frozen with each baseline** (R2-D7) |
| `BENEFIT` | quantified benefit within one project, with a measure and a target |
| `BENEFIT_SOLUTION` | (benefit × solution) — which answers deliver which benefit |
| `RISK` | risk within one project — something that might happen |
| `CHANGE_REQUEST` | one proposed change to a frozen baseline, priced before decision |
| `CR_IMPACT` | (change request × impacted object) — the traced blast radius of one CR |
| `DECISION` | one recorded decision: what, who, when, against which analysis |
| `PHASE` | delivery wave within one project |
| `SOLUTION_PHASE` | (solution × phase) assignment |
| `SOLUTION_DEPENDENCY` | (solution × prerequisite solution) |
| `WBS_ITEM` | one imported MS Project task line in one project, keyed by its MS Project Unique ID (D-33, Q13). Schedule fields are owned by MS Project; VB edits only the Phase / Solution links and records progress against it (D-41). **Not baselined** |
| *WBS progress update* | one dated progress record against one WBS line — % complete, actual start and finish, status, comment (D-41). Never overwritten. Named and modelled by `apple` when the WBS wave is specced (SC-4) |
| `CONTROL_RULE` | (project × analysis) → threshold, owning role, escalation path |
| `BASELINE` | frozen version of one project's scope at one point in time |
| `DIAGRAM_LAYOUT` | (project × diagram type × scope × diagram object) → saved position and size, for the ERD and the DFD. Presentation, **not scope — not baselined** |
| `baseline_*` | one live row as it stood at one baseline freeze, for every table in `FREEZE_SET` whose component gate was open (D-37, S8-1) |
| `BASELINE_EFFORT_RATE` | one rate-card cell (FR type × complexity → days) as it stood at one freeze — the rate card a baseline was priced on (R2-D7) |
| `APP_USER` | person who can log into Value Bridge — a platform admin, or staff of kind USER or VIEWER (D-40) |
| `PROJECT_MEMBER` | one membership period of one user on one project, at EDIT or VIEW. It decides access only while the project is restricted (OR-6, D-62) |
| `USER_ACCESS_GRANT` | **retired** (D-40): SELECT-only history of the former one-grant model, no new rows |
| `IMPORT_BATCH` | one uploaded file — an `.xlsx` sheet (incl. an MS Project WBS export) or a `vb-process-flow/2.0` JSON — awaiting validation, review and commit |
| `IMPORT_ROW` | one staged sheet row or one staged JSON object (step, I/O, performer, trigger, external party, WBS line …), with its verdict, errors and warnings. Purged 90 days after upload (Q14) |
| `PROJECT_SEQUENCE` | (project × number series) counter — DE, BR, FR, ISSUE, SOL, BEN, RSK, CR, DEC, EXT. **All ten seeded at project creation** (R2-D14) |
| `CODE_MASTER` | one configurable lookup value, in one category, in one scope |
| `AUDIT_EVENT` | one recorded security-relevant action (login, membership, restriction, component change, freeze) |

---

## 4. Business Requirement — the grid

The entity × function × logic grid. `Use` is C / R / U / D. Manual steps are marked
`(manual)` — they are part of the blueprint even though no code runs.

**Components (D-37).** A project uses a chosen set of components (§4.7 `set_components`). A write to
an off component is refused with **409 `COMPONENT_OFF`** after the 404 and 403 checks; reads stay open
and the UI hides the component. The rows below name their component where one applies. Always on:
the to-be BFC, business requirements and their CRUD, step I/O, RACI links, data entities and fields,
the org chart, external entities, stakeholders.

### 4.1 Business Function Chart (scope area 1)

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `create_bfc_node` | `BFC_NODE` | C | In a named chart (`TO_BE`, or `AS_IS` with the AS_IS component on). Reject if parent is L5 (max depth), if level ≠ parent.level + 1, if the parent is in another chart, or **if the parent is a process** (D-23 — a process has no children). Name unique among live siblings, normalised (Q1). Derive `level`, next `seq_no` within parent. `is_process` defaults to TRUE at L5 and may be set at L3–L4 → one BFC node row |
| `create_bfc_node` | `BFC_NODE` | R | Read parent + siblings to compute `seq_no` and the hierarchical code |
| `generate_bfc_code` | `BFC_NODE` | R | Walk ancestors, zero-pad each `seq_no` to 2 → dotted code `01.02.03.04.05`, unique per chart. **Computed at save, stored** (§9.8) |
| `reorder_bfc_node` | `BFC_NODE` | U | Re-sequence siblings, then recompute code for every shifted sibling **and all their descendants** in one transaction, in two phases (S1-2) |
| `mark_process` | `BFC_NODE`, `BUSINESS_REQUIREMENT` | U/C | **D-23.** Promote a childless L3–L5 node to a process; **a to-be node gets its BR in the same transaction** (S7-2). Demote one. **Demotion is refused with 409 naming every blocker** — an active BR, step I/O, step roles, external flows, as-is applications, triggers, the performer, a data-processing description, or volume figures (S13-1). **VB never retires them itself** (R2-P5, Q4); the consultant retires each, then demotes. Every step-level fact is also guarded in the DB (§5.4.7) |
| `describe_process` | `BFC_NODE` | U | Process nodes only. Store the data-processing description, written system-agnostic. Reject on a non-process node. A box's own description (`purpose_desc`) is shown as its **Purpose** on L1–L4 boxes; on a process, Purpose and Data processing sit together in the panel's collapsed Description section (S-P) |
| `set_process_volume` | `BFC_NODE` | U | **D-67, S13-1.** EDIT, process nodes only (422 otherwise), either chart (an as-is node needs AS_IS). All optional: how often it runs (`runs_per_period` + period DAY / WEEK / MONTH / QUARTER / YEAR, both or neither), transactions per run (`transactions_per_run`, with an optional unit from `TRANSACTION_UNIT`, sent as a code), and handling time per transaction in **seconds** (`seconds_per_transaction`, to the millisecond, so an automated 0.3 s step and a manual 6-minute one both fit; the screen accepts minutes or seconds). Each figure ≥ 0 and under a service cap (1,000,000 runs per period, 100,000,000 transactions per run, 86,400 s); more decimals than stored → 422. `row_version` checked. **A body carrying hours or FTE → 422** (VB law 6). Audit `PROCESS_VOLUME_SET {from, to}`. No component of its own (Q-10) |
| `derive_volume` | `BFC_NODE`, `PROJECT` | R | **D-67.** On every read of a process, never stored: `annual_hours = runs × periods_per_year × transactions × seconds / 3600`, `fte = annual_hours / (working_days_per_year × hours_per_working_day)`. DAY counts the project's working days (240 by default), WEEK 52, MONTH 12, QUARTER 4, YEAR 1. Any input missing → both `null` with the missing fields named, never guessed |
| `set_fte_basis` | `PROJECT`, `AUDIT_EVENT` | U | **D-67, Q-7.** Platform admin (`project_ctx("ADMIN")`). Working days per year (1–366, default 240) and hours per working day (0.25–24, default 8.00); 240 × 8 = 1,920 hours per FTE. `row_version` checked; audit `PROJECT_FTE_BASIS_CHANGED {from, to}`. No process row changes |
| `volume_summary` | `BFC_NODE` | R | **D-67, Q-9, Q-28.** VIEW. Per chart, annual hours and FTE per L1 and L2 area, as-is beside to-be — the time saved per area. **Areas match when both chart code and normalised name agree**; anything else is listed unmatched with its reason (`CODE_SAME_NAME_DIFFERS`, `NAME_ELSEWHERE` — "probably reordered", `ONLY_AS_IS`, `ONLY_TO_BE`) and never summed against the other side. Processes with incomplete volume are counted and listed per area, never guessed |
| `link_bfc_data_entity` | `BFC_NODE_DATA_ENTITY` | C/D | Process nodes only. Attach 0..N input and 0..N output data entities — the node states *that* data flows; the BR states *what is done to it* (§5.4.2). **The one record of a step's I/O** — the DFD, the flow file and the BR all read it (D-24). Written only through `step_io.ensure_step_io`. **Delete refused (409) while a BR CRUD or an external flow depends on the row, naming each** (R2-D13) |
| `link_bfc_external_flow` | `BFC_NODE_EXTERNAL_FLOW` | C/D | **D-24a.** Component: the chart's DFD (TO_BE_DFD or AS_IS). A process step exchanges data with an external party: (step × external entity × direction × data entity, optional). **When a data entity is named, the matching step I/O is ensured in the same transaction through the same `ensure_step_io` helper as BR CRUD** (R2-D13) — an inbound flow needs a step input, an outbound one a step output |
| `create_external_entity` | `EXTERNAL_ENTITY` | C/U/D | Next per-project sequence → `EXT-0001`. Name (unique among live parties, S1-6), kind (CUSTOMER / SUPPLIER / BANK / REGULATOR / PARTNER / OTHER), description |
| `link_bfc_role` | `BFC_NODE_ORG_ROLE` | C/D | **As-is processes only** (D-64). On a to-be process → 409 "Roles of a to-be process are recorded on its requirement" (§4.3 `link_br_role`); the database refuses a live step role on a to-be step. Attach client roles with a RACI participation type. **Rules key on the type's behaviour, not its letter** (R2-D9, Q7): at most one ACCOUNTABLE per step; several RESPONSIBLE are normal (D-46). A RASCI or RAPID project renames or adds codes and keeps the rule |
| `link_bfc_application` | `APPLICATION_BFC_NODE` | C/D | Components APPLICATION and AS_IS. **As-is processes only** (422 on a to-be process, whose systems come from BR → Solution → Application, D-22, D-8): a system that supports the step's performer today. A `TO_BE` application here warns and is allowed (S6b-4) |
| `create_bfc_node` | `BUSINESS_REQUIREMENT` | C | **When the new node is a to-be process:** auto-create its single BR in the same transaction (D-2, D-23, S7-2) |
| `retire_step_with_dependents` | the process node + its owned set | U | **S3-SR — the one cascade in VB.** Preview lists the owned set (the step's BR and that BR's CRUD, roles, solution links and FR links; the step's I/O, roles, external flows, as-is applications and trigger links) and every other blocker, with a `confirm_hash`. Confirm retires them all in one transaction with one `deleted_at` and one `STEP_RETIRED_WITH_DEPENDENTS` audit event, which is the undo key. Restore brings back exactly that set, all or nothing, refusing while any other parent is still inactive (A-SR-5) (`docs/step_retire_spec.md`, S5-1, S6b-1, slice10b Q-12) |
| `(manual)` workshop capture | — | — | Consultant elicits the L1–L5 chart with the client in workshop; VB is the system of record afterwards, not during |

### 4.1a The DFD — the one process diagram (D-31, D-38, D-46, D-47, D-49, D-54, D-55, D-65, D-68…D-70)

**There is no separate business process flow: every process is shown in the DFD** (D-38). The DFD
is generated from the BFC, the step I/O, external flows, triggers and performers (D-31). An editor may
also **draw a connection on the canvas**; it writes the same step I/O, external-flow or trigger row the panel
writes, through the same writer, so the diagram stays generated from one record (D-65). A project may hold two charts, each with its own DFD: a **to-be** chart, and an optional
**as-is** chart (D-47). The data-entity catalogue, external entities, triggers, the org chart and
applications are shared by both, so as-is and to-be compare on the same `DE-` numbers. Component:
TO_BE_DFD for the to-be chart, AS_IS for the as-is chart and its DFD.

**Order is derived from data, never stored** (D-38). Process B follows A when B reads a data entity
A writes. A branch is two different outputs ("Approved order" / "Rejected order") feeding different
processes; a loop is a later process writing what an earlier one reads. Explicit order arrows would
duplicate what the inputs and outputs already say. When a diagram has no derived order (a project whose
rule drops the data elements, or a diagram with no data yet), its processes are ranked in **chart order** —
`seq_no` under each parent, in `hier_code` order — drawn without arrows (D-70, Q-3 option A). `BFC_NODE_FLOW` is
retired: SELECT-only history, no new rows, never read by any diagram or report.

**Each chart's DFD rule decides what makes a process complete** (D-70, S13-1). The elements are a fixed,
code-defined list:

| Element | Met when the process has… |
|---|---|
| `STARTED` | a live step input, a live inbound external flow or a live trigger link (D-49). **Always required** — a process nothing starts cannot be placed |
| `DATA_IN` | a live step input (a data entity) |
| `DATA_OUT` | a live step output (a data entity) |
| `ORDER` | a derived order link to at least one other process of its chart (it reads what another writes, or writes what another reads); a one-process chart passes. Selectable only with `DATA_IN` and `DATA_OUT`, because order is data |
| `EXTERNAL` | checked **per diagram**, not per process: the diagram has at least one outside party. Off by default; it never changes a process's light and shows on the DFD index only (Q-6, Q-16) |

One rule **per chart** (Q-15), so a rough as-is chart never blocks the to-be freeze. A new project starts with
the recommended set — to-be: `STARTED`, `DATA_IN`, `DATA_OUT`, `ORDER`; as-is: `STARTED`. **A chart with no live
rule rows reads as `STARTED` + `DATA_OUT` — never as "nothing required"** (fails closed), and the consistency line
`project_without_dfd_rule` refuses the freeze until an admin saves one. A requirement for a trigger as such is not
an element: `STARTED` covers it (Q-14).

**The readiness light** (D-68, Q-13) on every process of a chart whose DFD component is on: **red** — a rule
element is missing, so the process **blocks the freeze**; **yellow** — the rule is met but a recommended element
is missing; **green** — complete. Always colour **plus** icon **plus** text ("Ready", "Partly", "Not ready"),
never colour alone (D-50). The fields the rule needs carry a "DFD" mark (D-69), drawn from the rule's element
list, so the marks change when the rule changes.

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `copy_bfc_set` | `BFC_NODE`, `BUSINESS_REQUIREMENT`, `BFC_NODE_DATA_ENTITY`, `BFC_NODE_EXTERNAL_FLOW`, `BFC_NODE_TRIGGER`, `BFC_NODE_ORG_ROLE`, `BR_ORG_ROLE`, `APPLICATION_BFC_NODE` | C | **D-47, Q-24.** Start one chart by copying the other, whole tree, **into an empty chart only** (409 otherwise). Component AS_IS. Preview → confirm by hash. Copies nodes (fresh ids, same `hier_code`), performers, step I/O, external flows and trigger links. Roles move with the change of home: as-is step roles → the new to-be BR's roles; to-be BR roles → the new as-is step roles (D-64). Supporting systems copy to-be → as-is only. **As-is → to-be mints a new DRAFT BR per process** (numbers at save); BR CRUD, solutions and FRs are never copied. One `BFC_SET_COPIED` audit event holds the old → new id map; no provenance column. Every row made live passes its component check |
| `set_performer` | `BFC_NODE` | U | **D-46.** One performer per process: `ORG_UNIT` (a department), `ORG_ROLE` (a position), `APPLICATION` (an IT system) or `AI` (with a label). The body sends codes, never ids. Refuses a retired target. A `TO_BE` application performing an as-is process warns and is allowed. **Zero is legal**: the process is drawn in the "unassigned" lane and listed as `no_performer`, a warning that does not block the freeze. Retiring an org unit, role or application that performs a live process → 409 naming the processes. Audit `PERFORMER_SET`. **Recordable whatever the DFD setting** (S10c-2): gated by the chart itself (AS_IS for the as-is chart, none for the to-be chart), never by TO_BE_DFD |
| `maintain_process_trigger` | `PROCESS_TRIGGER` | C/U/D | **D-49.** Project-wide catalogue: name (unique among live triggers), kind `TIME` / `EVENT`, `schedule_note` (TIME only), description. No number series. Writable when either DFD component is on. Retire with live links → 409 naming the processes; restore checks the name is free |
| `link_process_trigger` | `BFC_NODE_TRIGGER` | C/D | Process nodes only. This trigger starts this process. Relinking restores the old row (S1-7). Owned by the step (retires and restores with it). Component: the chart's DFD |
| `generate_dfd` | `BFC_NODE`, `BFC_NODE_DATA_ENTITY`, `BFC_NODE_EXTERNAL_FLOW`, `BFC_NODE_TRIGGER`, `PROCESS_TRIGGER`, `DATA_ENTITY`, `EXTERNAL_ENTITY`, `BUSINESS_REQUIREMENT`, `APPLICATION`, `DIAGRAM_LAYOUT` | R | **Returns a graph, not a picture** (D-21). Given any live non-process node of either chart: its process descendants in the same chart; **one swimlane per performer** (org units, then roles, then applications, then AI, then unassigned); data stores; external parties; triggers as start symbols; flows of kind STORE, EXTERNAL and TRIGGER; **`order`** derived as above; a left-to-right **rank** from the strongly connected components of `order`, so loops are legal and layout terminates — or, when `order` in scope is empty, from chart order (Q-3 option A); **boundary** stubs for stores written or read by a process of the same chart outside scope; cross-area stores; the completeness gaps of the processes in scope; saved positions. **`systems`** on a process box: as-is ← `APPLICATION_BFC_NODE`; to-be ← BR → `BR_SOLUTION` → `APPLICATION_SOLUTION`, only when SOLUTION and APPLICATION are on (OR-2), otherwise empty. A performer of kind APPLICATION is the lane, not a box entry |
| `dfd_index` | `BFC_NODE` | R | **D-54.** The DFD screen: one DFD per **direct parent of processes** (in a five-level chart, the L4s), listed flat with code, name, process count and readiness counts ("12 ready · 3 partly · 1 not", D-68), plus the per-diagram `EXTERNAL` check when the rule holds it; searchable, no tree; selecting one draws it. Wider roll-up diagrams (an L2 or L3 with every process below) open from the function chart |
| `export_dfd` | — | R | The DFD graph as Mermaid text: one subgraph per lane, triggers as start nodes, `order` drawn dashed only on request. **Every label goes through `escape_mermaid()`**, and `_guard` ends the exporter (R2-S7, §7.12b) |
| `process_completeness` | `BFC_NODE`, `BFC_NODE_DATA_ENTITY`, `BFC_NODE_EXTERNAL_FLOW`, `BFC_NODE_TRIGGER`, `BUSINESS_REQUIREMENT`, `PROJECT_DFD_RULE` | R | **D-38, D-49, D-70.** Every process must meet **its chart's DFD rule** (above). A missing rule element is a warning on the editing screens and **blocks the baseline freeze** (`FREEZE_BLOCKING_WARNINGS`: `process_missing_input` = STARTED, `process_missing_output` = DATA_OUT, `process_missing_data_in`, `process_missing_order`, and the chart-level `diagram_missing_external`); an element outside the rule is never reported as a warning, only as information on the DFD's warnings panel. **The rule applies only to a chart whose DFD component is on** (S7-3); a requirements-only project is never blocked by it. Also lists `no_performer` (warning), `step_without_br` (to-be only), `crud_without_io` and `ext_without_io` (must be 0), `live_link_on_retired_step` (must be 0), and `project_without_dfd_rule` and `dfd_rule_invalid` (must be 0) |
| `dfd_readiness` | `BFC_NODE`, step links, `PROJECT_DFD_RULE` | R | **D-68.** One owner (`process_flow.readiness`), the same predicates as `process_completeness`, so the light and the freeze never disagree. Per live process of a chart whose DFD is on: each rule element met or missing → the light (red / yellow / green, above) and `dfd_missing` (element codes). Shown on every process row of the function chart, in the process panel header and as counts on the DFD index; a "Not ready only" filter lists every process that is not Ready (red and yellow). A chart with its DFD off has no light. The marks (D-69) read only these codes, never whether a tile looks empty. Every writer of step I/O, external flows, trigger links, BR CRUD, step retire / restore, make-process and component toggles refreshes it |
| `get_dfd_rule` | `PROJECT_DFD_RULE` | R | **D-70.** VIEW. Per chart: the required elements, whether the rule applies (DFD on), which elements are locked and recommended; the catalogue with plain descriptions |
| `preview_dfd_rule` | `PROJECT_DFD_RULE`, `BFC_NODE` + step links | R | **D-70.** Platform admin. For a proposed set on one chart: how many processes would be red / yellow / green and how many would **block the next freeze**, with a digest. No write |
| `set_dfd_rule` | `PROJECT_DFD_RULE`, `PROJECT`, `AUDIT_EVENT` | C/U | **D-70, Q-5.** Platform admin (`project_ctx("ADMIN")`), as the data model depth. Body: chart, element codes, the project's `row_version`, the preview digest (409 if either is stale). `STARTED` cannot be dropped and `ORDER` needs `DATA_IN` and `DATA_OUT` (422). Dropped elements retire their rows; re-added ones restore them (S1-7). Audit `PROJECT_DFD_RULE_CHANGED {bfc_set_code, from, to, would_block}`. No component (a project setting) |
| `draw_dfd_connection` | `BFC_NODE_DATA_ENTITY`, `BFC_NODE_EXTERNAL_FLOW`, `BFC_NODE_TRIGGER` | C | **D-65.** EDIT, on a live diagram of a chart whose DFD is on (the canvas exists only there). Each line keeps its panel route's gate: a step input/output the function chart's (BR CRUD writes the same row), an external flow and a trigger the chart's DFD. Store → process or process → store writes a step input or output through **`step_io.ensure_step_io`**; party ↔ process uses the external-flow writer (asking for a data entity or a flow label); trigger → process uses `trigger.link`. Process → empty canvas opens a picker: an existing data entity, or a **new** one created there with its `DE-` number at save (Q-12). An existing row → "Already on the diagram", no write. Invalid pairs (store → store, party → store, a trigger to anything but a process) are refused in the browser and again by the server. **Drawing never writes BR CRUD** (Q-11): the CRUD grid shows the I/O as "On the diagram, not in the requirement yet — pick C, R, U or D" |
| `draw_hand_off` | `BFC_NODE_DATA_ENTITY` ×2 | C | **D-65.** Process A → process B: the editor picks the data entity A hands to B; **one transaction** writes A's output and B's input through `ensure_step_io`, and the derived order arrow appears by itself. Both live processes of the same project (404 if not visible) and **the same chart** (422 "Diagrams never cross charts"). The only new write route of D-65 |
| `remove_dfd_flow` | the three link tables | D (soft) | **D-65.** Only STORE, EXTERNAL and TRIGGER flows are removable, each backed by exactly one row, through the existing unlink route. **Derived order arrows cannot be selected for removal**; they change only when the data behind them changes. A step I/O a BR CRUD or an external flow depends on stays (409 naming them; the canvas links to the requirement). No keyboard delete |
| `save_diagram_layout` (DFD) | `DIAGRAM_LAYOUT` | C/U | As §4.2: positions of processes, stores, externals and triggers, last write wins per object (D-30). Diagram types are ERD and DFD; a `PROCESS_FLOW` position is refused (S7-5) |
| `download_flow_schema` | — | R | **D-25.** The JSON Schema for `vb-process-flow/2.0`, a worked example, and the **AI conversion prompt pack**: instructions an AI follows to turn a PowerPoint, BPMN or Visio flow into a valid file. **The pack names the approved services — Claude or Microsoft Copilot, under FTC's own accounts only — and opens with the personal-data removal step** (D-36) |
| `export_process_flow_json` | `BFC_NODE`, `BUSINESS_REQUIREMENT`, `BFC_NODE_DATA_ENTITY`, `BFC_NODE_EXTERNAL_FLOW`, `BFC_NODE_TRIGGER`, `PROCESS_TRIGGER` | R | The processes under one parent node as `vb-process-flow/2.0`: per step its `br_number` (to-be only — its identity, R2-D1), current `hier_code` (a cross-check), `row_version` (R2-D5), name, description, **performer**, **inputs** and **outputs**, **triggers** and **external flows**. **No edges and no lanes** (D-38, D-46). An edited file re-imports as an update and a stale step is caught |
| `validate_process_flow_json` | `IMPORT_BATCH`, `IMPORT_ROW` | C | **The anchor node and the mode come from the route, chosen in the UI** (R2-P3); the chart is the anchor's. Parse under the JSON caps (§7.12a) and check the format version; a `1.0` file is refused ("re-export from VB"). **Resolve each to-be step by `br_number`** (UPDATE), cross-checking `hier_code` ("moved since export", R2-D1) and `row_version`. A step with neither — and every as-is step, which has no BR number — is **matched by normalised name to an active process child of the anchor** (UPDATE with a warning, R2-P1, Q1, SC-6); otherwise it is an INSERT. Resolve data entities by `DE-` number or exact name, performers by code, triggers by name, external parties to `EXT-` rows. In replace mode, stage a **RETIRE** row per omitted step I/O and trigger link, and a **KEPT** row with a warning for I/O a BR CRUD or external flow depends on (R2-P4). **Warn and still import (D-55):** a process with no input/trigger or no output, an unconnected process, an unknown data entity name (created as a new entity, listed in the preview), an unknown trigger (added to the catalogue), an unknown performer (left blank), missing descriptions. **Errors block only what would damage data:** an unreadable file, a wrong format version, a file for a different anchor or mode than chosen, a stale `row_version`, and a step whose identity is wrong (unknown or out-of-scope BR number, moved `hier_code`, `hier_code` without `br_number`, two steps on one process, duplicate names — SC-6). **Nothing written to a business table** |
| `commit_process_flow_json` | `BFC_NODE`, `BUSINESS_REQUIREMENT`, `BFC_NODE_DATA_ENTITY`, `BFC_NODE_EXTERNAL_FLOW`, `BFC_NODE_TRIGGER`, `PROCESS_TRIGGER`, `DATA_ENTITY`, `EXTERNAL_ENTITY` | C/U | One transaction, all-or-nothing, the same six properties as §7.11. Component: the anchor chart's DFD. **Refused unless `acknowledged_inserts` equals the insert count whenever there are inserts, and `acknowledged_retires` equals the retire count whenever there are retirements** (R2-P1, R2-P2). New steps are process nodes; a new to-be step gets its BR (D-2). The file's performer **replaces** the step's performer. `merge` never retires. **`replace` retires only step I/O and trigger links (Q5)** — never steps, BRs, performers, roles, external flows, or I/O a BR CRUD or external flow depends on. The gaps imported stay visible as the DFD's warnings panel; an incomplete DFD can be imported, not frozen (D-55) |
| `(manual)` AI conversion | — | — | The consultant removes personal data from the source slide or BPMN export, then gives it and the prompt pack to **Claude or Microsoft Copilot under FTC's own account — no other service, no personal account** (D-36, R2-S6), and uploads the JSON it returns. **VB itself never sends client content to an AI service** (A-51) |

### 4.2 Data Entity management (scope area 3)

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `create_data_entity` | `DATA_ENTITY` | C | Take next per-project DE sequence at commit → `DE-0001`. Name unique among live entities in the project (S1-6) |
| `create_data_entity` | `PROJECT_SEQUENCE` | U | Atomic increment of (project, `DATA_ENTITY`) counter. Row-locked; gap-tolerant |
| `manage_data_fields` | `DATA_FIELD` | C/U/D | Field name unique among live fields of the DE. `is_primary_key` requires `pk_ordinal`; composite PKs allowed. **Logical, and partial is normal (D-26):** data type is optional, and a DE may list only its keys and key attributes. `is_mandatory` (yes / no / unknown) feeds ERD cardinality. Extra fields are always accepted, whatever the project's depth (D-39) |
| `manage_data_fields` | `DATA_FIELD` | U | If `is_foreign_key`, `fk_target_entity_id` is mandatory and must be a DE in the **same project** — cross-project FK is rejected |
| `validate_entity_model` | `DATA_ENTITY`, `DATA_FIELD`, `PROJECT` | R | Report DEs with no PK field, FK fields pointing at a DE with no PK, and **DEs with no fields at all**; under data model depth `FULL` also DEs with keys but no other attributes (D-39; never under `KEYS_ONLY`) → validation warning list. Warnings, never blocks — a partial logical model is the expected state during an assessment. A freeze with entities that have no fields warns and proceeds (S4-12) |
| `generate_erd` | `DATA_ENTITY`, `DATA_FIELD`, `DIAGRAM_LAYOUT` | R | **D-29.** Entities as boxes (PK, FK and attribute rows), one relationship per FK field → parent entity. Cardinality: parent side `1` if the FK is mandatory, `0..1` if optional or unknown; child side `many`, or `1` only when the FK field set equals the child's PK field set (`DATA_FIELD` models no alternate keys). Saved positions from `DIAGRAM_LAYOUT`. Filter by **subject area** = the entities a BFC L1/L2 branch reads or writes. The "attributes missing" hint follows the project's depth (D-39) |
| `export_erd` | — | R | The ERD as Mermaid `erDiagram` text, and as PNG/SVG from the canvas |
| `save_diagram_layout` | `DIAGRAM_LAYOUT` | C/U | **D-30.** Upsert (diagram × scope × object) → x, y, for the listed objects only. Last write wins, per object — two consultants dragging different entities never conflict, and a lost position is not a data-integrity event. A separate audited reset clears one diagram's positions (S2-6) |

### 4.3 Business Requirement (scope area 2)

The BR is part of the business function chart: it is read and edited from its process's panel, and
the BR page remains as a deep link (from FRs, solutions and the diff) under Business functions (D-53).
A to-be process and its BR are 1:1, so the process's **readiness light** (D-68, §4.1a) is the BR's; the fields
the chart's DFD rule needs carry the "DFD" mark with the note "Needed to complete the DFD" — on the BR page,
the CRUD grid header (DATA_OUT, and DATA_IN when the rule holds it) (D-69).

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `create_br` | `BUSINESS_REQUIREMENT` | C | Called only by `bfc.create_node` / `bfc.mark_process` / `copy_bfc_set` for a **to-be** process node. `UNIQUE (bfc_node_id)` makes a second BR on one node impossible (D-2), and the generated `'TO_BE'` FK makes one on an as-is node impossible (S7-2). Take next per-project BR sequence at commit → `BR-0001`. Starts DRAFT |
| `create_br` | `BFC_NODE` | R | Validate the node `is_process` and is to-be (also DB-enforced) |
| `update_br` | `BUSINESS_REQUIREMENT` | U | The consultant edits the BR that appeared with the step. `WHERE row_version = :v`; mismatch → 409 (D-6). **`BASELINED` / `SUPERSEDED` are set only by the baseline freeze**; `update_br` refuses them (422, S1-8). BR status is workflow, not hashed |
| `link_br_data_entity` | `BR_DATA_ENTITY` | C/U/D | One row per (BR × DE × **CRUD**). `crud_code` is in the key — one BR legitimately reads *and* updates the same entity. `direction` is a **generated column** (`R` → INPUT, else OUTPUT), so `(R, OUTPUT)` cannot be stored (§5.4.2). **D-24:** the matching step I/O row on the BR's process node is created in the same transaction if absent, so the BR and the DFD can never disagree |
| `read_br_attributes` | `BR_DATA_ENTITY`, `DATA_FIELD` | R | **D-60(a).** Each data entity linked to the BR expands to its live attributes — name, type, key, mandatory, in field order. Read-only. The "keys only" hint follows the project's depth (D-39) |
| `link_br_role` | `BR_ORG_ROLE` | C/D | **The RACI of a to-be process** (D-64). Attach client role(s) with a RACI participation type. **At most one role whose RACI behaviour is ACCOUNTABLE per BR** — keyed on behaviour, not on the letter `A` (R2-D9, Q7) |
| `link_br_solution` | `BR_SOLUTION` | C/U/D | Component SOLUTION. Many-to-many, with a `coverage_note` per pairing, edited in place (D-7, S5-3). A REJECTED solution can be linked; the link shows its status and coverage does not count it as an answer (S5-2). Owned by the BR: retires and restores with its step (S5-1) |
| `link_br_fr` | `BR_FUNCTION_REQUIREMENT` | C/U/D | **D-52 — the primary BR → FR mapping.** Component FUNCTION_REQUIREMENT only, so a project with SOLUTION off still maps BR → FR. One row per (BR × FR) with an editable `coverage_note`; relinking restores the old row (S1-7). FR fetched in the BR's project (404 otherwise). Linking an FR whose solution tag does not answer this BR is allowed, with the `fr_solution_outside_its_brs` warning. Owned by the BR: retires and restores with its step. Retiring an FR with live links → 409 naming the BRs (S10b-2) |
| `set_fr_solution_from_br` | `FUNCTION_REQUIREMENT` | U | Components FUNCTION_REQUIREMENT and SOLUTION (clearing needs FUNCTION_REQUIREMENT only). On a BR's FR row, pick which of **this BR's** live solutions the FR delivers, or none. Any other solution → 422 "SOL-0003 does not answer BR-0042. Add it to this requirement's solutions first"; **the server never creates a `BR_SOLUTION` as a side effect**. Uses the FR's `row_version` |
| `create_fr_from_br` | `FUNCTION_REQUIREMENT`, `BR_FUNCTION_REQUIREMENT` | C | Create an FR and link it to the BR in one transaction (slice10b Q-20) |
| `br_coverage_report` | `BUSINESS_REQUIREMENT`, `BR_DATA_ENTITY`, `BR_SOLUTION`, `BR_FUNCTION_REQUIREMENT`, `FUNCTION_REQUIREMENT` | R | BRs with no output DE; BRs with no solution; BRs with no FR (information — legal); **FRs with no BR link (warning, D-28 re-based on D-52)**; FRs with no solution (information); FRs whose tag answers none of their BRs (`fr_solution_outside_its_brs`, warning); FRs whose tag answers a BR they are not linked to (`solution_reach_without_link`, information — a hint, never a write); DEs referenced by no BR → the scope-gap list |

**The structured BR** (D-59, D-60b, D-61, S11-1; slice 11, `docs/slice11_schema.md`):

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `maintain_br_lines` | `BR_REQUIREMENT_LINE` | C/U/D | **D-59.** Numbered requirement lines under each BR — `BR-0043.3` — each with a kind (`BR_LINE_KIND`: Rule, Calculation, Validation, Output, Control; project-editable) and an optional MoSCoW priority (`BR_PRIORITY`; blank = not yet prioritised). **The line number is minted by the service at save** (max + 1 over all the BR's lines, retired included), kept for life and never reused or sent; display order (`seq_no`) is changed by dragging and is not a scope change. The BR's own priority is the highest of its live lines — derived, never stored. No component (a BR always exists). Owned by the BR: retires and restores with its step |
| `update_br` (structured) | `BUSINESS_REQUIREMENT` | U | `br_statement` stays editable as the BR's one-line headline. `business_logic` and `output_expectation` are **read-only legacy**: copied once, word for word, into one Rule line and one Output line per BR (priority blank, audit `BR_LINES_BACKFILLED`), never cleared or dropped; the panel shows non-blank legacy text collapsed as "Earlier free text" |
| `tick_br_attributes` | `BR_DATA_FIELD` | C/D | **D-60(b).** Which attributes the BR uses and how: one row per (BR × attribute × C / R / U) — **Delete stays entity-level**. **Licensed by the BR's entity-level CRUD row** (same BR, entity and CRUD, live), held by a composite FK, so an attribute tick can never outlive its entity tick. The CRUD grid saves entity and attribute ticks in **one request**; unticking an entity's action unticks its attributes on screen before Save. Unlinking an entity row that still has live attribute ticks any other way → 409 naming the attributes. Optional always: under `FULL` an entity row with no attribute ticked is information (`br_entity_without_attributes`), never a warning; under `KEYS_ONLY` nothing is shown. Retiring a data field a live BR uses → 409 naming the BRs. Relinking restores the old row (S1-7) |
| `state_br_system_flow` | `BR_SYSTEM_FLOW` | C/D | **D-61.** Component APPLICATION. "What data entity we copy from which system to which system": (BR × data entity × from-application × to-application), with a note; both ends from the Applications master list (D-56), never free text, and different. A flow of an entity the BR does not otherwise use is allowed, as information (`flow_entity_not_used_by_br`). Retiring an application or entity a live flow uses → 409 naming the BRs. Each flow is `INTEGRATION` (ongoing) or `MIGRATION` (one-off) (S11-2); both ends come from the one master list of systems, with no system of record per entity (S11-3) |
| `flow_coverage` | `BR_SYSTEM_FLOW`, `BR_FUNCTION_REQUIREMENT`, `FR_INTERFACE`, `FR_INTERFACE_DATA_ENTITY` | R | **Derived, never stored:** a flow is covered when the same BR links a live interface-behaviour FR with the same source and target that carries the entity. The panel shows "covered by FR-0031" or "no interface yet"; coverage reports list uncovered flows as information, as a warning when FUNCTION_REQUIREMENT is on, never a freeze block |
| `create_interface_fr_from_flows` | `FUNCTION_REQUIREMENT`, `FR_INTERFACE`, `FR_INTERFACE_DATA_ENTITY`, `BR_FUNCTION_REQUIREMENT` | C | Components FUNCTION_REQUIREMENT and APPLICATION. From one or more of a BR's flows **with the same source and target**: one transaction creates the interface FR, its interface detail, one carried entity per flow entity and the BR ↔ FR link; numbers minted at save |

Whether each data entity also names a master system (system of record) is an open question in the design
history §1.

### 4.4 Solution, Function Requirement and Applications (scope area 4, D-7/D-8/D-52)

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `create_solution` | `SOLUTION` | C | Component SOLUTION. Next per-project sequence → `SOL-0001`; name unique among live solutions. `category_code` from the system category `SOLUTION_CATEGORY` (projects cannot rename or retire it, S5-4): **ORG_AND_RULES / PEOPLE / PROCESS / DATA / TECHNOLOGY**. Starts PROPOSED |
| `create_function_requirement` | `FUNCTION_REQUIREMENT` | C | Component FUNCTION_REQUIREMENT. Next per-project sequence → `FR-0001`. `fr_type_code` from **`FR_TYPE`** (FORM / INTERFACE / REPORT / BATCH seeded; the project may rename, add or retire types — D-27). Names are not unique; a live duplicate under the same solution warns (S6a-2). First status SPECIFIED. **The solution tag is optional (D-28, D-52).** Warnings, never 422: `no_br` (no live BR link), `non_technology_solution`, `rejected_solution`, `duplicate_name` |
| `set_fr_solution` | `FUNCTION_REQUIREMENT` | U | Set or clear the FR's one solution tag from the FR register. **The tag must answer at least one of the BRs the FR serves** (a live `BR_SOLUTION` of one of them); an FR with no BR link may carry any live solution of its project, with `no_br`. The tag decides where the FR's effort counts, once. Later drift (an unlink, a step retire, a restore) is never refused and never auto-cleared: the response names the affected FRs and `fr_solution_outside_its_brs` reports them (slice10b §2) |
| `maintain_fr_types` | `CODE_MASTER` (`FR_TYPE`) | C/U | Per-project types, at EDIT. Each carries a **behaviour** ∈ FORM / INTERFACE / REPORT / BATCH / OTHER, which decides which detail panel the FR form shows and whether the FR appears on the interface list. A new type needs rate-card rows before its FRs can be priced (D-13). **When a project overrides a global type, the project's `EFFORT_RATE` rows and FRs are re-pointed to the override code in the same transaction**, so the rate-card lookup never silently misses (A-16). **A global type's behaviour is immutable once any FR or rate row references it → 409** (R2-D8, Q6): add a new type instead |
| `describe_interface` | `FR_INTERFACE`, `FR_INTERFACE_DATA_ENTITY` | C/U/D | Components FUNCTION_REQUIREMENT and APPLICATION. FRs whose type behaviour is INTERFACE only. Source application, target application (different, same project), pattern (PUSH / PULL / BIDIRECTIONAL), method (API / FILE / DB / MESSAGE / MANUAL), frequency, volume note, and the data entities carried, each with a note. One save covers the carried set and bumps the detail's `row_version`. Retiring an FR with live interface detail is refused until the detail is removed (S6b-3) |
| `interface_list` | `v_interface_list` | R | **D-27. Generated, never typed:** one row per interface FR — FR number, name, source → target, pattern, method, frequency, data entities and their notes, solution, BR(s) (through `BR_FUNCTION_REQUIREMENT`), status, effort. **Complete = source, target, method and at least one carried entity**; pattern and frequency optional (S6b2-1). Incomplete interfaces are listed as incomplete, not hidden. The pair filter matches direction as stored, BIDIRECTIONAL either way, and counts the interfaces it cannot match (S6b2-2, S6b2-3). Exportable to `.xlsx` |
| `link_fr_to_bfc_node` | `FR_BFC_NODE` | — | **Retired, never built** (SC-3). An FR reaches the chart through the BRs it serves (D-52); an FR for a whole area is linked to the BRs of that area's processes |
| `create_application` | `APPLICATION` | C | Component APPLICATION (needs no other component, S7-4). The project's application/technology catalogue. `lifecycle_code` ∈ AS_IS / TO_BE / BOTH. Codes upper-case, A–Z 0–9 `.` `_` `-`, unique and editable until a baseline freezes them; a code freed by a rename may be taken by another application; live names unique (S6b-2, S6b-6, S6b-7) |
| `link_application_solution` | `APPLICATION_SOLUTION` | C/D | Components APPLICATION and SOLUTION. **To-be allocation** — what delivers this solution. Rejected if the application's lifecycle is `AS_IS` |
| `solution_matrix` | `SOLUTION`, `BR_SOLUTION`, `BUSINESS_REQUIREMENT` | R | Solutions by category × BFC L1 area → *is this transformation actually balanced, or is it five technology answers and no org change?* |
| `application_gap_report` | `APPLICATION_BFC_NODE`, `APPLICATION_SOLUTION`, `BFC_NODE` | R | Per area, as-is support with no to-be allocation → the migration backlog. **The two charts are matched by area** — L1 / L2 chart code and normalised name agreeing, as the volume summary; unmatched areas are listed apart (SC-5). **The reason both links exist.** A `TO_BE` application linked as today's support does not count as today's support; it is listed on the informational line `as_is_support_by_to_be` (S6b-5) |
| `fr_traceability_matrix` | `BFC_NODE`, `BUSINESS_REQUIREMENT`, `BR_FUNCTION_REQUIREMENT`, `FUNCTION_REQUIREMENT`, `SOLUTION`, `APPLICATION` | R | Process step → BR → FR (through the direct link), grouped by FR type → the vendor-facing scope list. The Solution column is the FR's tag (blank allowed, flagged when it answers none of the FR's BRs); Application is the tag's live `APPLICATION_SOLUTION`. Untraced FRs listed in their own group at the end |

### 4.5 Issue Management (scope area 5)

Component ISSUE.

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `create_stakeholder` | `STAKEHOLDER` | C/U/D | Named client-side person: name, title, org unit, `is_bpo`. They have no login (D-4) |
| `raise_issue` | `ISSUE` | C | Next per-project sequence → `ISS-0001`. `severity_code`, `issue_type_code`, `status_code` from `code_master`. **`raised_by_stakeholder_id`** is the business user or BPO who raised it; **`recorded_by_user_id`** is the consultant, from the JWT (§9.2). The two are never the same person and are never conflated |
| `link_issue_br` | `ISSUE_BR` | C/D | Many-to-many — one issue may span several BRs |
| `resolve_issue` | `ISSUE` | U | Status → RESOLVED requires a non-empty `resolution`. Store `resolved_at`, `resolved_by` |
| `issue_dashboard` | `ISSUE`, `ISSUE_BR`, `STAKEHOLDER` | R | Open issues by severity × type, per BFC L1 area via the BR→BFC path, and per raising stakeholder |

### 4.5a Bulk upload / download (D-5)

Business users and BPO staff work in spreadsheets. Covers **Issues, Data Entities, Data Fields,
Business Requirements, Function Requirements** (D-28) and **WBS lines** (D-33), plus the
**process-flow JSON** of §4.1a (D-25), which shares the same pipeline. Six `.xlsx` column maps, one
staging model, one commit. Each target names its component, checked at validate and commit (DE, DF
and BR: none; FR: FUNCTION_REQUIREMENT; WBS: WBS; flow file: the anchor chart's DFD).

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `download_template` | — | R | Emit an `.xlsx` template per entity, with `code_master` values as dropdown validation so the returning file is already half-clean |
| `export_entity` | `ISSUE`, `DATA_ENTITY`, `DATA_FIELD`, `BUSINESS_REQUIREMENT`, `FUNCTION_REQUIREMENT`, `WBS_ITEM` | R | Current rows in template shape, including the business key (`ISS-0001`, `DE-0001`, `BR-0001`, MS Project Unique ID) and a **signed row token** (project, table, id, `row_version`) so a round-trip updates rather than duplicates (S4-11). FR exports carry `effort_days` as a **read-only** column (R2-D6). Every cell through `escape_cell()` |
| `validate_import` | `IMPORT_BATCH`, `IMPORT_ROW` | C | Parse → validate every row → stage. **Nothing is written to a business table at this step.** Row-level **errors** (block the batch) and **warnings** (shown, do not block), with the sheet row number; messages are objects `{code, column, message, params}` (S4-8). Duplicate keys in one file are caught before staging (S4-4). **A token row that no longer resolves to its live row is an error, never an INSERT**; renames and moves are done on screen. Blank clears; a missing column is refused; unchanged rows are MATCH and never written (S4-11). A field's key is `DE-nnnn/<normalised field name>`; its parent may be named by `de_number` or entity name, and both given must agree; fields in one file may reference each other (S4-5, S4-12). An entities sheet and a fields sheet in one workbook run as two batches in sequence, entities committed first (S4-12). **BR rows are identified by BR number** — every BR already exists with its step (D-2), so a blank BR number is an error. `hier_code` is a cross-check only: a mismatch is "moved since export — re-export" (R2-D1). FR rows may name a `SOL-` number (the tag) and `BR-` numbers, which create BR ↔ FR links (D-52); no import ever creates a SOLUTION. `effort_days` is ignored on the way in. Type and complexity changes are checked exactly as the rating services would check them: a missing rate, or live interface detail on a move away from INTERFACE, is a row error (R2-D6). The depth hints follow D-39. WBS rows per §4.15 |
| `commit_import` | `ISSUE` / `DATA_ENTITY` / `DATA_FIELD` / `BUSINESS_REQUIREMENT` / `FUNCTION_REQUIREMENT` / `BR_FUNCTION_REQUIREMENT` / `WBS_ITEM` | C/U | One transaction. Blank business key → insert (number minted at commit, §9.8); populated key → update. FR type and complexity go through `change_fr_type` / `rate_function_requirement`, never a direct column write (R2-D6). **All-or-nothing: one invalid row rejects the batch. Any insert requires the acknowledged insert count, and any retirement the acknowledged retire count — on every batch** (R2-P2). The batch's `row_version` is sent on commit (stale preview → 409). Any project EDITOR may commit a batch another uploaded (S4-12). Only a rule failure rejects a batch; an operational failure leaves it retryable (S4-11) |
| `(manual)` consultant review | `IMPORT_BATCH` | R | The consultant reviews the staged preview — before/after computed at preview, never stored (S4-8) — and approves before commit. **An upload never writes unattended** |
| `purge_import_rows` | `IMPORT_ROW`, `IMPORT_BATCH` | D/U | **Q14 — daily.** Staged rows (raw client content, incl. people's names and before-values) are deleted **90 days** after their batch was uploaded (`uploaded_at`), `rows_purged_at` is set and `file_name` becomes `(purged)`. The batch header — who, when, entity, counts, outcome — is kept. An uncommitted batch past 90 days becomes REJECTED. Audited. Closes A-32 |

### 4.6 Version control / baselines (scope area 6)

The freeze set is the tables in `FREEZE_SET` (`services/freeze_set.py`) whose component gate is open
for the project (D-37, S8-1); BR ↔ FR links join it under hash spec 2 (slice10b Q-14); the process volume
figures join `bfc_node`'s hashed list under **hash spec 3** (slice 13c, D-67); and the structured BR — requirement
lines, attribute usage and system flows — joins under **hash spec 4** (slice 11, S11-1). Freeze and client
approval are at EDIT. Baselines are always on: no component gates the routes.

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `preview_freeze` | every frozen table | R | Next version label, the typed confirmation text, errors, freeze-blocking warnings, warnings, row counts per entity, the baseline it will supersede (and whether that one still awaits sign-off), and a `preview_digest` over the live set. Writes nothing |
| `freeze_baseline` | `BASELINE` | C | One transaction, **opened at REPEATABLE READ from its first statement, with `consistency_check` inside it** (R2-P6), so the check and the snapshot see the same data. The body carries the typed confirmation (project code + version) and the `preview_digest`; a changed digest → 409 "The scope changed since you opened this freeze". **Refused on consistency errors and on `FREEZE_BLOCKING_WARNINGS`** (a process missing an element of its chart's DFD rule in a chart whose DFD is on, D-70; live rows in an off component); WARNINGS are returned and audited. Version label auto-increments (minor v1.0 → v1.1, or major). `frozen_by_user_id` from JWT. Status FROZEN. Copies `data_model_depth`, **each chart's DFD rule** (`dfd_rule_to_be`, `dfd_rule_as_is`, D-70) and **the FTE basis** (`fte_working_days`, `fte_hours_per_day`, D-67) onto the header, so a baseline says which rule it passed and re-derives its FTE as frozen. None of the three is in `content_digest` or ever a diff row: they are settings, protected by the header guard |
| `freeze_baseline` | every gated live table | R | Read the whole live set for the project, `is_active = TRUE` only, filtered by the components on |
| `freeze_baseline` | `baseline_*` | C | Copy each live row into its generated snapshot table, retaining `source_id`, code **and** label, and a `content_hash` computed in SQL; the header records a `content_digest` over every entity → the immutable baseline |
| `freeze_baseline` | `BUSINESS_REQUIREMENT`, `BASELINE` | U | **After** the snapshot, every live BR becomes BASELINED (so the frozen row keeps DRAFT/CONFIRMED), and the prior baseline becomes SUPERSEDED. Audit `BASELINE_FROZEN` with the components, counts and warnings |
| `diff_baseline` | `baseline_*` | R | **Any two baselines of one project, or a baseline against the live working set.** Per entity, full outer join on `source_id` → ADDED / CHANGED / REMOVED, with the changed field list, and **MOVED** when only a position column differs (D-10); CHANGED wins and carries `moved: true`. Each side reports which components were on. **Across hash specs** (Q-22): an entity whose hashed list grew between the two sides' specs (each later list extends the earlier one) is compared field by field **on the older list**, and the entry names what was not compared (`compared_on_spec`, `not_compared`) — "Volume is not in v1.2"; against a pre-13c baseline no process is CHANGED merely because volume exists. A side frozen before an entity joined the set shows its rows as ADDED, with a banner when the entity is the structured BR ("vX.Y predates requirement lines"). `SCHEMA_VERSION_MISMATCH` is kept for a list that does not extend the older one, which the freeze set's own assertion makes impossible. A side frozen before BR ↔ FR links existed derives them from its frozen solutions (slice10b §5.3). Runs read-only at REPEATABLE READ. Refused (409) for a baseline that fails its integrity check. Its screen shows counts per area with colour, text and icon, drill-down to before/after per row, and the diagrams highlighted (D-50) |
| `(manual)` client sign-off | `BASELINE` | U | Consultant records the client's approval against a frozen baseline. VB records the decision; it does not route it |
| `approve_baseline` | `BASELINE` | U | Records the client's sign-off — approver name, date (between the freeze date and today), note, optional `approval_reference` — on a **FROZEN or SUPERSEDED** baseline. FROZEN → APPROVED; a SUPERSEDED one keeps its status and gains the approval. Never undone, and no approval column changes once set. **The agreed baseline is the newest one with a recorded approval** (`is_agreed`). The next freeze supersedes an APPROVED baseline and keeps its approval facts (DR8-P1) |
| `reopen_baseline` | `BASELINE` | — | **Not offered.** A frozen baseline is immutable; scope moves forward by freezing v1.1 |

### 4.7 Auth, users, projects and visibility (scope area 7)

**Who sees what (D-40, OR-6, D-62).** A **platform admin** sees every project and the admin functions.
Staff are of kind **USER** (read and edit) or **VIEWER** (read only). Staff see every live project
**except a restricted one they are not a live member of**; on a restricted project their level is the
lower of their kind's cap and their membership level. **New projects are created restricted** (D-62).
A project the caller cannot see is **404, never 403**; the order is 404 → 403 → 409 (component).
Levels rank `VIEW` < `EDIT` < `ADMIN`; only platform admins reach ADMIN.

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `login` | `APP_USER` | R | Verify password hash, check `is_active` → JWT. Update `last_login_at` |
| `login` | `AUDIT_EVENT` | C | Log success/failure with timestamp and outcome |
| `create_user` | `APP_USER` | C | Platform admin only. `user_kind` (USER / VIEWER) required in the body. Store hash in `password_hash`; the plaintext is never persisted or logged. An address outside FTC's domains is refused until client logins exist (D-11, D-43) |
| `change_user_kind` · `set_platform_admin` | `APP_USER`, `AUDIT_EVENT` | U | Platform admin only. Audited (`USER_KIND_CHANGED`). Removing the admin flag requires the kind the user falls back to (DR7-S6) |
| `create_project` | `PROJECT`, `PROJECT_COMPONENT`, `PROJECT_DFD_RULE` | C | **Platform admin only.** Under a client, optionally in a program of the same client. Body names the component list (closed under its dependencies, else 422 naming the missing one), the template it started from (audit only), the data model depth, and **`is_restricted` explicitly** — the form preselects "Assigned consultants only" (D-62). Seeds **all ten number series** (DE, BR, FR, ISSUE, SOL, BEN, RSK, CR, DEC, EXT — R2-D14), the rate card, the control rules, the component rows and **each chart's recommended DFD rule** (D-70) in one transaction; the FTE basis starts at 240 × 8 (D-67). A restricted project starts with no members; the admin lands on its Access screen |
| `set_components` | `PROJECT_COMPONENT`, `AUDIT_EVENT` | C/U | **D-37, platform admin.** The body is the whole wanted set. Preview: what turns on (incl. what is added by dependency, OR-2), what turns off, and blockers — **a component cannot be switched off while live rows exist in it, or while a component that stays on needs it** (OR-1, named as `soft_delete` does). Confirm by hash; one `PROJECT_COMPONENTS_CHANGED` audit event. Switching back on restores the same row |
| `set_data_model_depth` | `PROJECT` | U | **D-39, platform admin.** `KEYS_ONLY` / `FULL`, audited, `row_version` checked |
| `set_restriction` | `PROJECT`, `AUDIT_EVENT` | U | **OR-6, platform admin.** Preview names everyone who **loses** access (restricting) or **gains** it (unrestricting), and who **keeps** it with each member's note, flagging kept members whose level drops; confirm by hash. One `PROJECT_RESTRICTED` / `PROJECT_UNRESTRICTED` audit event with the member list. Read per request, so it applies on the next request. Existing open projects are switched one by one by an admin after their members are checked, never by a migration (D-62) |
| `manage_members` | `PROJECT_MEMBER`, `AUDIT_EVENT` | C/U | **Platform admin.** Add (EDIT or VIEW, with a note), change level, remove (soft). One live membership per user per project; **re-adding inserts a new row** — a membership is history, never restored. Allowed on an unrestricted project, where it has no effect until the project is restricted. Audited (`MEMBER_ADDED`, `MEMBER_LEVEL_CHANGED`, `MEMBER_REMOVED`). A live membership blocks retiring its project |
| `list_visible_projects` | `PROJECT`, `PROJECT_MEMBER` | R | **`visible_project_ids(user)`**: every live unrestricted project plus the restricted ones the user is a live member of, or all for a platform admin. A project the user cannot see does not appear and returns 404, not 403 — non-existence, not refusal |
| `enforce_project_scope` | `PROJECT`, `PROJECT_MEMBER`, `PROJECT_COMPONENT` | R | **`require_project(user, project, min_level, component)`** — the single service-layer guard every list and detail query passes through, returning the caller's effective level. **One function, one file** (§9.10). Every route reaches it through exactly one declared guard (R2-S1, §9); a write to a component names it (criterion 49b) |
| `list_effective_access` | `PROJECT_MEMBER`, `APP_USER` | R | Platform admin. Everyone who can open the project, and why: platform admin, all staff (counts by kind) if open, or each member with their capped level if restricted |
| `deactivate_user` | `APP_USER` | U | Takes effect on the target's next request, because the JWT carries no role, kind or status claim (S4) |
| `soft_delete_record` | any soft-deletable business entity | U | **R2-D2, Q4.** Refused with **409 naming the active dependents** (business keys, counted). Nothing cascades, **except a process step** (§4.1 `retire_step_with_dependents`, S3-SR). Audited |
| `restore_record` | the business entities on the restore allow-list | U | Un-delete (P5). **Only entities on the allow-list** (§7.12). Memberships, control rules, users and `code_master` rows are excluded (R2-S5). **Refused while any parent is inactive** (R2-D2) — restore the parent first |
| `consistency_check` | `BFC_NODE`, `BUSINESS_REQUIREMENT`, `DATA_FIELD`, `BR_DATA_ENTITY`, `BFC_NODE_EXTERNAL_FLOW`, `BR_FUNCTION_REQUIREMENT`, `FR_INTERFACE`, every frozen table | R | **Errors:** `hier_code`/`level_no` drift, to-be processes without a BR, processes with children, BR CRUD or external flows with no matching step I/O, `FR_INTERFACE` rows under a non-interface type, and **an active row under an inactive parent, in any of the frozen tables** (R2-D2). **Freeze-blocking warnings:** processes missing an input or an output in a chart whose DFD is on (D-38, S7-3), live rows in an off component. **Warnings:** entities with no fields, entities with keys only under `FULL` (D-39), `fr_solution_outside_its_brs`. **Informational:** e.g. `as_is_support_on_to_be`. **Precondition of freeze, run inside the freeze transaction** (D11, R2-P6) |
| `(manual)` access review | `PROJECT_MEMBER`, `PROJECT` | R | Ben reviews **effective** access per project — restriction, members and platform admins — at each baseline freeze |
| client access | `APP_USER`, `PROJECT`, `AUDIT_EVENT` | — | **D-43, before first client use, only with the client's consent recorded on the project.** (a) A client read-only login sees **its own project only** — the one place the project wall holds whatever staff can see; withdrawable, every view audited. **Gate (D-11, A-11, finding S8):** before any external party gets a login, record-level confidentiality is built first — `issue_dashboard` reports open issues per named stakeholder, a per-person complaint count, which a client login must not see. (b) An offline HTML viewer file generated from a frozen baseline, by an admin or user, never a viewer; once sent it cannot be withdrawn; each file audited (OR-9) |

`USER_ACCESS_GRANT` is retired history: its rows were copied into `PROJECT_MEMBER` and soft-revoked,
and `vb_app` holds SELECT only on it (D-40, S7-6).

### 4.8 Size and effort (D-13)

Component EFFORT (needs FUNCTION_REQUIREMENT).

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `read_rate_card` | `EFFORT_RATE`, `FUNCTION_REQUIREMENT` | R | The grid of FR type × complexity. Per cell, the count and Σ days of live rated FRs **not at the cell's current rate**, visible to everyone (S6c-5). Untouched seeded cells are marked "FTC default, unconfirmed" (S6c-1). A cell above 60 days is flagged |
| `maintain_rate_card` | `EFFORT_RATE`, `AUDIT_EVENT` | C/U | (FR type × complexity) → standard man-days, per project, at **EDIT** (S6c-3). Seeded from an FTC default at `create_project`, then negotiated with the client. **Every change needs a rationale and writes an audit row with the old and new values** (R2-D7). A cell above 60 man-days needs explicit confirmation (S6c-7). **A rate change never reprices rated FRs**; it reports how many are no longer at the current rate (S6c-2, A-38). **The rate card is frozen with each baseline** (`baseline_effort_rate`, §6.1), so a priced diff can name the card that priced it |
| `rate_function_requirement` | `FUNCTION_REQUIREMENT` | U | `complexity_code` ∈ SIMPLE / MEDIUM / COMPLEX / VERY_COMPLEX. `effort_days` is **derived** at save from the rate card, and **stored**, so a later rate change cannot silently reprice agreed scope. Re-rating to the current rate is per FR, on purpose, audited (S6c-2) |
| `effort_summary` | `FUNCTION_REQUIREMENT`, `BR_FUNCTION_REQUIREMENT`, `SOLUTION`, `PHASE` | R | Man-days by FR type, by solution, by phase, by L1 area → the resource plan and the vendor sizing. By solution reads the FR's one tag, so nothing is double-counted; FRs with no tag sum into an **Unassigned** bucket, never dropped. FRs under a REJECTED solution are shown apart, outside the headline total (S6c-8). Informational lines: **untraced** FRs (no BR link: count and days), unrated FRs, days not at current rate. Effort is never summed by BR |
| `priced_diff` | `BASELINE_FUNCTION_REQUIREMENT`, `BASELINE_BR_FUNCTION_REQUIREMENT`, `BASELINE_BUSINESS_REQUIREMENT` | R | **Q3, R2-D3.** Only when EFFORT was on in both sides. Per `source_fr_id`, **`effort_b − effort_a`, counted exactly once**: ADDED = +effort, REMOVED = −effort, CHANGED = the delta → **"v1.1: +340 man-days added, −60 removed, +12 re-rated, net +292"**. **Untraced FR effort (no BR link) and unassigned FR effort (no solution tag) are their own lines.** A separate, informational **"effort exposed"** line is the effort of FRs linked to changed BRs. It is never added to the net |

### 4.9 Benefit (D-14)

Component BENEFIT (needs SOLUTION).

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `create_benefit` | `BENEFIT` | C | Next per-project sequence → `BEN-0001`. Measure, unit, baseline value, target value, realisation date, accountable `org_role_id` |
| `link_benefit_solution` | `BENEFIT_SOLUTION` | C/D | Many-to-many. A benefit usually needs several solutions; a solution may serve several benefits |
| `value_ranking` | `BENEFIT`, `BENEFIT_SOLUTION`, `FUNCTION_REQUIREMENT` | R | Per solution, **value = Σ (target − baseline) × contribution_pct**, ÷ effort days. **Ranked only within one `measure_unit`** (R2-D12, Q9) — hours saved and baht saved are never on one list. **This is what makes "trade, don't add" executable** — it names each unit's bottom quartile to displace |
| `benefit_gap_report` | `SOLUTION`, `BENEFIT_SOLUTION` | R | Solutions carrying effort and no quantified benefit → challenge at the next gate. Benefits whose solutions are all TECHNOLOGY → fragile benefit case (§4.13) |

### 4.10 Risk (D-15)

Component RISK.

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `raise_risk` | `RISK` | C | Next per-project sequence → `RSK-0001`. `probability_code` × `impact_code`, mitigation, owning `org_role_id`, target date. May link to a BFC node, a Solution or a Phase |
| `score_risk` | `RISK` | U | `exposure_score` derived from probability × impact at save; `status_code` ∈ OPEN / MITIGATING / CLOSED / MATERIALISED |
| `promote_risk_to_issue` | `RISK`, `ISSUE` | U/C | A materialised risk creates the issue and links back. **The one path between the two entities — they are never merged** |
| `risk_register` | `RISK` | R | Exposure-ranked, ageing, by owner and by phase |

### 4.11 Change control and decisions (D-16, D-17)

Component CHANGE_REQUEST (needs EFFORT).

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `raise_change_request` | `CHANGE_REQUEST` | C | Next per-project sequence → `CR-0001`. Raised against an agreed baseline — **FROZEN or APPROVED, or a SUPERSEDED one that carries the agreed client approval** (the newest baseline with a recorded approval, DR8-P1); **never the working set, never a SUPERSEDED baseline without that approval** (Q8, SC-2) — with a stated rationale and origin |
| `analyse_cr_impact` | `CR_IMPACT` | C | Trace the proposed change through BR → FR (direct links) and BR → Solution → Application → Data Entity → Phase. **An FR is accepted as a seed** as well as a BR, because an untraced FR cannot be reached from any BR. Every touched object becomes a row. **The blast radius is computed, not typed** |
| `price_cr` | `CHANGE_REQUEST` | U | Sum `effort_days` across impacted FRs (D-13); sum benefit delta across impacted benefits (D-14); flag impacted phases and dependencies |
| `decide_cr` | `CHANGE_REQUEST`, `DECISION` | U/C | APPROVED / REJECTED / DEFERRED, with `decided_by_user_id` and `displaces_cr_id` — **an approval of net-positive effort must name what it displaces, or record an explicit budget increase** |
| `record_decision` | `DECISION` | C | Any project decision, not only CRs: what, who, when, the analysis it was taken against, and the alternative rejected |
| `decision_log` | `DECISION` | R | Chronological, filterable by dimension → answers "why did we do that" six months later |

### 4.12 Phasing and dependency (D-18)

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `create_phase` | `PHASE` | C/U | Delivery wave: name, sequence, start and end dates, status |
| `assign_solution_phase` | `SOLUTION_PHASE` | C/D | A solution may span phases; the assignment carries the portion |
| `link_solution_dependency` | `SOLUTION_DEPENDENCY` | C/D | Prerequisite solutions. **Cycles are rejected** — topological check on insert |
| `phase_plan_report` | `PHASE`, `SOLUTION_PHASE`, `FUNCTION_REQUIREMENT` | R | Effort per phase, dependency violations (a solution scheduled before its prerequisite), and volatile areas still sitting in the current wave |

### 4.13 Control rules and the analysis pack (D-19)

The analyses below all read entities already in the model. `CONTROL_RULE` is what turns each
from a number into an action.

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `maintain_control_rule` | `CONTROL_RULE` | C/U | (project × `analysis_code`) → threshold value, comparison, owning `org_role_id`, escalation path, at EDIT. Agreed at mobilisation; the thresholds are **the client's, not hard-coded** |
| `control_panel` | `CONTROL_RULE` + every analysis | R | Runs every analysis, compares to its rule → **GREEN / FLAG / ESCALATE**, with the owning role and the prescribed action per row. The PMO's one screen |
| `requirement_volatility` | `BASELINE_BUSINESS_REQUIREMENT` | R | ADDED/CHANGED/REMOVED per L1 area across baseline generations. **The earliest warning the app produces** — an area churning across two consecutive baselines is not understood. *Action: pull it out of the current wave; do not let a vendor start there* |
| `process_change_intensity` | `BFC_NODE`, `BR_SOLUTION`, `SOLUTION` | R | Process steps carrying a solution, rolled up per L1 area, weighted by solution category. Where the transformation actually lands versus where it was said it would |
| `org_impact_heatmap` | `BFC_NODE_ORG_ROLE`, `BR_ORG_ROLE`, `BR_SOLUTION`, `ORG_UNIT` | R | Change absorbed per org unit. *Action: top decile gets a dedicated change agent and a capacity check — they are usually the SMEs too* |
| `stakeholder_engagement` | `STAKEHOLDER`, `ISSUE`, `ORG_UNIT` | R | Issues raised per stakeholder per org unit. **Silence is the signal**: high impact and no issues raised is adoption risk. *Action: interview before sign-off* |
| `interface_load` | `v_interface_list` | R | Interface FRs per source → target application pair (from `FR_INTERFACE`, D-27), and as a share of all FRs. *Action: over ~25–30%, stand up an integration workstream and book test environments early* |
| `data_migration_map` | `DATA_ENTITY`, `APPLICATION_BFC_NODE`, `APPLICATION_SOLUTION` | R | Source (as-is) → target (to-be) per data entity. Entities with no source, or with conflicting sources → data ownership decision before design freeze |
| `master_data_candidates` | `BR_DATA_ENTITY`, `BFC_NODE` | R | Entities referenced by BRs across many L1 areas. *Action: assign a single owner; it becomes a managed cross-workstream dependency* |
| `fr_unlinked` | `FUNCTION_REQUIREMENT`, `BR_FUNCTION_REQUIREMENT` | R | **D-28, re-based on D-52.** FRs with no live BR link, count and effort. *Action: link or retire before the next freeze; a vendor cannot be held to a function nobody traced to a requirement* |

### 4.14 Programs (D-32)

A program groups related projects for one client. **It shares no data and grants no access** (D-40):
every row below is either a program header or a read assembled from per-project reports.

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `create_program` · `update_program` | `PROGRAM` | C/U | **Platform admin.** Code, name, client, description — no status, dates or manager (A-65). A program's projects must share its `client_id` |
| `move_project_program` | `PROJECT`, `AUDIT_EVENT` | U | **Platform admin only** (Q10). Two steps: a **preview** showing the roll-up change, then a commit that must quote the preview's hash over from/to — if it changed in between, 409. Moving a project changes roll-ups, not access. Audited (R2-S3) |
| `program_dashboard` | every per-project report | R | **Every staff user.** For each project in `visible_project_ids(user) ∩ program.projects`: BR / FR / issue counts, control-panel status, effort summary, and WBS plan-vs-actual where a WBS is imported. **Built by calling the per-project report once per project — never new cross-project SQL** (R2-S2). A restricted project the caller is not on is omitted silently; a program whose every project is hidden from the caller is hidden too |
| `program_counts` · `program_interfaces` · `program_effort` · `program_control_status` | the same per-project reports | R | The same rule: a list of `{project, result}` pairs, one per visible project. Nothing is stored at program level |
| `(manual)` cross-project hand-off | — | — | Not a shared entity: each project records its own side. The other project is an **outside party** on the DFD boundary — an `EXTERNAL_ENTITY` named "Project: X", with external flows like any other party (SC-1). No new table |

### 4.15 WBS import and progress (D-33, D-41)

Component WBS (D-37). The task list stays owned by MS Project; VB imports it, lets consultants say
which phase and solution each line delivers, and **records progress against each line** (D-41), so
the progress report and the program dashboard show plan-vs-actual. Creating tasks, dependencies,
Gantt editing and critical path stay out of scope (§12.2).

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `download_template` (`wbs`) | — | R | The WBS column map: **MS Project Unique ID (required)**, WBS code, name, outline level, start, finish, actual start, actual finish, % complete. The instruction sheet carries the **date-format step** — set date columns to `yyyy-mm-dd` before saving, because MS Project exports dates in the Windows locale — and tells the consultant to add **Unique ID** to the MS Project export map (not exported by default) |
| `validate_import` (`wbs`) | `IMPORT_BATCH`, `IMPORT_ROW` | C | **Keyed by `ms_unique_id`** (R2-D15): a known ID updates, an unknown one inserts. WBS code, name and dates may all change on re-plan. Parent derived from outline level and row order. Duplicate Unique ID or WBS code in one file → error; non-ISO text date → error (A-33). `import_mode` ∈ merge / replace: **replace stages a RETIRE row for every active line the file omits** |
| `commit_import` (`wbs`) | `WBS_ITEM` | C/U | As §4.5a, with both acknowledgements. **Never touches the phase / solution links or VB's progress updates** — they survive every re-import. Imported actuals are kept beside VB progress, never over it (OR-7) |
| `link_wbs_item` | `WBS_ITEM` | U | Set or clear `phase_id` and `solution_id`, both in the same project. `row_version` checked. Any other field → 422 "Change it in MS Project and re-import" — progress is recorded by `record_wbs_progress`, never by editing the line (D-33, D-41) |
| `record_wbs_progress` | *WBS progress update* | C | **D-41.** A new dated row against one imported line: % complete, actual start and finish, status (on track / at risk / late), comment, date of the update. Never overwritten, so progress over time is kept |
| `wbs_progress_report` | `WBS_ITEM`, *WBS progress update*, `PHASE`, `SOLUTION` | R | **D-41, OR-7.** From VB progress (the reporting source): plan vs actual, slip in days, % complete by phase and solution, latest comments. Lines with no phase link are listed, not dropped. **Flags lines where the imported actuals and VB progress disagree.** Not baselined |

**Cross-check:** every entity named in this grid appears in §5/§6, and every function has
pseudocode in §7.

---

## 5. Logical design

Modelled by `apple` from the §4 grid and normalized 1NF → 2NF → 3NF. `ENGAGEMENT` is named
**`PROJECT`** throughout (A-2). Open modelling questions are kept in §11.

### 5.1 Conventions applied to every business table

Declared once here and **omitted from the diagram** so it stays readable. Every business table has
(`models/base.py::AuditMixin`, `alembic/vb_ops.py::audit_columns`):

| Column | Type | Note |
|---|---|---|
| `created_at` | `timestamptz NOT NULL DEFAULT now()` | |
| `updated_at` | `timestamptz NOT NULL DEFAULT now()` | maintained by the `fn_set_updated_at()` **DB trigger**, never SQLAlchemy `onupdate=` (playbook §13) |
| `created_by` | `bigint NOT NULL FK → APP_USER` | set from the JWT, never the request body (§9.2) |
| `updated_by` | `bigint NULL FK → APP_USER` | who last touched a live row before a freeze (A-25) |
| `is_active` | `boolean NOT NULL DEFAULT true` | soft-delete flag |
| `deleted_at` | `timestamptz NULL` | |
| `deleted_by` | `bigint NULL FK → APP_USER` | A-25 |
| `row_version` | `integer NOT NULL DEFAULT 1` | optimistic concurrency (D-6). Every `UPDATE` carries `WHERE row_version = :v` and increments it; a mismatch is a 409 (§7) |

This creates many FKs into `APP_USER`, which are deliberately not drawn.

**Tables that do not carry the full set**, each a documented deviation (`docs/PLAYBOOK_DEVIATIONS.md`):

| Table | What it carries instead |
|---|---|
| `CODE_MASTER`, `PROJECT_TEMPLATE_COMPONENT` | the full set, but `created_by` is nullable: seeded library rows have no author |
| `APP_USER` | its own audit columns, not `AuditMixin`; `created_by` is nullable because the first admin is created by nobody |
| `PROJECT_SEQUENCE` | none: it is a counter (§5.4.6) |
| `DIAGRAM_LAYOUT` | the four presence columns only (`created_*`, `updated_*`), no soft delete, no `row_version`; hard-deleted (D-30, S2-6) |
| `IMPORT_BATCH` | no soft delete (its status is its lifecycle); `uploaded_at` / `uploaded_by_user_id` are its created pair; keeps `updated_at` and `row_version` (S4-6) |
| `IMPORT_ROW` | none; hard-deleted after 90 days (Q14, S4-6) |
| `BASELINE` | no soft delete; `frozen_at` / `frozen_by_user_id` are its created pair; keeps `updated_at`, `updated_by`, `row_version` for status and approval (A-36) |
| `baseline_*` shadows | none: never updated (§6.1) |
| `DECISION` | append-only: no soft delete (§5.3 DECISION) |
| `AUDIT_EVENT` | append-only by grant and trigger |

**Keys.** Surrogate PKs are `bigint` identity throughout, **link tables included** (S1-5): a junction's
design key is a `UNIQUE NOT NULL` constraint beside the surrogate, and every FK that targets it still does.
Business numbers (`DE-0001`, `BR-0042`) are **alternate keys, not PKs**: they are project-scoped and
human-facing, and APIs should not leak sequence semantics into path params more than necessary.

**Uniqueness and soft delete.**
- **Minted numbers** (`de_number`, `br_number`, …) keep **full** `UNIQUE` constraints including deleted
  rows, so numbers are never reused.
- **User-typed names and codes** are unique **among live rows**, normalised `lower(btrim(…))`, through a
  partial unique index `WHERE is_active` (S1-6), so a retired name may be reused.
- **Link grains** are **full** unique constraints. Re-linking a retired pair **restores** the old row, never
  inserts a new one (S1-7), so its baseline `source_id` stays stable.
- **Positional uniqueness** (`seq_no` within a parent) is a partial unique index `WHERE is_active`, so
  retiring a sibling frees its slot.

**Patterns used everywhere** (detail in §5.4.7):
- **Tenancy:** every in-project FK is composite, `(x_id, project_id) → X(x_id, project_id)`, onto a UK
  `(x_id, project_id)`, so no row can point into another project (finding D9).
- **Category-verified lookups (S1-4):** every `code_master` FK carries a generated constant
  `<p>_category` column and a composite FK `(<p>_code_id, <p>_category) → CODE_MASTER(code_id, category)`.
  These category columns are omitted from the diagram except where they are part of a behaviour key.
- **Live guards:** a generated column `CASE WHEN is_active THEN <value> END` plus a composite FK onto the
  parent's `(…, is_process)`, `(…, is_active)` or `(…, bfc_set_code)` key. A retired row's guard is NULL,
  so MATCH SIMPLE skips it. Every guard FK is **ON UPDATE NO ACTION**, never CASCADE.

---

### 5.2 Entity-relationship diagram

```mermaid
erDiagram
    %% ---------- tenancy and project configuration ----------
    CLIENT ||--o{ PROJECT : "contracts"
    CLIENT ||--o{ PROGRAM : "groups projects under (D-32)"
    PROGRAM |o--o{ PROJECT : "rolls up (same client, composite FK)"
    PROJECT ||--o{ BFC_NODE : "scopes"
    PROJECT ||--o{ ORG_UNIT : "scopes"
    PROJECT ||--o{ DATA_ENTITY : "scopes"
    PROJECT ||--o{ BUSINESS_REQUIREMENT : "scopes"
    PROJECT ||--o{ FUNCTION_REQUIREMENT : "scopes"
    PROJECT ||--o{ SOLUTION : "scopes"
    PROJECT ||--o{ APPLICATION : "scopes"
    PROJECT ||--o{ STAKEHOLDER : "scopes"
    PROJECT ||--o{ ISSUE : "scopes"
    PROJECT ||--o{ PROCESS_TRIGGER : "scopes"
    PROJECT ||--o{ BASELINE : "freezes"
    PROJECT ||--|{ PROJECT_SEQUENCE : "numbers"
    PROJECT ||--o{ PROJECT_COMPONENT : "switches on (D-37)"
    PROJECT ||--|{ PROJECT_DFD_RULE : "requires, per chart (live row = required - D-70)"
    CODE_MASTER ||--o{ PROJECT_COMPONENT : "names the component"
    CODE_MASTER ||--o{ PROJECT_TEMPLATE_COMPONENT : "template x component (OR-3)"

    %% ---------- client organisation ----------
    ORG_UNIT ||--o{ ORG_UNIT : "parent of"
    ORG_UNIT ||--o{ ORG_ROLE : "defines"

    %% ---------- business function chart (two sets, D-47) ----------
    BFC_NODE ||--o{ BFC_NODE : "parent of (same set; a process has no children - D-23)"
    BFC_NODE ||--o{ BFC_NODE_DATA_ENTITY : "reads or writes (step I/O - D-24)"
    DATA_ENTITY ||--o{ BFC_NODE_DATA_ENTITY : "flows through"
    BFC_NODE ||--o{ BFC_NODE_ORG_ROLE : "is performed via (as-is RACI - D-64)"
    ORG_ROLE ||--o{ BFC_NODE_ORG_ROLE : "takes part in"
    BFC_NODE ||--o| BUSINESS_REQUIREMENT : "is specified by (one per to-be process - D-2, S7-2)"
    ORG_UNIT |o--o{ BFC_NODE : "performs (D-46)"
    ORG_ROLE |o--o{ BFC_NODE : "performs (D-46)"
    APPLICATION |o--o{ BFC_NODE : "performs (D-46)"
    PROCESS_TRIGGER ||--o{ BFC_NODE_TRIGGER : "starts (D-49)"
    BFC_NODE ||--o{ BFC_NODE_TRIGGER : "is started by"
    BFC_NODE ||--o{ BFC_NODE_FLOW : "flowed to (retired - D-38, history only)"
    CODE_MASTER |o--o{ BFC_NODE : "TRANSACTION_UNIT of the volume figures (D-67)"

    %% ---------- data entities ----------
    DATA_ENTITY ||--|{ DATA_FIELD : "is composed of"
    DATA_ENTITY ||--o{ DATA_FIELD : "is pointed to by (one fk_group_no per relationship)"
    DATA_FIELD ||--o{ DATA_FIELD : "is pointed to by"

    %% ---------- D-24: step I/O licenses BR CRUD ----------
    BFC_NODE_DATA_ENTITY ||--o{ BR_DATA_ENTITY : "licenses (R needs I; C/U/D need O)"

    %% ---------- D-24a: external parties ----------
    PROJECT ||--o{ EXTERNAL_ENTITY : "scopes"
    EXTERNAL_ENTITY ||--o{ BFC_NODE_EXTERNAL_FLOW : "exchanges data with"
    BFC_NODE ||--o{ BFC_NODE_EXTERNAL_FLOW : "receives from / sends to"
    BFC_NODE_DATA_ENTITY |o--o{ BFC_NODE_EXTERNAL_FLOW : "is sourced from / delivered to"
    CODE_MASTER ||--o{ EXTERNAL_ENTITY : "types kind"

    %% ---------- D-27: interfaces ----------
    FUNCTION_REQUIREMENT ||--o| FR_INTERFACE : "is detailed as interface (behaviour INTERFACE only)"
    APPLICATION ||--o{ FR_INTERFACE : "is source of"
    APPLICATION ||--o{ FR_INTERFACE : "is target of"
    FR_INTERFACE ||--o{ FR_INTERFACE_DATA_ENTITY : "carries"
    DATA_ENTITY ||--o{ FR_INTERFACE_DATA_ENTITY : "is carried by"
    CODE_MASTER ||--o{ FR_INTERFACE : "types pattern, method, frequency"
    CODE_MASTER ||--o{ EFFORT_RATE : "keys FR type and complexity"

    %% ---------- D-29/D-30: diagram layout (not baselined) ----------
    PROJECT ||--o{ DIAGRAM_LAYOUT : "positions"
    BFC_NODE |o--o{ DIAGRAM_LAYOUT : "scopes (scope_bfc_node_id)"
    BFC_NODE |o--o{ DIAGRAM_LAYOUT : "is placed as a process"
    DATA_ENTITY |o--o{ DIAGRAM_LAYOUT : "is placed as entity or store"
    EXTERNAL_ENTITY |o--o{ DIAGRAM_LAYOUT : "is placed as external party"
    PROCESS_TRIGGER |o--o{ DIAGRAM_LAYOUT : "is placed as a trigger"
    BFC_NODE_FLOW |o--o{ DIAGRAM_LAYOUT : "event marker (history rows only)"

    %% ---------- business requirement ----------
    BUSINESS_REQUIREMENT ||--o{ BR_DATA_ENTITY : "uses"
    DATA_ENTITY ||--o{ BR_DATA_ENTITY : "is used by"
    BUSINESS_REQUIREMENT ||--|{ BR_ORG_ROLE : "is owned via (to-be RACI - D-64)"
    ORG_ROLE ||--o{ BR_ORG_ROLE : "is accountable in"
    BUSINESS_REQUIREMENT ||--o{ BR_REQUIREMENT_LINE : "is detailed by (D-59)"
    CODE_MASTER ||--o{ BR_REQUIREMENT_LINE : "types kind and priority"
    BR_DATA_ENTITY ||--o{ BR_DATA_FIELD : "licenses (same BR, entity, CRUD; live - D-60b)"
    DATA_FIELD ||--o{ BR_DATA_FIELD : "is used as"
    BUSINESS_REQUIREMENT ||--o{ BR_SYSTEM_FLOW : "states (D-61)"
    DATA_ENTITY ||--o{ BR_SYSTEM_FLOW : "flows"
    APPLICATION ||--o{ BR_SYSTEM_FLOW : "is the from system of"
    APPLICATION ||--o{ BR_SYSTEM_FLOW : "is the to system of"

    %% ---------- solution and function requirement (D-7, D-52) ----------
    BUSINESS_REQUIREMENT ||--o{ BR_SOLUTION : "is answered by"
    SOLUTION ||--o{ BR_SOLUTION : "answers"
    BUSINESS_REQUIREMENT ||--o{ BR_FUNCTION_REQUIREMENT : "is served by (D-52)"
    FUNCTION_REQUIREMENT ||--o{ BR_FUNCTION_REQUIREMENT : "serves"
    SOLUTION |o--o{ FUNCTION_REQUIREMENT : "tags (effort counts to it; optional - D-28, D-52)"
    CODE_MASTER ||--o{ SOLUTION : "types category and status"

    %% ---------- application / technology (D-8) ----------
    APPLICATION ||--o{ APPLICATION_SOLUTION : "delivers"
    SOLUTION ||--o{ APPLICATION_SOLUTION : "is delivered by"
    APPLICATION ||--o{ APPLICATION_BFC_NODE : "supports today (as-is processes)"
    BFC_NODE ||--o{ APPLICATION_BFC_NODE : "is supported today by"
    CODE_MASTER ||--o{ APPLICATION : "types lifecycle and kind"

    %% ---------- stakeholders and issues ----------
    ORG_UNIT ||--o{ STAKEHOLDER : "employs"
    STAKEHOLDER ||--o{ ISSUE : "raises"
    APP_USER ||--o{ ISSUE : "records"
    ISSUE ||--o{ ISSUE_BR : "is raised against"
    BUSINESS_REQUIREMENT ||--o{ ISSUE_BR : "attracts"

    %% ---------- baselines (one generated shadow per frozen table - section 6.1) ----------
    BASELINE |o--o| BASELINE : "succeeds (prior_baseline_id)"
    BASELINE ||--o{ BASELINE_BUSINESS_REQUIREMENT : "contains (example shadow)"
    BUSINESS_REQUIREMENT ||--o{ BASELINE_BUSINESS_REQUIREMENT : "is snapshotted as (source_id)"
    CODE_MASTER ||--o{ BASELINE : "types status"

    %% ---------- identity and access ----------
    APP_USER ||--o{ PROJECT_MEMBER : "is a member through (OR-6)"
    PROJECT ||--o{ PROJECT_MEMBER : "names members of"
    APP_USER ||--o{ USER_ACCESS_GRANT : "held (retired - D-40, history only)"
    PROJECT |o--o{ USER_ACCESS_GRANT : "was opened to"
    PROGRAM |o--o{ USER_ACCESS_GRANT : "was opened to"
    APP_USER ||--o{ BASELINE : "froze / recorded approval"
    APP_USER ||--o{ AUDIT_EVENT : "emits"
    PROJECT ||--o{ AUDIT_EVENT : "contextualises"

    %% ---------- size, benefit, risk, change, phasing, control (D-13...D-19) ----------
    PROJECT ||--o{ EFFORT_RATE : "rate card"
    PROJECT ||--o{ BENEFIT : "scopes"
    PROJECT ||--o{ RISK : "scopes"
    PROJECT ||--o{ CHANGE_REQUEST : "scopes"
    PROJECT ||--o{ DECISION : "scopes"
    PROJECT ||--o{ PHASE : "scopes"
    PROJECT ||--o{ CONTROL_RULE : "governs (project_id NULL = FTC house default)"
    BENEFIT ||--o{ BENEFIT_SOLUTION : "is delivered by"
    SOLUTION ||--o{ BENEFIT_SOLUTION : "delivers"
    ORG_ROLE ||--o{ BENEFIT : "is accountable for"
    ORG_ROLE ||--o{ RISK : "owns"
    ORG_ROLE ||--o{ CONTROL_RULE : "owns the response"
    RISK ||--o| ISSUE : "materialised as"
    BASELINE ||--o{ CHANGE_REQUEST : "is challenged by"
    CHANGE_REQUEST ||--|{ CR_IMPACT : "traces to"
    CHANGE_REQUEST ||--o| DECISION : "is settled by"
    CHANGE_REQUEST ||--o| CHANGE_REQUEST : "displaces"
    DECISION |o--o| DECISION : "supersedes"
    PHASE ||--o{ SOLUTION_PHASE : "contains"
    SOLUTION ||--o{ SOLUTION_PHASE : "is scheduled in"
    SOLUTION ||--o{ SOLUTION_DEPENDENCY : "depends on"
    APP_USER ||--o{ DECISION : "decided"
    CODE_MASTER ||--o{ FUNCTION_REQUIREMENT : "types complexity"
    CODE_MASTER ||--o{ RISK : "types probability, impact, status"
    CODE_MASTER ||--o{ CHANGE_REQUEST : "types status"
    PROJECT ||--o{ WBS_ITEM : "imports its schedule (D-33)"
    WBS_ITEM |o--o{ WBS_ITEM : "parent of"
    PHASE |o--o{ WBS_ITEM : "is planned by (VB-edited link)"
    SOLUTION |o--o{ WBS_ITEM : "is scheduled by (VB-edited link)"
    IMPORT_BATCH |o--o{ WBS_ITEM : "last imported"

    %% ---------- bulk import staging (D-5) ----------
    PROJECT ||--o{ IMPORT_BATCH : "scopes"
    APP_USER ||--o{ IMPORT_BATCH : "uploaded / committed"
    IMPORT_BATCH ||--o{ IMPORT_ROW : "stages (purged after 90 days - Q14)"
    BFC_NODE |o--o{ IMPORT_BATCH : "anchors a process-flow import (D-25)"

    %% ---------- shared lookups ----------
    CODE_MASTER ||--o{ ORG_UNIT : "types level"
    CODE_MASTER ||--o{ DATA_FIELD : "types data type"
    CODE_MASTER ||--o{ BFC_NODE_ORG_ROLE : "types RACI (with behaviour - Q7)"
    CODE_MASTER ||--o{ BR_ORG_ROLE : "types RACI (with behaviour - Q7)"
    CODE_MASTER ||--o{ BUSINESS_REQUIREMENT : "types status"
    CODE_MASTER ||--o{ FUNCTION_REQUIREMENT : "types FR type (with behaviour, immutable once used) and fulfilment status"
    CODE_MASTER ||--o{ ISSUE : "types severity, type, status"
    CODE_MASTER ||--o{ IMPORT_BATCH : "types status"
    CODE_MASTER ||--o{ PROJECT : "types status"
    PROJECT ||--o{ CODE_MASTER : "may override"

    %% ==========================================================
    CLIENT {
        bigint client_id PK
        varchar client_code
        varchar client_name
        varchar industry
    }
    PROGRAM {
        bigint program_id PK
        bigint client_id FK
        varchar program_code
        varchar program_name
        text description
    }
    PROJECT {
        bigint project_id PK
        bigint client_id FK
        bigint program_id FK "nullable - D-32; composite FK with client_id"
        bool program_is_active FK "generated guard: TRUE if active, else NULL"
        varchar project_code
        varchar project_name
        date start_date
        date end_date
        bigint status_code_id FK
        varchar data_model_depth "KEYS_ONLY | FULL - D-39"
        bool is_restricted "OR-6, D-62"
        smallint working_days_per_year "FTE basis, default 240 - D-67"
        numeric hours_per_working_day "FTE basis, default 8.00 - D-67"
    }
    PROJECT_DFD_RULE {
        bigint project_dfd_rule_id PK
        bigint project_id FK "UK (project_id, bfc_set_code, element_code)"
        varchar bfc_set_code "TO_BE | AS_IS"
        varchar element_code "STARTED | DATA_IN | DATA_OUT | EXTERNAL | ORDER; STARTED never retired"
    }
    PROJECT_COMPONENT {
        bigint project_component_id PK
        bigint project_id FK "UK (project_id, component_code_id)"
        bigint component_code_id FK "PROJECT_COMPONENT"
    }
    PROJECT_TEMPLATE_COMPONENT {
        bigint project_template_component_id PK
        bigint template_code_id FK "PROJECT_TEMPLATE"
        bigint component_code_id FK "PROJECT_COMPONENT"
    }
    CODE_MASTER {
        bigint code_id PK
        bigint project_id FK "NULL = FTC library"
        varchar category
        varchar code
        varchar label
        varchar behaviour_code "FR_TYPE and RACI_TYPE only; immutable once referenced"
        int sort_order
        bool is_system
    }
    PROJECT_SEQUENCE {
        bigint project_id PK
        varchar sequence_code PK
        varchar prefix
        int pad_width
        bigint last_value
    }
    ORG_UNIT {
        bigint org_unit_id PK
        bigint project_id FK
        bigint parent_org_unit_id FK
        smallint level_no
        bigint level_code_id FK
        varchar org_unit_code
        varchar org_unit_name
        int seq_no
        text description
    }
    ORG_ROLE {
        bigint org_role_id PK
        bigint project_id FK
        bigint org_unit_id FK
        varchar org_role_code
        varchar org_role_name
        text responsibility_desc
        int headcount
    }
    BFC_NODE {
        bigint bfc_node_id PK
        bigint project_id FK
        bigint parent_bfc_node_id FK
        bool parent_is_process FK "generated: FALSE if active, else NULL"
        varchar bfc_set_code "TO_BE | AS_IS - D-47, immutable"
        smallint level_no
        bool is_process "D-23"
        int seq_no
        varchar hier_code
        varchar node_name
        text purpose_desc
        text data_processing_desc "process only"
        varchar performer_kind "ORG_UNIT | ORG_ROLE | APPLICATION | AI - D-46"
        bigint performer_org_unit_id FK
        bigint performer_org_role_id FK
        bigint performer_application_id FK
        varchar performer_label "AI only"
        numeric runs_per_period "process only - D-67"
        varchar volume_period_code "DAY | WEEK | MONTH | QUARTER | YEAR"
        numeric transactions_per_run
        bigint transaction_unit_code_id FK "TRANSACTION_UNIT"
        numeric seconds_per_transaction
    }
    BFC_NODE_DATA_ENTITY {
        bigint bfc_node_data_entity_id PK
        bigint project_id FK
        bigint bfc_node_id FK "UK (bfc_node_id, data_entity_id, direction)"
        bool node_is_process FK "generated guard"
        bigint data_entity_id FK
        char direction "I or O"
        text note
    }
    BFC_NODE_ORG_ROLE {
        bigint bfc_node_org_role_id PK
        bigint project_id FK
        bigint bfc_node_id FK "UK (bfc_node_id, org_role_id, raci_code_id)"
        bool node_is_process FK "generated guard"
        varchar node_live_set FK "generated: AS_IS if active - D-64"
        bigint org_role_id FK
        bigint raci_code_id FK
        varchar raci_category FK "generated: RACI_TYPE"
        varchar raci_behaviour FK "copy, FK-verified - Q7"
    }
    PROCESS_TRIGGER {
        bigint process_trigger_id PK
        bigint project_id FK
        varchar trigger_name
        varchar trigger_kind "TIME | EVENT"
        varchar schedule_note "TIME only"
        text description
    }
    BFC_NODE_TRIGGER {
        bigint bfc_node_trigger_id PK
        bigint project_id FK
        bigint bfc_node_id FK "UK (bfc_node_id, process_trigger_id)"
        bool node_is_process FK "generated guard"
        bigint process_trigger_id FK
        text note
    }
    BFC_NODE_FLOW {
        bigint bfc_node_flow_id PK "retired - D-38; SELECT-only"
        bigint project_id FK
        bigint from_bfc_node_id FK
        bool from_is_process FK "generated guard"
        bigint to_bfc_node_id FK
        bool to_is_process FK "generated guard"
        varchar flow_type "SEQUENCE | CONDITIONAL | PARALLEL | HANDOFF"
        varchar condition_label
        smallint seq_no
        text note
    }
    DATA_ENTITY {
        bigint data_entity_id PK
        bigint project_id FK
        varchar de_number
        varchar de_name
        text description
        text business_owner_note
    }
    DATA_FIELD {
        bigint data_field_id PK
        bigint project_id FK
        bigint data_entity_id FK
        int seq_no
        varchar field_name
        bigint data_type_code_id FK "nullable - D-26"
        int length_val
        int precision_val
        int scale_val
        bool is_mandatory "nullable = unknown"
        bool is_primary_key
        smallint pk_ordinal
        bool is_foreign_key
        bigint ref_data_entity_id FK
        bigint ref_data_field_id FK
        smallint fk_group_no "which relationship to ref entity; NULL iff not FK"
        text description
    }
    BUSINESS_REQUIREMENT {
        bigint br_id PK
        bigint project_id FK
        bigint bfc_node_id FK "immutable"
        bool node_is_process FK "generated guard"
        varchar node_bfc_set FK "generated: TO_BE - S7-2"
        varchar br_number
        text br_statement
        text business_logic "legacy, read-only - S11-1"
        text output_expectation "legacy, read-only - S11-1"
        bigint status_code_id FK
    }
    BR_REQUIREMENT_LINE {
        bigint br_requirement_line_id PK
        bigint project_id FK
        bigint br_id FK "UK (br_id, line_no)"
        smallint line_no "minted, never reused"
        smallint seq_no "display order"
        bigint line_kind_code_id FK "BR_LINE_KIND"
        bigint priority_code_id FK "BR_PRIORITY, nullable"
        text line_text
    }
    BR_DATA_FIELD {
        bigint br_data_field_id PK
        bigint project_id FK
        bigint br_id FK "UK (br_id, data_field_id, crud_code)"
        bigint data_entity_id FK
        char crud_code "C R U"
        bigint data_field_id FK
        text usage_note
    }
    BR_SYSTEM_FLOW {
        bigint br_system_flow_id PK
        bigint project_id FK
        bigint br_id FK "UK (br, entity, from, to)"
        bigint data_entity_id FK
        bigint source_application_id FK
        bigint target_application_id FK
        text flow_note
    }
    BR_DATA_ENTITY {
        bigint br_data_entity_id PK
        bigint project_id FK
        bigint br_id FK "UK (br_id, data_entity_id, crud_code)"
        bigint data_entity_id FK
        char crud_code "C R U D"
        char direction "generated from crud_code"
        bigint bfc_node_id FK "copy of the BR's node - D-24"
        bool io_is_active FK "generated guard"
        text usage_note
    }
    BR_ORG_ROLE {
        bigint br_org_role_id PK
        bigint project_id FK
        bigint br_id FK "UK (br_id, org_role_id, raci_code_id)"
        bigint org_role_id FK
        bigint raci_code_id FK
        varchar raci_category FK "generated: RACI_TYPE"
        varchar raci_behaviour FK "copy, FK-verified - Q7"
    }
    FUNCTION_REQUIREMENT {
        bigint fr_id PK
        bigint project_id FK
        bigint solution_id FK "nullable tag - D-28, D-52"
        varchar fr_number
        varchar fr_name
        text description
        bigint fr_type_code_id FK
        varchar fr_type_category FK "generated: FR_TYPE"
        varchar fr_type_behaviour FK "copy, FK-verified"
        bigint complexity_code_id FK "NULL together with effort_days"
        numeric effort_days "derived at save"
        bigint fulfilment_status_code_id FK
        text acceptance_note
    }
    BR_FUNCTION_REQUIREMENT {
        bigint br_function_requirement_id PK
        bigint project_id FK
        bigint br_id FK "UK (br_id, fr_id)"
        bigint fr_id FK
        text coverage_note
    }
    SOLUTION {
        bigint solution_id PK
        bigint project_id FK
        varchar solution_number
        varchar solution_name
        text description
        bigint category_code_id FK
        bigint status_code_id FK
        text benefit_note
        text effort_note
    }
    BR_SOLUTION {
        bigint br_solution_id PK
        bigint project_id FK
        bigint br_id FK "UK (br_id, solution_id)"
        bigint solution_id FK
        text coverage_note
    }
    APPLICATION {
        bigint application_id PK
        bigint project_id FK
        varchar application_code
        varchar application_name
        varchar vendor
        varchar version_label
        bigint app_kind_code_id FK "nullable"
        bigint lifecycle_code_id FK
        text description
    }
    APPLICATION_SOLUTION {
        bigint application_solution_id PK
        bigint project_id FK
        bigint application_id FK "UK (application_id, solution_id)"
        bigint solution_id FK
        text allocation_note
    }
    APPLICATION_BFC_NODE {
        bigint application_bfc_node_id PK
        bigint project_id FK
        bigint application_id FK "UK (application_id, bfc_node_id)"
        bigint bfc_node_id FK
        bool node_is_process FK "generated guard"
        text support_note
    }
    STAKEHOLDER {
        bigint stakeholder_id PK
        bigint project_id FK
        bigint org_unit_id FK
        varchar stakeholder_name
        varchar job_title
        varchar email
        bool is_bpo
    }
    EXTERNAL_ENTITY {
        bigint external_entity_id PK
        bigint project_id FK
        varchar ext_number "EXT-0001"
        varchar ext_name
        bigint kind_code_id FK "EXTERNAL_ENTITY_KIND, nullable"
        text description
    }
    BFC_NODE_EXTERNAL_FLOW {
        bigint bfc_node_external_flow_id PK
        bigint project_id FK
        bigint bfc_node_id FK
        bool node_is_process FK "generated guard"
        bigint external_entity_id FK
        char direction "I = party to step, O = step to party"
        bigint data_entity_id FK "nullable"
        bool io_is_active FK "generated guard"
        varchar flow_label
        text note
    }
    FR_INTERFACE {
        bigint fr_id PK, FK
        bigint project_id FK
        varchar fr_type_behaviour FK "generated: INTERFACE if active"
        bigint source_application_id FK
        bigint target_application_id FK
        bigint pattern_code_id FK
        bigint method_code_id FK
        bigint frequency_code_id FK
        text volume_note
    }
    FR_INTERFACE_DATA_ENTITY {
        bigint fr_interface_data_entity_id PK
        bigint project_id FK
        bigint fr_id FK "UK (fr_id, data_entity_id)"
        bigint data_entity_id FK
        bool interface_is_active FK "generated guard"
        text note
    }
    DIAGRAM_LAYOUT {
        bigint diagram_layout_id PK
        bigint project_id FK
        varchar diagram_type "ERD | DFD (PROCESS_FLOW: history rows only)"
        bigint scope_bfc_node_id FK "NULL = whole project (ERD only)"
        bigint bfc_node_id FK
        bigint data_entity_id FK
        bigint external_entity_id FK
        bigint bfc_node_flow_id FK "history rows only"
        bigint process_trigger_id FK
        numeric x
        numeric y
        numeric width
        numeric height
        bool is_collapsed
    }
    ISSUE {
        bigint issue_id PK
        bigint project_id FK
        varchar issue_number
        varchar title
        text description
        bigint severity_code_id FK
        bigint issue_type_code_id FK
        bigint status_code_id FK
        bigint raised_by_stakeholder_id FK
        bigint recorded_by_user_id FK
        date raised_date
        date target_date
        text resolution
        timestamptz resolved_at
        bigint resolved_by_user_id FK
    }
    ISSUE_BR {
        bigint issue_id PK
        bigint br_id PK
        bigint project_id FK
    }
    BASELINE {
        bigint baseline_id PK
        bigint project_id FK
        int major_no
        int minor_no
        varchar version_label "generated: v major.minor"
        bigint status_code_id FK
        smallint hash_spec_version
        varchar data_model_depth "copied from the project"
        varchar_array dfd_rule_to_be "the to-be rule passed; NULL before 13b = D-38 rule"
        varchar_array dfd_rule_as_is "the as-is rule passed"
        smallint fte_working_days "FTE basis at the freeze; NULL before 13c"
        numeric fte_hours_per_day
        text note
        bigint prior_baseline_id FK
        timestamptz frozen_at
        bigint frozen_by_user_id FK
        char content_digest
        varchar client_approver_name
        date client_approved_on
        text approval_note
        varchar approval_reference
        timestamptz approved_at
        bigint approved_by_user_id FK
    }
    BASELINE_BUSINESS_REQUIREMENT {
        bigint baseline_business_requirement_id PK
        bigint baseline_id FK
        bigint source_id FK "the live br_id"
        bigint project_id
        bigint bfc_node_id "source id, copied"
        varchar br_number
        text br_statement
        text business_logic
        text output_expectation
        bigint status_code_id "copied, unconstrained"
        varchar status_code
        varchar status_label
        char content_hash
    }
    APP_USER {
        bigint app_user_id PK
        varchar email
        varchar password_hash
        varchar display_name
        bool is_active
        bool is_platform_admin
        varchar user_kind "USER | VIEWER - D-40"
        timestamptz last_login_at
    }
    PROJECT_MEMBER {
        bigint project_member_id PK
        bigint project_id FK
        bool project_is_active FK "generated guard"
        bigint app_user_id FK
        varchar access_level "EDIT | VIEW"
        text member_note
    }
    EFFORT_RATE {
        bigint effort_rate_id PK
        bigint project_id FK "UK (project_id, fr_type_code_id, complexity_code_id)"
        bigint fr_type_code_id FK
        bigint complexity_code_id FK
        numeric standard_days
        text change_rationale "required once changed"
    }
    BENEFIT {
        bigint benefit_id PK
        bigint project_id FK
        varchar benefit_number
        varchar benefit_name
        text description
        bigint benefit_type_code_id FK
        varchar measure_name
        varchar measure_unit
        numeric baseline_value
        numeric target_value
        date realisation_date
        bigint accountable_org_role_id FK
        bigint status_code_id FK
    }
    BENEFIT_SOLUTION {
        bigint benefit_id PK
        bigint solution_id PK
        bigint project_id FK
        numeric contribution_pct
    }
    RISK {
        bigint risk_id PK
        bigint project_id FK
        varchar risk_number
        varchar title
        text description
        bigint probability_code_id FK
        bigint impact_code_id FK
        int exposure_score
        text mitigation
        bigint owner_org_role_id FK
        bigint status_code_id FK
        date target_date
        bigint bfc_node_id FK
        bigint solution_id FK
        bigint materialised_issue_id FK
    }
    CHANGE_REQUEST {
        bigint change_request_id PK
        bigint project_id FK
        varchar cr_number
        varchar title
        text rationale
        bigint against_baseline_id FK
        bigint origin_code_id FK
        numeric effort_delta_days
        numeric benefit_delta_value
        bigint status_code_id FK
        bigint displaces_cr_id FK
        bigint decision_id FK
    }
    CR_IMPACT {
        bigint cr_impact_id PK
        bigint change_request_id FK
        bigint project_id FK
        bigint impacted_br_id FK
        bigint impacted_solution_id FK
        bigint impacted_fr_id FK
        bigint impacted_application_id FK
        bigint impacted_data_entity_id FK
        bigint impacted_phase_id FK
        bigint impacted_benefit_id FK
        varchar impact_type
        numeric effort_delta_days
    }
    DECISION {
        bigint decision_id PK
        bigint project_id FK
        varchar decision_number
        varchar title
        text decision_text
        text alternative_rejected
        varchar analysis_code
        bigint decided_by_user_id FK
        timestamptz decided_at
        bigint dimension_code_id FK
        bigint supersedes_decision_id FK
    }
    PHASE {
        bigint phase_id PK
        bigint project_id FK
        varchar phase_code
        varchar phase_name
        int seq_no
        date start_date
        date end_date
        bigint status_code_id FK
    }
    SOLUTION_PHASE {
        bigint solution_id PK
        bigint phase_id PK
        bigint project_id FK
        numeric portion_pct
    }
    SOLUTION_DEPENDENCY {
        bigint solution_id PK
        bigint depends_on_solution_id PK
        bigint project_id FK
        text note
    }
    WBS_ITEM {
        bigint wbs_item_id PK
        bigint project_id FK
        int ms_unique_id "MS Project Unique ID - business key"
        varchar wbs_code "attribute, not a key"
        varchar task_name
        bigint parent_wbs_item_id FK
        smallint outline_level
        int display_order
        bool is_summary
        bool is_milestone
        date planned_start
        date planned_finish
        date actual_start
        date actual_finish
        numeric percent_complete
        bigint phase_id FK "VB-edited"
        bigint solution_id FK "VB-edited"
        bigint last_import_batch_id FK
    }
    CONTROL_RULE {
        bigint control_rule_id PK
        bigint project_id FK
        varchar analysis_code
        varchar comparison
        numeric threshold_value
        numeric escalate_value
        bigint owner_org_role_id FK
        text prescribed_action
        text escalation_path
        bool is_enabled
        bool is_house_default
        text change_rationale
        timestamptz agreed_at
    }
    IMPORT_BATCH {
        bigint import_batch_id PK
        bigint project_id FK
        varchar target_entity "incl. PROCESS_FLOW, WBS_ITEM"
        varchar source_format "xlsx | vb-process-flow/n.n"
        varchar import_mode "MERGE | REPLACE - flow JSON and WBS"
        bigint anchor_bfc_node_id FK "the flow's parent node"
        varchar file_name
        bigint uploaded_by_user_id FK
        timestamptz uploaded_at
        bigint status_code_id FK
        int row_count
        int error_count
        int warning_count
        int insert_count
        int update_count
        int retire_count
        jsonb file_warning_detail
        timestamptz committed_at
        bigint committed_by_user_id FK
        timestamptz rows_purged_at "Q14"
    }
    IMPORT_ROW {
        bigint import_row_id PK
        bigint import_batch_id FK
        varchar target_entity FK "copied from the batch - S4-2"
        varchar row_kind
        int sheet_row_no "xlsx"
        varchar source_path "JSON Pointer"
        varchar local_key "file-local key"
        varchar source_ref "author provenance"
        varchar business_key "BR number for BR and STEP rows; MS Unique ID for WBS"
        varchar cross_check_key "file hier_code or WBS code - compared, never matched"
        jsonb payload
        varchar verdict "INSERT|UPDATE|MATCH|RETIRE|KEPT"
        bool is_valid
        jsonb error_detail
        jsonb warning_detail
        bigint committed_target_id
    }
    USER_ACCESS_GRANT {
        bigint user_access_grant_id PK "retired - D-40; SELECT-only"
        bigint app_user_id FK
        bigint project_id FK "XOR program_id"
        bigint program_id FK "XOR project_id"
        bigint project_role_code_id FK
        bool scope_is_active FK "generated guard"
        timestamptz granted_at
        bigint granted_by_user_id FK
    }
    AUDIT_EVENT {
        bigint audit_event_id PK
        bigint app_user_id FK
        bigint project_id FK
        varchar event_type
        varchar target_table
        bigint target_id
        timestamptz occurred_at
        inet source_ip
        jsonb detail
    }
```

Multi-column PK markers on the remaining composite-key tables denote the composite key; Mermaid has no
composite notation, so each participating column is marked `PK`. Where a table has a surrogate PK, its
design key is shown as a `UK (…)` note.

**Build status.** The tables of the later waves — `STAKEHOLDER`, `ISSUE`, `ISSUE_BR`, `BENEFIT`,
`BENEFIT_SOLUTION`, `RISK`, `CHANGE_REQUEST`, `CR_IMPACT`, `DECISION`, `PHASE`, `SOLUTION_PHASE`,
`SOLUTION_DEPENDENCY`, `WBS_ITEM`, `CONTROL_RULE` — are designed and not yet built. `FR_BFC_NODE` is retired
and never built (SC-3); it is not drawn.
The `node_live_set` guard on `BFC_NODE_ORG_ROLE` (Slice 10d) is designed and being built. `BFC_NODE_FLOW` (D-38) and
`USER_ACCESS_GRANT` (D-40) are retired: the tables hold history and take no new rows.

---

### 5.3 Entity notes — grain, keys, key attributes

#### Tenancy and shared services

**CLIENT** — one row per client organisation FTC contracts with. PK `client_id`. UK `client_code`. No FKs.

**PROGRAM** *(D-32)* — one row per program: a named group of related projects for one client
("2027 Core Systems Renewal"). PK `program_id`; FK `client_id NOT NULL`. UK `(client_id,
program_code)`; partial UK `(client_id, lower(program_name)) WHERE is_active`. Three composite-FK
targets: UK `(program_id, client_id)`, UK `(program_id, client_id, is_active)` and UK
`(program_id, is_active)`. All three are trivially unique supersets of the PK; they exist only so that
PROJECT (and the retired USER_ACCESS_GRANT) can prove "same client" and "live program". Columns:
`program_code varchar(30) NOT NULL`, `program_name varchar(200) NOT NULL`, `description text`,
plus §5.1 (soft delete, `row_version`).

**A program is a roll-up grouping, never a data layer or an access scope** (D-32, D-40). No live business
table other than `PROJECT` carries `program_id`. There is no program-level BFC, DE, BR, FR, issue or
baseline, and no `PROJECT_SEQUENCE` series (the code is typed by a platform admin). Every program view is
built by calling each per-project report for the program's projects that the caller can see (R2-S2),
computed at read time. Baselines stay per project, and there is no program freeze (D-32). D-32 describes no
program status, dates or manager, so none is modelled (A-65).

**PROJECT** — one row per assessment project for one client. **Each project keeps its own BFC, DEs, BRs,
FRs, issues and baselines, and no data is shared across projects, even inside one program** (D-32). PK
`project_id`; FK `client_id`, `status_code_id`, `program_id` (nullable, D-32). UK `(client_id,
project_code)`; UK `(project_id, is_active)` as the target for live guards (`PROJECT_MEMBER`, and the
retired `USER_ACCESS_GRANT`).

- **Same client as its program, declaratively:** FK `(program_id, client_id) → PROGRAM(program_id,
  client_id)`. A project cannot join another client's program, and a project's `client_id` cannot change
  while it sits in a program. When `program_id` is NULL, MATCH SIMPLE skips the FK.
- **Live program only:** `program_is_active boolean GENERATED ALWAYS AS (CASE WHEN is_active
  THEN TRUE END) STORED` + FK `(program_id, client_id, program_is_active) → PROGRAM(program_id,
  client_id, is_active)` **ON UPDATE NO ACTION**. Retiring a program that still has active
  projects is refused. So is restoring a project into a retired program, or putting an active
  project into one (Q4, by construction).
- **Changing `program_id`** is platform-admin only (Q10), behind a preview and confirm (R2-S3), and audited
  as `PROJECT_PROGRAM_CHANGED` (§7.10a `move_project_program`). It changes roll-ups, not access. The model
  needs no membership-history table: AUDIT_EVENT holds the history.
- **`is_restricted boolean NOT NULL DEFAULT false`** (OR-6). Who sees a project is decided per request
  (D-40): platform admins see every project; staff (`USER`, `VIEWER`) see every project **except a
  restricted one they are not a live `PROJECT_MEMBER` of**, which is 404 to them. **New projects are created
  restricted** (D-62): the create API requires the choice explicitly and the new-project form preselects
  "assigned consultants only". The flag is set or cleared only through a preview → confirm pair that names
  who gains or loses access, audited `PROJECT_RESTRICTED` / `PROJECT_UNRESTRICTED`.
- **`data_model_depth varchar(10) NOT NULL DEFAULT 'FULL'`**, `CHECK (data_model_depth IN ('KEYS_ONLY',
  'FULL'))` (D-39). A CHECK-listed column, not a `code_master` FK, because the code branches on it. Read
  only through `components.depth()`.
- **The FTE basis (D-67, S13-1):** `working_days_per_year smallint NOT NULL DEFAULT 240` (`BETWEEN 1 AND 366`)
  and `hours_per_working_day numeric(4,2) NOT NULL DEFAULT 8.00` (`BETWEEN 0.25 AND 24`); 240 × 8 = 1,920 hours
  per FTE. Written only by `set_fte_basis` (platform admin, audited); copied onto each baseline header.

**PROJECT_DFD_RULE** *(D-70, S13-1)* — one row per (project, chart, required DFD element). PK
`project_dfd_rule_id`; FK `project_id`; `bfc_set_code varchar(10)` (`TO_BE` / `AS_IS`, CHECK-listed);
`element_code varchar(12)`, CHECK-listed `('STARTED','DATA_IN','DATA_OUT','EXTERNAL','ORDER')` (§8). UK
`(project_id, bfc_set_code, element_code)` **full**: re-adding an element restores its row (S1-7). **A live row
means "required", a retired row "not required"**, as `PROJECT_COMPONENT`. `ck_pdr_started_locked CHECK
(element_code <> 'STARTED' OR is_active)`: STARTED is always required. ORDER needs DATA_IN and DATA_OUT on the
same chart — a cross-row rule, held by `dfd_rule.set` (422) and re-proved at freeze by the must-be-empty line
`dfd_rule_invalid`. **One reader**, `dfd_rule.codes(project, chart)`: no live row → `STARTED` + `DATA_OUT`
(fails closed), and `project_without_dfd_rule` refuses the freeze until an admin saves a rule. Changed only by
`dfd_rule.set` (not `RESTORABLE`); concurrency token: the project's `row_version`. **Not shadowed, not in the
freeze set** (a setting, not scope); not step-owned. Every project existing when the table is created gets
`STARTED` + `DATA_OUT` on both charts, whatever its `is_active`, by the migration that creates it (the table is
born empty and must equal the fixed rule), with one `PROJECT_DFD_RULE_BACKFILLED` audit event per project; a
new project starts with the recommended set (to-be: STARTED, DATA_IN, DATA_OUT, ORDER; as-is: STARTED).

**PROJECT_COMPONENT** *(D-37)* — one row per component switched on for one project. PK
`project_component_id` (the stable `source_id` for its baseline shadow); FK `project_id`,
`(component_code_id, component_category) → CODE_MASTER(code_id, category)` with `component_category`
generated `'PROJECT_COMPONENT'`. UK `(project_id, component_code_id)` **full**. **A live row means "on", a
retired row "off"**; switching a component back on restores the same row. On/off goes only through
`components.set_components`, which audits it (not `RESTORABLE` through the generic restore route). A
component cannot be switched off while it has live rows (OR-1); switching one on also switches on what it
needs (OR-2). The components, their dependencies and their live-row tests are listed in §8 and
`services/components.py` (`COMPONENT_REQUIRES`, `COMPONENT_ROWS`). The to-be BFC, BRs and their CRUD,
step I/O, RACI, data entities and fields, the org chart, external entities and stakeholders are always
on, never components (D-47). Baselined: the live rows *are* the components on.

**PROJECT_TEMPLATE_COMPONENT** *(OR-3)* — one row per (project template × component), global. PK
`project_template_component_id`; category-verified FKs to `PROJECT_TEMPLATE` and `PROJECT_COMPONENT`
codes; UK `(template_code_id, component_code_id)` full. **No `project_id`:** a template is copied once into
`PROJECT_COMPONENT` at `create_project` and never linked afterwards; the `PROJECT_CREATED` audit detail
records which template was used. Seeded by `seeds/seed_project_templates.py`, never Alembic. Not baselined.

**CODE_MASTER** — one row per configurable lookup value, in one category, for one scope. PK `code_id`; FK
`project_id` (**nullable**: `NULL` = FTC-wide default library, non-null = project override). UK
`(project_id, category, code)` as one unique index **NULLS NOT DISTINCT**. UK `(code_id, category)` is the
target of every category-verified code FK (S1-4). `is_system` marks a category the code branches on, which
a project may not rename or retire. Resolution has one owner, `services/code_master.resolve` (A-16).

Categories on `code_master`, because the value set is genuinely client-configurable: **issue severity,
issue type, issue status, BR status, FR fulfilment status, FR complexity, project status, solution status,
application kind, data field data type, org unit level, RACI participation type, FR type (D-27),
interface pattern / method / frequency (D-27), external entity kind (D-24a)**. System categories (`is_system`, code compares their codes): `BASELINE_STATUS`,
`SOLUTION_CATEGORY` (S5-4), `APP_LIFECYCLE`, `IMPORT_STATUS` (global tier only, S4-7), and the global-only
`PROJECT_COMPONENT` and `PROJECT_TEMPLATE` (labels editable). `FLOW_TYPE` (S2-1) and `PROJECT_ROLE` (D-40)
are retired categories: their codes stay for the rows that reference them, inactive.

Deliberately **not** routed through `code_master`: `BFC_NODE.level_no` (a structural integer with a hard
`CHECK BETWEEN 1 AND 5`), `BFC_NODE.is_process` (D-23), `BFC_NODE.bfc_set_code` and
`performer_kind`, `PROCESS_TRIGGER.trigger_kind`, `BR_DATA_ENTITY.crud_code` and `direction` (§5.4.2),
`DIAGRAM_LAYOUT.diagram_type`, `PROJECT.data_model_depth`, `APP_USER.user_kind`,
`PROJECT_MEMBER.access_level`, `BFC_NODE_FLOW.flow_type`, `CODE_MASTER.behaviour_code` (closed vocabularies
that code branches on, §8), and anything boolean.

**Behaviour: what the application branches on (D-27, Q7).** Two categories have labels and codes a project
may configure, and they still need a stable meaning the code can branch on. **FR type** (`FR_TYPE`, seeded
FORM / INTERFACE / REPORT / BATCH, editable per project) and **RACI participation** (`RACI_TYPE`, seeded
R / A / C / I, configurable because clients use RASCI, RAPID or a house variant). The application never
branches on `code`. It branches on **`behaviour_code`**, one nullable column:

- `behaviour_code varchar(20) NULL`
- `CHECK ((category IN ('FR_TYPE','RACI_TYPE')) = (behaviour_code IS NOT NULL))`: every row in
  the two categories has a behaviour, and no other row has one.
- `CHECK (category <> 'FR_TYPE' OR behaviour_code IN ('FORM','INTERFACE','REPORT','BATCH','OTHER'))`
- `CHECK (category <> 'RACI_TYPE' OR behaviour_code IN ('RESPONSIBLE','ACCOUNTABLE','CONSULTED','INFORMED','SUPPORT','OTHER'))`
  (Q7). RASCI's S maps to SUPPORT. RAPID is a **mapping** in the seed, not a sixth vocabulary:
  Decide → ACCOUNTABLE, Perform → RESPONSIBLE, Input → CONSULTED, Recommend / Agree → OTHER.
- **`UNIQUE (code_id, category, behaviour_code)`** is the composite-FK target. The **category** is in it
  because the two vocabularies share `OTHER`, so behaviour alone does not prove which category a code
  belongs to.

Every referencing row carries a **generated constant category** and a **copy of the behaviour**, and
references all three columns **ON UPDATE NO ACTION**:

```
FUNCTION_REQUIREMENT (fr_type_code_id, fr_type_category = 'FR_TYPE', fr_type_behaviour)
BFC_NODE_ORG_ROLE    (raci_code_id,    raci_category    = 'RACI_TYPE', raci_behaviour)
BR_ORG_ROLE          (raci_code_id,    raci_category    = 'RACI_TYPE', raci_behaviour)
   → CODE_MASTER (code_id, category, behaviour_code)                       NO ACTION
```

Three things follow from it, all declarative:
1. **The code FK provably points at the right category.** An `fr_type_code_id` or a `raci_code_id` aimed
   at an ISSUE_SEVERITY row cannot be stored.
2. **A behaviour is immutable once any row references its code (Q6, R2-D8).** Changing `behaviour_code`
   changes a referenced key, so NO ACTION refuses it while *any* FR or RACI link, active or retired, points
   at the code. It needs no trigger and no service guard, and it covers global and project codes alike. An
   unreferenced code may still change behaviour. A project that wants a different behaviour adds a new code
   and moves its rows to it.
3. **Single-accountable rules can be declared,** because the literal sits on the link row
   (BFC_NODE_ORG_ROLE / BR_ORG_ROLE, below): `WHERE raci_behaviour = 'ACCOUNTABLE'`. A partial unique on
   the letter `'A'` over a code FK could not be expressed (R2-D11).

*Fallback on a build that refuses a constant generated column:* a plain column `DEFAULT 'FR_TYPE'` with
`CHECK (fr_type_category = 'FR_TYPE')`. The effect is identical.

Why a column and not a `jsonb` bag or a separate `FR_TYPE` / `RACI_TYPE` table: a column is checkable and
joinable, and it is the only option of the three that the composite-FK pattern can reach. A separate table
would move a category out of the lookup mechanism that §9.3 says owns all of them.

**PROJECT_SEQUENCE** — one row per (project, number series). PK `(project_id, sequence_code)`,
where `sequence_code ∈ {DE, BR, FR, ISSUE, SOL, BEN, RSK, CR, DEC, EXT}` under a CHECK on that
list. **All ten rows are seeded by `create_project` in the project's own transaction (R2-D14).**
"Every project has all ten" is a mandatory-child rule, which cannot be declared. So `next_number`
**raises** on a missing row and never inserts one lazily: a lazy insert races, because two first-ever
numbers would both try to create the row. `consistency_check` reports `project_sequence_missing`. There is
deliberately no interface series (D-27), no WBS series (the key is MS Project's Unique ID, D-33), no
program series (a program is not project-scoped), and no trigger series (triggers are named, D-49). As-is processes mint no number. Attributes
`prefix`, `pad_width`, `last_value`. See §5.4.6.

#### Client organisation (area 8)

**ORG_UNIT** — one row per organisational unit at any of three levels, within one project. PK
`org_unit_id`; FK `project_id`, `parent_org_unit_id` (self, nullable), `level_code_id` (category-verified,
`ORG_UNIT_LEVEL`, S1-4). UK `(org_unit_id, project_id)` as a composite-FK target. Partial UK
`(project_id, lower(btrim(org_unit_code))) WHERE is_active` (S1-6). Sibling order: `UNIQUE (project_id,
parent_org_unit_id, seq_no) NULLS NOT DISTINCT WHERE is_active` (S1-1), with `CHECK (seq_no <> 0 AND
seq_no BETWEEN -99 AND 99)` (S1-3: at most 99 siblings, negatives only mid-reorder). Constraints:
`CHECK (level_no BETWEEN 1 AND 3)`, `CHECK ((level_no = 1) = (parent_org_unit_id IS NULL))`, and the
composite FK `(parent_org_unit_id, project_id) → ORG_UNIT(org_unit_id, project_id)`, so a Division can
never be parented into another project's Department. Depth consistency (`child.level_no =
parent.level_no + 1`) is held by the service and `consistency_check` (S1-7). `level_no`, `seq_no` and the
parent are set by the service, never the request.

**ORG_ROLE** — one row per role defined within one org unit. PK `org_role_id`; FK `project_id`, composite
`(org_unit_id, project_id) → ORG_UNIT` (S1-7). UK `(org_role_id, project_id)`; partial UK `(project_id,
lower(btrim(org_role_code))) WHERE is_active` (S1-6). `CHECK (headcount IS NULL OR headcount >= 0)`.
**Named `ORG_ROLE`, never `ROLE`**, and the app-side vocabulary is `project_role_code` / access levels
(D-9, D-40). The bare word `ROLE` is banned from the schema, the SQLAlchemy models and the API paths
(`/org-roles`) — it is also a PostgreSQL reserved word, which makes the rule self-enforcing.

#### Business Function Chart (area 1)

**BFC_NODE** — one row per node in one of the project's business process hierarchies, at any level 1–5.
PK `bfc_node_id`; FK `project_id`, `parent_bfc_node_id`. UK `(bfc_node_id, project_id)`, UK
`(bfc_node_id, project_id, is_process)` and UK `(bfc_node_id, project_id, bfc_set_code)` as composite-FK
targets. Partial UKs:
- **`(project_id, bfc_set_code, hier_code) WHERE is_active`** (R2-D10). A retired node keeps the code it
  last had as history, and must not block its reuse by a live node. So **`hier_code` is not an
  identifier** (D-10): two rows, one retired, may share a code, and every lookup by code filters
  `is_active`. That is why imports identify steps by BR number (§5.4.18, R2-D1). Restoring a node whose
  code a live node now holds is refused by the index; the service renumbers the restored node into its
  parent (§7.12 `restore`).
- `(project_id, bfc_set_code, parent_bfc_node_id, seq_no) NULLS NOT DISTINCT WHERE is_active`: sibling
  order, L1 included, per set (S1-1). `CHECK (seq_no <> 0 AND seq_no BETWEEN -99 AND 99)` (S1-3).
  `hier_code` is `varchar(40)`, re-coded in two phases on reorder (S1-2).
- **`(parent_bfc_node_id, lower(btrim(node_name))) WHERE is_active AND is_process`** (Q1): two live
  process steps under one parent cannot share a name. Promoting a node to process when a process sibling
  already has its name is refused. The service check is wider and refuses any active sibling with the same
  normalised name, filtering by set at L1 (§7.2 `assert_name_free`, Q1), so the index is the backstop for
  steps rather than the whole rule.

**`bfc_set_code varchar(10) NOT NULL`**, `CHECK (bfc_set_code IN ('TO_BE','AS_IS'))` (D-47). A project
holds a to-be chart and, when the `AS_IS` component is on, a separate as-is chart, each with its own
processes, performers and data flows. **Immutable.** A child is always in its parent's set: FK
`(parent_bfc_node_id, project_id, bfc_set_code) → BFC_NODE(bfc_node_id, project_id, bfc_set_code)` ON
UPDATE NO ACTION. Both sets share the project's data entities, external entities, triggers, org chart and
applications, so as-is and to-be compare on the same numbers. One set can be started by copying the whole
other set into an empty set (§7.2, `BFC_SET_COPIED`); there is no provenance column, because a to-be
process may merge or split as-is ones.

**`is_process boolean NOT NULL DEFAULT FALSE`** (D-23) marks a **process node**: the lowest node of its
branch, which carries the step I/O, the performer, the triggers, the external flows and — by set — the BR
(to-be) or the step's RACI and supporting applications (as-is). It is a **stored, declared fact**, not
derived from "has no children", for two reasons. A CHECK cannot see other rows. And a leaf is not yet a
process while the consultant is still drafting the branch, so deriving it would make a BR appear and
vanish as children are added.

Constraints:
- `CHECK (level_no BETWEEN 1 AND 5)`; `CHECK ((level_no = 1) = (parent_bfc_node_id IS NULL))`
- `CHECK (NOT is_process OR level_no >= 3)`: a process sits at L3–L5 (A-47)
- `CHECK (level_no < 5 OR is_process)`: an L5 node can have no children, so it is always a process
  (A-54). Together with the guard below, this also enforces "no level 6".
- `CHECK (is_process OR data_processing_desc IS NULL)`: only a process step carries the processing
  description
- **Parent guard, so a process cannot have children:**
  `parent_is_process boolean GENERATED ALWAYS AS (CASE WHEN is_active THEN FALSE END) STORED`
  + FK `(parent_bfc_node_id, project_id, parent_is_process) → bfc_node(bfc_node_id, project_id,
  is_process)` **ON UPDATE NO ACTION**, alongside the plain FK `(parent_bfc_node_id, project_id)
  → bfc_node(bfc_node_id, project_id)` that guarantees existence and tenancy for every row,
  active or not.

How the guard behaves, since this is what D-23 rests on:
- **Adding a child to a process** inserts a row whose FK asks for `(parent, project, FALSE)`. The
  parent's key is `(…, TRUE)`, so the insert is refused.
- **Promoting a node that has active children** (`UPDATE … SET is_process = TRUE`) changes a
  referenced key that active children still point at, so NO ACTION refuses it. **It must not be
  `ON UPDATE CASCADE`.** That would try to write TRUE into the children, and PostgreSQL rejects a
  cascade into a generated column at DDL time anyway, which is a useful tripwire.
- **Soft-deleted children do not block promotion.** Their guard is NULL, so MATCH SIMPLE skips
  the FK. Restoring one under a node that has since become a process recomputes the guard to
  FALSE and is refused, which is correct.
- **Demotion** (`is_process → FALSE`) changes the key that every active step-level dependent references
  (BR, step I/O, step roles, triggers, external flows, as-is application links), so the DB refuses it
  until they are retired. `data_processing_desc` and the performer must be cleared too, by the CHECKs.
  Demotion is refused with a 409 naming the blockers (R2-P5, A-48); nothing cascades.
- **Retiring a process step** is the one cascade: the step retires with the rows listed in
  `services/step_retire.OWNED`, in one confirmed, undoable action (S3-SR).
- *Fallback if a target PostgreSQL build refuses a generated column in an FK:* a plain column
  plus `CHECK (parent_is_process IS NOT DISTINCT FROM CASE WHEN is_active THEN FALSE END)`. The
  effect is the same, and the soft-delete service writes the column.

Depth consistency (`child.level_no = parent.level_no + 1`) stays with the service and
`consistency_check` (`level_no_drift`).

**The performer: one per process (D-46).** The swimlane is the performer: the department, position, IT
system or AI that carries out the process. It is an exclusive arc of typed columns on the process row, so
it is frozen with the process and diffs as a CHANGED field:
- `performer_kind varchar(12) NULL`, `CHECK (performer_kind IS NULL OR performer_kind IN
  ('ORG_UNIT','ORG_ROLE','APPLICATION','AI'))`. NULL = not yet assigned.
- `performer_org_unit_id`, `performer_org_role_id`, `performer_application_id`, each nullable, each with a
  composite `(…, project_id)` FK to its table, ON UPDATE NO ACTION.
- `performer_label varchar(200) NULL`, which names an AI performer and is allowed only for `AI`.
- `ck_bfc_performer_arc`: exactly the reference column the kind names is set (none for `AI` or NULL);
  `ck_bfc_performer_label` / `ck_bfc_performer_ai_label`: an AI performer has a non-blank label and no
  other kind has one; `ck_bfc_performer_process CHECK (performer_kind IS NULL OR is_process)`.
- Retiring an org unit, role or application that performs a live process is refused with a 409 naming the
  processes (R2-D2). A system that *supports* a human performer is not the performer: it is an
  `APPLICATION_BFC_NODE` row (as-is) or comes through the BR's solutions (to-be).
- Zero performers is legal while drafting. The process is drawn in the "unassigned" lane and listed by
  `process_completeness.no_performer` as a warning that does not block the freeze.

**The volume figures: optional, per process (D-67, S13-1).** Columns on the process row, like the performer,
so they are frozen with the process and diff as CHANGED fields; hashed from **hash spec 3**:
- `runs_per_period numeric(11,2)` with `volume_period_code varchar(10)` (CHECK-listed `DAY` / `WEEK` / `MONTH` /
  `QUARTER` / `YEAR`), both or neither (`ck_bfc_volume_run_pair`) — "3" means nothing without "a week".
- `transactions_per_run numeric(14,2)`, with an optional `transaction_unit_code_id` (`TRANSACTION_UNIT`,
  category-in-key FK, library or project override) that needs a count (`ck_bfc_volume_unit`).
- `seconds_per_transaction numeric(12,3)` — seconds to the millisecond, so a 0.3 s automated step and a
  6-minute manual one fit the same type; a shadow column's type never changes, so the types hold both ends.
- `ck_bfc_volume_nonneg` (each ≥ 0); `ck_bfc_volume_process` (a non-process row holds none, as
  `ck_bfc_desc_process_only`). Caps are service constants, not CHECKs. **No hours or FTE column exists**:
  both are derived on read from these figures and the project's FTE basis (VB law 6). Written only by
  `process_volume.set`; a chart copy carries them; demoting a process with volume is refused.

**A single self-referencing table, not five typed tables.** Every read is a tree read (breadcrumb,
drilldown, full-chart export); with five tables each becomes a five-way join with a hand-written UNION for
"search all nodes by name", insert/move logic multiplies by five, and vertical relabelling ("we want a
level between 3 and 4") becomes a migration rather than a data change. The one thing typed tables buy,
different attributes per node kind, is real (only a process has `data_processing_desc`, a performer, and
step-level links), but it is a *subtype* problem of *process vs. non-process* (D-23), not of level. The
cost in one table is a few `CHECK`s plus a process guard on each step-level link. For PostgreSQL:
`hier_code` is indexed with `varchar_pattern_ops` (per project and set) so `LIKE '01.02.%'` subtree
queries use the index; if the chart ever exceeds a few thousand nodes, add `ltree`.

**BFC_NODE_DATA_ENTITY** — one row per (process node, data entity, direction). **The one record of a
step's inputs and outputs (D-24)**, written only by `step_io.ensure_step_io` (R2-D13); the DFD, BR CRUD and the
completeness rule all read it. A step has 0..N inputs and 0..N outputs. PK `bfc_node_data_entity_id`
(S1-5); UK `(bfc_node_id, data_entity_id, direction)`, `CHECK (direction IN ('I','O'))`. Direction is in
the key because a step can both read and write the same entity. FKs: `(bfc_node_id, project_id) →
BFC_NODE`, `(data_entity_id, project_id) → DATA_ENTITY`, and the **process guard**: `node_is_process
boolean GENERATED ALWAYS AS (CASE WHEN is_active THEN TRUE END) STORED` + FK `(bfc_node_id, project_id,
node_is_process) → BFC_NODE(bfc_node_id, project_id, is_process)`. **UK `(bfc_node_id, data_entity_id,
direction, is_active)`** is the target that BR CRUD and external flows reference (§5.4.2 D-24 note). It is
a superset of the grain, so it is trivially unique, and it exists only so that retiring an I/O row counts as
a key change.

**Order between processes is derived from this table, never stored (D-38):** B follows A when B reads a
data entity A writes. A branch is two different outputs feeding different processes; a loop is a later
process writing what an earlier one reads, and is legal (rework is ordinary business behaviour; the
generator ranks through strongly connected components, §7.2a).

**BFC_NODE_ORG_ROLE** — one row per (**as-is** process node, org role, RACI code) (D-64, S10d-1). PK
`bfc_node_org_role_id` (S1-5); UK `(bfc_node_id, org_role_id, raci_code_id)` full. The same
`node_is_process` guard as `BFC_NODE_DATA_ENTITY`. **Q7:** `raci_category varchar(40) GENERATED ALWAYS AS
('RACI_TYPE') STORED`, `raci_behaviour varchar(20) NOT NULL` (a copy the service writes from the code),
and FK `(raci_code_id, raci_category, raci_behaviour) → CODE_MASTER(code_id, category, behaviour_code)` NO
ACTION.
- **One RACI per process, chosen by chart (D-64):** a to-be process's roles are its BR's
  (`BR_ORG_ROLE`); an as-is process (which has no BR) keeps its roles here. Guard: `node_live_set
  varchar(10) GENERATED ALWAYS AS (CASE WHEN is_active THEN 'AS_IS' END) STORED` + FK `(bfc_node_id,
  project_id, node_live_set) → BFC_NODE(bfc_node_id, project_id, bfc_set_code)` ON UPDATE NO ACTION. A live
  or restored row on a to-be step fails at the database; retired rows are not checked. One read function,
  `raci.process_roles(node)`, picks the right list.
- **At most one Accountable per step:** partial `UNIQUE (bfc_node_id) WHERE is_active AND raci_behaviour
  = 'ACCOUNTABLE'`. Several Responsible roles are normal: the lane is the performer, not the `R` (D-46).
  "At least one Accountable" is a completeness report (§5.4.5).

**PROCESS_TRIGGER** *(D-49)* — one row per named time or event trigger in one project ("Month-end close",
"Customer calls"), shared by both sets. PK `process_trigger_id`; FK `project_id`. `trigger_name
varchar(200) NOT NULL`, `trigger_kind varchar(10) NOT NULL CHECK (trigger_kind IN ('TIME','EVENT'))`,
`schedule_note varchar(200) NULL` with `CHECK (schedule_note IS NULL OR trigger_kind = 'TIME')`,
`description text`. UK `(process_trigger_id, project_id)` (composite target); partial UK `(project_id,
lower(btrim(trigger_name))) WHERE is_active` (S1-6); `CHECK (btrim(trigger_name) <> '')`. **No number
series:** a trigger is identified by name in the UI and the flow file. A catalogue, because "month-end"
starts many processes and per-process text would drift. Retiring one with live links is refused with a 409
naming the processes.

**BFC_NODE_TRIGGER** *(D-49)* — one row per (process node × trigger): this trigger starts this process. PK
`bfc_node_trigger_id` (S1-5); UK `(bfc_node_id, process_trigger_id)` **full**, so re-linking restores.
FKs: `(bfc_node_id, project_id)` with the `node_is_process` guard; `(process_trigger_id, project_id) →
PROCESS_TRIGGER`. `note text`. Step-owned: it retires and restores with its step (`step_retire.OWNED`). A
live trigger link counts as an input for the completeness rule (D-38, D-49, §7.2a).

**BFC_NODE_FLOW** *(retired, D-38)* — held one flow edge between two process steps (D-20). Order is now
derived from step I/O. **The table is history only:** every row is soft-retired, the application role holds
SELECT but no INSERT or UPDATE, and the model is read-only; no route, report, freeze or step retire touches
it, and a step restore skips its keys in older events. What the rows still hold: PK `bfc_node_flow_id`;
nullable `from_bfc_node_id` / `to_bfc_node_id` (a NULL end was a start or end event,
`CHECK (num_nonnulls(from_bfc_node_id, to_bfc_node_id) >= 1)`), each with the composite FK and a process
guard; `flow_type` CHECK-listed `('SEQUENCE','CONDITIONAL','PARALLEL','HANDOFF')` (S2-1) with
`CHECK (flow_type <> 'CONDITIONAL' OR condition_label IS NOT NULL)` and a non-blank label CHECK;
`seq_no` 1–99 (S2-3); and the partial natural key `(from_bfc_node_id, to_bfc_node_id,
lower(btrim(condition_label))) NULLS NOT DISTINCT WHERE is_active` (Q2). Never baselined.

**EXTERNAL_ENTITY** *(D-24a)* — one row per party outside the client organisation that exchanges
data with the client's process steps (a Customer, a Bank, a Regulator, a Supplier), within one
project. PK `external_entity_id`; FK `project_id`, `kind_code_id` (nullable, category-verified →
`EXTERNAL_ENTITY_KIND`; an unknown kind is a warning, not a block, because an imported flow
often names a party without classifying it). UK `(project_id, ext_number)` → `EXT-0001`, a full
constraint, so numbers are never reused. Partial UK `(project_id, lower(btrim(ext_name))) WHERE
is_active` (S1-6), because two active "Customer" parties in one project is a modelling error. UK
`(external_entity_id, project_id)` is the composite-FK target. **It is not a `STAKEHOLDER`**: a
stakeholder is a named person who raises issues, while an external entity is a *role in a data
flow* ("Customer" is thousands of people and one box on a DFD). **It is not an `APPLICATION`**
either: the bank's system, if the interface list needs it, is an application; the bank is the
party.

**BFC_NODE_EXTERNAL_FLOW** *(D-24a)* — one row per (process node × external entity × direction ×
data entity), where the data entity is **nullable**, for an exchange whose data is not yet
modelled ("the customer phones in"). The key is a surrogate `bfc_node_external_flow_id` plus
**`UNIQUE NULLS NOT DISTINCT (bfc_node_id, external_entity_id, direction, data_entity_id)`**. This is a
full constraint, not partial: re-adding a removed flow restores the row, so its baseline `source_id` stays
stable and a diff does not report REMOVED + ADDED. `direction` is from the **step's** point of view, the
same axis as `BFC_NODE_DATA_ENTITY`: `'I'` = the party sends to the step, `'O'` = the step sends to the
party. `CHECK (direction IN ('I','O'))`. `flow_label varchar(200) NULL` names an informal exchange when
no DE is given.

FKs: `(bfc_node_id, project_id)` and the `node_is_process` guard (process steps only);
`(external_entity_id, project_id)`; `(data_entity_id, project_id)`; and, **when a DE is named,
the D-24 rule applied again**: `io_is_active boolean GENERATED ALWAYS AS (CASE WHEN is_active
THEN TRUE END) STORED` + FK `(bfc_node_id, data_entity_id, direction, io_is_active) →
BFC_NODE_DATA_ENTITY(bfc_node_id, data_entity_id, direction, is_active)`. "Customer → Sales
order → Receive order" is **also** an input of Receive order, and the model refuses to hold the
external flow without the step I/O it describes, so the DFD can never disagree with a step's inputs. A
null DE skips this FK. The service creates the missing I/O row in the same transaction through the same
`ensure_step_io` as BR CRUD (R2-D13). For `generate_dfd`: an I/O row that has a matching external flow is
drawn from/to the party; the store is still drawn, because another step may read it.

#### Data entities (area 3)

**DATA_ENTITY** — one row per logical data entity in one project, shared by both BFC sets (D-47). PK
`data_entity_id`; FK `project_id`. **UK `(project_id, de_number)`**, full — this is the uniqueness
guarantee; the generator is a convenience, the constraint is the law. Partial UK `(project_id,
lower(btrim(de_name))) WHERE is_active` (S1-6): two live entities called "Customer" in one project is a
modelling error the DB rejects. UK `(data_entity_id, project_id)` is the composite-FK target.

**DATA_FIELD** — one row per **logical** field within one data entity (D-26). VB models a
logical data model and never generates tables, so **a partial list is the normal state**: a DE
may list only its keys and key attributes. How much is expected is the project's `data_model_depth`
(D-39): `KEYS_ONLY` expects primary and foreign keys; `FULL` also warns when an entity has keys but no
other attributes. Extra fields are always accepted. PK `data_field_id`; FK `project_id`,
`(data_entity_id, project_id) → DATA_ENTITY`, `data_type_code_id` (**nullable**, category-verified
`FIELD_DATA_TYPE`), `ref_data_entity_id` (nullable), `ref_data_field_id` (nullable). Partial UKs among live
rows: `(data_entity_id, lower(btrim(field_name)))` (S1-6), `(data_entity_id, pk_ordinal) WHERE
is_primary_key`, `(data_entity_id, seq_no)`; `CHECK (seq_no <> 0 AND seq_no BETWEEN -999 AND 999)` (S1-3),
reordered in two phases (S1-2). UK `(data_field_id, data_entity_id)` is a composite-FK target.

**`is_mandatory boolean NULL`**: TRUE mandatory, FALSE optional, NULL *not yet known*. There is no
`is_nullable` column: storing both would hold the dependency `is_mandatory = NOT is_nullable` inside one row,
the same 3NF defect §5.4.2 removed from CRUD/direction. The ERD reads it: an FK whose fields are all
mandatory draws the parent side as `||`, and one with any field optional *or unknown* draws `o|`. Unknown
renders as optional on purpose, because a diagram must not claim a rule nobody stated (A-53, §7.4).

Composite PKs are representable: several fields in one DE with `is_primary_key = true` and distinct
`pk_ordinal` 1..n. Constraints: `CHECK (is_primary_key = (pk_ordinal IS NOT NULL))`, `CHECK (pk_ordinal
IS NULL OR pk_ordinal >= 1)`, `CHECK (is_foreign_key = (ref_data_entity_id IS NOT NULL))`, `CHECK
(ref_data_field_id IS NULL OR is_foreign_key)`, the composite FK `(ref_data_entity_id, project_id) →
DATA_ENTITY` and `(ref_data_field_id, ref_data_entity_id) → DATA_FIELD(data_field_id, data_entity_id)`
(the referenced field is in the referenced entity, and that entity is in this project, finding D9), and
`CHECK (NOT is_primary_key OR is_mandatory IS DISTINCT FROM FALSE)`, because a key field cannot be
optional (it may be unknown while the model is being drafted).

**Logical FK groups.** One entity may hold two relationships to the same parent:
`Order.ship_to_address_id → Address` and `Order.bill_to_address_id → Address`. With `ref_data_entity_id`
alone, the ERD would see one relationship with two fields and draw one composite FK. **`fk_group_no
smallint NULL`** says which relationship a field belongs to. **A relationship is the set of fields in one
DE sharing `(ref_data_entity_id, fk_group_no)`.** Ship-to is group 1 and bill-to is group 2. A composite
FK is several fields in one group.

- `CHECK ((fk_group_no IS NOT NULL) = is_foreign_key)`: every FK field is in exactly one group, and a
  non-FK field is in none. The request names the relationship (`new` or an existing group); the service
  assigns the number, never stored as sent (S1-7).
- `CHECK (fk_group_no IS NULL OR fk_group_no >= 1)`.
- Partial `UNIQUE (data_entity_id, ref_data_entity_id, fk_group_no, ref_data_field_id) WHERE
  is_active AND ref_data_field_id IS NOT NULL`: within one relationship, a parent field is
  referenced at most once. Two groups may both reference `Address.address_id`, which is the point.
- ERD derivation (A-53) runs **per group**. The parent side is `||` when every field of the group is
  mandatory. The child side is `1` when the group's field set equals the DE's PK set. The arity check
  against the parent PK stays a warning, because a partial field list is normal (D-26).
- *Gap, not modelled:* a **role name** for the relationship ("ship to", "bill to") for the ERD edge label.
  It depends on `(data_entity_id, ref_data_entity_id, fk_group_no)` and not on any one field; on
  `DATA_FIELD` it would repeat across the group's fields (a 2NF defect). If the canvas needs it, it is a new
  entity, `DATA_ENTITY_RELATIONSHIP`, keyed on that triple.

`length_val` / `precision_val` / `scale_val` stay optional and are meaningful only for some types. That is
*not* a normalization defect: they depend on the field, not on the type. Rules: `CHECK (data_type_code_id
IS NOT NULL OR num_nulls(length_val, precision_val, scale_val) = 3)`, because a length with no type has
nothing to be a length of; and positive sizes with `scale_val <= precision_val`. Which types show which of
the three is a UI rule that belongs on the `FIELD_DATA_TYPE` code_master rows, not in React; if it is
wanted, it is a second use of the `behaviour_code` column (§5.3 CODE_MASTER).

#### Business Requirement (area 2)

**BUSINESS_REQUIREMENT** — one row per **to-be process node** (D-2, D-23, S7-2). PK `br_id`; FK
`project_id`, `bfc_node_id`, `status_code_id` (category-verified `BR_STATUS`). UK `(project_id,
br_number)`; UK `(br_id, project_id)`; **partial UK `(bfc_node_id) WHERE is_active`**, the 1:1, which is
partial so that a retired BR does not occupy the node forever (P5).
- **Process guard:** `node_is_process boolean GENERATED ALWAYS AS (CASE WHEN is_active THEN TRUE END)
  STORED` + FK `(bfc_node_id, project_id, node_is_process) → BFC_NODE(bfc_node_id, project_id,
  is_process)`, beside the plain `(bfc_node_id, project_id)` FK: "process only" and "same project".
  A retired BR's guard is NULL, so it neither blocks demotion nor prevents a replacement BR.
- **To-be guard (S7-2):** `node_bfc_set varchar(10) GENERATED ALWAYS AS ('TO_BE') STORED` + FK
  `(bfc_node_id, project_id, node_bfc_set) → BFC_NODE(bfc_node_id, project_id, bfc_set_code)` ON UPDATE NO
  ACTION. A BR on an as-is node is impossible in the database. As-is processes carry no BR, no BR CRUD and
  no solutions.
- **UK `(br_id, project_id, bfc_node_id)`** is the target that carries the BR's node down to
  `BR_DATA_ENTITY` (D-24).
- `bfc_node_id` is **immutable**: a BR never moves between nodes (service-enforced, S1-7; the FK from
  `BR_DATA_ENTITY` would refuse it anyway once any CRUD exists).
- **Created empty with its process** (S1-7): `br_statement` is NULL until written, and the service sets
  `BR_STATUS/DRAFT`. `BASELINED` / `SUPERSEDED` are set only by the baseline freeze (S1-8).
- "Every to-be process node has an active BR" is a mandatory child, which is not declarable. It is
  service-guaranteed (`create_node` / `mark_process`) and reported by `consistency_check`
  (`process_without_br`, to-be only).

**The BR number is the step's import identity (R2-D1).** To-be process node ↔ active BR is 1:1 (D-2),
`br_number` is never reused (full UK), and `bfc_node_id` on the BR is immutable. So `br_number`
identifies the step more stably than the node's own `hier_code`, which changes on every reorder and is
only partially unique (R2-D10). Both importers (the BR sheet and the flow file's steps) therefore
**resolve an existing step by BR number**. A `hier_code` in the file is kept in
`IMPORT_ROW.cross_check_key` and only *compared*: a mismatch is a warning naming both codes, never a second
lookup (§5.4.18). An as-is anchor has no BR numbers.

**BR_DATA_ENTITY** — one row per (BR, data entity, CRUD operation). PK `br_data_entity_id` (S1-5); UK
`(br_id, data_entity_id, crud_code)`, where `crud_code char(1) CHECK (crud_code IN ('C','R','U','D'))`
(a CHECK, not a code_master FK: §5.4.2, §8). `direction` is **generated** (`R → 'I'`, else `'O'`).
`bfc_node_id bigint NOT NULL` is a copy of the BR's node, made safe by FK `(br_id, project_id,
bfc_node_id) → BUSINESS_REQUIREMENT(br_id, project_id, bfc_node_id)`. `io_is_active boolean GENERATED
ALWAYS AS (CASE WHEN is_active THEN TRUE END) STORED` and the **licence FK** `(bfc_node_id,
data_entity_id, direction, io_is_active) → BFC_NODE_DATA_ENTITY(bfc_node_id, data_entity_id, direction,
is_active)` (D-24). In words: **an active Read needs an active input row for that DE on the BR's own
step, and an active Create/Update/Delete needs an active output row.** Both sides of the FK come from
things the DB derives itself (the BR's node, the generated direction), so a disagreement cannot be stored.
See §5.4.2 (D-24 note) for the cost.

**BR_ORG_ROLE** — one row per (BR, org role, RACI code): **the RACI of a to-be process** (D-64). PK
`br_org_role_id` (S1-5); UK `(br_id, org_role_id, raci_code_id)` full. It has the same `raci_category` /
`raci_behaviour` columns and FK as `BFC_NODE_ORG_ROLE`. **At most one Accountable per BR:** partial
`UNIQUE (br_id) WHERE is_active AND raci_behaviour = 'ACCOUNTABLE'`. The rule keys on behaviour, not on the
letter `A`: `raci_code_id` is an FK and the letter lives on another table (R2-D11), and a client's
Accountable letter need not be `A`. See §5.4.5.

**BR_REQUIREMENT_LINE** *(D-59, S11-1)* — one row per numbered requirement statement within one BR. PK
`br_requirement_line_id`; FK `(br_id, project_id) → BUSINESS_REQUIREMENT`; `line_no smallint` (≥ 1), **minted
by the service** as max + 1 over all the BR's lines, retired ones included — never reused, never from a body —
UK `(br_id, line_no)` full; `seq_no smallint`, the display order, unique among live lines (a position column:
reordering is not a scope change); `line_kind_code_id` (`BR_LINE_KIND`) and nullable `priority_code_id`
(`BR_PRIORITY`), each with the category-in-key pattern; `line_text text NOT NULL`, non-blank. These are per-BR
ordinals, not one of the ten project series. The BR's priority is the highest of its live lines, derived.
`business_logic` and `output_expectation` stay on `BUSINESS_REQUIREMENT` untouched (so its shadow and hash list
do not move) and are read-only; each live BR's non-blank text is copied once, by the seed command `seeds.backfill_br_lines` run after `seed_code_master` (a migration cannot reach the seeded line kinds),
into one RULE and one OUTPUT line.

**BR_DATA_FIELD** *(D-60b, S11-1)* — one row per (BR, data attribute, C / R / U). PK `br_data_field_id`; UK
`(br_id, data_field_id, crud_code)` full; `CHECK (crud_code IN ('C','R','U'))` — Delete is entity-level only.
**The licence chain, one level down:** `brde_is_active` GENERATED and `fk_brdf_licence (br_id, data_entity_id,
crud_code, brde_is_active) → BR_DATA_ENTITY` (needs the additive UK `uq_brde_live_licence`), so a live attribute
row needs a live entity row with the same CRUD; `(data_field_id, data_entity_id) → DATA_FIELD` proves the
attribute belongs to that entity. `usage_note text NULL`. Step-owned through the BR, in a tier ahead of
`BR_DATA_ENTITY`, so it retires before and restores after its licence.

**BR_SYSTEM_FLOW** *(D-61, S11-1, S11-2)* — one row per (BR, data entity, from-application, to-application, kind). PK
`br_system_flow_id`; `flow_kind_code varchar(12) NOT NULL DEFAULT 'INTEGRATION'`, `ck_brsf_kind CHECK (flow_kind_code IN
('INTEGRATION','MIGRATION'))` (CHECK-listed: coverage branches on it); UK on those five, full; composite FKs to `BUSINESS_REQUIREMENT`, `DATA_ENTITY` and twice to
`APPLICATION`; `CHECK (source_application_id <> target_application_id)`; `flow_note text NULL`. To-be only,
as its BR. Gated by APPLICATION. **No pointer to an FR**: coverage by an interface FR is derived (same BR, same
source and target, the entity carried), whatever the FR's behaviour — a migration flow is often covered by a batch
FR (S11-4). Every flow starts as `INTEGRATION`. A data entity names no master system (S11-3).

#### Function Requirement (area 4)

**FUNCTION_REQUIREMENT** — one row per FTC-authored system function specification in one project. PK
`fr_id`; FK `project_id`, **`solution_id` (nullable, D-28)**, `fr_type_code_id` (D-27),
`complexity_code_id` (category-verified `FR_COMPLEXITY`), `fulfilment_status_code_id` (category-verified
`FR_FULFILMENT_STATUS`). UK `(project_id, fr_number)`; UK `(fr_id, project_id)`; **UK `(fr_id,
project_id, fr_type_behaviour)`** as the target for `FR_INTERFACE`. FR names are not unique (S6a-2); a live
duplicate under the same solution warns. `CHECK (btrim(fr_name) <> '')`.

- **BR ↔ FR is the stored many-to-many `BR_FUNCTION_REQUIREMENT`** (D-52). The solution is optional.
- **`solution_id` is the FR's solution tag** (D-28, D-52): stored once per FR, so its effort counts toward
  exactly one solution however many BRs it serves. `(solution_id, project_id) → SOLUTION` applies when
  present and is skipped when NULL. **The tag must answer at least one of the BRs the FR serves**: if the
  FR has live BR links, `solution_id` is NULL or the solution of a live `BR_SOLUTION` of at least one of
  them (service-enforced, it reads other tables). An FR with no BR link may carry any live solution of its
  project. Drift is warned, never blocked or cascaded.
- **An FR with no BR link is a warning** (`fr_unlinked` / untraced, the import preview, the control panel),
  never an error. A BR with no FR is legal.
- **D-27: `fr_type_behaviour varchar(20) NOT NULL`** is a copy of the type's behaviour, and
  **`fr_type_category varchar(40) GENERATED ALWAYS AS ('FR_TYPE') STORED`**. Both are verified by FK
  `(fr_type_code_id, fr_type_category, fr_type_behaviour) → CODE_MASTER(code_id, category,
  behaviour_code)` **ON UPDATE NO ACTION** (Q6, R2-D8). The service writes the copy from the code at save,
  and the FK rejects a wrong copy. Changing a type's behaviour is refused while any FR, live or retired,
  uses the type, so a global code can never write into other projects' FRs.
- **Effort (D-13):** `complexity_code_id` and `effort_days numeric(7,2)` are NULL together, `CHECK
  ((complexity_code_id IS NULL) = (effort_days IS NULL))`, `effort_days >= 0`. `effort_days` is derived
  at save from the rate card and stored, never accepted from a request (A-38).
- **Retiring an FR** with live BR links is refused with a 409 naming the BRs (S10b-2), and with live
  interface detail until the detail is removed (S6b-3).
- `fulfilment_status` encodes "FTC specifies, vendor builds later"; the first status is SPECIFIED
  (S6a-5). No vendor entity exists in the MVP.

**BR_FUNCTION_REQUIREMENT** *(D-52)* — one row per pairing of a BR with an FR that serves it. M:N: one
FORM serves several BRs, and one BR needs a FORM plus a BATCH plus an INTERFACE (§5.4.3). PK
`br_function_requirement_id` (S1-5); UK `(br_id, fr_id)` **full**, so a re-link restores the old row and
keeps its baseline `source_id`. FKs `(br_id, project_id) → BUSINESS_REQUIREMENT`, `(fr_id, project_id) →
FUNCTION_REQUIREMENT`: a cross-project pairing is impossible. `coverage_note text` ("this FR covers only the
validation half of BR-0042"), edited in place. **The solution is not in the grain**: it lives once on the
FR. No CHECK is needed: the BR's guards mean a link can only reach a to-be process's BR. Owned by the BR:
retires and restores with its step (`step_retire.OWNED_BY_BR`). Written from the BR screen, where the FR's
tag is picked from that BR's live solutions only (422 otherwise; the server never creates a `BR_SOLUTION`
as a side effect). The view `v_br_function_requirement` reads this table (with `tag_answers_br`) and
serves every flat BR → FR read.

**SOLUTION** *(D-7)* — one row per transformation answer within one project. PK `solution_id`; FK
`project_id`, `category_code_id`, `status_code_id` (both category-verified). UK `(project_id,
solution_number)` → `SOL-0001`; partial UK `(project_id, lower(btrim(solution_name))) WHERE is_active`
(S5-5). `category_code_id` resolves to **ORG_AND_RULES / PEOPLE / PROCESS / DATA / TECHNOLOGY**, a system
category (S5-4). New solutions start PROPOSED (S5-5). A solution in the first three categories legitimately
has no Function Requirements at all — not every answer is software.

**BR_SOLUTION** *(D-7)* — one row per (BR, solution) pairing. PK `br_solution_id` (S1-5); UK `(br_id,
solution_id)` full (S5-5). `coverage_note` carries the relationship-specific fact ("this solution answers
only the approval half of BR-0042"), edited in place (S5-3). M:N: one solution normally answers several
requirements, and one requirement may need an org change *and* a system function. Retires and restores
with its BR's step (S5-1). A REJECTED solution can be linked; the link shows its status and coverage does
not count it as an answer (S5-2).

**APPLICATION** *(D-8)* — one row per application or technology in one project's landscape, shared by
both sets. PK `application_id`; FK `project_id`, `app_kind_code_id` (nullable), `lifecycle_code_id`
(both category-verified). UK `(project_id, application_code)` full, so a retired code is never reused;
`CHECK (application_code ~ '^[A-Z0-9._-]+$')`; partial UK on the live normalised name (S6b-2). The code is
editable until a baseline freezes it, the old code going to the audit (S6b-6); a code freed by a rename
may be taken by another application (S6b-7). `lifecycle_code` is **AS_IS / TO_BE / BOTH**, a system
category, which lets one catalogue serve the current and the target landscape.

**APPLICATION_SOLUTION** *(D-8)* — one row per (application, solution) allocation: the to-be side, what
will deliver this answer. PK `application_solution_id` (S1-5); UK `(application_id, solution_id)` full.
Never for an AS_IS application (R2-D11, service-enforced; consistency line `as_is_allocated`).

**APPLICATION_BFC_NODE** *(D-8, D-23)* — one row per (application, **process node**) support statement:
what supports the process's performer today (the clerk works in SAP). PK `application_bfc_node_id`
(S1-5); UK `(application_id, bfc_node_id)` full; the `node_is_process` guard. **New rows only on as-is
processes** (service 422 on a to-be process): to-be systems come from BR → Solution → Application (D-22,
D-8). Rows left on to-be processes are listed by the informational line `as_is_support_on_to_be`. A system
that *performs* the process is the performer of kind `APPLICATION`, not a row here. A TO_BE application as
today's support warns and is allowed, and is not counted as today's support in `application_gap`
(S6b-4, S6b-5). Retires and restores with its step (S6b-1). **The gap between this table and
`APPLICATION_SOLUTION` is the deliverable.**

**STAKEHOLDER** *(D-4)* — one row per named client-side person in one project. PK `stakeholder_id`; FK
`project_id`, `org_unit_id`. Partial UK `(project_id, lower(stakeholder_name)) WHERE is_active` (D6).
`is_bpo` separates BPO staff from the client's own business users, because they answer to a different
contract. It is the raiser of an issue, and carries interview and workshop provenance in later increments.
Not baselined (a person is not scope).

**FR_BFC_NODE** — **retired, never built** (SC-3). The direct BR ↔ FR link (D-52) carries that coverage; there
is no table and no shadow.

**FR_INTERFACE** *(D-27)* — **one row per interface-type FR** (1:0..1). It holds what only an
interface has. PK and FK `fr_id`; FK `project_id`. Columns: `source_application_id NOT NULL`,
`target_application_id NOT NULL`, `pattern_code_id` (→ `INTERFACE_PATTERN`: PUSH / PULL /
BIDIRECTIONAL), `method_code_id` (→ `INTERFACE_METHOD`: API / FILE / DB / MESSAGE / MANUAL),
`frequency_code_id` (→ `INTERFACE_FREQUENCY`: REALTIME … ON_DEMAND), `volume_note text`. The three codes
are nullable (not yet known) and category-verified. The two applications are not nullable, because they
are the row's reason to exist. An interface FR whose endpoints are unknown has **no** `FR_INTERFACE` row
and is listed as incomplete (A-55). An interface is **complete** with source, target, method and at least
one carried entity; pattern and frequency are optional (S6b2-1). Constraints:
- `(source_application_id, project_id)` and `(target_application_id, project_id) →
  APPLICATION(application_id, project_id)`: both endpoints in the FR's project.
- `CHECK (source_application_id <> target_application_id)`.
- **Behaviour guard:** `fr_type_behaviour varchar(20) GENERATED ALWAYS AS (CASE WHEN is_active
  THEN 'INTERFACE' END) STORED` + FK `(fr_id, project_id, fr_type_behaviour) →
  FUNCTION_REQUIREMENT(fr_id, project_id, fr_type_behaviour)`, beside the plain `(fr_id,
  project_id)` FK. **"FR_INTERFACE only when the FR's type behaviour is INTERFACE" is therefore
  declarative**, and it also blocks retyping an FR away from INTERFACE while its interface
  detail is active (§5.4.8).
- UK `(fr_id, project_id)` and UK `(fr_id, project_id, is_active)` as targets for the junction
  below.

Why a 1:0..1 subtype table rather than six nullable columns on the FR: the attributes depend on
the FR only when its behaviour is INTERFACE. As columns they would be NULL for most FRs, and a CHECK
tying them to a behaviour held on another table cannot be written. As a table, the guard FK is
one declaration, and `FR_INTERFACE_DATA_ENTITY` can reference *interface FRs only*.

**FR_INTERFACE_DATA_ENTITY** *(D-27)* — one row per (interface FR × data entity) it carries. PK
`fr_interface_data_entity_id` (S1-5); UK `(fr_id, data_entity_id)` full; FK `project_id`; `note text`, the
carried-entity note shown on the vendor list and edited on the interface card (S6b2-4). FKs:
`(data_entity_id, project_id) → DATA_ENTITY`; `(fr_id, project_id) → FR_INTERFACE`; and a guard
`interface_is_active boolean GENERATED ALWAYS AS (CASE WHEN is_active THEN TRUE END) STORED` + FK
`(fr_id, project_id, interface_is_active) → FR_INTERFACE(fr_id, project_id, is_active)`. Retiring the
interface detail while it still lists active carried entities is refused, which closes the "live child
under a dead parent" class (D1) by construction.

**The interface list is a view, not a table (D-27).** Identity is the FR number. There is no
second number series to keep in step:

```sql
CREATE VIEW v_interface_list WITH (security_invoker = true) AS
SELECT
    fr.project_id,
    fr.fr_id,
    fr.fr_number                        AS interface_number,   -- identity = FR number (D-27)
    fr.fr_name                          AS interface_name,
    ft.code                             AS fr_type_code,
    ft.label                            AS fr_type_label,
    (fi.fr_id IS NOT NULL)              AS is_described,       -- FALSE → listed as incomplete
    fi.source_application_id,
    sa.application_code                 AS source_application_code,
    sa.application_name                 AS source_application_name,
    fi.target_application_id,
    ta.application_code                 AS target_application_code,
    ta.application_name                 AS target_application_name,
    pat.code AS pattern_code,   pat.label AS pattern_label,
    met.code AS method_code,    met.label AS method_label,
    frq.code AS frequency_code, frq.label AS frequency_label,
    fi.volume_note,
    ARRAY(SELECT de.de_number
          FROM   fr_interface_data_entity fide
          JOIN   data_entity de ON de.data_entity_id = fide.data_entity_id
          WHERE  fide.fr_id = fr.fr_id AND fide.is_active AND de.is_active
          ORDER  BY de.de_number)       AS data_entity_numbers,
    fr.solution_id,
    s.solution_number,                                          -- NULL = untagged (D-28, D-52)
    ARRAY(SELECT br.br_number
          FROM   v_br_function_requirement v                    -- reads BR_FUNCTION_REQUIREMENT (D-52)
          JOIN   business_requirement br ON br.br_id = v.br_id
          WHERE  v.fr_id = fr.fr_id AND br.is_active
          ORDER  BY br.br_number)       AS br_numbers,
    fs.code  AS fulfilment_status_code, fs.label AS fulfilment_status_label,
    fr.complexity_code_id,
    fr.effort_days
FROM       function_requirement fr
JOIN       code_master ft  ON ft.code_id  = fr.fr_type_code_id
LEFT JOIN  fr_interface fi ON fi.fr_id    = fr.fr_id AND fi.is_active
LEFT JOIN  application sa  ON sa.application_id = fi.source_application_id
LEFT JOIN  application ta  ON ta.application_id = fi.target_application_id
LEFT JOIN  code_master pat ON pat.code_id = fi.pattern_code_id
LEFT JOIN  code_master met ON met.code_id = fi.method_code_id
LEFT JOIN  code_master frq ON frq.code_id = fi.frequency_code_id
LEFT JOIN  solution s      ON s.solution_id = fr.solution_id AND s.is_active
LEFT JOIN  code_master fs  ON fs.code_id  = fr.fulfilment_status_code_id
WHERE  fr.is_active
AND    fr.fr_type_behaviour = 'INTERFACE';   -- behaviour, never code: a renamed type still lists
```

It is project-scoped by the caller (`reports.interface_list` filters `project_id` after
`require_project`), like every view here. `interface_load` (§7.9) reads this view and groups by
`(source_application_id, target_application_id)`: the endpoint is a stated fact, not inferred through
`APPLICATION_SOLUTION`. A pair filter is direction-as-stored, with BIDIRECTIONAL matching either way
(S6b2-3).

#### Issues (area 5)

**ISSUE** — one row per issue raised in one project (component `ISSUE`). PK `issue_id`; FK `project_id`,
`severity_code_id`, `issue_type_code_id`, `status_code_id`, **`raised_by_stakeholder_id NOT NULL`** (the
client-side person who raised it) and **`recorded_by_user_id NOT NULL`** (the consultant who typed it)
(D-4, D8). UK `(project_id, issue_number)`. Resolution is `resolution text`, `resolved_at timestamptz`,
`resolved_by_user_id`; there is no `resolved_date`.

The issue is anchored to the **project**, not to a BR: an issue found during discovery, before any BR
exists, still needs somewhere to live. BR linkage is optional and multiple.

**ISSUE_BR** — one row per (issue, BR) association. PK `(issue_id, br_id)`. See §3.3 for the cardinality
argument.

#### Control framework (D-13…D-19)

**EFFORT_RATE** — one row per (project × **FR type** × complexity) (D-13, D-27). PK `effort_rate_id`
(identity); UK `(project_id, fr_type_code_id, complexity_code_id)` **full**, the natural key. Both code
FKs are category-verified (`FR_TYPE`, `FR_COMPLEXITY`). `standard_days numeric(7,2) NOT NULL`, `CHECK
(standard_days > 0)`; a cell above 60 man-days needs confirmation and is flagged (S6c-7). Seeded from the
FTC default card at `create_project` (placeholder values until FTC confirms them, S6c-1), then negotiated
per client; confirmed defaults update untouched cells only, through an audited command (S6c-6). Read only
through `services/effort.rate_for`. **Changing a rate never reprices existing FRs** (A-38, S6c-2):
`FUNCTION_REQUIREMENT.effort_days` is derived at save and stored; the screen shows a standing per-cell
"not at current rate" count, and re-rating is per FR, audited (S6c-5). The card keys on the **type**, not
the behaviour. A project override of a global type gets a new `code_id`, and `maintain_fr_types` re-points
the project's rate rows and FRs to it in one transaction; the surrogate PK keeps a re-pointed rate the same
row to the diff, not REMOVED + ADDED.

**Rate changes are audited and frozen (R2-D7)**, because they answer different questions:
- **Audit** answers *who changed the rate, when, from what, and why*. `change_rationale text NULL` holds
  the reason for the current value, under **`CHECK (row_version = 1 OR change_rationale IS NOT NULL)`**
  and a non-blank CHECK; a trigger demands a rationale on every UPDATE of `standard_days`. Old, new and
  rationale go to `AUDIT_EVENT` (`RATE_CARD_CHANGED`, §7.13). Nothing reports from the history between
  freezes, so AUDIT_EVENT is the right home.
- **Freeze** answers *what rate card this baseline was priced on*: the commercial term a signed scope was
  agreed at, recoverable with the baseline for five years (Q12). `EFFORT_RATE` is in the freeze set under
  the `EFFORT` component (§6.1); its shadow hashes `fr_type_code`, `complexity_code` and `standard_days`.
  The labels are presentation and the rationale provenance, so neither is hashed.

**BENEFIT** — one row per quantified benefit in one project (D-14, component `BENEFIT`). PK `benefit_id`;
FK `project_id`, `benefit_type_code_id`, `accountable_org_role_id`, `status_code_id`. UK `(project_id,
benefit_number)` → `BEN-0001`. Carries `measure_name`, `measure_unit`, `baseline_value`, `target_value`,
`realisation_date`. **A benefit with no accountable org role is not a benefit, it is a hope** — the FK is
`NOT NULL`.

**BENEFIT_SOLUTION** — one row per (benefit × solution). PK both; `contribution_pct` carries the
relationship-specific fact, because a benefit is rarely delivered by one solution alone and the split is
what is argued about at realisation.

**RISK** — one row per risk in one project (D-15). PK `risk_id`; FK `project_id`, `probability_code_id`,
`impact_code_id`, `owner_org_role_id`, `status_code_id`, optional `bfc_node_id` / `solution_id`, and
`materialised_issue_id` (nullable). UK `(project_id, risk_number)` → `RSK-0001`. `exposure_score` is
derived at save from probability × impact. **Deliberately not merged with `ISSUE`** — an issue has
happened and needs resolution; a risk might happen and needs mitigation. The one path between them is
`promote_risk_to_issue`, which sets `materialised_issue_id` and leaves the risk row intact as the record
that it was foreseen.

**CHANGE_REQUEST** — one row per proposed change to a **frozen** baseline (D-16). PK
`change_request_id`; FK `project_id`, `against_baseline_id NOT NULL` (composite onto `BASELINE(baseline_id,
project_id)`), `origin_code_id`, `status_code_id`, `displaces_cr_id` (nullable self-reference),
`decision_id`. UK `(project_id, cr_number)` → `CR-0001`. `effort_delta_days` and `benefit_delta_value` are
**computed from `CR_IMPACT`, never typed** — a change priced by the person requesting it is not priced.

**Which baselines a CR may target (Q8, DR8-P1, SC-2, R2-D11): FROZEN or APPROVED, or a SUPERSEDED baseline
that carries the agreed client approval (the newest baseline with a recorded approval); never another
SUPERSEDED baseline — and the mechanism is not a CHECK.** A CHECK sees one row of one table, and the status lives on `BASELINE` as a code
FK. It is also a **point-in-time** rule: a CR raised against v1.0 while it was APPROVED stays valid when
v1.1 supersedes v1.0, so a declarative guard that refused superseding a baseline with CRs against it would
be wrong. The mechanism is:

1. `raise_cr` and any retarget read the baseline `SELECT … FOR SHARE`, and check its status code ∈
   {`FROZEN`, `APPROVED`}, or that it is the SUPERSEDED baseline carrying the agreed approval, inside that
   lock (§7.13 `raise_change_request`).
2. `freeze`'s transition of the prior baseline to SUPERSEDED takes that row `FOR UPDATE`, so the two
   serialize. A CR cannot slip in against a baseline in the instant it is superseded.
3. `BASELINE_STATUS` is a system category, because code compares its codes. `DRAFT` is seeded and never
   written.
4. A `consistency_check` for "CR raised on a superseded baseline" is not possible (history is not kept per
   status), so the lock is the whole guarantee, and criterion coverage tests it.

**CR_IMPACT** — one row per impacted object. PK `cr_impact_id`; FK `change_request_id`, `project_id`,
plus **seven nullable typed FKs** — `impacted_br_id`, `impacted_solution_id`, `impacted_fr_id`,
`impacted_application_id`, `impacted_data_entity_id`, `impacted_phase_id`, `impacted_benefit_id` — under
`CHECK (num_nonnulls(...) = 1)`. Every one carries the composite `(id, project_id)` FK pattern of §5.6, so a
CR physically cannot reach into another project's objects. **The database enforces what a row points at**:
typed columns instead of a polymorphic `impacted_entity` + `impacted_id` pair, which would be unenforceable
in SQL and painful in SQLAlchemy. The seven columns are wider but checkable, joinable and cascade-safe, and
"exactly one" is one `CHECK`, not a trigger. Adding an eighth impacted type later is a column and a
migration.

**DECISION** — one row per recorded project decision (D-17). PK `decision_id`; FK `project_id`,
`decided_by_user_id`, `dimension_code_id`, `supersedes_decision_id` (nullable self-reference). UK
`(project_id, decision_number)`. Carries `decision_text`, **`alternative_rejected`** and `analysis_code` —
the analysis it was taken against. The rejected alternative is the field that makes a decision log worth
reading; without it the log records outcomes and loses reasoning.

**`DECISION` is append-only and evidential.** It carries the same `BEFORE UPDATE OR DELETE` reject trigger
as the `baseline_*` shadow tables, is **exempt from soft delete** (no `is_active`, no `deleted_at`), and the
application database role holds no `UPDATE` or `DELETE` privilege on it (§6.6). A decision that can be
edited after the fact is a record of what someone currently wishes had been decided. A superseded decision
is corrected by writing a **new** decision that references the old one via `supersedes_decision_id`, which
also keeps the log readable as a narrative.

**PHASE / SOLUTION_PHASE / SOLUTION_DEPENDENCY** (D-18) — delivery waves, the assignment of solutions to
them (`portion_pct`, because a solution can span waves), and prerequisite links. `SOLUTION_DEPENDENCY` is a
DAG: **cycles are rejected on insert** by a topological check, the opposite of process order, where loops
are legal (BFC_NODE_DATA_ENTITY).

**WBS_ITEM** *(D-33, D-41, Q13, R2-D15)* — one row per imported MS Project task line in one project
(component `WBS`). **Tasks come from MS Project; VB does not author them.** VB holds a read copy of the
plan, the two links consultants own, and — separately — progress recorded in VB (D-41).

- **Key.** PK `wbs_item_id`; **UK `(project_id, ms_unique_id)`**, where `ms_unique_id int NOT NULL`
  is MS Project's *Unique ID*. That is the one task identifier MS Project never reassigns, so it
  is what a re-import updates by (R2-D15). It is a **full** constraint, not partial: a line
  retired by a replace-mode import and back in the next file restores the same row, with its VB
  links intact (A-68). UK `(wbs_item_id, project_id)` is the self-FK target.
- **`wbs_code varchar(50)` is an attribute, not a key** (Q13), and it carries no unique
  constraint. MS Project renumbers WBS codes when a task is moved in the outline, so during a
  re-import two rows legitimately swap codes, and a non-deferrable partial unique index would
  reject the valid file mid-statement. A duplicate code *within one file* is an import error (§7.11a).
- **Hierarchy.** `parent_wbs_item_id` (nullable) with FK `(parent_wbs_item_id, project_id) →
  WBS_ITEM(wbs_item_id, project_id)`; `outline_level smallint NOT NULL CHECK (outline_level >=
  1)`; `CHECK ((outline_level = 1) = (parent_wbs_item_id IS NULL))`; `CHECK (parent_wbs_item_id
  <> wbs_item_id)`. The import resolves the parent from outline order and drops MS Project's
  project-summary task (Unique ID 0). `display_order int NOT NULL` is the file's row order.
  `is_summary` and `is_milestone boolean NOT NULL` are stored **as MS Project states them**: they
  are imported facts, not VB derivations, for the same reason `is_process` is stored — a summary
  line's dates are MS Project's roll-up, and the dashboard must not add them to their children.
- **Imported dates and progress.** `planned_start`, `planned_finish`, `actual_start`, `actual_finish`,
  all `date NULL` (A-66); `CHECK (planned_finish IS NULL OR planned_start IS NULL OR
  planned_finish >= planned_start)`, the same for actuals; `CHECK (actual_finish IS NULL OR
  actual_start IS NOT NULL)`. `percent_complete numeric(5,2) NOT NULL DEFAULT 0 CHECK
  (percent_complete BETWEEN 0 AND 100)`.
- **Progress recorded in VB (D-41, OR-7).** Each progress update against a line — % complete, actual
  start and finish, a status (on track / at risk / late), a comment, and the update's date — is a **new
  dated row**, never an overwrite, so progress over time is kept. VB progress updates are the reporting
  source and are never overwritten by a re-import; the imported actuals above are kept beside them, and the
  progress report flags lines where the two disagree. The progress-update table is named and modelled by
  `apple` when the WBS wave is specced (SC-4); it is not drawn in §5.2 until then.
- **Links (VB-edited, Q13).** `phase_id` and `solution_id`, each nullable (a line may link to either,
  both or neither), with composite FKs `(phase_id, project_id) → PHASE` and `(solution_id, project_id) →
  SOLUTION`, so a link cannot cross projects. A link to a solution not scheduled in the linked phase is a
  dashboard warning, not a constraint: plans legitimately disagree with the wave plan, and that
  disagreement is what the dashboard exists to show.
- **Provenance.** `last_import_batch_id`, composite onto `IMPORT_BATCH(import_batch_id, project_id)` (the
  header survives the 90-day row purge).
- **`row_version` guards only the links (a documented deviation).** A link edit checks and bumps it. The
  import writes the MS-Project-owned columns **without** checking or bumping it and never touches
  `phase_id` / `solution_id`, so a consultant's link edit does not 409 because MS Project moved a date.
  Recorded in `docs/PLAYBOOK_DEVIATIONS.md`.
- **Soft delete as usual.** Only a replace-mode import retires lines, with an acknowledged count, as in
  D-25. Retiring a Phase or Solution that live WBS lines link to is refused with a 409 listing them (Q4).
- **Not baselined** (D-33): the schedule is not agreed scope. No shadow table and no hash. A consequence:
  a baseline diff can never show schedule slip (§5.6).

**CONTROL_RULE** — one row per (project × `analysis_code`), **or one FTC house default** when
`project_id IS NULL` (D-19). PK `control_rule_id`; FK `project_id` (**nullable**), `owner_org_role_id`.
Carries `comparison` (`GT` / `LT` / `PCT_GT`), `threshold_value`, `escalate_value`, `prescribed_action`,
`escalation_path`, `is_enabled`, and the provenance fields `change_rationale` / `agreed_at`.
**`analysis_code` is a closed vocabulary matching the report functions in §7.9 — a rule pointing at an
analysis that does not exist is rejected**, which stops the table filling with aspirational governance.

**Two tiers, as `code_master` has them (A-16).** `project_id IS NULL` is the **FTC house default**,
editable by a platform admin through the app — not a code seed, not a developer change. Non-null is that
project's own agreed rule. Uniqueness is a pair of partial indexes: `UNIQUE (analysis_code) WHERE
project_id IS NULL` and `UNIQUE (project_id, analysis_code) WHERE project_id IS NOT NULL`.

**The resolution rule is the opposite of `code_master`'s, deliberately.** Codes resolve *live*, so
renaming a global label updates every project that has not overridden it. Control rules **do not**:
`create_project` **copies** the house defaults into project rows, and the project's rules are thereafter
independent. Changing the FTC house default affects **future projects only**.

That asymmetry is the point. A project's thresholds are what FTC and the client **agreed at
mobilisation**; if tightening the house standard silently moved a live engagement from GREEN to ESCALATE,
the governance model would be something the client never signed up to. Same reasoning as `effort_days`
(A-38) and the frozen `code_master` labels in `baseline_*` (§5.4.4): **an agreed number is copied, never
referenced.**

`owner_org_role_id` is `NOT NULL` on a project rule and **nullable on a house default** — FTC cannot know
which of a client's roles owns a response before the client's org chart exists, so `create_project`
copies the thresholds and the project assigns the roles at mobilisation. A project rule with no owner is
reported by `coverage` as an incomplete control framework.

#### Diagram presentation (D-29, D-30)

**DIAGRAM_LAYOUT** — one row per (project × diagram type × scope × diagram object): where a consultant put
one box on one diagram. PK `diagram_layout_id`; FK `project_id`.

- `diagram_type varchar(20) NOT NULL CHECK (diagram_type IN ('ERD','PROCESS_FLOW','DFD'))`. A CHECK, not
  code_master, because the renderer and the object rules below branch on it (§8). **`PROCESS_FLOW` rows
  are history only:** they are kept, and the service refuses new ones (D-38, S7-5).
- `scope_bfc_node_id` (nullable): the node a DFD is drawn for, or the BFC branch an ERD is filtered to
  (the "subject area", §7.4). **NULL = the whole project**, ERD only: `CHECK (diagram_type = 'ERD' OR
  scope_bfc_node_id IS NOT NULL)`. The same entity has a different position in each scope. That is why
  scope is in the key, and why x/y depend on the whole key (2NF).
- **The object is five typed nullable FKs, not `object_type × object_id`:** `bfc_node_id` (a process, or a
  boundary process outside the frame), `data_entity_id` (an ERD entity or a DFD store),
  `external_entity_id`, `process_trigger_id` (a trigger's start symbol, D-49), and `bfc_node_flow_id` (the
  start/end event marker of a retired edge; NULL on every new row). `CHECK (num_nonnulls(bfc_node_id,
  data_entity_id, external_entity_id, bfc_node_flow_id, process_trigger_id) = 1)`. Each has the composite
  `(id, project_id)` FK: the database knows what a row points at and that it is in this project, as on
  CR_IMPACT. Scope and object validity beyond that are service-checked (S2-6).
- Per-type object rules: `CHECK (diagram_type <> 'ERD' OR data_entity_id IS NOT NULL)`, `CHECK
  (diagram_type = 'PROCESS_FLOW' OR bfc_node_flow_id IS NULL)`, and `CHECK (diagram_type = 'ERD' OR NOT
  is_collapsed)`.
- `x numeric(10,2) NOT NULL`, `y numeric(10,2) NOT NULL`, `width` / `height numeric(10,2) NULL`
  with `CHECK (width IS NULL OR width > 0)` and the same for height, and `is_collapsed boolean
  NOT NULL DEFAULT FALSE` (the ERD card's "+12 more").
- Natural key: the table constraint `uq_dl_object` = `UNIQUE NULLS NOT DISTINCT (project_id,
  diagram_type, scope_bfc_node_id, bfc_node_id, data_entity_id, external_entity_id, bfc_node_flow_id,
  process_trigger_id)`, a constraint so `save` can upsert `ON CONFLICT ON CONSTRAINT` (S2-6). It also
  serves as the "all positions for this diagram" index.
- Presence columns only: `created_at`, `updated_at`, `created_by`, `updated_by` (§5.1).

**Not baselined, explicitly.** A position is presentation, not scope. Nothing about what was agreed
changes when a box moves, and a baseline that recorded coordinates would report layout churn as scope
change. A frozen baseline re-opened later renders with today's positions for surviving objects and
auto-layout for the rest (A-52). A picture that must be kept is a PNG or PDF export attached to the
sign-off.

**Hard delete: a documented deviation.** `DIAGRAM_LAYOUT` is **hard-deleted and carries no `is_active` /
`deleted_at` / `deleted_by` / `row_version`**, recorded in `docs/PLAYBOOK_DEVIATIONS.md`; the application
role holds DELETE on this table (§6.6). It is referenced by nothing and copied into no baseline, and a
retired coordinate has no evidential value. Soft delete would push the natural key into a partial index and
turn every "reset layout" into a pile of dead rows. Last write wins per object (A-52), so a version column
would only manufacture 409s over a dragged box. `PUT` upserts only the listed objects, and a separate
audited reset clears one diagram (S2-6). The positioned objects themselves are soft-deleted as usual; their
layout rows stay, so a restored entity returns to where it was. Objects with no row are auto-laid-out by
the frontend.

*Not modelled:* lane order, edge waypoints and zoom. Lanes derive from the performer (D-46), so dragging a
process between lanes is not a layout change; it would be a change of performer.

#### Baselines (area 6)

**BASELINE** — one row per frozen version of one project's scope. PK `baseline_id`; FK `project_id`,
`status_code_id` (category-verified `BASELINE_STATUS`: FROZEN → APPROVED → SUPERSEDED, or FROZEN →
SUPERSEDED), `frozen_by_user_id`, `prior_baseline_id`.
- **Identity is two integers** (P9): `major_no >= 1`, `minor_no >= 0`; `version_label` is GENERATED `'v'
  || major_no || '.' || minor_no` STORED, rendered and never parsed. UK `(project_id, major_no,
  minor_no)`; UK `(project_id, version_label)`; UK `(baseline_id, project_id)` as the composite target for
  `prior_baseline_id` and `CHANGE_REQUEST.against_baseline_id`.
- **A straight line, declaratively:** `(prior_baseline_id, project_id) → BASELINE(baseline_id,
  project_id)`; `UNIQUE (prior_baseline_id)` (a baseline is succeeded at most once, A-8); partial
  `UNIQUE (project_id) WHERE prior_baseline_id IS NULL`; `CHECK ((prior_baseline_id IS NULL) = (major_no =
  1 AND minor_no = 0))`. Two simultaneous freezes produce one baseline and one 409 (criterion 37).
- `hash_spec_version smallint NOT NULL` (the hash spec the baseline was frozen under, finding D5);
  `data_model_depth` copied from the project; **`dfd_rule_to_be`, `dfd_rule_as_is varchar(12)[]`** — the rule
  each chart passed, both or neither, NULL on a baseline frozen before the per-chart rule ("D-38 rule", D-70);
  **`fte_working_days smallint`, `fte_hours_per_day numeric(4,2)`** — the FTE basis at the freeze, both or
  neither, required from hash spec 3 (D-67). All four are in the header guard's frozen list, outside
  `content_digest`, like the depth; `content_digest char(64) NOT NULL`, the digest over every
  entity's hashes; `note` (non-blank if present); `frozen_at`, `frozen_by_user_id` — the created pair.
- **Client approval set:** `client_approver_name`, `client_approved_on`, `approved_at`,
  `approved_by_user_id`, all set together or none (`CHECK (num_nonnulls(…) IN (0, 4))`); `approval_note`
  and `approval_reference` (which needs an approver name) are optional.
- **No `is_active` / `deleted_*`** (A-36). Only status, the approval set, `updated_by` and `row_version` may
  change: by column-level UPDATE grant and by the `fn_baseline_header_guard()` `BEFORE UPDATE OR DELETE`
  trigger, which also refuses changing an approval column once set. Status transitions are
  service-enforced under lock (R2-D11).

**BASELINE_\* (shadow tables)** — one row per live row as it stood at freeze time, **generated** by
`services/baseline_shadow.py` and never hand-written (VB law 2). Every shadow has the same shape:
- PK `baseline_<t>_id`; `baseline_id` FK → `BASELINE`; **`source_id`** FK → the live PK, ON DELETE NO
  ACTION; UK `(baseline_id, source_id)`; index on `source_id`.
- The live table's business columns, copied verbatim (FK columns hold *source* ids), minus the §5.1 audit
  columns, the PK and GENERATED columns (guards, `*_category`, `BR_DATA_ENTITY.direction`, which readers
  recompute). **No intra-baseline FKs**: a join inside one baseline is `child.parent_x_id =
  parent.source_id AND child.baseline_id = parent.baseline_id`.
- For every category-verified code FK, a **code pair** `<p>_code` and `<p>_label`: the code is hashed, the
  label is display only (R2-D3), and the unconstrained `<p>_code_id` is still copied. A baseline survives
  later renames or retirements of `code_master` rows (§5.4.4).
- `content_hash char(64) NOT NULL`: hex sha256 over the entity's hashed columns at its hash spec, computed
  in SQL at freeze (§6.1, §7.7). Position columns (`hier_code`, `seq_no`, parent, level) are excluded from
  the hash and drive MOVED (D-10).
- Every column nullable except `baseline_id`, `source_id`, `content_hash` (A-7). Immutable: the
  `fn_reject_modification()` trigger, the insert guard, and no UPDATE/DELETE for the application role.
  A migration that adds a column to a shadowed live table adds the shadow column in the same migration, and
  a shadow column's type is never ALTERed.

**`source_id` is the stable pointer.** A full outer join between two baselines on `source_id` yields added
(right only) / removed (left only) / present-in-both, and `content_hash` inequality among the both-rows
yields *changed* without comparing every column.

**The freeze set** (`services/freeze_set.FREEZE_SET` = `models/baseline.SHADOWED`, in freeze order; full
list, gates and hashed columns in §6.1): `org_unit`, `org_role`, `bfc_node`, `data_entity`, `data_field`,
`external_entity`, `process_trigger`, `bfc_node_data_entity`, `bfc_node_org_role`,
`bfc_node_external_flow`, `bfc_node_trigger`, `business_requirement`, `br_data_entity`, `br_org_role`,
`application`, `solution`, `br_solution`, `function_requirement`, `br_function_requirement`,
`fr_interface`, `fr_interface_data_entity`, `application_solution`, `application_bfc_node`, `effort_rate`,
`project_component` (D-3, D-12, S8-1). Each table is gated by the project's components
(D-37): a closed gate freezes zero rows of that table. **A new entity joining the set bumps the hash spec
and registers its hashed columns under the new version**, so older baselines' digests stay byte-identical
(S10b-1). `issue`, `issue_br`, `benefit`, `benefit_solution`, `phase`, `solution_phase` and
`solution_dependency` join the same way when built. Never baselined: `bfc_node_flow`, `diagram_layout`,
`project_template_component`, `project_member`, `user_access_grant`, `app_user`, `audit_event`,
`import_batch`, `import_row`, `project_sequence`, `code_master`, `project`, `program`, `client`,
`stakeholder`, `wbs_item`, `change_request`, `cr_impact`, `risk`, `decision`.

#### Bulk import staging (D-5, D-25, D-28)

**IMPORT_BATCH** — one row per uploaded file: the import trail (who, when, what, counts, outcome). PK
`import_batch_id`; FK `project_id`, `uploaded_by_user_id`, `committed_by_user_id`, `status_code_id`
(`IMPORT_STATUS`, category-verified), and **`anchor_bfc_node_id`** (nullable, composite with
`project_id`): the process-flow file's parent node, which must be live and not a process (service-checked
at validate and again at commit, S4-9). UK `(import_batch_id, project_id)` (target for
`WBS_ITEM.last_import_batch_id`); UK `(import_batch_id, target_entity)` (target for `IMPORT_ROW`).
- `target_entity CHECK (target_entity IN ('ISSUE','DATA_ENTITY','DATA_FIELD',
  'BUSINESS_REQUIREMENT','FUNCTION_REQUIREMENT','PROCESS_FLOW','WBS_ITEM'))`. BR and FR are D-28,
  PROCESS_FLOW is D-25, WBS_ITEM is D-33. One batch is one target; a workbook with an entities sheet and a
  fields sheet runs as two batches in sequence (S4-12).
- `source_format varchar(40) NOT NULL DEFAULT 'xlsx'`, the file's declared format (e.g.
  `'vb-process-flow/2.0'`), with `CHECK ((target_entity = 'PROCESS_FLOW') = (source_format LIKE
  'vb-process-flow/%'))`. Which versions are *supported* is a service registry, not a CHECK, so a new
  version is a code change, not a migration.
- `import_mode varchar(10) NULL CHECK (import_mode IN ('MERGE','REPLACE'))`, with `CHECK ((target_entity
  IN ('PROCESS_FLOW','WBS_ITEM')) = (import_mode IS NOT NULL))` (D-33) and `CHECK ((target_entity =
  'PROCESS_FLOW') = (anchor_bfc_node_id IS NOT NULL))`.
- Counts: `row_count` (staged rows), `error_count` and `warning_count` (rows, not messages: errors block
  the commit, warnings inform it), `insert_count`, `update_count`, `retire_count` (what a REPLACE commit
  would retire, which the consultant acknowledges). All non-negative and bounded by `row_count`;
  `CHECK (retire_count = 0 OR import_mode = 'REPLACE')` — merge never retires (S4-7).
- `file_warning_detail jsonb NOT NULL DEFAULT '[]'` (array); `committed_at` and `committed_by_user_id` set
  together, after `uploaded_at`; `rows_purged_at` (Q14).
- **Audit shape (S4-6):** no soft delete — its status is its lifecycle, and the application never deletes
  or retires a batch. `row_version` is sent on commit (a stale preview → 409). The application role may
  UPDATE only the lifecycle columns and `file_name`, which the purge blanks to `(purged)` (S4-9, S4-11).

**IMPORT_ROW** — one row per staged sheet row **or staged JSON object**. PK `import_row_id`; FK
`(import_batch_id, target_entity) → IMPORT_BATCH(import_batch_id, target_entity)`: `target_entity` is
copied from the batch by the service, so a row kind can never mismatch its batch (S4-2). One staged row
per sheet row or pointer (UK `(import_batch_id, sheet_row_no)`, UK `(import_batch_id, source_path)`).
A process-flow file is flattened into one row per object, so the preview and the verdicts work per object:
- `row_kind varchar(30) NOT NULL`, under a CHECK over the union and `ck_ir_kind_fits_target`. For a sheet
  it equals `target_entity`. For a flow file it is `STEP`, `STEP_IO`, `STEP_ROLE`, `EXTERNAL_ENTITY`,
  `EXTERNAL_FLOW` or `DATA_ENTITY`. `FLOW_EDGE` and `LANE` stay in the lists so that rows staged under the
  old flow format still satisfy the CHECKs. When the `vb-process-flow/2.0` import is built, the kinds gain
  `PERFORMER` (MATCH only), `TRIGGER` and `STEP_TRIGGER` (S7-1, slice7 §9.9).
- **Locator** (S4-1): RETIRE and KEPT rows are staged from the database and have no file locator; flow rows
  carry `source_path varchar(200)`, the JSON Pointer (`/steps/3/inputs/0`, must start with `/`); sheet rows
  carry `sheet_row_no` (2…1048576).
- `local_key varchar(50) NULL` is the file-local key (`S1`, `D1`, `X1`) that I/O and flows refer to, with
  partial `UNIQUE (import_batch_id, row_kind, local_key) WHERE local_key IS NOT NULL`. `source_ref
  varchar(200) NULL` is the author's provenance ("slide 4, shape 12"), kept verbatim so a human can check
  an AI conversion (§7.2b). Both only on flow rows.
- `business_key varchar(250) NULL`: the BR number for BR and STEP rows (R2-D1), the Unique ID for WBS,
  `DE-nnnn/<normalised field name>` for a data field (S4-5). Partial **`UNIQUE (import_batch_id,
  row_kind, business_key) WHERE business_key IS NOT NULL`**: a file naming the same key twice is a staging
  error, not two updates of one row; duplicates are caught in memory first and staged with the key NULL and
  a `DUPLICATE_KEY` error (S4-4).
- `cross_check_key varchar(100) NULL` holds the file's `hier_code` (for WBS, its WBS code). It is compared
  after resolution and never used to resolve.
- `payload jsonb NOT NULL` (an object). What a RETIRE or KEPT row acts on is `payload.target {table, id,
  label}`, CHECK-required (S4-2); before-values are kept in `payload.before` for the retention window
  (S4-11). Before/after is computed at preview, never stored separately (S4-8).
- `verdict varchar(10) NOT NULL CHECK (verdict IN ('INSERT','UPDATE','MATCH','RETIRE','KEPT'))`. `RETIRE`
  rows are staged from the database in REPLACE mode, so the preview lists what would go. `KEPT` marks a
  step I/O row a replace-mode flow import would have retired, kept because a BR CRUD or an external flow
  depends on it (§7.2b).
- `error_detail` and `warning_detail jsonb NOT NULL DEFAULT '[]'`, arrays of message objects `{code,
  column, message, params}` (S4-8), with `is_valid` consistent with an empty error array.
- `committed_target_id` is an untyped pointer, because staging is forensic. `row_kind` says which table it
  points at; it is set for every committed row except LANE (S4-3).
- **Audit shape (S4-6):** no audit columns, no soft delete, no `row_version`; provenance is the batch.

No new business table serves the flow file: every flow-file object lands in a table already defined.

**Retention (Q14).** `import_row` rows are **deleted** 90 days after `import_batch.uploaded_at` by a
scheduled purge, which locks batches first (`FOR UPDATE SKIP LOCKED`, S4-9). `IMPORT_BATCH.rows_purged_at`
records that the detail is gone. The batch header is **kept** as the import audit trail, and
`WBS_ITEM.last_import_batch_id` points at it. This is one of the two tables where the application role may
DELETE (§6.6).

#### Identity (area 7)

**APP_USER** — one row per **FTC staff member** who can log into Value Bridge (D-11). PK `app_user_id`; UK
`lower(email)` (functional unique index — case-insensitive email is not optional). `password_hash
varchar(255) NOT NULL` — bcrypt/argon2 output, never logged, never serialized by any Pydantic response
model. Access has three kinds of user (D-40), both columns read from the row on every request:
- **`is_platform_admin boolean NOT NULL DEFAULT false`**: every project plus the admin functions
  (users, projects, programs, global codes). It overrides `user_kind`. The FTC default rate card is a fixed
  default in code, not an admin function, until a client needs another (SC-10).
- **`user_kind varchar(20) NOT NULL DEFAULT 'VIEWER'`**, `CHECK (user_kind IN ('USER','VIEWER'))`: USER
  reads and edits, VIEWER reads only. `create_user` requires it in the body; the DB default is the least
  privilege. Changing it is platform-admin only and audited `USER_KIND_CHANGED`.
- Levels rank `VIEW` < `EDIT` < `ADMIN`; only a platform admin reaches `ADMIN`. There is no `APP_ROLE`
  table and no `CLIENT_REVIEWER` role (D-9, D-11).
- **Client viewer (D-43), designed and built with the D-43 slice:** `user_kind` widens to
  `CLIENT_VIEWER`, bound to exactly one project by a nullable `client_project_id` column (`CHECK
  ((user_kind = 'CLIENT_VIEWER') = (client_project_id IS NOT NULL))`, never a platform admin), with the
  client's consent recorded first in a separate `project_client_consent`.

Not `AuditMixin`: its own `created_by` (nullable, the first admin is created by nobody), `updated_by`,
`deleted_at`, `deleted_by`, `row_version`.

**PROJECT_MEMBER** *(OR-6, D-62)* — one row per membership period of one user on one project, with a
level. It matters only while the project is restricted. PK `project_member_id`; FK `project_id`,
`app_user_id`; `access_level varchar(4) NOT NULL CHECK (access_level IN ('EDIT','VIEW'))`; `member_note
text` (non-blank if present: why they are on it). Partial UK `(project_id, app_user_id) WHERE is_active`.
**Re-adding inserts a new row** — each period is history, not a link to restore, and access returns only
through the add route (R2-S5). Live guard: `project_is_active` generated + FK `(project_id,
project_is_active) → PROJECT(project_id, is_active)` ON UPDATE NO ACTION, so a live membership blocks
retiring its project. **Effective level** = the lower of the user's kind cap (USER → EDIT, VIEWER → VIEW)
and `access_level`. Membership on an unrestricted project is allowed and has no effect, so an admin can
prepare the list before restricting. Managed by admins only, audited `MEMBER_ADDED`,
`MEMBER_LEVEL_CHANGED`, `MEMBER_REMOVED`; removal is a soft delete. Never baselined: access is not scope.

**USER_ACCESS_GRANT** *(retired, D-40)* — held one grant of one project role (OWNER / EDITOR / REVIEWER,
D-9) to one user over one project or one program (D-32). Access is now `user_kind` plus `PROJECT_MEMBER`
on restricted projects. **The table is history only:** every grant was copied into `PROJECT_MEMBER`
(OWNER/EDITOR → EDIT, REVIEWER → VIEW) and then soft-revoked with an `ACCESS_REVOKED` audit event (S7-6);
the application role holds SELECT but no INSERT or UPDATE, and the `PROJECT_ROLE` category is retired. What
the rows still hold: PK `user_access_grant_id`; `app_user_id`, `project_id` XOR `program_id` (`CHECK
(num_nonnulls(project_id, program_id) = 1)`), `project_role_code_id`, `granted_at`, `granted_by_user_id`;
the partial UK `(app_user_id) WHERE is_active`; and the `scope_is_active` live guards onto `PROJECT` and
`PROGRAM`. With every row revoked, the guards never block.

**AUDIT_EVENT** — one row per security- or scope-significant event. PK `audit_event_id`; FK
`app_user_id` (nullable — a migration has no actor), `project_id` (nullable — a failed login has no
project). `event_type` is a plain varchar, **not** a code_master FK: audit rows must be writable even if
the lookup table is mid-migration, and an unknown event type should be recorded, not rejected.
`source_ip inet` holds only a valid address. `detail jsonb` holds the variable payload. This is the one
place JSONB earns its keep, because there is no diffing or reporting requirement on it — it is forensic.
Append-only by grant **and** trigger; even the owner role cannot UPDATE it.

---

### 5.4 The judgment calls

Each call below states the current answer and the reasoning that holds it in place. The debate
that led to each one is in the history file.

#### 5.4.1 BR grain — **a separate table, not columns on the process node.**

`BUSINESS_REQUIREMENT` is its own table, keyed to its process node by `bfc_node_id`. It is not
folded into `BFC_NODE`, for three reasons:

- **A BR has inbound references.** Issues (`ISSUE_BR`), solutions (`BR_SOLUTION`), function
  requirements (`BR_FUNCTION_REQUIREMENT`, D-52), RACI (`BR_ORG_ROLE`) and the CRUD grid
  (`BR_DATA_ENTITY`) all point at `br_id`. That FK means "about this requirement", not "about this
  process step". **Things with inbound references are entities, not columns.**
- **Two identifier systems with different lifecycles.** `br_number` (`BR-0042`) never changes and
  must survive the node being reordered. `hier_code` (`01.02.03.04.05`) may change on reorder
  (D-10).
- **No level-dependent column set.** Collapsing would put `br_number`, `br_statement`,
  `business_logic` and `status_code_id` on a table keyed by a node of any level, populated only on
  processes. Every BR query would become a filtered node query.

The cost is a join on every BR screen, on an indexed FK, with the BFC context (`hier_code`,
`node_name`) one row away.

#### 5.4.1a One BR per to-be process (D-2, D-23, S7-2)

**A to-be process node carries exactly one business requirement. An as-is process carries
none.** One BR may still map to many function requirements (D-52).

- **1:1** is `UNIQUE (bfc_node_id)` on `business_requirement` (`uq_br_one_per_node`).
- **Process only** is the D-23 guard: a generated `node_is_process` column in a composite FK onto
  `bfc_node.is_process` (§5.4.7).
- **To-be only** is a generated `node_bfc_set = 'TO_BE'` column in `fk_br_node_to_be
  (bfc_node_id, project_id, node_bfc_set) → bfc_node (uq_bfc_node_set)`, so a BR on an as-is node
  cannot be stored (S7-2).
- **The BR appears with its process.** `create_node` and `mark_process` create the BR in the same
  transaction when a to-be node is created as, or promoted to, a process (§7.2). The consultant
  never creates a BR by hand. They edit the one that appeared with the step.
  "Every to-be process has a live BR" is a mandatory child, so it is service-guaranteed and
  reported (`process_completeness.step_without_br`, to-be only), never a constraint.
- **`business_requirement.bfc_node_id` is immutable** (service-enforced, S1-7).

**The reversal cost is one dropped index.** If a process ever needs two requirements, dropping
the unique constraint makes the model 1:N with no migration of data, no repair and no lost
history. That is why the BR keeps its own table. The alternative, a fake sibling node holding a
second requirement, would corrupt the process hierarchy to store a requirement.

#### 5.4.2 BR ↔ Data Entity — **one associative table, CRUD as the stored axis, direction generated.**

**One table, not two.** `BR_INPUT_DE` and `BR_OUTPUT_DE` would be structurally identical,
differing only in a value (data-as-schema). Every "all DE touches for this BR" query would be a
UNION, and a third direction would be a migration.

**CRUD is stored; direction is derived from it.** `crud_code` determines direction (`R → I`,
`C/U/D → O`). Storing both would hold a functional dependency between two non-key attributes
inside a row (a 3NF break) and would allow an `(R, OUTPUT)` row. So:

- **Grain** `(br_id, data_entity_id, crud_code)`, held by `uq_brde_grain` beside the surrogate PK
  (S1-5). CRUD is in the grain because one BR legitimately reads *and* updates the same entity.
- **`crud_code` is `char(1) CHECK (crud_code IN ('C','R','U','D'))`, not a `code_master` FK.**
  C/R/U/D is a closed four-value vocabulary that no client configures, and a real char column is
  what lets the generated column work.
- **`direction` is a stored generated column**: `GENERATED ALWAYS AS (CASE WHEN crud_code = 'R'
  THEN 'I' ELSE 'O' END) STORED`. It filters, groups and indexes as if stored, and it cannot drift.

`BFC_NODE_DATA_ENTITY` (step I/O) stores direction as a key column and has no CRUD: **the node says
what flows, the BR says what is done to it.**

**The node licenses the BR (D-24).** A BR CRUD row is legal only if the BR's own process step has
the matching I/O row: an **input** for R, an **output** for C/U/D. It is enforced by construction,
with no trigger:

```
BR_DATA_ENTITY (bfc_node_id, data_entity_id, direction, io_is_active)
   → BFC_NODE_DATA_ENTITY (bfc_node_id, data_entity_id, direction, is_active)

bfc_node_id   copied from the BR, verified by FK (br_id, project_id, bfc_node_id) → BR
direction     GENERATED from crud_code
io_is_active  GENERATED: TRUE if active, else NULL
```

What this costs and how each cost is carried:

- **One redundant column**, `BR_DATA_ENTITY.bfc_node_id`. It is transitive through `br_id`, the
  same denormalization as `project_id` everywhere, made safe the same way, by a composite FK (§5.5).
- **The service writes the step I/O first.** Linking a BR CRUD creates the matching step I/O row
  (or restores a retired one) in the same transaction, *before* inserting the CRUD, through the one
  writer `step_io.ensure_step_io` (§7.3 `link_data_entity`). The consultant never sees a refusal on the
  BR.
- **Retiring a step I/O row is refused while an active BR CRUD depends on it.** A soft delete
  changes `is_active`, which is part of the referenced key, so NO ACTION fires. The service
  pre-checks so the 409 *names* the BR and CRUD rather than surfacing a bare FK error, and the
  step I/O editor offers to remove the BR's CRUD too.
- **`is_active` is in the target key on purpose.** The PK alone includes retired rows, so a plain
  FK would be satisfied by a dead I/O row and would never block the retire. This is what makes
  D-24 enforceable rather than decorative.
- **Import order is fixed:** any import that writes both writes step I/O before BR CRUD.
- **The converse is not a rule.** A step I/O with no BR CRUD is legal: the step says data flows
  before the requirement says what is done to it. `process_completeness.crud_without_io` must
  always be 0 and stays as a proof.

#### 5.4.3 BR ↔ FR — **many-to-many, stored directly; the solution is an optional tag on the FR (D-52).**

**BR ↔ FR is a stored M:N link, `BR_FUNCTION_REQUIREMENT`, and it is the primary mapping (D-52).**
One FORM serves several BRs; one BR may need a FORM plus a BATCH plus an INTERFACE. Grain
`(br_id, fr_id)`, held by the **full** unique `uq_brfr_grain` beside the surrogate PK, so relinking
restores the old row and a pair keeps one id across unlink and relink (S1-7, S10b-1). The link
carries a `coverage_note` for the relationship-specific fact ("this FR covers only the validation
half of BR-0042"), edited in place (S5-3). That note is what makes the junction a real entity
rather than a bare link. Both composite FKs make a cross-project pairing unstorable, and the BR's
own guards limit it to a to-be process's BR.

**The solution is not in the link's grain.** An FR carries at most one solution tag,
`function_requirement.solution_id` (nullable, D-28), stored once on the FR, so its effort counts
toward exactly one solution however many BRs it serves. Putting the solution in the link would
count the same man-days once per BR.

- **The tag must answer at least one of the BRs the FR serves** (S10b-1). If the FR has live BR
  links, `solution_id` is NULL or the solution of a live `BR_SOLUTION` of at least one of them. An
  FR with no BR link may carry any live solution of its project, with a `no_br` warning. On a BR's
  FR row the picker offers only that BR's live solutions, and anything else is 422. The server
  never creates a `BR_SOLUTION` as a side effect: a BR_SOLUTION is a scope statement and is made
  on purpose. This rule reads other tables, so it is service-enforced (`function_requirement.set_solution`).
- **Drift is a warning, never a block or a cascade.** `consistency_check.fr_solution_outside_its_brs`
  lists live FRs whose tag answers none of their BRs; it is not freeze-blocking.
- **`v_br_function_requirement` reads the direct link only**:
  `BR_FUNCTION_REQUIREMENT ⋈ FUNCTION_REQUIREMENT ⟕ SOLUTION` (all live). A path
  `BR_SOLUTION → SOLUTION → FR` with no stored link is not a mapping.
- **D-34's `suggested_br_id` is retired** (S10b-1): the direct link stores exactly the fact it
  stood in for. An FR import row that names BR numbers creates links.

**What an FR without a link or a tag means.** Two independent conditions, each a warning (D-28):
**untraced** = no live BR link; **unassigned** = no solution tag. Their knock-ons:

1. `effort_summary` by solution and by phase has an **UNASSIGNED** bucket, plus an informational
   untraced line, so man-days are never dropped from a total. Effort is never summed by BR.
2. `priced_diff` sums FR-level changes directly from `baseline_function_requirement`,
   de-duplicated by source FR, and reports `untraced_days` and `unassigned_days`. Effort exposed
   walks BR → `br_function_requirement` → FR.
3. `analyse_cr_impact` accepts an FR as a seed, because a walk from BRs cannot reach an untraced FR.
4. `value_ranking` reports effort with no solution tag separately, since it has no benefit to divide by.
5. An FR with no solution tag has no inherited application (A-27). An interface FR still states its
   endpoints in `FR_INTERFACE`, which is a different fact from the delivering application.

**There is no FR ↔ node link** (SC-3). `FR_BFC_NODE` (an FR linked straight to a node) is retired and
never built: an FR reaches the chart only through the BRs it serves, and an FR for a whole area
("a dashboard for the whole of Order Management") is linked to the BRs of that area's processes.

**ISSUE ↔ BR is many-to-many.** One issue ("the source system has no customer credit field") can
block six requirements, and one requirement can have several open issues. A 1:N model would force
six copies of the issue, six resolutions to keep in sync and a resolution-rate report that lies.
An issue with zero BR links is valid (project-level), which is why `ISSUE.project_id` is the
mandatory anchor and `ISSUE_BR` is `0..N`.

#### 5.4.4 Snapshot storage — **typed shadow tables, not JSONB.**

The point of a baseline is the **diff**, so the snapshot is stored where the diff is cheapest.

- **Diffability.** With typed shadows, "what changed between v1.0 and v1.1" is one SQL statement
  per entity: `FULL OUTER JOIN … ON source_id`, comparing `content_hash`, giving added / removed /
  changed with the changed columns available by name. JSONB would need a hand-written recursive
  dict-diff in Python.
- **Query cost.** "Every baseline in which BR-0042 appeared, with its statement at each freeze" is
  an indexed lookup on `source_id`. In JSONB it is a scan of every baseline document.
- **Schema drift is caught, not hidden.** A live column added without its shadow column fails the
  parity test, which reads the database (law 2). JSONB would silently start carrying a new key,
  and the diff could not tell "field added" from "schema changed". For an artefact that may be
  quoted in a commercial dispute, a silently shifting record is the worst property.

The shadows are **generated** by `services/baseline_shadow.py`, never hand-written, and frozen as
literal DDL in their migrations. The freeze set, its component gates and the hashed columns are
data in `services/freeze_set.py` (§7.7).

Rules every shadow follows:

- **Structured content you do not control** (attachments, rich-text blocks) is snapshotted as a
  JSONB *column inside the typed shadow row*. Hybrid at the column level, never at the table
  level. There is **no redundant JSONB payload** beside the typed columns: two representations of
  one fact in one row diverge.
- **Code and label are both copied** for every `code_master` FK (`<p>_code`, `<p>_label`), and the
  `<p>_code_id` is copied unconstrained. **The hash reads the code; the label is display only**
  (R2-D3, §7.7), so a relabel in `code_master` never makes a frozen row read CHANGED.
- **`source_id` is an FK to the live row, `ON DELETE NO ACTION`.** The app role never hard-deletes,
  so this is safe. If any hard delete reaching a shadowed table is ever introduced, `source_id` must
  degrade to an unconstrained `bigint` pointer; no cascade is ever added that could shred a frozen
  baseline.
- **No intra-baseline FKs** (S8-1). Parent keys are copied as source ids and joined on
  `(baseline_id, source_id)`.
- **The hash is computed in SQL** at freeze (S8-1), and the hash spec is versioned: **a new entity
  joining the freeze set, or a change to an entity's hashed columns, bumps the spec**, and
  verification skips entities unknown at a baseline's spec (S10b-1).

#### 5.4.5 RACI — **one RACI per process, held by its BR on the to-be side and by the step on the as-is side (D-64, S10d-1), with one enforced Accountable.**

**Participation type is part of the link.** Without it, a role link says only "this role is
involved", which cannot answer "who signs off this process?". The alternatives are worse: a
boolean `is_primary` is RACI with one bit and no vocabulary, and a separate
`accountable_org_role_id` on the parent row would put accountability in two places that would
disagree.

**Where a process's roles live depends on its set** (D-64, S10d-1):

- **A to-be process's roles are its BR's**, in `BR_ORG_ROLE`.
- **An as-is process's roles are the step's**, in `BFC_NODE_ORG_ROLE`, because an as-is process has
  no BR (S7-2).
- One read function, `raci.process_roles(node)`, picks the right list. The process panel's RACI
  editor and its Accountable tile use only that function.
- **The database refuses a live step role on a to-be step**: `bfc_node_org_role` carries a
  generated `node_live_set` (`'AS_IS'` when active, else NULL) in an FK onto `bfc_node (bfc_node_id,
  project_id, bfc_set_code)`, `ON UPDATE NO ACTION`. Retired rows are NULL, so history is untouched.
  `raci.link` on a to-be step returns 409 ("A to-be process's roles are on its requirement").
- **Copying a chart carries roles across the change of home**: as-is step roles become the new
  to-be BR's roles, and a to-be BR's roles become the new as-is step's roles (S10d-1).

Storing the same roles on both the step and the BR would be one fact stored twice, kept in step by
every writer and frozen and diffed twice. Nothing reads a to-be step role, so it is not stored.

**Grain** `(br_id, org_role_id, raci_code_id)` and `(bfc_node_id, org_role_id, raci_code_id)`, each a
unique key beside a surrogate PK (S1-5). Participation type is in `code_master` category `RACI_TYPE`
and is **client-configurable**: RACI and RASCI are supported, and RAPID is a seeded mapping onto the
behaviours (Q7).

**Exactly one Accountable, keyed on behaviour (Q7, R2-D9).** Each link row carries `raci_behaviour`,
copied from the code and FK-verified (§5.4.13). A partial unique index `WHERE is_active AND
raci_behaviour = 'ACCOUNTABLE'` gives "at most one" per BR (`uq_bror_one_accountable`) and per as-is
step (`uq_bnor_one_accountable`), mirrored in `raci.SINGLE`. A client's letter set may change; the
rule does not. "At least one Accountable" is a completeness report, not a constraint: a child row
cannot be required at insert time, and a consultant mid-draft is not blocked. Several Responsible
roles are normal.

**RACI is not the swimlane.** The lane is the process's performer (D-46, §5.4.7), and no lane,
DFD, export or report reads RACI. RACI is the record of accountability.

**Org unit linkage is indirect.** BFC nodes and BRs link to `ORG_ROLE`, and the org unit comes via
`ORG_ROLE.org_unit_id`. A direct `org_unit_id` on the junctions would be a transitive dependency
that disagrees after a role moves between units.

#### 5.4.6 Number generation under concurrency

Two mechanisms, and the distinction matters:

- **Uniqueness is guaranteed by the constraint**, e.g. `UNIQUE (project_id, de_number)`, not by the
  generator. A generator bug produces an error, never a duplicate. This is not negotiable.
- **Allocation** uses `PROJECT_SEQUENCE`, one row per (project, series). `numbering.next_number`
  locks that one row in the same transaction as the insert, increments `last_value`, and formats
  `prefix || lpad(last_value, pad_width, '0')` → `DE-0001`. The lock serializes only concurrent
  creations in the same series of the same project, for microseconds.
- **All ten series are seeded by `create_project`** (R2-D14). A missing series raises; a series is
  never inserted lazily, because a lazy insert races on the first number.

Not `MAX(de_number) + 1` (races under read-committed, and breaks against soft-deleted rows), and not
a PostgreSQL `SEQUENCE` per project (DDL at runtime, unmanageable in Alembic).

**Numbers are permanent and may have gaps.** A rolled-back transaction consumes a number. Closing
gaps would mean renumbering, which breaks every document, email and minute that cited `DE-0007`.
This is an explicit, user-visible rule.

`PROJECT_SEQUENCE` carries `prefix` and `pad_width`, so a client who wants `ENT-001` instead of
`DE-0001` is a data change.

#### 5.4.7 The process rule (D-23) — **stored flag, parent-side guard, all generated.**

"The lowest node in its branch" is a fact about other rows, which a CHECK cannot see. The model
keeps it declarative by storing the fact (`bfc_node.is_process`) and making every dependent
assert it through a composite FK onto `bfc_node (bfc_node_id, project_id, is_process)`. Three
rules make that work:

1. **Guards are NULL on inactive rows** (`GENERATED … CASE WHEN is_active THEN … END`). A
   soft-deleted child or retired BR therefore never blocks a later promotion or demotion.
   Existence and tenancy stay on a separate always-on `(id, project_id)` FK.
2. **`ON UPDATE NO ACTION`, never CASCADE,** on every process guard. The refusal *is* the rule, and
   PostgreSQL will not create a cascading FK into a generated column, so the DDL cannot drift into
   one.
3. **Demotion needs every step fact retired first.** Every dependent is guarded, so the database
   refuses a demotion while any is live. The service refuses first with a 409 naming every blocker
   (`bfc._step_blockers`: the BR, step I/O, step roles, external flows, triggers, supporting
   systems, a performer, a process description), and never retires them itself (R2-P5, Q4). Step
   facts on a node that has children would describe the children's work a second time.

**CHECKs on `bfc_node` keep the flag honest:** `level_no >= 3` for a process (A-47);
`level_no < 5 OR is_process`, so an L5 cannot have children (A-54); `data_processing_desc` and the
performer only on a process. What stays outside the database: "every leaf is a process" (a leaf may
be mid-draft; reported as `leaf_not_process`) and "every to-be process has an active BR" (a
mandatory child; service-guaranteed and reported, §5.4.1a).

**Tables carrying the process guard:** `business_requirement`, `bfc_node_data_entity`,
`bfc_node_org_role`, `bfc_node_external_flow`, `bfc_node_trigger`, `application_bfc_node`, and the
parent guard on `bfc_node` itself. `bfc_node_flow` keeps its guards but is retired (D-38, §5.4.14).
**Not guarded, deliberately:** `risk.bfc_node_id` (a
risk may sit on a whole area) and `diagram_layout.scope_bfc_node_id` (a diagram is drawn *for* a
non-process node).

**The performer is a column set on the process row (D-46).** One process has one performer: an org
unit, an org role, an application or AI. It is an exclusive arc of typed FK columns on `bfc_node`
(`performer_kind`, `performer_org_unit_id`, `performer_org_role_id`, `performer_application_id`,
`performer_label` for AI), held by CHECKs, because it is a single-valued fact about the process. A
link table would need a UNIQUE to give 1:0..1 and would add another step-owned table to retire and
restore. Kinds are a CHECK list, not `code_master`, because they are fixed and drawn differently.
Zero performers is legal while drafting; it is reported (`no_performer`) and does not block the
freeze.

#### 5.4.8 FR type behaviour and the interface subtype (D-27) — **a behaviour column on the code, a verified copy on the FR, a guard on the subtype.**

One nullable column, `code_master.behaviour_code`, CHECK-listed and legal only on `FR_TYPE` rows.
The chain is:

```
FR_INTERFACE (fr_id, project_id, fr_type_behaviour = 'INTERFACE' when active)
   → FUNCTION_REQUIREMENT (fr_id, project_id, fr_type_behaviour)                     NO ACTION
FUNCTION_REQUIREMENT (fr_type_code_id, fr_type_category = 'FR_TYPE', fr_type_behaviour)
   → CODE_MASTER (code_id, category, behaviour_code)                                NO ACTION
```

What each rule then costs:
- **An FR_INTERFACE row under a non-interface FR** cannot be stored.
- **Retyping an FR from an interface type to another type** while its interface detail is active is
  refused by the database. `change_fr_type`'s 409 is the friendly message in front of it.
- **Changing a type's behaviour** is refused while any FR uses the type (Q6): a behaviour is
  immutable once referenced (§5.4.13).
- **A mistyped code FK** (an `fr_type_code_id` pointing at an ISSUE_SEVERITY or RACI_TYPE row) is
  impossible, because the FK carries the category.

The cost is two extra columns and three unique keys. Because the chain closes, the §4.7 check
"FR_INTERFACE rows under a non-interface type" is a proof that returns 0. Code branches on the
behaviour, never on a type code (law 5).

#### 5.4.9 External flows (D-24a) — **surrogate key because the DE is optional; licensed by step I/O when it is not.**

A nullable data entity in the grain means the natural key cannot be the PK. It is a surrogate plus
a `NULLS NOT DISTINCT` unique. When a DE is named, the row carries an FK to the matching live step
I/O row (`io_is_active`, as in §5.4.2). Without it, a DFD could show "Customer → Sales order →
Receive order" while the step says Receive order has no inputs: two truths, which D-24 prevents.
The cost is the same as for BR CRUD: the service writes the step I/O row first, in the same
transaction, through the same `ensure_step_io`, and an unlink names external-flow blockers (R2-D13).

#### 5.4.10 Diagram layout (D-29, D-30) — **typed object FKs, scope in the key, hard-deleted, never baselined.**

Typed object FKs follow the CR_IMPACT ruling. The hard-delete exception and the not-baselined rule
are justified in the entity note (§5.3). Layout is the only business-facing table whose history is
not kept, and that is deliberate. Positions are written for the `ERD` and `DFD` diagrams; old
`PROCESS_FLOW` rows stay as history and the service refuses new ones (S7-5, D-38).

#### 5.4.11 Program and access (D-32, D-40, D-62) — **visibility computed per request; programs group projects, never grant access.**

**Staff visibility is computed, not stored per project.** It is derived on every request in
`services/access.py` from `app_user.is_platform_admin`, `app_user.user_kind` (USER / VIEWER),
`project.is_restricted` and live `project_member` rows (D-40, OR-6). Storing a row per user per
project would be derived data that goes stale the moment a project is created.

- **`project_member` is a named exception list.** It matters only on a restricted project, and a
  membership on an unrestricted one has no effect, which lets an admin prepare the list before
  restricting. **New projects are created restricted** (D-62); an admin may clear the flag.
- **Effective level** = the lower of the user kind's cap (USER → EDIT, VIEWER → VIEW) and the
  member's `access_level`. Only platform admins reach ADMIN.
- **Each membership period is its own row.** A partial unique `(project_id, app_user_id) WHERE
  is_active` allows one live row; re-adding inserts a new row, and access returns only through the
  add route, never restore (R2-S5).
- **`user_access_grant` is retired history**: its live rows were copied into `project_member` and
  soft-revoked, and `vb_app` has SELECT only (S7-6). It was not repurposed, because a table whose
  rows change meaning in place is a table whose history lies.

**A program is a roll-up grouping.** `PROJECT.program_id` links a project to at most one program.
The composite FK `(program_id, client_id)` enforces *same client*, and the generated
`program_is_active` guard enforces *live program*. *Who may move a project* is not declarable: it is
platform-admin only (Q10), held by the service and the audit, and moving a project changes
roll-ups, not access. Program, project and membership retirement interlock through the generated
`…_is_active` guards, so Q4's "refuse while live dependents exist" is structural in the access
layer, where a leak would matter most. Roll-ups call each per-project report for the projects in
`visible_project_ids(user) ∩ program` (R2-S2); a restricted project the caller cannot see is omitted
silently, with no "hidden" count.

#### 5.4.12 WBS (D-33, D-41) — **imported read copy keyed by MS Project Unique ID; two VB-owned links; progress as dated rows; not baselined.**

One table with split ownership: MS Project owns the schedule columns, and VB owns `phase_id` /
`solution_id`. One table rather than a 1:0..1 link table, because the links' only reader is the same
dashboard row. The split is carried by a rule: the import never writes the links and never bumps
`row_version`, and link edits do both. If a second VB-owned attribute appears, split the table then.
Progress is recorded in VB as separate dated updates per line, never overwriting each other and
never overwritten by a re-import; imported actuals are kept beside them (D-41, OR-7).

#### 5.4.13 Behaviour is immutable once referenced (Q6, Q7, R2-D8, R2-D9) — **NO ACTION on the verified copy, category in the key.**

The composite FK that verifies a behaviour copy (`fr_type_behaviour`, `raci_behaviour`) is also the
immutability mechanism: with NO ACTION, a referenced key cannot change. That one declaration
replaces a trigger, a service guard and a consistency line, and covers RACI as well as FR types. It
is not CASCADE, for two reasons: a global code's cascade would rewrite every client's rows from one
admin action, and a used behaviour does not change (Q6).

#### 5.4.14 Flow-edge natural key (Q2, R2-D4) — **retired with `bfc_node_flow` (D-38).**

Explicit order arrows are retired. `bfc_node_flow` is SELECT-only history: its rows are
soft-retired, `vb_app` has no INSERT or UPDATE on it, and a step restore skips its rows. Its natural
key (from, to, normalised condition, partial, restore-before-insert) therefore governs no write.
Order between processes is derived from data, never stored: B follows A when B reads what A writes
(§5.3 BFC_NODE_FLOW, D-38).

#### 5.4.15 Active rows under inactive parents (R2-D2, Q4) — **one derived list, three uses, service-enforced.**

Soft delete is an UPDATE, so a plain FK is satisfied by a retired parent, and the database lets a
live child sit under a dead one. Only FKs whose *target key includes `is_active`* refuse it by
construction; those are listed in the right-hand column below as proofs. **The D-23 process guards
are not among them**: they key on `is_process`, which stays TRUE on a retired node.

The service holds **one list, `FK_LIVENESS`, derived from the SQLAlchemy FK metadata minus the
exclusions below** (`services/lifecycle.py`), and uses it three ways:
1. **Delete refused (Q4).** Retiring a row with live children in any listed FK returns 409 with the
   dependents named. The list is read in reverse.
2. **Restore refused (Q4).** Restoring a row whose listed parent is inactive returns 409. The list is
   read forward.
3. **Proof.** `consistency_check.active_under_inactive` returns (table, row, FK, parent) for each
   violation. It must return 0, and it is a freeze precondition like the rest of `consistency_check`.

The one exception to "refuse, never cascade" is a process step: retiring it retires the rows in
`step_retire.OWNED` with it, in one confirmed, undoable action (S3-SR). A new table that points at a
step blocks the step's retire until it is added there.

A CI test asserts that every FK in the metadata is either in `FK_LIVENESS` or excluded, so a new FK
cannot be silently unchecked. **Excluded, deliberately:** FKs to `APP_USER` (a deactivated
consultant's records stay valid); `project_id` (the check runs inside a live project); `program`
and `client`; `code_master` (a code is retired through `code_master.maintain`, never blocked by the
rows that use it, Slice 5 Q-8); `baseline_*` (immutable, pointing at history by design);
`audit_event`, `import_batch`, `import_row` (forensic); and `diagram_layout` (hard-deleted, and a
retired object keeps its position on purpose, §5.3). Generated guard columns (`is_active`,
`is_process`, `fr_type_behaviour`, `bfc_set_code`) are ignored when matching, so each parent link is
counted once.

In the table, "codes" marks `*_code_id` FKs: a retired code still referenced is the same kind of
defect, but it is governed by the `code_master` rule above, not by `FK_LIVENESS`.

| Table | FKs covered by `FK_LIVENESS` (child active ⇒ parent must be active) | Already DB-refused (proof only) |
|---|---|---|
| `org_unit` | `parent_org_unit_id`; codes | — |
| `org_role` | `org_unit_id` | — |
| `bfc_node` | `parent_bfc_node_id`, `performer_org_unit_id`, `performer_org_role_id`, `performer_application_id` | — *(parent guard checks process-ness and set, not liveness)* |
| `data_entity` | — | — |
| `data_field` | `data_entity_id`, `ref_data_entity_id`, `ref_data_field_id`; codes | — *(subsumes `orphan_fields`)* |
| `external_entity` | codes | — |
| `process_trigger` | — | — |
| `bfc_node_data_entity` | `bfc_node_id`, `data_entity_id` | — |
| `bfc_node_org_role` | `bfc_node_id`, `org_role_id`, `raci_code_id` | — |
| `bfc_node_external_flow` | `bfc_node_id`, `external_entity_id`, `data_entity_id` | the step-I/O licence (`io_is_active`) |
| `bfc_node_trigger` | `bfc_node_id`, `process_trigger_id` | — |
| `business_requirement` | `bfc_node_id`; codes | — |
| `br_data_entity` | `br_id`, `data_entity_id` | the step-I/O licence (`io_is_active`) |
| `br_org_role` | `br_id`, `org_role_id`, `raci_code_id` | — |
| `application` | codes | — |
| `solution` | codes | — |
| `br_solution` | `br_id`, `solution_id` | — |
| `function_requirement` | `solution_id`; codes | — |
| `br_function_requirement` | `br_id`, `fr_id` | — |
| `fr_interface` | `fr_id`, `source_application_id`, `target_application_id`; codes | — *(behaviour guard checks type, not liveness)* |
| `fr_interface_data_entity` | `data_entity_id` | `fr_id` → `fr_interface` (`interface_is_active`) |
| `application_solution` | `application_id`, `solution_id` | — |
| `application_bfc_node` | `application_id`, `bfc_node_id` | — |
| `effort_rate` | `fr_type_code_id`, `complexity_code_id` | — |
| `project_component` | codes | — |
| `issue` | `raised_by_stakeholder_id`; codes | — |
| `issue_br` | `issue_id`, `br_id` | — |
| `benefit` | `accountable_org_role_id`; codes | — |
| `benefit_solution` | `benefit_id`, `solution_id` | — |
| `phase` | codes | — |
| `solution_phase` | `solution_id`, `phase_id` | — |
| `solution_dependency` | `solution_id`, `depends_on_solution_id` | — |
| *live-only:* `wbs_item` | `parent_wbs_item_id`, `phase_id`, `solution_id` | — |
| *live-only:* `risk`, `change_request`, `cr_impact`, `control_rule`, `stakeholder` | every non-excluded FK (owner role, BFC node, solution, impacted objects, org unit); codes | — |
| *live-only:* `project`, `project_member` | — | `program_id` (`program_is_active`); `project_id` (`project_is_active`) |

`bfc_node_flow` is not listed: its rows can never be live again (§5.4.14), so its links never block.
`user_access_grant` is retired history and takes no writes (§5.4.11).

Owned rows: `br_solution`, `br_function_requirement` and `br_org_role` retire and restore with
their BR's step (S5-1, S10b-1); `application_bfc_node` (S6b-1), `bfc_node_trigger` and the step's
other facts retire and restore with the step.

#### 5.4.16 Rate card (R2-D7) — **audited between freezes, frozen at each freeze.**

The two mechanisms are complementary, not redundant. AUDIT_EVENT answers "who moved the rate in
March and why". `baseline_effort_rate` answers "what card was v1.0 signed on", which must be
answerable for five years (Q12) and is exactly what a vendor disputes. Justified in the EFFORT_RATE
note (§5.3).

#### 5.4.17 Logical FK groups — **a group number on the field, not a relationship table.**

`fk_group_no` is the smallest change that makes two relationships to one parent distinct. A
`DATA_ENTITY_RELATIONSHIP` table would be the normalized home **if** a relationship gains its own
attributes (a role name, a stated cardinality). None is asked for, and A-53 rules out typed
cardinality. So the number goes on the field, and the table is flagged as the extension (§5.3
DATA_FIELD). The request names the relationship (new or an existing group), and the service assigns
the number (S1-7).

#### 5.4.18 Import identity (R2-D1, R2-D10, Q1, S4-11) — **BR number resolves, hier_code cross-checks, names are unique among live process siblings.**

Three rules that only work together:

- **The BR number resolves a step** (R2-D1). It never changes and is 1:1 with its to-be process
  (D-2).
- **`hier_code` cross-checks** ("moved since export"). It is unique only among live nodes of one set
  (R2-D10, D-47), so it cannot resolve a step alone.
- **A new step, arriving with neither, must not duplicate a live sibling's name** (Q1), normalised
  (NFKC, case-folded, whitespace collapsed) — checked by the service (`assert_name_free`), with the partial unique
  index on `lower(btrim(node_name))` as the backstop.

**A row exported from VB carries a signed row token** (project, table, id, `row_version`). A token
row that no longer resolves to its live row is an error, never an INSERT: a rename or move by
spreadsheet is refused, and renames are done on screen (S4-11).

The model's part is `business_key` / `cross_check_key` on `IMPORT_ROW` and the two partial indexes on
`BFC_NODE`. The resolution order is the service's (§7.2b, §7.11).

---

### 5.5 Normalization notes — 1NF → 2NF → 3NF

**1NF.** The interesting violations in the source material are all list-valued:
- "Process nodes link to input and output data entities" is a repeating group. It is resolved into
  `BFC_NODE_DATA_ENTITY`, with direction in the key rather than `input_de_1 … input_de_n` columns.
- "Data entities have data fields" is resolved into `DATA_FIELD` rows rather than a field-list blob,
  which is what makes PK/FK flags and composite keys representable at all.
- Composite primary keys inside a modelled DE: a naive design puts `pk_field_1, pk_field_2,
  pk_field_3` on `DATA_ENTITY`. Resolved by `is_primary_key` + `pk_ordinal` on `DATA_FIELD`, which
  supports any arity with no schema change.
- Issue categorization is three single-valued attributes (severity, type, status), *not* one
  multi-valued "tags" column.

**2NF.** Only composite keys can hide partial dependencies:
- `BR_DATA_ENTITY(br_id, data_entity_id, crud_code)`: `usage_note` depends on all three (the note
  about *reading* Customer differs from the note about *updating* it). Clean. `de_name` here would
  depend on `data_entity_id` alone, a partial dependency, which is why snapshot label-copying is
  confined to the baseline tables.
- `BFC_NODE_ORG_ROLE(bfc_node_id, org_role_id, raci_code_id)`: no non-key attributes beyond the
  verified behaviour copy. The safest kind of junction.
- `BR_FUNCTION_REQUIREMENT(br_id, fr_id)`: `coverage_note` is about the pair. The solution tag
  depends on the FR alone, which is why it lives on `FUNCTION_REQUIREMENT`, not on the link (D-52).
- `PROJECT_SEQUENCE(project_id, sequence_code)`: `prefix` and `pad_width` depend on both parts (DE
  numbering differs from BR numbering within one project). If prefixes ever become project-wide,
  they move to `PROJECT`.
- `PROJECT_MEMBER`: surrogate PK, so no partial dependency is possible. Its natural grain, (project,
  user) with at most one live row, is carried by the partial unique index. `access_level` and
  `member_note` depend on the membership period.

**3NF — the four decisions that shaped the model:**

1. **Every client-configurable categorized value is a `code_master` FK.** Storing `severity_label`
   on `ISSUE` beside `severity_code` is the canonical transitive dependency
   (`issue_id → severity_code → severity_label`). The FK removes it, and renaming "High" to "Major"
   is one UPDATE instead of a data-fix script. Closed vocabularies that no client configures and
   that code branches on are CHECK-listed columns instead (`crud_code`, `performer_kind`,
   `trigger_kind`, `bfc_set_code`).

2. **Org unit is reached through role, never stored beside it.** `BR_ORG_ROLE` does not carry
   `org_unit_id`, because `br_id, org_role_id → org_unit_id` is transitive through `ORG_ROLE`. If it
   were stored, moving a role between divisions would leave every link asserting the old unit. The
   cost is a join on the RACI screen; the benefit is that the org chart can be restructured
   mid-project without a data repair.

3. **`hier_code` and `level_no` are deliberate, constraint-backed denormalizations.** Both are
   derivable from the parent chain: `level_no` is depth, and `hier_code` is the concatenation of
   ancestor `seq_no`s. They are stored because the chart is displayed sorted by `hier_code` on every
   screen, and a recursive CTE per render is absurd for a value that changes rarely. `level_no`
   carries only the depth CHECKs; the process guard is `is_process` (D-23). `level_no` cannot be a
   generated column, because the parent's level is not in the row, so it is a maintained column
   with a `CHECK`. The risk is drift on reparent or reorder. The mitigation is that recalculation
   lives in exactly one function, `renumber_subtree`, which recomputes every shifted sibling and all
   their descendants in one transaction, in two phases (S1-2), plus a consistency check.
   **Reparenting is the one operation in this app that must never be done with a partial update.**

   **`hier_code` may change on a reorder** (D-10). It is excluded from `content_hash`, and a position
   change reports as MOVED, not CHANGED. The stable identifier of a step is its BR number (to-be) and
   its id; `hier_code` is a display order and an import cross-check (§5.4.18).

4. **Baseline snapshot rows store resolved labels, breaking 3NF on purpose.**
   `BASELINE_ISSUE.severity_label` is a copy of `code_master.label`, exactly the transitive
   dependency removed from `ISSUE`. It is correct here because a snapshot records *what was true at
   freeze time*, and a live FK would let a later rename silently rewrite a frozen document. The
   normalization rule is about update anomalies, and a table that is never updated cannot have
   them. The code is copied beside the label and is what the hash reads (R2-D3). The same reasoning
   covers copying `hier_code` and `node_name` into `BASELINE_BFC_NODE`. **This is the one place where
   denormalization is the correct answer, and the DDL comments it as such** so a future reviewer does
   not "fix" it.

**Also worth recording:** `DATA_FIELD.length_val` / `precision_val` / `scale_val` are *not* a 3NF
violation despite being type-dependent in their applicability. They depend on the field, not on the
data type: `varchar(50)` and `varchar(200)` are different fields with the same type. The type only
determines whether the attribute is *meaningful*, which is a UI rule, not a functional dependency.

**Process, interface and diagram tables:**

- **1NF.** A step's I/O is one set of rows (`BFC_NODE_DATA_ENTITY`), written by one writer
  (`ensure_step_io`), and the DFD, the process panel and the BR all read it (D-24). External
  exchanges are rows (`BFC_NODE_EXTERNAL_FLOW`), not a "parties" text column on the node. Triggers
  are rows (`BFC_NODE_TRIGGER`), not a text list. An interface's carried entities are rows
  (`FR_INTERFACE_DATA_ENTITY`), not a comma list. The import stages a nested JSON document as **one
  row per object**. `payload` stays `jsonb` because staging is forensic (§5.3 AUDIT_EVENT reasoning),
  and nothing is reported or diffed from it.
- **2NF.** `FR_INTERFACE_DATA_ENTITY(fr_id, data_entity_id)` has only `note`, which is about the
  pair. `DIAGRAM_LAYOUT`'s x/y/size depend on the *whole* natural key: the same entity sits in
  different places on different diagrams and scopes, so scope is a key part, not an attribute.
  `BFC_NODE_EXTERNAL_FLOW.flow_label` depends on the whole grain.
- **3NF.**
  1. **`is_mandatory` replaces `is_nullable`.** Both would hold `is_mandatory = NOT is_nullable`, a
     non-key attribute determined by another.
  2. **`FR_INTERFACE` is a subtype, not six nullable FR columns.** Its attributes depend on `fr_id`
     only *given* behaviour INTERFACE, a conditional dependency that belongs in a 1:0..1 table.
  3. **`EXTERNAL_ENTITY` and `PROCESS_TRIGGER` are their own entities.** A party name or trigger name
     typed on each link row would make the name depend on a string rather than a key, and renaming
     "Bank" or "Month-end" would become a multi-row update.
  4. **The performer is on the process row** (D-46). It is single-valued per process, so it depends
     on `bfc_node_id` alone; a link table would add a UNIQUE to say the same thing.

**Program, access, WBS and FK groups:**

- **1NF.** A program's project list is **not** stored on the program (it would be a repeating
  group); it is `PROJECT.program_id`, read at request time. A user's visibility is not stored as a
  list either; it is computed from the user kind, the restriction flag and live memberships
  (§5.4.11). WBS lines are rows, not an imported blob, and MS Project's outline is resolved into
  `parent_wbs_item_id`. FK groups are a scalar per field, not a list of "relationships" on the
  entity.
- **2NF.** `WBS_ITEM` and `PROJECT_MEMBER` have single-column surrogate PKs, so there is nothing
  partial to depend on. `BASELINE_EFFORT_RATE`'s attributes depend on the whole `(baseline_id,
  source_id)`. A relationship role name would depend on `(data_entity_id, ref_data_entity_id,
  fk_group_no)` rather than the field, which is why it is flagged as a separate entity and not added
  as a DATA_FIELD column.
- **3NF.**
  1. **Program membership is on PROJECT and nowhere else.** Any copy of "a program's projects" would
     hold `program → projects` transitively and go stale on every move.
  2. **`PROGRAM.client_id` cannot drift from the project's.** `PROJECT` keeps its own `client_id`
     (it is the project's key fact), and the composite FK `(program_id, client_id)` makes the two
     agree. This is the same "copy the database checks" class as `project_id`.

**Deliberate, constraint-backed copies (same class as `project_id`, §5.6).** Each is a copy the
database checks, not a copy the application must remember to maintain:
- `BR_DATA_ENTITY.bfc_node_id`: transitive through `br_id`, verified by composite FK (D-24).
- `FUNCTION_REQUIREMENT.fr_type_behaviour` and the RACI links' `raci_behaviour`: transitive through
  the code FK, FK-verified, and immutable once referenced by NO ACTION (§5.4.13).
- `BFC_NODE.is_process`: a stored fact where a derivation ("has no children") would be both
  undeclarable and wrong during drafting (D-23).
- Generated guard and constant columns that exist only to be FK participants and cannot drift:
  `*_is_process`, `io_is_active`, `interface_is_active`, FR_INTERFACE's `fr_type_behaviour`,
  `*_category` (S1-4), `business_requirement.node_bfc_set` (S7-2),
  `bfc_node_org_role.node_live_set` (D-64), `program_is_active`, `project_is_active`.
- `baseline_effort_rate` labels: the point-4 snapshot rule.

---

### 5.6 What this model means for the application

**The project key is everywhere, and it is the tenant wall.** Every scope table carries
`project_id`, several redundantly (e.g. `BUSINESS_REQUIREMENT.project_id` is derivable through
`bfc_node_id`). The redundancy is made safe by **composite foreign keys**:
`(bfc_node_id, project_id) → BFC_NODE(bfc_node_id, project_id)` makes it impossible for a BR to
reference a node from another project. That turns a denormalization risk into a database-enforced
invariant and gives every query a single-column tenant filter. **Which projects a caller may see is
decided in one place**, `services/access.py` (`visible_project_ids`, `require_project`), from the
user's kind, the project's restriction flag and live memberships (§5.4.11). **Every route declares
exactly one guard**, a route without one fails at import, and criterion 49 re-proves it. A project
the caller cannot see is 404, never 403. Row-level security is deferred (§6.4), and criterion 49 is
the stated condition of that deferral.

**A program widens what is rolled up, never what is shared (D-32, D-40).** No scope table carries
`program_id`, so no FK path runs from one project's scope into another's, and the composite
`(id, project_id)` FKs keep a cross-project reference unstorable. A program dashboard is a set of
per-project report calls, each passing the same guard, never a query over a shared table (R2-S2).
The cost is that "the same Customer entity in two projects" is two DEs. A hand-off to another project is
drawn as an outside party on the DFD boundary, "Project: X", recorded by each project on its own side (SC-1).

**The BFC is one table, so the UI is one tree component.** Drilldown, breadcrumb, drag-to-reorder,
full-chart export and cross-level search all hit `bfc_node`. The to-be and as-is charts are two
sets in the same table (`bfc_set_code`, D-47), so the same tree shows either. The process rules
(description, I/O, roles, external parties, triggers, performer, supporting systems) live in
`CHECK`s and generated-guard FKs, and in an **`is_process` conditional** in the React form. There
is no level conditional anywhere (D-23; a grep for `level_no = 5` is a pre-merge check, law 4). Two
UI consequences: "Add child" is disabled on a process node (the database would refuse it anyway),
and demoting a process is refused with a 409 naming every live step fact until each is retired
(R2-P5, §5.4.7). `renumber_subtree` is the most dangerous function in the codebase, and
`mark_process` is the second. **Splitting a process into sub-steps keeps this rule** (SC-8): the demotion is
refused with the list of its facts until the consultant clears them; VB offers no guided split that retires them.

**The BR sits at the centre of the process.** It has inbound references from every direction:
issues, solutions, function requirements, RACI and the DE grid. It is read and edited inside its
process's panel in the business function chart (D-53, D-63), and the BR page remains as a deep link
from FRs, solutions and the diff. The entity × function × logic grid of `design-spec` §4 is not a
report to construct: it *is* `BUSINESS_REQUIREMENT ⋈ BR_DATA_ENTITY ⋈ DATA_ENTITY ⋈ BFC_NODE`, one
query, pivotable in SQL.

**The DFD is the process diagram, drawn from the rows (D-38).** `BFC_NODE_DATA_ENTITY` (what flows),
`BR_DATA_ENTITY` with CRUD (what is done, licensed by the flow, D-24), the performer (who does it,
the swimlane, D-46), `EXTERNAL_ENTITY` + `BFC_NODE_EXTERNAL_FLOW` (who outside the organisation sends
or receives it, D-24a) and `PROCESS_TRIGGER` + `BFC_NODE_TRIGGER` (what time or event starts it,
D-49) together form a process-level data flow diagram in relational form. Processes, data stores,
flows, external agents and triggers are all rows. **Order is derived, never stored**: B follows A
when B reads what A writes, a branch is two outputs feeding different processes, and a loop is a
later process writing what an earlier one reads. The DFD cannot disagree with the process panel or
the BR about a step's inputs, because there is only one place a step's inputs are stored. As-is and
to-be are two sets, each with its own DFD (D-47), sharing one data-entity catalogue so they compare.

**"Person or system" independence is preserved structurally.** `data_processing_desc` lives on the
BFC node and describes the processing requirement; the FR layer, which says *how a system does it*,
is a separate table reached through the M:N link (D-52). Nothing in the BFC or BR layer assumes
automation, and the function requirement component may be off for a project (D-37). A consultant
can model an entire operation without one FR, which is the "blueprints the whole operation, not
just the software" property, enforced by the fact that no FK points from BFC or BR *to* FR.

**The vendor boundary is a status column, not a table.** FRs are FTC-authored rows with
`fulfilment_status`. There is no vendor user, no vendor-owned write path and no vendor deliverable
entity. Client logins, when built, are read-only on their own project (D-43). If a vendor is ever
given access, the extension is a new access kind in `services/access.py`, as the client viewer is,
with a write path limited to `fulfilment_status`, not a new ownership model.

**Baselines make the app bi-modal, and the UI shows it.** Live rows are editable; baseline rows are
immutable. The header carries a working-set version chip ("Working · after v1.2", from the real
baseline list, D-51), and a frozen version reads as read-only. Every baseline screen is a
read-only, diff-capable component tree distinct from its live equivalent: roughly a second, simpler
set of screens, not a toggle on the existing ones.

**Soft delete plus baselines means nothing is ever truly gone, and that is the point.** A BR retired
after v1.0 was frozen still exists as `is_active = false` in the live table and as an immutable row
in `BASELINE_BUSINESS_REQUIREMENT`. The v1.0 → v1.1 diff reports it as *removed*, which is the
scope-change evidence FTC needs in a change-control conversation. **There is no hard-delete
endpoint** (law 1): the app role has no DELETE grant, apart from `diagram_layout` and the 90-day
`import_row` purge, and `purge_project` runs as the owner role (Q15). One cascading `DELETE` would
destroy the commercial value of every baseline that references the row.

**Two role vocabularies, never conflated.** `ORG_ROLE` is the client's ("Claims Supervisor,
Underwriting Division"), project-scoped, used in RACI and as a performer. The app's access is
`app_user.is_platform_admin` (D-9), `app_user.user_kind` (USER / VIEWER, D-40) and
`project_member.access_level`, ranked `VIEW` < `EDIT` < `ADMIN`; `project_role_code` survives only on
retired `user_access_grant` history. They share no table, no FK and no name fragment. In the code:
`org_role` vs `project_role_code` / access level, `/bfc-nodes/{id}/org-roles` and
`/business-requirements/{id}/org-roles` vs `/projects/{id}/access` and `/projects/{id}/members`. The
bare word `role` is banned (law 7); it is a PostgreSQL reserved word anyway, so the rule enforces
itself the first time someone forgets.

**What the application can rely on the database for, so the service re-checks only to give a
friendly message:**
- a BR CRUD always has the step I/O behind it (D-24), and so does an external flow that names a DE
  (D-24a);
- interface detail exists only on interface-type FRs (D-27);
- a process node never has active children (D-23);
- a BR exists only on a to-be process (S7-2), and a live step role only on an as-is process (D-64).

They stay in `consistency_check` as proofs that return 0; a non-zero result is a schema defect, not
a data defect.

**What the model cannot do (by design, worth knowing):** it cannot express a BR spanning two process
nodes; a process node that also has sub-steps (D-23); a BR on an as-is process (S7-2); a stored
order between processes (D-38: order is derived from data); a partial baseline covering only one
area; **a baseline of a whole program (D-32)**; **an entity shared by two projects of one program
(D-32)**; **schedule slip in a baseline diff (D-33: WBS is not baselined)**; a named individual in
RACI (only roles); a BR-level attachment; a requirement traced to a specific source document; a
curated ERD subject area other than a BFC branch; a named relationship role on the ERD (§5.4.17); or
a frozen diagram layout. The first two would change the shape of the model rather than extend it.

---

## 6. Physical design

### 6.1 Table inventory

**Every table is NET-NEW.** Value Bridge has no prior schema, so nothing is NEEDS-CHANGES and there is no
migration from an earlier system. Row numbers are stable identifiers; tables added after the first
inventory carry a letter suffix next to their group. **Built** means a migration exists today; the others
are designed and arrive with their wave (§12).

| # | Table | Group | Carries `project_id` | Baselined (freeze gate, §6.1 shadows) | Built |
|---|---|---|---|---|---|
| 1 | `client` | Tenancy | — | — | ✓ |
| 2 | `program` | Tenancy (D-32) | — (carries `client_id`) | ✗ — roll-up grouping only; no program freeze | ✓ |
| 3 | `project` | Tenancy | (is the key); `program_id` nullable; `data_model_depth` (D-39); `is_restricted` (OR-6, D-62); FTE basis `working_days_per_year`, `hours_per_working_day` (D-67, slice 13c) | — (`data_model_depth` and the FTE basis are copied onto the baseline header) | ✓ (FTE basis: 13c) |
| 3a | `project_component` | Tenancy (D-37) | ✓ | ✓ always — the live rows *are* the components on at the freeze | ✓ |
| 3b | `project_template_component` | Tenancy (D-37, OR-3) | — (global) | ✗ — a starting point, copied once at `create_project` | ✓ |
| 3c | `project_dfd_rule` | Tenancy — the DFD rule per chart (D-70) | ✓ | ✗ — a setting, not scope; the rule each chart passed is copied onto the baseline header | — (13b) |
| 4 | `code_master` | Shared | nullable (global / override) | ✗ — code **and** label are copied into each shadow instead | ✓ |
| 5 | `project_sequence` | Shared | ✓ (PK part) | ✗ | ✓ |
| 6 | `org_unit` | Client org | ✓ | ✓ always *(D-12)* | ✓ |
| 7 | `org_role` | Client org | ✓ | ✓ always *(D-12)* | ✓ |
| 8 | `bfc_node` | BFC (D-23, D-46, D-47; volume figures D-67) | ✓ | ✓ to-be rows always; as-is rows ⇐ `AS_IS`; the volume figures hashed from spec 3 | ✓ (volume: 13c) |
| 9 | `bfc_node_data_entity` | BFC (D-24) | ✓ | ✓ to-be steps always; as-is steps ⇐ `AS_IS` | ✓ |
| 10 | `bfc_node_org_role` | BFC — **as-is steps only** (D-64) | ✓ | ✓ as-is steps ⇐ `AS_IS` | ✓ |
| 11 | `bfc_node_flow` | BFC — **retired** (D-38) | ✓ | ✗ — never shadowed; read-only history, no new rows (§6.6) | ✓ (retired) |
| 12 | `external_entity` | BFC (D-24a) | ✓ | ✓ always | ✓ |
| 13 | `bfc_node_external_flow` | BFC (D-24a) | ✓ | ✓ to-be ⇐ `TO_BE_DFD`; as-is ⇐ `AS_IS` | ✓ |
| 13a | `process_trigger` | BFC (D-49) | ✓ | ✓ ⇐ `TO_BE_DFD` or `AS_IS` | ✓ |
| 13b | `bfc_node_trigger` | BFC (D-49) | ✓ | ✓ to-be ⇐ `TO_BE_DFD`; as-is ⇐ `AS_IS` | ✓ |
| 14 | `data_entity` | DE | ✓ | ✓ always *(D-3)* | ✓ |
| 15 | `data_field` | DE | ✓ | ✓ always *(D-3)* | ✓ |
| 16 | `business_requirement` | BR — **to-be processes only** (S7-2) | ✓ | ✓ always | ✓ |
| 17 | `br_data_entity` | BR | ✓ | ✓ always | ✓ |
| 18 | `br_org_role` | BR — the RACI of a to-be process (D-64) | ✓ | ✓ always | ✓ |
| 18a | `br_requirement_line` | BR — structured lines (D-59) | ✓ | ✓ always (joins at hash spec 4) | — (11) |
| 18b | `br_data_field` | BR — attribute usage (D-60b) | ✓ | ✓ always (joins at hash spec 4) | — (11) |
| 18c | `br_system_flow` | BR — system-to-system flows (D-61) | ✓ | ✓ ⇐ `APPLICATION` (joins at hash spec 4) | — (11) |
| 19 | `solution` | Solution (D-7) | ✓ | ✓ ⇐ `SOLUTION` | ✓ |
| 20 | `br_solution` | Solution (D-7) | ✓ | ✓ ⇐ `SOLUTION` | ✓ |
| 21 | `function_requirement` | FR | ✓ | ✓ ⇐ `FUNCTION_REQUIREMENT` *(D-3)* | ✓ |
| 21a | `br_function_requirement` | FR — the BR ↔ FR mapping (D-52) | ✓ | ✓ ⇐ `FUNCTION_REQUIREMENT` (joined at hash spec 2) | ✓ |
| 22 | `fr_interface` | FR (D-27) | ✓ | ✓ ⇐ `FUNCTION_REQUIREMENT` ∧ `APPLICATION` | ✓ |
| 23 | `fr_interface_data_entity` | FR (D-27) | ✓ | ✓ ⇐ `FUNCTION_REQUIREMENT` ∧ `APPLICATION` | ✓ |
| 24 | `fr_bfc_node` | FR — **retired, never built** (SC-3) | — | — | — (no table) |
| 25 | `application` | Landscape (D-8) | ✓ | ✓ ⇐ `APPLICATION` | ✓ |
| 26 | `application_solution` | Landscape (D-8) | ✓ | ✓ ⇐ `APPLICATION` ∧ `SOLUTION` | ✓ |
| 27 | `application_bfc_node` | Landscape (D-8) — supporting systems of as-is processes (S7 Q-23) | ✓ | ✓ ⇐ `APPLICATION`; as-is rows also ⇐ `AS_IS` | ✓ |
| 28 | `stakeholder` | Issue (D-4) | ✓ | ✗ — people are not scope | — |
| 29 | `effort_rate` | Size (D-13) | ✓ | ✓ ⇐ `EFFORT` (R2-D7) — the agreed rate card is a commercial term | ✓ |
| 30 | `benefit` | Benefit (D-14) | ✓ | ✓ when built ⇐ `BENEFIT` | — |
| 31 | `benefit_solution` | Benefit (D-14) | ✓ | ✓ when built ⇐ `BENEFIT` | — |
| 32 | `risk` | Risk (D-15) | ✓ | ✗ — risk is live, not scope | — |
| 33 | `change_request` | Change (D-16) | ✓ | ✗ — a CR challenges baselines, is not in one | — |
| 34 | `cr_impact` | Change (D-16) | ✓ | ✗ | — |
| 35 | `decision` | Governance (D-17) | ✓ | ✗ — append-only, evidential | — |
| 36 | `phase` | Phasing (D-18) | ✓ | ✓ when built (gate set when built) | — |
| 37 | `solution_phase` | Phasing (D-18) | ✓ | ✓ when built (gate set when built) | — |
| 38 | `solution_dependency` | Phasing (D-18) | ✓ | ✓ when built (gate set when built) | — |
| 39 | `wbs_item` | Schedule (D-33, D-41) | ✓ | ✗ — imported from MS Project; the schedule is not agreed scope | — |
| 40 | `control_rule` | Control (D-19) | ✓ | ✗ — governance config, not scope | — |
| 41 | `issue` | Issue | ✓ | ✓ when built ⇐ `ISSUE` | — |
| 42 | `issue_br` | Issue | ✓ | ✓ when built ⇐ `ISSUE` | — |
| 43 | `diagram_layout` | Presentation (D-30) | ✓ | ✗ — presentation, not scope; hard-deleted (documented deviation, A-52) | ✓ |
| 44 | `baseline` | Baseline | ✓ | n/a (the header) | ✓ |
| 45 | `import_batch` | Import (D-5, D-25) | ✓ | ✗ — the import trail; header kept after the row purge | ✓ |
| 46 | `import_row` | Import (D-5, D-25) | via `import_batch` | ✗ — purged after 90 days (Q14) | ✓ |
| 47 | `app_user` | Identity | — (`user_kind`, D-40) | — | ✓ |
| 48 | `user_access_grant` | Identity — **retired** (D-40) | nullable — XOR `program_id` | — (SELECT-only history, §6.6) | ✓ (retired) |
| 48a | `project_member` | Identity (D-40, OR-6, D-62) | ✓ | ✗ — access is not scope | ✓ |
| 49 | `audit_event` | Identity | nullable | — | ✓ |
| 50– | `baseline_*` shadow tables (**25** today) | Baseline | copied | n/a (immutable) | ✓ |

*(`app_role` does not exist — D-9; access is `is_platform_admin` + `user_kind` + `project_member`, §7.8.)*

**The shadow tables (D-3, D-12, D-24a, D-27, D-37, D-49, D-52, R2-D7, S8-1).** One per baselined live table,
listed in `models/baseline.SHADOWED` and `services/freeze_set.FREEZE_SET` (a module assertion keeps the two equal),
**in freeze (FK) order**: `org_unit`, `org_role`, `bfc_node`, `data_entity`, `data_field`, `external_entity`,
`process_trigger`, `bfc_node_data_entity`, `bfc_node_org_role`, `bfc_node_external_flow`, `bfc_node_trigger`,
`business_requirement`, `br_data_entity`, `br_org_role`, `application`, `solution`, `br_solution`,
`function_requirement`, `br_function_requirement`, `fr_interface`, `fr_interface_data_entity`,
`application_solution`, `application_bfc_node`, `effort_rate`, `project_component`. The designed tables
`br_requirement_line`, `br_data_field` and `br_system_flow` (slice 11, hash spec 4), and `issue`, `issue_br`,
`benefit`, `benefit_solution`, `phase`, `solution_phase` and `solution_dependency` join when they are built; **a new entity joining the set bumps `CURRENT_HASH_SPEC` and registers
its hashed columns under the new version** (S10b-1, slice10b Q-14), so older baselines still verify.

**Every shadow is generated, never hand-written** (`services/baseline_shadow.py`, VB law 2):
- **Copied columns** = the live columns minus the §5.1 audit columns, the live PK, GENERATED columns
  (guard columns such as `node_is_process`, `node_bfc_set`, `*_category` and `br_data_entity.direction`, which
  readers recompute from `crud_code`) and `SHADOW_EXCLUDED` (empty today). Every copied column is nullable
  (A-7: a snapshot records what was).
- **Code pairs** (S8-1 Q-1): for each `<p>_code_id` with a GENERATED `<p>_category` sibling, the shadow adds
  `<p>_code` and `<p>_label` (the code is hashed, the label is display only, R2-D3) and keeps the
  unconstrained `<p>_code_id`. `raci_behaviour` and `fr_type_behaviour` are stored columns and are copied.
- **Keys:** PK `baseline_<t>_id`; `baseline_id` FK; `source_id` = the live PK, FK `ON DELETE NO ACTION`;
  `uq_baseline_<t>_source (baseline_id, source_id)`; `ix_baseline_<t>_source (source_id)`; `content_hash
  char(64) NOT NULL` (§7.7).
- **No intra-baseline FKs** (S8-1 Q-2). Copied FK columns hold source ids, so a join inside one baseline is
  `child.<fk> = parent.source_id AND child.baseline_id = parent.baseline_id`.
- Migration 0048 holds the shadows as literal DDL. A migration that adds a column to a shadowed live table adds
  the shadow column **in the same migration**, and a shadow column's type is never ALTERed (DR8-D1, §6.5).

At A-35's bound (2,000 processes, synchronous freeze) a freeze writes roughly **35,000 rows** for a to-be-only
project and **50,000** with the as-is set (slice8 §10).

**Why `effort_rate` is in the set (R2-D7).** `baseline_function_requirement.effort_days` stores the
**computed** days at freeze time, so a later renegotiation of the rate card cannot reprice a signed baseline;
that is what makes `priced_diff` reproducible. The **card itself** is also a term of the agreement: without
`baseline_effort_rate` nobody can show which rates v1.0 was priced at, or that a CR priced later used a card
the client never signed. Between freezes, rate changes are audited (§5.3 EFFORT_RATE). With `EFFORT` off the
card freezes no rows.

**Why `org_unit` and `org_role` are in the set (D-12, D4).** `br_org_role`, `bfc_node_org_role` and the
performer columns on `bfc_node` carry only ids that point at live, editable rows. Without the org chart frozen
beside them, a baseline that said "org_role 44 is Accountable for BR-0042" would, after the client renames and
re-parents role 44, render accountability — and, because §5.4.5 routes org unit through the role, a division —
that was never agreed.

**Deliberately not baselined:** `stakeholder` (a person is not a scope item, and freezing personal data into an
immutable table is a data-protection problem); `import_batch` / `import_row` (staging); `diagram_layout`
(D-30 — a box's position is presentation; a re-opened baseline renders with today's positions, A-52);
`wbs_item` (D-33 — the schedule belongs to MS Project); `program` (no program freeze, D-32);
`project_member`, `user_access_grant`, `app_user` (access is not scope); `project_template_component`;
`bfc_node_flow` (retired, D-38); `audit_event`, `project_sequence`, `code_master`, `project`, `client`;
`risk`, `change_request`, `cr_impact`, `decision`, `control_rule`.

**Retention (Q12):** a baseline is recoverable for at least five years because no application path and no
application grant can delete one (§6.6). The model needs no retention column. Long-term archive beyond Azure's
point-in-time restore window belongs to the deployment design (D-35, §15.3). **Contract wins (Q15):** where a
client contract requires deletion at engagement end, `purge_project` (§15.3) removes the project's live and
snapshot rows and destroys its archive key. It is the one hard-delete path in VB, platform-admin only, with a
recorded reason, and it runs under the owner role — `vb_app` still holds no DELETE (§6.6). Because the reject
triggers fire for the owner too, the purge disables them inside its own transaction, deletes shadows before
live rows (`source_id` is NO ACTION) and the header last; live members, components and triggers go before
their project (slice8 §11 item 8, slice7 §9.12).

Full column lists (Column · Type · Constraints · Description) are in §5.2's attribute blocks, §5.3's entity
notes and the slice schemas; the DDL lives in the Alembic migrations (§6.5).

### 6.2 Constraints that carry the design

These are not implementation detail. Each one is a business rule the database enforces, and losing any of
them silently breaks a promise this spec makes. Constraint names are the ones in the migrations.

**Conventions on every table:** a surrogate identity PK (link rows included, S1-5) with the design's natural
key as a `UNIQUE NOT NULL`; composite `(id, project_id)` FKs; every FK `NO ACTION`; **every code FK is
category-verified** — a generated constant `<p>_category` column and a composite FK to `code_master (code_id,
category)` (`uq_code_category_target`, S1-4); **user-typed names and codes are unique among live rows,
normalised `lower(btrim(…))`**, while minted numbers keep full UKs (S1-6); **link grains use a full UK** so
re-linking restores the old row and keeps its `source_id` (S1-7).

| Constraint | Table | Enforces |
|---|---|---|
| `ck_bfc_level CHECK (level_no BETWEEN 1 AND 5)` | `bfc_node` | the five-level contract |
| `ck_bfc_root CHECK ((level_no = 1) = (parent_bfc_node_id IS NULL))` | `bfc_node` | exactly one root layer per set |
| `ck_bfc_desc_process_only CHECK (is_process OR data_processing_desc IS NULL)`; `ck_bfc_process_level CHECK (NOT is_process OR level_no >= 3)`; `ck_bfc_l5_is_process CHECK (level_no < 5 OR is_process)` | `bfc_node` | D-23 — only a process carries the processing description; a process sits at L3–L5 (A-47); an L5 is always a process (A-54) |
| `ck_bfc_set CHECK (bfc_set_code IN ('TO_BE','AS_IS'))`; `uq_bfc_node_set (bfc_node_id, project_id, bfc_set_code)`; `fk_bfc_node_parent_set (parent_bfc_node_id, project_id, bfc_set_code) → bfc_node` ON UPDATE NO ACTION | `bfc_node` | **D-47 — two charts per project; a child is always in its parent's set.** `bfc_set_code` is immutable (service, and the FKs refuse a change while children or a BR exist) |
| partial `uq_bfc_hier_code_live (project_id, bfc_set_code, hier_code) WHERE is_active`; partial `uq_bfc_process_name (parent_bfc_node_id, lower(btrim(node_name))) WHERE is_active AND is_process` | `bfc_node` | **R2-D10** — no two live nodes of one chart share a code, and a retired node does not hold its code forever; `hier_code` is therefore not an identifier, and imports resolve by BR number (R2-D1). **Q1** — no two live process steps under one parent share a name (the service's check is wider, §7.2) |
| partial `uq_bfc_sibling_seq (project_id, bfc_set_code, parent_bfc_node_id, seq_no) NULLS NOT DISTINCT WHERE is_active`; `ck_bfc_seq CHECK (seq_no <> 0 AND seq_no BETWEEN -99 AND 99)` | `bfc_node` | sibling ordering, the roots of each set included (S1-1); a retired sibling frees its slot; at most 99 siblings, negatives only during a two-phase reorder (S1-3) |
| composite FK `(bfc_node_id, project_id)` | `business_requirement` and every junction | **structurally impossible to reference another project's row** |
| `node_is_process GENERATED (TRUE if active, else NULL)` + FK `(bfc_node_id, project_id, node_is_process) → bfc_node (uq_bfc_node_process_target)` ON UPDATE NO ACTION | `business_requirement`, `bfc_node_data_entity`, `bfc_node_org_role`, `bfc_node_external_flow`, `bfc_node_trigger`, `application_bfc_node` | D-23 — process-only, in the DB. A retired row's NULL guard neither blocks demotion nor pins the node |
| `parent_is_process GENERATED (FALSE if active, else NULL)` + `fk_bfc_node_parent_not_process (parent_bfc_node_id, project_id, parent_is_process) → bfc_node` **ON UPDATE NO ACTION**; plain `fk_bfc_node_parent (parent_bfc_node_id, project_id)` for existence | `bfc_node` | **D-23 — a process has no active children.** Adding a child to a process, or promoting a node with active children, is refused by the DB |
| `uq_bfc_node_process_target UNIQUE (bfc_node_id, project_id, is_process)` | `bfc_node` | the FK target for every process guard |
| `node_bfc_set GENERATED ('TO_BE')` + `fk_br_node_to_be (bfc_node_id, project_id, node_bfc_set) → bfc_node (uq_bfc_node_set)` ON UPDATE NO ACTION | `business_requirement` | **S7-2 — a BR exists only on a to-be process**; as-is processes carry no BR, CRUD or solutions |
| **partial `uq_br_one_per_node (bfc_node_id) WHERE is_active`** | `business_requirement` | **D-2 / S7-2 — exactly one live BR per to-be process.** Partial, so a soft-deleted BR never permanently occupies the key and leaves the node requirement-less (P5). Dropping this index is the entire cost of reversing D-2 (§5.4.1a) |
| `uq_br_node_carrier UNIQUE (br_id, project_id, bfc_node_id)` | `business_requirement` | the D-24 carrier of the BR's node; also makes `bfc_node_id` effectively immutable once CRUD exists (immutability is service-enforced, S1-7) |
| `ck_bfc_performer_kind CHECK (performer_kind IS NULL OR performer_kind IN ('ORG_UNIT','ORG_ROLE','APPLICATION','AI'))`; `ck_bfc_performer_arc` (exactly the one id column of the kind, none for `AI` or NULL); `ck_bfc_performer_label CHECK (performer_label IS NULL OR (performer_kind = 'AI' AND btrim(performer_label) <> ''))`; `ck_bfc_performer_ai_label CHECK (performer_kind IS DISTINCT FROM 'AI' OR performer_label IS NOT NULL)`; `ck_bfc_performer_process CHECK (performer_kind IS NULL OR is_process)`; composite FKs `fk_bfc_perf_unit` / `fk_bfc_perf_role` / `fk_bfc_perf_app` | `bfc_node` | **D-46 — one performer per process** (department, position, IT system or a named AI), in-project, only on a process. Zero is legal (the "unassigned" lane). A process with a performer cannot be demoted |
| `ck_bfc_volume_period` (CHECK-listed `DAY`…`YEAR`); `ck_bfc_volume_nonneg`; `ck_bfc_volume_run_pair ((runs_per_period IS NULL) = (volume_period_code IS NULL))`; `ck_bfc_volume_unit` (a unit needs a count); `ck_bfc_volume_process` (a non-process row holds no volume); `fk_bfc_txn_unit (transaction_unit_code_id, transaction_unit_category) → code_master` | `bfc_node` | **D-67** — volume belongs to a process, comes in meaningful pairs, and is never negative; caps and decimals are service-checked (422), hours and FTE have no column (law 6) |
| `ck_ptrg_kind CHECK (trigger_kind IN ('TIME','EVENT'))`; `ck_ptrg_schedule_time_only CHECK (schedule_note IS NULL OR trigger_kind = 'TIME')`; `ck_ptrg_name_not_blank`; partial `uq_ptrg_name_live (project_id, lower(btrim(trigger_name))) WHERE is_active`; `uq_ptrg_project (process_trigger_id, project_id)` | `process_trigger` | **D-49** — a named, project-wide time or event trigger; no number series |
| `uq_bntr_grain UNIQUE (bfc_node_id, process_trigger_id)` (full); process guard; `fk_bntr_trigger (process_trigger_id, project_id) → process_trigger` | `bfc_node_trigger` | D-49 — a trigger starts a process step of the same project; re-linking restores |
| `uq_bnde_grain UNIQUE (bfc_node_id, data_entity_id, direction)` (full); `uq_bnde_live_target UNIQUE (bfc_node_id, data_entity_id, direction, is_active)`; `ck_bnde_direction CHECK (direction IN ('I','O'))` | `bfc_node_data_entity` | D-24 — one step I/O row per (step × entity × direction); the live target is the licence FK target, with `is_active` in it so a soft delete is a key change |
| `crud_code CHECK (… IN ('C','R','U','D'))` + GENERATED `direction` (`'I'` for R, else `'O'`); `bfc_node_id` copied + `fk_brde_br (br_id, project_id, bfc_node_id) → business_requirement (uq_br_node_carrier)`; `io_is_active` GENERATED + `fk_brde_io_licence (bfc_node_id, data_entity_id, direction, io_is_active) → bfc_node_data_entity (uq_bnde_live_target)`; `uq_brde_grain (br_id, data_entity_id, crud_code)` | `br_data_entity` | **D-24 — R needs a step input, C/U/D a step output**, by construction; no `(R, OUTPUT)` contradiction (§5.4.2). Retiring an I/O row a BR CRUD depends on is refused |
| `ck_brdf_crud CHECK (crud_code IN ('C','R','U'))`; GENERATED `brde_is_active` + `fk_brdf_licence (br_id, data_entity_id, crud_code, brde_is_active) → br_data_entity (uq_brde_live_licence)`; `(data_field_id, data_entity_id) → data_field (uq_data_field_entity)`; UK `uq_brdf_grain (br_id, data_field_id, crud_code)` full | `br_data_field` *(slice 11)* | **D-60b** — an attribute tick never outlives the entity-level CRUD that licenses it, and the attribute belongs to that entity |
| UK `uq_brl_line_no (br_id, line_no)` full; partial `uq_brl_seq_live (br_id, seq_no) WHERE is_active`; `CHECK (line_no >= 1)`; non-blank `line_text`; category-in-key FKs to `BR_LINE_KIND` and `BR_PRIORITY` | `br_requirement_line` *(slice 11)* | **D-59** — a line number is never reused; display order is unique among live lines |
| UK `uq_brsf_grain (br_id, data_entity_id, source_application_id, target_application_id)` full; `CHECK (source_application_id <> target_application_id)`; composite FKs to the BR, the entity and both applications | `br_system_flow` *(slice 11)* | **D-61** — a flow names two different systems from the master list |
| `ext_number` minted, `uq_ext_number UNIQUE (project_id, ext_number)`; partial `uq_ext_name_live (project_id, lower(btrim(ext_name))) WHERE is_active` | `external_entity` | D-24a — business key never reused; no two live parties with one name |
| `uq_bnef_grain UNIQUE NULLS NOT DISTINCT (bfc_node_id, external_entity_id, direction, data_entity_id)`; `ck_bnef_direction CHECK (direction IN ('I','O'))`; process guard; when a DE is named, `fk_bnef_io_licence (bfc_node_id, data_entity_id, direction, io_is_active) → bfc_node_data_entity (uq_bnde_live_target)` | `bfc_node_external_flow` | D-24a, R2-D13 — one exchange per (step × party × direction × DE), only on process steps, never contradicting the step's own I/O. A flow with no DE carries a `flow_label` |
| `node_live_set GENERATED ('AS_IS' if active, else NULL)` + FK `(bfc_node_id, project_id, node_live_set) → bfc_node (uq_bfc_node_set)` ON UPDATE NO ACTION | `bfc_node_org_role` | **D-64, S10d-1 — one RACI per process:** a to-be process's roles live on its BR (`br_org_role`); a live step role exists only on an as-is step. Retired rows are unchecked history |
| `raci_category GENERATED ('RACI_TYPE')`, `raci_behaviour NOT NULL` + FK `(raci_code_id, raci_category, raci_behaviour) → code_master (uq_code_behaviour_target)` NO ACTION; full grain `(owner, org_role_id, raci_code_id)`; partial `uq_bror_one_accountable (br_id) WHERE is_active AND raci_behaviour = 'ACCOUNTABLE'` and `uq_bnor_one_accountable (bfc_node_id) WHERE is_active AND raci_behaviour = 'ACCOUNTABLE'` | `br_org_role`, `bfc_node_org_role` | **Q7, R2-D9** — at most one Accountable per process, keyed on behaviour, not the letter; the RACI code is provably a RACI_TYPE; a used behaviour is immutable. Several Responsible roles are normal RACI (D-46: the lane is the performer, not a RACI role) |
| `ck_code_behaviour_present CHECK ((category IN ('FR_TYPE','RACI_TYPE')) = (behaviour_code IS NOT NULL))`; `ck_code_fr_behaviour` (FORM / INTERFACE / REPORT / BATCH / OTHER); `ck_code_raci_behaviour` (RESPONSIBLE / ACCOUNTABLE / CONSULTED / INFORMED / SUPPORT / OTHER); `uq_code_behaviour_target (code_id, category, behaviour_code)`; `uq_code_category_target (code_id, category)`; `uq_code_master_scope (project_id, category, code) NULLS NOT DISTINCT` | `code_master` | D-27, **Q7** — every FR type and RACI code has a behaviour and nothing else has one; the targets carry the category because the vocabularies share `OTHER`; one code per category per tier (global or project) |
| `fr_type_behaviour NOT NULL`; `fr_type_category GENERATED ('FR_TYPE')`; `fk_fr_type_code (fr_type_code_id, fr_type_category, fr_type_behaviour) → code_master (uq_code_behaviour_target)` **ON UPDATE NO ACTION**; `uq_fr_behaviour_target (fr_id, project_id, fr_type_behaviour)` | `function_requirement` | D-27 — the FR's behaviour is its type's; the code is provably an FR_TYPE. **Q6 / R2-D8 — a type's behaviour is immutable once any FR references it** |
| `fr_type_behaviour GENERATED ('INTERFACE' if active, else NULL)` + `fk_fri_fr_behaviour (fr_id, project_id, fr_type_behaviour) → function_requirement (uq_fr_behaviour_target)`; `ck_fri_endpoints_distinct CHECK (source_application_id <> target_application_id)`; both applications `NOT NULL` with `(id, project_id)` FKs | `fr_interface` | **D-27 — interface detail only on an interface-behaviour FR, declaratively**; endpoints distinct and in-project |
| `interface_is_active GENERATED` + `fk_fide_interface_live (fr_id, project_id, interface_is_active) → fr_interface (uq_fri_live_target)`; `uq_fide_grain (fr_id, data_entity_id)` | `fr_interface_data_entity` | no live carried-entity rows under retired interface detail |
| `solution_id` **NULLABLE**; `fk_fr_solution (solution_id, project_id)` when present | `function_requirement` | **D-28 / D-52 — the optional solution tag**: the one solution an FR's effort counts toward. "The tag answers at least one of the FR's linked BRs" is service-enforced (it reads two other tables); drift afterwards is the warning `fr_solution_outside_its_brs` |
| `uq_brfr_grain UNIQUE (br_id, fr_id)` (full); `fk_brfr_br (br_id, project_id) → business_requirement`; `fk_brfr_fr (fr_id, project_id) → function_requirement` | `br_function_requirement` | **D-52 — BR ↔ FR is a stored many-to-many link and the primary mapping**; cross-project pairing is impossible; one id per pair forever (relink restores). The BR's own guards make it reach only a to-be process |
| `ck_fr_effort_with_complexity CHECK ((complexity_code_id IS NULL) = (effort_days IS NULL))`; `ck_fr_effort_nonneg`; `effort_days` derived at rating, never accepted from a request (law 6) | `function_requirement` | D-13 — an FR is rated or not, never half; a rate-card change never silently reprices a rated FR (S6c-2) |
| `uq_effort_rate_cell UNIQUE (project_id, fr_type_code_id, complexity_code_id)`; `ck_effort_rate_days_positive CHECK (standard_days > 0 AND standard_days <> 'NaN')`; `ck_effort_rate_rationale CHECK (row_version = 1 OR change_rationale IS NOT NULL)` and not blank; identity PK `effort_rate_id` | `effort_rate` | **R2-D7** — one rate per cell; a changed rate states why; a stable `source_id` survives the override re-pointing (§7.5). *Service-enforced:* a cell above 60 man-days needs confirmation and is flagged (S6c-7) |
| `UNIQUE (project_id, sequence_code)` (the PK) + `ck_sequence_code CHECK (sequence_code IN ('DE','BR','FR','ISSUE','SOL','BEN','RSK','CR','DEC','EXT'))` | `project_sequence` | **R2-D14** — the ten series; all ten are seeded by `create_project` and proved by `consistency_check.project_sequence_missing` |
| `UNIQUE (project_id, de_number)` / `br_number` / `fr_number` / `solution_number` / `ext_number` / `issue_number` | respective | **uniqueness comes from the constraint, never from the generator** |
| `uq_solution_number`; partial `uq_solution_name_live (project_id, lower(btrim(solution_name))) WHERE is_active`; `ck_sol_name_not_blank` | `solution` | business key quoted in client documents (S5-5) |
| `uq_application_code UNIQUE (project_id, application_code)`; `ck_app_code_chars CHECK (application_code ~ '^[A-Z0-9._-]+$')`; partial `uq_application_name_live` | `application` | S6b-2, S6b-6 — codes upper-case and never duplicated; editable until a baseline freezes them (service), live names unique |
| **service-enforced** (R2-D11): allocating an `AS_IS` application to a solution → 422; changing an application's lifecycle to `AS_IS` while it delivers live solutions → 409 naming them; `APP_LIFECYCLE` seeded `is_system` | `application_solution` | an as-is-only system cannot be allocated as a to-be answer. A CHECK sees one row of one table; the lifecycle is a code FK on `application`, and the rule must hold on both write paths |
| `uq_appnode_grain UNIQUE (application_id, bfc_node_id)` (full); process guard; **service:** new rows only on as-is processes (422 on a to-be process) | `application_bfc_node` | S7 Q-23 — supporting systems are as-is facts; a to-be process's systems come from BR → Solution → Application (D-22, D-8) |
| `ck_df_fk_group CHECK ((fk_group_no IS NOT NULL) = is_foreign_key)`; `ck_df_fk_group_pos CHECK (fk_group_no IS NULL OR fk_group_no >= 1)`; partial `uq_df_fk_group_field (data_entity_id, ref_data_entity_id, fk_group_no, ref_data_field_id) WHERE is_active AND ref_data_field_id IS NOT NULL` | `data_field` | §5.4.17 — two relationships to one parent are distinct; a composite FK is one group; a parent field appears once per relationship. The service assigns the number (S1-7) |
| `data_type_code_id` **NULLABLE**; `ck_df_size_needs_type CHECK (data_type_code_id IS NOT NULL OR num_nulls(length_val, precision_val, scale_val) = 3)`; `ck_df_sizes`; `ck_df_pk_not_optional CHECK (NOT is_primary_key OR is_mandatory IS DISTINCT FROM FALSE)`; `is_mandatory` nullable (= unknown) | `data_field` | D-26 — logical fields; no length without a type; a key field cannot be optional |
| `ck_df_pk_ordinal CHECK (is_primary_key = (pk_ordinal IS NOT NULL))`; `ck_df_pk_ordinal_pos`; partial `uq_df_pk_ordinal (data_entity_id, pk_ordinal) WHERE is_primary_key AND is_active` | `data_field` | composite PKs are ordered, one field per position |
| `ck_df_fk_target CHECK (is_foreign_key = (ref_data_entity_id IS NOT NULL))`; `ck_df_ref_field CHECK (ref_data_field_id IS NULL OR is_foreign_key)` | `data_field` | an FK field names its target, and only an FK field names one |
| partial `uq_df_name_live (data_entity_id, lower(btrim(field_name))) WHERE is_active`; partial `uq_df_seq_live (data_entity_id, seq_no) WHERE is_active`; `ck_df_seq CHECK (seq_no <> 0 AND seq_no BETWEEN -999 AND 999)` | `data_field` | field names unique within an entity among live fields (S1-6); ordered, two-phase reorder (S1-2, S1-3) |
| `project_id` + composite FKs `fk_df_entity`, `fk_df_ref_entity`, `fk_df_ref_field` | `data_field` | D9 — the DE layer carries the same cross-project backstop as every other layer |
| partial `uq_de_name_live (project_id, lower(btrim(de_name))) WHERE is_active` | `data_entity` | S1-6 — no two live entities share a name |
| `uq_project_component UNIQUE (project_id, component_code_id)` (full); `fk_pc_component (component_code_id, component_category) → code_master` | `project_component` | **D-37 — a live row means the component is on; switching back on restores the same row.** The vocabulary `PROJECT_COMPONENT` is `is_system`, global only |
| `uq_ptc_grain UNIQUE (template_code_id, component_code_id)`; category FKs to `PROJECT_TEMPLATE` and `PROJECT_COMPONENT` | `project_template_component` | OR-3 — templates are data, copied once at `create_project` |
| `ck_project_depth CHECK (data_model_depth IN ('KEYS_ONLY','FULL'))` | `project` | D-39 — how much of a data entity a project expects |
| `ck_project_fte_days CHECK (working_days_per_year BETWEEN 1 AND 366)`; `ck_project_fte_hours CHECK (hours_per_working_day BETWEEN 0.25 AND 24)` | `project` | **D-67** — the FTE basis is always usable |
| `ck_pdr_set` (`TO_BE` / `AS_IS`); `ck_pdr_element` (CHECK-listed elements); `ck_pdr_started_locked CHECK (element_code <> 'STARTED' OR is_active)`; UK `uq_project_dfd_rule (project_id, bfc_set_code, element_code)` full. **Service-enforced:** ORDER needs DATA_IN and DATA_OUT (422), re-proved by `dfd_rule_invalid`; a chart with no live row reads as STARTED + DATA_OUT and `project_without_dfd_rule` refuses the freeze | `project_dfd_rule` | **D-70** — a rule can never be empty in effect, and never requires order without the data it is derived from |
| `UNIQUE (client_id, program_code)`; partial `uq_program_name_live (client_id, lower(program_name)) WHERE is_active`; `uq_program_client`, `uq_program_client_live`, `uq_program_live` as FK targets | `program` | D-32 — program identity within a client; targets for the same-client and live-program FKs |
| `fk_project_program_client (program_id, client_id) → program`; `program_is_active GENERATED` + `fk_project_program_live (program_id, client_id, program_is_active) → program` ON UPDATE NO ACTION; `uq_project_live UNIQUE (project_id, is_active)` | `project` | **D-32 — a program's projects share its client; an active project sits only in a live program; a program with live projects cannot be retired (Q4).** Moving a project between programs is platform-admin only and audited (service) |
| `ck_app_user_kind CHECK (user_kind IN ('USER','VIEWER'))`; `uq_app_user_email (lower(email))` | `app_user` | **D-40** — staff are USER (edit) or VIEWER (read); `is_platform_admin` overrides the kind |
| partial `uq_pm_live (project_id, app_user_id) WHERE is_active`; `project_is_active GENERATED` + `fk_pm_live_project (project_id, project_is_active) → project (uq_project_live)` ON UPDATE NO ACTION; `ck_pm_level CHECK (access_level IN ('EDIT','VIEW'))`; `ck_pm_note_not_blank` | `project_member` | **OR-6, D-62** — one live membership per user per project; re-adding inserts a new row (each period is history); a live membership blocks retiring its project |
| `ck_grant_one_scope CHECK (num_nonnulls(project_id, program_id) = 1)`; partial `uq_grant_one_live_per_user`; live-scope guard FKs | `user_access_grant` | retired (D-40): no live rows remain and `vb_app` cannot INSERT or UPDATE (§6.6); the constraints keep the history consistent |
| `UNIQUE (project_id, ms_unique_id)` (full); `UNIQUE (wbs_item_id, project_id)`; FK `(parent_wbs_item_id, project_id)`; `CHECK ((outline_level = 1) = (parent_wbs_item_id IS NULL))`; `CHECK (parent_wbs_item_id <> wbs_item_id)`; date-order CHECKs; `CHECK (actual_finish IS NULL OR actual_start IS NOT NULL)`; `CHECK (percent_complete BETWEEN 0 AND 100)`; composite FKs `(phase_id, project_id)`, `(solution_id, project_id)` | `wbs_item` *(when built)* | **D-33, Q13, R2-D15** — one row per MS Project Unique ID per project, restored rather than duplicated on re-import; links cannot cross projects. `row_version` guards the two links only (documented deviation). No unique on `wbs_code` (renumbered by MS Project on outline moves) |
| `ck_dl_type CHECK (diagram_type IN ('ERD','PROCESS_FLOW','DFD'))` — **new `PROCESS_FLOW` rows are refused by the service** (S7-5); `ck_dl_one_object CHECK (num_nonnulls(bfc_node_id, data_entity_id, external_entity_id, bfc_node_flow_id, process_trigger_id) = 1)`; `ck_dl_erd_entity`; `ck_dl_event_flow_only CHECK (diagram_type = 'PROCESS_FLOW' OR bfc_node_flow_id IS NULL)`; `ck_dl_scope CHECK (diagram_type = 'ERD' OR scope_bfc_node_id IS NOT NULL)`; `ck_dl_collapse_erd`; `uq_dl_object UNIQUE NULLS NOT DISTINCT (project_id, diagram_type, scope_bfc_node_id, bfc_node_id, data_entity_id, external_entity_id, bfc_node_flow_id, process_trigger_id)` (a constraint, named in `ON CONFLICT`); composite `(id, project_id)` FKs | `diagram_layout` | D-30 — one position per object per diagram per scope; typed, project-safe pointers, triggers included (D-49). Old `PROCESS_FLOW` positions stay as history. **Exempt from soft delete and `row_version`** (documented deviation, A-52) |
| `ck_ib_target_entity CHECK (target_entity IN ('ISSUE','DATA_ENTITY','DATA_FIELD','BUSINESS_REQUIREMENT','FUNCTION_REQUIREMENT','PROCESS_FLOW','WBS_ITEM'))`; `ck_ib_flow_format CHECK ((target_entity = 'PROCESS_FLOW') = (source_format LIKE 'vb-process-flow/%'))`; `ck_ib_import_mode`; `ck_ib_mode_targets CHECK ((target_entity IN ('PROCESS_FLOW','WBS_ITEM')) = (import_mode IS NOT NULL))`; `ck_ib_flow_anchor CHECK ((target_entity = 'PROCESS_FLOW') = (anchor_bfc_node_id IS NOT NULL))`; `ck_ib_retire_needs_replace CHECK (retire_count = 0 OR import_mode IS NOT DISTINCT FROM 'REPLACE')`; count bounds; `uq_import_batch_target (import_batch_id, target_entity)` | `import_batch` | D-25 / D-33 — a flow import states its format, mode and anchor; a WBS import states its mode; **merge never retires** |
| `fk_ir_batch (import_batch_id, target_entity) → import_batch`; `ck_ir_kind_fits_target`; `ck_ir_locator` (none for RETIRE / KEPT, a JSON pointer for flow rows, a sheet row otherwise, S4-1); `ck_ir_valid_matches_errors`; `ck_ir_verdict CHECK (verdict IN ('INSERT','UPDATE','MATCH','RETIRE','KEPT'))`; `ck_ir_db_staged_target`; `ck_ir_retire_kinds`; `ck_ir_kept_kind CHECK (verdict <> 'KEPT' OR row_kind = 'STEP_IO')`; partial `uq_ir_local_key (import_batch_id, row_kind, local_key)` and `uq_ir_business_key (import_batch_id, row_kind, business_key)` | `import_row` | D-25, S4-2 — every staged object is locatable and fits its batch; validity cannot disagree with its errors; a duplicate file-local key or a business key named twice in one file is caught at staging (R2-D1, backstop to S4-4); `KEPT` marks step I/O a replace-mode flow import would have retired but a dependent protects (§7.2b). The flow-file row kinds of `vb-process-flow/2.0` are added by the import's own migration (§7.2b) |
| `SELECT … FOR UPDATE` on the batch row as the first statement of `commit`, status re-checked inside the lock, plus `row_version` sent on commit | `import_batch` | **a committed batch cannot be re-committed (P2)** — a CHECK is stateless and cannot express a state transition |
| `row_version` + `WHERE row_version = :v` on every UPDATE (ORM `version_id_col`) | all editable business tables | **D-6 — two consultants on one record never overwrite each other silently** (stale → 409) |
| `uq_baseline_version UNIQUE (project_id, major_no, minor_no)`; `version_label GENERATED ('v' ‖ major_no ‖ '.' ‖ minor_no)` + `uq_baseline_label`; `ck_baseline_major`, `ck_baseline_minor` | `baseline` | P9 — version identity is two integers; the label is rendered from them and can never disagree |
| `uq_baseline_prior UNIQUE (prior_baseline_id)`; partial `uq_baseline_first (project_id) WHERE prior_baseline_id IS NULL`; `ck_baseline_prior CHECK ((prior_baseline_id IS NULL) = (major_no = 1 AND minor_no = 0))` | `baseline` | A-8 — a straight line of versions, declaratively; two simultaneous freezes give one baseline and one 409 (criterion 37) |
| `ck_baseline_approval_set CHECK (num_nonnulls(client_approver_name, client_approved_on, approved_at, approved_by_user_id) IN (0, 4))`; `ck_baseline_approval_reference`; `ck_baseline_depth`; `ck_baseline_hash_spec`; `content_digest char(64) NOT NULL` | `baseline` | §4.6, DR8-P1, DR8-S1 — an approval is recorded whole or not at all; the header carries the digest of everything it froze |
| `ck_baseline_dfd_rule_pair CHECK (num_nonnulls(dfd_rule_to_be, dfd_rule_as_is) IN (0, 2))`; `ck_baseline_dfd_rule_vals` (each non-empty, within the element list); `ck_baseline_fte_pair CHECK (num_nonnulls(fte_working_days, fte_hours_per_day) IN (0, 2))`; `ck_baseline_fte_from_spec_3` and `ck_baseline_dfd_rule_from_spec_3 CHECK (hash_spec_version < 3 OR … IS NOT NULL)`; all four columns in `fn_baseline_header_guard()`'s frozen list | `baseline` | **D-70, D-67** — a baseline says which DFD rule each chart passed and the FTE basis it was priced on, and never changes either |
| `baseline` is **exempt from soft delete** — no `is_active`, no `deleted_*`; `fn_baseline_header_guard()` `BEFORE UPDATE OR DELETE` rejects DELETE, any change to a frozen column, and any change to an approval once recorded | `baseline` | P6 — a baseline is either frozen or it does not exist; only status and a first approval may be written (§6.6) |
| `uq_baseline_<t>_source (baseline_id, source_id)`; `source_id` FK **ON DELETE NO ACTION** | every `baseline_*` | one snapshot row per live row per baseline; a frozen baseline cannot be shredded by a cascade |
| `BEFORE UPDATE OR DELETE` reject trigger (`fn_reject_modification()`) **and** the statement-level `AFTER INSERT` guard (`fn_shadow_insert_guard()`: rows only into a baseline whose header was written in the same transaction) | every `baseline_*` | immutability at the database, not by convention (A-7); nothing is ever appended to an existing baseline (DR8-S1). No TRUNCATE trigger (S8-2) |
| `raised_by_stakeholder_id NOT NULL` and separate `recorded_by_user_id NOT NULL` | `issue` *(when built)* | D-4, D8 — who raised it and who typed it are different facts and cannot collapse |
| partial `UNIQUE (project_id, lower(btrim(stakeholder_name))) WHERE is_active` | `stakeholder` *(when built)* | D6 — the importer matches people by name, so the lookup must return at most one row |
| `accountable_org_role_id NOT NULL` | `benefit` *(when built)* | D-14 — a benefit with no owner is a hope, not a benefit |
| `exposure_score` derived from probability × impact at save | `risk` *(when built)* | D-15 — the score cannot be argued down independently of its inputs |
| `against_baseline_id NOT NULL` + composite `(against_baseline_id, project_id) → baseline (uq_baseline_project)`; **status rule service-enforced under lock** (R2-D11): the target baseline is read `FOR SHARE` and must be FROZEN, APPROVED, or the SUPERSEDED one carrying the agreed approval (SC-2); `freeze` supersedes the prior header `FOR UPDATE`, so the two serialize. `BASELINE_STATUS` seeded `is_system` | `change_request` *(when built)* | D-16, **Q8, SC-2** — a CR challenges something agreed: a baseline in force, or the superseded one that still carries the agreed client approval (DR8-P1). Point-in-time: an existing CR keeps its target when that baseline is later superseded |
| `effort_delta_days` / `benefit_delta_value` writable **only** by `price_cr` | `change_request` *(when built)* | D-16 — a change priced by its requester is not priced |
| topological check on insert; a cycle is rejected | `solution_dependency` *(when built)* | D-18 — a dependency cycle makes the phase plan unsolvable and is silent until someone tries to schedule |
| `UNIQUE (analysis_code) WHERE project_id IS NULL` + `UNIQUE (project_id, analysis_code) WHERE project_id IS NOT NULL`; `analysis_code` in a closed list matching §7.9; `CHECK (project_id IS NULL OR owner_org_role_id IS NOT NULL)` | `control_rule` *(when built)* | D-19 — two tiers (one FTC house default and one agreed rule per project per analysis); no rule for a non-existent analysis; **an analysis without a named owner is a report nobody acts on** (relaxed on the house tier, which precedes the client's org chart) |
| `CHECK (num_nonnulls(impacted_br_id, impacted_solution_id, impacted_fr_id, impacted_application_id, impacted_data_entity_id, impacted_phase_id, impacted_benefit_id) = 1)` + composite `(id, project_id)` FK on each | `cr_impact` *(when built)* | A-37 — the database enforces which object a CR row points at, and that it belongs to this project |
| `BEFORE UPDATE OR DELETE` reject trigger; **exempt from soft delete**; no `UPDATE`/`DELETE` grant | `decision` *(when built)* | A-41 — the decision log is evidential. Corrections are a new row with `supersedes_decision_id` |
| `bfc_node_flow` constraints (`ck_bnf_has_end`, `ck_bnf_flow_type`, `ck_bnf_conditional_label`, `ck_bnf_seq`, process guards, partial `uq_bfc_node_flow_edge`) | `bfc_node_flow` | retired (D-38): they remain on the read-only history rows; no row can be inserted or updated by `vb_app` (§6.6) |

**Rules the database does *not* hold, stated as such (R2-D11).** A CHECK sees one row of one table and has no
memory of the old row. So rules that read another table, or a transition, are service-enforced under a named
mechanism, each with a `consistency_check` proof or a test:
- the CR target status (`change_request`, when built);
- the as-is allocation and the as-is-only supporting-system rule (`application_solution`, `application_bfc_node`);
- the FR's solution tag answering one of its BRs (`function_requirement`, D-52; drift is the warning
  `fr_solution_outside_its_brs`);
- the BFC set's immutability and Q1's sibling-name rule beyond the process index (§7.2);
- **"no active row under an inactive parent"** on every FK in §5.4.15 except those whose target key includes
  `is_active` (R2-D2), proved by the `*_under_inactive` lines, which block a freeze;
- live rows only in components that are on (`rows_in_off_component`, which blocks a freeze, D-37).

A row in this table that claims a CHECK the database cannot evaluate is a defect in this spec, and a review
should treat it as one.

### 6.3 Indexes

- **Every FK gets an index** — PostgreSQL does not create them automatically, and this schema is FK-dense.
- `bfc_node`: the partial unique `uq_bfc_hier_code_live (project_id, bfc_set_code, hier_code)` serves the chart
  sort; `ix_bfc_hier_pattern (project_id, bfc_set_code, hier_code varchar_pattern_ops) WHERE is_active` serves
  the subtree prefix query (`steps_under`); `uq_bfc_sibling_seq` serves tree expansion; `ix_bfc_process_live
  (project_id, bfc_set_code) WHERE is_process AND is_active` serves the process list, the freeze count and
  `consistency_check`.
- **Referencing-side indexes for every composite guard FK.** A NO ACTION check on an UPDATE of
  `bfc_node.is_process` or `bfc_node_data_entity.is_active` scans the referencing table, on every promote,
  demote and I/O removal. Concretely: `ix_bfc_parent_guard (parent_bfc_node_id, project_id,
  parent_is_process)`, `ix_brde_io (bfc_node_id, data_entity_id, direction)`, `ix_bnef_io (bfc_node_id,
  data_entity_id, direction)`, and `(bfc_node_id, project_id)` on each guarded table (`ix_bnde_node`,
  `ix_bnor_node`, `ix_bnef_node`, `ix_bntr_node`, `ix_appnode_node`).
- **Performer** (D-46): `ix_bfc_perf_unit (performer_org_unit_id, project_id) WHERE performer_org_unit_id IS
  NOT NULL`, and the same for role and application — the liveness scan when an org unit, role or application
  retires.
- **Triggers** (D-49): `ix_bntr_trigger (process_trigger_id, project_id)`, `ix_bntr_project`; the live-name
  unique on `process_trigger` serves the catalogue lookup.
- `business_requirement (project_id, br_number)` (the UK) and `uq_br_one_per_node (bfc_node_id)`.
- `br_data_entity (data_entity_id)` — the reverse lookup "which BRs touch this DE", the impact-analysis screen.
- `bfc_node_external_flow (external_entity_id, project_id)`: "which steps does the Bank touch".
- **BR ↔ FR** (D-52): `uq_brfr_grain (br_id, fr_id)` serves "FRs serving this BR" and the step-retire scan;
  `ix_brfr_fr (fr_id, project_id)` serves "BRs this FR serves", the untraced-FR anti-join and
  `v_interface_list.br_numbers`; `ix_brfr_project`.
- `fr_interface (project_id, source_application_id, target_application_id)`: the interface list by application
  pair (`interface_load`).
- `function_requirement`: `ix_fr_unlinked (project_id) WHERE solution_id IS NULL AND is_active` (FRs with no
  solution tag, `?unassigned=`); `ix_fr_behaviour (project_id, fr_type_behaviour) WHERE is_active`
  (`v_interface_list`).
- `diagram_layout`: served by `uq_dl_object` (leading `project_id, diagram_type, scope_bfc_node_id`), plus one
  partial index per object column `WHERE <col> IS NOT NULL` for the object FKs.
- `data_field (data_entity_id, ref_data_entity_id, fk_group_no) WHERE is_foreign_key`: ERD relationship grouping.
- `bfc_node_org_role`: `uq_bnor_one_accountable (bfc_node_id) WHERE is_active AND raci_behaviour =
  'ACCOUNTABLE'` is also the Accountable lookup for an as-is step; `uq_bror_one_accountable` for a BR.
- `project_member`: `ix_pm_user_live (app_user_id) WHERE is_active` serves `visible_project_ids` on every
  request; `uq_pm_live` serves the project side.
- `project_component`: `uq_project_component` (leading `project_id`) serves `require_on` and `purge_project`.
- `bfc_node_flow`: `ix_bnf_from`, `ix_bnf_to (…, project_id)` remain for the guard-FK checks on the history rows.
- `wbs_item` *(when built)*: `(project_id, ms_unique_id)` is the unique index (the import match);
  `(parent_wbs_item_id)`; `(project_id, display_order) WHERE is_active` (tree render); `(phase_id) WHERE is_active`
  and `(solution_id) WHERE is_active` (the dashboard, and the Q4 refusal when a phase or solution is retired).
- `import_batch`: `ix_ib_purge_due (uploaded_at) WHERE rows_purged_at IS NULL` (the 90-day purge scan);
  `ix_ib_project (project_id, uploaded_at DESC)`; `ix_ib_anchor`.
- `code_master`: the referencing-side indexes on `(fr_type_code_id)` and `(raci_code_id)` make the NO ACTION check
  cheap on the rare behaviour edit.
- `issue (project_id, status_code_id, severity_code_id)` *(when built)* — the issue dashboard.
- `project (program_id) WHERE is_active` — program roll-ups (§7.10a).
- `baseline_*`: `uq_baseline_<t>_source (baseline_id, source_id)` serves the diff join, the per-baseline listing
  and intra-baseline joins; `ix_baseline_<t>_source (source_id)` serves the FK check and "every baseline in
  which BR-0042 appeared". No other shadow index.
- `audit_event (project_id, occurred_at)`.

### 6.4 Row-level security

**PostgreSQL RLS with a session variable is recommended as defence-in-depth, and is not in MVP.** RLS on a
connection-pooled FastAPI app needs the session variable set per checkout, which is a known footgun. MVP ships
the service-layer guard (`services/access.py`, §7.8). Under D-62 most projects are restricted, so the project
wall again matters on every request, and the wall is where a missed filter would go unnoticed; RLS remains a
scheduled decision, not an oversight.

**The deferral has a stated price.** The compensating control must be structural, not prose:

> **The condition of deferring RLS is acceptance criterion 49** — every route declares exactly one guard from
> the guard registry (`routers/guards.py`, R2-S1); a route without one fails at import, and the test re-proves
> it; a write guarded at VIEW is refused (49), and a write to a project component that does not name its
> component fails (49b). **Together with the restricted-project leak test** (DR7-S2:
> `tests/test_access.py::test_no_get_route_leaks_a_restricted_project` calls every GET route as a non-member
> and finds none of the project's marked rows), it is what stands in for RLS. If either test is not in the
> build, RLS is not deferred; it is absent.

### 6.6 Database privileges

Grants, not code (S11, R2-S9). The application connects as `vb_app`; migrations run as `vb_owner`
(`MIGRATION_DATABASE_URL`).

- **The application role does not own the schema.** It holds no DDL and **no `TRUNCATE` anywhere**. Default
  privileges give it SELECT, INSERT and UPDATE on new tables.
- **No `DELETE` on any table, with exactly two exceptions:** `diagram_layout` (the documented hard delete,
  A-52) and `import_row` (the 90-day purge, Q14). Soft delete is an UPDATE, so the app never needs DELETE on a
  business table, and §5.6's "never write a hard-delete endpoint" is a **permission error**, not a review rule.
  `import_batch`, `project_member`, `user_access_grant` and `audit_event` get no DELETE: they are the import
  trail, the access history and the security log.
- **No `UPDATE` on `decision`** (A-41), **on any `baseline_*` table**, or **on `audit_event`** (append-only by
  grant and trigger; even the owner cannot UPDATE it). The reject triggers (§6.2) are the belt, the revoked
  grants the braces.
- **`baseline` (header): column-level `UPDATE` only on** `status_code_id`, the approval columns
  (`client_approver_name`, `client_approved_on`, `approval_note`, `approval_reference`, `approved_at`,
  `approved_by_user_id`), `updated_by` and `row_version`. The FROZEN → APPROVED → SUPERSEDED transitions (Q8,
  DR8-P1) need these and nothing else; `fn_baseline_header_guard()` additionally refuses any change to a
  recorded approval. No DELETE: that is Q12's five-year recoverability, held by the database.
- **Shadows: SELECT and INSERT only**, and INSERT is accepted only into a baseline whose header was written in
  the same transaction (the insert-guard trigger, DR8-S1).
- **`import_batch`: column-level `UPDATE`** on its lifecycle, count and purge columns only (a write-once trail,
  S4-9).
- **Retired tables are SELECT-only:** `user_access_grant` (INSERT and UPDATE revoked, D-40) and `bfc_node_flow`
  (INSERT and UPDATE revoked, D-38). "No new rows" is a database fact.
- **Views** `v_br_function_requirement` and `v_interface_list`: INSERT and UPDATE revoked; both are
  `security_invoker`.
- **A CI test reads `information_schema.role_table_grants`** and fails if `vb_app` holds DELETE on anything other
  than the two tables above, UPDATE on a table or column listed here, or INSERT/UPDATE on a retired table. A
  grant is migration state, and migration state drifts.
- *Optional hardening:* run the purge job under a separate `vb_maintenance` role and drop `DELETE ON import_row`
  from `vb_app`. The HTTP-serving role would then delete only layout rows.
- **Azure (D-35):** both roles' credentials live in Key Vault, fetched by managed identity. The owner role's
  secret is available only to the migration job, never to the App Service at runtime.

Why this is cheap insurance: all users share one application database role with no RLS, so a single logic or
injection defect reaches every project at once. **Parameterise every raw query**, and escape `%` and `_` in any
`LIKE` prefix built from stored data (the subtree queries match on a `hier_code` prefix).

### 6.5 Schema generation

**The DDL is the Alembic migration chain** (one migration per commit, reversible; a destructive one pauses for
Ben — VB law 10), with partial and expression indexes in raw `op.execute`. Every new table is imported in
`models/__init__.py` so autogenerate sees it.

**Shadow tables are generated by `services/baseline_shadow.py`** and were written once as literal DDL in
migration 0048 (later shadows likewise, e.g. 0050), which imports nothing from `models`, so replaying the chain
on a fresh database next year builds the same columns. **The parity test (criterion 27,
`tests/test_baseline.py`) reads `information_schema.columns` after `upgrade head` and compares every shadow's
column names and types with `shadow_table(live)`** — live columns minus audit columns, plus snapshot columns
(§6.1). A live column added without its shadow column in the same migration fails CI; that test is what keeps
shadow tables safe against schema drift (§5.4.4).

---

## 7. Function — where business logic lives

All logic in the service layer (§9.11). Routers do HTTP only: each route declares one guard (§7.8), which
resolves the project, checks visibility (404), level (403) and, for writes to a project component, that the
component is on (409 `COMPONENT_OFF`, D-37), in that order.

### 7.0 Grid function → service map

Every function named in the §4 grid, and where it lives. Access levels are `VIEW` < `EDIT` < `ADMIN` (D-40).

<!-- CHECK: grid function names for the D-37…D-64 functions (performer, triggers, chart copy, BR↔FR link, solution tag, components, members, restriction, approve) are taken from the services and routes in code; align with the names the rewritten §4 uses. -->

| §4 grid function | Service | Written out in |
|---|---|---|
| `create_bfc_node` | `bfc.create_node` | §7.2 |
| `generate_bfc_code` | `bfc._code` (inside `create_node` / `reorder`) | §7.2 |
| `reorder_bfc_node` | `bfc.reorder` | §7.2 |
| `mark_process` | `bfc.mark_process` | §7.2 (D-23; promote creates the BR of a to-be process; demote refused while any step fact is live) |
| `describe_process` | `bfc.update_node` | §7.2 (the `is_process` guard, D-23) |
| `copy_bfc_set` | `bfc_set.copy_set` | §7.2 (D-47, S7 Q-24) |
| `set_performer` | `bfc.set_performer` | §7.2a (D-46) |
| `maintain_process_triggers` · `link_process_trigger` | `trigger.create/update/retire/restore_trigger` · `trigger.link` / `unlink` | §7.2a (D-49) |
| `link_bfc_data_entity` | `step_io.link` / `step_io.unlink` (writer: `step_io.ensure_step_io`) | §7.3 (unlink refused while a BR CRUD or an external flow depends on it, D-24, R2-D13) |
| `link_bfc_external_flow` · `create_external_entity` | `bfc.link_external_flow` · `external_entity.create_party` | §7.3 (ensures step I/O, R2-D13) |
| `generate_dfd` · `export_dfd` | `process_flow.generate_dfd` / `render.export_dfd` | §7.2a (D-31, D-38) |
| `process_completeness` | `process_flow.process_completeness` | §7.2a (D-38, D-49, S7-3; the chart's rule, D-70) |
| `dfd_readiness` | `process_flow.readiness` | §7.2a (D-68, D-69) |
| `get_dfd_rule` · `preview_dfd_rule` · `set_dfd_rule` | `dfd_rule.codes` / `preview` / `set` | §7.2a (D-70) |
| `draw_dfd_connection` · `draw_hand_off` · `remove_dfd_flow` | the existing writers (`step_io.ensure_step_io`, `bfc.link_external_flow`, `trigger.link`, the unlink routes) · `process_flow.hand_off` | §7.14 (D-65) |
| `set_process_volume` · `derive_volume` · `set_fte_basis` · `volume_summary` | `process_volume.set` / `derive` / `project.set_fte_basis` / `process_volume.summary` | §7.2a (D-67) |
| `download_flow_schema` · `export_process_flow_json` | `flow_import.schema` / `flow_import.export` | §7.2b (D-25) |
| `validate_process_flow_json` · `commit_process_flow_json` | `flow_import.validate` / `flow_import.commit` | §7.2b (D-25, D-55, on the §7.11 pipeline) |
| `generate_erd` · `export_erd` | `data_entity.generate_erd` / `render.export_erd` | §7.4 (D-29) |
| `save_diagram_layout` | `diagram_layout.save` | §7.14 (D-30) |
| `link_bfc_role` | `raci.link` (`bfc_node_org_role`, **as-is steps only**) | §7.0 (generic) (D-64) |
| `create_data_entity` | `data_entity.create_entity` | §7.4 |
| `manage_data_fields` | `data_entity.create_field` / `update_field` | §7.4 |
| `validate_entity_model` | `reports.entity_model_validation` | §7.9 |
| `create_br` | `business_requirement.create_br` (never from a router) | §7.3 |
| `link_br_data_entity` | `business_requirement.link_data_entity` | §7.3 |
| `update_br` | `business_requirement.update_br` | §7.3 |
| `maintain_br_lines` · `tick_br_attributes` · `state_br_system_flow` | `br_line.*` · `business_requirement.save_crud_grid` · `br_system_flow.*` | §7.3 (D-59, D-60b, D-61; slice 11) |
| `flow_coverage` · `create_interface_fr_from_flows` | `br_system_flow.coverage` · `br_system_flow.seed_interface_fr` | §7.3 (D-61) |
| `link_br_role` | `raci.link` (`br_org_role` — the RACI of a to-be process) | §7.0 (generic) (D-64) |
| `link_br_solution` | `solution.link` / `edit_note` / `unlink` | §7.5 (S5-3) |
| `link_br_function_requirement` | `function_requirement.link_fr` / `edit_link_note` / `unlink_fr` | §7.5 (D-52) |
| `set_fr_solution_tag` | `function_requirement.set_solution_from_br` · `update_fr` (`solution_id`) | §7.5 (D-52) |
| `create_solution` | `solution.create_solution` | §7.5 |
| `create_application` | `application.create_application` | §7.5 |
| `link_application_solution` | `application.link_solution` | §7.5 |
| `link_bfc_application` | `application.link_step` (as-is processes only) | §7.5 |
| `solution_matrix` | `reports.solution_matrix` | §7.9 |
| `application_gap_report` | `reports.application_gap` | §7.9 |
| `create_stakeholder` | `stakeholder.upsert` | §7.6 |
| `download_template` | `bulk.template` | §7.11 |
| `export_entity` | `bulk.export` | §7.11 |
| `validate_import` | `bulk.validate` | §7.11 |
| `preview_import` | `bulk.preview` | §7.11 (P3) |
| `commit_import` | `bulk.commit` | §7.11 |
| `retire_step` · `restore_step` | `step_retire.preview` / `retire` / `restore` | §7.12 (S3-SR) |
| `br_coverage_report` | `reports.coverage` | §7.9 |
| `create_function_requirement` | `function_requirement.create_fr` | §7.5 |
| `link_fr_to_bfc_node` | — **retired, never built** (SC-3) | — |
| `maintain_fr_types` | `code_master.maintain` (category `FR_TYPE`, with behaviour) | §7.12 (D-27) |
| `describe_interface` | `interface.describe_interface` / `remove_interface` | §7.5 (D-27) |
| `interface_list` | `interface.interface_list` (over `v_interface_list`) | §7.5 / §7.9 (D-27) |
| `fr_unlinked` | `reports.fr_unlinked` | §7.13 (D-28, re-based on the BR link by D-52) |
| `fr_traceability_matrix` | `reports.traceability` | §7.9 |
| `raise_issue` | `issue.raise_issue` | §7.6 |
| `link_issue_br` | `link_service` pattern | §7.0 (generic) |
| `resolve_issue` | `issue.resolve_issue` | §7.6 |
| `issue_dashboard` | `reports.issue_dashboard` | §7.9 |
| `freeze_baseline` | `baseline.preview` / `baseline.freeze` | §7.7 |
| `approve_baseline` | `baseline.approve` | §7.7 (§4.6, DR8-P1) |
| `diff_baseline` | `baseline.diff` (+ `priced`) | §7.7 |
| `reopen_baseline` | — | **not implemented, by design** (§4.6) |
| `login` | `auth.login` | §7.10 |
| `create_user` · `set_user_kind` · `set_platform_admin` | `user_admin.*` | §7.10 (D-40) |
| `deactivate_user` | `user_admin.deactivate_user` | §7.10 (S4) |
| `create_project` | `project.create_project` | §7.10 (platform admin; components, depth and the restriction chosen explicitly; ten series — D-37, D-39, D-62, R2-D14) |
| `set_project_components` · `set_data_model_depth` | `components.set_components` · `project.set_depth` | §7.10 (D-37, D-39; platform admin, preview → confirm) |
| `manage_project_members` · `restrict_project` · `list_effective_access` | `project.add/change/remove_member` · `project.set_restriction` · `access.effective_access` | §7.10 (OR-6, D-62; platform admin) |
| `list_visible_projects` | `access.visible_project_ids` | §7.8 |
| `enforce_project_scope` | `access.require_project` | §7.8 |
| `soft_delete_record` · `restore_record` | `lifecycle.retire` / `lifecycle.restore` | §7.12 (refuse with dependents; allow-list — R2-D2, R2-S5) |
| `consistency_check` | `consistency.consistency_check` | §7.12 (D11; inactive-parent lines R2-D2; runs inside the freeze R2-P6) |
| `resolve_codes` | `code_master.resolve` | §7.12 (D12) |
| `maintain_rate_card` | `effort.maintain_rate_card` | §7.13 |
| `rate_function_requirement` | `effort.rate_function_requirement` | §7.13 |
| `effort_summary` | `effort.summary` | §7.9 / §7.13 |
| `priced_diff` | `baseline.priced` | §7.7 / §7.13 |
| `create_benefit` · `link_benefit_solution` | `benefit.*` / `link_service` pattern | §7.13 / §7.0 |
| `value_ranking` · `benefit_gap_report` | `benefit.value_ranking` / `reports.benefit_gap` | §7.13 |
| `raise_risk` · `score_risk` · `promote_risk_to_issue` · `risk_register` | `risk.*` | §7.13 |
| `raise_change_request` · `analyse_cr_impact` · `price_cr` · `decide_cr` | `change.*` | §7.13 |
| `record_decision` · `decision_log` | `decision.*` | §7.13 |
| `create_phase` · `assign_solution_phase` · `link_solution_dependency` · `phase_plan_report` | `phase.*` | §7.13 |
| `maintain_control_rule` · `control_panel` | `control.*` | §7.13 |
| `requirement_volatility` · `process_change_intensity` · `org_impact_heatmap` · `stakeholder_engagement` · `interface_load` · `data_migration_map` · `master_data_candidates` | `reports.*` | §7.9 |
| `create_program` · `update_program` · `move_project_program` | `program.*` | §7.10a (D-32) |
| `program_dashboard` · `program_counts` · `program_interfaces` · `program_effort` · `program_control_status` | `program.rollup` | §7.10a (D-32, R2-S2) |
| `download_template` / `validate_import` / `commit_import` (`wbs`) · `link_wbs_item` · `wbs_plan_vs_actual` | `bulk.*` (WBS map) / `wbs.link` / `wbs.plan_vs_actual` | §7.11a (D-33, D-41) |
| `purge_import_rows` | `import_purge.purge_import_rows` | §7.12b (Q14) |
| — every Mermaid exporter | `render.escape_mermaid` | §7.12b (R2-S7) |
| — every route | `guards.*` (the guard registry) | §7.8 (R2-S1) |

**The link pattern.** Plain link / unlink functions are not written out one by one; they share one pattern,
implemented in each owning service with `lifecycle.relink` / `lifecycle.unlink`:

```
link(user, owner, other_id, **key):                 # guard: object_guard(Owner, "EDIT", component=…)
    lock the owner's step FOR SHARE (when it has one), then the owner, then the other end   # SR-5
    both ends live and in owner.project_id, else 409 "… is retired. Restore it first" / 404
    row = the pair by its FULL grain UK, FOR UPDATE                 # key = raci_code | direction | …
    if row is None:      insert (project_id copied from the owner, never from the body)
    elif row.is_active:  409 "already linked"
    else:                lifecycle.relink(row)                       # restore, never re-insert (S1-7)
unlink(row, row_version):  soft-delete WHERE row_version = :v        # law 1; 409 on a stale version
```
Every junction carries `project_id` and composite FKs, so the cross-project check is made twice: once in the
service and once by the database (§5.6). **`raci.link` adds one rule (D-64):** a step role on a to-be process is
refused with 409 "Roles of a to-be process are recorded on its requirement"; the BR's roles and an as-is step's
roles keep one Accountable each (`raci.SINGLE`, keyed on behaviour, R2-D9), which the database also enforces.

### 7.1 `services/numbering.py` → `next_number(db, project_id, sequence_code)`


The one place any VB identifier is minted (§9.10). Called at save, inside the transaction that inserts the row —
never on screen load (§9.8).

```
next_number(db, project_id, sequence_code):          # 'DE','BR','FR','ISSUE','SOL','BEN','RSK','CR','DEC','EXT'
    row = PROJECT_SEQUENCE(project_id, sequence_code) FOR UPDATE
    if absent: raise MissingSequence        # never insert lazily — create_project seeds all ten (R2-D14)
    row.last_value += 1
    return f"{row.prefix}-{row.last_value:0{row.pad_width}d}"   # DE-0001, BR-0001, FR-0001, ISS-0001, EXT-0001
```
Gap-tolerant by design: a rolled-back transaction burns a number. Numbers are identifiers, not counts — a gap is
not a defect. As-is processes, triggers and applications mint no number.

### 7.2 `services/bfc.py` → `create_node(...)`, `generate_code(node)`, `reorder(...)`

```
create_node(project_id, parent_id, name, is_process=False, purpose_desc=None, bfc_set='TO_BE'):
    # guard: project_ctx("EDIT"); the AS_IS component is checked here because the set comes from the body
    parent  = live node of this project, or None for a root
    bfc_set = parent.bfc_set_code if parent else bfc_set     # a child takes its parent's chart (D-47)
    if bfc_set == 'AS_IS': components.require_on(project_id, 'AS_IS')          # 409 COMPONENT_OFF
    level = 1 if parent is None else parent.level_no + 1
    if level > 5: 422 "The chart is fixed at 5 levels"
    if parent and parent.is_process:
        422 "A process has no children. Split it into sub-steps first"   # D-23 (DB-enforced too)
    if is_process and level not in (3, 4, 5): 422 "A process sits at level 3, 4 or 5"   # A-47
    assert_name_free(project_id, parent_id, name, bfc_set)                    # Q1
    seq_no = last live sibling's seq_no + 1;  if seq_no > 99: 422            # S1-3
    node = insert(…, level_no=level, seq_no, hier_code=_code(parent, seq_no),
                  is_process = is_process or level == 5, bfc_set_code=bfc_set)   # A-54
    if node.is_process and bfc_set == 'TO_BE':                                # D-2, S7-2
        business_requirement.create_br(node)          # same transaction, exactly one, DRAFT
    commit

normalise_name(s):            # Q1 — one definition, used by the flow import too
    return collapse_whitespace(unicodedata.normalize("NFKC", s)).strip().casefold()

assert_name_free(project_id, parent_id, name, except_id=None, bfc_set):
    if an ACTIVE sibling (roots: in the same set) has normalise_name(name), other than except_id:
        409 f"'{name}' already exists under this parent ({sibling.hier_code})"
    # Called by create_node, rename (update_node) and restore. The DB backs it for process steps
    # (uq_bfc_process_name); this check is wider (every live sibling) and stricter (NFKC, case-folded,
    # whitespace collapsed), so it is the rule and the index is the backstop.

_code(parent, seq_no):                                 # generate_bfc_code
    return f"{seq_no:02d}" if parent is None else f"{parent.hier_code}.{seq_no:02d}"   # 01.02.03.04.05
    # hier_code is varchar(40), derived per chart; both charts have an 01 (D-47)

reorder(node, row_version, new_seq_no):               # S1-2 — two phases for seq_no AND hier_code
    # PostgreSQL cannot defer a partial unique index, so a swap would collide mid-update.
    siblings = live siblings in the node's set; 1 <= new_seq_no <= len(siblings), else 422
    moved = every sibling whose position changes
    phase 1: moved.seq_no = -seq_no;  every live node in their subtrees: hier_code = '~' || bfc_node_id
    phase 2: moved.seq_no = target;   re-derive hier_code for each moved sibling and its subtree
    AUDIT_EVENT('BFC_REORDERED', {from, to, subtree_size})

update_node(node, row_version, fields):                # describe_process
    rename → assert_name_free(…, except_id=node);  data_processing_desc only on a process (422)

mark_process(node, row_version, is_process):           # D-23
    if is_process:                                      # promote
        level 3, 4 or 5, else 422 (A-47);  no live children, else 409 "the lowest one is the process"
        is_process = TRUE; if to-be: business_requirement.create_br(node)    # D-2, S7-2 — exactly one
    else:                                               # demote
        if level 5: 422 "A level-5 node is always a process"                 # A-54
        blockers = live BR, step data, step roles, external flows, as-is applications, triggers,
                   the performer, data_processing_desc
        if blockers: 409 "Retire first: …"              # named, so the fix is obvious
        is_process = FALSE
    # REFUSAL, NEVER CASCADE (R2-P5, Q4). The service retires no blocker on the consultant's behalf,
    # because each one is a scope fact a later diff must be able to show was removed deliberately.
    # The database refuses the same demotion through the guard FKs and ck_bfc_performer_process; the
    # service check exists to name the blockers. (Retiring a whole process step with its owned rows is the
    # one confirmed, undoable exception — S3-SR, docs/step_retire_spec.md.)

copy_set(project_id, to_set, from_set, confirm_hash):  # D-47, S7 Q-24; project_ctx("EDIT", component="AS_IS")
    the target set has no live node, else 409; preview → confirm (hash over the source rows' versions)
    one transaction, under a per-project advisory lock; every row made live passes needed_for_rows (DR7-P2)
    copies nodes (fresh ids, same hier_code), performers, step I/O, external flows, trigger links
    roles: as-is step roles → the new to-be BRs' roles; to-be BR roles → the new as-is step roles (D-64)
    application_bfc_node: to-be → as-is only;  as-is → to-be mints a new DRAFT BR per process (D-2)
    never copied: BR CRUD, solutions, FRs.  The old → new id map goes into one BFC_SET_COPIED audit event
```
Output data: one BFC node row with a stable dotted code per chart, and a re-coded subtree on reorder; on
`mark_process`, the process flag and, for a to-be process, its single BR.

### 7.2a `services/process_flow.py` — the DFD (D-31, D-38, D-46, D-47, D-49, D-65, D-67…D-70)

**There is one process diagram: the DFD (D-38).** It is generated (D-31) — a connection drawn on the canvas writes
the same row the panel writes (D-65, §7.14) — from the rows the BFC already holds: process steps, their inputs and outputs (`bfc_node_data_entity`, D-24), external flows (D-24a),
triggers (D-49) and performers (D-46). **Order is derived from data, never stored:** B follows A when B reads a
data entity A writes; a branch is two outputs feeding different processes; a loop is a later process writing
what an earlier one reads. Each chart (to-be, and the optional as-is, D-47) has its own DFDs; nothing crosses
charts. **`bfc_node_flow` (explicit order arrows) is retired:** never read, never written; its routes and the
`PROCESS_FLOW` diagram type are gone (§6.1, §6.6). A DFD is listed for every direct parent of processes (D-54)
and can be opened for any non-process node.

```
set_performer(node, row_version, kind, code | label):   # D-46; object_guard(BfcNode, "EDIT", component=node_set_component)
    # node_set_component(node) = "AS_IS" for an as-is node, else none: recordable whatever the DFD setting (S10c-2)
    node is a live process; locks the node and the target FOR SHARE
    kind ORG_UNIT / ORG_ROLE / APPLICATION → the live row with that CODE in this project (codes, never ids),
         a retired target → 409;  AI → a non-blank label;  None → clears it
    AUDIT PERFORMER_SET {from, to}
    # A TO_BE application performing an as-is process warns and is allowed (S6b-4 pattern).
    # Retiring an org unit, role or application that performs a live process → 409 naming the processes (R2-D2).

trigger catalogue (process_trigger):      # D-49; writable while EITHER DFD component is on (trigger.require_any_dfd)
    create / update / retire / restore by name; name live-unique; TIME may carry schedule_note
    retire with live links → 409 naming the processes; live triggers block switching both DFD components off
trigger.link(node, process_trigger_id, note) / unlink:   # step-owned (step_retire.OWNED_BY_STEP)
    the link pattern (§7.0), process steps only, component = dfd_component(node)

dfd_rule.codes(project_id, bfc_set) -> tuple:     # D-70; THE one reader of the rule
    live = sorted(element_code of live project_dfd_rule rows for (project, chart))
    if not live: return ("DATA_OUT", "STARTED")       # fails closed: the fixed rule, never "nothing required"
    return sorted(set(live) | {"STARTED"})

ELEMENTS = {   # code → predicate over one live process (EXISTS sub-selects, one SQL pass)
  STARTED:  a live step input OR a live inbound external flow (with or without a DE) OR a live trigger link
  DATA_IN:  a live step input (a data entity)
  DATA_OUT: a live step output (an outbound external flow with only a flow_label is not a data entity)
  ORDER:    joined to another process of its chart by the derived order (generate_dfd's pairs); one process passes
  EXTERNAL: per DIAGRAM (the DFD listed for a direct parent of processes, D-54): at least one outside party —
            never part of a process's light (Q-6, Q-16)
}
RECOMMENDED = {"TO_BE": {STARTED, DATA_IN, DATA_OUT, ORDER}, "AS_IS": {STARTED}}   # code constants; create_project

readiness(db, project_id, bfc_set, node_ids=None):   # D-68; one owner — the light, the marks, completeness, freeze
    if the chart's DFD component is off: return {rule_applies: False}            # S7-3
    rule = dfd_rule.codes(project_id, bfc_set)
    per live process: missing = [e for e in rule if not ELEMENTS[e](p)]
                      light = RED if missing                        # blocks the freeze (Q-13)
                              else YELLOW if RECOMMENDED[bfc_set] − rule has an unmet element
                              else GREEN
    return {rule_applies, rule, processes: {node_id: {light, dfd_missing}}}
    # exposed on bfc.tree (dfd_light, dfd_missing per process row) and on process-completeness (readiness)

process_completeness(project_id, bfc_set):    # GET /projects/{id}/process-completeness
    r = readiness(project_id, bfc_set)
    return {
      "rule_applies":  …,
      "missing_input" (STARTED), "missing_output" (DATA_OUT), "missing_data_in", "missing_order",
      "diagram_missing_external":          only the elements in the chart's rule; FREEZE_BLOCKING_WARNINGS
      "no_performer":                      warning only, never blocks the freeze (D-46)
      "step_without_br":                   to-be only (S7-2)
      "crud_without_io", "ext_without_io": must be empty (criteria 93, 148; D-24, R2-D13)
      "live_link_on_retired_step":         must be empty (step retire §4)
      "readiness":                         r.processes
    }
    # FREEZE_BLOCKING_WARNINGS are amber while editing and a refusal at freeze (§7.7). A requirements-only
    # project has no DFD component on and is never blocked by them. consistency_check adds the error lines
    # project_without_dfd_rule and dfd_rule_invalid (ORDER without DATA_IN and DATA_OUT).

dfd_rule.validate(codes): STARTED always present; ORDER requires DATA_IN and DATA_OUT; unknown code → 422
dfd_rule.preview(project, bfc_set, codes) → {ready, partly, not_ready, would_block, preview_digest}
dfd_rule.set(actor, project, bfc_set, codes, row_version, preview_digest):      # project_ctx("ADMIN")
    lock the project FOR UPDATE; 409 on a stale row_version or a changed digest; validate → 422
    restore / insert added rows, retire dropped rows (S1-7); project.row_version bumps (never from the body)
    AUDIT PROJECT_DFD_RULE_CHANGED {bfc_set_code, from, to, would_block}

process_volume.set(actor, node, row_version, fields):   # D-67; object_guard(BfcNode, "EDIT", node_set_component)
    node live and is_process (422); unit resolved by code_master.resolve(project, 'TRANSACTION_UNIT') (send codes)
    each figure ≥ 0 and ≤ CAPS (runs 1,000,000 · transactions 100,000,000 · seconds 86,400); more decimals → 422
    body is extra="forbid": annual_hours / fte → 422 (law 6);  AUDIT PROCESS_VOLUME_SET {from, to}
process_volume.derive(node, basis):    # on every read; Decimal; never stored
    PERIODS_PER_YEAR = {DAY: basis.working_days_per_year, WEEK: 52, MONTH: 12, QUARTER: 4, YEAR: 1}
    annual_hours = runs × PERIODS_PER_YEAR[period] × transactions × seconds / 3600
    fte          = annual_hours / (basis.working_days_per_year × basis.hours_per_working_day)
    any input missing → {annual_hours: null, fte: null, incomplete: [fields]}
process_volume.summary(project):        # per chart, per L1 / L2 area
    Σ hours, Σ FTE, n complete, n incomplete; as-is beside to-be where the areas MATCH — same level, same
    hier_code AND same lower(btrim(node_name)); otherwise unmatched with a reason (CODE_SAME_NAME_DIFFERS,
    NAME_ELSEWHERE, ONLY_AS_IS, ONLY_TO_BE), never summed against the other side            # Q-28

steps_under(node):        # live process descendants of a node, in the node's own set (hier_code prefix)

generate_dfd(node):       # GET /bfc-nodes/{id}/dfd; object_guard(BfcNode, "VIEW")
    node live (409 if retired) and not a process (422 "drawn for a parent node, not a step")
    steps = steps_under(node)
    return {
      "scope":      {bfc_node_id, hier_code, node_name, bfc_set_code},
      "lanes":      one per distinct performer + UNASSIGNED; order: org units (level, seq), roles (unit, code),
                    applications (code), AI (label), unassigned last                    # D-46
      "processes":  {…, lane_key, br_number (to-be only), data_processing_desc, rank,
                     systems: supporting applications — as-is ← APPLICATION_BFC_NODE;
                              to-be ← BR → BR_SOLUTION → APPLICATION_SOLUTION, only while SOLUTION and
                              APPLICATION are on (OR-2), else empty}                  # D-8, D-22 rule per chart
      "stores":     data entities read or written in scope,
      "externals":  external parties in scope,
      "triggers":   {process_trigger_id, trigger_name, trigger_kind, schedule_note} linked in scope,
      "flows":      STORE   one per step I/O row not already drawn by an external flow (store → step if 'I')
                    EXTERNAL one per external flow (party ↔ step, labelled with the DE or the flow_label)
                    TRIGGER  trigger → step,
      "order":      derived pairs {from, to, data_entity_ids} for A ≠ B where A outputs and B inputs a DE,
      "rank":       per process: Tarjan SCC condensation, then longest path from a source component, so loops
                    are legal and layout terminates                                   # S7 Q-33
                    — when "order" in scope is empty: chart order (seq_no under each parent, hier_code order),
                    no arrows, labelled "chart order"                                 # D-70, Q-3 option A
      "boundary":   in = stores read in scope and written by a process of the same chart outside it;
                    out = the reverse; drawn as stubs, never across charts,
      "completeness": the rule's gaps, no_performer, and each process's light, for the processes in scope,
      "cross_area": stores written in one L1 area and read in another, counted across the whole chart,
      "layout":     DIAGRAM_LAYOUT rows for ('DFD', node), triggers included          # D-30
    }
    # A GRAPH, NOT A PICTURE (D-21). Saved positions are returned where a consultant placed something;
    # auto-layout of the rest is the frontend's job (§7.14).

export_dfd(g, with_order=False):          # GET /bfc-nodes/{id}/dfd/export
    Mermaid flowchart LR: one subgraph per performer lane (unassigned last) holding its processes;
    stores as cylinders, parties as squares, triggers as circles; one edge per flow in its direction,
    labelled; boundary stubs as dotted links to an "outside" box; the derived order only when asked, dashed.
    node ids are generated ("s"+bfc_node_id, "d"+data_entity_id, "x"+…, "t"+…) — never user text
    EVERY label through render.escape_mermaid(), and _guard ends the exporter      # R2-S7, §7.12b
```

**As-is and to-be (D-47).** A project holds the to-be chart, and optionally an as-is chart with its own processes,
performers and data flows, sharing one data-entity catalogue, external parties, triggers, org chart and
applications, so the two pictures compare on the same `DE-` numbers. The difference between them is the
transformation, which is exactly the slide a consultant needs.

### 7.2b `services/flow_import.py` — process flow JSON (D-25)

**The file format is the contract, so it is versioned and published.** `vb-process-flow/2.0` is a JSON Schema
served by `download_flow_schema`, together with a worked example and the **AI conversion prompt pack** — the rules
an AI follows to turn a slide, a BPMN export or a Visio diagram into a valid file. The pack names the two approved
services, **Claude or Microsoft Copilot under FTC's own accounts only**, and opens with the step that removes
personal data first (D-36). The consultant runs the conversion; **VB calls no AI itself** (A-51) and receives only
the resulting JSON. Export writes the same format, so a flow round-trips. **A file carries what the DFD is drawn
from — steps, performers, inputs, outputs, triggers and external flows — and no edges and no lanes** (D-38).
`1.0` files are refused with "re-export from VB".

<!-- CHECK: the full 2.0 JSON Schema is owed to the import slice (wave 1e, not built: bulk.TARGETS holds only DE/DF). The external-party list below is carried from 1.0, since slice7 §9.9 does not restate how a party is referenced. -->

```json
{
  "format": "vb-process-flow/2.0",
  "parent": { "hier_code": "01.02.03", "name": "Order to cash — order capture" },
  "mode":   "merge",
  "external_entities": [ { "key": "X1", "ext_number": null, "name": "Customer", "kind": "CUSTOMER" } ],
  "steps": [
    { "key": "S1", "br_number": "BR-0012", "hier_code": "01.02.03.01", "row_version": 4,
      "name": "Receive order", "description": "…",
      "performer": { "kind": "ORG_ROLE", "code": "SALES-ADMIN" },
      "triggers":  [ { "name": "Customer calls", "kind": "EVENT" } ],
      "inputs": ["DE-0007"], "outputs": ["Sales order"],
      "external_flows": [ { "external": "X1", "direction": "I", "data_entity": "DE-0007" } ],
      "source_ref": "slide 4, shape 12" },
    { "key": "S2", "br_number": null, "hier_code": null, "row_version": null,
      "name": "Check credit", "description": "…",
      "performer": { "kind": "AI", "label": "Credit-scoring agent" },
      "inputs": ["Sales order"], "outputs": ["Credit decision"],
      "source_ref": "slide 4, shape 15" }
  ]
}
```

Rules the schema and the prompt pack both state — **keys are local to the file**, and business keys (`BR-`,
`DE-`, `EXT-`) and names are how the file meets the database:

1. **A step with a `br_number` updates that BR's process** (R2-D1, to-be anchors only — an as-is process has no
   BR; **an as-is step is always matched by name within its parent, rule 2**, SC-6). The BR number never changes; `hier_code` does, on every reorder (D-10). If the file also carries a
   `hier_code`, it must equal the node's current one, or the step is an error: "BR-0012 moved since export: now
   01.02.05, file says 01.02.03 — re-export". A `row_version` that is not the node's current one is an error that
   names the current values (R2-D5). **A step with a `hier_code` and no `br_number` is an error** — `hier_code` is
   a cross-check, not an identity.
2. **A step with neither is matched by name** (R2-P1). If a live process **directly under the anchor** has the
   same normalised name (Q1 makes it unique), the step **updates it**, with the warning "matched existing step
   01.02.03.04 by name". Otherwise the step is **created** as a new process under the anchor, in the anchor's
   chart, with its BR in the same transaction when the chart is to-be (D-2, S7-2). An AI conversion never knows
   BR numbers, so without this rule every re-run of the same slide would duplicate every step.
3. **Inputs and outputs** name a data entity by `DE-` number (it must exist in this project) or by exact name;
   an unknown name is **created**, with a warning, and listed in the preview (D-55).
4. **The performer** is `{kind, code}` for an org unit, org role or application (matched by its live code), or
   `{kind: "AI", label}`. **The file's performer replaces the step's performer** (D-46); nothing else about who
   does the work is touched — RACI is never read or written by an import. An unknown code leaves the performer
   blank, with a warning (D-55). Org units, roles and applications are never created from a file.
5. **Triggers** are matched by live name in the project's catalogue; an unknown trigger is created in the
   catalogue (name + kind), with a warning.
6. **External flows** link the step to a party (by `ext_number`, or a new party by name) with a direction and an
   optional data entity, through `bfc.link_external_flow`, which ensures the step I/O (R2-D13).
7. **The anchor node and the mode are chosen in VB, not by the file** (R2-P3). `parent` and `mode` in the file are
   checked against them, and a mismatch rejects the file. A file cannot aim itself at a different branch, or turn
   itself into a replace.
8. `mode: "merge"` (default) never retires anything. **`mode: "replace"` retires only step I/O and trigger links
   of the file's steps that the file omits** (Q5). **An I/O row that a BR CRUD or an external flow depends on is
   kept**, with a warning naming the dependent. Steps, BRs, performers, roles and external flows are never retired
   by an import. Every RETIRE row is listed in the preview, and the retire count must be acknowledged.
9. **An imperfect file still imports, with warnings** (D-55): a process with no input or trigger, or no output;
   a process connected to nothing; an unknown data-entity name (created); an unknown performer (left blank);
   missing descriptions. The gaps stay visible on the diagram's warnings panel and, where the chart's DFD rule
   requires the element, still block a freeze while unresolved (D-70). **A file is rejected, with nothing staged, only for** an unreadable file, a wrong format
   version, a different anchor or mode than chosen (R2-P3) or a stale `row_version` (R2-D5); and a step is an
   error when its identity is wrong — an unknown or out-of-scope BR number, a moved `hier_code`, a `hier_code`
   without a `br_number`, two steps resolving to one process, or two steps with one name — because importing it
   would write to the wrong process (SC-6).
10. `source_ref` is kept on the staged row so the preview can say *which shape on which slide* a problem came
    from — that is what makes an AI conversion checkable by a human.

```
validate_process_flow_json(project_id, anchor_bfc_node_id, mode, file):   # R2-P3: route-carried
    # guard: project_ctx("EDIT"); Target.component = the anchor's DFD component (TO_BE_DFD | AS_IS)
    anchor = live, non-process bfc_node of this project, else 404 / 422
    mode in ('merge', 'replace'), else 422
    enforce_json_limits(file)                      # §7.12a — bytes, depth, steps; body cap at ingress (R2-S8)
    doc = json.loads(file, parse_constant=reject)  # no NaN / Infinity
    jsonschema.validate(doc, VB_PROCESS_FLOW_2_0)  # structural errors → 422, nothing staged; 1.0 → 422 "re-export"
    doc.parent.hier_code == anchor.hier_code, else 422 "This file is for …; you chose …"
    doc.mode (default merge) == mode, else 422 "Nothing was staged"

    batch = INSERT IMPORT_BATCH(target_entity='PROCESS_FLOW', anchor_bfc_node_id, import_mode=mode.upper(),
                                source_format=doc.format, …)
    under   = steps_under(anchor)                                  # same chart, any level (D-23, D-47)
    by_name = {normalise_name(n.node_name): n for n in live process CHILDREN of anchor}
    for s in doc.steps:                                            # rules 1–2
        resolve to UPDATE (by BR number, cross-checked, row_version checked; or by name, warned) or INSERT
        errors: BR not in project / outside `under`, moved hier_code, hier_code without br_number,
                stale row_version, two file steps on one node, repeated name (Q1)
        INSERT IMPORT_ROW(row_kind='STEP', verdict, payload, source_ref, is_valid, error_detail, warning_detail)
    for performer, triggers, inputs/outputs, external flows: resolve per rules 3–6
        warnings (D-55): new data entity / trigger / party to be created, unknown performer left blank,
                         step with no input-or-trigger, step with no output, unconnected step, no description
    if mode == 'replace':                                          # rule 8 — Q5
        for io in live BFC_NODE_DATA_ENTITY on the file's resolved steps, not in the file:
            deps = live BR_DATA_ENTITY needing io ∪ live BFC_NODE_EXTERNAL_FLOW needing io
            stage STEP_IO as KEPT (warning names deps) if deps else RETIRE
        for t in live BFC_NODE_TRIGGER on the file's resolved steps, not in the file: stage STEP_TRIGGER RETIRE
        # NEVER staged for retirement: steps, BRs, performers, roles, external flows.
    batch counts (insert / update / retire / error / warning; MATCH and KEPT not counted, S4-7)
    return batch summary                      # nothing has touched a business table

preview(batch_id):   # the §7.11 preview, plus every RETIRE row by business key and description, every KEPT row
                     # with its warning, and before/after for every UPDATE step, computed now, never stored (S4-8)

commit_process_flow_json(batch_id, confirm):
    same lock / status / row_version / full re-validation as bulk.commit (§7.11), including
        acknowledged_inserts == insert_count  whenever insert_count > 0    # R2-P1, R2-P2
        acknowledged_retires == retire_count  whenever retire_count > 0
        the RETIRE set RE-COMPUTED inside the lock; if it differs → 409 "The flow changed since preview —
        validate again"
    one transaction, in dependency order:
        EXTERNAL_ENTITY, DATA_ENTITY, PROCESS_TRIGGER (new ones)       # numbers minted HERE (§9.8)
        BFC_NODE new steps (is_process, the anchor's set) + their BUSINESS_REQUIREMENT when to-be
        UPDATE steps: name (assert_name_free), description — WHERE row_version = :v   # 409 on 0
        BFC_NODE_DATA_ENTITY via step_io.ensure_step_io
        BFC_NODE_EXTERNAL_FLOW via bfc.link_external_flow             # ensures I/O too (R2-D13)
        BFC_NODE_TRIGGER via the link pattern
        performers via set_performer's rules (rule 4)
        RETIRE rows: soft-delete each I/O / trigger link, re-checking it has no dependent
    AUDIT_EVENT('IMPORT_COMMITTED', {entity: 'PROCESS_FLOW', anchor, mode, counts…})
```

**Staging rows.** The flow import stages `STEP`, `STEP_IO`, `EXTERNAL_ENTITY`, `EXTERNAL_FLOW` and
`DATA_ENTITY` rows as today, and its own migration adds the kinds `PERFORMER` (MATCH only), `TRIGGER` and
`STEP_TRIGGER` to `ck_ir_row_kind` / `ck_ir_kind_fits_target`, `STEP_TRIGGER` to `ck_ir_retire_kinds`, and
`PERFORMER` to the MATCH-only rule. `FLOW_EDGE`, `STEP_ROLE` and `LANE` stay in the lists so rows staged before
remain valid until the 90-day purge (S7 Q-32).

**Why the pipeline is reused rather than a second importer:** the six properties of §7.11 — separate validate and
commit, all-or-nothing, numbers at commit, project-scoped keys, re-validation inside the lock, approval of
consequences — matter *more* for an AI-produced file than for a hand-typed spreadsheet, because nobody typed it.

### 7.3 `services/business_requirement.py` → `create_br(...)`, `link_data_entity(...)`

```
create_br(node):                                   # never commits; the node change's transaction owns it
    if not node.is_process: 422 "A business requirement attaches to a process step"   # D-23
    # to-be only: the database refuses a BR on an as-is node (fk_br_node_to_be, S7-2)
    br_number = numbering.next_number(project_id, "BR")
    insert(…, status = BR_STATUS/DRAFT)

update_br(br, row_version, fields, status_code):   # D-6
    check live + row_version (409 "changed by someone else. Reload and reapply")
    BASELINED / SUPERSEDED are set only by the freeze → 422 if sent (S1-8)

link_data_entity(br, data_entity_id, crud_code, usage_note):
    crud_code in ('C','R','U','D'), else 422
    lock the step FOR SHARE, then the BR (SR-5); BR live, else 409
    step_io.ensure_step_io(step, data_entity_id, 'I' if crud_code == 'R' else 'O')   # D-24, the ONE writer
    the link pattern on BR_DATA_ENTITY (br_id, data_entity_id, crud_code)            # relink restores (S1-7)
    # The BR and the DFD cannot disagree: the step I/O the DFD shows is created with the CRUD that needs it,
    # and step_io.unlink refuses to remove it while any BR CRUD or external flow depends on it.
    # direction is GENERATED: 'R' → 'I', else 'O'. One BR reading AND updating one entity is two rows.

unlink_data_entity(row, row_version):   # soft-unlink; the step I/O stays — a fact about the step, removed on its own
```
Output data: one BR row; one BR↔DE row per CRUD operation, with direction derived.

```
step_io.ensure_step_io(node, data_entity_id, direction):   # R2-D13 — the one writer of step I/O; never commits
    lock the node FOR SHARE (SR-5); node live and a process, else 422; entity live in this project, else 422
    row = BFC_NODE_DATA_ENTITY(node, data_entity_id, direction)
    if row is None: insert;  elif retired: lifecycle.relink (restore, audited)
    # Called by: business_requirement.link_data_entity, bfc.link_external_flow, the step I/O editor
    # (step_io.link, 409 on a live duplicate), the flow import and copy_set. Nothing else writes step I/O.

bfc.link_external_flow(node, external_entity_id, direction, data_entity_id | None, flow_label, note):
    # component: TO_BE_DFD on a to-be step, AS_IS on an as-is step
    lock the node FOR SHARE; node a live process; party live in this project
    if data_entity_id: step_io.ensure_step_io(node, data_entity_id, direction)   # I needs an input, O an output
    the link pattern on BFC_NODE_EXTERNAL_FLOW (step × party × direction × DE)

step_io.unlink(row, row_version):
    crud = live BR_DATA_ENTITY on this step, same DE, same direction
    ext  = live BFC_NODE_EXTERNAL_FLOW on this step, same DE, same direction
    if crud or ext: 409 f"Still needed by {BR-0012 R, EXT-0003 I, …}"
    soft-delete WHERE row_version = :v
```
Output data: one step I/O row per (step × entity × direction), created only by the helper and removed only when
nothing depends on it. **An external flow and a BR CRUD are the same kind of dependent** (R2-D13).

**D-2 in the service:** creating a to-be process (`create_node`, `mark_process`, the flow import, `copy_set`
as-is → to-be) creates its single BR in the same transaction (S7-2). `create_br` is never called from a router —
there is no "add requirement" action — and `uq_br_one_per_node` makes a second live one impossible even by direct
SQL. The consultant edits the requirement that appeared with the process, from the process's panel in the
function chart (D-53).

Every editable business table takes `update_br`'s shape: `WHERE row_version = :v`, and 409 when no row matched.
The 409 is in the playbook error table (§7 doctrine); D-6 is what makes it reachable.

**The structured BR (D-59, D-60b, D-61, S11-1; slice 11).**
```
update_br(...):   EDITABLE = {br_statement} (+ status); business_logic / output_expectation are read-only legacy

br_line.add(br, kind_code, priority_code | None, text):      # D-59; no component; EDIT
    BR live; codes through code_master.resolve (BR_LINE_KIND, BR_PRIORITY); text non-blank
    line_no = max(line_no of ALL the BR's lines, retired included) + 1   # minted at save, never reused, never sent
    seq_no  = last live + 1
br_line.update / retire / restore / reorder(seq_no)           # row_version; reorder is a position change only
br_priority(br) = highest priority among live lines (MUST > SHOULD > COULD > WONT), else none   # derived, never stored

business_requirement.save_crud_grid(br, entity_ticks, attribute_ticks, row_versions):   # D-60b; ONE request
    entity ticks first (link_data_entity, which ensures the step I/O, D-24)
    attribute ticks: crud in ('C','R','U'); the licence FK proves the entity row with the same CRUD is live
    an unticked entity action retires its attribute ticks EXPLICITLY (the user removed them; nothing cascades)
unlink_data_entity(row): live attribute ticks under it → 409 naming them

br_system_flow.add(br, data_entity_id, source_app_id, target_app_id, note):   # D-61; component APPLICATION
    both applications live in this project and different; the entity live; relink restores (S1-7)
    info `flow_entity_not_used_by_br` when the BR has no live CRUD on the entity
br_system_flow.coverage(flow) = the same BR links a live interface-behaviour FR whose fr_interface has the
    same source and target and whose carried entities include the flow's entity        # derived, no fr_id stored
br_system_flow.seed_interface_fr(br, flow_ids):   # components FUNCTION_REQUIREMENT + APPLICATION
    all flows of this BR, one (source, target) pair, else 422
    one transaction: FR (an interface-behaviour type) + fr_interface + one fr_interface_data_entity per entity
                     + br_function_requirement link; numbers minted at save
```
All three tables are owned by the BR (`step_retire.OWNED`; `br_data_field` in a tier ahead of `br_data_entity`), are
soft-deleted only, and are frozen from hash spec 4. A retired data field, application or entity still used by a
live row → 409 naming the BRs (FK liveness).

### 7.4 `services/data_entity.py` → `create_entity(...)`, `upsert_field(...)`

```
create_field / update_field(de, name, spec):        # upsert_field
    # D-26: logical. data_type_code optional; is_mandatory ∈ TRUE / FALSE / NULL (unknown)
    lock the entity (FOR NO KEY UPDATE), the order the import's commit takes
    name free among the entity's live fields (lower(btrim)), S1-6
    if data_type_code: validate_required_code("FIELD_DATA_TYPE", data_type_code)
    is_primary_key ⇒ pk_ordinal given, else 422
    ref_data_entity_id given ⇒ a live entity of this project, else 422 "cross-project FK";
        ref_data_field_id, if given, belongs to it;
        fk_group = 'new' | an existing relationship number to that entity — the service assigns
        fk_group_no (S1-7, §5.4.17)
    ref_data_entity_id = null clears the FK (is_foreign_key, ref field and group together)
```
Output data: one data field row, with the PK/FK metadata that makes the DE list a real logical model rather than
a glossary. Extra fields are always accepted (D-39).

```
generate_erd(project_id, subject_area_node_id=None):              # D-29; project_ctx("VIEW")
    entities = live DATA_ENTITY in project
    if subject_area_node_id:
        entities = those in the live I/O of the processes under that node, in its own chart (steps_under)
    return {
      "entities": [ {id, de_number, de_name, description, field_count,
                     fields: [pk fields by pk_ordinal] + [fk fields] + [attributes],
                     warnings: NO_KEY when no PK field;
                               KEYS_ONLY when the project's depth is FULL and every field is a key   # D-39 } ],
      "relationships": [ {          # one per FK group (child entity, parent entity, fk_group_no)
          child_data_entity_id (holds the FK), parent_data_entity_id, fk_group_no, via_fields,
          parent_cardinality: '1' if every FK field is_mandatory is TRUE else '0..1',
          child_cardinality:  '1' if the group's fields == the child's PK field set, else 'many',
          identifying: every FK field is part of the child's PK,              # solid vs dashed
      } ],
      "outside_refs": FK groups to an entity outside the scope or retired     # drawn as a stub
      "data_model_depth": the project's (D-39),
      "layout": DIAGRAM_LAYOUT rows for ('ERD', scope),
    }
```
A logical ERD, deliberately: relationships come only from FK fields the consultant declared, so the diagram is
exactly as complete as the model. An entity with no key fields is drawn with a warning badge rather than hidden.

### 7.5 `services/solution.py`, `function_requirement.py`, `application.py`

```
create_solution(project_id, name, category_code, …):        # D-7; component SOLUTION
    validate_required_code("SOLUTION_CATEGORY", category_code)  # ORG_AND_RULES | PEOPLE | PROCESS | DATA | TECHNOLOGY
                                                               # a system category (S5-4)
    name free among live solutions (S5-5); status PROPOSED
    solution_number = numbering.next_number(project_id, "SOL")

solution.link(br, solution_id, coverage_note):               # BR_SOLUTION; the link pattern; component SOLUTION
    # a REJECTED solution can be linked; the link shows its status and coverage does not count it (S5-2)
solution.edit_note(row, row_version, note)                    # in place; the previous note to the audit (S5-3)
solution.unlink(row, row_version):   # the FR tags it leaves outside their BRs are named, never cleared (D-52)

create_fr(project_id, name, fr_type_code, solution_id | None, fields, br_id | None):   # component FUNCTION_REQUIREMENT
    type = validate FR_TYPE (project-editable, D-27); fr_type_behaviour copied from it
    fr_number = numbering.next_number(project_id, "FR"); fulfilment status SPECIFIED; effort unrated (S6a-3)
    if br_id:   link_fr(br, fr) in the same transaction (slice10b Q-20);
                a solution, if given, must be a live solution of THAT BR, else 422
    elif solution_id: the solution is a live solution of this project
    warnings: no_br (no live BR link — the D-28 warning, re-based by D-52),
              non_technology_solution, rejected_solution (S6a-5),
              duplicate_name (a live FR of the same name under the same solution, S6a-2)

link_fr(br, fr_id, coverage_note):          # D-52 — the primary BR ↔ FR mapping; component FUNCTION_REQUIREMENT only
    the FR is fetched scoped to the BR's project (404 otherwise)
    locks: step FOR SHARE → BR FOR SHARE → FR FOR SHARE, then both live, then the pair FOR UPDATE
    the link pattern on BR_FUNCTION_REQUIREMENT; a dead pair is relinked with the new note
    allowed even when the FR's tag does not answer this BR — the response warns (fr_solution_outside_its_brs)
edit_link_note(row, row_version, note)      # in place; previous note to the audit (S5-3)
unlink_fr(row, row_version):                # soft-unlink; the tag is never cleared; the response names the FR
                                            # when its tag now answers none of its BRs, or it has no BR left

set_solution_from_br(br, link, solution_id | None, fr_row_version):   # PUT …/function-requirements/{link}/solution
    # component FUNCTION_REQUIREMENT + SOLUTION (clearing to NULL needs only FUNCTION_REQUIREMENT)
    locks: step → BR (FOR SHARE) → FR FOR UPDATE (row_version, 409) → the link FOR SHARE (live, else 409)
           → solution FOR SHARE → the BR_SOLUTION pairing FOR SHARE
    a solution that is not a live BR_SOLUTION of THIS BR → 422 "SOL-0003 does not answer BR-0042. Add it to
        this requirement's solutions first."     # the server never creates a BR_SOLUTION (slice10b Q-5)
    audit RECORD_UPDATED {previous_solution_number, from_br}

update_fr(fr, row_version, fields, fr_type_code, status_code, solution_id?):   # the FR register
    lock FR FOR UPDATE; check live + row_version
    a new solution tag must answer AT LEAST ONE of the FR's live BR links (any live solution when it has
        none, with no_br) — 422 otherwise                                     # slice10b Q-3
    type change: INTERFACE behaviour → another behaviour with live interface detail → 409 "This FR has interface
        detail. Remove it first, or keep an interface type";  effort re-derived from the rate card for (new
        type, complexity), 422 when no cell; warns effort_changed                  # D-13
    a moved tag or a retype is audited with the previous values
    # Retiring an FR with live BR links → 409 naming the BRs (S10b-2); with live interface detail → 409 (S6b-3).

describe_interface(fr, source_app, target_app, pattern, method, frequency, volume_note, carried, row_version):
    # D-27; component FUNCTION_REQUIREMENT + APPLICATION
    fr.fr_type_behaviour == 'INTERFACE' (behaviour, never the code), else 422
    both applications live in fr.project_id and distinct (ck_fri_endpoints_distinct)
    one transaction: upsert FR_INTERFACE; every PUT bumps its row_version, which covers the carried set;
        replace the carried FR_INTERFACE_DATA_ENTITY set, keeping notes the request did not touch (S6b2-4)
    # Complete = source, target, method and ≥ 1 carried entity; pattern and frequency optional (S6b2-1).

maintain_fr_types(project_id, code, label, behaviour_code):          # D-27; EDIT
    if code exists as a GLOBAL FR_TYPE and this project has no override yet, in one transaction:   # A-16
        override = insert CODE_MASTER(project_id, 'FR_TYPE', code, label, behaviour_code)
        UPDATE effort_rate          SET fr_type_code_id = override WHERE project = :p AND type = global
        UPDATE function_requirement SET fr_type_code_id = override, fr_type_behaviour = override.behaviour
         WHERE project = :p AND type = global
    # Without the re-point, rate rows seeded against the global code stop matching the override and every
    # new FR of that type gets a 422 from rate_function_requirement.

maintain_global_fr_type(code_id, label, behaviour_code):             # platform admin
    a behaviour change while any FR or EFFORT_RATE (any project) references the code → 409 "This type is in
        use, so its behaviour is fixed. Add a new type instead"      # Q6, R2-D8
    label: always allowed — labels are presentation, and baselines keep their own
```
The FR form shows the **type-specific panel by behaviour, not by code** — a project that renames INTERFACE to
"連携" or adds "API" with behaviour INTERFACE gets the interface panel and the interface list without a code
change (law 5).

```
create_application(project_id, code, name, vendor, kind_code, lifecycle_code):   # D-8; component APPLICATION
    code: upper-case, A–Z 0–9 . _ -, never duplicated; live names unique (S6b-2)
    validate_required_code("APP_LIFECYCLE", lifecycle_code)   # AS_IS | TO_BE | BOTH (system category)
update_application: code editable until a baseline freezes it, old code to the audit (S6b-6, S6b-7);
    lifecycle → AS_IS while it delivers live solutions → 409 naming them (R2-D11);
    lifecycle → TO_BE while it supports as-is steps → allowed, with a warning (S6b-5)

application.link_solution(solution, application_id, note):  # APPLICATION_SOLUTION; component APPLICATION + SOLUTION
    an AS_IS application → 422 "as-is only, so it cannot deliver a future solution"   (read after the lock)
application.link_step(node, application_id, note):         # APPLICATION_BFC_NODE; component APPLICATION + AS_IS
    a process of the AS-IS chart only, else 422 — a to-be process's systems come from its solutions (D-22, D-8)
    a TO_BE application as today's support → allowed, with a warning (S6b-4)
```
Output data: the transformation answer set, categorised across the five operating-model dimensions; the
vendor-facing function list grouped by FR type and traced to the BRs it serves; the generated interface list; and
the target application landscape.

**BR → FR is a stored link, and the view reads it** (D-52):
```sql
CREATE VIEW v_br_function_requirement WITH (security_invoker) AS
SELECT l.project_id,
       l.br_id,
       fr.fr_id,
       fr.fr_number,
       fr.fr_type_code_id,
       fr.fr_type_behaviour,
       fr.solution_id,                               -- the FR's solution tag; may be NULL
       s.category_code_id AS solution_category_code_id,
       l.br_function_requirement_id,
       l.coverage_note,
       EXISTS (SELECT 1 FROM br_solution bs
               WHERE bs.br_id = l.br_id AND bs.solution_id = fr.solution_id AND bs.is_active) AS tag_answers_br
FROM   br_function_requirement l
JOIN   business_requirement br ON br.br_id = l.br_id AND br.is_active
JOIN   function_requirement fr ON fr.fr_id = l.fr_id AND fr.is_active
LEFT JOIN solution s           ON s.solution_id = fr.solution_id AND s.is_active
WHERE  l.is_active;
-- A path BR_SOLUTION → SOLUTION → FR with no link is not a mapping; coverage reports it as the informational
-- line solution_reach_without_link. An FR with no live link is untraced (the D-28 warning, re-based).
```
`v_interface_list.br_numbers` reads this view, so an interface FR mapped with no solution still shows its BRs.
Effort by solution reads the tag, stored once per FR, so it is never double-counted; effort is never summed by BR.

### 7.6 `services/issue.py` → `raise_issue(...)`, `resolve_issue(...)`

Designed, built with the `ISSUE` component's slice; every write names component `ISSUE` (D-37).

```
stakeholder.upsert(project_id, name, job_title, org_unit_id, email, is_bpo):   # D-4
    # a named client-side person with no login. Matched on (project_id, lower(btrim(name))) among live rows
    # by the importer; created if absent.

raise_issue(project_id, title, description, severity_code, issue_type_code,
            raised_by_stakeholder_id, br_ids):
    # guard: project_ctx("EDIT", component="ISSUE")
    if raised_by_stakeholder_id is None: 422 "An issue needs a raiser"     # D-4, D8
    validate_required_code for each of the three category fields
    issue_number = numbering.next_number(project_id, "ISSUE")
    issue = insert(…, status_code="OPEN",
                   raised_by_stakeholder_id=raised_by_stakeholder_id,  # the business user
                   recorded_by_user_id=jwt.user_id)                    # the consultant
    for br_id in br_ids: insert ISSUE_BR(issue.id, br_id)              # each BR live and in-project

resolve_issue(issue_id, resolution, row_version):
    # guard: object_guard(Issue, "EDIT", component="ISSUE")
    if not resolution.strip(): 422 "A resolution is required to close an issue"
    issue.status_code = "RESOLVED"
    issue.resolved_at = now()                      # timestamptz — see A-33 on timezone
    issue.resolved_by_user_id = jwt.user_id        # D8
```

### 7.7 `services/baseline.py` → `freeze(...)`, `diff(...)`

The scope-control core. One transaction and one snapshot; a partial baseline is not a state that can exist.
Baselines are always on — no component gates the freeze, the approval or the diff (S8-1 Q-18).

```
preview(project, bump):            # GET /projects/{id}/baselines/next?bump=; project_ctx("VIEW"); writes nothing
    returns {next_label, confirm_text, errors, freeze_blocking, warnings, counts_by_entity, preview_digest,
             the baseline it will supersede and whether that one still awaits sign-off}

freeze(user, project_id, note, bump, confirm_text, preview_digest):
    # POST /projects/{id}/baselines/freeze; project_ctx("EDIT") — a User freezes, a Viewer is refused (S8-1)
    with a NEW session at REPEATABLE READ, set before its first statement:          # R2-P6
        # The request session already ran the guard's queries at READ COMMITTED. Under READ COMMITTED each
        # SELECT below would take a new snapshot, so an edit committed mid-freeze would land in some shadows and
        # not others; and a check run in another transaction proves nothing about the data the freeze reads.
        access.require_project(user, project_id, "EDIT")            # re-checked inside the snapshot
        prior = latest baseline of the project FOR UPDATE           # None for the first
        major, minor = (1, 0) | (prior.major + 1, 0) if MAJOR | (prior.major, prior.minor + 1)   # P9: integers
        confirm_text == f"{project.project_code} v{major}.{minor}", else 422                       # P6
        report = consistency_check(project_id)                      # SAME transaction (D11)
        errors   = non-empty lines outside INFORMATIONAL ∪ WARNINGS ∪ FREEZE_BLOCKING_WARNINGS
        blocking = non-empty FREEZE_BLOCKING_WARNINGS lines: the process_missing_<element> lines of each
                   chart's DFD rule, read by dfd_rule.codes inside this snapshot (charts whose DFD component is
                   on, D-70, S7-3), diagram_missing_external when the rule holds it, and rows_in_off_component (D-37)
        # project_without_dfd_rule and dfd_rule_invalid are error lines: a missing or invalid rule refuses the freeze
        if errors or blocking: 409 {errors, freeze_blocking}        # criteria 35, 46
        on = components.enabled(project_id)
        content_digest = freeze_set.digest(project_id, on)
        if content_digest != preview_digest:
            409 "The scope changed since you opened this freeze. Review it again; nothing was saved."   # DR8-P2
        b = INSERT baseline(status=FROZEN, hash_spec_version=CURRENT_HASH_SPEC, content_digest,
                            data_model_depth=project.data_model_depth,
                            dfd_rule_to_be=dfd_rule.codes(p, 'TO_BE'), dfd_rule_as_is=dfd_rule.codes(p, 'AS_IS'),
                            fte_working_days=project.working_days_per_year,
                            fte_hours_per_day=project.hours_per_working_day,       # D-70, D-67: header facts,
                            prior_baseline_id=prior?.id,                            # not in content_digest
                            frozen_by_user_id=user, note)            # version_label is GENERATED
        for e in FREEZE_SET:                                         # the 25 shadows of §6.1, in FK order
            if e's gate is closed for `on`: freeze zero rows of it   # D-37; the shadow stays in the set
            INSERT INTO baseline_<t> (baseline_id, source_id, <copied>, <p>_code, <p>_label, content_hash)
            SELECT :b, t.<pk>, t.<copied>, cm.code, cm.label, <hash_sql>
            FROM <t> t LEFT JOIN code_master cm … [JOIN bfc_node for the step-set filter]
            WHERE t.project_id = :p AND t.is_active
        UPDATE business_requirement SET status = BASELINED, row_version = row_version + 1
            WHERE project live BRs not already BASELINED     # AFTER the snapshot: the frozen row keeps DRAFT /
                                                             # CONFIRMED, and status is not hashed (S8-1 Q-17)
        if prior: prior.status = SUPERSEDED                  # FROZEN or APPROVED → SUPERSEDED; approval facts stay
        AUDIT BASELINE_FROZEN {version_label, hash_spec_version, components, content_digest, counts,
                               superseded, superseded_awaiting_sign_off, warnings, warning_detail}
        commit
    unique violation, serialization failure or deadlock → 409 "Something changed while freezing. Nothing was
        saved; freeze again."  (no automatic retry, S8-1 Q-24)
```
WARNINGS (`entities_without_fields`, `entities_keys_only`, `fr_solution_outside_its_brs`) never refuse a freeze;
they are returned in the 201 body and recorded in the audit detail by business number (S4-12, S10b-3).

```
approve(b, client_approver_name, client_approved_on, approval_note, approval_reference, row_version):
    # POST /baselines/{id}/approve; object_guard(Baseline, "EDIT")             # §4.6, DR8-P1
    lock the header FOR UPDATE; stale row_version → 409; an approval already recorded → 409
    the baseline must verify (integrity), and no later version may already carry an approval → 409
    status FROZEN or SUPERSEDED, else 409; approver named; approved_on between the freeze date (ICT) and today
    record the approval set (all or none); FROZEN → APPROVED; SUPERSEDED keeps its status
    AUDIT BASELINE_APPROVED.  No un-approve, no reopen (§4.6)
    # The agreed (contractual) baseline is the newest one with a recorded approval — not a status.

verify(b):   # recompute the digest over every entity's ordered source_id:content_hash list, and every row's hash
             # from its columns; the header reports `intact`; the rows and diff routes refuse (409) a baseline
             # that fails it (DR8-S1)

diff(project_id, a, b):           # GET /projects/{id}/baselines/diff?from=&to={id|live}[&priced=true]; VIEW
    # S3 — the service 404s unless BOTH sides belong to project_id (criterion 50); `live` is the freeze's own
    # gated SELECT, hashed with CURRENT_HASH_SPEC. Every diff runs in its own read-only REPEATABLE READ session.
    for e in FREEZE_SET:
        cols_a, cols_b = e's hashed columns at each side's hash_spec_version
        if one side predates the entity: its rows simply read as ADDED / REMOVED
        elif cols_a != cols_b:                                                    # Q-22: the list grew
            older = the shorter list (each later list EXTENDS the earlier one — a freeze_set module assertion)
            compare on older field by field (the stored hashes cover different lists);
            entry gains compared_on_spec, not_compared = the newer columns   # "Volume is not in v1.2"
            # SCHEMA_VERSION_MISMATCH stays only for a list that does not extend the older one: impossible
        FULL OUTER JOIN A to B on source_id:
            only B → ADDED;  only A → REMOVED
            both, content_hash differs (or, across specs, a column of the older list) → CHANGED + the differing
                                                columns, before / after
            both, hash equal, a position column differs → MOVED              # D-10, P4
            # CHANGED wins over MOVED and carries moved: true (S8-1 Q-14)
        out[e] = {area, component_on: {a, b}, rows: [{source_id, change, fields, moved, label}]}
    br_function_requirement: a side frozen before hash spec 2 derives its links from its own frozen
        br_solution ⋈ function_requirement, and the sides match on (br_id, fr_id), so the first diff after
        direct links arrived shows no false ADDED rows ("derived_sides")      # slice10b Q-14
    priced=true → priced_diff (§7.13) over the FR shadows, only when EFFORT was on in both sides;
        otherwise pricing: {available: false, reason: "EFFORT_OFF"}           # S8-1 Q-20
```
Output data: an immutable baseline, a recorded client approval, and a scope-change report between any two
baselines or a baseline and the live working set — the actual deliverable of scope control. Labels on a link row
resolve its ends inside the same side, so a removed link to a removed BR still reads "BR-0042 ↔ FR-0007".

**`content_hash`, specified (D5, S8-1 Q-15, DR8-L2).** One algorithm, computed in SQL inside the freeze's
`INSERT … SELECT` (`freeze_set.hash_sql`), and the same expression for the live side of a diff, so live and frozen
hashes compare by construction:

```
content_hash = hex(sha256(utf8(
                 concat_ws(E'\x1f',
                   coalesce(char_length(c1::text) || ':' || c1::text, E'\x1e'),
                   coalesce(char_length(c2::text) || ':' || c2::text, E'\x1e'), …))))
               -- c1… = FREEZE_SET[t]'s hashed columns at the baseline's hash_spec_version, in order
```
- **An explicit, versioned column list per entity**, stored as `baseline.hash_spec_version`. The parity test forces
  every new live column into its shadow; only a change to an entity's **hashed** list bumps the version, and so
  does a **new entity joining the set**, which registers its list under the new version (S10b-1). **A later list
  of an entity always extends its earlier one** (append-only, asserted at import), which is what lets the diff
  compare across specs. The specs: **1** — the first freeze set; **2** — `br_function_requirement` joins (slice
  10b); **3** — `bfc_node` adds `runs_per_period`, `volume_period_code`, `transactions_per_run`,
  `transaction_unit_code` and `seconds_per_transaction` (slice 13c, D-67); **4** — `br_requirement_line`,
  `br_data_field` and `br_system_flow` join (slice 11, S11-1). `CURRENT_HASH_SPEC` is the highest built. `digest` and `verify` skip entities unknown at a baseline's version, so every older baseline
  still verifies byte for byte.
- **Canonical text is PostgreSQL's `::text` of the stored type** (booleans `true`/`false`, `numeric` with its
  stored scale, text as stored). Each value is **length-prefixed**, values are separated by `\x1f`, and NULL is the
  sentinel `\x1e`, so `("Approve", NULL, "Claim")`, `("Approve", "", "Claim")` and a value containing the
  separator all hash differently. Literal-hash tests pin these forms.
- **Position is excluded** (D-10): `hier_code`, `seq_no`, `parent_*_id` and `level_no` on `bfc_node` and
  `org_unit`, `seq_no` on `data_field`. Position changes report as MOVED, never CHANGED.
- **Codes, never labels** (R2-D3). The hash reads `<p>_code`; a `code_master` relabel changes only `<p>_label` in
  the next snapshot. `*_code_id` columns are never hashed (an override row's id is not scope).
- **Workflow is excluded** (S8-1 Q-13): BR `status_code`, FR `fulfilment_status_code` and
  `effort_rate.change_rationale` are snapshotted and shown, not hashed. `project_id` is never hashed.
- **FK ids are hashed.** They are source ids, stable across baselines: renaming org unit 12 shows as org unit 12
  CHANGED, not every process it performs.
- **The digest** (`baseline.content_digest`) is sha256 over every entity's ordered `source_id:content_hash` list,
  frozen with the header and recorded again in the append-only `BASELINE_FROZEN` audit row (DR8-S1).

---

### 7.8 `services/access.py` → `visible_project_ids(user)`, `require_project(user, project_id, min_level, component)`

The single visibility guard (§9.10, §9.11). Every list and detail query in the app passes
through it; nothing else decides who can see a project.

**The access model (D-40, D-62, OR-5, OR-6).** Three kinds of FTC user, and one optional wall per project:

- **Admin:** `app_user.is_platform_admin = true`. Sees every project, restricted or not, plus the admin
  functions (users, clients, projects, programs, members, restriction, components, global codes). Admins are
  the only holders of level `ADMIN`. The FTC default rate card stays a fixed default in code (SC-10).
- **User:** `app_user.user_kind = 'USER'`. Reads and edits, no admin functions.
- **Viewer:** `app_user.user_kind = 'VIEWER'`. Reads only; no edit controls, and every write is refused by
  the server. `ck_app_user_kind CHECK (user_kind IN ('USER', 'VIEWER'))`; the column default is the least
  privilege (`VIEWER`), and `create_user` requires the kind explicitly.

Both columns are read from the row on every request (S4), never from the token. `is_platform_admin`
overrides `user_kind`, which applies again if the flag is removed.

**Which projects a non-admin sees.** A project is either **open to all staff** (`project.is_restricted =
false`) or **assigned consultants only** (`is_restricted = true`, OR-6). **New projects are created
restricted** (D-62): the new-project form preselects "Assigned consultants only" and the API requires the
choice explicitly (§7.10). On a restricted project a USER or VIEWER sees it only as a live
**`project_member`** (`access_level` ∈ `EDIT` / `VIEW`); an admin may open a project to all staff by
clearing the flag. A project you cannot see is **404, never 403** (OR-6). Programs are roll-up groupings,
not access scopes (D-40).

Levels, ranked: **`VIEW` < `EDIT` < `ADMIN`**. A user's level on a project:

| Who | Open project | Restricted project |
|---|---|---|
| Admin | `ADMIN` | `ADMIN` |
| USER | `EDIT` | live member → lower of `EDIT` and the member's `access_level`; else **404** |
| VIEWER | `VIEW` | live member → `VIEW` (a VIEWER added at EDIT still reads only; the add route warns); else **404** |

`user_access_grant` (D-9, D-32) is **retired**: its rows are soft-revoked history, `vb_app` holds SELECT
only, and the `PROJECT_ROLE` category (OWNER / EDITOR / REVIEWER) is retired. Nothing reads it for access.

```python
LEVEL_RANK = {"VIEW": 1, "EDIT": 2, "ADMIN": 3}
KIND_CAP   = {"USER": "EDIT", "VIEWER": "VIEW"}        # + CLIENT_VIEWER: VIEW with D-43 (below)

@dataclass(frozen=True)
class EffectiveAccess:
    level: str            # VIEW / EDIT / ADMIN
    via: str              # PLATFORM_ADMIN / STAFF / MEMBER
    member: ProjectMember | None
```

| Operation | Level |
|---|---|
| Read anything in the project; download / export | `VIEW` |
| Create / edit / retire / restore / reorder BFC, DE, BR, Solution, FR, Application, Issue, Stakeholder and every link | `EDIT` |
| Upload, validate and **commit** an import batch | `EDIT` |
| **Freeze a baseline**; record client approval (S8-1) | `EDIT` |
| Rate card (S6c-3), project code overrides, control-rule thresholds, project FR types | `EDIT` |
| Link a WBS line to a phase / solution | `EDIT` |
| Generate the offline viewer file (OR-9) | `EDIT`, never `VIEW` |
| Members, restriction, components, data model depth, the effective-access list | `ADMIN` |
| Users, user kind, admin rights, clients, projects, programs, move a project between programs, global codes | `ADMIN` (platform admin) |
| Program roll-ups | `VIEW`, over the program's projects the caller can see |

```
visible_project_ids(user) -> set[int] | None:             # None = ALL
    if user.is_platform_admin: return None
    open    = {p.project_id | p.is_active and not p.is_restricted}
    members = {m.project_id | m.app_user_id = user and m.is_active
                              and m.project.is_active and m.project.is_restricted}
    return open ∪ members
    # restriction and membership are read per request: restricting a project, or removing a
    # member, hides it on that user's next request, with no token to expire

require_project(user, project_id, min_level, component=None) -> EffectiveAccess:
    p = PROJECT(project_id)
    if user.is_platform_admin:
        if p is None: raise 404
        eff = EffectiveAccess("ADMIN", "PLATFORM_ADMIN", None)
    else:
        if p is None or not p.is_active: raise 404
        cap = KIND_CAP[user.user_kind]                    # an unknown kind raises: fails closed
        if p.is_restricted:
            m = live project_member(p, user)
            if m is None: raise 404                       # not 403 — a project you cannot see does not exist
            eff = EffectiveAccess(lower_of(cap, m.access_level), "MEMBER", m)
        else:
            eff = EffectiveAccess(cap, "STAFF", None)
    if LEVEL_RANK[eff.level] < LEVEL_RANK[min_level]: raise 403
    if component and LEVEL_RANK[min_level] >= LEVEL_RANK["EDIT"]:
        components.require_on(db, project_id, component)  # 409 COMPONENT_OFF (D-37)
    return eff
    # THE ORDER IS FIXED: 404 → 403 → 409. A project you cannot see never reveals which
    # components it uses.

visible_program_ids(user) -> set[int] | None:             # None = ALL
    if user.is_platform_admin: return None
    return {p.program_id | p in visible_project_ids(user) and p.program_id is not None}
    # a program whose every project is restricted from the caller is hidden

require_program(user, program_id, min_level):
    g = PROGRAM(program_id)
    if user.is_platform_admin:
        if g is None: raise 404
        return EffectiveAccess("ADMIN", "PLATFORM_ADMIN", None)
    if g is None or not g.is_active or program_id not in visible_program_ids(user): raise 404
    level = KIND_CAP[user.user_kind]
    if LEVEL_RANK[level] < LEVEL_RANK[min_level]: raise 403
    return EffectiveAccess(level, "STAFF", None)
```

**Component gating (D-37).** A component that is off for a project has its write routes refused with
**409 `COMPONENT_OFF`** (`X-VB-Error: COMPONENT_OFF`). The check is the `component` argument of
`require_project`, called from the route's one guard; there is no separate component guard kind, because a
second guard on a route would break "exactly one guard". **Only writes are gated** (`min_level ≥ EDIT`):
an off component has no live rows (OR-1), and the UI hides it. **Admins are gated too** — the rule is
about the project's scope, not the person; an admin who needs to write switches the component on, which
is audited. `components.require_on` locks the project's component rows `FOR SHARE`, so a write and a
switch-off serialise. Where the component depends on the row, the guard takes a **resolver**
(`node_dfd_component(node)`: `TO_BE_DFD` or `AS_IS` by the node's set). Where it depends on the body (a
node created in a named set, an import target), the service calls `components.require_on` itself.

**Client viewer (D-43) — designed, built with the D-43 slice.** A client login is a `user_kind =
'CLIENT_VIEWER'` bound to exactly one project through the scalar `app_user.client_project_id`, so "one
project only" holds by construction: `require_project`'s client branch reads only that column (and the
project's recorded client consent) and returns before the staff branch; anything else is 404. No
membership, program or flag can widen it, and `require_program` is always 404 for a client viewer. This is
the one place the project wall survives regardless of restriction.

**Structure, not a promise (findings S2, S3).** A missing check returns a *successful* response, which
nobody reports as a bug. So omission is made impossible rather than discouraged:

```python
# THE GUARD REGISTRY (R2-S1), routers/guards.py. Every route declares EXACTLY ONE guard,
# as data on the route. GuardedRouter refuses a route without one at import time, and
# criterion 49 re-proves it over the running app.
class Guard(str, Enum):
    PUBLIC          # no JWT — POST /auth/login and first-run setup only
    AUTHENTICATED   # JWT only; the service filters (GET /projects, /programs, /auth/me, schema)
    PLATFORM_ADMIN  # current_user().is_platform_admin, re-read per request (S4)
    PROJECT_CTX     # /…/{project_id}/…  → require_project(user, project_id, min_level, component)
    OBJECT_GUARD    # /<things>/{id}/…   → resolve the owning project, then require_project
    PROGRAM_CTX     # /programs/{program_id}/… → require_program(user, program_id, min_level)

@dataclass(frozen=True)
class GuardSpec:
    kind: Guard; dep: Callable; min_level: str | None; model: type | None
    component: str | tuple | Callable[[obj], ...] | None      # D-37 — writes only
    route -> {"dependencies": [Depends(dep)],
              "openapi_extra": {"x-vb-guard": {kind, min_level, model, component}}}
    # every built guard dependency is registered by identity, so criterion 49 can prove the
    # declared kind is backed by a real attached dependency, not a copied marker

class GuardedRouter(APIRouter):                       # the only router type the app uses
    def add_api_route(self, path, endpoint, **kw):
        if "x-vb-guard" not in (kw.get("openapi_extra") or {}):
            raise RouteDefinitionError(f"{methods} {prefix}{path} declares no guard")
        super().add_api_route(path, endpoint, **kw)

# usage:  g = project_ctx("VIEW");  @router.get("/{project_id}", **g.route)

def project_ctx(min_level, component=None):
    dep(project_id, user=Depends(current_user), db=Depends(get_db)):
        return access.require_project(db, user, project_id, min_level, component)

def object_guard(model, min_level, id_param="id", component=None):
    # For routes that carry an object id and NO project (finding S3). The owning project is
    # resolved from the object BEFORE anything is returned. `model` must implement
    # owning_project_id(); a model that cannot is refused at registration.
    dep(request, user, db):
        obj = db.get(model, int(raw id))      # a non-numeric or over-long id → 404 (no bigint overflow)
        if obj is None: raise 404
        owner = obj.owning_project_id()
        if owner is None:                     # an object owned by no project
            if not user.is_platform_admin: raise 404
        else:
            comp = component(obj) if callable(component) else component
            access.require_project(db, user, owner, min_level, comp)   # 404 → 403 → 409
        return obj

def program_ctx(min_level):
    dep(program_id, user, db): return access.require_program(db, user, program_id, min_level)
```

A baseline diff is a project-scoped route, `GET /projects/{project_id}/baselines/diff?from=…&to=…`
(S8-1): both sides are resolved inside that project and the project is guarded, so two surrogate ids can
never read another client's scope report (§7.7).

**Acceptance criterion 49 is the test that keeps this true** (`tests/test_route_guards.py`). It walks
the running app's routes, not a list in this document, and fails on any route that declares no guard, or
whose declared guard is not the dependency actually attached. It also fails when a guard does not fit
the path: a `{project_id}` route that is not `PROJECT_CTX` (bar a named admin exception), a
`{program_id}` route that is not `PROGRAM_CTX` or `PLATFORM_ADMIN`, an object-id route whose guard is not
`OBJECT_GUARD`, `PROGRAM_CTX` or `PLATFORM_ADMIN`, a context guard with no minimum level, a **write
guarded at `VIEW`**, or `PUBLIC` anywhere but login and first-run setup. **Criterion 49b** fails any write
of a component route family (`ROUTE_COMPONENTS` in the test) that does not declare its component, or a
node-scoped DFD write that does not declare the resolver. A list that must be remembered is a list that
will be forgotten (R2-S1). `tests/test_access.py::test_no_get_route_leaks_a_restricted_project` calls
every GET route as a non-member of a restricted project, so a new route that bypasses
`visible_project_ids` fails. §6.4 makes these tests the stated price of deferring row-level security.

**Presentation.** `GET /projects/{project_id}` returns `my_access_level` (computed by `require_project`)
and the project's components; `/auth/me` returns `{is_platform_admin, user_kind}`. The browser hides edit
controls through `useCanEdit` and components through `useComponents`. Presentation only: the guards still
refuse.

### 7.9 `services/reports.py` — the read-only deliverables

These are the outputs FTC actually hands a client. They are queries, not workflows. Every report reads
the **to-be** set unless it says otherwise: BRs, solutions and FRs exist only there (S7-2, D-47).

```
coverage(project_id):                          # the scope-gap list
    return {
      "process_nodes_without_br": to-be process nodes with no active BR,          # S7-2
      "br_without_output_de":  BRs with no BR_DATA_ENTITY row where direction = 'O',
      "br_without_solution":   BRs with no BR_SOLUTION row,
      "br_without_fr":         BRs with no live BR_FUNCTION_REQUIREMENT link     # information (D-52)
      "fr_without_br":         FRs with no live BR_FUNCTION_REQUIREMENT link     # warning (D-28)
      "fr_without_solution":   FRs whose solution tag is NULL                    # information (D-52)
      "fr_solution_outside_its_brs": FRs tagged to a solution that answers none of
                               the FR's linked BRs                                # warning (S10b-1)
      "solution_reach_without_link": FR tagged S, S answers BR-B, FR not linked to
                               BR-B                                               # information: a suggestion
      "br_without_accountable": BRs with no BR_ORG_ROLE row whose RACI behaviour is
                                ACCOUNTABLE,                          # R2-D9 — not the letter
      "de_never_referenced":   DEs absent from both BR_DATA_ENTITY and BFC_NODE_DATA_ENTITY,
      "solution_without_br":   solutions answering nothing,
      "tech_solution_no_fr":   TECHNOLOGY solutions tagged on no FUNCTION_REQUIREMENT,
      "solution_no_application": TECHNOLOGY solutions with no APPLICATION_SOLUTION,
    }
    # a REJECTED solution may be linked, and is never counted as an answer (S5-2)

entity_model_validation(project_id):
    return {
      "de_without_pk":   DEs with no DATA_FIELD where is_primary_key,
      "fk_to_pkless_de": FK fields whose ref_data_entity_id has no PK field,
      "pk_ordinal_gaps": DEs whose pk_ordinal values are not 1..n contiguous,
    }
    # data model depth (D-39): under KEYS_ONLY an entity with keys and no other attributes is
    # expected and not reported; under FULL it is a warning

traceability(project_id):                      # the vendor-facing scope list
    BFC_NODE(is_process, to-be) ⋈ BUSINESS_REQUIREMENT ⋈ BR_FUNCTION_REQUIREMENT
                 ⋈ FUNCTION_REQUIREMENT ⟕ SOLUTION (the FR's tag) ⟕ APPLICATION_SOLUTION ⋈ APPLICATION
    order by hier_code, br_number; group by FR type
    → FORM / BATCH / INTERFACE / REPORT, each with its originating BRs, process steps,
      solution tag (blank allowed; flagged when the tag does not answer that BR) and target
      application; untraced FRs (no BR link) in their own group at the end (D-28, D-52)

solution_matrix(project_id):                   # D-7 — is the transformation balanced?
    SOLUTION ⋈ BR_SOLUTION ⋈ BUSINESS_REQUIREMENT ⋈ BFC_NODE
    pivot: solution category (ORG_AND_RULES|PEOPLE|PROCESS|DATA|TECHNOLOGY)
           × BFC L1 area, counting solutions and the BRs they answer
    → the question this report exists to ask: five technology answers and no org change
      is a finding

application_gap(project_id):                   # D-8 — the migration backlog
    as_is  = APPLICATION_BFC_NODE (as-is processes) ⋈ APPLICATION where lifecycle in (AS_IS, BOTH)
    to_be  = BFC_NODE(is_process, to-be) ⋈ BUSINESS_REQUIREMENT ⋈ BR_SOLUTION
                          ⋈ APPLICATION_SOLUTION ⋈ APPLICATION
    return {
      "unallocated": process steps in as_is with no row in to_be,     # nothing replaces it
      "unsupported": process steps in to_be with no row in as_is,     # net-new capability
      "retiring":    AS_IS applications with no to-be allocation anywhere,
      "as_is_support_by_to_be": as-is support links naming a TO_BE application — informational,
                     never counted as today's support (S6b-5)
    }
    # The two charts have their own node ids and no provenance (D-47), so as-is and to-be are matched by
    # AREA — an L1 / L2 area whose chart code and normalised name agree, as volume_summary (Q-28, SC-5).
    # "unallocated" / "unsupported" are per matched area; unmatched areas are listed apart with their reason.
    # A process-to-process link is a later, separate design.

issue_dashboard(project_id):
    ISSUE ⋈ ISSUE_BR ⋈ BUSINESS_REQUIREMENT ⋈ BFC_NODE
    → counts by (severity × status), and open issues rolled up to the L1 ancestor
      via the hier_code prefix
```
```
# ---- the analyses that need no new entities (D-19's inputs) ----------------
requirement_volatility(project_id):            # the earliest warning the app produces
    for each consecutive baseline pair (v_n, v_n+1):
        d = diff(v_n, v_n+1).business_requirement
        group ADDED|CHANGED|REMOVED by the L1 ancestor of each BR's bfc_node
    → churn rate per L1 area per generation; headline = max areas churning 2+ in a row

process_change_intensity(project_id):
    BFC_NODE(is_process, to-be) ⋈ BUSINESS_REQUIREMENT ⋈ BR_SOLUTION ⋈ SOLUTION
    count process steps carrying a solution, rolled to L1, weighted by solution category

org_impact_heatmap(project_id):
    ORG_UNIT ⋈ ORG_ROLE ⋈ (BR_ORG_ROLE on to-be BRs ∪ BFC_NODE_ORG_ROLE on as-is steps)
             ⋈ BR_SOLUTION
    # one RACI per process: to-be roles live on the BR, as-is roles on the step (D-64, S10d-1)
    → change absorbed per org unit; headline = the top decile

stakeholder_engagement(project_id):
    STAKEHOLDER ⋈ ORG_UNIT, LEFT JOIN ISSUE on raised_by_stakeholder_id
    → issues raised per stakeholder and per org unit.
      Headline = org units with high impact and ZERO issues raised. Silence is the signal.

interface_load(project_id):
    v_interface_list grouped by (source_application_id, target_application_id)   # D-27
    # the endpoint is a stated fact on FR_INTERFACE, not inferred via APPLICATION_SOLUTION
    → headline = INTERFACE FRs as a share of all FRs

data_migration_map(project_id):
    source = DATA_ENTITY ⋈ BFC_NODE_DATA_ENTITY (as-is processes) ⋈ APPLICATION_BFC_NODE
             ⋈ APPLICATION(AS_IS)
    target = DATA_ENTITY ⋈ BR_DATA_ENTITY ⋈ BR_SOLUTION ⋈ APPLICATION_SOLUTION ⋈ APPLICATION
    → source → target per entity; headline = entities with no source, or with >1 source

master_data_candidates(project_id):
    BR_DATA_ENTITY ⋈ BUSINESS_REQUIREMENT ⋈ BFC_NODE
    → data entities referenced from BRs under 3+ distinct L1 ancestors

effort_summary(project_id):                    # D-13
    FUNCTION_REQUIREMENT.effort_days grouped by FR type, solution tag (Unassigned when the
    tag is NULL), phase, L1 area
    + "untraced": live FRs with no live BR link — count and days (information, D-52)
    + FRs tagged to a REJECTED solution, shown apart (S6c-8)
    + per rate-card cell: the count and Σ days of FRs not at the current rate (S6c-5)
    # Never an additive "effort by BR": an FR serving three BRs would count three times. If
    # shown at all it is labelled "effort touching this BR" and never summed.
```
The L1-area grouping is built with the reports slice (S6c-4, SC-11).

Each of these has a `headline_value`, which is what `control_panel` (§7.13) compares against
its `CONTROL_RULE`. **That contract is why every analysis returns one number as well as a
table** — a report without a headline cannot be governed.

The `design-spec` §4 grid itself is a further report —
`BUSINESS_REQUIREMENT ⋈ BR_DATA_ENTITY ⋈ DATA_ENTITY ⋈ BFC_NODE`, one query, pivotable in
SQL (§5.6).

### 7.10 `services/auth.py`, `user_admin.py`, `project.py`

```
login(email, password, remember_me):
    user = APP_USER where lower(email) = lower(:email)
    ok = verify(password, user.password_hash if user else DUMMY_HASH)
        # a real bcrypt check runs for an unknown email too, so timing reveals no accounts
    if user is None or not user.is_active or not ok:
        AUDIT_EVENT(event_type='LOGIN_FAILED', detail={email})
        raise 401 "Incorrect email or password"    # same message either way — never
                                                   # distinguish "no such user" from
                                                   # "wrong password"
    user.last_login_at = now()
    AUDIT_EVENT(event_type='LOGIN_OK', app_user_id=user.id)
    return jwt(sub=user.id, exp=now() + (30 days if remember_me else 1 day))   # A-34, §14.5
    # finding S4: the token carries the SUBJECT ONLY. It carries no is_platform_admin, kind
    # or level, because a claim baked into a token cannot be revoked.

current_user(token):                               # the per-request dependency
    claims = verify_jwt(token)                     # signature + exp
    user = db.get(APP_USER, claims.sub)            # finding S4 — re-read, every request
    if user is None or not user.is_active: raise 401
    return user        # is_platform_admin and user_kind are read from the row, never the token
    # Deactivating a departing consultant takes effect on their very next request.

first_run_setup(email, display_name, password):    # PUBLIC; only when enabled and no user exists
    advisory lock; if any APP_USER exists: raise 409
    insert APP_USER(is_platform_admin=True, user_kind='USER')   # an admin falls back to USER
    AUDIT_EVENT('FIRST_ADMIN_CREATED')
    # switched off in every cloud environment (404)

create_user(actor, email, display_name, initial_password, user_kind):   # platform admin
    if not is_ftc_address(email):                  # D-11, finding S8
        raise 422 "Value Bridge accounts are FTC staff only. Client-side people are "
                  "recorded as stakeholders."
    require len(initial_password) >= 10
    require user_kind in (USER, VIEWER)            # required: no API default (D-40)
    insert APP_USER(password_hash=hash(initial_password), user_kind, is_platform_admin=False, ...)
    AUDIT_EVENT(event_type='USER_CREATED', detail={email, user_kind})
    # plaintext is never persisted, never logged, never in a response model.
    # Admin rights are never a checkbox on creation — see set_platform_admin.

set_user_kind(actor, user_id, user_kind, row_version):          # platform admin
    UPDATE ... WHERE row_version = :v                             # 409 on stale
    AUDIT_EVENT('USER_KIND_CHANGED', detail={from, to})           # effective on the next request

set_platform_admin(actor, user_id, value, rationale, row_version, user_kind=None):  # platform admin
    refuse on oneself (422); refuse a no-op (409); require rationale (422)
    if removing: require user_kind — the kind the user falls back to, so a demoted admin
                 never silently becomes an editor everywhere
    AUDIT_EVENT('PLATFORM_ADMIN_GRANTED' | 'PLATFORM_ADMIN_REMOVED', detail={rationale, ...})

deactivate_user(actor, target_user_id):                          # platform admin
    refuse on oneself (422)
    soft-delete the user (is_active, deleted_at, deleted_by)
    AUDIT_EVENT(event_type='USER_DEACTIVATED', detail={target_user_id})
    # takes effect on the target's very next request — see current_user above

create_project(actor, client_id, project_code, project_name, program_id, start, end,
               component_codes, is_restricted, template_code=None, data_model_depth='FULL'):
    # platform admin only (route guard)
    require an active client; if program_id: an active program of the SAME client
        else 422 "A program's projects belong to its client"
    is_restricted is REQUIRED in the body (§8.10 risk 1); the form preselects TRUE (D-62)
    component_codes must be closed under COMPONENT_REQUIRES, else 422 naming the missing
        dependency — the server never adds a component silently (D-37, OR-2);
        template_code is provenance only (OR-3)
    project = insert PROJECT(..., program_id, data_model_depth, is_restricted)
    # Creating a project grants nobody anything (D-32). A restricted project starts with no
    # members; the admin lands on its Access screen to add them.
    in the same transaction:
        seed PROJECT_SEQUENCE rows for all ten series:              # R2-D14
            DE, BR, FR, ISSUE, SOL, BEN, RSK, CR, DEC, EXT
        seed EFFORT_RATE from the FTC default card (S6c-1)
        insert PROJECT_COMPONENT rows (D-37)
        insert PROJECT_DFD_RULE rows per chart from dfd_rule.RECOMMENDED (D-70)
            (to-be: STARTED, DATA_IN, DATA_OUT, ORDER; as-is: STARTED); the FTE basis takes its 240 × 8 defaults
        copy CONTROL_RULE house defaults (§7.13)
    AUDIT_EVENT(event_type='PROJECT_CREATED', project_id=project.id,
                detail={program_id, template_code, components, data_model_depth, is_restricted})

# ---- members and restriction (OR-6, D-62) — ADMIN level ---------------------------------
add_member(actor, project, user_id, access_level, member_note):   # EDIT | VIEW
    lock the project row FOR SHARE                     # serialises with a restriction confirm
    require an active user; a platform admin needs no membership (422)
    if a live membership exists: raise 409
    insert PROJECT_MEMBER(...)                         # partial UK (project, user) WHERE is_active
    AUDIT_EVENT('MEMBER_ADDED', detail={user_id, access_level})
    warn VIEWER_CAPPED when a VIEWER is added at EDIT  # their effective level is VIEW
    # Membership on an open project is allowed and has no effect until it is restricted, so
    # the list can be prepared first. Re-adding inserts a new row: each membership period is
    # its own row, never a restore.

change_member_level(actor, member, access_level, row_version):
    AUDIT_EVENT('MEMBER_LEVEL_CHANGED', detail={user_id, from, to})

remove_member(actor, member, row_version):            # soft-remove (law 1)
    AUDIT_EVENT('MEMBER_REMOVED', detail={user_id})
    # Never restorable (R2-S5). Access returns only through add_member, which re-checks
    # everything and writes its own audit row.

set_restriction(actor, project, restricted, confirm_hash=None):   # PUT /projects/{id}/restriction
    preview = {restricted, changed,
               loses: staff with no live membership (when restricting),
               gains: the same set (when opening),
               keeps: each live member with level, effective level and note}
    # the preview flags kept members whose effective level is lower than their kind allows
    if confirm_hash is None: return {preview, confirm_hash: sha256(preview)}   # writes nothing
    lock the project row; recompute; a different hash → 409 "Who can see this project changed
        since the preview. Review it again."
    UPDATE project SET is_restricted = :restricted
    AUDIT_EVENT('PROJECT_RESTRICTED' | 'PROJECT_UNRESTRICTED',
                detail={members: [...], loses: [...], gains: [...]})
    # Every live open project is switched by an admin, one by one, on its Access screen after its
    # team is checked — never by a migration or a script (D-62, S10c-2); the inventory of projects,
    # members and levels is kept with the slice 10c spec until none is left open.

effective_access(project):                             # GET /projects/{id}/access, ADMIN
    admins  = every active platform admin
    members = every live membership of an active user, with its effective level
    if project.is_restricted: return {admins, members}
    return {admins, members (listed as "applies when restricted"),
            staff: counts of active non-admin users by kind}
    # "Who can read this client's data?" answered in full. The access review at each freeze
    # (§4.7) reads this list.
```

### 7.10a `services/program.py` (D-32, D-40)

A program is a header and a set of reads: a client-scoped **roll-up grouping, not an access scope**.
**It owns no business data**, so it has no SQL of its own over business tables.

```
create_program(actor, client_id, program_code, program_name, description):   # platform admin
    require an active client
    insert PROGRAM(...); AUDIT_EVENT('PROGRAM_CREATED')

program_projects(user, program_id):
    return PROJECT where program_id = :program_id and is_active
                     and project_id ∈ visible_project_ids(user)              # R2-S2

move_project_program(actor, project_id, target_program_id | None, confirm_hash=None):
    # platform admin only (Q10)
    p = PROJECT(project_id); t = PROGRAM(target_program_id) if target_program_id else None
    if t is not an active program: raise 422
    if t and t.client_id != p.client_id: raise 422 "A program's projects belong to its client"
    if p is already there: raise 422
    preview = {project: p.project_code, from_program_id, to_program_id, gains: [], loses: []}
    h = sha256(canonical(preview))
    if confirm_hash is None: return {preview, preview_hash: h}        # step 1 — writes nothing
    if confirm_hash != h: raise 409 "The project's program changed since the preview"
    UPDATE project SET program_id = :t
    AUDIT_EVENT('PROJECT_PROGRAM_CHANGED', project_id, detail=preview)
    # R2-S3. A move changes roll-ups, not access (D-40), so gains and loses are always empty;
    # the two steps stay so the admin sees exactly which roll-up the project leaves and joins.

ROLLUPS = {                         # program report → the per-project report it is made of
  'counts':         lambda u, pid: {br: reports.count(u, pid, 'BR'), fr: …, issue_open: …},
  'interfaces':     reports.interface_list,
  'effort':         reports.effort_summary,
  'control_status': control.control_panel,
  'plan_vs_actual': wbs.plan_vs_actual,          # projects with no WBS return "not imported"
}

rollup(user, program_id, report):
    access.require_program(user, program_id, VIEW)
    return [ {project_id, project_code, result: ROLLUPS[report](user, p.project_id)}
             for p in program_projects(user, program_id) ]
    # R2-S2 — EVERY per-project call runs its own require_project, exactly as the screen
    # would. There is no query here with `project_id IN (...)`, and code review rejects
    # one: a cross-project SQL path is a second visibility rule, and the one-guard design
    # (§7.8) exists so there is only one. A restricted project the caller is not on is
    # omitted silently — no "1 hidden" count, which would leak it.

program_dashboard(user, program_id):
    return {report: rollup(user, program_id, report) for report in ROLLUPS}
```
Output data: a program header, audited moves, and roll-ups that are lists of per-project
results. **Nothing is stored at program level**, so there is nothing to baseline. Baselines
stay per project (A-56).

### 7.11 `services/bulk.py` — upload / download (D-5)

**The one import pipeline** (VB law 8): template · export · validate · preview · commit, for every
target. A target is a `Target` in `TARGETS`: a column map plus `validate(ctx, rows)` (sets each row's
verdict and errors) and `apply(ctx, rows)` (writes through the services' no-commit forms), and the
component it needs (`Target.component`, checked by `validate` and `commit`, D-37). Targets: **Data
Entity, Data Field** (built), **Issue, Business Requirement, Function Requirement** (D-28), **WBS**
(D-33) and the **process-flow JSON** (§7.2b). `import_mode` (merge / replace) is accepted for **WBS and
the flow JSON only**; any other target with a mode is a 422. A workbook may carry an entities sheet and a
fields sheet; each sheet is its own batch for one target, run in sequence, entities first (S4-12).

**Row identity: the signed row token** (S4-11). Every exported row carries a protected **row token**:
readable claims — project, table, id, `row_version` — plus an HMAC-SHA256 over them under
`ROW_TOKEN_KEY` (never the JWT secret). The MAC is checked first, then each claim, so a stale row, a row
from another project and a row moved against its token each get their own error. A token row that no
longer resolves to its live row is **an error, never an INSERT**: renames and moves are done on screen,
not by spreadsheet. The field key is `DE-nnnn/<field name>`, normalised as the live-name index does,
`lower(btrim(name))`.

**Messages** are objects `{code, column, message, params}` (S4-8), rendered by the screen through
`t('import.msg.<code>', params)`; every string in them is untrusted text.

```
template(entity):
    build .xlsx from COLUMN_MAP[entity]
    attach data validation lists from code_master.resolve for every coded column
    → the returning file is already half-clean

export(project_id, entity):                                # VIEW
    rows = live rows
    emit template shape INCLUDING the business key (ISS-0001 / DE-0001) and the row token,
    as a protected column (finding D2) — the key makes a round-trip an update instead of a
    duplicate; the token stops it silently reverting a colleague's edit (D-6)
    every cell written through escape_cell()               # finding S5 — see §7.12
    the download gets a server-generated file name

validate(project_id, entity, file):                        # EDIT
    components.require_on(project_id, target.component)
    file-level checks first — the one tagged sheet, every mapped column present (a missing
        column is refused; a blank cell clears), the caps (§7.12), a token from another
        project → 422 with NOTHING staged
    batch = INSERT IMPORT_BATCH(target_entity=entity, status='VALIDATING',
                                file_name=sanitised basename ≤ 255, uploaded_by_user_id=jwt.user_id)
    duplicate keys in the file are caught in memory: later copies are staged with the key
        NULL and a DUPLICATE_KEY error (S4-4)
    for sheet_row_no, raw in parse_streaming(file):
        errors, warnings = [], []
        clean every text cell (Unicode whitespace and invisible edge characters)
        check required columns present and typed
        check every date column is ISO YYYY-MM-DD           # finding D10
        check every coded value resolves via code_master.resolve(project_id, category)
        check the business key, if present, exists in THIS project      # never another's
        check the row token: genuine, this project, this table, this row, current
            row_version — a stale row is a PER-ROW error with the current value shown (D2)
        verdict = INSERT (no key) | UPDATE | MATCH (every compared value unchanged — never written)
        for ISSUE: raised_by name must match exactly ONE active STAKEHOLDER,
                   else ERROR — the consultant picks or creates one in the preview.
                   NEVER auto-create a person from a spreadsheet cell.   # finding D6
        for DATA_FIELD: parent DE named by de_number or, when blank, by entity name; both
                   given must agree; the parent must be live; FK target DE in this project
                   (or named by ref_de_name); fields in one file may reference each other
        for BUSINESS_REQUIREMENT:                                      # R2-D1, S7-2
                   br_number is REQUIRED and must be an active BR in this project —
                   every BR already exists with its to-be process node (D-2), so a blank
                   br_number is an ERROR ("BRs are created with their step — use the
                   flow import to add steps"). An import never creates a BFC node or a BR.
                   hier_code, if present, is a CROSS-CHECK only: if it differs from the
                   BR's node's current hier_code →
                       errors += [f"{br_number} moved since export: now {node.hier_code}, "
                                  f"file says {hier_code}. Re-export"]
        for FUNCTION_REQUIREMENT:                                      # R2-D6, D-28, D-52
                   fr_type must resolve in FR_TYPE
                   BR- numbers optional → each creates a BR_FUNCTION_REQUIREMENT link at commit
                       (D-52); none → warnings += ["No BR: this FR will not trace"] (D-28)
                   SOL- number optional → the FR's solution tag; an import never creates a
                       SOLUTION
                   effort_days is EXPORT-ONLY: ignored on import; if the cell differs from
                       the stored value → warnings += ["effort_days is derived from the
                       rate card; your value was ignored"]
                   if complexity is set (new row, or changed) or fr_type changed:
                       rate = EFFORT_RATE(project, new type, new complexity)
                       if complexity and rate is None:
                           errors += [f"No rate-card cell for {type} × {complexity}"]
                   if fr_type changed and behaviour(old) == 'INTERFACE'
                      and behaviour(new) != 'INTERFACE' and FR_INTERFACE active:
                       errors += ["This FR has interface detail. Remove it first, or keep "
                                  "an interface type"]
                   # the same refusals rate_function_requirement and change_fr_type make —
                   # surfaced per row HERE, not as a whole-batch abort at commit
                   interface columns (source app, target app, method, frequency)
                   read only when the type's behaviour is INTERFACE
        for WBS: see §7.11a
        warnings never set is_valid = false            # D-28 — inform, do not block
        INSERT IMPORT_ROW(batch, sheet_row_no, business_key, payload=raw,
                          verdict, is_valid=not errors, error_detail=errors,
                          warning_detail=warnings)
    batch.status = 'VALIDATED'                         # even with errors (S4-7)
    batch.row_count, error_count, warning_count       # rows, not messages
    batch.insert_count, update_count                  # valid rows only; MATCH not counted
    return batch summary + the per-row errors, keyed by SHEET row number
    # nothing has touched a business table yet; no number is minted

preview(batch_id):                                  # finding P3 — what the human approves
    access.require_project(user, batch.project_id, VIEW)
    return {
      "summary": {insert_count, update_count, match_count, error_count,
                  stakeholders_to_create: […]},     # named, not counted
      "rows": [ {sheet_row_no, verdict, business_key, errors, warnings,
                 changes: [ {column, before, after, cleared} ]   # computed NOW, never stored
                } ],
      "purged": batch.rows_purged_at is not None,   # a purged batch says "detail purged",
    }                                               # never an empty list

commit(batch_id, row_version, acknowledged_inserts, acknowledged_retires):   # EDIT
    batch = SELECT … FROM import_batch WHERE id = :id FOR UPDATE    # finding P2
    if batch.status != 'VALIDATED':       raise 409     # re-checked INSIDE the lock
    if batch.row_version != row_version:  raise 409     # a stale preview
    if batch.error_count > 0:             raise 422 "Fix N rows and upload the file again"
    components.require_on(project_id, target.component)
    revalidate every row                    # finding D1 — FULL re-validation here, under lock
    a row whose verdict or resolved reference changed since validate → error
        # Verdicts were computed at validate time, possibly days earlier, because the
        # design deliberately puts a human between the two calls.
    any fresh error → the batch is REJECTED (follow-up transaction, the fresh errors written
        onto their rows), nothing applied, 422
    if inserts > 0 and acknowledged_inserts != inserts:
        raise 422 f"This will CREATE {inserts} new rows. Confirm the count."
        # finding D3, R2-P2 — required whenever there are inserts, not only when inserts
        # and updates are mixed: an all-insert batch is exactly the shape of a file whose
        # key column was cleared on every row.
    if retires > 0 and acknowledged_retires != retires:
        raise 422 f"This will RETIRE {retires} rows. Confirm the count."
        # replace mode — WBS (§7.11a) and the flow JSON (§7.2b)
    with one transaction:                                   # all-or-nothing
        apply every row in sheet order through the services' no-commit forms
            INSERT → create(...)            # number minted HERE, at commit (§9.8)
            UPDATE → update(..., WHERE row_version = token.row_version)   # D-6; 0 rows → abort
            # FR rows: fr_type and complexity go through function_requirement.change_fr_type /
            # effort.rate_function_requirement — never by writing the columns (R2-D6).
            # effort_days is never written from a file.
            UPDATE rows keep their before-values in payload.before (the 90-day window)
        row.committed_target_id = target.id
        batch.status = 'COMMITTED'; committed_at = now(); committed_by_user_id
        # Nothing may commit partway: a helper that tries raises.
    AUDIT_EVENT(event_type='IMPORT_COMMITTED', detail={entity, insert_count, update_count})
    # A rule failure marks the batch REJECTED. An operational failure (serialization,
    # deadlock, lock timeout, cancel) leaves it VALIDATED for a retry (503). Every failed
    # attempt writes IMPORT_COMMIT_FAILED. Any project editor may commit a batch another
    # uploaded (S4-12).
```

**The uploaded file's lifecycle** (R2-S8, Q14). The body is **size-checked at ingress before any handler
runs** (§7.12b) and held **in memory only**: the ingress layer buffers at most the route's cap and
nothing is spooled to disk. The `.xlsx` is **never stored**. It is parsed under the caps of §7.12 and
discarded when `validate` returns. Only `IMPORT_ROW.payload` persists, and it is **purged after 90 days**
(`purge_import_rows`, §7.12b). `IMPORT_BATCH.file_name` is a sanitised basename kept **for display
only**, never used to build a filesystem path or a `Content-Disposition` header, and overwritten with
`(purged)` at purge. Export downloads get a server-generated name. This removes file storage, file
permissions and filename handling from the attack surface entirely.

**Six properties that are not negotiable, because a bad import is worse than no import.**

1. **Validate and commit are separate calls.** The consultant sees a preview and approves.
   An upload never writes unattended — that is the `(manual)` row in §4.5a.
2. **All-or-nothing.** One invalid row rejects the batch. A half-applied spreadsheet is a
   data-integrity incident nobody notices for a week.
3. **Numbers are minted at commit, never at validate** (§9.8). A rejected batch must not
   burn `DE-0007`.
4. **Every row is project-scoped on the way in.** A business key or row token belonging to another
   project is an error, not a silent cross-project write. This is the one place where a file, not a
   query, is the attack surface (§6.4).
5. **Every verdict is re-computed inside the commit transaction** (finding D1). Validate-time
   results are advisory — they exist to build the preview. The world can change between
   validate and commit, and the design invites it to by putting a human in between.
6. **The consultant approves consequences, not contents** (findings P3, D3, R2-P2). The
   preview states per row whether it inserts, updates, matches or retires, shows before/after for
   every changed field, and names the stakeholders that would be created. **Any batch that
   creates rows requires an explicit acknowledgement of how many, and any batch that retires
   rows requires the same for retirements** — every batch, not only mixed ones.

### 7.11a `services/wbs.py` — WBS import (D-33, D-41)

**WBS is a project component** (`WBS`, D-37): a project with it off has no WBS, and the program
dashboard says "not imported" for it. Tasks come from MS Project; **progress is recorded in VB** (D-41).
Creating tasks, dependencies, Gantt editing and critical path are out of scope (§12.2).

```
COLUMN_MAP['wbs'] = [
    ms_unique_id  (required, integer — MS Project "Unique ID"; the KEY, R2-D15),
    wbs_code, name, outline_level,
    start, finish, actual_start, actual_finish,     # ISO dates (see template step)
    pct_complete  (0–100),
]   # NO phase / solution columns — those are set in VB (link_wbs_item) and never imported

template('wbs'):
    the §7.11 template, plus an INSTRUCTIONS sheet:
      1. In MS Project: File → Export → Excel, and ADD "Unique ID" to the export map —
         it is not in the default map, and without it every re-import is a fresh insert.
      2. In Excel: select every date column → Format Cells → Custom → yyyy-mm-dd → save.
         MS Project writes dates in the Windows locale, so 03/04/2027 is ambiguous (A-33).
    a date cell Excel itself typed as a date is accepted as is; a TEXT date must be ISO

validate(project_id, 'wbs', file, import_mode):       # merge | replace
    per row:
        ms_unique_id missing or not an integer → error
        ms_unique_id = 0 (MS Project's project-summary task) → row skipped, not staged
        ms_unique_id or wbs_code repeated in the file → error
        text date not YYYY-MM-DD → error (the template's step 2 was skipped)
        finish < start, pct_complete outside 0–100 → error
        existing = WBS_ITEM(project_id, ms_unique_id)
        verdict = 'UPDATE' if existing else 'INSERT'
        if existing and not existing.is_active: restore it (links intact, A-68); and if
            its task_name differs → warning "Unique ID reused for a different task?"
        # NO row-token check. MS Project is the system of record for every imported
        # column, and the VB-edited data (the links, the progress updates) is never in the
        # file, so an import cannot revert a colleague's edit.
    parent of each row = the nearest preceding row with outline_level one less
    if import_mode == 'replace':
        for every active WBS_ITEM whose ms_unique_id is not in the file:
            stage RETIRE                                    # counted, acknowledged at commit

commit: bulk.commit (§7.11) — both acknowledgements; parent links set after all rows exist;
        a RETIRE soft-deletes the line and KEEPS its phase / solution links on the row, so a
        line restored by a later import comes back linked

link_wbs_item(wbs_item_id, phase_id | None, solution_id | None, row_version):   # EDIT
    assert phase / solution in the item's project
    UPDATE wbs_item SET phase_id, solution_id WHERE ... row_version = :v            # 409 on 0
    # The imported columns are never edited in VB: PATCH with any of them → 422
    # "Change it in MS Project and re-import".

record_progress(wbs_item_id, pct_complete, actual_start, actual_finish, status, comment, as_of):  # EDIT
    insert a NEW dated progress-update row for the line           # D-41
    # status ∈ on track / at risk / late. Each update is its own row, so progress over time is
    # kept and never overwritten. A re-import never overwrites VB progress (OR-7).

plan_vs_actual(user, project_id):
    access.require_project(user, project_id, VIEW)
    per PHASE and SOLUTION (via link) and per top-level WBS line:
        planned_finish = max(finish), actual / forecast from the latest VB progress update,
        slip_days = actual_or_forecast − planned, pct_complete (duration-weighted),
        the latest comments
    imported actuals are kept beside VB progress, and lines where the two disagree are flagged (OR-7)
    "unlinked": lines with no phase, listed — never dropped
    headline_value = max slip_days across phases     # so a control rule can govern it
```
`record_progress` and its columns follow D-41; `apple` models the progress-update table when the WBS wave is
specced (SC-4).

**Not baselined** (D-33). The schedule is not agreed scope, and a re-plan is not a scope
change. Freezing it would put a re-plan in every diff.

### 7.12 Lifecycle, consistency, lookup and spreadsheet-safety services

```
# ---- soft delete and restore (services/lifecycle.py; findings P5, R2-D2, R2-S5) ----
DEPENDENTS[model] / PARENTS[model]
    # DERIVED FROM Base.metadata, never hand-kept: every FK between two tables that both
    # carry is_active — the FK_LIVENESS list of §5.4.15. Excluded as parents: APP_USER,
    # PROJECT, PROGRAM, CLIENT and CODE_MASTER (a code is retired through
    # code_master.maintain, R2-D8). Tables with no is_active — baseline_* (a frozen row never
    # blocks a live delete), AUDIT_EVENT, IMPORT_BATCH, IMPORT_ROW, DIAGRAM_LAYOUT (hard-
    # deleted, D-30) — never take part. Guard columns (is_active, is_process,
    # fr_type_behaviour, bfc_set_code) are ignored, so each FK yields one link. A nullable FK
    # is a parent only where it is set (FR.solution_id). tests/test_lifecycle.py proves
    # every FK is covered.

retire(entity, obj_id, row_version):                            # EVERY DELETE route
    obj = the object_guard-resolved row (EDIT)
    lock obj FOR UPDATE; 409 on a stale row_version; 409 if already retired
    blockers = [(child, active rows referencing obj) for child in DEPENDENTS[entity]]
    if blockers:
        raise 409 "Retire these first: " + "; ".join(
            f"{child.label}: {labels, first 10} (+{n - 10} more)" for …)
        # Q4. Deleting a DE with active BR CRUD, a solution with active FRs, an FR with live
        # BR links (S10b-2) or live interface detail (S6b-3) — each is REFUSED, with the
        # blockers named. NOTHING CASCADES. A cascade retires scope nobody chose to retire,
        # and the next priced diff reports it as a decision.
    UPDATE ... SET is_active = FALSE, deleted_at = now(), deleted_by = jwt.user_id
    AUDIT_EVENT(event_type='RECORD_DELETED', detail={label})

# The ONE exception: a process step retires with the rows that exist only because of it
# (S3-SR, docs/step_retire_spec.md), in one confirmed, undoable action —
# services/step_retire.py, the one owner of the owned set:
#   OWNED_BY_STEP = business_requirement, bfc_node_data_entity, bfc_node_org_role,
#                   bfc_node_external_flow, application_bfc_node (S6b-1), bfc_node_trigger
#   OWNED_BY_BR   = br_data_entity, br_org_role, br_solution (S5-1),
#                   br_function_requirement (D-52; the FR itself survives)
#   GET  /bfc-nodes/{id}/retire-preview          → {owned, blockers, confirm_hash}
#   POST /bfc-nodes/{id}/retire-with-dependents  {confirm_hash}  → one transaction, one
#        deleted_at, one STEP_RETIRED_WITH_DEPENDENTS event listing every row (the undo key)
#   POST /bfc-nodes/{id}/restore-with-dependents → restores the listed rows still carrying that
#        deleted_at; refuses as a whole while any other parent is inactive
# Any other active row referencing the step, its BR or an owned link blocks by default, so a
# new table pointing at a step blocks until it is added to the owned set. A summary node keeps
# refuse-with-dependents (422 on the with-dependents route).

RESTORABLE = {                 # THE ALLOW-LIST (R2-S5). One restore route per entry (§9).
    BfcNode, BusinessRequirement, DataEntity, DataField, ExternalEntity, OrgUnit, OrgRole,
    Solution, FunctionRequirement, Application, ProcessTrigger,
    Stakeholder, Issue, Benefit, Risk, ChangeRequest, Phase,     # as each is built
}
    # NOT restorable, by design:
    #   PROJECT_MEMBER — access returns only through add_member, which re-checks and audits
    #       it as an addition. USER_ACCESS_GRANT is retired history (SELECT-only).
    #   CONTROL_RULE — disabled via is_enabled, changed via maintain_control_rule (audited,
    #       with a rationale). A restore would move a threshold without a rationale.
    #   APP_USER — reactivation is user_admin, platform admin only.
    #   CODE_MASTER — maintained through code_master.maintain, with R2-D8's rule.
    #   PROGRAM, WBS_ITEM — admin-managed / import-managed.
    #   Junction rows — re-linking a removed link restores the same row through its link
    #       service (S1-7); there is no restore route.

restore(entity, obj_id):
    if entity not in RESTORABLE: raise 404                     # the route does not exist
    obj = the object_guard-resolved row (EDIT)
    if obj.is_active: raise 409 "is not retired"
    the row's component(s) must be on (DR7-P2)                 # 409 COMPONENT_OFF
    for parent_model, fk in PARENTS[entity]:                   # each parent locked FOR SHARE
        parent = the row obj references through fk
        if parent is not None and not parent.is_active:
            raise 409 f"Restore {parent.label} first"           # R2-D2, Q4
    if entity is BfcNode:
        if its latest retire was with-dependents: raise 409 "use Restore with its requirement
            and flows" — the plain path never discards the undo key or leaves a step with no BR
        bfc.assert_name_free(obj.project_id, obj.parent_id, obj.node_name, except_id=obj.id)  # Q1
        if a live node of the same set now holds obj.hier_code:   # R2-D10 — partial-unique
            obj.seq_no = next free seq under its parent; obj.hier_code = generate_code(obj)
    obj.is_active = True; obj.deleted_at = None; obj.deleted_by = None
    # a unique conflict (e.g. a second active BR on the node) surfaces as 409 (P10)
    AUDIT_EVENT(event_type='RECORD_RESTORED', detail={label})
    # "Nothing is ever truly gone" (§5.6) includes getting it back — for business rows only.

# ---- consistency check (services/consistency.py; findings D11, R2-D2, R2-P6) ----
consistency_check(project_id | None, db):        # None = across every project (operators)
    # the route checks require_project(…, VIEW) first; the caller owns access
    return {                                     # an empty list means the rule holds
      "hier_code_drift":  nodes where hier_code != recompute_from_parent_chain(node),
      "level_no_drift":   nodes where level_no != depth(node),
      "process_without_br": to-be process nodes with no active BR,      # S7-2
      "br_on_non_process":  BRs whose node is not a process   # DB-impossible since D-23; a proof
      "orphan_fields":    active data_fields whose parent data_entity is inactive,
      "active_under_inactive":                                          # R2-D2
          for T in FREEZE_SET, for (P, fk) in PARENTS[T]: active T rows whose P row is inactive
          — built per table as brsol_under_inactive, brfr_under_inactive,
            fr_under_inactive_solution, appsol_under_inactive, appnode_under_inactive,
            interface_under_inactive,
      "project_sequence_missing": number series of the ten with no PROJECT_SEQUENCE row,  # R2-D14
      "as_is_allocated":  active APPLICATION_SOLUTION rows on an AS_IS application,       # §6.2
      # each chart's DFD rule (dfd_rule.codes, D-70), for a chart whose DFD is on (S7-3); a line whose
      # element is not in that chart's rule lists nothing:
      "process_missing_input":  processes lacking STARTED (an input DE, inbound external flow or trigger),
      "process_missing_output": processes lacking DATA_OUT (an output data entity),
      "process_missing_data_in", "process_missing_order",  "diagram_missing_external",
      "project_without_dfd_rule": (project, chart) pairs with no live rule row,          # error, fails closed
      "dfd_rule_invalid":        charts whose live rule holds ORDER without DATA_IN and DATA_OUT,   # error
      "rows_in_off_component":  live rows in a component that is off,     # D-37
      # warnings — shown, a freeze warns, never refuses:
      "entities_without_fields", "entities_keys_only",                    # D-39, S4-12
      "fr_solution_outside_its_brs",                                      # D-52
      # informational — operations lapses or notes, never count toward the freeze gate:
      "purge_overdue":    import batches past 90 days still holding rows,
      "as_is_support_by_to_be", "as_is_support_on_to_be",                 # S6b-5, D-47
    }
    # Severity classes: INFORMATIONAL and WARNINGS never refuse; FREEZE_BLOCKING_WARNINGS
    # (the process_missing_<element> lines, diagram_missing_external, rows_in_off_component) are amber while
    # editing and a refusal at freeze; every other line must be empty.
    # The mitigation for storing derived hier_code and level_no (§5.5). It is a PRECONDITION
    # OF FREEZE (§7.7), run INSIDE the freeze transaction (R2-P6), because freeze is the
    # moment correctness starts carrying weight. active_under_inactive is how a row that
    # slipped past retire (direct SQL, a migration, a bug) is caught before it is frozen.

# ---- code_master resolution (finding D12) ---------------------------------
code_master.resolve(project_id, category):
    # THE single source of truth for the two-tier rule, with the same standing as
    # numbering.py and access.py (playbook §9.10). A project override shadows the global of
    # the same category+code. Live rows only; ordered by sort_order, code.
    overrides = live rows where project_id = :p and category = :c
    globals_  = live rows where project_id IS NULL and category = :c
    return overrides ∪ {g for g in globals_ if g.code not in overrides.codes}
    # Every consumer routes through this: the React dropdown, validate_required_code, the
    # import template's data-validation lists, and the import validator, so a project that
    # renamed HIGH to MAJOR gets a template offering exactly what its validator accepts.

# ---- spreadsheet safety (findings S5, S6) ---------------------------------
escape_cell(v):                                     # EVERY sheet-writing path uses this
    if isinstance(v, str) and v[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + v                              # or write as an explicit inline string
    return v
    # Issue titles, descriptions and DE/field descriptions arrive from workshops, client
    # documents and — via bulk import — directly from a client-supplied file, and FTC emails
    # the export to the client's BA or a vendor under its own name. The round trip (injected
    # by file → stored → emitted by file) never passes a human who would read the cell as code.

enforce_upload_limits(file):                        # finding S6 (services/xlsx.py)
    MAX_UPLOAD_BYTES         =  10 * 1024 * 1024    # 10 MB on the wire — enforced at ingress (§7.12b)
    MAX_DECOMPRESSED_BYTES   = 100 * 1024 * 1024    # the zip-bomb cap
    MAX_SHARED_STRINGS_BYTES =  20 * 1024 * 1024
    MAX_MEMBERS              = 1_000                # zip parts
    MAX_ROWS, MAX_COLS       = 5_000, 200

    parse with openpyxl load_workbook(read_only=True, data_only=True)
        # read_only streams row by row. One stray formatted cell near row 1,048,576 —
        # routine with copied Excel templates — would make a non-streaming parser build a
        # million rows and kill the worker.
    count decompressed bytes as the zip members are read; abort over the cap
    abort at MAX_ROWS / MAX_COLS while streaming, before materialising them
    # XML hardening: openpyxl parses through defusedxml, checked when the module loads (the
    # app refuses to start without it), so entity expansion and external-entity resolution are
    # neutralised. Acceptance criterion 75 feeds a workbook with an external entity
    # declaration and asserts it is rejected rather than resolved.
```

### 7.12a JSON import limits (D-25)

The same threat as the `.xlsx` parser in §7.12, in a different shape: a JSON file is cheap
to make deep or huge, and this one may have been written by an AI nobody watched.

```
enforce_json_limits(file):
    reject if the body exceeds 2 MB — enforced at ingress, before a byte reaches the handler (§7.12b)
    parse with the stdlib json module under a nesting-depth cap of 32
    reject NaN / Infinity (parse_constant), duplicate object keys (object_pairs_hook)
    reject if steps > 500, inputs + outputs + external flows + triggers > 2,000 combined (SC-6),
           data_entities > 500, any string > 4,000 chars
    key and source_ref lengths are capped by the published JSON Schema (S4-8)
    every free-text value is stored as text and rendered escaped — never as HTML (S5)
```
500 steps per file sits well inside A-35's 2,000 process nodes per project: one file is one
parent node's flow, not a whole chart.

### 7.12b Mermaid safety, ingress limits and import retention

```
# ---- Mermaid safety (R2-S7; services/render.py) -----------------------------
MERMAID_ENTITY = {'#': '#35;', '"': '#quot;', '<': '#lt;', '>': '#gt;', '`': '#96;',
                  '[': '#91;', ']': '#93;', '(': '#40;', ')': '#41;', '{': '#123;',
                  '}': '#125;', '|': '#124;', ';': '#59;'}
escape_mermaid(text):                      # EVERY Mermaid label uses this, no exceptions
    s = str(text or "")[:200]                          # cap the RAW text — never cut an entity
    s = break-like characters (Cc, Zl, Zp: CR, LF, tab, U+2028 …) → a space;
        invisible format characters (Cf: U+202E, U+200B, U+FEFF …) → removed
                                                       # a newline starts a new statement
    s = s.replace("%%", "")                            # comments and %%{init}%% directives
    s = "".join(MERMAID_ENTITY.get(c, c) for c in s)   # '#' first by construction (one pass)
    return '"' + s + '"'                               # EVERY label quoted
    # Process names, lanes, triggers, entity and field names arrive from workshops and — via
    # the flow JSON — from an AI conversion of a client slide. A label that closes its
    # bracket and opens a `click` directive, or an %%{init}%% that switches securityLevel to
    # loose, would turn the pasted diagram into a link or a script in the client's deck tool.

render_mermaid(graph):                     # the one renderer: export_dfd, export_erd
    renders exactly the dicts generate_dfd / generate_erd return, and reads nothing else
    ids are generated from database ids ("s12", "d7", "x2", "E7", "l1", "a_3") — never from user text
    erDiagram: entity as E7["DE-0007 Sales order"]; attribute names emitted as a_<n> with the
               real name in the quoted comment — erDiagram accepts no quoted attribute names
    NEVER emits: click, call, href, %%{init, style, classDef, linkStyle, class
    _guard (the last step of every exporter): any output line whose first token is one of
        those, in any case, or that opens %% or --- → log and raise 500 — a renderer bug,
        never a user-visible diagram

# ---- request body limits at ingress (R2-S8; services/body_limit.py) ---------
ROUTE_CAPS = [                                   # ordered: the first match wins
    ("POST /api/v1/projects/*/bulk/process-flow/validate",        2 MB),   # §7.12a
    ("POST /api/v1/projects/*/bulk/*/(validate|check)",          10 MB),   # §7.12
]   # every other request: the 1 MB default
    # A route taking more than the default registers here.
Layer 1 — Azure ingress (§15): a request-body cap at the edge set to the largest route
          limit (10 MB). An oversized body never reaches the container.
Layer 2 — BodyLimitMiddleware, the OUTERMOST ASGI middleware — before auth, before
          routing, before any handler or dependency runs:
    cap = cap_for(method, path)
    if Content-Length > cap: return 413 without reading the body
    if cap > default and there is no Bearer header: return 401 before reading a byte
        # a header check, not authentication — the route's guard still verifies the token
    read the body counting real bytes per chunk; past cap → 413 and the app is never called
        # a chunked body, or a Content-Length that lies
    replay the accepted body to the app from memory — at most the cap, held once,
    nothing spooled to disk
    # enforce_upload_limits (§7.12) and enforce_json_limits (§7.12a) stay: they check
    # decompressed size, rows and depth, which ingress cannot see.

# ---- import retention (Q14, closes A-32; services/import_purge.py) ----------
purge_import_rows():                       # daily scheduled job (§15), as the app role
    cutoff = the database's now() - 90 days            # no caller can pass a clock
    a row is due 90 days after its batch's upload, except an UPDATE row's before-values
        (payload.before), due 90 days after the commit
    lock due batches FOR UPDATE SKIP LOCKED            # a batch mid-commit waits for the next run;
                                                       # batch-then-rows is the commit's lock order
    with one transaction:
        DELETE the due import_row rows                 # one of VB's three hard deletes (law 1)
        when a batch's last row goes:
            UPDATE import_batch SET rows_purged_at = now(), file_name = '(purged)',
                   status = CASE WHEN status IN ('VALIDATING','VALIDATED') THEN 'REJECTED'
                                 ELSE status END       # an expired draft cannot be committed
    AUDIT_EVENT('IMPORT_ROWS_PURGED', detail={batches, rows, cutoff})   # every run, even empty
    # The header survives — who imported what, when, with what counts and outcome. The
    # payload — raw client cells, people's names — does not; nor does the file name, which can
    # identify a person. The app role's only DELETE grants are import_row and diagram_layout
    # (§6.6). consistency_check.purge_overdue makes a forgotten or failing run visible.
```

### 7.13 The control framework (D-13…D-19)

Each part runs only where its component is on (D-37): effort and the rate card under `EFFORT` (which
needs `FUNCTION_REQUIREMENT`), benefits under `BENEFIT` (needs `SOLUTION`), risks under `RISK`, change
requests under `CHANGE_REQUEST` (needs `EFFORT`). Their writes are refused with 409 `COMPONENT_OFF`
otherwise (§7.8).

```
# ---- size and effort (D-13) -----------------------------------------------
maintain_rate_card(project_id, cells, change_rationale, confirm_high=False):   # R2-D7
    access.require_project(user, project_id, EDIT, component='EFFORT')        # S6c-3, D-40
    if not change_rationale.strip():
        raise 422 "Changing the rate card is a commercial decision and needs a reason"
    if not confirm_high and any cell > 60 man-days:
        raise 422 "A rate above 60 man-days needs confirming"               # S6c-7; flagged on the card
    changes = []
    for (fr_type_code_id, complexity_code_id, standard_days) in cells:
        old = EFFORT_RATE(project_id, fr_type_code_id, complexity_code_id)
        upsert EFFORT_RATE(..., standard_days, change_rationale) WHERE row_version = :v   # 409 on 0
        # change_rationale is stored on the row too: CHECK (row_version = 1 OR
        # change_rationale IS NOT NULL), §5.3 EFFORT_RATE
        changes.append({fr_type, complexity, from: old.standard_days if old else None,
                        to: standard_days})
    AUDIT_EVENT(event_type='RATE_CARD_CHANGED', project_id,
                detail={changes, change_rationale})
    # Existing FRs are NOT repriced (A-38, S6c-2). The card reports, per cell, how many rated
    # FRs are not at the current rate and their Σ days, visible to every reader (S6c-5);
    # re-rating is per FR and audited. The card is frozen with every baseline
    # (baseline_effort_rate, §6.1), so a renegotiation is visible as itself rather than as
    # unexplained drift. The FTC default card is placeholder values, marked unconfirmed (S6c-1).

rate_function_requirement(fr_id, complexity_code, row_version):
    access.require_project(user, fr.project_id, EDIT, component='EFFORT')
    rate = EFFORT_RATE(project_id, fr.fr_type_code_id, complexity_code)     # D-27
    if rate is None: raise 422 "No rate card entry for this FR type and complexity"
    fr.complexity_code_id = complexity_code
    fr.effort_days = rate.standard_days          # DERIVED AT SAVE, THEN STORED
    # Never computed at read time, never accepted from a request (law 6). A renegotiated rate
    # card must not silently reprice scope that has already been agreed and frozen.

priced_diff(baseline_a, baseline_b | live):                           # Q3, R2-D3
    # available only when EFFORT is on in both sides; otherwise {available: false, EFFORT_OFF}
    d = baseline.diff(a, b)                      # §7.7 — same guard, same integrity check
    A = {r.source_fr_id: r for r in function_requirement rows of a}
    B = {r.source_fr_id: r for r in function_requirement rows of b}
    lines = []
    for fid in A.keys() | B.keys():              # EACH FR EXACTLY ONCE
        ea = A[fid].effort_days if fid in A else None
        eb = B[fid].effort_days if fid in B else None
        if   fid not in A:          cls, delta = 'ADDED',   +(eb or 0)
        elif fid not in B:          cls, delta = 'REMOVED', -(ea or 0)
        elif (eb or 0) != (ea or 0): cls, delta = 'CHANGED', (eb or 0) - (ea or 0)
        else: continue                           # same effort: MOVED or reworded, prices at 0
        row        = B.get(fid) or A[fid]
        untraced   = the FR has no BR_FUNCTION_REQUIREMENT link on the side the line reads   # D-52
        unassigned = row.solution_id is None                                              # D-52
        unrated    = (eb if fid in B else ea) is None
        lines.append({fid, row.fr_number, cls, delta, untraced, unassigned, unrated})
    totals = {
      "added_days":    Σ delta where cls = ADDED,
      "removed_days":  Σ delta where cls = REMOVED,       # negative
      "changed_days":  Σ delta where cls = CHANGED,       # re-rated or re-typed, net
      "net_days":      Σ delta,
      "untraced_days": Σ delta where untraced,            # its own line; inside net_days
      "unassigned_days": Σ delta where unassigned,        # its own line; inside net_days
      "unrated_fr_count": count where unrated,            # priced at 0 — say so
    }
    # ---- effort EXPOSED: informational, NEVER added to net (Q3) ----
    changed_brs = d.business_requirement rows with class ADDED | CHANGED | REMOVED
    exposed_frs = distinct FRs reachable BR → BR_FUNCTION_REQUIREMENT → FR
                  in baseline b (in baseline a, for a REMOVED BR)
    totals["effort_exposed_days"] = Σ effort_days of exposed_frs
                                    (None, not 0, when FUNCTION_REQUIREMENT is off)
    return {diff: d, lines, totals}
    # A priced diff prices only what changed — the FR's own effort — and shows the exposure
    # beside it: "+12 days re-rated; 340 days sit under requirements that changed".
    # "v1.1: +340 man-days added, -60 removed, net +280" — the sentence that turns a
    # scope log into scope control.

# ---- benefit (D-14) -------------------------------------------------------
value_ranking(project_id):                                            # R2-D12, Q9
    out = {}
    for unit in distinct BENEFIT.measure_unit among active benefits:
        rows = []
        for each SOLUTION s linked to an active benefit in this unit:
            value  = Σ over BENEFIT_SOLUTION bs of benefits b in unit:
                         (b.target_value - b.baseline_value) * bs.contribution_pct / 100
            effort = Σ FUNCTION_REQUIREMENT.effort_days where solution_id = s and is_active
            rows.append({solution, value, effort, ratio = value / nullif(effort, 0)})
        out[unit] = rows ordered by ratio desc, with bottom_quartile marked
    return out
    # Benefits are ranked only within one unit: hours saved and baht saved are never summed.
    # A solution with benefits in two units appears in both rankings, each with that unit's
    # value only. The bottom quartile of each unit answers "what does this change displace?"

# ---- risk (D-15) ----------------------------------------------------------
score_risk(risk):
    risk.exposure_score = PROBABILITY_WEIGHT[p] * IMPACT_WEIGHT[i]    # derived at save (law 6)

promote_risk_to_issue(risk_id, description):
    access.require_project(user, risk.project_id, EDIT, component='RISK')
    issue = issue.raise_issue(...)               # the risk's owner becomes the raiser
    risk.materialised_issue_id = issue.id
    risk.status_code = 'MATERIALISED'            # the risk row SURVIVES
    record_decision(... 'RISK_MATERIALISED' ...)
    # The risk is the record that it was foreseen — the evidence a post-mortem asks for.

# ---- change control (D-16) ------------------------------------------------
raise_change_request(project_id, baseline_id, title, rationale, origin_code):   # Q8
    access.require_project(user, project_id, EDIT, component='CHANGE_REQUEST')
    bl = BASELINE(baseline_id); if bl is None or bl.project_id != project_id: raise 404
    agreed = newest baseline of the project with a recorded client approval   # DR8-P1
    if bl.status_code not in ('FROZEN', 'APPROVED') and bl.baseline_id != agreed.baseline_id:   # SC-2
        raise 422 "A change request is raised against an agreed baseline — FROZEN, "
                  "APPROVED, or the superseded one carrying the client's approval"
    validate_required_code("CR_ORIGIN", origin_code)
    cr_number = numbering.next_number(db, project_id, "CR", "CR", 4)
    insert CHANGE_REQUEST(..., baseline_id, status_code='DRAFT',
                          raised_by_user_id=jwt.user_id)

analyse_cr_impact(cr_id, seed_objects):
    # The blast radius is COMPUTED, never typed.
    # seed_objects may be BRs or FRs: an untraced FR has no BR, so it can only be a seed.
    walk: BR -> BR_FUNCTION_REQUIREMENT -> FUNCTION_REQUIREMENT                   # D-52
          BR -> BR_SOLUTION -> SOLUTION (solution-level rows)
          FR -> its solution tag, if any -> APPLICATION_SOLUTION -> APPLICATION
          BR -> BR_DATA_ENTITY -> DATA_ENTITY -> DATA_FIELD
          SOLUTION -> SOLUTION_PHASE -> PHASE
          SOLUTION -> SOLUTION_DEPENDENCY (both directions)
          SOLUTION -> BENEFIT_SOLUTION -> BENEFIT
    for each reached object: INSERT CR_IMPACT(entity, id, impact_type)
    # impact_type ∈ ADD | MODIFY | REMOVE | RESEQUENCE

price_cr(cr_id):
    cr.effort_delta_days   = sum(CR_IMPACT.effort_delta_days)     # from D-13
    cr.benefit_delta_value = sum over impacted BENEFIT rows       # from D-14
    return { effort_delta, benefit_delta,
             phases_impacted, dependency_violations,
             displaced_candidates: {unit: value_ranking(project)[unit].bottom_quartile
                                    for unit in units of the CR's impacted benefits} }
             # per unit (Q9) — never one list across units

decide_cr(cr_id, outcome, displaces_cr_id, rationale, alternative_rejected):
    access.require_project(user, cr.project_id, EDIT, component='CHANGE_REQUEST')
    if outcome == 'APPROVED' and cr.effort_delta_days > 0 \
       and displaces_cr_id is None and not cr.budget_increase_approved:
        raise 422 "Approving net-positive effort must name what it displaces, or record " \
                  "an explicit budget increase."
        # This is the control. Not a warning, not a report footnote — a refused write.
    cr.status_code = outcome
    cr.decision_id = record_decision(project_id, title, rationale, alternative_rejected,
                                     analysis_code='priced_diff', dimension='SCOPE')
    AUDIT_EVENT(event_type='CR_DECIDED', detail={cr_number, outcome, effort_delta})

# ---- phasing (D-18) -------------------------------------------------------
link_solution_dependency(solution_id, depends_on_id):
    if creates_cycle(solution_id, depends_on_id): raise 422 "Dependency cycle"
    # Topological check on insert. A cycle is silent until someone tries to schedule.

phase_plan_report(project_id):
    return {
      "effort_by_phase":      sum FR.effort_days via SOLUTION_PHASE.portion_pct,
      "dependency_violations": solutions scheduled at or before a prerequisite,
      "volatile_in_current":  L1 areas flagged by requirement_volatility whose solutions
                              are still assigned to the current phase,
    }
    # The last one is the commonest control action in the whole app: move it right.

# ---- control rules (D-19) -------------------------------------------------
ANALYSIS_REGISTRY = {                # closed vocabulary; a rule must name one of these
  'priced_diff', 'requirement_volatility', 'coverage', 'solution_matrix',
  'application_gap', 'interface_load', 'org_impact_heatmap', 'stakeholder_engagement',
  'value_ranking', 'benefit_gap', 'risk_register', 'issue_dashboard',
  'data_migration_map', 'master_data_candidates', 'process_change_intensity',
  'phase_plan', 'consistency_check',
}

maintain_control_rule(project_id, analysis_code, fields, change_rationale):
    access.require_project(user, project_id, EDIT)
    if analysis_code not in ANALYSIS_REGISTRY: raise 422 "No such analysis"
    if not change_rationale.strip(): raise 422 "Changing a control threshold is a "
                                               "governance decision and needs a reason"
    upsert CONTROL_RULE(project_id, analysis_code, ..., agreed_at=now())
    AUDIT_EVENT(event_type='CONTROL_RULE_CHANGED', project_id,
                detail={analysis_code, from: old_values, to: new_values, change_rationale})
    # Without the audit row, a project that never went red is indistinguishable from one
    # whose thresholds were widened until it stopped going red.

maintain_house_default(analysis_code, fields):
    require user.is_platform_admin
    upsert CONTROL_RULE(project_id=NULL, analysis_code, ..., is_house_default=True)
    # Affects FUTURE projects only — see the entity note. No in-flight engagement moves.

reset_project_rules_to_house_default(project_id, change_rationale):
    access.require_project(user, project_id, EDIT)
    overwrite this project's rules from the project_id IS NULL tier, preserving
      owner_org_role_id where the analysis_code still exists
    AUDIT_EVENT(event_type='CONTROL_RULES_RESET', project_id, detail={change_rationale})
    # The explicit opt-in that the copy-on-create rule otherwise denies.

control_panel(project_id):
    access.require_project(user, project_id, VIEW)
    out = []
    for rule in CONTROL_RULE where project_id = :p and is_enabled:
        measured = ANALYSIS_REGISTRY[rule.analysis_code](project_id).headline_value
        state = ('ESCALATE' if breaches(measured, rule.escalate_value, rule.comparison)
                 else 'FLAG'  if breaches(measured, rule.threshold_value, rule.comparison)
                 else 'GREEN')
        out.append({rule.analysis_code, measured, rule.threshold_value, state,
                    owner: rule.owner_org_role_id,          # a ROLE, never "the PMO"
                    action: rule.prescribed_action,
                    escalation: rule.escalation_path})
    return out
    # The PMO's one screen. Every row carries the number, the verdict, the named owner
    # and the action agreed at mobilisation — so the response is not reinvented under
    # pressure, and the thresholds belong to the client rather than to this spec.
```
`decide_cr` and `reset_project_rules_to_house_default` run at **EDIT** — project editors, and admins always (SC-7).

**Seeded control rules.** `create_project` seeds the registry below with FTC defaults, which
the client then negotiates. These thresholds are starting points, not doctrine:

| `analysis_code` | Flag | Escalate | Prescribed action |
|---|---|---|---|
| `priced_diff` | >5% cumulative effort growth | >10% | Raise a CR to steering; name the displacement |
| `requirement_volatility` | area churns 2 baselines | 3 | Pull the area out of the current wave; re-run the workshop |
| `coverage` | any open gap at a gate | — | Assign owner + date per gap; do not pass the gate |
| `solution_matrix` | TECHNOLOGY >70% of solutions | >85% | Commission the org/process workstream, or lower the benefit forecast |
| `interface_load` | INTERFACE >25% of FRs | >35% | Stand up an integration workstream; book test environments |
| `org_impact_heatmap` | unit in top decile of impact | top decile + zero issues raised | Dedicated change agent; capacity check; interview before sign-off |
| `stakeholder_engagement` | org unit with zero issues raised | high impact + zero issues | Interview before sign-off — silence becomes rejection at UAT |
| `benefit_gap` | any solution with effort and no benefit | >20% of solutions | Challenge at the next gate |
| `risk_register` | exposure ≥ 12 open | ≥ 16 | Mitigation owner + date; steering if unmitigated |
| `data_migration_map` | entity with no source system | conflicting sources | Data ownership decision before design freeze |

---

### 7.14 The diagram canvas — DFD and ERD (D-29, D-30, D-31, D-38, D-65)

**One canvas component for every diagram** (VB law 8): `<ModelCanvas kind="dfd" | "erd">`
(`frontend/src/canvas/ModelCanvas.jsx`), built on React Flow (`@xyflow/react`, MIT) with `elkjs` for
auto-layout in a worker, and **one position saver**, `canvas/useLayoutSave.js`. Each kind supplies its
node and edge types; the component owns what every diagram shares — visible-only rendering, theme-driven
colour mode, no keyboard delete. There is no separate business process flow diagram (D-38): the
`PROCESS_FLOW` diagram type is retired, its stored positions stay as history, and the layout service
refuses new ones (S7-5).

**What the ERD looks like:**

- **Entity card.** A header in the data-entity teal with `DE-0007` and the name. Below it,
  PK rows (key icon, bold) first, then FK rows (link icon, and the parent entity's name in
  small type), then attributes. More than 8 attributes collapse to "+12 more". Hovering a
  row shows its description, logical type and mandatory flag. Under `KEYS_ONLY` depth (D-39) an
  entity with keys and no other attributes is expected, not flagged.
- **Field-level connectors.** Each FK row has its own handle, so the relationship line
  leaves from the FK row itself and arrives at the parent's PK row: you see *which* field joins,
  not only which two tables do.
- **Crow's-foot notation** as custom SVG markers: `|` one, `O|` zero-or-one, `<` many.
  Solid line for an identifying relationship (the FK is part of the child's key), dashed
  for a non-identifying one. Orthogonal routing (ELK `ORTHOGONAL`), so lines turn corners
  instead of cutting across cards. Edges are derived from FK fields; cardinality from
  `is_mandatory` and key uniqueness (D-29).
- **Interaction.** Drag to move, and the position is saved (D-30). **Auto-arrange**
  re-runs ELK for everything not pinned. Click an entity to highlight its neighbours and dim
  the rest; double-click opens the field editor in a side panel, so fields are edited *on*
  the diagram. Draw a line from an attribute to another entity to create an FK. Minimap,
  zoom to fit, search-to-focus.
- **Subject areas.** A filter by BFC L1/L2 branch shows only the entities that branch reads
  or writes. FKs leaving the area are drawn as short stubs labelled with the target, so a
  200-entity model stays readable one area at a time.
- **Export.** PNG and SVG for decks, Mermaid `erDiagram` text for documents (§7.12b), and PDF
  (D-42).

**What the DFD looks like** (the process diagram, as-is and to-be, D-38, D-47). It is **generated** (D-31):
every element comes from the process records (`generate_dfd`, §7.2a), and a connection drawn on it writes one of
those records (D-65):

- **Lanes are performers** (D-46): one lane per org unit, org role, application or AI performing a
  process in scope, plus an "Unassigned" lane. Supporting systems show inside the process box.
- **Processes**, **data stores** (cylinders), **external entities** (square nodes with a heavy
  border) and **triggers** (start symbols, D-49).
- **Flows** between processes and stores, external entities and triggers, from step I/O
  (D-24), external flows (D-24a) and trigger links. **Order is derived, never stored**: B follows A
  when B reads what A writes; it drives the left-to-right layout and is drawn, dashed, only as an
  optional overlay. A diagram with no derived order lays its processes out in chart order, without arrows,
  labelled "chart order" (D-70). Stores read or written outside the scope are boundary stubs.
- **Readiness** (D-68): each process box carries its light — colour, icon and text — and the DFD index
  counts ready / partly / not ready per diagram.
- **Interaction.** Processes, stores, parties and triggers can be dragged, and the position is saved
  (D-30). **Drawn connections write the same record** (D-65): `connectable` is on for an editor on a live
  diagram (off for viewers, a baseline view, and a chart whose DFD is off). `onConnect` classifies the two
  ends and calls the matching writer through `api/scope.js` — store ↔ process: a step input or output
  (`step_io.ensure_step_io`); party ↔ process: an external flow, with a small form for the data entity or a
  flow label; trigger → process: a trigger link; process → process: a **hand-off**, where the editor picks
  the data entity and one transaction writes both sides (`POST /bfc-nodes/{id}/hand-offs`), so the derived
  order arrow then appears by itself. A drag to empty canvas opens the data-entity picker, which can also
  create a new entity (Q-12). Invalid pairs (store → store, party → store, a trigger to anything but a
  process, anything across charts) are refused in the browser before any call and again by the server; an
  existing row → "Already on the diagram". A store or party that appears because of a new connection is placed
  where it was dropped (`useLayoutSave`). Clicking a STORE, EXTERNAL or TRIGGER flow offers "Remove this
  flow" (the existing unlink route; a step I/O a BR CRUD or external flow depends on stays, with a link to the
  requirement); **derived order arrows are not selectable for removal**. No keyboard delete. Drawing never
  writes BR CRUD (Q-11). Every row drawn is identical to the row the panel writes, so the diagram always stays
  a picture of one record.
- **Gaps stay visible** as a warnings panel on the diagram: processes missing an element of the chart's DFD
  rule (these block the freeze while the set's DFD is on, D-70, S7-3), elements outside the rule as
  information, and processes with no performer (D-55).
- **Export.** PNG, SVG, Mermaid (one subgraph per lane, triggers as start nodes, §7.12b) and PDF (D-42).

**JSON import** (the flow file, §7.2b) opens a preview diagram over the staged batch before commit,
with new, changed and warning items badged. A consultant approves a picture, not a row list.

**Rejected, in one line each.** GoJS and JointJS+ are more complete but carry commercial
licences per developer. Mermaid renders but cannot be dragged or edited. Embedding draw.io
gives free-form drawing that is not bound to the model, which is exactly the "diagram that
looks authoritative and is wrong" problem D-31 exists to prevent.

**Performance bound.** React Flow renders only visible nodes. The designed load is 200
entities with 2,000 fields on one ERD, and 150 processes on one DFD. Above that, the
subject-area filter is the answer, not a faster renderer.

---

## 8. `code_master` categories needed

Per playbook §9.3: no hard-coded enums, and the **code** goes over the wire, never the label.
Seeded by `backend/seeds/seed_code_master.py`, never in Alembic. Resolved only by
`services/code_master.resolve` (two tiers, below).

| Category | Codes (seeded) | Used by |
|---|---|---|
| `SOLUTION_CATEGORY` | `ORG_AND_RULES`, `PEOPLE`, `PROCESS`, `DATA`, `TECHNOLOGY` — **`is_system`, not project-editable** (S5-4) | `SOLUTION.category_code` — **D-7**, the five operating-model dimensions. Reports and `create_fr` branch on TECHNOLOGY / DATA, so a project cannot rename or retire the five |
| `SOLUTION_STATUS` | `PROPOSED`, `AGREED`, `IN_DELIVERY`, `DELIVERED`, `REJECTED` | `SOLUTION.status_code`. A new solution starts PROPOSED (S5-5) |
| `APP_LIFECYCLE` | `AS_IS`, `TO_BE`, `BOTH` — **`is_system`, not project-editable** | `APPLICATION.lifecycle_code` — **D-8**. Code branches on `AS_IS` (the allocation rule, §6.2), so the values are fixed |
| `APP_KIND` | `PACKAGE`, `CUSTOM`, `SAAS`, `PLATFORM`, `RPA`, `INTEGRATION`, `REPORTING` | `APPLICATION.app_kind_code` |
| `FR_TYPE` | `FORM`, `INTERFACE`, `REPORT`, `BATCH` — **project-editable**; each code carries a **behaviour** ∈ `FORM` / `INTERFACE` / `REPORT` / `BATCH` / `OTHER` (D-27) | `FUNCTION_REQUIREMENT.fr_type_code`. Behaviour decides the FR form's detail panel and membership of the interface list, so a renamed or added type keeps working. **A behaviour is immutable once any FR or rate row references the code** (Q6, R2-D8; the NO ACTION FK, §5.3 CODE_MASTER) |
| `INTERFACE_PATTERN` | `PUSH`, `PULL`, `BIDIRECTIONAL` | `FR_INTERFACE.pattern_code` — **D-27** |
| `INTERFACE_METHOD` | `API`, `FILE`, `DB`, `MESSAGE`, `MANUAL` | `FR_INTERFACE.method_code` — project-editable |
| `INTERFACE_FREQUENCY` | `REALTIME`, `NEAR_REALTIME`, `HOURLY`, `DAILY`, `WEEKLY`, `MONTHLY`, `ON_DEMAND` | `FR_INTERFACE.frequency_code` |
| `EXTERNAL_ENTITY_KIND` | `CUSTOMER`, `SUPPLIER`, `BANK`, `REGULATOR`, `PARTNER`, `OTHER` | `EXTERNAL_ENTITY.kind_code` — **D-24a** |
| `IMPORT_STATUS` | `VALIDATING`, `VALIDATED`, `REJECTED`, `COMMITTED` — **`is_system`, resolved from the global tier only** (S4-7) | `IMPORT_BATCH.status_code` — **D-5**. The 90-day purge turns an uncommitted batch REJECTED (Q14, §7.12b). *Import targets (`target_entity`) and `import_mode` are `CHECK` columns, not categories (§5.3 Import staging)* |
| `FR_COMPLEXITY` | `SIMPLE`, `MEDIUM`, `COMPLEX`, `VERY_COMPLEX` | `FUNCTION_REQUIREMENT.complexity_code` — **D-13**, keyed with FR type into `EFFORT_RATE` |
| `BENEFIT_TYPE` | `COST_REDUCTION`, `REVENUE`, `PRODUCTIVITY`, `RISK_REDUCTION`, `COMPLIANCE`, `CUSTOMER` | `BENEFIT.benefit_type_code` — **D-14** |
| `BENEFIT_STATUS` | `FORECAST`, `COMMITTED`, `IN_REALISATION`, `REALISED`, `ABANDONED` | `BENEFIT.status_code` |
| `RISK_PROBABILITY` | `RARE`, `UNLIKELY`, `POSSIBLE`, `LIKELY`, `ALMOST_CERTAIN` | `RISK.probability_code` — **D-15** |
| `RISK_IMPACT` | `NEGLIGIBLE`, `MINOR`, `MODERATE`, `MAJOR`, `SEVERE` | `RISK.impact_code` |
| `RISK_STATUS` | `OPEN`, `MITIGATING`, `CLOSED`, `MATERIALISED` | `RISK.status_code` |
| `CR_STATUS` | `DRAFT`, `ANALYSED`, `PRICED`, `APPROVED`, `REJECTED`, `DEFERRED` | `CHANGE_REQUEST.status_code` — **D-16** |
| `CR_ORIGIN` | `CLIENT`, `VENDOR`, `REGULATORY`, `FTC`, `DEFECT` | `CHANGE_REQUEST.origin_code` |
| `PM_DIMENSION` | `SCOPE`, `SCHEDULE`, `COST`, `BENEFIT`, `RISK`, `QUALITY`, `ORG_CHANGE`, `DATA`, `VENDOR` | `DECISION.dimension_code` — **D-17**, the dimensions the control framework acts on |
| `PHASE_STATUS` | `PLANNED`, `IN_DELIVERY`, `COMPLETE`, `CANCELLED` | `PHASE.status_code` — **D-18** |
| `ISSUE_SEVERITY` | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` | `ISSUE.severity_code` |
| `ISSUE_TYPE` | `PROCESS`, `DATA`, `SYSTEM`, `ORGANIZATION`, `POLICY`, `OTHER` | `ISSUE.issue_type_code` |
| `ISSUE_STATUS` | `OPEN`, `IN_PROGRESS`, `RESOLVED`, `DEFERRED`, `CLOSED` | `ISSUE.status_code` |
| `ORG_UNIT_LEVEL` | `DEPARTMENT`, `DIVISION`, `SECTION` | `ORG_UNIT.unit_level_code` |
| `RACI_TYPE` | `R`, `A`, `C`, `I` — **project-editable**; each code carries a **behaviour** ∈ `RESPONSIBLE` / `ACCOUNTABLE` / `CONSULTED` / `INFORMED` / `SUPPORT` / `OTHER` (Q7). Seeded R → RESPONSIBLE, A → ACCOUNTABLE, C → CONSULTED, I → INFORMED. RASCI adds `S` → SUPPORT. RAPID is a **mapping**, not a vocabulary: Perform → RESPONSIBLE, Decide → ACCOUNTABLE, Input → CONSULTED, Recommend / Agree → OTHER | `BR_ORG_ROLE` (a to-be process's roles) and `BFC_NODE_ORG_ROLE` (an as-is process's roles, D-64), both via `raci_behaviour`, FK-verified. Configurable because clients use RASCI / RAPID / house variants. **The single Accountable per BR and per step reads the behaviour, never the letter** (R2-D9). Several RESPONSIBLE roles are legal; the lane is the performer, not a RACI role (D-46). A project holds exactly one live code per load-bearing behaviour, RESPONSIBLE and ACCOUNTABLE: a second is refused when the code is saved (A-60). A behaviour is immutable once referenced, as for `FR_TYPE`; a project override of a global code must carry the global's behaviour |
| `TRANSACTION_UNIT` | `INVOICE`, `ORDER`, `CASE`, `DOCUMENT`, `RECORD`, `CALL`, `PAYMENT`, `EMPLOYEE`, `OTHER` — library + project override | `BFC_NODE.transaction_unit_code` — **D-67**, what one transaction of a process is. Optional; never branched on (slice 13c) |
| `BR_LINE_KIND` | `RULE`, `CALCULATION`, `VALIDATION`, `OUTPUT`, `CONTROL` — project-editable; no behaviour code (nothing branches on a line kind) | `BR_REQUIREMENT_LINE.line_kind_code` — **D-59** (slice 11) |
| `BR_PRIORITY` | `MUST`, `SHOULD`, `COULD`, `WONT` (MoSCoW) | `BR_REQUIREMENT_LINE.priority_code`, nullable = not yet prioritised. The BR's own priority is the highest of its live lines, derived, never stored — **D-59** (slice 11) |
| `BR_STATUS` | `DRAFT`, `CONFIRMED`, `BASELINED`, `SUPERSEDED` | `BUSINESS_REQUIREMENT.status_code`. `BASELINED` / `SUPERSEDED` are set only by the baseline freeze (S1-8) |
| `FR_FULFILMENT_STATUS` | `SPECIFIED`, `ACCEPTED_BY_VENDOR`, `BUILT`, `TESTED`, `DEFERRED` | `FUNCTION_REQUIREMENT.fulfilment_status_code` — **the vendor boundary is this column, not a table** |
| `PROJECT_STATUS` | `PLANNING`, `ACTIVE`, `ON_HOLD`, `CLOSED` | `PROJECT.status_code` |
| `BASELINE_STATUS` | `DRAFT`, `FROZEN`, `APPROVED`, `SUPERSEDED` — **`is_system`, not project-editable** | `BASELINE.status_code`. Code compares the values: a CR may target FROZEN or APPROVED, or the SUPERSEDED baseline carrying the agreed approval (Q8, SC-2, §5.3 CHANGE_REQUEST) |
| `FIELD_DATA_TYPE` | `STRING`, `INTEGER`, `DECIMAL`, `DATE`, `DATETIME`, `BOOLEAN`, `TEXT`, `UUID` | `DATA_FIELD.data_type_code` (optional, D-26) |
| `PROJECT_COMPONENT` | `SOLUTION`, `FUNCTION_REQUIREMENT`, `APPLICATION`, `EFFORT`, `ISSUE`, `TO_BE_DFD`, `AS_IS`, `WBS`, `BENEFIT`, `RISK`, `CHANGE_REQUEST` — **`is_system`, global only** | `PROJECT_COMPONENT.component_code` — **D-37**. Code branches on these codes; that is the same recorded exemption from VB law 5 as `SOLUTION_CATEGORY` and `APP_LIFECYCLE`, because a system category cannot be renamed or retired by a project. Dependencies (`COMPONENT_REQUIRES`) and live-row tests (`COMPONENT_ROWS`) are code constants in `services/components.py` |
| `PROJECT_TEMPLATE` | `REQUIREMENTS_ONLY`, `DATA_AND_PROCESS`, `FULL_DELIVERY` — **global only**, labels editable in code maintenance | `PROJECT_TEMPLATE_COMPONENT.template_code` — **OR-3**. A template is a starting point copied into `project_component` at `create_project` and never linked afterwards. Its contents are seeded by `seeds/seed_project_templates.py` |

**Retired categories** (`RETIRED_CATEGORIES` in the seed): `FLOW_TYPE` (S2-1: `bfc_node_flow.flow_type`
is CHECK-listed, and the table itself is retired by D-38) and `PROJECT_ROLE` (D-40: the
OWNER / EDITOR / REVIEWER grants are retired). Their seeded rows stay, inactive, because old rows
reference them.

**Deliberate exclusions from `code_master`.** Each is a fixed vocabulary the code branches on, held as
a `CHECK` — a playbook §9.3 deviation:

- **CRUD (`C`/`R`/`U`/`D`)** is a `CHECK (crud_code IN ('C','R','U','D'))`. It is a closed four-value
  vocabulary no client renames, and it must be a real `char` column for the generated `direction`
  column to work (§5.4.2). Making it configurable would let a consultant break the INPUT/OUTPUT
  derivation.
- **`DIAGRAM_LAYOUT.diagram_type`** (`ERD` / `DFD`; `PROCESS_FLOW` rows are kept as history and the
  service refuses new ones, S7-5). The renderer branches on each value, and the per-type object rules
  in §6.2 must name the literal.
- **`CODE_MASTER.behaviour_code`**, with one vocabulary per category that has one: `FR_TYPE` → `FORM` /
  `INTERFACE` / `REPORT` / `BATCH` / `OTHER` (D-27), and `RACI_TYPE` → `RESPONSIBLE` / `ACCOUNTABLE` /
  `CONSULTED` / `INFORMED` / `SUPPORT` / `OTHER` (Q7). It is the stable vocabulary code branches on, so
  that the labels and codes of those two categories can be configurable.
- **`PROJECT.data_model_depth`** (`KEYS_ONLY` / `FULL`, D-39), **`APP_USER.user_kind`** (`USER` /
  `VIEWER`, D-40) and **`PROJECT_MEMBER.access_level`** (`EDIT` / `VIEW`, OR-6).
- **`BFC_NODE.bfc_set_code`** (`TO_BE` / `AS_IS`, D-47), **`BFC_NODE.performer_kind`** (`ORG_UNIT` /
  `ORG_ROLE` / `APPLICATION` / `AI`, D-46), **`PROCESS_TRIGGER.trigger_kind`** (`TIME` / `EVENT`, D-49),
  and the retired **`BFC_NODE_FLOW.flow_type`** (S2-1).
- **`PROJECT_DFD_RULE.element_code`** (`STARTED` / `DATA_IN` / `DATA_OUT` / `EXTERNAL` / `ORDER`, D-70) and
  **`BFC_NODE.volume_period_code`** (`DAY` / `WEEK` / `MONTH` / `QUARTER` / `YEAR`, D-67): each code is a
  predicate or a multiplier in the code, so they are fixed lists with their wording in the screen text files
  (S13-1). They are CHECK-listed rather than `code_master` rows also because the 13b migration backfills the
  rule in pure SQL, before any seed runs.

`docs/PLAYBOOK_DEVIATIONS.md` records CRUD (deviation 2), `diagram_type` and `behaviour_code` (3),
`data_model_depth` (7e) and `user_kind` / `access_level` (7f).
`bfc_set_code`, `performer_kind`, `trigger_kind` and `flow_type` each get a deviation line of their own (SC-11),
as do the slice 13 vocabularies `element_code` and `volume_period_code` (S13-1).

**Scoping:** `code_master.project_id` is nullable — `NULL` is the FTC-wide default library, non-null
is a per-project override shadowing the global of the same `category + code` (A-16). `is_system`
categories and the global-only ones (`PROJECT_COMPONENT`, `PROJECT_TEMPLATE`, `IMPORT_STATUS`) take no
project override.

**Resolution has exactly one owner: `services/code_master.resolve()` (§7.12, finding D12).** The
import template generator, the import validator and the React dropdowns are three consumers of the
same data. Each reads it through `resolve`, so a project that renames `HIGH` to `MAJOR` sees the same
values in its template, its validator and its screens (criterion 47).

**Labels are translated, codes are not** (D-44, wave 4): every seeded label gets an English,
Japanese and Thai text, chosen by the user's language. The schema change for translated labels goes
to `apple` before it is built.

---

## 9. API surface

`/auth/*` sits at the root; everything else is under `/api/v1` (one `GuardedRouter` in
`backend/main.py`; routers declare only their sub-paths). Every route is **protected** except
`POST /auth/login` and first-run setup (`GET`/`POST /auth/setup`, off unless
`ALLOW_FIRST_RUN_SETUP`, deviation 16) — an unauthenticated read is a finding, not a detail.

- **Every `PATCH` on an editable business entity requires `row_version` in the body and returns 409
  on mismatch (D-6).** A `DELETE` takes `row_version` as a query parameter.
- **Every `DELETE` is a soft delete and returns 409 naming the active dependents, if there are any
  (R2-D2).** The one exception is `DELETE /projects/{id}/diagram-layouts/…`, a hard delete of
  presentation rows (D-30). Retiring a process step *with* its dependents is a separate, confirmed
  action (S3-SR).
- **Errors come in a fixed order: 404 → 403 → 409.** A project the caller cannot see is 404, never
  403 (D-40, OR-6); a level too low is 403; a write to a component that is off is 409
  `COMPONENT_OFF` (D-37, slice7_schema §5.2). The 409 kind travels in the `X-VB-Error` header.
- **Derived values are never accepted from a body** (§9.2): `created_by`, numbers, `effort_days`,
  `exposure_score`, `direction`, `row_version` increments.

**Every route declares exactly one guard (R2-S1, §7.8).** The guard is part of the route's
definition (`@router.get(path, **guard.route)` in `backend/routers/guards.py`); a route without one
raises at import, and criterion 49 re-proves it over the running app. Levels rank
**`VIEW` < `EDIT` < `ADMIN`**; only a platform admin reaches `ADMIN` (D-40). A write to a project
component names it (`component=`), and criterion 49b fails a write that forgets.

| Guard | Resolves | Routes |
|---|---|---|
| `public` | nothing — no JWT | `POST /auth/login`, `GET`/`POST /auth/setup` **only** |
| `authenticated` | the JWT user; the service filters | `GET /auth/me`, `GET /projects` (via `visible_project_ids`), `GET /programs` (programs with at least one project visible to the caller; admins: all), `GET /project-templates`, `GET /project-components`; later `GET /process-flow-json/schema` |
| `platform_admin` | `current_user().is_platform_admin`, re-read every request (S4) | `/users*`, `/clients*`, `POST /projects`, `POST /programs`, `POST /programs/{program_id}/projects`, `DELETE /programs/{program_id}/projects/{project_id}`; later `PATCH /programs/{id}`, house control-rule defaults, global code maintenance, `purge` |
| `project_ctx(level, component=)` | `require_project(user, {project_id}, level, component)` | **every route under `/projects/{project_id}/…`** — `VIEW` for reads and exports; `EDIT` for writes, imports, freeze, client approval, the rate card, project control rules and FR types; `ADMIN` for components, data model depth, the DFD rule and the FTE basis, effective access, members and restriction |
| `object_guard(Model, level, component=)` | the object's owning project, then `require_project`; an object with no project is platform-admin only | `/bfc-nodes/{id}` · `/business-requirements/{id}` · `/solutions/{id}` · `/function-requirements/{id}` (incl. `/interface`, `/complexity`) · `/applications/{id}` · `/data-entities/{id}` · `/data-fields/{id}` · `/external-entities/{id}` · `/org-units/{id}` · `/org-roles/{id}` · `/process-triggers/{id}` · `/project-members/{id}` · `/baselines/{id}` · `/bulk/batches/{batch_id}` · **each restore route**, one per `RESTORABLE` entity (§7.12); later `/stakeholders`, `/issues`, `/benefits`, `/risks`, `/change-requests`, `/phases`, `/wbs-items` |
| `program_ctx(level)` | `require_program(user, {program_id}, level)` | `GET /programs/{program_id}`, `GET /programs/{program_id}/projects`; later the roll-ups `/dashboard`, `/counts`, `/interfaces`, `/effort`, `/control-status`, `/plan-vs-actual` |

`component=` on `project_ctx` / `object_guard` is a code, a tuple of codes, or a resolver on the row
(e.g. a BFC node needs `AS_IS` when it is in the as-is set; external flows, trigger links and drawn
connections need the node's DFD component; the performer needs only the node's chart, S10c-2). It applies to writes only, platform admins included. Where the
component depends on the body (a node created in a named set, an FR given a solution, an import
target), the service calls `components.require_on` itself.

Surrogate ids are sequential `bigint`s, so enumeration is trivial and looks like normal use.
**Acceptance criterion 49 walks the running app and fails on any route that declares no guard, or a
guard that does not fit its path.**

**Routes built today** (`backend/routers/`):

| Method · Path | Guard | Request | Response / rule |
|---|---|---|---|
| **Auth and administration** | | | |
| `POST /auth/login` | public | email, password, remember_me | JWT + user. Login is by email (deviation 14) |
| `GET /auth/setup` · `POST /auth/setup` | public | email, display_name, password | first-run setup: creates the first platform admin while no account exists, then disables itself |
| `GET /auth/me` | authenticated | — | the user, `user_kind`, and scope `PLATFORM_ADMIN` / `STAFF`. A project's own level comes with `GET /projects/{id}` |
| `GET /users` · `POST /users` | platform_admin | email, display_name, initial_password, **user_kind** (required) | user(s). A non-FTC address is refused (D-11) |
| `PATCH /users/{id}/kind` | platform_admin | user_kind, row_version | `USER_KIND_CHANGED` (D-40) |
| `PATCH /users/{id}/platform-admin` | platform_admin | is_platform_admin, rationale, row_version | a separate, audited act (deviation 17) |
| `PATCH /users/{id}/deactivate` | platform_admin | — | effective on the target's next request (S4) |
| `GET /clients` · `POST /clients` | platform_admin | client_code, client_name, industry | client(s) — a client list is a cross-project read |
| **Projects, components and access** | | | |
| `GET /projects` | authenticated | — | **only the projects the caller can see**: admins all; staff every live unrestricted project plus restricted ones they are a live member of (D-40, D-62) |
| `POST /projects` | platform_admin | client_id, project_code, project_name, program_id, dates, **component_codes**, template_code, data_model_depth, **is_restricted** | project. **No membership row is created.** The component list must be closed under its dependencies (422 naming the missing one); `template_code` is audit provenance only. The choice of restriction is required; the form preselects "assigned consultants only" (D-62). The ten number series and the rate card are seeded in the same transaction (R2-D14) |
| `GET /projects/{project_id}` | project_ctx(VIEW) | — | project + **`my_access_level`**, which `useCanEdit` reads |
| `PATCH /projects/{project_id}` | project_ctx(EDIT) | project_name, dates, row_version | project. `program_id` is not PATCHable; moving goes through `/programs/{id}/projects` |
| `GET /projects/{project_id}/code-master/{category}` | project_ctx(VIEW) | — | codes + labels for dropdowns, resolved two-tier via `code_master.resolve` (S10) |
| `GET /project-templates` · `GET /project-components` | authenticated | — | the templates with their components, and the component catalogue (OR-3) |
| `GET /projects/{project_id}/components` | project_ctx(VIEW) | — | each component, on or off |
| `PUT /projects/{project_id}/components` | project_ctx(ADMIN) | component_codes (the whole wanted set), confirm_hash | **without the hash:** the preview — turned on, added by dependency, turned off, blockers, hash; writes nothing (OR-2). **With it:** applied in one transaction; 409 if the preview changed or a blocker remains (a component with live rows cannot be switched off, OR-1). One `PROJECT_COMPONENTS_CHANGED` audit event |
| `PUT /projects/{project_id}/data-model-depth` | project_ctx(ADMIN) | data_model_depth, row_version | `KEYS_ONLY` / `FULL` (D-39) |
| `GET /projects/{project_id}/access` | project_ctx(ADMIN) | — | **effective access**: the platform admins, and either the members with their effective level (restricted) or the staff counts by kind plus any members listed as "applies when restricted" |
| `GET /projects/{project_id}/members` · `POST …/members` | project_ctx(ADMIN) | user_id, access_level (`EDIT`/`VIEW`), member_note | membership. Re-adding a removed member inserts a new row. Adding a VIEWER at EDIT warns: the effective level is the lower of the two |
| `PATCH /project-members/{id}` · `DELETE /project-members/{id}` | object_guard(ProjectMember, ADMIN) | access_level, row_version | level change / soft removal. Audited (`MEMBER_*`). **Not restorable** (R2-S5) |
| `PUT /projects/{project_id}/restriction` | project_ctx(ADMIN) | is_restricted, confirm_hash | preview → confirm (R2-S3 pattern): the preview names who loses, gains and keeps access, flagging kept members whose level drops; a stale hash → 409. Applies on each user's next request. `PROJECT_RESTRICTED` / `PROJECT_UNRESTRICTED` |
| **Programs** | | | |
| `GET /programs` · `POST /programs` | authenticated · platform_admin | program_code, program_name, client_id, description | programs (D-32). Programs are client-scoped roll-up groupings, not an access scope (D-40) |
| `GET /programs/{program_id}` · `GET /programs/{program_id}/projects` | program_ctx(VIEW) | — | the program, and its projects visible to the caller |
| `POST /programs/{program_id}/projects` · `DELETE /programs/{program_id}/projects/{project_id}` | platform_admin | project_id; `confirm_hash` (omit for preview) | without the hash: a preview of the roll-up change, plus its hash — writes nothing. With it: moves the project; **409 if the preview changed** (R2-S3). Audited. A project of another client → 422 |
| **Business function chart (both sets, D-47)** | | | |
| `GET /projects/{project_id}/bfc-tree?bfc_set=TO_BE\|AS_IS&include_retired=` | project_ctx(VIEW) | — | the full tree of one set, with each to-be process's `br_number` |
| `POST /projects/{project_id}/bfc-nodes` | project_ctx(EDIT); `AS_IS` checked in the service for the as-is set | parent_bfc_node_id, node_name, is_process, purpose_desc, bfc_set | node incl. generated `hier_code`. A to-be process gets its BR in the same transaction (D-2, S7-2); an as-is process gets none |
| `GET /bfc-nodes/{id}` · `PATCH /bfc-nodes/{id}` | object_guard(BfcNode; writes: set resolver) | node fields, row_version | node |
| `PATCH /bfc-nodes/{id}/reorder` | object_guard(BfcNode, EDIT) | new_seq_no, row_version | re-coded siblings and their subtrees (two-phase, S1-2) |
| `PATCH /bfc-nodes/{id}/process` | object_guard(BfcNode, EDIT) | is_process, row_version | promote / demote (D-23). Promoting a to-be node returns the new BR. Demotion is 409 naming each blocker — an active BR, step I/O, a performer, triggers (R2-P5) |
| `DELETE /bfc-nodes/{id}` · `PATCH /bfc-nodes/{id}/restore` | object_guard(BfcNode, EDIT) | row_version | soft delete, refused with active dependents (R2-D2); restore |
| `GET /bfc-nodes/{id}/retire-preview` · `POST …/retire-with-dependents` · `POST …/restore-with-dependents` | object_guard(BfcNode, EDIT) | confirm_hash | retire a step with its requirement and the rows `step_retire.OWNED` lists, in one confirmed, undoable action; restore brings them back, all or nothing (S3-SR) |
| `GET /bfc-nodes/{id}/data-entities` · `POST` · `DELETE …/{link_id}` | object_guard(BfcNode) | data_entity_id, direction | step I/O, written only through `ensure_step_io` (R2-D13). DELETE is 409 while a BR CRUD or an external flow depends on it (D-24) |
| `GET /bfc-nodes/{id}/external-flows` · `POST` · `DELETE …/{link_id}` | object_guard(BfcNode; writes: DFD resolver) | external_entity_id, direction, data_entity_id, flow_label, note | step ↔ external party flows (D-24a); linking a carried entity adds the step I/O row in the same transaction |
| `GET /bfc-nodes/{id}/org-roles` · `POST` · `DELETE …/{link_id}` | object_guard(BfcNode) | org_role_id, raci_code | step RACI — **as-is processes only**. A to-be process's roles are recorded on its BR, so a write here on a to-be step is 409 (D-64, S10d-1) |
| `PUT /bfc-nodes/{id}/performer` | object_guard(BfcNode, EDIT, set resolver — the chart's own component, whatever the DFD setting, S10c-2) | performer_kind, code, performer_label, row_version | the one performer (D-46). The body sends codes (`org_unit_code` / `org_role_code` / `application_code`), never ids; a retired target → 409. `PERFORMER_SET` |
| `GET /bfc-nodes/{id}/applications` · `POST` · `PATCH`/`DELETE …/{link_id}` | object_guard(BfcNode; writes: `APPLICATION` + `AS_IS`) | application_id, note | supporting systems of an **as-is** process (S6b-1, D-47); 422 on a to-be process, whose systems come from BR → Solution → Application (D-22). A TO_BE application warns (S6b-4) |
| `GET /projects/{project_id}/bfc-sets` | project_ctx(VIEW) | — | node and process counts per set |
| `POST /projects/{project_id}/bfc-sets/{to_set}/copy-from/{from_set}` | project_ctx(EDIT, `AS_IS`) | confirm_hash (omit for preview) | whole-tree copy into an **empty** set (409 otherwise). To-be → as-is creates no BR; as-is → to-be creates a DRAFT BR per process. RACI moves between step roles and BR roles. `BFC_SET_COPIED` |
| **Triggers and the DFD (D-38, D-49)** | | | |
| `GET /projects/{project_id}/process-triggers` · `POST` | project_ctx(VIEW / EDIT; either DFD component, in the service) | trigger_name, trigger_kind (`TIME`/`EVENT`), schedule_note, description | the project's trigger catalogue, shared by both sets |
| `PATCH /process-triggers/{id}` · `DELETE` · `PATCH …/restore` | object_guard(ProcessTrigger, EDIT) | fields, row_version | retire is 409 naming the processes it still starts |
| `GET /bfc-nodes/{id}/triggers` · `POST` · `DELETE …/{link_id}` | object_guard(BfcNode; writes: DFD resolver) | process_trigger_id, note | this trigger starts this process |
| `GET /bfc-nodes/{id}/dfd` | object_guard(BfcNode, VIEW) | — | the DFD of a non-process node's processes in its own set: lanes (one per performer, plus UNASSIGNED), processes with their supporting systems, stores, externals, triggers, flows, the **derived order** and rank, boundary stubs, completeness, saved layout (§7.14). A process node → 422 |
| `GET /bfc-nodes/{id}/dfd/export?format=mermaid&order=` | object_guard(BfcNode, VIEW) | — | the same graph as Mermaid text, one subgraph per lane, triggers as start nodes; the derived order is drawn dashed only when asked. Every label through `escape_mermaid()` (R2-S7) |
| `GET /projects/{project_id}/process-completeness?bfc_set=` | project_ctx(VIEW) | — | the gaps against the chart's DFD rule — `missing_input` (STARTED), `missing_output` (DATA_OUT), and from slice 13b `missing_data_in`, `missing_order`, `diagram_missing_external` (**block the freeze** where the element is in the rule and the set's DFD component is on, D-70, S7-3), `no_performer` (warning), `step_without_br` (to-be), `crud_without_io` and `ext_without_io` (always 0), `live_link_on_retired_step`; and `readiness` — per process its light and `dfd_missing` codes (D-68). The tree read (`bfc-tree`) carries `dfd_light` and `dfd_missing` on each process row |
| `GET` · `PUT` · `DELETE /projects/{project_id}/diagram-layouts/{diagram_type}/{scope_key}` | project_ctx(VIEW / EDIT) | [{object, x, y, w, h, collapsed}], at most 2,000 | saved positions (D-30). PUT upserts only the listed objects; DELETE resets the diagram (audited). `diagram_type` is `ERD` or `DFD` |
| **Business requirements** | | | |
| `GET /projects/{project_id}/business-requirements?include_retired=` | project_ctx(VIEW) | — | BRs. **There is no create route**: a BR appears with its to-be process (D-2) |
| `GET /business-requirements/{id}` · `PATCH` | object_guard(BusinessRequirement) | br_statement, business_logic, output_expectation, status_code, row_version | BR. `BASELINED` / `SUPERSEDED` are refused (422, S1-8) |
| `DELETE /business-requirements/{id}` · `PATCH …/restore` | object_guard(BusinessRequirement, EDIT) | row_version | soft delete with refuse-with-dependents; restore |
| `GET /business-requirements/{id}/data-entities` · `POST` · `DELETE …/{link_id}` | object_guard(BusinessRequirement) | data_entity_id, crud_code | BR CRUD; `direction` is returned, never sent. A missing step I/O row is added in the same transaction (D-24) |
| `GET /business-requirements/{id}/org-roles` · `POST` · `DELETE …/{link_id}` | object_guard(BusinessRequirement) | org_role_id, raci_code | the to-be process's RACI (D-64). One ACCOUNTABLE-behaviour role per BR, held by the database (R2-D9) |
| `GET /data-entities/{id}/business-requirements` | object_guard(DataEntity, VIEW) | — | the BRs that use an entity, with CRUD |
| **Solutions** | | | |
| `GET /projects/{project_id}/solutions` · `POST` | project_ctx(VIEW / EDIT, `SOLUTION`) | solution_name, description, category_code | solution incl. generated `solution_number`; names unique among live solutions (S5-5) |
| `GET /solutions/{id}` · `PATCH` · `DELETE` · `PATCH …/restore` | object_guard(Solution; writes: `SOLUTION`) | fields, row_version | solution |
| `GET /solutions/{id}/business-requirements` · `GET /business-requirements/{id}/solutions` | object_guard(…, VIEW) | — | the BR ↔ Solution links, each showing the solution's status (S5-2) |
| `POST /business-requirements/{id}/solutions` · `PATCH`/`DELETE …/{link_id}` | object_guard(BusinessRequirement, EDIT, `SOLUTION`) | solution_id, coverage_note · coverage_note, row_version | link; the note is edited in place (S5-3). DELETE returns the drift warnings of FRs whose tag now answers none of their BRs |
| **Function requirements and BR ↔ FR (D-52)** | | | |
| `GET /projects/{project_id}/function-requirements?unlinked=&unassigned=&include_retired=` | project_ctx(VIEW) | — | FRs with `br_count`. `unlinked` = no live BR link (untraced); `unassigned` = no solution |
| `POST /projects/{project_id}/function-requirements` | project_ctx(EDIT, `FUNCTION_REQUIREMENT`; `SOLUTION` when a solution is given) | fr_name, fr_type_code, description, acceptance_note, solution_id, br_id | FR incl. generated `fr_number`. A `br_id` creates the link in the same transaction. Warnings: `no_br`, a REJECTED or non-TECHNOLOGY solution, a duplicate name (S6a-2) |
| `GET /function-requirements/{id}` · `PATCH` | object_guard(FunctionRequirement; writes: `FUNCTION_REQUIREMENT`) | FR fields incl. fr_type_code, fulfilment_status_code, solution_id, row_version | FR. A type change re-derives `effort_days`, and is 409 when moving an FR with live interface detail away from INTERFACE behaviour. `effort_days` in a body is ignored. A solution set from the register must answer at least one of the FR's BRs (any, if it has none) |
| `DELETE /function-requirements/{id}` · `PATCH …/restore` | object_guard(FunctionRequirement, EDIT, `FUNCTION_REQUIREMENT`) | row_version | **409 naming the BRs while live links exist** (S10b-2); 409 while live interface detail exists (S6b-3). Restore needs `EFFORT` on for a rated FR and `SOLUTION` for a tagged one |
| `GET /solutions/{id}/function-requirements` | object_guard(Solution, VIEW) | — | the FRs tagged with the solution |
| `GET /business-requirements/{id}/function-requirements` · `POST` · `PATCH`/`DELETE …/{link_id}` | object_guard(BusinessRequirement; writes: `FUNCTION_REQUIREMENT` only, so a project without Solutions can map) | fr_id, coverage_note · coverage_note, row_version | **the direct BR ↔ FR link.** Relinking a pair restores its row (S1-7). DELETE returns drift warnings |
| `PUT /business-requirements/{id}/function-requirements/{link_id}/solution` | object_guard(BusinessRequirement, EDIT, `FUNCTION_REQUIREMENT`; `SOLUTION` when setting one) | solution_id or null, fr_row_version | the FR's solution tag, chosen from this BR's row: **one of this BR's live solutions, or none** (422 otherwise). Stored once on the FR, so its effort counts once |
| `GET /function-requirements/{id}/business-requirements` | object_guard(FunctionRequirement, VIEW) | — | the BRs an FR serves |
| **Effort (D-13)** | | | |
| `GET /projects/{project_id}/rate-card` · `PUT` | project_ctx(VIEW / EDIT, `EFFORT`) | cells (FR type × complexity × days), **change_rationale**, confirm_high | the effort rate card (S6c-3: any User). Refused without a rationale; a cell above 60 man-days needs confirmation (S6c-7); audited old → new (R2-D7). **Never reprices a rated FR**; the response says how many are not at the current rate (S6c-2) |
| `PATCH /function-requirements/{id}/complexity` | object_guard(FunctionRequirement, EDIT, `FUNCTION_REQUIREMENT` + `EFFORT`) | complexity_code, row_version | FR incl. derived `effort_days`; 422 naming a missing rate-card cell |
| `GET /projects/{project_id}/effort-summary` | project_ctx(VIEW) | — | man-days by FR type and by solution, with an **Unassigned** bucket (no solution), FRs under a REJECTED solution shown apart (S6c-8), an informational **untraced** line never added into totals, and per-cell "not at current rate" counts (S6c-5) |
| **Applications and interfaces** | | | |
| `GET /projects/{project_id}/applications` · `POST` | project_ctx(VIEW / EDIT, `APPLICATION`) | application_code, name, vendor, version_label, kind_code, lifecycle_code, description | application catalogue. Codes are upper-case, unique, editable until a baseline freezes them (S6b-2, S6b-6, S6b-7) |
| `GET /applications/{id}` · `PATCH` · `DELETE` · `PATCH …/restore` | object_guard(Application; writes: `APPLICATION`) | fields, row_version | application; a lifecycle move to TO_BE warns about as-is support (S6b-5) |
| `GET /applications/{id}/solutions` · `GET /applications/{id}/bfc-nodes` | object_guard(Application, VIEW) | — | where an application is allocated and where it supports today |
| `GET /solutions/{id}/applications` · `POST` · `PATCH`/`DELETE …/{link_id}` | object_guard(Solution; writes: `SOLUTION` + `APPLICATION`) | application_id, note | to-be allocation. An `AS_IS` application → 422 |
| `GET` · `PUT` · `DELETE /function-requirements/{id}/interface` | object_guard(FunctionRequirement; writes: `FUNCTION_REQUIREMENT` + `APPLICATION`) | source and target application, pattern, method, frequency, volume_note, carried data entities with notes, row_version | interface detail. 422 unless the type's behaviour is INTERFACE (D-27); refused on a retired FR. Every PUT bumps the detail's `row_version` |
| `GET /projects/{project_id}/interfaces?source=&target=&status=` | project_ctx(VIEW) | — | **the generated interface list** (D-27). Complete = source, target, method and at least one carried entity (S6b2-1); the pair filter is direction-as-stored, BIDIRECTIONAL matches either way (S6b2-3) |
| **Data entities, fields and the ERD** | | | |
| `GET /projects/{project_id}/data-entities` · `POST` | project_ctx(VIEW / EDIT) | de_name, description, business_owner_note | DE incl. generated `de_number` and live field count |
| `GET /data-entities/{id}` · `PATCH` · `DELETE` · `PATCH …/restore` | object_guard(DataEntity) | fields, row_version | DE |
| `GET /data-entities/{id}/fields` · `POST` · `PATCH /data-fields/{id}` · `DELETE /data-fields/{id}` · `PATCH /data-fields/{id}/restore` | object_guard(DataEntity / DataField) | field fields (name, type, key flags, FK target, `fk_group`), row_version | data field. The request names an FK relationship (`new` or an existing group); the service assigns `fk_group_no` (S1-7) |
| `GET /projects/{project_id}/erd?subject_area={bfc_node_id}` · `/erd/export?format=mermaid` | project_ctx(VIEW) | — | the logical ERD graph with derived cardinality and saved layout (D-29); Mermaid `erDiagram` text through `escape_mermaid()` |
| **External parties and the client organisation** | | | |
| `GET /projects/{project_id}/external-entities` · `POST` · `PATCH /external-entities/{id}` · `DELETE` · `PATCH …/restore` | project_ctx / object_guard(ExternalEntity) | ext_name, kind_code, description | external parties incl. `EXT-0001` (D-24a) |
| `GET /projects/{project_id}/org-units` · `POST` · `PATCH /org-units/{id}` · `DELETE` · `PATCH …/restore` | project_ctx / object_guard(OrgUnit) | org_unit_code, org_unit_name, level_code, parent, description | the client's org tree. Retiring a unit that performs a live process → 409 naming the processes |
| `GET /projects/{project_id}/org-roles` · `POST` · `PATCH /org-roles/{id}` · `DELETE` · `PATCH …/restore` | project_ctx / object_guard(OrgRole) | org_role_code, org_role_name, org_unit, responsibility_desc, headcount | positions |
| **Imports — one pipeline (§7.11, VB law 8)** | | | |
| `GET /projects/{project_id}/bulk/templates/{target}` | project_ctx(EDIT) | — | `.xlsx` template with **that project's** resolved `code_master` dropdowns (D-5, D12). `target` = `data-entities`, `data-fields`, or `data-model` (both sheets, S4-12) |
| `GET /projects/{project_id}/bulk/{target}/export` | project_ctx(VIEW) | — | current rows in template shape, each with a signed row token (S4-11) |
| `POST /projects/{project_id}/bulk/{target}/check` | project_ctx(EDIT) | the raw `.xlsx` body | file-level checks only; nothing is staged |
| `POST /projects/{project_id}/bulk/{target}/validate` | project_ctx(EDIT) | the raw `.xlsx` body (never multipart); display name in `X-VB-File-Name` | `IMPORT_BATCH` + the preview. **Writes nothing to business tables.** Body capped at ingress at 10 MB (R2-S8, `ROUTE_CAPS`) |
| `GET /bulk/batches/{batch_id}` · `GET /bulk/batches/{batch_id}/preview` | object_guard(ImportBatch, EDIT) | — | the batch, and per-row INSERT / UPDATE / MATCH verdicts with before/after per changed field (P3, D3) |
| `POST /bulk/batches/{batch_id}/commit` | object_guard(ImportBatch, EDIT) | row_version, `acknowledged_inserts`, `acknowledged_retires` | applies the batch in one transaction, under a row lock, re-validating every row (P2, D1, D3). **422 unless each of `acknowledged_inserts` and `acknowledged_retires` is acknowledged whenever its count is non-zero** (R2-P2). Any project editor may commit a batch another uploaded |
| **Baselines (always on, no component; slice8_schema §5)** | | | |
| `GET /projects/{project_id}/baselines` | project_ctx(VIEW) | — | headers, newest first, with the agreed one marked |
| `GET /projects/{project_id}/baselines/next?bump=MINOR\|MAJOR` | project_ctx(VIEW) | — | the freeze preview: next label, the confirm text, errors, freeze-blocking warnings, warnings, counts by entity. Writes nothing |
| `POST /projects/{project_id}/baselines/freeze` | project_ctx(EDIT) | note, `bump: MINOR\|MAJOR`, `confirm_text` (project code + version), preview_digest | a new FROZEN baseline over every `FREEZE_SET` table whose component gate is open (S8-1, S8-3). Typed confirmation; refused while consistency reports errors or freeze-blocking warnings (P6, D11, D-38); warnings are returned and audited. Runs at REPEATABLE READ (R2-P6) |
| `GET /baselines/{id}` · `GET /baselines/{id}/rows/{entity}?offset=&limit=` | object_guard(Baseline, VIEW) | — | header, components on, counts per entity; the snapshot rows of one frozen entity (labels shown, never code ids). Every read re-verifies the stored digest |
| `POST /baselines/{id}/approve` | object_guard(Baseline, EDIT) | client_approver_name, client_approved_on, approval_note, approval_reference, row_version | records the client's sign-off once; only a FROZEN baseline; no un-approve, no reopen |
| `GET /projects/{project_id}/baselines/diff?from={a}&to={b\|live}[&priced=true]` | project_ctx(VIEW) | — | ADDED / CHANGED / REMOVED / **MOVED** per entity, with `component_on` for each side; an entity whose hashed list grew between the two specs is compared on the older list, with `compared_on_spec` and `not_compared` (Q-22, with slice 13c). **404 unless both baselines belong to this project** (S3). `priced=true` adds effort deltas (D-13, R2-D3) only where `EFFORT` is on in both sides |

No `PATCH`, `PUT` or `DELETE` route exists on a baseline or a shadow table.

**Routes owed to later waves** (§12.1). Each keeps the guard and level shown; a write names its
component.

| Method · Path | Guard | Request | Response / rule |
|---|---|---|---|
| **Slice 13b–13d — the DFD rule, process volume, drawing on the DFD (D-65, D-67, D-70)** | | | |
| `GET /projects/{project_id}/dfd-rule` | project_ctx(VIEW) | — | per chart: the required elements, `rule_applies`, locked and recommended flags; the catalogue; the project's `row_version` (D-70) |
| `POST /projects/{project_id}/dfd-rule/preview` | project_ctx(ADMIN) | bfc_set_code, codes | for that chart: ready / partly / not ready / would block, and `preview_digest`. No write |
| `PUT /projects/{project_id}/dfd-rule` | project_ctx(ADMIN) | bfc_set_code, codes, row_version, preview_digest | the chart's rule; 409 on a stale `row_version` or digest; 422 if STARTED is dropped or ORDER lacks DATA_IN and DATA_OUT. `PROJECT_DFD_RULE_CHANGED` (D-70, Q-5) |
| `POST /bfc-nodes/{id}/hand-offs` | object_guard(BfcNode, EDIT, DFD resolver) | to_bfc_node_id, data_entity_id | a hand-off drawn on the canvas: this process's output and the other process's input, in one transaction through `ensure_step_io`. 422 across charts; 404 for a process the caller cannot see (D-65). Every other drawn connection uses the existing step I/O, external-flow and trigger routes |
| `PATCH /bfc-nodes/{id}/volume` | object_guard(BfcNode, EDIT, set resolver) | runs_per_period, volume_period_code, transactions_per_run, transaction_unit_code, seconds_per_transaction, row_version | the process with its derived `annual_hours`, `fte` and `incomplete`. Hours or FTE in the body → 422 (`extra="forbid"`); a non-process node → 422. `PROCESS_VOLUME_SET` |
| `PUT /projects/{project_id}/fte-basis` | project_ctx(ADMIN) | working_days_per_year, hours_per_working_day, row_version | the FTE basis (default 240 × 8). `PROJECT_FTE_BASIS_CHANGED` |
| `GET /projects/{project_id}/volume-summary` | project_ctx(VIEW) | — | per chart, hours and FTE per L1 / L2 area, as-is beside to-be, matched by code and name; unmatched areas with their reason; incomplete processes listed (Q-28) |
| **Slice 11 — structured BR, attribute usage, system-to-system flows (D-59, D-60b, D-61)** | | | |
| BR requirement lines · attribute ticks in the CRUD grid · BR system flows · "Create interface FR from these flows" | object_guard(BusinessRequirement, EDIT; flows: `APPLICATION`; the seeding action: `FUNCTION_REQUIREMENT` + `APPLICATION`) | line_kind_code, priority_code, line_text, seq_no · attribute ticks with the entity ticks in one request · data_entity_id, source/target application, flow_note | §4.3. Line numbers, the BR's priority and flow coverage are derived, never sent. `PATCH /business-requirements/{id}` then accepts `br_statement` and status only. Route shapes fixed by the slice 11 build |
| **Wave 1e — imports 4b–4d** | | | |
| `POST /projects/{project_id}/bulk/{target}/validate` for `business-requirements`, `function-requirements`, `issues` | project_ctx(EDIT) | as above | BRs keyed by **BR number**, `hier_code` a cross-check (R2-D1); FRs (R2-D6) create BR links from BR numbers (D-52) and never create a SOLUTION; `effort_days` is export-only. FR target needs `FUNCTION_REQUIREMENT` |
| `GET /process-flow-json/schema` | authenticated | — | the `vb-process-flow/2.0` JSON Schema, an example, and the AI conversion prompt pack. The pack names **Claude or Microsoft Copilot under FTC's own accounts only** and opens with the personal-data removal step (D-25, D-36) |
| `POST /projects/{project_id}/bulk/process-flow/validate` | project_ctx(EDIT; the anchor's set decides the component) | JSON file, **`anchor_bfc_node_id`, `mode`** (merge \| replace), chosen in the UI | `IMPORT_BATCH` + per-item errors and warnings. Steps carry performer, inputs, outputs, triggers and external flows; **no edges, no lanes**. An imperfect DFD imports with warnings (D-55). **A file whose anchor or mode disagrees with the route → 422, nothing staged** (R2-P3); a `1.0` file is refused. Body cap 2 MB. Commit adds `acknowledged_retires` in replace mode |
| `GET /bfc-nodes/{id}/dfd/export?format=json` | object_guard(BfcNode, VIEW) | — | the flow under a node as `vb-process-flow/2.0`, every existing step with `br_number`, `hier_code` and `row_version` (R2-D1, R2-D5), so a flow round-trips |
| **Issues and stakeholders (component `ISSUE` for issues)** | | | |
| `GET/POST /projects/{project_id}/stakeholders` · `PATCH/DELETE /stakeholders/{id}` | project_ctx / object_guard(EDIT) | name, title, org_unit_id, is_bpo | client-side people with no login (D-4) |
| `GET/POST /projects/{project_id}/issues` · `PATCH /issues/{id}` | project_ctx / object_guard(EDIT, `ISSUE`) | issue fields, br_ids | issue incl. generated `issue_number`; raiser and recorder both required (D8) |
| **Wave 1f — reports, program roll-ups, PDF (D-42)** | | | |
| `GET /projects/{project_id}/traceability` | project_ctx(VIEW) | — | step → BR → BR ↔ FR link → FR, with the FR's solution tag and its applications; untraced FRs grouped last |
| `GET /projects/{project_id}/solution-matrix` · `/application-gap` · `/coverage` · `/consistency` | project_ctx(VIEW) | — | solutions by category × L1 area (D-7); as-is vs to-be backlog (D-8); the scope-gap report (§4.3); `hier_code` drift and completeness (D11) |
| `GET /projects/{project_id}/interfaces/export` | project_ctx(VIEW) | filters | the interface list as `.xlsx`, through `escape_cell()` |
| `GET /programs/{program_id}/dashboard` · `/counts` · `/interfaces` · `/effort` · `/control-status` · `/plan-vs-actual` | program_ctx(VIEW) | — | lists of `{project, result}`, one per project in the program visible to the caller, each built by the per-project report (R2-S2). A restricted project the caller is not on is omitted, uncounted |
| `PATCH /programs/{program_id}` | platform_admin | program fields | program |
| PDF export of each client-facing report | project_ctx(VIEW) | — | prints project, baseline version or "LIVE — not a baseline", time and author; audited (D-42, OR-8). Route shapes fixed by the 1f spec |
| **Control rules and the control panel (D-19)** | | | |
| `GET/PUT /control-rules/defaults` | platform_admin | analysis_code, threshold, escalate, action | **the FTC house defaults** (`project_id IS NULL`); affect future projects only |
| `GET/PUT /projects/{project_id}/control-rules` · `POST …/control-rules/reset` | project_ctx(VIEW / EDIT) | analysis_code, threshold, escalate, owner org role, action, is_enabled, **change_rationale** | the project's agreed governance. Every change needs a rationale and is audited; reset re-copies the house defaults |
| `GET /projects/{project_id}/control-panel` · `GET /projects/{project_id}/analysis/{analysis_code}` | project_ctx(VIEW) | — | **every analysis vs its rule → GREEN / FLAG / ESCALATE, with owner and action. The PMO's one screen**; any single analysis with its `headline_value` |
| **Wave 1g — code maintenance** | | | |
| `GET/PUT /projects/{project_id}/code-master/FR_TYPE` | project_ctx(VIEW / EDIT) | code, label, behaviour, sort, is_active | the project's FR types (D-27). Behaviour immutable once referenced (R2-D8) |
| `PUT /code-master/FR_TYPE` | platform_admin | as above | the global tier |
| **Wave 2 — benefits, change requests, WBS** | | | |
| `GET/POST /projects/{project_id}/benefits` · `PATCH/DELETE /benefits/{id}` · `POST/DELETE /benefits/{id}/solutions` | `BENEFIT` | benefit fields; solution_id, contribution_pct | benefit incl. `BEN-0001` (D-14) |
| `GET /projects/{project_id}/value-ranking` | project_ctx(VIEW) | — | value ÷ effort per solution, **one ranking per `measure_unit`** (D-14, R2-D12, Q9) |
| `GET/POST /projects/{project_id}/change-requests` · `PATCH /change-requests/{id}` | `CHANGE_REQUEST` | CR fields | CR incl. `CR-0001` (D-16); target baseline FROZEN or APPROVED, or the SUPERSEDED one carrying the agreed approval (Q8, SC-2) |
| `POST /change-requests/{id}/analyse` · `GET …/price` · `POST …/decide` | object_guard(ChangeRequest, EDIT) | seed objects · — · outcome, displaces_cr_id, rationale, alternative_rejected | the blast radius (`CR_IMPACT`); effort and benefit delta, phases hit, displacement candidates; the decision. **`decide` refuses net-positive effort with no displacement named (422)** and writes a `DECISION` row |
| `GET/POST /projects/{project_id}/decisions` | project_ctx(VIEW / EDIT) | decision fields | the decision log (D-17); corrections are new rows |
| `POST /projects/{project_id}/bulk/wbs/validate` · `GET /projects/{project_id}/wbs` · `PATCH /wbs-items/{id}` | project_ctx / object_guard(EDIT, `WBS`) | `.xlsx`, `import_mode` · filters · phase_id, solution_id, row_version | WBS keyed by MS Project Unique ID (D-33, R2-D15); **links only by PATCH** — any other field → 422 "Change it in MS Project and re-import". Progress updates are new dated rows, never overwritten by an import (D-41, OR-7); the progress report is generated from them |
| **Wave 3 — risks and phasing** | | | |
| `GET/POST /projects/{project_id}/risks` · `PATCH /risks/{id}` · `POST /risks/{id}/materialise` | `RISK` | risk fields · description | risk incl. `RSK-0001`, derived `exposure_score` (D-15); materialise creates and links an issue and leaves the risk row |
| `GET/POST /projects/{project_id}/phases` · `PATCH/DELETE /phases/{id}` · `POST/DELETE /solutions/{id}/phases` · `/dependencies` · `GET /projects/{project_id}/phase-plan` | project_ctx / object_guard(EDIT) | phase fields · phase_id · depends_on_solution_id | delivery waves and prerequisites, cycles rejected (D-18); effort by phase, dependency violations, volatile areas still in the current wave |
| **Before first client use** | | | |
| `POST /projects/{project_id}/purge` | platform_admin | reason, `confirm_text` (the project code) | contract-required deletion (Q15, §15.3): deletes live and snapshot rows as `vb_owner` and destroys the project's archive key. The one hard-delete route of business data |
| client read-only login and the offline viewer file (D-43) | — | — | client viewers see their own project only; the offline file is generated from a frozen baseline at `EDIT`, never `VIEW`, after recorded client consent (OR-9). Routes fixed by that slice's spec |

Deciding a change request and resetting a project's control rules to the house defaults are **EDIT** — project
editors, and admins always (SC-7). The FTC default rate card is a fixed default in code with no admin route (SC-10).

---

## 10. Acceptance criteria

Each is observable by someone who did not build it.

1. A BFC node cannot be created below level 5; the attempt returns 422 with a `detail`
   string naming the limit.
2. Creating the third child of node `01.02` produces `hier_code = "01.02.03"`, and the code
   appears only after save — never on the empty form.
3. Reordering `01.02` to position 1 renumbers its siblings **and** re-codes every
   descendant; no orphaned or duplicate code remains in the project's set.
4. A process node accepts a data-processing description; a non-process node rejects it.
5. Creating a to-be process node creates exactly one business requirement in the same
   transaction; creating a non-process node, or an as-is process, creates none (S7-2).
5a. A second business requirement on a process node is rejected by the database, not the UI
   (D-2), and so is a BR on an as-is node (S7-2). Dropping `UNIQUE (bfc_node_id)` makes the
   second BR succeed — that is the documented reversal path.
6. Two data entities created concurrently in one project receive different DE numbers; no
   duplicate `de_number` exists within a project under a 20-way concurrent create.
7. A data field flagged foreign key without a target entity is rejected; a target entity in
   a different project is rejected.
8. A data entity can be linked to one BR as both `R` and `U`, producing two rows whose
   generated `direction` reads INPUT and OUTPUT respectively. An attempt to store `R`
   against OUTPUT is impossible by construction, not by validation.
9. A function requirement rejects an `fr_type_code` not present in `code_master` category
   `FR_TYPE`. Creation with no BR link is accepted with a `no_br` warning; creation with no
   solution is accepted with no solution warning (D-28, D-52).
10. A solution of category `PEOPLE` can be created, linked to two BRs, and carry **no**
    function requirements at all — and the traceability report still reports it as a
    complete answer. *(This is the acceptance criterion for "blueprints the whole operation,
    not just the software".)*
10a. One FR linked directly to three BRs yields three rows in `v_br_function_requirement`; a
    BR → Solution → FR path with no direct link yields none. The FR's effort counts once,
    toward its one solution tag, and is never summed by BR (D-52).
10b. `solution_matrix` on a project with five TECHNOLOGY solutions and no ORG_AND_RULES
    solution shows an empty Organization & Rules column — the finding is visible, not
    buried.
10c. An application flagged `AS_IS` is rejected when allocated to a solution; one flagged
    `BOTH` is accepted.
10d. `application_gap` on a process step that has an as-is application and no to-be allocation
    lists that step under `unallocated`.
11. An issue linked to two BRs appears under both in the issue list.
11a. An issue records a stakeholder as raiser and the logged-in consultant as recorder;
    the two fields are independently queryable and neither is derived from the other (D-4).
12. Closing an issue with an empty resolution returns 422.
12a. Downloading the Issue template yields an `.xlsx` whose severity column is a dropdown
    of that project's `code_master` values.
12b. Uploading an issue sheet with one invalid severity stages the batch, reports the error
    against the correct **sheet row number**, and writes nothing to the `issue` table.
12c. Committing that batch is refused until the row is fixed; a rejected batch does not
    consume an issue number.
12d. Exporting Data Fields, changing one description, and re-uploading updates that row
    rather than creating a duplicate.
12e. An upload whose business key belongs to another project fails validation — it does not
    silently write across the project boundary.
13. Freezing a baseline on a project with 40 BFC nodes, 25 BRs, 12 solutions, 30 FRs, 15
    data entities and 10 issues creates one baseline row and snapshot rows across **every
    table in `FREEZE_SET` whose component gate is open**, in a single transaction (S8-3).
14. After freezing v1.0, editing a live BR does **not** change the v1.0 snapshot.
15. A freeze that fails partway leaves zero snapshot rows and no baseline header.
16. Adding one BR and deleting another, then freezing v1.1, makes `diff(v1.0, v1.1)` report
    exactly one ADDED and one REMOVED.
17. Editing a BR's logic text between freezes makes the diff report it CHANGED, naming the
    `logic_text` field.
17a. Renaming a data entity between freezes makes the diff report the DE as CHANGED (D-3).
17b. Two sessions PATCH the same BR with the same `row_version`; the first succeeds, the
    second returns 409 with a `detail` string, and the first write is not lost (D-6).
18. A non-admin who is not a live member of restricted project P receives **404** for
    `GET /projects/P`, and P does not appear in `GET /projects` (D-40, OR-6).
18a. A VIEWER sees every unrestricted project in `GET /projects`. Restricting a project first
    previews who loses access; after the confirm, the project is hidden from each of them on
    their next request.
19. A VIEWER receives 403 on any write to a project they can see.
19a. A VIEWER added as a member at `EDIT` still receives 403 on writes: the effective level is
    the lower of the kind's cap and the membership's level.
20. Every VB endpoint except `POST /auth/login` and first-run setup returns 401 without a
    valid JWT.
21. The app refuses to start when `JWT_SECRET_KEY` is unset (§9.1).
22. `created_by` on a newly created BR equals the JWT subject, even when the request body
    carries a different user id (§9.2).
23. Deleting a business requirement sets `is_active = FALSE`; the row remains queryable and
    prior baselines are unaffected.
24. Creating a to-be process node auto-creates its first business requirement in the same
    transaction; creating a non-process node creates none.
25. A second Accountable (`A`) role on one BR is rejected by the database, not the UI.
26. A frozen `baseline_*` row cannot be updated or deleted, including by direct SQL —
    the reject trigger fires.
27. A CI test asserts, against the database, that every `baseline_*` table's column set matches
    its live table (minus audit columns, plus snapshot columns). A migration that adds a column
    to a shadowed live table without the shadow column fails the build.
28. Renaming the `code_master` label "High" to "Major" changes the live issue list and
    leaves every frozen baseline reading "High".
29. Every VB screen renders the Fortience Consulting Inc. footer (§9.9).

### Concurrency, integrity and security

30. **(P1)** An edit committed while a freeze is running appears in neither half of that
    baseline — the freeze reflects one consistent snapshot across every table in `FREEZE_SET`
    whose component gate is open (S8-3).
31. **(P2)** Committing the same import batch twice applies it once; the second call
    returns 409. Two concurrent commits of one batch produce one set of rows.
32. **(P3, D3)** The preview states, per row, INSERT or UPDATE, and shows before/after for
    every changed field. A batch that would create rows cannot be committed without
    acknowledging the exact insert count.
33. **(P4, D-10)** Reordering a node whose subtree is 47 nodes deep produces a diff of
    **48 MOVED and 0 CHANGED**.
34. **(P5)** A soft-deleted business requirement can be restored, and while it is deleted a
    replacement BR can be created on that process node.
35. **(P6)** Freeze is refused to a VIEWER, refused without the typed confirmation, and
    refused while `consistency_check` reports drift or a freeze-blocking warning (D-38, S7-3).
36. **(P7)** Moving the third sibling to position one succeeds, with no unique-index
    violation at any point, and every descendant's `hier_code` is recomputed.
37. **(P9)** The tenth freeze on a project is `v1.10`, not `v2.0`; a `MAJOR` bump yields
    `v2.0`; two simultaneous freezes produce one baseline and one 409.
38. **(P10)** A unique-constraint violation returns 409 with a `detail` string, never a 500.
39. **(D1)** Validating a Data Field batch, then soft-deleting the parent DE, then
    committing → the batch is rejected. No live field exists under a dead entity.
40. **(D2)** Exporting rows, editing one in the app, then re-uploading the export → that
    row is a **validation error naming the current value**. A commit is all or nothing, so
    the other rows commit after the corrected file is re-uploaded (S4-10).
41. **(D5, Q-22)** Two baselines with different `hash_spec_version` never report "everything CHANGED"
    (S8-3): an entity whose hashed list grew is compared on the older list and names the columns not
    compared. Emptying a text field reports CHANGED, not unchanged.
42. **(D6)** An import row whose raiser name matches no stakeholder, or matches two, is a
    validation error. No stakeholder is ever created from a spreadsheet cell.
43. **(D8)** An issue cannot be created without a raiser; `raised_by_stakeholder_id` and
    `recorded_by_user_id` are both `NOT NULL` and independently queryable.
44. **(D9)** A data field cannot reference a data entity in another project — rejected by
    the database, with the service check removed to prove it.
45. **(D10)** An issue resolved at 06:30 ICT on the 18th records the 18th, not the 17th. An
    import date column not in `YYYY-MM-DD` is a validation error.
46. **(D11)** `GET /projects/{id}/consistency` reports a node whose `hier_code` does not
    match its parent chain, and freeze is blocked until it is clean.
47. **(D12)** A project override of `ISSUE_SEVERITY` appears in the import template's
    dropdown, passes the import validator, and shows in the React dropdown — all three read
    it from `code_master.resolve`.
48. **(S1, D-9, D-40)** A VIEWER is refused every write, baseline freeze included; a User is
    refused the admin functions (members, restriction, components, users); a platform admin
    passes every level check.
49. **(S2, S7, R2-S1)** **The route-coverage test.** It walks every route **registered in
    the running app** — not a list in §9 — and fails if any route declares **no guard**, or
    more than one, or if the declared guard is not really attached as a dependency. It also
    fails if the declared guard does not fit the path: a `{project_id}` path not guarded by
    `project_ctx` (one named exception: `DELETE /programs/{program_id}/projects/{project_id}`,
    platform admin); a `{program_id}` path not guarded by `program_ctx` or `platform_admin`; any
    other `{…id}` path guarded by anything other than `object_guard`, `program_ctx` or
    `platform_admin`; a `project_ctx`, `program_ctx` or `object_guard` with no minimum level;
    **a write guarded at `VIEW`**; or `public` on any route but `POST /auth/login` and
    `GET`/`POST /auth/setup`. An `object_guard` on a model with no `owning_project_id()`, and a
    route registered with no guard, fail at import time. *This test is the stated condition of
    deferring row-level security.*
49b. **(D-37)** Every non-GET route whose path carries a component's fragment
    (`ROUTE_COMPONENTS` in `tests/test_route_guards.py`: solutions, function requirements, BR ↔ FR
    links, applications, rate card, complexity, interface detail, as-is support, chart copy)
    declares that component in its guard marker, restore routes included; external flows, step
    trigger links and the drawn hand-off declare the node's DFD resolver, and the performer and the
    volume figures the node's set resolver (S10c-2). A write that forgets fails CI.
49c. **(D-37)** A write to a component that is off returns 409 `COMPONENT_OFF` only after
    visibility (404) and level (403) are decided, platform admins included.
50. **(S3)** `GET /projects/{project_id}/baselines/diff?from={a}&to={b}` returns 404 when either
    baseline belongs to another project, and when the project is restricted and the caller is
    not on it.
51. **(S4)** A deactivated user's existing token is rejected on the next request. Revoking
    platform admin takes effect on the next request without re-login.
52. **(S5)** An issue description beginning `=HYPERLINK(...)` exports as an inert text cell.
53. **(S8, D-11)** Creating an app user with a non-FTC email address is refused, and no client
    account kind exists to grant (`user_kind` is `USER` or `VIEWER`) until D-43 is built.
54. **(S9)** Freezing a baseline, reordering the chart, soft-deleting a row and removing a
    project member each write an `AUDIT_EVENT`.
55. **(S11)** The application database role cannot `UPDATE` or `DELETE` any `baseline_*`
    row, tested by attempting it directly.

### Control framework (D-13…D-19)

56. **(D-13)** Setting an FR's complexity to COMPLEX stores `effort_days` from the rate
    card. Changing the rate card afterwards does **not** change that FR's `effort_days`.
57. **(D-13)** A baseline frozen before a rate-card change and one frozen after report the
    same `effort_days` for an unchanged FR — a signed baseline cannot be repriced.
58. **(D-13)** `GET /projects/{id}/baselines/diff?priced=true` on a v1.1 that added two COMPLEX
    forms and removed one SIMPLE report returns the correct net man-days, not a row count.
59. **(D-14)** A benefit cannot be saved without an accountable org role.
60. **(D-14)** `value_ranking` on a project with one high-value/low-effort solution and one
    low-value/high-effort solution ranks them in that order, and names the second as a
    displacement candidate.
61. **(D-15)** A risk scored LIKELY × MAJOR carries a higher `exposure_score` than
    POSSIBLE × MODERATE, and the score cannot be edited independently of its inputs.
62. **(D-15)** Materialising a risk creates an issue, links it, sets the risk to
    MATERIALISED, and **leaves the risk row present** — the evidence it was foreseen.
63. **(D-16, Q8, SC-2)** A change request cannot be raised against a working set, nor against a
    SUPERSEDED baseline without the agreed approval (422). Against a FROZEN or an APPROVED baseline, or the
    SUPERSEDED baseline that carries the newest recorded client approval, it is accepted.
64. **(D-16)** `analyse` on a CR seeded with one BR returns impacted Solutions, FRs,
    Applications, Data Entities and Phases without any of them being typed by hand.
65. **(D-16)** Approving a CR with a positive effort delta, no `displaces_cr_id` and no
    recorded budget increase returns **422**. *This is the control: a refused write, not a
    warning.*
66. **(D-17)** Every CR decision writes a `DECISION` row carrying the rejected alternative
    and the analysis it was taken against.
67. **(D-18)** Linking solution A to depend on B, then B on A, is rejected as a cycle.
68. **(D-18)** `phase_plan` flags a solution scheduled in a phase at or before its
    prerequisite's phase.
69. **(D-19)** A control rule naming an `analysis_code` outside the registry is rejected.
70. **(D-19)** A control rule cannot be saved without an owning org role.
71. **(D-19)** With `priced_diff` flagged at 5% and escalating at 10%, a project at 7%
    growth returns **FLAG**, at 12% returns **ESCALATE**, and each row carries the owning
    role and the prescribed action.
72. **(D-19)** An L1 area whose BRs changed in two consecutive baselines appears in
    `requirement_volatility` and raises its control rule to FLAG.
73. **(D-19)** An org unit in the top decile of `org_impact_heatmap` with zero issues raised
    appears in `stakeholder_engagement` as ESCALATE — the adoption-risk signal.
74. **(D-19)** Every analysis in the registry returns a `headline_value`, verified by a test
    that iterates the registry.
75. **(S6)** A workbook containing an external entity declaration is rejected, not resolved.
    A 10 MB upload that expands past 100 MB is aborted mid-stream. A sheet with a formatted
    cell at row 1,000,000 is rejected at the row ceiling without the worker's memory rising.
76. **(A-35)** A freeze on a project at the designed bound — 2,000 process nodes, 2,000 BRs,
    ~50,000 rows across the frozen tables — completes inside the request timeout, in one
    transaction.
77. **(A-37)** A `cr_impact` row naming two impacted objects, or none, is rejected by the
    database. A row naming an object in another project is rejected by the composite FK.
78. **(A-41)** A `decision` row cannot be updated or deleted, including by direct SQL. A
    correction is a new row whose `supersedes_decision_id` points at the original, and both
    remain readable.
79. **(D-19)** Creating a project copies every FTC house default into that project's own
    control rules. Editing a house default afterwards leaves that project's thresholds
    unchanged, and a project created after the edit picks up the new value.
80. **(D-19, D-40)** A User can change a project's `priced_diff` flag threshold from 5% to 15%;
    the change is refused without a rationale, and when accepted it writes an
    `AUDIT_EVENT` recording the old value, the new value and the reason.
81. **(D-19)** A rule can be disabled (`is_enabled = false`) and disappears from the control
    panel without being deleted.
82. **(D-19)** A house default may be saved with no owning org role; a project rule may not.

### Process model, DFD and order (D-38, D-46, D-47, D-49)

83. **(D-38)** Flow edges are retired: `vb_app` holds no INSERT or UPDATE on `bfc_node_flow`,
    and no route writes it. Existing rows are readable history only.
84. **(D-38)** Retired with flow edges; a branch is two different outputs feeding different
    processes, and needs no label.
85. **(D-38)** A rework loop in the derived order — A writes an entity B reads, and B writes
    one A reads — is **accepted**; `generate_dfd` terminates, returns each process once, and
    gives the loop's members one rank.
86. **(D-38, D-46)** `generate_dfd` on a non-process node returns its process descendants in the
    node's own set — at whatever level each branch ends — one lane per performer plus an
    UNASSIGNED lane when a process has none, every input/output data entity as a store, and
    the derived order. Called on a process node it returns 422.
87. **(D-47, D-22)** An as-is DFD shows each process's supporting systems from
    `application_bfc_node`; a to-be DFD shows them through BR → Solution → Application, and only
    when `SOLUTION` and `APPLICATION` are both on.
88. **(D-38)** `export_dfd` returns Mermaid text that renders, with one subgraph per lane,
    each trigger as a start node, and the derived order drawn dashed only when asked.
89. **(D-23)** A childless L4 node can be promoted to a process; in the to-be set its BR is
    created in the same transaction. Adding a child to any process node is rejected by the
    database, not only the service.
90. **(D-23)** Demoting a process whose BR is active returns 409 naming the BR. After the BR
    is retired, demotion succeeds and the node accepts children.
91. **(D-23)** One L2 branch ending at L4 and another ending at L5 both appear, as processes,
    in one generated DFD for their common L1 parent.
92. **(D-24)** Linking a BR CRUD `U` on DE-0007 to a step with no output DE-0007 creates the
    step's output row in the same transaction; the DFD shows it immediately.
93. **(D-24)** Removing that step output while the BR's `U` exists returns 409 naming the
    BR. `process_completeness.crud_without_io` is 0 on any project, always.
94. **(D-24a)** An external entity "Customer" linked as an input to "Receive order" appears in
    the DFD as an external party with a labelled flow into that step, and in a frozen
    baseline's snapshot.
95. **(D-25)** `GET /process-flow-json/schema` returns a JSON Schema that the example file in
    the same response validates against.
96. **(D-25, D-55)** A valid `vb-process-flow/2.0` file with 12 steps (3 existing by `br_number`,
    9 new), 2 unknown data entities and 1 unknown performer: validate writes nothing to any
    business table, lists the 2 DEs as warnings to create and the performer as a warning to
    leave blank, each with its `source_ref`, and the batch can be committed.
97. **(D-25)** Commit creates 9 process nodes, 9 BRs, 2 data entities and every step input,
    output and trigger link in one transaction; exporting the flow as JSON and re-importing
    it unchanged produces a batch of 0 inserts.
98. **(D-25, Q5)** A file in `mode: "merge"` that omits an existing step input leaves it in
    place. The same file in `mode: "replace"` shows the retire count in the preview and is
    refused at commit unless that count is acknowledged.
<!-- CHECK: criteria 96–98, 110, 113, 114 and 118 are restated for the vb-process-flow/2.0 contract (slice7_schema §9.9) and D-55's warn-and-import split; slice7_schema §11 item 9 leaves their final wording to the wave 1e import spec, which is not yet written. -->
99. **(D-25)** A 3 MB file, a file nested 40 levels deep, a file with 501 steps and a file
    containing `NaN` are each rejected before anything is staged.
100. **(D-26)** A data entity with one PK field and no data types saves without error;
     `validate_entity_model` lists no warning for the missing types.
101. **(D-27, D-40)** A User renames FR type `INTERFACE` to "連携" and adds type "API" with
     behaviour INTERFACE. FRs of both types show the interface panel and appear on the
     interface list; no code change or deployment is involved.
102. **(D-27)** Interface detail on an FR of type FORM returns 422. Changing an interface FR's
     type to FORM while it has interface detail returns 409.
103. **(D-27)** The interface list shows one row per interface FR with its FR number, source →
     target application and data entities carried. An interface FR with no source is listed
     as incomplete. There is no separate interface number series in the database.
104. **(D-27)** A new FR type with no rate-card rows: an FR of that type saves, and rating
     its complexity returns 422 naming the missing rate-card cell.
105. **(D-28, D-52)** An FR created with no BR link saves and returns a `no_br` warning. It is
     listed by `unlinked=true`, in `br_coverage_report` and in the `fr_unlinked` control-panel
     rule. An FR with no solution appears in `effort_summary` under Unassigned.
106. **(D-28)** An FR import of 50 rows, 10 without a Solution number, validates with 10
     warnings and 0 errors, and commits. A BR import row naming a summary node is an error.
107. **(D-29)** Two entities joined by a composite FK draw as one relationship line from the
     FK rows to the parent's PK rows. A mandatory FK draws `1` on the parent side; an
     optional or unknown one draws `0..1`.
108. **(D-29)** The ERD filtered to one L1 subject area shows only the entities its steps read
     or write, plus a labelled stub for every FK leaving the area.
109. **(D-30)** An entity dragged on the ERD is in the same place after a reload and for a
     second user. Freezing and diffing a baseline is unaffected by any layout change.

### Imports, soft delete, access and retention

110. **(R2-P1, Q1)** A flow file under anchor `01.02` has a step "Receive  Order" with no
     `br_number` and no `hier_code`. `01.02` already has an active process child "receive
     order". Validate stages an UPDATE of that node with a "matched by name" warning. After
     commit the anchor has one such step, not two.
111. **(R2-P1, R2-P2)** Every batch with `insert_count > 0` is refused at commit unless
     `acknowledged_inserts` equals it. This holds for an all-insert `.xlsx` batch and for a
     flow JSON batch, not only for a mixed one.
112. **(R2-P3)** Validate with anchor `01.02` and mode `merge` on a file whose `parent` is
     `01.03`, or whose `mode` is `replace`, returns 422. No `IMPORT_BATCH` row is created.
     A file whose anchor lies in another project returns 404.
113. **(R2-P4, Q5)** A `replace` file omits one trigger link, one step input that BR-0012's
     `R` CRUD depends on, one unguarded step output, and one whole step. The preview lists
     the trigger link and the output as RETIRE and the input as KEPT, with a warning naming
     BR-0012. Commit retires exactly those two rows. The omitted step, its BR, its performer
     and its external flows are unchanged.
114. **(D-46)** A step has performer X and its BR has Accountable role Y, and the file gives it
     performer P. After commit, the step's performer is P and its RACI is untouched. This
     holds in `merge` mode too.
115. **(R2-P5)** Demoting a process whose BR is retired but which still carries one step
     I/O row returns 409 naming that row. Afterwards the I/O row is still active: the call
     retired nothing.
116. **(R2-P6)** Freeze issues `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ` before its
     first query, as seen in the statement log. A test hook commits an edit that creates
     `hier_code` drift after `consistency_check` has read the chart. The resulting baseline
     does not contain the edit.
117. **(R2-D1)** Export BRs, reorder the chart so BR-0012 moves from `01.02.03` to
     `01.02.05`, then upload the export with BR-0012's statement changed. The row is an
     error reading "moved since export", and no BR is written. A BR row with a blank BR
     number is an error.
118. **(R2-D1)** Export a flow, reorder its steps, and re-import the export unchanged except
     for its `hier_code` column cleared. The batch is 0 inserts, and each step updates the
     node its `br_number` names.
119. **(R2-D2, Q4)** Soft-deleting DE-0007 while BR-0012 reads it returns 409 naming
     BR-0012. Soft-deleting SOL-0003 while it has two active FRs returns 409 naming both FR
     numbers. Neither call changes any row.
120. **(R2-D2)** Restoring a data field whose DE is inactive returns 409 naming the DE. An
     active BR under an inactive BFC node, planted by direct SQL, appears in
     `consistency_check.active_under_inactive`, and freeze is refused until it is resolved.
121. **(R2-D3, Q3)** Between v1.0 and v1.1, FR-0004 is re-rated from 2 to 8 days and its BR
     is also edited, FR-0009 (5 days) is added and FR-0002 (3 days) is removed. The priced
     diff reports changed +6, added +5, removed −3, net +8, with FR-0004 counted once.
     `effort_exposed_days` is reported separately and is not part of the net.
122. **(R2-D3)** Relabel the complexity code "Complex" to "High complexity" between two
     freezes, with no FR edits. The diff reports no FR as CHANGED and the priced diff net is 0.
123. **(R2-D5)** A flow JSON step whose `row_version` is behind the node is a row error
     naming the node's current name, performer and description. The other steps still stage.
     The preview shows before/after for every UPDATE step.
124. **(R2-D6)** An FR import row whose only change is `effort_days` commits no change and
     warns. A row that moves an FR to a type with no rate for its complexity is an error. A
     row that moves an interface FR with live detail to a FORM type is an error. A committed
     type change re-derives `effort_days` from the rate card.
125. **(R2-D7)** A rate-card change without a rationale is refused (422). With one, it writes
     an `AUDIT_EVENT` holding each cell's old and new value and the rationale. Existing FRs
     keep their `effort_days`. A baseline frozen afterwards carries the card.
126. **(R2-D8, Q6)** Changing the behaviour of a global FR_TYPE that any FR or rate row
     references returns 409. Changing its label succeeds. Changing the behaviour of an
     unreferenced global type succeeds.
127. **(R2-D9, Q7)** A project adds RASCI code `S` (behaviour SUPPORT), and a RAPID project
     retires `R` and adds `P` with behaviour RESPONSIBLE (a second RESPONSIBLE code while `R`
     is live is refused, A-60). A second role on one BR whose code has behaviour ACCOUNTABLE
     is rejected, whatever its letter.
128. **(R2-D12, Q9)** One benefit is in THB and another in hours. `value_ranking` returns two
     rankings, and no ratio combines the two units. A benefit with baseline 100, target 160
     and 50% contribution yields value 30, not 110.
129. **(R2-D13)** Linking an inbound external flow carrying DE-0007 to a step with no input
     DE-0007 creates that input in the same transaction. Unlinking the input afterwards
     returns 409 naming the external party.
130. **(R2-D14)** A new project has ten `PROJECT_SEQUENCE` rows. Twenty concurrent first
     benefits produce `BEN-0001`…`BEN-0020` and no 409.
131. **(R2-D15, D-33)** Import a WBS, re-number its WBS codes in MS Project, and re-import.
     The same `WBS_ITEM` rows update by Unique ID and keep their phase and solution links. A
     text date `03/04/2027` is a row error. A `replace` import that omits two lines is
     refused until `acknowledged_retires = 2`.
132. **(D-33)** `PATCH /wbs-items/{id}` with a `phase_id` succeeds. With a `name` it returns
     422. A project with no WBS still freezes and diffs normally, and its program dashboard
     entry reads "not imported".
133. **(D-52)** An FR import row names BR-0012 and no solution. It saves linked to BR-0012,
     with no solution and no warning about one. No suggested-link column exists.
134. **(D-34)** No import, with or without BR numbers, ever creates a SOLUTION row.
135. **(R2-S1, D-40)** For each object route family — `/bfc-nodes`, `/business-requirements`,
     `/solutions`, `/function-requirements` (incl. `/interface`), `/applications`,
     `/data-entities`, `/data-fields`, `/external-entities`, `/org-units`, `/org-roles`,
     `/process-triggers`, `/project-members`, `/baselines`, `/bulk/batches`, each restore route,
     `/programs/{id}`, and later `/benefits`, `/risks`, `/change-requests`, `/phases`,
     `/wbs-items` — a user who cannot see project B, calling with an id owned by B, receives
     404. `test_no_get_route_leaks_a_restricted_project` calls every GET route as a non-member.
136. **(R2-S5)** No restore route exists for a project membership, a control rule, a user or a
     `code_master` row. A removed member comes back only through `POST /projects/{id}/members`,
     which inserts a new membership row and writes `MEMBER_ADDED`.
137. **(R2-S7)** A step named `x"] --> Y[click` and a performer named `%%{init: {"securityLevel":
     "loose"}}%%` export from every Mermaid exporter (DFD and ERD) as inert quoted labels. No
     exported line begins with `click`, `%%{init`, `style`, `classDef` or `linkStyle`, and the
     output renders.
138. **(R2-S8)** A 50 MB POST to a validate route returns 413, and the handler and its
     dependencies are never invoked, as seen in the log. A chunked body with no
     Content-Length is cut off at the cap. A 9 MB `.xlsx` accepted for validation creates no
     file under `TMPDIR`.
139. **(D-40)** The one-grant model is retired: `vb_app` cannot INSERT or UPDATE
     `user_access_grant`, and two live memberships of one user on one project are refused by
     the database.
140. **(D-40)** Program grants are retired. A program's roll-ups cover the projects in it that
     the caller can see; a restricted project the caller is not on is omitted without a count.
141. **(R2-S3)** Only a platform admin moves a project between programs. The preview returns a
     hash; committing with a stale `confirm_hash` returns 409; the committed move writes one
     audit row. Moving a project into a program of another client returns 422.
142. **(R2-S2)** A staff user calling a program roll-up receives one entry per project of the
     program visible to them, each equal to that project's own report; a program none of
     whose projects they can see is 404. A static check finds no query with `project_id IN`
     in `services/program.py`.
143. **(D-40)** A platform admin creating a project creates no membership row.
     `GET /projects/{id}/access` lists the platform admins and either the members with their
     effective level (restricted) or the staff counts by kind (unrestricted), each with its
     source.
144. **(D-36)** The prompt pack returned by `GET /process-flow-json/schema` names Claude and
     Microsoft Copilot under FTC accounts as the only approved services. Its first
     instruction is to remove personal data from the source.
145. **(Q1)** Creating, renaming or restoring a BFC node to a name already used by an active
     sibling in the same set, ignoring case, width and spacing, returns 409 naming the sibling.
146. **(D-38)** Retired with flow edges: no route creates an edge between two steps.
147. **(Q14)** A batch uploaded 91 days ago has no `IMPORT_ROW` rows after the daily purge.
     Its header still shows who, when, entity and counts, and an uncommitted one reads
     REJECTED. One `IMPORT_ROWS_PURGED` audit row records the run. A batch 89 days old is
     untouched.
148. **(R2-D13)** `process_completeness.ext_without_io` is 0 on any project, always.
149. **(D-46)** A process with no performer appears in `process_completeness.no_performer`
     as a warning that does not block the freeze, and is drawn in the UNASSIGNED lane.
150. **(D-40)** Retired with program grants.
151. **(R2-D2)** Soft-deleting a BFC node whose BR is active returns 409 naming the BR. The
     node, the BR and their links are unchanged.
152. **(R2-S8, D-35)** An upload of exactly the route cap is accepted; one byte more returns
     413 from ingress.
153. **(D-40)** Retired with program grants: memberships are managed only by a platform admin.
154. **(Q15)** `purge_project` by a non-admin returns 403, and without a reason 422. Run by a
     platform admin, it leaves no live or snapshot row for the project, the project's archive
     key is deleted, an existing archive file for it can no longer be decrypted, and a
     `PROJECT_PURGED` audit row names the project code, actor, date and reason with no
     content.
155. **(Q15, R2-S10)** Every baseline freeze writes one encrypted archive file under the
     project's own key; decrypting it and recomputing the hashes matches the frozen rows.

### The DFD rule, readiness, process volume and drawing (D-65…D-70, slice 13)

156. **(D-66, 13a A1–A2)** On a to-be process with SOLUTION and FUNCTION_REQUIREMENT on, the panel
     shows "Solutions (n)" then "Function requirements (n)" as two sections, above External parties,
     Description and Supporting systems. With SOLUTION off, only Function requirements shows, and an FR
     can still be linked.
157. **(D-68, 13a A4)** For every process of a project of at least 50 processes, the light is not
     "Ready" exactly when `process-completeness` lists it as missing a rule element — one source, no
     disagreement. With the chart's DFD component off, no light and no DFD mark shows.
158. **(D-68, D-50)** Every light carries text and an icon and reads correctly in greyscale; the DFD
     index's ready / partly / not-ready counts sum to each diagram's process count.
159. **(D-69, 13a A10)** A process whose only start is an inbound external party shows the *Started
     by* mark as met though its trigger list is empty; no data-in mark appears while the chart's rule
     lacks DATA_IN, and one appears as soon as it holds it.
160. **(D-68, 13a A11)** Adding an output data entity in the BR's CRUD grid changes that process's
     light in the tree without a reload; so do a step retire or restore and a DFD component toggle.
161. **(D-70, Q-4, 13b B1)** Every project existing when the rule arrives, active or not, has exactly
     STARTED + DATA_OUT on both charts, and a freeze that passed the day before still passes. A new
     project starts with STARTED, DATA_IN, DATA_OUT and ORDER on the to-be chart and STARTED on the
     as-is chart.
162. **(D-70, 13b B2–B3)** Removing DATA_OUT from the to-be rule: a process with a trigger and no data
     turns green and no longer blocks the freeze, and the audit holds `PROJECT_DFD_RULE_CHANGED` with
     from, to and the would-block count. Adding DATA_IN: the preview names how many processes would
     block, and after saving the freeze refuses with that list.
163. **(D-70, 13b B4–B5)** ORDER without DATA_IN and DATA_OUT returns 422; dropping STARTED returns
     422. A non-admin `PUT /dfd-rule` returns 403; a non-member of a restricted project gets 404 on the
     GET.
164. **(D-70, Q-15)** A stricter as-is rule never changes a to-be light or the to-be freeze check, and
     with AS_IS off the as-is rule blocks nothing.
165. **(D-70, 13b B9)** A chart whose rule rows are all retired (or missing) behaves as STARTED +
     DATA_OUT, appears in `project_without_dfd_rule`, and its freeze is refused until an admin saves a
     rule.
166. **(D-70, 13b B8)** With the freeze re-expressed over `readiness()`, an as-is process missing a rule
     element still refuses the freeze while AS_IS is on (`sara` reviewed).
167. **(D-70, 13b B6)** A baseline frozen under the per-chart rule shows both charts' rules on its
     header; one frozen before shows "D-38 rule"; both still verify, and neither rule ever appears as a
     diff row.
168. **(Q-13, S13-2)** A process that meets its chart's rule but misses a recommended element is
     yellow, does not block the freeze, and its tooltip does not say "Blocks the freeze"; a red one
     does.
169. **(Q-3, 13b B10)** A diagram with no derived order ranks its processes left to right in chart
     order (`seq_no`), with no arrows.
170. **(D-67, 13c C1, C10)** 3 runs a week × 40 invoices × 360 s on the 240 × 8 basis returns 624 hours
     and 0.33 FTE, computed by the server; 0.3 s per invoice × 40,000 a month stores as `0.300` without
     rounding and returns 200 hours and 0.10 FTE.
171. **(D-67, 13c C2–C3)** A body carrying `fte` or `annual_hours` returns 422; so do a non-process
     node, a negative value, too many decimals and a value above its cap. With any figure empty, FTE is
     `null` and the response names the missing fields.
172. **(D-67, 13c C4, C6)** Changing the project's FTE basis changes every process's FTE without
     touching a process row; a baseline frozen before the change re-derives its own FTE unchanged.
173. **(D-67, Q-22, 13c C5)** After volume arrives, shadow parity passes, every older baseline still
     verifies, and a diff of an older baseline against live shows no process CHANGED merely because
     volume exists — and says which columns were not compared.
174. **(D-67, Q-28, 13c C7, C9)** The volume summary shows as-is and to-be hours per matched L1 area side
     by side; after to-be area 02 is reordered to 03, the area is listed unmatched (`NAME_ELSEWHERE`),
     never paired; processes with incomplete volume are listed and contribute no number.
175. **(D-67, 13c C8)** Transaction units and periods are sent as codes; a project override label shows
     on screen and the code is stored. Demoting a process that has volume returns 409.
176. **(D-65, 13d D1, D6)** Dragging from a data store to a process creates exactly one step input
     through `step_io.ensure_step_io`, identical to the panel's row; the same drag again writes nothing
     and says "Already on the diagram".
177. **(D-65, 13d D2)** Drawing process A → process B and picking DE-0007 writes A's output and B's input
     in one transaction, and the derived order arrow A → B appears; if B's input fails, A's output is
     not written.
178. **(D-65, 13d D3, D7)** Removing a flow a BR's CRUD depends on returns the 409 naming the BR and
     removes nothing; removing a STORE, EXTERNAL or TRIGGER flow soft-deletes exactly one row; a derived
     order arrow cannot be selected for removal.
179. **(D-65, 13d D4–D5)** A viewer, a baseline view and a chart with its DFD off cannot start a
     connection; a hand-off between an as-is and a to-be process returns 422, and to a process the user
     cannot see, 404.
180. **(Q-11, Q-12)** Drawing a store → process writes no BR CRUD, and the CRUD grid shows the I/O as "On
     the diagram, not in the requirement yet"; drawing to empty canvas can create a new data entity,
     numbered at save.

### Organisation, systems and the structured BR (D-56, D-57, D-59…D-62, slices 10c and 11)

181. **(D-56)** Organisation and Systems are one click from the rail; the old Settings addresses,
     including `settings/applications/:appId`, land on the same page and item.
182. **(S10c-2)** With TO_BE_DFD off, the performer of a to-be process can be set and is audited
     `PERFORMER_SET`; a trigger link on the same process returns 409 `COMPONENT_OFF`.
183. **(D-57)** "Make this a process" never fires without a confirmation that says it creates a BR;
     the button shows only on a childless node at level 3 or below, and never to a viewer.
184. **(D-62)** A new project created through the form is restricted; a USER not assigned to it does not
     see it on the home page and gets 404 on its address. The restrict preview flags a kept member whose
     level drops.
185. **(D-59, S11-1)** A BR's lines are numbered BR-0043.1, .2, .3; retiring .2 and adding a line gives
     .4, never .2 again; reordering changes no number and is not a CHANGED row in a diff. The BR's
     priority shows as the highest of its live lines and is never accepted from a body.
186. **(D-59, S11-1)** After the structured BR arrives, each BR with business logic and output text has
     one RULE and one OUTPUT line holding that text word for word; the old fields are read-only and
     unchanged; a diff against an older baseline shows the lines as ADDED, with the "predates
     requirement lines" banner, and the older baseline still verifies.
187. **(D-60b)** An attribute tick without a live entity-level row of the same CRUD is refused by the
     database; unticking the entity's action in the grid removes its attribute ticks in the same save;
     a D on an attribute returns 422; retiring a data field a live BR uses returns 409 naming the BR.
188. **(D-61)** A flow with the same from and to system is refused; with APPLICATION off a flow write
     returns 409 `COMPONENT_OFF`; a flow shows "covered by FR-…" exactly when the BR links an interface
     FR with the same source, target and carried entity, and "Create interface FR from these flows"
     creates that FR, its interface detail and the link in one transaction.
189. **(S11-1)** Baselines frozen after the structured BR arrives carry hash spec 4 and its three
     shadows; every earlier baseline still verifies byte for byte.

### Settled rulings (SC-1…SC-11)

190. **(SC-2)** A change request against the SUPERSEDED baseline that carries the newest client approval
     is accepted; against any other SUPERSEDED baseline it returns 422.
191. **(SC-6)** A flow file whose step names an unknown BR number, or carries a moved `hier_code`, is a
     row error and nothing is written for it; an as-is step with no BR number updates the live process
     of the same name under the anchor; a file with more than 2,000 inputs, outputs, external flows and
     triggers combined is rejected before anything is staged; `GET /bfc-nodes/{id}/dfd/export?format=json`
     returns the file.
192. **(SC-7)** A project editor (EDIT) can decide a change request and reset the project's control rules
     to the house defaults; a viewer gets 403.

---

## 11. Assumptions

Confirm or kill each. Those marked ⚠ change the data model if wrong. Assumptions settled by a
decision are recorded in the design history, not here.

### Core model

- ⚠ `ASSUMPTION A-3` — **BR ↔ DE is one associative table keyed by CRUD**, with direction
  generated from it (`R` → INPUT, else OUTPUT). Not two relationships, and not two stored
  columns. *If wrong* — i.e. if a Read can legitimately be classified as output-side
  reference data — the generated column becomes two independent stored columns and the
  `(R, OUTPUT)` contradiction becomes possible again.
- `ASSUMPTION A-7` — Snapshot rows are **hard-immutable**: no `is_active`, no update path,
  no soft delete. A deliberate deviation from playbook §9.7 — a baseline that can be
  soft-deleted is not a baseline (`docs/PLAYBOOK_DEVIATIONS.md` deviation 1).
- `ASSUMPTION A-8` — Version labels auto-increment the minor (v1.0 → v1.1). Major bumps are
  a manual choice at freeze. No branching of baselines.
- `ASSUMPTION A-9` — The client org tree is exactly three levels (Department → Division →
  Section) but stored self-referencing with a level code, so a fourth level costs a seed
  row rather than a migration.
- `ASSUMPTION A-10` — Roles belong to one org unit. A role spanning units (e.g. "Internal
  Auditor") would need a many-to-many; not modelled in MVP.
- `ASSUMPTION A-13` — Single tenant deployment (FTC's own instance). `PROJECT` is the
  isolation boundary, not a separate `tenant_id`.
- `ASSUMPTION A-14` — Password reset is admin-initiated in MVP; no self-service email flow.

### Solutions, function requirements and applications

- ⚠ `ASSUMPTION A-27` — **An FR inherits its application through its solution tag.** There is
  no `APPLICATION_FUNCTION_REQUIREMENT` table, and an FR with no solution has no application
  (an interface FR names its endpoints in `FR_INTERFACE`). If one FR within a solution must be
  built on a different application from its siblings, that is unrepresentable — and it should
  stay a *finding* rather than become a column, because it usually means the solution was
  drawn too broadly. It is one junction table if that changes.
- `ASSUMPTION A-30` — **One application catalogue serves as-is and to-be**, distinguished by
  `lifecycle_code`. One table plus a flag makes the gap report a self-join rather than a union.

### Control framework

- `ASSUMPTION A-38` — **`effort_days` is a stored derivation, not computed at read.** A
  rate-card renegotiation must not reprice agreed scope (S6c-2). Same reasoning as §5.4.4's
  label copying, and the reason a baseline frozen without effort can never be repriced.
- `ASSUMPTION A-39` — **Effort is man-days, and the rate card is by (FR type ×
  complexity) only** — no per-vendor, per-technology or per-phase multiplier. Real
  estimates usually need at least a vendor factor; adding one is a column on `EFFORT_RATE`,
  not a model change.
- `ASSUMPTION A-40` — **Benefits are ranked only within one unit** (Q9): a benefit's value is
  **`(target_value − baseline_value) × contribution_pct / 100`** in `measure_unit`, and
  `value_ranking` returns one ranking per unit (R2-D12). **Open:** no currency conversion, no
  discounting, no NPV. If the business case needs NPV, that is a computed layer over this,
  and it needs a discount rate per project. `contribution_pct` is read as a percentage (0–100).
- `ASSUMPTION A-42` — **The thresholds in §7.13 are FTC starting points, and every one of
  them is configurable data, not code.** Three levels of configurability:
  1. **The FTC house default** — `project_id IS NULL`, edited by a platform admin in the
     app. Changes affect future projects only, never an in-flight engagement.
  2. **The project's agreed rule** — copied from the house default at `create_project`, then
     negotiated with the client at mobilisation. Threshold, escalate value, comparison,
     owning role, prescribed action, escalation path and on/off are editable by a User
     (D-40), with a mandatory rationale and an audit row.
  3. **Which analyses are governed at all** — any of the 17 in `ANALYSIS_REGISTRY` can carry
     a rule; the ten seeded are the ones worth governing on a first engagement.

  The house defaults should be set before the first engagement: they become the starting
  point on every project after.
- `ASSUMPTION A-43` — **`control_panel` computes live on request.** With 17 analyses over a
  large project this may be slow enough to need caching or a materialised view. The same
  "how big is a real project" question as A-57.
- `ASSUMPTION A-44` — **A project's thresholds do not vary by phase.** Tolerance usually
  tightens as an engagement progresses — 20% scope growth is normal in discovery and
  alarming after design freeze. Supporting it means a nullable `phase_id` in the rule key and
  a phase-aware lookup in `control_panel`. **Not added — it is a column plus a lookup if
  tolerance should tighten at a gate.**

### Time, tokens and baselines

- `ASSUMPTION A-33` — **Application timezone is `Asia/Bangkok` (ICT).** Every `date` column
  derives as `(now() AT TIME ZONE 'Asia/Bangkok')::date`, and import templates require ISO
  `YYYY-MM-DD` text with per-column format validation (finding D10): with the container on
  UTC, an issue resolved at 06:30 ICT would record the previous day, and a US-locale sheet
  reading `03/04/2027` would commit as 3 April where the author meant 4 March.
- `ASSUMPTION A-36` — **A `baseline` header cannot be soft-deleted.** A wrongly-frozen
  version stays visible in the lineage with its note; the repair is to freeze the next one
  (finding P6; deviations 4 and 8a).
- `ASSUMPTION A-20` — **Baselines are read-and-diff only; there is no restore.** Restore
  would require the shadow tables to be complete and reversible for every scoped entity
  including junctions, plus a strategy for un-resolving the copied labels. Read-only is much
  cheaper.

### Process model and diagrams

- ⚠ `ASSUMPTION A-47` — **A process node may sit at level 3, 4 or 5**, not at L1 or L2. An
  L2 "process" would put a whole business area in one box and one requirement. **If FTC
  ever models a branch that stops at L2, this is one CHECK.**
- ⚠ `ASSUMPTION A-48` — **Splitting a process is refused until the consultant has retired
  its BR and every other step-level fact** (D-23, R2-P5, Q4). Demotion returns 409 naming
  each blocker, and **VB never retires anything on the consultant's behalf**: moving the BR to
  one of the new children would guess which child the requirement meant, and a cascade would
  record a scope removal nobody decided. Retiring a step with its dependents is a separate,
  explicitly confirmed action (S3-SR).
- `ASSUMPTION A-49` — **The process-flow JSON carries one parent node's flow per file**,
  ≤ 500 steps. A whole-chart import would be a BFC import, which D-25 did not ask for.
- `ASSUMPTION A-51` — **The AI conversion runs outside VB**, **only in Claude or Microsoft
  Copilot under FTC's own accounts, with personal data removed first** (D-36). VB publishes
  the schema and prompt pack and accepts the file. An in-app "convert this PowerPoint" button
  would send client content to an AI service from VB itself and bring in the playbook's
  AI-layer rules (§12.2).
- `ASSUMPTION A-52` — **Layout is last-write-wins per object, and not versioned.** A baseline
  re-opened later renders with today's positions, or auto-layout for objects no longer
  there. A diagram frozen with the scope is a PNG export attached to the sign-off, not a
  stored state.
- `ASSUMPTION A-53` — **ERD cardinality is derived, never typed.** A consultant who wants a
  different crow's foot changes the key or the mandatory flag that produces it. A typed
  cardinality would be a second assertion of the same fact.
- `ASSUMPTION A-54` — **An L5 node is always a process** (`CHECK (level_no < 5 OR
  is_process)`). An L5 node can have no children, so it can only be the lowest node of its
  branch. Together with the parent guard, this also enforces "no level 6".
- `ASSUMPTION A-55` — **An interface FR's detail row requires both applications.**
  `FR_INTERFACE.source_application_id` and `target_application_id` are `NOT NULL`. An
  interface known only by pattern is an FR with no `FR_INTERFACE` row, listed as incomplete
  on the interface list (§4.4).
- `ASSUMPTION A-60` — **Each project has exactly one RACI code per load-bearing behaviour**:
  one RESPONSIBLE and one ACCOUNTABLE. The single-Accountable rule resolves "the" code by
  behaviour. A RAPID mapping that sends two codes to RESPONSIBLE is refused when the code is
  saved (→ `code_master` rules, §8).

### Programs, WBS and retention

- `ASSUMPTION A-56` — **Baselines stay per project, even inside a program.** There is no
  program freeze. A program's "agreed scope" is the set of each project's latest baseline,
  shown side by side. A program-wide freeze would be one transaction across several
  projects' tables, and would bring back the cross-project write path R2-S2 exists to avoid.
- `ASSUMPTION A-57` — **A program holds about ten projects at most.** Roll-ups make one
  per-project call per project per report, so a dashboard is about 50 report calls. That is
  acceptable at ten projects; at fifty the dashboard needs caching (the same question as
  A-43), not cross-project SQL.
- ⚠ `ASSUMPTION A-59` — **"Baselines recoverable for 5 years" (Q12) is met in two layers.**
  In the live database, baselines are never deleted (A-7, A-36). For loss of the database
  itself, the encrypted per-project baseline archive covers 5 years, because point-in-time
  restore covers only days (35 at most on Flexible Server). The mechanism, cost and restore
  drill are §15's. **A client contract that requires deletion at engagement end overrides the
  5 years (Q15): the project is purged and its archive key destroyed (§15.3).**
- `ASSUMPTION A-61` — **WBS parentage comes from outline level and row order** in the MS
  Project export, not from the WBS code, which is a display string some schedules customise.
  An export sorted by anything other than ID breaks parentage. The template says so, and
  validation rejects an outline level that jumps by more than one.
- `ASSUMPTION A-65` — **`PROGRAM` has no status, dates or manager.** The program dashboard
  shows its projects' statuses. Add them if a program lifecycle is described.
- `ASSUMPTION A-66` — **WBS dates are `date`, not `timestamptz`.** MS Project's time of day is
  a working-calendar artefact at dashboard grain.
- `ASSUMPTION A-68` — **A returning MS Project Unique ID restores the retired `WBS_ITEM` row,
  links intact.** A new MS Project file that restarts Unique IDs would wrongly restore
  unrelated lines, so the preview warns when a restored line's name differs.

### Modelling choices raised by `apple`

- ⚠ `ASSUMPTION A-16` — **`code_master` is two-tier**: a nullable `project_id`, where `NULL`
  is the FTC-wide default library and non-null is a per-project override. It carries a
  resolution rule (override shadows global on `category + code`) that every consumer reads
  through `code_master.resolve`. If clients never configure these, drop the column; if they
  always do, drop the global tier. **The hybrid is the most expensive of the three; confirm it
  earns its cost.**
- `ASSUMPTION A-22` — **`ORG_UNIT` stops at three levels** per Department / Division /
  Section, held by the service and a `consistency_check` line, not a CHECK (S1-7). Large
  clients run Group → Company → Department → … If the depth is uncertain, the service limit
  goes and the self-reference stays open; the only loss is the level-label guarantee.
- `ASSUMPTION A-23` — **No attachments.** Issues and BRs attract screenshots, extracts and
  signed-off documents on every real engagement. Per-parent attachment tables (not a
  polymorphic one) are the likely next increment.
- `ASSUMPTION A-25` — **`updated_by` and `deleted_by` are in the audit column set.** The
  playbook names only `created_by`; with soft delete and freezes VB needs to know who last
  touched a live row before it was baselined.

---

## 12. Delivery sequence and out of scope

### 12.1 Waves — everything here is mandatory, only the order is a decision

D-13…D-19 and D-37…D-70 are **requirements, not a roadmap**. Nothing below is dropped; the waves
exist because the model must be built in dependency order. **The wave line is Ben's to move.**

**Ordering rules:**
- **Spec before build (D-45).** No slice is built until the open rows touching it are answered
  and its section of the design is rewritten to match. A slice that changes the data model goes
  to `apple` first.
- **The foundations of D-37 (components) and D-40 (access) land before the baseline freeze**,
  because the freeze set depends on both (D-45).
- **D-13 precedes D-16, and both precede any baseline anyone intends to argue about.** A
  baseline frozen without `effort_days` is unpriced forever (A-38).
- Migrations land only on `main`, in order, one per commit.

| Wave | Slice | Contents | Status |
|---|---|---|---|
| **1a** | 7a | Project components and data model depth (D-37, D-39) | built |
| **1b** | 7b | Access: admin / user / viewer, restricted projects (D-40) | built |
| **1c** | 7c | One DFD: performer lanes, triggers, order from data, the as-is set (D-38, D-46, D-47, D-49) | built |
| **1d** | 8 | Baseline freeze over the enabled components, client approval, diff (S8-1…S8-3) | built |
| 1 | 9 | Every screen to the mockups: dark-first theme, left rail, the kit (D-51) | built |
| 1 | 10a | The BR inside the function chart; the DFD screen (D-53, D-54) | built |
| 1 | 10b | BR ↔ FR direct, solution optional, hash spec 2 (D-52, S10b-1…S10b-3) | built |
| 1 | 10d | The ranked process panel; one RACI per process (D-63, D-64, S10d-1) | built |
| 1 | 10c | Organisation and Systems in the rail, plain guidance and what starts a process on the panel, BR attributes (read-only), the performer recordable whatever the DFD setting, assigned-only projects (D-56, D-57, D-60a, D-62, S10c-2) | built; the one-off switch of existing projects is done project by project by an admin |
| 1 | 13a | Solutions and Function requirements as two panel sections; the readiness light and the DFD marks (D-66, D-68, D-69). Until 13b the light follows the fixed rule (STARTED + DATA_OUT), under which yellow also blocks the freeze | built |
| 1 | 13b | The DFD rule per chart: light, marks, warnings and the freeze driven by it; chart-order fallback (D-70, S13-1, S13-2) | built |
| 1 | 13c | Process volume and FTE; hash spec 3 (D-67, S13-1) | built |
| 1 | 13d | Drawing connections on the DFD (D-65, Q-11, Q-12) | built |
| 1 | 11 | Structured BR lines, the attributes a BR uses, BR system-to-system flows with a kind; hash spec 4 (D-59, D-60b, D-61, S11-1…S11-4) | next |
| 1 | 12 | The Scope dashboard's remaining KPIs S7–S11 and the Project-management card (D-58, S12-1, `docs/slice12_kpis.md`). Each tile appears when its wave lands | after 11; S1–S6 and M1 built with the 2026-10-16 screen work |
| **Next** | — | The Issue module (D-4, D-5; component ISSUE — screens and routes; its import is in 1e) and the control rules and control panel (D-19): right after slice 12, opening the next wave (SC-9) | — |
| **1e** | — | Imports 4b–4d: BR, FR and Issue `.xlsx`; the flow file `vb-process-flow/2.0` with warn-and-import (D-25, D-55) | — |
| **1f** | — | Reports, program roll-ups and PDF export (D-42) | — |
| **1g** | — | Code maintenance | — |
| **2** | — | Benefits (D-14) · change requests (D-16) · **WBS import + progress updates + progress report (D-33, D-41)** | — |
| **3** | — | Risks (D-15) · decisions (D-17) · phasing and dependency (D-18) | — |
| **4** | — | English / Japanese / Thai (D-44) · version comparison screen (D-50) | — |
| **Before first client use** | — | Azure (D-35) · restore drill (§15.3) · prompt pack (D-36) · baseline archive file and `purge_project` (S8-1) · client read-only login and the offline viewer file (D-43) | — |

The canvas (§7.14) is one component for the DFD and the ERD. Program roll-ups are built after the
per-project reports they are made of (R2-S2).

### 12.2 Out of scope

Explicit, so this spec is not read as a promise. **Per D-1 these are later increments of the
same platform, not rejected ideas** — §5 is modelled so they attach to this spine.

- **Task-level schedule *authoring*** — activities, dependencies, critical path, Gantt
  editing. A WBS is *imported* from MS Project, read-only apart from its phase and solution
  links and VB's own dated progress updates, to feed plan-vs-actual and the progress report
  (D-33, D-41). Building or editing the schedule stays in MS Project.
- **Resource and capacity management** — named people, allocation, utilisation. `EFFORT_RATE`
  gives the demand side (D-13); the supply side is not modelled.
- **Cost beyond effort** — licences, hardware, run cost, currency, NPV. D-13 gives man-days;
  converting those to money needs a rate-to-currency layer and A-40's discounting question
  answered.
- **Benefit *realisation* tracking after go-live** — D-14 models the commitment and the
  target; measuring actuals against it over time is a post-implementation capability.
- **Vendor and procurement management** — contracts, SOWs, invoices, vendor performance.
  Client-facing reports are exported as PDF (D-42); there is no separate vendor hand-off
  package.
- **BPMN / formal notation** — VB's process model is a DFD: processes, stores, external
  parties, triggers and performer lanes, with order derived from data (D-38). No event
  sub-types, no pools beyond performer lanes, no compensation or transaction semantics.
  Export is Mermaid text and `vb-process-flow/2.0` JSON, not BPMN XML. **A BPMN diagram can
  still be imported by converting it to the JSON (D-25)**; VB does not read BPMN XML directly.
- **BFC chart visualization** — the chart is a tree view, not a rendered org-chart graphic.
- **A full ROI or benefit model from volume** — the volume figures give hours and FTE per process and the
  time saved per area (D-67); turning them into money is the benefit component's job (D-14). Volume is not
  in the flow file yet (a format bump later), and as-is and to-be compare by area, not process by process.
- **Free drawing on the DFD** — drawing writes only step I/O, external flows, trigger links and hand-offs
  (D-65). Reconnecting an existing flow by dragging its end, and creating processes or parties from the
  canvas, are not offered; order is never drawn.
- **Import/export beyond Issue, Data Entity, Data Field, BR, FR, WBS and the flow file.**
  Solution is download-only.
- **Client-user editing** — client staff may only view their own project, and only with
  recorded consent (D-43). They never edit.
- **Baseline approval workflow** — the client's approval is recorded once on the baseline,
  not routed.
- **Notifications** — no email, no in-app alerts.
- **In-app AI agent** — none, including for the flow conversion (A-51). The conversion
  happens outside VB, in Claude or Microsoft Copilot under FTC's own accounts only (D-36). If
  an in-app agent is added later, the playbook AI-layer rules apply.
- **Cross-project reference library** — shared issue taxonomies live in `code_master`; a
  reusable reference BFC template library is deferred.
- **Baseline branching / merge.**
- **Field-level audit history** on live rows — baselines are the history mechanism.
- **Translating consultant content** — the UI and seeded labels are translated (D-44);
  what consultants type is shown as typed.

### 12.3 Designed separately, before the area is built

Areas this spec covers in their own sections, each with its own design pass.

| Area | Where | Note |
|---|---|---|
| **Frontend design** — shell, the tree, the read-only baseline mode, how untrusted free text is rendered, the program views and the import previews | §14 | `fortience-app-scaffold` supplies the patterns, the mockups the look (D-51). **Read-only baseline mode is enforced server-side, never only as UI state** |
| **Deployment and secret handling** — Azure (D-35): Container Apps, PostgreSQL Flexible Server on private networking, Key Vault via managed identity, the two DB roles (§6.6), ingress body limits (R2-S8), the daily purge job (Q14), and the Entra ID SSO decision (R2-S11) | §15 | Infrastructure, not application design |
| **Backup and restore** — point-in-time restore, 5-year recoverability of baselines (Q12, A-59), and the restore drill before first client use | §15.3 | **The only real reversal mechanism for a wrongly-frozen baseline** (§4.6 offers no reopen, A-20 no restore), which makes it a control, not an ops detail |

The uploaded-file lifecycle and the `.xlsx` parser configuration are specified in §7.11 and §7.12.

---

## 13. Build checklist

- **Spec before build (D-45).** A slice's spec is approved before its code; a data-model change
  goes to `apple` first, and `sara` reviews before any commit touching auth, access, baselines,
  imports or the migration chain.
- Migrations linear and reversible, **one per commit**, only on `main`, in order. A destructive
  migration, or an ALTER of a shadow column's type, pauses for Ben.
- Audit columns `created_at` / `updated_at` / `created_by` / `updated_by` / `deleted_by`,
  `is_active` / `deleted_at` and `row_version` on every business table from birth
  (`models/base.py::AuditMixin`, `alembic/vb_ops.py::audit_columns`). Stale `row_version` → 409
  (D-6).
- `fn_set_updated_at()` DB trigger is authoritative. **Never `onupdate=` in SQLAlchemy.**
- `code_master` seeds via `backend/seeds/` CLI — never in Alembic.
- **Every new table** is imported in `models/__init__.py` (autogenerate sees only what is
  imported).
- `BRAND`, `STATUS_COLOR_MAP` and `TOKENS` live in `frontend/src/theme/brand.js` (deviation 15)
  and reach components through `theme.vars.palette.*`. No hex anywhere else. Status colours are
  a separate semantic map; amber is reserved for regret-able actions.
- **Screens compose `components/kit.jsx` inside the left-rail shell** (D-51); `<Page crumb=…>`
  names the item in the header breadcrumb. A new screen is checked side by side with its mockup
  before merge. A mockup element with no data behind it is left out, never faked.
- Fortience Consulting Inc. footer on every screen, signed in or not.
- Error shape: 422 / 404 / 409 / 401 / 500, backend returns `detail`, frontend reads
  `err.response?.data?.detail`. No `.catch(() => {})`.
- Three-layer rule holds: Router → Service → Model. Single sources of truth: `access.py`
  (visibility), `components.py` (is a component on), `numbering.py` (numbers),
  `code_master.resolve` (lookups), `baseline.py` + `freeze_set.py` (the freeze).
- Tests at the service layer first — numbering concurrency, the freeze transaction, the
  diff, and the visibility guard are the four that matter.
- **Baselines are immutable by the database:** every `baseline_*` table carries
  `fn_reject_modification()` (`BEFORE UPDATE OR DELETE`) and the insert guard
  (`vb_ops.immutable_guards`), and `vb_app` holds no UPDATE or DELETE on them.
- **Shadows are generated by `services/baseline_shadow.py`, never hand-written**; 25 today
  (`models/baseline.SHADOWED`). Migration 0048 froze them as literal DDL, so a migration that adds
  a column to a shadowed live table adds the shadow column **in the same migration**; the parity
  test reads the database. A new frozen table is added to `freeze_set.py` (with its gate and
  hashed columns) and to `SHADOWED`, and a new entity in the set bumps the hash spec. So does a new
  hashed column on a frozen entity, whose new list **extends** the earlier one so the diff can compare
  across specs (Q-22). Spec 3 is slice 13c's volume figures, spec 4 slice 11's structured BR; 13b and
  13c add their migrations on `main` one after the other, and slice 11 follows 13c.
- **No hard delete.** The only hard deletes are `diagram_layout` (D-30), the 90-day
  `import_row` purge (Q14) and `purge_project` (Q15, as `vb_owner`). `vb_app` has no DELETE
  grant elsewhere, so a slip fails at the database.
- **Nothing cascades except a process step**: `services/step_retire.OWNED` is the only list of
  rows that retire with something else, and a new table that points at a step blocks until it
  is added there (S3-SR). Every other DELETE goes through `lifecycle` and refuses with active
  dependents; `DEPENDENTS` / `PARENTS` are derived from the model's FKs, never hand-kept (R2-D2).
- **`RESTORABLE` is the allow-list**, and each entry registers its own restore route (R2-S5).
- The bare word `role` is banned in code, tables and routes — `org_role`, `access_level`,
  `user_kind`. It is a PostgreSQL reserved word, so the rule enforces itself the first time
  someone forgets.
- `renumber_subtree` gets the most tests in the codebase. It is the one function that can
  corrupt the chart. `bulk.commit` is second — it is the only path that writes many business
  rows from an untrusted file.
- Bulk import writes nothing at validate time, and mints no numbers until commit (§7.11). **One
  pipeline** (`services/bulk.py`: validate → preview → commit); a new import adds a `Target` to
  `TARGETS`, with its component. A second importer is a code-review rejection.
- `effort_days`, `exposure_score`, `cr.effort_delta_days` and numbers are **derived at save and
  never accepted from the request body** — same rule as `created_by` (§9.2). `effort_days` is
  never read from a file; FR type and complexity from a file go through the rating services
  (R2-D6).
- Every analysis in `ANALYSIS_REGISTRY` returns a `headline_value`. A test iterates the
  registry and fails on any that does not — that contract is what `control_panel` stands on.
- `decide_cr` **refuses** a net-positive approval with no displacement named. It is a 422,
  not a warning; a control that can be clicked past is not a control.
- **Acceptance criterion 49 is not optional** — the route-coverage test is the stated price
  of deferring row-level security (§6.4). Routes register only on a `GuardedRouter` with
  `**guard.route`; a route with no guard fails at import. A write to a project component names
  it (`component=`), or criterion 49b fails it.
- **Visibility has one owner:** `access.visible_project_ids`, `require_project` and
  `require_program` are the only readers of `user_kind`, `is_restricted` and `project_member`
  (D-40, D-62). A project you cannot see is 404, never 403; the order is 404 → 403 → 409.
  `test_access.py::test_no_get_route_leaks_a_restricted_project` calls every GET route as a
  non-member.
- **`services/program.py` contains no SQL over business tables** (R2-S2). A roll-up is a loop
  over per-project reports. A `project_id IN (...)` anywhere in it is a code-review rejection.
- `escape_cell()` is used by **every** sheet-writing path, with no exceptions (S5).
- **`escape_mermaid()` is used by every Mermaid label** (R2-S7), and `_guard` ends every
  exporter: it refuses to emit `click`, `%%{init}`, `style`, `classDef`, `linkStyle`.
- **`BodyLimitMiddleware` caps every body before any handler runs** (R2-S8). A route that takes
  more than the 1 MB default registers in `services/body_limit.ROUTE_CAPS` (first match wins)
  and is refused with 401 before reading when there is no Bearer header. Bodies stay in memory;
  nothing is spooled to disk.
- `consistency_check` runs as a precondition of freeze, not on a schedule (D11). **`freeze`
  opens its own connection at REPEATABLE READ before its first statement** and runs
  `consistency_check` on that connection (R2-P6).
- Map unique-constraint violations to 409 with a `detail` string in the shared error
  handler, and disable submit controls while a create is in flight (P10).
- **The literal `level_no = 5` must not appear anywhere in the code** (D-23). Process-ness
  is `is_process`. A grep for `level_no = 5` / `level_no == 5` is part of the pre-merge check.
- FR type and RACI branch on **behaviour**, never on a code (D-27, Q7). A grep for
  `== 'INTERFACE'` against `fr_type_code` is a finding. The system categories
  (`PROJECT_COMPONENT`, `SOLUTION_CATEGORY`, `APP_LIFECYCLE`) are the recorded exemption.
- **`step_io.ensure_step_io` is the only writer of step I/O** (R2-D13). `normalise_name` is the
  only name comparison (Q1).
- **One canvas component** for the DFD and the ERD (§7.14), and one position saver
  (`canvas/useLayoutSave.js` → `diagram_layout.save`); nothing else writes `DIAGRAM_LAYOUT`.
- **Untrusted text renders as text.** `dangerouslySetInnerHTML`, `innerHTML`, `outerHTML` and
  `insertAdjacentHTML` fail lint (§14.5).
- `docs/PLAYBOOK_DEVIATIONS.md` records every deviation, among them A-7 (immutable snapshots),
  the CHECK-listed vocabularies of §8, `baseline` and the shadows exempt from soft delete and
  audit columns, `diagram_layout` hard-deleted with no `row_version` (D-30, A-52), `import_row`
  hard-deleted at 90 days (Q14), the import-staging audit exemptions (S4-6), `wbs_item.row_version`
  guarding only the VB-owned links (D-33), and the frontend deviations of §14. Staged client
  content is purged, not retired, because retiring it would keep exactly what the retention
  rule exists to remove.

---

## 14. Frontend design

Bound by `fortience-app-scaffold` (auth shell, error handling, footer) and playbook §6, with
**the screen mockups in `docs/mockups/` as the visual reference for every screen** (D-51). This
section states only what VB adds or decides on top.

### 14.1 Stack and structure

| Concern | Choice | Why |
|---|---|---|
| Framework | React 18 + Vite 8 + MUI 9 | FTC standard |
| Server state | TanStack Query 5 | Caching per project, and one place where `row_version` and 409 handling live. Query keys are shared in `app/links.js` so a save on one screen refreshes the others |
| Routing | React Router 7; every project URL is `/p/:projectId/...`, program URLs `/g/:programId` | A link names its scope, so the backend guard (§9) always receives it |
| Lists | MUI X DataGrid (MIT edition) | FTC standard list pattern |
| Tree | MUI X `RichTreeView` (MIT) over the set's full tree | At most 2,000 process nodes per project (A-35) |
| Diagrams | `@xyflow/react` 12 + `elkjs` 0.12 in a web worker | Proven by the canvas spike (§14.6) |
| Type | IBM Plex Sans and Mono, Noto Sans JP, self-hosted via `@fontsource` | Brand type; self-hosting keeps the CSP `font-src 'self'` |


```
frontend/src/
  app/          App.jsx (routes), AuthContext, links.js (page addresses + query keys),
                useCanEdit.js, useComponents.js, useCodes.js
  api/          client.js (one axios client), scope.js (one function per route), vb.js
  theme/        brand.js (BRAND, STATUS_COLOR_MAP, TOKENS, LEVEL_COLORS, RADIUS), theme.js
  components/   AppShell (rail, header, footer), Page, kit.jsx, ConflictDialog,
                ConfirmDialog, ImportWizard, CopyMermaidButton
  canvas/       ModelCanvas, elk.worker.js, layout.js, edges.jsx, useLayoutSave.js, CanvasChrome
  features/<area>/  one folder per screen area
  i18n/         en.json (shell) + en.<area>.json, t.js
```

**Screen contracts.** Page addresses and query keys live in `app/links.js`; one API function per
route in `api/scope.js`. Screens link to each other only through these.

### 14.2 Theme

- **The mockups are the reference** (D-51): `docs/mockups/` (React + MUI source, screenshots in
  `docs/mockups/screenshots/`). Tokens live in `theme/brand.js` and mirror the mockups'
  `tokens.js`.
- **Dark is the default, light the alternate**, both from one MUI `colorSchemes` theme, so
  every screen gets both at no extra cost. Dark neutrals are the mockups' purple-tinted
  `SURFACE` set.
- **`BRAND` = the Fortience deck palette**: FTC Dark Purple `#2B245C` carries the rail and the
  one highlight tile per screen; violet `#7848DC` marks selection, focus and business-function
  levels 1–5 (`LEVEL_COLORS`); cyan `#04AED6` is a focus accent. Navy (`#1F3A5F` light /
  `#4A73A8` dark) is actions and data; teal (`#2A9BB0`) is data entities and DFD stores.
- `STATUS_COLOR_MAP` (green / amber / red, per scheme) is separate from `BRAND`, per playbook §6.
  Amber stays reserved for regret-able actions. Meaning never rests on colour alone: a status
  also carries text (and an icon where it is a state).
- Radii: card 24 · diagram box 18 · field 14 · pill buttons (`RADIUS`).
- **The wrapper `Box` reads its fill and border from theme tokens**, so it works in both schemes.
- **Recorded in `docs/PLAYBOOK_DEVIATIONS.md`** (deviations 8–15): the deck palette, the two
  schemes, IBM Plex fonts, the token-based wrapper `Box`, React Flow + elkjs, the CSP's
  `style-src 'unsafe-inline'`, and `BRAND` in `brand.js`.

### 14.3 Shell, navigation and scope

- **The shell is the mockups' left rail plus a header** (D-51). The rail holds the engagement
  selector, the navigation grouped **Scope / Control / Admin** with icons, "All projects",
  Administration (platform admins), and the user and theme switch at the foot. The header holds
  the breadcrumbs (`<Page crumb=…>` names the item) and the working-set version chip ("Working ·
  after v1.2", or "Viewing v1.2" in a baseline), read from the real baseline list.
- **Rail items:** *Scope* — Dashboard · Business functions · Data flow diagram · Data entities ·
  Organisation · Systems · Solutions · Function requirements · Interfaces; *Control* — Effort ·
  Baselines; *Admin* — Settings · Project & access (admins). An item whose component is off is hidden (D-37);
  opening its address shows why instead of its content (`ComponentOff`). Presentation only: the
  guards still refuse.
- **Business requirements are part of the function chart** (D-53): there is no BR list; a BR is
  read and edited in its process's panel, and the BR page stays as a deep link
  (`/p/:id/requirements/:brId`) crumbed under Business functions.
- **The process panel is ranked** (D-63, D-66): primary — the process name, its path, the
  requirement statement (largest field), business logic, Draft/Confirmed, BR number and the
  **readiness light** (D-68); secondary — four tiles (performer, what starts it, Accountable, data
  in/out), each opening its editor; then **Solutions** and **Function requirements** as two sections
  of their own, ranked first and second of the collapsed sections, each with its count and a
  one-line summary — Solutions when SOLUTION is on, Function requirements when FUNCTION_REQUIREMENT
  is on, independently of SOLUTION (D-52) — open the first time, then remembered per person; then,
  collapsed with counts — external parties, **Description**, supporting systems, and the optional
  **volume** figures with their derived hours and FTE (D-67, 13c); a ⋯ menu for make process,
  retire, restore and the BR page. It shows **one RACI, the BR's** for a to-be process (D-64). Tree
  and panel scroll independently, side by side from 1100 px and one at a time below it. Static
  labels are at least 12.5 px, on a 4-step type scale, with help behind (i).
- **Purpose and Data processing** (S-P): on an L1–L4 box the description is its **Purpose**; on a
  process both the Purpose and the Data processing text sit in the collapsed Description section.
- **One save model on the process panel** (SP-1): typed text (name, statement, logic, descriptions)
  waits for **Save**, with an unsaved-changes counter and Ctrl+S; everything else — ticks, pickers,
  status, links — saves the moment it changes. The performer and trigger editors have no Save of
  their own: **Done** closes them, already saved.
- **Who performs it and what starts it** (D-56, D-57): the performer heads the panel as "Performed
  by …" ("Not assigned" when none) and is editable whatever the DFD setting (S10c-2). *Started by*
  lists the editable time / event triggers (with the DFD) and, read-only beside them, the process's
  other starts — its input data entities and inbound flows from outside parties — each labelled by
  kind; "Nothing starts this process" only when all three are empty.
- **The readiness light and the DFD marks** (D-68, D-69): on every process row of the function
  chart (always visible) and in the panel header — colour **plus** icon **plus** text ("Ready",
  "Partly", "Not ready"), never colour alone; the tooltip lists the missing elements, and a red one
  says it blocks the freeze. A "Not ready only" chart filter (every process not Ready, red and yellow). Each field the chart's DFD rule needs
  carries a small "DFD" mark with the note "Needed to complete the DFD" — one on *Started by*
  ("Any one of: a trigger, a data input, or an inbound external party"), one on the out half of
  the *Data* tile, one on its in half only when the rule holds DATA_IN — met shown by a tick,
  missing by the amber dot. Met / missing comes only from the server's `dfd_missing` codes, never
  from whether a tile looks empty. Light colours come from `STATUS_COLOR_MAP` tokens.
- **The project's DFD rule** (D-70) is a project settings screen: per chart, the elements with
  plain descriptions, the recommended and locked ones marked; an admin ticks the set, sees the
  preview (how many processes turn red / yellow / green and how many would block the next freeze),
  and saves. Everyone else sees it read-only.
- **The DFD has its own screen** (D-54): a flat, searchable list of DFDs — one per direct parent
  of processes, with code, name, process count and readiness counts (D-68) — and the selected
  diagram on the right, where an editor may draw connections (D-65, §7.14).
  Wider roll-up diagrams open from the function chart.
- **Organisation and Systems are rail items under Scope** (D-56). Organisation holds the org units
  and roles; Systems — the Applications master list — shows when APPLICATION is on. The old Settings
  addresses (`settings/organisation`, `settings/applications`, `settings/applications/:appId`)
  redirect to them, keeping ids and query. Non-process boxes carry plain-language guidance (D-57):
  inputs, outputs, roles and parties are recorded on processes, the lowest level — open a process
  below this function, or turn this function into one, with a button for each: **Open a process
  below** (lists this function's processes) and **Make this a process**, behind a confirmation that
  says what it does — a BR is created and numbered, never reused; the box can no longer hold
  sub-steps; undoing it means retiring that BR; a process missing its DFD rule's elements blocks the
  next freeze. The button shows only where the switch is allowed (level ≥ 3, no children). Viewers
  see the text only.
- **A BR shows the attributes of every data entity it touches** (D-60a): in the CRUD grid each
  linked entity expands to its live attributes, read-only, with the "keys only" hint under `FULL`.
  With slice 11 the same grid ticks the attributes the BR uses (C / R / U), and the panel holds the
  BR's numbered requirement lines and its system-to-system flows, each flow showing "covered by
  FR-…" or "no interface yet" (§4.3).
- **New projects are assigned-only** (D-62): the admin "New project" form preselects "Assigned
  consultants only"; the labels read "Assigned consultants only" / "Open to all staff", and the home
  page tags the open projects, the exception. After a create the admin lands on the new project's
  Access screen to add its members. Existing projects are switched one by one by an admin on their
  Access screen, after the team is checked; the restrict preview flags kept members whose level
  drops (S10c-2).
- **Two dashboards** (D-58): Scope (coverage and gaps, open warnings, effort by solution, change
  since the last baseline) and Project management (baselines and approvals, change requests,
  risks, issues, WBS progress). Each tile appears when its wave lands, never with invented
  numbers.
- **Engagement selector.** It lists only what `visible_project_ids(user)` returns, programs
  first with their projects. Program context (`/g/:programId`) shows only roll-ups; any
  drill-down opens the per-project screen under `/p/:projectId`, so project screens never mix
  projects.
- **Screens follow their mockup's layout** (side panels, tiles, tags, level badges, RACI
  toggles); screens with no mockup (users, admin, settings, rate card, effort, interfaces,
  applications, WBS, control rules) compose the same kit. **Nothing is faked:** a mockup element
  whose data or feature is not built yet (issues, history, search) is left out until its wave,
  not drawn empty or with invented values (D-51, S1-9).
- **Edit controls hide through `app/useCanEdit.js`**, which reads the project's
  `my_access_level` from `GET /projects/{id}`, and components through `app/useComponents.js` —
  never computed from memberships in the browser.

### 14.4 Read-only baseline mode

- A baseline opens under `/p/:projectId/baselines/:baselineId` and reads **only** the baseline
  read routes (`GET /baselines/{id}`, `/rows/{entity}`). **Those routes have no write
  counterparts**, and the snapshot tables reject UPDATE and DELETE by trigger. The UI mode is a
  convenience; it is not the control.
- A banner states "Viewing v1.2 · frozen 14 Nov · read only", with a way back to the working
  set, and the header chip reads "Viewing v1.2". Edit controls are **absent, not disabled**, so
  nobody hunts for why a button does nothing.
- Diagrams in baseline mode render with today's saved positions or auto-layout (A-52).

### 14.5 Untrusted text, the token and the browser

Everything a client, a spreadsheet or an AI-converted file wrote is untrusted: BR text,
issue text, names, labels, `source_ref`, code labels, file names.

- **Rendering is React's default text escaping, and nothing else.** ESLint fails
  `dangerouslySetInnerHTML` (`react/no-danger`), `innerHTML`, `outerHTML` and
  `insertAdjacentHTML`; Markdown rendering is not used. URLs in text are not auto-linked.
  Long text renders with `white-space: pre-wrap`. PDFs render untrusted text as text, exactly as
  the browser does (D-42).
- **Token: the FTC scaffold standard** — a Bearer JWT in `localStorage`, attached by one
  axios interceptor; a 401 clears it and returns to login; remember-me 30 days, 1 day
  otherwise; no refresh token. It carries only `sub` and `exp` (S4), and `current_user`
  re-reads the user on every request, so deactivation applies on the next request. An httpOnly
  cookie was not taken: it would be a playbook deviation and bring CSRF handling with it.
  **The compensating controls are the rendering rule above plus a strict
  Content-Security-Policy**, set by the hosting config (§15.2): `default-src 'self'; script-src
  'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self';
  connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action
  'self'`, with no inline script and no `eval`. `style-src 'unsafe-inline'` is needed by
  MUI/Emotion (deviation 13). **Revisit if Entra SSO is adopted** (§15.4).
- **Canvas exports** (PNG, SVG) serialise text nodes only. No `foreignObject` and no HTML
  from user content in an exported SVG. Mermaid export goes through `escape_mermaid()`
  (R2-S7).
- File downloads get server-generated names. Uploaded file names are shown as text only and
  travel percent-encoded in `X-VB-File-Name`.

### 14.6 The diagram canvas — build rules from the spike

One component, `<ModelCanvas kind="dfd" | "erd">`, in `frontend/src/canvas/` (VB law 8). The
canvas spike returned **GO**, with these rules:

- `onlyRenderVisibleElements` **always on**. React Flow does not virtualise by default,
  and the 200-entity case needs it.
- A **simplified low-zoom view** below zoom 0.45: row text and dashes hidden with
  `visibility`, never `display: none`, so handle positions stay valid.
- ELK runs in a **web worker**. Settings: `layered`, `ORTHOGONAL` routing, `BRANDES_KOEPF`
  node placement (never `NETWORK_SIMPLEX`: 35 s at 200 entities), and `FIXED_POS` ports at
  each key-field row. The DFD's left-to-right rank comes from the derived order (§7.14).
- **Handle ids never change**: `{s|t}-{L|R}-{fieldId}`. A collapsed card stacks every
  key-field handle on its summary row instead of switching ids.
- Composite FKs group on `(ref_data_entity_id, fk_group_no)` (§5.3 DATA_FIELD).
- **Pinned cards on auto-arrange**: ELK lays out everything, pinned cards return to their
  saved positions, and overlapping unpinned cards are pushed clear. Lines touching a moved
  card fall back to smoothstep until the next arrange.
- Edges are rebuilt on layout, drag end, collapse and selection — never on every drag frame.
- Positions save on **drag end**, debounced, through `canvas/useLayoutSave.js` →
  `PUT /projects/{id}/diagram-layouts/...` (D-30). A connection drawn on the DFD writes the same
  step I/O, external-flow or trigger row the panel writes, through the same writer (D-24, D-31,
  D-65); a derived order edge is never a drawable or removable object.
- The React Flow attribution stays visible; the MIT edition is used, not Pro.
- **Every diagram has a table view** of the same data, which is the keyboard and
  screen-reader path.

### 14.7 Forms, conflicts and imports

- Every edit form sends `row_version`. **A 409 opens one `ConflictDialog`**: "Updated by
  another user", the current values beside the user's unsaved ones, and a "Reload and
  reapply" action that keeps what they typed. Submit is disabled while a request is in
  flight (P10).
- **One `ImportWizard` for every import** — today data entities, data fields and the
  whole-data-model workbook (S4-12); later BR, FR, Issue, WBS and the flow file: Upload →
  Validate → Preview → Commit. Errors and warnings show the sheet row or the `source_ref`. Any
  batch that inserts requires typing the insert count (R2-P2). For a flow file, the anchor and
  mode are chosen in the wizard, never taken from the file (R2-P3), and replace mode lists every
  RETIRE row.
- **Strings go through `t()`**, one file per screen area: `i18n/en.json` (shell) plus
  `en.<area>.json`, keys prefixed by area. No hard-coded UI text in a screen.

### 14.8 Language

The UI is in English today, and every string already goes through `t()`. **English, Japanese
and Thai arrive in wave 4** (D-44): each user chooses a language, and PDFs and the offline viewer
file print in the language of the user who generates them. Every screen string and every seeded
`code_master` label is translated; **content typed by consultants is never translated** and shows
as typed. Client content is often Japanese, hence Noto Sans JP; Thai needs Noto Sans Thai beside
it.

---

## 15. Deployment on Azure (D-35)

### 15.1 Environments

| Environment | Where | Data |
|---|---|---|
| Local | Build machine, PostgreSQL 16 | Seeded fake data only. API on port 8100, web on 5180 |
| Dev | Azure Japan East (the prod region, so a restore drill never moves data across regions), own resource group, disposable | Seeded fake data only. **Never client data** |
| Prod | Azure Japan East, FTC tenant | Real engagements |

This is the environment switch `env-switch` reports on. A write is never made before the
target is confirmed.

### 15.2 Production topology

- **Frontend**: Azure Static Web Apps (Standard), custom domain, TLS. The CSP and security
  headers of §14.5 (plus `X-Content-Type-Options: nosniff`, `Referrer-Policy:
  strict-origin-when-cross-origin`, HSTS) are set in `staticwebapp.config.json`.
- **API**: Azure Container Apps, with a minimum of 1 replica so the first request of the
  day does not cold-start. HTTPS ingress only. uvicorn runs with `--proxy-headers
  --forwarded-allow-ips=<ingress range>` so audit rows record the caller's address, not the
  proxy's (sara L11).
- **First admin**: first-run setup is switched off in every Azure environment
  (`ALLOW_FIRST_RUN_SETUP=false`); the first platform admin is created with
  `python -m seeds.create_admin`, run by Ben as a one-off Container Apps Job (sara H1).
- **Database**: Azure Database for PostgreSQL Flexible Server (PostgreSQL 16), **private
  access only** — VNet-integrated, no public endpoint. The Container Apps environment sits
  in the same VNet.
- **Identity, no stored passwords**:
  - The API's managed identity signs in to PostgreSQL through **Entra authentication** as
    the `vb_app` role, so there is no database password to hold.
  - Migrations run as a **Container Apps Job** with its own managed identity mapped to
    `vb_owner`. The API's identity cannot run DDL.
  - `JWT_SECRET_KEY` lives in **Key Vault**. The Container App reads it through a Key Vault
    reference, with its managed identity holding only *Key Vault Secrets User*. It is never
    in plain app settings and never in the repo. The app refuses to start without it (§9.1).
  - The Flexible Server admin account is break-glass only, held by Ben.
- **Database grants** (§6.6, R2-S9): `vb_app` has SELECT / INSERT / UPDATE, and DELETE only
  on `diagram_layout` and `import_row`. It has no UPDATE on `baseline_*`, `audit_event` or
  `decision`, a column-level UPDATE on `baseline` and `import_batch`, and no INSERT or UPDATE on
  the retired `user_access_grant` and `bfc_node_flow`. `vb_owner` owns the schema.
- **Upload limits at ingress** (R2-S8): ASGI middleware rejects a request whose
  `Content-Length` exceeds the route's cap, and counts streamed bytes for chunked bodies,
  **before the handler runs**; a capped upload route without a Bearer header gets 401 before a
  byte is read. The body stays in memory (at most the route's cap) and is never spooled to disk.
  Nothing uploaded is ever written to persistent storage.
- **Logging**: Application Insights / Log Analytics capture request method, route, status,
  duration and user id. **Never** request bodies, query parameters carrying content, SQL
  parameters, JWTs or file contents. Retention 90 days.
- **Scheduled job**: the daily `purge_import_rows` (Q14, §7.12b) is part of the production deployment.
- **CI/CD**: GitHub Actions with an OIDC federated credential (no stored cloud secret):
  test → build → migration job → new revision. A destructive migration needs a manual
  approval on the production environment (§13).

### 15.3 Backup, restore and evidence retention (R2-S10, Q12)

Point-in-time restore is disaster recovery. It restores the **whole server**, reverting
every other client's work too, and keeps at most 35 days. It is therefore **not** the way
back from one wrong freeze, and not five-year evidence.

| Layer | What | Kept |
|---|---|---|
| Disaster recovery | Flexible Server point-in-time restore, geo-redundant backup | 35 days |
| **Baseline evidence archive** | At every freeze, that baseline's snapshot rows and content hashes are written as one JSON file to Blob Storage under a **locked immutability policy**, **encrypted with that project's own key in Key Vault** | **5 years**, unless the client contract requires deletion (Q15) |
| Logical dump | Monthly `pg_dump` to immutable Blob Storage | 13 months |

- **Reversing one project** means restoring that project's baseline archive into a side
  database, verifying hashes, and reading or re-importing from there. No other project is
  touched.
- **Contract-required deletion (Q15)** — the contract wins over the 5-year default.
  Write-once storage cannot be deleted early, which is what makes it evidence, so each
  project's archive is encrypted with its **own key**. `purge_project`, platform-admin only
  and with a recorded reason, deletes the project's live and snapshot rows (run as `vb_owner`,
  the one hard-delete path of business data in VB) and **destroys that project's key**. Because
  the reject trigger fires for the owner too, the purge disables the triggers inside its own
  transaction, deletes shadows before live rows and the header last. The archive files remain
  but can never be read again. The monthly logical dump ages out within 13 months; the purge
  record states that date. An `AUDIT_EVENT('PROJECT_PURGED')` keeps the project code, client,
  date, actor and reason — no content.
- **Restore drill before first client use** (§12.3): (a) point-in-time restore to a new
  server; (b) recover one project's baseline from the archive into a side database, with
  hashes verified. The result is recorded in the session handoff.

### 15.4 Authentication

JWT (FTC scaffold standard) for MVP, by email and password. **Entra ID single sign-on is
optional**, to be decided before the first client engagement. If it is adopted: reject
`userType = Guest` (client staff invited to Teams would otherwise pass sign-in; client access
exists only as a client viewer account bound to one consented project, D-43), keep `create_user`
as the only way an account is made, with no just-in-time creation, and revisit the token storage
of §14.5. *(Tracked: R2-S11.)*

### 15.5 Operations

Alerts to Ben on: API 5xx rate, repeated login failures for one account, database CPU and
storage, backup failure, and a Key Vault access denial.

### 15.6 Assumptions

- `ASSUMPTION A-63` — **The repository is hosted on GitHub**, so GitHub Actions and OIDC
  apply.
- `ASSUMPTION A-64` — **One production instance serves all FTC engagements** (A-13 single
  tenant). A client demanding its own instance is a separate deployment of the same build.
