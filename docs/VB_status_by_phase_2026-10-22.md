# Value Bridge — status by phase, slice and function (2026-10-22)

**For:** Ben · **Counted from:** `main` at `5f3768e`, branch `ren/2026-10-21_value-bridge-slice16-17` at `d36b56c` (slice 16, not merged), `docs/` specs and design history, `backend/tests`, and Lilly's session records. Days are the 2026-10-20 plan (`docs/VB_remaining_work.md`). Function numbers 1–150 are `docs/VB_スペック一覧.md`; 151–167 are functions added since (access slices A and B, the Issue module, waves, slices 16 and 17). Not estimated: where nothing is recorded the cell says **unknown**.

**Legend**

- **Spec** — none: only the one-line entry in the signed-off design, slice spec owed · drafted: written, not approved · approved: Ben approved it (or it was built from the signed-off design and his rulings).
- **Design** — none: no slice design yet · drafted: schema written, not reviewed · reviewed: a design review is recorded for the slice · unknown: built, but no review is recorded.
- **Build** — not started · partial: some of it works · built: complete on a branch, not merged · merged: on main.
- **Test** (highest level reached) — none · unit: tests exist · full suite: covered by a recorded full test run · browser-checked: also seen working in a browser (ui-verifier or a recorded scripted check) · unknown.

## Summary

| Phase | Functions | Days left (10-20 plan) | Spec | Design | Build | Test |
|---|---:|---:|---|---|---|---|
| Built before the phase plan (on main) | 92 | — | approved 92 | reviewed 84 · unknown 8 | partial 1 · merged 91 | full suite 6 · browser-checked 86 |
| Phase 1 — Finish the scope core | 34 | 11.5 | none 19 · approved 15 | none 19 · reviewed 14 · unknown 1 | not started 19 · partial 8 · merged 7 | none 19 · browser-checked 14 · unknown 1 |
| Phase 2 — Delivery control modules | 22 | 16 | none 17 · approved 5 | none 17 · reviewed 5 | not started 17 · merged 5 | none 17 · browser-checked 5 |
| Phase 3 — Ready for the first client | 14 | 15 | none 2 · approved 12 | none 2 · reviewed 12 | not started 8 · partial 1 · built 5 | none 8 · full suite 5 · browser-checked 1 |
| Phase 4 — After first client use | 4 | 9 | none 3 · approved 1 | none 3 · unknown 1 | not started 3 · partial 1 | none 3 · unknown 1 |
| Unscheduled | 1 | — | none 1 | none 1 | not started 1 | none 1 |
| **All** | **167** | **51.5** | none 42 · approved 125 | none 42 · reviewed 115 · unknown 10 | not started 48 · partial 11 · built 5 · merged 103 | none 48 · full suite 11 · browser-checked 106 · unknown 2 |

Two slices in the plan's days are already spent: slice 14's browser check (0.5) and slice 15 (2.5) — both merged and browser-checked since the plan was written, so **39.5 days remain to first client use, not 42.5**.

## Built before the phase plan (on main)

### Slice 1 — Function chart, requirements, data, foundation

*Evidence:* Signed-off design 09-28 (two review rounds) + slice 1 schema review 09-29; merged 52455cd; 115 tests on main; 12-step browser pass

*Count:* Spec: approved 22 / Design: reviewed 22 / Build: merged 22 / Test: browser-checked 22

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 1 | Add a business function | `create_bfc_node` | approved | reviewed | merged | browser-checked |  |
| 2 | Number the chart (01.02.03) | `generate_bfc_code` | approved | reviewed | merged | browser-checked |  |
| 3 | Reorder functions | `reorder_bfc_node` | approved | reviewed | merged | browser-checked |  |
| 4 | Mark / unmark a process | `mark_process` | approved | reviewed | merged | browser-checked |  |
| 5 | Describe a process | `describe_process` | approved | reviewed | merged | browser-checked |  |
| 10 | Link input / output data | `link_bfc_data_entity` | approved | reviewed | merged | browser-checked |  |
| 11 | Add an outside party | `create_external_entity` | approved | reviewed | merged | browser-checked |  |
| 12 | Link data exchanged with an outside party | `link_bfc_external_flow` | approved | reviewed | merged | browser-checked |  |
| 13 | As-is RACI on a process | `link_bfc_role` | approved | reviewed | merged | browser-checked |  |
| 16 | Organisation chart (units, roles) | `maintain_org_chart` | approved | reviewed | merged | browser-checked |  |
| 37 | Add a data entity | `create_data_entity` | approved | reviewed | merged | browser-checked |  |
| 38 | Manage data fields | `manage_data_fields` | approved | reviewed | merged | browser-checked |  |
| 42 | Business requirement created with a process | `create_br` | approved | reviewed | merged | browser-checked |  |
| 43 | Edit a business requirement | `update_br` | approved | reviewed | merged | browser-checked |  |
| 44 | Data a requirement uses (CRUD) | `link_br_data_entity` | approved | reviewed | merged | browser-checked |  |
| 85 | Sign in | `login` | approved | reviewed | merged | browser-checked |  |
| 89 | Add a client | `create_client` | approved | reviewed | merged | browser-checked |  |
| 90 | Create a project | `create_project` | approved | reviewed | merged | browser-checked |  |
| 98 | Retire a record (soft delete) | `soft_delete_record` | approved | reviewed | merged | browser-checked |  |
| 99 | Restore a retired record | `restore_record` | approved | reviewed | merged | browser-checked |  |
| 100 | Consistency check | `consistency_check` | approved | reviewed | merged | browser-checked |  |
| 101 | Resolve code lists (company + project) | `resolve_codes` | approved | reviewed | merged | browser-checked |  |

### Slice 3 — DFD, ERD, Mermaid export

*Evidence:* slice3_spec.md, review rounds 1–2; merged 6bed5d2/cc248d9/e56839b; 196 tests on main; ui-verifier per piece

*Count:* Spec: approved 3 / Design: reviewed 3 / Build: merged 3 / Test: browser-checked 3

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 23 | DFD to Mermaid text | `export_dfd` | approved | reviewed | merged | browser-checked |  |
| 32 | Save diagram positions | `save_diagram_layout` | approved | reviewed | merged | browser-checked |  |
| 40 | Generate the ERD | `generate_erd` | approved | reviewed | merged | browser-checked |  |

### Step retire

*Evidence:* step_retire_spec.md, two review rounds; merged 955a0b3; 217 tests on main; ui-verifier 5/5

*Count:* Spec: approved 1 / Design: reviewed 1 / Build: merged 1 / Test: browser-checked 1

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 15 | Retire / restore a process with what hangs off it | `retire_step_with_dependents` | approved | reviewed | merged | browser-checked |  |

### Slice 4a — Import pipeline (data entities and fields)

*Evidence:* slice4a_spec.md + schema review 10-01; merged 7fcd815/8c08078/1c21198; 343 tests; browser 9/9 and 8/8 for 4a-1/4a-2, none recorded for the purge (4a-3)

*Count:* Spec: approved 1 / Design: reviewed 1 / Build: merged 1 / Test: full suite 1

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 79 | 90-day purge of imported rows | `purge_import_rows` | approved | reviewed | merged | full suite | Built; no screen, so no browser check; the scheduled run on Azure comes with the Azure task |

### Slice 5 — Solutions

*Evidence:* slice5_spec.md, design review round 1; merged 364eb3f; 365 tests; ui-verifier 11/11

*Count:* Spec: approved 2 / Design: reviewed 2 / Build: merged 2 / Test: browser-checked 2

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 47 | Link requirement to solution | `link_br_solution` | approved | reviewed | merged | browser-checked |  |
| 57 | Add a solution | `create_solution` | approved | reviewed | merged | browser-checked |  |

### Slice 6a — Function requirements

*Evidence:* slice6a_spec.md, review round 1 (1 high fixed); merged a8389d4; 383 tests; browser 12/12

*Count:* Spec: approved 2 / Design: reviewed 2 / Build: merged 2 / Test: browser-checked 2

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 58 | Add a function requirement | `create_function_requirement` | approved | reviewed | merged | browser-checked |  |
| 59 | Solution that carries an FR's effort | `set_fr_solution` | approved | reviewed | merged | browser-checked |  |

### Slice 6b-1 — Applications

*Evidence:* slice6b1_spec.md, review round 1; merged fc91836; 402 tests; browser 12/12

*Count:* Spec: approved 3 / Design: reviewed 3 / Build: merged 3 / Test: browser-checked 3

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 14 | As-is systems behind a process | `link_bfc_application` | approved | reviewed | merged | browser-checked |  |
| 62 | System catalogue | `create_application` | approved | reviewed | merged | browser-checked |  |
| 63 | System that delivers a solution | `link_application_solution` | approved | reviewed | merged | browser-checked |  |

### Slice 6b-2 — Interfaces

*Evidence:* slice6b2_spec.md, review round 1 (1 high fixed); merged 1107839; 425 tests; browser 12/12

*Count:* Spec: approved 1 / Design: reviewed 1 / Build: merged 1 / Test: browser-checked 1

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 60 | Interface detail | `describe_interface` | approved | reviewed | merged | browser-checked |  |

### Slice 6c — Rate card and effort

*Evidence:* slice6c_spec.md, review round 1; merged 7c01033; 444 tests + deliberate-break check; browser 10/10

*Count:* Spec: approved 4 / Design: reviewed 4 / Build: merged 4 / Test: browser-checked 4

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 102 | Rate card | `read_rate_card` | approved | reviewed | merged | browser-checked |  |
| 103 | Adjust the rate card | `maintain_rate_card` | approved | reviewed | merged | browser-checked |  |
| 104 | Size an FR (effort days) | `rate_function_requirement` | approved | reviewed | merged | browser-checked |  |
| 105 | Effort summary | `effort_summary` | approved | reviewed | merged | browser-checked |  |

### Slice 7a — Project components, data model depth

*Evidence:* slice7_schema.md, review round 1 (13 findings, 7a–7c); merged b4be6bd; 460 tests; browser 8/8

*Count:* Spec: approved 3 / Design: reviewed 3 / Build: merged 3 / Test: browser-checked 3

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 39 | Data model warnings | `validate_entity_model` | approved | reviewed | merged | browser-checked |  |
| 91 | Project components on / off | `set_components` | approved | reviewed | merged | browser-checked |  |
| 92 | Data model depth | `set_data_model_depth` | approved | reviewed | merged | browser-checked |  |

### Slice 7b — Access: admin / user / viewer, restricted projects

*Evidence:* slice7_schema.md; merged f1dd75a; 465 tests; browser 8/9 then 6/6 recheck

*Count:* Spec: approved 8 / Design: reviewed 8 / Build: merged 8 / Test: browser-checked 8

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 86 | Add a user | `create_user` | approved | reviewed | merged | browser-checked |  |
| 87 | Change user type / platform admin | `change_user_kind · set_platform_admin` | approved | reviewed | merged | browser-checked | 87: slice 17 removes the direct grant (approval needed) |
| 88 | Deactivate a user | `deactivate_user` | approved | reviewed | merged | browser-checked |  |
| 93 | Restrict a project | `set_restriction` | approved | reviewed | merged | browser-checked |  |
| 94 | Project members | `manage_members` | approved | reviewed | merged | browser-checked |  |
| 95 | Projects I can see | `list_visible_projects` | approved | reviewed | merged | browser-checked |  |
| 96 | Who can open this project | `list_effective_access` | approved | reviewed | merged | browser-checked |  |
| 97 | Project access guard (404 → 403 → 409) | `enforce_project_scope` | approved | reviewed | merged | browser-checked |  |

### Slice 7c — The DFD rework (performers, triggers, as-is set)

*Evidence:* slice7_schema.md; merged 4f3ca3b; 462 tests; browser 7/10, 4 fixed; drag seen in slice 9

*Count:* Spec: approved 6 / Design: reviewed 6 / Build: merged 6 / Test: browser-checked 6

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 17 | Copy a chart (as-is ⇄ to-be) | `copy_bfc_set` | approved | reviewed | merged | browser-checked |  |
| 18 | Who performs a process | `set_performer` | approved | reviewed | merged | browser-checked |  |
| 19 | Triggers list | `maintain_process_trigger` | approved | reviewed | merged | browser-checked |  |
| 20 | Trigger starts a process | `link_process_trigger` | approved | reviewed | merged | browser-checked |  |
| 21 | Generate the DFD | `generate_dfd` | approved | reviewed | merged | browser-checked |  |
| 24 | Process completeness check | `process_completeness` | approved | reviewed | merged | browser-checked |  |

### Slice 8 — Baseline freeze, approval, diff

*Evidence:* slice8_schema.md, design-auditor 7 findings fixed; merged 01c8d1b; 499/499 tests; browser 9/10 + rechecks

*Count:* Spec: approved 5 / Design: reviewed 5 / Build: merged 5 / Test: browser-checked 5

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 80 | Freeze preview | `preview_freeze` | approved | reviewed | merged | browser-checked |  |
| 81 | Freeze a baseline | `freeze_baseline` | approved | reviewed | merged | browser-checked |  |
| 82 | Record client approval | `approve_baseline` | approved | reviewed | merged | browser-checked |  |
| 83 | Compare versions | `diff_baseline` | approved | reviewed | merged | browser-checked |  |
| 84 | Compare versions in person-days | `priced_diff` | approved | reviewed | merged | browser-checked |  |

### Slice 10a — BR inside the chart; DFD screen

*Evidence:* D-53/D-54 ruled by Ben; no slice review recorded; merged f7bc276; 18 browser checks pass; no full run recorded for the slice itself

*Count:* Spec: approved 1 / Design: unknown 1 / Build: merged 1 / Test: browser-checked 1

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 22 | DFD list | `dfd_index` | approved | unknown | merged | browser-checked |  |

### Slice 10b — BR ↔ FR direct

*Evidence:* slice10b_spec.md, review round 1 (1 high); merged b7eb096; 530 tests; ui-verifier blocked twice — Ben tested the link himself

*Count:* Spec: approved 3 / Design: reviewed 3 / Build: merged 3 / Test: full suite 3

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 48 | Link requirement to FR directly | `link_br_fr` | approved | reviewed | merged | full suite |  |
| 49 | Pick the FR's solution on the requirement | `set_fr_solution_from_br` | approved | reviewed | merged | full suite |  |
| 50 | Create an FR from a requirement | `create_fr_from_br` | approved | reviewed | merged | full suite |  |

### Slice 10c — Organisation and Systems, BR attributes

*Evidence:* slice10c_spec.md, review round 1 (1 high); merged bf89f32; 553 tests; browser 7/7

*Count:* Spec: approved 1 / Design: reviewed 1 / Build: merged 1 / Test: browser-checked 1

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 45 | Fields a requirement's data holds | `read_br_attributes` | approved | reviewed | merged | browser-checked |  |

### Slice 10d — Ranked process panel, one RACI

*Evidence:* slice10d_spec.md, 11 findings (3 high) built in; merged bbd0674; 541 tests; ui-verifier 12 + recheck

*Count:* Spec: approved 1 / Design: reviewed 1 / Build: merged 1 / Test: browser-checked 1

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 46 | To-be RACI on the requirement | `link_br_role` | approved | reviewed | merged | browser-checked |  |

### Slice 11 — Structured BR, attributes used, system flows

*Evidence:* slice11_schema.md, rulings S11-1…S11-7; no design review recorded; merged 6c276c9; 663 tests on 772b93d; browser 10/10, 6/6, 6/6

*Count:* Spec: approved 5 / Design: unknown 5 / Build: merged 5 / Test: browser-checked 5

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 51 | Requirement lines | `maintain_br_lines` | approved | unknown | merged | browser-checked |  |
| 52 | Fields a requirement uses (C/R/U) | `tick_br_attributes` | approved | unknown | merged | browser-checked |  |
| 53 | System-to-system flows | `state_br_system_flow` | approved | unknown | merged | browser-checked |  |
| 54 | Is each flow covered by an interface | `flow_coverage` | approved | unknown | merged | browser-checked |  |
| 55 | Create interface FRs from flows | `create_interface_fr_from_flows` | approved | unknown | merged | browser-checked |  |

### Slice 12 — Scope dashboard KPIs, project-management card

*Evidence:* slice12_kpis.md (S12-1); merged 7087ad4; no session record of its own — tests only through later full runs on main (821 at 5f3768e); browser check unknown

*Count:* Spec: approved 2 / Design: unknown 2 / Build: partial 1 · merged 1 / Test: full suite 2

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 141 | Scope dashboard (S1–S11) | `scope_dashboard` | approved | unknown | merged | full suite |  |
| 142 | Project-management card | `pm_dashboard` | approved | unknown | partial | full suite | M1 baselines and M3 issues built; M2 changes, M4 risks, M5 WBS come with their slices |

### Slice 13a — Solutions/FR split, readiness light

*Evidence:* slice13_spec.md (design review DR13); merged bd93239; 549 tests; ui-verifier run

*Count:* Spec: approved 1 / Design: reviewed 1 / Build: merged 1 / Test: browser-checked 1

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 25 | Readiness light per process | `dfd_readiness` | approved | reviewed | merged | browser-checked |  |

### Slice 13b — DFD rule per chart

*Evidence:* slice13_spec.md; merged 8997dd5; 614 tests on main; browser check was Lilly's own scripted run, not ui-verifier

*Count:* Spec: approved 3 / Design: reviewed 3 / Build: merged 3 / Test: browser-checked 3

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 26 | DFD rule | `get_dfd_rule` | approved | reviewed | merged | browser-checked |  |
| 27 | Preview a DFD rule change | `preview_dfd_rule` | approved | reviewed | merged | browser-checked |  |
| 28 | Set the DFD rule | `set_dfd_rule` | approved | reviewed | merged | browser-checked |  |

### Slice 13c — Process volume and FTE

*Evidence:* slice13_spec.md; merged b4b8b6f; 614 tests at f174b4d; scripted browser 10/11 (11th the deliberate refusal)

*Count:* Spec: approved 4 / Design: reviewed 4 / Build: merged 4 / Test: browser-checked 4

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 6 | Process volume | `set_process_volume` | approved | reviewed | merged | browser-checked |  |
| 7 | Hours and FTE worked out | `derive_volume` | approved | reviewed | merged | browser-checked |  |
| 8 | FTE basis | `set_fte_basis` | approved | reviewed | merged | browser-checked |  |
| 9 | Volume: as-is beside to-be | `volume_summary` | approved | reviewed | merged | browser-checked |  |

### Slice 13d — Draw connections on the DFD

*Evidence:* slice13_spec.md; merged 1a4e537; 563 tests; ui-verifier 6/7 + keyboard move

*Count:* Spec: approved 3 / Design: reviewed 3 / Build: merged 3 / Test: browser-checked 3

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 29 | Draw a connection on the DFD | `draw_dfd_connection` | approved | reviewed | merged | browser-checked |  |
| 30 | Draw a hand-off between processes | `draw_hand_off` | approved | reviewed | merged | browser-checked |  |
| 31 | Remove a flow on the DFD | `remove_dfd_flow` | approved | reviewed | merged | browser-checked |  |

### Slice 1g — Code list maintenance

*Evidence:* slice1g_spec.md (G-1…G-6, design review); merged c930947; 746 tests on 1bb1e1a; browser 6/6

*Count:* Spec: approved 2 / Design: reviewed 2 / Build: merged 2 / Test: browser-checked 2

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 64 | FR types per project | `maintain_fr_types` | approved | reviewed | merged | browser-checked |  |
| 144 | Code list maintenance | `maintain_code_master` | approved | reviewed | merged | browser-checked |  |

### Access slice A — Project admins

*Evidence:* slice_access_a_plan.md, access_v2_decision.md (design-auditor fixes §8); merged c930947; 700 → 746 tests; browser 5/7, both fails script errors

*Count:* Spec: approved 2 / Design: reviewed 2 / Build: merged 2 / Test: browser-checked 2

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 151 | Project admins manage members (added) | `appoint_project_admin` | approved | reviewed | merged | browser-checked |  |
| 152 | User-type change shows roles that come back (added) | `user_type_change_preview` | approved | reviewed | merged | browser-checked |  |

### Access slice B — Program members

*Evidence:* slice_access_b_plan.md; merged c930947; 746 tests on 3163a3c; browser 6/6

*Count:* Spec: approved 3 / Design: reviewed 3 / Build: merged 3 / Test: browser-checked 3

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 135 | Move a project to another program | `move_project_program` | approved | reviewed | merged | browser-checked |  |
| 153 | Program members: admin / editor / viewer (added) | `manage_program_members` | approved | reviewed | merged | browser-checked |  |
| 154 | Access list shows where each level comes from (added) | `access_source` | approved | reviewed | merged | browser-checked |  |

## Phase 1 — Finish the scope core

### Slice 14 — Issue module · **0.5 days**

*Evidence:* slice14_issue_spec.md (I-1…I-16), design review rounds 1–2; merged 8387fcb; 791 tests incl. slow; browser 9/10 + recheck on 10-20 — the 0.5 day in the plan is now spent

*Count:* Spec: approved 7 / Design: reviewed 7 / Build: merged 7 / Test: browser-checked 7

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 69 | Stakeholders | `create_stakeholder` | approved | reviewed | merged | browser-checked |  |
| 70 | Raise an issue | `raise_issue` | approved | reviewed | merged | browser-checked |  |
| 71 | Link issue to requirements | `link_issue_br` | approved | reviewed | merged | browser-checked |  |
| 72 | Resolve / reopen an issue | `resolve_issue` | approved | reviewed | merged | browser-checked |  |
| 73 | Issue dashboard | `issue_dashboard` | approved | reviewed | merged | browser-checked |  |
| 155 | Edit / retire an issue (added) | `edit_issue · retire_issue` | approved | reviewed | merged | browser-checked |  |
| 156 | Issues frozen into baselines (added) | `freeze_issues` | approved | reviewed | merged | browser-checked |  |

### Control rules + control panel · **4 days**

*Evidence:* Spec owed

*Count:* Spec: none 10 / Design: none 10 / Build: not started 10 / Test: none 10

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 124 | Control rules | `maintain_control_rule` | none | none | not started | none |  |
| 125 | Control panel | `control_panel` | none | none | not started | none |  |
| 126 | Requirement volatility | `requirement_volatility` | none | none | not started | none |  |
| 127 | Where change lands | `process_change_intensity` | none | none | not started | none |  |
| 128 | Organisation impact | `org_impact_heatmap` | none | none | not started | none |  |
| 129 | Stakeholder engagement | `stakeholder_engagement` | none | none | not started | none |  |
| 130 | Interface load | `interface_load` | none | none | not started | none |  |
| 131 | Data migration map | `data_migration_map` | none | none | not started | none |  |
| 132 | Master data candidates | `master_data_candidates` | none | none | not started | none |  |
| 133 | FRs with no requirement (threshold) | `fr_unlinked` | none | none | not started | none | Count already on the dashboard; threshold check not built |

### Slice 1e — Imports (BR, FR, Issue Excel; process-flow file) · **5 days**

*Evidence:* Spec owed

*Count:* Spec: none 4 · approved 5 / Design: none 4 · reviewed 5 / Build: not started 4 · partial 5 / Test: none 4 · browser-checked 5

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 33 | Process-flow JSON schema and prompt pack | `download_flow_schema` | none | none | not started | none |  |
| 34 | Export process-flow JSON | `export_process_flow_json` | none | none | not started | none |  |
| 35 | Check a process-flow JSON import | `validate_process_flow_json` | none | none | not started | none |  |
| 36 | Commit a process-flow JSON import | `commit_process_flow_json` | none | none | not started | none |  |
| 74 | Excel template | `download_template` | approved | reviewed | partial | browser-checked | Built for data entities and fields (slice 4a, browser-checked); BR, FR, Issue here; WBS with the WBS slice |
| 75 | Excel export | `export_entity` | approved | reviewed | partial | browser-checked | Built for data entities and fields (slice 4a, browser-checked); BR, FR, Issue here; WBS with the WBS slice |
| 76 | Check an import | `validate_import` | approved | reviewed | partial | browser-checked | Built for data entities and fields (slice 4a, browser-checked); BR, FR, Issue here; WBS with the WBS slice |
| 77 | Preview an import | `preview_import` | approved | reviewed | partial | browser-checked | Built for data entities and fields (slice 4a, browser-checked); BR, FR, Issue here; WBS with the WBS slice |
| 78 | Commit an import | `commit_import` | approved | reviewed | partial | browser-checked | Built for data entities and fields (slice 4a, browser-checked); BR, FR, Issue here; WBS with the WBS slice |

### Slice 1f — Reports and PDF · **2 days**

*Evidence:* Spec owed

*Count:* Spec: none 5 · approved 3 / Design: none 5 · reviewed 2 · unknown 1 / Build: not started 5 · partial 3 / Test: none 5 · browser-checked 2 · unknown 1

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 41 | ERD export | `export_erd` | approved | reviewed | partial | browser-checked | Mermaid built (slice 3); PNG / SVG owed |
| 56 | Requirements coverage report | `br_coverage_report` | none | none | not started | none |  |
| 61 | Interface list | `interface_list` | approved | reviewed | partial | browser-checked | Screen built (6b-2); Excel export owed |
| 66 | Solution matrix | `solution_matrix` | none | none | not started | none |  |
| 67 | System gap report | `application_gap_report` | none | none | not started | none |  |
| 68 | Traceability matrix | `fr_traceability_matrix` | none | none | not started | none |  |
| 134 | Add / edit a program | `create_program · update_program` | approved | unknown | partial | unknown | Add built; edit screen owed |
| 143 | Client reports to PDF | `export_report_pdf` | none | none | not started | none |  |

## Phase 2 — Delivery control modules

### Slice 15 — Waves (phasing) · **2.5 days**

*Evidence:* slice15_phasing_spec.md (W-1…W-9), design review rounds 1–2; merged 5f3768e; 821 tests; browser 10/10 — the 2.5 days in the plan are now spent

*Count:* Spec: approved 5 / Design: reviewed 5 / Build: merged 5 / Test: browser-checked 5

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 120 | Waves | `create_phase` | approved | reviewed | merged | browser-checked |  |
| 121 | Split a solution across waves | `assign_solution_phase` | approved | reviewed | merged | browser-checked |  |
| 122 | Solution dependencies | `link_solution_dependency` | approved | reviewed | merged | browser-checked |  |
| 123 | Wave plan | `phase_plan_report` | approved | reviewed | merged | browser-checked |  |
| 157 | Waves frozen into baselines (added) | `freeze_waves` | approved | reviewed | merged | browser-checked |  |

### Benefits · **2.5 days**

*Evidence:* Spec owed

*Count:* Spec: none 4 / Design: none 4 / Build: not started 4 / Test: none 4

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 106 | Add a benefit | `create_benefit` | none | none | not started | none |  |
| 107 | Link benefit to solution | `link_benefit_solution` | none | none | not started | none |  |
| 108 | Value-for-effort ranking | `value_ranking` | none | none | not started | none |  |
| 109 | No-benefit check | `benefit_gap_report` | none | none | not started | none |  |

### Change requests · **4 days**

*Evidence:* Spec owed

*Count:* Spec: none 4 / Design: none 4 / Build: not started 4 / Test: none 4

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 114 | Raise a change request | `raise_change_request` | none | none | not started | none |  |
| 115 | Change impact trace | `analyse_cr_impact` | none | none | not started | none |  |
| 116 | Price a change | `price_cr` | none | none | not started | none |  |
| 117 | Decide a change | `decide_cr` | none | none | not started | none |  |

### Risks · **2 days**

*Evidence:* Spec owed

*Count:* Spec: none 4 / Design: none 4 / Build: not started 4 / Test: none 4

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 110 | Add a risk | `raise_risk` | none | none | not started | none |  |
| 111 | Score a risk | `score_risk` | none | none | not started | none |  |
| 112 | Risk becomes an issue | `promote_risk_to_issue` | none | none | not started | none |  |
| 113 | Risk register | `risk_register` | none | none | not started | none |  |

### Decisions · **1.5 days**

*Evidence:* Spec owed

*Count:* Spec: none 2 / Design: none 2 / Build: not started 2 / Test: none 2

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 118 | Record a decision | `record_decision` | none | none | not started | none |  |
| 119 | Decision log | `decision_log` | none | none | not started | none |  |

### WBS import + progress · **3.5 days**

*Evidence:* Spec owed

*Count:* Spec: none 3 / Design: none 3 / Build: not started 3 / Test: none 3

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 138 | Link WBS lines | `link_wbs_item` | none | none | not started | none |  |
| 139 | Record progress | `record_wbs_progress` | none | none | not started | none |  |
| 140 | Progress report | `wbs_progress_report` | none | none | not started | none |  |

## Phase 3 — Ready for the first client

### Slice 16 — Archive files + project removal · **3.5 days**

*Evidence:* slice16_archive_purge_spec.md (AR-1…AR-13), review rounds 1–2 + one on the 10-18 changes; branch d36b56c, not merged; 904 tests on a596517; Removals tab ui-verifier 8/8

*Count:* Spec: approved 8 / Design: reviewed 8 / Build: not started 2 · partial 1 · built 5 / Test: none 2 · full suite 5 · browser-checked 1

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 149 | Archive file of each frozen baseline | `export_baseline_archive` | approved | reviewed | built | full suite | Written after each freeze; files owed are listed on the Removals tab |
| 150 | Carry out an approved removal (operator) | `purge_project` | approved | reviewed | not started | none | Waits on migrations 0074 / 0075 (Ben's decision) |
| 158 | Check an archive file reads back (added) | `verify_archive_file` | approved | reviewed | built | full suite |  |
| 159 | Archive identity per database (added) | `stamp_instance` | approved | reviewed | built | full suite |  |
| 160 | Removal request · approve · cancel; project locked while open (added) | `removal_request` | approved | reviewed | built | browser-checked | Ben tried it on 2026-10-21 |
| 161 | Two-year clock and projects due for archiving (added) | `archive_due_list` | approved | reviewed | partial | full suite | Due list built; closing / reopening a project not started |
| 162 | Request deletion of an archive (added) | `delete_archive_request` | approved | reviewed | built | full suite |  |
| 163 | Weekly archive check (added) | `weekly_archive_check` | approved | reviewed | not started | none |  |

### Slice 17 — Platform-admin grant approval · **1 days**

*Evidence:* slice17_admin_grant_spec.md + schema rev 2, AR-16…AR-23, review rounds 1–2; Ben's go 2026-10-21; build waits for Ben

*Count:* Spec: approved 4 / Design: reviewed 4 / Build: not started 4 / Test: none 4

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 164 | Ask for someone to be made platform admin (added) | `request_admin_grant` | approved | reviewed | not started | none |  |
| 165 | Approve / reject / cancel a request (added) | `decide_admin_grant` | approved | reviewed | not started | none |  |
| 166 | Admin requests list (added) | `list_admin_grants` | approved | reviewed | not started | none |  |
| 167 | Recorded grant by Fortience IS: first admins, fresh install (added) | `owner_admin_grant` | approved | reviewed | not started | none |  |

### Client read-only login + offline viewer · **3 days**

*Evidence:* Spec owed

*Count:* Spec: none 2 / Design: none 2 / Build: not started 2 / Test: none 2

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 147 | Client read-only sign-in | `client_readonly_login` | none | none | not started | none |  |
| 148 | Offline viewer file | `export_offline_viewer` | none | none | not started | none |  |

**Work in this phase that is not a function:**

| Task | Days |
|---|---:|
| Full review pass (Sara production depth; VB-005 backlog with Ben) | 2 |
| Azure (Container Apps, private PostgreSQL, Key Vault, sign-in) | 4 |
| Restore drill | 1 |
| Prompt pack sign-off | 0.5 |

## Phase 4 — After first client use

### Program roll-ups · **2 days**

*Evidence:* Spec owed

*Count:* Spec: none 1 · approved 1 / Design: none 1 · unknown 1 / Build: not started 1 · partial 1 / Test: none 1 · unknown 1

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 136 | Program dashboard | `program_dashboard` | approved | unknown | partial | unknown | Member-project list built |
| 137 | Program roll-up figures | `program_counts · interfaces · effort · control` | none | none | not started | none |  |

### Languages · **4 days**

*Evidence:* Spec owed

*Count:* Spec: none 1 / Design: none 1 / Build: not started 1 / Test: none 1

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 145 | Language switch (EN / JA / TH) | `switch_language` | none | none | not started | none |  |

### Version comparison screen · **3 days**

*Evidence:* Spec owed

*Count:* Spec: none 1 / Design: none 1 / Build: not started 1 / Test: none 1

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 146 | Version comparison screen | `version_compare_screen` | none | none | not started | none | Comparison logic built (slice 8) |

## Unscheduled

### No slice yet

*Evidence:* Designed, no date

*Count:* Spec: none 1 / Design: none 1 / Build: not started 1 / Test: none 1

| No | Function | ID | Spec | Design | Build | Test | Note |
|---:|---|---|---|---|---|---|---|
| 65 | Link an FR straight to a function | `link_fr_to_bfc_node` | none | none | not started | none |  |

## Gaps in the record

- **Slice 12** has no session record of its own: its tests run in every later full suite on main, but no browser check is recorded.
- **Slices 10a, 11, 12** have no design review recorded (Design = unknown).
- **Slices 13b, 13c**: the browser check was Lilly's own scripted run, not the ui-verifier.
- **Slice 10b**: ui-verifier was blocked twice; Ben tested the BR ↔ FR link himself before merge.
- **Slice 4a**: the 90-day purge (4a-3) has no browser check (it has no screen).
- **Slice 16** is not merged; the operator's removal run and key destruction wait on migrations 0074 / 0075.
