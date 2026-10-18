# Slice 15 — Waves (phasing) and solution dependencies (spec, APPROVED by Ben 2026-10-18)

**Status:** APPROVED by Ben 2026-10-18 with his rulings W-1…W-9 (history §3; Q-55…Q-66 answered, §7). Not built.
**Source of truth:** `docs/VB_design.md` (D-18; PHASE, SOLUTION_PHASE, SOLUTION_DEPENDENCY in §5.3; the wave plan
report; criterion 68), plan row "Phasing and dependency" in `docs/VB_remaining_work.md` (stream B, after 1g; 2.5 days).
**Schema:** `docs/slice15_phasing_schema.md` (apple, 2026-10-16, revised 2026-10-18) — grain, DDL, the no-cycle lock,
the effort split, retire rules, shadows at hash spec 6, migrations 0065–0067. This spec adds screens, routes,
acceptance and grade. Where §9 and the text above it disagree, §9 wins.

**Words (W-1).** A *wave* is a delivery wave within one project — "Wave 1: Finance + Procurement", "Wave 2:
Manufacturing" — never the project lifecycle (analysis, design, build, test), which comes from the MS Project WBS
import. **Every word a user sees says "Wave"**: the rail item, screen titles, labels, the plan, the comparison area,
`en.phasing.json`. Inside the code the names stay `phase` — tables `phase` / `solution_phase` /
`solution_dependency`, models, routes `/phases`, the component code `PHASING` — so the design's entity names hold.

## 1. Purpose
Plan delivery in waves: name a project's waves, say which share of each solution's effort lands in which wave, record
which solutions must come before others, and read a wave plan — effort per wave, what is not yet in a wave, and order
problems — that a signed baseline keeps.

## 1a. Interface
- **Input:** a consultant (EDIT, component PHASING on — W-3) names waves, splits solutions across them by percent and
  links solution dependencies. **FRs are never linked to a wave (W-2):** an FR's effort reaches a wave only through its
  one solution's split, so there is one place to plan per solution — for people and for agents writing through the
  planned MCP server. No import here (the WBS import links to waves later).
- **Output:** a Waves screen (list, reorder, dates, status), each solution's wave split and dependencies on its page,
  and the wave plan (effort per wave + UNPHASED + UNASSIGNED = the effort headline; order warnings).
- **Validation:** a solution's split totals **exactly 100 % or is empty** (W-5), saved whole with every row's version;
  a dependency never closes a cycle (refused with the path); a solution never depends on itself; links stay in one
  project; a new split into a CANCELLED wave is refused.
- **Archive:** audited writes, soft delete, the three tables frozen at hash spec 6.
- **Maintenance loop:** the wave plan's warnings (unphased solutions, a prerequisite in a later or the same wave) are
  reviewed by the engagement's consultant before each freeze; `consistency_check` adds "split not 100" and
  "dependency cycle" proofs.

## 2. Grade
**Grade 1 for the hash-spec bump** (spec 5 → 6, after the Issue module's 4 → 5, merged): old baselines keep verifying —
freeze at 5, migrate, verify old and new, downgrade refusals; specs 2–5 stay pinned (`test_hash_spec_pins`). **Grade 2**
for the effort split and the no-cycle rule (a wrong plan figure someone decides from; the cycle refusal proven with a
concurrent pair, since the advisory lock is the whole guarantee). **Grade 3** for layout.

## 3. Functions (design §4.12)
| Function | Logic |
|---|---|
| waves: add / edit / reorder / retire / restore | code typed, unique while live; two-phase reorder of `seq_no`; retire refused while splits exist |
| split a solution (`PUT`) | the whole split at once: every live row with its `row_version`, plus new rows; total exactly 100 % or no rows (W-5); 0 % rows refused; under a row lock on the solution |
| link / unlink a dependency | advisory lock per project, then a recursive walk; a cycle → 422 naming the path; restore only through link |
| wave plan | effort per wave from current FR `effort_days` × percent; UNPHASED (solutions with no split) and UNASSIGNED lines; order warnings (Q-61) |
| freeze | phase, solution_phase, solution_dependency at spec 6; status copied, not hashed (Q-58) |

## 4. API (`/api/v1`)
`GET/POST /projects/{id}/phases` · `PATCH/DELETE /phases/{id}` · `PATCH …/restore` · `POST /projects/{id}/phases/reorder`
· `PUT /solutions/{id}/phase-split` · `POST /solutions/{id}/dependencies` · `DELETE /solutions/{id}/dependencies/{link_id}`
(scoped to the path solution, 404 otherwise) · `GET /projects/{id}/phase-plan`. Reads VIEW; writes EDIT +
`component="PHASING"`, named in `ROUTE_COMPONENTS`. Route names are internal; nothing on screen says "phase".

## 5. Screens
Rail item **Waves** under Control (component on): the wave list with drag reorder, dates and status; the solution page
gains a "Waves" card (the split, edited and saved as a whole) and a "Depends on" card; the wave plan as a tab. Kit
components; strings in `en.phasing.json`, every visible word "wave"; no mockup exists — nothing faked, Ben sees it in
the browser check.

## 6. Acceptance criteria
1. A split totalling anything but 100 % (and not empty) → 422; an empty split leaves the solution wholly UNPHASED; a
   save built from stale rows, or missing a live row, → 409. 2. Waves + UNPHASED + UNASSIGNED = the effort headline, to
   the cent. 3. A → B → C, then C → A → 422 naming the cycle; two concurrent inserts that would close a cycle — one
   succeeds, one is refused. 4. A solution depending on itself → refused by the database. 5. A prerequisite in a later
   wave (or the same — Q-61) shows a warning in the plan. 6. A wave with splits, or a solution with splits or links,
   cannot be retired (409 naming them). 7. A freeze holds the three tables; a reorder shows as MOVED, a status change not
   at all; a spec-5 baseline still verifies. 8. Component off → writes 409 COMPONENT_OFF, rail item hidden. 9. A
   non-member gets 404 on every phasing route of a restricted project; a cross-project unlink through the path solution
   → 404. 10. A project cannot add, override or hide a wave status; an FTC admin can relabel one (W-4). 11. No screen,
   label, report or comparison area shows the word "phase" (W-1).

## 7. Ben's rulings (2026-10-18, via Ren — history W-1…W-9)
- **W-1** a phase is a delivery wave, shown as "Wave" everywhere; internal names stay `phase` · **W-2** no FR ↔ wave
  link; effort reaches a wave through the solution's split.
- **Q-55** yes, component `PHASING` needing SOLUTION · **Q-56** percent not days; *revisited by Q-63*: exactly 100 % or
  empty · **Q-57** wave statuses pinned and company-only (an FTC admin may relabel); each project names, orders and
  dates its own waves freely · **Q-58** code, name, dates hashed; `seq_no` a position; status copied not hashed ·
  **Q-59** surrogate keys on the link tables (§5.3 rewritten) · **Q-60** retiring a split or linked solution refused ·
  **Q-61** same-wave and unscheduled prerequisites warn · **Q-62** no "volatile areas" until 1f · **Q-63** one PUT of
  the whole split with versions · **Q-64** a CANCELLED wave's effort is its own line inside the identity · **Q-65**
  REJECTED with a split warns, does not block · **Q-66** live plan only.

## 8. Size and order
About 2.5 working days. Builds on `main` after the Issue module (merged 2026-10-18, `8387fcb`): hash spec 6,
migrations 0065–0067 (W-8), taken on `main` in order.

## 9. Revision after design review round 1 (design-auditor, 2026-10-16: 0 high, 4 medium, 5 low)
These rules supersede anything above that disagrees.
- **R1 (M).** Link writers take `lifecycle.lock_for_share` on both solutions before checking they are live (SR-5). A
  split write keeps the schema's `FOR NO KEY UPDATE` on the solution (it serialises two splits of one solution) and
  takes FOR SHARE on each wave. The schema's §5 governs locking except where this section names it.
  `consistency_check` gains freeze-blocking `solution_phase_under_inactive` and `solution_dependency_under_inactive`,
  as `brsol_under_inactive`.
- **R2 (M) — settled by Q-63.** The split is one `PUT` carrying `(solution_phase_id, row_version)` for every live row it
  was built from, plus new rows; a mismatch or an unlisted live row → 409 (the `br_lines.reorder` pattern). Rows left
  out of a valid save retire; rows named again restore (S1-7). The saved set totals exactly 100 % or is empty (W-5).
- **R3 (M).** The wave plan is built from `effort.summary(...)["by_solution"]` (rated, non-rejected, the unassigned
  bucket), so waves + UNPHASED + UNASSIGNED = the headline by construction; a test includes a rejected-but-split
  solution and an unrated FR.
- **R4 (M).** `COMPONENT_ROWS["PHASING"]` probes live waves, splits and dependencies, so PHASING cannot be switched off
  under any of them.
- **R5 (L).** After taking the advisory lock the service asserts the transaction is READ COMMITTED; the concurrent-pair
  test stays.
- **R6 (L).** Displayed wave lines use largest-remainder rounding to the headline's cents, and so does each line's
  per-solution breakdown (UNPHASED included) to its line; criterion 2 tests the displayed figures.
- **R7 (L).** Every body `phase_id` resolves to a live wave of the path solution's project before any write (404
  otherwise).
- **R8 (L).** One status mechanism: `PINNED += (PHASE_STATUS, IN_DELIVERY), (PHASE_STATUS, CANCELLED)`, and
  `PHASE_STATUS` joins `code_lists.COMPANY_ONLY` (W-4, as I-1); the deploy step lists and refuses existing
  project-tier PHASE_STATUS rows or hides.
- **R9 — retired by W-8** (no spec swap: Issue has merged at spec 5).

## 10. Design review of the 2026-10-18 changes (design-auditor, one round on the changed parts: 0 high, 2 medium, 2 low)
Nothing structural; each finding is a build rule here, and wins over the text above.

| # | Finding (rating) | Build rule |
|---|---|---|
| T1 | The split PUT's body contradicts itself: "an unlisted live row → 409" vs "rows left out retire" (MEDIUM, P1) | The body has two parts. `based_on: [(solution_phase_id, row_version)]` must equal the live set exactly (else 409 — the lost-update guard). `rows: [{phase_id, portion_pct}]` is the new split, **unique by `phase_id`** (a wave named twice → 422), totalling 100.00 or empty. Live rows whose wave is not in `rows` retire; a retired row of a wave in `rows` restores; others insert. Criterion 1 covers a duplicate wave and an empty save |
| T2 | Row ids in the body are not tied to the path solution (MEDIUM, S1) | Every `solution_phase_id` in `based_on` must be a row of the path solution, else 404 before any write; criterion 9 gains it |
| T3 | The exact-100 check can run before `numeric(5,2)` rounds (MEDIUM, D1) | A percent with more than two decimals → 422; sums are `Decimal`, never float; the check runs on the values that will be stored |
| T4 | Which rows the CANCELLED-wave rule covers (LOW, P2) | A row in a CANCELLED wave may be **kept at the same or a lower percent**; it may not be inserted, restored or raised. So a user can rebalance other waves without first moving a cancelled wave's effort, and no new effort enters it (the intent of Q-57/Q-64) |
| T5 | Criterion 11 would fail on wording the design seeds (LOW, S2a) | The component label is seeded as "Waves"; COMPONENT_OFF details and `consistency_check` proof names reach the screen through wave wording (`t()` keys), never `phase` identifiers |
| T6 | The schema still described the "≤ 100" backstop (LOW, D2) | Fixed in the schema (§3.5, §6): the proof is `solution_phase_split_not_100` (a live split that is neither 100 nor empty), and an assignment is retired or restored only through the whole-split PUT |
