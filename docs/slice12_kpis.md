# Slice 12 — dashboard KPI list (approved by Ben 2026-10-16, S12-1)

D-58 asks for two dashboards — **Scope** and **Project management** — and says the KPI list goes to Ben before
build. Every tile shows a number the app already holds; a tile whose data does not exist yet is left out, never
faked (D-51). The night batch of 2026-10-15 built the first cut of the Scope dashboard on the project home page
(`ProjectHome.jsx`, `GET /projects/{id}/scope-summary`), so the "Built" column below is what you can open today.

## Scope dashboard

| # | KPI | Source | Built |
|---|---|---|---|
| S1 | Requirements in the latest baseline vs today, added / changed since it | baseline counts + diff to live | yes (purple tile) |
| S2 | % of requirements that reach a functional requirement | BR ↔ FR links | yes |
| S3 | Requirements with no solution yet | BR ↔ solution links | yes |
| S4 | FRs not traced to any requirement | BR ↔ FR links | yes (note under S3) |
| S5 | Effort in scope (days), FRs rated / not yet | rate card (D-13) | yes |
| S6 | Per business area: processes, requirements, confirmed, FRs, reach, effort | scope-summary | yes (table) |
| S7 | Processes not ready for the DFD rule (red / amber lights) | DFD light (D-68, D-70) | no — after 13b merges |
| S8 | Data entities without fields / keys only | consistency check | no |
| S9 | Effort by solution | effort summary `by_solution` | no (data exists) |
| S10 | Open freeze warnings | baseline preview gate | no (data exists) |
| S11 | Filter by business area (the mockup's workstream switch) | — | no |

## Project management dashboard

| # | KPI | Source | Built |
|---|---|---|---|
| M1 | Baselines and sign-off (version, frozen, approved by) | baselines | yes (card) |
| M2 | Change requests open / decided | wave 2 (D-16) | no — no data until wave 2 |
| M3 | Issues by severity | Issue module (next wave) | no — no data yet |
| M4 | Risks by exposure | wave 3 (D-15) | no — no data yet |
| M5 | WBS plan vs actual, late tasks, milestones | WBS import (D-33, D-41) | no — no data until wave 2 |

## Questions for Ben

1. Are S1–S11 the right Scope KPIs, and is anything missing?
2. Should the Project management dashboard be its own page now (showing only M1 until the later waves land), or
   stay a card on the Scope dashboard until it has more than one tile?
