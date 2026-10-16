# Slice 14 — Issue module (spec, DRAFT for Ben, night batch 2026-10-16)

**Status:** DRAFT — not approved, not built. Needs Ben's answers to the schema's questions (Q-39…Q-48 below) and his
OK on this spec. **Source of truth:** `docs/VB_design.md` §4.5 (Issue Management: `create_stakeholder`, `raise_issue`,
`link_issue_br`, `resolve_issue`, `issue_dashboard`), §5.3 (STAKEHOLDER, ISSUE, ISSUE_BR), §4.9 (`stakeholder_engagement`,
for later), the plan row in `docs/VB_remaining_work.md` ("Issue module": stakeholders; raise / link / resolve `ISS-`;
dashboard; issues in the freeze; the M3 tile). **Schema:** `docs/slice14_issue_schema.md` (apple, 2026-10-16) — grain,
DDL, shadows, retire rules, migrations 0061–0063. This spec adds the screens, routes, acceptance and grade; it does not
restate the schema.

## 1. Purpose
Record the issues the client's people raise during scoping — who raised them, how serious, which requirements they
touch, and how they were resolved — so a consultant can see what is open per area and a signed baseline shows which
issues were open when it was signed.

## 1a. Interface
- **Input:** a consultant (EDIT on the project, component ISSUE on) types stakeholders and issues, links issues to BRs
  and resolves them. No import in this slice (1e adds the Excel round-trip).
- **Output:** the Issues list and detail, a stakeholders list, the issue dashboard (open by severity × type, by area, by
  raiser), the M3 tile on the project dashboard, and issues inside every baseline frozen after this lands.
- **Validation:** codes from `code_master` (severity, type, status); RESOLVED needs a resolution (§4.5); a raiser must
  be a live stakeholder of the same project (composite FK); an issue links only to BRs of its own project.
- **Archive:** every write is audited; nothing is deleted (law 1); a baseline keeps its issues and their status as
  frozen (law 2).
- **Maintenance loop:** none automatic; the dashboard and the M3 tile are the review surface.

## 2. Doctrine
Playbook §5, §9 (2, 3, 7, 8, 10, 11); VB laws 1–3, 5, 6, 10; D-4 (stakeholders have no login), D-37 (component ISSUE),
law 2's hash-spec rule (spec 4 → 5, taken on `main` in order, one merge with both frozen tables).

## 3. Grain
See schema §1: one stakeholder per named client person per project; one issue per raised issue (project-level, not
per BR); one `issue_br` per (issue, BR) pair, surrogate id (Q-46).

## 4. Business requirement grid
| Function | Entity | Use | Logic → output |
|---|---|---|---|
| `create_stakeholder` / edit / retire | STAKEHOLDER | C/U/soft | name, title, org unit (optional, Q-40), `is_bpo`; retire refused while a live issue names them (Q-45) |
| `raise_issue` | ISSUE | C | `ISS-0001` minted at save; raiser = stakeholder; recorder = the JWT user; raised date defaults to today (Q-44) |
| `edit_issue` | ISSUE | U | title, description, severity, type, target date; row_version |
| `link_issue_br` / unlink | ISSUE_BR | C / soft | same project; re-linking restores the same row (S1-7) |
| `resolve_issue` / reopen | ISSUE | U | RESOLVED (and CLOSED, Q-39) need a resolution; reopen clears the resolution fields (audit keeps the text) |
| `retire_issue` | ISSUE | soft | only for issues raised in error; refused while linked (Q-42) |
| `issue_dashboard` | ISSUE, ISSUE_BR, STAKEHOLDER, BFC_NODE | R | open (OPEN + IN_PROGRESS, by behaviour — Q-39) by severity × type, by L1 area via BR → step → area, by raiser |
| freeze | BASELINE_ISSUE, BASELINE_ISSUE_BR | C | issues and links frozen with code + label pairs; status and resolution hashed (Q-43) |
| M3 tile | ISSUE | R | open issues, of which high severity; links to the dashboard |

## 5–6. Logical and physical design
`docs/slice14_issue_schema.md` §2–§5 (apple). Three migrations, one table plus shadow each, downgrade guards; ISSUE
joins `components.BUILT` with a live-row probe.

## 7. Function notes
- **Guards:** reads `project_ctx(VIEW)`; writes `project_ctx(EDIT, component="ISSUE")` / `object_guard(…, EDIT,
  component="ISSUE")`, named in `ROUTE_COMPONENTS` (criterion 49b). Stakeholder writes gated by ISSUE too (Q-47).
- **Status by behaviour, not code (law 5):** if Q-39 is taken, ISSUE_STATUS becomes a system list (labels editable,
  codes fixed), and `code_lists.PINNED` covers it automatically.
- **Step retire:** `IssueBr` joins `step_retire.OWNED_BY_BR`; the issue stays live and becomes project-level; the retire
  preview names the issues that lose their link (Q-41).
- **Org chart:** an org unit with a live stakeholder cannot be retired (new blocker, schema §4).

## 8. API surface (`/api/v1`)
| Method · path | Guard |
|---|---|
| `GET/POST /projects/{id}/stakeholders` · `PATCH/DELETE /stakeholders/{id}` · `PATCH …/restore` | VIEW · EDIT+ISSUE |
| `GET/POST /projects/{id}/issues` · `GET/PATCH /issues/{id}` · `DELETE /issues/{id}` | VIEW · EDIT+ISSUE |
| `POST /issues/{id}/resolve` · `POST /issues/{id}/reopen` | EDIT+ISSUE |
| `POST /issues/{id}/brs` · `DELETE /issues/{id}/brs/{link_id}` | EDIT+ISSUE |
| `GET /projects/{id}/issue-dashboard` | VIEW |

## 9. Screens
Rail item **Issues** under Control (component ISSUE on): list with filters (status, severity, type, area, raiser) and
an add dialog; issue detail (fields, linked BRs with a BR picker, resolve / reopen); **Stakeholders** under Settings;
the dashboard tab on the Issues page; the M3 tile on the project dashboard. Kit components only; strings in
`en.issues.json`; mockup reference: none exists for issues — **a mockup element with no data behind it is left out**,
and Ben sees the screens in the browser check before merge.

## 10. Acceptance criteria
1. Raising an issue mints `ISS-0001`, then `ISS-0002`, at save only; the raiser and the recorder are stored apart.
2. A raiser from another project, or a retired stakeholder, is refused (422).
3. RESOLVED without a resolution → 422; with one, `resolved_at` / `resolved_by` are set from the server.
4. An issue links to several BRs; a BR of another project → 422; unlink then re-link restores the same row.
5. Retiring a step retires its BR's issue links; the issue stays live; the preview names it.
6. A stakeholder named by a live issue cannot be retired (409); an org unit with a live stakeholder cannot be retired.
7. The dashboard's open counts agree with the list filtered to open, per severity × type, per area, per raiser.
8. A freeze after this slice holds every live issue and link; resolving an issue afterwards shows CHANGED in the diff;
   a baseline frozen at spec 4 still verifies unchanged (Grade 1).
9. With component ISSUE off, every issue write is 409 COMPONENT_OFF and the rail item is hidden.
10. A non-member gets 404 on every issue route of a restricted project (the leak sweep covers the new GET routes).

## 11. Grade
**Grade 1 for the hash-spec bump** (spec 4 → 5): a mistake breaks the verification of every signed baseline — proven by
freezing at spec 4, migrating, and verifying both an old and a new baseline, plus the downgrade refusals. **Grade 2**
for the issue data and dashboard (figures someone decides from; edge cases left uncovered named at build). **Grade 3**
for layout. Test plumbing: the existing fast harness.

## 12. Questions for Ben (from `docs/slice14_issue_schema.md` §6, numbered in history order)
Q-39 issue statuses system-owned (rec. yes) · Q-40 stakeholder org unit optional (rec. yes) · Q-41 retiring a step with an
open issue allowed (rec. yes) · Q-42 soft retire for issues raised in error only (rec. yes) · Q-43 status and resolution
in the baseline hash (rec. yes) · Q-44 raised date = the day raised, defaults today (rec. yes) · Q-45 a stakeholder
with issues can't be retired (rec. yes) · Q-46 `issue_br` surrogate id (rec. yes, rewrite §5.3) · Q-47 stakeholder
writes gated by ISSUE (rec. yes) · Q-48 risk promotion's raiser (rec. the consultant picks a stakeholder on promotion).

## 13. Size
About 3 working days (the plan's figure), 1,500–2,000 lines with tests; the hash bump is the riskiest piece.

## 14. Revision after design review round 1 (design-auditor, 2026-10-16: 1 high, 7 medium, 4 low)
These rules supersede anything above that disagrees. The hash bump 4 → 5 was checked and found sound.
- **R1 (HIGH).** Unlink fetches the link `WHERE issue_br_id = :link AND issue_id = :id` (404 otherwise); every
  sub-resource route scopes its row to the path parent. A cross-project unlink test joins criterion 10.
- **R2 (M).** Which route sets which status: PATCH may set the open statuses (OPEN, IN_PROGRESS, DEFERRED — Q-49);
  only `resolve` sets RESOLVED / CLOSED (with a resolution); only `reopen` returns to OPEN. The database refuses
  RESOLVED / CLOSED without `resolved_at`.
- **R3 (M).** Reopen clears `resolved_at` / `resolved_by_user_id` only and keeps `resolution` (the next resolve
  overwrites it; a baseline in between holds the old text). Resolve and reopen take `row_version`; stale → 409. The
  audit holds no free text (baseline.py's rule), so "the audit keeps the text" is withdrawn.
- **R4 (M).** The area rule (Q-50): an issue counts once in every L1 area it touches through a live link to a live BR of
  a live step; issues with no such link count in a "No area" row; area rows are not meant to sum to the total. The
  list's area filter uses the same rule.
- **R5 (M).** Maintenance loop: the consultant who owns the engagement reviews open issues weekly; the dashboard adds an
  **overdue** count (target date passed, still open).
- **R6 (M).** Q-39 restated as a real choice (below). Whatever Ben picks, the deploy step refuses while any project-tier
  ISSUE_STATUS row or live hide of one exists (it lists them), so no project-only status escapes the open count.
- **R7 (M).** Audit labels for stakeholder and issue are the id / number only, never a name or title — audit_event is
  append-only and a purge could not clean them.
- **R8 (M).** Stakeholder `email` is dropped from this slice (no feature uses it). Description and resolution carry the
  hint "describe the problem, not the person". History records that `baseline_issue` falls in `purge_project`'s scope.
- **R9 (L).** `raised_by_stakeholder_id` is editable (live, same project), so duplicates can be merged, then retired.
- **R10 (L).** `COMPONENT_ROWS["ISSUE"]` also probes live stakeholders, so ISSUE cannot be switched off under them.
- **R11 (L).** Lock order: link_issue_br locks step → BR → issue FOR SHARE (SR-5); raise / edit lock the raiser FOR
  SHARE; stakeholder create / edit lock the org unit FOR SHARE.
- **R12 (L).** `raised_date` defaults to `baseline.local_today()` (ICT).

Added acceptance criteria: 11. An EDIT user of project A unlinking a link of project B through A's issue → 404, nothing
written. 12. PATCH to RESOLVED → 422; the database refuses a RESOLVED row without `resolved_at`. 13. Two resolves with
the same row_version → the second is 409. 14. A multi-area issue counts in each area; an unlinked one under "No area".
15. No audit_event detail contains a stakeholder name or an issue title.

Questions added for Ben: **Q-49** is DEFERRED open or closed, and does it need a resolution (rec. open, none) ·
**Q-50** the area rule (rec. as R4) · **Q-51** the tile's "high severity" (rec. CRITICAL + HIGH, both pinned) ·
**Q-52** resolving 30 issues shows "30 CHANGED" in the diff headline (rec. yes, with issues counted apart from scope in
the headline) · **Q-53** a baseline shows the raiser's current name, so renaming a stakeholder changes how old
baselines display (rec. accept — names are not frozen, by design) · **Q-54** two client people with the same name (rec.
allow; unique on name + org unit). **Q-39 restated:** (a) system list — nobody can relabel or add statuses; (b) pinned
and company-only — a platform admin may relabel, projects cannot add or hide statuses (as PROJECT_STATUS, G-2).
Rec. (b).

## 15. Design review round 2 (final under the cap, 2026-10-16): R1–R12 hold; two medium points settled here
- **N1.** PATCH refuses any status change while the issue is closed (409, "use reopen"). The database rule is two-way:
  `resolved_at` is set **if and only if** the status is a closed one. How the database knows "closed": ISSUE_STATUS
  gets a required **open / closed behaviour** (a `behaviour_code` like FR and RACI types, D-27), carried on the issue
  row through the composite FK, and a CHECK on that column — no code literal (law 5).
- **N2.** Every ISSUE_STATUS row, company or project, carries that behaviour, required on add; the dashboard, the tile,
  the overdue count and the route split all read the behaviour, never the codes. A status added later is therefore
  open or closed by its own declaration. §4's "open = OPEN + IN_PROGRESS" becomes "open = every status of open
  behaviour" (DEFERRED follows Q-49). The schema's `email` column and `ck_stk_email` are struck (R8).
- This makes ISSUE_STATUS a behaviour category: `code_lists.BEHAVIOUR_CATEGORIES` and the code_master CHECKs gain it,
  in the slice's first migration. Overdue uses `local_today()` (ICT); whether a DEFERRED issue past its target date is
  overdue follows Q-49.
