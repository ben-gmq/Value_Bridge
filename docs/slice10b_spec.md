# Slice 10b: Business requirement ↔ function requirement, direct (D-52)

**Date:** 2026-10-12 · **Author:** Lilly · **Status:** rev 1 — Ben's rulings S10b-1…S10b-3 (2026-10-12); design review round 1 applied (13 findings, 1 HIGH, all accepted)
**Builds on:** D-52 (§1a "Ben's front-end review — 2026-10-12"), which reverses D-7's derived BR→FR; D-28 (FR without a
solution); D-37 (components); D-53 (BR edited inside the function chart, Slice 10a); S5-1, S5-3, S6a-1, S6b-3, S8-1.
Schema: `docs/slice10b_schema.md` (apple), **all 21 [Q-n] accepted as recommended** (S10b-1). This file is the
function view of that schema; it does not restate it. Where this file and the design disagree, the design wins.
Built on Slice 8 (the freeze, head `0048`) and Slice 10a (merged `f7bc276`).

## 1. Purpose
A consultant maps each business requirement straight to the function requirements that deliver it, from the BR
itself, without having to invent a solution first. Where the project uses solutions, the consultant can still say
which of the BR's solutions an FR delivers; that solution is one tag on the FR, so the FR's effort counts once,
toward one solution, however many BRs it serves.

Today the mapping only exists as a path BR → Solution → FR. A project that does not use solutions cannot map at
all, and an FR serving a BR through no solution is invisible to traceability. After 10b the stored link is the
mapping, and the solution is optional.

## 2. Scope
**In:**
- the link table `br_function_requirement` with a coverage note, its baseline shadow, and the backfill of every
  live mapping that exists today (schema §1, §3, §5);
- the **baseline integrity fix** (Q-14): hash spec 2, so every baseline frozen before 10b still verifies;
- link, unlink, note, solution-tag and "new FR from the BR" routes on the BR (schema §1.2);
- the tag rule and the drift warnings (schema §2);
- every read that changes (schema §6.1–6.5, 6.10–6.12, 6.14): the view, the BR's FR list, the interface list's BR
  column, the FR register filters, the effort summary's untraced line, the priced diff, the consistency lines;
- **S10b-3 step 1:** the freeze's audit event records *which* rows each open warning was about, not only its name;
- the BR panel (function chart) and BR page: a "Function requirements" section to link, create, note, tag and unlink;
- removal of the never-built D-34 remnants (schema §3.5).

**Out:**
- reports not yet built (`br_coverage_report`, `fr_traceability_matrix`, `fr_unlinked`, `analyse_cr_impact`):
  schema §6.6–6.9 is their obligation when they are built (wave 1f);
- the FR import (wave 1e). It will create links from BR numbers (D-34 retired, Q-10);
- **S10b-3 step 2:** turning a warning into a tracked issue with an owner and a status. It belongs to the Issue
  module, whose spec must include it;
- effort summed by BR (Q-18: never — an FR serving three BRs would count three times).

## 3. Keystone grain
`br_function_requirement` — **one row per pairing of one BR with one FR that serves it, in one project, forever.**
Unlink soft-deletes the row; linking the pair again restores the same row (S1-7), so a baseline diff sees one
identity across unlink and relink. The solution is **not** in the grain: it lives once on the FR (`solution_id`).

## 4. Business Requirement grid

| Function | Entity | Use | Logic → output |
|---|---|---|---|
| `link_fr` | `br_function_requirement` | C/U | EDIT, component FUNCTION_REQUIREMENT. FR fetched scoped to the BR's project (404 otherwise). Lock order step → BR → FR (share) → link row. New pair inserts; live pair 409; dead pair relinks. Response warns `fr_solution_outside_its_brs` if the FR's tag answers none of its BRs (Q-6) |
| `update_link_note` | `br_function_requirement` | U | EDIT. `row_version` → 409; previous note in the audit detail (S5-3) |
| `unlink_fr` | `br_function_requirement` | U (soft) | EDIT. `lifecycle.unlink`. Response names any FR whose tag now answers none of its BRs; never clears the tag (Q-4) |
| `set_solution` | `function_requirement.solution_id` | U | EDIT, components FUNCTION_REQUIREMENT + SOLUTION (clearing needs FR only). From the BR row: must be a live solution **of this BR** (422 otherwise, with the "Add SOL-x" fix offered by the screen, Q-5). From the FR register: must answer **at least one** of the FR's BRs; any solution if it has none (Q-3). FR `row_version` → 409. `RECORD_UPDATED` with the previous solution number |
| `create_fr` (+ `br_id`) | `function_requirement`, `br_function_requirement` | C | EDIT. Optional `br_id` creates and links in one transaction (Q-20). No link → `no_br` warning (replaces `no_solution`, Q-17) |
| retire FR | `function_requirement` | U (soft) | **409 naming the BRs while live links exist** (Q-13, S10b-2: no silent loss). Unlink first |
| step retire / restore | `br_function_requirement` | U (soft) | Owned by the BR, tier 2 beside `br_solution` (Q-12). Restore brings the links back, all or nothing |
| `frs_of_br` | `v_br_function_requirement` | R | VIEW. One row per live link, solution tag nullable, `tag_answers_this_br` |
| `list_frs` | `function_requirement` | R | VIEW. `unlinked=true` = no live BR link; `unassigned=true` = no solution; rows carry `br_count` |
| `effort.summary` | `function_requirement` | R | By solution as today (UNASSIGNED grows, correctly); adds an informational `untraced` count and days (Q-18) |
| `priced_diff` | baseline sides | R | `untraced` / `unassigned` flags per line; `untraced_days` / `unassigned_days` totals; exposed effort walks BR → link → FR (Q-17) |
| `consistency_check` | — | R | `brfr_under_inactive` (blocks the freeze); `fr_solution_outside_its_brs` (warning, never blocks, Q-4) |
| `freeze` | `baseline`, `audit_event` | C | The new entity freezes when FUNCTION_REQUIREMENT is on (Q-15). `BASELINE_FROZEN` keeps `warnings` and gains `warning_detail` — the rows behind each warning (S10b-3) |
| `verify` / `diff` | baselines | R | Hash spec 2: an entity unknown at a baseline's spec is skipped, so old digests are unchanged (Q-14). A v1 side's links are derived from its frozen solutions and matched on `(br, fr)`, so the first diff after 10b shows no false ADDED rows |

## 5–6. Logical / physical
`docs/slice10b_schema.md`. Migrations **0049** (table), **0050** (shadow + immutable guards), **0051** (backfill
with a count assertion, one `BR_FR_BACKFILLED` audit event per project, view replaced). Additive upgrades; each
downgrade refuses rather than destroy links or frozen rows written after it (Q-21). Nothing pauses under law 10.

## 7. Function — where it lives
- Backend: `models/function_requirement.py` (`BrFunctionRequirement`); `services/function_requirement.py` (link,
  note, unlink, `set_solution`); `services/{freeze_set,baseline,baseline_shadow,consistency,effort,step_retire,
  lifecycle,components}.py`; routes in `routers/scope.py`; `tests/test_route_guards.py` `ROUTE_COMPONENTS`.
- Frontend: `features/requirements/BrEditor.jsx` (the BR section in the process panel and the BR page), the FR
  register filters, the effort summary line, `api/scope.js`, `i18n/en.<area>.json`. Edit controls through
  `useCanEdit`; the solution picker hides when SOLUTION is off (`useComponents`). Link actions are immediate, like
  solution linking today — they are not part of the panel's one Save (Slice 10a).

## 8. Risk grade and test depth
**Grade 1 for the baseline part, Grade 2 for the rest.**
- **Grade 1 — the hash spec and the backfill.** A wrong digest makes every client-approved baseline report as
  tampered (409 on every read of it); a wrong backfill silently loses or invents scope mappings that baselines and
  the priced diff then carry. Heavy proof, no argument needed:
  - a baseline frozen at spec 1, then the entity added: `verify()` passes, digest byte-identical;
  - a v2 baseline: tampering one frozen link row is detected;
  - backfill count equals the old view's count, per project; step-retired paths come back as retired links and a
    step restore after 10b brings the FRs back; retired FRs are not backfilled;
  - diff v1 → live with no user change shows **zero** link changes; a real link added shows exactly one ADDED;
  - migrations up, down and up again on the test database; each downgrade refuses once a post-migration row exists.
- **Grade 2 — the routes and screens.** A wrong mapping reaches a client but is correctable once seen.
  pytest: link / relink keeps the id / 409 on a live duplicate; cross-project FR 404 identical to a missing one;
  viewer 403, non-member of a restricted project 404; SOLUTION off → link works, tag refused 409 COMPONENT_OFF;
  tag from the BR row with another BR's solution → 422, nothing written; register tag rule "at least one";
  drift warnings name the FRs on unlink, BR_SOLUTION unlink and step retire; FR retire with links → 409 naming
  the BRs; `unlinked` / `unassigned` filters; effort `untraced` line never added into totals; freeze audit carries
  `warning_detail`; route-guard criteria 49 / 49b; the GET-leak test.
- ui-verifier: link an existing FR from the process panel → pick a solution → note → unlink → relink; "New FR"
  from the BR; a 422 shows the "Add SOL-x" fix and the fix works; a project with SOLUTION off shows no picker;
  a viewer sees no controls; FR retire with links shows the refusal naming the BRs.
- **Deliberately uncovered:** two editors tagging one FR at once (row_version decides); phone width.

## 9. Acceptance
1. Every live BR → Solution → FR mapping that existed before 10b exists after it as a direct link; none is
   lost and none invented (count proven per project).
2. Every baseline frozen before 10b still verifies, and its first diff against live shows no false link changes.
3. A project with Solutions switched off can map BRs to FRs.
4. An FR's effort counts toward exactly one solution, however many BRs it serves; effort is never summed by BR.
5. From the BR (in the function chart), a consultant can link an existing FR, create a new one, write a note,
   pick which of the BR's solutions the FR delivers, and unlink — and cannot pick a solution the BR does not have.
6. An FR still linked to BRs cannot be retired; the refusal names the BRs.
7. A tag that drifts outside its FR's BRs is warned about — on the action, on the control panel, and in the
   freeze record with the rows named — and never blocks the freeze or changes silently.

## 10. Design review round 1 of 2 (design-auditor, 2026-10-12)

13 findings (1 HIGH, 6 MEDIUM, 6 LOW). All accepted and sent to the build, which ran in parallel with the review
(Ben, 2026-10-12: "start doing the spec and also building").

| Id | Rating | Finding | Disposition |
|---|---|---|---|
| DR10b-P1 | HIGH | Only side "a" derived its links, so v1→v1 and newer→older diffs showed every link REMOVED | **Fix** — derive each pre-v2 side independently (`derived_sides`), always match the link on `(br_id, fr_id)`; tests v1→v1, v2→v1, v1→v2, v1→live |
| DR10b-D1 | MED | Derived v1 links not in the side cache, so `priced` / `_exposed` read an empty shadow (false `untraced_days`) | **Fix** — derive once per side into the cache; every reader uses the cache |
| DR10b-D2 | MED | A coverage note added after a v1 baseline is hidden by pair matching | **Fix** — a derived note is NULL; a non-null note on the other side is CHANGED |
| DR10b-D3 | MED | `_e()` hard-codes v1 and the docstring states the old rule, so a future entity re-breaks every old baseline; a self-referential digest test proves nothing | **Fix** — `_e(since=)`, a module assert pinning today's 24 v1 entities, docstrings corrected, golden digest from a literal copy of the pre-10b algorithm |
| DR10b-P2 | MED | Step restore's same-stamp read could revive a link under a retired FR, or restore a row twice | **Fix** — merge and dedupe before the parent and component checks |
| DR10b-P3 | MED | `create_fr` + `br_id`: tag could bypass the BR rule; no BR lock; cross-project `br_id` → 500 | **Fix** — create, then the same `link_fr` (scoped 404, locks); both ids sent → the BR-row rule (422) |
| DR10b-S1 | MED | The tag PUT could write through a dead or stale link | **Fix** — lock the link FOR SHARE, require it live and on this FR, else 409; unlink locks FOR UPDATE first |
| DR10b-S2 | LOW | Drift warnings could miss a concurrent tag write (the schema's claim that `solution.unlink` locks first is not true in code) | **Fix** — both unlinks lock the row first and compute drift after the flush; the register path locks the answering BR_SOLUTION |
| DR10b-S3 | LOW | `fr_solution_outside_its_brs` would block the freeze unless listed in `WARNINGS` | **Fix** — added to `WARNINGS`; test a freeze with a drifted tag |
| DR10b-S4 | LOW | `warning_detail` unbounded and carrying client names into the append-only audit, which a purge cannot clean | **Fix** — per warning `{count, numbers}` (first 100), numbers only, no names |
| DR10b-D4 | LOW | v1 baselines show "0 links" | **Fix** — `null`, "not frozen at this spec" |
| DR10b-P4 | LOW | 0051 not re-runnable after its downgrade; writes between the count and the insert | **Fix** — SHARE locks before the count, insert `NOT EXISTS`, assert existing + inserted = view; event only where rows were inserted. **Deploy note:** stop the API, upgrade, then start the new code |
| DR10b-Q | — | Two product questions: (1) a tag move that still answers ≥1 BR but leaves another BR's solution — warn? (2) v1→v1 links derived or omitted? | (1) **No warning** — the move is legal and deliberate; the control-panel lines stay the record. (2) **Derived** (DR10b-P1) — consistent with v1→live. Lilly, under S10b-1 |
