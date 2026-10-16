# Value Bridge — Design History

**Companion to** [`VB_design.md`](VB_design.md), **which is the clean, current spec.** This file keeps everything
the spec no longer carries: every decision as it was made (who, when, why, what it overrode), the review rounds,
the slice rulings, the spec's revision history, and the items Ben has raised that are not yet decided.

**How the two files work together**
- A new piece of feedback is **recorded here first**, under §1 *Open*, with the date and Ben's words. The spec is not touched.
- When Ben decides it, the entry moves to §3 with its id (D-n, S-n) and status, and **in the same commit** the spec is
  rewritten to the new current state, citing the id. The spec never says "revised", "was", or "supersedes"; that lives here.
- Slice specs and schemas (`docs/slice*.md`) are the detailed record of each enhancement; §4 indexes them.

---

## 1. Open — recorded, not decided

Nothing here is in the spec yet.

- **[Q-32] Who maintains a project's code lists — EDIT (as signed off) or ADMIN?** (raised 2026-10-16, wave 1g spec,
  `design-auditor` round 1.) §7.12 and the API table give `maintain_fr_types` / `PUT …/code-master/FR_TYPE` the EDIT
  guard. Ren's working assumption for 1g is "the project's admin role" — in VB only platform admins reach ADMIN (D-40),
  so that would mean FTC admins only. `docs/slice1g_spec.md` §14 R2.
- **[Q-33] When a project relabels a company code, do its existing rows follow?** (raised 2026-10-16, wave 1g,
  `design-auditor` HIGH.) Today the FR-type override re-points the project's rows (§7.12); for every other category a
  relabel would leave old rows on the company label and new rows on the project label, so exports and baselines show two
  names for one value. Proposed: extend the re-point to every category (spec §14 R1). Round 2 calls this a new design;
  its costs: every write at EDIT or above takes a shared lock on the project row (a re-point briefly holds writes in that
  project), the re-point updates every row of that category in the project in one transaction (not bumping row_version),
  and a short exclusion list is kept by hand with a test (spec §15). The alternative — every backend read labels by
  (project, category, code) — touches every exporter and the freeze and is not recommended.
- **[Q-35] Rate cells for a new FR type or complexity** (raised 2026-10-16, wave 1g round 2). Adding a company FR type
  or complexity seeds unconfirmed cells in every live project (spec R6), so the picker never offers a type that cannot
  be rated. Which numbers? Proposal: copy each project's own cell of the existing type with the same behaviour; behaviour
  OTHER and a new complexity have no source — FTC to give a default, or leave those cells blank (rating returns 422
  until filled). It also shows as added rate rows in each project's next baseline comparison.
- **[Q-36] May PROJECT_STATUS be overridden per project?** (raised 2026-10-16, wave 1g round 2.) It is a plain code
  column on `project`; if yes it joins the re-point, if no it is company-only like PROJECT_TEMPLATE.
- **[Q-34] A project may hide a company code, and Japanese / Thai labels wait for wave 4** (Ren's working assumptions
  A2, A3 for 1g) — Ben to confirm.

---

## 2. Revision history of the spec

**Status:** **SIGNED OFF by Ben, 2026-09-28, in Plan Mode.** Changes from here are proposed with evidence and approved before they land.
**Date:** 2026-09-17 · **Revised:** 2026-09-28 (D-23…D-31, Ben's v8 review) · 2026-09-28 (round-2 review, D-32…D-36) · 2026-09-29 (Slice 1 schema review, S1-1…S1-7) · slice rulings S2…S6c (§1a) · **2026-10-11 (one platform, many kinds of project, D-37…D-50 — signed off by Ben; D-47/D-49 modelling to `apple`)** · **Supersedes:** nothing. Builds on `docs/ASSESSMENT_BRIEF.md`.
- **2026-10-13** — split into this history file and a clean current spec; all decisions D-1…D-64 and slice rulings
  through S10d-1 folded into the spec text.

- **2026-10-13 (night)** — slice 10d merged (`bbd0674`). UAT change: the process chart shows tree and panel side by
  side from **1100 px** (was 900 px in D-63) — at 900 px the panel was ~250 px wide and clipped its buttons
  (ui-verifier, Evidence/2026-10-13/slice-10d). Spec §14 updated.

---

## 3. Decision log (formerly design §1a)

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
| D-31 | **The DFD is generated, not drawn** *(pending D-65: drawing connections on the canvas, recorded 2026-10-13)* — processes, data stores and external entities from the same rows as the process flow, without sequence | `generate_dfd` / `export_dfd` beside `generate_process_flow`. No new table | — |

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

### Revision 2026-10-11 — one platform, many kinds of project (D-37…D-49)

**Status: SIGNED OFF by Ben, 2026-10-11**, apart from the modelling detail of D-47 and D-49,
which goes to `apple` before anything is built on it. Ben answered OR-4 and OR-4b himself and
accepted Lilly's recommendation on every other open question (D-48). **No slice builds on a
row that is still OPEN.** These rows override the sections they name. Those sections are rewritten when
the slice that builds them gets its spec, and until then each carries a pointer back here.

**Why this revision exists.** VB will be used on engagements that need different parts of the
model. Some need business requirements only. Some need no function requirements but do need
as-is and to-be data flows. Some define every data attribute and some define primary keys
only. The signed-off design assumed every project uses the whole chain (BFC → BR → Solution →
FR → effort → baseline). This revision makes the chain configurable per project, and records
five other changes Ben asked for in the same conversation.

| # | Decision | Status | Effect | Overrides |
|---|---|---|---|---|
| D-37 | **The components a project uses are chosen per project.** Ben: *"some projects might just require business requirements … they might not have a functional requirement, but they might want an as-is data flow and a to-be data flow."* | **DECIDED** (incl. OR-1…OR-3) | A per-project component set, chosen at project creation and changeable by an admin. Candidates: Solutions · Function requirements · Applications & interfaces · Effort & rate card · Issues · To-be DFD · As-is BFC + DFD (D-47) · WBS (D-41) · Benefits · Risks · Change requests. **A component that is off is hidden in the UI and its write routes are refused by the server**, with one guard check (presentation alone is never the control, as with `useCanEdit`). **A baseline freezes only the components that are on**, and the priced diff appears only when effort is on | The implicit "every project uses everything" in §4 and §7.7. D-33's "WBS optional per project" becomes one case of this |
| D-38 | **There is no separate business process flow; every process is shown in the DFD.** *(Pending D-70, recorded 2026-10-13: the fixed completeness rule may become a per-project setting.)* Ben: *"In my philosophy there is no such thing as BPF because every process we are going to make in DFD."* | **DECIDED** (incl. OR-4, Ben 2026-10-11) | The DFD becomes **the** process diagram (as-is and to-be: D-47). "Business process flow" stops being a screen name or a concept. **Explicit order arrows are retired.** Order is derived from data: B follows A when B reads what A writes. A branch is two different outputs ("Approved order" / "Rejected order") feeding different processes, and a loop is a later process writing what an earlier one reads. Ben: *keeping both would be a duplicate.* **Every process has at least one input or trigger (D-49) and at least one output data entity.** A process missing either is a warning, and **blocks the baseline freeze**. `BFC_NODE_FLOW` is retired (no new rows; existing rows soft-retired, never deleted), and the flow-file import (D-25) carries inputs, outputs, triggers and the performer instead of edges. The swimlane is the performer (D-46) | D-20, D-21, D-31 (two diagrams from one record); §4.1a. D-24 (step I/O recorded once) is unchanged and is what the DFD is drawn from |
| D-46 | **The swimlane is the performer: one per process.** Ben: *"this could be done by a human being, an IT system, or AI … a swim lane to say which department, position, IT system, or technology is taking care of this process."* | **DECIDED** | Each process has **one performer**, which is a department (org unit), a position (org role), an IT system (application), or AI. A system that supports a human performer (a clerk working in SAP) shows inside the process box, as today. The performer replaces "the one RESPONSIBLE RACI role is the lane" (R2-D9, A-46). RACI stays as the record of accountability, not of the lane | R2-D9 lane rule, A-46 |
| D-47 | **A project may hold two sets: a to-be BFC + DFD, and an optional as-is BFC + DFD.** Ben: *"two different types of DFDs in each project, but it's not mandatory … two subsets of the BFC and the DFD as a set … 'as is' is always going to be optional because we might not make it in many projects."* | **DECIDED** (direction); modelling detail to **`apple`** | The as-is set is a separate BFC tree with its own processes, performers and data flows, so the to-be picture can add, drop, merge or re-perform processes. The as-is set is created only if the project wants it. **Proposed for `apple` to confirm:** (1) one data-entity catalogue per project, shared by both sets, so as-is and to-be data compare; (2) business requirements, solutions and FRs attach to the **to-be** set only; (3) the as-is set can be started blank or by copying the to-be tree, and the to-be set by copying the as-is; (4) the as-is support on a step (S6b-1) becomes the performer and supporting systems of as-is processes. A project with neither DFD component still has the to-be BFC, because BRs hang off it | D-22 (as-is and to-be as the same flow rendered twice), OR-4b |
| D-48 | **The open questions OR-1…OR-3 and OR-5…OR-9 are decided as recommended** (Ben, 2026-10-11: "accept all"; "as long as the goal is met, I am okay") | **DECIDED** | The recommendation column of the table below is now the decision | — |
| D-49 | **A process is started by data, by an outside party, or by a time or event.** | **DECIDED** (accepted recommendation) | A trigger is an input data entity, an inbound flow from an external entity, or a new **time/event trigger** ("month-end", "customer calls"): a named trigger with a kind (TIME / EVENT). Shown on the DFD as a start symbol. The time/event trigger is a new table, so it goes to `apple` | — |
| D-50 | **Version comparison screen: any two versions side by side, changes highlighted, drill down to the gap.** Ben, 2026-10-11: *"do the comparison between some of the versions … version 1 against version 3 … highlight with colors and some text … drill down inside the link to see what the gaps are."* | **DECIDED**, wave 4; detail as recommended (D-48 pattern) | Built on `diff_baseline` (§4.6), which arrives with the freeze in wave 1. **Any two baselines** of one project (not only neighbours), and a baseline against the live working set. **Summary:** per area (BFC, BR, DFD, data entities and fields, solutions, FRs, applications and interfaces, effort), counts of **added / changed / removed**, each with a colour from `STATUS_COLOR_MAP` *and* a text label and icon, so meaning never rests on colour alone. Effort shows the priced delta in man-days. **Drill-down:** each count opens the list of rows; each row opens a before/after view of the changed fields (old struck through, new highlighted) and a link to the live item. **Diagrams:** the DFD and the ERD of the later version are drawn with added, changed and removed elements highlighted, and removed ones shown ghosted. A comparison can be exported as PDF (D-42) | §4.6 `diff_baseline` gains a UI; §14 gains the screen |
| D-39 | **How much of a data entity is defined is chosen per project.** Ben: *"some projects might want all of the data attributes defined, whereas some will only put the primary keys."* | **DECIDED** | A per-project setting **data model depth** ∈ `KEYS_ONLY` / `FULL`. `KEYS_ONLY` expects primary and foreign keys and does not warn about missing attributes. `FULL` warns when an entity has keys but no other attributes. Either way, extra fields are always accepted. The ERD, `validate_entity_model`, the import preview and the freeze warning "entities with no fields" (S4-12) read the setting | Extends D-26, which already makes a partial field list legal |
| D-40 | **Three kinds of user. Staff users see every project.** Ben: *"The admin can see everything, including the admin functions. The users are able to see the whole projects and also the edit functions. There's another user that only can see."* Answer of 2026-10-11: **users see all projects** | **DECIDED** (incl. OR-5, OR-6) | **Admin:** every project plus the admin functions (users, projects, programs, house rate card, global codes). **User:** every project, read and edit, but no admin functions. **Viewer:** read only, no edit controls and every write refused by the server. Program grants and the "one grant per user" rule stop being how FTC staff reach projects. Programs remain as roll-up groupings. **Cost to make visible:** the project is no longer a data wall *between FTC staff*. Any staff user can read every client's data. This is Ben's call to make, and OR-6 asks whether any engagement's confidentiality terms need an exception | D-9 (OWNER/EDITOR/REVIEWER), D-32 (one grant per user, the project as a hard data wall), Q10, Q16; §4.7, §7.8. The rule "a project you cannot see is 404, never 403" still holds wherever a project is restricted (OR-6) and for client logins (D-43) |
| D-41 | **WBS: imported from MS Project, and progress is recorded in VB.** Answer of 2026-10-11: *"Import + progress only."* | **DECIDED** (incl. OR-7) | Tasks still come from MS Project (D-33, keyed by Unique ID). VB adds **progress updates against each imported line**: % complete, actual start and finish, a status (on track / at risk / late), a comment, and the date of the update. Each update is a new dated row, so progress over time is kept and never overwritten. A **progress report** (plan vs actual, slip, % complete by phase and solution, latest comments) is generated from VB. Creating tasks, dependencies, Gantt editing and critical path stay out of scope (§12.2) | D-33 "read-only in VB except the phase/solution links": progress fields become editable through progress updates. §4.15 gains functions; §12.1 moves WBS to wave 2 (see below) |
| D-42 | **Many reports can be produced as PDF.** | **DECIDED** (incl. OR-8) | A PDF export for each client-facing report: BFC, BR register, DFD (as-is and to-be), ERD, solution and FR registers, interface list, effort summary, baseline and priced diff, issue log, WBS progress report. Every PDF prints its project, its baseline version (or "LIVE — not a baseline"), its generation time and who generated it, and every PDF generated is recorded in `AUDIT_EVENT`. Untrusted text renders as text in PDFs exactly as in the browser (§14.5) | §12.2 non-goal "no vendor hand-off package", narrowed |
| D-43 | **Clients can view their project in a browser, two ways, only when the client agrees.** Answer of 2026-10-11: **both** | **DECIDED** (incl. OR-9) | **(a) Client read-only login:** client staff log in as viewers of **their own project only**, never of any other project. That limit holds even though FTC staff see every project (D-40), and it is the one place the project wall must survive. Access can be withdrawn and every view is audited. **(b) Offline viewer file:** one self-contained HTML file generated from a frozen baseline, opened in any browser with no login and no network, in which the client clicks through reports and drills down. **Once sent, it cannot be withdrawn and anyone holding it can read it.** Both need the client's consent recorded on the project first (who agreed, when). Each file generated is audited | D-11 (no client logins in MVP); the `CLIENT_REVIEWER` exclusion in §1a; §12.2 "client-user login" non-goal |
| D-44 | **The UI is in English, Japanese and Thai.** | **DECIDED**, wave 4 | Each user chooses a language, and PDFs and the offline file print in the language of the user who generates them. Translated: every screen string (already through `t()`, one file per area, §14.8) and every seeded `code_master` label. **Content typed by consultants is never translated**; it shows as typed. Thai needs its own font (Noto Sans Thai) beside Noto Sans JP. The `code_master` label change is a schema change and goes to `apple` first | §14.8 "English for MVP" |
| D-45 | **Spec before build.** Ben: *"make sure that we have the spec document updated according to the function that we are going to make."* | **DECIDED** | No slice after Slice 6 is built until (1) this revision's OPEN rows touching it are answered, and (2) its section of §4 is rewritten to match. The wave table below is reordered so the foundations of D-37 and D-40 land before the baseline freeze, because the freeze set depends on both | §12.1 order |

**Questions put to Ben, and the decision.** All decided 2026-10-11: OR-4 and OR-4b by Ben's own answer, the rest as recommended (D-48).

| # | Question | Decision |
|---|---|---|
| OR-1 | **Can a component be switched off after data exists in it?** | **No while live rows exist.** The switch is refused with a list naming them, as soft delete is (R2-D2). Data is never hidden while still live, and nothing is deleted |
| OR-2 | **Dependencies between components.** Effort needs function requirements. Applications & interfaces need function requirements for interfaces. The to-be DFD shows systems through Solution → Application (D-22) | Switching a component on also switches on what it needs, and the admin is shown the list first. A to-be DFD without Solutions shows steps and data, with no systems |
| OR-3 | **Is there a default set, or project templates** (e.g. "Requirements only", "Data & process", "Full delivery")? | Three named templates as a starting point, then any combination. Templates are `code_master`-style data, not code |
| OR-4 | **Step order** (D-38). VB already records which step follows which (arrows, branches, loops, swimlanes), and the flow-file import carries it. Keep it or drop it? | **Ben: retire the arrows; order is derived from data** (D-38). Lilly had recommended an optional component; Ben's reasoning (every process has an input and an output, so arrows duplicate the data) carried |
| OR-4b | **Is the to-be DFD the same steps with different systems (today's D-22), or a separately drawn future process with its own steps, stores and flows?** | **Ben: two sets per project, a to-be BFC + DFD and an optional as-is BFC + DFD** (D-47) |
| OR-5 | **What may a viewer see?** Every project, like a user, or only projects they are given? | FTC viewers: every project, read only. Client viewers: their own project only (D-43). Otherwise there are two different viewers |
| OR-6 | **Restricted projects.** Does any engagement's confidentiality agreement forbid staff outside the engagement from seeing its data? | A per-project **restricted** flag, off by default. A restricted project is visible only to admins and to named users, and keeps today's 404 behaviour. This keeps D-40 simple for the normal case and safe for the exception |
| OR-7 | **WBS re-import vs VB progress.** When MS Project is re-imported with its own % complete and actual dates, which wins? | VB progress updates are the reporting source and are never overwritten by an import. Imported actuals are kept beside them, and the report flags lines where the two disagree |
| OR-8 | **Which reports first, and may a PDF be made from live (unfrozen) data?** | Live data allowed, stamped "LIVE — not a baseline" on every page. Client-facing PDFs from a baseline. First five: BR register, DFD as-is/to-be, ERD, baseline diff, WBS progress |
| OR-9 | **Offline file safeguards.** | Generated only from a frozen baseline. Admin or user only, never a viewer. Requires recorded client consent. Every page footer names the client, version and generation date. Opt-in to include issues and stakeholder names, which may carry personal data |

**Delivery order** (signed off with this revision; supersedes the wave table in §12.1):

| Wave | Contents |
|---|---|
| **1 (remaining)** | **1a** Project components and data model depth (D-37, D-39) · **1b** Access: admin / user / viewer, restricted projects (D-40) · **1c** One DFD: performer lanes, triggers, order from data, the as-is set (D-38, D-46, D-47, D-49) · **1d** Baseline freeze over the enabled components · **1e** Imports 4b–4d · **1f** Reports, program roll-ups and PDF export (D-42) · **1g** Code maintenance |
| **2** | Benefits (D-14) · change requests (D-16) · **WBS import + progress updates + progress report (D-33, D-41)** |
| **3** | Risks (D-15) · decisions (D-17) · phasing and dependency (D-18) |
| **4** | English / Japanese / Thai (D-44) · **Version comparison screen (D-50)** |
| **Before first client use** | Azure (D-35) · restore drill (§15.3) · prompt pack (D-36) · client read-only login and the offline viewer file (D-43) |

### Slice 7 schema rulings — 2026-10-11

Schema `docs/slice7_schema.md` (apple), covering 7a components, 7b access and 7c the DFD rework.
Ben, 2026-10-11: *"I will accept your recommendations, so build it first."*

| # | Ruling | Supersedes | Source |
|---|---|---|---|
| S7-1 | **All 33 [Q-n] in `slice7_schema.md` §10 are accepted as recommended**, as amended below (Ben) | — | apple Q-1…Q-33 |
| S7-2 | **One BR per *to-be* process.** As-is processes carry no BR; the database enforces it (generated `'TO_BE'` column + FK on `business_requirement`) | D-2 "every process node carries exactly one BR" | apple §11.1 |
| S7-3 | **The input/output completeness rule blocks the freeze only for a set whose DFD component is on.** *(Pending D-70: the rule itself may become per project.)* A requirements-only project freezes without it | D-38 as written | apple §11.2, Q-29 |
| S7-4 | **Applications need no other component; only the interface routes need FRs and Applications** | OR-2's "applications need FRs" | apple Q-4 |
| S7-5 | **No layout rows are deleted.** Old `PROCESS_FLOW` positions stay as history, the type CHECK is unchanged, and the service refuses new ones | apple Q-31 (delete) | Lilly, to keep law 1 without exception |
| S7-6 | **Grants are soft-revoked after being copied into `project_member` (0038)**; nothing is deleted, so it proceeds without a pause (Ben: build without stopping unless critical) | — | apple §8.5 |
| S7-7 | **Until 7c retires them, the process-flow arrows (`bfc_node_flow`) are gated under To-be DFD**, with external flows. A requirements-only project does not sequence steps; under D-38 sequence becomes derived in 7c anyway | slice7_schema §5.2 table | sara L10 (Lilly, under S7-1) |

### D-51 — the mockups are the visual reference, 2026-10-11

**Status: DECIDED by Ben, 2026-10-11** (*"yes please work on front end"*, after he found the built screens far
from the mockups). Overrides §14.2 and §14.3 where they disagree.

| # | Decision | Effect | Overrides |
|---|---|---|---|
| D-51 | **The ten screen mockups in `docs/mockups/` (React + MUI, screenshots in `docs/mockups/screenshots/`) are the visual reference for every screen.** The "v9 canvas boards" §14.2–14.3 cite are not in the repo and are superseded | **Dark is the default, light the alternate** (one `colorSchemes` theme, as before). Dark neutrals are the mockups' purple-tinted `SURFACE` set; radii card 24 · diagram 18 · field 14 · pill buttons. **The shell is the mockups' left rail** (engagement selector, nav grouped Scope / Control / Admin with icons, user at the foot) **plus a header** with breadcrumbs and the working-set version chip ("Working · after v1.2", from the real baseline list). Screens follow their mockup's layout (side panels, tiles, tags, level badges, RACI toggles); screens with no mockup use the same kit. **Nothing is faked:** a mockup element whose data or feature is not built yet (issues, history, search, trigger/frequency/priority on a BR) is left out until its wave, not drawn empty or with invented values | §14.2 "light is the default", §14.3 top bar; §14.3 "no further mockups are needed" stays true for screens without one |

### Ben's front-end review — 2026-10-12 (D-52…D-55)

**Status: DECIDED by Ben, 2026-10-12** (*"Yes please work on this in the next slice"*), after reviewing the
Slice 9 screens. D-52 changes the data model and goes to `apple` before it is built (Slice 10b); D-53 and
D-54 are screen-only (Slice 10a); D-55 is built with the flow-file import (wave 1e). These rows override the
sections they name; those sections are rewritten when the slice that builds them gets its spec.

| # | Decision | Effect | Overrides |
|---|---|---|---|
| D-52 | **A BR maps to FRs directly; the Solution is optional.** Ben: *"The whole point is we wanted to do the mapping between the business requirements and the functional requirements … if user want to use Solutions then can map BR-Sol-FR. But if they want to skip then just BR-FR."* | **BR ↔ FR is a stored many-to-many link** and the primary mapping. BR ↔ Solution (`BR_SOLUTION`) is unchanged. An FR may carry an **optional solution tag**, stored once on the FR (`solution_id`, already nullable since D-28), so its effort counts toward one solution and is never double-counted. The user does all of it from the BR screen: link solutions, link FRs, and on each FR row optionally pick which of the BR's solutions it delivers. No separate Solution–FR screen. Knock-ons for `apple`: backfill direct links from today's derived BR→Solution→FR paths so no mapping is lost; what becomes of D-34's `suggested_br_id`; the baseline shadow; traceability, coverage and effort reports read the direct link | **D-7** (FR hangs off a Solution; `FR_BR` deleted, BR→FR derived) and its §5.4.3 override, which reinstates `apple`'s original M:N recommendation; A-26 |
| D-53 | **Business requirements are part of the business function chart, not a separate module.** Ben: *"the lowest level of the business functions is going to be the business requirements … it's not a separate component."* | The data already holds this (D-2, S7-2: one BR per to-be process, created with it). **Screen change only:** the "Business requirements" left-rail item and its list page go; the BR is read and edited from the process's panel in the function chart. The BR detail page stays as a deep link (from FRs, solutions, the diff), crumbed under Business functions | §14 rail; D-51 rail grouping |
| D-54 | **The DFD menu is its own screen: a flat list of DFDs on the left, the diagram on the right.** Ben: *"BFC and DFD looks very alike and confusing."* | One DFD per **direct parent of processes** (in a five-level chart, the L4s), listed flat with its code, name and process count, searchable, no tree. Selecting one draws its diagram on the right. Wider roll-up diagrams (an L2 or L3 with all processes below) still open from the function chart. Replaces the redirect into the function chart with a picker | D-51 DFD navigation |
| D-55 | **An imperfect DFD file still imports, with warnings.** Ben: *"the DFD might not be perfect … we want some warning but still can upload and import."* | **Warn and import:** a process with no input/trigger or no output, an unconnected process, an unknown data entity name (created as a new entity, listed in the preview), an unknown performer (left blank), missing descriptions. The gaps then stay visible as a warnings panel on the diagram (D-38's freeze block is unchanged: an incomplete DFD can be imported, not frozen). **Still blocks** only what would damage data: unreadable file, wrong format version, a file for a different anchor or mode than chosen (R2-P3), a stale `row_version` (R2-D5) | §4.1a `validate_process_flow_json` error/warning split |

### Ben's UI feedback, evening — 2026-10-12 (D-56…D-62)

**Status: DECIDED by Ben, 2026-10-12** (*"I do accept the plans"*; D-62 *"go with B"*), on Lilly's recommendations. D-56, D-57 and the
first half of D-60 are screen-only (Slice 10c, after 10b merges). D-59, the second half of D-60, and D-61 change
the data model and go to `apple` first (Slice 11). D-58 gets its own spec with a KPI list for Ben (Slice 12).
"Trailer" in Ben's note is read as **trigger** (ASSUMPTION, to confirm).

| # | Decision | Effect | Slice |
|---|---|---|---|
| D-56 | **Organisation and Systems are first-class in the menu.** Ben: *"there's no organization component"*; *"the system has to be like a master."* | Org units and org roles (today under Settings → Organisation) and Applications (today under Interfaces, only with APPLICATION on) get their own rail items. Each process's performer (D-46, the "organisation in charge") is shown plainly in the process panel. No data change: both lists and the performer already exist | 10c |
| D-57 | **Plain-language guidance on non-process boxes, and triggers on the panel.** Ben could not parse `processes.stepFactsHelp` | Reworded: inputs, outputs, roles and parties are recorded on processes (the lowest level); open a process below this function, or turn this function into a process — with a button for each. The process's triggers (D-49) show in the process/BR panel | 10c |
| D-58 | **Two dashboards: Scope and Project management.** Ben: *"the current dashboard is very simple … all the KPIs that we need to manage the entire project."* | Scope: coverage and gaps (processes with a BR, BRs with FRs, untraced / no-solution FRs, entities without fields, open warnings, effort by solution, change since the last baseline). Project management: baselines and approvals, change requests, risks, issues, WBS progress — each tile appears when its wave lands, never with invented numbers (D-51). KPI list goes to Ben before build | 12 |
| D-59 | **A BR is structured, not three free-text boxes.** Ben: *"It should be a bit more structured."* | Direction: numbered requirement lines under each BR, each with a kind (e.g. rule / calculation / validation / output / control) and a priority. `apple` proposes the model with two or three options and examples for Ben | 11 |
| D-60 | **A BR shows, then names, the data attributes it works with.** Ben: *"show the data attributes that are related to each of the BRs."* | (a) **10c:** each data entity linked to the BR expands to its attributes (name, type, key, mandatory), read-only. (b) **11:** the BR marks which attributes it uses and how (CRUD per attribute), optional under `KEYS_ONLY` (D-39) | 10c / 11 |
| D-62 | **Consultants see only the projects they are assigned to.** Ben: *"when the users actually log in, they have the list of projects that they will be able to access."* Chosen over ticking "restricted" project by project (option A) | **New projects are created restricted**: the new-project form preselects "assigned consultants only" (the API already requires the choice explicitly, §8.10 risk 1, so no schema change), so a USER or VIEWER sees a project only as a live `project_member`; admins still see all. An admin may open a project to all staff by clearing the flag. **Existing projects are switched once**, by an admin, after their member lists are checked — never silently by a migration. The 404-not-403 rule (OR-6) now covers the normal case. No migration (Slice 10c spec); `sara` reviews before commit (access). **Overrides D-40** "staff users see every project" and OR-6's "off by default" | 10c |
| D-61 | **A BR records system-to-system data flows.** Ben: *"what data entity we want to copy from which system to which system."* | A BR can state data entity + from-system + to-system (Applications as the master list, D-56), which can later seed interface FRs (whose source/target already point at Applications). Model to `apple` | 11 |

### Design critique of the business-functions screen — 2026-10-13 (D-63…D-64)

**Status: DECIDED by Ben, 2026-10-13**, after an /impeccable critique (23/40; `.impeccable/critique/` in the 10b
worktree): the process panel had become mockup 01 + all of mockup 03 + the DFD facts + the FR section stacked in one
~1,900 px column, with duplicates and 10.5 px labels. Built as **Slice 10d**, before 10c.

| # | Decision | Effect | Slice |
|---|---|---|---|
| D-63 | **The process panel is ranked.** Ben accepted the proposed order. *(Pending D-66, recorded 2026-10-13: Delivery splits into Solutions and Function requirements, ranked higher.)* | **Primary:** process name (large, editable heading), its path, the **requirement statement** (largest field), business logic, Draft/Confirmed, BR number. **Secondary:** four tiles — performer, what starts it, Accountable, data in/out — each opening its editor. **Collapsed with counts:** Delivery (solutions + FRs), external parties, description, supporting systems. **⋯ menu:** make process, retire, restore, open the BR page. Tree and panel scroll independently; one at a time below 900 px. Static labels ≥ 13 px, a 4-step type scale, help behind (i). The Coverage tile leaves the panel (stays on the BR page) | 10d |
| D-64 | **One RACI per process on screen: the BR's.** Ben chose it over keeping both | The panel shows and edits the BR's roles only. What happens to the step's own role rows (`bfc_node_org_role`: kept in step with the BR's, derived, or retired) is a data-design change and goes to `apple` before 10d builds it | 10d (apple first) |

Pending: Purpose and Data processing (Ben asked what goes in them, with sample text, before deciding).

**Slice 10d RACI rulings (Ben, 2026-10-13: "I accept all six").** S10d-1: all six [Q-n] in `docs/slice10d_raci_schema.md`
accepted as recommended — to-be roles live on the BR, as-is roles on the step (option c); the BR's Accountable wins a
conflict (audited); roles of retired processes are merged so a restore brings them back; chart copy carries roles
across; a to-be process with no live BR blocks migration 0052 with a list; the one-time moved entries in old-baseline
diffs are accepted.

### Ben's rulings, 2026-10-14 — "I accept all of your recommendations" (D-65…D-70 and the open questions)

**Status: DECIDED by Ben, 2026-10-14**, on the decision page of that night (every open question with Lilly's
recommendation). Ben: *"I cannot select the button, so I accept all of your recommendations."* The page's slice 11 line
excluded [Q-11] and [Q-17], which stay open (§1).

**D-65…D-70 (Ben's feedback of 2026-10-13), now decided as specced in `slice13_spec.md` and `slice13_schema.md`:**

| # | Decision | Effect (as recorded; the spec and schema give the detail) | Slice |
|---|---|---|---|
| D-65 | **Can the DFD be edited on the diagram itself (connect, move)?** Ben asked whether it is always generated from the BRs and function descriptions | Today: boxes can be **moved** by an editor and the position is kept (D-30); **connections cannot be drawn** — every flow is generated from the process's inputs, outputs and external flows (D-31, D-24), edited in the panel. Open for the spec: drawing a connection on the canvas that writes the same step I/O row (`bfc.ensure_step_io`), so the diagram stays generated from one record | — |
| D-66 | **Split Delivery in the process panel into two: Solutions and Function requirements.** Ben: they are the most important things | Revises D-63, which put both in one collapsed "Delivery" section. Two sections, ranked higher than the other collapsed sections; FRs list independently of solutions (D-52, solution optional) | 10d follow-up |
| D-67 | **Optional process-volume fields for a time-saving / ROI analysis.** On the process description: frequency, number of transactions with a **unit chosen from a master**, assumed time to run the process, and from those the **estimated FTEs** to run it | All optional. Units a `code_master` type (send codes). FTEs are derived, never accepted from a request (VB law 6); the hours-per-FTE basis is a spec question. As-is vs to-be values (D-47) would show the time saved. New columns → `apple` first, shadow columns in the same migration | — |
| D-68 | **The BR list shows each BR's DFD readiness as a traffic light.** Red: the DFD cannot be completed from it. Yellow: partly. Green: complete | Measured against the project's completeness rule (D-70). The light needs a text label and an icon too, never colour alone (as D-50) | — |
| D-69 | **On each BR, mark the data needed for the DFD.** Ben: *"put a reference that you need to fill in this information in order to complete your DFD"* | A marker on each field the project's rule (D-70) requires, with a short note saying it is needed to complete the DFD. The marker follows the rule, so it changes when the project changes its rule | — |
| D-70 | **Each project decides what makes its DFD complete.** Ben: a process flow with no data entities is possible, *"but I don't recommend it"* | A project setting listing the required elements, chosen from: process, forward arrow (order), trigger, external entity, data entity in/out. Default is the full set, recommended. **Conflicts to settle in the spec:** (1) D-38's fixed rule (at least one input or trigger and one output, which blocks the freeze) becomes this setting; (2) under D-38, order is **derived from data** and explicit arrows are retired, so "arrows without data entities" needs either explicit arrows back as an option or a different source of order; (3) Ben's wording *"fully with the external, maybe only with the D"* is read as *"or only with the data entities"* (ASSUMPTION, to confirm) | — |

| # | Ruling | Source |
|---|---|---|
| S13-1 | **All slice 13 questions accepted as recommended**: Q-1…Q-16 (`slice13_spec.md` §15 — incl. Q-3 option A: per-project rule, order still derived from data only, chart order when there is none; Q-13 red = blocks the freeze, yellow = passes it but misses a recommended element; Q-15 one rule per chart) and Q-17…Q-28 (`slice13_schema.md` §8 — incl. Q-8 transactions per run and time per transaction, stored in seconds; 240 × 8 h working year) | slice13_spec §15, slice13_schema §8 |
| S13-2 | **The interim 13a rule ends**: yellow no longer says "Blocks the freeze" once 13b ships the rule (Q-13) | slice13_spec §16 DR13-P2 |
| SC-1 | Cross-project hand-off: the other project is shown as an outside party on the DFD boundary ("Project: X"); no new table | spec CHECK C-1 |
| SC-2 | A change request may target a FROZEN or APPROVED baseline, or a SUPERSEDED one that carries the agreed approval (DR8-P1 wins over Q8) | C-2 |
| SC-3 | `FR_BFC_NODE` (FR linked straight to a function, never built) is retired; BR ↔ FR direct covers it | C-3 |
| SC-4 | WBS progress updates: `apple` models the table when the WBS wave is specced | C-4 |
| SC-5 | As-is vs to-be system gap: matched by area (code and name), as Q-28; a process link later | C-5 |
| SC-6 | Flow-file import: identity errors still block; as-is processes match by name within their parent; cap 2,000 inputs/outputs/flows/triggers combined; export at `/bfc-nodes/{id}/dfd/export?format=json` | C-6 |
| SC-7 | Deciding a change request and resetting control rules: EDIT (project editors); admins always | C-7 |
| SC-8 | "Split into sub-steps" keeps the built rule: refused with a list until the consultant clears the facts (R2-P5) | C-8 |
| SC-9 | Issue module and control rules come right after slice 12 (dashboards), opening the next wave | C-9 |
| SC-10 | House rate card stays a fixed default in code until a client needs another; removed from the admin list | C-10 |
| SC-11 | Four lookup lists (`bfc_set_code`, `performer_kind`, `trigger_kind`, `flow_type`) get a playbook-deviation line; A-15 (naming final) confirmed; "effort by L1 area" moves to the reports slice | C-11 |
| SP-1 | **One save model on the process panel**: typed text waits for Save (unsaved counter, Ctrl+S); everything else saves the moment it changes; the performer and trigger editors lose their own Save (Done = saved) | P-1 |
| S10c-2 | **10c Q-1…Q-3**: the performer can be recorded whatever the DFD setting (performer gated by the function chart; triggers stay with the DFD); every live project switches to assigned-only after its team is checked; Lilly keeps the inventory (`slice10c_spec.md` §12) and an admin confirms each switch on its Access screen | slice10c_spec §11 |
| S11-1 | **Slice 11 [Q-1]…[Q-16] accepted as recommended** (option A numbered BR lines, kinds, life-long numbers, MoSCoW priority, old boxes copied once and kept read-only, attribute C/R/U ticks, flows as business statements, frozen from the next hash spec — spec 4, since slice 13c takes spec 3). **[Q-11] and [Q-17] stay open** (§1) | slice11_schema §8 |
| S-T | "Trailer" in Ben's 2026-10-12 note means **trigger** | D-56…D-62 note |

### Ben's rulings, 2026-10-16 — the two slice 11 questions left open by S11-1

| # | Decision | Supersedes / answers |
|---|---|---|
| S11-2 | **[Q-11] Both.** *(The flow kind is superseded by S11-5: migration is an FR type.)* Ben chose option (a): "Integration and migration, each flow tagged." A BR system-to-system flow carries a kind, `INTEGRATION` (ongoing) or `MIGRATION` (one-off data migration), CHECK-listed because coverage branches on it; built into slice 11's own migration, not added later. The kind joins the flow's grain. One sub-point opens: [Q-11a] (§1) | slice11_schema §3.3, §8 |
| S11-4 | *(Superseded by S11-5.)* **[Q-11a] A migration flow is covered by any FR of the same BR whose interface carries the entity between the same two systems, whatever the FR's behaviour (batch included).** Ben: "Not sure what is Migration Flow" — explained as the one-off copy at go-live; every flow defaults to Integration, Migration is an option; the recommendation taken | slice11_schema §3.3 |
| S11-5 | **Migration is an FR type, not a flow tag** — supersedes S11-2's flow kind and S11-4. Ben: "So you are talking about Solution Type or FR Type? If that is the case should be FR Type." A BR system-to-system flow stays (BR × entity × from × to) with no kind. FR_TYPE gains `MIGRATION` "Data migration" with behaviour `INTERFACE`, so it has the interface card (source, target, entities) and covers a flow exactly as an interface FR does; the rate card gains its four complexity rows, at the interface rates until FTC confirms its man-days | S11-2, S11-4 |
| S11-6 | **[Q-29] Slice 11 merges as one: 11a, 11b and 11c land on `main` together, once all three are built and tested, with one hash-spec bump (spec 4) for all three tables.** Ben: "Q-29 combine please". The spec's §5 / criterion 189 stand as written; the three pieces are built and reviewed one by one on the branch, never merged one by one | slice11_schema §5, §7 |
| S11-8 | **[Q-30] A requirement-line edit counts towards "effort exposed".** Ben: option (a), "line edits count, as built". A BR counts as changed in the priced diff when its own row changed or one of its requirement lines was added, changed or removed; a reorder does not, and lines a side never froze (`not_frozen_in`) are skipped (sara 11a H2) | `priced_diff` |
| S11-7 | **[Q-31] Yes to both.** Ben: "Q-31 Yes". (1) Data migration FRs (S11-5) are listed in the Interfaces register beside interface FRs, with their FR type shown so the two can be told apart; a migration FR carries the same interface card, Frequency optional as for any interface (S6b2-1). (2) Rate-card rows added between two baselines (e.g. the four MIGRATION rows backfilled into existing projects) count in the comparison headline like any other added row | `interface_list`; §7.7 diff |
| S12-1 | **Slice 12 KPI list approved as drafted** (`docs/slice12_kpis.md`). Ben: "let's go with that, I do not want too many in the beginning." Slice 12 adds only S7–S11 from the list; the Project-management view stays a card on the dashboard until it has more than one tile (the list's question 2) | D-58 |
| S11-3 | **[Q-17] One master list of systems.** Same answer (a): flows pick both ends from the Applications list (D-56) as built; no system of record per data entity | slice11_schema §3.3, §8 |
| S-P | Purpose and Data processing: Purpose is the description on L1–L4 boxes; on processes both sit in the collapsed Description section (as built in 10d) | slice10d_spec §11 |

### Slice 10b schema rulings — BR ↔ FR direct (D-52), 2026-10-12

Schema `docs/slice10b_schema.md` (apple). Ben, 2026-10-12: *"Accept all 21 items."*

| # | Ruling | Supersedes | Source |
|---|---|---|---|
| S10b-1 | **All 21 [Q-n] in `slice10b_schema.md` §10 are accepted as recommended**, Q-14 (hash spec v2, the digest defect) included and landing in this slice | D-7's derived BR→FR, D-34 | apple Q-1…Q-21 |
| S10b-2 | **Q-13 confirmed by Ben on its merits:** an FR with live BR links cannot be retired (409 naming the BRs), *"as it avoids silent data loss"* | — | Ben |
| S10b-3 | **Q-4 warnings stay non-blocking, and Ben asked that they be reportable and trackable later.** Pending Ben's choice of how (see the 10b spec) | — | Ben |

### Slice 8 schema rulings — the baseline freeze (wave 1d), 2026-10-11

Schema `docs/slice8_schema.md` (apple). Ben, 2026-10-11: *"For every decision that I need to make, I will
follow your recommendations."* These rows override §4.6, §6.1 ("30 shadow tables"), §7.7 and §9's baseline
rows where they disagree; slice8_schema §11 lists each rewording.

| # | Ruling | Supersedes | Source |
|---|---|---|---|
| S8-1 | **All 24 [Q-n] in `slice8_schema.md` §12 are accepted as recommended**, as amended below. In short: 24 shadows today (− `bfc_node_flow`, − the never-built `fr_bfc_node`, − the seven unbuilt wave 2–3 tables; + `process_trigger`, `bfc_node_trigger`, `project_component`); code **and** label copied, code hashed; no intra-baseline FKs; hash in SQL (`::text`, `\x1f`, NULL `\x1e`); freeze and client approval at EDIT; diff under `/projects/{id}/baselines/diff` with `to=live`; archive file and `purge_project` before first client use | §6.1 count, §7.7 `str(v)`, §9 routes, "OWNER only" | apple Q-1…Q-24 |
| S8-2 | **No `BEFORE TRUNCATE` trigger on the shadows.** The row-level reject trigger, the revoked UPDATE and the absent DELETE/TRUNCATE privileges hold immutability for `vb_app`; a statement trigger would also refuse the owner's test-harness wipe and the future purge | slice8_schema §3 `trg_…_no_truncate` | Lilly |
| S8-3 | **Criteria 13 and 30 read "every table in `FREEZE_SET` whose gate is open"**; criterion 41 is per entity | criteria 13, 30, 41 | apple §11 |

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
| S4-11 | **Import identity and meaning (Ben, 2026-10-01, on Slice 4a review).** A row exported from VB carries a **signed row token** (project, table, id, `row_version`) instead of a bare `row_version`. A token row that no longer resolves to its live row is an **error, never an INSERT**: a rename or move by spreadsheet is refused, and renames are done on screen. The field key normalises as the live-name index does, `lower(btrim(name))`. Blank clears; a missing column is refused; unchanged rows are MATCH and never written. `fk_group` is a file-local label on new rows. Fields in one file may reference each other (two-pass commit). Before-values are kept in `payload.before` for the 90-day window. `file_name` becomes `(purged)` at purge. Only a rule failure rejects a batch; an operational failure leaves it retryable | S4-5 (rename "arrives as an acknowledged INSERT", `normalise_name`), §10 criterion 6 (Slice 4a) | — (`docs/slice4a_spec.md` Q1–Q9) |
| S4-12 | **A whole data model from one workbook (Ben, 2026-10-08, on Slice 4a round-2 finding N1).** A workbook may carry an entities sheet and a fields sheet. Each sheet is still its **own batch for one target** (S4-2 and `ck_ir_kind_fits_target` unchanged), and the two run **in sequence**: the entities batch is validated, previewed and committed first, then the fields sheet is validated against the now-live entities. The browser keeps the file and sends it once per step; each target reads only its own sheet. A field row names its parent by `de_number` **or**, when that is blank, by parent entity name normalised as `lower(btrim(name))` and resolved in SQL against live entities; both given must agree. **Ben accepts that the entities commit before the fields preview is seen**: a failed fields step leaves the new entities live without fields until a corrected file is uploaded to the fields step alone. **Ben, 2026-10-09:** a referenced entity may likewise be named by `ref_de_name` (4a-R19); freezing a baseline **warns** about entities with no fields and still allows it (owed to the baseline slice); any project EDITOR may commit a batch another uploaded | §10 criterion 9 and A-4a-1 (Slice 4a) | — (`docs/slice4a_spec.md` §3, A-4a-8) |

### Slice 5 solutions — 2026-10-09

Schema `docs/slice5_schema.md` (apple), spec `docs/slice5_spec.md`; design review round 1 of 2 (8 findings, 0 HIGH).

| # | Ruling | Changes | Source |
|---|---|---|---|
| S5-1 | **A BR's solution links retire and restore with its step** (Ben). `BrSolution` joins `step_retire.OWNED_BY_BR`; a step restore asks for a since-retired solution first (A-SR-5) | §5.4.15 row `br_solution` (still covered; now owned) | Q-3, DR1-P3 |
| S5-2 | **A REJECTED solution can be linked** (Ben); the link shows its status, and coverage reports will not count it as an answer | §4.3 `br_coverage_report` (when built) | auditor Q1 |
| S5-3 | **A link's coverage note is edited in place** (Ben): `PATCH /business-requirements/{id}/solutions/{link_id}`; the previous note goes into the audit detail | §4.3 `link_br_solution` (was C/D), §9 | auditor Q2 |
| S5-4 | **`SOLUTION_CATEGORY` is a system category** (Ben): projects cannot rename or retire the five, because reports and `create_fr` branch on TECHNOLOGY / DATA | §8 | Q-5 |
| S5-5 | **Physical choices adopted on apple's recommendation:** solution names unique among live solutions per project (`lower(btrim())`); `br_solution` has the S1-5 surrogate PK with `(br_id, solution_id)` as a full UNIQUE; new solutions start PROPOSED; the D-34 hook waits for FRs | §5.3 BR_SOLUTION (PK wording), §6.2 | Q-1, Q-2, Q-4, Q-7 |

### Slice 6c rate card and effort — 2026-10-11

Schema `docs/slice6c_schema.md` (apple), spec `docs/slice6c_spec.md`; design review round 1 of 2 (11 findings, 1 HIGH — all fixed).

| # | Ruling | Changes | Source |
|---|---|---|---|
| S6c-1 | **The FTC default card uses placeholder values** (Ben), marked unconfirmed until FTC confirms | §7.10 | apple Q-7 |
| S6c-2 | **A rate change never reprices rated FRs**; it reports how many are not at the current rate; re-rating is per FR, audited (Ben) | §4.8 (as A-38) | apple Q-11 |
| S6c-3 | **Owners and Editors change the rate card** (Ben). Supersedes OWNER-only in §4.8 `maintain_rate_card`, §7.13 and the §9 rate-card row | §4.8, §7.13, §9 | — |
| S6c-4 | **Effort by L1 area waits for the reports slice** (Ben) | §7.9 | apple Q-9 |
| S6c-5 | **Visibility, not approval, controls the Editor who rates and re-rates**: a standing per-cell "not at current rate" count and Σ days, visible to reviewers (Ben) | §7.9, §7.13 | DR6c-P1 |
| S6c-6 | **Confirmed defaults update untouched cells only**, through an audited command (Ben). Ben or an FTC lead supplies the real values; the command is built then (Ben, 2026-10-11) | §7.10 | auditor Q3 |
| S6c-7 | **A cell above 60 man-days needs confirmation** and is flagged (Ben) | §6.2 | auditor Q4 |
| S6c-8 | **FRs under a REJECTED solution are shown apart** in the effort summary (Ben) | §7.9 | auditor Q5 |

### Slice 6b-2 interfaces — 2026-10-11

Schema `docs/slice6b_schema.md` §4–§7 (apple), spec `docs/slice6b2_spec.md`; design review round 1 of 2 (8 findings, 1 HIGH — all fixed).

| # | Ruling | Changes | Source |
|---|---|---|---|
| S6b2-1 | **An interface is complete with source, target, method and ≥1 carried entity** (Ben); pattern and frequency optional | §4.4 `interface_list` (was: endpoints only) | auditor Q1 |
| S6b2-2 | **A pair-filtered list counts the interfaces it cannot match** (no endpoints yet) (Ben) | §4.4 | DR6b2-P5 |
| S6b2-3 | **The pair filter is direction-as-stored; BIDIRECTIONAL matches either way** (Ben) | §9 | auditor Q3 |
| S6b2-4 | **Carried-entity notes appear on the vendor list**, edited on the interface card; a save keeps notes it did not touch (Ben) | §5.3 FR_INTERFACE_DATA_ENTITY, §4.4 | auditor Q4, DR6b2-D1 |
| — | Every interface PUT bumps the detail's `row_version` (it covers the carried set); per-branch version rules; one transaction | §7.5 `describe_interface` | DR6b2-P1…P3 |

### Slice 6b-1 applications — 2026-10-11

Schema `docs/slice6b_schema.md` §1–§3 (apple), spec `docs/slice6b1_spec.md`; design review round 1 of 2 (5 findings, 0 HIGH — all fixed).

| # | Ruling | Changes | Source |
|---|---|---|---|
| S6b-1 | **As-is support on a step is built now and retires/restores with the step** (Ben). `ApplicationBfcNode` joins `step_retire.OWNED_BY_STEP` | §5.4.15 row `application_bfc_node` (owned) | apple Q-1, Q-2 |
| S6b-2 | **Application codes unique (never reused) and upper-case; live names unique** (Ben) | §5.3 APPLICATION | apple Q-3 |
| S6b-3 | **Retiring an FR with live interface detail is refused until the detail is removed** (Ben; built in 6b-2) | §7.5 | apple Q-6 |
| S6b-4 | **A TO_BE application as today's support warns and is allowed** (Ben) | §4.4 | apple Q-7 |
| S6b-5 | **Such links do not count as today's support in `application_gap`**, and are never silent: a warning on the link and on a lifecycle move to TO_BE, plus the informational line `as_is_support_by_to_be` (Ben) | §7.9 `application_gap` | DR6b-P1 |
| S6b-6 | **Application codes are editable until a baseline freezes them**; characters A–Z 0–9 `.` `_` `-`; the old code goes to the audit (Ben) | §5.3, §6.2 (supersedes "code not editable") | auditor Q3 |
| S6b-7 | **A code freed by a rename may be taken by another application** (Ben, 2026-10-11). Before baselines nothing quotes it; once frozen a code cannot be renamed (S6b-6) | §5.3 | sara L2 |

### Slice 6a function requirements — 2026-10-09

Schema `docs/slice6a_schema.md` (apple), spec `docs/slice6a_spec.md`; design review round 1 of 2 (5 findings, 1 HIGH — fixed).

| # | Ruling | Changes | Source |
|---|---|---|---|
| S6a-1 | **`suggested_br_id` (D-34) arrives with the FR import** (Ben). That slice adds the column, excludes its FK from `FK_LIVENESS`, clears it on BR retire and on `BR_SOLUTION` link, and keeps it out of the baseline shadow and hash; a 6a tripwire test guards the last two | §5.3 FUNCTION_REQUIREMENT, §7.5 (deferred) | Q-2, DR6a-P1 |
| S6a-2 | **FR names are not unique** (Ben); a live duplicate under the same Solution warns | §5.3 | Q-1, DR6a-P2 |
| S6a-3 | **Complexity is not settable until the rate card (6c)** (Ben); `complexity_code_id` and `effort_days` ship NULL under the D-13 CHECK | §4.8 | Q-6 |
| S6a-4 | **The FR register is a second tab under BR–FR map** (Ben) | §14.3 | — |
| S6a-5 | **Adopted on recommendation:** an FR under a REJECTED Solution warns, never blocks; the first status is SPECIFIED, any status settable by an EDITOR; `v_br_function_requirement` is a DB view carrying `project_id`, `security_invoker` | §7.5 | Q-3, Q-7 |

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

---

## 4. Enhancement specs and schemas (one per slice)

| Document | What it is | Date |
|---|---|---|
| `docs/slice1_schema.md` | Slice 1 — BFC & requirements: physical schema | — |
| `docs/briefs/slice1-*.md` | Slice 1 screen briefs (chart, data, settings, common rules) | — |
| `docs/slice2_schema.md` | Slice 2 — process flow (order arrows; retired by D-38) | — |
| `docs/slice3_spec.md` | Slice 3 — DFD, ERD and Mermaid export | 2026-09-30 |
| `docs/step_retire_spec.md` | Retire a step with its requirement and flows | 2026-09-30 |
| `docs/draft_arrows_spec.md` | Suggest a flow's arrows from the chart order (retired with the arrows by D-38) | 2026-10-01 |
| `docs/slice4_schema.md · slice4a_spec.md` | Slice 4/4a — import staging and pipeline (data entities and fields) | 2026-10-01 |
| `docs/slice5_schema.md · slice5_spec.md` | Slice 5 — Solutions and BR → Solution links | 2026-10-09 |
| `docs/slice6a_schema.md · slice6a_spec.md` | Slice 6a — Function Requirements, first cut | 2026-10-09 |
| `docs/slice6b_schema.md · slice6b1_spec.md · slice6b2_spec.md` | Slice 6b — Applications, interface detail, interface list | 2026-10-11 |
| `docs/slice6c_schema.md · slice6c_spec.md` | Slice 6c — Rate card and FR effort days | 2026-10-11 |
| `docs/slice7_schema.md` | Slice 7 — project components, access, the one DFD | 2026-10-11 |
| `docs/slice8_schema.md` | Slice 8 — the baseline freeze | 2026-10-11 |
| `docs/briefs/slice9-ui-common.md` | Slice 9 (D-51) — screens to the mockups | 2026-10-11 |
| `docs/slice10b_schema.md · slice10b_spec.md` | Slice 10b — BR ↔ FR direct (D-52) | 2026-10-12 |
| `docs/slice10c_spec.md` | Slice 10c — Organisation and Systems up front, BR attributes, assigned-only projects | 2026-10-12 |
| `docs/slice10d_spec.md · slice10d_raci_schema.md` | Slice 10d — ranked process panel (D-63), one RACI per process (D-64) | 2026-10-13 |
| `docs/slice11_schema.md` | Slice 11 — structured BR, attribute usage, system-to-system flows (proposal) | 2026-10-12 |

---

## 5. Settled assumptions and removed history

What the clean spec dropped when it was rewritten on 2026-10-13: assumptions closed by a decision, and narrative that
explained how a rule came about.

**Assumptions closed by a decision** (dropped from spec §11): A-1, A-2, A-4, A-5 (S8-1), A-6, A-11, A-12, A-15
(naming final — no decision id; confirm), A-17, A-18, A-19, A-21, A-24, A-26 (D-52), A-28, A-29 (D-7), A-31, A-32,
A-34, A-35, A-37, A-41, A-45, A-46 (D-46), A-50, A-58 (S10b-1), A-62, A-67 (D-40). Their full text is in the spec as
it stood at commit `7a811ff` (`git show 7a811ff:docs/VB_design.md`, §11).

**Narrative removed from the spec body** (the decision itself is in §3; the old wording is at `7a811ff`):
- §2–§4: revision banners, "was OWNER", the edge-table rationale for process flow, the APP_ROLE row, "Ben's addendum".
- §5: `apple`'s 1:N argument for D-2, the D-7/D-28 override boxes, "three changes made by me", "added by Lilly/apple",
  "CASCADE was delta 1's choice", the superseded S2-1 paragraph, the APP_ROLE deletion, the CR_IMPACT story,
  the PostgreSQL generated-column FK fallback, the "Client Reviewer" rationale.
- §6–§7: first-draft and finding stories (the `/baselines/diff` leak, the "seeded five" race, the Starlette spool),
  the shadow-count history (17 → 30 → 25 built), `apple`'s schema offer, D-34 `suggested_br_id` (retired by D-52, never built).
- §8–§15: "Added by …" / "New in this revision" headings (retitled by topic; criterion numbers unchanged), round
  narratives, the APP_ROLE withdrawal.

**Criteria added on the rewrite:** 18a, 19a, 49c (from `slice7_schema.md` §8.8, accepted under S7-1) and 49b (slice7 §5.2).

**Stated as built, with no decision recorded:** §14.1 — the business function tree loads the whole set
(`GET /projects/{id}/bfc-tree`), not "lazy-loaded one level at a time" as first designed. §14.5 — the CSP is no longer
described as "tested by a criterion"; no criterion ever tested it.
