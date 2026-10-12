# Slice 10c: Organisation and Systems up front, plainer process panel, BR attributes, assigned-only projects

**Date:** 2026-10-12 · **Author:** Lilly · **Status:** rev 1 — draft, design review round 1 pending
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
2. **D-56 performer.** The process panel (function chart) shows the process's **performer** — department,
   position, system or AI (D-46) — read-only, with "Edit in the DFD" linking to the step on its DFD, where it is
   edited today. "Not assigned" when NULL.
3. **D-57 guidance.** `processes.stepFactsHelp` is rewritten in plain words, with two buttons: **Open a process
   below** (lists this function's processes) and **Make this a process** (the existing mark-as-process action,
   with its existing confirmation and refusals). Viewers see the text only.
4. **D-57 triggers.** The process panel lists the process's triggers (D-49: time, event, data, outside party),
   read-only, with "Edit in the DFD".
5. **D-60(a) attributes.** In the BR's data-entity grid (`CrudGrid`), each linked entity expands to its live
   attributes: name, type, key, mandatory, in `seq_no` order. Read-only. Under `KEYS_ONLY` (D-39) only keys are
   expected, so an entity with no other attributes shows no warning there. Empty → "No attributes recorded".
6. **D-62 assigned-only projects.**
   - The admin "New project" form preselects **"Assigned consultants only"** (`is_restricted = true`). The API
     still requires the choice explicitly (§8.10 risk 1), so nothing changes server-side.
   - Labels change from "Restricted" to **"Assigned consultants only"** / **"Open to all staff"**. On the home
     page the tag marks the *open* projects (the exception), not the restricted ones.
   - The one-off switch of existing projects is done by an admin from each project's Access screen, using the
     existing restrict action with its "who loses access" preview. **No script, no migration.**

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
- `components/AppShell.jsx` (rail), `app/links.js` (addresses + redirects), `features/settings/*` (pages move,
  unchanged inside), `features/processes/NodePanel.jsx` (performer, triggers, guidance + buttons),
  `features/requirements/CrudGrid.jsx` (attribute expander), `features/admin/AdminPage.jsx` (default + labels),
  `features/projects/HomePage.jsx` (tag), i18n `en.json`, `en.processes.json`, `en.requirements.json`,
  `en.settings.json`, `en.admin.json`.
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
  "not found" on its address**; a viewer sees no edit buttons; side-by-side with mockups 01 and 03.
- **Deliberately uncovered:** phone width.

## 9. Acceptance
1. Organisation and Systems are one click from the left menu.
2. Every process shows who performs it and what starts it, without opening the DFD.
3. The guidance on a non-process box says what to do in plain words, and its buttons do it.
4. A BR shows the attributes of every data entity it touches.
5. A new project is visible only to admins and the consultants assigned to it, unless an admin opens it to all
   staff.

## 10. Design review round 1 of 2
_Pending._
