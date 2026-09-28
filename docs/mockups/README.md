# Value Bridge — UI mockups (dark theme)

Ten form mockups as React + MUI components, with a clean 1440×900 PNG of each in
`screenshots/`. Dark mode first; light is not built yet.

| # | Screen | File |
|---|---|---|
| 1 | Business function chart — level 1–5 tree and node form | `src/screens/01_BfcHierarchy.jsx` |
| 2 | Data flow diagram — generated, editable | `src/screens/02_DfdEditor.jsx` |
| 3 | Business requirement | `src/screens/03_BusinessRequirement.jsx` |
| 4 | Data entity and fields | `src/screens/04_DataEntity.jsx` |
| 5 | Solution (5 categories) and solution mix | `src/screens/05_Solution.jsx` |
| 6 | Functional requirement — effort from the rate card | `src/screens/06_FunctionalRequirement.jsx` |
| 7 | Issue — raise and resolve | `src/screens/07_Issue.jsx` |
| 8 | Bulk import preview | `src/screens/08_ImportPreview.jsx` |
| 9 | Baseline freeze and priced diff | `src/screens/09_Baseline.jsx` |
| 10 | Project and access | `src/screens/10_ProjectAccess.jsx` |

## Run

```bash
npm install
npm run dev          # http://localhost:5190/?screen=1 … ?screen=10
```

## Colour

All colour comes from `src/tokens.js` (`BRAND`, `SURFACE`, `STATUS_COLOR_MAP`), fed into
the MUI theme in `src/App.jsx`. Three colours on tinted dark neutrals:

- **FTC Dark Purple `#2B245C`** — the "Dark 2" colour of the Fortience deck theme
  (`Inbox/Reference/Fortience_PPT_16_9_KeyVisual_EN.pptx`). Navigation rail and
  highlight panels. Its brighter partner `#7848DC` (deck accent 4) marks selection,
  focus and business-function levels 1–5.
- **Navy `#4A73A8`** — primary actions and data.
- **Teal `#2A9BB0`** (from deck accent 6 `#02788E`) — data entities and DFD data stores.
- Status is semantic and separate: green, amber `#FBAE40` (deck highlight), red.

Radii: cards 24 · diagram boxes 18 · fields 14 · buttons pill.

Tokens sit in `tokens.js` rather than at the top of `App.jsx` (FTC scaffold §5) so the
screens can import them without a circular import.

All names, figures and organisations are illustrative.
