# Slice 1 — session "chart": the business function chart and business requirements

Read `docs/briefs/slice1-common.md` first. Workspace: `.worktrees/slice-1-chart`, API 8111, web 5181.

**You own:** `frontend/src/features/processes/**`, `frontend/src/features/requirements/**`,
`frontend/src/i18n/en.processes.json`, `frontend/src/i18n/en.requirements.json`.

## Processes → `ProcessesPage` (`/p/:projectId/processes`, `?node=<id>` selects a node)

Mockup: `01_bfc-hierarchy.png` / `01_BfcHierarchy.jsx`. Two panels.

**Hierarchy (left):** the tree from `bfcApi.tree` (flat list, ordered by `hier_code`; build the
tree from `parent_bfc_node_id`). Each row: level badge, `hier_code`, name; process nodes marked.
Filter by code or name. "Show retired" toggles `include_retired`. The selected node syncs with
`?node=`. Top-level action "Add level-1 function"; on a selected non-process node "Add child".
Reorder with up/down actions (or drag if easy) calling `bfcApi.reorder` with the new position —
codes are recomputed by the server; refresh the tree after.

**Node panel (right):** name, purpose; for a process, data-processing description. Save sends
`row_version`. Shows the code as read-only ("generated from the parent chain on save").
- **Process switch** (`bfcApi.markProcess`): allowed at levels 3–5; level 5 is always a process.
  A demote refused by the server shows its `detail` (it names the blockers). After promote, the
  panel shows the new requirement's number.
- **Requirement banner** for a process: its BR number and statement, and "Open requirement" →
  `links.requirement(p, brId)` (find the BR via `brApi.list` by `bfc_node_id`, or the tree's `br_number`).
- **Data in / Data out** chips (`bfcApi.stepData`), each `DE-#### name`, linking to
  `links.entity`. "Add entity" picks from `dataApi.list` and a direction. Removing one that a CRUD
  still needs is refused — show the server's `detail`.
- **External parties** list (`bfcApi.flows`): party, direction, optional entity, label. Add
  picks from `partyApi.list`; if no parties exist, link to `links.parties(p)`.
- **Roles (RACI) · one Accountable, one Responsible** (`bfcApi.roles`): each row an org role
  with an R/A/C/I toggle built from `useCodes(p, 'RACI_TYPE')` (labels from the codes, never
  hard-coded letters). "Add role" picks from `orgApi.roles`; if none exist, link to
  `links.organisation(p)`. A second Accountable/Responsible is refused by the server — show it.
- Retire / Restore the node (Restore only in "Show retired").

## Requirements → `RequirementsPage` (`/p/:projectId/requirements`) and `RequirementPage` (`…/:brId`)

**List:** DataGrid of `brApi.list`: BR number, the node's `hier_code` and name (from the tree),
statement (first line), status label. Row click → `links.requirement`. **No "add requirement"
button** — a requirement appears with its process step (D-2); say so in the empty state with a
link to Processes.

**Detail** (mockup `03_business-requirement.png`): header `BR-#### name` with the node's code
and a link back → `links.node(p, nodeId)`. Fields: statement, business logic, output
expectation, status. **Status offers only DRAFT and CONFIRMED**; BASELINED / SUPERSEDED are
shown read-only if present (S1-8, set by the freeze).
- **Data usage · CRUD** grid (`brApi.data`): one row per entity, C/R/U/D checkboxes, and a
  derived In/Out column from the returned `direction` (never sent). Ticking calls `linkData`,
  unticking `unlinkData`. "Add entity" picks from `dataApi.list`. Entity names link to `links.entity`.
  Note: ticking a CRUD also creates the step's data in/out on the server — invalidate the node.
- **Accountability (RACI)** (`brApi.roles`), the same R/A/C/I toggle; one Accountable.
- Retire / Restore.

## ui-verifier checks

1. Add a 3-level branch; the third node is a process; its requirement `BR-0001` appears.
2. Codes read 01 / 01.01 / 01.01.01; reorder two level-1 functions and every code below them changes.
3. Demote the process while its BR is live → the refusal names `BR-0001`.
4. Add data in and data out to the step; the chips link to the entity screen address.
5. Assign two roles; a second Accountable is refused with the holder named.
6. Open the requirement from the banner; edit and save; a stale save (two tabs) opens the ConflictDialog.
7. Tick R and U for an entity; the derived column shows In · Out; the step now shows that data.
8. Status offers Draft and Confirmed only.
9. Retire then restore a leaf node; retire a parent with children is refused with them named.
10. Light and dark both legible; no console errors.
