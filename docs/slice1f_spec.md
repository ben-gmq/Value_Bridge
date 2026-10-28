# Slice 1f — reports, interface Excel, print to PDF, program edit (spec, 2026-10-28)

**Status:** DRAFT for Ren / Ben. Plan approved by Ren for Ben 2026-10-28 (pieces 1–6; piece 7, ERD to PNG/SVG, held
for Ben's choice of method). Working assumptions are tagged **A1…A9**. Design review round 1 (design-auditor,
2026-10-28): 13 findings, dispositions in §7; **§3.4's step rule (D1) is open for Ben and the System gap report
waits for his answer.**
**Source of truth:** `docs/VB_design.md` §4.3 (`br_coverage_report`), §4.4 (`interface_list`, `solution_matrix`,
`application_gap_report`, `fr_traceability_matrix`), §4.7 (`create_program` · `update_program`), §7.9 (the report
pseudo-code: `traceability`, `solution_matrix`, `application_gap`), §11 routes ("Phase 1 — slice 1f"), §12 criteria
10, 10a, 10b, 10d, §14.5 (untrusted text), D-7, D-8, D-27, D-28, D-42, D-52, OR-8, S6b-5, SC-5. This spec fixes the
route shapes the design leaves to "the 1f spec" and adds no rule those sections do not already state.
**Functions:** 68, 56, 66, 67, 61, 143, 134 of `docs/VB_function_status_2026-10-28.md`. Function 41 (ERD PNG/SVG) is
out of this spec until Ben chooses its method.
**No migration.** Every report reads existing tables; `audit_event.event_type` is plain text (§5.3); `program`
already holds every edited field.

## 1. Interface
- **Input:** the project's live rows (chart, BRs, links, FRs, solutions, applications, data entities). For the
  program edit, a platform admin's typed fields. No file is read.
- **Output:** four read-only reports on one Reports screen; the interface list as `.xlsx`; a print layout of each
  report (and of the interface list) that the browser saves as PDF; an edited program header.
- **Validation:** every report route is `project_ctx(VIEW)` — a project the caller cannot see is 404. Report parts
  that need a project component the project has switched off come back `null`, and the screen says the component
  is off (A1). Program edit: platform admin only; stale `row_version` → 409; a client change while any project (live or
  retired) is in the program → 409 naming them; a code or live name already used under that client → 409.
- **Archive:** every print is an `audit_event` `REPORT_PRINTED` (who, when, project, report, filters) — D-42.
  Every program edit is `PROGRAM_UPDATED` with before → after of the changed fields. Nothing else is stored; the
  reports are derived on every read.
- **Maintenance loop:** none automatic. Which reports went to a client is answered on request (an engagement
  dispute, a client audit) by IS reading `audit_event` with SQL; there is no audit screen in this slice and none is
  scheduled. Program edits are read the same way.
  The thresholds of `solution_matrix` (TECHNOLOGY >70 % / >85 %) arrive with the control rules (D-19, functions
  124–125); until then the screen shows the share and no flag (A5).

## 2. Routes (all under `/api/v1`, one guard each, `backend/routers/reports.py`)
| Route | Guard | Returns |
|---|---|---|
| `GET /projects/{project_id}/traceability` | project_ctx(VIEW) | §3.1 |
| `GET /projects/{project_id}/coverage` | project_ctx(VIEW) | §3.2 |
| `GET /projects/{project_id}/solution-matrix` | project_ctx(VIEW) | §3.3 |
| `GET /projects/{project_id}/application-gap?level=1\|2` | project_ctx(VIEW) | §3.4; level default 1 |
| `GET /projects/{project_id}/interfaces/export?source=&target=&status=` | project_ctx(VIEW) | `.xlsx`, §3.5 |
| `GET /projects/{project_id}/print-stamp?report=<code>&filters=<text>` | project_ctx(VIEW) | §3.6; records `REPORT_PRINTED` |
| `PATCH /programs/{program_id}` | platform_admin | §3.7 |

`/consistency` (in the design's route list) is not in this slice. Logic lives in `backend/services/reports.py`
(the four reports and the print stamp) and `services/program.py::update_program`; the interface export reuses
`services/interface.interface_list` and writes cells only through `services/xlsx.write_cell` (§7.12 `escape_cell`).

**The print stamp is a GET that writes one audit row (A2).** The design guards PDF export at VIEW (§11); the route
test refuses any non-GET at VIEW (sara 7b M3: a viewer reaches no write). The audit row is not a scope write, so a
GET is the honest shape. The screen calls it only when the user presses *Print / PDF* — never on load, never
prefetched — then opens the browser's print dialog. It proves the stamp was fetched, not that a PDF was saved; that
is the most a browser-printed PDF can prove (A3).
- The frontend calls it as a **plain one-shot request** (`api/scope.js`, retry off), never through `useQuery`, never
  under a query key that is invalidated (round 1 P1).
- *Print / PDF* first **refetches the report**; the report response carries its own `generated_at`, which is the time
  printed and is sent to the stamp, which records it in the audit detail (P3). Only when both succeed does the print
  dialog open; a failure shows the error toast and no dialog.
- **Ctrl+P without the button** (P2): in `@media print` the report body is shown only while a stamp fetched for this
  print is held; otherwise the page prints one line, "Use Print / PDF to print this report." The stamp is dropped on
  the browser's `afterprint` event and whenever the report data or filters change (round 2 N1).
- The `generated_at` sent to the stamp must be an ISO time with its zone, no later than now and no earlier than 30
  minutes ago, else 422 (N2).
- `filters` is checked at the boundary: control characters (NUL included) → 422, over 200 characters → 422 (S2).
- A project with an open removal request may still be printed and the row is written (reads are not refused on
  such a project; A9).

## 3. The reports (grain = one row per WHAT)
### 3.1 Traceability (function 68; §7.9 `traceability`; criteria 10, 10a)
- **Grain:** one row per live (to-be process step × live BR on it × live BR↔FR link × live FR). An FR linked to
  three BRs gives three rows (10a); an FR reached only through a solution gives none (D-52).
- **Groups:** by the FR's type (project label), ordered by behaviour FORM, BATCH, INTERFACE, REPORT, OTHER, then
  type label; within a group by `hier_code`, `br_number`, `fr_number`.
- **Columns:** step (`hier_code`, name), BR number + statement, FR number + name, FR status, solution tag (number,
  name, category, or blank), `tag_answers_br` (false → flagged on the row: the tag is not a live solution of that
  BR), applications = the tag's live `APPLICATION_SOLUTION` (code, name).
- **Untraced group, last:** live FRs with no live BR link, with their tag.
- **Answered without software:** live non-REJECTED solutions that answer a live BR and carry no live FR, with their
  BRs — criterion 10 (a PEOPLE solution with two BRs and no FRs reads as a complete answer).
- **REJECTED tag (D4):** `tag_answers_br` means *a live, non-REJECTED solution of that BR*; a row whose tag is REJECTED
  carries its own `rejected_solution` flag. Such FRs stay on the list, flagged.
- The "answered without software" list holds only categories outside `function_requirement.TECH_CATEGORIES`; a
  TECHNOLOGY solution with no live FR is a coverage line instead (D5).
- Needs FUNCTION_REQUIREMENT; with SOLUTION off the solution and application columns and the "answered without
  software" list are `null`; with APPLICATION off the application column is `null`.
- Every report response carries `generated_at` (server time, UTC; the screen and print show it in ICT).

### 3.2 Coverage (function 56; §4.3 `br_coverage_report`)
One list per line, each `{code, severity, rows}`; severity is `warning` or `information`. A line whose component is
off is `null`.
| Code | Rows | Severity | Needs |
|---|---|---|---|
| `br_without_output_de` | live BRs with no live C/U/D data-entity row | information (A4) | — |
| `br_without_solution` | live BRs with no live link to a non-REJECTED solution (S5-2) | information (A4) | SOLUTION |
| `br_without_fr` | live BRs with no live BR↔FR link — legal | information | FUNCTION_REQUIREMENT |
| `fr_without_br` | live FRs with no live BR link | **warning** (D-28/D-52) | FUNCTION_REQUIREMENT |
| `fr_without_solution` | live FRs with no tag | information | FR + SOLUTION |
| `fr_solution_outside_its_brs` | reused from `function_requirement` | **warning** | FR + SOLUTION |
| `solution_reach_without_link` | (FR, BR) where the FR's tag answers the BR and the FR is not linked to it — a hint | information | FR + SOLUTION |
| `flow_uncovered` | live BR system flows no interface FR covers (`br_flows.coverage`) | warning with FR on, else information | APPLICATION |
| `fr_rejected_tag` | live FRs tagged to a REJECTED solution (round 2 N3; `fr_solution_outside_its_brs` is the freeze's line and stays as it is) | warning | FR + SOLUTION |
| `tech_solution_without_fr` | live TECHNOLOGY-category solutions answering a live BR with no live FR (D5; §7.9 `tech_solution_no_fr`) | warning | FR + SOLUTION |
| `de_unreferenced` | live data entities no live BR references — the scope-gap list | information (A4) | — |

### 3.3 Solution matrix (function 66; §7.9 `solution_matrix`; criterion 10b)
- **Layout:** to-be L1 areas are the rows and the five categories the **columns**, so criterion 10b reads literally
  (an empty Organization & Rules column).
- **Grain:** one cell per (to-be L1 area × solution category). Cell = distinct live non-REJECTED solutions that
  answer a live BR on a process under that area, and the count of those BRs. A solution answering BRs in two areas
  counts in both cells; the row total counts it once.
- All five categories always appear, in `SOLUTION_CATEGORY` sort order, so an empty ORG_AND_RULES column is visible
  (10b). An extra row counts solutions linked to no live BR. REJECTED solutions are counted apart (A6).
- **Headline:** TECHNOLOGY as a share of live non-REJECTED solutions. No flag until control rules exist (A5).
- Needs SOLUTION.

### 3.4 System gap (function 67; §7.9 `application_gap`; criterion 10d; S6b-5, SC-5) — **waits for Ben (D1)**
**Open (round 1 D1, HIGH):** at area level one allocation anywhere in a matched area hides every supported as-is step
in it, so the migration backlog reads "none". Which reading Ben chooses decides the grain below; nothing in §3.4 is
built until he does. The text below is the draft that the review found wanting.
- As-is support = live `APPLICATION_BFC_NODE` on a live as-is process, application lifecycle AS_IS or BOTH. To-be
  allocation = live to-be process ⋈ live BR ⋈ live `BR_SOLUTION` ⋈ live `APPLICATION_SOLUTION` ⋈ live application.
- Areas paired as `process_volume.summary` does: same level, chart code and normalised name; everything else is
  listed under `unmatched` with the same reasons (ONLY_AS_IS, ONLY_TO_BE, CODE_SAME_NAME_DIFFERS, NAME_ELSEWHERE).
  The pairing is lifted into one shared function both reports call (playbook §10) — no second copy.
- **`unallocated`:** as-is steps with support, in a matched area whose to-be side has no allocation — one row per
  (step × supporting application). **`unsupported`:** to-be steps with an allocation, in a matched area whose
  as-is side has no support. **`retiring`:** applications supporting an as-is step that are allocated to no live
  solution anywhere (A7). **`as_is_support_by_to_be`:** support links naming a TO_BE application — information,
  never counted as support.
- Needs APPLICATION, AS_IS and SOLUTION (to-be allocation joins `BR_SOLUTION` and `APPLICATION_SOLUTION`, D2); with
  any off the report is `null`.
- Returns its input counts — as-is processes, support links, to-be allocations; a zero count shows "no as-is support
  recorded" (or the like), never an empty list that reads "no gap" (D3).

### 3.5 Interface list to Excel (function 61; D-27)
The rows of `interface_list` with the same filters as the screen, one sheet: rows 1–3 the print stamp (project,
"LIVE — not a baseline", generated at, by), then the filters applied and, when filtered, "N interfaces not yet described are not in this filtered list"
(`unfilterable_incomplete`, D6), then a header row and one row per interface — FR number, name, type,
source → target, pattern, method, frequency, carried entities with notes, solution, BRs, status, effort, complete /
missing; the effort column is blank with EFFORT off (A1). The time is written as text with its zone
("2026-10-28 14:05 ICT"; openpyxl refuses zone-aware datetimes, D8). Every value through `xlsx.write_cell` (text typed as text; `= + - @` tab CR leads marked as text). No
hidden code row, no protection: this is a report, not an import template. Not audited (D-42 covers PDFs; A8).

### 3.6 Print to PDF (function 143; D-42, OR-8)
- **Printable reports in 1f:** `traceability`, `coverage`, `solution_matrix`, `interfaces` (`application_gap` joins
  when it is built, round 2 N4) —
  the registry `reports.PRINTABLE`; any other `report` → 422. The other D-42 reports (BFC, BR register, DFD, ERD,
  registers, effort, baseline diff, issue log, WBS) get the same button later; function 143 stays *partly built*.
- **Stamp:** `{report, project_code, project_name, is_live: true, generated_at, generated_by}` (`generated_at` = the
  report response's, P3); the interface list's print states its filters and the not-described count as the Excel does; the screen prints
  "LIVE — not a baseline" on every page (`position: fixed` header in `@media print`). Reports read live data only
  in 1f; printing from a frozen baseline is later.
- **Layout:** one print stylesheet hides the left rail, header and buttons; tables keep their header row on every
  page and avoid breaking a row. No new library (spec list row 143). Text renders through React, as on screen.
- `filters` is the screen's own filter text (at most 200 characters, stored in the audit detail as sent).

### 3.7 Program edit (function 134; §4.7)
Body `{row_version, program_code?, program_name?, client_id?, description?}`; code upper-cased and trimmed as at
create. Refused: stale row_version 409; a retired program 409; an inactive client 422; client change while **any project, live or
retired,** is in the program 409 naming their codes (a retired project's composite FK `fk_project_program_client`
still binds the client; round 1 D7) — the program row is locked FOR UPDATE before the check; code or live name taken under the client 409. Audited
`PROGRAM_UPDATED` `{field: [before, after]}` for changed fields only; an edit changing nothing writes nothing. The
Program home shows *Edit* to platform admins only (presentation; the guard refuses everyone else).

## 4. Screens
One **Reports** page `/p/:projectId/reports` with a `Segmented` choice of the four reports (`?tab=`), in the left
rail under the project; `<Page crumb>`; strings in a new `en.reports.json`. The Interfaces page gains *Download
Excel* and *Print / PDF*. No mockup exists for these reports; they compose the kit's Card, Tag, Code and Status (D-51).

## 5. Risk and tests — Grade 2
Wrong figures reach a client deck or the vendor scope list; noticed when someone checks a row; corrected by fixing
the data. **Proposed depth:** each report's rules tested directly on built fixtures — traceability grouping, 10a
(three rows), the untraced group, the flagged tag, criterion 10; each coverage line, one positive and one negative;
10b; 10d plus one unmatched area and the TO_BE-support line; interface export reads back with an `=` cell kept as
text; the print stamp writes one audit row, refuses an unknown report and is 404 for a non-member of a restricted
project; program edit: 409 stale, 409 client change with projects, audit before/after, non-admin refused by the
existing guard test. The new report routes and `print-stamp?report=traceability` join the positive-control list of
`test_no_get_route_leaks_a_restricted_project`, so the sweep proves they return marked data to a member and 404 to a
non-member (S3); the filters check (NUL, 201 characters); the REJECTED-tag flag; the TECHNOLOGY-without-FR line. **Left uncovered on purpose:** print layout pagination (seen in the browser pass only); very large
projects (no performance test); Excel opening in Excel itself (read back with openpyxl only).

## 6. Working assumptions
- **A1** A report part whose component is off returns `null`, never an empty list (an empty list would read "no gaps").
- **A2** The print stamp is a GET that records an audit row (§2).
- **A3** Audited = the stamp was fetched for printing; whether a PDF was saved cannot be known.
- **A4** Severities §4.3 does not state (BR without output DE, BR without solution, unreferenced DE) are information.
- **A5** No FLAG / ESCALATE colour on the matrix until the control rules (D-19) are built.
- **A6** REJECTED solutions are counted apart in the matrix, as coverage does not count them (S5-2).
- **A7** "Retiring" reads as *support applications with no to-be allocation anywhere*: an AS_IS application can never
  be allocated (§4.4), so the design's literal wording would list every AS_IS application.
- **A8** Excel exports are not audited; only PDFs are (D-42).
- **A9** A project with an open removal request can still be printed, and the print is audited.

## 7. Design review round 1 (design-auditor, 2026-10-28) — dispositions
| Id | Sev | Finding | Disposition |
|---|---|---|---|
| D1 | HIGH | Area-level gap rule hides supported steps | **Open — Ben.** §3.4 not built until decided |
| P1 | MED | GET stamp refired by query machinery | Fixed: one-shot call, retry off (§2). Kept a GET: a POST at VIEW would need an exception in the viewer-write rule |
| P2 | MED | Ctrl+P prints without stamp/audit | Fixed: body prints only under a held stamp (§2) |
| P3 | MED | Stamp time ≠ data time | Fixed: refetch, report `generated_at` printed and audited (§2) |
| P4 | MED | Maintenance loop names nobody | Fixed: IS by SQL, on request (§1) |
| D2 | MED | Gap ignores SOLUTION component | Fixed (§3.4) |
| D3 | MED | Empty inputs read as no gap | Fixed: input counts (§3.4) |
| D4 | MED | REJECTED tag unflagged | Fixed: flag, kept on list (§3.1) |
| D5 | MED | TECHNOLOGY with no FR counted as answer | Fixed: excluded; coverage line (§3.1, §3.2) |
| D6 | MED | Filtered Excel silently short | Fixed: filters + not-described count printed (§3.5) |
| S1 | MED | No egress statement | Fixed: §8 |
| D7 | LOW | Client change blocked by retired projects, vague 409 | Fixed: any project blocks, named; lock (§3.7) |
| D8 | LOW | Zone-aware datetime fails in openpyxl | Fixed: time as text with zone (§3.5) |
| S2 | LOW | `filters` unchecked | Fixed: 422 on control characters / >200 (§2) |
| S3 | LOW | Leak sweep proves nothing for new routes | Fixed: positive controls (§5) |

Questions Q3a (effort in vendor Excel: kept, as `interface_list` lists effort), Q4 (A8), Q5 (A9), Q6 (D7), Q7
(denominator = live non-REJECTED solutions) are **defaults put to Ben, not settled** — Q6 under D7 means a program
that ever held a project never changes client. Q8 (columns) is settled by layout; Q1/Q2 are D1.

**Round 2 (final, 2026-10-28):** every round-1 fix closes its finding; four new points fixed — N1 stamp released on
`afterprint`, N2 `generated_at` bounded, N3 `fr_rejected_tag` line, N4 `application_gap` not printable until built.

## 8. Egress and confidentiality
No outside service is called: PDF by the browser's own print, `.xlsx` by download, no fonts or scripts from a CDN.
The content is client-confidential; it leaves only when a consultant hands the file over.
