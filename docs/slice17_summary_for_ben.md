# Slice 17 on one page — who may make someone a platform admin (2026-10-23)

**For:** Ben's OK. **The full spec:** `docs/slice17_admin_grant_spec.md` (§19 is the current state) · **schema:**
`docs/slice17_admin_grant_schema.md` rev 3.

## What it does for you
A platform admin sees every client's projects and can approve the permanent removal of one. Today any one admin can
make anyone else an admin with a click. After slice 17 **nobody becomes an admin on one person's say-so**:

- One admin **asks** ("Request admin rights", with a reason — who asked for it and for which engagement).
- A **different** admin **approves** — and the user is an admin that moment. Or rejects (with a reason), or anyone
  cancels.
- The approver must be **independent** of the one who asked: neither made the other an admin, and — your answer to
  Q-107 — **neither created the other's account**. So an admin can never create an account, then get it made an admin,
  then use it as their "second pair of eyes" — not directly, and not through a colleague.
- The database itself refuses every other way to the admin switch, for the app and for the server's own login alike.

## Your two answers, built in
- **Q-107 (a):** whoever created an account counts as having made that admin. They can never ask for or approve its
  admin rights, and never pair with it on any approval — including the approval of a project's removal.
- **Q-105 (a):** on a fresh install the first two admins come from Fortience IS's command line; **the third is one
  recorded IS grant naming the admin who asked**. Every admin after that comes through a request.

## What changes for you day to day
- The users page: **"Make admin" becomes "Request admin rights"**, and a **"Pending admin requests"** card shows each
  request with the person's email, who created their account and when, whether they have ever signed in, and how many
  days the request has waited — what an approver needs before saying yes.
- **Removing** someone's admin rights stays a one-admin action — the safe direction.
- **Removal approvals** (slice 16) now check independence from this record instead of the audit log, which the app
  could write to; the approver's admin rights must still be 30 days old.
- **Small teams feel it:** with three or four admins, some pairs can never approve each other. Practical rule: *the admin
  who creates a new account is the one who asks for its rights* — then the others stay free to approve.

## What it costs
- **Time:** planned 1 day; actual about 1½ — the extra half moved every existing test onto the proper paths.
- **Fortience IS** becomes part of the process: the first two admins, and any admin after a loss, are IS jobs, never a
  platform admin's (your ruling AR-22).
- **No new table for passwords:** your Q-107 answer removed it — **three database changes instead of four**, and the
  rule moved into the database, stricter than before.

## Where it stands
- **Built, not switched on anywhere.** Six commits on my branch, **not pushed**; the three database changes (0076–0078)
  exist only on my own throwaway test databases. Each **pauses for your click** before any other database.
- Tests for each of the 13 agreed checks pass on their own; **the full test run and Sara's review were interrupted**
  when the session ended on 10-22 and must be re-run before anything is called done.
- **Two small questions** (design history Q-108, Q-109), both recommended yes: (1) only databases named
  `…_test_db`, `…_uat_db` or `…_demo_db` may carry back-dated IS grants (a UAT database named `vb_uat_2026` would not);
  (2) the database also refuses an app-made account that names no live admin as its creator, and locks the creator
  for good — otherwise the creator rule could be edited away.

**The ask:** OK the spec as summarised here (with Q-108 and Q-109 as recommended), so I can finish its review, full test
run and browser check, and push it.
