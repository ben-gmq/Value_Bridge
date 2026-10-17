# Slice 16 — Baseline archive file + `purge_project` (spec, DRAFT for Ben, 2026-10-17)

**Status:** DRAFT — not approved, not built. After design review rounds 1–2 (the cap; §17, §18). Needs Ben's answers
(Q-67…Q-85) and his OK. **Source of truth:**
`docs/VB_design.md` §15.3 (the evidence archive and contract-required deletion), the Q15 paragraph in §6, criteria 154–155,
§6.6 (the two roles; "the owner role's secret is available only to the migration job"), plan row "Baseline archive file
+ `purge_project`" in `docs/VB_remaining_work.md` (stream B, 2 days, no dependency). **Schema:**
`docs/slice16_archive_purge_schema.md` (apple, 2026-10-17). This spec adds the flow, the functions, routes, acceptance
and the grade.

## 1. Purpose
Keep a sealed, encrypted copy of every frozen baseline outside the database for five years, and — when a client contract
requires it — remove one project completely, leaving its archive copies unreadable and a record that the removal happened.

## 1a. Interface
- **Input:** (archive) every successful baseline freeze, automatically; (purge) a platform admin's request naming the
  project, a reason and the typed project code, then an FTC operator running the purge job.
- **Output:** (archive) one encrypted JSON file per baseline in write-once storage, and its row in `baseline_archive`;
  (purge) no live, snapshot or archive-readable data left for the project, the project's key destroyed, one
  `project_purge` record and a `PROJECT_PURGED` audit row (code, client, date, actor, reason — no content).
- **Validation:** the archive writer re-reads the frozen rows and refuses to write a file whose recomputed digest differs
  from the header's; a file is never overwritten. The purge refuses: a non-admin (403), no reason (422), a wrong typed
  code (422), a second open request for the project (409), and an execution without a second admin's approval, or within
  24 hours of that approval (Q-72).
- **Archive:** the archive file *is* the archive (5 years, locked); the purge record and audit rows are kept forever
  and hold no client content.
- **Maintenance loop:** the archive writer's backlog (`baseline_archive` rows still owed, and those with an error) is shown to
  platform admins and checked at each release; the restore drill (§15.3) recovers one baseline from its file into a side
  database before first client use and once a year after.

## 2. Playbook / doctrine
`~/.claude/ftc-playbook.md` §9 items 7 (soft delete — this is the one recorded exception, Q15), 10–11 (one service per
concern), §2 (`created_by` from the token). VB law 1 (the hard-delete list already names `purge_project`), law 2
(immutability — this slice adds a narrow purge exception, Q-75), law 3 (audit columns), law 10 (migrations one per
commit, destructive pauses). Deviations: none proposed.

## 3. Keystone grain
**`baseline_archive` — one row per frozen baseline: the archive file owed for it.** It is the outbox that makes "every
freeze writes a file" provable: a baseline whose row is still owed is a visible gap, never a silent one.
`project_purge` — one row per purge of one project; it outlives the project (no FK to it).

## 4. Business Requirement — the grid

| Function | Entity | Use | Business logic → output data |
|---|---|---|---|
| `baseline.freeze` (existing) | `baseline_archive` | C | in the freeze transaction: one owed row for the new baseline |
| `archive.write_pending` | `baseline`, the 28 `baseline_*` shadows | R | read the header and every shadow row of one baseline, hashed columns as Postgres `::text` |
| `archive.write_pending` | `baseline_archive` | U | recompute the digest from the rows read; equal → encrypt, store write-once, set the object name, sha256, size, key ref and `written_at` together; else count the attempt and keep the error |
| `archive.write_pending` | project key (outside DB) | R | create the project's key on first use; wrap a fresh data key per file |
| `archive.verify_file` | archive file, project key | R | decrypt, recompute every row hash and the digest in Python from the stored text → matches / names the first mismatch |
| `archive.restore` (manual, drill) | side database | C | load one file into a side database and run the SQL verify there |
| `purge.request` | `project_purge` | C | open request: reason, requester, typed code checked; while it is open every write to the project is refused (Q-73) |
| `purge.cancel` | `project_purge` | U | `cancelled_at` / `cancelled_by`; writes allowed again |
| `purge.execute` (operator CLI, `vb_owner`) | every project table, 28 shadows, `baseline`, `baseline_archive`, `code_master` overrides, `import_row` | D | in one transaction, child before parent (computed from the catalog), scoped trigger bypass for this project only (Q-75) |
| `purge.execute` | `project` | D | last, in one statement with its `code_master` overrides |
| `purge.execute` | `audit_event` | D / C | the project's old audit rows go under Q-69 (b); `PROJECT_PURGED` (code, client, reason, actors, counts) is written |
| `purge.execute` | `project_purge`, `project_purge_key` | U / C | `executed_at`, executor, `backups_age_out_on`; one key row per key name to destroy |
| `purge.destroy_key` | project key (outside DB), `project_purge_key` | D / U | after the commit: write the tombstone, then delete **and** purge each recorded key of this instance (Q-71); each key row's `destroyed_at` |
| (manual) FTC operator | Azure backups | — | point-in-time restore ages out in 35 days, the monthly dump in 13 months; the record states the date |

## 5–6. Logical and physical design
**apple:** `docs/slice16_archive_purge_schema.md` — `baseline_archive` (NET-NEW, PK `baseline_id`, write-once file
columns, state derived from `written_at`), `project_purge` (NET-NEW, no FK to `project`, state derived from
`cancelled_at` / `executed_at`, one open and one executed per project), `fn_purge_allows` + a new
`fn_reject_modification_purgeable` for the 28 shadows + the header guard's DELETE branch (NEEDS-CHANGES; the shared
`fn_reject_modification` that guards `audit_event` is **not** touched), `audit_event` (NEEDS-CHANGES: drop its FK to
`project` — only under Q-69 (a); under (b) the `PURGE_*` events are written with `project_id` NULL and the id in
`detail`, and the FK stays), the purge order (§8 there), migrations 0061–0066 (final list in §17 R1). No key material in any table.
**Where this spec and apple differ, apple's schema wins**; I adopted her corrections: derived state instead of status
codes, a separate purgeable function, ids-only file and key names, the lock correction (DISABLE TRIGGER blocks other
projects' freezes, not their reads — and guards nothing while off, which is the real reason not to use it).

## 7. Functions

**Archive file format (one per baseline).** An envelope, so the same code runs on a local key folder now and on
Key Vault later:
```
{ "format": "vb-baseline-archive/1", "instance_id", "project_id", "baseline_id", "key_ref",
  "wrapped_data_key", "nonce", "ciphertext" }          # AES-256-GCM; the project key only wraps the data key;
                                                       # ids only outside the ciphertext — no code or name
plaintext = { header: every baseline column, hash_spec_version, content_digest,
              tables: { <shadow>: [ { source_id, content_hash, columns: { name: <Postgres ::text or null> } } ] } }
```
Columns are stored as their Postgres text form (`c::text`), the same input `freeze_set.hash_sql` hashes, so a reader can
recompute each `content_hash` and the digest without a database (criterion 155) — the Python recompute mirrors
`hash_sql` and `digest` and is tested against them on every shadow.

```
archive.write_pending(db, store, keys, limit):            # services/archive.py — the one writer
    for row in baseline_archive where written_at is null for update skip locked, limit:   # owed, incl. failed
        b = baseline header; rows = per shadow at b.hash_spec_version, columns as ::text
        if python_digest(rows) != b.content_digest:
            attempt_count += 1; last_error = "digest mismatch"; audit ARCHIVE_FAILED; continue
        dek = random 32 bytes; wrapped, key_ref = keys.wrap(project_id, dek)   # creates the project key on first use
        blob = envelope(aesgcm(dek).encrypt(json(plaintext)))
        name = f"{env}/{project_id}/{baseline_id}.json.enc"                    # ids only
        store.put_once(name, blob)                         # refuses if the name exists (write-once)
        set object_name, file_sha256, byte_size, key_ref, written_at together; audit ARCHIVE_WRITTEN
    commit per row
```
Called right after `baseline.freeze` commits (best effort, its failure never fails the freeze), and by
`python -m scripts.write_archives` for the backlog and for baselines frozen before this slice (Q-77).

```
archive.verify_file(blob, keys) -> {ok, first_mismatch}   # the drill and criterion 155; also scripts.verify_archive
```

```
purge.request(user, project_id, reason, confirm_text):    # services/purge.py; route guard platform_admin
    reason required (422); confirm_text == project.project_code (422)
    an open request already (409, uq_pp_open); insert project_purge; audit PURGE_REQUESTED; commit
    # from now project_ctx / object_guard refuse every write to it: 409 PURGE_PENDING (Q-73), the freeze included

purge.execute(owner_db, project_purge_id, executor_email): # scripts/purge_project.py, MIGRATION_DATABASE_URL, operator
    p = open, approved request for update; approved >= 24 h ago; requester and approver distinct, both live
        platform admins now (Q-72, round 2 L1)
    print client name, project name, latest baseline, per-table counts; operator types <client_code>/<project_code>
    begin; lock the project row; set_config('vb.purge_project_id', p.project_id, true)   # the scoped bypass (Q-75)
    order = catalog sort from pg_constraint; refuse any table with project_id in neither the delete set nor KEEP
    delete in that order (schema §8), each statement filtered to the project; strongly connected sets in one statement
    prove zero: every table with project_id, and every shadow by baseline_id, counts 0 for the project — else rollback
    p.executed_*, backups_age_out_on (ICT) ; project_purge_key rows from the key refs read before the deletes;
    audit PROJECT_PURGED (codes, counts, requester, approver); commit
purge.destroy_key(p):                                      # same script, after the commit
    store.put_once(f"{instance}/purged/{project_id}", tombstone)    # R4
    for k in p.keys under this instance's prefix: keys.destroy(k)    # Azure: delete, then purge (Q-71)
        k.destroyed_at = now(); commit   # a failure leaves executed_at without key_destroyed_at: reported, rerunnable
                                         # (key after commit: a rollback after the key is gone would strand a live
                                         #  project with unreadable archives; the reverse is retryable)
```

**Storage and keys behind two small interfaces** (`services/archive_store.py`): `ArchiveStore.put_once/get` and
`ProjectKeys.wrap/unwrap/destroy`. Local: a folder outside the repo set by `VB_ARCHIVE_DIR`, files created with
`O_EXCL` and made read-only; keys as one file per project under `VB_ARCHIVE_KEY_DIR` (destroy = remove the file).
Azure (later, with D-35): Blob Storage with a locked immutability policy, Key Vault keys (wrap/unwrap in the vault;
destroy = delete and purge the key). Encryption uses `cryptography` (AESGCM) — a new dependency (Q-76).

## 8. `code_master`
None, if Q-67 goes as recommended: archive and purge state is derived from their dates and shown through `t()`.

## 9. API (`/api/v1`)
| Method · path | Guard | In → out |
|---|---|---|
| `POST /projects/{project_id}/purge-requests` | platform_admin | `reason`, `confirm_text` → the open request; writes to the project now 409 |
| `POST /purge-requests/{id}/cancel` | platform_admin | → cancelled; writes allowed again |
| `GET /purge-requests` | platform_admin | every purge record (no content: code, client, dates, actors, reason) |
| `GET /projects/{project_id}/baselines/{id}/archive` | project_ctx(VIEW) | the archive row's status, name, size, written_at — never the file |
| `GET /admin/archive-backlog` | platform_admin | owed rows (and their last error) across projects |

There is **no HTTP route that deletes**: execution is the operator script, as the owner role (design §6.6). The design's
`POST /projects/{project_id}/purge` becomes the request route above (Q-74). A project with an open request refuses every
write with 409 PURGE_PENDING — one check in the write guards, read from `project_purge`, not in each service (Q-73).

## 10. Acceptance criteria
1. A freeze leaves one `baseline_archive` row; after the writer runs `written_at` is set, and the file exists under its name.
2. Decrypting the file and recomputing every row hash and the digest in Python matches the frozen rows (criterion 155),
   for a baseline touching every one of the 28 shadows.
3. A changed byte in the file fails `verify_file`, naming the table and source id; a second write to the same name is
   refused by the store.
4. A writer crash between the freeze and the file leaves the row owed; the backlog command writes it later; the freeze is never
   rolled back by a writer failure.
5. `POST …/purge-requests` by a non-admin → 403; without a reason → 422; with the wrong code → 422; a second request →
   409. After a request every write to the project → 409; cancelling restores writes.
6. The purge script refuses: no open request, an executor who is not a live platform admin, the requester as
   executor, no second admin's approval or one under 24 hours old (Q-72), and a table holding `project_id` that is in neither the delete set
   nor `KEEP` (the next slice's new table can't be skipped silently).
7. After execution no row with the project's id remains in any table that has a `project_id` column, no shadow or
   header row of its baselines, no `import_row` of its batches, no `code_master` override — checked by a catalog query
   over every table, not a hand list.
8. Another project's baselines, live rows and audit rows are byte-identical before and after (digest + row counts), and
   its baseline reads are not blocked while the purge runs (no `ALTER TABLE … DISABLE TRIGGER`).
9. After execution the project key is gone and an archive file written for it can no longer be decrypted (criterion 154).
10. A `PROJECT_PURGED` audit row names the code, client, actors, date, reason and per-table counts, and no text of the
    project; under Q-69 (b) no other audit row of the project remains and no other project's audit row changes.
11. `vb_app` still cannot DELETE a shadow or header row, even with `vb.purge_project_id` set; the owner cannot either
    without an open request for that project, nor delete a row of another project with the setting naming this one;
    no role can UPDATE a frozen row.
12. The purge is one transaction: a failure part-way (forced in a test) leaves every row in place and the request open.
13. While a request is open, every write to the project (the freeze included) → 409 PURGE_PENDING; reads still work.

## 11. Assumptions
- ~~A-16-1 audit `detail` holds no client content~~ — **false** (apple): `lifecycle` writes item labels ("BR-0042
  Approve invoice") and `effort.py` a `change_rationale`. Hence Q-69.
- `ASSUMPTION` A-16-2: deletion of the Azure backups is not asked for; the contract accepts "unreadable now, gone from
  backups within 13 months". **If a contract needs faster, the deployment design changes, not this model.**
- `ASSUMPTION` A-16-3: copies outside VB (downloaded exports, screenshots, e-mailed reports) are the engagement's to clear;
  the purge record lists them as out of reach.
- `ASSUMPTION` A-16-4: a purge is rare (end of engagement), so a few seconds of lock on the purged project's rows is fine.
- ~~A-16-5 every shadow row carries the project id~~ — the copy is nullable; the bypass reads the header's NOT NULL
  `project_id` through `baseline_id` instead (schema §4).
- `ASSUMPTION` A-16-6: the owner role is named `vb_owner` in every environment (the bypass names it; the Azure roles
  in D-35 must keep the name, or the function is regenerated there).

## 12. Out of scope
Azure Blob and Key Vault implementations (with D-35) · deleting or shortening the Azure backups · a screen for archive
contents or for restoring (the drill is a script) · purging a program, a client or a user · key rotation · the client
read-only login and offline viewer (D-43, which will read these files later).

## 13. Grade and test depth
**Grade 1** — the purge destroys client data and keys irreversibly, and a wrong scope deletes another client's work.
Proposed depth: criteria 5–12 as service and script tests against the test database, with two concurrency tests (a freeze
in another project during a purge; a write to the purged project during it). **A mutation harness over the purge
order and the scoped bypass is justified at this grade, but it is its own approved piece of work** (Q-78), not part of
this slice. The archive writer is Grade 2 (a missing file is visible as owed; the hash recompute is proven against
the SQL on every shadow).

## 14. Build checklist
Migrations from 0061, one per commit, reversible; dropping the audit FK and changing the trigger functions pause for Ben
· shadows untouched (no new shadow) · `cryptography` added only after Ben's OK · `sara` before the commit (baselines,
grants, the migration chain) · no key or credential in a file in the repo, a log or an audit row · the operator script
prints what it will delete (counts per table) and needs the project code typed again · full suite before merge.

## 15. Questions for Ben
Q-67…Q-73 are apple's (schema §10, full reasoning there); Q-74…Q-78 are mine. All carry a recommendation.

- **Q-67 — Status codes, or state worked out from the dates?** **Recommend:** from the dates (`written_at`,
  `cancelled_at`, `executed_at`); a stored status could disagree with them.
- **Q-68 — Leave soft delete off the two new tables?** Neither row can ever be retired. **Recommend:** yes, as the
  baseline header already does (created/updated columns and `row_version` kept) — an exception to law 3 you accept.
- **Q-69 — Does the project's activity history go too?** It holds client text (item labels, effort rationale), so
  keeping it breaks "no content left". (a) keep it and drop its database link to the project; (b) delete it in the
  purge, keeping only the purge events — this gives the activity log the same narrow exception as the baselines (its
  own purgeable guard; the shared one stays strict); (c) encrypt history under the project key from now on.
  **Recommend (b)**, confirmed by whoever reads the client contract; (a) only if they say labels may stay.
- **Q-70 — Should a client sign-off wait until its archive file exists?** **Recommend:** no; show "archive owed" on the
  baseline and alert if a file is owed for more than an hour.
- **Q-71 — What does "key destroyed" mean in Azure?** Key Vault keeps deleted keys recoverable for 7–90 days.
  **Recommend:** deleted and then purged; the archive vault keeps deleted keys 7 days and has no purge protection.
- **Q-72 — Four eyes on the purge?** **Recommend:** the person who runs it must not be the person who asked, and the
  request must be at least 24 hours old. Needs two platform admins at FTC.
- **Q-73 — Freeze the project while a purge waits?** **Recommend:** yes — every write refused (409) while a request is
  open, read from the request itself, not a second flag; cancelling lifts it.
- **Q-74 — Who presses the button?** The design puts the purge behind a web route as the owner role, but also says the
  owner credential never reaches the running app. **Recommend:** the app records the request; an FTC operator runs the
  purge script with the owner credential.
- **Q-75 — How do frozen baselines let go?** They refuse deletion for every role. Switching the guards off protects
  nothing while they are off. **Recommend:** the narrow exception in schema §4 — the owner only, inside a purge
  transaction, only rows of the one project with an open request. A change to VB law 2 that you accept.
- **Q-76 — New dependency `cryptography`** (the standard Python crypto library on PyPI, maintained by the Python
  Cryptographic Authority). **Recommend:** yes; no hand-rolled crypto.
- **Q-77 — Archive files for baselines frozen before this slice?** **Recommend:** yes, once, by the backlog script,
  each checked against its digest first (migration 0061 creates their owed rows).
- **Q-78 — A mutation harness for the purge?** **Recommend:** yes, as its own task after this slice lands (about half a
  day): it proves the tests fail if the order, the project filter or the bypass scope is broken.

## 16. Size
About 3.5 days after round 1 (the plan said 2): archive writer, format, verify, local store and keys 1.5 days; purge
request, approval, pending-purge check, script with counts and tombstone 1.5 days; tests and the drill script 0.5 day.
Azure implementations are part of the Azure work (D-35).

## 17. Revision after design review round 1 (design-auditor, 2026-10-17: 1 blocking, 7 high, 8 medium, 5 low)
Every finding is fixed in the design except one, which is Ben's question (Q-79). Where this section and an earlier one
differ, **this section wins**; schema changes are in the schema's §11 (apple). Round 2 of 2 follows; after it, what
is left is tracked and settled against the code.

| # | Finding (rating) | Disposition → change |
|---|---|---|
| R1 | Q-69 (b) deletes audit rows with no mechanism (BLOCKING) | **Fixed.** Schema §11: `fn_reject_modification_audit_purgeable` on `audit_event` only (DELETE only under `fn_purge_allows`, never a `PURGE_*` event; UPDATE never); the shared function stays strict for everything else. Under (b) purge events carry `project_id` NULL and the id in `detail`, so the audit FK stays; migration 0066 is exactly one of (a) drop the FK or (b) the audit trigger change, decided by Q-69. Final migrations (schema §9/§11): 0061 `baseline_archive`, 0062 `vb_instance`, 0063 `project_purge`, 0064 `project_purge_key`, 0065 the scoped bypass, 0066 (a) or (b); 0065 and 0066 pause for Ben. |
| R2 | Four eyes rests on a typed email (HIGH) | **Fixed.** A second platform admin approves in the app (`approved_by` ≠ requester, authenticated). `fn_purge_allows` and the script need an approved request; the 24 h runs from approval. `--actor-email` is a label only. Route: `POST /purge-requests/{id}/approve` (platform_admin). |
| R3 | Typed code can't tell two clients' `ERP-01` apart (HIGH) | **Fixed.** The confirmation is client code + project code at the request, the approval and the script; the script prints the client name, the project name and the latest baseline label before asking. |
| R4 | A restore before the purge brings the data back (HIGH) | **Fixed.** Destroying the key also writes a write-once tombstone `<instance>/purged/<project_id>` in the archive store; the writer refuses to create a key for a tombstoned project and says why; the restore runbook (§15.3 drill) lists tombstones first and re-runs those purges. How fast, and who is told: Q-83. |
| R5 | Other projects' live rows guarded only by each WHERE (HIGH) | **Fixed — first.** Count per table for the project and each table's total before deleting; after each DELETE the rowcount must equal the project's count, and before commit each total must have fallen by exactly that — else roll back. The one control that doesn't depend on the filters being right. |
| R6 | Writer checks the digest, not the text it stores (HIGH) | **Fixed.** The writer runs `verify_file` on the exact bytes it is about to store (decrypt, recompute every row hash and the digest) and stores only on success. |
| R7 | The file never holds the client's sign-off (HIGH) | **Question for Ben (Q-79).** If yes: a second owed file per baseline, written when the approval is recorded, same outbox; the main file is not delayed. |
| R8 | Key and file names collide across environments and restores (HIGH) | **Fixed.** Names start with an instance id (schema §11); the purge records the exact `key_ref`s used by the project's files and destroys those; before marking a key destroyed, it proves it by failing to decrypt one stored file. |
| R9 | Stored file but row not marked → owed forever (MEDIUM) | **Fixed.** On "name exists" the writer reads that file, verifies it against the frozen rows and adopts it; a test forces the case. |
| R10 | Always-failing rows starve the queue; an audit row per retry (MEDIUM) | **Fixed.** Order by `last_attempt_at NULLS FIRST`, skip rows tried in the last 6 h; `ARCHIVE_FAILED` only when the error changes. |
| R11 | Half-finished states have no owner; maintenance loop vague (MEDIUM) | **Fixed.** The platform-admin purge list shows "executed, key not destroyed" and "backups age out on <date>"; the destroy step treats "deleted, not yet purged" as "go on and purge". Maintenance loop: a named owner checks owed archives, unfinished purges and `verify_archive --all` **weekly** — who is Q-84. |
| R12 | Only `project_id` tables are classified (MEDIUM) | **Fixed.** Every `public` table is in exactly one of DELETE (computed), KEEP or NO_PROJECT_DATA; an unlisted table stops the purge. |
| R13 | The file can't be checked without 2026 source code (MEDIUM) | **Fixed.** The plaintext carries `hash_spec_version`, the ordered table list (empty tables included), each table's hashed columns and a one-line algorithm description. |
| R14 | Nothing checks a written row has its file (MEDIUM) | **Fixed.** `verify_archive --all` (exists, size, sha256; no decryption) runs weekly (R11); a mismatch reopens the row as owed and alerts. The local store fsyncs the file and its folder before the row is marked. |
| R15 | Where the two powerful credentials live (MEDIUM) | **Fixed in principle, built with D-35.** The purge runs as a one-off job in the migrations pipeline and identity, with the request id as its only input; the app's Key Vault rights are create, get and wrap only; delete and purge belong to the job alone. Locally the owner URL stays in the gitignored `.env`, as today. |
| R16 | Key creation on first use races (MEDIUM) | **Fixed.** Create-if-absent, versioned refs even locally; a key is never replaced (schema §11). |
| R17 | Platform-admin write paths skip the pending-purge check (LOW) | **Fixed.** One check in `services/access`, called by the write guards **and** by the services behind platform-admin writes (program attach, company code lists, seeds that write to every project); criterion 13 calls every non-GET route, like the read-leak test. |
| R18 | Envelope ids not bound to the ciphertext (LOW) | **Fixed.** Format, instance, project_id, baseline_id and key_ref are AES-GCM associated data; `verify_file` checks them against the file name. |
| R19 | `last_error` may hold client text (LOW) | **Fixed.** Error class plus a fixed message per known error, never the exception text. |
| R20 | Drill side databases outlive a purge (LOW) | **Fixed.** The drill script drops its side database at the end and records it; the purge record lists "drill copies: none open" as checked. |
| R21 | `backups_age_out_on` timezone (LOW) | **Fixed.** Computed in ICT from the database `now()`. |

**Acceptance criteria added:** 14. A purge that would delete one row more than counted in any table rolls back,
naming it (forced with a planted row of another project). 15. A purge is refused without a second admin's approval, or
within 24 h of it. 16. After a restore to before a purge, the writer refuses to archive the project and names the
tombstone. 17. A file stored but not recorded is adopted on the next run after verification. 18. Two writers for one
project create one key. 19. A file whose ids were swapped fails `verify_file`.

**Questions for Ben added (from the auditor; business rules, left unanswered by me):**
- **Q-79 — Must the five-year evidence include the client's sign-off** (approver, date, signed-document reference),
  or only the frozen scope? **Recommend:** yes — a dispute turns on who approved what; a second file at approval.
- **Q-80 — Should a record of who had access, and when, survive a purge** with labels removed? Q-69 (b) erases it.
  **Recommend:** keep only the purge events (as drafted); decide with whoever reads the contract.
- **Q-81 — Who authorises a purge?** Is a platform admin's reason enough, or must it cite a signed client
  instruction, checked by the approver? **Recommend:** the reason cites the signed instruction's reference; the
  approver checks it.
- **Q-82 — May the purge record name the client?** The kept `reason`, `project_code` and the surviving `client` row
  can. **Recommend:** yes for the client row and the codes (FTC must show whose data it removed); the reason cites a
  reference, not content.
- **Q-83 — After a restore that predates a purge, how fast must the purge be redone, and who is told?**
  **Recommend:** before the restored database takes traffic; Ben and the client contact are told.
- **Q-84 — Who owns the weekly check** (owed archives, unfinished purges, file check)? **Recommend:** an FTC platform
  admin named per environment, with a weekly report as the reminder.
- **Q-85 (apple) — What does the app show for a purged project that a restore brought back?** The tombstone stops
  new keys, but the rows are visible again. **Recommend:** the app answers 404 for a tombstoned project, and the
  restore runbook re-purges it with a second approver but without the 24 h wait.
- **Apple's push-backs, adopted:** any platform admin may cancel a request (cancelling is the safe direction); keys are
  destroyed by key name, since Key Vault deletes a whole key, and the project's computed key name is always included.
- **Left for the Azure work (D-35):** one archive vault without purge protection means one bad deletion could make
  every client's evidence unreadable (auditor question 6). **Recommend:** one vault per client, so a mistake stays
  with one client.

**COULD NOT REVIEW, addressed:** slices 14–15 tables → the classification lists are pinned by a test that fails on an
unlisted table, so they are covered when they land; the restore loader → it loads with parameters (COPY), never
string-built SQL, and is in this slice's acceptance (the drill script); Azure Blob immutability and Key Vault
permissions → designed with D-35, against R8 and R15; the pending-purge check's place in the guards → R17; column
types vs `::text` → the writer's own verify (R6) catches a mismatch on real data; logs → re-checked at the
pre-client Sara pass.

## 18. Design review round 2 of 2 — the last (design-auditor, 2026-10-17: 0 blocking, 3 high, 3 medium, 3 low)
Nothing structural. Per the two-round cap there is no third review: each finding below is **adopted as a build rule**
and settled against the running code, with its test in the slice. Where this section and §17 or the schema differ,
**this section wins** until the schema is updated at build. The three HIGHs need Ben's OK on the approach.

| # | Finding (rating) | Build rule |
|---|---|---|
| S1 | The count and the delete share one predicate, so neither catches a wrong one; R5 not closed (HIGH) | Before deleting, record for every DELETE table the count of rows **not** of the project, computed on the table's own `project_id` column (for `import_row`, from its batch's `project_id` read separately), never through the delete's join path; require it unchanged before commit. The per-statement rowcount stays as a race check. Criterion 14 becomes "a planted row of another project reached by a wrong predicate rolls the purge back". **Fix first.** |
| S2 | Destroying every recorded key name can destroy another environment's key (HIGH) | Destroy only names under the current `vb_instance` prefix; any other name is recorded "not destroyed: other instance" and the script stops for the operator. Each environment's purge job holds rights to its own vault only (D-35). |
| S3 | A point-in-time restore rewinds the id sequences, so a new project can inherit an old project's key and file names (HIGH) | A restore step (in `stamp_instance` and checked at start-up) moves every identity sequence past the highest project and baseline ids found in the archive store and its tombstones before the database takes traffic. The alternative — a restore generation in every name — is a format change and Ben's call. |
| S4 | The total counts move under live traffic; an over-delete can hide behind unrelated inserts (MEDIUM) | The purge transaction runs at REPEATABLE READ, so before and after counts come from one snapshot; a serialization failure means "retry". |
| S5 | "A mismatch reopens the row as owed" can't work: the written row is locked (MEDIUM) | The weekly check records failures in their own columns (`check_failed_at`, `last_check_error`), exempt from the written-row lock; recovery is a replacement file under a new suffixed name, the old one kept. Schema change at build. |
| S6 | Re-stamping the instance escapes the tombstone, and re-stamping isn't defined (MEDIUM) | `stamp_instance` is a named owner script that records `restored_from_instance_id`; the writer and the restore runbook check tombstones under both ids. |
| S7 | Four eyes trusts an approval made before a demotion (LOW) | At execution the script re-checks that requester and approver are distinct and both still live platform admins; both are named in `PROJECT_PURGED`. (In §7.) |
| S8 | Three small gaps in the purge steps (LOW) | Key refs are read before `baseline_archive` is deleted; "FK path to `project`" means references towards `project`, transitively (not `created_by` → `app_user`); the four purge event types are named explicitly rather than matched by `PURGE\_%` (`PROJECT_PURGED` doesn't match it). |
| S9 | The start-up check will trip tests and local setups (LOW) | `bootstrap_local_db.sh` stamps a per-database id, the test harness re-stamps after a wipe, and tests use temporary archive and key folders, so no worktree can touch another's keys. |

**Spec–schema disagreements** the auditor listed: fixed in this spec's body (24 h from approval; keys in
`project_purge_key`; `<client_code>/<project_code>`; migrations 0061–0066; the instance id in the envelope). Two remain
for the schema at build: the "prove the key is gone by failing to decrypt one stored file" step (skipped, and said so,
for a project with no file), and S5's columns.
**For Ben with Q-85:** "re-purge without the 24 h wait" needs `fn_purge_allows` to allow it; if he says yes, the
function gains that one case.
**Still open after both rounds:** Q-67…Q-85 and the D-35 questions (can a non-production purge job reach the
production vault — that decides whether S2 is reachable in Azure); not reviewable until built: the Key Vault and Blob
setup, the restore loader, the pending-purge check's code, the slice 14–15 tables, and the `detail` of audit events
written without a project id (checked at build: if one names a project item, it joins the purge under Q-69 (b)).
