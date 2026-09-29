# Slice 1 — session "data": data entities and their fields

Read `docs/briefs/slice1-common.md` first. Workspace: `.worktrees/slice-1-data`, API 8112, web 5182.

**You own:** `frontend/src/features/data/**`, `frontend/src/i18n/en.data.json`.

## Data → `DataEntitiesPage` (`/p/:projectId/data`) and `DataEntityPage` (`…/:deId`)

**List:** DataGrid of `dataApi.list`: DE number, name, description (first line). "Add entity"
(name, description, business owner note) → `dataApi.create`; the number is minted by the
server. Row click → `links.entity`. "Show retired" with Restore.

**Detail** (mockup `04_data-entity.png` / `04_DataEntity.jsx`): header `DE-#### name`. Editable
name, description, business-owner note (save with `row_version`).
- **Fields** table (`dataApi.fields`), in `seq_no` order: name, data type
  (`useCodes(p, 'FIELD_DATA_TYPE')`, optional — D-26), length / precision / scale, required
  (three states: yes / no / unknown → `is_mandatory` true / false / null), PK with its position
  (`pk_ordinal`), foreign key → target entity (and optionally its field). "Add field".
  - Foreign keys: pick the target entity from `dataApi.list` and optionally one of its fields
    (`dataApi.fields`). Send `fk_group: "new"` for a new relationship, or an existing
    `fk_group_no` of the same target to extend a composite key. Show `fk_group_no` read-only.
    The number is assigned by the server (S1-7) — never type it.
  - Retire / restore a field. A field another field references is refused — show the `detail`.
- **Used by requirements** panel (`dataApi.usedBy`): BR number, node code and name, CRUD letters;
  each links to `links.requirement(p, brId)`.
- A small **model checks** panel computed in the browser from the loaded fields only: "no
  primary key", "foreign key without a target field". (The full entity-model report is a
  later slice; keep this to these two.)
- Retire / restore the entity. Retiring one with live fields or requirement links is refused and
  the server names them.

## ui-verifier checks

1. Create two entities; numbers are DE-0001, DE-0002.
2. Add fields to DE-0001: a PK (position 1), a date, a string with length; required tri-state works.
3. On DE-0002 add two foreign keys to DE-0001 with "new": their relationship numbers are 1 and 2.
4. A field name duplicated in the same entity (ignoring case/spaces) is refused.
5. Retire a field and restore it; retire an entity with fields is refused with them named.
6. The used-by panel lists a requirement after one is linked (create one via Processes if needed,
   or seed through the API) and links to its address.
7. A stale save opens the ConflictDialog.
8. Light and dark both legible; no console errors.
