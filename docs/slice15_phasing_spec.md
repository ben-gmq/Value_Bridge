# Slice 15 — Phasing and dependency (spec, DRAFT for Ben, night batch 2026-10-16)

**Status:** DRAFT — not approved, not built. Needs Ben's answers (Q-55…Q-62) and his OK. **Source of truth:**
`docs/VB_design.md` (D-18; PHASE, SOLUTION_PHASE, SOLUTION_DEPENDENCY in §5.3; the phase plan report; criterion 68),
plan row "Phasing and dependency" in `docs/VB_remaining_work.md` (stream B, after 1g; 2.5 days). **Schema:**
`docs/slice15_phasing_schema.md` (apple, 2026-10-16) — grain, DDL, the no-cycle lock, the effort split, retire rules,
shadows at hash spec 6, migrations 0064–0066. This spec adds screens, routes, acceptance and grade.

## 1. Purpose
Plan delivery in waves: name the phases, say which share of each solution's effort lands in which phase, record which
solutions must come before others, and read a phase plan — effort per phase, what is not yet phased, and order
problems — that a signed baseline keeps.

## 1a. Interface
- **Input:** a consultant (EDIT, component PHASING on — Q-55) names phases, splits solutions across them by percent and
  links solution dependencies. No import here (WBS import later links to phases).
- **Output:** a Phases screen (list, reorder, dates, status), each solution's phase split and dependencies on its page,
  and the phase plan report (effort per phase + UNPHASED + UNASSIGNED = the effort headline; order warnings).
- **Validation:** a solution's split is ≤ 100 % (Q-56); a dependency never closes a cycle (refused with the path); a
  solution never depends on itself; links stay in one project.
- **Archive:** audited writes, soft delete, the three tables frozen at hash spec 6.
- **Maintenance loop:** the phase plan's warnings (unphased effort, a prerequisite in a later phase) are reviewed by the
  engagement's consultant before each freeze; `consistency_check` adds "split over 100" and "dependency cycle" proofs.

## 2. Grade
**Grade 1 for the hash-spec bump** (spec 5 → 6, after the Issue module's 4 → 5): old baselines keep verifying — freeze
at 5, migrate, verify old and new, downgrade refusals. **Grade 2** for the effort split and the no-cycle rule (a wrong
plan figure someone decides from; the cycle refusal proven with a concurrent pair, since the advisory lock is the whole
guarantee). **Grade 3** for layout.

## 3. Functions (design §4 grid, as built)
| Function | Logic |
|---|---|
| phases: add / edit / reorder / retire / restore | code typed, unique while live; two-phase reorder of `seq_no`; retire refused while splits exist |
| split a solution | percent per phase; total ≤ 100 % under a row lock on the solution; 0 % rows refused |
| link / unlink a dependency | advisory lock per project, then a recursive walk; a cycle → 422 naming the path; restore only through link |
| phase plan | effort per phase from current FR `effort_days` × percent; UNPHASED and UNASSIGNED lines; order warnings (Q-61) |
| freeze | phase, solution_phase, solution_dependency at spec 6; status copied, not hashed (Q-58) |

## 4. API (`/api/v1`)
`GET/POST /projects/{id}/phases` · `PATCH/DELETE /phases/{id}` · `PATCH …/restore` · `POST /projects/{id}/phases/reorder`
· `PUT /solutions/{id}/phase-split` · `POST /solutions/{id}/dependencies` · `DELETE /solutions/{id}/dependencies/{link_id}`
(scoped to the path solution, 404 otherwise) · `GET /projects/{id}/phase-plan`. Reads VIEW; writes EDIT +
`component="PHASING"`, named in `ROUTE_COMPONENTS`.

## 5. Screens
Rail item **Phases** under Control (component on): phase list with drag reorder, dates and status; the solution page
gains a "Phases" card (split) and a "Depends on" card; the phase plan as a tab. Kit components; strings in
`en.phasing.json`; no mockup exists — nothing faked, Ben sees it in the browser check.

## 6. Acceptance criteria
1. A split over 100 % → 422; under 100 % shows the rest as UNPHASED. 2. Phases + UNPHASED + UNASSIGNED = the effort
headline, to the cent. 3. A → B → C, then C → A → 422 naming the cycle; two concurrent inserts that would close a cycle
— one succeeds, one is refused. 4. A solution depending on itself → refused by the database. 5. A prerequisite in a later
phase (or the same — Q-61) shows a warning in the plan. 6. A phase with splits, or a solution with links, cannot be
retired (409 naming them). 7. A freeze holds the three tables; a reorder shows as MOVED, a status change not at all; a
spec-5 baseline still verifies. 8. Component off → writes 409 COMPONENT_OFF, rail item hidden. 9. A non-member gets 404
on every phasing route of a restricted project; a cross-project unlink through the path solution → 404.

## 7. Questions for Ben (from the schema's §9)
Q-55 a PHASING component needing SOLUTION (rec. yes) · Q-56 split ≤ 100 %, percent not days, under 100 % allowed as
UNPHASED and never blocking a freeze (rec. yes) · Q-57 PHASE_STATUS pinned and company-only, like Q-39 (rec. yes; "current
phase" = live IN_DELIVERY with the lowest `seq_no`; cancelled phases refuse new splits) · Q-58 hash code, name, dates;
`seq_no` as position; status copied not hashed (rec. yes) · Q-59 surrogate keys on the link tables, rewriting §5.3 (rec.
yes) · Q-60 retiring a solution with splits or dependencies is refused (rec. yes) · Q-61 a prerequisite in the same phase
counts as a warning ("at or before", criterion 68), and so does an unphased prerequisite (rec. yes) · Q-62 ship the plan
without "volatile areas in the current wave" until 1f lands (rec. yes).

## 8. Size and order
About 2.5 working days. Builds after the Issue module merges (hash spec 5 then 6, in order on `main`); if Issue is held,
the two swap spec numbers — one commit editing `CURRENT_HASH_SPEC`, the three `since=`, the three migration guards and
the spec comment.

## 9. Revision after design review round 1 (design-auditor, 2026-10-16: 0 high, 4 medium, 5 low)
These rules supersede anything above that disagrees.
- **R1 (M).** Link writers take `lifecycle.lock_for_share` on both solutions before checking they are live (SR-5). A
  split write keeps the schema's `FOR NO KEY UPDATE` on the solution (it serialises two splits of one solution, so the
  ≤ 100 % check cannot be raced — round 2) and takes FOR SHARE on each phase. The schema's §5 governs locking except
  where this section names it. `consistency_check` gains freeze-blocking
  `solution_phase_under_inactive` and `solution_dependency_under_inactive`, as `brsol_under_inactive`.
- **R2 (M).** The split write carries `(solution_phase_id, row_version)` for every live row it was built from, plus new
  rows; a mismatch or an unlisted live row → 409 (the `br_lines.reorder` pattern). Whether it is one PUT of the whole
  set or the signed POST / DELETE per assignment is Q-63; if PUT, Q-56 ("must equal 100") is asked again.
- **R3 (M).** The phase plan is built from `effort.summary(...)["by_solution"]` (rated, non-rejected, the unassigned
  bucket), so phases + UNPHASED + UNASSIGNED = the headline by construction; a test includes a rejected-but-split
  solution and an unrated FR.
- **R4 (M).** `COMPONENT_ROWS["PHASING"]` probes live phases, splits and dependencies, so PHASING cannot be switched off
  under any of them.
- **R5 (L).** After taking the advisory lock the service asserts the transaction is READ COMMITTED (the "first
  statement" wording is dropped); the concurrent-pair test stays.
- **R6 (L).** Displayed phase lines use largest-remainder rounding to the headline's cents, and so does each line's
  per-solution breakdown (UNPHASED included) to its line; criterion 2 tests the displayed figures. *(Round 2: the
  schema's "lock is the first statement" wording, line ~162, is superseded by R5.)*
- **R7 (L).** Every body `phase_id` resolves to a live phase of the path solution's project before any write (404
  otherwise).
- **R8 (L).** One status mechanism: `PINNED += (PHASE_STATUS, IN_DELIVERY), (PHASE_STATUS, CANCELLED)` with PHASE_STATUS
  company-only (as G-2); the deploy step lists and refuses existing project-tier PHASE_STATUS rows or hides.
- **R9 (L).** The spec-swap edit set is named in §8.

Questions added: **Q-63** PUT of the whole split vs the signed POST / DELETE per assignment (rec. PUT with versions,
and then "must equal 100 or be empty" — Q-56 revisited) · **Q-64** effort split into a CANCELLED phase: its own line
inside the identity (rec. yes) · **Q-65** moving a split solution to REJECTED: warn, not block (rec. warn; its effort
leaves the plan with the headline) · **Q-66** a phase plan read from a baseline's shadows — in scope now? (rec. no:
live only now; the frozen tables make it possible later).
