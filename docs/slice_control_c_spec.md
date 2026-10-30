# Slice Control-C — where change lands, master data, FTC defaults, reset, unlinked FRs (spec, 2026-10-30)

**Design:** `VB_design.md` §7.9 (`process_change_intensity`, `master_data_candidates`, `fr_unlinked`, the
`headline_value` contract), §7.13 (registry, seeded-rule table, `maintain_house_default`,
`reset_project_rules_to_house_default`, `control_panel`), D-19, A-42, acceptance 79, 82, 192; Control-A
(`slice_control_a_spec.md`, CT-1…CT-4) and Control-B (`slice_control_b_spec.md`, CB-1…CB-5).
**Status:** approved by Ben 2026-10-30 (via Ren), *"all recommended"* — CC-1…CC-7 (history §3). Plan:
`docs/plans/control_c_plan_2026-10-30.md`. Design review round 1 in §11; round 2 in §13. **Not in this slice:** §9.

**What it adds.** (1) Two more analyses, each a report tab, a headline number and a seeded rule. (2) A screen where a
platform admin edits the FTC company defaults that future projects start from. (3) A button that resets a project's
rules to those defaults. (4) A rule on FRs nobody traced to a requirement (`fr_unlinked`, piece C3 — the only piece
with a migration). After it, the panel's "still to come" line names only `benefit_gap` and `risk_register`.

## 1. Interface
- **Input:** none new for the analyses — they read the to-be chart, BRs, solutions, data entities and FRs the project
  already holds. A platform admin's edit to a company default (threshold, escalate, action, escalation path, reason).
  An editor's reset (reason, plus the rule versions the preview showed).
- **Output:** two report tabs and three more panel rows (§2); a company-defaults tab on the Admin page; a reset preview
  and the reset itself on the control panel.
- **Validation:** the analysis GETs are `project_ctx(VIEW)`, 404 for a project you cannot see. The company-default
  routes are `platform_admin` — staff, a project ADMIN and an editor get 403. Reset is `project_ctx(EDIT)` — a viewer
  gets 403. Every write needs a non-blank reason (422) and a current row version (409). A threshold below zero, or an
  escalate value not beyond the threshold, is 422 (as Control-A).
- **Archive:** reading writes nothing. A company-default edit writes `CONTROL_RULE_CHANGED` with no project (CC-6). A
  reset writes one `CONTROL_RULES_RESET` naming the codes it changed and added, with the reason. The seed writes
  `CONTROL_RULES_SEEDED` per project, as before. Audit rows are append-only and kept with the project.
- **Maintenance loop:** FTC (a platform admin) reviews the company defaults after each engagement's close-out and
  before the next mobilisation; the PMO reads the panel every steering cycle and renegotiates thresholds with the
  client. Every change is audited with its reason.

## 2. The analyses — what each measures
All follow the §7.9 contract (`{measured, reason, figures}`; `None` + reason = NOT MEASURED, never 0). Equal to the
threshold is GREEN, as in Control-A. "An area" is a to-be L1 node, **keyed by its node id**, never its `hier_code`
(as CB-1); a step's area is found by walking its live parents.

### 2.1 `process_change_intensity` — "is the change piling up in one part of the business?" (CC-1)
- **A changed step** is a live to-be process step (`is_process`) with at least one live BR that has a live,
  non-rejected solution — the same "change" as `org_impact_heatmap` (CB-2), counted per step. Every changed step
  weighs the same, whatever its solution category (CC-1: no weighting).
- **Per area:** changed steps, total live process steps, and changed steps per solution category (context, never
  counted — a step with two categories shows in both columns, once in the total).
- **Headline:** the share of all changed steps that sit in the busiest area, %. Tied areas: the share is the same;
  the figure names the first by chart order and how many areas share it.
- **NOT MEASURED:** SOLUTION off; fewer than two areas hold a process step (one area always reads 100 %); no changed
  step.
- **Rule (CC-1):** flag > 50 %, escalate > 70 %. Action: "Check the change workload and the change-management plan for
  that area before the next gate".

### 2.2 `master_data_candidates` — "is shared data owned by anyone?" (CC-2)
- **A candidate** is a live data entity used (`br_data_entity`, live) by live to-be BRs under **three or more**
  distinct areas.
- **Table:** per candidate — its number and name, its areas, how many BRs use it, and its `business_owner_note`.
- **No owner** = the note is empty or only spaces. Any other text counts as an owner — a note such as "TBD" counts,
  and the table shows it (assumption C1).
- **Headline:** candidates with no owner noted. Unit COUNT. The number of candidates stands beside it.
- **NOT MEASURED:** no live to-be BR uses any live entity (the data mapping has not started).
- **Rule (CC-2):** flag > 0, escalate > 5. Action (§7.9): "Assign a single owner; it becomes a managed cross-workstream
  dependency".

### 2.3 `fr_unlinked` — "is a vendor being asked for a function nobody traced to a requirement?" (CC-3, piece C3)
- **Counted:** live FRs with no live link to a live BR — the same set as the FR register's `unlinked=true` filter
  (`function_requirement` service), so the panel figure and the register list always agree.
- **Headline:** that count. Unit COUNT. Their effort days stand beside it when EFFORT is on.
- **NOT MEASURED:** FUNCTION_REQUIREMENT off; the project has no live FR.
- **Rule (CC-3):** flag > 0, escalate > 5. Action (§7.9): "Link or retire before the next freeze; a vendor cannot be
  held to a function nobody traced to a requirement". No report tab: the panel row links to the FR register filtered
  to unlinked. A BR on an as-is step is a live BR here as in the register (round 1 Q4), so the two never disagree.

## 3. FTC company defaults (§7.13 `maintain_house_default`, CC-6)
- **Who:** platform admins only (`platform_admin` guard). FTC's standard, not any client's.
- **Edits:** threshold, escalate value, prescribed action, escalation path — replaced as a whole. Its own request body
  holds only those four fields plus reason and row version, extra fields refused (R1-D1): never an owner (the
  database refuses one too, `ck_ctl_house_no_owner`), never the comparison, never on/off (§9). Validation of the
  numbers is the one shared with the project PATCH.
- **The two text fields reach every future client** (R1-S1): the edit dialog says so under them — "Every future
  client project starts with this text: name roles, never people or clients".
- **Needs a reason**, kept on the row (`change_rationale`), and a current `row_version` (409 if stale).
- **Audit:** `CONTROL_RULE_CHANGED`, `project_id` empty, `detail.house = true`, numbers from / to, the two text fields
  only as "changed" (CT-3), the reason in full. No change → nothing written.
- **History** (R1-P4): the tab lists each default's changes — when, who, numbers from / to, the reason — read from its
  `CONTROL_RULE_CHANGED` audit rows (append-only, kept for the life of the installation). That is what FTC's
  close-out review reads.
- **Effect:** future projects only (acceptance 79). No running project's rules move — they are copies (D-19).

## 4. Reset a project's rules to the FTC defaults (§7.13 `reset_project_rules_to_house_default`, CC-4)
- **Who:** an editor of the project (`project_ctx(EDIT)`, SC-7, acceptance 192).
- **What it does, per house rule:**
  - The project has the rule: overwrite `threshold_value`, `escalate_value`, `prescribed_action`, `escalation_path`
    from the house row. **Keep** `owner_org_role_id` and `is_enabled` (CC-4 — a reset never switches on a rule the
    client has not agreed). A rule already equal to the default is left untouched (no version bump, not listed).
  - The project lacks the rule: add it **switched off** (as the CB-5 backfill).
- **Preview first:** `GET …/control-rules/reset-preview` (EDIT) lists, per rule that would change, the current and
  default values of the four fields, and the rules that would be added. The screen shows it in the confirm dialog, so
  the editor sees the agreed action and escalation text they are about to replace — the audit does not keep that text
  (CT-3). It also returns a **version stamp**: the `row_version` of **every** live project rule and **every** house
  row it read, changed or not (R1-P1).
- **The reset** (`POST …/control-rules/reset`) carries the reason and that stamp. In one transaction the server locks
  the project's rules (`FOR UPDATE`) and the house rows (`FOR SHARE`), compares the stamp to every row, and returns 409
  with nothing written if any project rule or house row differs, appeared or went (R1-P1, R1-P3). Only then does it
  recompute and write. A reset with nothing to change writes nothing — no rule, no audit row — and says so.
- **After a reset** a rule changed by it shows on the panel "Reset to FTC defaults on <date> by <name>" with the
  reason, until a person next edits it (R1-P2). The marker is read from the audit trail, as `_switched_on_ever`: it
  shows when the rule's latest event is a `CONTROL_RULES_RESET` naming its code, and clears once a later
  `CONTROL_RULE_CHANGED` targets the rule (round 2 N2) — so an ESCALATE against FTC's numbers is never read as a threshold
  the client agreed.
- **Audit:** one `CONTROL_RULES_RESET` with the reason, the codes changed and the codes added; per changed rule the
  numbers from / to, text fields as "changed" (CT-3). Each changed rule's `change_rationale` becomes the reason.

## 5. Services, routes and screens
- `services/control_reports.py`: `process_change_intensity`, `master_data_candidates` (table + headline, as Control-B).
- `services/control.py`: three more `HOUSE_RULES` rows (`fr_unlinked` in C3), `headline()` dispatch, `_fr_unlinked`;
  `list_house`, `update_house`, `reset_preview`, `reset`. Validation shared with `update_rule` (one function, playbook
  §10). `COMING` keeps `benefit_gap`, `risk_register`.

| Method + path | Guard | Does |
|---|---|---|
| `GET /projects/{id}/change-intensity` | `project_ctx(VIEW)` | areas with changed / total steps, categories, headline |
| `GET /projects/{id}/master-data` | `project_ctx(VIEW)` | candidate entities, areas, BR count, owner note, headline |
| `GET /control-rules/defaults` | `platform_admin` | the company defaults |
| `PATCH /control-rules/defaults/{analysis_code}` | `platform_admin` | edit one default (reason, row_version) |
| `GET /projects/{id}/control-rules/reset-preview` | `project_ctx(EDIT)` | what a reset would change and add |
| `POST /projects/{id}/control-rules/reset` | `project_ctx(EDIT)` | the reset (reason, row versions) |

The design's API table names `GET/PUT /control-rules/defaults`; this slice builds GET + PATCH per analysis, matching
the project rule route (`PATCH /projects/{id}/control-rules/{code}`); the table is updated. Control is always on, so
the writes name no component and their paths match no `ROUTE_COMPONENTS` fragment (as Control-A).

**Screens.** Two tabs on Reports ("Where change lands", "Master data"), from `reportKit.jsx` / `kit.jsx`. A "Company
control defaults" tab on the Admin page (platform admins only, as the page already is), one card per rule with an edit
dialog asking for the reason. On the control panel, a "Reset to FTC defaults" button for editors (`useCanEdit`) opening
the preview, a reason field and an amber confirm (a regret-able action, playbook §6). Strings in `en.reports.json`,
`en.control.json`, `en.admin.json` (or the file the Admin page uses); addresses in `app/links.js`; one API function per
route in `api/scope.js`. No mockup exists for these (checked `docs/mockups/`): kit only, nothing faked. Names and
notes render as text (VB law 9).

## 6. Seeding and deploy
`seeds.seed_control_rules` adds the new house rows (never overwrites) and, with `--actor-email`, copies them into
every live project that lacks them, **switched off** (CB-5); new projects get them on. CLAUDE.md gets one deploy line
for Control-C: run the seed with `--actor-email` straight after deploy — until it runs, `create_project` returns 409
(Control-B round 2 N4). C3 also needs migration 0082 before the seed (the seed would otherwise fail on
`ck_ctl_analysis`).

## 7. C3 — migration 0082
`0082_control_fr_unlinked`: drop and re-create `ck_ctl_analysis` with `fr_unlinked` added; downgrade restores the
list, and stops with a message while any row names `fr_unlinked` (the old constraint would refuse it; a downgrade
never deletes rules). Not destructive, no table, no shadow (`control_rule` is not frozen), no hash-spec bump.
`models/control.REGISTRY` and the §7.13 registry gain the code in the same change. **C3 starts only when Ren confirms
the migration slot is free**, on top of the latest main.

## 8. Risk and tests — Grade 2
**Grade 2:** a wrong figure or verdict reaches a steering meeting; a wrong company default reaches the next project;
both correctable once noticed. The riskiest concern is the **platform-admin gate on the company defaults** — a client
editor changing FTC's standard. That is an access check on a non-money, non-destructive write, so Grade 2 with the
gate tested directly from three refused identities; no mutation harness (that is its own approved task).
1. Change intensity: a changed step counted once with two solutions; a rejected solution and a retired step, BR or
   solution are not counted; the 50 / 70 boundaries (equal is GREEN); a tie between two areas; one area → NOT
   MEASURED; no change → NOT MEASURED; SOLUTION off → NOT MEASURED; an area keyed by id survives an L1 inserted above.
2. Master data: 2 areas not a candidate, 3 is; an owner note of spaces is no owner; a retired BR or entity drops out;
   the 0 / 5 boundaries; nothing mapped → NOT MEASURED.
3. Company defaults: staff, project ADMIN and editor refused (403); the routes join `test_project_admin.py`'s
   platform-only list; reason required (422); stale version 409; an owner can never be set; the audit row has no
   project and the text only as changed; an edit leaves every existing project's rules unchanged and a project created
   after gets the new value (acceptance 79).
4. Reset: viewer 403; owner and on/off kept; a missing rule added off; an unchanged rule not bumped; a rule the
   preview did not list edited since → 409; a house row edited since → 409; nothing written on 409; empty reason 422;
   an empty reset writes no audit; one `CONTROL_RULES_RESET` naming changed and added; the panel names the reset.
5. `fr_unlinked` (C3): matches the register's `unlinked=true` count; FUNCTION_REQUIREMENT off and no FRs → NOT
   MEASURED; 0 / 5 boundaries; migration 0082 up and down.
6. Seed and panel: the new rules backfill off and are measured ("not yet agreed"); a new project gets them on;
   acceptance 74 (every registry code in `HOUSE_RULES` returns a headline) extended.
7. Existing guards: `test_route_guards` (49 / 49b), `test_no_get_route_leaks_a_restricted_project` (covers the new
   GETs), `test_project_admin.py`.
8. Browser (ui-verifier): both tabs on the demo project; the new panel rows link to their tabs (fr_unlinked to the FR
   register); the company-defaults tab edits a value with a reason; the reset preview, confirm and result.
**Left uncovered on purpose:** weighting by solution category (CC-1 keeps every change equal); speed at the design
bound beyond one timed run on the 2,000-BR fixture.

## 9. Not in this slice
Rules for `application_gap`, `value_ranking`, `issue_dashboard`, `phase_plan`, `consistency_check` (CC-5);
`benefit_gap` and `risk_register` (Phase 2 modules); switching a company default off; adding or retiring a company
default from the screen (only the seed adds); verdict history; the M-tiles; a "confirmed new data" marker; the ERD as
SVG (CC-7: PNG only).

## 10. Build plan
- **C1 (~0.7 day):** the two analyses, two routes, two tabs, two house rules, panel rows, seed backfill. Tests 1, 2, 6,
  7.
- **C2 (~0.8 day):** company defaults (routes, Admin tab) and reset (preview, POST, panel button). Tests 3, 4, 7.
- **C3 (~0.3 day):** migration 0082, `fr_unlinked` rule and panel row. Tests 5, 6. **Waits for the migration slot.**
Each: test-runner fast run → sara → commit. Then merge latest main → full suite on the merged commit (named) →
ui-verifier → ask Ben to push. Ports 8122 / 5192 (8102 / 5182 are held by another task); databases `vb_s2_uat_db`,
`vb_s2_test_db` and its four worker copies, dropped at the end (CC-7).

## 11. Design review round 1 (design-auditor, 2026-10-30) — dispositions
6 findings (0 HIGH, 3 MEDIUM, 3 LOW), none structural — all fixed in this draft:
- **R1-P1 MED** the reset's version check covered only the rules the preview listed, so a rule edited meanwhile (or a
  house row) could be overwritten unseen — **fixed** (§4: the stamp covers every project rule and house row; 409).
- **R1-P2 MED** a rule left on after a reset is judged against FTC's numbers and looks agreed — **fixed** (§4: the
  panel names the reset until a person edits the rule). Whether such a rule should count as agreed is put to Ben as a
  WHENEVER question; Ben's CC-4 (keep on / off) stands.
- **R1-S1 MED** house text is copied to every future client and could name a person — **fixed** (§3: the dialog
  warns "name roles, never people or clients"). Taking escalation text off the house tier altogether would make every
  reset blank the project's escalation path, against CC-4 — so not done.
- **R1-P3 LOW** reset must lock what it checks — **fixed** (§4). **R1-P4 LOW** FTC's review had nothing to read —
  **fixed** (§3 history list; retention stated). **R1-D1 LOW** the house PATCH could switch a rule off — **fixed**
  (§3 own body, extra fields refused).
- Re-run: an empty reset writes nothing (§4). Its question 3 (does "TBD" count as an owner) → assumption C1, to Ben.
  Its question 4 (BR on an as-is step) — yes it can; `fr_unlinked` follows the register (§2.3).
- COULD NOT REVIEW: `ControlRuleIn` already forbids extra fields; `audit_event.project_id` is nullable (slice 17 writes
  project-less events); the guard internals are covered by `test_route_guards` and `test_project_admin.py`.

## 12. Working assumptions (ASSUMPTION — confirm or correct)
- C1 Any owner note but blank counts as an owner ("TBD" included); the table shows the text.
- C2 A changed step is counted once in the headline however many solutions or categories it carries.

## 13. Design review round 2 (design-auditor, 2026-10-30) — the final round
Round 1: 6 CLOSED but R1-S1, which is PARTLY. 2 new (both LOW), none structural — settled in the code:
- **R1-S1 (partly)** the warning relies on the admin; history shows text only as "changed" — **accepted (LOW)**: only
  platform admins (FTC staff) write it; the company-defaults card shows each default's current text in full, so the
  close-out review reads it.
- **N1 LOW** a reset racing the seed's insert of the same rule hits the unique index → a bare 500 — **fixed in the
  build:** that violation returns 409 "the rules changed since the preview; open it again".
- **N2 LOW** where the reset marker comes from — **fixed** (§4: from the audit trail).
- Two questions carried to Ben (WHENEVER): does a rule left on after a reset count as agreed; assumption C1.
