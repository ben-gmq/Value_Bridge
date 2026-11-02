# Plan — Decisions log (D-17), Phase 2 — 2026-11-02 (awaiting Ben's approval)

**Why this slice:** the smallest Phase 2 module. It changes nothing frozen (design §6 row 35: `decision` is not a
baseline table), so it needs no shadow tables or hash-spec bump. Change requests need it, because `decide_cr` writes
a DECISION row (§7.13).
**Runner-up:** Benefits (D-14). It needs two frozen tables, their shadows and a hash-spec bump on main, so it is a
heavier slice.

## Scope
- In:
  - The `decision` table, per design §5.3. It is append-only: a reject trigger, no UPDATE or DELETE grant for
    `vb_app`, and no soft delete (A-41).
  - `DEC-0001` numbers. The DEC series is already seeded by `create_project`.
  - `record_decision` (POST).
  - The decision log (GET): chronological, filtered by dimension.
  - Correcting a decision: a new row with `supersedes_decision_id`.
  - Screens: the log, a record dialog, and a decision page with "Correct this decision".
  - The `PM_DIMENSION` code list (seed it if it is missing).
- Out:
  - The CR `decide` route (that comes with Change requests).
  - Any control rule over decisions.
  - Importing decisions.

## Pieces
- **A — backend:**
  - Migration 0084: the table, the trigger, the grants.
  - The model, the service, the routes, and their tests.
  - The trigger is the purgeable kind, so `purge_project` can still delete a project's decisions (law 1).
- **B — screens:**
  - Log, dialog and page, with `en.decisions.json`.
  - Links through `links.js`, and API calls through `scope.js`.
- **C — docs:** design and history (DC-n decisions), and a CLAUDE.md deploy note.

## Questions for Ben (recommendation first)
1. Is the log always on, or does it get its own component switch? Recommend always on, as the design says (no
   component).
2. May a decision be corrected twice? Recommend that only the latest in a chain can be corrected (one successor
   each).
3. Is "the analysis it was taken against" free text, or picked from the project's control rules? Recommend
   optional and picked.
4. "Decided on": the meeting date (never in the future, today by default) or the moment it is typed? Recommend the
   meeting date. The row's created time keeps when it was typed.
5. Should promoting a risk also write a decision? Recommend no: a decision is a person's act (RK-7 spirit).

## Migration
One migration, **0084**. This task may not take a migration number until Ren or Ben grants the claim.

## Risk grade and review
- Riskiest concern, **Grade 1**: a decision record that could be edited or deleted destroys the original reasoning.
  Proof: tests that UPDATE and DELETE fail at the database as the app and as the owner, and that only the scoped
  purge deletes. No mutation harness (that would be its own task).
- Rest Grade 2 (log, filters) and Grade 3 (screens).
- Reviews:
  - apple: the schema.
  - design-auditor: two rounds on the slice spec.
  - sara: the code (it touches the migration chain and grants).
  - ui-verifier: the screens.

## Done means
- Full suite (`-n 6`) green on the merged commit, with the commit named. Lint and build clean.
- ui-verifier passes on the log, record, correct and filter checks.
- sara reports no CRITICAL or HIGH.
- Design and history are updated in the same commit.
