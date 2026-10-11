# Slice 6b-2: Interface detail and the interface list

**Date:** 2026-10-11 · **Author:** Lilly · **Status:** rev 2 — design review round 1 applied (8 findings, 1 HIGH, all fixed); Ben's rulings S6b2-1…S6b2-4 (2026-10-11)
**Builds on:** D-27, A-55 (§1a); §4.4 `describe_interface`, `interface_list`; §5.3 FR_INTERFACE,
FR_INTERFACE_DATA_ENTITY, `v_interface_list`; §5.4.8; §7.5 `describe_interface`, `change_fr_type`;
§9 `PUT/DELETE /function-requirements/{id}/interface`, `GET /projects/{id}/interfaces`;
criteria 101, 102, 103. Schema: `docs/slice6b_schema.md` §4–§7 (apple). Builds on 6a (FRs) and 6b-1
(applications), both merged before 6b-2's migrations are written. Where this file and the design
disagree, the design wins.

## 1. Purpose
An FR whose type behaves as an **interface** carries what only an interface has: the source and
target applications, the pattern (push/pull/bidirectional), the method (API/file/DB/message/manual),
the frequency, a volume note, and the data entities it carries. From those FRs VB **generates** the
interface list — one row per interface FR, never typed, identity = FR number — which a vendor builds
against. An interface FR whose endpoints are not known yet is listed as **incomplete**, not hidden.

## 2. Scope
**In:** `fr_interface`, `fr_interface_data_entity`, the view `v_interface_list`; an "Interface detail"
card on the FR page (shown only when the FR's type behaves as INTERFACE): set / change / remove;
the **Interfaces** top-bar section (today a placeholder) showing the generated list, filterable by
application pair, with incomplete rows marked; the type-change guard; FR retire guard (S6b-3).
**Out:** `.xlsx` export of the list (a later export slice); `interface_load` report; showing
interfaces on the DFD/ERD canvases; FR import.

## 3. Keystone grain
- `fr_interface` — **one row per interface-type FR** (1:0..1, PK `fr_id`). No endpoints known → no
  row → listed as incomplete (A-55). Source ≠ target; both applications in the FR's project.
  Endpoints may have any lifecycle (a legacy → new feed is normal).
- `fr_interface_data_entity` — one row per (interface FR × data entity carried), with a note.
- `v_interface_list` — one row per live interface-behaviour FR; a view, never a table.

**Retire / guards:**
- Removing interface detail retires its carried-entity rows and the detail in one write (S6b Q-5).
- Retiring an FR with live interface detail → 409, remove the detail first (S6b-3).
- Retiring an application named as a live source or target → 409 (generic); retiring a data entity
  carried by a live interface → 409 (generic).
- Changing an interface FR to a non-interface type while live detail exists → 409 (criterion 102);
  to another INTERFACE-behaviour type ("API") → allowed.
- `lifecycle.GUARD_TARGET_COLUMNS` gains `fr_type_behaviour` so a guard FK never double-counts a
  dependent (schema §7).

## 4. Business Requirement grid

| Function | Entity | Use | Logic → output |
|---|---|---|---|
| `read_interface` | `fr_interface`, `fr_interface_data_entity` | R | REVIEWER. `GET /function-requirements/{id}/interface` → the detail (live or retired, with `row_version` and `is_active`) and its live carried entities with notes; 404-free: `{described: false}` when no row (DR6b2-P2) |
| `describe_interface` | `fr_interface`, `fr_interface_data_entity` | C/U | EDITOR. `PUT /function-requirements/{id}/interface`. Lock the FR FOR SHARE; **refuse a retired FR (409)** (DR6b2-P4); its **behaviour** must be INTERFACE (422 otherwise, criterion 102 — never a code test). Lock the `fr_interface` row **FOR UPDATE** if it exists. **Version rule per branch** (DR6b2-P2): insert takes no `row_version` (a racing insert loses on the PK → 409); update and restore require the stored row's `row_version` (409 stale). **Every successful PUT bumps the detail's `row_version`, even when only the carried set changed** (DR6b2-P1). **All checks run before the first write, and the PUT commits once**; carried rows change only through the no-commit helpers (`retire_row`/`relink`/`restore_row`), never `unlink` (DR6b2-P3). Body: `carried` **required** — a list of `{data_entity_id, note}` (`[]` = none; an omitted `note` keeps the stored note — S6b2-4, DR6b2-D1); duplicates → 422; at most 200 entries; locked in id order (DR6b2-D2). Both applications and every data entity **fetched scoped to the FR's project first** (404), then locked FOR SHARE and live-checked (409). Source ≠ target (422). Codes resolve in `INTERFACE_PATTERN/METHOD/FREQUENCY` (optional). Insert, update (row_version) or restore the detail; replace the carried set (retire the dropped, insert/restore the new) |
| `remove_interface` | both | D (soft) | EDITOR. `DELETE …/interface?row_version=`. FR live (409); detail locked FOR UPDATE, version checked; carried rows retire, then the detail, one transaction |
| audit | `fr_interface` | — | Any change to source, target, pattern, method, frequency or volume note writes `RECORD_UPDATED` with the previous application codes / codes / note (DR6b2-S1, as DR6a-S2) |
| `change_fr_type` | `function_requirement` | U | (6a's update_fr) INTERFACE → non-interface with live detail → **409** "This FR has interface detail. Remove it first, or keep an interface type"; the FR is locked FOR UPDATE |
| `retire FR` | `function_requirement` | U | Live detail → 409 (generic FK_LIVENESS through the detail) |
| `interface_list` | `v_interface_list` | R | REVIEWER. `GET /projects/{id}/interfaces?source=&target=&status=`; rows with names, codes, carried DEs **with notes** (S6b2-4), solution, BRs (through `v_br_function_requirement`), status. **Complete** = source, target, method and ≥1 carried entity (S6b2-1); anything less is marked incomplete with what is missing (103). **Pair filter** = source→target as stored, plus BIDIRECTIONAL either way round (S6b2-3); the response also carries the **count of interface FRs with no endpoints** the filter cannot match, shown on the page (S6b2-2, DR6b2-P5). Filter ids are resolved only within the project |
| `consistency_check` | both | R | Gains `interface_under_inactive` (live detail or carried row whose FR, application or DE is retired) — must be empty |

## 5–6. Logical / physical
`docs/slice6b_schema.md` §4–§7. Migrations 0028 `fr_interface` (+ `vb_ops.live_tag`, + the
`GUARD_TARGET_COLUMNS` change, same commit), 0029 `fr_interface_data_entity`, 0030 `v_interface_list`.

## 7. Function — where it lives
- `services/interface.py` (new): `read_interface`, `describe_interface`, `remove_interface`, the list
  reader and the consistency line; `services/function_requirement.py` gains the type-change guard;
  routes in `routers/scope.py`.
- Frontend: `features/frs/InterfaceCard.jsx` on the FR page; `features/interfaces/InterfacesPage.jsx`
  replaces the Interfaces placeholder; `i18n/en.interfaces.json`.

## 8. Risk grade and test depth
**Grade 2** — the interface list is a vendor-facing scope document; a wrong endpoint or a hidden
incomplete interface misleads a build, correctable once noticed. Riskiest concern: **interface
detail on a non-interface FR, or across projects**, and **a renamed type dropping out of the list**
— proven directly.
- pytest: detail on a FORM FR → 422 (102); type change away with detail → 409, to "API" (a new
  INTERFACE-behaviour type) allowed (101/102); list shows the renamed/new type (101); undescribed
  interface FR listed incomplete (103); source = target 422; cross-project app/DE 404 (live and
  retired, nothing leaked); retired app/DE 409; carried set replaced (retire + restore same rows);
  remove detail retires carried rows; FR retire with detail 409; application retire naming the
  interface 409; one Link per FK pair (guard dedup); the consistency line finds a planted orphan;
  reviewer 403, outsider 404.
- ui-verifier: add an interface FR → card appears → set endpoints/pattern/method/DEs → list shows the
  row → remove detail → row shows incomplete → a FORM FR shows no card → reviewer sees no controls.
- Added by review: two PUTs from one version where only the carried set differs → second 409 (DR6b2-P1); re-PUT after remove restores with entities and needs the retired row's version (DR6b2-P2); one retired DE in the list → nothing changes (DR6b2-P3); PUT/DELETE on a retired FR → 409 (DR6b2-P4); omitted `carried` → 422, omitted note keeps the note (DR6b2-D1); duplicate ids → 422 (DR6b2-D2); endpoint change audited (DR6b2-S1); the card keys on `fr_type_behaviour`, and an FR of an added "API" type (behaviour INTERFACE) shows the card (DR6b2-S2).
- **Deliberately uncovered:** `.xlsx` export; >200 carried entities.

## 9. Acceptance
1. Only an FR whose type behaves as an interface can carry interface detail (102).
2. A renamed interface type, or a new one with interface behaviour, still lists (101).
3. An interface FR with no endpoints is listed as incomplete, not hidden (103).
4. Nothing crosses projects; a reviewer changes nothing.

## 10. Design review round 1 of 2 (design-auditor, 2026-10-11)

| Id | Rating | Finding | Disposition |
|---|---|---|---|
| DR6b2-P1 | HIGH | A set-only change didn't move `row_version`, so a stale tab silently reverted it | **Fixed** — detail locked FOR UPDATE, every PUT bumps the version; test |
| DR6b2-P2 | MEDIUM | Version rules per branch unspecified; no read path | **Fixed** — per-branch rule; GET route |
| DR6b2-P3 | MEDIUM | A failed PUT could half-replace the set | **Fixed** — all checks before the first write, one commit, no-commit helpers |
| DR6b2-P4 | MEDIUM | Detail could be written under a retired FR | **Fixed** — 409 on PUT and DELETE |
| DR6b2-P5 | MEDIUM | Pair filter silently dropped incomplete interfaces | **Fixed** — count of unfilterable incomplete FRs (S6b2-2) |
| DR6b2-D1 | MEDIUM | Omitted set meant "carries nothing"; note had no write path | **Fixed** — `carried` required; notes on the PUT, omitted note kept (S6b2-4) |
| DR6b2-D2 | LOW | Duplicates/size unspecified | **Fixed** — 422 on duplicates, cap 200, sorted locks |
| DR6b2-S1 | MEDIUM | Endpoint/code changes not audited | **Fixed** — `RECORD_UPDATED` with previous values |
| DR6b2-S2 | LOW | Card visibility could test the type code | **Fixed** — `fr_type_behaviour` (already on `FrOut`); UAT with an added "API" type |
| — | note | `maintain_fr_types` re-point refused by the FK has no named 409 | **Tracked** for the code-maintenance slice (VB-005 line) |

**Rulings (Ben, 2026-10-11):**
- **S6b2-1** An interface is complete when it has source, target, method and at least one carried data entity; pattern and frequency optional.
- **S6b2-2** A pair-filtered list shows a count of interfaces with no endpoints yet, linking to them.
- **S6b2-3** The pair filter is direction-as-stored, and BIDIRECTIONAL interfaces match either way round.
- **S6b2-4** Carried-entity notes appear on the vendor list and are edited on the FR's interface card; a save keeps notes it did not touch.
- Adopted: the design's `status` filter on the list is kept.
