# Plan — Change requests (D-16), Phase 2 — 2026-11-03 (awaiting approval)

**For:** Ren / Ben · **By:** Lilly · **Status:** plan only. Nothing built, migrated or seeded.
**Counted from:** `origin/main` at `c3fb909` (Benefits merged; 1,326 tests passed on that commit).
**The spec:** `docs/slice_change_requests_spec.md` (requirement grid, logical and physical design, acceptance
criteria, assumptions, the three questions for Ben). This file adds the review result, test plan and slices.

## 1. Migration slot and clashes

- Next migration numbers after origin/main's 0086: **0087 `change_request`** and **0088 `cr_impact`** (one table per
  migration, as Benefits 0085 / 0086). No branch in the repo holds a 0087 (checked `git log --all`).
- No other open slice found. No hash-spec bump is taken (spec §5).

## 2. Baselines and hash spec

Nothing changes. Both tables are live-only (design §6.1 rows 33–34); no shadow, no freeze-set entry,
`CURRENT_HASH_SPEC` stays 7. Every baseline already frozen is untouched and still verifies. The slice only reads the
target's frozen FR and benefit rows; a target frozen before spec 7 shows "value change not measured" (spec A6).

## 3. Design review

Two rounds, the cap: round 1 design-auditor (2 H, 4 M, 2 L) and apple (1 H, 5 M, 5 L); round 2 design-auditor on the
revision (1 H, 2 M, 2 L, **none structural** — grain, identity and write list hold). Every finding and what I did
with it is in §6. Nothing goes to a third round; what is left is three questions for Ben (CR-1…CR-3) and is otherwise
settled against the running code.

## 4. Test plan — Grade 2

**Grade 2**, because a wrong price or a gate that lets an uncovered increase through puts wrong figures in front of
a steering meeting and into the decision log; it is recoverable (the decision is visible and a new CR corrects it)
and moves no money, grants no access, destroys no data. Access goes through the existing guards and the existing
GET-leak test. No break-the-code harness. Proof, mapped to spec §6:

- **API tests** (`test_change_request_api.py`, ~30): criteria 1–11 directly, including the two races — two CRs
  claiming one cut (partial unique index → 409) and a freeze superseding the target while a raise holds it
  (`FOR SHARE` vs `FOR UPDATE`, two connections, as Benefits M2).
- **Migration tests** (`test_migration_0087_0088.py`, ~6): up / down, the one-of-seven CHECK, seed/impact-type CHECK,
  decision and budget all-or-none, vb_app has no DELETE.
- **Pins updated, not weakened:** route guards / components (49b), code lists (PINNED / COMPANY_ONLY), purge table
  list, M2 tile.
- **Deliberately not covered:** trace over a project with thousands of links (no performance test; the walk is a
  handful of set queries); a CR on a target frozen before hash spec 2 (no BR ↔ FR rows — the trace reads live links
  so it still works, not tested); D2-2 time-zone edge at midnight.
- **Browser:** ui-verifier on 5181 → 8101, spec criterion 12, screenshots under `Evidence/2026-11-0x/change-requests/`.
- **Full suite** `pytest -q -m "" -n 6` on the merged commit before asking to merge; lint and build.

**Ports and databases for the build (slot 1):** API 8101, web 5181; databases `vb_s1cr_db`, `vb_s1cr_uat_db`,
`vb_s1cr_test_db` and `vb_s1cr_test_db_gw0…5`, all created and dropped by this task. No shared file fixes a port or
database name that needs changing (ports come from flags / `VB_API_PORT`, databases from the worktree's own `.env`).

## 5. Slices and days (4.3)

| Piece | What a person can do when it lands | Days |
|---|---|---:|
| **A — raise, trace, price** | 0087 + 0088, code lists, service, routes, register, New CR, CR page with seeds, "Trace and price", impact table and price panel. A user raises CR-0001 against v1.0, seeds a BR and two FRs, and sees the blast radius and +n days | 2.0 |
| **B — decide** | Decide dialog and the gate (cut / budget), `decision.insert_decision` in one transaction, DEFERRED re-decide, decision correction through the CR, retire / restore, the unagreed-edit list and freeze-preview warning, decision page back-link, M2 tile, rail entry | 1.4 |
| **C — prove and document** | ui-verifier pass, sara review (fix CRITICAL / HIGH; MEDIUM / LOW to VB-005), design §4.11 / §5 / ERD / §7.13 / criteria rewritten to Ben's answers, history CR-n to §3, CLAUDE deploy note (`seed_code_master` after 0088), full suite | 0.9 |

Up 0.3 day from the 4 quoted, for the round-1/2 fixes (decision correction route, hash-based freeze warning).
Each piece is a commit series on this branch; A is usable on its own (a priced CR nobody can decide yet).

## 6. Review findings and what I do with each

| # | From | Finding | Disposition |
|---|---|---|---|
| 1 | R1 auditor H | A rejected / open change left in the working set is frozen as if agreed | **Fixed** (unagreed-edit list + freeze-preview warning, by content hash, R2 M) · what to do with the edit → **Ben, CR-1** |
| 2 | R1 auditor H | Seeds / analyse could rewrite a decided CR | **Fixed** — open-only, 409; criterion 8 |
| 3 | R1 auditor M | CR state and decision log can disagree | **Fixed** — a CR's DEC is corrected only through the CR (`decision-correction`, R2 M) |
| 4 | R1 auditor M | Two CRs on one FR price the same edit twice | **Fixed** — one open seed per FR, FRs locked `FOR UPDATE` (R2 L) · the rule itself is in **CR-1** |
| 5 | R1 auditor M / apple M4 | Stale-price check undefined | **Fixed** — seed figures block; exposure and value shown "moved since pricing" (R2 L) · **CR-1** |
| 6 | R1 auditor M | Budget cover is typed by the decider | **Ben, CR-3** (recommend any editor; alternative: not the raiser) |
| 7 | R1 auditor M | No `## Interface` | **Fixed** — spec §6 |
| 8 | R1 auditor L ×2 | Double-click / repeated DEFERRED; unscoped ids | **Fixed** — buttons disabled in flight, DEFERRED-on-DEFERRED 409, scoped reads |
| 9 | apple H | Departs from the signed data design | **Ben, CR-2** — spec §5 and the ERD rewritten in the same commit as his answer |
| 10 | apple M2–M6 | Unit lost; per-row CHECKs; price all-or-none; decider copied; status not tied to fields | **Fixed** — `value_unit`; CHECKs; decider read from DEC; status behaviours with CHECKs |
| 11 | apple L7–L11 | Cut pointing at a cut; raiser = creator; `reached_via` open; number width; unique index | **Fixed** (CHECKs, width 20) · L11 kept as the one NULLS NOT DISTINCT constraint |
| 12 | R2 auditor H | DEFERRED CR re-seeded loses its DEC (CHECK forced NULL) | **Fixed** — `decision_id` survives; CHECK narrowed to "decided ⇒ set" |
| 13 | R2 auditor M | Unagreed-edit warning compared effort only | **Fixed** — content hash vs shadow, BR and FR, ADDs, retired CRs |
| 14 | R2 auditor M | A final CR's DEC could not be corrected | **Fixed** — `correct_cr_decision`, same outcome |
| 15 | R2 auditor L ×2 | Overlap race; all-figure compare stalls | **Fixed** (#4, #5) |

Nothing tracked in BUGLOG: every finding is fixed in the spec or is one of Ben's three questions. One later idea
(a control rule on the age of open CRs) goes to VB-005 at build.
