# Slice 6b-1: Applications — the catalogue, to-be allocation, as-is support

**Date:** 2026-10-11 · **Author:** Lilly · **Status:** rev 2 — design review round 1 applied (5 findings, 0 HIGH); Ben's rulings S6b-1…S6b-6 (2026-10-11)
**Builds on:** D-8, D-23, R2-D11 (§1a); §4.4 `create_application`, `link_application_solution`;
§5.3 APPLICATION / APPLICATION_SOLUTION / APPLICATION_BFC_NODE; §6.2; §7.5 `application.link_solution`;
§9; criterion 10c. Schema: `docs/slice6b_schema.md` §1–§3 and §7 (apple). Interface detail
(§4–§6 of that file) is **Slice 6b-2**. Where this file and the design disagree, the design wins.
Builds on 6a (`function_requirement`, merged before 6b-1's migrations are written).

## 1. Purpose
A consultant keeps the project's **application landscape** — each system flagged as today's
(AS_IS), the future's (TO_BE) or both — and records two facts about it: **which Solutions an
application will deliver** (the to-be side), and **which process steps it supports today** (the
as-is side). The gap between the two is the migration backlog (`application_gap_report`, later).

## 2. Scope
**In:** `application`, `application_solution`, `application_bfc_node`; Applications register and
page (new tab or menu — see §7); "Delivered by" panel on the Solution page; "Supported today by"
panel on the process-step panel of the function chart; retire rules.
**Out:** interface detail and the interface list (6b-2); the gap report; showing applications on the
process-flow canvas (the as-is flow view reads this table later); application import.

## 3. Keystone grain
- `application` — one row per application or technology in one project's landscape. Key
  `application_code` typed by the consultant, stored upper-case, letters/digits/`-_.` only, **full
  unique** (never reused), **editable until a baseline freezes it** (S6b-6; the old code to the audit);
  live names unique (S6b-2). Lifecycle AS_IS / TO_BE / BOTH (system codes).
- `application_solution` — one row per (application × solution) to-be allocation, with a note.
- `application_bfc_node` — one row per (application × **process step**) as-is support statement,
  with a note. Process-only, guarded by the D-23 guard FK.

**Retire:**
- Retiring an application with live allocations or as-is links → 409 naming them (generic).
- Retiring a Solution with live allocations → 409 (generic; adds to the FR blocker from 6a).
- **As-is links retire and restore with their step** (S6b-1, mirrors S5-1): `ApplicationBfcNode`
  joins `step_retire.OWNED_BY_STEP`, tier 2, shown in the retire preview. A since-retired
  application is asked for first on restore (A-SR-5).
- Demoting a step from process with live as-is links → 409 naming them (`bfc._step_blockers`).

## 4. Business Requirement grid

| Function | Entity | Use | Logic → output |
|---|---|---|---|
| `create_application` | `application` | C | EDITOR. Code trimmed + upper-cased, required, unique in project (409 naming the holder); name required, unique among live (409); lifecycle required from `APP_LIFECYCLE`; kind optional from `APP_KIND` |
| `update_application` | `application` | U | EDITOR. Allow-list (code, name, vendor, version_label, kind, lifecycle, description). `kind_code`: absent = unchanged, **explicit null = clear** (DR6b-P3). Code change (S6b-6) and lifecycle change write `RECORD_UPDATED` with the previous value (DR6b-D1). Moving lifecycle **to AS_IS** locks the application FOR UPDATE and returns **409 naming the live allocations** (R2-D11). Moving lifecycle **to TO_BE** while live as-is links exist **warns and names the steps** (DR6b-P1, S6b-5). AS_IS is identified by the resolved code string, never a global code_id |
| `link_application_solution` | `application_solution` | C | EDITOR, from either page. Both ends **fetched scoped to the project first** (404 otherwise), then locked FOR SHARE application → solution, then live-checked (409). The AS_IS check reads lifecycle **after** the lock and **before** any relink: **AS_IS application → 422** and a removed pair stays removed (criterion 10c; BOTH accepted). Relink restores the same row |
| `link_application_step` | `application_bfc_node` | C | EDITOR, from the step panel. Application scoped-fetched first; then **the step FOR SHARE, then the application FOR SHARE** (SR-5 order, no cycle with step restore — DR6b-P2); both live; the step must be a process step. **TO_BE application → warning, allowed** (S6b-4) |
| `restore_application` | `application` | U | EDITOR. Lock, live-name check naming the holder (409), then restore (DR6b-D2, as `restore_solution`) |
| edit note / unlink | both links | U / D | EDITOR. Note edited in place, previous note to the audit (S5-3 pattern); unlink soft, `row_version` checked |
| lists | all three | R | REVIEWER. Register (with live allocation and step counts); a Solution's applications; a step's applications; an application's solutions and steps |
| `consistency_check` | links | R | Gains `appsol_under_inactive`, `appnode_under_inactive` (must be empty) and `as_is_allocated` (live allocation of an AS_IS application — must be empty); **informational** `as_is_support_by_to_be` (live as-is links whose application is TO_BE — S6b-5, DR6b-P1) |

## 5–6. Logical / physical
`docs/slice6b_schema.md` §1–§3, §7 (the parts that concern these three tables). Migrations 0025
`application`, 0026 `application_solution`, 0027 `application_bfc_node` (+ step-retire owned set in
the same commit).

## 7. Function — where it lives
- `services/application.py` (new); routes in `routers/scope.py`; `schemas/application.py`.
- `step_retire`: owned set, tier, `describe()`; `bfc._step_blockers`; `lifecycle` LABELS (two-ended
  for both links, as DR1-P1) and RESTORABLE.
- Frontend: `features/applications/{ApplicationsPage,ApplicationPage}.jsx`; a generic two-ended link
  panel reused for "Delivered by" (Solution page) and "Supported today by" (step panel);
  **menu: Settings → Applications** (the landscape is project reference data like the organisation
  and external parties, and the top bar already clips — VB-006). `i18n/en.applications.json`.

## 8. Risk grade and test depth
**Grade 2** — a wrong allocation or as-is link misstates the landscape and the migration backlog in a
client deliverable; correctable once noticed. Riskiest concern: **a link across projects or onto a
retired end, and the AS_IS rule slipping between its two write paths** — proven directly.
- pytest: code upper-cased and unique (409); name unique live; lifecycle required; kind optional;
  code editable, previous value audited (S6b-6); AS_IS allocation 422, BOTH accepted (10c); lifecycle → AS_IS with allocations
  409 naming them; cross-project application/solution/step 404 with nothing leaked (live and
  retired); retired ends 409; TO_BE as-is warning; step retire carries as-is links and restore
  brings them back; restore refused while the application is retired; demotion 409 names them;
  retire application/solution with links 409 naming both ends; reviewer 403, outsider 404; the three
  consistency lines find planted orphans.
- ui-verifier: create two applications (AS_IS, TO_BE) → allocate TO_BE to a Solution, AS_IS refused →
  link AS_IS to a step → retire the step and restore it → reviewer sees no controls.
- **Deliberately uncovered:** a lifecycle change racing an allocation for real (the lock order is
  reasoned, and the `as_is_allocated` line is the proof); phone width.

## 9. Acceptance
1. An application flagged AS_IS cannot be allocated to a Solution; one flagged BOTH can (10c).
2. An application with live allocations cannot be moved to AS_IS; the refusal names them.
3. A step shows the applications that support it today; they retire and come back with the step.
4. Nothing links across projects; a reviewer changes nothing.

## 10. Rulings (Ben, 2026-10-11)
- **S6b-1** As-is support on a step is built now and retires/restores with the step.
- **S6b-2** Application codes are unique and upper-case; live names are unique.
- **S6b-3** (6b-2) Retiring an FR with live interface detail is refused until the detail is removed.
- **S6b-4** A TO_BE application linked as today's support warns and is allowed.
- Adopted on recommendation (apple Q-4, Q-5, Q-8): kind is optional; removing interface detail removes
  its carried entities in the same transaction (6b-2); both link notes are edited in place.

## 11. Design review round 1 of 2 (design-auditor, 2026-10-11)

| Id | Rating | Finding | Disposition |
|---|---|---|---|
| DR6b-P1 | MEDIUM | A lifecycle edit or step restore can leave TO_BE apps as "today's support" silently | **Fixed** — warning on the lifecycle PATCH naming the steps; informational `as_is_support_by_to_be` line; Ben ruled the gap report does not count them (S6b-5) |
| DR6b-D1 | MEDIUM | Lifecycle change leaves no record of the old value | **Fixed** — `RECORD_UPDATED` with previous lifecycle (and previous code) |
| DR6b-P2 | LOW | Application-first lock order cycles with step restore | **Fixed** — step FOR SHARE, then application |
| DR6b-P3 | LOW | Optional kind could not be cleared | **Fixed** — explicit null clears; one test |
| DR6b-D2 | LOW | Restore had no named name-clash check | **Fixed** — `restore_application` row |
| — | (question) | `data_migration_map` (§7.9) uses AS_IS only where `application_gap` uses AS_IS+BOTH | **Tracked** for the reports slice (design inconsistency, not 6b-1) |

**Further rulings (Ben, 2026-10-11):**
- **S6b-5** As-is links to a TO_BE application do **not** count as today's support in the gap report, but are never silent: a warning when created or when the lifecycle moves, and an informational consistency line.
- **S6b-6** Application codes are editable until a baseline freezes them (the baseline slice adds that lock); allowed characters A–Z 0–9 `-` `_` `.`; the old code goes to the audit.
- **S6b-7 (Lilly, pending Ben — sara L2):** a code freed by a rename may be taken by another application. Before
  baselines nothing quotes it; once a baseline freezes a code it can no longer be renamed (S6b-6), so a frozen code is never freed.
