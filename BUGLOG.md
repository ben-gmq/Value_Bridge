# Value Bridge — BUGLOG

**Id prefix:** `VB-###` · **Next id:** VB-006 *(derive it, never trust this line — see the
`buglog` skill Step 0b)*
**Open: 1 entry (VB-005, the standing backlog) · 1 unworked line in it — measured 2026-09-28.**
**Archives:** none yet.

**Status of the app:** design only. No code, no schema, no data, **no defects**. The design
spec is `docs/VB_design.md`; the originating brief is `docs/ASSESSMENT_BRIEF.md`.

**Why this file has four closed entries and no open ones.** VB-001…VB-004 were never code
defects — there is no code. They were three design-review findings that could not be closed
in the spec on 2026-09-17, plus the standing backlog stub. All three were settled on
2026-09-24 and folded into `docs/VB_design.md`. An open design question belongs in that
document's §11 Assumptions, not in a defect log; these should have gone there in the first
place.

**Section map:** `## Closed` · `## Standing backlog` (VB-005; VB-004 closed unused).

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
