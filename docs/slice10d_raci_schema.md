# Slice 10d — one RACI per process (D-64): what becomes of `bfc_node_org_role`

`apple`, 2026-10-13. Draft for Ben. Main at migration 0051, `CURRENT_HASH_SPEC = 2`. Docs only.
Design rows: D-64, D-63 (Accountable tile), D-2 / S7-2 (one BR per **to-be** process, none on as-is),
D-46 (lane = performer, not RACI), R2-D9 / Q7 (rules key on behaviour), D-47 (as-is chart).

## 1. Facts found in code

Both tables have the same shape: surrogate PK, `(owner, org_role_id, raci_code_id)` grain unique **including
retired rows**, `raci_behaviour` copied from the code and FK-verified, and a partial unique index allowing one live
ACCOUNTABLE (`uq_bnor_one_accountable` from 0014, `uq_bror_one_accountable` from 0015). 0046 dropped the step's
one-Responsible index (D-46). Since D-46 **no lane, DFD, export or report reads RACI**: `process_flow` lanes read
`bfc_node.performer_*` only, and `render.py`, `bulk.py`, `consistency*.py`, `business_requirement.py` never
touch either table.

| Touches | `bfc_node_org_role` (step) | `br_org_role` (BR) |
|---|---|---|
| Write: link/unlink | `raci.link/unlink` via `POST/DELETE /bfc-nodes/{id}/org-roles` (refuses a non-process) | `raci.link/unlink` via `/business-requirements/{id}/org-roles` |
| Write: chart copy | `bfc_set.copy_set` copies step roles **both ways** (as-is ⇄ to-be) | never copied (the new BR starts empty) |
| Write: seed | `seed_demo` line 113 puts an `R` on every **to-be** step | none |
| Write: retire/restore | `step_retire` OWNED_BY_STEP, tier 2 | `step_retire` OWNED_BY_BR, tier 2 |
| Read: screen | `NodePanel` "step facts" RaciPanel (`STEP_SINGLE`) | `BrRaci` in `BrSection` (process panel **and** BR page) |
| Read: guards/checks | `bfc._step_blockers` ("step roles" block un-making a process); `process_flow._live_on_retired` | none |
| Read: labels | `lifecycle` "Step role"; `step_retire.describe`; `RetireStepDialog` count | same |
| Baseline | FREEZE_SET area BFC, hashed `(bfc_node_id, org_role_id, raci_code, raci_behaviour)`, gate `by_step_set AS_IS` | area BR, same hashed list, always frozen |
| History | 0041 backfilled performers from RESPONSIBLE step roles (its test downgrades to 0040 and back) | — |

So today a to-be process carries **two** RACI lists for the same thing, both shown in the panel, and both
frozen. An as-is process has only the step list, because it has no BR.

## 2. Options

**(a) Keep in sync.** Each BR role write mirrors to the step row. *Consequences:* the same fact stored twice
(a 3NF break); three writers (link, copy, retire/restore) must each keep both in step; a baseline freezes it
twice and the diff shows every change twice (BFC area and BR area). It buys nothing, since nothing reads the step
copy. **Rejected.**

**(b) Derived: stop writing to-be step rows and read through a view** (BR roles for to-be, step rows for as-is).
*Consequences:* a view in FREEZE_SET counts as a new entity, so a spec bump (spec 3) for no new information. Old to-be
step rows are left live but unused unless they are also retired, and then this is (c) with an extra object.
**Rejected**, but its read rule is kept as a service function (see the recommendation).

**(c) Split by chart: the step table holds as-is roles only, the BR table holds to-be roles.** *(Recommended.)*
Live to-be step roles are merged once into their BR's list and then retired. The database refuses a live step role
on a to-be step from then on. *Consequences:* one record per process, chosen by chart. No new table, no shadow
change, no hash-spec change (§4). As-is keeps its RACI ("who is accountable today"), which the D-63 Accountable
tile needs for as-is processes too.

(d) A new `process_org_role` replacing both: a new frozen entity (spec 3), two tables retired, every reader
rewritten. Same result as (c) at about four times the cost. Not proposed.

## 3. Recommendation (option c), in detail

**Rule.** Where a process's roles live depends on its chart: a **to-be process's roles are its BR's**
(`br_org_role`), and an **as-is process's roles are the step's** (`bfc_node_org_role`). One read function,
`raci.process_roles(node)`, picks the right one. The panel's RACI editor and the Accountable tile use only that function.

**Database guard (same pattern as S7-2 and `node_is_process`).** Add to `bfc_node_org_role` a generated
`node_live_set varchar(10) GENERATED ALWAYS AS (CASE WHEN is_active THEN 'AS_IS' END) STORED`, and
`FK (bfc_node_id, project_id, node_live_set) → bfc_node (bfc_node_id, project_id, bfc_set_code)` (target
`uq_bfc_node_set` exists), `ON UPDATE NO ACTION`. Retired rows have NULL, so they are not checked and history stays
as it is. A live or restored row on a to-be step fails at the database.

**RACI rules: no change, and they stay in two places, each at the database and in the service:**
one live ACCOUNTABLE per BR (`uq_bror_one_accountable`) and one per as-is step (`uq_bnor_one_accountable`), both
mirrored in `raci.SINGLE`, keyed on behaviour (R2-D9). Several R is normal (D-46).

**Service changes (10d builds them):**
1. `raci.link(BfcNodeOrgRole, …)` on a to-be step → 409 "A to-be process's roles are on its requirement".
   The route stays (as-is uses it) and keeps its guard.
2. `bfc_set.copy_set`: as-is → to-be copies step roles **into the new BR's** `br_org_role`. To-be → as-is copies
   the to-be **BR's roles** onto the new as-is steps. The preview key `step_roles` keeps its name and counts the rows
   that will be copied.
3. `step_retire.restore`: an older event may list `bfc_node_org_role` rows on a to-be step, and those can never be
   live again. Skip them as `RETIRED_TABLES` skips `bfc_node_flow`, but by chart instead of by table.
4. `seed_demo`: its `R` goes on the step's BR.
5. `NodePanel`: drop the step RaciPanel for to-be (the BR's is shown). As-is shows the step's.
   `_step_blockers` and `_live_on_retired` are unchanged.

## 4. Baselines

`bfc_node_org_role` and `br_org_role` stay in FREEZE_SET with the same hashed lists. **No spec bump**: the 10b rule
bumps only when an entity's hashed list changes or a new entity joins, and neither happens here. The generated
column is not in the shadow (`snapshot_column_names` skips GENERATED columns), so no shadow DDL changes, and no shadow
type is ALTERed. Old baselines recompute byte-identical. **The one visible effect:** the first diff of a pre-10d
baseline against live shows each merged to-be step role as REMOVED (area BFC). Where the BR did not already hold it,
it also shows as ADDED (area BR). That is a true record of the move, and the migration's audit event explains it.

## 5. Migration 0052 (one commit, as `vb_owner`, reversible)

Upgrade, in one transaction:
1. **Pre-check (stops for Ben):** a live to-be step role whose step has no live BR (should be impossible under S7-2;
   `step_without_br` reports it). The migration aborts and lists them, and never invents a BR.
2. **Merge each live to-be step role** into the step's live BR, matching on (org_role_id, raci_code_id):
   - the BR already has it live → nothing to copy;
   - the BR has it retired → restore that row (the grain unique includes retired rows; same as `raci.link` re-link);
   - otherwise → insert, with `created_by` = the step row's author.
   - **Accountable conflict** (step A = X, BR A = Y, X ≠ Y): **the BR's wins** (D-64 makes it the record). X is
     not copied as A. Its step row is still retired and listed under `conflicts` in the audit event.
3. **Retire every live to-be step role** (`is_active=false`, one `deleted_at`, `deleted_by` = actor).
4. One `audit_event` `RACI_MERGED_TO_BR` (decision D-64) whose detail lists `copied`, `restored`, `already`, `conflicts`
   and `retired` ids, so every change can be traced and undone by hand.
5. **Retired-with-step history** (see Q-3): for each to-be step retired with its dependents, copy its step roles into
   its retired BR as **retired** `br_org_role` rows carrying the event's `deleted_at`. `step_retire._same_stamp_links`
   is extended to `br_org_role` (the 10b Q-8 precedent), so a later restore brings them back with the BR.
6. Add the generated column and the FK.

Downgrade: drop the FK and the column. That cannot fail, so `test_0041`'s step back to 0040 still works. The data
merge is **not** undone automatically: no row was deleted, the step rows are retired and intact, and the audit event
holds the full id map. Undoing the data automatically could re-create Accountable conflicts, so that stops for Ben.

Tests to add: FK refuses a live/restored to-be step role; link 409 on to-be; as-is link still works; merge cases
(new, already, retired-restored, A-conflict, no-BR abort); copy both ways; restore of a pre-10d event skips the
step rows and returns the same-stamp BR rows; hash parity: a pre-10d baseline still verifies.

## 6. Questions for Ben

- **[Q-1] Option (c): to-be roles live on the requirement, as-is roles stay on the process.**
  *Recommendation: yes.* As-is processes have no requirement, so they keep their own list. The database refuses a
  to-be process role from now on.
- **[Q-2] When a process and its requirement name different Accountables, the requirement's wins.**
  *Recommendation: yes.* The process's one is kept as a retired row and listed in the migration's audit record for
  someone to review. Alternative: stop the migration and fix them by hand first.
- **[Q-3] Roles of processes retired before 10d come back with the requirement when restored.**
  *Recommendation: yes* (step 5). Without it, restoring such a process brings back the requirement without the roles
  that were on the process.
- **[Q-4] Copying a chart carries the roles across the change of home** (as-is process ⇄ to-be requirement).
  *Recommendation: yes.* Today's copy already carries step roles.
- **[Q-5] A process with no requirement blocks the migration rather than being skipped.**
  *Recommendation: block.* It should never exist, and skipping it would hide a broken process.
- **[Q-6] The first comparison against an older baseline shows the moved roles once as removed and added.**
  *Recommendation: accept it.* It is a true record, explained by the audit event. No hash-spec change.
