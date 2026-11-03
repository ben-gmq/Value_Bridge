# Value Bridge — remaining work by phase and slice (2026-11-03)

**Words (P-1, Ben 2026-10-20) — the plan is phase → slice, nothing else:**
- **Phase** — a milestone; the plan has four.
- **Slice** — one piece of work that gets built inside a phase (14, 15, 1e, …).
- **Wave** — only the in-app feature of slice 15 (a client's delivery wave), never a way of grouping this plan.

**For:** Ben · **Replaces** the 2026-10-20 plan (in git history). The function-by-function view stays in
`docs/VB_スペック一覧.md`.

**Unit: person-days** — one working day of build time, covering the slice's spec, design review, build, tests and
browser check. **Not counted:** Ben's own review hours.

**State counted from:** `origin/main` at `c3fb909` (Benefits merged; 1,326 tests passed on that commit).
**Done since 2026-10-20:** all of Phase 1 (Control rules A/B/C and the panel, 1e imports, 1f reports, the Issue
module's browser check); in Phase 2, slice 15 waves, Risks, Decisions and Benefits; in Phase 3, slice 16 archive
files and project purge, and the platform-admin grant approval.

---

## Phase 1 — Finish the scope core — **done**

## Phase 2 — Delivery control modules (7.8 days)

| Slice | Remaining tasks | Spec | Days |
|---|---|---|---:|
| **Change requests** | Raise against an agreed baseline (`CR-`), automatic impact trace, pricing (effort and benefit per unit), decide (an increase needs a cut or a budget record, written as a decision); M2 tile | Plan awaiting approval (`docs/plans/change_requests_plan_2026-11-03.md`) | 4.3 |
| **WBS import + progress** | Import from MS Project; link lines to wave and solution; dated progress; progress report; M5 tile | Owed | 3.5 |

## Phase 3 — Ready for the first client (11.5 days)

| Slice | Remaining tasks | Spec | Days |
|---|---|---|---:|
| **Archive runs on the purge runner** | Move slice 16's ARCHIVE / DELETE_ARCHIVE runs onto `purge_run` (not on main yet) | Owed | 1 |
| **Client read-only login + offline viewer** | Client staff see their own project only, after recorded consent; offline HTML file from a frozen baseline. **Needs from Ben:** the sign-in decision for the login half | Owed | 3 |
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

**On hold:** DFD redesign (Ben).

---

## Totals

| Phase | Slices | Days |
|---|---:|---:|
| 1 — Finish the scope core | 0 | 0 |
| 2 — Delivery control modules | 2 | 7.8 |
| 3 — Ready for the first client | 6 | 11.5 |
| **To first client use (1–3)** | **8** | **19.3** |
| 4 — After first client use | 3 | 9 |
| **Everything in the design** | **11** | **28.3** |

Built one slice at a time from 2026-11-04, 19.3 days reaches first client use around **the end of November
2026**, if Ben's two Phase 3 inputs (sign-in decision, Azure subscription) arrive by mid-November.
