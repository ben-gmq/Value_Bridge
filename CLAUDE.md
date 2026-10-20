@~/.claude/lilly.md
@~/.claude/ftc-playbook.md

# Value Bridge (VB)

Fortience Consulting's Strategic PMO platform — MVP is **Scope Management & Control**:
business function chart → processes → business requirements → solutions → functional
requirements, data entities and interfaces, all frozen into priced, diffable baselines.
Multi-project, with programs as roll-up scopes. **The signed-off design is
[docs/VB_design.md](docs/VB_design.md) (signed off 2026-09-28). It is the source of truth —
cite it, don't restate it.** Changes to data design or business logic go to Ben first.
**Two files, kept apart:** `VB_design.md` is the clean current spec — present tense, no "revised/was/supersedes",
decisions cited by id only. [docs/VB_design_history.md](docs/VB_design_history.md) holds every decision with its date
and Ben's words, the reviews, the spec's revisions and the slice-spec index. New feedback goes to history §1 *Open*
only; once Ben decides, it moves to history §3 and the spec is rewritten to the new state **in the same commit**.

## Stack & where things run
- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic, psycopg 3, PostgreSQL 16.
- **Frontend:** React 18 + MUI 9 + Vite 8, TanStack Query, React Router 7.
- **Ports: API 8100, web 5180.** Not 8000/5173 — those belong to other FTC apps on this machine.
  A parallel session uses its own pair (`--port 81xx`, `VB_API_PORT=81xx VB_WEB_PORT=51xx npm run dev`)
  and its own database; never stop a server by pattern (`pkill -f vite`) — stop your own by PID.
- **First time on a machine:** `cd backend && VB_EMAIL_DOMAINS=fortience.com ./scripts/bootstrap_local_db.sh`
  (creates roles `vb_owner`/`vb_app`, databases `vb_db`/`vb_test_db`, writes a gitignored `.env`),
  then `./venv/bin/alembic upgrade head && ./venv/bin/python -m seeds.seed_code_master && ./venv/bin/python -m seeds.seed_project_templates`.
  **7a deploy only (one-off, not every deploy):** a database with pre-7a projects then runs
  `seeds.seed_project_components --actor-email <admin>`, or their gated writes return 409 COMPONENT_OFF.
  **Slice 11 deploy only:** after `seed_code_master`, `seeds.backfill_br_lines --actor-email <admin>` copies each BR's
  legacy logic / output text into requirement lines once (idempotent per project), then
  `seeds.seed_effort_rate --actor-email <admin>` adds the Data migration rate cells (S11-5) to existing projects —
  before their next freeze, or their next diff counts four added rate rows.
  **Slice 15 deploy:** `seed_code_master` stops while any project still holds its own wave status (a project-tier
  PHASE_STATUS row or hide, now company-only — W-4); clear those with Ben, then re-run it.
- **Run:** `cd backend && ./venv/bin/uvicorn main:app --port 8100 --reload` ·
  `cd frontend && npm run dev` → http://localhost:5180 (proxies `/api` and `/auth`).
- **Test:** `cd backend && ./venv/bin/pytest -q` (runs as `vb_app` against `vb_test_db`; skips the `slow` mark) ·
  **before every merge, the full suite:** `./venv/bin/pytest -q -m "" -n 4` (needs `pip install -r requirements-dev.txt`
  and `./scripts/make_test_worker_dbs.sh 4` once: one test DB per worker) · `cd frontend && npm run lint && npm run build`.
- **Test screenshots** go to `Evidence/<YYYY-MM-DD>/<slice>/NN-<check>.png` (date of the test run),
  never loose in the repo root and never directly in `Evidence/`. ui-verifier saves PNGs in the repo root
  (sometimes `.playwright-mcp/`); move them after every run. PNGs are gitignored; see `Evidence/README.md`.
  Files it must **upload** have to sit inside the repo: stage them in `.playwright-mcp/<slice>/` (gitignored).
- **Demo/UAT data:** `VB_ALLOW_DEMO_SEED=1 ./venv/bin/python -m seeds.seed_demo --secrets-out <file outside the repo>`
  against a throwaway database whose name contains `uat` or `demo`; it refuses anything else.
- **Upload routes:** a route taking more than the 1 MB default body registers in `services/body_limit.ROUTE_CAPS`
  (ordered, first match wins), and is refused with 401 before reading when there is no Bearer header.
- **Two database roles (§6.6):** the app connects as `vb_app` (SELECT/INSERT/UPDATE, **no DELETE**
  except `diagram_layout` and `import_row`); migrations run as `vb_owner` (`MIGRATION_DATABASE_URL`).

## Source of truth (read the code, don't guess)
- **Routing:** `backend/main.py`. `/auth/*` at the root; everything else under one
  `GuardedRouter(prefix="/api/v1")`. Routers declare only their sub-paths.
- **Every route declares exactly one guard** — `backend/routers/guards.py`: `public`,
  `authenticated`, `platform_admin`, `project_ctx(min_level, component=)`, `object_guard(Model, min_level,
  component=)`, `program_ctx(min_level)`; levels `VIEW` < `EDIT` < `ADMIN` < `PLATFORM`. ADMIN is a project
  admin (a `project_member` at ADMIN, D-71) and guards only members and the access list; **an FTC-only project
  setting takes `PLATFORM`** (only platform admins hold it) — `test_project_admin.py` pins both route sets. A write to a project component names it (`component=`), else 409 COMPONENT_OFF; criterion 49b
  (`ROUTE_COMPONENTS` in `tests/test_route_guards.py`) fails a write that forgets. Use
  `@router.get(path, **guard.route)`. A route without a guard **fails at import**, and criterion 49 re-proves it.
- **Visibility has one owner:** `backend/services/access.py` (`visible_project_ids`,
  `require_project`, `require_program`, and `level_for` / `who_can_open` — the only place a level is computed).
  D-40/D-71: admins see all; staff see every project **except a restricted one they are not a live
  `project_member` of, or reach through a live `program_member` of its program**, at the higher of the staff default
  (`KIND_BASE`), their project role and their program role, capped by kind
  (`KIND_CAP`, never a default).
  A project you cannot see is **404, never 403**; order is 404 → 403 → 409. `user_access_grant` is
  retired history (SELECT-only). `tests/test_access.py::test_no_get_route_leaks_a_restricted_project`
  calls every GET route as a non-member — a new route that bypasses `visible_project_ids` fails it.
- **Numbers are minted only by** `services/numbering.py::next_number`, at save time. All ten series
  are seeded by `create_project`; a missing series raises — never insert one lazily.
- **Lookups:** `code_master`, two-tier (global + project override), resolved only by
  `services/code_master.resolve`. Send codes, never labels. Seeds: `backend/seeds/`, never Alembic.
  Writes to the lists go only through `services/code_lists` (wave 1g): a project override re-points the project's rows
  on every code column found in the catalog; a new code FK is re-pointed or named in `code_lists.EXCLUDED`, and a value
  the code looks up by literal joins `code_lists.PINNED` — `tests/test_code_lists.py` fails otherwise. Pickers use
  `useCodes().options(current)`, never the full list (hidden codes, R5).
- **Brand/theme:** `frontend/src/theme/brand.js` (`BRAND`, `STATUS_COLOR_MAP`, `TOKENS`) →
  `theme.js`. Components read `theme.vars.palette.*` — no hex anywhere else.
- **Look (D-51):** the mockups in `docs/mockups/` (screenshots + source) are the visual reference; dark is the
  default. Screens compose `components/kit.jsx` (Card, Tag, Code, Status, LevelBadge, Segmented, PurpleTile, Tile…)
  inside the left-rail shell; `<Page crumb=…>` names the item in the header breadcrumb. A mockup element with no
  data behind it is left out, never faked. New screens are checked side by side with their mockup before merge.
- **Strings:** via `t()`, one file per screen area — `frontend/src/i18n/en.json` (shell) plus
  `en.<area>.json`, keys prefixed by area. No hard-coded UI text in new screens.
- **Screen contracts:** page addresses and query keys in `frontend/src/app/links.js`; one API
  function per route in `frontend/src/api/scope.js`. Screens link to each other only through these.
- **Edit controls** hide through `frontend/src/app/useCanEdit.js` (reads the project's `my_access_level`
  from `GET /projects/{id}`) and components through `app/useComponents.js` — never computed from
  memberships in the browser. Presentation only; the guards still refuse.
- **Browser Back / Forward** is guarded only through `app/backGuard.js` (`useBackGuard`). A screen's own `popstate`
  listener runs after BrowserRouter's and stops nothing (VB-007, VB-010).
- **Deviations** from the playbook: [docs/PLAYBOOK_DEVIATIONS.md](docs/PLAYBOOK_DEVIATIONS.md).
- **Bugs:** [BUGLOG.md](BUGLOG.md) (`VB-###`). Standing review backlog is VB-005.

## The VB law (enforced in code; `sara` audits it)
1. **No hard delete.** Soft delete (`is_active=false`) everywhere. The only hard deletes are
   `diagram_layout` (D-30), the 90-day `import_row` purge (Q14) and `purge_project` (Q15, runs as `vb_owner`). The app role has no
   DELETE grant, so this fails at the database, not in review.
   Nothing cascades except a process step: `services/step_retire.OWNED_BY_STEP` / `OWNED_BY_BR` are the only lists
   of rows that retire with something else; a new table that points at a step or a BR blocks until added to one.
2. **Baselines are immutable** — every `baseline_*` table gets the `fn_reject_modification()`
   trigger and the insert guard (`vb_ops.immutable_guards`), and shadows are **generated** by
   `services/baseline_shadow.py`, never hand-written. Migration 0048 froze them as literal DDL: a migration
   that adds a column to a shadowed live table adds the shadow column **in the same migration** (the parity
   test in `tests/test_baseline.py` reads the database), and a shadow column's type is **never** ALTERed
   (pauses for Ben). The freeze set, its component gates and the hashed columns are data in
   `services/freeze_set.py` (+ `components.FREEZE_GATES`); a new frozen table is added there and to
   `models/baseline.SHADOWED`.
3. **Audit columns, soft delete and `row_version` are born with every business table**
   (`models/base.py::AuditMixin`, `alembic/vb_ops.py::audit_columns`). `updated_at` is set by the
   `fn_set_updated_at()` trigger — never `onupdate=`. Stale `row_version` → 409.
4. **A process is `is_process`, never `level_no = 5`** (D-23). The literal is banned in code.
5. **Branch on behaviour, never on a code** — FR type, RACI and issue status (`code_master.behaviour_code`,
   D-27/Q7, I-1). `== 'INTERFACE'` against a type code is a finding.
6. **Derived values are never accepted from a request body**: `created_by`, `effort_days`,
   `exposure_score`, `row_version` increments, numbers.
7. **The bare word `role` is banned** in tables, models and routes: `org_role` vs
   `project_role_code`.
8. **One import pipeline** (`services/bulk.py`: validate → preview → commit) for every import, flow JSON
   included; a new import adds a `Target` to `TARGETS` (column map + `validate`/`apply`). **One canvas component** for process flow, DFD and ERD, and one position saver
   (`canvas/useLayoutSave.js`) for all three.
9. **Untrusted text renders as text.** `dangerouslySetInnerHTML` / `innerHTML` fail lint (§14.5).
   Every Mermaid label goes through `services/render.escape_mermaid`, and `_guard` ends every exporter.
10. **Every new table** is added to `models/__init__.py` (autogenerate only sees what is imported)
    and gets its migration **one per commit**, reversible; a destructive one pauses for Ben.

## Parallel sessions (up to ~20 a day)
- **One git worktree per slice**, at `.worktrees/<branch>` inside the repo (gitignored) — never a
  sibling folder. Branch from `main`; merge back through review. Give each worktree its own
  copied `backend/.env` with its own `TEST_*` database — pytest wipes its test DB, so two never share one.
- **Migrations only on `main`, in order.** A slice branch that needs a table rebases onto the
  latest `main` before creating its migration, so revision ids never fork. Two slices never
  add migrations at the same time — coordinate on `main`.
- **A hash-spec bump (`freeze_set.CURRENT_HASH_SPEC`) is taken on `main` in order, like a migration id**; tables that
  share one spec reach `main` in one merge (S11-6).
- **This file is the shared rulebook.** A rule learned in one session lands here (via
  `rules-check-drift`) so the other nineteen follow it.

## Delegation
- **Schema changes → `apple`** before code. **`sara`** before any commit touching auth, access,
  grants, baselines, imports or the migration chain. **`test-runner` / `ui-verifier`** before
  claiming a change works. **`bug-hunter`** for a failure with an unknown cause.

## Landmines
1. `TRUNCATE app_user … CASCADE` also empties `code_master` (its audit columns reference
   `app_user`) — the test harness copies the library back from its `vb_test_snapshot` schema after a wipe; a script
   must re-seed.
2. `audit_event` is append-only by grant **and** trigger; even the owner role cannot UPDATE it.
3. `request.client.host` is not always an IP — `services/audit.py` stores only valid addresses.
4. `code_master.created_by` is nullable **only** because seeded library rows have no author.
5. Start Vite with the frontend folder as root (`npm run dev` from `frontend/`); run from the repo
   root it serves 404s.
