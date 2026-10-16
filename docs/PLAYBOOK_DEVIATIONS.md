# Value Bridge — deviations from the FTC Vibe Coding Playbook

Each deviation is deliberate, has a reason, and is cited in the design spec
(`docs/VB_design.md`). Anything not listed here follows the playbook and the
`fortience-app-scaffold` recipes exactly. `sara` audits against this list.

## Data model

| # | Deviation | Playbook rule | Reason | Spec |
|---|---|---|---|---|
| 1 | Baseline snapshot rows are immutable and never soft-deleted | §9.7 soft delete everywhere | A frozen baseline is evidence; a soft-delete flag on it would be an edit | A-7, §6.2 |
| 2 | CRUD letters on BR ↔ data entity are a `CHECK`, not `code_master` | §9.3 all lookups in `code_master` | Code branches on each value; a configurable CRUD letter would break the direction rule | §8 |
| 3 | `diagram_type` and `code_master.behaviour_code` are `CHECK`-listed | §9.3 | Closed vocabularies the code branches on (D-27, Q7, D-30) | §8, §5.3 |
| 4 | The `baseline` header is exempt from soft delete; only its status, the client-approval set (once, then closed), `updated_by` and `row_version` may change (column grant + `trg_baseline_header_guard`) | §9.7 | FROZEN → APPROVED → SUPERSEDED and one recorded sign-off are the only allowed changes; 5-year recoverability (Q12) | §6.2, §6.6 (P6); slice8_schema §2, §13 |
| 5 | `diagram_layout` is hard-deleted and has no `row_version` | §9.7, D-6 concurrency | Presentation, not scope; last write wins per object (A-52) | D-30 |
| 6 | `wbs_item.row_version` guards only the two consultant-editable link fields | D-6 | WBS rows are otherwise read-only imports from MS Project (D-33) | §5.3 |
| 7 | `code_master.created_by` is nullable | §9.2 `created_by` from the JWT | Seeded FTC library rows are created by the seed CLI, not a user | §5.1 |
| 7a | `app_user.created_by` is nullable | §9.2 | The first platform admin is created by nobody (first-run setup or `seeds.create_admin`) | §5.3 |
| 7b | `import_row` is hard-deleted after 90 days (DELETE granted on that table only) | §9.7 soft delete | Raw client-supplied payloads are purged for data protection (Q14); the batch header is kept | §6.6, Q14 |
| 7c | `import_batch` has no soft delete and no `updated_by` (`uploaded_at` / `uploaded_by_user_id` are its created pair; `row_version` kept); `import_row` carries no audit columns, soft delete or `row_version` | §9.7 soft delete, VB law 3 / design §5.1 audit columns | The batch's status is its lifecycle and the header is kept as the import trail; a staged row is short-lived staging whose provenance is its batch | S4-6, slice4_schema Q-7 |
| 7d | `project_template_component.created_by` is nullable | §9.2 `created_by` from the JWT | Template rows are seeded by `seeds.seed_project_templates`, like `code_master` (deviation 7) | slice7_schema §3, Q-5 |
| 7e | `project.data_model_depth` is a `CHECK` (`KEYS_ONLY` / `FULL`), not a `code_master` lookup | §9.3 all lookups in `code_master` | A two-value vocabulary the code branches on (S2-1 precedent) | slice7_schema §4, Q-8 |
| 7f | `app_user.user_kind` (USER / VIEWER) and `project_member.access_level` (EDIT / VIEW) are `CHECK`-listed, not `code_master` | §9.3 all lookups in `code_master` | Closed access vocabularies the guard branches on (S2-1 precedent) | slice7_schema §8.2, §8.4, Q-11 |
| 7g | `bfc_node.bfc_set_code` (TO_BE / AS_IS), `bfc_node.performer_kind`, `process_trigger.trigger_kind` (TIME / EVENT) and the retired `bfc_node_flow.flow_type` are `CHECK`-listed, not `code_master` | §9.3 all lookups in `code_master` | Closed vocabularies the code branches on (S2-1 precedent); renaming one in code maintenance would break the program | slice7_schema §9.1, §9.4, §9.5; SC-11 |
| 7h | The DFD rule elements (`project_dfd_rule`) and the volume period (`bfc_node.volume_period_code`) are `CHECK`-listed; only transaction units are a `code_master` category | §9.3 all lookups in `code_master` | The program depends on both lists; seeds run after migrations, so the 13b backfill cannot reference `code_master` rows | slice13_schema [Q-17] |
| 7i | `br_requirement_line.created_by` on lines copied by `seeds.backfill_br_lines` is the BR's `updated_by` (else `created_by`), not the person running the command | §2 `created_by` from the JWT | The copy carries text the BR's author wrote; the admin who ran the command is recorded on the `BR_LINES_BACKFILLED` audit event with OS user and host | slice11_schema §1.2, S11-1 |
| 8a | `baseline` (header) has no soft delete and no `created_at` / `created_by`; `frozen_at` / `frozen_by_user_id` are that pair | §9.7 soft delete; §5.1 audit columns | A baseline is never retracted (A-36); the design names the creation pair (§5.2) | slice8_schema §2, Q-6 |
| 8b | `baseline_*` shadow tables carry no audit columns, no `is_active`, no `row_version` | §5.1 audit columns on every business table | A snapshot is never updated or deleted (A-7); `baseline_id` → the header carries who and when | slice8_schema §3 |
| 13b | `project_dfd_rule.element_code` (STARTED / DATA_IN / DATA_OUT / EXTERNAL / ORDER) is `CHECK`-listed, not a `code_master` lookup; labels in `en.components.json`. `baseline.dfd_rule_to_be` / `_as_is` are `varchar(12)[]` arrays (a 1NF exception) | §9.3 all lookups in `code_master`; normal form | Each code is a predicate the code branches on (S2-1); a `code_master` FK would make the 0053 backfill impossible (seeds run after migrations). The arrays are a frozen record of a small set, read whole, never queried by element | slice13_schema §2.3, §2.6, [Q-17], [Q-19] |

## Frontend

| # | Deviation | Playbook / scaffold rule | Reason | Spec |
|---|---|---|---|---|
| 8 | `BRAND` is the Fortience deck palette (indigo `#2B245C`, cyan `#04AED6`, violet `#7848DC`) instead of the neutral slate default | scaffold §5 default palette | VB is FTC's own tool, not a client app; Ben's direction 2026-09-28 | §14.2 |
| 9 | Light **and dark** themes from one MUI `colorSchemes` theme | — (not in the scaffold) | Ben asked for both sets; tokens make it free per screen | §14.2 |
| 10 | IBM Plex Sans / Mono + Noto Sans JP, self-hosted via `@fontsource` | scaffold default fonts | Brand type; self-hosting keeps the CSP `font-src 'self'` | §14.2, §14.5 |
| 11 | The wrapper `Box` reads fill and border from theme tokens, not `#fafafa` / `#e0e0e0` | scaffold §2 recipe | Hard-coded greys break dark mode; the recipe is otherwise unchanged | §14.2 |
| 12 | React Flow 12 + elkjs for diagrams | fixed stack (not covered) | Canvas spike GO 2026-09-28; one component for three diagrams | §7.14, §14.6 |
| 13 | CSP allows `style-src 'unsafe-inline'` | §14.5 strict CSP | MUI/Emotion inject style tags; `script-src` stays `'self'` only | §14.5 |
| 14 | Login is by **email**, not username | scaffold §1 username | Accounts are FTC staff identified by email domain (D-11) | §7.10 |
| 15 | `BRAND` lives in `frontend/src/theme/brand.js`, not at the top of `App.jsx` | scaffold §5 | Tokens for two themes plus the FTC chrome; one module every screen imports. Still the single source of truth | §14.2 |
| 16 | First-run setup is **off by default** (`ALLOW_FIRST_RUN_SETUP`); cloud environments create the first admin with `python -m seeds.create_admin` | scaffold §1 first-run setup | An anonymous setup endpoint on a fresh Azure database would let the first caller become platform admin (sara H1) | §15.4 |
| 17 | Platform-admin rights are granted by a separate, audited action with a reason, never by a checkbox on user creation | scaffold §1 two roles | An admin sees every client; the change must be deliberate and on the record (sara M7) | §7.10 |

## Process

| # | Deviation | Playbook / brief rule | Reason | Repaid by |
|---|---|---|---|---|
| P1 | **2026-10-15 night batch (Ben: "skip the security review and test after bundle build").** On branches `ui-mockup` and the wave-1 slices built the same night, `sara` and `ui-verifier` run **once over the whole bundle** instead of per slice. pytest, lint and build still run after every slice | Lilly brief: `sara` before any commit touching access/baselines/imports; `ui-verifier` before claiming a screen works | Local-only app, no real data; Ben asked to keep the night moving | One `sara` pass and one `ui-verifier` pass over every commit of the bundle **before any of it merges to `main`**. Not a standard: the next slice reviews per slice again |
| P2 | **Reduced review depth while local-only (taken 2026-10-16, slice 11 onward; recorded late — it was cited before this row existed, sara L6).** `sara`'s CRITICAL and HIGH are fixed before each commit; her MEDIUM and LOW go to the VB-005 standing backlog instead of holding the slice | Lilly brief, "Review depth follows the app's phase": full depth is the default | The app is local-only, holds no real data and no screen is reachable outside the team | **The gate before first client use:** one production-depth `sara` pass over everything built since sign-off, and VB-005 cleared or accepted with Ben line by line (`docs/VB_remaining_work.md`, "At the end") |
