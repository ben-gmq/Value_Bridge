# Value Bridge — BUGLOG

**Id prefix:** `VB-###` · **Next id:** VB-014 *(derive it, never trust this line — see the
`buglog` skill Step 0b)*
**Open: VB-006, VB-008 and VB-005 (the standing backlog); VB-007, VB-009 and VB-010 closed 2026-10-17 · 44 unworked lines in VB-005 (8 more fixed, awaiting Ben's close) — measured 2026-10-09.**
**Archives:** none yet.

**Status of the app:** design signed off 2026-09-28; foundation, Slice 1 (chart, requirements,
data, settings) and Slice 2a (process flow edges) built — migrations 0001–0018.
The design spec is `docs/VB_design.md`; the originating brief is `docs/ASSESSMENT_BRIEF.md`.

**Why this file has four closed entries and no open ones.** VB-001…VB-004 were never code
defects — there is no code. They were three design-review findings that could not be closed
in the spec on 2026-09-17, plus the standing backlog stub. All three were settled on
2026-09-24 and folded into `docs/VB_design.md`. An open design question belongs in that
document's §11 Assumptions, not in a defect log; these should have gone there in the first
place.

**Section map:** `## Open` · `## Closed` · `## Standing backlog` (VB-005; VB-004 closed unused).

---

## Open

### VB-011 | The web app loads the owner database login, so a compromised app process defeats every database guard | OPEN
- **Found:** 2026-10-21, design review of slice 17 (design-auditor S2, HIGH). Predates slices 16–17; both depend on it.
- **What:** `backend/config.py` makes `migration_database_url` (vb_owner) a required setting of the running web
  server. Any read of the server's environment (a path bug, a settings dump, code execution, a bad dependency) gives
  the owner login, which can drop the purge and admin-grant triggers or take the owner-only paths (LEGACY grants,
  purge execution).
- **Fix:** split the settings — the web server loads only `DATABASE_URL` (vb_app); alembic and the owner scripts read
  `MIGRATION_DATABASE_URL` themselves. Before the first non-local deploy (Azure, D-35).
- **Severity:** HIGH, not reachable today (local only, no real data).
- **Ben, 2026-10-21:** accepted until the first non-local deploy; stays HIGH and is a **hard blocker** for that deploy
  (history, slice 17 rulings; design §15.2).

### VB-012 | Nobody sees the weekly admin-check lines: no route and no card yet | OPEN — FIXED, awaiting Ben's close
- **FIXED 2026-10-23, slice 16 weekly check:** `GET /admin/weekly-check` (platform admin) serves the lines with the
  check's last run; the Weekly archive check card on the Removals tab shows them; `scripts.weekly_check` prints them
  and records each run (audit `WEEKLY_CHECK_RAN`). Tests: `tests/test_weekly_check.py`.
- **Found:** 2026-10-23, `sara` slice 17 review (M-2, deviation 4).
- **What:** `services/admin_grant.weekly_admin_lines` reports open requests over 7 days, recent approvals, live admins
  below two, admins with no grant record (the only standing view of the admins 0076's backfill skipped), owner grants,
  LEGACY rows with no asker, removals and deactivations — all tested — but no route serves it and no screen shows it.
  The design puts it on the Removals tab beside slice 16's weekly check (AR-23), which is not built.
- **Fix:** with slice 16's weekly check: a platform-admin route and the card on the Removals tab, plus the operator's
  run log line.
- **Severity:** MEDIUM, not reachable today (local only, no real data). **Gate:** before the first non-local deploy,
  beside VB-011.

### VB-013 | The flow import's AI safety rules must reach the consultant even where the prompt pack is withheld | OPEN
- **type:** ENHANCEMENT (design) · **found:** 2026-10-28, design review of slice 1e-b, round 2 (design-auditor N1,
  MEDIUM) · **depends-on:** —
- **What:** the 1e-b spec withheld the AI prompt pack until the vendor's data terms were recorded, and the pack is
  what carries the rules "Claude Enterprise under FTC's account only" and "remove personal data first". Withholding
  it would also have withheld those rules, leaving a consultant to try an AI with no guidance.
- **Fix (piece a):** the import dialog and the schema download state "no client content into any AI except Claude
  Enterprise under FTC's account; remove personal data first"; the pack asset is committed only together with the
  spec §1a terms row. FI-10 (Ben, 2026-10-28) recorded the Claude Enterprise terms, so the pack ships in piece (a)
  naming that one service; the warning stays for any other.
- **Severity:** MEDIUM, not reachable today (local only, no real data; nothing of 1e-b is built). Closes with piece (a).

### VB-006 | App shell overflows horizontally on a phone; top nav clips below ~930px | OPEN — FIXED, awaiting Ben's close

- **type:** BUG · **found:** 2026-09-30 by `ui-verifier` (Slice 2a UAT, process chart) · **depends-on:** —
- **FIXED 2026-10-11, slice 9 (D-51):** the top bar is gone; the shell is the left rail, which becomes a
  drawer behind a menu button below 900px. ui-verifier S9 check 14: at 400px the drawer opens and the BR page
  has no page-level sideways scroll; at 945px the chart stacks (Evidence/2026-10-11/slice-9/).
- At 390px wide the page renders 477px wide: the top bar's user menu is cut off at the right
  and the footer text overflows. At ~930px the nav shows "BR–FR map" as "BR" and hides
  Interfaces and Data. The step panel content itself fits. Not caused by Slice 2; likely
  the shell (`frontend/src/components/AppShell.jsx`, cf. commit 07c6fbe "nav scrolls instead
  of squashing"). Evidence: `.playwright-mcp/page-2026-09-30T02-20-08-918Z.png`.
- **root cause:** not yet investigated · **files:** `frontend/src/components/AppShell.jsx` (suspected)

### VB-008 | The data entity page shows edit controls to reviewers | CLOSED

- **type:** BUG (presentation) · **found:** 2026-10-09 by `sara` (Slice 4a-2 review, M-3) · **depends-on:** —
- `DataEntityPage.jsx` shows Edit/Retire/Restore, Retire entity, Add field and the snackbar Restore
  to a REVIEWER; `DataEntitiesPage.jsx` shows Restore on retired rows. The server guards refuse
  every one (403), so nothing is breached. Predates Slice 4a.
- **root cause:** those controls never went through `useCanEdit` (CLAUDE.md "Edit controls").
  · **files:** `frontend/src/features/data/DataEntityPage.jsx`, `DataEntitiesPage.jsx`
- **closed:** 2026-10-11, slice 7b. Every control on both pages goes through `useCanEdit`, which now reads
  the project's `my_access_level`. Found again by `ui-verifier` (7b UAT check 1) together with the same
  gap on the BR page, Client organisation and External parties — all fixed in the same commit.

---

## Closed

### VB-001 | `.xlsx` parser hardening unspecified — no library, size cap, expansion cap or row ceiling | CLOSED

- **type:** BUG (design gap) · **raised:** 2026-09-17, `design-auditor` review, MEDIUM (S6)
- **root cause:** The spec set a 5,000-row cap as a business rule checked *after* parsing,
  and named no parser. An `.xlsx` is a zip of XML: one stray formatted cell near row
  1,048,576 makes a non-streaming parser materialise a million rows and exhaust the worker,
  and a crafted archive does it deliberately at a fraction of the size.
- **resolution — 2026-09-24:** Specified in `docs/VB_design.md` §7.12: `openpyxl` in
  `read_only=True` streaming mode, 10 MB wire cap checked before reading a byte, 100 MB
  decompressed cap counted as zip members are read, 5,000 row / 200 column ceilings enforced
  mid-stream, and `defusedxml` required so entity expansion and external-entity resolution
  are neutralised. **Acceptance criterion 75** feeds a workbook containing an external
  entity declaration and asserts it is rejected rather than resolved.
- **files:** `docs/VB_design.md` §7.12, A-32, criterion 75

### VB-002 | Baseline freeze unbounded, may exceed a synchronous request | CLOSED

- **type:** BUG (design gap) · **raised:** 2026-09-17, `design-auditor` review, MEDIUM (P8)
- **root cause:** §7.7 read "the whole live set" across 24 tables with no stated bound, while
  acceptance criterion 13 sized it at 40 BFC nodes. A real enterprise chart is orders of
  magnitude larger, and the proxy timeout plus a browser retry lands straight in the
  double-commit and isolation failures fixed elsewhere in the same review.
- **resolution — 2026-09-24:** Converted to a **stated design bound** rather than an open
  defect. A-35 now designs the freeze for up to 2,000 level-5 nodes (~50,000 rows across the
  24 frozen tables) and **acceptance criterion 76** tests it at that bound inside the
  request timeout. **The number is Lilly's, not Ben's** — it is tagged `⚠` in §11 and is one
  of the two open questions in the spec. If a real engagement is materially larger the
  freeze becomes `202 Accepted` + a status endpoint, which is a build-shape decision taken
  before build, not a defect found after it.
- **files:** `docs/VB_design.md` A-35, A-43, criterion 76

### VB-003 | Four areas not reviewable — frontend, uploaded-file lifecycle, deployment/secrets, backups | CLOSED

- **type:** ENH (review coverage) · **raised:** 2026-09-17, `design-auditor` COULD NOT REVIEW
- **root cause:** Genuinely absent from the design rather than wrong in it, so the auditor
  could assess none of the four.
- **resolution — 2026-09-24:** Split. **The uploaded-file lifecycle is now specified** in
  §7.11 — the `.xlsx` is never written to disk, only `IMPORT_ROW.payload` persists, and
  `file_name` is display-only and never used to build a path or a `Content-Disposition`
  header, which removes file storage from the attack surface rather than securing it. The
  **parser configuration** went to VB-001. The remaining three — frontend design, deployment
  and secret handling, backup and restore — are now **§12.3 "Designed separately, before the
  area is built"**, each with the gate at which it must be designed. Backup/restore is called
  out as a control, not an ops detail: it is the only reversal mechanism for a wrongly-frozen
  baseline.
- **files:** `docs/VB_design.md` §7.11, §12.3

### VB-004 | Standing review backlog — LOW-rated findings | CLOSED (empty, never used)

- **type:** register stub · **opened:** 2026-09-17 per the `buglog` skill Step 0c
- **resolution — 2026-09-24:** Closed unused. The four LOW findings from the 2026-09-17
  review (P10 duplicate creates surfacing as 500s; D13 `SOL` missing from the seeded
  sequence series; S10 `GET /code-master/{category}` unscoped; S11 the application DB role
  holding `UPDATE`/`DELETE` on `baseline_*`) were all **fixed in the spec rather than
  deferred**, so no line ever entered this entry. Recorded so a future reader does not
  conclude the LOWs were dropped.
- **Re-open the standing backlog with a new id** when the first LOW-rated finding is
  genuinely deferred. Per the skill, ids are permanent and VB-004 is not reused.

### VB-007 | Import wizard's "Do fields later" gate can be left with the browser Back button | CLOSED

- **type:** BUG · **found:** 2026-10-09 by `sara` (Slice 4a-2 pre-merge review, M-2) · **depends-on:** —
- 4a-R10 says that after the entities step commits, the wizard can be left only through "Do fields
  later". `beforeunload` covers reload and tab close, and the dialog blocks Esc and backdrop, but
  browser Back unmounts the page with no prompt, so a half-built model can be left silently. The
  "No fields yet" marker and `entities_without_fields` still show it afterwards.
- **root cause:** `useBlocker` needs a data router; `frontend/src/main.jsx` uses `<BrowserRouter>`.
  Fix by moving to `createBrowserRouter` (a routing change across the app) or a popstate guard in
  `ImportWizard.jsx`. · **files:** `frontend/src/main.jsx`, `frontend/src/components/ImportWizard.jsx`
- **2026-10-17:** a popstate guard in the wizard alone does not work: Chrome runs a window's popstate listeners in
  the order they were added, capture or not, and BrowserRouter adds its own at mount, so the router moves first
  (seen in headless Chrome). Same cause as VB-010.
- **closed:** 2026-10-17, branch `fix/vb-007-009` (Ben: option (a), one shared guard). `app/backGuard.js` adds the
  one popstate listener when it loads (`main.jsx` imports it before render); a screen registers with
  `useBackGuard`. After step 1 commits, Back keeps the wizard open and asks "Leave without the fields?" (Stay and
  finish / Do fields later). Headless Chrome, 6 of 6 checks: Evidence/2026-10-17/vb-007/.
  · **files:** `frontend/src/app/backGuard.js`, `frontend/src/main.jsx`, `frontend/src/components/ImportWizard.jsx`

### VB-010 | The Processes page's unsaved-changes prompt on browser Back appears after the edit is already lost | CLOSED

- **type:** BUG · **found:** 2026-10-17 by Lilly (VB-007 browser check, same cause) · **depends-on:** —
- With an unsaved change in the node panel, browser Back showed "Save your changes first?", but behind it the router
  had already moved: the panel had closed and the edit was gone, while the address bar was put back on the node.
  "Save and continue" then had nothing to save. Reproduced on `main` in headless Chrome:
  Evidence/2026-10-17/vb-010/10-main-before-fix-edit-lost.png.
- **root cause:** the sara L5 popstate guard in `ProcessesPage.jsx` was a capture listener added by the page, so it
  ran after BrowserRouter's (see VB-007); it stopped nothing.
- **closed:** 2026-10-17, branch `fix/vb-007-009`, with VB-007: the page uses `useBackGuard`. Back keeps the panel and
  the edit; Keep editing stays; Discard and continue goes where Back was heading, nothing saved (headless Chrome, 4 of
  4 checks, database row unchanged: Evidence/2026-10-17/vb-010/).
  · **files:** `frontend/src/features/processes/ProcessesPage.jsx`, `frontend/src/app/backGuard.js`

### VB-009 | A BR→data-entity link may land under an entity retired at the same instant (suspected) | CLOSED

- **type:** BUG (concurrency, unverified) · **found:** 2026-10-09 by `design-auditor` (Slice 5 design review round 1, side note to DR1-D1, MEDIUM) · **depends-on:** —
- `business_requirement.link_data_entity` checks the entity through `step_io.live_entity`, a plain
  `db.get` with no lock. A data-entity retire that commits between that read and the link's INSERT
  would leave a live `br_data_entity` under a retired entity; the INSERT's FK check still passes.
- **To confirm:** two sessions — hold a DataEntity retire open between its lock and its commit
  while a link runs. Slice 5 adopts the locked form for `br_solution`, so the fix is the same
  `lock_for_share` before the liveness check. · **files:** `backend/services/step_io.py:16-20`,
  `backend/services/business_requirement.py`
- **2026-10-16 (slice 11b, `sara` M1):** the CRUD grid save (`business_requirement.save_grid` → `_link` →
  `step_io.ensure_step_io` → `live_entity`) reaches the same unlocked entity check. Its attribute half was fixed in
  11b (each newly ticked field is locked FOR SHARE first; `test_br_attributes` proves the race); the entity half
  waits for this entry's fix in `step_io.live_entity`, which covers both paths.
- **root cause:** confirmed — `live_entity` checked `is_active` on an unlocked read.
- **closed:** 2026-10-17, branch `fix/vb-007-009`. `step_io.live_entity` takes the entity FOR SHARE before the
  check, which covers the BR link, the grid save, the step I/O editor and hand-off. `sara` H-1 on the fix: the grid
  save then locked a field before its entity, the reverse of the field writers (`data_entity._lock_entity`), a
  deadlock; `save_grid` now locks the newly ticked entities first, in id order. Tests in `test_br_attributes.py`:
  a link waiting on a retire is refused (red without the fix), the grid save leaves the field free while it waits
  on the entity (red without the H-1 change), and a retire waiting on a link is refused (an order guard; the FK's
  KEY SHARE holds it too).

---

## Standing backlog

### VB-005 | Standing review backlog — LOW-rated findings deferred from design review round 2 | OPEN

- **type:** register · **opened:** 2026-09-28 per the `buglog` skill Step 0c, replacing VB-004
- **Repaid at the gate:** worked through with Ben line by line before the first client
  engagement (spec §12.3, §15.3 restore drill).
- R2-S11 · `design-auditor`, round 2, 2026-09-28 · LOW, conditional · **If Entra ID single
  sign-on is adopted** (D-35, spec §15.4): reject `userType = Guest` (client staff invited to
  FTC's Teams would pass sign-in and break D-11), keep `create_user` the only way an account
  is made (no just-in-time creation), and revisit JWT storage (§14.5). Moot while auth stays
  JWT; escalates to its own id the day SSO is chosen.
- sara LOW-3 · `sara`, slice-2-flow pre-merge review, 2026-09-30 · LOW · **The step panel shows
  add / edit / remove to REVIEWERs**: `StepData`, `RaciPanel` and `StepSequence` hide their
  controls only when the node is retired, so a reviewer clicks and gets a 403. Fix once across
  the panel from the user's project role, not per section. The server refuses correctly; this
  is presentation only. **FIXED 2026-09-30, Slice 3 piece 0 (`useCanEdit`, `pushClear`, `LabelledEdge`); ui-verifier 6/6 — awaiting Ben's close.**
- sara L5 · `sara`, slice-2-canvas pre-merge review, 2026-09-30 · LOW · **The flow canvas lets a
  REVIEWER drag, draw a flow and press Reset**, each ending in a 403 alert. Same root as sara
  LOW-3 above — fix both with one project-role hook. **FIXED 2026-09-30, Slice 3 piece 0 (`useCanEdit`, `pushClear`, `LabelledEdge`); ui-verifier 6/6 — awaiting Ben's close.**
- sara L7 · `sara`, slice-2-canvas, 2026-09-30 · LOW · **Pinned boxes can overlap auto-placed
  ones**: §14.6 says overlapping unpinned cards are pushed clear on auto-arrange; the flow canvas
  lets a saved position win over ELK without pushing. **Owed to the shared canvas before the ERD
  (Slice 3)**, where 200-entity diagrams make it visible. **FIXED 2026-09-30, Slice 3 piece 0 (`useCanEdit`, `pushClear`, `LabelledEdge`); ui-verifier 6/6 — awaiting Ben's close.**
- sara L8 · `sara`, slice-2-canvas, 2026-09-30 · LOW · **Edge condition labels stay visible in the
  low-zoom view** (below 0.45 box text hides, edge labels do not). A custom edge reading the zoom. **FIXED 2026-09-30, Slice 3 piece 0 (`useCanEdit`, `pushClear`, `LabelledEdge`); ui-verifier 6/6 — awaiting Ben's close.**
- Q5 · `design-auditor`, Slice 3 spec round 1, 2026-09-30 · policy question · **Mermaid export
  moves client names out of VB.** A consultant pasting DE, field and step names into an outside
  renderer (mermaid.live puts the whole diagram in its share URL) sends client content to a
  third party, and no export is audited. Ben to decide before first client use: a stated rule
  for consultants (FTC-approved tools only, cf. D-36), an audited export, or both.
- R2-NEW-1 · `design-auditor`, Slice 3 spec round 2, 2026-09-30 · LOW · **ERD expand cannot be
  saved**: if a stored `collapsed=false` means "default by size", a large card re-collapses on
  reload. Build rule: no row = default by size; a stored row's flag is honoured. Settle in 3b.
- R2-NEW-2 · same review · LOW · **ERD stub edges to ghost boxes** would target a row handle the
  ghost does not draw and be dropped. Build rule: stubs always land on `t-L-entity`. Settle in 3b.
- R2-NEW-3 · same review · LOW · **A PK-and-FK field in `erDiagram`** needs Mermaid's `PK, FK`
  list form, or the paste fails / the FK is lost. Settle in 3c (criterion 20a gets an
  identifying field).
- sara M1 · `sara`, Slice 3 piece 0 pre-commit review, 2026-09-30 · MEDIUM · **Platform-admin
  creation exists in three hand-written copies** (`seeds/create_admin.py`, `services/auth_service.py`
  first-run setup, `seeds/seed_demo.py`): a new password or domain rule added to one misses the
  others. One `user_admin.create_platform_admin(...)` running `check_ftc_address`, `MIN_PASSWORD`
  and the audit event, called by all three. The seed already checks the domain (its missing D-11
  check is fixed).
- sara M1 · `sara`, slice-3-dfd pre-merge review, 2026-09-30 · MEDIUM · **Layout-save logic is
  copied** between `FlowPage` and `DfdPage` (pendingSave, debounce, flush, save-on-leave, reset),
  and the copies already differ; the ERD would be a third. One `useLayoutPersistence` hook in
  `frontend/src/canvas/`. **Scheduled: on main straight after slice-3-erd merges.** **FIXED 2026-09-30 (`useLayoutSave`, one copy for flow/DFD/ERD; ui-verifier 7/7) — awaiting Ben's close.**
- sara M2 · same review · MEDIUM · **The header's "DFD" nav item still opens the "coming later"
  placeholder** (`App.jsx` SECTIONS, `AppShell.jsx` nav), while the real DFD lives under a chart
  node. Ben to choose: drop the nav item, or point it at the chart with a "pick a node" hint. **FIXED 2026-09-30 (Ben chose (b): the chart with a "pick a branch" hint) — awaiting Ben's close.**
- sara L1 · same review · LOW · The spec says "Auto-arrange and Reset"; the diagrams have only
  Reset (which re-arranges). Ben to say whether Reset is the auto-arrange; then fix the spec wording.
- sara L3 · same review · LOW · A drag within 600 ms before Reset can land after the reset and pin
  the box again (flow and DFD). Flush-and-discard on reset — folds into the M1 hook. **FIXED 2026-09-30 (`useLayoutSave`, one copy for flow/DFD/ERD; ui-verifier 7/7) — awaiting Ben's close.**
- sara L1 · `sara`, slice-3-erd pre-merge review, 2026-09-30 · LOW · **No test pins the ERD query
  count** (fixed today, ~8 statements at any size). One statement-counting test so a later lazy
  load cannot quietly make the 200-entity diagram slow.
- UAT B · `ui-verifier`, Slice 3 UAT, 2026-09-30 · LOW · **Slow first paint on DFD and ERD**:
  5–8 s of an empty canvas (ELK in the worker), with the ERD area picker showing a raw id until
  the chart tree loads. A loading state at least; profile ELK at 200 entities.
- UAT C · same · LOW · **Parallel lines overlap**: two relationships to one parent (ERD ship_to /
  bill_to) or two flows between one pair of boxes (DFD) share a route and their labels stack.
  Lines also run behind other boxes (smoothstep, not ELK's routes) — flow canvas too.
- UAT D · same · LOW · **An expanded ERD card can overlap its neighbours**: expanding grows the
  card without pushing others clear. Re-run `pushClear` on a collapse change.
- UAT E · same · LOW · **At 390 px the minimap covers much of the ERD canvas** — hide it below a
  breakpoint (with VB-006, the shell overflow).
- ERD staleness · slice-3-erd builder, 2026-09-30 · LOW · **Editing a step's data does not refresh
  an open ERD** until the 30 s staleTime passes: step I/O edits refresh `flows(p)`, not
  `entities(p)`. Invalidate both from the step sections.
- sara L3 · `sara`, slice-3-mermaid pre-merge review, 2026-09-30 · LOW · **Invisible format
  characters survive the Mermaid escape** (Unicode Cf: right-to-left override U+202E, zero-width
  space, BOM). No parser break-out, but a pasted label can read differently from what it says.
  Mapping Cf too is a spec change to §7 3c — Ben to approve (5 min + tests). **FIXED 2026-09-30 (Ben: strip them; Cf removed in escape_mermaid, tested) — awaiting Ben's close.**
- UAT loose end · slice-3-mermaid builder, 2026-09-30 · LOW · The builder checked the exports
  with `mermaid.parse()` borrowed from another app's `node_modules` (PE-Demo) — not a VB
  dependency. Criterion 21 still stands as Ben's one manual paste.
- SR-1…SR-5 · `design-auditor`, step-retire spec round 2, 2026-09-30 · MEDIUM ×3, LOW ×2 ·
  build rules for `docs/step_retire_spec.md` (its "Round 2" section): which restore fits a step
  (stamp vs latest event), restore through `restore_node`'s renumbering, `step_without_br` as a
  warning, FK-declared-only blocking, and the child-path `FOR SHARE` lock. Settle in the build.
- A-SR-7 · same review · LOW · **Baseline freeze vs a step retired with its BR since the last
  freeze** — warn or block? Belongs to the freeze slice.
- sara L2 · `sara`, step-retire pre-merge review, 2026-10-01 · LOW · **The node panel guesses which
  restore to offer** and switches only after a 409: a plainly-retired step costs two clicks. A
  derived `restore_mode` on `BfcNodeOut` (from `step_retire._retired_with_dependents`).
- sara L3 · same · LOW · **The "restore these first" list is parsed from the error text** — a name
  holding `;` splits into two bullets. Return the list as structured data in the 409 body.
- sara L5 · same · LOW · The criterion-4 probe class stays mapped in `Base.registry` after its test.
  Use a throwaway registry.
- Suggest-arrows review · `design-auditor`, 2026-10-01 · LOW · **Restoring a retired step after its
  flow was re-drawn brings its old arrows back beside the new ones** (a second path, possibly two
  start events). Also true of a hand-redrawn flow today. `step_retire.restore` could list the
  restored arrows whose far end already has other live arrows.
  *sara L4 (suggest-arrows, 2026-10-01):* a restore running **alongside** a Keep is not serialised
  either (it locks the retired step, which Keep's frame excludes). Same end state; when fixed,
  `restore` also locks the step's live siblings.
- 4a-R1…R9 · `design-auditor`, Slice 4a round 2, 2026-10-01 · MEDIUM ×4, LOW ×5 · build rules
  in `docs/slice4a_spec.md` "Round 2": fk_group meaning, PK-position collision, claim-carrying
  token with its own key, number-without-token, column codes in a hidden row, before-values from
  `committed_at`, the operational-error list, file-name encoding, one `write_cell`. Settle in the build.
- sara LOW-1 · slice-4-schema review, 2026-10-01 · LOW · **"Merge never retires" is held only on the
  batch header**: a RETIRE/KEPT row inside a MERGE flow batch passes every CHECK; the commit's
  re-validation is the only guard. Carry `import_mode` onto `import_row` via the carrier FK + a CHECK —
  a schema change, Ben's call.
- sara LOW-2 · same · LOW · **Nothing proves a purged batch's name was blanked.** Optional
  `ck_ib_purged_name (rows_purged_at IS NULL OR file_name = '(purged)')` — schema change, Ben's call.
- sara LOW-5 · `sara`, slice-4a-1 pre-merge review, 2026-10-08 · LOW · **"Refused mid-stream" is not
  proven**: the 5,000-row / 200-column test passes for a parser that loads everything and counts
  afterwards. Count the rows `xlsx._rows` yields and assert it stops at the cap. The code does stop
  (`xlsx.py:330`); only the proof is missing.
- sara LOW-6 · same · LOW · **A hostile upload leaves no trace**: a file refused for a DTD or a zip
  bomb gets 422 and no audit row, though it is the clearest sign of probing. Write
  `IMPORT_VALIDATE_REFUSED` (reason + IP) from the router. Before the cloud gate.
- 4a-1 UI · builder note, 2026-10-08 · LOW · **Server messages translate poorly in places**:
  `TOKEN_ROW_MISMATCH`/`ROW_STALE` come with or without their params; `INVALID`/`APPLY_FAILED` carry
  the reason only in English (APPLY_FAILED on a reject now has `params.reason`); `COLUMN_IGNORED`
  puts the column outside `params`; the plain 409 has no `X-VB-Error` kind; `VERDICT_CHANGED` sends
  raw verdict codes. The screen falls back to the English text, so nothing is lost today.
- 4a-1 UAT · ui-verifier, 2026-10-08 · LOW · **An error row still wears an "Add" chip** beside its
  "Error" chip in the import review. The counts no longer include it (b546e6d); the chip is cosmetic.
  Show only "Error" on an invalid row.
- 4a-1 build · 2026-10-08 · LOW · **A description that starts with a tab or CR does not round-trip
  exactly**: `clean_cell` strips leading Unicode whitespace, so re-importing an export trims it and
  reports an UPDATE. Accepted as safer than writing control characters; revisit if a client hits it.
- sara L-4 · `sara`, slice-4a-2 review, 2026-10-09 · LOW · **Field counts on the Data list are merged
  in the router** (`routers/scope.py:256`), not in `de_service`; move them to a
  `list_entities_with_counts` (§10 layers).
- sara L-5 · same · LOW · `bulk.live_names` re-implements `sql_keys`; call it instead.
- sara L-6 · same · LOW · **Preview of a row's own FK group lists no members** (`"with": []`) even for
  a composite relationship; fill it from `live_of` as the numeric branch does (4a-R1).
- sara L-7 · same · LOW · **4a-R19's pin on the referenced entity has no direct test**: add a
  rename-between-validate-and-commit case on `ref_de_name` expecting `RESOLVED_CHANGED`.
- sara L-9 · same · LOW · **The 10 MB cap pattern is wider than needed**: `[^/]+/(validate|check)`
  covers unknown slugs (which then 404); list the known targets in `body_limit.ROUTE_CAPS`.
- sara L-10 · same · LOW · **`consistency_check` has no route or screen yet**: its lines
  (`purge_overdue`, `entities_without_fields`) are reachable only from the service and the purge
  CLI. Owed with the design's `GET /projects/{id}/consistency` and the baseline-freeze warning.
- sara L-1 · `sara`, slice-4a-3 review, 2026-10-09 · LOW · **A purge nobody runs is visible to nobody**
  until L-10's route exists; the purge CLI could also exit non-zero when batches are left over, for a
  future scheduler.
- sara L-3 · same · LOW · `import_purge` restates `bulk._statuses` (circular import); move the
  global-tier status lookup to `code_master` and use it from both.
- sara L-4 · same · LOW · **A preview racing a purge can read "not purged" with no rows**; re-read
  `rows_purged_at` when the row list comes back empty.
- sara L-6 · same · LOW · **Purge test gaps**: no mixed INSERT+UPDATE committed batch (pins the
  retention ruling either way) and no purge of a batch REJECTED by a failed commit.
- sara round-2 L-2 · `sara`, slice-4a-3 per-row purge, 2026-10-09 · LOW · **A partly purged batch shows
  misleading totals** if opened directly: `match_count` comes from the rows left (so 0) while the other
  counts come from the header, and the preview says `purged: false` with only the UPDATE rows listed.
  Derive match from the header, and return a `partly_purged` flag with a one-line notice.
- sara L-1 · `sara`, Slice 5 pre-commit review, 2026-10-09 · LOW · **The link panel flags a
  rejected solution by matching the code `REJECTED`** in the browser (S5-2). Before the coverage
  report counts answers server-side, give `SOLUTION_STATUS` a `behaviour_code` (e.g.
  `NOT_AN_ANSWER`) and branch on that, as law 5 does for FR type and RACI. **Also the server copy in `services/function_requirement.py::_warnings`** (S6a-5). **And `services/interface.py::_pair_matches` matches `INTERFACE_PATTERN` code `BIDIRECTIONAL`** (S6b2-3; the category is not system — sara 6b-2 L2): give it a behaviour or make it system. **And `services/effort.py::summary` sets rejected-solution FRs apart by `SOLUTION_STATUS` code `REJECTED`** (S6c-8).
- sara L-2 · same review · LOW · **`create_solution` needs `SOLUTION_STATUS/PROPOSED`**, a
  non-system category: a project override that retires it makes every create a 500 (as
  `BR_STATUS/DRAFT` already does for steps). Ben to rule: seed it `is_system=True`, or have
  `code_master.maintain` refuse to retire a code a service uses as a default. **Also `FR_FULFILMENT_STATUS/SPECIFIED`** (`create_fr`, Slice 6a design review, 2026-10-09).
- design-auditor Q5 · Slice 6b-1 design review, 2026-10-11 · LOW · **Design inconsistency:**
  `data_migration_map` (§7.9) reads `APPLICATION(AS_IS)` only, while `application_gap` reads
  AS_IS + BOTH. Settle whether BOTH is a migration source when the reports slice is specced.
- design-auditor note · Slice 6b-2 design review, 2026-10-11 · LOW · **`maintain_fr_types`' override re-point** is
  refused by `fk_fri_fr_behaviour` when it would change a live interface FR's behaviour — today a generic FK 409.
  Name it ("…has interface detail") when the code-maintenance slice is built.
- sara L-2 · `sara`, Slice 6c pre-commit review, 2026-10-11 · LOW · **`effort_rate` grants are table-wide:** the
  change-guard trigger refuses a days change without a new version and a non-blank reason, but accepts a reused
  reason, and a key re-point (type/complexity) is unguarded. Revoke table UPDATE and grant column-level UPDATE
  (`standard_days, change_rationale, row_version, updated_by, is_active`), as 0019 does; add the key columns back
  with A-16. Needs a migration on `main`.
- sara L10 · `sara`, Slice 7c pre-commit review, 2026-10-11 · LOW · **Legacy supporting-system rows on to-be
  steps are not shown on the step:** `as_is_support_on_to_be` lists them, but the panel renders only on as-is
  steps, so the consultant cannot unlink them there. Show a read-only list with Unlink on a to-be step while any
  exist. Related: restoring such a step with dependents needs `AS_IS` on (`ROW_COMPONENTS[ApplicationBfcNode]`).
- sara 8 L6 · `sara`, slice 8 pre-commit, 2026-10-11 · LOW · **`COMPONENT_ROWS` probes no link tables**
  (`br_solution`, `application_solution`, `fr_interface*`, legacy to-be `application_bfc_node`), so the
  freeze's "a gate never silently drops a live row" leans on OR-1 and the must-be-empty dangling-link lines.
  Add probes, or a test that a live link in an off component blocks the freeze.
- sara 8 L7 · `sara`, slice 8 pre-commit, 2026-10-11 · LOW · **Baseline reads recompute the integrity
  digest every time, and the diff is one synchronous response** (~50k rows a side at the A-35 bound, any
  VIEWER). Cache `verify` per baseline (it cannot change) and page or stream the diff with D-50's screen.
- sara 8 M4 (rest) · `sara`, slice 8 pre-commit, 2026-10-11 · LOW · **The first-freeze race (two v1.0s at
  once) is held by `uq_baseline_first` + 23505 → 409 but not tested**; the prior-header race is.
- UAT 9 · `ui-verifier`/`a91…` report, slice 9, 2026-10-11 · LOW · **The project dashboard reads its counts from the
  freeze preview** (`baselines/next`), which runs the consistency check and hashes the live set. Cached 60s and shared
  with Baselines, but heavy on a large project → give the dashboard a light counts route.
- UAT 9 · slice 9, 2026-10-11 · LOW · **The BR page carries its own copies of the RACI panel and the solution links**
  (`features/requirements/BrRaci.jsx`, `BrSolutionTags.jsx`) beside the shared `chartKit.RaciPanel` and
  `SolutionLinkPanel`; a fix to one does not reach the other. Fold back into the shared components.
- UAT 9 · slice 9, 2026-10-11 · LOW · **DFD at fit-zoom is still dense on a big branch** (text ~9px, crossing lines);
  the data band now packs into rows. Revisit with the layout work of D-50's diagram highlighting.
- UAT 10a · slice 10a, 2026-10-12 · LOW · **"New trigger" button runs past the process panel's right edge** at 1440px
  in the "Started by" section (`features/processes/StepSections.jsx`); pre-existing, seen in
  Evidence/2026-10-12/slice-10a/02-br-edited-in-chart-panel-light.png. **FIXED 2026-10-14, slice 10e (`9fa1ea3`); ui-verifier Evidence/2026-10-14/slice-10e — awaiting Ben's close.**
- UAT 10d-1 · slice 10d, 2026-10-13 · LOW · **At 400px the header breadcrumb collides with the "Working · no baseline
  yet" pill** (shell, not the panel). Evidence/2026-10-13/slice-10d/s10d-07c-400.png.
- UAT 10d-2 · slice 10d, 2026-10-13 · LOW · **The chart toolbar wraps at 1440px**: Move up / Move down / (i) drop under
  "Add child" (`features/processes/ProcessesPage.jsx`, tree column `clamp(340px, 32%, 440px)`). s10d-01-panel-top.png. **FIXED 2026-10-14, slice 10e (`9fa1ea3`); ui-verifier Evidence/2026-10-14/slice-10e — awaiting Ben's close.**
- UAT 10d-3 · slice 10d, 2026-10-13 · LOW · **At 1440px the page scrolls ~186px before the sticky tree/panel columns
  pin**, so the tree card's header scrolls partly off; the selected row stays visible. s10d-07a-scrolled-1440.png.
- test-runner · slice 10d, 2026-10-13 · LOW · **Two Pydantic serializer warnings** (a dict where a model is expected):
  `warnings` in `test_application_api.py::test_moving_to_to_be_with_as_is_links_warns_and_the_line_lists_them`,
  `effort_change` in `test_effort_api.py::test_a_type_change_rederives_and_says_so` — loose response-model typing.
- UAT 13a-1 · slice 13a, 2026-10-14 · LOW · **A selected/hovered process row truncates its name to one letter** ("C…")
  once the BR chip appears beside the new readiness tag (`ProcessesPage.jsx` row). Evidence/2026-10-13/slice-13a/s13a-01-chart.png. **FIXED 2026-10-14, slice 10e (`9fa1ea3`); ui-verifier Evidence/2026-10-14/slice-10e — awaiting Ben's close.**
- UAT 13a-2 · slice 13a, 2026-10-14 · LOW · **The left rail shows "Settings" to a viewer** (screens inside are read-only;
  presentation only). s13a-10-viewer.png.
- UAT 13a-3 · slice 13a, 2026-10-14 · question · **Unticking a CRUD box leaves the step's data out in place** (D-24: one
  record of step I/O; the grid tooltip says ticking adds it). The BR page lists it under "Recorded on the DFD, not on the
  requirement"; the tester found no control there to remove it — check the panel's Data tile is the obvious path.
- sara L3 · slice 10c pre-merge review, 2026-10-14 · LOW · **The "keys only" attribute hint rule (D-39) now also lives
  in the browser** (BR CRUD grid expander, slice 10c) besides the entity page; two places to keep in step. Move to one
  shared helper, or have the server send the flag.
- UAT 10c-1 · slice 10c, 2026-10-14 · LOW · **A project you cannot see still draws the project shell under "Not found"**
  (rail items, empty Baselines / Program dashboard cards; no name leaks, 404s are correct). Render the plain not-found
  page when the project read is 404. Evidence/2026-10-14/slice-10c/s10c-28*.png.
- sara L3 · slice 13d pre-merge review, 2026-10-15 · LOW · **Drawing a link another user has just drawn shows a 409**
  instead of "Already on the diagram" (DfdDraw.jsx). Map that 409 to the same message.
- sara (out of slice) · slice 13d review, 2026-10-15 · LOW · **`step_io.live_entity` reads the data entity without a lock**,
  so a link could be saved against an entity retired in the same instant (cf. VB-009). Take `FOR SHARE` on the entity.
  **Fixed 2026-10-17 with VB-009 (branch `fix/vb-007-009`), awaiting Ben's close.**
- sara L-3 · VB-009 fix review, 2026-10-17 · LOW · **`bfc.link_external_flow` checks the external party without a
  lock**, so a flow could land under a party retired in the same instant (VB-009's class). Take
  `lifecycle.lock_for_share(db, ext)` after the project check, before the liveness check.
- review L1 · VB-007/VB-010 review, 2026-10-17 · LOW · **After Back and "Do fields later" / "Discard and continue",
  a second Back returns to the guarded screen** (`navigate(target)` adds an entry: […, A, B', A']). Use
  `navigate(target, { replace: true })` in `ImportWizard.jsx` and `ProcessesPage.jsx`.
- review L2 · same · LOW · **Chrome may skip the re-pushed entry on a real toolbar Back** (an entry pushed with no
  user activation, inside the popstate handler), so a second toolbar Back while the prompt is open could leave the
  page; headless `goBack` does not show it. Check once by hand with the toolbar Back pressed twice.
- review L3 · same · LOW · **An in-page `#` link on a guarded screen would raise the prompt** (`app/backGuard.js`).
  If such a link is added, let a move through when only the hash differs.
- test-runner · slice 10c, 2026-10-15 · LOW · **An interrupted pytest run leaves rows the next run's downgrade refuses**
  (`br_function_requirement`, `baseline`: the 0049 / 0047 downgrade guards raise), so every test errors in the `schema`
  fixture until the DB is cleared by hand. The `clean` fixture's `DATA_TABLES` omits them; wipe them before the downgrade.
- sara L1–L8 · `sara`, night-batch bundle review (ui-mockup + slice 13c), 2026-10-16 · LOW · **eight lines,
  one review**: (L1) the node/BR detail reads assemble `stamp.of` in the router — move to a service read;
  (L2) `scope_summary.AGREED` branches on BR_STATUS codes — a `behaviour_code` later; (L3) the dashboard tests
  `status_code === 'FROZEN'` — prefer a server `awaiting_signoff` flag; (L4) dashboard queries other than the
  project and the scope summary fail silently (cards vanish) — fold into the page error; (L5) the home page runs a
  full baseline→live diff per visit — a counts-only diff for large projects; (L6) `process_volume.set_volume`
  writes, bumps `row_version` and audits on a no-op — skip as `set_basis` does; (L7) `lock_for_share` then UPDATE
  can deadlock two saves of one node → 500, not 409 (pre-existing in `set_performer`) — map 40P01 to 409 once,
  centrally; (L8) housekeeping — `select` imported inside `process_volume.summary`, `ProjectOut.hours_per_working_day`
  float vs Decimal string elsewhere, `VolumeSection` repeats the period list (deviation 7h), a stray
  `s13d-snap-check2b.yml` at main's root.
- **2026-10-16 · slice 11a (`sara` pre-commit; H1, H2, M1, L1, L3 fixed in the slice; M2 → history [Q-29]):**
  (L4) the derived BR priority is on the BR detail read only — §1.1 also wants it on the BR list (`BrOut` /
  `list_brs`); (L7) no test of a reversed cross-spec diff (spec 4 → spec 3: lines REMOVED, kept out of the
  summary), and §7's spec-2 baseline case is not re-proven for lines; (L2) after a 0055 downgrade and re-upgrade the
  backfill marker survives and the copy never re-runs — documented in `br_lines.backfill`; legacy text stays visible.
- **2026-10-16 · slice 11a browser check (Lilly):** the baseline comparison names a requirement line
  "3 · BR-0002 · 01.01.02 Check credit" (own label, then its BR's label), where the panel says "BR-0002.3" — read the
  same way in both places (a label rule for `br_requirement_line` in the diff labeller).
- **2026-10-16 · slice 11c (`sara` pre-commit; M1, L1–L6, L8 fixed in the slice):** (L4) the flow-note PATCH has its
  API function, audit and test but no edit control on screen yet (notes are set when a flow is added); (L7) a flow
  removed while "Create interface FR" runs can still seed the FR — accepted, the user asked for that FR; (L9)
  `br_flows.info` queries once per flow — batch it like `coverage()` if a BR ever holds many flows.
- **2026-10-16 · test harness (`sara`, L3):** the app's bcrypt cost is bcrypt's library default, implicitly; pin it
  as `auth.security.BCRYPT_ROUNDS = 12` with a test that it is ≥ 12, and have the harness lower that constant.

- **2026-10-16 · access slice A (`sara`; steps 1–3: L1, L5–L8 fixed in the slice):** (L4) switched-off users' memberships
  do not show on the member list (as before, sara 7b L8); the decision paper wants them shown, marked inactive and
  removable — take it with program members in slice B. (L9) the user-type confirm's lock is not exercised by a
  concurrent test (sequential stale case only); and slice B must add program memberships to `user_admin._comes_back`
  and its digest, or a demoted admin's program role comes back unseen.
- **2026-10-16 · wave 1g (`sara` pre-commit; M1, M3, L1–L3, L5–L7 fixed; M2 → history [Q-38]):** (L4, part) the
  code-column list is cached per process but `GET …/code-lists` still runs ~25 count queries per load — fine at
  today's sizes, measure before a client project grows large. (L8) four scratch copies of service code sit untracked
  in `backend/` (never staged) — delete on Ben's click. Criterion 19 (a save during a re-point) is proven by lock
  order, not a two-connection test.
- **2026-10-16 · access slice B (`sara`; M1, M2, L1, L2, L5, L6 fixed in the slice):** (L3) `program._check_level`
  duplicates `project._check_level`, and `program.py` imports `project._user_share_lock` / `lock_program` — move the
  three to one home (`services/access.py` or a `services/locks.py`). (L4) `program._move_changes` is N+1 (up to 3
  queries per active staff user) and runs under the move confirm's locks — load both programs' members and the
  project's members in 3 queries before a client tenant has many users.
- **2026-10-18 · slice 14 step A (`sara`; M1–M3 fixed in the step):** (L1) 0061's downgrade clears the behaviour of
  every ISSUE_STATUS row, so a status a platform admin added later makes the re-upgrade refuse — clear only the five
  seeded codes and refuse while another company status exists. (L2) `test_migration_0061_0062.py` covers the
  project-tier refusal but not the live-hide refusal. (L3) the ISSUE switch-off blocker lists bare stakeholder ids;
  label them `#<id>` like `lifecycle.LABELS`. (L4) `StakeholdersPage` does not show a failed org-unit load. (L5)
  `CodeListsPage` keeps a third copy of the behaviour vocabularies — serve them from the API.
- **2026-10-18 · slice 14 step B (`sara`; M1, L1–L4, L6 fixed in the step):** (L5) the issue schemas do not forbid
  unknown fields, so a PATCH carrying `resolution` / `resolved_at` is ignored with a 200 rather than a 422 (law 6
  holds) — add `extra="forbid"`. (L7) no two-connection race test for R11 (raise / edit-raiser against a concurrent
  stakeholder retire); the FOR SHARE → FOR UPDATE order carries it. (L8) `IssuePage` does not check that the issue
  belongs to the project in the address; `/p/A/issues/<B's id>` shows B's issue with A's pickers.
- **2026-10-18 · slice 14 step C (`sara`; M2, M3, L1, L4, L6 fixed in the step; M1 is step D's Grade 1 proof):**
  (L2) `issue.links_of` and the link route read each link's BR lazily, one query per link — load `br_row` with
  `selectinload`. (L3) the register's area filter lists only areas with open issues and drops the "As-is" prefix the
  dashboard shows. (L5) `DashboardOut` rows are untyped `list[dict]` — pin them as small models.
- **2026-10-20 · slice 14 browser check (`ui-verifier`, Evidence/2026-10-20/slice14/; 9 of 10 pass, check 3 was the
  brief's own date error; four defects fixed on `fix/2026-10-20_issue-screens`):** (L1) in the register a retired
  issue's "Retired" chip is cut to "Retir…" beside a long title. (L2) the requirement picker opens empty with no
  "nothing to link" text when every live requirement is already linked. (L3) the retire-step dialog's requirement
  number is small low-contrast monospace. (L4) a retired issue shows its "Open" tag beside "Retired", which can read as
  live. (L5) the date inputs show the browser's mm/dd/yyyy while the register shows 2026-10-20 (native input). (L6)
  the retire-issue and retire-stakeholder dialogs word the blocker differently ("linked to requirements" / "a live
  issue").
- **2026-10-20 · slice 15 backend, steps 1–5 (`sara`; no critical or high; M1, M2, L2, L3, L4 fixed in step 5;
  L1 is Ben's, in the design history §1):** (L5) `phasing.plan` forces its displayed lines onto the effort headline;
  if the exact lines ever stopped summing to it (only on corrupt data, e.g. a live FR under a retired solution) the
  gap would be spread silently — log a warning when they differ. (L6) body ids are plain `int`, so an id beyond
  bigint reaches PostgreSQL and returns a 500 — app-wide, a shared `Id = Field(gt=0, lt=2**63)`.
- **2026-10-20 · slice 15 screens (`sara` step 6: no critical or high; M-A, M-B, L1, L2, L5–L7 fixed; and the
  `ui-verifier` Waves check, 10 of 10, Evidence/2026-10-20/slice15/):** (L3) the Waves list works out "Current wave" in
  the browser while the plan takes it from the server — return it from `GET /phases` so one rule serves both. (L4)
  "Remove from all waves" saves at once with no confirm. (L8) a refused wave retire says "Retire these first" though
  the remedy is to remove the splits (the shared lifecycle wording). (L9) the comparison's Object column is empty for
  wave rows (their code, e.g. "W2", does not match the label splitter). (L10) the "Add wave" button and the split row
  buttons lack an accessible name in some states.
- **2026-10-21 · slice 16 step 1, `baseline_archive` (`sara`; no critical or high; M1 fixed — a row is born owed):**
  (M2) no `test_migration_0068`: the backfill (one SCOPE per baseline by the freezer, one SIGNOFF per approved
  baseline by the approver) and the downgrade refusal are untested — add a slow-marked migration test before the
  0068 deploy. (M3) VB_design §6.6 ("no UPDATE on any `baseline_*` table") and CLAUDE.md law 2 read as if
  `baseline_archive` were a shadow; it is not (column UPDATE, `fn_baseline_archive_guard`) — a one-line carve-out in
  both, Ben's to approve. (L1) a written row's `row_version` may be set lower. (L2) an owed row may be written and
  marked check-failed in one UPDATE.
  (M2 done 2026-10-21: `tests/test_migration_0068_0069.py`. M3 done 2026-10-21: Ben's AR-14, law 2 and design §6.6.)
- **2026-10-21 · slice 16 step 2, archive writer + `vb_instance` (`sara`; H1 fixed — the backlog script checks the
  instance; M1, M2, L1, L2, L4 fixed):** (L3) `VB_ARCHIVE_DIR` / `VB_ARCHIVE_KEY_DIR` may point inside the repo and
  `.gitignore` has no archive entry — `archive_store.from_settings` should refuse a folder under the repo root.
  (L5) `scripts.stamp_instance` writes no audit row — add `INSTANCE_STAMPED` (old id, new id, OS user).
- **2026-10-21 · slice 16, 0072–0073 (`sara`; H1, H2, M1–M3, L1–L6 fixed):** (own note) `audit_event.occurred_at`
  is not forced by the database on INSERT, so the app role could write an aged grant row and pass AR-13's 30-day
  check — not reachable from any route; force `occurred_at := statement_timestamp()` in the audit insert guard.
- **2026-10-21 · slice 17 design review (design-auditor D4, LOW):** "kept forever, no DELETE" does not cover
  `TRUNCATE` — an owner `TRUNCATE app_user CASCADE` empties `project_purge`, `project_purge_key` and (slice 17)
  `platform_admin_grant`; add a statement-level `BEFORE TRUNCATE` refusal outside test databases.
- **2026-10-21 · slice 16 request screens (`sara`; H1 fixed — a company FR type waits while a removal is open; M2,
  L1–L10 fixed):** (M1) the one-off operator backfills that loop over every project (`br_lines.py:136`,
  `components.py:422`, `effort.py:76`, `dfd_rule.py:191`) do not skip a project with an open removal request — skip
  `access.pending_project_ids()` and print the skipped codes.
- **2026-10-22 · slice 16, 0074–0075 and the DELETE run (`sara` ×2; no critical or high; M1–M3, M-A, L1–L5, L-b–L-d,
  L-f, L-g fixed; a NULL from `fn_purge_allows` letting a key row through found by the full suite and fixed):**
  (L6) the bypass names the role `vb_owner` literally — the Azure migration / purge login must be that role, or every
  purge fails closed with "immutable"; one line in the deploy runbook. (L-a) for a table without `project_id`
  (`import_row`) the purge proof falls back to the delete rule — add a test counting it by a hand-written join, with
  import rows in two projects. (L-e) the operator's prompt waits inside the transaction holding the project lock — the
  runbook says "answer promptly". (L-h) criterion 8's "baseline reads not blocked" has no concurrent-read test, and
  criterion 10 checks the project's audit rows by `project_id` only — assert no non-kept event names the project by
  `target_table = 'project'`. (Accepted, sara M1 note) `current_user = 'vb_owner'` alone is not proven by a test: it
  needs an owner session under another role.
- **2026-10-22 · slice 16, DELETE key destruction (`sara` ×2; H1, H2, M1, M2, L1–L4, N1, N2 fixed):** (L5) local key
  destruction is a file delete — the deploy runbook keeps `VB_ARCHIVE_KEY_DIR` out of every backup, or criterion 9
  holds only on paper. (tests) not yet exercised: a stray non-envelope object in the project's folder, the retry whose
  proof file is already unreadable, the advisory-lock refusal and the exactly-one-row check, the re-purge tombstone,
  and "exactly one PURGE_KEYS_DESTROYED after a retry".
- **2026-10-23 · slice 17 (`sara`; H-1, H-2, M-1, M-2 (tests; the card is VB-012), M-3 (test + deploy line), L-1–L-3,
  L-5 (deploy line) fixed):** (L-4) a fifth test-only trigger bypass — `test_admin_grant_api` disables
  `trg_platform_admin_grant_guard` to age a request, beside `seed_bootstrap`, `forget_grants` and the backfill-row and
  unrecorded-admin helpers; all owner-only, on a test database, re-enabled in `finally`. (L-6) `tests/conftest.py`
  accepts any database whose name contains "test" (`vb_latest_db` would pass) — reuse `fn_backdating_allowed`'s
  whole-name pattern. (M-3 option) BOOTSTRAP could also require that the target row was inserted in this transaction,
  so even a TEMP-capable session could not forge one.
- **2026-10-23 · slice 16 project status, reopen, retire (`sara`; HIGH-1 refused by name, MEDIUM-1, LOW-1–LOW-3
  fixed):** (LOW-4) moving between two closed statuses keeps `closed_on`, but the card offers only open statuses once
  closed and no test covers it — add both when a second closed code exists. (LOW-5) the card labels the status from the
  live code list, so a retired status code shows "—" — have `ProjectOut` carry the code. (browser) the "Project
  retired" message was not caught on screen (same 3-second message as every admin action).
- **2026-10-23 · slice 16 weekly archive check (`sara`; M1–M3, L1, L2, L6 fixed):** (L3) a held archive's error is the
  backend's English sentence inside translated card text — return a code and translate it. (L4) "fewer than two admins"
  is counted in both `purge.overview` and `admin_grant.weekly_admin_lines` — one owner of the count (the duplicate
  alert was removed from the card 2026-10-23, FIXED, awaiting Ben's close). (L5) UNREADABLE (a hash-matching file that
  is not an envelope) is not exercised; the script's exit code now has its test (2026-10-23, FIXED, awaiting Ben's close). (browser, 400px) the Requests grid cuts its columns
  after State and the admin tab strip hides Code lists and Removals — not checked whether either scrolls.
- **2026-10-23 · test speed, delete-based wipe and saved states (`sara`; HIGH, MEDIUM, five LOWs fixed):** both
  remaining LOWs fixed the same day, awaiting Ben's close — `_restore_library` now calls `_cols`; the test-database
  guard matches a name ending in `_test_db` instead of any name containing "test".
- **2026-10-28 · approvers setting, migration 0079 (`sara`; H1, M1, M2, M5 fixed):** (M3) FIXED 2026-10-28, Ben: "YES"
  — single-owner is refused unless FRONTEND_URL's host is localhost / 127.0.0.1 / ::1 (server, writer, weekly check,
  removal run and the owner command, through `instance.not_this_computer`); an unset FRONTEND_URL counts as not
  local (sara re-check M). Open for Ben: the check reads the configured address, not the one uvicorn listens on — a
  server started `--host 0.0.0.0` with FRONTEND_URL still on localhost and both single-owner declarations would pass;
  closing that needs the run command or the deploy to state the listen address. (M4,
  before the DELETE_ARCHIVE run is built) a DELETE_ARCHIVE approved alone whose key destruction started, then the
  setting back at 2: keys still destroyable, execution refused, cancel refused — decide "finishing is safe" and test
  the destroy clause. (M6) after the return to 2 a voided lone approval still lists as APPROVED with a runnable time,
  and the run's message says "approve again" where only cancel-and-re-request works. (L1) 1→2→1 revives a voided
  approval. (L2) the guards read the setting without a lock. (L3) PROJECT_PURGED audit lacks `approved_alone`. (L4)
  some wording still says "two" under 1. (L5) owner TRUNCATE bypasses the one-way kind and the append-only log. (L6) a
  first stamp can declare the kind with no operator. (L7) the banner hides if the overview fails to load. (L8)
  `purge_run` reads `fn_approvers_required()` directly (it holds a Connection) — note it. (L9, re-check) back at 2 an
  admin made alone pairs with nobody until re-granted by a request or an IS grant — intended, but silent: list "live
  admins made alone" in the weekly check and show "approved alone" on decided grants.
- **2026-10-28 · slice 1e-a imports, BR / FR / Issue (`sara`; M1, M2 fixed, Ren for Ben 2026-10-28):** (M3) the
  import validators repeat the service rules (status changes, closed issue, SOLUTION / EFFORT) instead of calling one
  check the screen also uses — two copies can drift. (L1) the RESOLVED_CHANGED message shows ids, not numbers. (L2) a
  stakeholder renamed after export can re-point an issue's raiser to a different person of the old name. (L3) commit
  runs per-row queries and locks every stakeholder; `create_fr`'s `link_fr` still runs the drift query. (L4) the
  default-status literals ("OPEN" and the FR default) are written twice. (L5) `tag_br_fr` still checks SOLUTION in the
  router, not the service.
- **2026-10-28 · slice 1e-b design review round 2 (design-auditor):** (N2) a step or party name that, once
  cleaned, matches two live records is not yet defined — make it a row error naming both (piece a).
