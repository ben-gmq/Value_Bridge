# Retire a step with its requirement and flows

**Date:** 2026-09-30 · **Author:** Lilly · **Status:** rev 2 (after design review round 1) — for Ben's sign-off
**Revises:** design Q4 / R2-D2 ("a delete with active dependents is refused … nothing cascades",
§7.12) **for process steps only**, on Ben's decision of 2026-09-30 (Slice 3 report, decision 5a).
Everything else keeps refuse-with-dependents.

## 1. Purpose
Let a consultant retire a process step, together with the rows that exist only because of it,
in one confirmed action, and undo it in one action. Today the canvas refuses every step retire,
because every step owns a requirement.

## 2. Doctrine
Playbook soft delete (no hard delete, VB law 1), `row_version` (law 3), audit on every write,
one owner per rule (§9.10). Design §7.12 `lifecycle.retire` / `restore`, and R2-S3's
preview-then-confirm-by-hash pattern (`services/program.py`).

## 3. Grain
There is no new table. One action covers **one process step** plus its **owned set**: the rows
whose meaning ends when the step ends. It is recorded as **one summary audit event**, which
lists every row the action retired. That event is the undo key.

## 4. Business Requirement grid

| Function | Entity | Use | Logic → output |
|---|---|---|---|
| `preview` | `bfc_node` (the step) | R | active process node; a non-process node → 422 (a summary node keeps refuse-with-dependents) |
| `preview` | owned set | R | the step's active `business_requirement` and that BR's active `br_data_entity` / `br_org_role` rows; the step's active `bfc_node_data_entity`, `bfc_node_org_role` and `bfc_node_external_flow` rows; every active `bfc_node_flow` with the step at either end (a self-loop counts once) |
| `preview` | blockers | R | `lifecycle.active_dependent_ids` (new, uncapped, by (table, id)) of **the step and every owned row**, minus the owned ids. A future table hanging off the step, the BR **or any owned link** therefore blocks by default |
| `preview` | — | — | → `{owned: [{table, id, label}], blockers: [...], confirm_hash}`. The hash covers the step's `row_version` and every owned row's (table, id, `row_version`) |
| `retire_with_dependents` | the step + owned set | U | lock the step (`SELECT … FOR UPDATE`) and recompute. Blockers → 409 naming them. A hash that differs from the one sent → 409 "the step changed; review again". Otherwise, in ONE transaction and in dependency tiers (§7), soft-delete every owned row and then the step, **all with one `deleted_at` value**. Writes one `RECORD_DELETED` event per row (each carrying the action id) and one `STEP_RETIRED_WITH_DEPENDENTS` event whose `detail` holds `{action_id, rows: [(table, id)], confirm_hash, deleted_at}` |
| `restore_with_dependents` | the step + listed rows | U | read the step's **latest** `STEP_RETIRED_WITH_DEPENDENTS` event **before any write**. The rows to restore = the listed rows that are still inactive **and** carry that event's `deleted_at` (a row restored or re-retired since is left alone). If any of them has another parent that is still inactive — a far step, a DE, an org role — the restore **refuses as a whole** (409 naming each, "restore these first"), per A-SR-5. Otherwise it restores everything in one transaction, in reverse tiers. One `RECORD_RESTORED` per row, plus `STEP_RESTORED_WITH_DEPENDENTS` |
| plain `restore` of a step | `bfc_node` | U | **refused (409)** when the step's latest retire was a with-dependents one: "use Restore with its requirement and flows". The plain path can then never throw away the undo key or leave a live step with no BR |
| `flow_completeness_report` | — | R | gains `step_without_br` (a live process step with no live BR) and `live_link_on_retired_step` (a live I/O / role / external flow / arrow on a retired step). **Both must be 0** — the independent check that this feature never leaves a half state |
| confirm on screen *(manual)* | — | — | the consultant reads the list ("BR-0012 and its 3 data links, 2 roles, 1 outside flow, 4 arrows") and confirms |

## 5–6. Logical and physical design
**No schema change and no migration.** The undo record is the summary `audit_event`
(append-only by grant and trigger). Its `detail` jsonb holds the row list. `lifecycle.soft_delete`
gains an optional `at=` argument, so every row in one action shares one timestamp.

## 7. Function — `services/step_retire.py`, the one owner of the owned-set rule
```
OWNED = step: BusinessRequirement, BfcNodeDataEntity, BfcNodeOrgRole, BfcNodeExternalFlow,
              BfcNodeFlow (from | to, de-duplicated)
        br:   BrDataEntity, BrOrgRole
TIERS (retire order; restore runs them reversed) — the D-24 licence FKs (fk_brde_io_licence,
fk_bnef_io_licence) are immediate, so a licensee always goes before its licence:
  1. BrDataEntity, BfcNodeExternalFlow      # licensees of the step I/O
  2. BfcNodeDataEntity, BrOrgRole, BfcNodeOrgRole, BfcNodeFlow
  3. BusinessRequirement
  4. the step
  db.flush() between tiers

preview(db, step)                   -> {owned, blockers, confirm_hash}
retire(db, actor, step, hash)       # FOR UPDATE; recompute; 409s; one `at`; tiers; audit; ONE commit
restore(db, actor, step)            # read the event first; refuse-as-a-whole; reverse tiers; ONE commit
```
It uses no-commit variants of `lifecycle` (extracted, so the existing `retire` / `restore` /
`relink` keep their behaviour). It uses `inactive_parents` on every row to be restored, and
`audit.record`. **Nothing inside it commits partway.** Any failure rolls the whole action back.

The existing child-writing paths (`step_io.link`, `raci.link`, `link_external_flow`,
`link_process_flow`, BR CRUD / role link) already refuse a retired step or BR. Retire's
`FOR UPDATE` lock serialises them against a retire in flight (A-SR-6).

## 8. code_master
None.

## 9. API (`object_guard(BfcNode, "EDITOR")`, one guard each)

| Method · path | Body | Response |
|---|---|---|
| `GET /bfc-nodes/{id}/retire-preview` | — | `{owned, blockers, confirm_hash}` |
| `POST /bfc-nodes/{id}/retire-with-dependents` | `{confirm_hash}` | 204; 409 on blockers or a changed hash |
| `POST /bfc-nodes/{id}/restore-with-dependents` | — | `{restored: n}`; 409 naming what must be restored first |

## 10. Acceptance criteria (Grade 2: recoverable, but it changes many rows at once)
1. A step with a BR, 2 BR data links, 1 BR role, 3 step I/O rows, 1 step role, 1 external flow
   (licensed by an I/O row) and 2 arrows (one a self-loop) previews exactly those rows once each.
   Retire leaves them and the step inactive, **all with an equal `deleted_at`**, one per-row
   event each plus one summary event listing them. This test is what proves the tier order
   against the licence FKs.
2. After retire, `step_without_br` and `live_link_on_retired_step` are 0, and the chart hides the
   step.
3. A preview hash taken before someone added an I/O row to the step → 409, and nothing is
   retired.
4. A dependent outside the owned set blocks: one on the step, one on the BR, and one on an owned
   link row. Each → 409 naming it, and nothing retired. The test table is registered before
   `lifecycle.LINKS` is built (or LINKS is rebuilt), so the real rule is exercised.
5. Restore-with-dependents brings back exactly the listed rows. A BR role retired on its own the
   day before stays retired. A listed row restored by hand in between is left alone.
6. Restore refuses as a whole, naming the blocker, when a listed row's other parent is retired
   (a far step of an arrow, or a DE of an I/O row). Once that parent is restored, it succeeds.
   Whatever order two related steps are restored in, no arrow is lost.
7. A forced failure on the last row of a restore (and of a retire) leaves the database exactly
   as it was before the call.
8. A plain `PATCH …/restore` of a step retired this way → 409 pointing to the with-dependents
   route. A step retired the plain way still restores the plain way.
9. A REVIEWER gets 403 on all three routes; a step in an invisible project gets 404; a summary
   node gets 422.
10. On the canvas, the step pop-up's Retire shows the preview list and retires on confirm. The
    node panel does the same. A retired step offers only "Restore with its requirement and flows".
11. A frozen baseline is untouched (snapshots are immutable). *The freeze itself is not built yet;
    criterion 11 is proven against `baseline_shadow` when it is (A-SR-7).*

## 11. Assumptions
- **A-SR-1** The owned set is exactly §7 `OWNED`. A future link table joins it only by an
  explicit edit to `OWNED`, with its own test. Until then it blocks.
- **A-SR-2** Arrows through the step are retired, not re-joined (A→step→B does not become A→B).
  Re-joining would guess the business sequence; `orphan_steps` shows the gap and a person decides.
- **A-SR-3** A BASELINED BR may be retired this way, as it already can through its own route.
  The baseline keeps its frozen copy.
- **A-SR-4** Same permission as a plain retire (EDITOR), with no typed confirmation. The preview
  list is the confirmation, because the action is undoable in one step. The hash is a staleness
  check, not proof that the user read the preview.
- **A-SR-5** **Restore is all or nothing.** If anything the step needs is still retired, the
  restore refuses and names it, so a step never comes back half-built. *Ben's call; the
  alternative is restore-what-you-can plus a named list of skips.*
- **A-SR-6** Step roles and external flows are owned by the step. They describe the step's
  work, and retiring them leaves the org role and the outside party themselves untouched.
  *Ben's call.*
- **A-SR-7** Whether a baseline freeze should warn about a step retired with its BR since the
  last freeze belongs to the freeze slice (VB-005 line), not here.

## 12. Out of scope
- Cascade for summary nodes (a whole branch).
- Re-joining the flow around a removed step.
- Undo for anything other than a step.

## 13. Build checklist
- Tests first in `tests/test_step_retire.py`, one per criterion.
- sara before commit: this touches soft delete, restore, audit, and revises Q4.
- Record the revision in design §1a (S3-SR → this file).
- One commit for the backend and one for the screens. No migration.

**Design review:** round 1 of 2 on 2026-09-30 (`design-auditor`: 10 findings, 3 HIGH, 5 MEDIUM,
2 LOW). Round 2 confirmed 9 closed. Business questions 1 and 3 are A-SR-5 and A-SR-6
(Ben's call); question 2 is A-SR-7; question 4 is A-SR-4.

**Round 2 of 2** (2026-09-30): 9 of 10 closed. Four new items and one leftover are **tracked, not
redrafted**, as VB-005 lines SR-1…SR-5, and the builder applies these rules:
- **SR-1 (N1):** both restore routes compare `step.deleted_at` with the latest summary event's
  `deleted_at`, stored as a full-precision ISO string. Equal → with-dependents only; not equal →
  plain only; each route answers 409 in the other's case. Restore-with-dependents refuses unless
  the step itself is in the matched set. The UI offers the restore that fits.
- **SR-2 (N2):** the step tier restores through a no-commit form of `bfc.restore_node`, keeping its
  name check and renumbering (`_free`). Test: the parent is reordered while the step is retired.
- **SR-3 (N3):** `step_without_br` is a **warning**, not must-be-0. Retiring a BR while its step
  is live is the designed first step of a demote (criterion 90, D-2). `live_link_on_retired_step`
  stays must-be-0.
- **SR-4 (N4):** A-SR-1 reads "any **FK-declared** table blocks by default". A future polymorphic
  reference (`target_table`, `target_id`) must add an FK or join `OWNED` explicitly.
- **SR-5 (finding 5, LOW):** the child-writing paths load the step `FOR SHARE` before their
  `is_active` check; until then, `live_link_on_retired_step` catches the race.
