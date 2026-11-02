# Value Bridge — next slice: Risks plan (2026-11-02)

**For:** Ren / Ben · **By:** Lilly · **Status:** plan only, awaiting approval. Nothing built, branched off, or migrated.
**Counted from:** `origin/main` at `55fff0c` (Control-C1, C2, C3 merged; 1,250 tests passed on `fffee07`).
**Sources:** `docs/VB_remaining_work.md`, `docs/plans/control_c_plan_2026-10-30.md` §1, design §4.10, §5 (RISK),
§7.13, criteria 61–62, the API table's Phase 2 risk rows, `services/control.py`, `services/issue.py`,
`services/step_retire.py`, `models/shared.py` (code_master), migrations 0003 and 0081–0082.

---

## 1. What is left, by phase and slice

| Phase | Slice | Days | Blocked by |
|---|---|---:|---|
| **1 Finish the scope core** | — **done** (Control-A/B/C, 1e, 1f, 14). ERD as SVG closed by CC-7 (PNG only) | 0 | — |
| **2 Delivery control modules** | **Risks** (`RSK-`, score, promote to an issue, `risk_register` rule) — *this plan* | 2.5 | The migration slot (0083) |
| 2 | Decisions (append-only log, rejected options, timeline by area) | 1.5 | Migration slot; spec owed |
| 2 | Benefits (`BEN-`, link to solutions with %, value ranking, `benefit_gap` rule) | 2.5 | Migration slot; spec owed |
| 2 | Change requests (`CR-`, impact trace, pricing, decision) | 4 | Migration slot; spec owed; reads better after Decisions |
| 2 | WBS import + progress | 3.5 | Migration slot; spec owed |
| **3 Ready for the first client** | Port slice 16's ARCHIVE / DELETE_ARCHIVE runs onto `purge_run` (still "not here yet" on main) | ~1 | Nothing |
| 3 | Client read-only login + offline viewer | 3 | **Ben:** sign-in decision (Entra) for the login half; the viewer is free |
| 3 | Full review pass (Sara production depth + VB-005 backlog) | 2 | **Ben:** the backlog line by line (gate) |
| 3 | Azure (Container Apps, private PostgreSQL, Key Vault, roles, purge job, Entra) | 4 | **Ben:** subscription access + sign-in decision |
| 3 | Restore drill | 1 | The Azure database |
| 3 | Prompt pack sign-off | 0.5 | **Ben:** his review |
| **4 After first client use** | Program roll-ups 2 · Languages 4 · Version comparison screen 3 | 9 | Nothing (but after first use) |
| On hold | DFD redesign | — | **Ben** put it on hold |

No open Q-numbers in design history §1 ("Nothing open", 2026-11-02). Blocked on Ben: the four bold items above.

## 2. Recommendation

**Next slice: Risks.** Phase 1 is finished, so Phase 2 is the next milestone, and Risks is its most ready module:
the design already fixes the table, the `RSK` number series, the three code lists, the `RISK` component and the
`risk_register` thresholds (≥ 12 flag, ≥ 16 escalate) — the panel already lists it as "coming". It needs **one
migration (0083)**; this task may not claim one, so **Ren has to confirm the slot** before piece A starts.

**Runner-up: the ARCHIVE / DELETE_ARCHIVE port** (~1 day, likely no migration, nothing blocks it) — but it is
Grade 1 (it destroys archive keys) and nobody sees it until first client use.

## 3. Risks — scope

**In:** design §4.10 — `raise_risk`, `score_risk`, `promote_risk_to_issue`, `risk_register` — plus the
`risk_register` control rule (§7.13), retire / restore (law 1), and the screens.

**Out:** Excel import / export of risks; the M4 tile (no M-tiles exist yet); a "decision" record on
materialise (the Decisions module is not built — an audit entry `RISK_MATERIALISED` stands in); program roll-up.

**Grain:** one row per risk in one project. Live, **not frozen** in baselines (design §5 table 32), so no shadow.

## 4. Pieces (each one a person can open and try)

### Piece 0 — the two VB-005 Control-C3 lines (~0.3 day, no migration) — *if Ben says yes (Q6)*
- L1: one `traced_fr_ids` helper read by the FR register, the effort summary and the scope summary.
- L2: the untraced view ignores "show retired" and says so on screen, so it matches the panel count.
- Can be built while Ren confirms the migration slot.

### Piece A — raise, score and list risks (~1.1 days, ~900 lines)
- **Migration 0083** (one commit, reversible): table `risk` per design §5 RISK + optional `phase_id` (Q3), audit
  columns, `row_version`, grants (no DELETE), code FKs by category as `issue` does; `ck_code_behaviour_present`
  widened so `RISK_PROBABILITY` / `RISK_IMPACT` carry weights and `RISK_STATUS` carries a behaviour (Q1), with
  the library rows backfilled; `ck_ctl_comparison` widened with `GE` (Q2). Downgrade refuses while any risk row
  exists.
- Seeds: `seed_code_master` gains the behaviour codes for the risk lists.
- Service `services/risk.py`: create (number from `next_number('RSK')`), update, retire, restore;
  `exposure_score` = probability weight × impact weight, set at save, ignored if sent (law 6).
- Routes: `GET/POST /projects/{id}/risks` (`project_ctx`, `component='RISK'` on the write),
  `GET/PATCH /risks/{id}` (`object_guard`), retire / restore through `lifecycle.RESTORABLE`.
- Plumbing: `models/__init__`, `code_lists` (three new code columns re-pointed), `step_retire` (risk on a step
  is deliberately **not** owned — design §5 "not guarded"; named in its exclusions), `components.COMPONENT_ROWS`.
- Screen: **Risks** in the left rail (hidden when the component is off) — register ranked by exposure, with age,
  owner and wave columns and filters; a risk page with the form. Strings in `en.risks.json`; links in `links.js`;
  one API function per route.

### Piece B — promote a risk to an issue (~0.6 day, ~450 lines)
- `POST /risks/{id}/materialise`, EDIT, needs the `ISSUE` component on too (else 409, nothing written).
- One transaction: `issue.raise_issue(commit=False)`, set `materialised_issue_id`, status → the MATERIALISED
  behaviour, audit `RISK_MATERIALISED`. Twice → 409. The risk row stays (criterion 62).
- The dialog asks for the issue's raiser stakeholder, severity and type (Q4); title and description carry over.
- The issue page shows "materialised from RSK-0003" with a link back.

### Piece C — the `risk_register` control rule (~0.4 day, ~300 lines)
- Headline = the highest exposure among open risks (Q5); house rule `GE` 12 / 16, action "Mitigation owner + date;
  steering if unmitigated"; added to `HOUSE_RULES`, removed from `COMING`; a Reports tab is not needed — the
  panel row links to the register.
- `seed_control_rules` adds it switched off in running projects (CB-5), on in new ones.

**Total:** ~2.1 days build + ~0.4 spec / review = **~2.5 days** (plus 0.3 if piece 0 rides along).

## 5. Grade and tests

**Grade 2**, because a wrong exposure score or panel colour reaches a steering meeting and the client acts on it;
nothing moves money, grants access or destroys data (soft delete; access through the existing guards, which the
route-guard and leak tests already police). Riskiest concern: **materialise half-failing** (an issue without the
link, or the reverse). I propose ~30 tests, no mutation harness:
- Criteria 61 and 62 as written; `exposure_score` sent in a body is ignored; changing probability re-scores.
- A project that relabels or adds a probability code still scores by weight, never by code or label.
- Stale `row_version` → 409; `RISK` off → 409 `COMPONENT_OFF`; materialise with `ISSUE` off → 409 and no issue row.
- Materialise twice → 409; a failure after the issue insert leaves neither row.
- Register order (exposure, then oldest first); retired owner / wave / node shown, not hidden.
- Rule: no open risks → "not measured", never 0; 11 normal, 12 flag, 16 escalate; CLOSED and MATERIALISED ignored.
- Seed: off in a running project, on in a new one. Migration 0083 up / down, and down refused with a risk row.
- Step retire leaves a risk on that step live. Purge covers risk rows. GET leak test and criterion 49 / 49b pass.
- **Left uncovered on purpose:** ageing beyond "days since raised"; volume beyond 500 risks per project.

## 6. Review steps
1. **apple** on the `risk` table and the code-behaviour change, before the spec is final (CLAUDE.md: schema → apple).
2. Spec `docs/slice_risks_spec.md` to the `design-spec` standard → **design-review** (design-auditor), two rounds
   at most; all findings relayed to Ben with a disposition.
3. **Sara** before each commit touching the migration or the routes; CRITICAL / HIGH fixed, the rest to VB-005.
4. **test-runner**: fast run per commit; the full suite (`-m "" -n 4`) on the merged-with-main commit, named.
5. **ui-verifier** on the register, the risk page, the materialise dialog and the panel row, beside the mockup.
6. `rules-check-drift` before the merge (the CLAUDE.md deploy line gains a Risks note).

## 7. Ports and databases (slot 1)
- API **8121**, web **5191** (`VB_API_PORT=8121 VB_WEB_PORT=5191 npm run dev`); the frontend calls
  `http://localhost:8121` through the Vite proxy. Checked free before start; stopped by PID.
- Databases I create and drop: `vb_s1rk_db` (dev), `vb_s1rk_uat_db` (browser check), `vb_s1rk_test_db` and its
  four worker copies `_gw0`…`_gw3`. The existing `vb_s1_*` are not mine and are left alone.
- No shared file fixes a port or database name that I need to change (each worktree has its own `backend/.env`).

## 8. Questions for Ben
- **Q1 How are exposure weights held?** (a) a weight 1–5 as the behaviour code on each probability / impact code,
  and OPEN / CLOSED / MATERIALISED behaviours on the status list — buys a project being able to rename or add a
  level and still score correctly · costs a check-constraint change in 0083. (b) the list's sort order — no
  constraint change, but reordering a list silently changes every score. **I recommend (a).**
- **Q2 How is "≥ 12" stored?** (a) add a `GE` comparison — the rule screen reads "12 or more" · costs one more line
  in 0083. (b) store "> 11" — no schema change, but the screen shows "> 11". **I recommend (a).**
- **Q3 Can a risk name a wave?** §4.10 says a risk "may link to a Phase" but the table has no column for it.
  (a) add an optional wave link, so the register groups by wave · costs one column. (b) derive the wave from the
  linked solution — misses risks with no solution. **I recommend (a).**
- **Q4 Who is the raiser of the issue a risk becomes?** The design says the risk's owner, but an issue's raiser is
  a stakeholder and a risk's owner is a role, so it cannot hold. (a) the dialog asks for the raiser stakeholder.
  (b) a stakeholder field on the risk itself. **I recommend (a).**
- **Q5 What does the panel measure?** (a) the highest exposure among open risks · (b) the number of open risks
  scoring 12+, flag > 0 and escalate if any scores 16+ — two numbers in one rule, which the rule shape does not
  hold. **I recommend (a).**
- **Q6 Ride the two VB-005 lines along as piece 0?** Neither touches risks; both make the untraced-FR figures agree
  everywhere. (a) yes, +0.3 day, built first while the slot is confirmed · (b) leave them for the full review pass.
  **I recommend (a).**

## 9. Deploy steps owed on Ben's main database (not done by this task)
`alembic upgrade head` (0068 → 0082), then `python -m seeds.seed_control_rules --actor-email <admin>` once.
