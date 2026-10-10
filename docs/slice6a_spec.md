# Slice 6a: Function Requirements, first cut

**Date:** 2026-10-09 · **Author:** Lilly · **Status:** rev 2 — design review round 1 applied (5 findings, 1 HIGH, all fixed); Ben's rulings S6a-1…S6a-4 (2026-10-09)
**Builds on:** D-7, D-27, D-28 (§1a); §4.4 `create_function_requirement`, `link_fr_solution`; §5.3
FUNCTION_REQUIREMENT; §5.4.8; §6.2–6.3; §7.5; §9 FR routes; criteria 9, 10a, 105 (first half).
Schema: `docs/slice6a_schema.md` (apple). Where this file and the design disagree, the design wins.
Built on Slice 5 (`solution`, `br_solution`, merged 364eb3f).

## 1. Purpose
A consultant records the system functions to be built — each one an FR of a type (Form,
Interface, Report, Batch…) — and hangs it under the Solution that needs it. An FR may be
recorded before its Solution exists (D-28): it saves with a warning and shows as unlinked. Through
the Solution, every FR traces to the requirements that Solution answers (BR → FR is derived, never
stored, D-7).

## 2. Scope
**In:** `function_requirement`; the view `v_br_function_requirement`; FR register (list, create,
filter "unlinked"), FR detail page (edit, link/unlink a Solution, retire/restore); "Function
requirements" panel on the Solution page; "Function requirements (via solutions)" read-only panel
on the BR page.

**Out:** complexity and effort (6c, with the rate card — the columns ship NULL, Q-6); applications
and interface detail (6b); `fr_bfc_node`; FR import and with it **the D-34 suggested-BR field**
(**deferred to the import slice, S6a-1** — obligations in §10); FR type maintenance screen.

## 3. Keystone grain
`function_requirement` — one row per FTC-authored system function specification in one project.
Business key `fr_number` (`FR-0001`, minted at save; series already seeded). Name is **not**
unique (S6a-2): two solutions may each have "Approval form" — but a live FR with the same
`lower(btrim(name))` under the same Solution (or among unlinked FRs) returns a `duplicate_name`
warning, and the create form disables submit while in flight (DR6a-P2).

Retire: retiring a Solution with live FRs → 409 naming them (generic FK_LIVENESS). Retiring an FR
needs nothing; restoring one under a retired Solution → 409 "restore SOL-… first". No FR is owned
by a process step.

## 4. Business Requirement grid

| Function | Entity | Use | Logic → output |
|---|---|---|---|
| `create_fr` | `function_requirement` | C | EDITOR. Name required; `fr_type_code` must resolve in `FR_TYPE` (400 otherwise, criterion 9); the behaviour copy is written from the code and verified by the 3-column FK. Solution optional: **project-scoped fetch first** (404 for another project's, live or retired, before any lock or label), then `lock_for_share` and **409 if retired** (DR6a-D1). A REJECTED solution → warning, never a block (S6a-5). Status set to SPECIFIED. No solution → response carries `warnings: ["no_solution"]` (D-28). A solution whose category is not TECHNOLOGY/DATA → warning, never a block (§7.5) |
| `update_fr` | `function_requirement` | U | EDITOR. Allow-list: name, description, acceptance_note, fr_type_code, fulfilment_status_code, solution_id (incl. null = unlink). `row_version` → 409. **A new `solution_id` goes through the same scoped fetch (project from `fr.project_id`, never the body), lock and live check as create** (DR6a-S1, DR6a-D1). Same warnings as create. A change of solution or type writes `RECORD_UPDATED` with the previous solution number / type code (DR6a-S2) |
| `list_frs` | `function_requirement` | R | REVIEWER. Live by default; `include_retired`; `unlinked=true` filter (the D-28 list) |
| `frs_of_solution` | `function_requirement` | R | REVIEWER. FRs under one Solution |
| `frs_of_br` | `v_br_function_requirement` | R | REVIEWER. Derived through BR_SOLUTION; each FR with the Solution it came through |
| `consistency_check` | `function_requirement` | R | Gains `fr_under_inactive_solution`: live FRs whose Solution is retired. Must be empty (DR6a-D1) |
| retire / restore | `function_requirement` | U | EDITOR. Generic routes; restore refuses under a retired Solution |

## 5–6. Logical / physical
`docs/slice6a_schema.md`, as amended by the rulings in §10. Migrations 0023 (table) and 0024 (view).

## 7. Function — where it lives
- `services/function_requirement.py` (new); routes in `routers/scope.py`; `schemas/function_requirement.py`.
- `lifecycle`: `LABELS` and `RESTORABLE` gain the FR.
- Frontend: `features/frs/{FrsPage,FrPage}.jsx`, FR panels on the Solution and BR pages, `api/scope.js`
  (`frApi`), `links.js`, `i18n/en.frs.json`. Edit controls through `useCanEdit`. Nav: the FR register
  sits under **BR–FR map** beside Solutions (two tabs: Solutions · Function requirements).

## 8. Risk grade and test depth
**Grade 2** — a wrong FR or a wrong Solution link puts a wrong vendor-scope line in front of a client,
correctable once noticed. Nothing is priced in 6a (effort ships empty), which is what keeps it out of
Grade 1. Riskiest concern: **an FR linked to another project's Solution** — proven directly.
- pytest: retired Solution in the same project → 409 on create **and** PATCH; `fr_under_inactive_solution`
  finds a planted orphan; PATCH to another project's Solution (live and retired) → 404 identical to a
  missing id; duplicate-name warning; solution move audited with the previous number; tripwire: if
  `function_requirement` ever gains `suggested_br_id`, the test fails unless it is in
  `lifecycle.EXCLUDED_FKS` and the baseline shadow exclusion (DR6a-P1);
  create/number/edit/stale 409; bad type 400; behaviour copy matches the type (and a forged
  mismatch is refused by the FK); no-solution warning; non-technology warning; cross-project
  solution 404 with nothing leaked (live and retired); reviewer 403, outsider 404; allow-list ignores
  `fr_number`/`effort_days`/`complexity_code`/`project_id`; retire Solution with FRs → 409 naming
  them; restore FR under a retired Solution → 409; criterion 10a (1 solution × 3 BRs × 2 FRs = 6
  view rows); BR panel lists FRs only through live links.
- ui-verifier: create unlinked FR (warning shown) → link it to a Solution → see it on the Solution
  page and on each linked BR's page → retire Solution refused → reviewer sees no controls.
- **Deliberately uncovered:** concurrent relink of one FR by two editors (row_version decides);
  phone width.

## 9. Acceptance
1. An FR with no Solution saves with a warning and appears in the "unlinked" filter (105, first half).
2. A bad FR type is refused (9).
3. One Solution answering three BRs and carrying two FRs gives six BR→FR rows (10a).
4. An FR cannot hang under another project's Solution; a reviewer cannot change FRs.
5. A Solution with live FRs cannot be retired; the refusal names the FRs.

## 10. Design review round 1 of 2 (design-auditor, 2026-10-09) and rulings

| Id | Rating | Finding | Disposition |
|---|---|---|---|
| DR6a-D1 | HIGH | FR could be linked to a retired Solution (no check, no lock) and vanish from every trace | **Fixed** — scoped fetch → `lock_for_share` → 409 if retired, on create and update; `fr_under_inactive_solution` line |
| DR6a-P1 | MEDIUM | Spec and schema disagreed on `suggested_br_id`; §10 missing | **Fixed** — Ben deferred it (S6a-1); 0023 ships without it; obligations + tripwire below |
| DR6a-P2 | MEDIUM | Double-submit makes duplicate FRs unseen | **Fixed** — `duplicate_name` warning + in-flight submit |
| DR6a-S1 | MEDIUM | PATCH path's cross-project scoping unspecified | **Fixed** — same scoped fetch on update; PATCH test |
| DR6a-S2 | LOW | Moving an FR between Solutions leaves no trace | **Fixed** — `RECORD_UPDATED` with previous solution / type |

**Rulings (Ben, 2026-10-09):**
- **S6a-1** `suggested_br_id` (D-34) is **deferred to the FR import slice**. That slice must, together:
  (1) add the column + `fk_fr_suggested_br` + `ix_fr_suggested_br`; (2) put the FK in
  `lifecycle.EXCLUDED_FKS` so a hint never blocks a BR retire or an FR restore; (3) clear hints on BR
  retire inside `lifecycle.retire_row` (covers step retire) and in `solution.link` (the `# D-34 hook`);
  (4) exclude it from the baseline shadow and `content_hash`. apple's design for all four is in
  `docs/slice6a_schema.md` §4 and Q-2/Q-4/Q-5. A 6a tripwire test guards (2) and (4).
- **S6a-2** FR names are not unique; duplicates warn.
- **S6a-3** Complexity is not settable until 6c (rate card); `complexity_code_id` and `effort_days` ship NULL with the D-13 CHECK.
- **S6a-4** The FR register is a second tab under **BR–FR map** (Solutions · Function requirements).
- Adopted on recommendation (in the approved plan): **S6a-5** linking an FR to a REJECTED Solution warns, never blocks (mirrors S5-2);
  first status SPECIFIED, any status settable by an EDITOR, no transition rules yet; the view `v_br_function_requirement` is a DB
  view with `project_id` and `security_invoker` (Q-7). VB-005 sara L-2 is extended to `FR_FULFILMENT_STATUS/SPECIFIED`.
