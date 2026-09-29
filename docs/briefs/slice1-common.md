# Slice 1 screens — rules for all three sessions

You are building **one** Slice 1 screen area of Value Bridge in parallel with two other
sessions. The backend, the page addresses and the API calls are finished and reviewed. Your
job is the React screens for your area and nothing else. Read `CLAUDE.md` first; it binds you.

## Your workspace (already set up — do not recreate)

| Session | Worktree / branch | Database | API port | Web port |
|---|---|---|---|---|
| chart | `.worktrees/slice-1-chart` · `slice-1-chart` | `vb_s1_chart_db` | 8111 | 5181 |
| data | `.worktrees/slice-1-data` · `slice-1-data` | `vb_s1_data_db` | 8112 | 5182 |
| settings | `.worktrees/slice-1-settings` · `slice-1-settings` | `vb_s1_settings_db` | 8113 | 5183 |

- The database is migrated to head and seeded. `backend/.env` points at it; `backend/venv` is a link.
- Run: `cd backend && ./venv/bin/uvicorn main:app --port <API> --reload` and
  `cd frontend && VB_API_PORT=<API> VB_WEB_PORT=<WEB> npm run dev`.
- First use: open `http://localhost:<WEB>/setup` and create a throwaway admin on `@fortience.com`,
  then a client and a project on the Admin page. Make up a local password; never write it in a report.
- **Stop your own servers by PID.** Never `pkill -f vite` or similar — other sessions' servers match.
- Do **not** run the backend test suite: it wipes your database. You should not be changing the backend.

## Files you own — and the ones you must not touch

You may create and edit only the files listed in your own brief, plus new files inside your
`features/<area>/` folder. **Everything else is shared and frozen for this slice**:
`app/App.jsx`, `app/links.js`, `components/*`, `api/scope.js`, `api/vb.js`, `i18n/en.json`,
another area's `en.<area>.json`, `theme/*`, `package.json`, and all of `backend/`.

If you need a change in a frozen file (a missing API field or route, a shared component, a new
package), **stop and say so in your hand-back** with the exact change. Do not work around it.

## Contracts to use

- **Page addresses:** `links.*` in `frontend/src/app/links.js`. Link to another area only through
  these (e.g. `links.requirement(p, brId)`, `links.entity(p, deId)`, `links.node(p, nodeId)`).
- **Query keys:** `keys.*` in the same file. Invalidate the other areas' keys you affect
  (e.g. after linking CRUD, invalidate `keys.entity` / the entity's used-by list).
- **API:** `frontend/src/api/scope.js` — `bfcApi`, `brApi`, `dataApi`, `partyApi`, `orgApi`.
  Backend reference: `backend/routers/scope.py` and `backend/schemas/scope.py` (read only).
- **Lookups:** `useCodes(projectId, CATEGORY)` from `app/useCodes.js`. Send codes, show labels.
- **Conflicts:** every edit sends `row_version`; a 409 opens `components/ConflictDialog.jsx`
  ("Reload and reapply", keeps what was typed). Read other 409s' `detail` and show it — the
  backend names the blocker ("Retire these first: …"). Disable submit while a request is in flight.
- **Look:** `components/Page.jsx` (`Page`, `WrapperBox`), MUI DataGrid for lists,
  `@mui/x-tree-view` `RichTreeView` (MIT) for trees. Colour only from `theme.vars.palette.*`.
- **Text:** every string through `t()` in your own `i18n/en.<area>.json`, keys prefixed by area.
- **Untrusted text renders as text** — no `dangerouslySetInnerHTML`, no Markdown. Long text
  uses `white-space: pre-wrap`.
- **Retired rows:** a DELETE is a soft retire. Offer "Show retired" and a Restore action where
  the entity is restorable (chart nodes, requirements, data entities, fields, parties, org units, roles).

## Design references

- Signed-off design: `docs/VB_design.md` §14 (frontend), §7.2–§7.4 (rules), §9 (routes),
  §1a S1-1…S1-9 (Slice 1 decisions).
- Mockups: `docs/mockups/screenshots/*.png` and `docs/mockups/src/screens/*.jsx`. **Use them for
  layout only.** The mockups show a left navigation rail; the app has the top bar — ignore the
  rail. **Do not build** mockup fields the data model lacks (S1-9): BR trigger, frequency,
  priority; DE owning area, master-candidate switch; the BFC "Current system (As-Is)" picker,
  solutions, issues, FR coverage, history and "changed since baseline" badges (later slices).

## Definition of done

1. `npm run lint` and `npm run build` pass.
2. `ui-verifier` passes the checks listed in your brief, in light and dark, with no console errors.
3. `sara` reviews your diff; fix every HIGH and MEDIUM, or say why not.
4. Commit on your branch (one or more commits, attribution lines per CLAUDE.md). **Do not merge,
   rebase or push.** Lilly merges the three branches into `slice-1-bfc`.
5. Hand back: what was built, the check results, anything you needed from a frozen file, and
   anything left undone — marked as undone.
