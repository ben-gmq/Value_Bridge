# Slice 9 (D-51) — screens to the mockups: rules for every screen session

Ben found the built screens far from the mockups. **D-51** (VB_design §1a) makes the ten mockups in
`docs/mockups/` the visual reference. The foundation is done on branch `slice-9-ui`: dark-first theme
(`frontend/src/theme/`), the left-rail shell with breadcrumbs and version chip (`components/AppShell.jsx`),
the page header (`components/Page.jsx`) and **the kit** (`components/kit.jsx`). Your job: rework **your
screen area only** so it looks and lays out like its mockup. Presentation only.

## Read first
1. `CLAUDE.md` (binding), then the D-51 row in `docs/VB_design.md` §1a.
2. Your mockup(s): source `docs/mockups/src/screens/NN_*.jsx` and picture `docs/mockups/screenshots/NN_*.png`
   (open the PNG with the Read tool — look at it). The mockup kit is `docs/mockups/src/kit.jsx`.
3. Our kit `frontend/src/components/kit.jsx`: `Card`, `SectionLabel`, `Code` + `codeTone`, `Status`, `Tag`,
   `LevelBadge`, `KV`, `Segmented`, `PurpleTile`, `Tile`, `ListRow`, `MonoChip`. Use these; they are the
   mockup primitives on theme tokens. `Page` takes `eyebrow` and `crumb` (the item's code for the header breadcrumb).

## What "done" looks like
- The screen's **structure follows the mockup**: the same cards and side panels, the same order, title with
  eyebrow (level badge + hierarchy code where the mockup has one), coloured codes (BR purple, FR/SOL navy,
  DE teal, hierarchy muted mono), tags/status pills instead of plain chips, small-caps section labels, the
  RACI pill toggle where the mockup shows one, the purple highlight panel for the screen's key figure.
- **Every existing behaviour still works**: same queries, mutations, dialogs, conflict handling, `useCanEdit`
  hiding, component gating, routes and links. You are re-laying-out, not re-writing logic. If a component
  is long, restructure its JSX; do not change what it sends to the API.
- **Nothing is faked** (D-51). A mockup element with no data or feature behind it today (issues, history,
  search, trigger / frequency / priority on a BR, "Saved · v7" if the API gives no version, etc.) is **left
  out**, not drawn with invented values. Where the data exists (row_version, numbers, links), show it.
- Works at 1440 and 1280 wide, and at 400 wide nothing pushes the page sideways (tables scroll inside their card).
- Both colour schemes: dark is default; use theme tokens only (`th.vars.palette.*`, `brand.*`, `status.*`).

## Hard rules
- **Files you may edit:** only those your brief lists, plus new files inside your `features/<area>/`
  folder, plus your own `i18n/en.<area>.json`. **Frozen:** `theme/*`, `components/*` (AppShell, Page,
  kit, …), `app/*`, `api/*`, `i18n/en.json`, other areas' files, `backend/`, `package.json`. If you truly
  need a new primitive, write it in your feature folder and say so in your report.
- **No hex colours, no `dangerouslySetInnerHTML`, all UI text through `t()`** with keys prefixed by your area.
- Do **not** start servers or use the browser tools (one shared browser; the lead verifies). Do not run the
  backend tests.
- Check: `cd frontend && npm run lint && npm run build` must both pass.
- Commit on your branch (one or a few commits), message starting `Slice 9 <area>:`, ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Do not merge, push or rebase.

## Report back (short)
What each screen now looks like versus its mockup, every mockup element you left out and why (no data /
not built), any primitive you added, and the lint/build result.
