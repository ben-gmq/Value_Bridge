# Value Bridge — Design Spec

**App:** Value Bridge (VB) · **For:** Fortience Consulting Inc. — Strategic PMO practice
**Scope of this spec:** MVP — Scope Management & Control
**Status:** **SIGNED OFF by Ben, 2026-09-28, in Plan Mode.** Changes from here are proposed with evidence and approved before they land.
**Date:** 2026-09-17 · **Revised:** 2026-09-28 (D-23…D-31, Ben's v8 review) · 2026-09-28 (round-2 review, D-32…D-36) · 2026-09-29 (Slice 1 schema review, S1-1…S1-7) · **Supersedes:** nothing. Builds on `docs/ASSESSMENT_BRIEF.md`.

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

## 1a. Decision log

Product calls made by Ben in the design conversation of 2026-09-17. Recorded because three
of them override a recommendation from `apple`, the modelling agent, and a reviewer needs to
see that the override was deliberate.

| # | Decision | Effect | Overrides |
|---|---|---|---|
| D-1 | Purpose is the **full transformation lifecycle**; MVP is Scope Management & Control only | §1 rewritten; §12 reframed as *later increments*, not *rejected* | — |
| D-2 | **L5 is the lowest process level and carries exactly one BR.** One BR may still have many FRs | BR ↔ L5 becomes **1:1**, enforced by `UNIQUE (bfc_node_id)` | **`apple` §5.4.1**, which recommended 1:N |
| D-3 | **Baselines freeze Data Entities, Data Fields and Function Requirements too**, not just BFC + BR + Issue | Six further shadow tables; §7.7 extended | Confirms `apple`'s §5.3 recommendation, reverses Ben's own item 6 |
| D-4 | Issues are raised by **business users and BPO staff who have no login**; FTC records them. Recorded via a **`STAKEHOLDER`** entity | New entity; `ISSUE.raised_by_stakeholder_id` + `recorded_by_user_id` | Resolves A-18 as `apple`'s option (b) |
| D-5 | **Upload/download for Issues, Data Entities and Data Fields** | Pulled out of §12 into MVP; new §7.11 and API routes | — |
| D-6 | **Concurrent update must be controlled** | Optimistic concurrency (`row_version` + 409) into MVP | Confirms `apple`'s §5 flag and A-24 |
| D-7 | **The Solution layer returns**, categorized to **Organization & Rules / People / Process / Data / Technology** | New `SOLUTION` entity between BR and FR. `FUNCTION_REQUIREMENT` now hangs off a Solution, not directly off a BR | Reverses this session's earlier "Function Requirement only" call |
| D-8 | An **Application / Technology catalogue** links to Solutions | New `APPLICATION` entity, flagged AS_IS / TO_BE / BOTH, linked to Solutions (to-be) and to BFC nodes (as-is landscape) | — |

**D-7 is the structurally largest change in this revision, and it fixes something.** With
`SOLUTION` in place, the five categories carry the load the spec was missing: a
transformation answer that is an org change, a people change or a process change is now a
first-class row, and only `TECHNOLOGY` (and sometimes `DATA`) solutions descend into
Function Requirements. That is precisely the "blueprints the whole operation, not just the
software" property §5.6 claims — previously it was true only by omission.

**Consequence I want visible:** `FR_BR` is **deleted**. BR → FR is now derived through
`BR_SOLUTION → SOLUTION → FUNCTION_REQUIREMENT`. Your original item 4 asked for BFC/BR to
link to Function Requirements; that link still exists, as a two-step path rather than a
stored row. Storing both would be the transitive redundancy `apple` warns against in
§5.4.3, and the two copies would disagree. A database view `v_br_function_requirement`
gives you the flat BR→FR list wherever a screen wants it. **See A-26 if you want the direct
link kept as well.**

### Control framework — 2026-09-18

Ben: *"control meaning I want to know the action to take in terms of different dimensions of
project management by this analysis. Control does not mean no change — there is always
going to be changes in projects."*

That reframing is the origin of D-13…D-19. The first draft could detect change; it could not
tell anyone what to do about it. Seven decisions close that gap, and Ben has called them
**mandatory requirements**, so they are specified here in full and **sequenced into waves
(§12), not deferred to a roadmap**. Nothing below is optional.

| # | Decision | Effect |
|---|---|---|
| D-13 | **Every Function Requirement carries a complexity rating, and each project carries an effort rate card** | `FUNCTION_REQUIREMENT.complexity_code` + `EFFORT_RATE` (project × FR category × complexity → man-days). **Turns every baseline diff from "12 BRs added" into "340 man-days added."** |
| D-14 | **Benefits are quantified, owned and baselined** | `BENEFIT` — measure, baseline value, target value, unit, accountable org role, realisation date. Linked to Solution, and optionally to the L5 step it lands on |
| D-15 | **Risk is a separate entity from Issue** | `RISK` — probability × impact → exposure, mitigation, owner, status. An issue has happened; a risk might. Conflating them is why risk registers rot |
| D-16 | **Change is a first-class object, priced before it is decided** | `CHANGE_REQUEST` — impacted BRs / Solutions / FRs, effort delta from D-13, benefit delta from D-14, decision, decided_by, decided_at. **This is what lets you say no with a number attached, or say yes and name what it displaces** |
| D-17 | **Decisions are recorded** | `DECISION` — what was decided, by whom, on what date, against which analysis. "Why did we do that" is a question the app must answer six months later |
| D-18 | **Solutions are assigned to phases, and phases have dependencies** | `PHASE` + `SOLUTION_PHASE` + `SOLUTION_DEPENDENCY`. Sequencing is a control action — the commonest response to a volatility signal is *move that area right* |
| D-19 | **Every analysis has a threshold and a named owner** | `CONTROL_RULE` — project × analysis × threshold × owning org role × escalation path. **An analysis without a threshold and an owner is a report nobody acts on.** This is the smallest of the seven and the one that makes the other six operational |

**On D-13, the load-bearing one.** Scope control without a unit of size is bookkeeping. A
baseline diff that says "12 BRs added, 3 removed" cannot tell anyone whether that matters;
the same diff priced says "+340 man-days, −60" and forces a decision. It must be in the
first wave, because retrofitting a size unit after baselines exist leaves **every frozen
baseline unpriced forever** — the snapshot stores the computed `effort_days` (§5.4.4's
label-copying rule), so a baseline frozen before D-13 can never be repriced.

**On D-19, the cheapest one.** The reports in §7.9 currently return numbers. A control rule
turns each into **green / flag / escalate** against a threshold the client agreed at
mobilisation, with the role that owns the response named. It also stops the thresholds being
mine, hard-coded.

---

### Business process flow — 2026-09-24

Ben asked whether a single function could generate the business process flow from the BFC,
the data entity list and the business requirements. **Almost** — three of the four
ingredients are already modelled, and `apple` said so in §5.6: L5 nodes are the processes,
`BFC_NODE_DATA_ENTITY` the flows, `DATA_ENTITY` the stores, `BFC_NODE_ORG_ROLE` the
swimlanes, `APPLICATION` the systems.

**The missing ingredient is sequence.** The BFC gives *hierarchy* and *sibling display
order*. It does not say that step 3 follows step 2, and it cannot express a branch, a join,
a rework loop or a hand-off to another business area. A process flow without decision points
is not a business process flow — every real process has *"if approved… otherwise…"*.

| # | Decision | Effect |
|---|---|---|
| D-20 | **Add `BFC_NODE_FLOW`** — an explicit flow edge between level-5 nodes | from-node, to-node, `flow_type` (SEQUENCE / CONDITIONAL / PARALLEL / HANDOFF), `condition_label`. Nullable from/to express start and end events. **Loops are legal** — unlike `SOLUTION_DEPENDENCY`, rework cycles are real process behaviour and are not rejected |
| D-21 | **`generate_process_flow` returns a graph, not a picture** | The service returns nodes / edges / lanes / stores as data; the frontend renders it. A separate `export_process_flow` emits Mermaid text for pasting into a deck |
| D-22 | **As-is and to-be are the same flow rendered twice** | `variant = AS_IS` resolves systems through `APPLICATION_BFC_NODE`; `variant = TO_BE` resolves them through `BR_SOLUTION → APPLICATION_SOLUTION`. One diagram definition, two pictures, and the difference between them is the transformation |

This closes **brief question 7** and **A-12**, and removes "DFD rendering" from §12.2. It
lands in **wave 1**: the BFC, DE and BR layers it draws from are all wave 1, and the process
flow is a client-facing deliverable of the assessment itself, not a later increment.

**Cost, honestly:** one table, three functions, one `code_master` category. `BFC_NODE_FLOW`
is baselined (shadow tables 24 → 25) because an agreed as-is process flow is part of what
was agreed.

---

### Ben's review of the v8 screens — 2026-09-28

Six points from Ben's review of the UI concept canvas (v8), plus his answers to the open
questions from 2026-09-25. **These reverse one withdrawal proposed on 2026-09-25:** the
flow-edge table `BFC_NODE_FLOW` (D-20…D-22) is **kept**, not replaced by the DFD. Ben wants
a real business process flow, with sequence, that can be imported from other BPM tools, and
you cannot import a sequence into a model that has nowhere to store one. The DFD (D-31) is a
**second picture of the same rows**, not a replacement.

| # | Decision | Effect | Overrides |
|---|---|---|---|
| D-23 | **A process is the lowest node in its BFC branch, not a fixed level 5.** Ben: *"it doesn't have to be level 5, but it has to be the lowest level of the BFC."* | `bfc_node.is_process`. Every table pinned to `level_no = 5` (BR, step I/O, step roles, flow edges, as-is application) pins to `is_process` instead. A process node cannot have children. **The BR stays 1:1 with its node — D-2 now reads "one BR per process node"** | D-2's "L5" wording; A-45 |
| D-24 | **A step's input and output data entities are recorded once, on the BFC node**, and the process flow, the DFD and the BR all read that one record | The flow editor writes `BFC_NODE_DATA_ENTITY` directly. A step has 0..N inputs and 0..N outputs. **BR CRUD must agree with the step's I/O**: a Read needs an input, a Create/Update/Delete needs an output. Linking a BR CRUD adds the missing step I/O row in the same transaction; removing a step I/O row that a BR CRUD still depends on is refused | — |
| D-24a | **External entities** — Customer, Bank, Regulator, Supplier | `EXTERNAL_ENTITY` (`EXT-0001`) + `BFC_NODE_EXTERNAL_FLOW` (step × external party × direction × data entity). Drawn as the rectangles at the edge of the DFD. Baselined | — |
| D-25 | **Business process flows can be imported from a JSON file**, and VB publishes the rules of that file so an AI can convert a PowerPoint, BPMN or Visio flow into it | Published schema `vb-process-flow/1.0` + a downloadable **conversion prompt pack**. Import goes through the existing validate → preview → commit pipeline (§7.11): all-or-nothing, numbers minted at commit, the consultant approves consequences. Export writes the same format, so a flow round-trips. **VB does not call an AI itself** — the conversion happens outside, in whatever tool the consultant uses | §12.2 "BPMN out of scope" narrowed: still no BPMN XML, but a BPMN-derived JSON is importable |
| D-26 | **Data fields are logical, and a partial list is normal.** Ben: *"it doesn't have to be everything, but at least the primary key, foreign key and key attributes."* | `DATA_FIELD.data_type_code` becomes optional. New `is_mandatory` (nullable) drives optional/mandatory on the ERD. **VB models a logical data model and a logical DFD; it never generates tables** | — |
| D-27 | **The FR "functional type" is configurable, and the interface list is generated from the FRs** | `FR_CATEGORY` renamed **`FR_TYPE`** (FORM / INTERFACE / REPORT / BATCH seeded, editable per project). Each type carries a **behaviour** code, so a renamed or added type still drives the right screens and reports. New `FR_INTERFACE` (source app, target app, pattern, method, frequency) + `FR_INTERFACE_DATA_ENTITY`. **The interface list is a view whose identity is the FR number** — no second number series to keep in step | D-7's `FR_CATEGORY` name |
| D-28 | **BR and FR are imported independently, and an FR may exist with no link.** An FR with no Solution, and therefore no BR, is a **warning, not an error**. A BR with no FR was always legal | `function_requirement.solution_id` becomes **nullable**. The bulk pipeline covers **BR** and **FR** as well (§4.5a). Unlinked FRs appear in the coverage report, in the import preview and on the control panel | **D-7's "every FR belongs to a Solution"** |
| D-29 | **The ERD is generated from the data entities, as an interactive canvas** — drag entities, see the connectors | Edges are derived from FK fields; cardinality from `is_mandatory` and key uniqueness. Crow's-foot notation, logical level. Same canvas library as the process flow and DFD (§7.14) | — |
| D-30 | **Diagram positions are stored.** Something a consultant drags must stay where it was put | `DIAGRAM_LAYOUT` (project × diagram × object → x, y). Objects with no saved position are auto-laid-out. **Not baselined** — layout is presentation, not scope | D-21's "layout is the frontend's job" |
| D-31 | **The DFD is generated, not drawn** — processes, data stores and external entities from the same rows as the process flow, without sequence | `generate_dfd` / `export_dfd` beside `generate_process_flow`. No new table | — |

**Answers recorded the same day:**
- **A-35 resolved.** At most **2,000 process nodes per project**. Ben also said "per
  application"; the freeze runs one project at a time, so the bound holds either way and
  `freeze_baseline` **stays a synchronous request**.
- **External entity approved** (D-24a).
- **Diagram layout: stored** (D-30), not auto-layout only.

**On D-23, the cost I want visible.** "Level 5" was the cheapest rule in the model: a literal
in a composite FK, fully declarative. "The lowest node in its branch" is a fact about *other*
rows, and a CHECK cannot see other rows. The design keeps it declarative by storing the fact
as `is_process` and making the parent side of every child row assert `NOT parent_is_process`
through the same composite-FK trick (§5, `apple`). The price is one rule in the service:
**to split a process into sub-steps, retire its BR first.** Otherwise a node with children
would carry a requirement that describes the children's work twice.

**On D-28, the trade.** D-7 forbade a floating FR because an FR with no Solution has no path
to a BR, a phase or a benefit. It is priced (the rate card needs only its type and
complexity) but it is not traced. Ben's call is that real FR lists arrive before the
solution design does, and refusing them is worse than holding them as flagged. The control
panel's `fr_unlinked` rule is what stops "flagged" from becoming "forgotten".

---

### Round 1 design review — 2026-09-17

`design-auditor` reviewed this spec and returned **33 findings**. Blast radius was confirmed
by Ben as **internal — rework, not liability**, which re-rated P1, P4 and D4 from HIGH to
MEDIUM by the auditor's own stated rule. Net 9 HIGH · 19 MEDIUM · 5 LOW.

**30 fixed in this revision. 3 tracked in `BUGLOG.md` (VB-001…VB-003). 0 accepted.**
Findings are cited by their auditor id (P1–P10, D1–D13, S1–S11) at each fix.

| # | Decision | Effect | Closes |
|---|---|---|---|
| D-9 | **Platform admin flag + per-project role.** `app_user.is_platform_admin` boolean; per-project role is OWNER / EDITOR / REVIEWER | The `APP_ROLE` table is **deleted**. One vocabulary, one `rank`, a capability matrix in §7.8 | S1, and structurally S8 |
| D-10 | **`hier_code` may change on reorder.** Excluded from `content_hash`; a position change reports as **MOVED**, not CHANGED | A-19 resolved. Diff gains a fourth class | P4, D5 |
| D-11 | **No client-side logins in MVP.** Every `app_user` is FTC staff; client people are `STAKEHOLDER` rows | `CLIENT_REVIEWER` does not exist as a role, so there is nothing to grant by mistake. `create_user` rejects an external address until record-level confidentiality ships | S8, A-11 |
| D-12 | **`org_unit` and `org_role` are baselined too** | Freeze set 17 → **19** shadow tables *(later 24, via D-14 and D-18)*. The org chart is frozen as agreed, not as it is today | D4, A-28 |

**On D-9:** the auditor called S1 the blocking input to four other findings, and it was
right — S2 (one enforced entry point), S3 (route annotations), S8 (the Client Reviewer gate)
and P6 (who may freeze) were all unanswerable until the roles had names that exist in one
table. `rank` is now an explicit ordered list, not an undefined function.

**On D-11:** this is the better half of the fix. Gating a `CLIENT_REVIEWER` grant leaves the
role in the model for someone to reach for under time pressure. Deleting it means the
exposure cannot be created at all, and `stakeholder` stays what D-4 made it — data about a
person, not an account.

---

### Design review round 2 — 2026-09-28

`design-auditor` reviewed the spec at D-31, together with the draft D-32…D-35. This is
**round 2 of 2, the last** before build. **33 findings: 7 HIGH · 19 MEDIUM · 7 LOW**, cited
by auditor id (R2-P*, R2-D*, R2-S*) at each fix.

**All 33 were dispositioned by Ben on 2026-09-28. Every recommended fix is applied, and 0 are
accepted as risk. One is tracked: R2-S11**, which applies only if Entra ID single sign-on is
adopted. D-35 leaves SSO to the deployment design (§15).

**Five findings the auditor marked structural** — R2-D1, R2-D2, R2-D4, R2-S2 and R2-D15 —
**were ruled by Ben to be fixes, not a redesign.** Each is applied inside the existing shape:

- **R2-D1:** the BR number, which never changes, identifies an existing step on import.
  `hier_code` becomes a cross-check.
- **R2-D2:** every soft delete is refused while active dependents exist, and nothing
  cascades.
- **R2-D4:** a model-side fix (`apple`).
- **R2-S2:** program views are assembled from the existing per-project reports, not from new
  cross-project SQL.
- **R2-D15:** WBS lines are keyed by MS Project's own Unique ID.

| # | Decision | Effect | Overrides |
|---|---|---|---|
| D-32 | **Program layer, and one grant per user.** Ben: *"I should be able to register many different projects and each user tied to 1 project unless it is a program."* | New `PROGRAM` (one per group of related projects for one client). `PROJECT.program_id` is nullable, and a program's projects share its `client_id`. **The project stays a hard data wall**: nothing is shared between a program's projects. **A user holds at most one active grant, naming one project or one program**, with one role for every project in a program. **Program roll-ups** (dashboard, counts, interfaces, effort, control-panel status) **require a program grant or platform admin. They are built by calling each per-project report for the projects in `visible_project_ids(user) ∩ program.projects`, never by new cross-project SQL** (R2-S2). **Moving a project into or out of a program is platform-admin only, behind a preview that names who gains and who loses access** (R2-S3). **`grant_access` returns 409 if the user already holds another active grant. Only a platform admin reassigns** (R2-S4). **Platform admins get no auto-grant on `create_project`.** `GET /projects/{id}/access` lists **effective** access, including access derived from a program grant or the admin flag | The many-grants model (§4.7, A-21); "creator is auto-granted OWNER"; the draft's "program OWNER may move a project" (Q10) |
| D-33 | **WBS is imported, not owned, and it is optional per project** | New `WBS_ITEM`, imported from MS Project via Excel as a sixth `.xlsx` column map. **Read-only in VB** except the `PHASE` / `SOLUTION` links consultants set. **Keyed by MS Project Unique ID**, not WBS code, which renumbers on every re-plan (R2-D15). `import_mode` (merge / replace) is allowed for WBS as well as the flow JSON. The template carries a **date-format step**: ISO dates before saving. Not baselined. Feeds the program dashboard's plan-vs-actual | §12.2 "Task-level schedule — WBS", in its import-only form |
| D-34 | **An FR imported with a BR but no Solution keeps a suggested link** | `FUNCTION_REQUIREMENT.suggested_br_id`. The FR saves unlinked (warning, D-28). **The suggestion clears only when a `BR_SOLUTION` path from that BR to the FR's solution exists.** Linking the FR to a solution the BR does not reach leaves it in place, and the UI offers to add the missing `BR_SOLUTION`. **Excluded from `content_hash`.** No placeholder solution is ever created (R2-D16) | Resolves A-50 |
| D-35 | **Hosting: Azure, in FTC's tenant** | API and static frontend on App Service or Container Apps. Azure Database for PostgreSQL Flexible Server on private networking. `JWT_SECRET_KEY` and DB credentials in Key Vault, read by managed identity — never plain app settings, never the repo. App and owner DB roles as §6.6. Point-in-time restore plus a tested restore drill before first client use, and baselines recoverable for **5 years** (Q12). **Request-body limits enforced at ingress, before any handler** (R2-S8). Auth stays JWT for MVP; Entra ID SSO is decided in §15, not assumed. **Deployment design: §15** | — |
| D-36 | **Approved AI services for client content in the flow conversion: Claude or Microsoft Copilot, under FTC's own accounts only, with personal data removed first** | The conversion prompt pack (D-25) names the two services and opens with the personal-data removal step. A consultant's personal account, or any other service, is out of policy. VB still calls no AI itself (A-51). **Closes R2-S6** | §4.1a "an AI tool of their choice" |

**Ben's answers to the review questions (2026-09-28):**

| Q | Answer | Lands in |
|---|---|---|
| Q1 | **Step names are unique under a parent** (normalised: NFKC, case-folded, whitespace collapsed) | §7.2 `create_node` / rename / restore → 409; flow JSON name match (R2-P1) |
| Q2 | **Two edges between the same two steps are legal only with different conditions** | §7.2a `link_process_flow` → 409 |
| Q3 | **Priced diff = the per-FR effort delta, counted once, plus a separate "effort exposed" line** | §7.13 `priced_diff` (R2-D3) |
| Q4 | **A delete with active dependents is refused (409 naming them). A restore under an inactive parent is refused** | §7.12 `soft_delete` / `restore` (R2-D2) |
| Q5 | **Replace mode retires only flow edges and step I/O.** Never steps, never BRs, never lane roles beyond the one-RESPONSIBLE rule (at most one RESPONSIBLE-behaviour role per step; the file's lane replaces it), never I/O a BR CRUD or an external flow depends on | §7.2b (R2-P4) |
| Q6 | **A global FR_TYPE's behaviour is immutable once referenced** | §7.5 `maintain_fr_types` → 409 (R2-D8) |
| Q7 | **RACI and RASCI now; RAPID through behaviour mapping** | `RACI_TYPE` carries a behaviour; lanes and the single Accountable key on it (R2-D9) |
| Q8 | **A CR may target a FROZEN or APPROVED baseline, not a SUPERSEDED one** | §7.13 `raise_change_request` |
| Q9 | **Benefits are ranked only within one unit** | §7.13 `value_ranking` (R2-D12); A-40 |
| Q10 | **Only a platform admin moves projects. Only platform admins span unrelated projects. One role per program grant** | §7.10, §7.10a |
| Q11 | **Claude or Copilot** | D-36 |
| Q12 | **Baselines recoverable for 5 years** | D-35, A-59, §15 |
| Q15 | **A client contract requiring deletion at engagement end overrides the 5 years** — per-project crypto-shred | §6.1, A-59, §15.3 |
| Q16 | **A program OWNER may grant a single project inside their program** | §4.7 `grant_access`, §7.10 |
| Q17 | **Production region: Azure Japan East** | A-62, §15 |
| Q13 | **WBS is optional; consultants set the links** | D-33, §7.11a |
| Q14 | **Import rows purged at 90 days** | §7.12b `purge_import_rows`; closes A-32 |

**Where each service-side fix lands** (model-side fixes are in `apple`'s delta):

| Finding | Fix | Where |
|---|---|---|
| R2-P1 | Flow step with no BR number and no `hier_code` matches an active process child of the anchor by normalised name → UPDATE with a warning. Insert count acknowledged on every flow batch with inserts | §7.2b |
| R2-P2 | `acknowledged_inserts == insert_count` whenever `insert_count > 0`, not only on mixed batches | §7.11 |
| R2-P3 | Anchor node and mode are chosen in the UI and carried by the route. A file that disagrees is an error. The preview lists every RETIRE row | §7.2b, §9 |
| R2-P4 | Replace mode per Q5. I/O a BR CRUD or external flow depends on is staged KEPT with a warning. At most one RESPONSIBLE-behaviour role per step; the file's lane replaces it | §7.2b, §5.3 BFC_NODE_ORG_ROLE |
| R2-P5 | Demote is refused with a 409 naming the blockers. No cascade anywhere | §7.2, A-48 |
| R2-P6 | Freeze runs at REPEATABLE READ from its first statement; `consistency_check` runs inside the same transaction | §7.7 |
| R2-D1 | `.xlsx` BR import and flow JSON identify rows by BR number. `hier_code` is a cross-check ("moved since export") | §7.2b, §7.11 |
| R2-D2 | Soft delete refused with active dependents. Restore refused under an inactive parent. `consistency_check` gains "active row under an inactive parent"; freeze precondition | §7.12 |
| R2-D3 | Per-FR effort delta counted once; unlinked effort as its own line; separate "effort exposed"; hash codes, not labels | §7.13, §7.7 |
| R2-D5 | Flow JSON carries `row_version` per step; stale step is a per-row error; preview shows before/after | §7.2b |
| R2-D6 | FR map: `effort_days` export-only; type/complexity through the rating services; missing rate or live interface detail = row error | §7.11 |
| R2-D7 | Rate-card changes audited with old / new / rationale; frozen with the baseline | §7.13 |
| R2-D8 | Global FR_TYPE behaviour immutable once referenced → 409 | §7.5 |
| R2-D9 | Lanes and single-Accountable keyed on RACI **behaviour** | §7.2a, §7.9, §7.2b |
| R2-D12 | `(target − baseline) × pct`, ranked within one unit | §7.13 |
| R2-D13 | External-flow link uses the same `ensure_step_io` as BR CRUD; unlink names external-flow blockers | §7.3 |
| R2-D14 | `create_project` seeds all ten number series | §7.10 |
| R2-D15 | WBS keyed by `ms_unique_id`; `import_mode`; ISO date step | §7.11a |
| R2-D16 | As D-34 | §7.5 |
| R2-S1 | Guard registry: every route declares exactly one guard; criterion 49 fails any route that declares none | §7.8, §9, §10 |
| R2-S2/S3/S4 | As D-32 | §7.8, §7.10, §7.10a |
| R2-S5 | `restore` has an allow-list; grants, control rules, users and `code_master` excluded | §7.12 |
| R2-S6 | As D-36 | §4.1a, §7.2b |
| R2-S7 | One `escape_mermaid()` for every Mermaid writer | §7.12b |
| R2-S8 | Body-size limits at ingress, before the handler; temp spool location stated | §7.12b, §7.11 |
| R2-S11 | **Tracked**, conditional on Entra ID SSO | `BUGLOG.md`, §15 |

**On D-32, the cost I want visible.** Per-project roll-ups are N report calls, not one query.
That is slower than a UNION, and it is the point. Each call passes through `require_project`
exactly as a screen would, so no new SQL path exists that could see a project the caller cannot.
A program of ten projects is ten calls (A-57).

**Resolved while merging the round-2 deltas (2026-09-28).** `apple` asked whether a step may
have two RESPONSIBLE roles, and if so which is its lane. **No: a step has at most one
RESPONSIBLE-behaviour role, and a flow file's lane replaces it** (A-46, R2-P4). The database
holds the rule as a partial unique index keyed on behaviour, not on the letter `R` (§5.3
BFC_NODE_ORG_ROLE, §6.2). Zero remains legal: the step is drawn in the "unassigned" lane and
reported. **Resolved by Ben the same day (Q15): a client contract that requires deletion at
engagement end overrides the 5-year baseline retention.** Five years is the default when the
contract says nothing. The mechanism is per-project crypto-shredding of the evidence archive
(§15.3), so the archive's storage stays write-once.

### Slice 1 schema review — 2026-09-29

Before migration 0005, `apple` turned §5–§6 into a physical spec for the Slice 1 tables
(`docs/slice1_schema.md`, whose `[Q-n]` numbers are cited below). Three items are defects in
the signed-off text; the rest close gaps. **Ben approved S1-1…S1-9 on 2026-09-29**, on the
test that anything which would otherwise need a schema change later is fixed now. Where
these rows and the section they cite disagree, **these rows win**.

| # | Decision | Supersedes | apple |
|---|---|---|---|
| S1-1 | **Sibling order covers the roots.** `UNIQUE (project_id, parent_*_id, seq_no) NULLS NOT DISTINCT WHERE is_active` on `bfc_node` and `org_unit`. A NULL parent (L1) is one shared parent per project | §5.3 BFC_NODE, §6.2 (`(parent_bfc_node_id, seq_no)` let two L1 nodes share a position) | Q-1 |
| S1-2 | **Reorder writes codes in two phases.** `renumber_subtree` first sets `hier_code = '~' \|\| bfc_node_id` on every affected row, then writes the final codes. The affected set is **every shifted sibling and all their descendants**, not only the moved node's subtree. `hier_code` is `varchar(40)`. Field reorder (`data_field.seq_no`) uses the same two-phase pattern | §7.2 (a swap hit the live `hier_code` index mid-update) | Q-2 |
| S1-3 | **Position range** `CHECK (seq_no <> 0 AND seq_no BETWEEN -99 AND 99)` on `bfc_node` and `org_unit`: at most 99 siblings, negatives only during a reorder. **`data_field` uses ±999** (it has no two-digit code; Ben, 2026-09-29) | §5.3, §4.1 (two-digit pad broke at 100) | Q-3 |
| S1-4 | **Lookups are category-verified.** Each code FK in the slice (`org_unit.level_code_id`, `data_field.data_type_code_id`, `external_entity.kind_code_id`, `business_requirement.status_code_id`) gets a generated constant `*_category` column and a composite FK to `code_master (code_id, category)` (`uq_code_category_target`). Project scope stays with `code_master.resolve` plus a `consistency_check` line | §5.3, §6.2 (only RACI and FR type were verified) | Q-4 |
| S1-5 | **Link rows have their own identity.** `bfc_node_data_entity`, `br_data_entity`, `bfc_node_org_role` and `br_org_role` get a surrogate identity **primary key** `<table>_id`; the design's composite key becomes a `UNIQUE NOT NULL` constraint, and every FK that targeted it still does. This is what lets `baseline_shadow.py` snapshot them unchanged (it records the PK as `source_id`) | §5.3 junction PKs, §6.1 | Q-12, taken as surrogate-PK rather than apple's generator change |
| S1-6 | **User-entered names and codes are unique among live rows**, normalised `lower(btrim(…))`: `data_entity.de_name`, `data_field.field_name` (and `pk_ordinal`), `org_role.org_role_code`, `org_unit.org_unit_code`, `external_entity.ext_name` (Ben, 2026-09-29; §6.2 had `lower(ext_name)`). Minted numbers keep full UKs (§5.1) | §5.3, §6.2 (full UKs blocked re-adding a retired name) | Q-6, Q-7, Q-8 |
| S1-7 | **Smaller items.** `org_unit` depth held by the service + `consistency_check` (column `level_code_id`); `org_role → org_unit` is composite `(org_unit_id, project_id)`; `br_statement` is nullable and the service sets `BR_STATUS/DRAFT`; `fk_group_no` — the request names the relationship (`new` or an existing group), the service assigns the number; `business_requirement.bfc_node_id` immutability is service-enforced; re-linking a retired link **restores** the row, never inserts; `raci_category` is `varchar(40)`; apple's four sanity CHECKs | §5.3, §7.2–§7.4 | Q-9…Q-11, Q-13, Q-14, Q-16…Q-18 |
| S1-8 | **Build-review calls (Ben, 2026-09-29).** A BR's `BASELINED` / `SUPERSEDED` status is set only by the baseline freeze; `update_br` refuses them (422). The RACI link routes are `/bfc-nodes/{id}/org-roles` and `/business-requirements/{id}/org-roles`, not `/roles` (VB law 7). `/org-units/{id}` and `/org-roles/{id}` join the §9 object-guard list | §9, §7.3 | sara M5, L9 |
| S1-9 | **Screens (Ben, 2026-09-29).** The top-bar item **Processes opens the business function chart**; the process flow arrives later as a view of it. **Client organisation and external parties live under Settings** (configuration and master data), beside people and access. **The mockups' extra fields are not built**: BR trigger, frequency and priority; DE owning area and master-candidate switch. A requirement priority was checked against the design: nothing reads one — prioritisation is per solution (`value_ranking`, D-14; phasing, D-18) | §14.3 | — |

**Deferred, not decided:** `bfc_node_flow` moves to the process-flow slice (Q-15), and whether
`FLOW_TYPE` becomes a CHECK column is decided with it (Q-5, Ben 2026-09-29) — **both now settled by S2-1**. **For the shadow
slice:** the generator will also copy `purpose_desc`, `output_expectation` and
`business_owner_note`, which §5.2's shadow blocks omit, and still needs code labels and
baseline-id remapping of parent keys.

### Slice 2 schema review — 2026-09-30

`apple` made §5.3 `BFC_NODE_FLOW` and `DIAGRAM_LAYOUT` physical (`docs/slice2_schema.md`,
`[Q-n]` cited below). **Ben approved every recommendation on 2026-09-30.** As with S1, where
these rows and the section they cite disagree, **these rows win**.

| # | Decision | Supersedes | apple |
|---|---|---|---|
| S2-1 | **`flow_type` is a CHECK-listed column**, `IN ('SEQUENCE','CONDITIONAL','PARALLEL','HANDOFF')`, not a `code_master` FK. "A CONDITIONAL edge needs a label" is a table CHECK (`ck_bnf_conditional_label`), so `consistency_check.conditional_without_label` and `flow_completeness_report.unlabelled_branch` are dropped. The `FLOW_TYPE` category leaves the seed and its seeded rows are retired once | D-20 ("one `code_master` category"), §5.3, §6.2, §8 | Q-5 |
| S2-2 | **An edge's ends are fixed after create.** PATCH carries `flow_type`, `condition_label`, `seq_no`, `note`; re-pointing is remove + add. Twin restore happens on create only, and only after both ends are checked live, process and in-project | §9 `PATCH /process-flows/{id}`, §7.2a | Q-2, Q-8 |
| S2-3 | **`seq_no`** is optional, 1–99, not unique, set by the consultant; render order `seq_no NULLS LAST, id`. It is snapshotted but **not** part of `content_hash` | §5.3 | Q-3, Q-4 |
| S2-4 | **Self-loops are legal** (no CHECK); the flow import warns on one. **A HANDOFF with no `to` step names the receiving party in `condition_label`** | §5.3 | Q-6, Q-7 |
| S2-5 | **Indexes.** Full `ix_bnf_from` / `ix_bnf_to (…_bfc_node_id, project_id)` (the partial natural key cannot serve the guard-FK checks); five partial object-FK indexes on `diagram_layout`. Label twins match on `normalise_name`; the latest retired twin is restored | §6.3 | Q-1, Q-9, Q-15 |
| S2-6 | **`diagram_layout` physical shape.** `vb_ops.presence_columns()` (four audit columns, no soft delete, no `row_version`); `uq_dl_object` is a table constraint so `save` upserts `ON CONFLICT ON CONSTRAINT`; `PUT` upserts only the listed objects, and a separate audited `DELETE /diagram-layouts/{type}/{scope_key}` resets a diagram; scope and EVENT markers are service-validated; `ck_dl_collapse_erd` added. `vb_app` gets DELETE on this table only, and the grant test asserts exactly that set | §5.3, §9, §6.6 | Q-10…Q-14, Q-16, Q-17 |

### Slice 4 schema review — 2026-10-01

`apple` made §5.3 `IMPORT_BATCH` and `IMPORT_ROW` physical for every import target (`docs/slice4_schema.md`,
`[Q-n]` cited below). **Ben approved all 22 recommendations on 2026-10-01.** As with S1 and S2,
where these rows and the section they cite disagree, **these rows win**.

| # | Decision | Supersedes | apple |
|---|---|---|---|
| S4-1 | **Locator CHECK fixed.** RETIRE / KEPT rows are staged from the database and have no file locator. Replaced by `ck_ir_locator`: none for RETIRE/KEPT, a JSON pointer for flow rows, a sheet row for sheet rows | §6 `num_nonnulls(sheet_row_no, source_path) = 1` (a defect) | Q-1 |
| S4-2 | **`import_row` carries `target_entity`**, with a composite FK to its batch and `ck_ir_kind_fits_target`, so a row kind can never mismatch its batch. What a RETIRE/KEPT row acts on is `payload.target {table, id, label}`, CHECK-required | §5.3 | Q-2, Q-3 |
| S4-3 | **`committed_target_id` is set for every committed row except LANE.** STEP_IO and STEP_ROLE have their own ids since S1-5 | §5.3 (out of date) | Q-4 |
| S4-4 | **Duplicate keys are caught in memory before staging.** Later copies are staged with the key NULL and a `DUPLICATE_KEY` error; the partial unique indexes stay as a backstop | §7.12 | Q-5 |
| S4-5 | **A data field's import key is `DE-nnnn/<normalised field name>`** (`varchar(250)`). Renaming a field by spreadsheet arrives as an acknowledged INSERT; renames are done on screen | §5.3 (no field key) | Q-6 |
| S4-6 | **Audit exemptions (deviation 7c).** `import_batch` has no soft delete (its status is its lifecycle) but keeps `row_version`, sent on commit (stale preview → 409); `uploaded_at` / `uploaded_by_user_id` are its created pair. `import_row` has no audit columns. Added: `committed_by_user_id` and `file_warning_detail jsonb` | §5.1 audit columns, for these two tables | Q-7, Q-8, Q-9 |
| S4-7 | **Counts and status.** `row_count` = staged rows; `error_count` / `warning_count` count rows, not messages; verdict counts include invalid rows; MATCH and KEPT are not counted on the header; `ck_ib_retire_needs_replace`. VALIDATING exists only inside validate; VALIDATED even with errors; a failed re-validation at commit sets REJECTED in a follow-up transaction. IMPORT_STATUS resolves from the global tier only | §5.3, §7.12 | Q-10…Q-12 |
| S4-8 | **Messages are objects** `{code, column, message, params}` (i18n, untrusted text). **Before/after is computed at preview, never stored.** Key and `source_ref` lengths are capped in the flow JSON Schema; `file_name` is a sanitised basename of at most 255 characters | §7.11, §7.12a/b | Q-13…Q-15 |
| S4-9 | **Locks, grants, keys.** The purge locks batches first (`FOR UPDATE SKIP LOCKED`), so it can't deadlock a commit. `vb_app` gets DELETE on `import_row` only, plus a column-level UPDATE grant on `import_batch` (write-once trail). No process guard on the anchor; it is service-checked. `uq_import_batch_project` is created now, for WBS. The added CHECKs hold. One staged row per sheet row or pointer | §6.6, §5.3 | Q-16…Q-21 |
| S4-10 | **Criterion 40 reads "after re-upload".** A commit is all or nothing, so the other rows never "still commit" | §10 criterion 40 (wording) | Q-22 |

### Slice 3 step retire — 2026-09-30

| # | Decision | Supersedes | Spec |
|---|---|---|---|
| S3-SR | **A process step retires with its requirement and flows**, in one confirmed, undoable action (Ben, 2026-09-30). Everything else keeps refuse-with-dependents. No schema change | Q4 / R2-D2 "nothing cascades" (§7.12), **for process steps only** | [`docs/step_retire_spec.md`](step_retire_spec.md) |

---

**D-8 attaches one level up from where you first chose it.** You picked "link Applications
to Function Requirements plus as-is on BFC" before `SOLUTION` existed. Now that it does,
Applications link to **Solutions** — which is also the word you used — and an FR inherits
its application through its solution. Linking at both levels would be the same redundancy
as above. If a single FR ever needs a different application from its parent solution's,
that is a genuine finding and the model should flag it, not absorb it silently (A-27).

On D-2: I put the counter-argument in §5.4.1 and Ben held. It is recorded there in full so
that if an L5 step ever needs two requirements, the cost of the reversal is visible and the
reasoning is not lost. The BR stays its own table with a unique constraint rather than
collapsing into `bfc_node` — see §5.4.1a for why that matters.

---

## 2. Playbook / doctrine references

Bound by `~/.claude/ftc-playbook.md` (v1.3). The non-negotiables this design leans on
hardest, by number:

| # | Rule | Where it bites in this app |
|---|---|---|
| §9.1 | `JWT_SECRET_KEY` from env only, no fallback | Scope area 7 (auth) |
| §9.2 | `created_by` from the JWT, never the request body | Every business table; baseline `frozen_by` likewise |
| §9.3 | All lookups in `code_master`, send the code not the label | FR type, issue severity/type/status, org unit level, project role |
| §9.7 | Soft delete `is_active = FALSE`, no hard DELETE | All business entities. **Baseline snapshot rows are the exception** — see §11 A-7 |
| §9.8 | **IDs generated at save time only** — never on screen load or preview | Directly governs BFC / BR / DE / FR / Issue number generation (scope areas 1–5) |
| §9.10 | Shared logic in ONE service file | Number generation and the visibility predicate are each one service, used everywhere |
| §9.11 | Three-layer rule: Router → Service → Model | Visibility filtering lives in the service layer, never in a router |
| §7 | Standardized error handling, `detail` string | 409 on optimistic lock when two consultants edit one BFC node |

Any deviation gets a recorded reason in `docs/PLAYBOOK_DEVIATIONS.md`.

---

## 3. The keystone grain

> **`BUSINESS_REQUIREMENT` — one row per process node.**

A **process node** is the lowest node of its BFC branch (`bfc_node.is_process = TRUE`, D-23). It
sits at level 3, 4 or 5 (A-47), an L5 node is always one (A-54), and it has no children. Process
node → BR is **1:1** (D-2, restated by D-23), enforced by the partial `UNIQUE (bfc_node_id) WHERE
is_active` and by a composite FK that accepts only an active process node. Everything
downstream anchors here: Solutions answer BRs, Issues are raised against BRs, Data Entities
attach to BRs with a CRUD use (licensed by the step's own I/O, D-24), and a baseline freezes
the BR set.

One BR may still lead to **many** Function Requirements — via one or more Solutions
(D-7). The fan-out the earlier draft put on BR-per-node now lives where it belongs, on the
answer rather than on the question.

Grain of every other table, one sentence each:

| Entity | One row per… |
|---|---|
| `CLIENT` | client organization FTC has engaged with |
| `PROGRAM` | named group of related projects for one client (D-32) — a **roll-up and access scope, not a data layer**: it holds no scope of its own and is never baselined |
| `PROJECT` | transformation project — the scoping key on every business table, and **the data wall**: nothing is shared between projects, even within one program (D-32) |
| `BFC_NODE` | business function at one level (1–5) within one project. `is_process` marks the lowest node of a branch — a **process node** (L3–L5, D-23), which carries a BR and has no children |
| `BFC_NODE_DATA_ENTITY` | (process node × data entity × direction) — *that* data flows into or out of a step. **The one record of a step's I/O** (D-24): the flow editor, the DFD and BR CRUD all read it |
| `BFC_NODE_ORG_ROLE` | (process node × org role × RACI code) — who performs a step. The code's **behaviour** (RESPONSIBLE, ACCOUNTABLE …) is copied onto the row and FK-verified (Q7) |
| `BFC_NODE_FLOW` | one flow edge between two process steps — what follows what, and on what condition. Two live edges may join the same two steps only if their conditions differ (Q2) |
| `EXTERNAL_ENTITY` | party outside the client organisation that exchanges data with the client's process steps (Customer, Bank, Regulator, Supplier), within one project — `EXT-0001` |
| `BFC_NODE_EXTERNAL_FLOW` | (process node × external entity × direction × data entity, nullable) — "Customer → order data → Receive order" |
| `BUSINESS_REQUIREMENT` | **one process node** — 1:1 (D-2, D-23). Its BR number is how imports identify the step (R2-D1) |
| `DATA_ENTITY` | logical data entity within one project |
| `DATA_FIELD` | logical field within one data entity. A partial list (keys and key attributes) is normal; type optional (D-26). FK fields are grouped into relationships by `fk_group_no` |
| `BR_DATA_ENTITY` | (BR × data entity × CRUD) — *what is done* to that data. Direction is generated from CRUD, and the row must be licensed by a matching step I/O row on the BR's node (D-24) |
| `BR_ORG_ROLE` | (BR × org role × RACI code) — who is accountable for a requirement; behaviour copied as on `BFC_NODE_ORG_ROLE` |
| `SOLUTION` | transformation answer within one project, in one of five categories |
| `BR_SOLUTION` | (BR × solution) pairing — which answers address which requirement |
| `FUNCTION_REQUIREMENT` | system function to be built within one project, of one FR type, belonging to **zero or one** Solution (D-27, D-28); an unlinked FR may carry a **suggested** BR (D-34) |
| `FR_BFC_NODE` | (FR × BFC node) pairing — coverage *not* expressed through a BR |
| `FR_INTERFACE` | interface-type FR (behaviour INTERFACE) — its source and target application, pattern, method, frequency. 1:0..1 with the FR; identity is the FR number |
| `FR_INTERFACE_DATA_ENTITY` | (interface FR × data entity) — what one interface carries |
| `APPLICATION` | application or technology in one project's landscape (as-is / to-be / both) |
| `APPLICATION_SOLUTION` | (application × solution) — what delivers this answer (to-be) |
| `APPLICATION_BFC_NODE` | (application × process node) — what supports this step today (as-is) |
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
| `WBS_ITEM` | one imported MS Project task line in one project, keyed by its MS Project Unique ID (D-33, Q13). Schedule fields are owned by MS Project; only the Phase / Solution links are edited in VB. **Not baselined** |
| `CONTROL_RULE` | (project × analysis) → threshold, owning role, escalation path |
| `BASELINE` | frozen version of one project's scope at one point in time |
| `DIAGRAM_LAYOUT` | (project × diagram type × scope × diagram object) → saved position and size. Presentation, **not scope — not baselined** |
| `baseline_*` | one live row as it stood at one baseline freeze |
| `BASELINE_EFFORT_RATE` | one rate-card cell (FR type × complexity → days) as it stood at one freeze — the rate card a baseline was priced on (R2-D7). Named here because it is the one shadow table added in round 2 |
| `APP_USER` | person who can log into Value Bridge |
| `IMPORT_BATCH` | one uploaded file — an `.xlsx` sheet (incl. an MS Project WBS export) or a `vb-process-flow/1.0` JSON — awaiting validation, review and commit |
| `IMPORT_ROW` | one staged sheet row or one staged JSON object (step, edge, I/O, lane, external party, WBS line …), with its verdict, errors and warnings. Purged 90 days after upload (Q14) |
| `STAKEHOLDER` → see above | *(the `APP_ROLE` table is deleted — D-9)* |
| `USER_ACCESS_GRANT` | one grant of one project role to one user over **one scope — a project or a program** (D-32). At most one active per user; platform admins need none |
| `PROJECT_SEQUENCE` | (project × number series) counter — DE, BR, FR, ISSUE, SOL, BEN, RSK, CR, DEC, EXT. **All ten seeded at project creation** (R2-D14) |
| `CODE_MASTER` | one configurable lookup value, in one category, in one scope |
| `AUDIT_EVENT` | one recorded security-relevant action (login, grant, freeze) |

---

## 4. Business Requirement — the grid

The entity × function × logic grid. `Use` is C / R / U / D. Manual steps are marked
`(manual)` — they are part of the blueprint even though no code runs.

### 4.1 Business Function Chart (scope area 1)

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `create_bfc_node` | `BFC_NODE` | C | Reject if parent is L5 (max depth), if level ≠ parent.level + 1, or **if the parent is a process** (D-23 — a process has no children). Derive `level`, next `seq_no` within parent. `is_process` defaults to TRUE at L5 and may be set at L3–L4 → one BFC node row |
| `create_bfc_node` | `BFC_NODE` | R | Read parent + siblings to compute `seq_no` and the hierarchical code |
| `generate_bfc_code` | `BFC_NODE` | R | Walk ancestors, zero-pad each `seq_no` to 2 → dotted code `01.02.03.04.05`. **Computed at save, stored** (§9.8) |
| `reorder_bfc_node` | `BFC_NODE` | U | Re-sequence siblings, then recompute code for the node **and every descendant** in one transaction |
| `mark_process` | `BFC_NODE`, `BUSINESS_REQUIREMENT` | U/C | **D-23.** Promote a childless L3–L5 node to a process (its BR is created in the same transaction), or demote one. **Demotion is refused with 409 naming every blocker** — an active BR, step I/O, roles, flow edges, external flows, as-is application links, or a process description. **VB never retires them itself** (R2-P5, Q4); the consultant retires each, then demotes. Every step-level fact is also guarded in the DB (§5.4.7) |
| `describe_process` | `BFC_NODE` | U | Process nodes only. Store the data-processing description, written system-agnostic. Reject on a non-process node |
| `link_bfc_data_entity` | `BFC_NODE_DATA_ENTITY` | C/D | Process nodes only. Attach 0..N input and 0..N output data entities — the node states *that* data flows; the BR states *what is done to it* (§5.4.2). **The one record of a step's I/O** — the process flow editor, the DFD and the BR all read it (D-24). Written only through `bfc.ensure_step_io`. **Delete refused (409) while a BR CRUD or an external flow depends on the row, naming each** (R2-D13) |
| `link_bfc_external_flow` | `BFC_NODE_EXTERNAL_FLOW` | C/D | **D-24a.** A process step exchanges data with an external party: (step × external entity × direction × data entity, optional). **When a data entity is named, the matching step I/O is ensured in the same transaction through the same `ensure_step_io` helper as BR CRUD** (R2-D13) — an inbound flow needs a step input, an outbound one a step output |
| `create_external_entity` | `EXTERNAL_ENTITY` | C/U/D | Next per-project sequence → `EXT-0001`. Name, kind (CUSTOMER / SUPPLIER / BANK / REGULATOR / PARTNER / OTHER), description |
| `link_bfc_role` | `BFC_NODE_ORG_ROLE` | C/D | Attach performing client roles to a process node with a RACI participation type. **Rules key on the type's behaviour, not its letter** (R2-D9, Q7): at most one ACCOUNTABLE, and at most one RESPONSIBLE, which is the step's lane. A RASCI or RAPID project renames or adds codes and keeps both rules |
| `link_bfc_application` | `APPLICATION_BFC_NODE` | C/D | **As-is landscape** — which application supports this step today (D-8) |
| `create_bfc_node` | `BUSINESS_REQUIREMENT` | C | **When the new node is a process:** auto-create its single BR in the same transaction (D-2, D-23) |
| `(manual)` workshop capture | — | — | Consultant elicits the L1–L5 chart with the client in workshop; VB is the system of record afterwards, not during |

### 4.1a Business process flow and DFD (D-20…D-22, D-25, D-31)

Generated from the BFC, the data entity list and the business requirements — plus one new
thing, the flow edge.

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `link_process_flow` | `BFC_NODE_FLOW` | C/U/D | An edge between two **process** nodes (D-23). `flow_type` ∈ SEQUENCE / CONDITIONAL / PARALLEL / HANDOFF, with `condition_label` on a conditional ("与信NG" / "credit check failed"). A null from-node is a start event, a null to-node an end event. **A second active edge between the same two steps is legal only with a different condition (Q2); the same condition → 409** |
| `generate_process_flow` | `BFC_NODE`, `BFC_NODE_FLOW`, `BFC_NODE_DATA_ENTITY`, `DATA_ENTITY`, `BFC_NODE_ORG_ROLE`, `ORG_UNIT`, `BUSINESS_REQUIREMENT`, `APPLICATION` | R | Given any non-process node, return the **graph**: its process descendants as process boxes, the flow edges between them, swimlanes from the role whose RACI **behaviour is RESPONSIBLE** (R2-D9), data stores from the input/output entities, and the system on each step. `variant` ∈ AS_IS / TO_BE (D-22) |
| `export_process_flow` | — | R | The same graph as Mermaid text, for pasting into a deck or a report. **Every label goes through `escape_mermaid()`** (R2-S7, §7.12b) |
| `flow_completeness_report` | `BFC_NODE`, `BFC_NODE_FLOW`, `BFC_NODE_DATA_ENTITY` | R | Process nodes with no inbound and no outbound edge (orphaned steps), flows with no start or no end event, conditional edges with no `condition_label`, **steps with no output data entity**, and **BR CRUD with no matching step I/O** (should be impossible after D-24; the check proves it) → the gaps that make a flow unreadable |
| `generate_dfd` | `BFC_NODE`, `BFC_NODE_DATA_ENTITY`, `BFC_NODE_EXTERNAL_FLOW`, `DATA_ENTITY`, `EXTERNAL_ENTITY` | R | **D-31.** Same scope as a process flow, **no sequence**: processes, data stores, external entities, and one flow per (step × entity × direction), labelled with the data entity. A store read in one L1 area and written in another is marked as a cross-area flow |
| `export_dfd` | — | R | The DFD graph as Mermaid text, every label through `escape_mermaid()` (R2-S7) |
| `download_flow_schema` | — | R | **D-25.** The JSON Schema for `vb-process-flow/1.0`, a worked example, and the **AI conversion prompt pack**: instructions an AI follows to turn a PowerPoint, BPMN or Visio flow into a valid file. **The pack names the approved services — Claude or Microsoft Copilot, under FTC's own accounts only — and opens with the personal-data removal step** (D-36) |
| `export_process_flow_json` | `BFC_NODE`, `BUSINESS_REQUIREMENT`, `BFC_NODE_FLOW`, `BFC_NODE_DATA_ENTITY`, `BFC_NODE_EXTERNAL_FLOW`, `BFC_NODE_ORG_ROLE` | R | The flow for one parent node as `vb-process-flow/1.0`. **Every existing step carries its `br_number` (its identity, R2-D1), its current `hier_code` (a cross-check) and its `row_version` (R2-D5)**, so an edited file re-imports as an update and a stale one is caught per step |
| `validate_process_flow_json` | `IMPORT_BATCH`, `IMPORT_ROW` | C | **The anchor node and the mode come from the route, chosen in the UI** (R2-P3). A file whose `parent` or `mode` disagrees is rejected. Parse under the JSON caps (§7.12a) and check the schema version. **Resolve each step by `br_number`** (UPDATE), cross-checking `hier_code` ("moved since export" on mismatch, R2-D1) and `row_version` (stale → per-row error, R2-D5). A step with neither is **matched by normalised name to an active process child of the anchor** (UPDATE with a warning, R2-P1, Q1); otherwise it is an INSERT. Resolve data entities by `DE-` number or exact name, lanes to org roles, external parties to `EXT-` rows. In replace mode, stage a **RETIRE** row per omitted edge and per omitted, unguarded step I/O, and a **KEPT** row with a warning for I/O a BR CRUD or external flow depends on (R2-P4) → staged rows with **errors** (block) and **warnings** (inform). **Nothing written to a business table** |
| `commit_process_flow_json` | `BFC_NODE`, `BUSINESS_REQUIREMENT`, `BFC_NODE_FLOW`, `BFC_NODE_DATA_ENTITY`, `BFC_NODE_EXTERNAL_FLOW`, `BFC_NODE_ORG_ROLE`, `DATA_ENTITY`, `EXTERNAL_ENTITY` | C/U | One transaction, all-or-nothing, the same six properties as §7.11. **Refused unless `acknowledged_inserts` equals the insert count whenever there are inserts, and `acknowledged_retires` equals the retire count whenever there are retirements** (R2-P1, R2-P2). New steps are process nodes and get their BR (D-2). The file's lane **replaces** the step's one RESPONSIBLE role and touches no other role. `merge` never retires. **`replace` retires only flow edges and step I/O (Q5)** — never steps, BRs, other roles, external flows, or I/O a BR CRUD or external flow depends on |
| `(manual)` AI conversion | — | — | The consultant removes personal data from the source slide or BPMN export, then gives it and the prompt pack to **Claude or Microsoft Copilot under FTC's own account — no other service, no personal account** (D-36, R2-S6), and uploads the JSON it returns. **VB itself never sends client content to an AI service** (A-51) |

**Why the edge table earns its place rather than deriving sequence from `seq_no`:** sibling
order is *display* order. Deriving flow from it silently asserts a straight line through
every process — no branches, no loops, no hand-offs between business areas — and produces a
diagram that looks authoritative and is wrong. The edge is also where the consultant records
what the workshop actually established.

### 4.2 Data Entity management (scope area 3)

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `create_data_entity` | `DATA_ENTITY` | C | Take next per-project DE sequence at commit → `DE-0001`. Unique within project |
| `create_data_entity` | `PROJECT_SEQUENCE` | U | Atomic increment of (project, `DATA_ENTITY`) counter. Row-locked; gap-tolerant |
| `manage_data_fields` | `DATA_FIELD` | C/U/D | Field name unique within DE. `is_primary_key` requires `pk_ordinal`; composite PKs allowed. **Logical, and partial is normal (D-26):** data type is optional, and a DE may list only its keys and key attributes. `is_mandatory` (yes / no / unknown) feeds ERD cardinality |
| `manage_data_fields` | `DATA_FIELD` | U | If `is_foreign_key`, `fk_target_entity_id` is mandatory and must be a DE in the **same project** — cross-project FK is rejected |
| `validate_entity_model` | `DATA_ENTITY`, `DATA_FIELD` | R | Report DEs with no PK field, FK fields pointing at a DE with no PK, and **DEs with no fields at all** → validation warning list. Warnings, never blocks — a partial logical model is the expected state during an assessment |
| `generate_erd` | `DATA_ENTITY`, `DATA_FIELD`, `DIAGRAM_LAYOUT` | R | **D-29.** Entities as boxes (PK, FK and attribute rows), one relationship per FK field → parent entity. Cardinality: parent side `1` if the FK is mandatory, `0..1` if optional or unknown; child side `many`, or `1` only when the FK field set equals the child's PK field set (`DATA_FIELD` models no alternate keys). Saved positions from `DIAGRAM_LAYOUT`. Filter by **subject area** = the entities a BFC L1/L2 branch reads or writes |
| `export_erd` | — | R | The ERD as Mermaid `erDiagram` text, and as PNG/SVG from the canvas |
| `save_diagram_layout` | `DIAGRAM_LAYOUT` | C/U | **D-30.** Upsert (diagram × scope × object) → x, y. Last write wins, per object — two consultants dragging different entities never conflict, and a lost position is not a data-integrity event |

### 4.3 Business Requirement (scope area 2)

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `create_br` | `BUSINESS_REQUIREMENT` | C | Called only by `bfc.create_node` / `bfc.mark_process` for a process node. `UNIQUE (bfc_node_id)` makes a second BR on one node impossible (D-2). Take next per-project BR sequence at commit → `BR-0001` |
| `create_br` | `BFC_NODE` | R | Validate the node `is_process` (also DB-enforced) |
| `update_br` | `BUSINESS_REQUIREMENT` | U | The consultant edits the BR that appeared with the step. `WHERE row_version = :v`; mismatch → 409 (D-6) |
| `link_br_data_entity` | `BR_DATA_ENTITY` | C/U/D | One row per (BR × DE × **CRUD**). `crud_code` is in the key — one BR legitimately reads *and* updates the same entity. `direction` is a **generated column** (`R` → INPUT, else OUTPUT), so `(R, OUTPUT)` cannot be stored (§5.4.2). **D-24:** the matching step I/O row on the BR's process node is created in the same transaction if absent, so the BR and the flow can never disagree |
| `link_br_role` | `BR_ORG_ROLE` | C/D | Attach client role(s) with a RACI participation type. **At most one role whose RACI behaviour is ACCOUNTABLE per BR** — keyed on behaviour, not on the letter `A` (R2-D9, Q7) |
| `link_br_solution` | `BR_SOLUTION` | C/D | Many-to-many, with a `coverage_note` per pairing (D-7). **D-34:** creating the pair clears `suggested_br_id` on every FR of that solution whose suggestion is this BR, in the same transaction |
| `br_coverage_report` | `BUSINESS_REQUIREMENT`, `BR_DATA_ENTITY`, `BR_SOLUTION`, `FUNCTION_REQUIREMENT` | R | BRs with no output DE, BRs with no solution, BRs with no FR (information — legal), **FRs with no Solution and so no BR (warning, D-28)**, DEs referenced by no BR → the scope-gap list |

### 4.4 Solution, Function Requirement and Applications (scope area 4, D-7/D-8)

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `create_solution` | `SOLUTION` | C | Next per-project sequence → `SOL-0001`. `category_code` from `code_master` category `SOLUTION_CATEGORY`: **ORG_AND_RULES / PEOPLE / PROCESS / DATA / TECHNOLOGY** |
| `create_function_requirement` | `FUNCTION_REQUIREMENT` | C | Next per-project sequence → `FR-0001`. `fr_type_code` from **`FR_TYPE`** (FORM / INTERFACE / REPORT / BATCH seeded; the project may rename, add or retire types — D-27). **Solution is optional (D-28)**: an FR saved without one returns a warning, not a 422. **D-34:** an FR that names a BR it is not traced to stores the BR as `suggested_br_id` — never a placeholder solution |
| `link_fr_solution` | `FUNCTION_REQUIREMENT` | U | Attach or move an FR to a Solution later — the normal path for FRs that arrived by import before the solution design. **D-34:** the suggestion clears **only** if a `BR_SOLUTION` path from `suggested_br_id` to the new solution exists. Otherwise it stays and the response carries a prompt to add that `BR_SOLUTION` (R2-D16) |
| `maintain_fr_types` | `CODE_MASTER` (`FR_TYPE`) | C/U | Per-project types. Each carries a **behaviour** ∈ FORM / INTERFACE / REPORT / BATCH / OTHER, which decides which detail panel the FR form shows and whether the FR appears on the interface list. A new type needs rate-card rows before its FRs can be priced (D-13). **When a project overrides a global type, the project's `EFFORT_RATE` rows and FRs are re-pointed to the override code in the same transaction**, so the rate-card lookup never silently misses (A-16). **A global type's behaviour is immutable once any FR or rate row references it → 409** (R2-D8, Q6): add a new type instead |
| `describe_interface` | `FR_INTERFACE`, `FR_INTERFACE_DATA_ENTITY` | C/U/D | FRs whose type behaviour is INTERFACE only. Source application, target application (different, same project), pattern (PUSH / PULL / BIDIRECTIONAL), method (API / FILE / DB / MESSAGE / MANUAL), frequency, volume note, and the data entities carried |
| `interface_list` | `v_interface_list` | R | **D-27. Generated, never typed:** one row per interface FR — FR number, name, source → target, pattern, method, frequency, data entities, solution, BR(s), status, effort. Filterable by application pair; exportable to `.xlsx`. Interface FRs with no source/target are listed as incomplete, not hidden |
| `link_fr_to_bfc_node` | `FR_BFC_NODE` | C/D | For coverage no BR expresses — an FR on a non-process node, or a process node whose Solution is not written yet. **Rejected if the node is already reachable through `BR_SOLUTION`** (§5.4.3 override) |
| `create_application` | `APPLICATION` | C | The project's application/technology catalogue. `lifecycle_code` ∈ AS_IS / TO_BE / BOTH |
| `link_application_solution` | `APPLICATION_SOLUTION` | C/D | **To-be allocation** — what delivers this solution. Rejected if the application's lifecycle is `AS_IS` |
| `solution_matrix` | `SOLUTION`, `BR_SOLUTION`, `BUSINESS_REQUIREMENT` | R | Solutions by category × BFC L1 area → *is this transformation actually balanced, or is it five technology answers and no org change?* |
| `application_gap_report` | `APPLICATION_BFC_NODE`, `APPLICATION_SOLUTION`, `BFC_NODE` | R | Process steps with an as-is application but no to-be allocation → the migration backlog. **The reason both links exist** |
| `fr_traceability_matrix` | `BFC_NODE`, `BUSINESS_REQUIREMENT`, `SOLUTION`, `FUNCTION_REQUIREMENT`, `APPLICATION` | R | Process step → BR → Solution → FR → Application, grouped by FR type → the vendor-facing scope list. Unlinked FRs listed in their own group at the end |

### 4.5 Issue Management (scope area 5)

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `create_stakeholder` | `STAKEHOLDER` | C/U/D | Named client-side person: name, title, org unit, `is_bpo`. They have no login (D-4) |
| `raise_issue` | `ISSUE` | C | Next per-project sequence → `ISS-0001`. `severity_code`, `issue_type_code`, `status_code` from `code_master`. **`raised_by_stakeholder_id`** is the business user or BPO who raised it; **`recorded_by_user_id`** is the consultant, from the JWT (§9.2). The two are never the same person and are never conflated |
| `link_issue_br` | `ISSUE_BR` | C/D | Many-to-many — one issue may span several BRs |
| `resolve_issue` | `ISSUE` | U | Status → RESOLVED requires a non-empty `resolution`. Store `resolved_at`, `resolved_by` |
| `issue_dashboard` | `ISSUE`, `ISSUE_BR`, `STAKEHOLDER` | R | Open issues by severity × type, per BFC L1 area via the BR→BFC path, and per raising stakeholder |

### 4.5a Bulk upload / download (D-5)

Business users and BPO staff work in spreadsheets. Covers **Issues, Data Entities, Data
Fields, Business Requirements, Function Requirements** (BR and FR added by D-28) and **WBS
lines** (D-33), plus the **process-flow JSON** of §4.1a (D-25), which shares the same
pipeline. Six `.xlsx` column maps, one staging model, one commit.

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `download_template` | — | R | Emit an `.xlsx` template per entity, with `code_master` values as dropdown validation so the returning file is already half-clean |
| `export_entity` | `ISSUE`, `DATA_ENTITY`, `DATA_FIELD`, `BUSINESS_REQUIREMENT`, `FUNCTION_REQUIREMENT`, `WBS_ITEM` | R | Current rows in template shape, including the business key (`ISS-0001`, `DE-0001`, `BR-0001`, MS Project Unique ID) so a round-trip can update rather than duplicate. FR exports carry `effort_days` as a **read-only** column (R2-D6). Every cell through `escape_cell()` |
| `validate_import` | `IMPORT_BATCH`, `IMPORT_ROW` | C | Parse → validate every row → stage. **Nothing is written to a business table at this step.** Row-level **errors** (block the batch) and **warnings** (shown, do not block), with the sheet row number. **BR rows are identified by BR number** — every BR already exists with its step (D-2), so a blank BR number is an error. `hier_code` is a cross-check only: a mismatch is "moved since export — re-export" (R2-D1). FR rows may name a `SOL-` number (blank → warning, D-28) and a `BR-` number (kept as a suggestion, D-34). `effort_days` is ignored on the way in. Type and complexity changes are checked exactly as the rating services would check them: a missing rate, or live interface detail on a move away from INTERFACE, is a row error (R2-D6). WBS rows per §4.15 |
| `commit_import` | `ISSUE` / `DATA_ENTITY` / `DATA_FIELD` / `BUSINESS_REQUIREMENT` / `FUNCTION_REQUIREMENT` / `WBS_ITEM` | C/U | One transaction. Blank business key → insert (number minted at commit, §9.8); populated key → update. FR type and complexity go through `change_fr_type` / `rate_function_requirement`, never a direct column write (R2-D6). **All-or-nothing: one invalid row rejects the batch. Any insert requires the acknowledged insert count, and any retirement the acknowledged retire count — on every batch, not only mixed ones** (R2-P2) |
| `(manual)` consultant review | `IMPORT_BATCH` | R | The consultant reviews the staged preview and approves before commit. **An upload never writes unattended** |
| `purge_import_rows` | `IMPORT_ROW`, `IMPORT_BATCH` | D/U | **Q14 — daily.** Staged rows (raw client content, incl. people's names) are deleted **90 days** after their batch was uploaded (`uploaded_at`), and `rows_purged_at` is set. The batch header — who, when, entity, counts, outcome — is kept. An uncommitted batch past 90 days becomes REJECTED. Audited. Closes A-32 |

### 4.6 Version control / baselines (scope area 6)

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `freeze_baseline` | `BASELINE` | C | One transaction, **opened at REPEATABLE READ from its first statement, with `consistency_check` inside it** (R2-P6), so the check and the snapshot see the same data. Version label auto-increments (v1.0 → v1.1). `frozen_by` from JWT. Status → FROZEN |
| `freeze_baseline` | `BFC_NODE`, `BUSINESS_REQUIREMENT`, `ISSUE` + links | R | Read the whole live set for the project, `is_active = TRUE` only |
| `freeze_baseline` | `baseline_*` | C | Copy each live row into its snapshot table, retaining `source_id` → the immutable baseline |
| `diff_baseline` | `baseline_*` | R | Full outer join baseline A to B on `source_id` → ADDED / CHANGED / REMOVED per entity, with the changed field list |
| `(manual)` client sign-off | `BASELINE` | U | Consultant records the client's approval against a frozen baseline. VB records the decision; it does not route it |
| `reopen_baseline` | `BASELINE` | — | **Not offered.** A frozen baseline is immutable; scope moves forward by freezing v1.1 |

### 4.7 Auth, users, projects and visibility (scope area 7 + Ben's addendum)

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `login` | `APP_USER` | R | Verify password hash, check `is_active` → JWT. Update `last_login_at` |
| `login` | `AUDIT_EVENT` | C | Log success/failure with timestamp and outcome |
| `create_user` | `APP_USER` | C | Admin only. Store hash in `password_hash`; the plaintext is never persisted or logged |
| `create_project` | `PROJECT` | C | **Platform admin only.** Under a client, optionally in a program of the same client. **No auto-grant**: the creator is a platform admin and needs none (D-32). Seeds **all ten number series** (DE, BR, FR, ISSUE, SOL, BEN, RSK, CR, DEC, EXT — R2-D14), the rate card and the control rules |
| `grant_access` | `USER_ACCESS_GRANT` | C/U | **One active grant per user, naming one project or one program** (D-32). A project grant needs project OWNER — **including a program OWNER, for a project inside their program (Ben, Q16)** — or platform admin; a **program grant needs a platform admin** (Q10). Granting to someone who holds an active grant on the **same** scope changes their role. **Granting to someone who holds a grant on a different scope → 409 naming it** (R2-S4). Granting to a platform admin → 422 (they need none). Audited |
| `reassign_access` | `USER_ACCESS_GRANT` | U/C | **Platform admin only.** Revoke the user's one grant and issue the new one in one transaction, with a rationale. One audit row names both scopes |
| `list_visible_projects` | `PROJECT`, `USER_ACCESS_GRANT` | R | **`visible_project_ids(user)`: the granted project, or every active project of the granted program**, or all for a platform admin. A project the user cannot see does not appear and returns 404, not 403 — non-existence, not refusal. `program_id` is read per request, so moving a project changes visibility on the next request |
| `enforce_project_scope` | `USER_ACCESS_GRANT`, `PROJECT` | R | The single service-layer guard every list and detail query passes through. **One function, one file** (§9.10). Every route reaches it through exactly one declared guard (R2-S1, §9) |
| `list_effective_access` | `USER_ACCESS_GRANT`, `PROJECT`, `APP_USER` | R | **D-32.** Everyone who can open the project, and why: a project grant, the program grant it inherits (named), or platform admin. OWNER or platform admin |
| `revoke_access` | `USER_ACCESS_GRANT` | U | Soft-revoke. **Audited** — the first draft logged grants and not revokes (S9). A program grant is revoked only by a platform admin. **A revoked grant is never restored**; access returns only through `grant_access` (R2-S5) |
| `deactivate_user` | `APP_USER` | U | Takes effect on the target's next request, because the JWT carries no role or status claim (S4) |
| `soft_delete_record` | any soft-deletable business entity | U | **R2-D2, Q4.** Refused with **409 naming the active dependents** (business keys, counted). Nothing cascades. Audited |
| `restore_record` | the business entities on the restore allow-list | U | Un-delete (P5). **Only entities on the allow-list** (§7.12). Grants, control rules, users and `code_master` rows are excluded (R2-S5). **Refused while any parent is inactive** (R2-D2) — restore the parent first |
| `consistency_check` | `BFC_NODE`, `BUSINESS_REQUIREMENT`, `DATA_FIELD`, `BR_DATA_ENTITY`, `FR_INTERFACE`, every frozen table | R | `hier_code`/`level_no` drift, process nodes without a BR, process nodes with children, BR CRUD with no matching step I/O, `FR_INTERFACE` rows under a non-interface type, and **an active row under an inactive parent, in any of the frozen tables** (R2-D2). **Precondition of freeze, run inside the freeze transaction** (D11, R2-P6) |
| `(manual)` access review | `USER_ACCESS_GRANT` | R | Ben reviews **effective** access per project — including program-derived and platform-admin access — at each baseline freeze |

### 4.8 Size and effort (D-13)

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `maintain_rate_card` | `EFFORT_RATE`, `AUDIT_EVENT` | C/U | (FR type × complexity) → standard man-days, per project. Seeded from an FTC default at `create_project`, then negotiated with the client. **OWNER; every change needs a rationale and writes an audit row with the old and new values** (R2-D7). **The rate card is frozen with each baseline** (`baseline_effort_rate`, §6.1), so a priced diff can name the card that priced it |
| `rate_function_requirement` | `FUNCTION_REQUIREMENT` | U | `complexity_code` ∈ SIMPLE / MEDIUM / COMPLEX / VERY_COMPLEX. `effort_days` is **derived** at save from the rate card, and **stored**, so a later rate change cannot silently reprice agreed scope |
| `effort_summary` | `FUNCTION_REQUIREMENT`, `SOLUTION`, `PHASE` | R | Man-days by FR type, by solution, by phase, by L1 area → the resource plan and the vendor sizing. Unlinked FRs (D-28) sum into an **Unassigned** bucket, never dropped |
| `priced_diff` | `BASELINE_FUNCTION_REQUIREMENT`, `BASELINE_BR_SOLUTION`, `BASELINE_BUSINESS_REQUIREMENT` | R | **Q3, R2-D3.** Per `source_fr_id`, **`effort_b − effort_a`, counted exactly once**: ADDED = +effort, REMOVED = −effort, CHANGED = the delta → **"v1.1: +340 man-days added, −60 removed, +12 re-rated, net +292"**. **Unlinked FR effort (D-28) is its own line.** A separate, informational **"effort exposed"** line is the effort of FRs reachable from changed BRs. It is never added to the net |

### 4.9 Benefit (D-14)

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `create_benefit` | `BENEFIT` | C | Next per-project sequence → `BEN-0001`. Measure, unit, baseline value, target value, realisation date, accountable `org_role_id` |
| `link_benefit_solution` | `BENEFIT_SOLUTION` | C/D | Many-to-many. A benefit usually needs several solutions; a solution may serve several benefits |
| `value_ranking` | `BENEFIT`, `BENEFIT_SOLUTION`, `FUNCTION_REQUIREMENT` | R | Per solution, **value = Σ (target − baseline) × contribution_pct**, ÷ effort days. **Ranked only within one `measure_unit`** (R2-D12, Q9) — hours saved and baht saved are never on one list. **This is what makes "trade, don't add" executable** — it names each unit's bottom quartile to displace |
| `benefit_gap_report` | `SOLUTION`, `BENEFIT_SOLUTION` | R | Solutions carrying effort and no quantified benefit → challenge at the next gate. Benefits whose solutions are all TECHNOLOGY → fragile benefit case (§4.13) |

### 4.10 Risk (D-15)

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `raise_risk` | `RISK` | C | Next per-project sequence → `RSK-0001`. `probability_code` × `impact_code`, mitigation, owning `org_role_id`, target date. May link to a BFC node, a Solution or a Phase |
| `score_risk` | `RISK` | U | `exposure_score` derived from probability × impact at save; `status_code` ∈ OPEN / MITIGATING / CLOSED / MATERIALISED |
| `promote_risk_to_issue` | `RISK`, `ISSUE` | U/C | A materialised risk creates the issue and links back. **The one path between the two entities — they are never merged** |
| `risk_register` | `RISK` | R | Exposure-ranked, ageing, by owner and by phase |

### 4.11 Change control and decisions (D-16, D-17)

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `raise_change_request` | `CHANGE_REQUEST` | C | Next per-project sequence → `CR-0001`. Raised against a baseline that is **FROZEN or APPROVED — never SUPERSEDED, never the working set** (Q8), with a stated rationale and origin |
| `analyse_cr_impact` | `CR_IMPACT` | C | Trace the proposed change through BR → Solution → FR → Application → Data Entity → Phase. **An FR is accepted as a seed** as well as a BR, because an unlinked FR (D-28) cannot be reached from any BR. Every touched object becomes a row. **The blast radius is computed, not typed** |
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
| `maintain_control_rule` | `CONTROL_RULE` | C/U | (project × `analysis_code`) → threshold value, comparison, owning `org_role_id`, escalation path. Agreed at mobilisation; the thresholds are **the client's, not hard-coded** |
| `control_panel` | `CONTROL_RULE` + every analysis | R | Runs every analysis, compares to its rule → **GREEN / FLAG / ESCALATE**, with the owning role and the prescribed action per row. The PMO's one screen |
| `requirement_volatility` | `BASELINE_BUSINESS_REQUIREMENT` | R | ADDED/CHANGED/REMOVED per L1 area across baseline generations. **The earliest warning the app produces** — an area churning across two consecutive baselines is not understood. *Action: pull it out of the current wave; do not let a vendor start there* |
| `process_change_intensity` | `BFC_NODE`, `BR_SOLUTION`, `SOLUTION` | R | Process steps carrying a solution, rolled up per L1 area, weighted by solution category. Where the transformation actually lands versus where it was said it would |
| `org_impact_heatmap` | `BFC_NODE_ORG_ROLE`, `BR_ORG_ROLE`, `BR_SOLUTION`, `ORG_UNIT` | R | Change absorbed per org unit. *Action: top decile gets a dedicated change agent and a capacity check — they are usually the SMEs too* |
| `stakeholder_engagement` | `STAKEHOLDER`, `ISSUE`, `ORG_UNIT` | R | Issues raised per stakeholder per org unit. **Silence is the signal**: high impact and no issues raised is adoption risk. *Action: interview before sign-off* |
| `interface_load` | `v_interface_list` | R | Interface FRs per source → target application pair (from `FR_INTERFACE`, D-27), and as a share of all FRs. *Action: over ~25–30%, stand up an integration workstream and book test environments early* |
| `data_migration_map` | `DATA_ENTITY`, `APPLICATION_BFC_NODE`, `APPLICATION_SOLUTION` | R | Source (as-is) → target (to-be) per data entity. Entities with no source, or with conflicting sources → data ownership decision before design freeze |
| `master_data_candidates` | `BR_DATA_ENTITY`, `BFC_NODE` | R | Entities referenced by BRs across many L1 areas. *Action: assign a single owner; it becomes a managed cross-workstream dependency* |
| `fr_unlinked` | `FUNCTION_REQUIREMENT` | R | **D-28.** FRs with no Solution, count and effort. *Action: link or retire before the next freeze; a vendor cannot be held to a function nobody traced to a requirement* |

### 4.14 Programs (D-32)

A program groups related projects for one client. **It shares no data**: every row below is
either a program header, an access fact, or a read that is assembled from per-project reports.

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `create_program` · `update_program` | `PROGRAM` | C/U | **Platform admin.** Code, name, client, description — no status, dates or manager (A-65). A program's projects must share its `client_id` |
| `move_project_program` | `PROJECT`, `AUDIT_EVENT` | U | **Platform admin only** (Q10). Two steps: a **preview** naming every user who **gains** access (holders of the target program's grant) and every user who **loses** it (holders of the current program's grant), then a commit that must quote the preview's hash — if the lists changed in between, 409. Audited with both lists (R2-S3) |
| `program_dashboard` | every per-project report | R | **Program grant or platform admin.** For each project in `visible_project_ids(user) ∩ program.projects`: BR / FR / issue counts, control-panel status, effort summary, and WBS plan-vs-actual where a WBS is imported. **Built by calling the per-project report once per project — never new cross-project SQL** (R2-S2) |
| `program_counts` · `program_interfaces` · `program_effort` · `program_control_status` | the same per-project reports | R | The same rule: a list of `{project, result}` pairs, one per visible project. Nothing is stored at program level |
| `(manual)` cross-project hand-off | `BFC_NODE_FLOW` | — | Drawn as a HANDOFF edge to an end event labelled with the other project — not a shared entity |

### 4.15 WBS import (D-33)

**Optional per project** (Q13). The schedule's system of record stays in MS Project; VB
imports it so the program dashboard can show plan-vs-actual, and so consultants can say which
phase and solution each line delivers.

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `download_template` (`wbs`) | — | R | The WBS column map: **MS Project Unique ID (required)**, WBS code, name, outline level, start, finish, actual start, actual finish, % complete. The instruction sheet carries the **date-format step** — set date columns to `yyyy-mm-dd` before saving, because MS Project exports dates in the Windows locale — and tells the consultant to add **Unique ID** to the MS Project export map (not exported by default) |
| `validate_import` (`wbs`) | `IMPORT_BATCH`, `IMPORT_ROW` | C | **Keyed by `ms_unique_id`** (R2-D15): a known ID updates, an unknown one inserts. WBS code, name and dates may all change on re-plan. Parent derived from outline level and row order. Duplicate Unique ID or WBS code in one file → error; non-ISO text date → error (A-33). `import_mode` ∈ merge / replace: **replace stages a RETIRE row for every active line the file omits** |
| `commit_import` (`wbs`) | `WBS_ITEM` | C/U | As §4.5a, with both acknowledgements. **Never touches the phase / solution links** — they survive every re-import |
| `link_wbs_item` | `WBS_ITEM` | U | **The only edit VB allows on a WBS line** (D-33): set or clear `phase_id` and `solution_id`, both in the same project. `row_version` checked. Any other field → 422 "Change it in MS Project and re-import" |
| `wbs_plan_vs_actual` | `WBS_ITEM`, `PHASE` | R | Per phase and per top-level WBS line: planned vs actual finish, slip in days, % complete. Lines with no phase link are listed, not dropped. Not baselined |

**Cross-check:** every entity named in this grid appears in §5/§6, and every function has
pseudocode in §7.

---

## 5. Logical design

Modelled by `apple` from the §4 grid and normalized 1NF → 2NF → 3NF. Reproduced here with
three changes made by me, each marked in place:

1. **`ENGAGEMENT` renamed to `PROJECT`** throughout, per Ben's scoping decision (A-2).
   `USER_ENGAGEMENT_ACCESS` → `USER_PROJECT_ACCESS`, `ENGAGEMENT_SEQUENCE` →
   `PROJECT_SEQUENCE`, `engagement_id` → `project_id`.
2. **`updated_at` maintained by the `fn_set_updated_at()` DB trigger**, not SQLAlchemy
   `onupdate=`. `apple` wrote the latter; playbook §13 forbids it.
3. Her open-questions list is folded into §11 rather than duplicated.

Where I disagree with her, I say so in §11 — I do not have a disagreement large enough to
override the model.

### 5.1 Conventions applied to every business table

Declared once here and **omitted from the diagram** so it stays readable. Every business table (everything except `CODE_MASTER` lookups themselves, which also carry them) has:

| Column | Type | Note |
|---|---|---|
| `created_at` | `timestamptz NOT NULL DEFAULT now()` | |
| `updated_at` | `timestamptz NOT NULL DEFAULT now()` | maintained by the `fn_set_updated_at()` **DB trigger**. Playbook §13 forbids `onupdate=` in SQLAlchemy — corrected from `apple`'s draft |
| `created_by` | `bigint NOT NULL FK → APP_USER` | set from the JWT, never the request body (§9.2) |
| `updated_by` | `bigint NULL FK → APP_USER` | **added on `apple`'s recommendation** — see A-25 |
| `is_active` | `boolean NOT NULL DEFAULT true` | soft-delete flag |
| `deleted_at` | `timestamptz NULL` | |
| `deleted_by` | `bigint NULL FK → APP_USER` | **added** — A-25 |
| `row_version` | `integer NOT NULL DEFAULT 1` | **added — D-6.** Optimistic concurrency. Every `UPDATE` carries `WHERE row_version = :v` and increments it; a mismatch is a 409 (§7). On the editable business tables only — not on `baseline_*`, which are never updated |

Two consequences worth stating up front:

1. This creates ~25 FKs into `APP_USER` that I deliberately do not draw. Implement as a SQLAlchemy `AuditMixin`.
2. **`updated_by` is missing from your list.** With soft delete and baselines you will want to know who last touched a live row before a freeze. I recommend adding it; flagged rather than silently added.

Soft delete interacts with uniqueness: number columns (`de_number`, `br_number`, …) keep full `UNIQUE` constraints including deleted rows, so numbers are never reused. Positional uniqueness (`seq_no` within a parent) uses a **partial unique index `WHERE is_active`**, so deleting a sibling frees its slot.

Surrogate PKs are `bigint` identity throughout. Business numbers (`DE-0001`, `BR-0042`) are **alternate keys, not PKs** — they are project-scoped and human-facing, and JWT-era APIs should not leak sequence semantics into path params any more than necessary.

---

### 5.2 Entity-relationship diagram

```mermaid
erDiagram
    %% ---------- tenancy ----------
    CLIENT ||--o{ PROJECT : "contracts"
    CLIENT ||--o{ PROGRAM : "groups projects under (D-32)"
    PROGRAM |o--o{ PROJECT : "groups (same client, composite FK)"
    PROGRAM |o--o{ USER_ACCESS_GRANT : "is opened to (program grant)"
    PROJECT ||--o{ BFC_NODE : "scopes"
    PROJECT ||--o{ ORG_UNIT : "scopes"
    PROJECT ||--o{ DATA_ENTITY : "scopes"
    PROJECT ||--o{ BUSINESS_REQUIREMENT : "scopes"
    PROJECT ||--o{ FUNCTION_REQUIREMENT : "scopes"
    PROJECT ||--o{ SOLUTION : "scopes"
    PROJECT ||--o{ APPLICATION : "scopes"
    PROJECT ||--o{ STAKEHOLDER : "scopes"
    PROJECT ||--o{ ISSUE : "scopes"
    PROJECT ||--o{ BASELINE : "freezes"
    PROJECT ||--|{ PROJECT_SEQUENCE : "numbers"

    %% ---------- client organisation ----------
    ORG_UNIT ||--o{ ORG_UNIT : "parent of"
    ORG_UNIT ||--o{ ORG_ROLE : "defines"

    %% ---------- business function chart ----------
    BFC_NODE ||--o{ BFC_NODE : "parent of (a process has no children — D-23)"
    BFC_NODE ||--o{ BFC_NODE_DATA_ENTITY : "consumes or produces"
    DATA_ENTITY ||--o{ BFC_NODE_DATA_ENTITY : "flows through"
    BFC_NODE ||--o{ BFC_NODE_FLOW : "flows to"
    BFC_NODE ||--o{ BFC_NODE_ORG_ROLE : "is performed via"
    ORG_ROLE ||--o{ BFC_NODE_ORG_ROLE : "performs"
    BFC_NODE ||--o| BUSINESS_REQUIREMENT : "is specified by (exactly one per process node — D-2/D-23)"

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
    BFC_NODE |o--o{ DIAGRAM_LAYOUT : "is placed as a step"
    DATA_ENTITY |o--o{ DIAGRAM_LAYOUT : "is placed as entity or store"
    EXTERNAL_ENTITY |o--o{ DIAGRAM_LAYOUT : "is placed as external party"
    BFC_NODE_FLOW |o--o{ DIAGRAM_LAYOUT : "start/end event is placed"

    %% ---------- business requirement ----------
    BUSINESS_REQUIREMENT ||--o{ BR_DATA_ENTITY : "uses"
    DATA_ENTITY ||--o{ BR_DATA_ENTITY : "is used by"
    BUSINESS_REQUIREMENT ||--|{ BR_ORG_ROLE : "is owned via"
    ORG_ROLE ||--o{ BR_ORG_ROLE : "is accountable in"

    %% ---------- solution (D-7) ----------
    BUSINESS_REQUIREMENT ||--o{ BR_SOLUTION : "is answered by"
    SOLUTION ||--o{ BR_SOLUTION : "answers"
    SOLUTION |o--o{ FUNCTION_REQUIREMENT : "is detailed by (optional — D-28)"
    BUSINESS_REQUIREMENT |o--o{ FUNCTION_REQUIREMENT : "is suggested for (D-34, cleared on link)"
    CODE_MASTER ||--o{ SOLUTION : "types category and status"

    %% ---------- application / technology (D-8) ----------
    APPLICATION ||--o{ APPLICATION_SOLUTION : "delivers"
    SOLUTION ||--o{ APPLICATION_SOLUTION : "is delivered by"
    APPLICATION ||--o{ APPLICATION_BFC_NODE : "supports today"
    BFC_NODE ||--o{ APPLICATION_BFC_NODE : "is supported today by"
    CODE_MASTER ||--o{ APPLICATION : "types lifecycle and kind"

    %% ---------- function requirement ----------
    FUNCTION_REQUIREMENT ||--o{ FR_BFC_NODE : "supports"
    BFC_NODE ||--o{ FR_BFC_NODE : "is supported by"

    %% ---------- stakeholders and issues ----------
    ORG_UNIT ||--o{ STAKEHOLDER : "employs"
    STAKEHOLDER ||--o{ ISSUE : "raises"
    APP_USER ||--o{ ISSUE : "records"
    ISSUE ||--o{ ISSUE_BR : "is raised against"
    BUSINESS_REQUIREMENT ||--o{ ISSUE_BR : "attracts"

    %% ---------- baselines ----------
    BASELINE ||--o{ BASELINE_BFC_NODE : "contains"
    BASELINE ||--o{ BASELINE_DATA_ENTITY : "contains"
    BASELINE ||--o{ BASELINE_BUSINESS_REQUIREMENT : "contains"
    BASELINE ||--o{ BASELINE_BR_DATA_ENTITY : "contains"
    BASELINE ||--o{ BASELINE_ISSUE : "contains"
    BASELINE ||--o{ BASELINE_DATA_FIELD : "contains (D-3)"
    BASELINE ||--o{ BASELINE_SOLUTION : "contains (D-3, D-7)"
    BASELINE ||--o{ BASELINE_FUNCTION_REQUIREMENT : "contains (D-3)"
    BASELINE ||--o{ BASELINE_ORG_UNIT : "contains (D-12)"
    BASELINE ||--o{ BASELINE_ORG_ROLE : "contains (D-12)"
    BASELINE ||--o{ BASELINE_BENEFIT : "contains (D-14)"
    BASELINE ||--o{ BASELINE_PHASE : "contains (D-18)"
    BASELINE ||--o{ BASELINE_BFC_NODE_FLOW : "contains (D-20)"
    BASELINE ||--o{ BASELINE_EXTERNAL_ENTITY : "contains (D-24a)"
    BASELINE ||--o{ BASELINE_BFC_NODE_EXTERNAL_FLOW : "contains (D-24a)"
    BASELINE ||--o{ BASELINE_FR_INTERFACE : "contains (D-27)"
    BASELINE ||--o{ BASELINE_FR_INTERFACE_DATA_ENTITY : "contains (D-27)"
    BFC_NODE ||--o{ BASELINE_BFC_NODE : "is snapshotted as"
    DATA_ENTITY ||--o{ BASELINE_DATA_ENTITY : "is snapshotted as"
    BUSINESS_REQUIREMENT ||--o{ BASELINE_BUSINESS_REQUIREMENT : "is snapshotted as"
    ISSUE ||--o{ BASELINE_ISSUE : "is snapshotted as"
    BASELINE ||--o{ BASELINE_EFFORT_RATE : "contains (R2-D7)"
    EFFORT_RATE ||--o{ BASELINE_EFFORT_RATE : "is snapshotted as"

    %% ---------- identity and access ----------
    APP_USER ||--o{ USER_ACCESS_GRANT : "holds (at most one active - D-32)"
    PROJECT |o--o{ USER_ACCESS_GRANT : "is opened to (project grant)"
    CODE_MASTER ||--o{ USER_ACCESS_GRANT : "types project role (D-9)"
    APP_USER ||--o{ BASELINE : "froze"
    APP_USER ||--o{ AUDIT_EVENT : "emits"
    PROJECT ||--o{ AUDIT_EVENT : "contextualises"

    %% ---------- size, benefit, risk, change, phasing, control (D-13…D-19) ----------
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
    APP_USER ||--o{ IMPORT_BATCH : "uploaded"
    IMPORT_BATCH ||--o{ IMPORT_ROW : "stages (purged after 90 days - Q14)"
    BFC_NODE |o--o{ IMPORT_BATCH : "anchors a process-flow import (D-25)"

    %% ---------- shared lookups ----------
    CODE_MASTER ||--o{ ORG_UNIT : "types level"
    CODE_MASTER ||--o{ DATA_FIELD : "types data type"
    CODE_MASTER ||--o{ BFC_NODE_ORG_ROLE : "types RACI (with behaviour - Q7)"
    CODE_MASTER ||--o{ BR_ORG_ROLE : "types RACI (with behaviour - Q7)"
    CODE_MASTER ||--o{ BUSINESS_REQUIREMENT : "types status"
    CODE_MASTER ||--o{ FUNCTION_REQUIREMENT : "types FR type (with behaviour, immutable once used) and status"
    CODE_MASTER ||--o{ ISSUE : "types severity, type, status"
    CODE_MASTER ||--o{ BASELINE : "types status"
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
    }
    CODE_MASTER {
        bigint code_id PK
        bigint project_id FK
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
        smallint level_no
        bool is_process "D-23"
        int seq_no
        varchar hier_code
        varchar node_name
        text purpose_desc
        text data_processing_desc "process only"
    }
    BFC_NODE_DATA_ENTITY {
        bigint bfc_node_id PK
        bigint data_entity_id PK
        char direction PK "I or O"
        bigint project_id FK
        bool node_is_process FK "generated guard"
        text note
    }
    BFC_NODE_FLOW {
        bigint bfc_node_flow_id PK
        bigint project_id FK
        bigint from_bfc_node_id FK
        bool from_is_process FK "generated guard"
        bigint to_bfc_node_id FK
        bool to_is_process FK "generated guard"
        bigint flow_type_code_id FK
        varchar condition_label
        int seq_no
        text note
    }
    BFC_NODE_ORG_ROLE {
        bigint bfc_node_id PK
        bigint org_role_id PK
        bigint raci_code_id PK
        bigint project_id FK
        bool node_is_process FK "generated guard"
        varchar raci_category FK "generated: RACI_TYPE"
        varchar raci_behaviour FK "copy, FK-verified - Q7"
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
        varchar br_number
        text br_statement
        text business_logic
        text output_expectation
        bigint status_code_id FK
    }
    BR_DATA_ENTITY {
        bigint br_id PK
        bigint data_entity_id PK
        char crud_code PK "C R U D"
        char direction "generated from crud_code"
        bigint project_id FK
        bigint bfc_node_id FK "copy of the BR's node - D-24"
        bool io_is_active FK "generated guard"
        text usage_note
    }
    BR_ORG_ROLE {
        bigint br_id PK
        bigint org_role_id PK
        bigint raci_code_id PK
        bigint project_id FK
        varchar raci_category FK "generated: RACI_TYPE"
        varchar raci_behaviour FK "copy, FK-verified - Q7"
    }
    FUNCTION_REQUIREMENT {
        bigint fr_id PK
        bigint project_id FK
        bigint solution_id FK "nullable - D-28"
        bigint suggested_br_id FK "nullable - D-34; cleared when a BR_SOLUTION path exists"
        varchar fr_number
        varchar fr_name
        text description
        bigint fr_type_code_id FK
        varchar fr_type_category FK "generated: FR_TYPE"
        varchar fr_type_behaviour FK "copy, FK-verified"
        bigint complexity_code_id FK
        numeric effort_days
        bigint fulfilment_status_code_id FK
        text acceptance_note
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
        bigint br_id PK
        bigint solution_id PK
        bigint project_id FK
        text coverage_note
    }
    APPLICATION {
        bigint application_id PK
        bigint project_id FK
        varchar application_code
        varchar application_name
        varchar vendor
        varchar version_label
        bigint app_kind_code_id FK
        bigint lifecycle_code_id FK
        text description
    }
    APPLICATION_SOLUTION {
        bigint application_id PK
        bigint solution_id PK
        bigint project_id FK
        text allocation_note
    }
    APPLICATION_BFC_NODE {
        bigint application_id PK
        bigint bfc_node_id PK
        bigint project_id FK
        bool node_is_process FK "generated guard (new pin)"
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
    FR_BFC_NODE {
        bigint fr_id PK
        bigint bfc_node_id PK
        bigint project_id FK
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
        bigint fr_id PK, FK
        bigint data_entity_id PK, FK
        bigint project_id FK
        bool interface_is_active FK "generated guard"
        text note
    }
    DIAGRAM_LAYOUT {
        bigint diagram_layout_id PK
        bigint project_id FK
        varchar diagram_type "ERD | PROCESS_FLOW | DFD"
        bigint scope_bfc_node_id FK "NULL = whole project (ERD only)"
        bigint bfc_node_id FK
        bigint data_entity_id FK
        bigint external_entity_id FK
        bigint bfc_node_flow_id FK
        numeric x
        numeric y
        numeric width
        numeric height
        bool is_collapsed
    }
    BASELINE_FR_INTERFACE {
        bigint baseline_fr_interface_id PK
        bigint baseline_id FK
        bigint source_fr_id FK
        bigint baseline_fr_id FK
        bigint baseline_source_application_id FK
        bigint baseline_target_application_id FK
        varchar pattern_code
        varchar pattern_label
        varchar method_code
        varchar method_label
        varchar frequency_code
        varchar frequency_label
        text volume_note
        char content_hash
    }
    BASELINE_BFC_NODE_EXTERNAL_FLOW {
        bigint baseline_bnef_id PK
        bigint baseline_id FK
        bigint source_bfc_node_external_flow_id FK
        bigint baseline_bfc_node_id FK
        bigint baseline_external_entity_id FK
        bigint baseline_data_entity_id FK
        char direction
        varchar flow_label
        char content_hash
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
        varchar version_label
        int hash_spec_version
        bigint status_code_id FK
        text note
        timestamptz frozen_at
        bigint frozen_by_user_id FK
        bigint prior_baseline_id FK
    }
    BASELINE_BFC_NODE {
        bigint baseline_bfc_node_id PK
        bigint baseline_id FK
        bigint source_bfc_node_id FK
        bigint baseline_parent_node_id FK
        smallint level_no
        bool is_process
        int seq_no
        varchar hier_code
        varchar node_name
        text data_processing_desc
        char content_hash
    }
    BASELINE_DATA_ENTITY {
        bigint baseline_data_entity_id PK
        bigint baseline_id FK
        bigint source_data_entity_id FK
        varchar de_number
        varchar de_name
        text description
        char content_hash
    }
    BASELINE_FUNCTION_REQUIREMENT {
        bigint baseline_fr_id PK
        bigint baseline_id FK
        bigint source_fr_id FK
        bigint baseline_solution_id FK "nullable - D-28"
        varchar fr_number
        varchar fr_name
        varchar fr_type_code
        varchar fr_type_label
        varchar fr_type_behaviour
        varchar complexity_code
        varchar complexity_label
        numeric effort_days
        char content_hash
    }
    BASELINE_BUSINESS_REQUIREMENT {
        bigint baseline_br_id PK
        bigint baseline_id FK
        bigint source_br_id FK
        bigint baseline_bfc_node_id FK
        varchar br_number
        text br_statement
        text business_logic
        varchar status_code
        varchar status_label
        char content_hash
    }
    BASELINE_BR_DATA_ENTITY {
        bigint baseline_br_de_id PK
        bigint baseline_id FK
        bigint baseline_br_id FK
        bigint baseline_data_entity_id FK
        char crud_code
        varchar crud_label
        char direction
    }
    BASELINE_ISSUE {
        bigint baseline_issue_id PK
        bigint baseline_id FK
        bigint source_issue_id FK
        varchar issue_number
        varchar title
        text description
        varchar severity_code
        varchar severity_label
        varchar issue_type_code
        varchar issue_type_label
        varchar status_code
        varchar status_label
        date target_date
        char content_hash
    }
    BASELINE_EFFORT_RATE {
        bigint baseline_effort_rate_id PK
        bigint baseline_id FK
        bigint source_effort_rate_id FK
        varchar fr_type_code
        varchar fr_type_label
        varchar fr_type_behaviour
        varchar complexity_code
        varchar complexity_label
        numeric standard_days
        text change_rationale
        char content_hash
    }
    APP_USER {
        bigint app_user_id PK
        varchar email
        varchar password_hash
        varchar display_name
        bool is_active
        bool is_platform_admin
        timestamptz last_login_at
    }
    EFFORT_RATE {
        bigint project_id PK
        bigint fr_type_code_id PK
        bigint complexity_code_id PK
        bigint effort_rate_id UK "stable source pointer for the baseline"
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
        varchar source_format "xlsx | vb-process-flow/1.0"
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
        timestamptz committed_at
        timestamptz rows_purged_at "Q14"
    }
    IMPORT_ROW {
        bigint import_row_id PK
        bigint import_batch_id FK
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
        bigint user_access_grant_id PK
        bigint app_user_id FK
        bigint project_id FK "XOR program_id"
        bigint program_id FK "XOR project_id"
        bigint project_role_code_id FK "one role over the whole scope - Q10"
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

Multi-column PK markers in junction tables denote the composite key; Mermaid has no composite notation, so each participating column is marked `PK`.

---

### 5.3 Entity notes — grain, keys, key attributes

#### Tenancy and shared services

**CLIENT** — one row per client organisation FTC contracts with. PK `client_id`. UK `client_code`. No FKs.

**PROGRAM** *(D-32)* — one row per program: a named group of related projects for one client
("2027 Core Systems Renewal"). PK `program_id`; FK `client_id NOT NULL`. UK `(client_id,
program_code)`; partial UK `(client_id, lower(program_name)) WHERE is_active`. Three composite-FK
targets: UK `(program_id, client_id)`, UK `(program_id, client_id, is_active)` and UK
`(program_id, is_active)`. All three are trivially unique supersets of the PK, and they exist
only so that PROJECT and USER_ACCESS_GRANT can prove "same client" and "live program". Columns:
`program_code varchar(30) NOT NULL`, `program_name varchar(200) NOT NULL`, `description text`,
plus §5.1 (soft delete, `row_version`).

**A program is a roll-up and access scope, never a data layer.** No business table other than
`PROJECT` and `USER_ACCESS_GRANT` carries `program_id`. There is no program-level BFC, DE, BR,
FR, issue or baseline, and no `PROJECT_SEQUENCE` series (the code is typed by a platform
admin). Every program view is a UNION over the program's projects, computed at read time
(D-32). Baselines stay per project, and there is no program freeze (D-32, confirmed). *Gap
(A-65):* D-32 describes no program status, dates or manager, so none is modelled.

**PROJECT** — one row per assessment project for one client, and **the data wall**. Each
project keeps its own BFC, DEs, BRs, FRs, issues and baselines, and nothing is shared across
projects, even inside one program (D-32). PK `project_id`; FK `client_id`, `status_code_id`,
**`program_id` (nullable, D-32)**. UK `(client_id, project_code)`; UK `(project_id, is_active)`
as the target for the grant guard (USER_ACCESS_GRANT, below).

- **Same client as its program, declaratively:** FK `(program_id, client_id) →
  PROGRAM(program_id, client_id)`. A project cannot join another client's program, and a
  project's `client_id` cannot change while it sits in a program. When `program_id` is NULL,
  MATCH SIMPLE skips the FK.
- **Live program only:** `program_is_active boolean GENERATED ALWAYS AS (CASE WHEN is_active
  THEN TRUE END) STORED` + FK `(program_id, client_id, program_is_active) → PROGRAM(program_id,
  client_id, is_active)` **ON UPDATE NO ACTION**. Retiring a program that still has active
  projects is refused. So is restoring a project into a retired program, or putting an active
  project into one (Q4, by construction).
- **Changing `program_id` changes who can see the project** (D-32). It is platform-admin only
  (Q10) and audited as `PROJECT_PROGRAM_CHANGED` with the users gaining and losing visibility
  (R2-S3, §7.10a `move_project_program`). The model needs no membership-history table: AUDIT_EVENT holds the history,
  and nothing reports or diffs from it.

**CODE_MASTER** — one row per configurable lookup value, in one category, for one scope. PK `code_id`; FK `project_id` (**nullable**: `NULL` = FTC-wide default library, non-null = project override). UK is a pair of partial indexes: `UNIQUE (category, code) WHERE project_id IS NULL` and `UNIQUE (project_id, category, code) WHERE project_id IS NOT NULL` (or a single index with `NULLS NOT DISTINCT` on PG 15+). `is_system` marks rows the UI must not let a consultant delete (e.g. the four CRUD letters).

Fields I put on `code_master` because the value set is genuinely client-configurable: **issue
severity, issue type, issue status, BR status, FR fulfilment status, project status, baseline
status, data field data type, org unit level label, RACI participation type, FR type (D-27),
interface pattern / method / frequency (D-27), external entity kind (D-24a)**. Fields I
deliberately did **not** route through it: `BFC_NODE.level_no` (a structural integer with a hard
`CHECK BETWEEN 1 AND 5`), `BFC_NODE.is_process` (a structural boolean, D-23),
`BR_DATA_ENTITY.direction` (derived, §5.4.2), `DIAGRAM_LAYOUT.diagram_type` and
`CODE_MASTER.behaviour_code` (closed vocabularies that code branches on, §8), and anything
boolean.

**Behaviour: what the application branches on (D-27, extended by Q7).** Two categories have
labels and codes a project may configure, and they still need a stable meaning the code can
branch on. **FR type** (`FR_TYPE`, seeded FORM / INTERFACE / REPORT / BATCH, editable per
project) and **RACI participation** (`RACI_TYPE`, seeded R / A / C / I, configurable because
clients use RASCI, RAPID or a house variant). The application never branches on `code`. It
branches on **`behaviour_code`**, one nullable column:

- `behaviour_code varchar(20) NULL`
- `CHECK ((category IN ('FR_TYPE','RACI_TYPE')) = (behaviour_code IS NOT NULL))`: every row in
  the two categories has a behaviour, and no other row has one.
- `CHECK (category <> 'FR_TYPE' OR behaviour_code IN ('FORM','INTERFACE','REPORT','BATCH','OTHER'))`
- `CHECK (category <> 'RACI_TYPE' OR behaviour_code IN ('RESPONSIBLE','ACCOUNTABLE','CONSULTED','INFORMED','SUPPORT','OTHER'))`
  (Q7). RASCI's S maps to SUPPORT. RAPID is a **mapping** in the seed, not a sixth vocabulary.
  For example, Decide → ACCOUNTABLE, Perform → RESPONSIBLE, Input → CONSULTED, and Recommend /
  Agree → OTHER unless Ben says otherwise.
- **`UNIQUE (code_id, category, behaviour_code)`**, which replaces delta 1's `(code_id,
  behaviour_code)`. This is the composite-FK target. The **category** is in it because the two
  vocabularies share `OTHER`, so behaviour alone no longer proves which category a code
  belongs to.

Every referencing row carries a **generated constant category** and a **copy of the
behaviour**, and references all three columns **ON UPDATE NO ACTION**:

```
FUNCTION_REQUIREMENT (fr_type_code_id, fr_type_category = 'FR_TYPE', fr_type_behaviour)
BFC_NODE_ORG_ROLE    (raci_code_id,    raci_category    = 'RACI_TYPE', raci_behaviour)
BR_ORG_ROLE          (raci_code_id,    raci_category    = 'RACI_TYPE', raci_behaviour)
   → CODE_MASTER (code_id, category, behaviour_code)                       NO ACTION
```

Three things follow from it, all declarative:
1. **The code FK provably points at the right category.** An `fr_type_code_id` or a
   `raci_code_id` aimed at an ISSUE_SEVERITY row cannot be stored. Before this, no RACI FK could
   prove that.
2. **A behaviour is immutable once any row references its code (Q6, R2-D8).** Changing
   `behaviour_code` changes a referenced key, so NO ACTION refuses it while *any* FR or RACI
   link, active or retired, points at the code. That is the mechanism. It needs no trigger and
   no service guard, and it covers global and project codes alike. An
   unreferenced code may still change behaviour. A project that wants a different behaviour
   adds a new code and moves its rows to it.
3. **Single-accountable and lane rules can be declared,** because the literal now sits on the
   link row (BFC_NODE_ORG_ROLE / BR_ORG_ROLE, below). "Partial unique on `'A'` over a code FK" (R2-D11) could not be expressed.
   `WHERE raci_behaviour = 'ACCOUNTABLE'` can.

*Fallback on a build that refuses a constant generated column:* a plain column `DEFAULT
'FR_TYPE'` with `CHECK (fr_type_category = 'FR_TYPE')`. The effect is identical.

Why a column and not a `jsonb` bag or a separate `FR_TYPE` / `RACI_TYPE` table: a column is
checkable and joinable, and it is the only option of the three that the composite-FK trick can
reach. A separate table would move a category out of the lookup mechanism that §9.3 says owns
all of them.

**PROJECT_SEQUENCE** — one row per (project, number series). PK `(project_id, sequence_code)`,
where `sequence_code ∈ {DE, BR, FR, ISSUE, SOL, BEN, RSK, CR, DEC, EXT}` under a CHECK on that
list. **All ten rows are seeded by `create_project` in the project's own transaction (R2-D14).**
"Every project has all ten" is a mandatory-child rule, which cannot be declared. So
`next_number` **raises** on a missing row and never inserts one lazily: a lazy insert races,
because two first-ever numbers would both try to create the row. `consistency_check` reports
`project_sequence_missing`. There is deliberately no interface series (D-27), no WBS series
(the key is MS Project's Unique ID, D-33) and no program series (a program is not
project-scoped). Attributes `prefix`, `pad_width`, `last_value`. See §5.4.6.

#### Client organisation (area 8)

**ORG_UNIT** — one row per organisational unit at any of three levels, within one project. PK `org_unit_id`; FK `project_id`, `parent_org_unit_id` (self, nullable), `level_code_id`. UK `(project_id, org_unit_id)` as a composite-FK target. Constraints: `CHECK (level_no BETWEEN 1 AND 3)`, `CHECK ((level_no = 1) = (parent_org_unit_id IS NULL))`, and a composite FK `(parent_org_unit_id, project_id) → ORG_UNIT(org_unit_id, project_id)` so a Division can never be parented into another project's Department. Depth-consistency (`child.level_no = parent.level_no + 1`) needs a trigger or a second composite FK carrying `parent_level_no`; at three levels I would use the composite-FK trick, at five (BFC) I would too — it is declarative and costs one smallint.

**ORG_ROLE** — one row per role defined within one org unit. PK `org_role_id`; FK `org_unit_id`, `project_id`. UK `(project_id, org_role_code)`. **Named `ORG_ROLE`, never `ROLE`**, and the app-side one is `project_role_code` (D-9). The bare word `ROLE` is banned from the schema, the SQLAlchemy models and the API paths (`/org-roles` vs `/app-roles`) — it is also a PostgreSQL reserved word, which conveniently makes the rule self-enforcing.

#### Business Function Chart (area 1)

**BFC_NODE** — one row per node in the client's business process hierarchy, at any level 1–5,
within one project. PK `bfc_node_id`; FK `project_id`, `parent_bfc_node_id`. UK
`(bfc_node_id, project_id)` and UK `(bfc_node_id, project_id, is_process)` as composite-FK
targets. Partial UKs:
- **`(project_id, hier_code) WHERE is_active`** (R2-D10, was a full UK). A retired node keeps
  the code it last had as history, and must not block its reuse by a live node. The
  consequence is that **`hier_code` is no longer an identifier** (it never was a stable one,
  D-10). Two rows, one retired, may share a code, so every lookup by code filters `is_active`.
  That is why imports identify steps by BR number (§5.4.18, R2-D1). Restoring a node whose
  code a live node now holds is refused by the index. The service renumbers the restored node
  into its parent (§7.12 `restore`).
- `(project_id, parent_bfc_node_id, seq_no) NULLS NOT DISTINCT WHERE is_active`: sibling
  order, L1 included (**S1-1**; was `(parent_bfc_node_id, seq_no)`).
- **`(parent_bfc_node_id, lower(btrim(node_name))) WHERE is_active AND is_process`** (Q1): two
  live process steps under one parent cannot share a name. Promoting a node to process when a
  process sibling already has its name is refused. The partial predicate follows Ben's answer
  exactly: *process* children. The index covers process children only; the service check is wider and refuses any active
  sibling with the same normalised name (§7.2 `assert_name_free`, Q1), so the index is the
  backstop for steps rather than the whole rule.

**`is_process boolean NOT NULL DEFAULT FALSE`** (D-23) marks a **process node**: the lowest node
of its branch, which carries the BR, the step I/O, the roles, the flow edges, the external
flows and the as-is application. It is a **stored, declared fact**, not derived from "has no
children", for two reasons. A CHECK cannot see other rows. And a leaf is not yet a process while
the consultant is still drafting the branch, so deriving it would make a BR appear and vanish as
children are added.

Constraints:
- `CHECK (level_no BETWEEN 1 AND 5)`; `CHECK ((level_no = 1) = (parent_bfc_node_id IS NULL))`
- `CHECK (NOT is_process OR level_no >= 3)`: a process sits at L3–L5 (A-47)
- `CHECK (level_no < 5 OR is_process)`: an L5 node can have no children, so it is always a
  process (A-54). Together with the guard below, this also enforces the old "no level 6" rule.
- `CHECK (is_process OR data_processing_desc IS NULL)`: only a process step carries the
  processing description (replaces `level_no = 5 OR …`)
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
- **Demotion** (`is_process → FALSE`) changes the key that every active dependent references
  (BR, step I/O, roles, flow edges, external flows, as-is application links), so the DB refuses
  it until they are retired. `data_processing_desc` must be cleared too, by the CHECK above.
  Ben's service rule "retire the BR first" is therefore **enforced by the database, and extended
  to every step-level fact**. `bfc.mark_process(demote)` retires them in one transaction, after
  a preview naming each one (A-48).
- *Fallback if a target PostgreSQL build refuses a generated column in an FK:* a plain column
  plus `CHECK (parent_is_process IS NOT DISTINCT FROM CASE WHEN is_active THEN FALSE END)`. The
  effect is the same, and the soft-delete service writes the column.

Depth consistency (`child.level_no = parent.level_no + 1`) stays with the service and
`consistency_check` (`level_no_drift`), as before.

**I confirm the single self-referencing table over five typed tables.** The case against five typed tables is decisive here: every read is a tree read (breadcrumb, drilldown, full-chart export), and with five tables each of those becomes a five-way join with a hand-written UNION for "search all nodes by name". Insert/move logic multiplies by five. Vertical relabelling ("we want a level between 3 and 4") becomes a migration rather than a data change. The one thing typed tables buy you, different attributes per node kind, is real (only a process node has `data_processing_desc`, and only a process node links to DEs, roles, flows, external parties and as-is applications). But it is a *subtype* problem, and D-23 has made it a subtype of *process vs. non-process*, not of level. That is one more reason typed-by-level tables would now be wrong. The honest cost in one table is four `CHECK`s plus a process guard on eight FK relationships. That is a much smaller bill than five tables. Practical addition for PostgreSQL: index `hier_code` with `varchar_pattern_ops` so `LIKE '01.02.%'` subtree queries use the index; if the chart ever exceeds a few thousand nodes, add `ltree`.

**BFC_NODE_DATA_ENTITY** — one row per (process node, data entity, direction). **The one record
of a step's inputs and outputs (D-24)**: the process-flow editor writes it directly, and there
is no flow-level I/O table. A step has 0..N inputs and 0..N outputs. PK `(bfc_node_id,
data_entity_id, direction)`, `CHECK (direction IN ('I','O'))`. Direction is in the key because a
step can both read and write the same entity. FKs: `(bfc_node_id, project_id) → BFC_NODE`,
`(data_entity_id, project_id) → DATA_ENTITY`, and the **process guard**: `node_is_process
boolean GENERATED ALWAYS AS (CASE WHEN is_active THEN TRUE END) STORED` + FK `(bfc_node_id,
project_id, node_is_process) → BFC_NODE(bfc_node_id, project_id, is_process)`. This replaces the
`bfc_level_no = 5` literal and keeps the trick: ugly-looking, entirely declarative, zero
triggers. **UK `(bfc_node_id, data_entity_id, direction, is_active)`** is the target that
BR CRUD and external flows reference (§5.4.2 D-24 note). It is a superset of the PK, so it is
trivially unique, and it exists only so that retiring an I/O row counts as a key change.

**BFC_NODE_ORG_ROLE** — one row per (process node, org role, RACI code). PK `(bfc_node_id,
org_role_id, raci_code_id)`. The same `node_is_process` guard as `BFC_NODE_DATA_ENTITY`.
**Q7:** `raci_category varchar(20) GENERATED ALWAYS AS ('RACI_TYPE') STORED`, `raci_behaviour
varchar(20) NOT NULL` (a copy the service writes from the code), and FK `(raci_code_id,
raci_category, raci_behaviour) → CODE_MASTER(code_id, category, behaviour_code)` NO ACTION
(§5.3 CODE_MASTER). **At most one Accountable per step:** partial `UNIQUE (bfc_node_id) WHERE
is_active AND raci_behaviour = 'ACCOUNTABLE'`. This rule was promised in §5.4.5 and missing
from §6.2. **At most one Responsible per step:** partial `UNIQUE (bfc_node_id) WHERE is_active
AND raci_behaviour = 'RESPONSIBLE'`. That role is the step's swimlane (A-46), never read from
the letter `R`, and a flow import's lane replaces it (§7.2b). A step with none is legal, drawn
in the "unassigned" lane and reported (`flow_completeness_report.no_lane`). "At least one Accountable" stays a completeness report (§5.4.5).

**BFC_NODE_FLOW** *(added by Lilly, D-20)* — one row per flow edge between two process steps
(D-23: process nodes, at any of L3–L5). PK `bfc_node_flow_id`; FK `project_id`,
`from_bfc_node_id` (nullable = start event), `to_bfc_node_id` (nullable = end event),
`flow_type_code_id`. `CHECK (num_nonnulls(from_bfc_node_id, to_bfc_node_id) >= 1)`. Each end
carries the plain composite `(id, project_id)` FK and a process guard: `from_is_process` /
`to_is_process boolean GENERATED ALWAYS AS (CASE WHEN is_active THEN TRUE END) STORED` + FK
`(from_bfc_node_id, project_id, from_is_process) → BFC_NODE(bfc_node_id, project_id,
is_process)`, and the same for `to`. A null end skips its guard under MATCH SIMPLE, which is what
a start or end event needs. So an edge cannot cross projects, and cannot attach to a summary
node.

**Natural key (Q2, R2-D4):** a partial unique index,

```sql
CREATE UNIQUE INDEX uq_bfc_node_flow_edge
    ON bfc_node_flow (from_bfc_node_id, to_bfc_node_id, lower(btrim(condition_label)))
    NULLS NOT DISTINCT
    WHERE is_active;
```

plus `CHECK (condition_label IS NULL OR btrim(condition_label) <> '')`, so an empty string
cannot pose as a distinct condition. In words: **two live edges may join the same two steps
only if their conditions differ** (Q2). NULLS NOT DISTINCT makes one start event per step and
one unlabelled end event per step, and forbids a second unlabelled S1 → S2.

- **The flow type is deliberately not in the key.** Otherwise a SEQUENCE and a
  PARALLEL edge, both unlabelled, could join the same pair, which Q2 rules out.
- **Partial, not full**, unlike `BFC_NODE_EXTERNAL_FLOW`. An edge's
  `condition_label` is editable, while an external flow's key columns are not. A full
  constraint would let a retired edge's label block renaming a live one. **Restore
  semantics:** adding an edge whose retired twin exists (same from, to and normalised label)
  **restores the twin** rather than inserting (§7.2a `link_process_flow`). So `source_bfc_node_flow_id` stays
  stable across baselines, and a diff does not report REMOVED + ADDED for an edge that was
  taken out and put back. Restoring a twin while a live duplicate exists is refused by the
  index.

> **Superseded by S2-1 (2026-09-30):** `flow_type` is a CHECK-listed column and the label rule is the table CHECK `ck_bnf_conditional_label`; the paragraph below is the rejected variant.

**Restated mechanism for the CONDITIONAL rule (R2-D11 class).** "A CONDITIONAL edge
needs a label" cannot be a CHECK, because `flow_type_code_id` is an FK and `'CONDITIONAL'` is on
another table. It is enforced by the service on create and update, and proved by
`consistency_check.conditional_without_label`. `FLOW_TYPE` must be seeded `is_system` (not
project-editable), because code branches on each value. *Recommended alternative:* make the
flow type a `CHECK`-listed column, as `diagram_type` is. The rule is then one real CHECK.

**`condition_label`** is required when `flow_type = CONDITIONAL` and is what turns a box-and-arrow picture into a readable process: *「与信NG」*, *"amount > 1,000,000"*. `seq_no` orders the outbound edges of a node so a decision's branches render in a stable order.

**Cycles are permitted, deliberately.** `SOLUTION_DEPENDENCY` rejects them because a dependency cycle makes a phase plan unsolvable; a *process* cycle is a rework loop — "reject → correct → resubmit" — and is ordinary business behaviour. The traversal in `generate_process_flow` is therefore visited-set guarded rather than assumed acyclic. **Flagged because it is the opposite rule to the one two tables away, and a builder who generalises from `SOLUTION_DEPENDENCY` will break it.**

**Edges may cross business areas.** A hand-off from Order Management to Fulfilment is a real flow, so `from` and `to` are not constrained to share a parent — `flow_type = HANDOFF` marks it, and `generate_process_flow` renders it as an edge leaving the diagram rather than pretending it does not exist.

**EXTERNAL_ENTITY** *(D-24a)* — one row per party outside the client organisation that exchanges
data with the client's process steps (a Customer, a Bank, a Regulator, a Supplier), within one
project. PK `external_entity_id`; FK `project_id`, `kind_code_id` (nullable →
`EXTERNAL_ENTITY_KIND`; an unknown kind is a warning, not a block, because an imported flow
often names a party without classifying it). UK `(project_id, ext_number)` → `EXT-0001`, a full
constraint, so numbers are never reused. Partial UK `(project_id, lower(ext_name)) WHERE
is_active`, because two active "Customer" parties in one project is a modelling error. UK
`(external_entity_id, project_id)` is the composite-FK target. **It is not a `STAKEHOLDER`**: a
stakeholder is a named person who raises issues, while an external entity is a *role in a data
flow* ("Customer" is thousands of people and one box on a DFD). **It is not an `APPLICATION`**
either: the bank's system, if the interface list needs it, is an application; the bank is the
party.

**BFC_NODE_EXTERNAL_FLOW** *(D-24a)* — one row per (process node × external entity × direction ×
data entity), where the data entity is **nullable**, for an exchange whose data is not yet
modelled ("the customer phones in"). Because a nullable column cannot sit in a PK, the key is a
surrogate `bfc_node_external_flow_id` plus **`UNIQUE NULLS NOT DISTINCT (bfc_node_id,
external_entity_id, direction, data_entity_id)`** (PostgreSQL 15+; on 14, two partial unique
indexes split on `data_entity_id IS NULL`). This is a full constraint, not partial: re-adding a
removed flow restores the row, so its baseline `source_id` stays stable and a diff does not
report REMOVED + ADDED. `direction` is from the **step's** point of view, the same axis as
`BFC_NODE_DATA_ENTITY`: `'I'` = the party sends to the step, `'O'` = the step sends to the party.
`CHECK (direction IN ('I','O'))`. `flow_label varchar(200) NULL` names an informal exchange when
no DE is given.

FKs: `(bfc_node_id, project_id)` and the `node_is_process` guard (process steps only);
`(external_entity_id, project_id)`; `(data_entity_id, project_id)`; and, **when a DE is named,
the D-24 rule applied again**: `io_is_active boolean GENERATED ALWAYS AS (CASE WHEN is_active
THEN TRUE END) STORED` + FK `(bfc_node_id, data_entity_id, direction, io_is_active) →
BFC_NODE_DATA_ENTITY(bfc_node_id, data_entity_id, direction, is_active)`. "Customer → Sales
order → Receive order" is **also** an input of Receive order, and the model refuses to hold the
external flow without the step I/O it describes. Otherwise the DFD and the process flow would
disagree about a step's inputs, which is exactly what D-24 exists to prevent. A null DE skips
this FK. The service creates the missing I/O row in the same transaction, as it does for BR
CRUD. For `generate_dfd`: an I/O row that has a matching external flow is drawn from/to the
party; the store is still drawn, because another step may read it.

#### Data entities (area 3)

**DATA_ENTITY** — one row per logical data entity in one project. PK `data_entity_id`; FK `project_id`. **UK `(project_id, de_number)`** — this is the uniqueness guarantee; the generator is a convenience, the constraint is the law. UK `(project_id, de_name)` too, probably — confirm, since two entities called "Customer" in one project is a modelling error you want the DB to reject.

**DATA_FIELD** — one row per **logical** field within one data entity (D-26). VB models a
logical data model and never generates tables, so **a partial list is the normal state**: a DE
may list only its keys and key attributes. PK `data_field_id`; FK `project_id`,
`data_entity_id`, `data_type_code_id` (**nullable**: the logical type is optional),
`ref_data_entity_id` (nullable), `ref_data_field_id` (nullable). UK `(data_entity_id,
field_name)`, partial UK `(data_entity_id, pk_ordinal) WHERE is_primary_key`.

**`is_mandatory boolean NULL`** replaces `is_nullable`. Three states: TRUE mandatory, FALSE
optional, NULL *not yet known*. Keeping both columns would store the dependency `is_mandatory =
NOT is_nullable` inside one row, the same 3NF defect §5.4.2 removed from CRUD/direction. The
ERD reads it: an FK whose fields are all mandatory draws the parent side as `||`, and one with
any field optional *or unknown* draws `o|`. Unknown renders as optional on purpose, because a
diagram must not claim a rule nobody stated (A-53, §7.4).

Composite PKs are representable exactly as asked: several fields in one DE with
`is_primary_key = true` and distinct `pk_ordinal` 1..n. Constraints (**PK/FK composite
constraints unchanged by D-26**): `CHECK (is_primary_key = (pk_ordinal IS NOT NULL))`,
`CHECK (is_foreign_key = (ref_data_entity_id IS NOT NULL))`, `CHECK (ref_data_field_id IS NULL OR
is_foreign_key)`, the composite FK `(ref_data_field_id, ref_data_entity_id) →
DATA_FIELD(data_field_id, data_entity_id)` with its supporting UK, and the `(…, project_id)`
composite FKs of finding D9. Added by D-26: `CHECK (NOT is_primary_key OR is_mandatory IS
DISTINCT FROM FALSE)`, because a key field cannot be optional (it may be unknown while the model
is being drafted).

**Logical FK groups (canvas spike, GO).** One entity may hold two relationships to the same
parent: `Order.ship_to_address_id → Address` and `Order.bill_to_address_id → Address`. With
`ref_data_entity_id` alone, the ERD sees one relationship with two fields and draws one
composite FK, which is wrong. **`fk_group_no smallint NULL`** says which relationship a field
belongs to. **A relationship is the set of fields in one DE sharing `(ref_data_entity_id,
fk_group_no)`.** Ship-to is group 1 and bill-to is group 2. A composite FK is several fields in
one group.

- `CHECK ((fk_group_no IS NOT NULL) = is_foreign_key)`: every FK field is in exactly one group,
  and a non-FK field is in none. The service assigns 1 for the first relationship to a parent
  and the next free number for another.
- `CHECK (fk_group_no IS NULL OR fk_group_no >= 1)`.
- Partial `UNIQUE (data_entity_id, ref_data_entity_id, fk_group_no, ref_data_field_id) WHERE
  is_active AND ref_data_field_id IS NOT NULL`: within one relationship, a parent field is
  referenced at most once. Two groups may both reference `Address.address_id`, which is the
  point.
- ERD derivation (A-53) now runs **per group**. The parent side is `||` when every field of the
  group is mandatory. The child side is `1` when the group's field set equals the DE's PK set.
  The arity check against the parent PK stays a warning, because a partial field list is
  normal (D-26).
- *Gap, flagged, not modelled:* a **role name** for the relationship ("ship to", "bill to") for
  the ERD edge label. It depends on `(data_entity_id, ref_data_entity_id, fk_group_no)` and not
  on any one field. On `DATA_FIELD` it would repeat across the group's fields, which is a 2NF
  defect. If the canvas needs it, it is a new entity, `DATA_ENTITY_RELATIONSHIP`, keyed on that
  triple.

`length_val` / `precision_val` / `scale_val` stay optional and are meaningful only for some
types. That is *not* a normalization defect: they depend on the field, not on the type. D-26
adds one rule: `CHECK (data_type_code_id IS NOT NULL OR num_nulls(length_val, precision_val,
scale_val) = 3)`, because a length with no type has nothing to be a length of. Which types show
which of the three is a UI rule. It should live on the `FIELD_DATA_TYPE` code_master rows, not
in React. If Ben wants it, it is a second use of the `behaviour_code` column (§5.3 CODE_MASTER).

#### Business Requirement (area 2)

**BUSINESS_REQUIREMENT** — one row per **process node** (D-2, restated by D-23). PK `br_id`; FK
`project_id`, `bfc_node_id`, `status_code_id`. UK `(project_id, br_number)`; **partial UK
`(bfc_node_id) WHERE is_active`**, the 1:1, which is partial so that a retired BR does not
occupy the node forever (finding P5). *(The previous note's `(bfc_node_id, seq_no)` UK was a
1:N-era leftover and is removed.)* **Process guard:** `node_is_process boolean GENERATED ALWAYS
AS (CASE WHEN is_active THEN TRUE END) STORED` + FK `(bfc_node_id, project_id, node_is_process)
→ BFC_NODE(bfc_node_id, project_id, is_process)`, beside the plain `(bfc_node_id, project_id)`
FK. Together they enforce "process only" and "same project" and replace `bfc_level_no = 5`. A
retired BR's guard is NULL, so it neither blocks demotion nor prevents a replacement BR. **UK
`(br_id, project_id, bfc_node_id)`** is the target that carries the BR's node down to
`BR_DATA_ENTITY` (D-24). `bfc_node_id` is **immutable**: a BR never moves between nodes. The
service refuses the update, and the FK from `BR_DATA_ENTITY` would refuse it anyway once any CRUD
exists. "Every process node has an active BR" is a mandatory child, which is not declarable. It
is service-guaranteed (`create_node` / `mark_process`) and reported by `consistency_check`
(`process_without_br`).

**The BR number is the step's import identity (R2-D1).** Process node ↔ active BR is 1:1 (D-2),
`br_number` is never reused (full UK), and `bfc_node_id` on the BR is immutable. So `br_number`
identifies the step more stably than the node's own `hier_code`, which changes on every
reorder and is only partially unique since R2-D10. Both importers (the BR sheet and the flow
JSON's steps) therefore **resolve an existing step by BR number**. A `hier_code` in the file is
kept in `IMPORT_ROW.cross_check_key` and only *compared*: a mismatch is a warning naming both
codes, never a second lookup (§5.4.18).

**BR_DATA_ENTITY** — one row per (BR, data entity, CRUD operation). PK `(br_id, data_entity_id,
crud_code)`, where `crud_code char(1) CHECK (crud_code IN ('C','R','U','D'))` (a CHECK, not a
code_master FK: §5.4.2, §8; the old diagram's `crud_code_id` is corrected). `direction` is
**generated** (`R → 'I'`, else `'O'`). **D-24 adds** `bfc_node_id bigint NOT NULL`, a copy of the
BR's node, made safe by FK `(br_id, project_id, bfc_node_id) → BUSINESS_REQUIREMENT(br_id,
project_id, bfc_node_id)`. It also adds `io_is_active boolean GENERATED ALWAYS AS (CASE WHEN
is_active THEN TRUE END) STORED` and the **licence FK** `(bfc_node_id, data_entity_id,
direction, io_is_active) → BFC_NODE_DATA_ENTITY(bfc_node_id, data_entity_id, direction,
is_active)`. In words: **an active Read needs an active input row for that DE on the BR's own
step, and an active Create/Update/Delete needs an active output row.** Both sides of the FK
come from things the DB derives itself (the BR's node, the generated direction), so a
disagreement cannot be stored. See §5.4.2 (D-24 note) for the cost.

**BR_ORG_ROLE** — one row per (BR, org role, RACI code). PK `(br_id, org_role_id,
raci_code_id)`. It has the same `raci_category` / `raci_behaviour` columns and FK as
`BFC_NODE_ORG_ROLE`. **At most one Accountable per BR:** partial `UNIQUE (br_id) WHERE
is_active AND raci_behaviour = 'ACCOUNTABLE'`. The old `WHERE raci_code = 'A'` could not be
written, because `raci_code_id` is an FK and the letter lives on another table (R2-D11). It
would also have been wrong for a client whose Accountable letter is not `A`. See §5.4.5.

#### Function Requirement (area 4)

**FUNCTION_REQUIREMENT** — one row per FTC-authored system function specification in one
project. PK `fr_id`; FK `project_id`, **`solution_id` (nullable, D-28)**, `fr_type_code_id` (was
`category_code_id`, D-27), `complexity_code_id`, `fulfilment_status_code_id`. UK `(project_id,
fr_number)`; UK `(fr_id, project_id)`; **UK `(fr_id, project_id, fr_type_behaviour)`** as the
target for `FR_INTERFACE`.

- **D-28: an FR may exist with no Solution**, and therefore with no path to a BR, a phase, a
  benefit or a delivering application. `(solution_id, project_id) → SOLUTION` applies when a
  solution is present and is skipped when it is NULL. An unlinked FR is a **warning**
  (`coverage.fr_unlinked`, the import preview, the control panel), never an error. A BR with no
  FR was always legal.
- **D-27: `fr_type_behaviour varchar(20) NOT NULL`** is a copy of the type's behaviour, and
  **`fr_type_category varchar(20) GENERATED ALWAYS AS ('FR_TYPE') STORED`**. Both are verified
  by FK `(fr_type_code_id, fr_type_category, fr_type_behaviour) → CODE_MASTER(code_id, category,
  behaviour_code)` **ON UPDATE NO ACTION** (Q6, R2-D8; was CASCADE). The service writes the copy
  from the code at save, and the FK rejects a wrong copy. Changing a type's behaviour is
  refused while any FR, live or retired, uses the type. The behaviour is immutable once
  referenced, and a cascade can no longer write into other projects' FRs from a global code.
- **D-34: `suggested_br_id bigint NULL`**: the BR an FR import row named that the FR is not yet
  traced to. FK `(suggested_br_id, project_id) → BUSINESS_REQUIREMENT(br_id, project_id)` (the
  `(br_id, project_id)` target every junction already references; declare it if absent), so a
  suggestion cannot cross projects (R2-D16). **It may coexist with `solution_id`** (D-34 as
  ruled, §1a): it clears only when a `BR_SOLUTION` path from the suggested BR to the FR's
  solution exists (`link_fr_solution` and `link_br_solution`, §7.5), so linking a solution the
  BR does not reach leaves it set. That rule reads another table, so it is service-enforced,
  not a CHECK. It is a working hint, not agreed scope. So it is **excluded from
  `content_hash`** (R2-D16), and it is not copied into `baseline_function_requirement` either:
  it goes on the column-parity test's exclusion list beside the audit columns. Retiring the
  suggested BR clears the hint rather than being refused by it (§7.12).
- `fulfilment_status` still encodes "FTC specifies, vendor builds later". No vendor entity
  exists in the MVP.

**SOLUTION** *(added by Lilly, D-7)* — one row per transformation answer within one project. PK `solution_id`; FK `project_id`, `category_code_id`, `status_code_id`. UK `(project_id, solution_number)` → `SOL-0001`. `category_code_id` resolves to **ORG_AND_RULES / PEOPLE / PROCESS / DATA / TECHNOLOGY**. A solution in the first three categories legitimately has no Function Requirements at all — that is the model expressing that not every answer is software.

**BR_SOLUTION** *(added, D-7)* — one row per (BR, solution) pairing. PK `(br_id, solution_id)`; `coverage_note` carries the relationship-specific fact ("this solution answers only the approval half of BR-0042"). M:N: one solution normally answers several requirements, and one requirement may need an org change *and* a system function.

**APPLICATION** *(added, D-8)* — one row per application or technology in one project's landscape. PK `application_id`; FK `project_id`, `app_kind_code_id`, `lifecycle_code_id`. UK `(project_id, application_code)`. `lifecycle_code` is **AS_IS / TO_BE / BOTH**, which is what lets one catalogue serve the current landscape and the target landscape without two tables.

**APPLICATION_SOLUTION** *(added, D-8)* — one row per (application, solution) allocation. PK `(application_id, solution_id)`. The to-be side: what will deliver this answer.

**APPLICATION_BFC_NODE** *(added, D-8; pinned by D-23)* — one row per (application, **process
node**) support statement. PK `(application_id, bfc_node_id)`, with the `node_is_process` guard.
This is newly pinned: before D-23 it accepted any level. It is now process-only because both
readers are step-level. `generate_process_flow` puts a system on each box, and `application_gap`
compares it with the to-be side, which is reached through the step's BR. An as-is link on a
summary node could never match. The as-is side says what supports this process today. **The
gap between this table and `APPLICATION_SOLUTION` is the deliverable.**

**STAKEHOLDER** *(added, D-4)* — one row per named client-side person in one project. PK `stakeholder_id`; FK `project_id`, `org_unit_id`. `is_bpo` separates BPO staff from the client's own business users, because they answer to a different contract. This is the entity `apple` recommended as option (b) for `raised_by`; it also carries interview and workshop provenance in later increments.

**FR_BFC_NODE** — one row per (FR, BFC node) direct link. PK `(fr_id, bfc_node_id)`. See §3.3.

**FR_INTERFACE** *(D-27)* — **one row per interface-type FR** (1:0..1). It holds what only an
interface has. PK and FK `fr_id`; FK `project_id`. Columns: `source_application_id NOT NULL`,
`target_application_id NOT NULL`, `pattern_code_id` (→ `INTERFACE_PATTERN`: PUSH / PULL /
BIDIRECTIONAL), `method_code_id` (→ `INTERFACE_METHOD`: API / FILE / DB / MESSAGE / MANUAL),
`frequency_code_id` (→ `INTERFACE_FREQUENCY`: REALTIME … ON_DEMAND), `volume_note text`. The
three codes are nullable (not yet known). The two applications are not, because they are the row's
reason to exist. An interface FR whose endpoints are unknown has **no** `FR_INTERFACE` row and is
listed as incomplete (A-55). Constraints:
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
`(fr_id, data_entity_id)`; FK `project_id`; `note text`. FKs: `(data_entity_id, project_id) →
DATA_ENTITY`; `(fr_id, project_id) → FR_INTERFACE`; and a guard `interface_is_active boolean
GENERATED ALWAYS AS (CASE WHEN is_active THEN TRUE END) STORED` + FK `(fr_id, project_id,
interface_is_active) → FR_INTERFACE(fr_id, project_id, is_active)`. Retiring the interface
detail while it still lists active carried entities is refused, which closes the "live child
under a dead parent" class of finding D1 by construction.

**The interface list is a view, not a table (D-27).** Identity is the FR number. There is no
second number series to keep in step:

```sql
CREATE VIEW v_interface_list AS
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
    s.solution_number,                                          -- NULL = unlinked (D-28)
    ARRAY(SELECT br.br_number
          FROM   v_br_function_requirement v
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
`require_project`), like every view here. `interface_load` (§7.9) should read this view and group
by `(source_application_id, target_application_id)` instead of inferring pairs through
`APPLICATION_SOLUTION`. The endpoint is a stated fact now, not a guess.

#### Issues (area 5)

**ISSUE** — one row per issue raised in one project. PK `issue_id`; FK `project_id`, `severity_code_id`, `issue_type_code_id`, `status_code_id`, **`raised_by_stakeholder_id NOT NULL`** (the client-side person who raised it) and **`recorded_by_user_id NOT NULL`** (the consultant who typed it). UK `(project_id, issue_number)`. Resolution is `resolution text`, `resolved_at timestamptz`, `resolved_by_user_id` — there is no `resolved_date`. *(Rewritten — the pre-D-4 `raised_by_user_id` + `raised_by_name` hedge described here was superseded and is gone; finding D8.)*

The issue is anchored to the **project**, not to a BR. That matters: an issue found during discovery, before any BR exists, still needs somewhere to live. BR linkage is optional and multiple.

**ISSUE_BR** — one row per (issue, BR) association. PK `(issue_id, br_id)`. See §3.3 for the cardinality argument.

#### Control framework (D-13…D-19) — added by Lilly

**EFFORT_RATE** — one row per (project × **FR type** × complexity) (D-27). PK `(project_id,
fr_type_code_id, complexity_code_id)`. `standard_days numeric NOT NULL`. Seeded from an FTC
default at `create_project`, then negotiated per client. **Changing a rate does not reprice
existing FRs**: `FUNCTION_REQUIREMENT.effort_days` is derived at save and stored. The card keys
on the **type**, not the behaviour. A project override of a global type gets a new `code_id`,
and `maintain_fr_types` re-points the project's rate rows and FRs to it in one transaction.

**R2-D7: audited and frozen. I recommend both, because they answer different questions.**
- **Audit** answers *who changed the rate, when, from what, and why*.
  `change_rationale text NULL` holds the reason for the current value, under **`CHECK
  (row_version = 1 OR change_rationale IS NOT NULL)`**. A row that has ever been updated must
  say why. `row_version` increments on every UPDATE (§5.1), so this is declarative. It proves
  that *a* rationale exists, not that it is fresh: the service demands a new one on each change.
  Old, new and rationale go to `AUDIT_EVENT` (`RATE_CARD_CHANGED`, §7.13). Nothing reports from the
  history between freezes, so AUDIT_EVENT is the right home (§5.3 AUDIT_EVENT reasoning).
- **Freeze** answers *what rate card this baseline was priced on*. It is the commercial term
  a signed scope was agreed at, and it must be recoverable with the baseline for five years
  (Q12). **`effort_rate` joins the freeze set as `baseline_effort_rate`** (§6.1; the set is now 30 tables).
  This reverses §6.1's earlier "deliberately not". That reasoning was about FR days, and the
  FR still carries its computed days, so both statements hold.
- **`effort_rate_id bigint GENERATED ALWAYS AS IDENTITY`, UK**: an alternate key that is the
  shadow's `source_effort_rate_id`. A surrogate is needed because the natural PK *moves* when
  `maintain_fr_types` re-points a rate to an override code. With the surrogate, a re-pointed
  rate is still the same row to the diff, not REMOVED + ADDED.

**BASELINE_EFFORT_RATE** — one row per live rate as it stood at a freeze. PK
`baseline_effort_rate_id`; FK `baseline_id`, `source_effort_rate_id → effort_rate(effort_rate_id)`
ON DELETE NO ACTION. UK `(baseline_id, source_effort_rate_id)`. It copies resolved codes and
labels, not code FKs (§5.4.4): `fr_type_code`, `fr_type_label`, `fr_type_behaviour`,
`complexity_code`, `complexity_label`, `standard_days`, `change_rationale`, `content_hash`.
`HASH_COLUMNS`: `fr_type_code`, `complexity_code`, `standard_days`. The labels are presentation
and the rationale is provenance, so neither is hashed.

**BENEFIT** — one row per quantified benefit in one project. PK `benefit_id`; FK `project_id`, `benefit_type_code_id`, `accountable_org_role_id`, `status_code_id`. UK `(project_id, benefit_number)` → `BEN-0001`. Carries `measure_name`, `measure_unit`, `baseline_value`, `target_value`, `realisation_date`. **A benefit with no accountable org role is not a benefit, it is a hope** — the FK is `NOT NULL`.

**BENEFIT_SOLUTION** — one row per (benefit × solution). PK both; `contribution_pct` carries the relationship-specific fact, because a benefit is rarely delivered by one solution alone and the split is what you argue about at realisation.

**RISK** — one row per risk in one project. PK `risk_id`; FK `project_id`, `probability_code_id`, `impact_code_id`, `owner_org_role_id`, `status_code_id`, optional `bfc_node_id` / `solution_id`, and `materialised_issue_id` (nullable). UK `(project_id, risk_number)` → `RSK-0001`. `exposure_score` is derived at save from probability × impact. **Deliberately not merged with `ISSUE`** — an issue has happened and needs resolution; a risk might happen and needs mitigation. The one path between them is `promote_risk_to_issue`, which sets `materialised_issue_id` and leaves the risk row intact as the record that it was foreseen.

**CHANGE_REQUEST** — one row per proposed change to a **frozen** baseline. PK `change_request_id`; FK `project_id`, `against_baseline_id NOT NULL`, `origin_code_id`, `status_code_id`, `displaces_cr_id` (nullable self-reference), `decision_id`. UK `(project_id, cr_number)` → `CR-0001`. `effort_delta_days` and `benefit_delta_value` are **computed from `CR_IMPACT`, never typed** — a change priced by the person requesting it is not priced.

**Which baselines a CR may target (Q8, R2-D11): FROZEN or APPROVED, never SUPERSEDED, and the
mechanism is not a CHECK.** A CHECK sees one row of one table, and the status lives on
`BASELINE` as a code FK. It is also a **point-in-time** rule. A CR raised against v1.0 while it
was APPROVED stays valid when v1.1 supersedes v1.0, so a declarative guard that refused
superseding a baseline with CRs against it would be wrong. The mechanism is:

1. `raise_cr` and any retarget read the baseline `SELECT … FOR SHARE`, and check its status
   code ∈ {`FROZEN`, `APPROVED`} inside that lock (§7.13 `raise_change_request`).
2. `freeze`'s transition of the prior baseline to SUPERSEDED takes that row `FOR UPDATE`, so the
   two serialize. A CR cannot slip in against a baseline in the instant it is superseded.
3. `BASELINE_STATUS` is seeded `is_system` and not project-editable, because code compares its
   codes. *(`DRAFT` in §8 is never written by `freeze`, so it looks unused.)*
4. `consistency_check.cr_on_superseded_at_creation` is **not** possible (history is not kept per
   status), so the lock is the whole guarantee, and criterion coverage should test it.

**CR_IMPACT** — one row per impacted object. PK `cr_impact_id`; FK `change_request_id`, `project_id`, plus **seven nullable typed FKs** — `impacted_br_id`, `impacted_solution_id`, `impacted_fr_id`, `impacted_application_id`, `impacted_data_entity_id`, `impacted_phase_id`, `impacted_benefit_id` — under `CHECK (num_nonnulls(...) = 1)`. Every one carries the composite `(id, project_id)` FK pattern of §5.6, so a CR physically cannot reach into another project's objects.

*(This replaces the soft polymorphic `impacted_entity` + `impacted_id` pair the first draft used. **Ben's call, 2026-09-24: the database enforces it.** `apple` warned against polymorphic FKs as unenforceable in SQL and painful in SQLAlchemy, and she was right — the seven columns are wider but they are checkable, joinable, and cascade-safe. `num_nonnulls()` is a PostgreSQL built-in, so "exactly one" is one `CHECK`, not a trigger. Adding an eighth impacted type later is a column and a migration, which is the honest cost and is paid once.)*

**DECISION** — one row per recorded project decision. PK `decision_id`; FK `project_id`, `decided_by_user_id`, `dimension_code_id`. UK `(project_id, decision_number)`. Carries `decision_text`, **`alternative_rejected`** and `analysis_code` — the analysis it was taken against. The rejected alternative is the field that makes a decision log worth reading; without it you record outcomes and lose reasoning.

**`DECISION` is append-only and evidential (Ben's call, 2026-09-24).** It carries the same `BEFORE UPDATE OR DELETE` reject trigger as the `baseline_*` shadow tables, is **exempt from soft delete** (no `is_active`, no `deleted_at`), and the application database role holds no `UPDATE` or `DELETE` privilege on it (§6.6). A decision that can be edited after the fact is not a record of a decision — it is a record of what someone currently wishes had been decided. A superseded decision is corrected by writing a **new** decision that references the old one via `supersedes_decision_id`, which is also how the log stays readable as a narrative.

**PHASE / SOLUTION_PHASE / SOLUTION_DEPENDENCY** — delivery waves, the assignment of solutions to them (`portion_pct`, because a solution can span waves), and prerequisite links. `SOLUTION_DEPENDENCY` is a DAG: **cycles are rejected on insert** by a topological check, the same discipline `apple` applied to `dim_bom` in the design-spec worked example.

**WBS_ITEM** *(D-33, Q13, R2-D15)* — one row per imported MS Project task line in one project.
**The schedule's system of record stays in MS Project.** VB holds a read copy for the program
dashboard's plan-vs-actual, plus two links that consultants own. WBS import is **optional per
project** (Q13). A project with no rows simply has no plan-vs-actual, so no flag is needed.

- **Key.** PK `wbs_item_id`; **UK `(project_id, ms_unique_id)`**, where `ms_unique_id int NOT NULL`
  is MS Project's *Unique ID*. That is the one task identifier MS Project never reassigns, so it
  is what a re-import updates by (R2-D15). It is a **full** constraint, not partial: a line
  retired by a replace-mode import and back in the next file restores the same row, with its VB
  links intact (A-68). UK `(wbs_item_id, project_id)` is the self-FK target.
- **`wbs_code varchar(50)` is an attribute, not a key** (Q13), and it carries no unique
  constraint. MS Project renumbers WBS codes when a task is moved in the outline, so during a
  re-import two rows legitimately swap codes, and a non-deferrable partial unique index would
  reject the valid file mid-statement. A duplicate code *within one file* is an
  import error (§7.11a).
- **Hierarchy.** `parent_wbs_item_id` (nullable) with FK `(parent_wbs_item_id, project_id) →
  WBS_ITEM(wbs_item_id, project_id)`; `outline_level smallint NOT NULL CHECK (outline_level >=
  1)`; `CHECK ((outline_level = 1) = (parent_wbs_item_id IS NULL))`; `CHECK (parent_wbs_item_id
  <> wbs_item_id)`. The import resolves the parent from outline order and drops MS Project's
  project-summary task (Unique ID 0). `display_order int NOT NULL` is the file's row order.
  `is_summary` and `is_milestone boolean NOT NULL` are stored **as MS Project states them**. They
  are imported facts, not VB derivations, for the same reason `is_process` is stored: a summary
  line's dates are MS Project's roll-up, and the dashboard must not add them to their children.
- **Dates and progress.** `planned_start`, `planned_finish`, `actual_start`, `actual_finish`,
  all `date NULL` (A-66); `CHECK (planned_finish IS NULL OR planned_start IS NULL OR
  planned_finish >= planned_start)`, the same for actuals; `CHECK (actual_finish IS NULL OR
  actual_start IS NOT NULL)`. `percent_complete numeric(5,2) NOT NULL DEFAULT 0 CHECK
  (percent_complete BETWEEN 0 AND 100)`.
- **Links (the only VB-edited fields, Q13).** `phase_id` and `solution_id`, each nullable (a
  line may link to either, both or neither), with composite FKs `(phase_id, project_id) →
  PHASE` and `(solution_id, project_id) → SOLUTION`, so a link cannot cross projects. A link
  to a solution not scheduled in the linked phase is a dashboard warning, not a constraint.
  Plans legitimately disagree with the wave plan, and that disagreement is what the dashboard
  exists to show.
- **Provenance.** `last_import_batch_id` → `IMPORT_BATCH` (the header survives the 90-day row
  purge, §5.3 Import staging).
- **`row_version` guards only the links (a documented deviation).** A link edit
  checks and bumps it. The import writes the MS-Project-owned columns **without** checking or
  bumping it and never touches `phase_id` / `solution_id`. VB holds nothing in the schedule
  columns that an import could overwrite, and a consultant's link edit must not 409 because MS
  Project moved a date. Recorded in `docs/PLAYBOOK_DEVIATIONS.md`.
- **Soft delete as usual.** Only a replace-mode import retires lines, with an acknowledged
  count, as in D-25. Retiring a Phase or Solution that live WBS lines link to is refused with a
  409 listing them (Q4).
- **Not baselined** (D-33): the schedule is not agreed scope. No shadow table and no hash. A
  consequence to know: a baseline diff can never show schedule slip (§5.6).

**CONTROL_RULE** — one row per (project × `analysis_code`), **or one FTC house default** when `project_id IS NULL`. PK `control_rule_id`; FK `project_id` (**nullable**), `owner_org_role_id`. Carries `comparison` (`GT` / `LT` / `PCT_GT`), `threshold_value`, `escalate_value`, `prescribed_action`, `escalation_path`, `is_enabled`, and the provenance fields `change_rationale` / `agreed_at`. **`analysis_code` is a closed vocabulary matching the report functions in §7.9 — a rule pointing at an analysis that does not exist is rejected**, which is what stops the table filling with aspirational governance.

**Two tiers, exactly as `code_master` does it (A-16).** `project_id IS NULL` is the **FTC house default**, editable by a platform admin through the app — not a code seed, not a developer change. Non-null is that project's own agreed rule. Uniqueness is the same pair of partial indexes: `UNIQUE (analysis_code) WHERE project_id IS NULL` and `UNIQUE (project_id, analysis_code) WHERE project_id IS NOT NULL`.

**But the resolution rule is the opposite of `code_master`'s, deliberately.** Codes resolve *live*, so renaming a global label updates every project that has not overridden it. Control rules **do not**: `create_project` **copies** the house defaults into project rows, and the project's rules are thereafter independent. Changing the FTC house default affects **future projects only**.

That asymmetry is the whole point. A project's thresholds are what FTC and the client **agreed at mobilisation**; if tightening the house standard in March silently moved a live engagement from GREEN to ESCALATE, the governance model would be something the client never signed up to, and the first person to notice would be the client. Same reasoning as `effort_days` (A-38) and the frozen `code_master` labels in `baseline_*` (§5.4.4): **an agreed number is copied, never referenced.**

`owner_org_role_id` is `NOT NULL` on a project rule and **nullable on a house default** — FTC cannot know which of a client's roles owns a response before the client's org chart exists, so `create_project` copies the thresholds and the OWNER assigns the roles at mobilisation. A project rule with no owner is reported by `coverage` as an incomplete control framework.

#### Diagram presentation (D-29, D-30)

**DIAGRAM_LAYOUT** — one row per (project × diagram type × scope × diagram object): where a
consultant put one box on one diagram. PK `diagram_layout_id`; FK `project_id`.

- `diagram_type varchar(20) NOT NULL CHECK (diagram_type IN ('ERD','PROCESS_FLOW','DFD'))`.
  This is a CHECK, not code_master, because the renderer and the object rules below branch on
  it (§8).
- `scope_bfc_node_id` (nullable): the node a process flow or DFD is drawn for, or the BFC branch
  an ERD is filtered to (Lilly's "subject area", §7.4). **NULL = the whole project**, ERD only:
  `CHECK (diagram_type = 'ERD' OR scope_bfc_node_id IS NOT NULL)`. The same entity has a
  different position in each scope. That is why scope is in the key, and why x/y depend on the
  whole key (2NF).
- **The object is four typed nullable FKs, not `object_type × object_id`:** `bfc_node_id` (a
  step, or a hand-off target outside the frame), `data_entity_id` (an ERD entity or a DFD/flow
  store), `external_entity_id`, and `bfc_node_flow_id` (the start/end event marker of an edge
  whose one end is NULL). `CHECK (num_nonnulls(bfc_node_id, data_entity_id, external_entity_id,
  bfc_node_flow_id) = 1)`. Each has the composite `(id, project_id)` FK. This is Ben's
  2026-09-24 CR_IMPACT ruling applied again: the database knows what a row points at and that it
  is in this project.
- Per-type object rules: `CHECK (diagram_type <> 'ERD' OR data_entity_id IS NOT NULL)` and
  `CHECK (diagram_type = 'PROCESS_FLOW' OR bfc_node_flow_id IS NULL)`.
- `x numeric(10,2) NOT NULL`, `y numeric(10,2) NOT NULL`, `width` / `height numeric(10,2) NULL`
  with `CHECK (width IS NULL OR width > 0)` and the same for height, and `is_collapsed boolean
  NOT NULL DEFAULT FALSE` (the ERD card's "+12 more").
- Natural key: `UNIQUE NULLS NOT DISTINCT (project_id, diagram_type, scope_bfc_node_id,
  bfc_node_id, data_entity_id, external_entity_id, bfc_node_flow_id)`. It also serves as the
  "all positions for this diagram" index.
- `created_at`, `updated_at`, `created_by`, `updated_by` (the "updated_by" Ben asked for) per
  §5.1.

**Not baselined, explicitly.** A position is presentation, not scope. Nothing about what was
agreed changes when a box moves, and a baseline that recorded coordinates would report layout
churn as scope change. A frozen baseline re-opened later renders with today's positions for
surviving objects and auto-layout for the rest (A-52). A picture that must be kept is a PNG export
attached to the sign-off.

**Soft delete: a documented deviation.** `DIAGRAM_LAYOUT` is **hard-deleted and carries no
`is_active` / `deleted_at` / `deleted_by` / `row_version`**, recorded in
`docs/PLAYBOOK_DEVIATIONS.md`. It is referenced by nothing and copied into no baseline, and a
retired coordinate has no evidential value. Soft delete would push the natural key into a
partial index and turn every "reset layout" into a pile of dead rows. Last write wins per
object (A-52), so a version column would only manufacture 409s over a dragged box. The positioned
objects themselves are soft-deleted as usual. Their layout rows stay, so a restored entity
returns to where it was. Objects with no row are auto-laid-out by the frontend.

*Not modelled, and worth knowing:* lane order, edge waypoints and zoom. Lanes derive from the
`R` role (A-46), so dragging a step between lanes is not a layout change. It would be a change
of performer.

#### Baselines (area 6)

**BASELINE** — one row per frozen version of one project's scope. PK `baseline_id`; FK `project_id`, `status_code_id`, `frozen_by_user_id`, `prior_baseline_id` (self, nullable — gives you a default diff target and a lineage chain). UK `(project_id, version_label)`. `frozen_at` is set once; the whole row and all its children become read-only after that (enforced by a `BEFORE UPDATE` trigger on the snapshot tables, or simply by never exposing a write route — I recommend the trigger, because "immutable" that depends on application discipline is not immutable).

**BASELINE_* (shadow tables)** — one row per live row as it stood at freeze time. PK: own surrogate. FKs: `baseline_id`, `source_<x>_id` → the live row, and intra-baseline FKs to sibling snapshot rows (`baseline_parent_node_id`, `baseline_br_id`, `baseline_data_entity_id`). UK `(baseline_id, source_<x>_id)`.

Two details that make diffing cheap:
- **`source_*_id` is the stable pointer** you asked for. A full outer join between two baselines on `source_id` yields added (right only) / removed (left only) / present-in-both, and `content_hash` inequality among the both-rows yields *changed* without comparing every column. `content_hash` is `sha256` over the concatenated business columns, computed at freeze.
- **Snapshot rows store resolved labels, not code FKs** (`status_label` not `status_code_id`). A baseline must survive someone renaming or deleting a `code_master` row afterwards. This is a deliberate, documented denormalization — see §4.

I show five shadow tables in the diagram. The full recommended set is nine: `BFC_NODE`, `BFC_NODE_DATA_ENTITY`, `BFC_NODE_ORG_ROLE`, `DATA_ENTITY`, `DATA_FIELD`, `BUSINESS_REQUIREMENT`, `BR_DATA_ENTITY`, `FUNCTION_REQUIREMENT`, `FR_BR`, `ISSUE`, `ISSUE_BR` (eleven if you count the link tables separately). **[RESOLVED — D-3: Ben accepted this recommendation. The freeze covers DE, Data Field, FR, Solution and their links as well. The full shadow set is in §6.1.]** `apple`'s original argument follows. **Your spec says the freeze covers BFC + BR + Issue only. I recommend extending it to DATA_ENTITY / DATA_FIELD / FUNCTION_REQUIREMENT** — a baselined BR that points at "DE-0007" is not a scope record if DE-0007's name and field list can change underneath it. Scope control on an implementation project is argued in terms of *what data the system must hold*, so the DE layer is the part a vendor will dispute. Flagged as a decision, not taken unilaterally.

#### Bulk import staging (D-5, D-25, D-28)

**IMPORT_BATCH** — one row per uploaded file awaiting validation, review and commit. PK
`import_batch_id`; FK `project_id`, `uploaded_by_user_id`, `status_code_id` (`IMPORT_STATUS`),
and **`anchor_bfc_node_id`** (nullable): the process-flow file's `parent`, the node the flow is
drawn for, which must not be a process (checked by the service at validate and again at commit).
Columns added for D-25 / D-28:
- `target_entity CHECK (target_entity IN ('ISSUE','DATA_ENTITY','DATA_FIELD',
  'BUSINESS_REQUIREMENT','FUNCTION_REQUIREMENT','PROCESS_FLOW','WBS_ITEM'))`. BR and FR are D-28,
  PROCESS_FLOW is D-25, and WBS_ITEM is D-33.
- `source_format varchar(40) NOT NULL DEFAULT 'xlsx'`. It holds the file's declared format,
  e.g. `'vb-process-flow/1.0'`, with `CHECK ((target_entity = 'PROCESS_FLOW') = (source_format
  LIKE 'vb-process-flow/%'))`. Which versions are *supported* is a service registry, not a CHECK,
  so that a 1.1 schema is a code change, not a migration.
- `import_mode varchar(10) NULL CHECK (import_mode IN ('MERGE','REPLACE'))`, with
  `CHECK ((target_entity IN ('PROCESS_FLOW','WBS_ITEM')) = (import_mode IS NOT NULL))` (D-33) and `CHECK
  ((target_entity = 'PROCESS_FLOW') = (anchor_bfc_node_id IS NOT NULL))`.
- `warning_count int NOT NULL DEFAULT 0`: warnings are counted separately from `error_count`.
  Errors block the commit; warnings inform it.
- `insert_count`, `update_count` (already used by §7.11, missing from §5.2), and `retire_count`,
  the edges and I/O (or, for WBS, the lines) a REPLACE-mode commit would retire. It is what the consultant acknowledges.

**IMPORT_ROW** — one row per staged sheet row **or staged JSON object**. PK `import_row_id`; FK
`import_batch_id`. A process-flow file is flattened into one row per object, so the preview and
the verdicts work per object:
- `row_kind varchar(30) NOT NULL`. For a sheet it equals `target_entity`. For a flow file it is
  `STEP`, `STEP_IO`, `STEP_ROLE` (a lane assignment), `FLOW_EDGE`, `EXTERNAL_ENTITY`,
  `EXTERNAL_FLOW`, `DATA_ENTITY` or `LANE` (resolution only), under a CHECK over the union.
- Locator: `sheet_row_no` becomes nullable, `source_path varchar(200) NULL` holds the JSON
  Pointer (`/steps/3/inputs/0`), and `CHECK (num_nonnulls(sheet_row_no, source_path) = 1)`.
- `local_key varchar(50) NULL` is the file-local key (`S1`, `D1`, `X1`) that edges and I/O refer
  to, with partial `UNIQUE (import_batch_id, row_kind, local_key) WHERE local_key IS NOT NULL`,
  so a duplicate key in the file is a staging error, not a silent overwrite.
- `source_ref varchar(200) NULL`: the author's provenance ("slide 4, shape 12"), kept verbatim so
  a human can check an AI conversion (§7.2b rule 6).
- `verdict varchar(10) NOT NULL CHECK (verdict IN ('INSERT','UPDATE','MATCH','RETIRE','KEPT'))`.
  `KEPT` (round 2) marks a step I/O row a replace-mode flow import would have retired, kept
  because a BR CRUD or an external flow depends on it (§7.2b).
  `RETIRE` rows are staged from the database in REPLACE mode, so the preview can list what
  would go.
- `error_detail jsonb NOT NULL DEFAULT '[]'` (was `text`) and `warning_detail jsonb NOT NULL
  DEFAULT '[]'`, with `CHECK (is_valid = (jsonb_array_length(error_detail) = 0))`, so validity
  cannot disagree with the errors recorded.
- `committed_target_id` stays an untyped pointer, because staging is forensic. `row_kind` says
  which table it points at, and it stays NULL for composite-key targets (`STEP_IO`, `STEP_ROLE`),
  whose key is in `payload`.

No new business table: every flow-file object lands in a table D-20…D-24a already defined.

**Round 2 and D-33 additions to staging.**
- **`WBS_ITEM` is a sixth sheet target** (D-33): `target_entity` and `row_kind` gain
  `'WBS_ITEM'`. `business_key` holds the Unique ID as text. The MS Project → Excel export is
  one column map, not a new pipeline. **`import_mode` now applies to two targets:** `CHECK
  ((target_entity IN ('PROCESS_FLOW','WBS_ITEM')) = (import_mode IS NOT NULL))`. Lines missing
  from a WBS file are retired only in REPLACE mode, counted in `retire_count` and acknowledged
  (the D-25 rule). `anchor_bfc_node_id` stays PROCESS_FLOW-only.
- **BR number is the business key for BR and STEP rows (R2-D1).** `business_key` holds
  `BR-0042`. **`cross_check_key varchar(100) NULL`** is new and holds the file's `hier_code`
  (for WBS, its WBS code). It is compared after resolution and never used to resolve. Partial
  **`UNIQUE (import_batch_id, row_kind, business_key) WHERE business_key IS NOT NULL`**: a file
  naming the same BR, issue, DE or Unique ID twice is a staging error, not two updates of one
  row.
- **Retention (Q14):** `import_row` rows are **deleted** 90 days after `import_batch.uploaded_at`
  by a scheduled purge. **`IMPORT_BATCH.rows_purged_at timestamptz NULL`** records that the
  detail is gone. The batch header (who, when, which file name, counts, status) is **kept** as
  the import audit trail, and `WBS_ITEM.last_import_batch_id` points at it. This is one of the
  two places the application role may DELETE (§6.6), and it closes A-32's "90 days" as Ben's
  decision rather than mine.

#### Identity (area 7)

**APP_USER** — one row per **FTC staff member** who can log into Value Bridge (D-11). PK `app_user_id`; UK `lower(email)` (functional unique index — case-insensitive email is not optional). `password_hash varchar(255) NOT NULL` — column named, bcrypt/argon2 output, never logged, never serialized by any Pydantic response model. **`is_platform_admin boolean NOT NULL DEFAULT false`** is the whole of the global tier (D-9): true means the user sees every project; false means the user sees exactly what their one active `USER_ACCESS_GRANT` opens (a project,
or every active project of a program) and nothing else.

*(The `APP_ROLE` table described here has been **deleted** — D-9, finding S1. It held Admin / Consultant / Client Reviewer while the service pseudocode used OWNER / EDITOR / VIEWER, which is the two-vocabulary defect the auditor rated HIGH. One boolean plus one per-project code replaces it, and `CLIENT_REVIEWER` no longer exists anywhere in the model, which closes S8 structurally rather than by a gate.)*

**USER_ACCESS_GRANT** *(was `USER_PROJECT_ACCESS`; D-32, R2-S2, R2-S4)* — one row per grant of
one project role to one user over **one scope: a single project, or a single program**. The
rename is deliberate: the row no longer always names a project. PK
`user_access_grant_id` (a surrogate, because both scope columns are nullable); FK
`app_user_id NOT NULL`, `project_id NULL`, `program_id NULL`, `project_role_code_id NOT NULL`
(→ `PROJECT_ROLE`: OWNER / EDITOR / REVIEWER, D-9), `granted_by_user_id`, plus `granted_at`
and §5.1 (`is_active` = live grant, `deleted_at` / `deleted_by` = revoked at / by,
`row_version`).

- **`CHECK (num_nonnulls(project_id, program_id) = 1)`**: a grant names exactly one scope.
- **Partial `UNIQUE (app_user_id) WHERE is_active`**: **at most one live grant per user**
  (D-32: "nobody holds grants to two unrelated projects"). Only a platform admin spans
  unrelated projects (Q10), and an admin needs no grant at all (A-67).
- **One role over the whole scope (Q10).** A program grant gives the same role on every
  project in the program, including projects added later.
- **Program-derived access is computed, never stored.** `visible_project_ids` returns the grant's
  project, or every active project whose `program_id` is the grant's program, per request. A
  stored user × project expansion would go stale the moment a project joined the program,
  which D-32 says must take effect immediately.
- **Live scope only:** `scope_is_active boolean GENERATED ALWAYS AS (CASE WHEN is_active THEN
  TRUE END) STORED` + FK `(project_id, scope_is_active) → PROJECT(project_id, is_active)` and FK
  `(program_id, scope_is_active) → PROGRAM(program_id, is_active)`, both ON UPDATE NO ACTION,
  beside the plain FKs. The NULL scope column skips its FK under MATCH SIMPLE, so one generated
  column serves both. Granting on a retired project or program is refused. So is retiring
  either while a live grant names it (Q4).
- **Scope is immutable; role is not.** Moving a user to another scope is revoke plus a new
  grant in one transaction, by a platform admin. A role change updates in place under
  `row_version`, audited old → new. The table is thus the history of who could see what, and
  since the application role cannot DELETE from it (§6.6), that history cannot be erased.

Why one table with a XOR, not `USER_PROJECT_GRANT` + `USER_PROGRAM_GRANT`: "at most one active
grant per user" would then span two tables, and that is not declarable. With one table it is a
single partial index. That argument is decisive.

**AUDIT_EVENT** — one row per security- or scope-significant event. PK `audit_event_id`; FK `app_user_id`, `project_id` (nullable — a failed login has no project). `event_type` is a plain varchar, **not** a code_master FK: audit rows must be writable even if the lookup table is mid-migration, and an unknown event type should be recorded, not rejected. `detail jsonb` holds the variable payload. This is the one place JSONB earns its keep, because there is no diffing or reporting requirement on it — it is forensic.

---

### 5.4 The judgment calls, and how they were decided

#### 5.4.1 BR grain — **separate table, 1:N from the L5 node. Recommended.**

One row per discrete business requirement within a level-5 BFC node, as proposed. I am confirming it, and here is what actually decides it.

*What breaks if you collapse BR into BFC_NODE:*

- A BR is referenced by two other things — `ISSUE_BR` and `FR_BR`. Collapse it and those links must point at `bfc_node_id`, which means the FK no longer says "this issue is about this requirement", it says "this issue is about this process step". That is a genuine loss of meaning, and it is irreversible once the data exists: you cannot later split one node's two requirements apart and know which issues belonged to which.
- It forces a **level-dependent column set** onto a table whose key is a node of any level. `br_number`, `br_statement`, `business_logic` and `status_code_id` would be non-null only for L5 rows. Formally this is fine in 3NF (they still depend on `bfc_node_id`), but it is the same smell that 3NF is trying to prevent: a single relation holding two different kinds of fact. Practically it means every BR query is `WHERE level_no = 5 AND br_statement IS NOT NULL`, and every BR list screen is a filtered node list.
- It hard-codes 1:1 forever. Your own note says "commonly 1:1 in practice" — *commonly*, not always. The first time a consultant hits an L5 step with two distinct rules ("validate the claim" and "route the claim"), the only escapes are to invent a fake L5 sibling node (corrupting the process hierarchy to store a requirement) or to cram both rules into one text field (destroying the grid). Both are worse than a join.
- It breaks the numbering. `BR-0042` and the node's `01.02.03.04.05` are different identifier systems with different lifecycles — the BR number must survive a node being re-sequenced.

*What breaks with the separate table (be honest about it):*

- Every BR screen is a join. Mitigated: the join is on an indexed FK and the BFC context you need (`hier_code`, `node_name`) is one row.
- You can create an L5 node with no BR. **Do not enforce this with a `NOT NULL` you cannot express** (a mandatory child is not declarable in SQL without deferred constraints and pain). Handle it in the service layer: creating an L5 node auto-creates BR seq 1 in the same transaction, so the 1:1 common case costs the user nothing, and a "L5 nodes without requirements" completeness report covers the rest. That completeness report is itself a deliverable FTC will want.
- Two levels of numbering to explain to the client. Real, but small.

The deciding argument in one line: **a BR has its own identity, its own lifecycle, and its own inbound references (issues, FRs). Things with inbound references are entities, not columns.**

#### 5.4.1a Override — D-2: one BR per L5 node

**Ben's call, taken after reading the above: L5 is the lowest level of process and carries
exactly one business requirement.** One BR may still have many Function Requirements, via
Solutions.

`apple` argued for 1:N and I put her case; Ben held. Recorded rather than argued again.

**What the model does with that, and why it is not a collapse into `bfc_node`:**

`BUSINESS_REQUIREMENT` stays its own table, with `UNIQUE (bfc_node_id)` enforcing the 1:1.
It is not folded into `bfc_node` as extra columns, for the three reasons above that survive
the cardinality change unaltered:

- Issues and Solutions point at `br_id`. That FK means "about this requirement", and it
  keeps meaning that.
- `br_number` (`BR-0001`) and `hier_code` (`01.02.03.04.05`) are different identifier
  systems with different lifecycles. The BR number must survive the node being reordered.
- Collapsing would put `br_number`, `br_statement`, `business_logic` and `status_code_id`
  on a table keyed by a node of any level, non-null only for L5. Every BR query becomes
  `WHERE level_no = 5 AND br_statement IS NOT NULL`.

**So the reversal cost is one dropped index.** If an L5 step ever turns out to need two
requirements, `DROP the UNIQUE constraint` and the model is already 1:N — no migration, no
data repair, no lost history. That is the whole reason to spend a table on it. The
alternative, inventing a fake L5 sibling node to hold a second requirement, would corrupt
the process hierarchy to store a requirement, and it is the outcome this shape prevents.

**Service consequence:** `create_bfc_node` at level 5 creates its BR in the same
transaction (§7.2). The consultant never creates a BR by hand; they edit the one that
appeared with the step.

> **Restated by D-23 (2026-09-28).** "L5" above now reads **"process node"**: the lowest node of
> its branch, at L3, L4 or L5. The 1:1 is unchanged, and so is the reversal cost (drop the
> partial unique index). What changed is the guard. The literal `bfc_level_no = 5` became a
> generated `node_is_process` guard against `bfc_node.is_process`, and the BR now appears when
> a node is **created as, or promoted to,** a process (`create_node` / `mark_process`). The
> history above is left as written.

#### 5.4.2 BR ↔ Data Entity — **one associative table, CRUD as the stored axis, direction generated.**

Not two relationships. Two tables (`BR_INPUT_DE` and `BR_OUTPUT_DE`) would be structurally identical, differing only in a value — the textbook definition of data-as-schema. Every query that wants "all DE touches for this BR" becomes a UNION, and adding a third direction later (a genuine possibility: "reference / lookup only") is a migration.

The non-obvious part is the interaction between direction and CRUD, and it is a **3NF issue**. If you store both, you store a functional dependency inside a row: `R → INPUT`, and `C, U, D → OUTPUT`. `crud_code` determines `direction_code`; `direction_code` is a non-key attribute determined by another non-key attribute. Storing both invites exactly one class of bug — a row that says `(R, OUTPUT)` — and no amount of UI discipline prevents it forever.

Recommendation:

- PK `(br_id, data_entity_id, crud_code_id)`. CRUD is in the key because one BR legitimately reads *and* updates the same entity — that is the single most common pattern in the grid ("read the customer record, update the status").
- `direction` is a **PostgreSQL generated column**: `GENERATED ALWAYS AS (CASE WHEN crud_code = 'R' THEN 'I' ELSE 'O' END) STORED`. The UI and API can filter and group on direction exactly as if it were stored; it is indexable; it cannot drift. To make this work, `crud_code` must be a real char column, so either denormalize the letter alongside the code_master FK or — my preference — **do not put CRUD in code_master at all**. C/R/U/D is not client-configurable; it is a closed four-value vocabulary. A `char(1) CHECK (crud_code IN ('C','R','U','D'))` is honest and lets the generated column work. I drew the code_master FK in the diagram to match your brief, but this is my recommendation: **CRUD is a CHECK, not a lookup.**
- If the FD ever breaks — someone insists on an entity that is Read but classified as an output-side reference — then you store both columns independently and accept the denormalization with a documented reason. Ask the question before building; it is a five-minute conversation now and a data migration later.

Same pattern applies to `BFC_NODE_DATA_ENTITY`, except there CRUD is not required (the L5 node states *that* data flows, the BR states *how*), so direction is the stored key column there. That asymmetry is intentional and worth documenting in the app: **the node says what flows, the BR says what is done to it.**

**D-24 turns that asymmetry into a rule: the node licenses the BR.** A BR CRUD row is legal only if
the BR's own process step has the matching I/O row: an **input** for R, an **output** for C/U/D.
This is enforced by construction, with no trigger:

```
BR_DATA_ENTITY (bfc_node_id, data_entity_id, direction, io_is_active)
   → BFC_NODE_DATA_ENTITY (bfc_node_id, data_entity_id, direction, is_active)

bfc_node_id   copied from the BR, verified by FK (br_id, project_id, bfc_node_id) → BR
direction     GENERATED from crud_code        (already true, §5.4.2)
io_is_active  GENERATED: TRUE if active, else NULL
```

**Feasible, and here is what it costs:**
- **One redundant column** (`BR_DATA_ENTITY.bfc_node_id`). It is transitive through `br_id`,
  which is the same denormalization as `project_id` everywhere, and it is made safe the same way,
  by a composite FK (§5.5).
- **The service creates the step I/O row in the same transaction** as the CRUD (or restores it if
  it was retired), *before* inserting the CRUD. This is `business_requirement.link_data_entity`
  in Lilly's §7.3. The consultant never sees a refusal on the BR screen.
- **Retiring a step I/O row is refused while an active BR CRUD depends on it.** A soft delete
  changes `is_active`, which is part of the referenced key, so NO ACTION fires. The service
  pre-checks so that it can return a 409 that *names* the BR and CRUD, rather than a bare FK
  error. The flow editor offers "remove the BR's Read too".
- **Why `is_active` is in the target key.** The PK alone includes retired rows, so a plain FK to
  it would be satisfied by a dead I/O row and would never block the retire. This is the
  point that makes D-24 enforceable rather than decorative.
- **Import order is fixed:** step I/O before BR CRUD. `commit_process_flow_json` already writes in
  that order.
- **The converse is not a rule.** A step I/O with no BR CRUD is legal: the step says data flows
  before the requirement says what is done to it. `flow_completeness_report.crud_without_io`
  should always be 0, and it stays as a proof.
- *Fallback on a PostgreSQL build that refuses generated columns in an FK:* plain columns
  maintained by the service, with a `CHECK` equating each to its expression. The declarative
  property is unchanged.

#### 5.4.3 FR cardinality — **M:N to BR (confirmed), and M:N to BFC_NODE with a caveat.**

FR↔BR is unambiguously many-to-many and the brief already suspected it: one FORM serves several BRs; one BR may need a FORM plus a BATCH plus an INTERFACE. `FR_BR` with PK `(fr_id, br_id)` and a `coverage_note` for the relationship-specific fact ("this FR covers only the validation half of BR-0042"). That note is the proof the junction is a real entity, not just a link.

FR↔BFC_NODE is the one to be careful about. Keep it, but understand what it means: **it is not a second path to the same fact.** If an FR is linked to BR-0042, and BR-0042 lives on node `01.02.03.04.05`, then FR→node is already derivable. Storing it again as a direct row is a transitive redundancy and the two will disagree.

Recommendation: `FR_BFC_NODE` exists **only** for coverage that is not expressed through a BR — typically an FR attached to an L1–L4 node ("a dashboard for the whole of Order Management") or to an L5 node whose BRs are not written yet. Add `CHECK` documentation and an application rule: when an FR is linked to a BR, do not also write the BR's own node into `FR_BFC_NODE`. Compute "effective BFC coverage" in a view as the UNION of the direct links and the links derived through `FR_BR → BUSINESS_REQUIREMENT.bfc_node_id`. If you would rather have one path and no rule to remember, drop `FR_BFC_NODE` entirely and require every FR to hang off at least one BR — cleaner model, less flexible during early discovery. I recommend keeping it for MVP because discovery-phase FRs genuinely precede BRs, but I want the redundancy rule written down.

> **Override — D-7 (Lilly).** `FR_BR` **no longer exists.** With `SOLUTION` inserted between
> BR and FR, an FR belongs to exactly one Solution (`FUNCTION_REQUIREMENT.solution_id`,
> mandatory), and a Solution answers many BRs through `BR_SOLUTION`. BR → FR is therefore
> derived, exposed as the view `v_br_function_requirement`.
>
> `apple`'s reasoning above is *why* this shape is right, not an argument against it: she
> objects to storing a fact that is already derivable, and `FR_BR` alongside
> `BR_SOLUTION → SOLUTION → FR` would be exactly that. Her M:N conclusion is preserved —
> one FORM can still serve several BRs, because its Solution can. What changed is which
> table carries it.
>
> `FR_BFC_NODE` survives on her reasoning, unchanged: discovery-phase FRs and L1–L4
> coverage ("a dashboard for the whole of Order Management") genuinely precede both BRs and
> Solutions. The redundancy rule she asks for is written down as a service guard in §7.5.

> **D-28 (2026-09-28) relaxes "mandatory".** `solution_id` is nullable: an FR may arrive before
> its Solution, and so has no BR path. It is a warning, not an error. `v_br_function_requirement`
> is unaffected, because an inner join from `BR_SOLUTION` simply does not reach an unlinked FR,
> which is the correct answer to "which FRs serve this BR". Knock-ons: (1) `effort_summary` by
> solution and by phase gains an **UNASSIGNED** bucket, so man-days are never dropped from a
> total. (2) `priced_diff` must also sum FR-level changes directly from
> `baseline_function_requirement`, de-duplicated by `source_fr_id`, or unlinked FRs go unpriced.
> (3) `analyse_cr_impact` must accept an FR as a seed, because the BR → Solution → FR walk
> cannot reach one. (4) `FR_BFC_NODE`'s reachability guard is vacuous for an unlinked FR, so any
> node may be linked. That is the discovery-phase use it was kept for. (5) `value_ranking`
> reports unlinked effort separately, since it has no benefit to divide by. (6) An unlinked
> FR has no inherited application (A-27). An interface FR still states its endpoints in
> `FR_INTERFACE`, which is a different fact from the delivering application.

**ISSUE ↔ BR: many-to-many, confirmed.** One issue ("the source system has no customer credit field") plausibly blocks six requirements; one requirement plausibly has several open issues. A 1:N model would force the consultant to duplicate the issue six times — six issue numbers, six resolutions to keep in sync, and a resolution rate report that lies. The junction costs one table. The optional side matters too: an issue with zero BR links is valid (project-level), which is why `ISSUE.project_id` is the mandatory anchor and `ISSUE_BR` is `0..N`.

#### 5.4.4 Snapshot storage — **typed shadow tables. Strongly recommended over JSONB.**

The whole point of a baseline in scope control is the **diff**. Everything else follows from that.

*Diffability.* With shadow tables, "what changed between v1.0 and v1.1" is one SQL statement per entity:

```
FULL OUTER JOIN ON source_br_id, compare content_hash
→ added / removed / changed, with the changed columns available by name
```
It runs in the database, it is indexable, and it produces a result set the React table renders directly. With JSONB you fetch two blobs, deserialize both in Python, walk them with a recursive dict-diff, and hand-write the ordering, the field labels and the "this is a list, match by id" logic. That diff engine is a few hundred lines of code you now own and test, versus a query you can read. The diff is the product feature; put it where it is cheapest.

*Query cost.* Shadow tables index and join. "Show every baseline in which BR-0042 appeared, with its statement at each freeze" is a trivial indexed query. In JSONB it is a `jsonb_path_query` over every baseline blob in the project — a full scan of large documents, with GIN indexes that help containment but not the projection. Client Reviewers *will* ask to see a specific requirement's history.

*Schema drift.* This is the argument usually made *for* JSONB — "the shadow table breaks when I add a column to BR". I think it points the other way. With shadow tables, adding a column to `BUSINESS_REQUIREMENT` and forgetting the shadow is caught by a test (assert the shadow's column set matches the live table's, minus audit columns, plus snapshot columns — twenty lines of SQLAlchemy introspection in CI). The failure is loud, at build time, once. With JSONB the snapshot silently starts containing a new key from the day of the deploy, old baselines don't have it, and the diff engine has to decide whether "key absent in v1.0, present in v1.1" means *added field* or *schema changed* — and it cannot tell. **JSONB does not eliminate schema drift; it eliminates the error message.** For a scope-control artefact that may be quoted in a commercial dispute, a silently-shifting record is the worst possible property.

*The real cost, stated plainly.* Roughly nine to eleven extra tables, a `SnapshotMixin`, and one freeze service that inserts them in FK order. It is an afternoon of work and it is mechanical. Mitigations: generate the shadow models from the live models, and cover the whole thing with the column-parity test above.

*What I would concede:* if you later add attachments or rich-text blocks whose structure you genuinely do not control, snapshot those as JSONB *columns inside the typed shadow row*. Hybrid at the column level, never at the table level. And I would **not** add a redundant JSONB payload alongside the typed columns "just in case" — two representations of the same fact in one row is a 1NF-adjacent sin and they will diverge.

*One more property to build in now:* snapshot rows resolve `code_master` FKs to **the code and its label**, both copied (§4). **The code is what `content_hash` reads; the label is display only** (R2-D3, §7.7), so a relabel in `code_master` never makes a frozen row read CHANGED. Every `*_label` column in a `baseline_*` table has its `*_code` beside it. And snapshot FKs point to live rows with `ON DELETE NO ACTION`. Since the model soft-deletes and never hard-deletes, these FKs are safe. If hard delete is ever introduced, `source_*_id` must degrade to an unconstrained `bigint` pointer — note that in the migration policy so nobody adds a cascade later and silently shreds a frozen baseline.

#### 5.4.5 RACI on role links — **yes, recommended, on both link tables, with one enforced Accountable.**

Adopt it. The reasoning is that you are already going to need it and the alternative encodings are worse.

Without a participation type, `BFC_NODE_ORG_ROLE` says only "this role is involved in this step" — which is close to useless for the deliverable FTC actually produces. The moment someone asks "who signs off this process?" you need the distinction, and the two ways to get it without RACI are both bad: a boolean `is_primary` (which is RACI with one bit and no vocabulary), or a separate `accountable_org_role_id` FK on the parent row alongside the junction for everyone else (which puts accountability in two places — a redundancy that will disagree).

So: PK `(bfc_node_id, org_role_id, raci_code_id)` and `(br_id, org_role_id, raci_code_id)`. Participation type in `code_master` under category `RACI_TYPE` — this one *is* client-configurable, because plenty of clients use RASCI, RAPID or a house variant, and the model should not care.

Enforce **exactly one Accountable** per node and per BR: partial unique index on `(br_id) WHERE raci_code = 'A'` gives you "at most one" declaratively; "at least one" is a completeness report, not a constraint (you cannot require a child row at insert time, and you don't want to block a consultant mid-draft). Your spec says a BR links to "the Org Unit / Role accountable for it", singular — that singular is exactly the `A` row, and this model gives it to you without a second column.

Note the diagram marks `BUSINESS_REQUIREMENT ||--|{ BR_ORG_ROLE` (one-or-many) to express the intent that every BR ends up with at least an Accountable. If you want the DB to permit drafts with no role at all, it is `||--o{` and the rule lives in the completeness report. I would ship `o{` and report on it.

Org Unit linkage is deliberately **indirect**: BFC nodes and BRs link to `ORG_ROLE`, and the org unit comes via `ORG_ROLE.org_unit_id`. Adding a direct `org_unit_id` to those junctions would be a transitive dependency (§4) and would let the two disagree after a role is moved between units.

> **Q7 (2026-09-28): the rule keys on behaviour, not the letter.** "One Accountable" is now
> `WHERE is_active AND raci_behaviour = 'ACCOUNTABLE'` on **both** link tables, and lanes read
> `RESPONSIBLE` (A-46). RACI and RASCI are supported now. RAPID is a seeded mapping onto the
> six behaviours. A client letter set is free to change, and the rules are not (§5.3
> CODE_MASTER). The partial index above was never expressible as written (`raci_code` is an FK,
> R2-D11). The behaviour copy is what makes it real.

#### 5.4.6 DE number generation under concurrency

Two mechanisms, and the distinction matters:

- **Uniqueness is guaranteed by the constraint**, `UNIQUE (project_id, de_number)`. Not by the generator. Any generator bug produces an error, never a duplicate. This is the part that must never be negotiable.
- **Allocation** uses `PROJECT_SEQUENCE`: in the same transaction as the insert, `UPDATE project_sequence SET last_value = last_value + 1 WHERE project_id = :e AND sequence_code = 'DE' RETURNING last_value`, then format `prefix || lpad(last_value::text, pad_width, '0')` → `DE-0001`. The `UPDATE` takes a row lock on one row, so it serializes only concurrent DE creations *within the same project* — other projects and other series are unaffected. At FTC's concurrency (a handful of consultants per project) the lock is held for microseconds and contention is irrelevant.

Do **not** use `MAX(de_number) + 1` (races under read-committed, and breaks against soft-deleted rows), and do not use a real PostgreSQL `SEQUENCE` per project (DDL at runtime, unmanageable in Alembic, and a migration nightmare).

Gaps: a rolled-back transaction consumes a number. You specified gap-tolerant, so this is correct behaviour, and it is the *right* behaviour — closing gaps means renumbering, and renumbering breaks every document, email and meeting minute that ever cited `DE-0007`. Make "numbers are permanent and may have gaps" an explicit, user-visible rule in the app.

The `PROJECT_SEQUENCE` row also carries `prefix` and `pad_width`, so a client who wants `ENT-001` instead of `DE-0001` is a data change. Same table serves BR, FR and ISSUE numbering.

#### 5.4.7 The process rule (D-23) — **stored flag, parent-side guard, all generated. Recommended as proposed, with three corrections.**

"Level 5" was a literal in the row. "The lowest node in its branch" is a fact about other rows,
which a CHECK cannot see. Ben's proposed mechanism keeps it declarative by storing the fact
(`is_process`) and making every dependent assert it through the composite-FK trick. I confirm it,
with three corrections:

1. **Guards must be NULL on inactive rows** (`GENERATED … CASE WHEN is_active THEN … END`).
   With a `NOT NULL DEFAULT` literal, a soft-deleted child or retired BR blocks promotion or
   demotion forever, and "nothing is ever truly gone" (§5.6) becomes "nothing can ever change".
   Existence and tenancy stay on a separate always-on `(id, project_id)` FK.
2. **`ON UPDATE NO ACTION`, never CASCADE,** on every process guard. The refusal *is* the
   rule. PostgreSQL will not create a cascading FK into a generated column, so the DDL cannot
   drift into it by accident.
3. **Demotion needs every step fact retired, not only the BR.** The DB enforces this because
   every dependent is guarded. I think that is right, because I/O, lanes and edges on a node that
   now has children would describe the children's work a second time. The service does it in
   one previewed transaction.

Two CHECKs make the flag honest: `level_no >= 3` for a process (A-47), and `level_no < 5 OR
is_process` (an L5 cannot have children, A-54). What stays *outside* the DB: "every leaf is a
process" (a leaf may still be mid-draft, so it is reported by `consistency_check` as
`leaf_not_process`), and "every process has an active BR" (a mandatory child, so it is
service-guaranteed and reported).

**Tables carrying the guard: seven, plus `bfc_node` itself.** They are `business_requirement`,
`bfc_node_data_entity`, `bfc_node_org_role`, `bfc_node_flow` (×2),
`application_bfc_node` (new pin), `bfc_node_external_flow` (new table), and the parent guard on
`bfc_node`. **Not guarded, deliberately:** `fr_bfc_node` (coverage at any level, §5.4.3),
`risk.bfc_node_id` (a risk may sit on a whole area), `diagram_layout.scope_bfc_node_id` (a flow
is drawn *for* a non-process node).

#### 5.4.8 FR type behaviour and the interface subtype (D-27) — **a behaviour column on the code, a verified copy on the FR, a guard on the subtype.**

The least invasive option that stays declarative is one nullable column,
`code_master.behaviour_code`, CHECK-listed and legal only on `FR_TYPE` rows. The chain is:

```
FR_INTERFACE (fr_id, project_id, fr_type_behaviour = 'INTERFACE' when active)
   → FUNCTION_REQUIREMENT (fr_id, project_id, fr_type_behaviour)                     NO ACTION
FUNCTION_REQUIREMENT (fr_type_code_id, fr_type_category = 'FR_TYPE', fr_type_behaviour)
   → CODE_MASTER (code_id, category, behaviour_code)                                NO ACTION
```

What each rule then costs:
- **An FR_INTERFACE row under a non-interface FR** is impossible to store.
- **Retyping an FR from an interface type to a FORM type** while its interface detail is active
  is refused by the DB. Lilly's `change_fr_type` 409 is the friendly message in front of it.
- **Changing a type's behaviour** is refused while any FR uses the type (Q6; was CASCADE,
  changed by round 2). A behaviour is immutable once referenced (§5.4.13).
- **A mistyped code FK** (an `fr_type_code_id` pointing at an ISSUE_SEVERITY or a RACI_TYPE row)
  is impossible, because the FK carries the category.

The cost is two extra columns and three unique keys. The alternative, "service rule plus a
`consistency_check` line", is what I would have accepted if the chain did not close. It closes,
so the `FR_INTERFACE rows under a non-interface type` check in §4.7 becomes a proof that returns 0.

#### 5.4.9 External flows (D-24a) — **surrogate key because the DE is optional; licensed by step I/O when it is not.**

A nullable data entity in the grain means the natural key cannot be the PK. It becomes a
surrogate plus a `NULLS NOT DISTINCT` unique. The decision that matters is the FK to step I/O
when a DE is named. Without it, a DFD could show "Customer → Sales order → Receive order" while
the process flow says Receive order has no inputs, which is the two-truths problem D-24 was
decided to prevent. The cost is the same as for BR CRUD: the service writes the I/O row
first, in the same transaction.

#### 5.4.10 Diagram layout (D-29, D-30) — **typed object FKs, scope in the key, hard-deleted, never baselined.**

The typed-FK choice follows the CR_IMPACT ruling. The hard-delete deviation and not-baselined
rule are justified in the entity note (§5.3). One consequence to state: layout is the only
business-facing table in the model whose history is not kept, and that is deliberate.

#### 5.4.11 Program and access (D-32) — **one grant table, scope = project XOR program, derived access computed. Recommended.**

Three shapes were possible. (a) Keep user × project and *expand* a program grant into one row
per project. That is stored derived data: it goes stale when a project joins, and "at most one
grant" becomes "at most one grant or one program's worth of grants", which cannot be declared.
(b) Two grant tables. The one-grant rule would span them, so it could not be declared either.
(c) **One table, XOR scope, partial unique on the user.** Only (c) states Ben's rule in the
database. It also keeps `access.visible_project_ids` the single entry point (§7.8): one lookup,
then either an id or a program's active projects.

The project ↔ program link carries two rules the DB enforces by composite FK: *same client*
and *live program*. The one it cannot enforce is *who may change it* (platform admin, Q10).
That stays with the service and the audit. Program retirement, grant retirement and project
retirement all interlock through generated `…_is_active` guards, so Q4's "refuse while live
dependents exist" is structural for the access layer, where a leak would matter most.

#### 5.4.12 WBS (D-33) — **imported read copy keyed by MS Project Unique ID; two VB-owned links; not baselined.**

One table with split ownership: MS Project owns the schedule columns and VB owns `phase_id` /
`solution_id`. I kept one table rather than a 1:0..1 link table because the links' only reader
is the same dashboard row. The split is carried by a rule instead: the import never writes the
links and never bumps `row_version`, and link edits do both. If a second VB-owned attribute ever
appears, split the table then.

#### 5.4.13 Behaviour is immutable once referenced (Q6, Q7, R2-D8, R2-D9) — **NO ACTION on the verified copy, category in the key.**

The composite FK that verifies the behaviour copy is also the immutability mechanism. With NO
ACTION, a referenced key cannot change. That one declaration replaces a trigger, a service guard
and a consistency line, and it covers RACI as well as FR types. CASCADE was delta 1's choice.
It is withdrawn for two reasons. A global code's cascade would rewrite every client's rows from
one admin action. And Ben's rule is that a used behaviour does not change.

#### 5.4.14 Flow-edge natural key (Q2, R2-D4) — **(from, to, normalised condition), partial, restore-before-insert.**

The reasoning is in the BFC_NODE_FLOW note (§5.3). The judgment was partial vs full: full
gives free `source_id` stability but turns every label edit into a possible collision with a
dead row. Partial plus a restore rule gets the same stability without that failure.

#### 5.4.15 Active rows under inactive parents (R2-D2, Q4) — **one declared list, three uses, service-enforced.**

Soft delete is an UPDATE, so a plain FK is satisfied by a retired parent, and the DB lets a
live child sit under a dead one. Only the FKs whose *target key includes `is_active`* refuse it
by construction. Those are listed in the right-hand column below as proofs. **The D-23 process
guards are not among them**: they key on `is_process`, which stays TRUE on a retired node.

The service holds **one declared list, `FK_LIVENESS`, generated from the SQLAlchemy FK metadata
minus the exclusions below**, and uses it three ways:
1. **Delete refused (Q4).** Retiring a row with live children in any listed FK returns 409 with
   the dependents named. The list is read in reverse.
2. **Restore refused (Q4).** Restoring a row whose listed parent is inactive returns 409. The
   list is read forward.
3. **Proof.** `consistency_check.active_under_inactive` returns (table, row, FK, parent)
   for each violation. It should always return 0, and it is a freeze precondition like the
   rest of `consistency_check`.

A CI test asserts that every FK in the metadata is either in `FK_LIVENESS` or on the
exclusion list, so a new FK cannot be silently unchecked. **Excluded, deliberately:** FKs to
`APP_USER` (a deactivated consultant's records stay valid); `project_id` (the check runs inside
a live project); `baseline_*` (immutable, and they point at history by design); `audit_event`,
`import_batch`, `import_row` (forensic); `diagram_layout` (hard-deleted, and a retired object
keeps its position on purpose, §5.3); and `function_requirement.suggested_br_id` (a hint, which
is cleared rather than blocking, §5.3 FUNCTION_REQUIREMENT).

Per frozen table (30), plus the live-only tables that have parents. "codes" means every
`*_code_id` FK on the row, because a retired code still referenced is the same defect.

| Table | FKs covered by `FK_LIVENESS` (child active ⇒ parent must be active) | Already DB-refused (proof only) |
|---|---|---|
| `org_unit` | `parent_org_unit_id`; codes | — |
| `org_role` | `org_unit_id` | — |
| `bfc_node` | `parent_bfc_node_id` | — *(parent guard checks process-ness, not liveness)* |
| `data_entity` | — | — |
| `data_field` | `data_entity_id`, `ref_data_entity_id`, `ref_data_field_id`; codes | — *(subsumes `orphan_fields`)* |
| `external_entity` | codes | — |
| `bfc_node_data_entity` | `bfc_node_id`, `data_entity_id` | — |
| `bfc_node_org_role` | `bfc_node_id`, `org_role_id`, `raci_code_id` | — |
| `bfc_node_flow` | `from_bfc_node_id`, `to_bfc_node_id`; codes | — |
| `bfc_node_external_flow` | `bfc_node_id`, `external_entity_id`, `data_entity_id` | the step-I/O licence (`io_is_active`) |
| `business_requirement` | `bfc_node_id`; codes | — |
| `br_data_entity` | `br_id`, `data_entity_id` | the step-I/O licence (`io_is_active`) |
| `br_org_role` | `br_id`, `org_role_id`, `raci_code_id` | — |
| `application` | codes | — |
| `solution` | codes | — |
| `br_solution` | `br_id`, `solution_id` | — |
| `function_requirement` | `solution_id`; codes | — |
| `fr_interface` | `fr_id`, `source_application_id`, `target_application_id`; codes | — *(behaviour guard checks type, not liveness)* |
| `fr_interface_data_entity` | `data_entity_id` | `fr_id` → `fr_interface` (`interface_is_active`) |
| `fr_bfc_node` | `fr_id`, `bfc_node_id` | — |
| `application_solution` | `application_id`, `solution_id` | — |
| `application_bfc_node` | `application_id`, `bfc_node_id` | — |
| `issue` | `raised_by_stakeholder_id`; codes | — |
| `issue_br` | `issue_id`, `br_id` | — |
| `benefit` | `accountable_org_role_id`; codes | — |
| `benefit_solution` | `benefit_id`, `solution_id` | — |
| `phase` | codes | — |
| `solution_phase` | `solution_id`, `phase_id` | — |
| `solution_dependency` | `solution_id`, `depends_on_solution_id` | — |
| `effort_rate` | `fr_type_code_id`, `complexity_code_id` | — |
| *live-only:* `wbs_item` | `parent_wbs_item_id`, `phase_id`, `solution_id` | — |
| *live-only:* `risk`, `change_request`, `cr_impact`, `control_rule`, `stakeholder` | every non-excluded FK (owner role, BFC node, solution, impacted objects, org unit); codes | — |
| *live-only:* `project`, `user_access_grant` | — | `program_id` (`program_is_active`); `project_id` / `program_id` (`scope_is_active`) |

#### 5.4.16 Rate card (R2-D7) — **audited between freezes, frozen at each freeze.**

The two mechanisms are complementary, not redundant. AUDIT_EVENT answers "who moved the rate
in March and why". `baseline_effort_rate` answers "what card was v1.0 signed on", which has to
be answerable for five years (Q12) and is exactly what a vendor disputes. Justified in the
EFFORT_RATE note (§5.3).

#### 5.4.17 Logical FK groups (canvas spike) — **a group number on the field, not a relationship table.**

`fk_group_no` is the smallest change that makes two relationships to one parent distinct. A
`DATA_ENTITY_RELATIONSHIP` table would be the normalized home **if** a relationship gains its
own attributes (a role name, a stated cardinality). None is asked for, and A-53 rules out typed
cardinality. So the number goes on the field, and the table is flagged as the extension (§5.3
DATA_FIELD).

#### 5.4.18 Import identity (R2-D1, R2-D10, Q1) — **BR number resolves, hier_code cross-checks, names are unique among live process siblings.**

Three changes that only make sense together. `hier_code` became partially unique (R2-D10), so it
can no longer resolve a step alone. The BR number is stable and 1:1 with the step (D-2), so it
resolves (R2-D1). And a step arriving with neither, a new step, must not duplicate a sibling's
name (Q1), which is now an index rather than a hope. The model's part is `business_key` /
`cross_check_key` on `IMPORT_ROW` and the two partial indexes on `BFC_NODE`. The resolution
order is the service's (§7.2b, §7.11).

---

### 5.5 Normalization notes — 1NF → 2NF → 3NF

**1NF.** The interesting violations in the source material are all list-valued:
- "Level 5 nodes link to input Data Entities and output Data Entities" — a repeating group. Resolved into `BFC_NODE_DATA_ENTITY`, with direction in the key rather than as `input_de_1 … input_de_n` columns.
- "Data entities have data fields" — resolved into `DATA_FIELD` rows rather than a field list blob, which is what makes PK/FK flags and composite keys representable at all.
- Composite primary keys inside a modelled DE: a naive design puts `pk_field_1, pk_field_2, pk_field_3` on `DATA_ENTITY`. Resolved by `is_primary_key` + `pk_ordinal` on `DATA_FIELD`, which supports any arity with no schema change.
- Issue categorization: three separate single-valued attributes (severity, type, status), *not* one multi-valued "tags" column. Multi-axis was the right call in the brief; it also happens to be the 1NF-clean one.

**2NF.** Only the junction tables have composite keys, so this is where partial dependencies could hide:
- `BR_DATA_ENTITY(br_id, data_entity_id, crud_code_id)`: `usage_note` depends on all three (the note about *reading* Customer differs from the note about *updating* it). Clean. But note what would *not* be clean: putting `de_name` here would depend on `data_entity_id` alone — a partial dependency, and the reason snapshot label-copying (below) is confined to the baseline tables.
- `BFC_NODE_ORG_ROLE(bfc_node_id, org_role_id, raci_code_id)`: no non-key attributes at all. The safest kind of junction.
- `PROJECT_SEQUENCE(project_id, sequence_code)`: `prefix` and `pad_width` depend on both parts (DE numbering differs from BR numbering within one project). Clean. If you ever decide prefixes are project-wide, they move to `PROJECT` — watch for it.
- `USER_ACCESS_GRANT`: surrogate PK, so no partial dependency is possible. Its natural grain,
  (user, scope) with at most one live row per user, is carried by the XOR CHECK and the
  partial unique index. `project_role_code_id` and `granted_at` depend on the grant.

**3NF — the four decisions that actually shaped the model:**

1. **Every categorized value became a `code_master` FK.** Storing `severity_label` on `ISSUE` alongside `severity_code` is the canonical transitive dependency: `issue_id → severity_code → severity_label`. The FK removes it, and renaming "High" to "Major" becomes one UPDATE instead of a data-fix script. This is why the lookup table exists and why I routed eleven attributes through it.

2. **Org unit is reached through role, never stored beside it.** `BR_ORG_ROLE` does not carry `org_unit_id`, because `br_id, org_role_id → org_unit_id` is transitive through `ORG_ROLE`. If it were stored, moving a role from Division A to Division B would leave every BR link asserting the old unit. The cost is a join on the RACI matrix screen; the benefit is that the org chart can be restructured mid-project without a data repair — which, on a transformation project, happens.

3. **`hier_code` and `level_no` are deliberate, constraint-backed denormalizations.** Both are strictly derivable from the parent chain: `level_no` is depth, `hier_code` is the concatenation of ancestor `seq_no`s. Pure 3NF says compute them. I store them, for three reasons: the chart is displayed sorted by `hier_code` on every screen (a recursive CTE per render is absurd for a value that changes rarely), `hier_code` is quoted in client documents so it must be a stable stored fact rather than a derivation that silently changes, and `level_no` was the guard in the composite FKs that enforced "L5 only" (D-23 moved that guard to `is_process`; `level_no` now carries only the depth CHECKs). The risk is drift on reparent/reorder, and the mitigation is that recalculation lives in exactly one service function (`renumber_subtree`) with the subtree recomputed in one transaction — plus a periodic consistency check. **In PostgreSQL 12+ `level_no` could be a generated column only if the parent's level were in the row; since it isn't, it stays a maintained column with a `CHECK`.** Flag this to whoever builds it: reparenting is the one operation in this app that must never be done with a partial update.

    A related question I want answered rather than assumed: **must `hier_code` be stable across a reorder?** If a node moves from position 2 to position 3, its code changes and so does every descendant's — and every document citing the old code is now wrong. The alternative is an immutable `node_number` assigned at creation plus a separate display-order code. See §6.

4. **Baseline snapshot rows store resolved labels, breaking 3NF on purpose.** `BASELINE_ISSUE.severity_label` is a copy of `code_master.label` — exactly the transitive dependency I removed from `ISSUE`. It is correct here because a snapshot's job is to record *what was true at freeze time*, and a `code_master` FK would let a later rename silently rewrite history in a frozen document. The normalization rule is about avoiding update anomalies; a table that is never updated cannot have them. The same reasoning applies to copying `hier_code` and `node_name` into `BASELINE_BFC_NODE`. **This is the one place in the model where denormalization is the correct answer, and it should be commented as such in the DDL** so a future reviewer doesn't "fix" it.

**Also worth recording:** `DATA_FIELD.length_val` / `precision_val` / `scale_val` are *not* a 3NF violation despite being type-dependent in their applicability. They depend on the field, not on the data type — `varchar(50)` and `varchar(200)` are different fields with the same type. The type merely determines whether the attribute is *meaningful*, which is a UI rule, not a functional dependency.

**This revision (D-23 … D-30), step by step:**

- **1NF.** A process step's I/O is still a repeating group resolved into rows
  (`BFC_NODE_DATA_ENTITY`). D-24 *removes* the temptation to hold a second list of it on the flow
  editor's side, so there is one set of rows and not two lists. External exchanges are rows
  (`BFC_NODE_EXTERNAL_FLOW`), not a "parties" text column on the node. An interface's carried
  entities are rows (`FR_INTERFACE_DATA_ENTITY`), not a comma list. The import side stages a
  nested JSON document as **one row per object**. `payload` stays `jsonb` because staging is
  forensic (§5.3 AUDIT_EVENT reasoning), and nothing is reported or diffed from it.
- **2NF.** The new composite keys carry no partial dependencies. `FR_INTERFACE_DATA_ENTITY(fr_id,
  data_entity_id)` has only `note`, which is about the pair. `DIAGRAM_LAYOUT`'s x/y/size depend on
  the *whole* natural key: the same entity sits in different places on different diagrams and
  scopes, so scope is a key part, not an attribute. `BFC_NODE_EXTERNAL_FLOW.flow_label` depends
  on the whole grain.
- **3NF.**
  1. **`is_mandatory` replaces `is_nullable`.** Both would hold `is_mandatory = NOT is_nullable`,
     a non-key attribute determined by another.
  2. **`FR_INTERFACE` is a subtype, not six nullable FR columns.** Its attributes depend on
     `fr_id` only *given* behaviour INTERFACE, which is a conditional dependency that belongs in a
     1:0..1 table.
  3. **`EXTERNAL_ENTITY` is its own entity.** Putting `party_name` on each external flow row
     would make `ext_name` depend on a name string rather than a key, and renaming "Bank" would
     become a multi-row update.
- **Deliberate, constraint-backed denormalizations (same class as `project_id`, §5.6):**
  - `BR_DATA_ENTITY.bfc_node_id`: transitive through `br_id`, verified by composite FK (D-24).
  - `FUNCTION_REQUIREMENT.fr_type_behaviour`: transitive through `fr_type_code_id`, verified
    by composite FK and cascaded on change (D-27).
  - `BFC_NODE.is_process`: a stored fact where a derivation ("has no children") would be both
    undeclarable and wrong during drafting (D-23).
  - The generated guard columns (`*_is_process`, `io_is_active`, `interface_is_active`,
    FR_INTERFACE's `fr_type_behaviour`): pure functions of `is_active`. They exist only to be
    FK participants and cannot drift, being generated.

  Each is a copy the database checks, not a copy the application must remember to maintain.

**Round 2 (D-32 … D-34, 2026-09-28), step by step:**

- **1NF.** A user's access used to be a set of rows, and it is now at most one live row. A
  program's project list is **not** stored on the grant or the program (it would be a
  repeating group). It is `PROJECT.program_id`, read at request time. WBS lines are rows, not
  an imported blob. MS Project's outline is resolved into `parent_wbs_item_id`. FK groups are a
  scalar per field, not a list of "relationships" on the entity.
- **2NF.** `WBS_ITEM` and `USER_ACCESS_GRANT` have single-column surrogate PKs, so there is
  nothing partial to depend on. `BASELINE_EFFORT_RATE`'s attributes depend on the whole
  `(baseline_id, source_effort_rate_id)`. A relationship role name would depend on
  `(data_entity_id, ref_data_entity_id, fk_group_no)` rather than the field, which is why it is
  flagged as a separate entity and not added as a DATA_FIELD column.
- **3NF.**
  1. **Program membership is on PROJECT, not on each grant.** A program grant that also stored
     "its" project ids would hold `grant → program → projects` transitively. It would go stale
     on every membership change, and the stale copy would be *access*.
  2. **`PROGRAM.client_id` is not repeated in a way that can drift.** `PROJECT` keeps its own
     `client_id` (it is the project's key fact), and the composite FK `(program_id, client_id)`
     makes the two agree. This is the same "copy the DB checks" class as `project_id`.
  3. **`suggested_br_id` is a fact about the FR** (0..1 per FR), so it is kept on the FR, not in
     a side table. It is a transient working fact, so it is excluded from the hash and the
     shadow.
- **Deliberate, constraint-backed copies added:** `raci_behaviour` (transitive through
  `raci_code_id`, FK-verified, immutable by NO ACTION); `fr_type_category` / `raci_category`
  (generated constants that exist only to be FK participants); `program_is_active` /
  `scope_is_active` (generated guards); `baseline_effort_rate` labels (the §5.5 point-4
  snapshot rule).

---

### 5.6 What this model means for the application

**The project key is genuinely everywhere, and that is the security model.** Nineteen tables carry `project_id`, and several carry it redundantly (e.g. `BUSINESS_REQUIREMENT.project_id` is derivable through `bfc_node_id`). That redundancy is intentional and is made safe by **composite foreign keys**: `(bfc_node_id, project_id) → BFC_NODE(bfc_node_id, project_id)` makes it structurally impossible for a BR to reference a node from another project. This converts a denormalization risk into a database-enforced invariant, and it gives every query a single-column tenant filter. In FastAPI, resolve `project_id` from the JWT + `USER_ACCESS_GRANT` once per request and apply it as a mandatory filter in the repository layer — or, better, use PostgreSQL row-level security with a session variable so a forgotten `WHERE` clause cannot leak client A's scope to client B. Given that Client Reviewer is a real role in this app, I would not rely on application discipline alone.

**A program widens who can see, never what is shared (D-32).** No scope table carries
`program_id`, so no FK path runs from one project's scope into another's, and the composite
`(id, project_id)` FKs still make a cross-project reference unstorable. A program changes
exactly one thing: the result of `visible_project_ids` for program-scoped grants. The program
dashboard is therefore a UNION of per-project queries, each passing the same guard, and never a
query over a shared table. The practical cost is that "the same Customer entity in two
projects" is two DEs. A cross-project hand-off is a HANDOFF edge to an end event labelled with
the other project (D-32). Both are what Ben chose.

**The BFC is one table, so the UI is one tree component.** Drilldown, breadcrumb,
drag-to-reorder, full-chart export and cross-level search all hit `bfc_node`. The process subtype
rules (description, I/O, roles, flows, external parties, as-is application) live in `CHECK`s
and generated-guard FKs, and in an **`is_process` conditional** in the React form. There is no
level conditional anywhere (D-23; a grep for `level_no = 5` is a pre-merge check). Two UI
consequences: "Add child" is disabled on a process node (the DB would refuse it anyway), and
"Split into sub-steps" is a guided action, which previews the BR, I/O, roles and edges it will
retire, then demotes, then creates the children. `renumber_subtree` is still the most dangerous
function in the codebase. `mark_process(demote)` is the second.

**The BR is the hub, and the model says so.** It is the only entity with inbound references from three directions — issues, FRs, and the DE grid. That means the BR detail screen is the application's centre of gravity: statement, logic, input/output DE grid, RACI, linked issues, linked FRs, all on one page. It also means the entity × function × logic grid from `design-spec` §4 is not a report you have to construct — it *is* `BUSINESS_REQUIREMENT ⋈ BR_DATA_ENTITY ⋈ DATA_ENTITY ⋈ BFC_NODE`, one query, pivotable in SQL. The brief asked whether the app should eventually emit that grid; this model makes the answer nearly free, which I think settles it.

**The DFD question from the brief answers itself, and now completely.** `BFC_NODE_DATA_ENTITY`
(what flows), `BR_DATA_ENTITY` with CRUD (what is done, licensed by the flow, D-24),
`BFC_NODE_ORG_ROLE` (who does it) and, since D-24a, `EXTERNAL_ENTITY` +
`BFC_NODE_EXTERNAL_FLOW` (who outside the organisation sends or receives it) together form a
process-level data flow diagram in relational form. Processes, data stores, flows and external
agents are all rows. The earlier draft claimed external agents were present when they were not;
now they are. The process flow (D-20) and the DFD (D-31) are **two renderings of one set of
rows**. They cannot disagree about a step's inputs, because there is only one place a step's
inputs are stored.

**"Person or system" independence is preserved structurally.** `data_processing_desc` lives on the BFC node and describes the processing requirement; the FR layer, which says *how a system does it*, is a separate table linked M:N. Nothing about the BFC or BR layer assumes automation. A consultant can complete areas 1–3 and 5 for an entire operation and never create an FR — which is exactly the "blueprints the whole operation, not just the software" property you asked for, and it is enforced by the fact that no FK points from BFC or BR *to* FR.

**The vendor boundary is a status column, not a table.** FRs are FTC-authored rows with `fulfilment_status`. There is no vendor user, no vendor-owned write path, and no vendor deliverable entity. If a vendor is ever given login access, the correct extension is a new `PROJECT_ROLE` code plus a `USER_ACCESS_GRANT` grant with read-only rights and a write path limited to `fulfilment_status` — not a new ownership model. Design the permission layer now so that is a config change. **Note D-11: no external party holds a login in MVP, so this is a future extension, not a deferred feature.**

**Baselines make the app bi-modal, and the UI must show it.** Live rows are editable; baseline rows are immutable. Users need to know at a glance which mode they are in — a persistent version selector in the MUI app bar, "v1.1 (frozen 2027-03-14) — read only" versus "Working". Every baseline screen is a different (read-only, diff-capable) component tree from its live equivalent. Budget for that; it is roughly a second, simpler set of screens, not a toggle on the existing ones.

**Soft delete plus baselines means nothing is ever truly gone, and that is the point.** A BR deleted after v1.0 was frozen still exists as `is_active = false` in the live table and as an immutable row in `BASELINE_BUSINESS_REQUIREMENT`. The v1.0→v1.1 diff reports it as *removed* — which is precisely the scope-change evidence FTC needs in a change-control conversation. Corollary: **never write a hard-delete endpoint**, and make that a code-review rule, because one `DELETE` cascade destroys the commercial value of every baseline that references the row.

**Two role vocabularies, never conflated.** `ORG_ROLE` is the client's ("Claims Supervisor, Underwriting Division"), project-scoped, used in RACI. The app's authorization role is `USER_ACCESS_GRANT.project_role_code` (OWNER / EDITOR / REVIEWER), one per grant over a project or a program (D-32), plus the `app_user.is_platform_admin` boolean (D-9). They share no table, no FK and no name fragment. In the code: `org_role` vs `project_role`, `/api/projects/{id}/org-roles` vs `/api/projects/{id}/access`. The bare word `role` is banned — it is a PostgreSQL reserved word anyway, which makes the rule enforce itself the first time someone forgets.

**Three things the application can now rely on the database for, so the service need not
re-check them for correctness (only for friendly messages).** First, a BR CRUD always has
the step I/O behind it (D-24). Second, interface detail exists only on interface-type FRs
(D-27). Third, a process node never has active children (D-23). Each of these was a
`consistency_check` line or a service assertion in the first draft. They stay in
`consistency_check` as proofs that return 0, and a non-zero result is a schema defect, not a
data defect.

**What the model cannot do (by design, worth knowing):** it cannot express a BR spanning two
process nodes, a process node that also has sub-steps (D-23: a split retires the parent's step
facts), a partial baseline covering only one area, **a baseline of a whole program (D-32)**,
**an entity shared by two projects of one program (D-32)**, **a non-admin user who sees two
unrelated projects (D-32)**, **schedule slip in a baseline diff (D-33: WBS is not baselined)**,
a named individual (only roles), a BR-level attachment, a requirement traced to a specific
source document, a curated ERD subject area other than a BFC branch, a named relationship role
on the ERD (§5.4.17), or a frozen diagram layout. The first two would change the shape of the
model rather than extend it.

---


---

## 6. Physical design

### 6.1 Table inventory

**Every table below is NET-NEW.** Value Bridge has no existing schema — nothing is
NEEDS-CHANGES, and there is no migration from a prior state.

| # | Table | Group | Carries `project_id` | Baselined |
|---|---|---|---|---|
| 1 | `client` | Tenancy | — | — |
| 2 | `program` | Tenancy (D-32) | — (carries `client_id`) | ✗ — **roll-up and access scope only; no program freeze** **new** |
| 3 | `project` | Tenancy | (is the key); `program_id` nullable | — |
| 4 | `code_master` | Shared | nullable (global / override) | — |
| 5 | `project_sequence` | Shared | ✓ (PK part) | — |
| 6 | `org_unit` | Client org | ✓ | ✓ *(D-12)* |
| 7 | `org_role` | Client org | ✓ | ✓ *(D-12)* |
| 8 | `bfc_node` | BFC | ✓ | ✓ |
| 9 | `bfc_node_data_entity` | BFC | ✓ | ✓ |
| 10 | `bfc_node_org_role` | BFC | ✓ | ✓ |
| 11 | `bfc_node_flow` | BFC (D-20) | ✓ | ✓ |
| 12 | `external_entity` | BFC (D-24a) | ✓ | ✓ |
| 13 | `bfc_node_external_flow` | BFC (D-24a) | ✓ | ✓ |
| 14 | `data_entity` | DE | ✓ | ✓ *(D-3)* |
| 15 | `data_field` | DE | ✓ | ✓ *(D-3)* |
| 16 | `business_requirement` | BR | ✓ | ✓ |
| 17 | `br_data_entity` | BR | ✓ | ✓ |
| 18 | `br_org_role` | BR | ✓ | ✓ |
| 19 | `solution` | Solution (D-7) | ✓ | ✓ |
| 20 | `br_solution` | Solution (D-7) | ✓ | ✓ |
| 21 | `function_requirement` | FR | ✓ | ✓ *(D-3)* |
| 22 | `fr_interface` | FR (D-27) | ✓ | ✓ |
| 23 | `fr_interface_data_entity` | FR (D-27) | ✓ | ✓ |
| 24 | `fr_bfc_node` | FR | ✓ | ✓ *(D-3)* |
| 25 | `application` | Landscape (D-8) | ✓ | ✓ *(D-3)* |
| 26 | `application_solution` | Landscape (D-8) | ✓ | ✓ *(D-3)* |
| 27 | `application_bfc_node` | Landscape (D-8) | ✓ | ✓ *(D-3)* |
| 28 | `stakeholder` | Issue (D-4) | ✓ | ✗ — people are not scope |
| 29 | `effort_rate` | Size (D-13) | ✓ (PK part) | ✓ **new (R2-D7)** — the agreed rate card is a commercial term |
| 30 | `benefit` | Benefit (D-14) | ✓ | ✓ |
| 31 | `benefit_solution` | Benefit (D-14) | ✓ | ✓ |
| 32 | `risk` | Risk (D-15) | ✓ | ✗ — risk is live, not scope |
| 33 | `change_request` | Change (D-16) | ✓ | ✗ — a CR challenges baselines, is not in one |
| 34 | `cr_impact` | Change (D-16) | ✓ | ✗ |
| 35 | `decision` | Governance (D-17) | ✓ | ✗ — append-only, evidential |
| 36 | `phase` | Phasing (D-18) | ✓ | ✓ |
| 37 | `solution_phase` | Phasing (D-18) | ✓ | ✓ |
| 38 | `solution_dependency` | Phasing (D-18) | ✓ | ✓ |
| 39 | `wbs_item` | Schedule (D-33) | ✓ | ✗ — **imported from MS Project; the schedule is not agreed scope** **new** |
| 40 | `control_rule` | Control (D-19) | ✓ | ✗ — governance config, not scope |
| 41 | `issue` | Issue | ✓ | ✓ |
| 42 | `issue_br` | Issue | ✓ | ✓ |
| 43 | `diagram_layout` | Presentation (D-30) | ✓ | ✗ — **presentation, not scope; hard-deleted (documented deviation)** |
| 44 | `baseline` | Baseline | ✓ | n/a |
| 45 | `import_batch` | Import (D-5, D-25) | ✓ | ✗ — staging; header kept after the row purge |
| 46 | `import_row` | Import (D-5, D-25) | via `import_batch` | ✗ — **purged after 90 days (Q14)** |
| 47 | `app_user` | Identity | — | — |
| 48 | `user_access_grant` *(was `user_project_access`)* | Identity (D-32) | nullable — XOR `program_id` | — |
| 49 | `audit_event` | Identity | nullable | — |
| 50–79 | `baseline_*` shadow tables (**30**) | Baseline | via `baseline` | n/a (immutable) |

*(`app_role` is deleted — D-9.)*

**The 30 shadow tables (D-3, D-12, D-14, D-18, D-20, D-24a, D-27, R2-D7).** One per baselined
live table, **in freeze (FK) order**: `org_unit`, `org_role`, `bfc_node`, `data_entity`,
`data_field`, `external_entity`, `bfc_node_data_entity`, `bfc_node_org_role`, `bfc_node_flow`,
`bfc_node_external_flow`, `business_requirement`, `br_data_entity`, `br_org_role`,
`application`, `solution`, `br_solution`, `function_requirement`, `fr_interface`,
`fr_interface_data_entity`, `fr_bfc_node`, `application_solution`, `application_bfc_node`,
`issue`, `issue_br`, `benefit`, `benefit_solution`, `phase`, `solution_phase`,
`solution_dependency`, **`effort_rate`**. `effort_rate` references only `code_master`, so it can
go anywhere. Putting it last keeps the earlier tables in their order. Column changes to existing shadows:
`baseline_bfc_node` gains `is_process`; `baseline_data_field` gains `is_mandatory` and
**`fk_group_no`** (hashed, because it changes the relationship structure); `data_type_label`
becomes nullable; `baseline_function_requirement` gains `fr_type_label`, `fr_type_behaviour`
and a nullable `baseline_solution_id`, but **not** `suggested_br_id` (a hint, excluded from
hash and shadow, R2-D16); `baseline_bfc_node_org_role` and `baseline_br_org_role` carry
`raci_label` **and `raci_behaviour`** (hashed). At A-35's bound (2,000 process nodes,
synchronous freeze), the freeze writes roughly **45,000–70,000 rows across 30 tables**. The rate
card adds a few dozen.

A benefit commitment and an agreed wave plan are scope, and so are the sequencing constraints
that make the plan solvable. **`effort_rate` is now in the set (R2-D7), for a different reason
than the FRs.** `baseline_function_requirement.effort_days` still stores the **computed** days
at freeze time, so a later renegotiation of the rate card cannot reprice a signed baseline. That
is unchanged, and it is what makes `priced_diff` reproducible. What was missing was the **card
itself** as a term of the agreement. Without `baseline_effort_rate`, nobody can show which
rates v1.0 was priced at, or that a CR priced in month six used a card the client never signed.
Between freezes, rate changes are audited (§5.3 EFFORT_RATE).

**`org_unit` and `org_role` are in the set because of finding D4.** `br_org_role` and
`bfc_node_org_role` were already frozen, but they can only carry `org_role_id` — a pointer
at a live, editable row. Baseline v1.0 said "org_role 44 is Accountable for BR-0042"; the
client renames role 44 and re-parents it in month four; opening v1.0 then renders
accountability that was never agreed, and because §5.4.5 routes org unit *through* the role,
the wrong division as well. That is precisely the failure §5.4.4 says shadow tables exist to
prevent, applied to a table the first draft left out.

That is the real cost of D-3 and D-7, and it is worth naming plainly: **30 mechanical
tables (17 at D-3/D-7), a `SnapshotMixin`, and one freeze service that inserts them in FK order.** `apple`
priced it at an afternoon (§5.4.4) and the column-parity CI test is what keeps it honest.
Generate the shadow models from the live models rather than hand-writing them.

**Deliberately not baselined:** `stakeholder` (a person is not a scope item — and freezing
personal data into an immutable table is a data-protection problem, not a feature) and
`import_batch` / `import_row` (staging). `org_unit` / `org_role` **were** on this list in the
first draft; D-12 moved them into the freeze set. Also not baselined: **`diagram_layout`**
(D-30). A box's position is presentation, not scope. A re-opened baseline renders with today's positions (A-52).
Also not baselined: **`wbs_item`** (D-33: the schedule belongs to MS Project and is not agreed scope, so a diff
cannot show slip), **`program`** (no program freeze, D-32) and **`user_access_grant`** (access
is not scope; its history is the grant rows themselves, which cannot be deleted, §6.6).
**Retention (Q12):** a baseline is recoverable for at least five years because no application
path, and no application grant, can delete one (§6.6). The model needs no retention column.
Long-term archive beyond Azure's PITR window belongs to the deployment design (D-35, §15.3).
**Contract wins (Ben, Q15):** where a client contract requires deletion at engagement end,
`purge_project` (§15.3) removes the project's live and snapshot rows and destroys its archive
key. It is the one hard-delete path in VB, platform-admin only, with a recorded reason, and it
runs under the owner role — `vb_app` still holds no DELETE (§6.6).

Full column lists (Column · Type · Constraints · Description) are in §5.2's attribute
blocks and §5.3's entity notes; the DDL is generated from them at build time — see §6.5.

### 6.2 Constraints that carry the design

These are not implementation detail. Each one is a business rule the database enforces, and
losing any of them silently breaks a promise this spec makes.

| Constraint | Table | Enforces |
|---|---|---|
| `CHECK (level_no BETWEEN 1 AND 5)` | `bfc_node` | the five-level contract |
| `CHECK (parent IS NULL) = (level_no = 1)` | `bfc_node` | exactly one root layer |
| `CHECK (is_process OR data_processing_desc IS NULL)`; `CHECK (NOT is_process OR level_no >= 3)`; `CHECK (level_no < 5 OR is_process)` | `bfc_node` | D-23 — only a process step carries the processing description; a process sits at L3–L5 (A-47); an L5 is always a process (A-54) |
| `CHECK (num_nonnulls(from_bfc_node_id, to_bfc_node_id) >= 1)`; both ends a generated process guard + FK to `(bfc_node_id, project_id, is_process)`; composite `(id, project_id)` FKs; **partial `UNIQUE (from_bfc_node_id, to_bfc_node_id, lower(btrim(condition_label))) NULLS NOT DISTINCT WHERE is_active`**; `CHECK (condition_label IS NULL OR btrim(condition_label) <> '')`. *"CONDITIONAL needs a label" is **service-enforced** + `consistency_check.conditional_without_label` — not a CHECK, because `flow_type` is a code FK (R2-D11 class)* | `bfc_node_flow` | D-20/D-23 — an edge must attach to something, only to process steps, only within its project. **Q2 — two live edges join the same two steps only if their conditions differ**; restore-before-insert keeps `source_id` stable |
| partial `UNIQUE (project_id, hier_code) WHERE is_active`; partial `UNIQUE (parent_bfc_node_id, lower(btrim(node_name))) WHERE is_active AND is_process` | `bfc_node` | **R2-D10** — no two live nodes share a chart code, and a retired node does not hold its code forever. `hier_code` is therefore not an identifier; imports resolve by BR number (R2-D1). **Q1** — no two live process steps under one parent share a name |
| partial `UNIQUE (parent_bfc_node_id, seq_no) WHERE is_active` | `bfc_node` | sibling ordering; a deleted sibling frees its slot |
| composite FK `(bfc_node_id, project_id)` | `business_requirement` and all junctions | **structurally impossible to reference another project's row** |
| `node_is_process GENERATED (TRUE if active, else NULL)` + FK `(bfc_node_id, project_id, node_is_process) → bfc_node(bfc_node_id, project_id, is_process)` ON UPDATE NO ACTION | `business_requirement`, `bfc_node_data_entity`, `bfc_node_org_role`, `application_bfc_node`, `bfc_node_external_flow` | D-23 — process-only, in the DB. A retired row's NULL guard neither blocks demotion nor pins the node |
| `parent_is_process GENERATED (FALSE if active, else NULL)` + FK `(parent_bfc_node_id, project_id, parent_is_process) → bfc_node(bfc_node_id, project_id, is_process)` **ON UPDATE NO ACTION** (never CASCADE); plain FK `(parent_bfc_node_id, project_id)` for existence | `bfc_node` | **D-23 — a process has no active children.** Adding a child to a process, or promoting a node with active children, is refused by the DB |
| `UNIQUE (bfc_node_id, project_id, is_process)` | `bfc_node` | the FK target for every process guard (replaces `(project_id, bfc_node_id, level_no)`) |
| `UNIQUE (client_id, program_code)`; partial `UNIQUE (client_id, lower(program_name)) WHERE is_active`; UKs `(program_id, client_id)`, `(program_id, client_id, is_active)`, `(program_id, is_active)` as FK targets | `program` | D-32 — program identity within a client; targets for the same-client and live-program FKs |
| FK `(program_id, client_id) → program(program_id, client_id)`; `program_is_active GENERATED (TRUE if active, else NULL)` + FK `(program_id, client_id, program_is_active) → program(program_id, client_id, is_active)` ON UPDATE NO ACTION; `UNIQUE (project_id, is_active)` | `project` | **D-32 — a program's projects share its client; an active project sits only in a live program; a program with live projects cannot be retired (Q4).** Who may change `program_id` (platform admin, Q10) is service-enforced and audited |
| `CHECK (num_nonnulls(project_id, program_id) = 1)`; **partial `UNIQUE (app_user_id) WHERE is_active`**; `scope_is_active GENERATED` + FKs `(project_id, scope_is_active) → project(project_id, is_active)` and `(program_id, scope_is_active) → program(program_id, is_active)` ON UPDATE NO ACTION | `user_access_grant` | **D-32, R2-S2, R2-S4 — one scope per grant; at most one live grant per user (only platform admins span unrelated projects, Q10); no live grant on a retired scope, and no retiring a scope that live grants name** |
| `UNIQUE (project_id, ms_unique_id)` (full); `UNIQUE (wbs_item_id, project_id)`; FK `(parent_wbs_item_id, project_id)`; `CHECK ((outline_level = 1) = (parent_wbs_item_id IS NULL))`; `CHECK (parent_wbs_item_id <> wbs_item_id)`; date-order CHECKs; `CHECK (actual_finish IS NULL OR actual_start IS NOT NULL)`; `CHECK (percent_complete BETWEEN 0 AND 100)`; composite FKs `(phase_id, project_id)`, `(solution_id, project_id)` | `wbs_item` | **D-33, Q13, R2-D15** — one row per MS Project Unique ID per project, restored rather than duplicated on re-import; links cannot cross projects. **`row_version` guards the two links only** (documented deviation). No unique on `wbs_code` (renumbered by MS Project on outline moves) |
| composite FK `(suggested_br_id, project_id) → business_requirement(br_id, project_id)` | `function_requirement` | **D-34, R2-D16** — a suggestion stays in-project. *Clearing it (only once a `BR_SOLUTION` path to the FR's solution exists) is service-enforced, because it reads another table.* Excluded from `content_hash` and the shadow |
| `CHECK ((fk_group_no IS NOT NULL) = is_foreign_key)`; `CHECK (fk_group_no IS NULL OR fk_group_no >= 1)`; partial `UNIQUE (data_entity_id, ref_data_entity_id, fk_group_no, ref_data_field_id) WHERE is_active AND ref_data_field_id IS NOT NULL` | `data_field` | **canvas spike** — two relationships to one parent are distinct; a composite FK is one group; a parent field appears once per relationship |
| `CHECK (row_version = 1 OR change_rationale IS NOT NULL)`; `effort_rate_id` identity `UNIQUE` | `effort_rate` | **R2-D7** — a changed rate states why; a stable source pointer survives the override re-pointing |
| `UNIQUE (baseline_id, source_effort_rate_id)`; `source_effort_rate_id` ON DELETE NO ACTION; reject trigger as every `baseline_*` | `baseline_effort_rate` | **R2-D7** — the rate card a baseline was priced on, immutable |
| `UNIQUE (project_id, sequence_code)` (the PK) + `CHECK (sequence_code IN ('DE','BR','FR','ISSUE','SOL','BEN','RSK','CR','DEC','EXT'))` | `project_sequence` | **R2-D14** — the ten series; presence of all ten is seeded by `create_project` and proved by `consistency_check.project_sequence_missing` |
| `bfc_node_id` copied + FK `(br_id, project_id, bfc_node_id) → business_requirement`; `io_is_active` GENERATED + FK `(bfc_node_id, data_entity_id, direction, io_is_active) → bfc_node_data_entity(bfc_node_id, data_entity_id, direction, is_active)` | `br_data_entity` | **D-24 — R needs a step input, C/U/D need a step output**, by construction. Retiring an I/O row a BR CRUD depends on is refused |
| `UNIQUE (bfc_node_id, data_entity_id, direction, is_active)` | `bfc_node_data_entity` | the D-24 FK target. `is_active` is in it so that a soft delete is a key change |
| `UNIQUE (br_id, project_id, bfc_node_id)` | `business_requirement` | the D-24 carrier of the BR's node; also makes `bfc_node_id` effectively immutable once CRUD exists |
| `UNIQUE (project_id, ext_number)`; partial `UNIQUE (project_id, lower(ext_name)) WHERE is_active` | `external_entity` | D-24a — business key never reused; no two live parties with one name |
| `UNIQUE NULLS NOT DISTINCT (bfc_node_id, external_entity_id, direction, data_entity_id)`; `CHECK (direction IN ('I','O'))`; process guard; when a DE is named, FK `(bfc_node_id, data_entity_id, direction, io_is_active) → bfc_node_data_entity(…, is_active)` | `bfc_node_external_flow` | D-24a — one exchange per (step × party × direction × DE), only on process steps, and never contradicting the step's own I/O |
| `CHECK ((category IN ('FR_TYPE','RACI_TYPE')) = (behaviour_code IS NOT NULL))`; `CHECK (category <> 'FR_TYPE' OR behaviour_code IN ('FORM','INTERFACE','REPORT','BATCH','OTHER'))`; `CHECK (category <> 'RACI_TYPE' OR behaviour_code IN ('RESPONSIBLE','ACCOUNTABLE','CONSULTED','INFORMED','SUPPORT','OTHER'))`; `UNIQUE (code_id, category, behaviour_code)` | `code_master` | D-27, **Q7** — every FR type and RACI code has a behaviour, nothing else has one; the FK target carries the category because the vocabularies share `OTHER` |
| `fr_type_behaviour NOT NULL`; `fr_type_category GENERATED ('FR_TYPE')`; FK `(fr_type_code_id, fr_type_category, fr_type_behaviour) → code_master(code_id, category, behaviour_code)` **ON UPDATE NO ACTION** (was CASCADE); `UNIQUE (fr_id, project_id, fr_type_behaviour)` | `function_requirement` | D-27 — the FR's behaviour is its type's; the code is provably an FR_TYPE. **Q6 / R2-D8 — a type's behaviour is immutable once any FR references it** |
| `fr_type_behaviour GENERATED ('INTERFACE' if active, else NULL)` + FK `(fr_id, project_id, fr_type_behaviour) → function_requirement(fr_id, project_id, fr_type_behaviour)`; `CHECK (source_application_id <> target_application_id)`; both applications `(id, project_id)` FKs, `NOT NULL` | `fr_interface` | **D-27 — interface detail only on an interface-behaviour FR, declaratively**; endpoints distinct and in-project |
| `interface_is_active GENERATED` + FK `(fr_id, project_id, interface_is_active) → fr_interface(fr_id, project_id, is_active)` | `fr_interface_data_entity` | no live carried-entity rows under retired interface detail |
| `data_type_code_id` **NULLABLE**; `CHECK (data_type_code_id IS NOT NULL OR num_nulls(length_val, precision_val, scale_val) = 3)`; `CHECK (NOT is_primary_key OR is_mandatory IS DISTINCT FROM FALSE)`; `is_nullable` **dropped** for `is_mandatory` (nullable = unknown) | `data_field` | D-26 — logical fields; no length without a type; a key field cannot be optional |
| `CHECK (diagram_type IN ('ERD','PROCESS_FLOW','DFD'))`; `CHECK (num_nonnulls(bfc_node_id, data_entity_id, external_entity_id, bfc_node_flow_id) = 1)`; `CHECK (diagram_type <> 'ERD' OR data_entity_id IS NOT NULL)`; `CHECK (diagram_type = 'PROCESS_FLOW' OR bfc_node_flow_id IS NULL)`; `CHECK (diagram_type = 'ERD' OR scope_bfc_node_id IS NOT NULL)`; `UNIQUE NULLS NOT DISTINCT (project_id, diagram_type, scope_bfc_node_id, bfc_node_id, data_entity_id, external_entity_id, bfc_node_flow_id)`; composite `(id, project_id)` FKs | `diagram_layout` | D-30 — one position per object per diagram per scope; typed, project-safe object pointers. **Exempt from soft delete and `row_version`** (documented deviation, A-52) |
| `CHECK (target_entity IN (…,'BUSINESS_REQUIREMENT','FUNCTION_REQUIREMENT','PROCESS_FLOW','WBS_ITEM'))`; `CHECK ((target_entity = 'PROCESS_FLOW') = (source_format LIKE 'vb-process-flow/%'))`; `CHECK ((target_entity IN ('PROCESS_FLOW','WBS_ITEM')) = (import_mode IS NOT NULL))`; `CHECK ((target_entity = 'PROCESS_FLOW') = (anchor_bfc_node_id IS NOT NULL))` | `import_batch` | D-25/D-28/**D-33** — a flow import states its format, mode and parent; a WBS import states its mode, because only REPLACE retires lines |
| `CHECK (num_nonnulls(sheet_row_no, source_path) = 1)`; `CHECK (is_valid = (jsonb_array_length(error_detail) = 0))`; `CHECK (verdict IN ('INSERT','UPDATE','MATCH','RETIRE','KEPT'))`; partial `UNIQUE (import_batch_id, row_kind, local_key) WHERE local_key IS NOT NULL`; **partial `UNIQUE (import_batch_id, row_kind, business_key) WHERE business_key IS NOT NULL`** | `import_row` | D-25 — every staged object is locatable; validity cannot disagree with its errors; a duplicate file-local key **or a business key (BR number, Unique ID …) named twice in one file** is caught at staging (R2-D1); `KEPT` marks step I/O a replace-mode flow import would have retired but a dependent protects (§7.2b) |
| **partial `UNIQUE (bfc_node_id) WHERE is_active`** | `business_requirement` | **D-2 — exactly one BR per process node (D-2, D-23). Partial, not full (finding P5): a soft-deleted BR must not permanently occupy the key, leaving the node requirement-less with no repair but hand-written SQL.** Dropping this index is the entire cost of reversing D-2 (§5.4.1a) |
| `solution_id` **NULLABLE**; composite FK `(solution_id, project_id)` when present | `function_requirement` | **D-28 reverses D-7's constraint** — an FR may arrive before its Solution. Unlinked = warning (`coverage.fr_unlinked`, control panel), never an error. A BR with no FR remains legal |
| `UNIQUE (project_id, solution_number)` / `application_code` | `solution`, `application` | business keys quoted in client documents |
| **service-enforced, not a CHECK** (R2-D11): `allocate_application` refuses an `AS_IS` application; changing an application's lifecycle to `AS_IS` is refused (409, allocations listed) while live `application_solution` rows exist; `consistency_check.as_is_allocated` proves it. `APP_LIFECYCLE` seeded `is_system` | `application_solution` | an as-is-only system cannot be allocated as a to-be answer. *A CHECK sees one row of one table; the lifecycle is a code FK on `application`, and the rule must hold on both write paths* |
| `raised_by_stakeholder_id NOT NULL` and separate `recorded_by_user_id NOT NULL` | `issue` | D-4 — who raised it and who typed it are different facts and cannot collapse. **`NOT NULL`, not a `CHECK`: the first draft wrote `CHECK (raised_by_stakeholder_id <> NULL)`, which evaluates to NULL for every row and therefore never fails — a constraint that guaranteed nothing (finding D8)** |
| `row_version` + `WHERE row_version = :v` on every UPDATE | all editable business tables | **D-6 — two consultants on one BR no longer overwrite each other silently** |
| `SELECT … FOR UPDATE` on the batch row as the first statement of `commit`, status re-checked inside the lock | `import_batch` | **a committed batch cannot be re-committed. The first draft claimed a `CHECK` did this; a `CHECK` is stateless — it sees only the new row, never the old — so it cannot express a state transition, and a double-click applied the file twice (finding P2)** |
| `project_id` + composite FKs on `data_entity_id`, `ref_data_entity_id`, `ref_data_field_id` | `data_field` | **finding D9 — the DE layer was the one place the composite-FK backstop §5.6 sells as universal did not exist, leaving cross-project references prevented by service code alone** |
| `UNIQUE (project_id, lower(stakeholder_name)) WHERE is_active` | `stakeholder` | finding D6 — the import matched people by name against a table with no unique key, so the lookup could legitimately return more than one row |
| `UNIQUE (project_id, major_no, minor_no)` | `baseline` | finding P9 — version identity is two integers; `version_label` is rendered from them, never parsed |
| `effort_days NOT NULL` once `complexity_code_id` is set; derived at save, never accepted from the request | `function_requirement` | D-13 — a rate-card change must not silently reprice agreed scope |
| `accountable_org_role_id NOT NULL` | `benefit` | D-14 — a benefit with no owner is a hope, not a benefit |
| `exposure_score` derived from probability × impact at save | `risk` | D-15 — the score cannot be argued down independently of its inputs |
| `against_baseline_id NOT NULL` + composite `(against_baseline_id, project_id)` FK; **status rule service-enforced under lock** (R2-D11): the target baseline is read `FOR SHARE` and must be `FROZEN` or `APPROVED`; `freeze` supersedes the prior baseline `FOR UPDATE`, so the two serialize. `BASELINE_STATUS` seeded `is_system` | `change_request` | D-16, **Q8** — a CR challenges something agreed and still in force, never a SUPERSEDED baseline. Point-in-time: an existing CR keeps its target when that baseline is later superseded |
| `effort_delta_days` / `benefit_delta_value` writable **only** by `price_cr` | `change_request` | D-16 — a change priced by its requester is not priced |
| topological check on insert; a cycle is rejected | `solution_dependency` | D-18 — a dependency cycle makes the phase plan unsolvable and is silent until someone tries to schedule |
| `UNIQUE (analysis_code) WHERE project_id IS NULL` + `UNIQUE (project_id, analysis_code) WHERE project_id IS NOT NULL` | `control_rule` | D-19 — the two tiers: one FTC house default per analysis, one agreed rule per project per analysis |
| `analysis_code` in a closed list matching §7.9 | `control_rule` | D-19 — a rule pointing at a non-existent analysis is rejected, which stops aspirational governance accumulating |
| `CHECK (project_id IS NULL OR owner_org_role_id IS NOT NULL)` | `control_rule` | D-19 — **an analysis without a named owner is a report nobody acts on.** Relaxed on the house-default tier only, because FTC cannot name a client role before the client's org chart exists |
| `CHECK (num_nonnulls(impacted_br_id, impacted_solution_id, impacted_fr_id, impacted_application_id, impacted_data_entity_id, impacted_phase_id, impacted_benefit_id) = 1)` + composite `(id, project_id)` FK on each | `cr_impact` | **A-37 resolved — the database enforces which object a CR row points at, and that it belongs to this project.** Replaces the soft polymorphic pointer |
| `BEFORE UPDATE OR DELETE` reject trigger; **exempt from soft delete**; no `UPDATE`/`DELETE` grant | `decision` | **A-41 resolved — the decision log is evidential.** Corrections are a new row with `supersedes_decision_id`, never an edit |
| `baseline` is **exempt from soft delete** — no `is_active`, no `deleted_at` | `baseline` | finding P6 — the header carried `is_active` while its 19 children were hard-immutable, so a "retracted" baseline stayed visible to any diff query that forgot the filter. A baseline is either frozen or it does not exist |
| `UNIQUE (project_id, de_number)` / `br_number` / `fr_number` / `issue_number` | respective | **uniqueness comes from the constraint, never from the generator** |
| `UNIQUE (data_entity_id, field_name)` | `data_field` | field names unique within an entity |
| `CHECK (NOT is_primary_key OR pk_ordinal IS NOT NULL)` | `data_field` | composite PKs are ordered |
| `CHECK (NOT is_foreign_key OR ref_data_entity_id IS NOT NULL)` | `data_field` | an FK field must name its target |
| `CHECK (crud_code IN ('C','R','U','D'))` + generated `direction` column | `br_data_entity` | removes the `(R, OUTPUT)` contradiction by construction (§5.4.2) |
| `raci_category GENERATED ('RACI_TYPE')`, `raci_behaviour NOT NULL` + FK `(raci_code_id, raci_category, raci_behaviour) → code_master(code_id, category, behaviour_code)` NO ACTION; partial `UNIQUE (br_id) WHERE is_active AND raci_behaviour = 'ACCOUNTABLE'` on `br_org_role`, and `UNIQUE (bfc_node_id) WHERE is_active AND raci_behaviour = 'ACCOUNTABLE'` plus `UNIQUE (bfc_node_id) WHERE is_active AND raci_behaviour = 'RESPONSIBLE'` on `bfc_node_org_role` | `br_org_role`, `bfc_node_org_role` | **Q7, R2-D9, R2-D11** — at most one Accountable per BR **and per step**, and at most one Responsible per step (its lane, A-46; a flow import's lane replaces it), keyed on behaviour, not the letter; the RACI code is provably a RACI_TYPE; a used behaviour is immutable. *The old row could not be written: `raci_code` is an FK* |
| `UNIQUE (project_id, version_label)` | `baseline` | one v1.1 per project |
| `ON DELETE NO ACTION` on every `source_*_id` | `baseline_*` | a frozen baseline cannot be shredded by a cascade |
| `BEFORE UPDATE OR DELETE` reject trigger | `baseline_*` | immutability at the database, not by convention (A-7) |

**Rules in this table that the database does *not* hold, stated as such (R2-D11).** A CHECK sees
one row of one table and has no memory of the old row. So four rules that read another table's
code value, or a transition, are service-enforced under a named mechanism: the CR target status
(row 8), the as-is allocation (row 7), the CONDITIONAL label (row 2), and **"no active row under
an inactive parent" on every FK in §5.4.15** except the few whose target key includes
`is_active`. Each has a `consistency_check` proof. A row here that claims a CHECK the DB cannot
evaluate is a defect in this spec, and a review should treat it as one.

### 6.3 Indexes

- Every FK gets an index — PostgreSQL does not create them automatically, and this schema
  is FK-dense.
- `bfc_node (project_id, hier_code)` — the sort order of every chart screen.
- `bfc_node (parent_bfc_node_id, seq_no)` — tree expansion.
- `business_requirement (project_id, br_number)` and `(bfc_node_id)`.
- `br_data_entity (data_entity_id)` — the reverse lookup "which BRs touch this DE", which is
  the impact-analysis screen.
- **Referencing-side indexes for every composite guard FK.** A NO ACTION check on an UPDATE
  of `bfc_node.is_process` or `bfc_node_data_entity.is_active` scans the referencing table.
  Without an index that scan runs on every promote, demote and I/O removal. Concretely:
  `bfc_node (parent_bfc_node_id, project_id, parent_is_process)`, `br_data_entity
  (bfc_node_id, data_entity_id, direction)`, `bfc_node_external_flow (bfc_node_id,
  data_entity_id, direction)`, and `(bfc_node_id, project_id)` on each guarded table.
- `bfc_node (project_id) WHERE is_process AND is_active`: the process list, the freeze count and
  `consistency_check`.
- `bfc_node_external_flow (external_entity_id)`: "which steps does the Bank touch".
- `fr_interface (project_id, source_application_id, target_application_id)`: the interface
  list by application pair (`interface_load`).
- `function_requirement (project_id) WHERE solution_id IS NULL AND is_active`: the unlinked-FR
  warning (D-28).
- `function_requirement (project_id, fr_type_behaviour) WHERE is_active`: `v_interface_list`.
- `diagram_layout`: served by its natural-key unique index (leading `project_id,
  diagram_type, scope_bfc_node_id`), so no extra index is needed.
- `bfc_node (project_id, hier_code varchar_pattern_ops) WHERE is_active`: subtree `LIKE`, now
  that the unique index is partial. The chart sort is served by the partial unique index
  itself.
- `bfc_node_flow`: the partial natural-key index serves "edges out of S1". Add
  `(to_bfc_node_id)` for "edges into S1".
- `bfc_node_org_role (bfc_node_id) WHERE is_active AND raci_behaviour = 'RESPONSIBLE'`: the
  partial unique index (at most one Responsible per step) is also the lane lookup (A-46).
- `function_requirement (suggested_br_id) WHERE suggested_br_id IS NOT NULL`: "FRs suggested for
  this BR", and the clearing step when that BR is retired.
- `data_field (data_entity_id, ref_data_entity_id, fk_group_no) WHERE is_foreign_key`: ERD
  relationship grouping.
- `wbs_item`: `(project_id, ms_unique_id)` is the unique index (the import match);
  `(parent_wbs_item_id)`; `(project_id, display_order) WHERE is_active` (tree render);
  `(phase_id) WHERE is_active` and `(solution_id) WHERE is_active` (the dashboard, and the Q4
  refusal when a phase or solution is retired).
- `import_batch (uploaded_at) WHERE rows_purged_at IS NULL`: the 90-day purge scan.
- `code_master`: the referencing-side indexes on `(fr_type_code_id)` and `(raci_code_id)` already
  exist under "every FK gets an index". They make the NO ACTION check cheap on the rare
  behaviour edit.
- `issue (project_id, status_code_id, severity_code_id)` — the issue dashboard.
- `user_access_grant (app_user_id) WHERE is_active`: the partial unique index is the lookup, hit
  on **every request** by the visibility guard. There is no extra index.
- `project (program_id) WHERE is_active`: the second half of `visible_project_ids` for a program
  grant, and the program dashboard's UNION.
- `user_access_grant (project_id) WHERE is_active` and `(program_id) WHERE is_active`: "who can
  see this" screens, the move-preview of `set_project_program`, and the NO ACTION check when a
  scope is retired.
- `baseline_* (baseline_id, source_*_id)` — the diff join. Without it the diff is a
  cross-product.
- `audit_event (project_id, occurred_at DESC)`.

### 6.4 Row-level security

`apple` recommends PostgreSQL RLS with a session variable on top of the service-layer
guard, on the grounds that Client Reviewer is a real role and a forgotten `WHERE` clause
should not be able to leak client A's scope to client B. **I agree and recommend it, but
not for MVP** — RLS plus a connection-pooled FastAPI app needs the session variable set per
checkout, which is a known footgun. MVP ships the `access.py` guard (§7.8) with acceptance
criteria 18–19 covering it; RLS goes in as defence-in-depth once the app is real. Recorded
so it is a scheduled decision, not an oversight.

**The deferral now has a stated price (finding S7).** The auditor's objection was not that
deferring RLS is wrong — it is that the compensating control it was deferred *in favour of*
was prose. §7.8 asserted "every service function calls `require_project` first" while the
guard appeared in five of twenty written functions, with no decorator, no dependency and no
test that would catch a router shipped without it.

> **The condition of deferring RLS is acceptance criterion 49** — a test that enumerates
> every route in §9 and fails if any project-scoped route is not covered by the
> `require_project` FastAPI dependency. If that test is not in the build, RLS is not
> deferred; it is absent. That is the price, written down.

### 6.6 Database privileges (finding S11)

Grants, no code, in the first migration (finding S11, **R2-S9**):

- **The application role does not own the schema.** Migrations run as a separate owner role.
  The app role holds no DDL and **no `TRUNCATE` anywhere**.
- **No `DELETE` on any table, with exactly two exceptions:** `diagram_layout` (the documented
  hard-delete, A-52) and `import_row` (the 90-day purge, Q14). Soft delete is an `UPDATE`, so
  the app never needs `DELETE` on a business table. With the privilege revoked, §5.6's "never
  write a hard-delete endpoint" becomes a **permission error** rather than a code-review rule,
  and no bug or injection in the HTTP-serving role can shred a row that a baseline references.
  `import_batch`, `user_access_grant` and `audit_event` get no `DELETE` either. They are the
  import trail, the access history and the security log.
- **No `UPDATE` on `decision`** (A-41), **on any `baseline_*` table**, or **on `audit_event`**
  (append-only). The reject triggers (§6.2) are the belt, and the revoked grants are the braces.
- **`baseline` (header): `UPDATE` on the status column and its audit columns only**, as a
  PostgreSQL column-level grant. The FROZEN → APPROVED → SUPERSEDED transitions (Q8) need it,
  and nothing else on a frozen header may change. No `DELETE`: that is Q12's five-year
  recoverability, held by the database.
- **A CI test reads `information_schema.role_table_grants`** and fails if the application role
  holds `DELETE` on anything other than the two tables above, or `UPDATE` on a table listed here.
  A grant is migration state, and migration state drifts.
- *Optional hardening:* run the purge job under a separate `vb_maintenance` role and drop
  `DELETE ON import_row` from the application role too. The HTTP-serving role would then
  delete only layout rows.
- **Azure (D-35):** both roles' credentials live in Key Vault, fetched by managed identity. The
  owner role's secret is not available to the App Service at runtime at all, only to the
  migration job.

Why this is cheap insurance: all users share one application database role with no RLS, so a
single logic or injection defect reaches every project at once. The ORM makes injection
unlikely with two named exceptions — `baseline.diff` and `reports.py` are raw SQL, and
`issue_dashboard` rolls issues to the L1 ancestor via a `hier_code` prefix, i.e. a `LIKE`
against a user-editable string in which `%` and `_` are wildcards. **Escape `%` and `_` in
that prefix, and parameterise every raw query.**

### 6.5 Schema generation

`apple` has offered to emit `schema.sql` (PostgreSQL DDL mirroring this model exactly —
composite FKs, partial unique indexes, the generated `direction` column, the freeze
immutability trigger) or `schema.dbml`. **Take her up on it after sign-off, not before** —
regenerating DDL is cheap, and any change made to §5 during review would invalidate it.

A CI test asserts each `baseline_*` table's column set matches its live table, minus audit
columns, plus snapshot columns. That test is what makes shadow tables safe against schema
drift (§5.4.4).

---

## 7. Function — where business logic lives

All logic in the service layer (§9.11). Routers do HTTP only.

### 7.0 Grid function → service map

Every function named in the §4 grid, and where it lives. Plain link/unlink functions are
grouped: they share one generic `link_service` pattern (validate both ends are in the
caller's project, upsert or soft-delete the junction row) and are not written out
individually.

| §4 grid function | Service | Written out in |
|---|---|---|
| `create_bfc_node` | `bfc.create_node` | §7.2 |
| `generate_bfc_code` | `bfc.generate_code` | §7.2 |
| `reorder_bfc_node` | `bfc.reorder` | §7.2 |
| `mark_process` | `bfc.mark_process` | §7.2 *(new — D-23; promote creates the BR, demote refused while the BR or any other step-level fact is active)* |
| `describe_process` | `bfc.update_node` | §7.2 (the `is_process` guard, D-23) |
| `link_bfc_data_entity` | `bfc.ensure_step_io` / `bfc.unlink_data_entity` | §7.3 *(no longer generic — unlink refused while a BR CRUD **or an external flow** depends on it, D-24, R2-D13)* |
| `link_bfc_external_flow` · `create_external_entity` | `bfc.link_external_flow` / `external_entity.upsert` | §7.3 *(no longer generic — ensures step I/O through `bfc.ensure_step_io`, R2-D13)* · §7.0 (generic) |
| `generate_dfd` · `export_dfd` | `process_flow.generate_dfd` / `export_dfd` | §7.2a *(new — D-31)* |
| `download_flow_schema` · `export_process_flow_json` | `flow_import.schema` / `flow_import.export` | §7.2b *(new — D-25)* |
| `validate_process_flow_json` · `commit_process_flow_json` | `flow_import.validate` / `flow_import.commit` | §7.2b *(new — D-25, on the §7.11 pipeline)* |
| `generate_erd` · `export_erd` | `data_entity.generate_erd` / `export_erd` | §7.4 *(new — D-29)* |
| `save_diagram_layout` | `diagram_layout.save` | §7.14 *(new — D-30)* |
| `link_bfc_role` | `link_service.link` | §7.0 (generic) |
| `link_process_flow` | `process_flow.link_process_flow` | §7.2a |
| `generate_process_flow` | `process_flow.generate_process_flow` | §7.2a |
| `export_process_flow` | `process_flow.export_process_flow` | §7.2a |
| `flow_completeness_report` | `process_flow.flow_completeness_report` | §7.2a |
| `create_data_entity` | `data_entity.create_entity` | §7.4 |
| `manage_data_fields` | `data_entity.upsert_field` | §7.4 |
| `validate_entity_model` | `reports.entity_model_validation` | §7.9 |
| `create_br` | `business_requirement.create_br` | §7.3 |
| `link_br_data_entity` | `business_requirement.link_data_entity` | §7.3 |
| `update_br` | `business_requirement.update_br` | §7.3 |
| `link_br_role` | `link_service.link` | §7.0 (generic) |
| `link_br_solution` | `link_service.link` | §7.0 (generic) |
| `create_solution` | `solution.create_solution` | §7.5 |
| `create_application` | `application.create_application` | §7.5 |
| `link_application_solution` | `application.link_solution` | §7.5 |
| `link_bfc_application` | `link_service.link` | §7.0 (generic) |
| `solution_matrix` | `reports.solution_matrix` | §7.9 |
| `application_gap_report` | `reports.application_gap` | §7.9 |
| `create_stakeholder` | `stakeholder.upsert` | §7.6 |
| `download_template` | `bulk.template` | §7.11 |
| `export_entity` | `bulk.export` | §7.11 |
| `validate_import` | `bulk.validate` | §7.11 |
| `commit_import` | `bulk.commit` | §7.11 |
| `revoke_access` | `project.revoke_access` | §7.10 *(new — S9)* |
| `deactivate_user` | `user_admin.deactivate_user` | §7.10 *(new — S4)* |
| `br_coverage_report` | `reports.coverage` | §7.9 |
| `create_function_requirement` | `function_requirement.create_fr` | §7.5 |
| `link_fr_to_bfc_node` | `function_requirement.link_node` | §7.5 |
| `link_fr_solution` | `function_requirement.update_fr` | §7.5 *(new — D-28)* |
| `maintain_fr_types` | `code_master.maintain` (category `FR_TYPE`, with behaviour) | §7.12 *(new — D-27)* |
| `describe_interface` | `function_requirement.describe_interface` | §7.5 *(new — D-27)* |
| `interface_list` | `reports.interface_list` (over `v_interface_list`) | §7.5 / §7.9 *(new — D-27)* |
| `fr_unlinked` | `reports.fr_unlinked` | §7.13 *(new — D-28, control-panel rule)* |
| `fr_traceability_matrix` | `reports.traceability` | §7.9 |
| `raise_issue` | `issue.raise_issue` | §7.6 |
| `link_issue_br` | `link_service.link` | §7.0 (generic) |
| `resolve_issue` | `issue.resolve_issue` | §7.6 |
| `issue_dashboard` | `reports.issue_dashboard` | §7.9 |
| `freeze_baseline` | `baseline.freeze` | §7.7 |
| `diff_baseline` | `baseline.diff` | §7.7 |
| `reopen_baseline` | — | **not implemented, by design** (§4.6) |
| `login` | `auth.login` | §7.10 |
| `create_user` | `user_admin.create_user` | §7.10 |
| `create_project` | `project.create_project` | §7.10 *(platform admin; no auto-grant; ten series — D-32, R2-D14)* |
| `grant_access` · `reassign_access` · `list_effective_access` | `project.grant_access` / `project.reassign_access` / `project.effective_access` | §7.10 *(one grant per user — D-32, R2-S4)* |
| `list_visible_projects` | `access.visible_project_ids` | §7.8 |
| `enforce_project_scope` | `access.require_project` | §7.8 |
| `soft_delete_record` · `restore_record` | `lifecycle.soft_delete` / `lifecycle.restore` | §7.12 *(refuse with dependents; allow-list — R2-D2, R2-S5)* |
| `consistency_check` | `consistency_check` | §7.12 *(new — D11; inactive-parent check R2-D2; runs inside freeze R2-P6)* |
| `resolve_codes` | `code_master.resolve` | §7.12 *(new — D12)* |
| `preview_import` | `bulk.preview` | §7.11 *(new — P3)* |
| `maintain_rate_card` | `effort.maintain_rate_card` | §7.13 |
| `rate_function_requirement` | `effort.rate_function_requirement` | §7.13 |
| `effort_summary` | `reports.effort_summary` | §7.9 / §7.13 |
| `priced_diff` | `effort.priced_diff` | §7.13 |
| `create_benefit` · `link_benefit_solution` | `benefit.*` / `link_service.link` | §7.13 / §7.0 |
| `value_ranking` · `benefit_gap_report` | `benefit.value_ranking` / `reports.benefit_gap` | §7.13 |
| `raise_risk` · `score_risk` · `promote_risk_to_issue` · `risk_register` | `risk.*` | §7.13 |
| `raise_change_request` · `analyse_cr_impact` · `price_cr` · `decide_cr` | `change.*` | §7.13 |
| `record_decision` · `decision_log` | `decision.*` | §7.13 |
| `create_phase` · `assign_solution_phase` · `link_solution_dependency` · `phase_plan_report` | `phase.*` | §7.13 |
| `maintain_control_rule` · `control_panel` | `control.*` | §7.13 |
| `requirement_volatility` · `process_change_intensity` · `org_impact_heatmap` · `stakeholder_engagement` · `interface_load` · `data_migration_map` · `master_data_candidates` | `reports.*` | §7.9 |
| `create_program` · `update_program` · `move_project_program` | `program.*` | §7.10a *(new — D-32)* |
| `program_dashboard` · `program_counts` · `program_interfaces` · `program_effort` · `program_control_status` | `program.rollup` | §7.10a *(new — D-32, R2-S2)* |
| `download_template` / `validate_import` / `commit_import` (`wbs`) · `link_wbs_item` · `wbs_plan_vs_actual` | `bulk.*` (sixth map) / `wbs.link` / `wbs.plan_vs_actual` | §7.11a *(new — D-33)* |
| `purge_import_rows` | `bulk.purge_import_rows` | §7.12b *(new — Q14)* |
| — every Mermaid exporter | `render.escape_mermaid` | §7.12b *(new — R2-S7)* |
| — every route | `guards.*` (the guard registry) | §7.8 *(new — R2-S1)* |

```
link_service.link(user, project_id, parent_table, parent_id, child_table, child_id, **key):
    access.require_project(user, project_id, EDITOR)
    assert parent.project_id == project_id and child.project_id == project_id
    upsert junction(parent_id, child_id, **key)          # key = raci_code | direction
```
That `assert` is the reason every junction carries `project_id` and a composite FK: the
cross-project check is made twice, once in the service and once by the database (§5.6).

### 7.1 `services/numbering.py` → `next_number(db, project_id, entity_type, prefix, width)`

The one place any VB identifier is minted (§9.10). Called at commit, never on screen load
(§9.8).

```
lock row PROJECT_SEQUENCE(project_id, entity_type) FOR UPDATE
if absent: raise MissingSequence      # never insert lazily — create_project seeds all ten (R2-D14)
seq = row.last_value + 1
row.last_value = seq
return f"{prefix}-{seq:0{width}d}"        # DE-0001, BR-0001, FR-0001, ISS-0001
```
Gap-tolerant by design: a rolled-back transaction burns a number. Numbers are identifiers,
not counts — a gap is not a defect.

### 7.2 `services/bfc.py` → `create_node(...)`, `generate_code(node)`, `reorder(...)`

```
create_node(project_id, parent_id, name, requested_is_process=False):
    parent = get(parent_id) if parent_id else None
    level  = 1 if parent is None else parent.level + 1
    if level > 5: raise 422 "BFC is fixed at 5 levels"
    if parent and parent.is_process:
        raise 422 "A process has no children. Split it into sub-steps first"   # D-23 (DB-enforced too)
    assert_name_free(project_id, parent_id, name)                               # Q1
    is_process = (level == 5) or (requested_is_process and level in (3, 4))   # A-47, A-54
    seq_no = max(seq_no of parent's active children) + 1
    node   = insert(project_id, parent_id, level, seq_no, name, is_process)
    node.hier_code = generate_code(node)          # at save time
    if node.is_process:                           # D-2, D-23
        business_requirement.create_br(node)      # same transaction, exactly one
    return node

normalise_name(s):                                # Q1 — one definition, used by the flow import too
    return collapse_whitespace(unicodedata.normalize("NFKC", s)).strip().casefold()

assert_name_free(project_id, parent_id, name, except_id=None):
    if an ACTIVE sibling under parent_id has normalise_name(name), other than except_id:
        raise 409 f"'{name}' already exists under this parent ({sibling.hier_code})"
    # Called by create_node, rename (update_node) and restore. The DB backs it for process
    # steps: partial unique (parent_bfc_node_id, lower(btrim(node_name))) WHERE is_active AND
    # is_process (§5.3 BFC_NODE). This check is wider (every active sibling) and stricter
    # (NFKC, case-folded, whitespace collapsed), so it is the rule; the index is the backstop.

generate_code(node):
    walk parent chain to root, collect seq_no
    return ".".join(f"{s:02d}" for s in reversed(chain))   # 01.02.03.04.05

reorder(node, new_seq_no):                       # finding P7
    # Two-phase, because the declared mechanism and the declared algorithm were
    # incompatible: sibling 1→2 collides with the existing sibling 2 the moment the
    # UPDATE lands, and PostgreSQL cannot defer a PARTIAL unique index at all (nor any
    # unique *index* — only a unique *constraint*, which cannot be partial).
    with one transaction:
        UPDATE siblings SET seq_no = -seq_no WHERE parent = :p   # disjoint negative range
        UPDATE siblings SET seq_no = <target>                    # into place, no collision
        # S1-2: codes are two-phase too, and every SHIFTED sibling's subtree is re-coded.
        affected = ∪ {s} ∪ descendants(s) for s in siblings whose seq_no changed
        UPDATE affected SET hier_code = '~' || bfc_node_id       # cannot equal a dotted code
        for n in affected: n.hier_code = generate_code(n)
        AUDIT_EVENT(event_type='BFC_REORDERED', detail={node, from, to, subtree_size})

mark_process(node_id, is_process, row_version):          # D-23
    node = get(node_id); access.require_project(user, node.project_id, EDITOR)
    if is_process:                                        # promote
        if node.level not in (3, 4, 5): raise 422 "A process sits at level 3, 4 or 5"   # A-47
        if active children(node): raise 409 "This node has sub-steps; the lowest one is the process"
        with one transaction:
            UPDATE bfc_node SET is_process = TRUE WHERE id = :id AND row_version = :v   # 409 on 0
            business_requirement.create_br(node)          # D-2 — exactly one
    else:                                                 # demote
        if node.level == 5: raise 422 "A level-5 node is always a process"             # A-54
        blockers = active BR, step I/O, step roles, flow edges, external flows,
                   as-is application links, data_processing_desc on node
        if blockers: raise 409 f"Retire first: {blockers}"   # named, so the fix is obvious
        UPDATE bfc_node SET is_process = FALSE WHERE ... row_version = :v
    # REFUSAL, NEVER CASCADE (R2-P5, Q4). The service does not retire any blocker on the
    # consultant's behalf — not the BR, not an I/O row — because each one is a scope fact that
    # a later diff must be able to show was removed deliberately.
    # The database refuses the same demotion through the guard FKs (§5.3); the service
    # check exists to name the blockers instead of surfacing an FK violation.
```
Output data: one BFC node row with a stable dotted code, and a re-coded subtree on reorder;
on `mark_process`, the node's process flag and, on promotion, its single BR.

### 7.2a `services/process_flow.py` (D-20…D-22, D-31)

```
link_process_flow(project_id, from_id, to_id, flow_type, condition_label, seq_no):
    access.require_project(user, project_id, EDITOR)
    for n in (from_id, to_id) if not None:
        assert node.project_id == project_id and node.is_process      # D-23
    if flow_type == 'CONDITIONAL' and not condition_label:
        raise 422 "A conditional branch needs a label — a flow nobody can read is worse "
                  "than no flow"
    # Q2 — two edges between the same steps only with different conditions
    if an ACTIVE edge (from_id, to_id) exists whose normalise_name(condition_label or '')
       equals this one's, other than the edge being edited:
        raise 409 "These two steps are already joined under that condition. "
                  "Give the second edge a different condition, or edit the first"
    # NO cycle check. A rework loop is ordinary process behaviour, unlike a solution
    # dependency cycle (§7.13). This is the opposite rule to the table two along.
    if an INACTIVE twin (from_id, to_id, same normalised condition) exists:
        restore it and apply the edit                   # keeps source_bfc_node_flow_id stable
    else:
        insert BFC_NODE_FLOW(...)
    # The DB backs Q2 with uq_bfc_node_flow_edge: partial unique (from, to,
    # lower(btrim(condition_label))) NULLS NOT DISTINCT WHERE is_active (§5.3 BFC_NODE_FLOW).

generate_process_flow(bfc_node_id, variant='AS_IS'):
    access.require_project(user, node.project_id, REVIEWER)
    if node.is_process: raise 422 "A process flow is drawn for a parent node, not a step"

    steps = process descendants of node, active                    # D-23, any level
    return {
      "nodes": [ {                                  # the process boxes
          id, hier_code, node_name, data_processing_desc,
          br_number, br_statement,                  # from BUSINESS_REQUIREMENT (1:1, D-2)
          lane:    the ORG_ROLE whose RACI code has behaviour RESPONSIBLE on that step,
                   or None → the "unassigned" lane               # swimlane — R2-D9, A-46
          system:  AS_IS  -> APPLICATION via APPLICATION_BFC_NODE
                   TO_BE  -> APPLICATION via BR_SOLUTION -> APPLICATION_SOLUTION,
        } for s in steps ],
      "edges": [ {from, to, flow_type, condition_label, seq_no,
                  is_external: to-node outside `steps`} ],      # HANDOFF leaves the frame
      "lanes": distinct ORG_ROLE grouped by ORG_UNIT, ordered by org hierarchy,
      "stores": [ {data_entity_id, de_number, de_name,
                   reads:  steps with direction 'I',
                   writes: steps with direction 'O'} ],         # BFC_NODE_DATA_ENTITY
      "externals": [ {ext_number, name, flows: BFC_NODE_EXTERNAL_FLOW rows} ],   # D-24a
      "layout": DIAGRAM_LAYOUT rows for ('PROCESS_FLOW', bfc_node_id),           # D-30
      "visited_guard": true,      # traversal is visited-set bounded — cycles are legal
    }
    # A GRAPH, NOT A PICTURE (D-21). The backend returns saved positions where a consultant
    # placed something (D-30) and nothing else; auto-layout of the rest is the frontend's job.

export_process_flow(bfc_node_id, variant, format='mermaid'):
    g = generate_process_flow(bfc_node_id, variant)
    render g as a Mermaid flowchart: one `subgraph` per lane, `-->|label|` for conditional
    edges, cylinder shapes for stores, dashed edges for HANDOFF
    node ids are generated ("s" + bfc_node_id, "d" + data_entity_id) — never user text
    EVERY label — step name, lane, condition, store, external party — through
        render.escape_mermaid()                                   # R2-S7, §7.12b
    # For pasting into a deck or a report. The same graph, as text. export_dfd and
    # export_erd use the same renderer rules; there is no second label path.

flow_completeness_report(project_id):
    return {
      "orphan_steps":     process nodes with neither inbound nor outbound edge,
      "no_start":         parent nodes whose steps have no start event,
      "no_end":           ... no end event,
      "unlabelled_branch": CONDITIONAL edges with no condition_label,
      "dangling_handoff": HANDOFF edges whose far end is inactive,
      "no_output":        process steps with no output data entity,             # D-24
      "no_lane":          process steps with no RESPONSIBLE role                # A-46, R2-D9
      "crud_without_io":  BR_DATA_ENTITY rows with no matching step I/O row,    # must be 0
      "ext_without_io":   BFC_NODE_EXTERNAL_FLOW rows naming a DE with no matching
                          step I/O row,                                         # must be 0 (R2-D13)
    }

generate_dfd(bfc_node_id):                          # D-31 — the same rows, no sequence
    access.require_project(user, node.project_id, REVIEWER)
    steps = process descendants of node, active
    return {
      "processes": [ {id, hier_code, node_name} for s in steps ],
      "stores":    DATA_ENTITY rows in any step's I/O,
      "externals": EXTERNAL_ENTITY rows in any step's BFC_NODE_EXTERNAL_FLOW,
      "flows":     one per BFC_NODE_DATA_ENTITY row   (store → step if 'I', step → store if 'O')
                 + one per BFC_NODE_EXTERNAL_FLOW row (party ↔ step, labelled with the DE),
      "cross_area": stores written in one L1 area and read in another,
      "layout":    DIAGRAM_LAYOUT rows for ('DFD', bfc_node_id),
    }
    # No BFC_NODE_FLOW read at all. A DFD shows what data moves, not in what order;
    # the process flow shows the order. Two pictures, one set of rows (D-24).
```

### 7.2b `services/flow_import.py` — process flow JSON (D-25)

**The file format is the contract, so it is versioned and published.** `vb-process-flow/1.0`
is a JSON Schema served by `download_flow_schema`, together with a worked example and the
**AI conversion prompt pack** — the rules an AI follows to turn a slide, a BPMN export or a
Visio diagram into a valid file. The consultant runs the conversion in the AI tool they
choose; VB receives only the resulting JSON.

```json
{
  "format": "vb-process-flow/1.0",
  "parent": { "hier_code": "01.02.03", "name": "Order to cash — order capture" },
  "mode":   "merge",
  "lanes":  [ { "key": "L1", "org_role": "Sales administrator", "org_unit": "Sales Ops" } ],
  "external_entities": [ { "key": "X1", "ext_number": null, "name": "Customer", "kind": "CUSTOMER" } ],
  "data_entities":     [ { "key": "D1", "de_number": "DE-0007", "name": "Sales order" } ],
  "steps": [
    { "key": "S1", "br_number": "BR-0012", "hier_code": "01.02.03.01", "row_version": 4,
      "name": "Receive order", "lane": "L1",
      "description": "…", "inputs": ["D1"], "outputs": ["D1"],
      "external_flows": [ { "external": "X1", "direction": "I", "data_entity": "D1" } ],
      "source_ref": "slide 4, shape 12" },
    { "key": "S2", "br_number": null, "hier_code": null, "row_version": null,
      "name": "Check credit", "lane": "L1",
      "description": "…", "inputs": ["D1"], "outputs": [],
      "source_ref": "slide 4, shape 15" }
  ],
  "flows": [
    { "from": null, "to": "S1", "type": "SEQUENCE" },
    { "from": "S1", "to": "S2", "type": "CONDITIONAL", "condition": "Credit check failed" }
  ]
}
```

Rules the schema and the prompt pack both state — **keys are local to the file**, and
business keys (`BR-`, `DE-`, `EXT-`) are how the file meets the database:

1. **A step with a `br_number` updates that BR's process node** (R2-D1). The BR number never
   changes; `hier_code` does, on every reorder (D-10). If the file also carries a `hier_code`,
   it must equal the node's current one, or the step is an error: "BR-0012 moved since
   export: now 01.02.05, file says 01.02.03 — re-export". A `row_version` that is not the
   node's current one is an error that names the current values (R2-D5). **A step with a
   `hier_code` and no `br_number` is an error** — `hier_code` is a cross-check, not an
   identity.
2. **A step with neither is matched by name** (R2-P1). If an active process node **directly
   under the anchor** has the same normalised name (Q1 makes it unique), the step **updates
   it**, with the warning "matched existing step 01.02.03.04 by name". Otherwise the step is
   **created** as a new process node under the anchor, with its BR in the same transaction
   (D-2, D-23). An AI conversion never knows BR numbers, so without this rule every re-run of
   the same slide would duplicate every step.
3. A data entity with a `de_number` must exist in this project. One without a number is
   matched by exact name; no match is **created**, and listed by name in the preview.
4. A lane must match one active `ORG_ROLE` by name; no match is an **error**. Org roles are
   people's jobs, and the same rule as stakeholders applies — never created from a file.
   **The lane is the step's one RESPONSIBLE role: the file's lane replaces it, and no other
   role on the step is touched** (R2-P4, R2-D9).
5. `from: null` is a start event, `to: null` an end event. `CONDITIONAL` needs `condition`.
   Two flows between the same two steps need different conditions (Q2).
6. **The anchor node and the mode are chosen in VB, not by the file** (R2-P3). `parent` and
   `mode` in the file are checked against them, and a mismatch rejects the file. A file cannot
   aim itself at a different branch, or turn itself into a replace.
7. `mode: "merge"` (default) never retires anything. **`mode: "replace"` retires only flow
   edges and step I/O** (Q5): edges leaving a process step under the anchor that the file
   omits, and I/O rows of the file's steps that the file omits. **An I/O row that a BR CRUD or
   an external flow depends on is kept**, with a warning naming the dependent. Steps, BRs,
   roles other than the lane, and external flows are never retired by an import. Every
   RETIRE row is listed in the preview, and the retire count must be acknowledged.
8. `source_ref` is kept on the staged row so the preview can say *which shape on which
   slide* a problem came from — that is what makes an AI conversion checkable by a human.

```
validate_process_flow_json(project_id, anchor_bfc_node_id, mode, file):   # R2-P3: route-carried
    # guard: project_ctx(EDITOR) — the route declares it (§9)
    anchor = bfc_node(anchor_bfc_node_id)
    if anchor is None or anchor.project_id != project_id or not anchor.is_active: raise 404
    if anchor.is_process: raise 422 "A flow is imported under a parent node, not a step"
    if mode not in ('merge', 'replace'): raise 422
    enforce_json_limits(file)                      # §7.12a — bytes, depth, steps, flows
    doc = json.loads(file, parse_constant=reject)  # no NaN/Infinity
    jsonschema.validate(doc, VB_PROCESS_FLOW_1_0)  # structural errors → 422, nothing staged
    if doc.parent.hier_code != anchor.hier_code:
        raise 422 f"This file is for {doc.parent.hier_code}; you chose {anchor.hier_code}. "
                  "If the node moved since export, re-export it"
    if doc.get('mode', 'merge') != mode:
        raise 422 f"The file says '{doc.mode}', you chose '{mode}'. Nothing was staged"

    batch = INSERT IMPORT_BATCH(target_entity='PROCESS_FLOW', anchor_bfc_node_id=anchor.id,
                                import_mode=mode.upper(), source_format=doc.format, ...)
    under    = active process descendants of anchor                  # D-23, any level
    by_name  = {normalise_name(n.node_name): n for n in active process CHILDREN of anchor}
    resolved = {}                                                   # file step key → node | NEW

    for s in doc.steps:
        errors, warnings = [], []
        if s.br_number:                                             # rule 1 — R2-D1
            br = active BR (project_id, s.br_number)
            if br is None: errors += [f"{s.br_number} is not a BR in this project"]
            elif br.node not in under:
                errors += [f"{s.br_number} belongs to {br.node.hier_code}, outside this flow"]
            else:
                node = br.node
                if s.hier_code and s.hier_code != node.hier_code:
                    errors += [f"{s.br_number} moved since export: now {node.hier_code}, "
                               f"file says {s.hier_code}. Re-export"]
                if s.row_version != node.row_version:               # R2-D5
                    errors += [f"Step changed since export. Current: {node.node_name!r}, "
                               f"lane {current_lane(node)}, description {node.data_processing_desc!r}"]
                verdict, target = 'UPDATE', node
        elif s.hier_code:
            errors += ["hier_code is a cross-check, not an identity — add br_number (export "
                       "the flow to get it)"]
        elif (m := by_name.get(normalise_name(s.name))):            # rule 2 — R2-P1
            verdict, target = 'UPDATE', m
            warnings += [f"Matched existing step {m.hier_code} {m.node_name!r} by name — it "
                         "will be updated, not duplicated"]
        else:
            verdict, target = 'INSERT', NEW
        if target in resolved.values() and target is not NEW:
            errors += ["Two steps in this file resolve to the same process node"]
        if normalise_name(s.name) is repeated among the file's steps:
            errors += ["Two steps in this file have the same name under one parent (Q1)"]
        before_after = diff(target: name, description, lane) if verdict == 'UPDATE'   # R2-D5
        resolved[s.key] = target
        INSERT IMPORT_ROW(..., row_kind='STEP', verdict, payload={…, before_after}, source_ref,
                          is_valid=not errors, error_detail=errors, warning_detail=warnings)

    for lane, external, data_entity, flow: resolve per rules 3–5
        errors   += unresolvable references, duplicate keys, lane not found,
                    duplicate (from, to, condition) (Q2)
        warnings += new data entity to be created, step with no output,
                    orphan step, flow into a step with no inputs

    if mode == 'replace':                                          # rule 7 — R2-P4, Q5
        for e in active BFC_NODE_FLOW whose from-node is in `under` (or, for a start event,
                 whose to-node is), not matched by any file flow:
            INSERT IMPORT_ROW(row_kind='FLOW_EDGE', verdict='RETIRE', target=e)
        for io in active BFC_NODE_DATA_ENTITY on the file's resolved steps, not in the file:
            deps = active BR_DATA_ENTITY needing io  ∪  active BFC_NODE_EXTERNAL_FLOW needing io
            if deps: INSERT IMPORT_ROW(row_kind='STEP_IO', verdict='KEPT', target=io,
                                       warning_detail=[f"Kept: {names(deps)} depend on it"])
            else:    INSERT IMPORT_ROW(row_kind='STEP_IO', verdict='RETIRE', target=io)
        # NEVER staged for retirement: steps, BRs, roles other than the lane, external flows.

    batch.insert_count = count(verdict='INSERT'); batch.update_count = count(verdict='UPDATE')
    batch.retire_count = count(verdict='RETIRE'); batch.error_count  = count(not is_valid)
    return batch summary                      # nothing has touched a business table

preview(batch_id):   # the §7.11 preview, plus: every RETIRE row listed by business key and
                     # description ("edge BR-0012 → BR-0015, 'Credit check failed'"), every KEPT
                     # row with its warning, and before/after for every UPDATE step (R2-P3, D5)

commit_process_flow_json(batch_id, confirm):
    same lock / status / full re-validation as bulk.commit (§7.11), including
        acknowledged_inserts == insert_count  whenever insert_count > 0    # R2-P1, R2-P2
        acknowledged_retires == retire_count  whenever retire_count > 0
        the RETIRE set RE-COMPUTED inside the lock; if it differs from the staged set,
        abort with 409 "The flow changed since preview — validate again"
    with one transaction, in dependency order:
        EXTERNAL_ENTITY, DATA_ENTITY (new ones)     # numbers minted HERE (§9.8)
        BFC_NODE (new steps, is_process = TRUE) + their BUSINESS_REQUIREMENT
        UPDATE steps: name (assert_name_free), description — WHERE row_version = :v   # 409 on 0
        BFC_NODE_DATA_ENTITY via bfc.ensure_step_io
        BFC_NODE_EXTERNAL_FLOW via bfc.link_external_flow            # ensures I/O too (R2-D13)
        lanes: for each step with a lane —
            r = the project's RESPONSIBLE-behaviour RACI code (code_master.resolve, A-60)
            retire the step's current RESPONSIBLE role if it differs; ensure (step, lane role, r)
            # no other role on the step is read or written (R2-P4)
        BFC_NODE_FLOW (via link_process_flow's rules, incl. Q2)
        RETIRE rows: soft-delete each edge / I/O row, re-checking it has no dependent
    AUDIT_EVENT('IMPORT_COMMITTED', {entity: 'PROCESS_FLOW', anchor, mode, counts…})
```

**Why the pipeline is reused rather than a second importer:** the six properties of §7.11 —
separate validate and commit, all-or-nothing, numbers at commit, project-scoped keys,
re-validation inside the lock, approval of consequences — matter *more* for an
AI-produced file than for a hand-typed spreadsheet, because nobody typed it.

**As-is versus to-be is one definition rendered twice (D-22).** The steps, the lanes and the
data stores are the same; only the `system` on each box changes, because `AS_IS` resolves
through `APPLICATION_BFC_NODE` and `TO_BE` through `BR_SOLUTION → APPLICATION_SOLUTION`.
**The difference between the two pictures is the transformation**, which is exactly the
slide a consultant needs and previously had to draw by hand.

### 7.3 `services/business_requirement.py` → `create_br(...)`, `link_data_entity(...)`

```
create_br(project_id, bfc_node_id, statement, logic_text):
    node = get(bfc_node_id)
    if not node.is_process: raise 422 "A business requirement attaches to a process step"   # D-23
    br_number = numbering.next_number(db, project_id, "BR", "BR", 4)
    return insert(...)

link_data_entity(br_id, data_entity_id, crud_code):
    if crud_code not in ('C','R','U','D'): raise 422
    direction = 'I' if crud_code == 'R' else 'O'
    with one transaction:                                              # D-24
        bfc.ensure_step_io(br.bfc_node_id, data_entity_id, direction)  # the ONE helper (R2-D13)
        upsert BR_DATA_ENTITY(br_id, data_entity_id, crud_code)
    # The BR and the process flow cannot disagree: the step I/O the flow shows is created
    # with the CRUD that needs it, and bfc.unlink_data_entity refuses to remove it while
    # any BR CRUD or external flow still depends on it (409, naming each).
    # direction is a GENERATED column: 'R' → INPUT, else OUTPUT.
    # One BR reading AND updating the same entity is two rows — the normal case,
    # and the reason crud_code sits in the primary key.
```
Output data: one BR row; one BR↔DE row per CRUD operation, with direction derived.

```
bfc.ensure_step_io(bfc_node_id, data_entity_id, direction):          # R2-D13 — one helper
    node = get(bfc_node_id); assert node.is_process and node.is_active
    assert data_entity in node.project_id and active
    row = BFC_NODE_DATA_ENTITY(bfc_node_id, data_entity_id, direction)
    if row is None: insert it
    elif not row.is_active: re-activate it (audited as a restore)
    return row
    # Called by: business_requirement.link_data_entity, bfc.link_external_flow,
    # flow_import.commit, and the step I/O editor. Nothing else writes step I/O.

bfc.link_external_flow(bfc_node_id, external_entity_id, direction, data_entity_id | None):
    access.require_project(user, node.project_id, EDITOR)
    assert external entity and data entity (if given) in node.project_id
    with one transaction:
        if data_entity_id:
            bfc.ensure_step_io(bfc_node_id, data_entity_id, direction)   # I needs input, O output
        upsert BFC_NODE_EXTERNAL_FLOW(bfc_node_id, external_entity_id, direction, data_entity_id)

bfc.unlink_data_entity(bfc_node_id, data_entity_id, direction, row_version):
    crud = active BR_DATA_ENTITY on this node's BR, same DE, same direction
    ext  = active BFC_NODE_EXTERNAL_FLOW on this node, same DE, same direction
    if crud or ext:
        raise 409 f"Still needed by {[b.br_number + ' ' + b.crud_code for b in crud]
                                    + [x.ext_number + ' ' + x.direction for x in ext]}"
    soft-delete the row WHERE row_version = :v
```
Output data: one step I/O row per (step × entity × direction), created only by the helper
and removed only when nothing depends on it. **An external flow and a BR CRUD are now the same
kind of dependent.** Before R2-D13, a DFD could show an external party feeding a step data the
step did not take in.

**D-2 in the service:** `create_bfc_node` for a process node (and `mark_process`, D-23)
creates the node's single BR in the same transaction. `create_br` is never called from a router — there is no "add requirement"
button — and `UNIQUE (bfc_node_id)` makes a second one impossible even by direct SQL. The
consultant edits the requirement that appeared with the step.

```
update_br(br_id, fields, row_version):            # D-6
    n = UPDATE business_requirement
        SET ..., row_version = row_version + 1
        WHERE br_id = :id AND row_version = :v
    if n == 0: raise 409 "This requirement was changed by someone else. Reload and reapply."
```
Every editable business table takes the same shape. The 409 is already in the playbook error
table (§7 doctrine); D-6 is what makes it reachable.

### 7.4 `services/data_entity.py` → `create_entity(...)`, `upsert_field(...)`

```
upsert_field(data_entity_id, field):
    # D-26: logical. data_type_code optional; is_mandatory ∈ TRUE / FALSE / NULL (unknown)
    if field.data_type_code: validate_required_code("FIELD_DATA_TYPE", field.data_type_code)
    if field.is_primary_key and field.pk_ordinal is None: raise 422
    if field.is_foreign_key:
        if field.fk_target_entity_id is None: raise 422 "FK field needs a target entity"
        target = get(field.fk_target_entity_id)
        if target.project_id != entity.project_id: raise 422 "cross-project FK"
    enforce unique (data_entity_id, field_name) among active fields
```
Output data: one data field row, with the PK/FK metadata that makes the DE list a real
logical model rather than a glossary.

```
generate_erd(project_id, subject_area_node_id=None):              # D-29
    access.require_project(user, project_id, REVIEWER)
    entities = active DATA_ENTITY in project
    if subject_area_node_id:
        entities = those in the I/O of any process under that node   # subject area
    return {
      "entities": [ {id, de_number, de_name,
                     fields: [pk fields by pk_ordinal] + [fk fields] + [attributes],
                     field_count} ],
      "relationships": [ {
          from_entity: child (holds the FK), to_entity: parent,
          via_field_ids: the FK field(s) — composite FKs grouped by ref target,
          parent_cardinality: '1' if every FK field is_mandatory else '0..1',
          child_cardinality:  '1' if FK field set == child PK field set, else 'many',   # no AK column exists
          identifying: FK fields are part of the child's PK,           # solid vs dashed
      } ],
      "outside_refs": FKs from an entity in scope to one outside it  # drawn as a stub
      "layout": DIAGRAM_LAYOUT rows for ('ERD', scope_key),
    }
```
A logical ERD, deliberately: relationships come only from FK fields the consultant
declared, so the diagram is exactly as complete as the model. An entity with no key fields
is drawn with a warning badge rather than hidden.

### 7.5 `services/solution.py`, `function_requirement.py`, `application.py`

```
create_solution(project_id, name, description, category_code):     # D-7
    validate_required_code("SOLUTION_CATEGORY", category_code)
    # ORG_AND_RULES | PEOPLE | PROCESS | DATA | TECHNOLOGY
    solution_number = numbering.next_number(db, project_id, "SOL", "SOL", 4)
    return insert(...)

create_fr(project_id, solution_id | None, name, description, fr_type_code,
          suggested_br_id | None = None):                            # D-34
    validate_required_code("FR_TYPE", fr_type_code)          # project-editable — D-27
    fr_number = numbering.next_number(db, project_id, "FR", "FR", 4)
    if suggested_br_id:
        assert BR(suggested_br_id).project_id == project_id and active
        if solution_id and path_exists(suggested_br_id, solution_id):   # active BR_SOLUTION
            suggested_br_id = None                                      # already traced
    fr = insert(..., solution_id=solution_id, suggested_br_id=suggested_br_id)
    if solution_id is None:
        warn("No solution, so no business requirement — this FR is not traced")   # D-28
        if suggested_br_id: warn(f"Suggested link to {br.br_number} kept until a solution "
                                 "that answers it is linked")
    else:
        solution = get(solution_id); assert solution.project_id == project_id
        if solution.category_code not in ('TECHNOLOGY', 'DATA'):
            warn("Function requirement on a non-technology solution")   # a finding, not a block
    return fr

describe_interface(fr_id, source_app_id, target_app_id, pattern, method, frequency,
                   volume_note, data_entity_ids, row_version):          # D-27
    fr = get(fr_id)
    if code_master.behaviour(fr.fr_type_code) != 'INTERFACE':
        raise 422 "Only an interface-type FR carries interface detail"
    assert both applications in fr.project_id and source_app_id != target_app_id
    upsert FR_INTERFACE(...) WHERE row_version = :v        # 409 on mismatch (D-6)
    replace FR_INTERFACE_DATA_ENTITY set for fr_id

change_fr_type(fr_id, new_type, row_version):
    if behaviour(old) == 'INTERFACE' and behaviour(new) != 'INTERFACE' and FR_INTERFACE exists:
        raise 409 "This FR has interface detail. Remove it first, or keep an interface type"
    re-derive effort_days from the rate card for (new_type, complexity)   # D-13

link_fr_solution(fr_id, solution_id | None, row_version):             # D-28, D-34, R2-D16
    access.require_project(user, fr.project_id, EDITOR)
    assert solution (if given) in fr.project_id
    UPDATE function_requirement SET solution_id = :s WHERE ... row_version = :v   # 409 on 0
    if fr.suggested_br_id:
        if solution_id and path_exists(fr.suggested_br_id, solution_id):
            fr.suggested_br_id = None                              # the suggestion is now true
        else:
            return {fr, prompt: f"{br.br_number} is not answered by {sol.solution_number}. "
                                "Link them?", action: POST /business-requirements/{br}/solutions}
    return {fr}

on BR_SOLUTION linked (br_id, solution_id):                         # in link_service, same tx
    UPDATE function_requirement SET suggested_br_id = NULL
     WHERE solution_id = :s AND suggested_br_id = :br AND is_active
    # The ONLY places the suggestion clears: these two, and retiring the suggested BR
    # (lifecycle.soft_delete clears it, listed in the retire response, §7.12). It is
    # never cleared by guesswork.

maintain_fr_types(project_id, code, label, behaviour_code):          # D-27
    if code already exists as a GLOBAL FR_TYPE and this project has no override yet:
        with one transaction:                                    # §5.3 EFFORT_RATE, A-16
            override = insert CODE_MASTER(project_id, 'FR_TYPE', code, label, behaviour_code)
            UPDATE effort_rate          SET fr_type_code_id = override.code_id
             WHERE project_id = :p AND fr_type_code_id = global.code_id
            UPDATE function_requirement SET fr_type_code_id   = override.code_id,
                                            fr_type_behaviour = override.behaviour_code
             WHERE project_id = :p AND fr_type_code_id = global.code_id
    # Without the re-point, rate rows seeded against the global code_id stop matching the
    # override and every new FR of that type gets a 422 from rate_function_requirement.

maintain_global_fr_type(code_id, label, behaviour_code):             # platform admin
    g = CODE_MASTER(code_id) where project_id IS NULL and category = 'FR_TYPE'
    if behaviour_code != g.behaviour_code and (
           exists FUNCTION_REQUIREMENT with fr_type_code_id = g.code_id   # any project
        or exists EFFORT_RATE          with fr_type_code_id = g.code_id):
        raise 409 "This type is in use, so its behaviour is fixed. Add a new type instead"
        # R2-D8, Q6. A global behaviour change would re-behave FRs in every project that
        # never overrode it — interface FRs dropping off interface lists they were agreed on.
    update label (always allowed — labels are presentation, and baselines keep their own)
```
The FR form shows the **type-specific panel by behaviour, not by code** — a project that
renames INTERFACE to "連携" or adds "API" with behaviour INTERFACE gets the interface panel
and the interface list without a code change.

```
link_node(fr_id, bfc_node_id):                    # FR_BFC_NODE — apple's §5.4.3 rule
    if bfc_node_id in nodes_reachable_via(fr.solution_id):
        raise 422 "Already covered through this FR's solution — do not store it twice"
    upsert FR_BFC_NODE(fr_id, bfc_node_id)

create_application(project_id, code, name, vendor, kind_code, lifecycle_code):   # D-8
    validate_required_code("APP_LIFECYCLE", lifecycle_code)   # AS_IS | TO_BE | BOTH
    return insert(...)

application.link_solution(application_id, solution_id):
    app = get(application_id)
    if app.lifecycle_code == 'AS_IS':
        raise 422 "An as-is-only application cannot be allocated as a to-be answer"
    upsert APPLICATION_SOLUTION(application_id, solution_id)
```
Output data: the transformation answer set, categorized across the five operating-model
dimensions; the vendor-facing function list grouped by FR type; the generated interface
list; and the target application landscape.

**BR → FR is a view, not a table** (D-7):
```sql
CREATE VIEW v_br_function_requirement AS
SELECT bs.br_id,
       fr.fr_id,
       fr.fr_number,
       fr.fr_type_code_id,                          -- D-27 (was category_code_id)
       fr.fr_type_behaviour,
       s.solution_id,
       s.category_code_id AS solution_category_code_id
FROM   br_solution bs
JOIN   solution s              ON s.solution_id = bs.solution_id
JOIN   function_requirement fr ON fr.solution_id = s.solution_id
WHERE  bs.is_active AND s.is_active AND fr.is_active;
-- D-28: an FR with solution_id NULL never appears here, which is the correct answer to
-- "which FRs serve this BR". Unlinked FRs are listed by coverage.fr_unlinked instead.
```

### 7.6 `services/issue.py` → `raise_issue(...)`, `resolve_issue(...)`

```
stakeholder.upsert(project_id, name, job_title, org_unit_id, email, is_bpo):   # D-4
    # a named client-side person with no login. Matched on (project_id, lower(name))
    # by the importer; created if absent.

raise_issue(project_id, title, description, severity_code, issue_type_code,
            raised_by_stakeholder_id, br_ids):
    access.require_project(user, project_id, EDITOR)
    if raised_by_stakeholder_id is None: raise 422 "An issue needs a raiser"   # D8
    validate_required_code for each of the three category fields
    issue_number = numbering.next_number(db, project_id, "ISSUE", "ISS", 4)
    issue = insert(..., status_code="OPEN",
                   raised_by_stakeholder_id=raised_by_stakeholder_id,  # the business user
                   recorded_by_user_id=jwt.user_id)                    # the consultant
    for br_id in br_ids: insert ISSUE_BR(issue.id, br_id)

resolve_issue(issue_id, resolution, row_version):
    access.require_project(user, issue.project_id, EDITOR)
    if not resolution.strip(): raise 422 "A resolution is required to close an issue"
    issue.status_code = "RESOLVED"
    issue.resolved_at = now()                      # timestamptz — see A-33 on timezone
    issue.resolved_by_user_id = jwt.user_id        # reconciled: no `resolved_date` (D8)
```

### 7.7 `services/baseline.py` → `freeze(...)`, `diff(...)`

The scope-control core. One transaction; partial baselines are not a state that can exist.

```
freeze(project_id, note, bump, confirm_text):
    # ---- finding P1, R2-P6: ONE snapshot, from the FIRST statement ----
    with db.connection(isolation_level='REPEATABLE READ') as tx:   # set BEFORE any query
        # SET TRANSACTION ISOLATION LEVEL must precede every statement in the transaction,
        # and PostgreSQL takes the snapshot at the first one. The first draft set it AFTER
        # require_project and consistency_check had already run — so it either raised
        # ("must be called before any query") or, on a pooled connection, silently
        # checked one state of the data and froze another.
        access.require_project(user, project_id, OWNER, db=tx)   # finding P6 — OWNER only
        if confirm_text != f"{project.project_code} {next_label}":
            raise 422 "Type the project code and version to confirm"      # P6
        if consistency_check(project_id, db=tx).has_errors:              # SAME transaction
            raise 409 "Chart is inconsistent; resolve before freezing"    # D11 precondition
        # Under READ COMMITTED each SELECT in the loop below takes a NEW snapshot, so an edit
        # committed mid-freeze lands in some shadow tables and not others — or produces a
        # snapshotted BR whose parent node was never captured. And a check run in a separate
        # transaction proves nothing about the data the freeze then reads.

        prior = latest BASELINE for project
        major, minor = (1, 0) if prior is None else (
            (prior.major_no + 1, 0) if bump == 'MAJOR' else (prior.major_no, prior.minor_no + 1))
        # finding P9 — integers, not string arithmetic. bump_minor("v1.9") had no defined answer.
        baseline = insert(project_id, major_no=major, minor_no=minor,
                          version_label=f"v{major}.{minor}",     # rendered, never parsed
                          hash_spec_version=CURRENT_HASH_SPEC,   # finding D5
                          frozen_at=now(), frozen_by=jwt.user_id,
                          status="FROZEN", note=note)
        # a duplicate (project, major, minor) surfaces as 409, not an unhandled integrity error
        for each entity in FREEZE_SET:                 # the 30 shadow tables of §6.1, in FK order
            # ORG_UNIT, ORG_ROLE, BFC_NODE, DATA_ENTITY, DATA_FIELD, EXTERNAL_ENTITY,
            # BFC_NODE_DATA_ENTITY, BFC_NODE_ORG_ROLE, BFC_NODE_FLOW, BFC_NODE_EXTERNAL_FLOW,
            # BUSINESS_REQUIREMENT, BR_DATA_ENTITY, BR_ORG_ROLE, APPLICATION, SOLUTION,
            # BR_SOLUTION, FUNCTION_REQUIREMENT, FR_INTERFACE, FR_INTERFACE_DATA_ENTITY,
            # FR_BFC_NODE, APPLICATION_SOLUTION, APPLICATION_BFC_NODE, ISSUE, ISSUE_BR,
            # BENEFIT, BENEFIT_SOLUTION, PHASE, SOLUTION_PHASE, SOLUTION_DEPENDENCY,
            # EFFORT_RATE (R2-D7 — the rate card the baseline was priced on)
            for row in live rows where project_id = ? and is_active = TRUE:
                insert snapshot(baseline_id=baseline.id, source_id=row.id, **copy of columns)
        AUDIT_EVENT(event_type='BASELINE_FROZEN', project_id, detail={version_label, counts})
        return baseline

diff(baseline_a, baseline_b):
    # finding S3 — resolve BOTH baselines' project and prove they match, before anything
    if a.project_id != b.project_id: raise 404
    access.require_project(user, a.project_id, REVIEWER)

    if a.hash_spec_version != b.hash_spec_version:
        return {"error": "SCHEMA_VERSION_MISMATCH", ...}    # finding D5(b): report it as
        # itself, never as "the entire project CHANGED"

    for each snapshot entity type:
        full outer join A to B on source_id
            A missing → ADDED
            B missing → REMOVED
            both, content_hash differs      → CHANGED + the differing column names
            both, content_hash equal but
              (hier_code | seq_no) differs  → MOVED                     # finding P4
    return { entity_type: [ {source_id, change_type, fields[]} ] }
```
Output data: an immutable baseline, and a scope-change report between any two baselines —
which is the actual deliverable of scope control.

**`content_hash`, specified (finding D5).** The first draft named it in §5.4.4 and defined a
second, different diff algorithm in this section. One algorithm survives — the one above —
and the hash is pinned:

```
content_hash = sha256( "\x1f".join(
        NULL_SENTINEL if v is None else str(v)
        for v in HASH_COLUMNS[entity][hash_spec_version] ) )
```
- **An explicit, versioned column list per entity**, stored as `baseline.hash_spec_version`.
  Without it, the CI column-parity test (§6.5) *forces* a new live column into the shadow
  table, the hashed column set changes, and every row in the next baseline differs from its
  v1.0 counterpart — the whole project reads as CHANGED with no way to tell schema change
  from scope change.
- **`\x1f` as the separator and a distinct NULL sentinel.** Naive concatenation makes
  `("Approve", NULL, "Claim")`, `("Approve", "", "Claim")` and `("ApproveClaim", NULL, NULL)`
  hash identically — so emptying a field reads as unchanged, silently and forever.
- **`hier_code` and `seq_no` are excluded** (D-10). They are position, not content. With them
  in the hash, reordering `01.02` reported 48 process steps CHANGED and buried the one real
  change among them.
- **Codes, never labels** (R2-D3). `HASH_COLUMNS` lists the code value of every coded column
  (`fr_type_code`, `complexity_code`, `severity_code`, …), never the label copied into the
  snapshot for display (§5.4.4). A `code_master` relabel — "High" to "Major" — is
  presentation, not scope. Hashing the label made every issue in the project read CHANGED at
  the next freeze, and the priced diff re-priced FRs whose effort had not moved.
- **`suggested_br_id` is excluded** (D-34). A suggestion is a to-do for the consultant, not
  agreed scope. Clearing it must not report the FR as CHANGED.

### 7.8 `services/access.py` → `visible_project_ids(user)`, `require_project(user, project_id, min_role)`

The single visibility guard (§9.10, §9.11). Every list and detail query in the app passes
through it.

**The role model (D-9, finding S1).** The first draft defined Admin / Consultant / Client
Reviewer as a table and then wrote OWNER / EDITOR / VIEWER into this pseudocode and the
acceptance criteria, with `rank()` undefined. One vocabulary now:

- **Platform tier:** `app_user.is_platform_admin` — a boolean. True sees every project.
- **Project tier:** `user_access_grant.project_role_code` ∈ **OWNER / EDITOR / REVIEWER** — one active grant per user, over one project or one program (D-32).

```python
PROJECT_ROLE_RANK = {"REVIEWER": 1, "EDITOR": 2, "OWNER": 3}   # rank(), defined
```

| Operation | OWNER | EDITOR | REVIEWER |
|---|:--:|:--:|:--:|
| Read anything in the project | ✓ | ✓ | ✓ |
| Create / edit BFC, DE, BR, Solution, FR, Application, Issue, Stakeholder | ✓ | ✓ | ✗ |
| Soft-delete and restore a business row | ✓ | ✓ | ✗ |
| Reorder the BFC chart | ✓ | ✓ | ✗ |
| Upload, validate and **commit** an import batch | ✓ | ✓ | ✗ |
| Download / export | ✓ | ✓ | ✓ |
| **Freeze a baseline** | ✓ | ✗ | ✗ |
| Grant / revoke project access | ✓ | ✗ | ✗ |
| See effective access to the project (incl. program-derived) | ✓ | ✗ | ✗ |
| Link a WBS line to a phase / solution | ✓ | ✓ | ✗ |
| Program roll-ups — **only through a program grant**, at that grant's role | ✓ | ✓ | ✓ |
| Grant a **program**, reassign a user, move a project between programs | platform admin only | | |

A platform admin passes every check. **Creating a project grants nobody anything** (D-32): only
a platform admin creates one, and a platform admin needs no grant. **A user holds at most one
active grant, naming one project or one program** (`USER_ACCESS_GRANT`: `num_nonnulls(project_id,
program_id) = 1`, partial unique on `app_user_id WHERE is_active`, §5.3). A program grant carries one
role for every project in the program, including projects added later (Q10).

```
visible_project_ids(user):
    if user.is_platform_admin: return ALL
    g = the ONE active grant of user                      # D-32 — at most one exists
    if g is None:            return ∅
    if g.project_id:         return {g.project_id}
    return {p.project_id for p in PROJECT where program_id = g.program_id and is_active}
    # program_id is read HERE, per request: moving a project out of a program removes it from
    # every program holder's set on their next request, with no token to expire.

require_project(user, project_id, min_role):
    if user.is_platform_admin: return ADMIN_GRANT
    g = the ONE active grant of user
    p = PROJECT(project_id)
    if g is None or p is None:                                         raise 404
    if   g.project_id == project_id:                                   role = g.role
    elif g.program_id is not None and p.program_id == g.program_id:    role = g.role
    else:                                                              raise 404
    # not 403 — a project you cannot see does not exist
    if PROJECT_ROLE_RANK[role] < PROJECT_ROLE_RANK[min_role]: raise 403
    return EffectiveGrant(g, role, via='PROGRAM' if g.program_id else 'PROJECT')

require_program(user, program_id, min_role):                          # D-32, R2-S2
    if user.is_platform_admin: return ADMIN_GRANT
    g = the ONE active grant of user
    if g is None or g.program_id != program_id: raise 404   # a PROJECT grant sees no roll-up
    if PROJECT_ROLE_RANK[g.role] < PROJECT_ROLE_RANK[min_role]: raise 403
    return g
```

**Structure, not a promise (findings S2 and S3).** The first draft asserted "every service
function calls `require_project` first" and then wrote it into five of twenty functions. A
missing check returns a *successful* response, which nobody reports as a bug. Two changes
make omission impossible rather than discouraged:

```python
# THE GUARD REGISTRY (R2-S1). Every route declares EXACTLY ONE guard, as data on the route.
# A route with none does not register: the router factory raises at import time, and
# criterion 49 re-proves it over the running app.
class Guard(Enum):
    PUBLIC          # no JWT. POST /auth/login and nothing else.
    AUTHENTICATED   # JWT only; the service filters (GET /projects, /programs, /auth/me, schema)
    PLATFORM_ADMIN  # current_user().is_platform_admin, re-read per request (S4)
    PROJECT_CTX     # /projects/{project_id}/…  → require_project(user, project_id, min_role)
    OBJECT_GUARD    # /<things>/{id}/…          → resolve the owning project, then require_project
    PROGRAM_CTX     # /programs/{program_id}/…  → require_program(user, program_id, min_role)

def route(method, path, *, guard: GuardSpec, **kw):     # the ONLY way to register a route
    if guard is None: raise RouteDefinitionError(f"{method} {path} declares no guard")
    endpoint = app.api_route(path, methods=[method], dependencies=[guard.dependency], **kw)
    endpoint.guard = guard                               # read back by criterion 49
    return endpoint

def project_ctx(min_role):  return GuardSpec(PROJECT_CTX, min_role,
    Depends(lambda project_id=Path(...), user=Depends(current_user):
            access.require_project(user, project_id, min_role)))

def object_guard(model, min_role, id_params=("id",)):
    # For routes that carry an object id and NO project (finding S3). The owning project is
    # resolved from the object BEFORE anything is returned. `model` must implement
    # owning_project_id(); a model that cannot is refused at registration.
    def dep(request, user=Depends(current_user), db=Depends(get_db)):
        objs = [db.get(model, request.path_params.get(p) or request.query_params.get(p))
                for p in id_params]
        if any(o is None for o in objs): raise 404
        owners = {o.owning_project_id() for o in objs}
        if len(owners) != 1: raise 404                   # e.g. a diff across two projects
        owner = owners.pop()
        if owner is None:                                # a program grant row (no project)
            if not user.is_platform_admin: raise 404
        else:
            access.require_project(user, owner, min_role)   # 404 if not granted
        return objs if len(objs) > 1 else objs[0]
    return GuardSpec(OBJECT_GUARD, min_role, Depends(dep), model=model)
```

`GET /baselines/diff?from=12&to=19` was the concrete leak: two surrogate `bigint`s, no
project in the path, and `diff` did no resolution at all — so a consultant granted only on
project A could read another client's full ADDED / CHANGED / REMOVED scope report, and
`AUDIT_EVENT` recorded no reads, so there was no trace it happened. `diff` now resolves both
baselines, requires them to share a project, and guards that project (§7.7).

**Acceptance criterion 49 is the test that keeps this true.** It walks the running app's
routes, not a list in this document, and fails on any route that declares no guard. It also
fails when a declared guard does not fit the path: a `{project_id}` route that is not
`PROJECT_CTX`, an `{id}` route outside `/projects/…` whose guard is not `OBJECT_GUARD`,
`PROGRAM_CTX` or `PLATFORM_ADMIN`, or `PUBLIC` anywhere but login. **R2-S1:** the first
draft's hand-kept list of object-id routes had already missed seven route families by D-31
(external entities, process flows, FR interface, benefits, risks, change requests, phases).
A list that must be remembered is a list that will be forgotten. §6.4 makes this test the
stated price of deferring row-level security.

### 7.9 `services/reports.py` — the four read-only deliverables

These are the outputs FTC actually hands a client. They are queries, not workflows.

```
coverage(project_id):                          # the scope-gap list
    return {
      "process_nodes_without_br": process nodes with no active BR,
      "br_without_output_de":  BRs with no BR_DATA_ENTITY row where direction = 'O',
      "br_without_solution":   BRs with no BR_SOLUTION row,
      "br_without_accountable": BRs with no BR_ORG_ROLE row whose RACI behaviour is
                                ACCOUNTABLE,                          # R2-D9 — not the letter
      "fr_with_suggestion":    FRs whose suggested_br_id is still set, with the BR   # D-34
      "de_never_referenced":   DEs absent from both BR_DATA_ENTITY and BFC_NODE_DATA_ENTITY,
      "solution_without_br":   solutions answering nothing,
      "tech_solution_no_fr":   TECHNOLOGY solutions with no FUNCTION_REQUIREMENT,
      "solution_no_application": TECHNOLOGY solutions with no APPLICATION_SOLUTION,
    }

entity_model_validation(project_id):
    return {
      "de_without_pk":   DEs with no DATA_FIELD where is_primary_key,
      "fk_to_pkless_de": FK fields whose ref_data_entity_id has no PK field,
      "pk_ordinal_gaps": DEs whose pk_ordinal values are not 1..n contiguous,
    }

traceability(project_id):                      # the vendor-facing scope list
    BFC_NODE(is_process) ⋈ BUSINESS_REQUIREMENT ⋈ BR_SOLUTION ⋈ SOLUTION
                 ⋈ FUNCTION_REQUIREMENT ⋈ APPLICATION_SOLUTION ⋈ APPLICATION
    UNION the direct FR_BFC_NODE coverage (§5.4.3 override)
    order by hier_code, br_number; group by FR type (unlinked FRs last, D-28)
    → FORM / BATCH / INTERFACE / REPORT, each with its originating BRs, process steps,
      solution and target application

solution_matrix(project_id):                   # D-7 — is the transformation balanced?
    SOLUTION ⋈ BR_SOLUTION ⋈ BUSINESS_REQUIREMENT ⋈ BFC_NODE
    pivot: solution category (ORG_AND_RULES|PEOPLE|PROCESS|DATA|TECHNOLOGY)
           × BFC L1 area, counting solutions and the BRs they answer
    → the question this report exists to ask: five technology answers and no org change
      is a finding, and until now the model could not show it

application_gap(project_id):                   # D-8 — the migration backlog
    as_is  = APPLICATION_BFC_NODE ⋈ APPLICATION where lifecycle in (AS_IS, BOTH)
    to_be  = BFC_NODE(is_process) ⋈ BUSINESS_REQUIREMENT ⋈ BR_SOLUTION
                          ⋈ APPLICATION_SOLUTION ⋈ APPLICATION
    return {
      "unallocated": process steps in as_is with no row in to_be,     # nothing replaces it
      "unsupported": process steps in to_be with no row in as_is,     # net-new capability
      "retiring":    AS_IS applications with no to-be allocation anywhere,
    }

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
    BFC_NODE(is_process) ⋈ BUSINESS_REQUIREMENT ⋈ BR_SOLUTION ⋈ SOLUTION
    count process steps carrying a solution, rolled to L1, weighted by solution category

org_impact_heatmap(project_id):
    ORG_UNIT ⋈ ORG_ROLE ⋈ (BFC_NODE_ORG_ROLE ∪ BR_ORG_ROLE) ⋈ BR_SOLUTION
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
    source = DATA_ENTITY ⋈ BFC_NODE_DATA_ENTITY ⋈ APPLICATION_BFC_NODE ⋈ APPLICATION(AS_IS)
    target = DATA_ENTITY ⋈ BR_DATA_ENTITY ⋈ BR_SOLUTION ⋈ APPLICATION_SOLUTION ⋈ APPLICATION
    → source → target per entity; headline = entities with no source, or with >1 source

master_data_candidates(project_id):
    BR_DATA_ENTITY ⋈ BUSINESS_REQUIREMENT ⋈ BFC_NODE
    → data entities referenced from BRs under 3+ distinct L1 ancestors

effort_summary(project_id):                    # D-13
    FUNCTION_REQUIREMENT.effort_days grouped by FR type, solution (Unassigned for
    unlinked FRs, D-28), phase, L1 area
```

Each of these has a `headline_value`, which is what `control_panel` (§7.13) compares against
its `CONTROL_RULE`. **That contract is why every analysis returns one number as well as a
table** — a report without a headline cannot be governed.

The `design-spec` §4 grid itself is a fifth report and is nearly free here —
`BUSINESS_REQUIREMENT ⋈ BR_DATA_ENTITY ⋈ DATA_ENTITY ⋈ BFC_NODE`, one query, pivotable in
SQL (§5.6). The brief asked whether the app should emit that grid; this model settles it.

### 7.10 `services/auth.py`, `user_admin.py`, `project.py`

```
login(email, password):
    user = APP_USER where lower(email) = lower(:email)
    if user is None or not user.is_active or not verify(password, user.password_hash):
        AUDIT_EVENT(event_type='LOGIN_FAILED', detail={email})
        raise 401                                  # same message either way — never
                                                   # distinguish "no such user" from
                                                   # "wrong password"
    user.last_login_at = now()
    AUDIT_EVENT(event_type='LOGIN_OK', app_user_id=user.id)
    return jwt(sub=user.id, exp=now() + (30 days if remember_me else 1 day))   # A-34, §14.5
    # finding S4: the token carries the SUBJECT ONLY. It does not carry is_platform_admin
    # or any role, because a claim baked into a token cannot be revoked.

current_user(token):                               # the per-request dependency
    claims = verify_jwt(token)                     # signature + exp
    user = db.get(APP_USER, claims.sub)            # finding S4 — re-read, every request
    if user is None or not user.is_active: raise 401
    return user        # is_platform_admin is read from the row, never from the token
    # The request already joins USER_ACCESS_GRANT (§6.3), so this is one more lookup,
    # not a new round trip. Without it, deactivating a departing consultant on Friday
    # leaves their browser session reading and writing every granted client project.

create_user(actor, email, display_name, initial_password):
    require actor.is_platform_admin
    if not is_ftc_address(email):                  # D-11, finding S8
        raise 422 "Value Bridge accounts are FTC staff only. Client-side people are "
                  "recorded as stakeholders; external logins need record-level "
                  "confidentiality first (A-11)."
    insert APP_USER(password_hash=hash(initial_password), is_platform_admin=False, ...)
    AUDIT_EVENT(event_type='USER_CREATED', detail={email})
    # plaintext is never persisted, never logged, never in a response model

deactivate_user(actor, target_user_id):
    require actor.is_platform_admin
    target.is_active = False
    AUDIT_EVENT(event_type='USER_DEACTIVATED', detail={target_user_id})
    # takes effect on the target's very next request — see current_user above

create_project(actor, client_id, project_name, program_id=None):
    require actor.is_platform_admin                               # §9 — platform admin only
    if program_id and PROGRAM(program_id).client_id != client_id:
        raise 422 "A program's projects belong to its client"     # D-32
    project = insert PROJECT(..., program_id=program_id)
    # NO grant for the actor (D-32). A platform admin sees every project already; an
    # auto-grant would be a second, redundant access path that outlives the admin flag.
    seed PROJECT_SEQUENCE rows for all ten series:                 # R2-D14
        DE, BR, FR, ISSUE, SOL, BEN, RSK, CR, DEC, EXT
    # The first draft seeded five; next_number's "create at 0 if absent" then raced on the
    # first BEN / RSK / CR / DEC / EXT of a project — two concurrent first inserts, one PK
    # violation, surfaced as a 409 on an ordinary create.
    seed EFFORT_RATE from the FTC default; copy CONTROL_RULE house defaults (§7.13)
    AUDIT_EVENT(event_type='PROJECT_CREATED', project_id=project.id, detail={program_id})
    # Creating a project INSIDE a program grants its program holders access at once — the
    # admin console shows the same gains list as move_project_program before submitting.

grant_access(actor, target_user_id, scope, project_role_code):
    # scope = {project_id} | {program_id} — exactly one (D-32)
    validate_required_code("PROJECT_ROLE", project_role_code)   # OWNER|EDITOR|REVIEWER
    if scope.program_id: require actor.is_platform_admin        # Q10 — spans projects
    else:                access.require_project(actor, scope.project_id, OWNER)
        # Ben, Q16: a program OWNER may grant ONE project inside their program — they hold
        # OWNER on it through the program grant, so this check already admits them. They
        # can never grant the program itself, or a project outside it.
    target = APP_USER(target_user_id); require target.is_active
    if target.is_platform_admin: raise 422 "A platform admin needs no grant"
    existing = the ONE active grant of target
    if existing and existing.scope == scope:                     # a role change, not a 2nd grant
        UPDATE grant SET project_role_code = :r WHERE ... row_version = :v
        AUDIT_EVENT('ACCESS_ROLE_CHANGED', detail={target, scope, from, to})
        return existing
    if existing:
        raise 409 f"{target.display_name} already has access to {existing.scope_name}. "
                  "Only a platform admin can reassign them."      # R2-S4
    insert grant(target_user_id, scope, project_role_code,
                 granted_by_user_id=actor.id, granted_at=now())
    AUDIT_EVENT(event_type='ACCESS_GRANTED', detail={target, scope, role})
    # The partial unique index is the backstop: two concurrent grants to one user produce
    # one row and one 409, never two grants.

reassign_access(actor, target_user_id, new_scope, project_role_code, rationale):
    require actor.is_platform_admin
    if not rationale.strip(): raise 422 "Moving someone between clients needs a reason"
    with one transaction:
        old = the ONE active grant of target (may be None)
        if old: old.is_active = False
        insert grant(target_user_id, new_scope, project_role_code, granted_by=actor.id)
        AUDIT_EVENT('ACCESS_REASSIGNED', detail={target, from: old.scope, to: new_scope,
                                                 role, rationale})

revoke_access(actor, grant_id):
    # guard: object_guard(Grant, OWNER); a program grant resolves to no project →
    # platform admin only (§7.8)
    grant.is_active = False
    AUDIT_EVENT(event_type='ACCESS_REVOKED', detail={target, scope})   # finding S9
    # Never restorable (R2-S5). A revoked grant comes back only through grant_access,
    # which re-checks every rule above and writes its own audit row.

effective_access(actor, project_id):                               # D-32
    access.require_project(actor, project_id, OWNER)
    p = PROJECT(project_id)
    return sorted by source, name:
        [ {user, role, source: 'PROJECT', granted_by, granted_at}
              for active grants where project_id = :p ]
      + [ {user, role, source: 'PROGRAM', program: p.program.name, granted_by, granted_at}
              for active grants where program_id = p.program_id ]
      + [ {user, role: 'ALL', source: 'PLATFORM_ADMIN'}
              for active APP_USER where is_platform_admin ]
    # "Who can read this client's data?" answered in full. Listing only direct grants —
    # the first draft's GET /access — hid everyone who arrived through the program.
```

### 7.10a `services/program.py` (D-32)

A program is a header, an access scope, and a set of reads. **It owns no business data**, so
it has no SQL of its own over business tables.

```
create_program(actor, client_id, program_code, program_name, description):   # platform admin
    require actor.is_platform_admin
    insert PROGRAM(...); AUDIT_EVENT('PROGRAM_CREATED')

move_project_program(actor, project_id, target_program_id | None, confirm_hash=None):
    require actor.is_platform_admin                        # Q10 — nobody else, not a program OWNER
    p = PROJECT(project_id); t = PROGRAM(target_program_id) if target_program_id else None
    if t and t.client_id != p.client_id: raise 422 "A program's projects belong to its client"
    gains = active grants where program_id = t.id                    (if t)
    loses = active grants where program_id = p.program_id           (if p.program_id)
    preview = {project: p.project_code, from: p.program, to: t,
               gains: [user + role], loses: [user + role]}
    h = sha256(canonical(preview))
    if confirm_hash is None: return {preview, preview_hash: h}        # step 1 — writes nothing
    if confirm_hash != h:
        raise 409 "Who gains or loses access changed since the preview. Review it again"
    UPDATE project SET program_id = :t WHERE project_id = :p AND row_version = :v
    AUDIT_EVENT('PROJECT_PROGRAM_CHANGED', project_id,
                detail={from, to, gained: gains, lost: loses})
    # R2-S3. Moving a project is the one act that changes who can read a client's data
    # without touching a grant row, so it gets the same weight as a grant: named people,
    # an explicit confirmation, and an audit row that lists them.

ROLLUPS = {                         # program report → the per-project report it is made of
  'counts':         lambda u, pid: {br: reports.count(u, pid, 'BR'), fr: …, issue_open: …},
  'interfaces':     reports.interface_list,
  'effort':         reports.effort_summary,
  'control_status': control.control_panel,
  'plan_vs_actual': wbs.plan_vs_actual,          # projects with no WBS return "not imported"
}

rollup(user, program_id, report):
    access.require_program(user, program_id, REVIEWER)          # program grant or admin
    ids = visible_project_ids(user) ∩ {p.project_id for p in PROJECT
                                        where program_id = :program_id and is_active}
    return [ {project_id, project_code, result: ROLLUPS[report](user, pid)}
             for pid in sorted(ids) ]
    # R2-S2 — EVERY per-project call runs its own require_project, exactly as the screen
    # would. There is no query here with `project_id IN (...)`, and code review rejects
    # one: a cross-project SQL path is a second visibility rule, and the one-guard design
    # (§7.8) exists so there is only one.

program_dashboard(user, program_id):
    return {report: rollup(user, program_id, report) for report in ROLLUPS}
```
Output data: a program header, audited moves, and roll-ups that are lists of per-project
results. **Nothing is stored at program level**, so there is nothing to baseline. Baselines
stay per project (A-56).

### 7.11 `services/bulk.py` — upload / download (D-5)

Covers **Issue, Data Entity, Data Field, Business Requirement, Function Requirement** (the
last two added by D-28) **and WBS** (D-33). One service, one staging model, six column-map
definitions, not six importers. The process-flow JSON (§7.2b) reuses the same staging and
commit. `import_mode` (merge / replace) is accepted for **WBS and the flow JSON only**. Any
other entity with a mode is a 422.

```
template(entity):
    build .xlsx from COLUMN_MAP[entity]
    attach data validation lists from code_master for every coded column
    → the returning file is already half-clean, which is most of the battle

export(project_id, entity):
    access.require_project(user, project_id, REVIEWER)
    rows = live rows where is_active
    emit template shape INCLUDING the business key (ISS-0001 / DE-0001)
    #   AND row_version, as a PROTECTED column          # finding D2
    # the key is what makes a round-trip an update instead of a duplicate; row_version is
    # what stops the round-trip silently reverting a colleague's edit. Without it, D-6
    # did not cover the ONE path in the app that updates many rows at once.
    every cell written through escape_cell()            # finding S5 — see §7.12

validate(project_id, entity, file):
    access.require_project(user, project_id, EDITOR)
    enforce_upload_limits(file)          # bytes, decompressed bytes, rows, cols — §7.12
    batch = INSERT IMPORT_BATCH(target_entity=entity, status='VALIDATING',
                                uploaded_by_user_id=jwt.user_id)
    for sheet_row_no, raw in parse_streaming(file):
        errors = []
        check required columns present and typed
        check every date column is ISO YYYY-MM-DD           # finding D10
        check every coded value resolves via code_master.resolve(project_id, category)
        check business_key, if present, exists in THIS project      # never another's
        if business_key present and raw.row_version != current.row_version:
            errors += ["Row changed since export. Current value: <…>"]   # finding D2:
            # a stale row is a PER-ROW error surfaced HERE, with the current value shown —
            # not a whole-batch abort at commit, which is the pressure that gets the
            # check disabled.
        for ISSUE: raised_by name must match exactly ONE active STAKEHOLDER,
                   else ERROR — the consultant picks or creates one in the preview.
                   NEVER auto-create a person from a spreadsheet cell.   # finding D6
        for DATA_FIELD: parent DE must exist and be active; FK target DE in this project
        for BUSINESS_REQUIREMENT:                                      # R2-D1
                   br_number is REQUIRED and must be an active BR in this project —
                   every BR already exists with its process node (D-2), so a blank
                   br_number is an ERROR ("BRs are created with their step — use the
                   flow import to add steps"). An import never creates a BFC node or a BR.
                   hier_code, if present, is a CROSS-CHECK only: if it differs from the
                   BR's node's current hier_code →
                       errors += [f"{br_number} moved since export: now {node.hier_code}, "
                                  f"file says {hier_code}. Re-export"]
                   The first draft keyed BR rows by hier_code — which changes on every
                   reorder (D-10) — so a reorder between export and upload wrote each
                   requirement onto its former neighbour's step, with no error.
        for FUNCTION_REQUIREMENT:                                      # R2-D6, D-28, D-34
                   fr_type must resolve in FR_TYPE; SOL- number optional —
                   blank → warnings += ["No solution: this FR will not trace to a BR"]
                   BR- number optional → staged as suggested_br_id (D-34);
                       warnings += [f"Suggested link to {br} kept"] unless the SOL answers it
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
                   # the same two refusals rate_function_requirement and change_fr_type
                   # make — surfaced per row HERE, not as a whole-batch abort at commit
                   interface columns (source app, target app, method, frequency)
                   read only when the type's behaviour is INTERFACE
        for WBS: see §7.11a
        warnings never set is_valid = false            # D-28 — inform, do not block
        INSERT IMPORT_ROW(batch, sheet_row_no, business_key, payload=raw,
                          verdict='INSERT' if blank key else 'UPDATE',   # finding P3
                          is_valid=not errors, error_detail=errors,
                          warning_detail=warnings)
    batch.status = 'VALIDATED'
    batch.error_count  = count(not is_valid)
    batch.insert_count = count(verdict='INSERT')
    batch.update_count = count(verdict='UPDATE')
    return batch summary + the per-row error list, keyed by SHEET row number
    # nothing has touched a business table yet

preview(batch_id):                                  # finding P3 — what the human approves
    access.require_project(user, batch.project_id, EDITOR)
    return {
      "summary": {insert_count, update_count, error_count,
                  stakeholders_to_create: […]},     # named, not counted
      "rows": [ {sheet_row_no, verdict, business_key,
                 changes: [ {column, current_value, new_value} ]   # before/after per field
                } ],
    }
    # The first draft returned "staged rows" — which is what the uploader already knows.
    # A consultant approving 300 exported rows could not see that 12 of them carried
    # Monday's values for fields a colleague corrected on Wednesday.

commit(batch_id, confirm):
    batch = SELECT … FROM import_batch WHERE id = :id FOR UPDATE    # finding P2
    access.require_project(user, batch.project_id, EDITOR)
    if batch.status != 'VALIDATED':   raise 409     # re-checked INSIDE the lock
    if batch.error_count > 0:         raise 422 "Fix N rows and re-upload"
    if batch.insert_count > 0 and confirm.acknowledged_inserts != batch.insert_count:
        raise 422 f"This will CREATE {batch.insert_count} new rows. Confirm the count."
        # finding D3 — a client BA clearing the ISS- column turns an update batch into
        # 200 brand-new issues. Nothing is invalid, so all-or-nothing does not help.
        # R2-P2 — required whenever there are inserts, not only when inserts and updates
        # are mixed. The first draft let an ALL-insert batch through unacknowledged, which is
        # exactly the shape of a file whose key column was cleared on every row.
    if batch.retire_count > 0 and confirm.acknowledged_retires != batch.retire_count:
        raise 422 f"This will RETIRE {batch.retire_count} rows. Confirm the count."
        # replace mode — WBS (§7.11a) and the flow JSON (§7.2b)
    with one transaction:                                   # all-or-nothing
        for row in batch.rows ordered by sheet_row_no:
            revalidate(row)                         # finding D1 — FULL re-validation here
            if not row.is_valid: abort batch
            # Verdicts were computed at validate time, possibly days earlier, because the
            # design deliberately puts a human between the two calls. A DE soft-deleted in
            # between would otherwise leave live fields under a dead parent, and break the
            # next freeze weeks later with an FK error and no explanation.
            if row.business_key is blank:
                target = create(...)        # number minted HERE, at commit (§9.8)
            else:
                target = update(..., WHERE row_version = payload.row_version)   # D-6
                # FR rows: fr_type and complexity are applied by calling
                # function_requirement.change_fr_type / effort.rate_function_requirement
                # inside this transaction — never by writing the columns (R2-D6). effort_days
                # is never written from a file.
                if rowcount == 0: abort batch with 409
            row.committed_target_id = target.id
        batch.status = 'COMMITTED'; batch.committed_at = now()
    AUDIT_EVENT(event_type='IMPORT_COMMITTED', detail={entity, insert_count, update_count})
```

**The uploaded file's lifecycle** (COULD-NOT-REVIEW gap, now specified; R2-S8, Q14). The
body is **size-checked at ingress before any handler runs** (§7.12b). The `.xlsx` is **never
stored**. It is streamed from the request, parsed under the caps above, and discarded when
`validate` returns. **The multipart spool threshold is set at or above the route's cap**, so
an accepted upload stays in memory and is never written to disk. Starlette's default spools
anything over 1 MB to a temp file, which made the first draft's "never written to disk"
untrue for any real workbook. Where the platform forces a spool, the directory is
container-local ephemeral storage (`TMPDIR`), never a mounted share, and the file is deleted
when the request ends. Only `IMPORT_ROW.payload` persists, and it is **purged 90 days** after
its batch (`purge_import_rows`, §7.12b). `IMPORT_BATCH.file_name` is kept **for display only**
and is never used to construct a filesystem path or a `Content-Disposition` header. Export
downloads get a server-generated name. This removes file storage, file permissions and filename
handling from the attack surface entirely rather than securing them.

**Six properties that are not negotiable, because a bad import is worse than no import.**
Properties 5 and 6 were added by the round-1 review; without them the first four were
decorative.

1. **Validate and commit are separate calls.** The consultant sees a preview and approves.
   An upload never writes unattended — that is the `(manual)` row in §4.5a.
2. **All-or-nothing.** One invalid row rejects the batch. A half-applied spreadsheet is a
   data-integrity incident nobody notices for a week.
3. **Numbers are minted at commit, never at validate** (§9.8). A rejected batch must not
   burn `DE-0007`.
4. **Every row is project-scoped on the way in.** A business key belonging to another
   project is a validation error, not a silent cross-project write. This is the one place
   where a file, not a query, is the attack surface (§6.4).
5. **Every verdict is re-computed inside the commit transaction** (finding D1). Validate-time
   results are advisory — they exist to build the preview. The world can change between
   Tuesday's validate and Thursday's commit, and the design *invites* it to by putting a
   human in between.
6. **The consultant approves consequences, not contents** (findings P3, D3, R2-P2). The
   preview states per row whether it inserts, updates or retires, shows before/after for
   every changed field, and names the stakeholders that would be created. **Any batch that
   creates rows requires an explicit acknowledgement of how many, and any batch that retires
   rows requires the same for retirements** — every batch, not only mixed ones.

### 7.11a `services/wbs.py` — WBS import (D-33)

**Optional per project** (Q13). A project with no WBS works exactly as before; the program
dashboard says "not imported" for it.

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
        # NO row_version check. MS Project is the system of record for every imported
        # column, and the only VB-edited columns (the links) are never in the file, so an
        # import cannot revert a colleague's edit.
    parent of each row = the nearest preceding row with outline_level one less
    if import_mode == 'replace':
        for every active WBS_ITEM whose ms_unique_id is not in the file:
            stage RETIRE                                    # counted, acknowledged at commit

commit: bulk.commit (§7.11) — both acknowledgements; parent links set after all rows exist;
        a RETIRE soft-deletes the line and KEEPS its phase / solution links on the row, so a
        line restored by a later import comes back linked

link_wbs_item(wbs_item_id, phase_id | None, solution_id | None, row_version):   # EDITOR
    assert phase / solution in the item's project
    UPDATE wbs_item SET phase_id, solution_id WHERE ... row_version = :v            # 409 on 0
    # The ONLY write VB makes to a WBS line (D-33). PATCH with any other field → 422
    # "Change it in MS Project and re-import".

plan_vs_actual(user, project_id):
    access.require_project(user, project_id, REVIEWER)
    per PHASE (via link) and per top-level WBS line:
        planned_finish = max(finish), actual_finish = max(actual_finish),
        slip_days = actual_or_forecast − planned, pct_complete (duration-weighted)
    "unlinked": lines with no phase, listed — never dropped
    headline_value = max slip_days across phases     # so a control rule can govern it later
```
**Not baselined** (D-33). The schedule is not agreed scope, and a re-plan is not a scope
change. Freezing it would put a re-plan in every diff.

### 7.12 Services added by the round-1 review

```
# ---- soft delete and restore (findings P5, R2-D2, R2-S5) ------------------
DEPENDENTS[model] = [(child_model, fk_columns)
                     for every FK in Base.metadata whose target is model's table,
                     where the child table has is_active]
PARENTS[model]    = the reverse: every FK FROM model's table to a table with is_active
    # BOTH DERIVED FROM THE MODEL, never hand-kept: together they are the FK_LIVENESS list
    # of §5.4.15, with its exclusions — FKs to APP_USER, project_id, baseline_* (a frozen
    # row never blocks a live delete), AUDIT_EVENT, IMPORT_BATCH, IMPORT_ROW, DIAGRAM_LAYOUT
    # (hard-deleted, D-30) and FUNCTION_REQUIREMENT.suggested_br_id (a hint: retiring the
    # BR clears it instead of being blocked). A CI test proves every FK is listed or
    # excluded. A nullable FK is a parent only where it is set (FR.solution_id).

soft_delete(entity, obj_id, row_version):                       # EVERY DELETE route
    obj = the object_guard-resolved row (EDITOR)
    blockers = [(child, active rows referencing obj) for child in DEPENDENTS[entity]]
    if blockers:
        raise 409 "Retire these first: " + "; ".join(
            f"{child.label}: {business keys, first 10} (+{n - 10} more)" for …)
        # Q4. Deleting a DE with active BR CRUD, a solution with active FRs, a BFC node with
        # its BR — each is REFUSED, with the blockers named. NOTHING CASCADES. A cascade
        # retires scope nobody chose to retire, and the next priced diff reports it as a
        # decision.
    UPDATE ... SET is_active = FALSE, deleted_at = now(), deleted_by = jwt.user_id
     WHERE id = :id AND row_version = :v                        # 409 on 0
    if entity is BusinessRequirement:                           # D-34 — the hint clears
        UPDATE function_requirement SET suggested_br_id = NULL WHERE suggested_br_id = :id
    AUDIT_EVENT(event_type='RECORD_DELETED', detail={entity, business_key})

RESTORABLE = {                 # THE ALLOW-LIST (R2-S5). One restore route per entry (§9).
    BfcNode, BusinessRequirement, DataEntity, DataField, ExternalEntity, OrgUnit, OrgRole,
    Solution, FunctionRequirement, Application, Stakeholder, Issue, Benefit, Risk,
    ChangeRequest, Phase,
}
    # NOT restorable, by design:
    #   USER_ACCESS_GRANT (grants) — access returns only through grant_access, which
    #       re-checks the one-grant rule and audits the grant as a grant. Restoring a grant
    #       row would re-open access with the revoker's audit trail and nobody's decision.
    #   CONTROL_RULE — disabled via is_enabled, changed via maintain_control_rule (audited,
    #       with a rationale). A restore would move a threshold without a rationale.
    #   APP_USER — reactivation is user_admin, platform admin only.
    #   CODE_MASTER — maintained through code_master.maintain, with R2-D8's rule.
    #   PROGRAM, WBS_ITEM — admin-managed / import-managed.
    #   Junction rows — re-linked through their link service, never restored.

restore(entity, obj_id):
    if entity not in RESTORABLE: raise 404                     # the route does not exist
    obj = the object_guard-resolved row (EDITOR)
    for parent_model, fk in PARENTS[entity]:
        parent = the row obj references through fk
        if parent is not None and not parent.is_active:
            raise 409 f"Restore {parent.label} {parent.business_key} first"   # R2-D2, Q4
    if entity is BfcNode: bfc.assert_name_free(obj.project_id, obj.parent_id, obj.node_name,
                                               except_id=obj.id)                   # Q1
        if a live node now holds obj.hier_code:                  # R2-D10 — code is partial-unique
            obj.seq_no = next free seq under its parent; obj.hier_code = generate_code(obj)
    obj.is_active = True; obj.deleted_at = None; obj.deleted_by = None
    # a unique conflict (e.g. a second active BR on the node) surfaces as 409 (P10)
    AUDIT_EVENT(event_type='RECORD_RESTORED', detail={entity, obj_id})
    # An app whose stated premise is "nothing is ever truly gone, and that is the point"
    # (§5.6) had no way for a user to get anything back. It now has one — for business
    # rows, and only for them.

# ---- consistency check (findings D11, R2-D2, R2-P6) -----------------------
consistency_check(project_id, db=None):          # db = the caller's transaction, if any
    access.require_project(user, project_id, REVIEWER)
    return {
      "hier_code_drift":  nodes where hier_code != recompute_from_parent_chain(node),
      "level_no_drift":   nodes where level_no != depth(node),
      "process_without_br": process nodes with no active BR,
      "br_on_non_process":  BRs whose node is not a process   # DB-impossible for active BRs
                                                             # since D-23; kept as a proof
      "orphan_fields":    active data_fields whose parent data_entity is inactive,
      "active_under_inactive":                                          # R2-D2
          for T in FREEZE_SET, for (P, fk) in PARENTS[T]:
              active T rows in this project whose P row is inactive
          → [{table, business_key, parent_table, parent_key}],
      "project_sequence_missing": number series of the ten with no PROJECT_SEQUENCE row,  # R2-D14
      "conditional_without_label": active CONDITIONAL edges with no condition_label,     # §5.3
      "as_is_allocated":  active APPLICATION_SOLUTION rows on an AS_IS application,       # §6.2
    }
    # §5.5 named "a periodic consistency check" as the mitigation for storing derived
    # hier_code and level_no — and it existed in no grid row, service, route, criterion or
    # checklist item. The mitigation for the design's most-flagged risk did not exist.
    # It is now a PRECONDITION OF FREEZE (§7.7), run INSIDE the freeze transaction
    # (R2-P6): the cheapest possible place, because freeze is the moment correctness
    # starts carrying weight. active_under_inactive is how a row that slipped past
    # soft_delete (direct SQL, a migration, a bug) is caught before it is frozen as scope.

# ---- code_master resolution (finding D12) ---------------------------------
code_master.resolve(project_id, category):
    # THE single source of truth for the two-tier rule, with the same standing as
    # numbering.py and access.py (playbook §9.10). Project override shadows the global of
    # the same category+code.
    overrides = rows where project_id = :p and category = :c
    globals_  = rows where project_id IS NULL and category = :c
    return overrides ∪ {g for g in globals_ if g.code not in overrides.codes}
    # Every consumer routes through this: the React dropdown, validate_required_code, the
    # import template's data-validation lists, and the import validator. When the template
    # generator and the validator disagreed about the tier, a project that renamed HIGH to
    # MAJOR got a template offering values its own validator rejected.

# ---- spreadsheet safety (findings S5, S6) ---------------------------------
escape_cell(v):                                     # EVERY sheet-writing path uses this
    if isinstance(v, str) and v[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + v                              # or write as an explicit inline string
    return v
    # Issue titles, descriptions, resolutions and DE/field descriptions arrive from
    # workshops, client documents and — via bulk import — directly from a client-supplied
    # file, so a payload can be planted without any FTC consultant typing it. FTC then
    # emails that export to the client's BA or a system vendor under its own name. The
    # round trip (injected by file → stored → emitted by file) never passes a human who
    # would read the cell as code.

enforce_upload_limits(file):                        # finding S6 — now specified
    MAX_UPLOAD_BYTES       =  10 * 1024 * 1024      # 10 MB on the wire
    MAX_DECOMPRESSED_BYTES = 100 * 1024 * 1024      # 100 MB expanded — the zip-bomb cap
    MAX_ROWS, MAX_COLS     = 5_000, 200

    reject if content_length > MAX_UPLOAD_BYTES              # before reading a byte
    parse with openpyxl load_workbook(read_only=True, data_only=True)
        # read_only streams row by row instead of materialising the sheet. A-32's row cap
        # was a business rule checked AFTER parsing: one stray formatted cell near row
        # 1,048,576 — routine with copied Excel templates — makes a non-streaming parser
        # build a million rows and kill the worker.
    count decompressed bytes as the zip members are read; abort over the cap
    abort at MAX_ROWS / MAX_COLS while streaming, before materialising them
    # XML hardening: defusedxml must be installed so entity expansion and external-entity
    # resolution are neutralised. An .xlsx is a zip of XML and is parsed as untrusted
    # input. VERIFY IT — acceptance criterion 75 feeds a workbook containing an external
    # entity declaration and asserts it is rejected rather than resolved.
```

### 7.12a JSON import limits (D-25)

The same threat as the `.xlsx` parser in §7.12, in a different shape: a JSON file is cheap
to make deep or huge, and this one may have been written by an AI nobody watched.

```
enforce_json_limits(file):
    reject if Content-Length > 2 MB, checked before reading a byte
    parse with the stdlib json module under a nesting-depth cap of 32
    reject NaN / Infinity (parse_constant), duplicate object keys (object_pairs_hook)
    reject if steps > 500, flows > 2,000, data_entities > 500, any string > 4,000 chars
    every free-text value is stored as text and rendered escaped — never as HTML (S5)
```
500 steps per file sits well inside A-35's 2,000 process nodes per project: one file is one
parent node's flow, not a whole chart.

### 7.12b Services added by design review round 2

```
# ---- Mermaid safety (R2-S7) ------------------------------------------------
MERMAID_ENTITY = {'#': '#35;', '"': '#quot;', '<': '#lt;', '>': '#gt;', '`': '#96;',
                  '[': '#91;', ']': '#93;', '(': '#40;', ')': '#41;', '{': '#123;',
                  '}': '#125;', '|': '#124;', ';': '#59;'}
escape_mermaid(text):                      # EVERY Mermaid-writing path uses this, no exceptions
    s = str(text or "")
    s = s.replace("\r", " ").replace("\n", " ")        # a newline starts a new statement
    s = s.replace("%%", "")                            # comments and %%{init}%% directives
    s = "".join(MERMAID_ENTITY.get(c, c) for c in s)   # '#' first by construction (one pass)
    return '"' + s + '"'                               # EVERY label quoted
    # Step names, lanes, conditions, entity and field names arrive from workshops and — via
    # the flow JSON — from an AI conversion of a client slide. A label that closes its
    # bracket and opens a `click` directive, or an %%{init}%% that switches securityLevel to
    # loose, turns the pasted diagram into a link or a script in the client's own deck tool.

render_mermaid(graph):                     # the one renderer: export_process_flow, export_dfd,
                                           # export_erd
    ids are generated ("s123", "d7", "x2", "E7") — never derived from user text
    erDiagram: entity as E7["DE-0007 Sales order"]; attribute names emitted as a_<n> with the
               real name in the quoted comment — erDiagram accepts no quoted attribute names
    NEVER emits: click, call, href, %%{init}, style, classDef, linkStyle, class
    final guard: any output line whose first token is one of those → raise 500 and log —
                 a renderer bug, never a user-visible diagram

# ---- request body limits at ingress (R2-S8) -------------------------------
BODY_LIMITS = [
    ("POST /projects/*/bulk/process-flow/validate",  2 * 1024 * 1024),   # §7.12a
    ("POST /projects/*/bulk/*/validate",            10 * 1024 * 1024),   # §7.12
    ("*",                                            1 * 1024 * 1024),   # every JSON body
]
Layer 1 — Azure ingress (§15): a request-body cap at the edge set to the largest route
          limit (10 MB). An oversized body never reaches the container.
Layer 2 — BodySizeLimitMiddleware, the OUTERMOST ASGI middleware — before auth, before
          routing, before any handler or dependency runs:
    cap = first BODY_LIMITS entry matching (method, path)
    if Content-Length > cap: return 413 without reading the body
    wrap receive(): count bytes per chunk; past cap → 413 and stop reading
                    # a chunked body, or a Content-Length that lies
    # enforce_upload_limits (§7.12) and enforce_json_limits (§7.12a) stay: they check
    # decompressed size, rows and depth, which ingress cannot see. The first draft checked
    # Content-Length INSIDE the handler — after FastAPI had already parsed the multipart
    # form, spooling the whole body to disk.
Temp spool: multipart spool threshold ≥ the route cap, so accepted bodies stay in memory
            (§7.11). If spooled, TMPDIR = container-local ephemeral storage, never a mount.

# ---- import retention (Q14, closes A-32) ----------------------------------
purge_import_rows():                       # daily scheduled job (§15), as the app role
    expired = IMPORT_BATCH where uploaded_at < now() - interval '90 days'
                             and rows_purged_at IS NULL
    with one transaction:
        DELETE FROM import_row WHERE import_batch_id IN expired   # the ONE hard delete of
                                                                  # client content (§13)
        UPDATE import_batch SET rows_purged_at = now(),
               status = CASE WHEN status IN ('VALIDATING','VALIDATED') THEN 'REJECTED'
                             ELSE status END                      # an expired draft cannot
         WHERE import_batch_id IN expired                         # be committed later
    AUDIT_EVENT('IMPORT_ROWS_PURGED', detail={batches: n, rows: m, cutoff})
    # The header survives — who imported what, when, with what counts and outcome. The
    # payload — raw client cells, people's names — does not. IMPORT_BATCH.rows_purged_at
    # records it (§5.3 Import staging); the app role's only DELETE grants are import_row
    # and diagram_layout (§6.6). A preview of a purged batch reports "detail purged",
    # never an empty list.
```

### 7.13 The control framework (D-13…D-19)

```
# ---- size and effort (D-13) -----------------------------------------------
maintain_rate_card(project_id, cells, change_rationale):              # R2-D7
    access.require_project(user, project_id, OWNER)
    if not change_rationale.strip():
        raise 422 "Changing the rate card is a commercial decision and needs a reason"
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
    # Existing FRs are NOT repriced (A-38). The card is frozen with every baseline
    # (baseline_effort_rate, §6.1), so "v1.2 priced on the card agreed 2027-03-01" is answerable,
    # and a renegotiation is visible as itself rather than as unexplained drift.

rate_function_requirement(fr_id, complexity_code, row_version):
    access.require_project(user, fr.project_id, EDITOR)
    rate = EFFORT_RATE(project_id, fr.fr_type_code_id, complexity_code)     # D-27
    if rate is None: raise 422 "No rate card entry for this FR type and complexity"
    fr.complexity_code_id = complexity_code
    fr.effort_days = rate.standard_days          # DERIVED AT SAVE, THEN STORED
    # Never computed at read time. A renegotiated rate card must not silently reprice
    # scope that has already been agreed and frozen.

priced_diff(baseline_a, baseline_b):                                  # Q3, R2-D3
    d = baseline.diff(a, b)                      # §7.7 — same guard, same hash-spec check
    A = {r.source_fr_id: r for r in baseline_function_requirement(a)}
    B = {r.source_fr_id: r for r in baseline_function_requirement(b)}
    lines = []
    for fid in A.keys() | B.keys():              # EACH FR EXACTLY ONCE
        ea = A[fid].effort_days if fid in A else None
        eb = B[fid].effort_days if fid in B else None
        if   fid not in A:          cls, delta = 'ADDED',   +(eb or 0)
        elif fid not in B:          cls, delta = 'REMOVED', -(ea or 0)
        elif (eb or 0) != (ea or 0): cls, delta = 'CHANGED', (eb or 0) - (ea or 0)
        else: continue                           # same effort: MOVED or reworded, prices at 0
        row      = B.get(fid) or A[fid]
        unlinked = row.source_solution_id is None                     # D-28
        unrated  = (eb if fid in B else ea) is None
        lines.append({fid, row.fr_number, cls, delta, unlinked, unrated})
    totals = {
      "added_days":    Σ delta where cls = ADDED,
      "removed_days":  Σ delta where cls = REMOVED,       # negative
      "changed_days":  Σ delta where cls = CHANGED,       # re-rated or re-typed, net
      "net_days":      Σ delta,
      "unlinked_days": Σ delta where unlinked,            # its own line; inside net_days
      "unrated_fr_count": count where unrated,            # priced at 0 — say so
    }
    # ---- effort EXPOSED: informational, NEVER added to net (Q3) ----
    changed_brs = d.business_requirement rows with class ADDED | CHANGED | REMOVED
    exposed_frs = distinct source_fr_id reachable BR → BR_SOLUTION → SOLUTION → FR
                  in baseline b (in baseline a, for a REMOVED BR)
    totals["effort_exposed_days"] = Σ effort_days of exposed_frs (from b, else a)
    return {diff: d, lines, totals}
    # The first draft summed "FRs reachable from changed BRs" INTO each change class, so one
    # edited BR sentence priced every FR under it as CHANGED effort, and an FR reachable from
    # two changed BRs could be counted twice. A priced diff now prices only what changed —
    # the FR's own effort — and shows the exposure beside it: "+12 days re-rated; 340 days
    # sit under requirements that changed".
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
    # Two fixes. (1) Precedence: the first draft computed target − (baseline × pct), which is
    # not a number anyone meant. (2) Units: hours saved and baht saved were summed into one
    # "value" and ranked on one list. A solution with benefits in two units appears in both
    # rankings, each with that unit's value only.
    # The bottom quartile of each unit is the answer to "what does this change displace?"
    # Without this, "trade, don't add" is a slogan.

# ---- risk (D-15) ----------------------------------------------------------
score_risk(risk):
    risk.exposure_score = PROBABILITY_WEIGHT[p] * IMPACT_WEIGHT[i]    # derived at save

promote_risk_to_issue(risk_id, description):
    access.require_project(user, risk.project_id, EDITOR)
    issue = issue.raise_issue(...)               # the risk's owner becomes the raiser
    risk.materialised_issue_id = issue.id
    risk.status_code = 'MATERIALISED'            # the risk row SURVIVES
    record_decision(... 'RISK_MATERIALISED' ...)
    # The risk is the record that it was foreseen. Deleting it loses the only evidence
    # that the PMO saw this coming, which is exactly what a post-mortem asks for.

# ---- change control (D-16) ------------------------------------------------
raise_change_request(project_id, baseline_id, title, rationale, origin_code):   # Q8
    access.require_project(user, project_id, EDITOR)
    bl = BASELINE(baseline_id); if bl is None or bl.project_id != project_id: raise 404
    if bl.status_code not in ('FROZEN', 'APPROVED'):
        raise 422 "A change request is raised against an agreed baseline — FROZEN or "
                  "APPROVED. A superseded baseline is history; raise it against the latest"
    validate_required_code("CR_ORIGIN", origin_code)
    cr_number = numbering.next_number(db, project_id, "CR", "CR", 4)
    insert CHANGE_REQUEST(..., baseline_id, status_code='DRAFT',
                          raised_by_user_id=jwt.user_id)
analyse_cr_impact(cr_id, seed_objects):
    # The blast radius is COMPUTED, never typed.
    # seed_objects may be BRs or FRs (D-28): an unlinked FR has no BR, so the
    # BR -> SOLUTION -> FR walk can never reach it. impacted_fr_id already exists.
    frontier = seed_objects
    walk: BR -> BR_SOLUTION -> SOLUTION -> FUNCTION_REQUIREMENT
                            -> APPLICATION_SOLUTION -> APPLICATION
          BR -> BR_DATA_ENTITY -> DATA_ENTITY -> DATA_FIELD
          SOLUTION -> SOLUTION_PHASE -> PHASE
          SOLUTION -> SOLUTION_DEPENDENCY (both directions)
          SOLUTION -> BENEFIT_SOLUTION -> BENEFIT
          FR (seed) -> its SOLUTION, if any, and on from there as above
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
    access.require_project(user, cr.project_id, OWNER)
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
    access.require_project(user, project_id, OWNER)
    if analysis_code not in ANALYSIS_REGISTRY: raise 422 "No such analysis"
    if not change_rationale.strip(): raise 422 "Changing a control threshold is a "
                                               "governance decision and needs a reason"
    upsert CONTROL_RULE(project_id, analysis_code, ..., agreed_at=now())
    AUDIT_EVENT(event_type='CONTROL_RULE_CHANGED', project_id,
                detail={analysis_code, from: old_values, to: new_values, change_rationale})
    # Moving a threshold mid-engagement is exactly the kind of act that must be visible
    # later. Without the audit row, a project that never went red is indistinguishable
    # from one whose thresholds were widened until it stopped going red.

maintain_house_default(analysis_code, fields):
    require user.is_platform_admin
    upsert CONTROL_RULE(project_id=NULL, analysis_code, ..., is_house_default=True)
    # Affects FUTURE projects only — see the entity note. No in-flight engagement moves.

reset_project_rules_to_house_default(project_id, change_rationale):
    access.require_project(user, project_id, OWNER)
    overwrite this project's rules from the project_id IS NULL tier, preserving
      owner_org_role_id where the analysis_code still exists
    AUDIT_EVENT(event_type='CONTROL_RULES_RESET', project_id, detail={change_rationale})
    # The explicit opt-in that the copy-on-create rule otherwise denies.

control_panel(project_id):
    access.require_project(user, project_id, REVIEWER)
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

### 7.14 The diagram canvas — process flow, DFD and ERD (D-29, D-30, D-31)

Ben asked for a suggestion. **Recommendation: one canvas component, built on React Flow
(`@xyflow/react`, MIT) with `elkjs` for auto-layout, used for all three diagrams.** It is
already the choice for the process flow and DFD (2026-09-25), so the ERD adds node and edge
types, not a second library.

**What the ERD looks like:**

- **Entity card.** A header in the data-entity teal with `DE-0007` and the name. Below it,
  PK rows (key icon, bold) first, then FK rows (link icon, and the parent entity's name in
  small type), then attributes. More than 8 attributes collapse to "+12 more". Hovering a
  row shows its description, logical type and mandatory flag.
- **Field-level connectors.** Each FK row has its own handle, so the relationship line
  leaves from the FK row itself and arrives at the parent's PK row. You can see *which*
  field joins, not only which two tables do. This is the thing most ERD tools get wrong.
- **Crow's-foot notation** as custom SVG markers: `|` one, `O|` zero-or-one, `<` many.
  Solid line for an identifying relationship (the FK is part of the child's key), dashed
  for a non-identifying one. Orthogonal routing (ELK `ORTHOGONAL`), so lines turn corners
  instead of cutting across cards.
- **Interaction.** Drag to move, and the position is saved (D-30). **Auto-arrange**
  re-runs ELK for everything not pinned. Click an entity to highlight its neighbours and dim
  the rest; double-click opens the field editor in a side panel, so fields are edited *on*
  the diagram. Draw a line from an attribute to another entity to create an FK. Minimap,
  zoom to fit, search-to-focus.
- **Subject areas.** A filter by BFC L1/L2 branch shows only the entities that branch reads
  or writes. FKs leaving the area are drawn as short stubs labelled with the target, so a
  200-entity model stays readable one area at a time.
- **Export.** PNG and SVG for decks, Mermaid `erDiagram` text for documents.

**Process flow and DFD on the same component:** swimlanes are group nodes, stores are
cylinder nodes, external entities are square nodes with a heavy border, and conditional
edges carry their label. **JSON import** opens a preview diagram over the staged batch
before commit, with new, changed and warning items badged. A consultant approves a picture,
not a row list.

**Rejected, in one line each.** GoJS and JointJS+ are more complete but carry commercial
licences per developer. Mermaid renders but cannot be dragged or edited. Embedding draw.io
gives free-form drawing that is not bound to the model, which is exactly the "diagram that
looks authoritative and is wrong" problem D-20 exists to prevent.

**Performance bound.** React Flow virtualises off-screen nodes. The designed load is 200
entities with 2,000 fields on one ERD, and 150 steps on one process flow. Above that, the
subject-area filter is the answer, not a faster renderer.

## 8. `code_master` categories needed

Per §9.3 — no hard-coded enums, and the **code** goes over the wire, never the label.
Seeded via `backend/seeds/`, never in Alembic.

| Category | Codes (seeded) | Used by |
|---|---|---|
| `SOLUTION_CATEGORY` | `ORG_AND_RULES`, `PEOPLE`, `PROCESS`, `DATA`, `TECHNOLOGY` | `SOLUTION.category_code` — **D-7**, the five operating-model dimensions |
| `SOLUTION_STATUS` | `PROPOSED`, `AGREED`, `IN_DELIVERY`, `DELIVERED`, `REJECTED` | `SOLUTION.status_code` |
| `APP_LIFECYCLE` | `AS_IS`, `TO_BE`, `BOTH` — **`is_system`, not project-editable** | `APPLICATION.lifecycle_code` — **D-8**. Code branches on `AS_IS` (the allocation rule, §6.2), so the values are fixed |
| `APP_KIND` | `PACKAGE`, `CUSTOM`, `SAAS`, `PLATFORM`, `RPA`, `INTEGRATION`, `REPORTING` | `APPLICATION.app_kind_code` |
| `FR_TYPE` *(was `FR_CATEGORY`, D-27)* | `FORM`, `INTERFACE`, `REPORT`, `BATCH` — **project-editable**; each code carries a **behaviour** ∈ `FORM` / `INTERFACE` / `REPORT` / `BATCH` / `OTHER` | `FUNCTION_REQUIREMENT.fr_type_code`. Behaviour decides the FR form's detail panel and membership of the interface list, so a renamed or added type keeps working. **A behaviour is immutable once any FR or rate row references the code** (Q6, R2-D8; the NO ACTION FK, §5.3 CODE_MASTER) |
| `INTERFACE_PATTERN` | `PUSH`, `PULL`, `BIDIRECTIONAL` | `FR_INTERFACE.pattern_code` — **D-27** |
| `INTERFACE_METHOD` | `API`, `FILE`, `DB`, `MESSAGE`, `MANUAL` | `FR_INTERFACE.method_code` — project-editable |
| `INTERFACE_FREQUENCY` | `REALTIME`, `NEAR_REALTIME`, `HOURLY`, `DAILY`, `WEEKLY`, `MONTHLY`, `ON_DEMAND` | `FR_INTERFACE.frequency_code` |
| `EXTERNAL_ENTITY_KIND` | `CUSTOMER`, `SUPPLIER`, `BANK`, `REGULATOR`, `PARTNER`, `OTHER` | `EXTERNAL_ENTITY.kind_code` — **D-24a** |
| `IMPORT_STATUS` | `VALIDATING`, `VALIDATED`, `REJECTED`, `COMMITTED` | `IMPORT_BATCH.status_code` — **D-5**. The 90-day purge turns an uncommitted batch REJECTED (Q14, §7.12b). *Import targets (`target_entity`, now including `WBS_ITEM`, D-33) and `import_mode` are `CHECK` columns, not categories (§5.3 Import staging)* |
| `PROJECT_ROLE` | `OWNER`, `EDITOR`, `REVIEWER` | `USER_ACCESS_GRANT.project_role_code` — **D-9**; one role per grant over its whole scope, a project or a program (D-32, Q10). Capability matrix in §7.8 |
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
| ~~`FLOW_TYPE`~~ **Superseded by S2-1** — not a `code_master` category; `bfc_node_flow.flow_type` is CHECK-listed | `SEQUENCE`, `CONDITIONAL`, `PARALLEL`, `HANDOFF` — **`is_system`, not project-editable** | `BFC_NODE_FLOW.flow_type_code` — **D-20**. Code branches on each value ("CONDITIONAL needs a label" is service-enforced, §5.3 BFC_NODE_FLOW) |
| `RACI_TYPE` | `R`, `A`, `C`, `I` — **project-editable**; each code carries a **behaviour** ∈ `RESPONSIBLE` / `ACCOUNTABLE` / `CONSULTED` / `INFORMED` / `SUPPORT` / `OTHER` (Q7). Seeded R → RESPONSIBLE, A → ACCOUNTABLE, C → CONSULTED, I → INFORMED. RASCI adds `S` → SUPPORT. RAPID is a seeded **mapping**, not a vocabulary: Perform → RESPONSIBLE, Decide → ACCOUNTABLE, Input → CONSULTED, Recommend / Agree → OTHER | `BFC_NODE_ORG_ROLE`, `BR_ORG_ROLE` (`raci_behaviour`, FK-verified). Configurable because clients use RASCI / RAPID / house variants. **The lane (at most one RESPONSIBLE role per step) and the single Accountable (per step and per BR) read the behaviour, never the letter** (R2-D9). A project holds exactly one live code per load-bearing behaviour, RESPONSIBLE and ACCOUNTABLE: a second is refused when the code is saved (A-60). A behaviour is immutable once referenced, as for `FR_TYPE`; a project override of a global code must carry the global's behaviour |
| `BR_STATUS` | `DRAFT`, `CONFIRMED`, `BASELINED`, `SUPERSEDED` | `BUSINESS_REQUIREMENT.status_code` |
| `FR_FULFILMENT_STATUS` | `SPECIFIED`, `ACCEPTED_BY_VENDOR`, `BUILT`, `TESTED`, `DEFERRED` | `FUNCTION_REQUIREMENT.fulfilment_status_code` — **the vendor boundary is this column, not a table** |
| `PROJECT_STATUS` | `PLANNING`, `ACTIVE`, `ON_HOLD`, `CLOSED` | `PROJECT.status_code` |
| `BASELINE_STATUS` | `DRAFT`, `FROZEN`, `APPROVED`, `SUPERSEDED` — **`is_system`, not project-editable** | `BASELINE.status_code`. Code compares the values: a CR may target only FROZEN or APPROVED (Q8, §5.3 CHANGE_REQUEST) |
| `FIELD_DATA_TYPE` | `STRING`, `INTEGER`, `DECIMAL`, `DATE`, `DATETIME`, `BOOLEAN`, `TEXT`, `UUID` | `DATA_FIELD.data_type_code` |

**Four deliberate exclusions from `code_master` — all playbook §9.3 deviations, all to be
recorded in `docs/PLAYBOOK_DEVIATIONS.md`:**

- **CRUD (`C`/`R`/`U`/`D`)** is a `CHECK (crud_code IN ('C','R','U','D'))`, not a lookup. It
  is a closed four-value vocabulary no client renames, and it must be a real `char` column
  for the generated `direction` column to work (§5.4.2). Making it configurable would let a
  consultant break the INPUT/OUTPUT derivation.
- ~~**`APP_ROLE` is its own table**~~ — **withdrawn (D-9, finding S1).** The argument was
  that permissions branch on it, so it is not a dropdown. In practice having it as a table
  while the pseudocode used a second, different vocabulary is what produced the HIGH
  finding. It is now one boolean (`app_user.is_platform_admin`) plus one `code_master`
  category (`PROJECT_ROLE`), which is both playbook-conformant and the reason
  `CLIENT_REVIEWER` can no longer be granted by accident.
- **`DIAGRAM_LAYOUT.diagram_type`** (`ERD` / `PROCESS_FLOW` / `DFD`) is a `CHECK`. The renderer
  branches on each value, and the per-type object rules in §6.2 must name the literal. A
  code_master FK could not carry those rules, and "not project-editable" is what a CHECK already
  means.
- **`CODE_MASTER.behaviour_code`** is a `CHECK`, with one vocabulary per category that has
  one: `FR_TYPE` → `FORM` / `INTERFACE` / `REPORT` / `BATCH` / `OTHER` (D-27), and
  `RACI_TYPE` → `RESPONSIBLE` / `ACCOUNTABLE` / `CONSULTED` / `INFORMED` / `SUPPORT` / `OTHER`
  (Q7). It is the stable vocabulary code branches on, so that the *labels and codes* of those
  two categories can be configurable. A configurable behaviour would reintroduce the problem
  it solves.

**Scoping:** `code_master.project_id` is nullable — `NULL` is the FTC-wide default library,
non-null is a per-project override shadowing the global of the same `category + code`. See
A-16; this is the flexible option and it is not free.

**Resolution has exactly one owner: `services/code_master.resolve()` (§7.12, finding D12).**
Playbook §9.10 exists to stop a rule like this living in prose and being reimplemented per
consumer. The template generator and the import validator are two consumers of the same
data; when they disagreed about the tier, a project that renamed `HIGH` to `MAJOR` got a
template offering values its own validator rejected, with an error the consultant could not
act on. The React dropdowns are the third consumer and their divergence would have been
silent.

---

## 9. API surface

All under `/api/v1`. Every route below is **protected** except `POST /auth/login` — an
unauthenticated read is a finding, not a detail. **Every `PATCH` on an editable business
entity requires `row_version` in the body and returns 409 on mismatch (D-6).** **Every
`DELETE` is a soft delete and returns 409 naming the active dependents, if there are any
(R2-D2).**

**Every route declares exactly one guard (R2-S1, §7.8).** The guard is part of the route's
definition, not a comment in this document, and a route without one does not register. This
table replaces the first draft's route-class table and its hand-kept list of object-id
routes. That list had already fallen seven route families behind by D-31.

| Guard | Resolves | Routes |
|---|---|---|
| `public` | nothing — no JWT | `POST /auth/login` **only** |
| `authenticated` | the JWT user; the service filters | `GET /auth/me`, `GET /projects` (via `visible_project_ids`), `GET /programs` (admin: all; program grant: its one), `GET /process-flow-json/schema` |
| `platform_admin` | `current_user().is_platform_admin`, per request | `/users*`, `/clients*`, `POST /projects`, `POST /programs`, `PATCH /programs/{id}`, `POST/DELETE /programs/{id}/projects*`, `POST /programs/{id}/access`, `POST /access/reassign`, `GET/PUT /control-rules/defaults`, `PUT /code-master/FR_TYPE` (global tier) |
| `project_ctx(role)` | `require_project(user, {project_id}, role)` | **every route under `/projects/{id}/…`** — REVIEWER for GET and export; EDITOR for writes and import validate; OWNER for freeze, access, rate card, control rules, FR types |
| `object_guard(Model, role)` | the object's owning project, then `require_project` | `/bfc-nodes/{id}` · `/business-requirements/{id}` · `/data-entities/{id}` · `/data-fields/{id}` · `/external-entities/{id}` · `/org-units/{id}` · `/org-roles/{id}` · `/process-flows/{id}` · `/solutions/{id}` · `/function-requirements/{id}` (incl. `/interface`, `/complexity`) · `/applications/{id}` · `/stakeholders/{id}` · `/issues/{id}` · `/benefits/{id}` · `/risks/{id}` · `/change-requests/{id}` · `/phases/{id}` · `/wbs-items/{id}` · `/baselines/{id}` · `/baselines/diff` (both ids, one project) · `/bulk/batches/{id}` · `/access/{grant_id}` (a program grant resolves to no project → platform admin) · **each restore route**, one per `RESTORABLE` entity (§7.12) |
| `program_ctx(role)` | `require_program(user, {program_id}, role)` | `GET /programs/{id}`, `/programs/{id}/dashboard`, `/counts`, `/interfaces`, `/effort`, `/control-status`, `/plan-vs-actual` |

Surrogate ids are sequential `bigint`s, so enumeration is trivial and looks like normal use.
**Acceptance criterion 49 walks the running app and fails on any route that declares no guard,
or a guard that does not fit its path.**

| Method · Path | Request | Response |
|---|---|---|
| `POST /auth/login` | email, password | JWT + user profile |
| `GET /auth/me` | — | current user + project grants |
| `GET /users` · `POST /users` · `PATCH /users/{id}` | user fields | user(s). **Admin only** |
| `GET /clients` · `POST /clients` | client fields | client(s). **Platform admin** — a client list is a cross-project read |
| `GET /projects` | — | **only projects the caller is granted** |
| `POST /projects` · `GET/PATCH /projects/{id}` | project fields, optional `program_id` | project. **POST: platform admin; no grant is created** (D-32). `program_id` is not PATCHable — moving goes through `/programs/{id}/projects` |
| `GET /projects/{id}/access` | — | **effective access**: every user who can open the project, with role and source — PROJECT grant, PROGRAM grant (named), or PLATFORM_ADMIN (D-32). **OWNER** |
| `POST /projects/{id}/access` · `DELETE /access/{grant_id}` | user_id, project_role_code | a project grant. **OWNER.** Same scope → role change; **user holds another active grant → 409 naming it** (R2-S4). Revokes are audited (S9) and never restorable (R2-S5) |
| `GET /projects/{id}/bfc-tree` | — | full L1–L5 tree |
| `POST /projects/{id}/bfc-nodes` · `PATCH/DELETE /bfc-nodes/{id}` | name, parent_id | node incl. generated `hier_code` |
| `PATCH /bfc-nodes/{id}/reorder` | new_seq_no | re-coded subtree |
| `GET/POST /projects/{id}/org-units` · `/org-roles` | org fields | client org tree + roles |
| `GET/POST /projects/{id}/data-entities` · `PATCH/DELETE /data-entities/{id}` | name, description | DE incl. generated `de_number` |
| `GET/POST /data-entities/{id}/fields` · `PATCH/DELETE /data-fields/{id}` | field fields | data field |
| `GET/POST /projects/{id}/business-requirements` · `PATCH/DELETE /business-requirements/{id}` | bfc_node_id, statement, logic | BR incl. generated `br_number` |
| `POST/DELETE /business-requirements/{id}/data-entities` | de_id, crud_code | BR↔DE links; `direction` is returned, never sent |
| `POST/DELETE /business-requirements/{id}/org-roles` | org_role_id, raci_code | BR↔role links (renamed from `/roles`, VB law 7, S1-8) |
| `PATCH /bfc-nodes/{id}/process` | is_process, row_version | promote / demote a node (D-23). Promote returns the new BR; demote is 409 while the BR is active |
| `POST/DELETE /bfc-nodes/{id}/data-entities` | de_id, direction | process step ↔ DE links. DELETE is 409 while a BR CRUD depends on it (D-24) |
| `POST/DELETE /bfc-nodes/{id}/org-roles` | org_role_id, raci_code | process step ↔ role links (renamed from `/roles`, S1-8) |
| `GET/POST /projects/{id}/external-entities` · `PATCH/DELETE /external-entities/{id}` | name, kind_code, description | external parties incl. `EXT-0001` (D-24a) |
| `POST/DELETE /bfc-nodes/{id}/external-flows` | external_entity_id, direction, data_entity_id | step ↔ external party flows (D-24a) |
| `GET/POST /projects/{id}/process-flows` · `PATCH/DELETE /process-flows/{id}` | from, to, flow_type, condition_label | flow edges between process steps (D-20, D-23). **409 on a second edge between the same steps under the same condition** (Q2) |
| `GET /bfc-nodes/{id}/dfd` · `/dfd/export?format=mermaid` | — | the DFD graph: processes, stores, externals, flows (D-31) |
| `GET /process-flow-json/schema` | — | the `vb-process-flow/1.0` JSON Schema, example and AI conversion prompt pack (D-25). The pack names **Claude or Microsoft Copilot under FTC's own accounts only** and opens with the personal-data removal step (D-36). **`authenticated`** |
| `GET /bfc-nodes/{id}/process-flow/export?format=json` | — | the flow as `vb-process-flow/1.0`; every existing step carries `br_number`, `hier_code` and `row_version` (R2-D1, R2-D5) |
| `POST /projects/{id}/bulk/process-flow/validate` | JSON file, **`anchor_bfc_node_id`, `mode`** (merge \| replace) — chosen in the UI | `IMPORT_BATCH` + per-item errors and warnings, INSERT / UPDATE / RETIRE / KEPT per item. **A file whose `parent` or `mode` disagrees with the route → 422, nothing staged** (R2-P3). **Writes nothing** (D-25). Preview and commit use the `/bulk/batches/{batch_id}` routes |
| `GET /projects/{id}/erd?subject_area={bfc_node_id}` · `/erd/export?format=mermaid` | — | the logical ERD graph with cardinality and saved layout (D-29) |
| `GET/PUT /projects/{id}/diagram-layouts/{diagram_type}/{scope_key}` | [{object_type, object_id, x, y, w, h, collapsed}] | saved positions (D-30). **EDITOR** to PUT |
| `GET /bfc-nodes/{id}/process-flow?variant=AS_IS\|TO_BE` | — | the graph: nodes, edges, lanes, stores (D-21, D-22) |
| `GET /bfc-nodes/{id}/process-flow/export?format=mermaid` | — | the same graph as Mermaid text |
| `GET /projects/{id}/flow-completeness` | — | orphan steps, missing start/end, unlabelled branches |
| `GET/POST /projects/{id}/solutions` · `PATCH/DELETE /solutions/{id}` | name, description, category_code | Solution incl. generated `solution_number` |
| `POST/DELETE /business-requirements/{id}/solutions` | solution_id, coverage_note | BR↔Solution links |
| `GET/POST /projects/{id}/function-requirements` | name, description, fr_type_code, solution_id (optional) | FR incl. generated `fr_number`; `warnings: ["no solution"]` when unlinked (D-28) |
| `GET /solutions/{id}/function-requirements` | — | FRs under one Solution |
| `PATCH/DELETE /function-requirements/{id}` | FR fields incl. solution_id, fr_type_code, `suggested_br_id` is **read-only** | FR. Type change re-derives `effort_days` (409 with live interface detail on a move away from INTERFACE). Linking a solution returns a `prompt` when the suggested BR is not answered by it (D-34). `effort_days` in the body is ignored |
| `PUT/DELETE /function-requirements/{id}/interface` | source/target application, pattern, method, frequency, volume_note, data_entity_ids, row_version | interface detail. 422 unless the type's behaviour is INTERFACE (D-27) |
| `GET /projects/{id}/interfaces` · `/interfaces/export` | filters: application pair, status | **the generated interface list** (D-27), and the same as `.xlsx` |
| `GET/PUT /projects/{id}/code-master/FR_TYPE` | code, label, behaviour, sort, is_active | the project's FR types. **OWNER** (D-27) |
| `GET /business-requirements/{id}/function-requirements` | — | **derived** via `v_br_function_requirement` (D-7) |
| `GET/POST /projects/{id}/applications` · `PATCH/DELETE /applications/{id}` | code, name, vendor, kind, lifecycle | application catalogue |
| `POST/DELETE /solutions/{id}/applications` | application_id | to-be allocation |
| `POST/DELETE /bfc-nodes/{id}/applications` | application_id | as-is landscape |
| `GET/POST /projects/{id}/stakeholders` · `PATCH/DELETE /stakeholders/{id}` | name, title, org_unit_id, is_bpo | client-side people (D-4) |
| `GET/POST /projects/{id}/issues` · `PATCH /issues/{id}` | issue fields, br_ids | issue incl. generated `issue_number` |
| `GET /projects/{id}/baselines` | — | baseline list |
| `POST /projects/{id}/baselines/freeze` | note, `bump: MINOR\|MAJOR`, `confirm_text` | new frozen baseline over all **30** entities (D-3, D-12, D-14, D-18, D-20, D-24a, D-27, R2-D7). **OWNER only**; typed confirmation; consistency check must pass (P6, P9, D11) |
| `GET /baselines/{id}` | — | baseline header + snapshot counts |
| `GET /baselines/diff?from={a}&to={b}` | — | ADDED / CHANGED / REMOVED / **MOVED** per entity. **404 unless both baselines belong to one project the caller is granted** (S3) |
| `GET /projects/{id}/traceability` | — | process step → BR → Solution → FR → Application matrix; unlinked FRs grouped last |
| `GET /projects/{id}/solution-matrix` | — | solutions by category × L1 area (D-7) |
| `GET /projects/{id}/application-gap` | — | as-is vs to-be migration backlog (D-8) |
| `GET /projects/{id}/coverage` | — | scope-gap report (§4.3) |
| `GET /projects/{id}/bulk/templates/{entity}` | — | `.xlsx` template with **that project's** resolved `code_master` dropdowns (D-5, D12). Moved under the project: the unscoped route could only serve the global tier. `entity` includes `wbs` (with the date-format step, D-33) |
| `GET /projects/{id}/bulk/{entity}/export` | — | current rows in template shape, with business keys |
| `POST /projects/{id}/bulk/{entity}/validate` | multipart file; `import_mode` (**`wbs` only**) | `IMPORT_BATCH` + per-row errors and warnings. **Writes nothing**. `entity` ∈ issues, data-entities, data-fields, business-requirements (keyed by **BR number**, R2-D1), function-requirements (R2-D6), **wbs** (keyed by MS Project Unique ID, D-33). Body capped at ingress (R2-S8) |
| `GET /bulk/batches/{batch_id}` | — | staged rows for the review preview |
| `POST /bulk/batches/{batch_id}/commit` | `acknowledged_inserts`, `acknowledged_retires` | applies the batch in one transaction, under a row lock, re-validating every row (P2, D1, D3). **422 unless each count is acknowledged whenever it is non-zero** (R2-P2) |
| `GET /projects/{id}/code-master/{category}` | — | codes + labels for dropdowns, resolved two-tier via `code_master.resolve` (S10 — the unscoped route could only return the global tier or leak every project's custom labels) |
| `PATCH /{entity}/{id}/restore` | — | un-delete (P5). **Registered once per `RESTORABLE` entity (§7.12), each with its own `object_guard`** — there is no generic `{entity}` parameter. No restore route exists for grants, control rules, users, `code_master`, programs or WBS lines (R2-S5). **409 while a parent is inactive** (R2-D2) |
| `GET /projects/{id}/consistency` | — | `hier_code`/`level_no` drift and completeness (D11) |
| `GET/PUT /projects/{id}/rate-card` | FR type × complexity × days, **`change_rationale`** | the effort rate card (D-13). **OWNER.** Refused without a rationale; audited old → new (R2-D7) |
| `PATCH /function-requirements/{id}/complexity` | complexity_code, row_version | FR incl. derived `effort_days` |
| `GET /projects/{id}/effort-summary` | — | man-days by FR type, solution, phase, L1 area, with an **Unassigned** bucket (D-28) |
| `GET /baselines/diff?from={a}&to={b}&priced=true` | — | the diff with effort deltas per change class (D-13) |
| `GET/POST /projects/{id}/benefits` · `PATCH/DELETE /benefits/{id}` | benefit fields | benefit incl. `BEN-0001` (D-14) |
| `POST/DELETE /benefits/{id}/solutions` | solution_id, contribution_pct | benefit ↔ solution |
| `GET /projects/{id}/value-ranking` | — | value ÷ effort per solution, **one ranking per `measure_unit`** (D-14, R2-D12, Q9) |
| `GET/POST /projects/{id}/risks` · `PATCH /risks/{id}` | risk fields | risk incl. `RSK-0001`, derived `exposure_score` (D-15) |
| `POST /risks/{id}/materialise` | description | creates the issue, links it, leaves the risk row intact |
| `GET/POST /projects/{id}/change-requests` · `PATCH /change-requests/{id}` | CR fields | CR incl. `CR-0001` (D-16) |
| `POST /change-requests/{id}/analyse` | seed objects | computes `CR_IMPACT` — the blast radius |
| `GET /change-requests/{id}/price` | — | effort delta, benefit delta, phases hit, displacement candidates |
| `POST /change-requests/{id}/decide` | outcome, displaces_cr_id, rationale, alternative_rejected | **OWNER.** Refuses net-positive effort with no displacement named |
| `GET/POST /projects/{id}/decisions` | decision fields | the decision log (D-17) |
| `GET/POST /projects/{id}/phases` · `PATCH/DELETE /phases/{id}` | phase fields | delivery waves (D-18) |
| `POST/DELETE /solutions/{id}/phases` · `/dependencies` | phase_id · depends_on_solution_id | assignment and prerequisites; cycles rejected |
| `GET /projects/{id}/phase-plan` | — | effort by phase, dependency violations, volatile areas still in the current wave |
| `GET/PUT /control-rules/defaults` | analysis_code, threshold, escalate, action | **the FTC house defaults** (`project_id IS NULL`). **Platform admin.** Affects future projects only |
| `GET/PUT /projects/{id}/control-rules` | analysis_code, threshold, escalate, owner role, action, is_enabled, change_rationale | that project's agreed governance (D-19). **OWNER.** Every change is audited and needs a rationale |
| `POST /projects/{id}/control-rules/reset` | change_rationale | re-copy from the house defaults — the explicit opt-in |
| **`GET /projects/{id}/control-panel`** | — | **every analysis vs its rule → GREEN / FLAG / ESCALATE, with owner and action. The PMO's one screen** |
| `GET /projects/{id}/analysis/{analysis_code}` | — | any single analysis, table + `headline_value` |
| `GET /bulk/batches/{batch_id}/preview` | — | per-row INSERT/UPDATE verdict, before/after per changed field, stakeholders to be created, and the batch summary (P3, D3) |
| `PATCH /users/{id}/deactivate` | — | platform admin. Effective on the target's next request (S4) |
| `POST /projects/{id}/purge` | reason, `confirm_text` (the project code) | **platform admin.** Contract-required deletion (Q15, §15.3): deletes live and snapshot rows as `vb_owner` and destroys the archive key. The one hard-delete route in VB |
| `GET /programs` · `POST /programs` · `PATCH /programs/{id}` | program_code, program_name, client_id, description | programs (D-32). GET: `authenticated` (admin sees all, a program-grant holder sees its one). POST/PATCH: **platform admin** |
| `POST /programs/{id}/projects` · `DELETE /programs/{id}/projects/{project_id}` | project_id; `confirm_hash` (omit for preview) | **Platform admin.** Without `confirm_hash`: a preview naming who **gains** and who **loses** access, plus its hash — writes nothing. With it: moves the project; **409 if the preview changed** (R2-S3). Audited |
| `POST /programs/{id}/access` | user_id, project_role_code | a **program grant** — one role on every project in the program (Q10). **Platform admin.** 409 if the user holds another active grant |
| `POST /access/reassign` | user_id, project_id \| program_id, project_role_code, rationale | revoke the user's one grant and issue the new one, in one transaction (R2-S4). **Platform admin** |
| `GET /programs/{id}` · `/dashboard` · `/counts` · `/interfaces` · `/effort` · `/control-status` · `/plan-vs-actual` | — | **program roll-ups** (D-32): lists of `{project, result}`, one per project in `visible_project_ids ∩ program`, each built by the per-project report (R2-S2). **`program_ctx`** — a project grant sees none (404) |
| `GET /projects/{id}/wbs` | filters: phase, unlinked | the imported WBS tree with links and plan-vs-actual (D-33) |
| `PATCH /wbs-items/{id}` | phase_id, solution_id, row_version | **links only** (D-33). Any other field → 422 "Change it in MS Project and re-import". **EDITOR** |

---

## 10. Acceptance criteria

Each is observable by someone who did not build it.

1. A BFC node cannot be created below level 5; the attempt returns 422 with a `detail`
   string naming the limit.
2. Creating the third child of node `01.02` produces `hier_code = "01.02.03"`, and the code
   appears only after save — never on the empty form.
3. Reordering `01.02` to position 1 renumbers its siblings **and** re-codes every
   descendant; no orphaned or duplicate code remains in the project.
4. A process node accepts a data-processing description; a non-process node rejects it.
5. Creating a process node creates exactly one business requirement in the same
   transaction; creating a non-process node creates none.
5a. A second business requirement on a process node is rejected by the database, not the UI
   (D-2). Dropping `UNIQUE (bfc_node_id)` makes it succeed — that is the documented
   reversal path.
6. Two data entities created concurrently in one project receive different DE numbers; no
   duplicate `de_number` exists within a project under a 20-way concurrent create.
7. A data field flagged foreign key without a target entity is rejected; a target entity in
   a different project is rejected.
8. A data entity can be linked to one BR as both `R` and `U`, producing two rows whose
   generated `direction` reads INPUT and OUTPUT respectively. An attempt to store `R`
   against OUTPUT is impossible by construction, not by validation.
9. A function requirement rejects an `fr_type_code` not present in `code_master` category
   `FR_TYPE` (was `FR_CATEGORY`, D-27). Creation without a Solution is accepted with a
   warning (D-28 reverses D-7 here; see criterion 105).
10. A solution of category `PEOPLE` can be created, linked to two BRs, and carry **no**
    function requirements at all — and the traceability report still reports it as a
    complete answer. *(This is the acceptance criterion for "blueprints the whole operation,
    not just the software".)*
10a. One Solution linked to three BRs, carrying two FRs, yields six rows in
    `v_br_function_requirement`, and no `fr_br` table exists.
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
    table in `FREEZE_SET`** (30: the 29 of D-31 plus the rate card, R2-D7), in a single transaction.
14. After freezing v1.0, editing a live BR does **not** change the v1.0 snapshot.
15. A freeze that fails partway leaves zero snapshot rows and no baseline header.
16. Adding one BR and deleting another, then freezing v1.1, makes `diff(v1.0, v1.1)` report
    exactly one ADDED and one REMOVED.
17. Editing a BR's logic text between freezes makes the diff report it CHANGED, naming the
    `logic_text` field.
17a. Renaming a data entity between freezes makes the diff report the DE as CHANGED — the
    case that motivated D-3.
17b. Two sessions PATCH the same BR with the same `row_version`; the first succeeds, the
    second returns 409 with a `detail` string, and the first write is not lost (D-6).
18. A user with no grant on project P receives **404** for `GET /projects/P` and P does not
    appear in `GET /projects`.
19. A user with `REVIEWER` on project P receives 403 on any write to P.
20. Every VB endpoint except `POST /auth/login` returns 401 without a valid JWT.
21. The app refuses to start when `JWT_SECRET_KEY` is unset (§9.1).
22. `created_by` on a newly created BR equals the JWT subject, even when the request body
    carries a different user id (§9.2).
23. Deleting a business requirement sets `is_active = FALSE`; the row remains queryable and
    prior baselines are unaffected.
24. Creating a process node auto-creates its first business requirement in the same
    transaction; creating a non-process node creates none.
25. A second Accountable (`A`) role on one BR is rejected by the database, not the UI.
26. A frozen `baseline_*` row cannot be updated or deleted, including by direct SQL —
    the reject trigger fires.
27. A CI test asserts every `baseline_*` table's column set matches its live table
    (minus audit columns, plus snapshot columns); adding a column to
    `business_requirement` without updating the shadow fails the build.
28. Renaming the `code_master` label "High" to "Major" changes the live issue list and
    leaves every frozen baseline reading "High".
29. Every VB screen renders the Fortience Consulting Inc. footer (§9.9).

### Added by the round-1 design review

30. **(P1)** An edit committed while a freeze is running appears in neither half of that
    baseline — the freeze reflects one consistent snapshot across all 30 tables.
31. **(P2)** Committing the same import batch twice applies it once; the second call
    returns 409. Two concurrent commits of one batch produce one set of rows.
32. **(P3, D3)** The preview states, per row, INSERT or UPDATE, and shows before/after for
    every changed field. A batch that would create rows cannot be committed without
    acknowledging the exact insert count.
33. **(P4, D-10)** Reordering a node whose subtree is 47 nodes deep produces a diff of
    **48 MOVED and 0 CHANGED**.
34. **(P5)** A soft-deleted business requirement can be restored, and while it is deleted a
    replacement BR can be created on that process node.
35. **(P6)** Freeze is refused to an EDITOR, refused without the typed confirmation, and
    refused while `consistency_check` reports drift.
36. **(P7)** Moving the third sibling to position one succeeds, with no unique-index
    violation at any point, and every descendant's `hier_code` is recomputed.
37. **(P9)** The tenth freeze on a project is `v1.10`, not `v2.0`; a `MAJOR` bump yields
    `v2.0`; two simultaneous freezes produce one baseline and one 409.
38. **(P10)** A unique-constraint violation returns 409 with a `detail` string, never a 500.
39. **(D1)** Validating a Data Field batch, then soft-deleting the parent DE, then
    committing → the batch is rejected. No live field exists under a dead entity.
40. **(D2)** Exporting rows, editing one in the app, then re-uploading the export → that
    row is a **validation error naming the current value**, and the other rows still commit.
41. **(D5)** Two baselines with different `hash_spec_version` report
    `SCHEMA_VERSION_MISMATCH`, not "everything CHANGED". Emptying a text field reports
    CHANGED, not unchanged.
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
48. **(S1, D-9)** An EDITOR is refused baseline freeze and access-granting; a REVIEWER is
    refused every write; a platform admin passes every check.
49. **(S2, S7, R2-S1)** **The route-coverage test.** It walks every route **registered in
    the running app** — not a list in §9 — and fails if any route declares **no guard**, or
    more than one. It also fails if the declared guard does not fit the path: a
    `{project_id}` path not guarded by `project_ctx`; an `{id}` path outside `/projects/…`
    guarded by anything other than `object_guard`, `program_ctx` or `platform_admin`; an
    `object_guard` on a model with no `owning_project_id()`; or `public` on any route but
    `POST /auth/login`. Registering a route with no guard fails at import time. *This test is
    the stated condition of deferring row-level security.*
50. **(S3)** `GET /baselines/diff?from={a}&to={b}` returns 404 when the two baselines belong
    to different projects, and when they belong to a project the caller is not granted.
51. **(S4)** A deactivated user's existing token is rejected on the next request. Revoking
    platform admin takes effect on the next request without re-login.
52. **(S5)** An issue description beginning `=HYPERLINK(...)` exports as an inert text cell.
53. **(S8, D-11)** Creating an app user with a non-FTC email address is refused, and no
    `CLIENT_REVIEWER` role exists to grant.
54. **(S9)** Freezing a baseline, reordering the chart, soft-deleting a row and revoking a
    grant each write an `AUDIT_EVENT`.
55. **(S11)** The application database role cannot `UPDATE` or `DELETE` any `baseline_*`
    row, tested by attempting it directly.

### Added by the control framework (D-13…D-19)

56. **(D-13)** Setting an FR's complexity to COMPLEX stores `effort_days` from the rate
    card. Changing the rate card afterwards does **not** change that FR's `effort_days`.
57. **(D-13)** A baseline frozen before a rate-card change and one frozen after report the
    same `effort_days` for an unchanged FR — a signed baseline cannot be repriced.
58. **(D-13)** `GET /baselines/diff?priced=true` on a v1.1 that added two COMPLEX forms and
    removed one SIMPLE report returns the correct net man-days, not a row count.
59. **(D-14)** A benefit cannot be saved without an accountable org role.
60. **(D-14)** `value_ranking` on a project with one high-value/low-effort solution and one
    low-value/high-effort solution ranks them in that order, and names the second as a
    displacement candidate.
61. **(D-15)** A risk scored LIKELY × MAJOR carries a higher `exposure_score` than
    POSSIBLE × MODERATE, and the score cannot be edited independently of its inputs.
62. **(D-15)** Materialising a risk creates an issue, links it, sets the risk to
    MATERIALISED, and **leaves the risk row present** — the evidence it was foreseen.
63. **(D-16, Q8)** A change request cannot be raised against a working set, nor against a
    SUPERSEDED baseline (422). Against a FROZEN or an APPROVED baseline it is accepted.
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
    ~50,000 rows across the 30 frozen tables — completes inside the request timeout, in one
    transaction.
77. **(A-37)** A `cr_impact` row naming two impacted objects, or none, is rejected by the
    database. A row naming an object in another project is rejected by the composite FK.
78. **(A-41)** A `decision` row cannot be updated or deleted, including by direct SQL. A
    correction is a new row whose `supersedes_decision_id` points at the original, and both
    remain readable.
79. **(D-19)** Creating a project copies every FTC house default into that project's own
    control rules. Editing a house default afterwards leaves that project's thresholds
    unchanged, and a project created after the edit picks up the new value.
80. **(D-19)** An OWNER can change a project's `priced_diff` flag threshold from 5% to 15%;
    the change is refused without a rationale, and when accepted it writes an
    `AUDIT_EVENT` recording the old value, the new value and the reason.
81. **(D-19)** A rule can be disabled (`is_enabled = false`) and disappears from the control
    panel without being deleted.
82. **(D-19)** A house default may be saved with no owning org role; a project rule may not.
83. **(D-20, D-23)** A flow edge to a non-process node is rejected; to a process node in
    another project, rejected; with neither end set, rejected.
84. **(D-20)** A `CONDITIONAL` edge without a `condition_label` is rejected.
85. **(D-20)** A rework loop — A → B → C → A — is **accepted**, and
    `generate_process_flow` terminates and returns each step once.
86. **(D-21, D-23)** `generate_process_flow` on a parent node returns its process
    descendants as nodes — at whatever level each branch ends — the edges between them, one
    lane per Responsible org role, and every input/output data entity as a store. Called on
    a process node it returns 422.
87. **(D-22)** The same L4 node rendered `AS_IS` and `TO_BE` returns identical nodes, lanes
    and edges, and differing `system` values on the steps whose application changes.
88. **(D-21)** `export_process_flow` returns Mermaid text that renders, with one subgraph
    per lane and the condition label on each conditional edge.

### Added by Ben's v8 review (D-23…D-31)

89. **(D-23)** A childless L4 node can be promoted to a process; its BR is created in the
    same transaction. Adding a child to any process node is rejected by the database, not
    only the service.
90. **(D-23)** Demoting a process whose BR is active returns 409 naming the BR. After the BR
    is retired, demotion succeeds and the node accepts children.
91. **(D-23)** One L2 branch ending at L4 and another ending at L5 both appear, as steps, in
    one generated process flow for their common L1 parent.
92. **(D-24)** Linking a BR CRUD `U` on DE-0007 to a step with no output DE-0007 creates the
    step's output row in the same transaction; the process flow shows it immediately.
93. **(D-24)** Removing that step output while the BR's `U` exists returns 409 naming the
    BR. `flow_completeness_report.crud_without_io` is 0 on any project, always.
94. **(D-24a)** An external entity "Customer" linked as an input to "Receive order" appears in
    the DFD as an external party with a labelled flow into that step, and in a frozen
    baseline's snapshot.
95. **(D-25)** `GET /process-flow-json/schema` returns a JSON Schema that the example file in
    the same response validates against.
96. **(D-25)** A valid file with 12 steps (3 existing by `hier_code`, 9 new), 2 unknown data
    entities and 1 unknown lane: validate writes nothing to any business table, reports the
    lane as an error with its `source_ref`, the 2 DEs as warnings to create, and commit is
    refused until the lane is fixed.
97. **(D-25)** After fixing the lane, commit creates 9 process nodes, 9 BRs, 2 data entities
    and every flow edge in one transaction; exporting the flow as JSON and re-importing it
    unchanged produces a batch of 0 inserts.
98. **(D-25)** A file in `mode: "merge"` that omits an existing edge leaves the edge in place.
    The same file in `mode: "replace"` shows the removal count in the preview and is refused
    at commit unless that count is acknowledged.
99. **(D-25)** A 3 MB file, a file nested 40 levels deep, a file with 501 steps and a file
    containing `NaN` are each rejected before anything is staged.
100. **(D-26)** A data entity with one PK field and no data types saves without error;
     `validate_entity_model` lists no warning for the missing types.
101. **(D-27)** An OWNER renames FR type `INTERFACE` to "連携" and adds type "API" with
     behaviour INTERFACE. FRs of both types show the interface panel and appear on the
     interface list; no code change or deployment is involved.
102. **(D-27)** Interface detail on an FR of type FORM returns 422. Changing an interface FR's
     type to FORM while it has interface detail returns 409.
103. **(D-27)** The interface list shows one row per interface FR with its FR number, source →
     target application and data entities carried. An interface FR with no source is listed
     as incomplete. There is no separate interface number series in the database.
104. **(D-27)** A new FR type with no rate-card rows: an FR of that type saves, and rating
     its complexity returns 422 naming the missing rate-card cell.
105. **(D-28)** An FR created with no Solution saves and returns a warning. It appears in
     `br_coverage_report`, in the `fr_unlinked` control-panel rule, and in `effort_summary`
     under Unassigned.
106. **(D-28)** An FR import of 50 rows, 10 without a Solution number, validates with 10
     warnings and 0 errors, and commits. A BR import row naming a summary node is an error.
107. **(D-29)** Two entities joined by a composite FK draw as one relationship line from the
     FK rows to the parent's PK rows. A mandatory FK draws `1` on the parent side; an
     optional or unknown one draws `0..1`.
108. **(D-29)** The ERD filtered to one L1 subject area shows only the entities its steps read
     or write, plus a labelled stub for every FK leaving the area.
109. **(D-30)** An entity dragged on the ERD is in the same place after a reload and for a
     second user. Freezing and diffing a baseline is unaffected by any layout change.

### Added by design review round 2 (D-32…D-36)

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
113. **(R2-P3, R2-P4, Q5)** A `replace` file omits one unguarded edge, one step input that
     BR-0012's `R` CRUD depends on, one unguarded step output, and one whole step. The
     preview lists the edge and the output as RETIRE and the input as KEPT, with a warning
     naming BR-0012. Commit retires exactly those two rows. The omitted step, its BR and its
     external flows are unchanged.
114. **(R2-P4, R2-D9)** A step has RESPONSIBLE role X and ACCOUNTABLE role Y, and the file
     gives it lane L. After commit, the step's only RESPONSIBLE role is L's role and Y is
     untouched. This holds in `merge` mode too.
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
     naming the node's current name, lane and description. The other steps still stage. The
     preview shows before/after for every UPDATE step.
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
     is live is refused, A-60). A step whose role is `P` is drawn in that role's lane. A second role on one
     BR whose code has behaviour ACCOUNTABLE is rejected, whatever its letter.
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
133. **(D-34, R2-D16)** An FR import row names BR-0012 and no solution. It saves unlinked,
     with a warning and `suggested_br_id` = BR-0012. Linking it to SOL-0003, which BR-0012
     does not reach, keeps the suggestion and returns a prompt. Linking BR-0012 to SOL-0003
     clears it. Neither step makes the FR read CHANGED in a diff.
134. **(D-34)** No import, with or without BR numbers, ever creates a SOLUTION row.
135. **(R2-S1)** For each of `/external-entities/{id}`, `/process-flows/{id}`,
     `/function-requirements/{id}/interface`, `/benefits/{id}`, `/risks/{id}`,
     `/change-requests/{id}`, `/phases/{id}`, each restore route, `/programs/{id}` and
     `/wbs-items/{id}`: a user granted only on project A, calling with an id owned by project
     B, receives 404.
136. **(R2-S5)** No restore route exists for a grant, a control rule, a user or a
     `code_master` row. A revoked grant can come back only through `grant_access`, which
     writes `ACCESS_GRANTED`.
137. **(R2-S7)** A step named `x"] --> Y[click` and a lane named `%%{init: {"securityLevel":
     "loose"}}%%` export from all three Mermaid exporters as inert quoted labels. No exported
     line begins with `click`, `%%{init`, `style`, `classDef` or `linkStyle`, and the output
     renders.
138. **(R2-S8)** A 50 MB POST to a validate route returns 413, and the handler and its
     dependencies are never invoked, as seen in the log. A chunked body with no
     Content-Length is cut off at the cap. A 9 MB `.xlsx` accepted for validation creates no
     file under `TMPDIR`.
139. **(D-32, R2-S4)** A user holding an EDITOR grant on P1 is granted P2 by P2's OWNER. The
     call returns 409 naming P1. A platform admin's `reassign` moves the user to P2 in one
     transaction, and one audit row names both. Two concurrent grants to one user produce one
     grant and one 409.
140. **(D-32)** A program grant (EDITOR) on PG lets its holder edit every active project in
     PG, including one created in PG afterwards. A project outside PG returns 404, and so
     does a project removed from PG, on the holder's next request.
141. **(D-32, R2-S3)** An OWNER, including an OWNER through the program grant, cannot move a
     project between programs. A platform admin's preview names every gainer and loser.
     Committing with a stale `confirm_hash` returns 409. The committed move writes one audit
     row listing both sets. Moving a project into a program of another client returns 422.
142. **(D-32, R2-S2)** A user with a project grant calling `GET /programs/{id}/dashboard`
     receives 404. A program holder receives one entry per visible project, each equal to
     that project's own report. A static check finds no query with `project_id IN` in
     `services/program.py`.
143. **(D-32)** A platform admin creating a project leaves no grant row. `GET
     /projects/{id}/access` on a program project lists the direct grants, the program
     holders (with the program's name) and the platform admins, each with its source.
144. **(D-36)** The prompt pack returned by `GET /process-flow-json/schema` names Claude and
     Microsoft Copilot under FTC accounts as the only approved services. Its first
     instruction is to remove personal data from the source.
145. **(Q1)** Creating, renaming or restoring a BFC node to a name already used by an active
     sibling, ignoring case, width and spacing, returns 409 naming the sibling.
146. **(Q2)** A second edge A → B with the same condition returns 409. With a different
     condition it is accepted. A second unconditional A → B returns 409.
147. **(Q14)** A batch uploaded 91 days ago has no `IMPORT_ROW` rows after the daily purge.
     Its header still shows who, when, entity and counts, and an uncommitted one reads
     REJECTED. One `IMPORT_ROWS_PURGED` audit row records the run. A batch 89 days old is
     untouched.
148. **(R2-D13)** `flow_completeness_report.ext_without_io` is 0 on any project, always.
149. **(A-46, R2-D9)** A step with no RESPONSIBLE role appears in
     `flow_completeness_report.no_lane` and is drawn in the "unassigned" lane.
150. **(D-32)** Every per-project criterion in §10 still passes when the caller's access
     comes through a program grant instead of a project grant. The suite runs the §10 access
     tests under both fixtures.
151. **(R2-D2)** Soft-deleting a BFC node whose BR is active returns 409 naming the BR. The
     node, the BR and their links are unchanged.
152. **(R2-S8, D-35)** An upload of exactly the route cap is accepted; one byte more returns
     413 from ingress.
153. **(Q16)** A user holding a program OWNER grant grants a colleague EDITOR on one project
     inside that program; it succeeds. The same user granting a project outside the program,
     or the program itself, is refused.
154. **(Q15)** `purge_project` by a non-admin returns 403, and without a reason 422. Run by a
     platform admin, it leaves no live or snapshot row for the project, the project's archive
     key is deleted, an existing archive file for it can no longer be decrypted, and a
     `PROJECT_PURGED` audit row names the project code, actor, date and reason with no
     content.
155. **(Q15, R2-S10)** Every baseline freeze writes one encrypted archive file under the
     project's own key; decrypting it and recomputing the hashes matches the frozen rows.

---

## 11. Assumptions

Confirm or kill each. Those marked ⚠ change the data model if wrong.

- ✅ `A-1` — **RESOLVED by D-2.** BR is a separate entity from the process node (D-23), **1:1**,
  enforced by `UNIQUE (bfc_node_id)`. It stays its own table so that issues and solutions
  can reference `br_id`, the BR number survives reordering, and reversing D-2 costs one
  dropped index (§5.4.1a).
- ✅ `A-2` — **RESOLVED by D-32 (2026-09-28).** "Project" stays the scoping key and the hard
  data wall. Several related projects of one client group under a **`PROGRAM`**, which owns no
  business data, so no FK moves. The program is an access scope and a set of roll-up reads
  (§4.14). *(Superseded text:)* If a client can run several projects under one commercial
  engagement, an `ENGAGEMENT` level goes between CLIENT and PROJECT and every FK moves.
- ⚠ `ASSUMPTION A-3` — **BR ↔ DE is one associative table keyed by CRUD**, with direction
  generated from it (`R` → INPUT, else OUTPUT). Not two relationships, and not two stored
  columns. *If wrong* — i.e. if a Read can legitimately be classified as output-side
  reference data — the generated column becomes two independent stored columns and the
  `(R, OUTPUT)` contradiction becomes possible again. **Ask before building; it is a
  five-minute conversation now and a data migration later.**
- ✅ `A-4` — **SUPERSEDED by D-7.** `FR_BR` no longer exists. An FR belongs to exactly one
  Solution; a Solution answers many BRs. BR → FR is the view `v_br_function_requirement`.
- ⚠ `ASSUMPTION A-5` — **Snapshot storage is typed shadow tables**, not a JSONB blob, so a
  diff is a SQL join rather than application-side JSON walking. *If wrong:* one table
  instead of eight, at the cost of diffability. `apple`'s recommendation in §5/§6 is
  authoritative here.
- ✅ `A-6` — **RESOLVED by D-3.** Baselines freeze all 17 tables: BFC, DE, Data Field, BR,
  Solution, FR, Application and Issue, with their link tables (§6.1).
- `ASSUMPTION A-7` — Snapshot rows are **hard-immutable**: no `is_active`, no update path,
  no soft delete. This is a deliberate, documented deviation from §9.7 — a baseline that
  can be soft-deleted is not a baseline. Goes in `docs/PLAYBOOK_DEVIATIONS.md`.
- `ASSUMPTION A-8` — Version labels auto-increment the minor (v1.0 → v1.1). Major bumps are
  a manual override. No branching of baselines.
- `ASSUMPTION A-9` — The client org tree is exactly three levels (Department → Division →
  Section) but stored self-referencing with a level code, so a fourth level costs a seed
  row rather than a migration.
- `ASSUMPTION A-10` — Roles belong to one org unit. A role spanning units (e.g. "Internal
  Auditor") would need a many-to-many; not modelled in MVP.
- ✅ `A-11` — **RESOLVED by D-11.** Record-level confidentiality stays out of MVP, and the
  exposure is now closed structurally rather than deferred: there is no `CLIENT_REVIEWER`
  role to grant, and `create_user` rejects a non-FTC email address. Finding S8 was that A-11
  was an assumption where it needed to be a gate — an escape clause in a numbered list is
  not a control, and the decision to grant would have been made by whoever was under time
  pressure during the engagement. Before any external party is given a login,
  record-level confidentiality is built first: `issue_dashboard` reports open issues per
  named stakeholder, i.e. a per-person complaint count.
- ✅ `A-12` — **RESOLVED by D-20…D-22, and brief question 7 with it.** The process flow is
  generated from the BFC, the data entities and the business requirements, plus one explicit
  flow-edge table. It is neither a stored diagram nor a narrative field: the structured data
  *is* the diagram, and `data_processing_desc` remains the human narrative alongside it.
  *(Superseded text: DFD is **not** stored as structured data. The L5 data-processing
  description plus the BR input/output data entities are the DFD source; rendering is
  deferred.)*
- ✅ `A-45` — **RESOLVED by D-23 (2026-09-28).** A process flow is drawn for any parent node
  and contains its process descendants, wherever each branch ends. *(Superseded text:)* A
  process flow is drawn for an L3 or L4 node, containing its L5
  descendants. Drawing at L2 or L1 would produce a diagram too large to read; drawing at L5
  is a single box. **If FTC's practice is to draw the flow at a different level, this is one
  line in `generate_process_flow`.**
- `ASSUMPTION A-46` — **Swimlanes come from the role whose RACI behaviour is RESPONSIBLE**
  on each step (R2-D9), not the Accountable one. Responsible is who does the work, which is
  what a lane represents. A step has at most one RESPONSIBLE role, and a flow import's lane
  replaces it. A step with none renders in an "unassigned" lane and is reported by
  `flow_completeness_report.no_lane`.
- `ASSUMPTION A-13` — Single tenant deployment (FTC's own instance). `PROJECT` is the
  isolation boundary, not a separate `tenant_id`.
- `ASSUMPTION A-14` — Password reset is admin-initiated in MVP; no self-service email flow.
- `ASSUMPTION A-15` — `Value_Bridge` is the final name, and **"Function Requirement" is the
  final term** (settled this session, replacing the brief's "Solution Requirement"). Naming
  propagates into table names, API paths and every client-facing document, so it is
  cheapest to settle before the first migration.

### New in this revision (D-7 / D-8 / D-5)

- ⚠ `ASSUMPTION A-26` — **BR → FR is derived, not stored.** The path is
  `BR_SOLUTION → SOLUTION → FUNCTION_REQUIREMENT`, exposed as `v_br_function_requirement`.
  Your original item 4 asked for BFC/BR to link to Function Requirements directly. *If you
  want the stored link back*, it returns as `FR_BR` — but then two paths assert the same
  fact and will disagree (§5.4.3). **Confirm the view is acceptable.** *(2026-09-28: D-28
  makes this sharper. An FR imported with a BR number but no Solution has nowhere to put
  that BR. See A-50.)*
- ⚠ `ASSUMPTION A-27` — **An FR inherits its application through its Solution.** There is no
  `APPLICATION_FUNCTION_REQUIREMENT` table. If one FR within a solution must be built on a
  different application from its siblings, that is currently unrepresentable — and I think
  it should stay a *finding* rather than become a column, because it usually means the
  solution was drawn too broadly. **Flag if you disagree; it is one junction table.**
- ✅ `A-28` — **RESOLVED by D-12.** `org_unit` and `org_role` are in the freeze set; 19
  shadow tables. Finding D4 confirmed the concern mechanically: the RACI shadow tables could
  only carry `org_role_id`, a pointer at a live editable row, so a frozen baseline silently
  rendered today's org chart.
- `ASSUMPTION A-29` — **Solution → BR is many-to-many.** One solution normally answers
  several requirements; one requirement may need an org change *and* a system function.
  This was the open question in the original brief and D-7 settles it as M:N.
- `ASSUMPTION A-30` — **One application catalogue serves as-is and to-be**, distinguished by
  `lifecycle_code`. The alternative is two tables. One table plus a flag makes the gap
  report a self-join rather than a union, which is why it was chosen.
- ✅ `A-31` — **Narrowed by D-25 and D-28 (2026-09-28):** BR and FR upload are in MVP, and
  the BFC is populated by the process-flow JSON import. Solution stays download-only.
  *(Superseded text:)* Bulk upload covers Issue, Data Entity and Data Field only (D-5).
  BFC, BR, Solution and FR are download-only in MVP. Uploading BFC/BR is materially harder:
  the importer must resolve parent hierarchy by `hier_code` and honour the 1:1 L5↔BR rule,
  which is the part that goes wrong. **Likely MVP+1; say if it is needed sooner.**
- ✅ `A-32` — **RESOLVED by Ben, 2026-09-28 (Q14): import rows are purged at 90 days.**
  `purge_import_rows` (§7.12b) deletes `IMPORT_ROW` 90 days after its batch and keeps the
  header. Files are `.xlsx` (and the flow JSON), ≤ 5,000 rows per batch, with caps enforced
  at ingress (R2-S8) and *while streaming*; §7.12 specifies the parser and its hardening,
  and acceptance criterion 75 verifies them. *(Superseded text:)* retained with their staged
  rows for 90 days — a data-protection decision wearing an implementation default.

### New in this revision (control framework, D-13…D-19)

- ✅ `A-37` — **RESOLVED by Ben, 2026-09-24: the database enforces it.** `CR_IMPACT` carries
  seven nullable typed FKs under `CHECK (num_nonnulls(...) = 1)`, each with the composite
  `(id, project_id)` pattern. The soft polymorphic pointer is gone, and §5.6's composite-FK
  discipline now has **no exception anywhere in the model**.
- `ASSUMPTION A-38` — **`effort_days` is a stored derivation, not computed at read.** A
  rate-card renegotiation must not reprice agreed scope. Same reasoning as §5.4.4's label
  copying, and the reason a baseline frozen before D-13 can never be repriced.
- `ASSUMPTION A-39` — **Effort is man-days, and the rate card is by (FR type ×
  complexity) only** — no per-vendor, per-technology or per-phase multiplier in wave 1. Real
  estimates usually need at least a vendor factor; adding one is a column on `EFFORT_RATE`,
  not a model change.
- `ASSUMPTION A-40` — **PARTLY RESOLVED by Ben, 2026-09-28 (Q9): benefits are ranked only
  within one unit.** A benefit's value is **`(target_value − baseline_value) ×
  contribution_pct / 100`** in `measure_unit`, and `value_ranking` returns one ranking per
  unit (R2-D12). **Still open:** no currency conversion, no discounting, no NPV. If the
  business case needs NPV, that is a computed layer over this, and it needs a discount rate
  per project. `contribution_pct` is read as a percentage (0–100).
- ✅ `A-41` — **RESOLVED by Ben, 2026-09-24: yes.** `DECISION` carries the `BEFORE UPDATE OR
  DELETE` reject trigger, is exempt from soft delete, and the application role holds no
  `UPDATE`/`DELETE` grant on it. Corrections are a new row with `supersedes_decision_id`.
- `ASSUMPTION A-42` — **The thresholds in §7.13 are FTC starting points, and every one of
  them is configurable data, not code.** They are mine, drawn from practice, not from your
  method. Three levels of configurability, all live:
  1. **The FTC house default** — `project_id IS NULL`, edited by a platform admin in the
     app. Changes affect future projects only, never an in-flight engagement.
  2. **The project's agreed rule** — copied from the house default at `create_project`, then
     negotiated with the client at mobilisation. Threshold, escalate value, comparison,
     owning role, prescribed action, escalation path and on/off are all editable by the
     project OWNER, with a mandatory rationale and an audit row.
  3. **Which analyses are governed at all** — any of the 17 in `ANALYSIS_REGISTRY` can carry
     a rule; the ten seeded are the ones worth governing on a first engagement.

  **Still worth you setting the house defaults before the first engagement**, because they
  become the starting point on every project after — and a default nobody revisits is the
  number that ends up governing the work.
- `ASSUMPTION A-44` — **A project's thresholds do not vary by phase.** In practice tolerance
  usually tightens as an engagement progresses — 20% scope growth is normal in discovery and
  alarming after design freeze. Supporting it means a nullable `phase_id` in the rule key and
  a phase-aware lookup in `control_panel`: small, but it makes every rule read a two-step
  resolution instead of one. **Not added — say the word if tolerance should tighten at a
  gate, and it is a column plus a lookup.**
- `ASSUMPTION A-43` — **`control_panel` computes live on request.** With 17 analyses over a
  large project this may be slow enough to need caching or a materialised view. Related to
  A-35 — the same "how big is a real project" question, and both wait on your number.

### New in the previous revision (round-1 design review)

- `ASSUMPTION A-33` — **Application timezone is `Asia/Bangkok` (ICT).** Every `date` column
  derives as `(now() AT TIME ZONE 'Asia/Bangkok')::date`, and import templates require ISO
  `YYYY-MM-DD` text with per-column format validation. Finding D10: with the container on
  UTC, an issue resolved at 06:30 ICT recorded the previous day, and a US-locale sheet
  reading `03/04/2027` committed as 3 April where the author meant 4 March. Every wrong
  value looks plausible, so nothing would ever have surfaced it.
- ✅ `A-34` — **Revised 2026-09-28 at build: JWT lifetime follows the FTC scaffold standard** — 1 day, or 30 days with remember-me (§14.5), no refresh token. The earlier 8-hour figure contradicted §14.5. Deactivation still takes effect on the next request, because `current_user` re-reads the user (S4).
- ✅ `A-35` — **RESOLVED by Ben, 2026-09-28: at most 2,000 process nodes per project.**
  `freeze_baseline` stays synchronous; criterion 76 stands with "process nodes" for "L5
  nodes", and with **30** frozen tables for 25 (D-24a, D-27 added four shadow tables; R2-D7 the rate card).
  *(Superseded text follows.)* The freeze is designed for a project of up to 2,000 level-5 nodes
  — hence ~2,000 BRs and roughly 40,000–60,000 rows across the 25 frozen tables. Acceptance
  criterion 76 tests the freeze at that bound inside the request timeout. **This number is
  mine, not yours.** If a real FTC engagement produces a materially larger chart, the freeze
  must become a job-and-poll (`202 Accepted` + a status endpoint) rather than a synchronous
  request, and that is a build-shape decision, not a tuning exercise — **tell me the real
  number and I will either confirm the bound or change the shape.** Related: A-43, whether
  `control_panel` needs caching at the same scale.
- `ASSUMPTION A-36` — **A `baseline` header cannot be soft-deleted.** A wrongly-frozen
  version stays visible in the lineage with its note; the repair is to freeze the next one.
  Finding P6: the header carried `is_active` while its 19 children were hard-immutable, so a
  "retracted" baseline still appeared in any diff query that forgot the filter.

### New in this revision (Ben's v8 review, D-23…D-31)

- ⚠ `ASSUMPTION A-47` — **A process node may sit at level 3, 4 or 5**, not at L1 or L2. An
  L2 "process" would put a whole business area in one box and one requirement. **If FTC
  ever models a branch that stops at L2, this is one CHECK.**
- ⚠ `ASSUMPTION A-48` — **Splitting a process is refused until the consultant has retired
  its BR and every other step-level fact** (D-23, R2-P5, Q4). Demotion returns 409 naming
  each blocker, and **VB never retires anything on the consultant's behalf**. The
  alternatives were to move the BR to one of the new children automatically, which guesses
  which child the requirement meant, or to retire it in a cascade, which records a scope
  removal nobody decided. The consultant chooses; VB refuses until they have.
- `ASSUMPTION A-49` — **The process-flow JSON carries one parent node's flow per file**,
  ≤ 500 steps. A whole-chart import would be a BFC import, which D-25 did not ask for.
- ✅ `A-50` — **RESOLVED by D-34 (2026-09-28): "import unlinked + suggest".** An FR row that
  names a BR but no Solution is imported with `solution_id NULL` (warning, D-28), and the BR
  is stored on the FR as `suggested_br_id`. The suggestion clears only when a `BR_SOLUTION`
  path from that BR to the FR's solution exists. **No placeholder solution is ever created.**
  *(Superseded text:)* the BR number kept in the staged row only, or a placeholder
  TECHNOLOGY Solution per BR.
- `ASSUMPTION A-51` — **The AI conversion runs outside VB**, and since D-36 **only in Claude
  or Microsoft Copilot under FTC's own accounts, with personal data removed first**. VB
  publishes the schema and prompt pack and accepts the file. An in-app "convert this
  PowerPoint" button would send client content to an AI service from VB itself and bring in
  the playbook's AI-layer rules (§12.2). Deliberately not in MVP.
- `ASSUMPTION A-52` — **Layout is last-write-wins per object, and not versioned.** A baseline
  re-opened later renders with today's positions, or auto-layout for objects no longer
  there. A diagram frozen with the scope is a PNG export attached to the sign-off, not a
  stored state.
- `ASSUMPTION A-53` — **ERD cardinality is derived, never typed.** A consultant who wants a
  different crow's foot changes the key or the mandatory flag that produces it. A typed
  cardinality would be a second assertion of the same fact.
- `ASSUMPTION A-54` — **An L5 node is always a process** (`CHECK (level_no < 5 OR
  is_process)`). An L5 node can have no children, so it can only be the lowest node of its
  branch. Together with the parent guard, this also enforces the old "no level 6" rule.
- `ASSUMPTION A-55` — **An interface FR's detail row requires both applications.**
  `FR_INTERFACE.source_application_id` and `target_application_id` are `NOT NULL`. An
  interface known only by pattern is recorded as an FR with no `FR_INTERFACE` row and is
  listed as incomplete on the interface list (§4.4).

### New in this revision (design review round 2, D-32…D-36)

- `ASSUMPTION A-56` — **Baselines stay per project, even inside a program.** There is no
  program freeze. A program's "agreed scope" is the set of each project's latest baseline,
  shown side by side. A single program-wide freeze would be one transaction across several
  projects' 30 tables, and would bring back the cross-project write path D-32 exists to
  avoid.
- `ASSUMPTION A-57` — **A program holds about ten projects at most.** Roll-ups make one
  per-project call per project per report, so a dashboard is about 50 report calls. That is
  acceptable at ten projects; at fifty the dashboard needs caching (the same question as
  A-43), not cross-project SQL.
- ⚠ `ASSUMPTION A-58` — **A suggested BR link cannot be dismissed.** It clears only when the
  `BR_SOLUTION` path exists, the FR is retired, or the suggested BR is retired (D-34, as ruled; §7.12). If consultants need to
  reject a wrong suggestion, that is one PATCH field plus an audit event. **Say if it is
  needed.**
- ⚠ `ASSUMPTION A-59` — **"Baselines recoverable for 5 years" (Q12) is met in two layers.**
  In the live database, baselines are never deleted (A-7, A-36). For loss of the database
  itself, long-term backup retention covers 5 years, because point-in-time restore covers
  only days (35 at most on Flexible Server). The mechanism, cost and restore drill are §15's.
  **A client contract that requires deletion at engagement end overrides the 5 years (Q15):
  the project is purged and its archive key destroyed (§15.3).**
- `ASSUMPTION A-60` — **Each project has exactly one RACI code per load-bearing behaviour**:
  one RESPONSIBLE and one ACCOUNTABLE. The lane and the single-Accountable rules resolve "the"
  code by behaviour. A RAPID mapping that sends two codes to RESPONSIBLE is refused when the
  code is saved (→ `code_master` rules, §8).
- `ASSUMPTION A-61` — **WBS parentage comes from outline level and row order** in the MS
  Project export, not from the WBS code, which is a display string some schedules customise.
  An export sorted by anything other than ID breaks parentage. The template says so, and
  validation rejects an outline level that jumps by more than one.

*Raised by `apple` in the round-2 model (proposed there as A-56…A-59; renumbered because
those numbers were taken above):*

- `ASSUMPTION A-65` — **`PROGRAM` has no status, dates or manager.** D-32 describes none. The
  program dashboard shows its projects' statuses. Add them if Ben describes a program
  lifecycle.
- `ASSUMPTION A-66` — **WBS dates are `date`, not `timestamptz`.** MS Project's time of day is
  a working-calendar artefact at dashboard grain.
- `ASSUMPTION A-67` — **A platform admin holds no grant.** If one does, the grant is inert
  while the flag is on, and it becomes the fallback when the flag is removed.
- `ASSUMPTION A-68` — **A returning MS Project Unique ID restores the retired `WBS_ITEM` row,
  links intact.** A new MS Project file that restarts Unique IDs would wrongly restore
  unrelated lines, so the preview warns when a restored line's name differs.

### Raised by `apple` during modelling — not previously on the list

- ⚠ `ASSUMPTION A-16` — **`code_master` is two-tier**: a nullable `project_id`, where `NULL`
  is the FTC-wide default library and non-null is a per-project override. This is the
  flexible choice and it carries a resolution rule (override shadows global on
  `category + code`) that must be implemented identically in every dropdown. If clients
  never configure these, drop the column; if they always do, drop the global tier. **The
  hybrid is the most expensive of the three and was chosen on the strength of one word in
  my brief to her — confirm it earns its cost.**
- ✅ `A-17` — **RESOLVED by D-2.** A BR belongs to exactly one process node, and a process
  node has exactly one BR. A process node is the lowest node of its branch, at L3–L5 (D-23).
  The fan-out lives on Solutions and FRs instead (D-7).
- ✅ `A-18` — **RESOLVED by D-4**, as `apple`'s option (b). `STAKEHOLDER` is a project-scoped
  person (name, title, org unit, `is_bpo`) with no login. `ISSUE.raised_by_stakeholder_id`
  is who raised it; `ISSUE.recorded_by_user_id` is the consultant who typed it. The
  `raised_by_name` text hedge is gone.
- ✅ `A-19` — **RESOLVED by D-10.** `hier_code` may change on reorder; codes quoted in older
  client documents may go stale. The uncosted half — that a presentational reorder reported
  48 process steps as CHANGED and buried the one real change (finding P4) — is fixed by
  excluding `hier_code` and `seq_no` from `content_hash` and reporting position changes as
  **MOVED**.
- `ASSUMPTION A-20` — **Baselines are read-and-diff only; there is no restore.** Restore
  would require the shadow tables to be complete and reversible for *every* scoped entity
  including junctions, plus a strategy for un-resolving the denormalized labels. Read-only
  is much cheaper.
- ✅ `A-21` — **SUPERSEDED by D-32 (2026-09-28).** A user holds **one active grant in
  total**, naming one project or one program, with one role (Q10). Two roles on one project
  cannot arise, so no precedence rule is owed. *(Superseded text:)* One project role per
  user per project (composite PK `(app_user_id, project_id)`).
- `ASSUMPTION A-22` — **`ORG_UNIT` stops at three levels** (`CHECK level_no BETWEEN 1 AND 3`)
  per Department / Division / Section. Large clients run Group → Company → Department → …
  If the depth is uncertain, drop the `CHECK` and keep the self-reference open; the only
  loss is the level-label guarantee.
- `ASSUMPTION A-23` — **No attachments.** Nothing in your list mentions files, but issues
  and BRs attract screenshots, extracts and signed-off documents on every real engagement.
  Per-parent attachment tables (not a polymorphic one) are the likely MVP+1.
- ✅ `A-24` — **RESOLVED by D-6.** `row_version integer` on every editable business table;
  every `UPDATE` carries `WHERE row_version = :v` and increments it; mismatch returns 409
  with a `detail` string. Acceptance criterion 17b covers it.
- `ASSUMPTION A-25` — **`updated_by` and `deleted_by` are added** to the audit column set.
  The playbook names only `created_by`; with soft delete and freezes you will want to know
  who last touched a live row before it was baselined. Added on `apple`'s recommendation.

---

## 12. Delivery sequence and out of scope

### 12.1 Waves — everything here is mandatory, only the order is a decision

D-13…D-19 are **requirements, not a roadmap** (Ben, 2026-09-18). Nothing below is dropped;
the waves exist because the model must be built in dependency order, and because two of the
seven cannot be retrofitted.

| Wave | Contents | Why here |
|---|---|---|
| **1** | Scope Management & Control (§4.1–§4.7) · **D-23…D-31** (process nodes, step I/O, external entities, flow JSON import, logical fields, FR types and interface list, unlinked FRs, ERD, stored layout, DFD) · **D-13 size & effort** · **D-19 control rules** · the seven analyses in §7.9 | **D-13 cannot be retrofitted** — a baseline frozen without `effort_days` is unpriced forever, so every wave-1 baseline would be worthless for change control. D-19 is the smallest of the seven and makes everything already built actionable. The seven analyses need no new entities |
| **2** | **D-14 benefit** · **D-16 change request** | The pair that makes "trade, don't add" executable: you cannot displace scope without a value ranking, and you cannot price a change without D-13. Needed before the first baseline is challenged |
| **3** | **D-15 risk** · **D-17 decisions** · **D-18 phasing & dependency** | Real from mobilisation, but each stands alone and none blocks the others. Phasing in particular wants a real engagement to tell it what a wave looks like |

**D-23 and D-27 are first-migration items**, for the same reason as `row_version`: `is_process`
replaces the `level_no = 5` pin on seven tables plus `bfc_node` itself (§5.4.7), and
`FR_TYPE` behaviour is read by the FR form, the interface list and the rate card. Retrofitting either touches every path that reads them.
The canvas (§7.14) is built once, for the process flow, and reused for the DFD and the ERD.

**Round 2 (D-32…D-36).** **The one-grant access model (D-32) is a first-migration item**,
for the same reason as `row_version`: every guard reads it, and moving from many grants to one
later means a data clean-up on live grants. The guard registry (R2-S1), `escape_mermaid`,
the ingress limits and the refuse-with-dependents soft delete also land in wave 1, before
the first protected route, the first export and the first delete. **Program roll-ups** go in
wave 1 after the per-project reports they are made of. **D-34** ships with the FR import in
wave 1. **D-33 WBS** lands in **wave 3**, beside phasing (D-18), whose `PHASE` it links to.
It is optional per project, so nothing earlier waits for it. **D-35** (the Azure deployment,
§15) and **D-36** (the prompt pack) come before first client use.

**The wave line is Ben's to move.** If the first engagement needs risk and phasing from day
one, they move to wave 1 — nothing in the model prevents it, and the only hard ordering
constraint is that D-13 precedes D-16, and that both precede any baseline anyone intends to
argue about.

### 12.2 Out of scope

Explicit, so this spec is not read as a promise. **Per D-1 these are later increments of the
same platform, not rejected ideas** — §5 is modelled so they attach to this spine.

- **Task-level schedule *authoring*** — activities, dependencies, critical path, Gantt
  editing. **Narrowed by D-33:** a WBS can now be *imported* from MS Project, read-only
  apart from its phase and solution links, to feed plan-vs-actual (§4.15). Building or
  editing the schedule stays in MS Project.
- **Resource and capacity management** — named people, allocation, utilisation. `EFFORT_RATE`
  gives the demand side (D-13); the supply side is not modelled.
- **Cost beyond effort** — licences, hardware, run cost, currency, NPV. D-13 gives man-days;
  converting those to money needs a rate-to-currency layer and A-40's discounting question
  answered.
- **Benefit *realisation* tracking after go-live** — D-14 models the commitment and the
  target; measuring actuals against it over time is a post-implementation capability.
- **Vendor and procurement management** — contracts, SOWs, invoices, vendor performance.

### 12.3 Designed separately, before the area is built

Not defects and not deferred features — areas this spec deliberately does not cover, each
needing its own short design pass at the point it is built. Named here so none is discovered
missing later.

| Area | When it must be designed | Why it is not here |
|---|---|---|
| **Frontend design** — page shells, the tree component, the read-only baseline mode, how untrusted free text is rendered, the program dashboard and the import previews | **Now written: §14** | `fortience-app-scaffold` supplies the patterns; §14 holds the screen inventory. **One thing this spec still asserts on its own: read-only baseline mode is enforced server-side, never only as UI state** |
| **Deployment and secret handling** — Azure (D-35): App Service or Container Apps, PostgreSQL Flexible Server on private networking, Key Vault via managed identity, the two DB roles (§6.6), ingress body limits (R2-S8), the daily purge job (Q14), and the Entra ID SSO decision (R2-S11) | **Now written: §15** | Infrastructure, not application design |
| **Backup and restore** — point-in-time restore, 5-year recoverability of baselines (Q12, A-59), and the restore drill before first client use | **Now written: §15.3** | **This is the only real reversal mechanism for a wrongly-frozen baseline** (§4.6 offers no reopen, A-20 no restore), which makes it a control, not an ops detail |

The uploaded-file lifecycle and the `.xlsx` parser configuration were on this list in an
earlier draft; both are now specified in §7.11 and §7.12.
- ~~**Solution layer**~~ — **now in scope (D-7).** BR → Solution → Function Requirement,
  with solutions categorized Organization & Rules / People / Process / Data / Technology.
- **BPMN / formal notation** — the flow model is deliberately lighter than BPMN: no event
  sub-types, no pools beyond org lanes, no compensation or transaction semantics. It is a
  consulting process flow, not an executable model. Export is Mermaid text and
  `vb-process-flow/1.0` JSON, not BPMN XML. **A BPMN diagram can still be imported, by
  converting it to the JSON (D-25)**; VB does not read BPMN XML directly.
- **BFC chart visualization** — the tree is a tree view, not a rendered org-chart graphic.
- **Import/export beyond Issue, DE, Data Field, BR, FR, WBS and the process-flow JSON.**
  Solution is download-only; no vendor hand-off package. See A-31.
- **Client-user login** — client reviewers do not log in during MVP; consultants do.
  Depends on A-11.
- **Baseline approval workflow** — approval is a recorded field, not a routed process.
- **Notifications** — no email, no in-app alerts.
- **In-app AI agent** — none, including for the process-flow conversion (A-51). The
  conversion happens outside VB, in Claude or Microsoft Copilot under FTC's own accounts
  only (D-36). If an in-app agent is added later, the playbook AI-layer rules apply.
- **Cross-project reference library** — shared issue taxonomies live in `code_master`;
  a reusable reference BFC template library is deferred.
- **Baseline branching / merge.**
- **Field-level audit history** on live rows — baselines are the history mechanism.

---

## 13. Build checklist

- Spec approved in Plan Mode **before** `fortience-app-scaffold` runs. The scaffold is an
  afternoon; the model is the product.
- Migrations linear and reversible, **one per commit**. Destructive migrations pause for
  approval.
- Audit columns `created_at` / `updated_at` / `created_by` and `is_active` / `deleted_at`
  on every business table from day one — never retrofitted.
- `fn_set_updated_at()` DB trigger is authoritative. **Never `onupdate=` in SQLAlchemy.**
- `code_master` seeds via `backend/seeds/` CLI — never in Alembic.
- `BRAND` constant at the top of `App.jsx`; components read via `useTheme`. No hard-coded
  hex. Status colors in a separate semantic map; `warning` amber reserved for regret-able
  actions.
- Filter sections and detail headers share the same wrapper `Box` recipe. Every list page
  gets a bold `h5` title with `mb={3}`.
- Fortience Consulting Inc. footer on every screen.
- Error shape: 422 / 404 / 409 / 401 / 500, backend returns `detail`, frontend reads
  `err.response?.data?.detail`. No `.catch(() => {})`.
- Three-layer rule holds: Router → Service → Model. `access.py`, `numbering.py` and
  `baseline.py` are each a single source of truth.
- Tests at the service layer first — numbering concurrency, the freeze transaction, the
  diff, and the visibility guard are the four that matter.
- Reject trigger on every `baseline_*` table (`BEFORE UPDATE OR DELETE`) — immutability
  enforced by the database, not by convention.
- CI column-parity test: each `baseline_*` column set == its live table, minus audit
  columns, plus snapshot columns. This is what makes shadow tables safe (§5.4.4).
- Never write a hard-delete endpoint. One `DELETE` cascade destroys the commercial value of
  every baseline referencing the row. Make it a code-review rule.
- The bare word `role` is banned in code, tables and routes — `org_role` vs `app_role`,
  `OrgRole` vs `AppRole`. It is a PostgreSQL reserved word, so the rule enforces itself the
  first time someone forgets.
- `renumber_subtree` gets the most tests in the codebase. It is the one function that can
  corrupt the chart. `bulk.commit` is second — it is the only path that writes many business
  rows from an untrusted file.
- Generate the **30** shadow models from the live models; do not hand-write them (§6.1).
- Optimistic concurrency (`row_version`) goes in with the first migration, not later —
  retrofitting it means touching every update path in the app (D-6).
- Bulk import writes nothing at validate time, and mints no numbers until commit (§7.11).
- **`FUNCTION_REQUIREMENT.complexity_code` and `effort_days` ship in wave 1 (D-13).** A
  baseline frozen without them is unpriced forever and cannot be repriced — this is the one
  item in the whole spec with no recovery path.
- Every analysis in `ANALYSIS_REGISTRY` returns a `headline_value`. A test iterates the
  registry and fails on any that does not — that contract is what `control_panel` stands on.
- `decide_cr` **refuses** a net-positive approval with no displacement named. It is a 422,
  not a warning; a control that can be clicked past is not a control.
- `effort_days`, `exposure_score` and `cr.effort_delta_days` are **derived at save and never
  accepted from the request body** — same rule as `created_by` (§9.2).
- **Round-1 review fixes that cannot be retrofitted**, so they go in with the first
  migration: `row_version` (D-6), `project_id` on `data_field` (D9), the `PROJECT_ROLE`
  model (D-9), `baseline.major_no`/`minor_no`/`hash_spec_version` (P9, D5), and the two
  database grants in §6.6 (S11).
- **Acceptance criterion 49 is not optional** — the route-coverage test is the stated price
  of deferring row-level security (§6.4). Build it with the first protected route, not last.
- `escape_cell()` is used by **every** sheet-writing path, with no exceptions (S5).
- `consistency_check` runs as a precondition of freeze, not on a schedule (D11).
- Map unique-constraint violations to 409 with a `detail` string in the shared error
  handler, and disable submit controls while a create is in flight (P10).
- **The literal `level_no = 5` must not appear anywhere in the code** after D-23. Process-ness
  is `is_process`. A grep for `level_no = 5` / `level_no == 5` is part of the pre-merge check.
- The FR form, the interface list and `interface_load` switch on the FR type's **behaviour**,
  never on its code (D-27). A grep for `== 'INTERFACE'` against `fr_type_code` is a finding.
- The process-flow JSON import is the **same** staging, lock and commit as `bulk.py` —
  one pipeline, a sixth column map. A second importer is a code-review rejection.
- One canvas component for process flow, DFD and ERD (§7.14). Positions go through
  `diagram_layout.save`; nothing else writes `DIAGRAM_LAYOUT`.
- **Routes register only through `route(..., guard=…)`** (R2-S1). A route with no guard
  fails at import; criterion 49 re-proves it over the running app. Build it with the first
  route.
- **The one-grant index and `program_id` on the grant go in the first migration** (D-32).
  `visible_project_ids` / `require_project` / `require_program` in `access.py` are the only
  readers of grants.
- **`services/program.py` contains no SQL over business tables** (R2-S2). A roll-up is a loop
  over per-project reports. A `project_id IN (...)` anywhere in it is a code-review rejection.
- **`escape_mermaid()` is used by every Mermaid-writing path** (R2-S7), the same rule as
  `escape_cell()`. The renderer refuses to emit `click`, `%%{init}`, `style`, `classDef`.
- **`BodySizeLimitMiddleware` is the outermost middleware** and the ingress cap is set in
  §15 (R2-S8). The multipart spool threshold is at least the route cap.
- **`DEPENDENTS` / `PARENTS` are derived from the model's FKs**, never hand-kept (R2-D2).
  Nothing cascades; every DELETE route goes through `lifecycle.soft_delete`.
- **`RESTORABLE` is the allow-list**, and each entry registers its own restore route
  (R2-S5).
- **`bfc.ensure_step_io` is the only writer of step I/O** (R2-D13). `normalise_name` is the
  only name comparison (Q1).
- **`freeze` opens its connection at REPEATABLE READ before its first statement** and runs
  `consistency_check` on that connection (R2-P6).
- **`effort_days` is never read from a file**, and FR type and complexity from a file go
  through the rating services (R2-D6).
- `docs/PLAYBOOK_DEVIATIONS.md` records six deviations: **A-7** (immutable snapshots, no
  soft delete), **CRUD as a `CHECK` rather than `code_master`** (§8; `diagram_type` and
  `behaviour_code` are the same kind of `CHECK`), **`baseline` exempt from soft delete** (§6.2,
  finding P6), **`diagram_layout` hard-deleted, with no `row_version`** (D-30, A-52), and
  **`import_row` hard-deleted at 90 days** (Q14, §7.12b), and **`wbs_item.row_version`
  guards only the two VB-owned links** (D-33, §5.3 WBS_ITEM). Staged client content is
  purged, not retired, because retiring it would keep exactly what the retention rule exists
  to remove. *(The third original deviation — `APP_ROLE` as a table — is withdrawn; D-9 removed
  the table.)*

---

## 14. Frontend design

Bound by `fortience-app-scaffold` (auth shell, page shell, wrapper `Box`, error handling,
footer) and playbook §6. This section states only what VB adds or decides on top.

### 14.1 Stack and structure

| Concern | Choice | Why |
|---|---|---|
| Framework | React 18 + Vite + MUI (current major) | FTC standard |
| Server state | TanStack Query | Caching per project, and one place where `row_version` and 409 handling live |
| Routing | React Router; every project URL is `/p/:projectId/...`, program URLs `/g/:programId/...` | A link names its scope, so the backend guard (§9 registry) always receives it |
| Lists | MUI DataGrid (MIT edition) | FTC standard list pattern |
| Tree | MUI X `RichTreeView` (MIT), lazy-loaded one level at a time | 2,000 process nodes per project (A-35) |
| Diagrams | `@xyflow/react` 12 + `elkjs` 0.12 in a web worker | Proven by the canvas spike, 2026-09-28 (§14.6) |

```
frontend/src/
  app/          shell, routes, auth, error boundary
  api/          one axios client + one module per resource
  theme/        BRAND, STATUS_COLOR_MAP, light and dark tokens
  components/   wrapper Box, page shell, ImportWizard, ConflictDialog, …
  canvas/       ModelCanvas (ERD / process flow / DFD), elk.worker.ts
  features/<area>/  one folder per §4 scope area
```

### 14.2 Theme

- **`BRAND` = the Fortience deck palette**, not the scaffold's neutral slate default:
  indigo `#2B245C` (header, footer, page titles), cyan `#04AED6` (accent rule, focus
  highlights), violet `#7848DC` (avatar, selection accents). Primary actions stay navy
  (`#1F3A5F` light / `#4A73A8` dark) for contrast on white. Data entities keep the teal family.
- **Light is the default, dark the alternate**, both from one MUI `colorSchemes` theme, so
  every screen gets both at no extra cost. The v9 canvas boards are the reference for both sets.
- `STATUS_COLOR_MAP` (green / amber / red) is separate from `BRAND`, per playbook §6. Amber
  stays reserved for regret-able actions.
- **The wrapper `Box` reads its fill and border from theme tokens**, where the scaffold
  snippet has hard-coded `#fafafa` / `#e0e0e0`, so it works in dark mode. The recipe itself
  is unchanged.
- Type: IBM Plex Sans and Mono, with Noto Sans JP for Japanese client content.
- **Recorded in `docs/PLAYBOOK_DEVIATIONS.md`**: dark theme, IBM Plex fonts, React Flow +
  elkjs, and the token-based wrapper `Box` (open item 3 of the 2026-09-25 handoff).

### 14.3 Shell, navigation and scope

- Top bar as on the v9 boards: **Dashboard · Processes · DFD · Requirements · BR–FR map ·
  Interfaces · Data**, plus Settings. The FTC footer is on every screen.
- **Scope selector** in the header. It lists only what `visible_project_ids(user)` returns.
  A program grant (D-32) shows the program first, then its projects. A single-project user
  never sees a selector with one item — it shows the project name, not a menu.
- Program context shows only the roll-up views (D-32). Any drill-down opens the per-project
  screen under `/p/:projectId`, so project-level screens never mix projects.
- Screens with no canvas board (login, users, access, project and program admin, baselines
  list and diff, control panel, issues, solutions, applications, stakeholders, rate card,
  control rules, WBS) use the scaffold's standard list and detail shells. No further
  mockups are needed for them.

### 14.4 Read-only baseline mode

- A baseline opens under `/p/:projectId/baselines/:baselineId/...` and reads **only**
  snapshot endpoints. **Those endpoints have no write routes**, and the snapshot tables
  reject UPDATE and DELETE by trigger. The UI mode is a convenience; it is not the control.
- A full-width banner states "Viewing v1.2 · frozen 14 Nov · read only", with a "Back to
  working set" action. Edit controls are **absent, not disabled**, so nobody hunts for why a
  button does nothing.
- Diagrams in baseline mode render with today's saved positions or auto-layout (A-52).

### 14.5 Untrusted text, the token and the browser

Everything a client, a spreadsheet or an AI-converted file wrote is untrusted: BR text,
issue text, names, condition labels, `source_ref`, code labels, file names.

- **Rendering is React's default text escaping, and nothing else.** `dangerouslySetInnerHTML`,
  `innerHTML` and Markdown rendering are banned in MVP by ESLint rule. URLs in text are not
  auto-linked. Long text renders with `white-space: pre-wrap`.
- **Token: the FTC scaffold standard** — a Bearer JWT in `localStorage`, attached by one
  axios interceptor; a 401 clears it and returns to login; remember-me 30 days, 1 day
  otherwise. It carries only `sub` and `exp` (S4). An httpOnly cookie was considered and not
  taken: it would be a playbook deviation and bring CSRF handling with it. **The compensating
  controls are the rendering rule above plus a strict Content-Security-Policy**:
  `default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none';
  base-uri 'none'`, with no inline script and no `eval`. The CSP is set by the hosting
  config (§15.2) and tested by a criterion. **Revisit if Entra SSO is adopted** (§15.4).
- **Canvas exports** (PNG, SVG) serialise text nodes only. No `foreignObject` and no HTML
  from user content in an exported SVG. Mermaid export goes through `escape_mermaid()`
  (R2-S7).
- File downloads get server-generated names. Uploaded file names are shown as text only.

### 14.6 The diagram canvas — build rules from the spike

One component, `<ModelCanvas kind="erd" | "flow" | "dfd">`, in `frontend/src/canvas/`. The
canvas spike of 2026-09-28 returned **GO**, with these rules:

- `onlyRenderVisibleElements` **always on**. React Flow does not virtualise by default,
  despite what §7.14 says, and the 200-entity case needs it.
- A **simplified low-zoom view** below zoom 0.45: row text and dashes hidden with
  `visibility`, never `display: none`, so handle positions stay valid.
- ELK runs in a **web worker**. Settings: `layered`, `ORTHOGONAL` routing, `BRANDES_KOEPF`
  node placement (never `NETWORK_SIMPLEX`: 35 s at 200 entities), and `FIXED_POS` ports at
  each key-field row.
- **Handle ids never change**: `{s|t}-{L|R}-{fieldId}`. A collapsed card stacks every
  key-field handle on its summary row instead of switching ids — the spike's collapse race.
- Composite FKs group on `(ref_data_entity_id, fk_group_no)`. `fk_group_no` is the new
  `DATA_FIELD` column the spike showed is needed (§5.3 DATA_FIELD).
- **Pinned cards on auto-arrange**: ELK lays out everything, pinned cards return to their
  saved positions, and overlapping unpinned cards are pushed clear. Lines touching a moved
  card fall back to smoothstep until the next arrange.
- Edges are rebuilt on layout, drag end, collapse and selection — never on every drag frame.
- Positions save on **drag end**, debounced, through `PUT /diagram-layouts/...` (D-30).
- The React Flow attribution stays visible; the MIT edition is used, not Pro.
- **Every diagram has a table view** of the same data (the tables already exist), which is
  the keyboard and screen-reader path.

### 14.7 Forms, conflicts and imports

- Every edit form sends `row_version`. **A 409 opens one `ConflictDialog`**: "Updated by
  another user", the current values beside the user's unsaved ones, and a "Reload and
  reapply" action that keeps what they typed. Submit is disabled while a request is in
  flight (P10).
- **One `ImportWizard` for all seven imports** (five `.xlsx` entities, WBS, flow JSON):
  Upload → Validate → Preview → Commit. Errors and warnings show the sheet row or the
  `source_ref`. Any batch that inserts requires typing the insert count (R2-P2). For a flow,
  the anchor and mode are chosen in the wizard, never taken from the file (R2-P3). Replace
  mode lists every RETIRE row.

### 14.8 Language

The UI is in English for MVP. Every string lives in one `en.json`, so a Japanese UI is a
translation, not a refactor. Client content is often Japanese, hence Noto Sans JP.

---

## 15. Deployment on Azure (D-35)

### 15.1 Environments

| Environment | Where | Data |
|---|---|---|
| Local | Build machine, PostgreSQL in Docker | Seeded fake data only |
| Dev | Azure, own resource group, disposable | Seeded fake data only. **Never client data** |
| Prod | Azure, FTC tenant | Real engagements from 2027 |

This is the environment switch `env-switch` reports on. A write is never made before the
target is confirmed.

### 15.2 Production topology

- **Frontend**: Azure Static Web Apps (Standard), custom domain, TLS. The CSP and security
  headers of §14.5 are set in `staticwebapp.config.json`.
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
  on `diagram_layout` and the import-staging purge. `vb_owner` owns the schema.
- **Upload limits at ingress** (R2-S8): ASGI middleware rejects a request whose
  `Content-Length` exceeds the route's cap, and counts streamed bytes for chunked bodies,
  **before the handler runs**. Any spool goes to the container's ephemeral `/tmp` and is
  deleted when `validate` returns. Nothing uploaded is ever written to persistent storage.
- **Logging**: Application Insights / Log Analytics capture request method, route, status,
  duration and user id. **Never** request bodies, query parameters carrying content, SQL
  parameters, JWTs or file contents. Retention 90 days.
- **CI/CD**: GitHub Actions with an OIDC federated credential (no stored cloud secret):
  test → build → migration job → new revision. A destructive migration needs a manual
  approval on the production environment (§13).

### 15.3 Backup, restore and evidence retention (R2-S10, Ben Q12)

Point-in-time restore is disaster recovery. It restores the **whole server**, reverting
every other client's work too, and keeps at most 35 days. It is therefore **not** the way
back from one wrong freeze, and not five-year evidence.

| Layer | What | Kept |
|---|---|---|
| Disaster recovery | Flexible Server point-in-time restore, geo-redundant backup | 35 days |
| **Baseline evidence archive** | At every freeze, that baseline's snapshot rows and content hashes are written as one JSON file to Blob Storage under a **locked immutability policy**, **encrypted with that project's own key in Key Vault** | **5 years (Ben, 2026-09-28)**, unless the client contract requires deletion (Q15) |
| Logical dump | Monthly `pg_dump` to immutable Blob Storage | 13 months |

- **Reversing one project** means restoring that project's baseline archive into a side
  database, verifying hashes, and reading or re-importing from there. No other project is
  touched.
- **Contract-required deletion (Ben, Q15)** — the contract wins over the 5-year default.
  Write-once storage cannot be deleted early, which is what makes it evidence, so each
  project's archive is encrypted with its **own key**. `purge_project`, platform-admin only
  and with a recorded reason, deletes the project's live and snapshot rows (run as
  `vb_owner`, the one hard-delete path in VB) and **destroys that project's key**. The archive
  files remain but can never be read again. The monthly logical dump ages out within 13
  months; the purge record states that date. An `AUDIT_EVENT('PROJECT_PURGED')` keeps the
  project code, client, date, actor and reason — no content.
- **Restore drill before first client use** (§12.3): (a) point-in-time restore to a new
  server; (b) recover one project's baseline from the archive into a side database, with
  hashes verified. The result is recorded in the session handoff.

### 15.4 Authentication

JWT (FTC scaffold standard) for MVP. **Entra ID single sign-on is optional**, to be decided
before the first client engagement. If it is adopted: reject `userType = Guest` (client staff
invited to Teams would otherwise pass sign-in and break D-11), keep `create_user` as the only
way an account is made, with no just-in-time creation, and revisit the token storage of
§14.5. *(Tracked: R2-S11.)*

### 15.5 Operations

Alerts to Ben on: API 5xx rate, repeated login failures for one account, database CPU and
storage, backup failure, and a Key Vault access denial.

### 15.6 Assumptions

- ✅ `A-62` — **RESOLVED by Ben, 2026-09-28: production runs in Azure Japan East.** Dev uses
  the same region, so a restore drill never moves data across regions.
- `ASSUMPTION A-63` — **The repository is hosted on GitHub**, so GitHub Actions and OIDC
  apply. There is no remote yet.
- `ASSUMPTION A-64` — **One production instance serves all FTC engagements** (A-13 single
  tenant). A client demanding its own instance is a separate deployment of the same build.
