# Wave 1g — code-list maintenance: build plan (night batch, 2026-10-16)

Builds the approved spec `docs/slice1g_spec.md` (§1–§16; G-1…G-5, D-71). Stacked on access slice A on branch
`ren/2026-10-16_value-bridge-remaining-and-spec-list`; not merged.

## What a person can do when it lands
- Settings → **Code lists**: every list the project uses, its company values, the project's own wording, hidden
  values, and which values are in use.
- A **project admin** renames a value for this project, adds a project-only value, retires it, hides a company value
  the project doesn't use, and unhides it. Existing records follow a rename (G-3).
- A **platform admin** does the same on the company library (Administration → Code lists), including adding a new FR
  type or complexity, which adds unconfirmed rate cells to every live project (G-4).
- Pickers leave hidden values out; a record that already holds one still shows and saves it.

## Grade
**Grade 2** (spec §13): a wrong rename or re-point mislabels figures in exports and the next baseline — recoverable
(retiring the override re-points back), noticed by the people reading the list. Proven directly: criteria 1–19 as tests
through the API, with the re-point checked against the database on every code column. Left uncovered on purpose: a
true concurrent save during a re-point (criterion 19) is proven by the lock order, not by a two-connection race test.

## Steps (one commit each)
1. **Migration 0059** `project_code_visibility` (+ model, `models/__init__`), downgrade refuses while rows exist.
2. **Service `code_lists.py`** — the one owner of code-list writes: list (company / project), add, relabel, reorder,
   behaviour (refused while in use, Q6), retire / restore, override (R10: same behaviour), hide / unhide; the
   **re-point** (R1, R11–R13), its FK list discovered from the catalog with the explicit exclusion list (R12 +
   `project.status_code_id`, G-2) and a test that fails on an FK in neither; **`PINNED`** (§7.4, R4) and its grep test;
   R6/G-4 rate-cell seeding; `resolve(for_picker=)`.
   **Lock (N3, narrowed):** `validate_required_code` takes the project row FOR SHARE before resolving, and the re-point
   takes it FOR UPDATE — every write that picks a code goes through `validate_required_code`, so a save during a
   re-point waits and lands on the new row, without adding a lock to every EDIT write (which could deadlock writes that
   later take the project row FOR UPDATE). Recorded as my decision in the morning report.
3. **Routes** per spec §9, one guard each; `ROUTE_COMPONENTS` untouched (no component).
4. **Screens**: Settings → Code lists (project) and Administration → Code lists (company); `useCodes` gains
   `options(current)` (hidden values left out, the record's own value kept, R5) and every picker uses it.
5. **Checks**: Sara (touches `code_master`, which every lookup depends on), full suite on 4 workers, browser check,
   `rules-check-drift`.

## Size
About 2 working days, 1,200–1,600 lines (the picker sweep touches ~25 screens lightly).

## For the morning list
- Migration 0059 round-trip (down/up) — a downgrade asks Ben.
- Merge, stacked after slice A.
