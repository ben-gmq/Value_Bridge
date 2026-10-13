# Slice 10d: the business-functions screen, ranked (D-63) — one RACI per process (D-64)

**Date:** 2026-10-13 · **Author:** Lilly · **Status:** rev 1 — Ben's rulings D-63, D-64, S10d-1; design review round 1 applied (11 findings, 3 HIGH)
**Builds on:** the /impeccable critique of 2026-10-13 (23/40, snapshot in `.impeccable/critique/`), D-63, D-64,
S10d-1 (§1a "Design critique of the business-functions screen"); schema `docs/slice10d_raci_schema.md` (apple, all six
[Q-n] accepted). D-46, D-49, D-51, D-52, D-53. Built on main `3430b1d` (10b merged). **Comes before 10c**, whose
additions (performer without DFD, attribute expander, plain guidance) then land in this layout.

## 1. Purpose
Ben: *"terrible … items all over the place … labels quite small and not visible … decide what the most important thing
is."* The process panel stacks the old process panel, the whole BR page, the DFD facts and the FR section in one
~1,900 px column: two RACI lists, two data lists, two Retire buttons, the FR list twice, 10.5 px labels, 13 font sizes,
~19 visible actions. 10d ranks it around what a consultant does most — name the process and write what it must do,
then say who does it, who is Accountable, what data goes in and out and what starts it, then move to the next one —
and shows each fact once.

## 2. Scope
**In:**
1. **Layout (D-63).** Tree and panel side by side from 900 px, each in its own sticky, independently scrolling column
   (`clamp(340px, 32%, 440px) | 1fr`); the selected tree row stays in view. Below 900 px, one at a time: the tree, or
   the panel with "← Chart". Tree rows: full names with ellipsis + tooltip; the BR chip and flow icon show on hover,
   focus or selection only.
2. **Panel header (sticky):** level badge · code · parent path (one muted line); the **process name** as an editable
   20 px heading; on the right the BR number (link to the BR page), Draft/Confirmed as a segmented control, and a
   **⋯ menu** holding: this is a process (with the consequences confirmation from 10c §2.3), Retire step…, Retire
   requirement…, Restore, Open the requirement page.
3. **Primary — the requirement:** "Requirement" (statement, 16 px, ≥ 2 rows), "Business logic" (≥ 3 rows), "Expected
   output" (one line). Static 13 px/600 labels above every field — no floating labels in the panel.
4. **Secondary — "How it runs" (saves as you go):** a 2×2 grid of tiles — **Performed by**, **Started by**,
   **Accountable** (the one A + count of R/C/I), **Data** (in n / out n). Empty: muted "Not set · Set" and a small
   amber dot on the label — no Alert boxes. Clicking a tile opens its editor full width below the grid, one at a time,
   with Done: the existing PerformerPanel, TriggerPanel (row wraps), BrRaci, CrudGrid. Performer/Started by tiles show
   only where they can be written today (DFD on); 10c widens the performer.
5. **Tertiary — collapsed sections** with count and one-line summary, open state remembered per user: **Delivery**
   (solutions + function requirements, 10b's controls unchanged inside — *pending D-66, recorded 2026-10-13: split into Solutions and Function requirements, ranked above the other collapsed sections; a follow-up, not this slice*), **External parties**, **Description**
   (Purpose and Data processing — see §11), **Supporting systems** (as-is only).
6. **Removed from the panel:** the Coverage tile (stays on the BR page); the step's own RACI panel and step Data
   in/out block for to-be processes (the BR's RACI and the CRUD grid are the single editors — CRUD already writes the
   step's data); the second Retire button; always-on help paragraphs (behind (i) tooltips).
7. **Save:** the footer appears only when the text form has unsaved changes or an error ("2 unsaved changes"); Discard
   is neutral; Ctrl/Cmd+S saves; "Save & next process". Immediate-save zones say so and flash a brief ✓.
8. **Type and kit:** a 4-step scale in the panel (20 / 16 / 14 / 12.5); a `GroupHeader` (14/600, sentence case) in the
   kit beside `SectionLabel`; the theme's shrunk input label ≥ 12.5 px so other screens gain too.
9. **One RACI (D-64, S10d-1).** Migration **0052** per the schema doc: live to-be step roles merged into their BR
   (BR's Accountable wins, `RACI_MERGED_TO_BR` audit event), then retired; roles of steps retired with their BR copied
   as retired BR rows with the same stamp; generated column `node_live_set` + composite FK so a live step role exists
   only on an as-is step. Code: `raci.link` 409 on a to-be step; `copy_set` maps step roles ↔ BR roles;
   `step_retire.restore` skips to-be step roles; `seed_demo` puts its R on the BR. **As-is processes** keep the step
   RACI as their Accountable tile's editor.

**Out:** structured BR lines (slice 11); 10c items (menu entries for Organisation and Systems, performer without DFD,
attribute expander, assigned-only projects); the BR deep-link page layout (only its Coverage tile is kept); the DFD and
ERD canvases.

## 3. Keystone grain
No new table. `bfc_node_org_role` narrows to **one row per (as-is process step × org role × RACI kind)**; a to-be
process's roles are `br_org_role` rows only (D-64).

## 4. Business Requirement grid

| Function | Entity | Use | Logic → output |
|---|---|---|---|
| merge (0052) | `br_org_role`, `bfc_node_org_role`, `audit_event` | C/U | vb_owner. Blocks with a list if a live to-be step role has no live BR (Q-5). Merge; BR's A wins; retire merged step rows; same-stamp copies for retired steps; FK added last |
| `raci.link` (step) | `bfc_node_org_role` | C | EDIT. 409 on a to-be step ("Roles of a to-be process are recorded on its requirement") |
| `raci.link` (BR) | `br_org_role` | C | unchanged (one Accountable) |
| `copy_set` | both | C | as-is step roles → the to-be BR's roles; to-be BR roles → as-is step roles |
| step restore | both | U | to-be step roles skipped; BR roles restored with the BR |
| panel reads | existing routes | R | VIEW. No new route; tiles read what the editors already load |

## 7. Function — where it lives
- Backend: `alembic/versions/0052_*.py`; `services/raci.py`, `services/bfc_set.py`, `services/step_retire.py`,
  `seeds/seed_demo.py`; tests for the migration (up, down, re-run), the merge cases and the 409.
- Frontend: `features/processes/{ProcessesPage,NodePanel,chartKit,StepDfd,StepSections}.jsx`,
  `features/requirements/{BrEditor,BrRaci,CrudGrid,BrFrLinks,BrSolutionTags}.jsx`, `components/kit.jsx`
  (`GroupHeader`, fact tile), `theme/theme.js` (label size), i18n `en.processes.json`, `en.requirements.json`.

## 8. Risk grade and test depth
**Grade 1 for 0052** — it moves accountability records that baselines freeze and clients sign; a wrong merge silently
changes who is Accountable. Heavy proof: per-project counts before/after (every live to-be step role is on its BR or
listed as a lost-Accountable conflict); BR's A wins and the loser is in the audit event; a to-be step with no BR blocks
with the list; retired-with-BR roles come back on restore; re-run after downgrade adds nothing; old baselines still
verify; the old-baseline diff shows each moved role once. **Grade 3 for the layout** — visible, harmless if wrong.
- pytest: the above + `raci.link` 409 + `copy_set` both directions + the GET-leak and guard criteria.
- lint + build; `detect.mjs` over the changed files.
- ui-verifier (once login is possible) or Ben: 1440 and 900 and 400 px; the tree keeps its place while the panel
  scrolls; the four tiles open their editors; collapsed sections remember state; ⋯ menu actions with confirmations;
  Ctrl+S; Save & next; viewer sees no controls; side by side with mockups 01 and 03.
- Re-run `/impeccable critique` after the build; target ≥ 30/40.

## 9. Acceptance
1. Each fact about a process appears once on its panel.
2. The requirement statement is the largest field; no label in the panel is below 12.5 px.
3. Performer, trigger, Accountable and data are readable at a glance without scrolling at 1440 × 900.
4. The tree stays in view while the panel is edited; below 900 px the two never stack.
5. A to-be process has one RACI, on its BR; no Accountable is lost in the merge without being named in the audit.
6. Every baseline frozen before 10d still verifies.

## 10. Design review round 1 of 2 (design-auditor, 2026-10-13)

| Id | Rating | Finding | Disposition |
|---|---|---|---|
| DR10d-D1 | HIGH | Retired-history copies could give a retired BR two Accountables, so its step could never be restored (Q-3 broken) | **Fix** — BR-wins applied to the copies too; conflict listed; restore test asserts 200 with one A |
| DR10d-D2 | HIGH | Matching on raw `raci_code_id` misses project-override codes: deploy abort on A, silent duplicate R/C/I | **Fix** — match on org role + resolved behaviour; A conflict decided before restore/insert |
| DR10d-P1 | HIGH | Switching process with unsaved text drops it silently; Save & next could drop a refused BR | **Fix** — Save / Discard / Stay on leaving; Save & next only when all saved |
| DR10d-P2 | MED | Performer and trigger tiles hold half-filled forms that Done / switch / Ctrl+S drop | **Fix** — confirm before dropping; honest caption; accordions keep content mounted |
| DR10d-P3 | MED | No owner for the lost-Accountable list | **Fix** — 0052 prints the list; deploy step: send it to Ben / project leads |
| DR10d-P4 | MED | No lock / deploy order: a running old API fails 0052 or 500s after it | **Fix** — ACCESS EXCLUSIVE lock first; deploy note: stop API, upgrade, start new code |
| DR10d-P5 | MED | The no-BR block is reachable through "Retire requirement" today | **Fix** — read-only pre-check script run before deploy; the menu hides "Retire requirement…" on to-be processes (Q-3 below) |
| DR10d-D3 | MED | Step-5 inserts collide with the grain; re-runs undefined | **Fix** — NOT EXISTS, `not_carried`, no event on a no-op run |
| DR10d-D4 | MED | "Its retired BR" ambiguous after promote/demote/promote | **Fix** — the BR with the event stamp and in the event's rows; else `unplaced` in the event |
| DR10d-D5 | LOW | As-is Data tile had no editor | **Fix** — as-is: Accountable → step RaciPanel, Data → StepData |
| DR10d-S1 | LOW | Pre-10d restore without the chart skip → 500 | **Fix** — skip by the step's chart; 409 before relink; test asserts 200 |
| DR10d-Q | — | (1) Same-behaviour codes = same role? (2) merge actor? (3) "Retire requirement…" on a to-be process? | (1) **Yes — Ben, 2026-10-13**; (2) NULL, 0051 precedent (Lilly); (3) **hidden on the panel menu and the BR page — Ben, 2026-10-13** (`OFFER_RETIRE_BR = false`) |

**Deploy checklist (10d):** run the pre-check on the target DB and fix its list → stop the API → `alembic upgrade head`
→ start the new code → send 0052's conflict list to Ben.

## 11. Open for Ben
- **Purpose and Data processing** — recommended: Purpose is the description on L1–L4 boxes (shown), and on processes
  both sit in the collapsed "Description" section; Data processing is phased into the slice-11 lines later, its text
  copied, never deleted. Built as recommended unless Ben says otherwise (a one-line change either way).
