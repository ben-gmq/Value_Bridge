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
| 4 | The `baseline` header is exempt from soft delete; only its status may change (column grant) | §9.7 | FROZEN → APPROVED → SUPERSEDED is the only allowed change; 5-year recoverability (Q12) | §6.2, §6.6 (P6) |
| 5 | `diagram_layout` is hard-deleted and has no `row_version` | §9.7, D-6 concurrency | Presentation, not scope; last write wins per object (A-52) | D-30 |
| 6 | `wbs_item.row_version` guards only the two consultant-editable link fields | D-6 | WBS rows are otherwise read-only imports from MS Project (D-33) | §5.3 |
| 7 | `code_master.created_by` is nullable | §9.2 `created_by` from the JWT | Seeded FTC library rows are created by the seed CLI, not a user | §5.1 |
| 7a | `app_user.created_by` is nullable | §9.2 | The first platform admin is created by nobody (first-run setup or `seeds.create_admin`) | §5.3 |
| 7b | `import_row` is hard-deleted after 90 days (DELETE granted on that table only) | §9.7 soft delete | Raw client-supplied payloads are purged for data protection (Q14); the batch header is kept | §6.6, Q14 |
| 7c | `import_batch` has no soft delete and no `updated_by` (`uploaded_at` / `uploaded_by_user_id` are its created pair; `row_version` kept); `import_row` carries no audit columns, soft delete or `row_version` | §9.7 soft delete, §5.1 audit columns | The batch's status is its lifecycle and the header is kept as the import trail; a staged row is short-lived staging whose provenance is its batch | S4-6, slice4_schema Q-7 |

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
