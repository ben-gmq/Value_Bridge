# Slice 10c: Organisation and Systems up front, plainer process panel, BR attributes, assigned-only projects

**Date:** 2026-10-12 · **Author:** Lilly · **Status:** rev 2 — design review round 1 applied (7 findings, 1 HIGH); 3 questions for Ben (§11)
**Builds on:** D-56, D-57, D-60(a), D-62 (§1a "Ben's UI feedback, evening — 2026-10-12"); D-40, OR-6, D-46, D-49,
D-51, D-53. **Waits on Slice 10b being merged** (it edits `BrEditor.jsx`, which 10b changed). Where this file and the
design disagree, the design wins.

## 1. Purpose
Ben could not find the organisation or the systems, could not parse the process panel's guidance, found the BR too
thin to see what data it touches, and expects a consultant to see only the projects they are assigned to. Every
item here is presentation over data that already exists, except D-62's default, which is a choice on a form.
**No migration, no new table, no schema change.**

## 2. Scope
**In:**
1. **D-56 menu.** Two rail items under *Scope*: **Organisation** (today `settings/organisation`) and **Systems**
   (today `settings/applications`, labelled "Applications"). Systems shows when APPLICATION is on, as now. The old
   Settings tabs redirect to the new addresses (`links.js`), so existing links keep working.
2. **D-56 performer.** The process panel **already edits** the performer and the time/event triggers
   (`PerformerPanel`, `TriggerPanel`, `NodePanel.jsx:240-245`) when the chart's DFD component is on; that stays as
   is. 10c makes it plain: the performer heads the panel as "Performed by …" ("Not assigned" when NULL). **When
   the DFD component is off**, the performer cannot be written today (`node_dfd_component` gate) — whether it should
   be is Q-1 for Ben; until answered, the section is hidden, as now.
3. **D-57 guidance.** `processes.stepFactsHelp` is rewritten in plain words, with two buttons: **Open a process
   below** (lists this function's processes) and **Make this a process**, which calls the existing
   `PATCH /bfc-nodes/{id}/process` **behind a new confirmation** saying what happens: a BR is created and numbered
   (never reused), the box can no longer hold sub-steps, undoing it means retiring that BR, and a process with no
   input/output blocks the next freeze (D-38). The button shows only where the switch is allowed (level ≥ 3, no
   children). Viewers see the text only.
4. **D-57 what starts it.** Beside the editable time/event triggers, a read-only line lists the process's
   other starts (D-49): its **input data entities** (`GET /bfc-nodes/{id}/data-entities`, direction IN) and
   **inbound flows from outside parties** (`/external-flows`), each labelled by kind. All three are existing
   VIEW-guarded routes; no new route. "Nothing starts this process" only when all three are empty.
5. **D-60(a) attributes.** In the BR's data-entity grid (`CrudGrid`), each linked entity expands to its live
   attributes: name, type, key, mandatory, in `seq_no` order. Read-only. Under `KEYS_ONLY` (D-39) only keys are
   expected, so an entity with no other attributes shows no warning there; under `FULL` it shows the same
   "keys only — no other attributes yet" hint the entity page uses. Empty → "No attributes recorded".
6. **D-62 assigned-only projects.**
   - The admin "New project" form preselects **"Assigned consultants only"** (`is_restricted = true`). The API
     still requires the choice explicitly (§8.10 risk 1), so nothing changes server-side.
   - Labels change from "Restricted" to **"Assigned consultants only"** / **"Open to all staff"**. On the home
     page the tag marks the *open* projects (the exception), not the restricted ones.
   - After a successful create, the admin lands on the new project's **Access** screen to add its members (a
     restricted project starts with none).
   - All wording follows: `en.json` (`home.kindNote.*`, `admin.makeUserBody`, `access.*`), `ProjectHome.jsx`,
     `AccessPage.jsx`; done-check: no i18n string still describes "every project except restricted ones".
   - **Existing projects — the one-off switch (DR10c-P1).** By an admin from each project's Access screen, using
     the existing restrict action. Its preview now **flags kept members whose level drops** (EDIT → VIEW, members
     copied from old grants at VIEW). An inventory of every live project is kept in §12 — switched, or left open
     on Ben's explicit say-so — and D-62 is done only when the admin's Home shows "Open to all staff" on nothing
     but those exceptions. **No script, no migration.**

**Out:** editing performer or triggers from the panel (stays in the DFD, one place); the BR picking attributes
(D-60b), structured BR lines (D-59), system-to-system flows (D-61) — slice 11, apple first; dashboards (D-58) —
slice 12.

## 3. Keystone grain
None new. Read-only views over `bfc_node` (performer), `bfc_node_trigger` / `process_trigger`, `br_data_entity` ⋈
`data_field`, `project.is_restricted`.

## 4. Business Requirement grid

| Function | Entity | Use | Logic → output |
|---|---|---|---|
| rail items | — | R | Organisation always; Systems when APPLICATION is on (`useComponents`) |
| performer on panel | `bfc_node` | R | VIEW. From the existing process read; link to the DFD step |
| triggers on panel | `bfc_node_trigger` | R | VIEW. From the existing step read used by the DFD; no new route if one already returns them, else one GET with `object_guard(BfcNode, VIEW)` |
| attributes on BR | `data_field` | R | VIEW. Existing entity-fields route per expanded entity (fetched on expand, cached by query key) |
| mark as process | `bfc_node` | U | EDIT. Existing route and refusals, unchanged |
| new project default | `project` | C | ADMIN. Form default only; body still carries `is_restricted` |

## 7. Function — where it lives
- `components/AppShell.jsx` (rail), `app/links.js` (addresses), `app/App.jsx` (routes, `NEEDS`, redirects of
  `settings/organisation`, `settings/applications` **and `settings/applications/:appId`**, keeping ids and query), `features/settings/*` (pages move,
  unchanged inside), `features/processes/NodePanel.jsx` (performer, triggers, guidance + buttons),
  `features/requirements/CrudGrid.jsx` (attribute expander), `features/admin/AdminPage.jsx` (default + labels),
  `features/projects/HomePage.jsx` (tag), i18n `en.json`, `en.processes.json`, `en.requirements.json`,
  `en.settings.json`, `en.json` (admin and access strings live there), `features/projects/ProjectHome.jsx`,
  `features/settings/AccessPage.jsx` (preview flag).
- Backend: none expected. If the panel needs triggers and no existing route returns them for one step, one GET is
  added with its guard, and the GET-leak test covers it.

## 8. Risk grade and test depth
**Grade 3 for 1–5** (presentation; wrong output is visible and harmless). **Grade 2 for 6** — a wrong default exposes
a client's project to every consultant, recoverable but acted on. Proof:
- pytest: only if a route is added (guard, 404 for a non-member of a restricted project).
- lint + build.
- ui-verifier: both rail items reach their pages, and old Settings links redirect; the panel shows the performer
  and triggers for a process with each, "Not assigned" for one without; the guidance buttons work on an L4; the
  attribute expander on a BR with a FULL entity and a KEYS_ONLY project; the new-project form defaults to
  "Assigned consultants only"; **a USER not assigned to a new project does not see it on the home page and gets
  "not found" on its address**; the restrict preview flags a member whose level drops; the old
  `settings/applications/:appId` link lands on the system; "Make this a process" shows its confirmation; a viewer
  sees no edit buttons; side-by-side with mockups 01 and 03. UAT on demo data restricts one project first
  (`seed_demo` creates open projects).
- **Deliberately uncovered:** phone width.

## 9. Acceptance
1. Organisation and Systems are one click from the left menu.
2. Every process shows who performs it and what starts it, without opening the DFD.
3. The guidance on a non-process box says what to do in plain words, and its buttons do it.
4. A BR shows the attributes of every data entity it touches.
5. A new project is visible only to admins and the consultants assigned to it, unless an admin opens it to all
   staff — and every existing project is either switched or on Ben's list of deliberate exceptions (§12).
6. "Make this a process" never fires without a confirmation that says what it creates.

## 10. Design review round 1 of 2 (design-auditor, 2026-10-12)

| Id | Rating | Finding | Disposition |
|---|---|---|---|
| DR10c-P1 | HIGH | D-62 covered only new projects; existing ones stay open with nothing tracking the switch | **Fixed** — inventory in §12, done = only Ben's exceptions open; acceptance 5 |
| DR10c-P2 | MED | "Make this a process" has no confirmation today; promoting mints a BR and is costly to undo | **Fixed** — new confirmation naming the consequences; button only where allowed; acceptance 6 |
| DR10c-D1 | MED | "What starts it" would show only time/event triggers, not input data or outside-party flows | **Fixed** — all three starts, each labelled, existing routes |
| DR10c-S1 | MED | The one-off restrict silently drops a kept member from EDIT to VIEW | **Fixed** — preview flags level drops; checklist step |
| DR10c-P3 | LOW | Restricted project created with no members, admin not sent to add any | **Fixed** — land on Access after create |
| DR10c-S2 | LOW | Wording outside the file list still says "every project except restricted" | **Fixed** — files added, grep done-check |
| DR10c-S3 | LOW | Redirects belong in `App.jsx`; Systems detail deep link missed | **Fixed** — `App.jsx`, `:appId`, `NEEDS` moved |
| — | fact | The panel **already** edits performer and triggers when DFD is on (spec rev 1 said otherwise) | Spec corrected (§2.2); Q-1 below |

## 11. Questions for Ben (recommendation first)
1. **Performer without the DFD.** Today a project with the DFD component off cannot record who performs a
   process. Ben asked that *each* process have its organisation in charge. **Rec:** allow the performer whatever
   the DFD setting (a small server change: the performer route gated by the BFC, not the DFD). Triggers stay
   with the DFD.
2. **Existing projects to leave open.** **Rec:** none — switch every live project, after its team is checked.
3. **Who switches them.** **Rec:** Lilly prepares the inventory with each project's members and levels; an admin
   (Ben) confirms each switch on its Access screen.

## 12. D-62 switch inventory
_Filled before 10c merges: project · members (level) · switched on / left open by Ben's say-so._
