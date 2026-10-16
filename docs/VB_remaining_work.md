# Value Bridge — remaining work to first client use (2026-10-16)

**For:** Ben · **Source:** `docs/VB_design.md` §12.1 (waves), the slice specs in `docs/`, `BUGLOG.md`, and the code on `main`
(commit `a5e7d2f`). The function-by-function view is in `docs/VB_スペック一覧.md`.

## The answer in three lines

- **Built:** slices 7a–13d, plus everything before them. That is 79 of the design's 150 functions; 11 more are partly built.
- **To first client use:** about **52 working days** of my time (likely range 45–65). That covers the rest of wave 1,
  waves 2 and 3, and the "Before first client use" gate. Run back to back, that lands in **early-to-mid January 2027** (year-end holidays included).
- **To finish everything in the design:** about **59 days**, which adds wave 4 (English / Japanese / Thai, and the
  version comparison screen).

**How the days were estimated.** Each figure covers the whole slice: spec, design review, build, tests and the
browser check.
- **The pace so far.** Thirteen active days since sign-off (2026-09-28) built the foundation and about twenty slices.
- **Already counted.** Ben's review turnaround is counted as same-day, as it has been so far.
- **Not counted.** The hours Ben spends reviewing are not in the totals. Neither is anything outside VB: Azure access, a
  client's consent.
- **Confidence.** High = the spec is written and the work resembles something already built. Medium = the spec is owed
  but the shape is known. Low = the spec is owed and the area is new.

**What "spec owed" means.** Under D-45, nothing is built before its spec is approved. A slice marked "spec owed" starts
with about ½–1 day of spec and review before its build (already inside its days), and waits for Ben's yes.

---

## Wave 1 — what's left (≈ 22.5 days)

| Slice | What's in it | Spec | Depends on | Days | Confidence |
|---|---|---|---|---:|---|
| **11** — structured requirements | Numbered requirement lines under each BR (kind + priority); which attributes a BR uses (C/R/U per field); system-to-system data flows on a BR; "create the interface FR from these flows" button; the **Data migration** FR type with its own rate-card rows (S11-5); 3 new tables + 3 baseline shadows (migrations 0055–0057); baseline hash spec 4; one-off backfill of existing BR text into lines | **Written** — schema accepted (S11-1, S11-3, S11-5); two wording fixes to `VB_design.md` noted in `slice11_schema.md` §0 | 13c on `main` (done) | 2.5 | High |
| **12** — dashboard tiles | Scope dashboard tiles S7–S11: processes not ready, data entities without fields, effort by solution, open freeze warnings, filter by business area. The project-management view stays a card (S12-1) | **Written** (`docs/slice12_kpis.md`, approved S12-1) | 11 (so the tiles count the new rows) | 1 | High |
| **Next** — Issue module | Stakeholders; raise / link to BRs / resolve issues (`ISS-` numbers); issue dashboard; issues in the baseline freeze; the M3 tile | **Owed** — the design has the functions (§4.5) but no build spec; the schema goes to `apple` first | 12 | 3 | Medium |
| **Next** — control rules + control panel | Control rules (threshold, accountable role, response); the control panel (normal / attention / escalate); the 8 analyses: requirement volatility, process change intensity, org impact, stakeholder engagement, interface load, data migration map, master-data candidates, unlinked FRs | **Owed** | Issue module (stakeholder engagement reads issues); 11 (data migration map reads the Migration FR type) | 4 | Low |
| **1e** — imports | Excel import / export for **BRs, FRs and Issues** (data entities and fields are already done); the process-flow JSON file `vb-process-flow/2.0`: its schema, worked example, AI prompt pack (D-36), export, warn-and-import (D-55) | **Owed** (the design covers the pipeline; each target needs its column map agreed) | 11 (BR columns include the new lines); Issue module | 5 | Medium |
| **1f** — reports, program roll-ups, PDF | Requirements coverage report; traceability matrix; solution classification matrix; application gap report; interface list to Excel; ERD to PNG / SVG; program dashboard and roll-ups (counts, interfaces, effort, control status); program edit; **PDF export of client reports** (D-42) | **Owed** | 1e and the control panel (roll-ups include control status). PDF needs a new library — **I ask before installing it** | 5 | Low |
| **1g** — code maintenance | One screen to keep the drop-down / status lists (global and per-project), including the FR types per project | **Owed** | — | 2 | Medium |

## Wave 2 (≈ 10 days)

| Slice | What's in it | Spec | Depends on | Days | Confidence |
|---|---|---|---|---:|---|
| Benefits (D-14) | Register benefits (`BEN-`), link to solutions with contribution %, value-for-effort ranking, "no benefit yet" check | Owed | Effort (built) | 2.5 | Low |
| Change requests (D-16) | Raise against a frozen or approved baseline (`CR-`), automatic impact trace, effort and benefit pricing, decide — an effort increase needs a cut or a budget record; M2 tile | Owed | Baselines + effort (built); benefits; **phases come in wave 3**, so the impact trace shows no phase until then | 4 | Low |
| WBS import + progress (D-33, D-41) | Import from MS Project through the same import pipeline; link rows to phase and solution; dated progress updates; progress report; M5 tile | Owed | Import pipeline (built); phases (wave 3) for the phase link | 3.5 | Low |

## Wave 3 (≈ 6 days)

| Slice | What's in it | Spec | Depends on | Days | Confidence |
|---|---|---|---|---:|---|
| Risks (D-15) | Register (`RSK-`), probability × impact scoring, promote a risk to an issue, risk register; M4 tile | Owed | Issue module | 2 | Medium |
| Decisions (D-17) | Decision log (append-only, rejected options kept), timeline by area | Owed | Change requests | 1.5 | Medium |
| Phasing and dependency (D-18) | Phases, solution-to-phase split, solution dependencies (no cycles), phase plan report | Owed | Effort (built) | 2.5 | Medium |

## Before first client use — the gate (≈ 13.5 days)

| Item | What's in it | Spec | Depends on | Days | Confidence |
|---|---|---|---|---:|---|
| Azure (D-35) | Container Apps, PostgreSQL Flexible Server on private networking, Key Vault, the two database roles, upload size limits, the scheduled 90-day purge, the sign-in decision (R2-S11) | Designed (§15) | **Ben:** Azure subscription access; the Entra ID sign-in decision | 4 | Low |
| Restore drill (§15.3) | Point-in-time restore rehearsed and written down — the only real way to undo a wrongly frozen baseline | Designed | Azure | 1 | Medium |
| Prompt pack sign-off (D-36) | Final review of the AI prompt pack that 1e ships (Claude / Copilot under FTC accounts only, personal data removed first) | Built in 1e | 1e | 0.5 | High |
| Baseline archive file + `purge_project` (S8-1, Q15) | Long-term archive file of each frozen baseline; full removal of a project at contract end, run as the owner role | Owed | — | 2 | Medium |
| Client read-only login + offline viewer (D-43) | Client staff see their own project only, after recorded consent; an offline HTML file built from a frozen baseline | Owed | Archive file | 3 | Low |
| Full review pass and backlog | Sara's one production-depth pass over everything built since sign-off; **VB-005 backlog cleared or accepted with Ben, line by line** | — | Everything above | 2 | Medium |
| VB-007 | The import wizard's "Do fields later" step can be left with the browser Back button | — | — | 0.5 | High |
| VB-009 | A BR could, in a rare race, link to a data entity being retired at the same moment (suspected; same lock fix as slice 5) | — | — | 0.5 | High |

## Wave 4 — after first client use (≈ 7 days)

| Slice | What's in it | Spec | Depends on | Days | Confidence |
|---|---|---|---|---:|---|
| Languages (D-44) | Japanese and Thai for every screen string and seeded label; a language switch. What consultants type is not translated | Owed | All screens settled | 4 | Medium |
| Version comparison screen (D-50) | Two versions side by side: counts by area, before / after per row, changes highlighted on the diagrams. The comparison logic is already built | Owed | — | 3 | Medium |

## Totals

| Block | Days |
|---|---:|
| Wave 1 remainder (11, 12, Issue, control, 1e, 1f, 1g) | 22.5 |
| Wave 2 | 10 |
| Wave 3 | 6 |
| Before first client use | 13.5 |
| **To first client use** | **52** (range 45–65) |
| Wave 4 | 7 |
| **Everything in the design** | **59** |

**Counted as tasks:** 21 work packages (the rows above), carrying the **71 functions** still to build or finish in the spec list
(59 planned, 11 partly built, 1 with no date — the direct FR-to-function-chart link).

## Bug log (counted 2026-10-16 from `BUGLOG.md`)

- **Open entries:** VB-005 (the standing backlog), VB-006 (fixed, waiting for Ben to close it), VB-007, VB-009. The log's
  header still says five open entries, but VB-008 closed on 2026-10-11; the header needs re-counting.
- **The VB-005 backlog:** 75 lines; 11 of them are marked fixed and waiting for Ben to close. These are presentation and
  tidy-up items from earlier reviews. They hold nothing back now, but every line must be cleared or accepted before
  first client use. That work is inside the 2-day review row above.
