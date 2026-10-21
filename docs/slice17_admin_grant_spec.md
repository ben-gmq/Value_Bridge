# Slice 17 — Platform-admin grant approval (spec, APPROVED by Ben 2026-10-21 — AR-16…AR-23, Q-105 a, Q-107 a; schema rev 3)

**Source of truth:** `docs/VB_design.md` §9.10 access model ("Making someone a platform admin needs a second platform
admin's approval (AR-13)"), §6.6; history AR-13 (Q-93 b), AR-15. Plan row "Platform-admin grant approval" in
`docs/VB_remaining_work.md` (Phase 3, 1 day). **Schema:** `docs/slice17_admin_grant_schema.md` (apple). **Depends on:**
slice 16's `project_purge` guard (0072), whose interim AR-13 (a) check reads the grant this slice records — built.

## 1. Purpose
Nobody becomes a platform admin — who sees every client's data and can approve the deletion of a client's project —
on one person's say-so: one platform admin proposes, a different one approves, and the database refuses the flag
any other way.

## 1a. Interface
- **Input:** a platform admin's request naming an active FTC user and a reason; a different platform admin's approval
  or rejection; any platform admin's cancellation. Owner-run by the Fortience IS department only (AR-22): the first two
  admins through `seeds.create_admin` while fewer than two people have ever been granted (AR-16), and recorded LEGACY
  grants (AR-19).
- **Output:** on approval, the user is a platform admin in the same transaction, with one `PLATFORM_ADMIN_GRANTED`
  audit row naming requester and approver; the request record, kept forever. Removing admin rights is unchanged
  (one admin, a reason, the existing preview) — Q-96.
- **Validation:** refused: a non-admin (403); no reason (422); the requester approving their own request, or the
  target approving a request about themselves (409); a second open request for the same user (409); a target who is
  inactive or already an admin (409); an approval by an admin who is not independent of the requester in either
  direction (409, AR-18 — no 30-day rule for grants, AR-20); a request for an account the requester created (409, AR-21
  as settled by Q-107); any change of `app_user.is_platform_admin` from false to true that is not the approval of an
  open request in the same transaction (`approved_xact`), the owner's BOOTSTRAP or a LEGACY grant — refused by the
  database for every role.
- **Archive:** every request row and its audit rows, forever; no client content in either (ids, codes, a reason).
- **Maintenance loop:** the slice 16 weekly check adds the admin lines of §16 P2 (open requests > 7 days, recent
  grants, live admins below two, BOOTSTRAP / LEGACY rows after 0076, recent removals), read by every platform admin
  where Q-104 says. **Not live until slice 16's weekly check is built** — until then nothing reconciles admin grants.

## 2. Playbook / doctrine
`~/.claude/ftc-playbook.md` §9 items 2 (`created_by` from the token), 7 (soft delete — the request record has no
delete at all), 10–11 (one service: `services/user_admin`). VB law 1, 3, 6, 10; design §6.6. Deviation: the request
table carries the design's named actor pairs (`requested_*`, `approved_*`…) instead of `AuditMixin`, as
`project_purge` does (schema §3.2 of slice 16) — recorded there.

## 3. Keystone grain
**`platform_admin_grant` — one row per way one user was made (or asked to be made) a platform admin**: a REQUEST, the
BOOTSTRAP of the first two admins, or a LEGACY row backfilled for admins who exist when this lands (apple, schema §1 —
widened from "one row per request" so AR-13 never reads `audit_event`, whose time and detail the app role can write).
State is derived from its dates (open, approved, rejected, cancelled). At most one open request per user.

## 4. Business Requirement — the grid

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `admin_grant.request` | `platform_admin_grant` | C | requester is a live platform admin (token); target active, not an admin, no open request; reason not blank → one open row; audit `PLATFORM_ADMIN_GRANT_REQUESTED` |
| `admin_grant.request` | `app_user` | R | target's active / admin flags; requester re-read live |
| `admin_grant.approve` | `platform_admin_grant` | U | open; approver ≠ requester, ≠ target; approver a live admin, independent of the requester both ways (AR-18, `fn_admin_grant_independent`) → `approved_*` and `approved_xact` set by the database |
| `admin_grant.approve` | `app_user` | U | target still active and not an admin → `is_platform_admin = true`, same transaction |
| `admin_grant.approve` | `audit_event` | C | `PLATFORM_ADMIN_GRANTED`, actor = approver, detail {requested_by, grant id, reason} — for people to read; **AR-13 never reads it** (it reads `platform_admin_grant` through `fn_admin_grant_independent`, §16 P3) |
| `admin_grant.reject` | `platform_admin_grant` | U | open; any live admin other than the requester → `rejected_*` + reason; audit |
| `admin_grant.cancel` | `platform_admin_grant` | U | open; any live admin → `cancelled_*`; audit |
| `admin_grant.list` | `platform_admin_grant`, `app_user` | R | open requests first, then decided; names of the people |
| `user_admin.set_platform_admin` (existing) | `app_user` | U | **grant branch removed** (422 → "request it"); remove branch unchanged |
| `seeds.create_admin` (existing CLI, moves to the owner URL) | `app_user`, `platform_admin_grant`, `audit_event` | C | owner only, while fewer than two people have ever been granted (AR-16, counted as the greater of grant rows and live flagged admins — N6 a); records operator and `--actor-email` on the BOOTSTRAP row |
| `seeds.owner_grant.legacy_grant` (new IS CLI) | `platform_admin_grant`, `app_user` | C, U | owner only; reason, operator and the asking admin (`--actor-email`, N5) required; never backdated outside the named test / demo databases (AR-19, N4) |
| `auth_service.first_run_setup` (existing) | `app_user` | C | unchanged — only when no user exists |
| `archive.weekly_check` (slice 16, to come) | `platform_admin_grant` | R | lists open requests > 7 days and grants in the last 7 days |
| (manual) the approving admin | — | — | confirms out of band that the person should hold the role (who asked for it, for which engagement) before approving |

## 5–6. Logical and physical design
**apple:** `docs/slice17_admin_grant_schema.md` — the request table, the `app_user` guard, the migration list and the
change to slice 16's AR-13 check. Where this spec and apple differ, apple's schema wins.

## 7. Functions

```
admin_grant.request(db, actor, user_id, reason):            # services/admin_grant.py; route guard platform_admin
    reason.strip() or 422
    target = app_user(user_id) live, not admin, else 409 (404 if absent)
    insert platform_admin_grant(target, reason, requested_by=actor)   # uq_pag_open → 409 "already requested"
    audit PLATFORM_ADMIN_GRANT_REQUESTED; commit

admin_grant.approve(db, actor, grant_id, row_version):
    g = open request for update, row_version matches else 409
    actor ≠ g.requested_by and actor ≠ g.target else 409 (four eyes)
    access.grant_independent(db, actor, g.requested_by) else 409   # calls fn_admin_grant_independent (AR-18);
                                                                    # the guard calls it too — never re-coded in Python
    g.approved_by = actor                                   # the guard sets approved_at := statement_timestamp()
    target.is_platform_admin = True                          # the app_user guard checks this row is being approved
    audit PLATFORM_ADMIN_GRANTED {grant id, requested_by, reason}; commit

admin_grant.reject(db, actor, grant_id, reason, row_version)  # actor ≠ requester; reason required
admin_grant.cancel(db, actor, grant_id, row_version)          # any live admin
```
`user_admin.set_platform_admin(value=True)` → 422 "Make someone an admin through a request a second admin approves".

## 8. `code_master`
None. State is derived from dates (the slice 16 precedent, Q-67); labels via `t()`.

## 9. API (`/api/v1`)
| Method · path | Guard | In → out |
|---|---|---|
| `GET /admin/grant-requests` | platform_admin | every request (open first): target, requester, reason, dates, decider |
| `POST /users/{id}/grant-requests` | platform_admin | `reason` → the open request (201) |
| `POST /grant-requests/{id}/approve` | platform_admin | `row_version` → the approved request; the user is now an admin |
| `POST /grant-requests/{id}/reject` | platform_admin | `reason`, `row_version` → rejected |
| `POST /grant-requests/{id}/cancel` | platform_admin | `row_version` → cancelled |
| `PATCH /users/{id}/platform-admin` (existing) | platform_admin | removal only; `true` → 422 |

**Screen:** the existing users page (`features/admin/AdminPage.jsx`): "Make admin" becomes "Request admin rights"
(reason dialog); a "Pending admin requests" card above the user list with Approve / Reject / Cancel, the approve
button hidden for the requester and the target (presentation only; the guards refuse anyway). Strings in
`en.admin.json`.

## 10. Acceptance criteria
1. A platform admin requests admin rights for an active user with a reason → one open request; the user is not yet an
   admin. Without a reason → 422; a non-admin → 403; a second open request for the same user → 409.
2. The requester approving their own request → 409; the target approving → 409 (when the target is somehow an admin
   already, the request is refused at creation instead).
3. A different live admin approves → the user is an admin, `approved_at` is the database's time, one
   `PLATFORM_ADMIN_GRANTED` row names requester and approver.
4. **AR-18, both directions:** an approver whose latest grant the requester requested or approved is refused, **and**
   an approver who requested or approved the requester's latest grant is refused. A grant approval needs no 30 days
   (AR-20): an independent approver granted yesterday may approve.
5. **AR-20 for purges (slice 16 re-pointed, 0077):** a purge approval additionally needs the approver's latest grant to
   be at least 30 days old; the purge guard reads `fn_admin_purge_independent`, never `audit_event`; 0077's copy of the
   purge guard equals the body at its parent revision (a test diffs it, N6 b).
6. Reject (with a reason) and cancel close the request; a closed request never changes; the user can be requested
   again afterwards.
7. `PATCH /users/{id}/platform-admin` with `true` → 422; removal works as before (AR-17).
8. **At the database, for `vb_app`:** `UPDATE app_user SET is_platform_admin = true` — reactivating a deactivated admin
   included — is refused unless a REQUEST for that user was approved **in this transaction** (`approved_xact =
   pg_current_xact_id()`); one approved in an earlier transaction cannot be replayed (D1). An INSERT with the flag is
   refused unless `app_user` is empty (`first_run_setup`). An INSERT of an inactive admin is refused for every role (D3).
9. **The owner paths (AR-16, AR-19):** `seeds.create_admin` as the owner succeeds while fewer than two people have
   ever been granted and refuses after — removing an admin never reopens it; it records the operator and the asking
   admin. A LEGACY grant needs owner, reason, operator and asking admin; its `approved_at` is the database's time except
   on a database whose name is exactly one of the named test / demo databases (N4).
10. **AR-21 as settled by Q-107:** a request for an account the requester created → 409; (if Q-107 (a)) an approver who
    created the target's account → 409, and an account's creator counts as having made that admin in the independence
    functions.
11. The grant record refuses DELETE for every role; neither role can backdate `approved_at`, `rejected_at`,
    `cancelled_at`; the flag and an approval land together or neither (the deferred commit check).
12. The weekly-check query lists live flagged admins with no approved grant row (N3), LEGACY rows without an asking
    admin or with `approved_at < recorded_at` (N5, N4), and admins removed in the last 7 days (§16 P2).
13. The users page shows pending requests and their actions, with the target's email, who created the account and
    when, and the request's age; seen in a browser (ui-verifier).

## 11. Assumptions
- `ASSUMPTION` A-17-1: removing admin rights stays a one-admin action — it is the safe direction (Q-96).
- `ASSUMPTION` A-17-2: requests do not expire; the weekly check names old ones and an admin cancels them.
- `ASSUMPTION` A-17-3: `first_run_setup` stays as is (only with no users at all, and only where it is switched on).
- `ASSUMPTION` A-17-4: the target is told out of band; no e-mail exists in VB.

## 12. Out of scope
Two-person removal of admin rights (unless Q-96 says otherwise) · request expiry · notifications · changing a user's
kind (USER / VIEWER) · Entra ID group-based admin rights (Azure, D-35).

## 13. Grade and test depth
**Grade 1** — a wrong answer grants access to every client's data. Proposed depth: criteria 1–12 as service and
database tests for both roles (the guards proven directly, as slice 16's purge record); one browser pass (criterion
13). A mutation harness is justified at this grade but is its own approved piece of work, not this slice.

## 14. Build checklist
One migration per commit, reversible (apple's list) · `sara` before the commit (grants, access) · `ROUTE_COMPONENTS`
and the route-guard tests updated · strings via `t()` · independence is answered only by the database functions over
`platform_admin_grant` — `fn_admin_grant_independent` (grant approvals) and `fn_admin_purge_independent` (purge
approvals, + 30 days) — the guards and `access.grant_independent` call them, never re-implement them (§16 P3) ·
run 0076 on a copy as the deploy will and confirm its NOTICEs reach the console (N3) ·
full suite before merge · CLAUDE.md "Slice 17 deploy" line if the bootstrap rule changes an operator step.

## 15. Questions for Ben
- **Q-95 — How is the second admin made?** With one admin there is nobody to approve. (a) the operator's
  `seeds.create_admin` works only while fewer than two live admins exist — after that, every admin comes through a
  request; (b) the single admin's first request approves itself. **Recommend (a)** — it needs server access, which is
  itself a second control, and it closes once two exist.
- **Q-96 — Does removing admin rights also need a second admin?** **Recommend no** — removal is the safe direction,
  and a compromised admin should be removable by one other admin at once.
- **Q-97 — Who counts as "made by the requester" for AR-13 (a) once grants have two people?** **Recommend:** both the
  person who requested the approver's grant and the person who approved it — so neither can then approve that
  admin's purge request. One function (`fn_admin_grant_independent`) answers it for both guards (schema, migration
  0078 replaces slice 16's audit lookup).
- **Q-98 (apple) — May the owner make an admin directly, recorded as LEGACY?** Criterion 7 binds the owner too, so
  neither a restore nor the test harness could make a third admin without waiting 30 days. **Recommend:** an
  owner-only, recorded LEGACY path (a script with a reason, written to the grant table), never reachable by the app.
- **Trade-off for Ben (apple):** with AR-13 on grants, a fresh install cannot approve a third admin until the first
  two have held the role 30 days; deactivating admins down to one re-opens the CLI bootstrap (Q-95 as worded).

**Migrations (apple, schema §6):** 0076 the grant table, guard, independence function and LEGACY / BOOTSTRAP
backfill · 0077 the `app_user` guard (**pauses for Ben**) · 0078 slice 16's purge guard reads the function
(**pauses for Ben**). 0074 / 0075 stay reserved for slice 16. No hash-spec change.

## 16. Design review round 1 (design-auditor, 2026-10-21: 0 blocking, 3 high, 5 medium, 3 low)
Each finding has one disposition. Where this section and the text above differ, **this section wins**; apple folds
the schema changes into `slice17_admin_grant_schema.md` at build. Round 2 of 2 re-checks these changes after Ben's
answers to Q-99…Q-104; whatever it leaves open is tracked and settled against the code.

| # | Finding (rating) | Disposition → change |
|---|---|---|
| P1 | One person can reopen the bootstrap: remove the second admin, run `create_admin` as the app role, and 30 days later hold an "independent" admin (HIGH) | **Fix now.** The `app_user` INSERT-with-flag branch is allowed only when `app_user` is empty (`first_run_setup`) or `session_user = 'vb_owner'`; `seeds.create_admin` moves to the owner URL and takes `--actor-email`: when a live admin exists, that admin is recorded on the BOOTSTRAP row as its maker, so the independence function treats them as such (`ck_pag_requester` relaxed for BOOTSTRAP). Whether dropping to one admin reopens the bootstrap at all: **Q-99** |
| P2 | The weekly check is unbuilt, undelivered and too narrow (MEDIUM) | **Fix now (scope) + state it.** Its lines: open requests > 7 days, grants in the last 7 days, live admins below two, every BOOTSTRAP or LEGACY row dated after 0076, admin removals and deactivations in the last 7 days. Until slice 16's weekly check exists, **the maintenance loop is not live** — said in §1a. Where it is read: **Q-104** |
| P3 | Spec said AR-13 reads audit detail; schema says it reads the grant table (MEDIUM) | **Fixed** in §4 and §14: only `fn_admin_grant_independent` decides; audit rows are for people |
| P4 | The LEGACY path (Q-98) has no limits; the 30-day wait invites it (MEDIUM) | **Fix now.** A LEGACY row is owner-only, carries a reason and the operator's name, and may be **backdated only on a test or demo database** (the `seed_demo` name rule); elsewhere `approved_at` is the database's time, so a LEGACY admin waits 30 days like anyone. The weekly check lists every LEGACY row after 0076. Whether the 30-day rule stays once two-person grants exist: **Q-100** |
| P5 | Requests never expire; an old one can be approved after its reason went stale (LOW) | **Fix now (display).** The pending card and the approve dialog show the request's age; expiry stays A-17-2 (Ben's, unchanged) |
| D1 | "Approved in this transaction" can be replayed by a transaction left open (MEDIUM) | **Fix now.** The grant guard stamps `approved_xact = pg_current_xact_id()` on approval; the `app_user` guard requires it to equal the current transaction's id (top-level, so savepoints are safe; the guard overwrites it, so it cannot be forged) |
| D2 | The 0076 backfill trusts forgeable audit history and is silent about who it skipped (MEDIUM) | **Fix now.** 0076 raises a NOTICE per admin backfilled (origin, source event id) and per admin skipped; the spec records that the backfill trusts audit as of the migration day. No production database exists yet |
| D3 | An inactive admin can be inserted and gets a BOOTSTRAP row; schema §4 says a deactivated admin can "request" — it cannot (LOW) | **Fix now.** Refuse an INSERT with `is_platform_admin AND NOT is_active`; schema §4 text corrected (reactivation: clear the flag in the same UPDATE, then request) |
| D4 | "No DELETE" does not cover TRUNCATE (LOW) | **Track** — VB-005 line (also covers slice 16's purge records) |
| S1 | The approver cannot see that the requester created the target account, so one person can hold two admin identities; independence is one-directional (HIGH) | **Fix now (display)**: the pending card and approve dialog show the target's email, who created the account and when, and whether the target has logged in and set their own password. **The rules are Ben's:** refuse a request for an account the requester created until its owner has set their own password (**Q-101**); make independence symmetric — the approver also must not have made the requester an admin (**Q-102**) |
| S2 | The web app loads the owner login, so a compromised app defeats every database guard (HIGH, predates the slice) | **Track — VB-011**, fix before the first non-local deploy. A HIGH carried until then: **Ben's to accept** |
| S3 | Closing the grant path breaks test and demo setup; the fixture path is unnamed (MEDIUM) | **Fix now.** One helper, `tests.conftest.make_admin(owner, uid, days=…)`, writes a LEGACY row as owner on the test database only; `seed_demo` makes its admins the same way (it already refuses non-demo databases). Every test that flips the flag by SQL moves to it, slice 16's `test_project_purge_record` included |

**Questions for Ben added by round 1:**
- **Q-99 — Once two admins have ever existed, may dropping back to one reopen the command-line way to make an
  admin?** **Recommend no:** after the second admin exists, every admin comes through a request; if only one is left,
  an owner-run, recorded LEGACY grant (reason, operator, no backdating) is the way back.
- **Q-100 — Does the 30-day / not-made-by-the-requester rule stay once two-person grants exist?** It was the interim
  rule. **Recommend yes** for purge approvals only (the irreversible step), **no** for approving a grant — so a fresh
  install can add its third admin without waiting 30 days.
- **Q-101 — May an admin request admin rights for an account they created?** **Recommend:** only after the account's
  owner has logged in and set their own password.
- **Q-102 — Should "independent" also mean the approver did not make the requester an admin?** **Recommend yes** —
  one clause in the function, and it closes S1's second half.
- **Q-103 — Who holds server access to the production database, and is that someone other than the platform
  admins?** The bootstrap and LEGACY paths lean on it. (For the Azure work, D-35, with VB-011.)
- **Q-104 — Where should the weekly admin check be read, given VB sends no e-mail?** **Recommend:** a card on the
  `/admin` page (with slice 16's "last run" warning) and the operator's run log.

## 17. Ben's answers to Q-95…Q-104 (2026-10-21, history AR-16…AR-23) — the current design
"Follow her recommendations"; Q-103: "it will be our Fortience IS department". Each is a build rule and wins over
everything above it.

| Ruling | Build rule |
|---|---|
| **AR-16 (Q-95, Q-99)** | The `app_user` INSERT-with-flag branch (and `seeds.create_admin`) works only as the owner, and only while **fewer than two admins have ever been granted** (counted from `platform_admin_grant`, any origin) — not "fewer than two live", so removing an admin never reopens it (§16 P1). It records who ran it on the BOOTSTRAP row. `first_run_setup` keeps working only on an empty `app_user` |
| **AR-17 (Q-96)** | Removal unchanged: one admin, a reason, the existing preview |
| **AR-18 (Q-97, Q-102)** | `fn_admin_grant_independent(approver, requester)` is symmetric: false if the requester requested or approved the approver's latest grant, **or** the approver requested or approved the requester's latest grant |
| **AR-19 (Q-98)** | LEGACY rows: owner only, reason and operator required, `approved_at` the database's time except on a test or demo database (§16 P4) |
| **AR-20 (Q-100)** | Two checks, one function each: **grant approval** = four eyes + AR-18 (no 30 days); **purge approval** = four eyes + AR-18 + the approver's latest grant ≥ 30 days old. Migration 0077 re-points slice 16's purge guard to the purge check |
| **AR-21 (Q-101)** | A request is refused while the target's account was created by the requester and its owner has not yet logged in and set their own password — needs a "password set by its owner" fact on `app_user` (apple, schema) |
| **AR-22 (Q-103)** | Production server access (owner role, operator jobs, database admin) is the Fortience IS department's, not a platform admin's (design §15.2). The bootstrap and LEGACY scripts are IS jobs |
| **AR-23 (Q-104)** | The admin lines of the weekly check (§16 P2) appear on the `/admin` Removals tab beside slice 16's "last run" card, and in the operator's run log |
| VB-011 | Accepted until the first non-local deploy; HIGH; a hard blocker for that deploy |

**Schema rev 2 (apple, 2026-10-21)** folds §16 and §17 in: migrations 0076 (the owner-set-password fact on `app_user`),
0077 (the grant table, independence functions, backfill with a NOTICE per admin — pauses for Ben), 0078 (slice 16's
purge guard reads the purge check — pauses), 0079 (the `app_user` guard — pauses). Two questions it raised:
- **Q-105 — A fresh install's third admin.** With AR-18 symmetric and the BOOTSTRAP row naming who ran it, the first
  two admins are each "made by" the other, so neither can approve a request for a third (the same holds on today's
  databases where admin 1 promoted admin 2). (a) the third admin is one recorded IS LEGACY grant (AR-19, no backdating)
  — IS is the independent party (AR-22); (b) leave the maker off BOOTSTRAP rows, which re-opens §16 P1. **Recommend (a).**
- **Q-106 — AR-21 needs "the owner set their own password", and VB has no self-service password change.** Until one
  exists, an admin can never request rights for an account they created. (a) build `POST /auth/me/password` and a small
  "change my password" screen in slice 17 (about half a day; sets `password_set_by_owner_at`); (b) leave it out — those
  accounts go through an IS LEGACY grant. ~~Recommend (a)~~ — **withdrawn after round 2 (N1): see Q-107.**

## 18. Design review round 2 of 2 — the last (design-auditor, 2026-10-21: 1 high, 3 medium, 1 low new)
Round 1's P1, P3, P5, D1, D2, D3 and S3 are closed; P4 mostly; P2 and S1 partly; D4 tracked; S2 accepted by Ben
(VB-011). Per the two-round cap there is no third review: what remains is settled against the running code, and the
structural one goes to Ben.

| # | Finding (rating) | Disposition |
|---|---|---|
| N1 | AR-21's "owner set their own password" can be produced by the creator, who types every initial password; and the rule binds only the requester — a creator can launder an account through a second admin and later approve their own purge as it (HIGH) | **Structural — a decision for Ben (Q-107).** The premise does not hold until sign-in is Entra ID (D-35) |
| N2 | §10 and several body lines still stated replaced rules; no criterion for the new controls (MEDIUM) | **Fixed:** §1a, §4, §7, §10 (now 13 criteria, one per control), §13, §14 rewritten to rev 2 and AR-16…AR-23 |
| N3 | 0077's NOTICE list of skipped admins may never reach the operator (MEDIUM) | **Fixed in design:** criterion 12 derives "live admin with no approved grant" from the tables; build checklist runs 0077 on a copy and confirms the NOTICEs show |
| N4 | The backdating gate matches substrings of the database name ("latest", "evaluation") (MEDIUM) | **Fixed in design:** an exact list of the named test / demo databases (`vb_test_db` and its `_gw<n>` workers, names starting `vb_uat_` / `vb_demo_`); the IS CLI refuses `days` elsewhere (criterion 9) |
| N5 | Q-105 (a) makes LEGACY the routine way to add an admin (LOW) | **Fixed in design:** the LEGACY CLI requires the asking admin; the weekly check lists LEGACY rows without one |
| N6 | The AR-16 count can read low where the backfill skipped admins; 0078 copies a body that 0074/0075 may change (LOW) | **Fixed in design:** count the greater of grant rows and live flagged admins; 0078 copies the body at its parent revision and a test diffs it (criterion 5) |

**Question for Ben from round 2 (replaces the Q-106 recommendation):**
- **Q-107 — How is "the creator made a sock-puppet admin" closed?** VB has no way to give a person a password the
  creating admin cannot see, so "the owner set their own password" proves nothing. (a) **the creator of an account
  counts as having made that admin**: they may neither request nor approve its grant, and the account's creator is a
  "maker" in both independence checks — so a creator can never pair with an account they made, directly or through
  another admin; no password route is needed in slice 17 (Q-106 → (b)); (b) build the password route anyway and accept
  the gap until Entra ID. **Recommend (a)** — it closes N1 with one more column read in two functions, and Q-106's route
  can come with the Azure sign-in work.
- Q-105 stands: **recommend (a)**, a fresh install's third admin is one recorded IS LEGACY grant naming the admin who
  asked.

## 19. Ben's answers to Q-105 and Q-107 (2026-10-21, "go do 1") and schema rev 3 — the current design
Q-105 (a) and Q-107 (a), as recommended; Q-106 is therefore (b), no password route. Schema rev 3 (apple, 2026-10-22)
drops the `password_set_by_owner_at` column and its migration: **three migrations, 0076–0078, all pausing for Ben**
(Ren's OK 2026-10-22: no control weakened; what the dropped migration enforced is enforced in the database). The creator
rule (AR-21) is enforced by the grant guard (request, LEGACY and approval refused for the account's creator), by both
independence functions (the creator is a maker) and by the `app_user` guard (`created_by` never changes; an app-made
account names a live admin). Schema rev 3 §"Rev 3 changes" maps each criterion of §10 to the database object that
enforces it; §8 is the migration list. Two questions from rev 3 are with Ben (history §1).
