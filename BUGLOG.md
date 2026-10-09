# Value Bridge — BUGLOG

**Id prefix:** `VB-###` · **Next id:** VB-010 *(derive it, never trust this line — see the
`buglog` skill Step 0b)*
**Open: 5 entries (VB-006, VB-007, VB-008, VB-009; VB-005, the standing backlog) · 39 unworked lines in VB-005 (8 more fixed, awaiting Ben's close) — measured 2026-10-09.**
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

### VB-006 | App shell overflows horizontally on a phone; top nav clips below ~930px | OPEN

- **type:** BUG · **found:** 2026-09-30 by `ui-verifier` (Slice 2a UAT, process chart) · **depends-on:** —
- At 390px wide the page renders 477px wide: the top bar's user menu is cut off at the right
  and the footer text overflows. At ~930px the nav shows "BR–FR map" as "BR" and hides
  Interfaces and Data. The step panel content itself fits. Not caused by Slice 2; likely
  the shell (`frontend/src/components/AppShell.jsx`, cf. commit 07c6fbe "nav scrolls instead
  of squashing"). Evidence: `.playwright-mcp/page-2026-09-30T02-20-08-918Z.png`.
- **root cause:** not yet investigated · **files:** `frontend/src/components/AppShell.jsx` (suspected)

### VB-007 | Import wizard's "Do fields later" gate can be left with the browser Back button | OPEN

- **type:** BUG · **found:** 2026-10-09 by `sara` (Slice 4a-2 pre-merge review, M-2) · **depends-on:** —
- 4a-R10 says that after the entities step commits, the wizard can be left only through "Do fields
  later". `beforeunload` covers reload and tab close, and the dialog blocks Esc and backdrop, but
  browser Back unmounts the page with no prompt, so a half-built model can be left silently. The
  "No fields yet" marker and `entities_without_fields` still show it afterwards.
- **root cause:** `useBlocker` needs a data router; `frontend/src/main.jsx` uses `<BrowserRouter>`.
  Fix by moving to `createBrowserRouter` (a routing change across the app) or a popstate guard in
  `ImportWizard.jsx`. · **files:** `frontend/src/main.jsx`, `frontend/src/components/ImportWizard.jsx`

### VB-008 | The data entity page shows edit controls to reviewers | OPEN

- **type:** BUG (presentation) · **found:** 2026-10-09 by `sara` (Slice 4a-2 review, M-3) · **depends-on:** —
- `DataEntityPage.jsx` shows Edit/Retire/Restore, Retire entity, Add field and the snackbar Restore
  to a REVIEWER; `DataEntitiesPage.jsx` shows Restore on retired rows. The server guards refuse
  every one (403), so nothing is breached. Predates Slice 4a.
- **root cause:** those controls never went through `useCanEdit` (CLAUDE.md "Edit controls").
  · **files:** `frontend/src/features/data/DataEntityPage.jsx`, `DataEntitiesPage.jsx`

### VB-009 | A BR→data-entity link may land under an entity retired at the same instant (suspected) | OPEN

- **type:** BUG (concurrency, unverified) · **found:** 2026-10-09 by `design-auditor` (Slice 5 design review round 1, side note to DR1-D1, MEDIUM) · **depends-on:** —
- `business_requirement.link_data_entity` checks the entity through `step_io.live_entity`, a plain
  `db.get` with no lock. A data-entity retire that commits between that read and the link's INSERT
  would leave a live `br_data_entity` under a retired entity; the INSERT's FK check still passes.
- **To confirm:** two sessions — hold a DataEntity retire open between its lock and its commit
  while a link runs. Slice 5 adopts the locked form for `br_solution`, so the fix is the same
  `lock_for_share` before the liveness check. · **files:** `backend/services/step_io.py:16-20`,
  `backend/services/business_requirement.py`

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

