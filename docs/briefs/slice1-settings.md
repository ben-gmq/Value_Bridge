# Slice 1 — session "settings": client organisation and external parties

Read `docs/briefs/slice1-common.md` first. Workspace: `.worktrees/slice-1-settings`, API 8113, web 5183.

**You own:** `frontend/src/features/settings/OrganisationPage.jsx`,
`frontend/src/features/settings/PartiesPage.jsx`, new files under `frontend/src/features/settings/`
(not `SettingsPage.jsx`), and `frontend/src/i18n/en.settings.json` (keep the existing keys).
There is no mockup for these; use the scaffold's list and detail shells (§14.3).

## Client organisation → `OrganisationPage` (`/p/:projectId/settings/organisation`)

Two parts on one page.
- **Units tree** (`orgApi.units`, build the tree from `parent_org_unit_id`; up to 3 levels):
  code, name, level label (`useCodes(p, 'ORG_UNIT_LEVEL')`). Add a top unit or a child of the
  selected one: code, name, optional level (defaults from depth on the server), description.
  Edit with `row_version`. Retire (refused while it has live children or roles — show `detail`),
  "Show retired", Restore.
- **Roles** of the selected unit (`orgApi.roles`, filtered by `org_unit_id`) in a DataGrid:
  code, name, responsibility, headcount. Add / edit / retire / restore. A role may be moved to
  another unit by editing its unit. Codes are unique among live roles (the server refuses a duplicate).
- Say, in one line of help text, that these roles are what the chart and requirement screens
  assign as R/A/C/I.

## External parties → `PartiesPage` (`/p/:projectId/settings/parties`)

DataGrid of `partyApi.list`: EXT number, name, kind label (`useCodes(p, 'EXTERNAL_ENTITY_KIND')`,
optional), description. Add (number minted by the server) / edit / retire / restore. Retiring a
party still used by a process flow is refused — show the `detail`.

Both pages: a breadcrumb or back link to `links.settings(p)`.

## ui-verifier checks

1. Add Finance → Payables → AP clerks (3 levels); level labels read Department / Division / Section; a 4th level is refused.
2. Add two roles to Payables; a duplicate role code (any case) is refused.
3. Retire Payables while it has roles → refused, roles named. Retire the roles, then the unit; show retired; restore in order.
4. Add parties Bank and Customer: EXT-0001, EXT-0002; kind optional.
5. A stale save opens the ConflictDialog.
6. Light and dark both legible; no console errors.
