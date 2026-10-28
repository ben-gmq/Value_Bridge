# Approvers required — a per-installation setting (spec, 2026-10-24)

**Ben's ruling, 2026-10-24** ("Follow her recommendation. Let's go, Ren."): the hard-coded "a second admin must approve"
rule becomes a per-installation setting, **2 or 1**. This is **Ben's own change to his rulings Q-67…Q-85** (removal four
eyes, slice 16) and AR-18 / AR-20 / AR-24 (admin grants, slice 17), dated 2026-10-24. His terms:
- default 2; never below 2 on an installation holding client data or running on a server;
- only the owner command can set 1, and only on an installation marked local / single-owner;
- the admin page shows a clear banner while it is 1;
- every approval records "approved alone under the single-owner setting";
- the 24-hour wait and the type-the-code-to-confirm step are unchanged.

Data model by `apple` (2026-10-24), summarised here; Grade 1 (a permission gate and a data-destroying path).

## The setting
- `vb_instance` (NEEDS-CHANGES): `installation_kind varchar(20) NULL` (NULL = undeclared, treated as SHARED;
  `SHARED` | `LOCAL_SINGLE_OWNER`) and `approvers_required smallint NOT NULL DEFAULT 2`, with
  `CHECK (approvers_required IN (1,2) AND (approvers_required = 2 OR installation_kind IS NOT DISTINCT FROM
  'LOCAL_SINGLE_OWNER'))` — NULL-safe: an undeclared installation can never run at 1.
- The kind is **one-way**: NULL → either, once; LOCAL → SHARED (forcing 2) always; SHARED → LOCAL never. A re-stamp
  forces `approvers_required := 2`. Writes only as `vb_owner` (session and current user), naming an operator.
- `vb_instance_setting_log` (NET-NEW): one append-only row per change of kind or setting, written by a trigger (so no
  path changes the setting unlogged); `vb_app` SELECT only; joins `purge_run.NO_PROJECT_DATA` and `models/__init__.py`.
- One reader: `fn_approvers_required()` → 1 only when the kind is LOCAL_SINGLE_OWNER and the setting is 1; no row,
  NULL or mismatch → 2 (fails closed). Guards read it once per firing; the app reads it through one helper
  (`services/instance.approvers_required`), never re-implementing it.

## The checks (2 = exactly as today)
- `project_purge` and `platform_admin_grant` gain `approved_single_owner boolean NOT NULL DEFAULT false`, set only by
  the guard at approval (`quorum = 1`), forced false on insert, never changed after, not in `vb_app`'s UPDATE grant.
- `ck_pp_four_eyes` / `ck_pag_four_eyes` stay CHECKs: "approver ≠ requester **or** approved_single_owner"; the grant
  target never approves their own grant and requester ≠ target always. New `ck_pp_single_owner`,
  `ck_pag_single_owner` (the flag only on an approved row; grants only on REQUEST rows).
- Under 1: the same live admin may request and approve; AR-24 ("target created by requester/approver") and the
  "neither made the other" independence check apply only under 2; live-admin counts compare with the setting.
- An approval made alone **cannot be executed once the setting is back at 2** (guards and `fn_purge_allows`).
- Python mirrors follow: `services/admin_grant.py`, `services/purge_run.py`, the "fewer than two admins" alerts
  (`admin_grant.weekly_admin_lines`, `scripts/weekly_check.py`, `RemovalsTab.jsx`), all reading the one helper.

## Unchanged
The 24-hour wait; typed confirmation; live-admin checks; a target never approves their own grant; LEGACY owner-only,
BOOTSTRAP first two only; the owner-only DELETE path; rejection never by the requester.

## Migration 0079 (owner; reversible; paused for Ben before any non-throwaway database)
Columns and CHECKs above; the log table and its trigger; `fn_approvers_required`, `fn_admin_rights_aged`; the purge
and grant guards replaced by the SHA-freeze pattern (expect the 0077 / 0076 bodies); `fn_purge_allows` + one clause.
Downgrade refuses if any approval was made alone or the setting is or ever was 1.

## Open for Ben (the build takes the recommendation and flags it)
- **A-Q1** Under 1, does a removal's approver still need admin rights at least 30 days old? *Default: kept (unchanged
  rule; AR-20 is a purge (project removal) rule — a grant approval never had it).*
- **A-Q2** Under 1, may the same admin also run the removal (today the requester may not run it)? *Recommended: yes,
  only under 1 — otherwise a sole admin can never finish a removal.*
- **A-Q3** Server refuses to start when the database says single-owner but `.env` lacks
  `VB_INSTALLATION_KIND=LOCAL_SINGLE_OWNER`. *Recommended: yes.*
- **A-Q4** A SHARED installation stays SHARED for good; existing databases declare their kind once. *Recommended: yes.*
- **A-Q5** Back from 1 to 2: open approvals made alone are void and need a second admin. *Recommended: yes.*
- **A-Q6** 1 is allowed even with two or more live admins (every approval flagged). *Default: allowed.*

## Acceptance (Grade 1; each proven on a throwaway database, with the guard's refusal seen)
1. Fresh 0079: the setting reads 2; an undeclared or SHARED installation cannot be set to 1 (CHECK and guard).
2. Only `vb_owner` naming an operator can declare LOCAL and set 1; `vb_app` cannot; every change is one log row.
3. Under 2 every existing four-eyes test still passes unchanged.
4. Under 1, one admin requests and approves a removal; after 24 hours and the typed code it runs; the request and the
   audit carry "approved alone"; the purge record shows it.
5. Under 1, one admin requests and approves admin rights for an account they created; the grant is flagged.
6. A request approved alone, the setting then put back to 2: execution is refused.
7. SHARED → LOCAL refused; a re-stamp puts the setting back to 2.
8. The admin page shows the banner while the setting is 1, and not under 2.
9. 0079 downgrade refuses after any lone approval; otherwise it round-trips.
