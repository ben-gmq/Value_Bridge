# Slice 6c: Rate card and FR effort days

**Date:** 2026-10-11 · **Author:** Lilly · **Status:** rev 2 — design review round 1 applied (11 findings, 1 HIGH, all fixed); Ben's rulings S6c-1…S6c-8 (2026-10-11)
**Builds on:** D-13, A-38, A-39, R2-D7 (§1a); §4.8; §5.3 EFFORT_RATE; §6.2; §7.5 `change_fr_type`;
§7.9 `effort_summary`; §7.10 `create_project`; §7.13 `rate_function_requirement`, `maintain_rate_card`;
criteria 56, 104, 125. Schema: `docs/slice6c_schema.md` (apple). Builds on 6a (FR complexity and
effort columns, shipped NULL — S6a-3). Where this file and the design disagree, the design wins,
except where Ben has ruled (§10).

## 1. Purpose
Every project gets a **rate card** — standard man-days per FR type × complexity — seeded from an FTC
default and adjustable for the engagement. An FR is **rated** by choosing its complexity: its effort days
are derived from the card, never typed. Changing a rate never silently reprices FRs already rated; it says
how many carry the old rate, and any FR can be re-rated on purpose. An **effort summary** totals the days
by FR type and by Solution (with an Unassigned bucket) and counts the FRs not yet rated.

## 2. Scope
**In:** `effort_rate`; seeding at `create_project` + a backfill command for existing projects; rate-card
screen (Settings → Rate card); the complexity control on the FR page (rating); FR type change re-deriving
effort; effort summary (by type, by solution, unrated count) on the BR–FR map.
**Out:** baseline shadow of the card and `priced_diff` (baseline slice); effort by phase (no `phase` yet)
and by L1 area (S6c-4); code maintenance and the A-16 re-point; a "reprice all" action (S6c-2).

## 3. Keystone grain
`effort_rate` — one row per (project × FR type × complexity): the standard man-days for that cell, with
the reason for its current value. Surrogate PK, natural key a full UNIQUE (apple Q-1). Rates > 0, two
decimals (more → 422, never rounded). Never removed in 6c.

## 4. Business Requirement grid

| Function | Entity | Use | Logic → output |
|---|---|---|---|
| `seed_rate_card` | `effort_rate` | C | Inside `create_project`, same transaction: one cell per resolved (type × complexity) in the FTC default (`seeds/ftc_rate_card.py`, placeholders — S6c-1). A type missing from the default gets no cells; its FRs save, and rating them is 422 (104) |
| backfill | `effort_rate` | C | `python -m seeds.seed_effort_rate --actor-email <admin>`: refuses unless the email is an **active platform admin**; records the OS user and host in the event (DR6c-S1); fills **missing** cells only, idempotent, one transaction and one `RATE_CARD_SEEDED` audit event per project |
| seeding check | — | — | A default key that does not resolve is logged as an error and counted in the event (DR6c-D5); the test pins 16 cells |
| `read_rate_card` | `effort_rate` | R | REVIEWER. Full grid of resolved types × complexities; a gap shows as empty. **Per cell: the count and Σ days of live rated FRs whose `effort_days` ≠ the cell's current rate** — "not at current rate", visible to everyone (DR6c-P1, S6c-5). Untouched seeded cells (row_version 1, no rationale) are marked **"FTC default, unconfirmed"** (DR6c-P3). A cell above 60 days is flagged (S6c-7) |
| `maintain_rate_card` | `effort_rate` | C/U | **EDITOR (S6c-3).** Only changed cells, each with its `row_version` (409 stale; whole request rolls back), **processed in (type code_id, complexity code_id) order** (DR6c-P5). Rationale required (422 blank, 125). Codes resolve (400). Days > 0, ≤ 99,999.99, two decimals, not NaN (422; DR6c-D3/D4); above 60 the request must carry `confirm_high: true` or it is 422 asking to confirm (S6c-7). One `RATE_CARD_CHANGED` audit event: per cell `effort_rate_id`, from/to and the **not-at-current-rate count after the change**, plus the rationale. **No FR is repriced** (A-38); the same counts come back in the response (S6c-2). A DB trigger refuses any change to `standard_days` that does not bump `row_version` and carry a non-blank rationale (DR6c-D1) |
| `rate_function_requirement` | `function_requirement` | U | EDITOR. `PATCH /function-requirements/{id}/complexity` `{complexity_code | null, row_version}`: FR **locked FOR UPDATE first, then `check_live`** (DR6c-D2), then the rate FOR SHARE; an FR of a retired type → 409; no cell → **422 naming the cell** (104); sets complexity and `effort_days` together (the CHECK forbids a half-write); null clears both; re-rating at the same complexity takes today's rate (explicit, audited). `RECORD_UPDATED` with previous complexity and days |
| `change_fr_type` | `function_requirement` | U | (update_fr) after the interface check: a rated FR re-derives days at the new type's rate; no cell → 422 naming it and the whole PATCH is refused. Audit gains `previous_effort_days`. **The response carries an `effort_changed` warning with previous and new days, shown on the FR page** (DR6c-P2) |
| `effort_summary` | `function_requirement`, `solution` | R | REVIEWER. Live FRs: Σ days and count by type (grouped by code_id, label from the code row — a retired type still shows, DR6c-D5), by solution (Unassigned for no solution), the count of unrated FRs (unknown, not zero), **FRs under REJECTED solutions shown apart, outside the headline total** (S6c-8), the count of rated FRs on "FTC default, unconfirmed" cells, and the total days not at current rate |

## 5–6. Logical / physical
`docs/slice6c_schema.md`. One migration, 0031 `effort_rate`. No DDL change to `function_requirement`.

## 7. Function — where it lives
`services/effort.py` (new: `rate_for` — the only rate reader — seed, maintain, rate, summary);
`services/project.py` (`create_project` seeds); `services/function_requirement.py` (type change);
`seeds/ftc_rate_card.py`, `seeds/seed_effort_rate.py`; routes in `routers/scope.py`. Frontend: Settings →
Rate card page; complexity select + effort on the FR page; an "Effort" summary tab on BR–FR map; strings
in `i18n/en.effort.json`.

## 8. Risk grade and test depth
**Grade 1** — effort days price the vendor scope; a silent wrong number moves money. Heavy proof is the
default. Riskiest concern: **days that do not come from the card** (typed, stale, or silently repriced).
- pytest: create_project seeds the full default grid; backfill fills only gaps and is idempotent; rating
  sets days from the card (56), clearing clears both, a missing cell is 422 naming it (104), effort_days
  in any body is ignored; changing a rate leaves rated FRs untouched and reports the count (A-38),
  re-rating takes the new rate and is audited; blank rationale 422 (125), stale cell 409 rolls back the
  whole request, 3 decimals / zero / negative 422, unchanged cells write nothing; type change re-derives
  and refuses on a missing cell; the DB CHECK refuses a half-write by direct SQL; summary totals,
  Unassigned bucket and unrated count; reviewer 403 on writes, outsider 404.
- ui-verifier: Settings → Rate card shows the grid → change one cell with a reason → rate an FR → change
  its type → summary updates → reviewer read-only.
- **Done in-slice as a one-off check (not a harness):** three deliberate breakages of the derivation (days ≠ card, off-rate count inverted, type change keeping old days) each turned the effort tests red; code restored byte-for-byte. A standing mutation harness stays a separate ask.
- **Deliberately uncovered:** two editors changing the same cell at the same instant (row_version decides).

## 9. Acceptance
1. A new project starts with the FTC default card; an Editor can change a cell, with a reason.
2. Choosing an FR's complexity sets its days from the card; days are never typed (56).
3. A type/complexity with no card entry cannot be rated, and the message names the cell (104).
4. Changing a rate never silently reprices rated FRs; the change and its reason are audited (125).
5. The effort summary shows days by type and by solution, with Unassigned and the unrated count.

## 10. Rulings (Ben, 2026-10-11)
- **S6c-1** The FTC default card uses placeholder values (Form 2/4/8/15 · Report 2/4/8/15 · Interface
  3/6/12/20 · Batch 2/5/10/18 man-days for Simple/Medium/Complex/Very complex), marked as placeholders in
  one seed file until FTC confirms.
- **S6c-2** A rate change keeps rated FRs as they are and reports how many carry the old rate; no
  "reprice all" — any FR can be re-rated individually, audited.
- **S6c-3** **Owners and Editors** may change the rate card (the design said Owner only — §4.8, §7.13, §9
  amended). Reviewers read it.
- **S6c-4** Effort by L1 area waits for the reports slice.
- Adopted on apple's recommendation: surrogate PK (Q-1); default in a seed module keyed by code (Q-3); no
  cell removal (Q-4); > 0 (Q-5); two decimals, reject more (Q-6); backfill command (Q-8); complexity
  clearable (Q-10); re-rate takes today's rate (Q-11); rating an FR of a retired type 409 (Q-12); project
  overrides of FR_COMPLEXITY are out of scope until code maintenance handles the re-point (Q-13).

## 11. Design review round 1 of 2 (design-auditor, 2026-10-11)

| Id | Rating | Finding | Disposition |
|---|---|---|---|
| DR6c-P1 | HIGH | Nothing permanent shows which FRs are priced off the current card; an Editor can move a rate, re-rate, and move it back | **Fixed** — per-cell "not at current rate" count and Σ days on the card and summary; same count in the audit event (S6c-5) |
| DR6c-P2 | MEDIUM | A type change silently reprices the FR | **Fixed** — `effort_changed` warning in the response, shown on the FR page |
| DR6c-P3 | MEDIUM | Placeholder rates look negotiated | **Fixed** — "FTC default, unconfirmed" marking; summary counts FRs on such cells; confirmed defaults reach untouched cells only (S6c-6) |
| DR6c-P4 | MEDIUM | Writer role stated three ways; no test pins it | **Fixed** — §1a S6c rows; §4.8, §7.13, §9 amended; test: EDITOR gets 200 |
| DR6c-P5 | LOW | Two multi-cell PUTs can deadlock (500) | **Fixed** — fixed key order |
| DR6c-D1 | MEDIUM | DB does not tie a rate change to a version bump and a reason | **Fixed** — BEFORE UPDATE trigger on `effort_rate` |
| DR6c-D2 | LOW | Rating checks the version before the lock | **Fixed** — lock, then check |
| DR6c-D3 | LOW | No upper bound; overflow is a 500 | **Fixed** — 422 above 99,999.99; 60-day warning (S6c-7) |
| DR6c-D4 | LOW | CHECK admits NaN | **Fixed** — `standard_days <> 'NaN'`; test |
| DR6c-D5 | LOW | Seeding skips unresolved keys silently; summary can drop a retired type | **Fixed** — error logged + counted, 16 pinned; group by code_id |
| DR6c-S1 | LOW | Backfill actor self-declared | **Fixed** — active platform admin only; OS user and host recorded |

**Further rulings (Ben, 2026-10-11):**
- **S6c-5** Visibility is the control on an Editor who both rates and changes rates: the standing per-cell "not at current rate" count, visible to reviewers, plus the audit trail. No approval step. "Not at current rate" means `effort_days` ≠ the cell's current `standard_days`.
- **S6c-6 action (Ben, 2026-10-11):** Ben or an FTC lead sends the real default rates; Lilly then updates `seeds/ftc_rate_card.py`, builds the confirmed-defaults command and applies it to untouched cells only.
- **S6c-6** When FTC confirms the default card, an audited one-off command updates **untouched** cells only (row_version 1, no rationale) in existing projects; rated FRs keep their days and show as not at current rate. (The command is built when the values exist.)
- **S6c-7** A cell above 60 man-days needs an explicit confirmation and is flagged on the card; the hard limit is the column's 99,999.99.
- **S6c-8** FRs under a REJECTED solution are shown apart in the effort summary, outside the headline total.
