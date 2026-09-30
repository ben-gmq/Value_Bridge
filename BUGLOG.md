# Value Bridge — BUGLOG

**Id prefix:** `VB-###` · **Next id:** VB-007 *(derive it, never trust this line — see the
`buglog` skill Step 0b)*
**Open: 2 entries (VB-006; VB-005, the standing backlog) · 14 unworked lines in VB-005 (6 more fixed, awaiting Ben's close) — measured 2026-09-30.**
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
  node. Ben to choose: drop the nav item, or point it at the chart with a "pick a node" hint.
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

