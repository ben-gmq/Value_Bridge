# Value Bridge — status of every function (2026-10-28)

**For:** Ben. **Source:** the 150 functions of `docs/VB_スペック一覧.md` (2026-10-16), each kept with its id and name. **Method:** each row is brought up to date to 2026-10-28 from `docs/VB_status_by_phase_2026-10-22.md`, `docs/VB_remaining_work.md`, the slice specs and the design history's slice-spec index. Each row is then checked against the code (`backend/routers`, `backend/services`, `frontend/src/features`), the test files in `backend/tests`, `BUGLOG.md` and recent commits: the slices 16 and 17 merge `5d7de4b`, the slice 1e-a merge `0c052c6` and today's 1e-b piece a1 `38953c3`. No tests were run for this table. "Tested" means a test file exercises the function, not that it passed today. *Spec status* is "Slice spec written" where a `docs/slice*` spec, schema or plan covers the function, and "Signed-off design" otherwise. Every row is in the signed-off `VB_design.md`, so none is "Not specced". "Spec owed" in Basis means the slice spec has not been written yet. The 29 rows marked **(judgement)** are inference, not direct evidence. **Counts:** Built 105 · Partly built 6 · Not built 38 · Not scheduled 1. On 2026-10-16 they were 79 · 11 · 59 · 1.

| Type | Functions | Built | Partly built | Not built | Not scheduled |
|---|---:|---:|---:|---:|---:|
| Form | 98 | 82 | 1 | 14 | 1 |
| Batch | 5 | 5 | 0 | 0 | 0 |
| Report | 35 | 10 | 4 | 21 | 0 |
| Interface | 12 | 8 | 1 | 3 | 0 |
| **All** | **150** | **105** | **6** | **38** | **1** |

## Every function

| ID | Function (JA / EN) | Type | Spec status | Build status | Test status | Basis |
|---|---|---|---|---|---|---|
| 1 `create_bfc_node` | 業務機能ノード登録 / Add a business function | Form | Slice spec written | Built | Tested (test_bfc_schema.py) | slice1_schema.md; services/bfc.py; ProcessesPage.jsx |
| 2 `generate_bfc_code` | 階層コード自動採番 / Number the chart (01.02.03) | Form | Slice spec written | Built | Tested (test_bfc_schema.py) | services/bfc.py; server-side |
| 3 `reorder_bfc_node` | 並び順変更 / Reorder functions | Form | Slice spec written | Built | Tested (test_bfc_schema.py) | services/bfc.py; browser-checked per 10-22 status |
| 4 `mark_process` | プロセス指定・解除 / Mark / unmark a process | Form | Slice spec written | Built | Tested (test_bfc_schema.py) | NodePanel.jsx; test file matched by area **(judgement)** |
| 5 `describe_process` | 処理内容記述 / Describe a process | Form | Slice spec written | Built | Tested (test_bfc_schema.py) | StepSections.jsx; test file matched by area **(judgement)** |
| 6 `set_process_volume` | 業務量登録 / Process volume | Form | Slice spec written | Built | Tested (test_process_volume.py) | slice13_spec.md; services/process_volume.py |
| 7 `derive_volume` | 年間時間・FTE算出 / Hours and FTE worked out | Form | Slice spec written | Built | Tested (test_process_volume.py) | services/process_volume.py; server-side |
| 8 `set_fte_basis` | FTE換算基準設定 / FTE basis | Form | Slice spec written | Built | Tested (test_process_volume.py) | FteBasisCard.jsx |
| 9 `volume_summary` | 業務量サマリ（As-Is／To-Be比較） / Volume: as-is beside to-be | Report | Slice spec written | Built | Tested (test_process_volume.py) | VolumePage.jsx |
| 10 `link_bfc_data_entity` | 入出力データ紐付け / Link input / output data | Form | Slice spec written | Built | Tested (test_dfd_api.py, test_bfc_schema.py) | services/step_io.py |
| 11 `create_external_entity` | 外部エンティティ登録 / Add an outside party | Form | Slice spec written | Built | Tested (test_bfc_schema.py) | services/external_entity.py; PartiesPage.jsx |
| 12 `link_bfc_external_flow` | 外部データ授受紐付け / Data exchanged with an outside party | Form | Slice spec written | Built | Tested (test_bfc_schema.py, test_dfd_drawing_13d.py) | services/step_io.py |
| 13 `link_bfc_role` | 実施役割紐付け（As-Is） / As-is RACI on a process | Form | Slice spec written | Built | Tested (test_charts_7c.py, test_bfc_schema.py) | services/raci.py; test file matched by keyword **(judgement)** |
| 14 `link_bfc_application` | 現行システム紐付け（As-Is） / As-is systems behind a process | Form | Slice spec written | Built | Tested (test_application_api.py) | slice6b1_spec.md; services/application.py |
| 15 `retire_step_with_dependents` | プロセス一括廃止・復元 / Retire / restore a process with its dependants | Form | Slice spec written | Built | Tested (test_step_retire.py) | step_retire_spec.md; RetireStepDialog.jsx |
| 16 `maintain_org_chart ※` | 組織図管理（部門・役職） / Organisation chart (units, roles) | Form | Slice spec written | Built | Tested (test_client_org.py) | slice10c_spec.md; OrganisationPage.jsx |
| 17 `copy_bfc_set` | 体系の複製（As-Is⇔To-Be） / Copy a chart as-is ⇄ to-be | Batch | Slice spec written | Built | Tested (test_charts_7c.py) | slice7_schema.md; services/bfc_set.py |
| 18 `set_performer` | 実施主体設定 / Who performs a process | Form | Slice spec written | Built | Tested (test_dfd_api.py) | PUT /bfc-nodes/{id}/performer |
| 19 `maintain_process_trigger` | トリガー管理 / Triggers list | Form | Slice spec written | Built | Tested (test_charts_7c.py, test_dfd_api.py) | services/trigger.py |
| 20 `link_process_trigger` | トリガー紐付け / Trigger starts a process | Form | Slice spec written | Built | Tested (test_dfd_api.py) | /bfc-nodes/{id}/triggers routes |
| 21 `generate_dfd` | DFD生成 / Generate the DFD | Report | Slice spec written | Built | Tested (test_dfd_api.py) | slice3_spec.md; DfdPage.jsx |
| 22 `dfd_index` | DFD一覧 / DFD list | Form | Signed-off design | Built | Tested (test_dfd_api.py) | DfdListPage.jsx; no slice-10a spec file; test matched by area **(judgement)** |
| 23 `export_dfd` | DFDエクスポート / DFD to Mermaid text | Interface | Slice spec written | Built | Tested (test_mermaid_export.py) | GET /bfc-nodes/{id}/dfd/export |
| 24 `process_completeness` | プロセス整備状況チェック / Process completeness check | Form | Slice spec written | Built | Tested (test_dfd_api.py, test_consistency.py) | GET /process-completeness; server-side |
| 25 `dfd_readiness` | 整備状況ランプ / Readiness light per process | Form | Slice spec written | Built | Tested (test_readiness_13a.py) | slice13_spec.md; DfdLight.jsx |
| 26 `get_dfd_rule` | DFDルール参照 / DFD rule | Form | Slice spec written | Built | Tested (test_dfd_rule.py) | services/dfd_rule.py; DfdRuleCard.jsx |
| 27 `preview_dfd_rule` | DFDルール変更プレビュー / Preview a DFD rule change | Form | Slice spec written | Built | Tested (test_dfd_rule.py) | services/dfd_rule.py |
| 28 `set_dfd_rule` | DFDルール設定 / Set the DFD rule | Form | Slice spec written | Built | Tested (test_dfd_rule.py) | services/dfd_rule.py |
| 29 `draw_dfd_connection` | DFD上での接続描画 / Draw a connection on the DFD | Form | Slice spec written | Built | Tested (test_dfd_drawing_13d.py) | DfdDraw.jsx |
| 30 `draw_hand_off` | プロセス間引継ぎ描画 / Draw a hand-off between processes | Form | Slice spec written | Built | Tested (test_dfd_drawing_13d.py) | DfdDraw.jsx |
| 31 `remove_dfd_flow` | DFD上の流れ削除 / Remove a flow on the DFD | Form | Slice spec written | Built | Tested (test_dfd_drawing_13d.py) | DfdDraw.jsx |
| 32 `save_diagram_layout` | 図の配置保存 / Save diagram positions | Form | Slice spec written | Built | Tested (test_diagram_api.py) | services/diagram_layout.py; canvas/useLayoutSave.js |
| 33 `download_flow_schema` | JSON仕様・プロンプト集の提供 / Process-flow schema and AI prompt pack download | Interface | Slice spec written | Built | Tested (test_flow_export.py) | commit 38953c3 (1e-b a1, today); GET /process-flow-json/schema; FlowFileDialog.jsx |
| 34 `export_process_flow_json` | 業務フローJSON出力 / Export process-flow JSON | Interface | Slice spec written | Built | Tested (test_flow_export.py) | commit 38953c3; GET /bfc-nodes/{id}/process-flow-json; re-import is rows 35–36 |
| 35 `validate_process_flow_json` | 業務フローJSON取込検証 / Check a process-flow JSON import | Interface | Slice spec written | Not built | n/a | slice1e_b_flow_import_spec.md §12, pieces a2/b; no flow target in bulk.TARGETS; only migration 0080 |
| 36 `commit_process_flow_json` | 業務フローJSON取込確定 / Commit a process-flow JSON import | Interface | Slice spec written | Not built | n/a | 1e-b a2 (merge mode) and piece b (replace mode) not built |
| 37 `create_data_entity` | データエンティティ登録 / Add a data entity | Form | Slice spec written | Built | Tested (test_bulk_import.py, test_erd_api.py) | services/data_entity.py; DataEntitiesPage.jsx; test matched by area **(judgement)** |
| 38 `manage_data_fields` | データ項目管理 / Manage data fields | Form | Slice spec written | Built | Tested (test_bulk_import_fields.py) | FieldDialog.jsx; test matched by area **(judgement)** |
| 39 `validate_entity_model` | モデル整合性検証 / Data model warnings | Form | Slice spec written | Built | Tested (test_components.py, test_consistency.py) | slice7_schema.md; server-side; test matched by area **(judgement)** |
| 40 `generate_erd` | ERD生成 / Generate the ERD | Report | Slice spec written | Built | Tested (test_erd_api.py) | ErdPage.jsx |
| 41 `export_erd` | ERDエクスポート / ERD export (Mermaid; PNG/SVG) | Interface | Slice spec written | Partly built | Partly tested (test_mermaid_export.py) | Mermaid built; no PNG/SVG export in features/data (slice 1f) |
| 42 `create_br` | 業務要件登録 / Requirement created with a process | Form | Slice spec written | Built | Tested (test_bfc_schema.py, test_scope_api.py) | services/business_requirement.py; test matched by area **(judgement)** |
| 43 `update_br` | 業務要件更新 / Edit a requirement | Form | Slice spec written | Built | Tested (test_scope_api.py, test_bulk_import_br.py) | BrEditor.jsx; test matched by area **(judgement)** |
| 44 `link_br_data_entity` | 使用データ紐付け（CRUD） / Data a requirement uses (CRUD) | Form | Slice spec written | Built | Tested (test_br_attributes.py) | CrudGrid.jsx; test matched by area **(judgement)** |
| 45 `read_br_attributes` | 使用データ項目の参照 / Fields a requirement's data holds | Form | Slice spec written | Built | Tested (test_br_attributes.py) | slice10c_spec.md |
| 46 `link_br_role` | 責任組織紐付け（RACI） / To-be RACI on the requirement | Form | Slice spec written | Built | Tested (test_charts_7c.py) | slice10d_spec.md; BrRaci.jsx; test matched by keyword **(judgement)** |
| 47 `link_br_solution` | ソリューション紐付け / Link requirement to solution | Form | Slice spec written | Built | Tested (test_solution_api.py) | slice5_spec.md; BrSolutionTags.jsx |
| 48 `link_br_fr` | 機能要件の直接紐付け / Link requirement to FR directly | Form | Slice spec written | Built | Tested (test_br_fr.py) | slice10b_spec.md; BrFrLinks.jsx |
| 49 `set_fr_solution_from_br` | BR画面での実現ソリューション指定 / Pick the FR's solution on the requirement | Form | Slice spec written | Built | Tested (test_br_fr.py) | slice10b_spec.md |
| 50 `create_fr_from_br` | BRからの機能要件作成 / Create an FR from a requirement | Form | Slice spec written | Built | Tested (test_br_fr.py) | slice10b_spec.md |
| 51 `maintain_br_lines` | 要件明細行（構造化記述） / Requirement lines | Form | Slice spec written | Built | Tested (test_br_lines.py) | slice11_schema.md; services/br_lines.py; BrLines.jsx |
| 52 `tick_br_attributes` | 使用データ項目のCRU指定 / Fields a requirement uses (C/R/U) | Form | Slice spec written | Built | Tested (test_br_attributes.py) | slice 11; merged per 10-22 status |
| 53 `state_br_system_flow` | システム間データ連携の記述 / System-to-system flows | Form | Slice spec written | Built | Tested (test_br_flows.py) | services/br_flows.py; BrFlows.jsx |
| 54 `flow_coverage` | 連携のIF充足判定 / Is each flow covered by an interface | Form | Slice spec written | Built | Tested (test_br_flows.py) | services/br_flows.py; server-side |
| 55 `create_interface_fr_from_flows` | 連携からのIF機能要件作成 / Create interface FRs from flows | Form | Slice spec written | Built | Tested (test_br_flows.py) | services/br_flows.py |
| 56 `br_coverage_report` | 要件網羅性レポート / Requirements coverage report | Report | Signed-off design | Not built | n/a | slice 1f, spec owed; CoveragePanel.jsx is the per-BR panel, not this report **(judgement)** |
| 57 `create_solution` | ソリューション登録 / Add a solution | Form | Slice spec written | Built | Tested (test_solution_api.py) | slice5_spec.md; SolutionsPage.jsx |
| 58 `create_function_requirement` | 機能要件登録 / Add a function requirement | Form | Slice spec written | Built | Tested (test_function_requirement_api.py) | slice6a_spec.md; FrsPage.jsx |
| 59 `set_fr_solution` | 実現ソリューション指定 / Solution that carries an FR's effort | Form | Slice spec written | Built | Tested (test_function_requirement_api.py) | slice6a_spec.md |
| 60 `describe_interface` | インターフェース詳細 / Interface detail | Form | Slice spec written | Built | Tested (test_interface_api.py) | slice6b2_spec.md; InterfaceCard.jsx |
| 61 `interface_list` | インターフェース一覧 / Interface list (screen; Excel) | Report | Slice spec written | Partly built | Partly tested (test_interface_api.py) | InterfacesPage.jsx built; no Excel export on it (slice 1f) |
| 62 `create_application` | システム登録 / System catalogue | Form | Slice spec written | Built | Tested (test_application_api.py) | ApplicationsPage.jsx |
| 63 `link_application_solution` | 実現システム割当 / System that delivers a solution | Form | Slice spec written | Built | Tested (test_application_api.py) | AppLinkPanel.jsx |
| 64 `maintain_fr_types` | 機能種別の設定 / FR types per project | Form | Slice spec written | Built | Tested (test_code_lists.py) | slice1g_spec.md; CodeListsPage.jsx |
| 65 `link_fr_to_bfc_node` | 業務機能への直接紐付け / Link an FR straight to a business function | Form | Signed-off design | Not scheduled | n/a | no code found; designed, no slice |
| 66 `solution_matrix` | ソリューション分類マトリクス / Solution type × area matrix | Report | Signed-off design | Not built | n/a | slice 1f, spec owed; SolutionMix.jsx is a per-solution view, not this report **(judgement)** |
| 67 `application_gap_report` | システム移行ギャップ / System gap report | Report | Signed-off design | Not built | n/a | slice 1f, spec owed |
| 68 `fr_traceability_matrix` | トレーサビリティ表 / Traceability matrix | Report | Signed-off design | Not built | n/a | slice 1f, spec owed; FrTracePanel.jsx traces one FR only **(judgement)** |
| 69 `create_stakeholder` | 関係者登録 / Stakeholders | Form | Slice spec written | Built | Tested (test_issue_api.py) | slice14_issue_spec.md; StakeholdersPage.jsx |
| 70 `raise_issue` | 課題起票 / Raise an issue | Form | Slice spec written | Built | Tested (test_issue_api.py) | services/issue.py; IssuesPage.jsx |
| 71 `link_issue_br` | 課題と要件の紐付け / Link issue to requirements | Form | Slice spec written | Built | Tested (test_issue_api.py) | IssueBrLinks.jsx |
| 72 `resolve_issue` | 課題解決 / Resolve / reopen an issue | Form | Slice spec written | Built | Tested (test_issue_api.py) | IssuePage.jsx |
| 73 `issue_dashboard` | 課題ダッシュボード / Issue dashboard | Report | Slice spec written | Built | Tested (test_issue_api.py) | IssueDashboard.jsx |
| 74 `download_template` | テンプレート出力 / Excel template | Interface | Slice spec written | Built | Tested (test_bulk_import.py, test_bulk_import_br/fr/issue.py) | DE, fields, BR, FR, Issue in bulk.TARGETS (1e-a, merge 0c052c6); WBS target counted with row 138 **(judgement)** |
| 75 `export_entity` | データ出力 / Excel export (signed row keys) | Interface | Slice spec written | Built | Tested (test_bulk_import_br/fr/issue.py) | GET /bulk/{target}/export; WBS counted with row 138 **(judgement)** |
| 76 `validate_import` | 取込検証 / Check an import | Interface | Slice spec written | Built | Tested (test_bulk_import*.py) | POST /bulk/{target}/validate; WBS counted with row 138 **(judgement)** |
| 77 `preview_import` | 取込内容プレビュー / Preview an import | Interface | Slice spec written | Built | Tested (test_bulk_import*.py) | GET /bulk/batches/{id}/preview; WBS counted with row 138 **(judgement)** |
| 78 `commit_import` | 取込確定 / Commit an import | Interface | Slice spec written | Built | Tested (test_bulk_import*.py) | POST /bulk/batches/{id}/commit; WBS counted with row 138 **(judgement)** |
| 79 `purge_import_rows` | 取込データの定期削除 / 90-day purge of imported rows | Batch | Slice spec written | Built | Tested (test_import_purge.py) | scripts/purge_import_rows.py; its Azure schedule comes with the Azure task |
| 80 `preview_freeze` | 確定内容プレビュー / Freeze preview | Form | Slice spec written | Built | Tested (test_baseline.py) | slice8_schema.md; FreezeDialog.jsx |
| 81 `freeze_baseline` | ベースライン確定 / Freeze a baseline | Batch | Slice spec written | Built | Tested (test_baseline.py, test_baseline_shadow.py) | services/baseline.py |
| 82 `approve_baseline` | 顧客承認の記録 / Record client approval | Form | Slice spec written | Built | Tested (test_baseline.py) | BaselinePage.jsx |
| 83 `diff_baseline` | 版間差分比較 / Compare versions | Report | Slice spec written | Built | Tested (test_baseline.py) | DiffPanel.jsx |
| 84 `priced_diff` | 工数換算差分 / Compare versions in person-days | Report | Slice spec written | Built | Tested (test_baseline.py) | DiffPanel.jsx; test matched by area **(judgement)** |
| 85 `login` | ログイン / Sign in | Form | Slice spec written | Built | Tested (test_foundation.py) | routers/auth.py; LoginPage.jsx |
| 86 `create_user` | ユーザー登録 / Add a user | Form | Slice spec written | Built | Tested (test_access.py) | POST /users; test matched by area **(judgement)** |
| 87 `change_user_kind · set_platform_admin` | ユーザー区分・管理者権限変更 / Change user type / platform admin | Form | Slice spec written | Built | Tested (test_admin_grant_api.py, test_admin_grant_record.py, test_approvers_setting.py) | slice17_admin_grant_spec.md: admin rights now need a second admin's approval (one approver only on a local single-owner install, migration 0079); GrantRequests.jsx |
| 88 `deactivate_user` | ユーザー無効化 / Deactivate a user | Form | Slice spec written | Built | Tested (test_access.py) | PATCH /users/{id}/deactivate; test matched by area **(judgement)** |
| 89 `create_client ※` | 顧客登録 / Add a client | Form | Slice spec written | Built | Tested (test_foundation.py) | POST /clients |
| 90 `create_project` | プロジェクト登録 / Create a project | Form | Slice spec written | Built | Tested (test_foundation.py, test_components.py) | services/project.py; test matched by area **(judgement)** |
| 91 `set_components` | コンポーネント設定 / Project components on / off | Form | Slice spec written | Built | Tested (test_components.py) | ComponentsPage.jsx |
| 92 `set_data_model_depth` | データモデル詳細度設定 / Data model depth | Form | Slice spec written | Built | Tested (test_components.py) | slice7_schema.md |
| 93 `set_restriction` | 限定公開の設定・解除 / Restrict a project | Form | Slice spec written | Built | Tested (test_access.py) | services/access.py |
| 94 `manage_members` | プロジェクトメンバー管理 / Project members | Form | Slice spec written | Built | Tested (test_access.py, test_project_admin.py) | slice_access_a_plan.md; AccessPage.jsx |
| 95 `list_visible_projects` | 参照可能プロジェクト一覧 / Projects I can see | Form | Slice spec written | Built | Tested (test_access.py) | access.visible_project_ids; HomePage.jsx |
| 96 `list_effective_access` | 実効アクセス一覧 / Who can open this project | Report | Slice spec written | Built | Tested (test_access.py, test_program_members.py) | slice_access_b_plan.md; AccessPage.jsx |
| 97 `enforce_project_scope` | プロジェクト境界制御 / Project access guard (404→403→409) | Form | Slice spec written | Built | Tested (test_access.py, test_route_guards.py) | routers/guards.py; server-side |
| 98 `soft_delete_record` | 論理削除 / Retire a record (soft delete) | Form | Slice spec written | Built | Tested (test_bfc_schema.py, test_function_requirement_api.py) | server-side, across services; tests matched by area **(judgement)** |
| 99 `restore_record` | 論理削除データの復元 / Restore a retired record | Form | Slice spec written | Built | Tested (test_bfc_schema.py, test_application_api.py) | restore routes across services; tests matched by area **(judgement)** |
| 100 `consistency_check` | 整合性チェック / Consistency check | Form | Slice spec written | Built | Tested (test_consistency.py) | services/consistency.py |
| 101 `resolve_codes` | コードマスタ解決 / Resolve code lists (company + project) | Form | Slice spec written | Built | Tested (test_code_lists.py) | services/code_master.py |
| 102 `read_rate_card` | 標準工数表の参照 / Rate card | Form | Slice spec written | Built | Tested (test_effort_api.py) | slice6c_spec.md; RateCardPage.jsx |
| 103 `maintain_rate_card` | 標準工数マスタ管理 / Adjust the rate card | Form | Slice spec written | Built | Tested (test_effort_api.py) | services/effort.py |
| 104 `rate_function_requirement` | 機能要件の規模設定 / Size an FR (effort days) | Form | Slice spec written | Built | Tested (test_effort_api.py, test_function_requirement_api.py) | FrEffort.jsx |
| 105 `effort_summary` | 工数集計 / Effort summary | Report | Slice spec written | Built | Tested (test_effort_api.py) | EffortPage.jsx |
| 106 `create_benefit` | 効果登録 / Add a benefit | Form | Signed-off design | Not built | n/a | Phase 2 Benefits; spec owed |
| 107 `link_benefit_solution` | 効果とソリューションの紐付け / Link benefit to solution | Form | Signed-off design | Not built | n/a | Phase 2 Benefits |
| 108 `value_ranking` | 費用対効果ランキング / Value-for-effort ranking | Report | Signed-off design | Not built | n/a | Phase 2 Benefits |
| 109 `benefit_gap_report` | 効果未設定検知 / No-benefit check | Report | Signed-off design | Not built | n/a | Phase 2 Benefits |
| 110 `raise_risk` | リスク登録 / Add a risk | Form | Signed-off design | Not built | n/a | Phase 2 Risks; spec owed |
| 111 `score_risk` | リスク評価 / Score a risk | Form | Signed-off design | Not built | n/a | Phase 2 Risks |
| 112 `promote_risk_to_issue` | リスク顕在化 / Risk becomes an issue | Form | Signed-off design | Not built | n/a | Phase 2 Risks |
| 113 `risk_register` | リスク一覧 / Risk register | Report | Signed-off design | Not built | n/a | Phase 2 Risks |
| 114 `raise_change_request` | 変更要求起票 / Raise a change request | Form | Signed-off design | Not built | n/a | Phase 2 Change requests; spec owed |
| 115 `analyse_cr_impact` | 影響範囲分析 / Change impact trace | Report | Signed-off design | Not built | n/a | Phase 2 Change requests |
| 116 `price_cr` | 変更要求の試算 / Price a change | Form | Signed-off design | Not built | n/a | Phase 2 Change requests |
| 117 `decide_cr` | 変更要求の意思決定 / Decide a change | Form | Signed-off design | Not built | n/a | Phase 2 Change requests |
| 118 `record_decision` | 意思決定記録 / Record a decision | Form | Signed-off design | Not built | n/a | Phase 2 Decisions; spec owed |
| 119 `decision_log` | 意思決定履歴 / Decision log | Report | Signed-off design | Not built | n/a | Phase 2 Decisions |
| 120 `create_phase` | フェーズ登録 / Waves | Form | Slice spec written | Built | Tested (test_phasing_api.py) | slice15_phasing_spec.md; WavesPage.jsx |
| 121 `assign_solution_phase` | ソリューションのフェーズ割当 / Split a solution across waves | Form | Slice spec written | Built | Tested (test_phasing_api.py) | SolutionWaves.jsx |
| 122 `link_solution_dependency` | 依存関係登録 / Solution dependencies | Form | Slice spec written | Built | Tested (test_phasing_api.py) | services/phasing.py |
| 123 `phase_plan_report` | フェーズ計画レポート / Wave plan | Report | Slice spec written | Built | Tested (test_phasing_api.py, test_baseline_phasing.py) | WavePlan.jsx |
| 124 `maintain_control_rule` | コントロールルール設定 / Control rules | Form | Signed-off design | Not built | n/a | Phase 1 Control rules + panel; spec owed |
| 125 `control_panel` | コントロールパネル / Control panel | Report | Signed-off design | Not built | n/a | Phase 1 Control |
| 126 `requirement_volatility` | 要件変動分析 / Requirement volatility | Report | Signed-off design | Not built | n/a | Phase 1 Control |
| 127 `process_change_intensity` | 業務変更集中度 / Where change lands | Report | Signed-off design | Not built | n/a | Phase 1 Control |
| 128 `org_impact_heatmap` | 組織影響度 / Organisation impact | Report | Signed-off design | Not built | n/a | Phase 1 Control |
| 129 `stakeholder_engagement` | 関係者関与度 / Stakeholder engagement | Report | Signed-off design | Not built | n/a | Phase 1 Control (the issue module it needs is built) |
| 130 `interface_load` | インターフェース負荷 / Interface load | Report | Signed-off design | Not built | n/a | Phase 1 Control |
| 131 `data_migration_map` | データ移行マップ / Data migration map | Report | Signed-off design | Not built | n/a | Phase 1 Control |
| 132 `master_data_candidates` | マスタデータ候補 / Master data candidates | Report | Signed-off design | Not built | n/a | Phase 1 Control |
| 133 `fr_unlinked` | 未紐付け機能要件 / FRs with no requirement (threshold) | Report | Signed-off design | Partly built | Partly tested (test_scope_summary_12.py) | count shown on the scope dashboard; threshold check comes with Control; test match **(judgement)** |
| 134 `create_program · update_program` | プログラム登録・更新 / Add / edit a program | Form | Signed-off design | Partly built | Partly tested (test_program_members.py) | POST /programs only, no PATCH route; edit owed in 1f; test match **(judgement)** |
| 135 `move_project_program` | プロジェクトの所属変更 / Move a project to another program | Form | Slice spec written | Built | Tested (test_program_members.py) | services/program.move_project_program; test match **(judgement)** |
| 136 `program_dashboard` | プログラムダッシュボード / Program dashboard | Report | Signed-off design | Partly built | Partly tested (test_program_members.py) | ProgramHome.jsx shows the member-project list only; test match **(judgement)** |
| 137 `program_counts · program_interfaces · program_effort · program_control_status` | プログラム集計 / Program roll-up figures | Report | Signed-off design | Not built | n/a | Phase 4; no roll-up in services/program.py |
| 138 `link_wbs_item` | WBS行の紐付け / Link WBS lines (MS Project import) | Form | Signed-off design | Not built | n/a | Phase 2 WBS; no WBS target in bulk.TARGETS |
| 139 `record_wbs_progress` | 進捗更新の記録 / Record progress | Form | Signed-off design | Not built | n/a | Phase 2 WBS |
| 140 `wbs_progress_report` | 進捗レポート / Progress report | Report | Signed-off design | Not built | n/a | Phase 2 WBS |
| 141 `scope_dashboard ※` | スコープダッシュボード / Scope dashboard (S1–S11) | Report | Slice spec written | Built | Tested (test_scope_summary.py, test_scope_summary_12.py) | slice12_kpis.md; merged per 10-22 status; ProjectHome.jsx |
| 142 `pm_dashboard ※` | プロジェクト管理ダッシュボード / Project-management card | Report | Slice spec written | Partly built | Partly tested (test_scope_summary_12.py, test_baseline_issue.py) | services/scope_summary.py has M1 baselines and M3 issues; M2 changes, M4 risks and M5 WBS come with their modules |
| 143 `export_report_pdf ※` | レポートPDF出力 / Client reports printed to PDF | Report | Signed-off design | Not built | n/a | slice 1f; no print layout found in the frontend |
| 144 `maintain_code_master ※` | コードマスタ保守 / Code list maintenance | Form | Slice spec written | Built | Tested (test_code_lists.py) | slice1g_spec.md; services/code_lists.py; CodeListsPage.jsx |
| 145 `switch_language ※` | 表示言語切替 / Language switch (EN / JA / TH) | Form | Signed-off design | Not built | n/a | Phase 4; frontend/src/i18n holds English files only |
| 146 `version_compare_screen ※` | 版比較画面 / Version comparison screen | Report | Signed-off design | Not built | n/a | Phase 4; the comparison logic (row 83) is built |
| 147 `client_readonly_login ※` | 顧客参照ログイン / Client read-only sign-in | Form | Signed-off design | Not built | n/a | Phase 3; spec owed |
| 148 `export_offline_viewer ※` | オフライン閲覧ファイル出力 / Offline viewer file | Interface | Signed-off design | Not built | n/a | Phase 3; spec owed |
| 149 `export_baseline_archive ※` | ベースラインアーカイブ出力 / Archive file of each frozen baseline | Batch | Slice spec written | Built | Tested (test_baseline_archive.py, test_archive.py, test_weekly_check.py) | slice16_archive_purge_spec.md; scripts/write_archives.py; merge 5d7de4b |
| 150 `purge_project ※` | プロジェクト完全削除 / Remove a project for good (two-person approval) | Batch | Slice spec written | Built | Tested (test_purge_run.py, test_purge_api.py, test_purge_bypass.py) | scripts/purge_project.py → services/purge_run; RemovalsTab.jsx; migrations 0074/0075 merged in 5d7de4b |

## Still to build (from the table)

**Phase 1 — finish the scope core**
- **Slice 1e-b, the rest:** 35 check a process-flow file import and 36 commit it. Piece a2 is merge mode and piece b is replace mode.
- **Slice 1f — reports:** 41 ERD to PNG/SVG, 56 requirements coverage report, 61 interface list to Excel, 66 solution matrix, 67 system gap report, 68 traceability matrix, 134 program edit and 143 client reports to PDF.
- **Control rules and control panel:** 124–132, plus the threshold check for 133. The count for 133 is already on the dashboard.

**Phase 2 — delivery control modules** (slice 15, waves, rows 120–123, is done)
- **Benefits:** 106–109. **Risks:** 110–113. **Change requests:** 114–117. **Decisions:** 118–119.
- **WBS import and progress:** 138–140, including the WBS target of the Excel import (rows 74–78).
- **Project-management card:** the M2 (changes), M4 (risks) and M5 (WBS) tiles for 142, each built with its module.

**Phase 3 — ready for the first client** (slice 16, archives and removal, and slice 17, admin approval, are done)
- **Client read-only login and offline viewer:** 147, 148.
- **Work that is not a function:** Sara's full review pass with the VB-005 backlog, Azure (VB-011 is still open there), the restore drill and the prompt pack sign-off.

**Phase 4 — after first client use**
- **Program roll-ups:** 136 (beyond the member list) and 137. **Languages:** 145. **Version comparison screen:** 146.

**Unscheduled:** 65, linking an FR straight to a business function.
