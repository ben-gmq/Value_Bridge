# Value Bridge — remaining work to first client use (2026-10-16)

**For:** Ben · **Source:** `docs/VB_design.md` §12.1 (waves), the slice specs in `docs/`, `BUGLOG.md`, and the code on `main`.
The function-by-function view is in `docs/VB_スペック一覧.md`.
**Plan agreed with Ben 2026-10-16:** keep the §12.1 order; run **two work streams at once**; two trims (PDF by browser
printing; program roll-ups after first client use); **Azure is done with Ben at the end**, once the app is ready.

## The answer in three lines

- **Built:** slices 7a–13d and everything before them — 79 of the design's 150 functions, 11 more partly built.
- **To first client use:** about **40 working days** of calendar (range 36–50) — **mid-December 2026** if started
  Monday 2026-10-19. The work itself is about **49 days**; two streams fit it into 40 calendar days.
- **To finish everything in the design:** about **58 days** of work. That adds wave 4 (English / Japanese / Thai, the
  version comparison screen) and the program roll-ups moved after first client use.

**How the days were estimated.** Each figure covers the whole slice: spec, design review, build, tests and the
browser check.
- **The pace so far.** Thirteen active days since sign-off (2026-09-28) built the foundation and about twenty slices.
- **Already counted.** Ben's review turnaround is counted as same-day, as it has been so far.
- **Not counted.** Ben's own review hours. Azure access and the sign-in decision are Ben's, done together at the end.
- **Confidence.** High = the spec is written and the work resembles something already built. Medium = the spec is owed
  but the shape is known. Low = the spec is owed and the area is new.

**What "spec owed" means.** Under D-45, nothing is built before its spec is approved. In this plan, each spec is
drafted **while the slice before it is being built**, so Ben's questions come in batches and no slice waits on its own
spec.

---

## How the two streams run

| | Stream A — the feature chain (sets the date) | Stream B — everything that does not wait for it |
|---|---|---|
| **Order** | 11 → 12 → Issue module → control rules → 1e imports → 1f reports → change requests → decisions → WBS | 1g code maintenance → phasing → benefits → archive file + `purge_project` → VB-007, VB-009 → risks (after the Issue module lands) → client read-only login + offline viewer |
| **Days of work** | ≈ 26.5 | ≈ 15 |
| **Rule** | Both streams share one database design, so **only one stream adds tables at a time**. Each migration lands on `main` in order, and the other stream rebases before its own (CLAUDE.md). I am the only one who merges, so this is a queue, not a clash. | |

Then, in sequence, once both streams are done:
- **Sara's full review pass** and the **VB-005 backlog cleared with Ben** (2 days).
- **Azure with Ben** (4 days), the **restore drill** (1 day), and **prompt pack sign-off** (½ day).

**Why 40 and not 34.** The critical path is 26.5 + 7.5 = 34 days. About 6 days are added for running two streams:
- migrations waiting their turn on `main`;
- two streams' reviews arriving at Sara and at Ben on the same day;
- rebasing.

---

## Stream A — the feature chain (≈ 26.5 days)

| Slice | What's in it | Spec | Depends on | Days | Confidence |
|---|---|---|---|---:|---|
| **11** — structured requirements | Numbered requirement lines under each BR (kind + priority); which attributes a BR uses (C/R/U per field); system-to-system data flows on a BR; "create the interface FR from these flows" button; the **Data migration** FR type with its own rate-card rows (S11-5); 3 new tables + 3 baseline shadows (migrations 0055–0057); baseline hash spec 4; one-off backfill of existing BR text into lines | **Written** — schema accepted (S11-1, S11-3, S11-5); two wording fixes to `VB_design.md` noted in `slice11_schema.md` §0 | 13c on `main` (done) | 2.5 | High |
| **12** — dashboard tiles | Scope dashboard tiles S7–S11; the project-management view stays a card (S12-1) | **Written** (`docs/slice12_kpis.md`) | 11 | 1 | High |
| **Issue module** | Stakeholders; raise / link to BRs / resolve issues (`ISS-`); issue dashboard; issues in the baseline freeze; the M3 tile | **Owed** — drafted during 11; schema to `apple` | 12 | 3 | Medium |
| **Control rules + control panel** | Rules (threshold, accountable role, response); the panel (normal / attention / escalate); the 8 analyses | **Owed** — drafted during the Issue module | Issue module; 11 | 4 | Low |
| **1e** — imports | Excel import / export for BRs, FRs and Issues; the process-flow JSON `vb-process-flow/2.0` with schema, example, AI prompt pack (D-36), export, warn-and-import (D-55) | **Owed** — column maps drafted during control rules | 11; Issue module | 5 | Medium |
| **1f** — reports | Requirements coverage (including the project-wide list of system flows no FR covers yet — information, a warning with Function requirements on; slice 11c shows it per requirement only), traceability matrix, solution matrix, application gap, interface list to Excel, ERD to PNG / SVG, program edit; **client reports printed to PDF from the browser** (print layout, no new library) | **Owed** | 1e; control panel | 2 | Medium |
| **Change requests** (wave 2, D-16) | Raise against a frozen or approved baseline (`CR-`), automatic impact trace, pricing, decide — an increase needs a cut or a budget record; M2 tile | **Owed** | Benefits and phasing (stream B, both done by then) | 4 | Low |
| **Decisions** (wave 3, D-17) | Append-only decision log with rejected options; timeline by area | **Owed** | Change requests | 1.5 | Medium |
| **WBS import + progress** (wave 2, D-33, D-41) | Import from MS Project through the import pipeline; link rows to phase and solution; dated progress; progress report; M5 tile | **Owed** | Import pipeline (built); phasing (stream B) | 3.5 | Low |

## Stream B — alongside (≈ 15 days)

| Item | What's in it | Spec | Depends on | Days | Confidence |
|---|---|---|---|---:|---|
| **1g** — code maintenance | One screen for the drop-down / status lists, global and per project, including FR types | Owed | — | 2 | Medium |
| **Phasing and dependency** (wave 3, D-18) | Phases, solution-to-phase split, dependencies (no cycles), phase plan report | Owed | Effort (built) | 2.5 | Medium |
| **Benefits** (wave 2, D-14) | Register (`BEN-`), link to solutions with contribution %, value-for-effort ranking, "no benefit yet" check | Owed | Effort (built) | 2.5 | Low |
| **Baseline archive file + `purge_project`** (S8-1, Q15) | Long-term archive file of each frozen baseline; full removal of a project at contract end, run as the owner role | Owed | — | 2 | Medium |
| **VB-007, VB-009** | Import wizard Back-button gap; the rare BR-link race (same lock fix as slice 5) | — | — | 1 | High |
| **Risks** (wave 3, D-15) | Register (`RSK-`), probability × impact, promote to an issue, register; M4 tile | Owed | Issue module (stream A) | 2 | Medium |
| **Client read-only login + offline viewer** (D-43) | Client staff see their own project only, after recorded consent; offline HTML file from a frozen baseline | Owed | Archive file | 3 | Low |

## At the end, in sequence (≈ 7.5 days)

| Item | What's in it | Days | Confidence |
|---|---|---:|---|
| Full review pass and backlog | Sara's production-depth pass over everything since sign-off; VB-005 cleared or accepted with Ben, line by line. The 11 items already fixed can be closed as we go | 2 | Medium |
| **Azure with Ben** (D-35) | Container Apps, PostgreSQL Flexible Server on private networking, Key Vault, the two database roles, upload limits, the scheduled 90-day purge, the sign-in (Entra ID) setup. **Ben provides the subscription access and the sign-in decision** | 4 | Low |
| Restore drill (§15.3) | Point-in-time restore rehearsed and written down | 1 | Medium |
| Prompt pack sign-off (D-36) | Final review of the prompt pack shipped in 1e | 0.5 | High |

## After first client use (≈ 9 days)

| Item | What's in it | Days | Confidence |
|---|---|---:|---|
| **Program roll-ups** (moved here 2026-10-16) | Program dashboard and roll-ups: counts, interfaces, effort, control status, side by side per project. Only matters once a client runs several projects as one program | 2 | Medium |
| Languages (wave 4, D-44) | Japanese and Thai for every screen string and seeded label; a language switch | 4 | Medium |
| Version comparison screen (wave 4, D-50) | Two versions side by side with changes highlighted on the diagrams; the comparison logic is already built | 3 | Medium |

## Totals

| Block | Days of work |
|---|---:|
| Stream A | 26.5 |
| Stream B | 15 |
| At the end | 7.5 |
| **Work to first client use** | **49** |
| **Calendar to first client use** (two streams) | **≈ 40** (range 36–50) |
| After first client use | 9 |
| **Everything in the design** | **58** |

**What the trims saved:**
- Printing to PDF from the browser instead of adding a PDF library saves 1 day.
- Moving the program roll-ups saves 2 days before first client use; they are still built, after it.

**Counted as tasks:** 20 work packages before first client use (the rows above), carrying the **71 functions** still to build
or finish in the spec list (59 planned, 11 partly built, 1 with no date — the direct FR-to-function-chart link).

## Bug log (counted 2026-10-16 from `BUGLOG.md`)

- **Open entries:** VB-005 (the standing backlog), VB-006 (fixed, waiting for Ben to close it), VB-007, VB-009. The
  log's header still says five open entries, but VB-008 closed on 2026-10-11; the header needs re-counting.
- **The VB-005 backlog:** 75 lines; 11 of them are marked fixed and waiting for Ben to close. Each line must be cleared or
  accepted before first client use; closing the fixed ones as we go keeps the end block to 2 days.
