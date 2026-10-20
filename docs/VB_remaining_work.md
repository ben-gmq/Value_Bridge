# Value Bridge — remaining work by phase and slice (2026-10-20)

**Words (P-1, Ben 2026-10-20) — the plan is phase → slice, nothing else:**
- **Phase** — a milestone; the plan has four.
- **Slice** — one piece of work that gets built inside a phase (14, 15, 1e, …).
- **Wave** — only the in-app feature of slice 15 (a client's delivery wave), never a way of grouping this plan.

**For:** Ben · **Replaces** the 2026-10-16 plan (in git history at `daecb2f`). The function-by-function view stays in `docs/VB_スペック一覧.md`.

**Unit: person-days** — one working day of build time, covering the slice's spec, design review, build, tests and
browser check. **Based on** the 2026-10-16 estimates, re-sized where a spec has since been written (slice 15: 2.5,
slice 16: 3.5), and checked against the pace since: slices 11, 12, 1g and the Issue module each landed close to their
estimate. **Not counted:** Ben's own review hours.

**State counted from:** `origin/main` at `e2933b5` (slice 14 Issue module merged) and branch `spec/slice15-16-rulings`
(`57b4768`, rulings for slices 15 and 16 written into the specs, not yet on `main`).
**Done since 2026-10-16:** slices 11 and 12, 1g code maintenance, access slices A and B, the Issue module,
VB-007 / VB-009 / VB-010.

**Phases** are milestones, in the order they finish. A phase is not a build order: slices 15 and 16 have their specs
and go first, while the specs owed in Phase 1 are drafted.

---

## Phase 1 — Finish the scope core (11.5 days)

| Slice | Remaining tasks | Spec | Days |
|---|---|---|---:|
| **14 — Issue module** | Browser check of the Issue screens (built and merged; not yet seen in a browser) | Approved | 0.5 |
| **Control rules + control panel** | Rules (threshold, accountable role, response); the panel (normal / attention / escalate); the 8 analyses | Owed | 4 |
| **1e — Imports** | Excel import / export for BRs, FRs and Issues; the process-flow file `vb-process-flow/2.0` with its schema, example, AI prompt pack, export, warn-and-import | Owed | 5 |
| **1f — Reports** | Requirements coverage, traceability matrix, solution matrix, application gap, interface list to Excel, ERD to PNG / SVG, program edit; client reports printed to PDF from the browser | Owed | 2 |

## Phase 2 — Delivery control modules (16 days)

| Slice | Remaining tasks | Spec | Days |
|---|---|---|---:|
| **15 — Waves (phasing)** | Waves per project, each solution's split across waves (100 % or empty), solution dependencies with no cycles, the wave plan report; frozen in baselines | Approved (W-1…W-9) | 2.5 |
| **Benefits** | Register (`BEN-`), link to solutions with contribution %, value-for-effort ranking, "no benefit yet" check | Owed | 2.5 |
| **Change requests** | Raise against a frozen baseline (`CR-`), automatic impact trace, pricing, decide (an increase needs a cut or a budget record); M2 tile | Owed | 4 |
| **Risks** | Register (`RSK-`), probability × impact, promote to an issue; M4 tile | Owed | 2 |
| **Decisions** | Append-only decision log with rejected options; timeline by area | Owed | 1.5 |
| **WBS import + progress** | Import from MS Project; link lines to wave and solution; dated progress; progress report; M5 tile | Owed | 3.5 |

## Phase 3 — Ready for the first client (15 days)

| Slice | Remaining tasks | Spec | Days |
|---|---|---|---:|
| **16 — Archive files + project purge** | Archive file of each frozen baseline; two-year project archive (kept, with the live state and activity history); four-eyes purge with the key kept; the interim admin-independence check (Ben's answers 2026-10-20, AR-7…AR-13) | Approved | 3.5 |
| **Platform-admin grant approval** | Making someone a platform admin needs a second platform admin's approval (AR-13, Q-93 b); covers every four-eyes control | Owed | 1 |
| **Client read-only login + offline viewer** | Client staff see their own project only, after recorded consent; offline HTML file from a frozen baseline | Owed | 3 |
| **Full review pass** | Sara's production-depth pass over everything since sign-off; the VB-005 backlog cleared or accepted with Ben, line by line | — | 2 |
| **Azure** | Container Apps, PostgreSQL on private networking, Key Vault, the two database roles, upload limits, the 90-day purge job, Entra ID sign-in. **Needs from Ben:** subscription access and the sign-in decision | — | 4 |
| **Restore drill** | Point-in-time restore rehearsed and written down | — | 1 |
| **Prompt pack sign-off** | Final review of the prompt pack shipped in 1e | — | 0.5 |

## Phase 4 — After first client use (9 days)

| Slice | Remaining tasks | Spec | Days |
|---|---|---|---:|
| **Program roll-ups** | Program dashboard: counts, interfaces, effort, control status, side by side per project | Owed | 2 |
| **Languages** | Japanese and Thai for every screen string and seeded label; a language switch | Owed | 4 |
| **Version comparison screen** | Two versions side by side, changes highlighted on the diagrams (the comparison logic is built) | Owed | 3 |

---

## Totals

| Phase | Slices | Days |
|---|---:|---:|
| 1 — Finish the scope core | 4 | 11.5 |
| 2 — Delivery control modules | 6 | 16 |
| 3 — Ready for the first client | 7 | 15 |
| **To first client use (1–3)** | **17** | **42.5** |
| 4 — After first client use | 3 | 9 |
| **Everything in the design** | **20** | **51.5** |

**Against the 2026-10-16 plan:** 9.5 days of it are done; slice 16 grew by 1.5 days in its spec (the two-year
archive); the Issue module's browser check adds 0.5; the platform-admin grant approval (AR-13) adds 1. Access slices A and B were added and done outside the plan.
Built one slice at a time from 2026-10-21, 42.5 days reaches first client use around **mid-December 2026**.
