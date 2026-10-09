# Slice 5: Solutions and BR → Solution links

**Date:** 2026-10-09 · **Author:** Lilly · **Status:** rev 3, design review round 1 applied; Ben's rulings S5-1…S5-4 (2026-10-09)
**Builds on:** design D-7, §4.3 (`link_br_solution`), §4.4 (`create_solution`), §5.3 SOLUTION /
BR_SOLUTION, §5.4.15 (`FK_LIVENESS`), §6.1 rows 19–20, §7.5, §9 (routes), §14.3 (nav), criterion
10 (first half). Schema: `docs/slice5_schema.md` (apple). Where this file and the design
disagree, the design wins.

## 1. Purpose
A consultant records the project's **answers** — each one a Solution in one of five categories
(Organization & rules / People / Process / Data / Technology) — and says which business
requirements each answer addresses, with a note on how much of the requirement it covers. This
is the layer FRs, applications, benefits and phases hang off later; it is useful on its own
because it shows which requirements have no answer yet and whether the answers are all
technology.

## 2. Scope
**In:**
- Solution register: list (with category, status, linked-BR count), create, edit, retire, restore.
- Solution detail page: its fields, plus a **Requirements** panel: link a BR with a coverage
  note, unlink.
- BR detail page: a **Solutions** panel, the same link from the other side.
- Nav: **BR–FR map** opens the solution register (the section's own description is "Solutions,
  functional requirements and traceability"); the map itself arrives with FRs.
- Retire rules (§3.2) and the `code_master` lookups `SOLUTION_CATEGORY` / `SOLUTION_STATUS`
  (already seeded).

**Out (later slices):** function requirements and the D-34 suggestion clearing (no FRs exist
yet — the hook point is named in §4), applications, `solution_matrix`, traceability, benefits,
phases, solution import (one more `Target` in `TARGETS`), baseline shadows (the baseline slice
generates them for every frozen table, these two included).

## 3. Keystone grain
- `solution` — one row per transformation answer within one project. Business key
  `solution_number` (`SOL-0001`, minted at save by `numbering.next_number`; the `SOL` series is
  already seeded by `create_project`).
- `br_solution` — one row per (BR × solution) pairing in one project; `coverage_note` is the
  fact about the pairing. Soft-deleted on unlink and restored on re-link, like `br_data_entity`.

### 3.2 Retire
- **Retiring a solution** that has live links → 409 naming the BRs (generic `FK_LIVENESS`).
  Unlink first. Restore needs nothing.
- **Retiring a BR** (only ever with its process step): its live `br_solution` rows retire with
  it and restore with it — `BrSolution` joins `step_retire.OWNED_BY_BR`, shown in the step's
  retire preview. **S5-1 (Ben).** If the solution was retired meanwhile, the step restore asks for it first (A-SR-5, DR1-P3).
- Linking to a retired BR or retired solution → 409 "restore it first".

## 4. Business Requirement grid

| Function | Entity | Use | Logic → output |
|---|---|---|---|
| `create_solution` | `solution` | C | EDITOR. Name required; `category_code` required from `SOLUTION_CATEGORY`; `status_code` defaults to `PROPOSED`. Number minted at commit |
| `update_solution` | `solution` | U | EDITOR. An explicit `EDITABLE` allow-list: name, description, category, status, benefit_note, effort_note — never `project_id`, `solution_number`, `created_by`, `row_version` (DR1-S2, law 6). `row_version` → 409 on mismatch. Only changed fields are sent |
| `list_solutions` | `solution`, `br_solution` | R | REVIEWER. Live by default, `include_retired` optional. Each row carries its live BR count |
| `retire` / `restore` | `solution` | U | EDITOR. The generic `_retire_and_restore` routes; 409 with dependents named |
| `link_br_solution` | `br_solution` | C | EDITOR. The solution is fetched **scoped to the BR's project first** — another project's solution is 404 whatever its state, and no name leaks (DR1-S1). Then the SR-5 locks, the solution locked before its liveness check (DR1-D1), and the pair row locked before branching (DR1-P4). Both ends live, else 409. Duplicate live pair → 409. A retired pair is restored with the new note. **Hook for D-34:** this is where `suggested_br_id` clears once FRs exist |
| `edit_coverage_note` | `br_solution` | U | **S5-3.** EDITOR. `PATCH /business-requirements/{id}/solutions/{link_id}` with `coverage_note`, `row_version` (409 stale). The old note goes into the audit detail |
| `unlink_br_solution` | `br_solution` | D (soft) | EDITOR. `row_version` checked |
| `consistency_check` | `br_solution` | R | Gains `brsol_under_inactive`: live pairings whose BR or solution is retired. Should always be 0 — the independent proof the locks hold (DR1-D1) |
| `list links` | `br_solution` | R | REVIEWER. From a BR: its solutions (number, name, category, note). From a solution: its BRs (number, step name, note) |

## 5–6. Logical / physical
`docs/slice5_schema.md`. One migration per table (0021 `solution`, 0022 `br_solution`), on
`main`, reversible.

## 7. Function — where it lives
- `services/solution.py` (new): create, update, list, link, unlink, list_links.
- `routers/scope.py`: the routes of §9 — `GET/POST /projects/{id}/solutions`,
  `GET/PATCH /solutions/{id}`, retire/restore, `GET/POST/DELETE /business-requirements/{id}/solutions`,
  `GET /solutions/{id}/business-requirements`. One guard each (`project_ctx` /
  `object_guard(Solution, …)`).
- Frontend: `features/solutions/{SolutionsPage,SolutionPage}.jsx`, a shared link panel used by
  both detail pages, `api/scope.js` (`solutionApi`), `app/links.js`, `i18n/en.solutions.json`.
  Edit controls hide through `useCanEdit`.

## 8. Risk grade and test depth
**Grade 2**, because a wrong or missing link puts a wrong traceability statement in front of a
client, and it is correctable once noticed. The riskiest concern is **a link that crosses
projects or is made by someone who may only read** — that is the existing guard and
composite-FK pattern, proven directly (no mutation harness: it is not new access logic).
Proposed proof:
- pytest: create/number/edit/409 stale; PATCH carrying `project_id`/`solution_number`/`created_by`/
  `row_version` changes none of them; category required and resolved via `code_master`;
  link/unlink/relink (previous note in the audit detail); duplicate 409; cross-project link
  refused **including a retired solution of another project → 404 with nothing of it in the body**;
  solution-retire 409 text names the BRs; step restore refused while its pairing's solution is retired;
  `brsol_under_inactive` finds a planted orphan; reviewer refused; invisible
  project 404; retire solution with links 409; BR retire with its step takes its links and
  restore brings them back; route-guard test stays green.
- Frontend: Create disabled while its request is in flight (DR1-P2).
- ui-verifier: register → create → link two BRs from the solution page → see them on the BR
  page → unlink → retire refused while linked → retire after unlinking.
- **Deliberately uncovered:** two users linking the same pair at the same instant (the unique
  index decides; the loser gets a 409/500 race, not tested), and screen layout below tablet width.

## 9. Acceptance
1. A PEOPLE solution can be created and linked to two BRs, and carries no FRs (criterion 10,
   first half — the traceability half waits for the report).
2. Numbers run `SOL-0001`, `SOL-0002` per project, never typed.
3. A BR shows the solutions that answer it, and a solution shows the BRs it answers, each with
   its coverage note.
4. A solution cannot be linked to a BR of another project, and a reviewer sees no edit controls
   and is refused by the API.
5. Retiring a linked solution is refused, naming the BRs; retiring a step retires its BR's
   links and restoring it brings them back.

## 10. Design review — round 1 of 2 (design-auditor, 2026-10-09)
8 findings: 0 HIGH, 4 MEDIUM, 4 LOW. Codes are `DR1-<lens><n>`.

| Id | Rating | Finding | Disposition |
|---|---|---|---|
| DR1-S1 | MEDIUM | Link check order could leak another project's solution name | **Fixed** — project-scoped fetch first, 404 |
| DR1-D1 | MEDIUM | Live link under a retired solution if the solution isn't locked; no independent check | **Fixed** — lock then check; `brsol_under_inactive` consistency line |
| DR1-P1 | MEDIUM | Solution-retire 409 would list SOL numbers, not BRs | **Fixed** — two-ended label |
| DR1-P2 | MEDIUM | Double-submit creates duplicate solutions | **Fixed** if Ben takes Q-1 (live-name UK), plus in-flight button |
| DR1-P3 | LOW | Step restore forces a deliberately retired solution back | **Ben** — with Q-3; tested either way |
| DR1-P4 | LOW | Concurrent relinks: last note silently wins | **Fixed** — FOR UPDATE on the pair row |
| DR1-D2 | LOW | Relink overwrites the note with no history | **Fixed** — previous note in the audit detail |
| DR1-S2 | LOW | Nothing in the DB pins `project_id` before a link exists | **Fixed** — allow-list + test |
| — | (side note) | Same unlocked-target pattern may exist today in `br_data_entity` vs entity retire | **Tracked** — VB-009 (unverified) |

## 11. Rulings (Ben, 2026-10-09)
- **S5-1** A BR's solution links retire and restore with its step (`OWNED_BY_BR`).
- **S5-2** A REJECTED solution can be linked; the link shows its status, and later coverage reports do not count it as an answer. No status rule in this slice.
- **S5-3** A live link's coverage note is edited in place; the previous note is kept in the audit detail.
- **S5-4** `SOLUTION_CATEGORY` is seeded `is_system=True` (projects cannot rename or retire the five).
- Adopted on apple's recommendation, in the approved plan: Q-1 live-name unique per project; Q-2 surrogate PK + full UK `(br_id, solution_id)`; Q-4 PROPOSED on create; Q-6 keep `category_category`; Q-7 D-34 hook waits for FRs; Q-8 / Q-10 wording fixes; Q-9 notes are free text.
