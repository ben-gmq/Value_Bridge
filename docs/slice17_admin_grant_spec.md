# Slice 17 — Platform-admin grant approval (spec, DRAFT for Ben, 2026-10-21)

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
  or rejection; any platform admin's cancellation. Bootstrap only: the operator's `seeds.create_admin` while fewer than
  two live platform admins exist (Q-95).
- **Output:** on approval, the user is a platform admin in the same transaction, with one `PLATFORM_ADMIN_GRANTED`
  audit row naming requester and approver; the request record, kept forever. Removing admin rights is unchanged
  (one admin, a reason, the existing preview) — Q-96.
- **Validation:** refused: a non-admin (403); no reason (422); the requester approving their own request, or the
  target approving a request about themselves (409); a second open request for the same user (409); a target who is
  inactive or already an admin (409); an approval by an admin whose own grant fails AR-13 (a) (409, the slice 16 rule
  applied here too — Q-97); any change of `app_user.is_platform_admin` from false to true that is not the approval of
  an open request in the same transaction, or the bootstrap path — refused by the database for every role.
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
| `admin_grant.approve` | `platform_admin_grant` | U | open; approver ≠ requester, ≠ target; approver a live admin passing AR-13 (a) → `approved_*` set (time by the database) |
| `admin_grant.approve` | `app_user` | U | target still active and not an admin → `is_platform_admin = true`, same transaction |
| `admin_grant.approve` | `audit_event` | C | `PLATFORM_ADMIN_GRANTED`, actor = approver, detail {requested_by, grant id, reason} — for people to read; **AR-13 never reads it** (it reads `platform_admin_grant` through `fn_admin_grant_independent`, §16 P3) |
| `admin_grant.reject` | `platform_admin_grant` | U | open; any live admin other than the requester → `rejected_*` + reason; audit |
| `admin_grant.cancel` | `platform_admin_grant` | U | open; any live admin → `cancelled_*`; audit |
| `admin_grant.list` | `platform_admin_grant`, `app_user` | R | open requests first, then decided; names of the people |
| `user_admin.set_platform_admin` (existing) | `app_user` | U | **grant branch removed** (422 → "request it"); remove branch unchanged |
| `seeds.create_admin` (existing CLI) | `app_user`, `audit_event` | C | allowed only while fewer than two live platform admins exist (Q-95); else refuses |
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
    access.independent_approver(db, actor, g.requested_by) else 409 (AR-13 a — the one function slice 16 uses too)
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
4. An approver whose own grant is under 30 days old, or was requested or approved by this requester, is refused
   (AR-13 a, applied here as in slice 16 — Q-97).
5. Reject (with a reason) and cancel close the request; a closed request never changes; the user can be requested
   again afterwards.
6. `PATCH /users/{id}/platform-admin` with `true` → 422; removal works as before.
7. **At the database, for `vb_app` (and `vb_owner` outside the recorded LEGACY path, Q-98):**
   `UPDATE app_user SET is_platform_admin = true` — reactivating a deactivated admin included — is refused unless an
   approved REQUEST for that user was approved in the same transaction; an INSERT of a user with
   `is_platform_admin = true` is refused unless fewer than two live platform admins exist (the bootstrap, Q-95), and
   records a BOOTSTRAP row.
8. `seeds.create_admin` succeeds with zero or one live admin and refuses with two or more.
9. The request record refuses DELETE for every role; the app role cannot backdate `approved_at`.
10. The users page shows pending requests and their actions; seen in a browser (ui-verifier), side by side with the
    admin mockup.

## 11. Assumptions
- `ASSUMPTION` A-17-1: removing admin rights stays a one-admin action — it is the safe direction (Q-96).
- `ASSUMPTION` A-17-2: requests do not expire; the weekly check names old ones and an admin cancels them.
- `ASSUMPTION` A-17-3: `first_run_setup` stays as is (only with no users at all, and only where it is switched on).
- `ASSUMPTION` A-17-4: the target is told out of band; no e-mail exists in VB.

## 12. Out of scope
Two-person removal of admin rights (unless Q-96 says otherwise) · request expiry · notifications · changing a user's
kind (USER / VIEWER) · Entra ID group-based admin rights (Azure, D-35).

## 13. Grade and test depth
**Grade 1** — a wrong answer grants access to every client's data. Proposed depth: criteria 1–9 as service and
database tests for both roles (the guard proven directly, as slice 16's purge record); one browser pass (criterion
10). A mutation harness is justified at this grade but is its own approved piece of work, not this slice.

## 14. Build checklist
One migration per commit, reversible (apple's list) · `sara` before the commit (grants, access) · `ROUTE_COMPONENTS`
and the route-guard tests updated · strings via `t()` · AR-13 is answered only by the database function
`fn_admin_grant_independent` over `platform_admin_grant` — in both guards and in `access.independent_approver`, which
calls it rather than re-implementing it (§16 P3) ·
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
