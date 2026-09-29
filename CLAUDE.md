@~/.claude/lilly.md
@~/.claude/ftc-playbook.md

# Value Bridge (VB)

Fortience Consulting's Strategic PMO platform — MVP is **Scope Management & Control**:
business function chart → processes → business requirements → solutions → functional
requirements, data entities and interfaces, all frozen into priced, diffable baselines.
Multi-project, with programs as roll-up scopes. **The signed-off design is
[docs/VB_design.md](docs/VB_design.md) (signed off 2026-09-28). It is the source of truth —
cite it, don't restate it.** Changes to data design or business logic go to Ben first.

## Stack & where things run
- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic, psycopg 3, PostgreSQL 16.
- **Frontend:** React 18 + MUI 9 + Vite 8, TanStack Query, React Router 7.
- **Ports: API 8100, web 5180.** Not 8000/5173 — those belong to other FTC apps on this machine.
- **First time on a machine:** `cd backend && VB_EMAIL_DOMAINS=fortience.com ./scripts/bootstrap_local_db.sh`
  (creates roles `vb_owner`/`vb_app`, databases `vb_db`/`vb_test_db`, writes a gitignored `.env`),
  then `./venv/bin/alembic upgrade head && ./venv/bin/python -m seeds.seed_code_master`.
- **Run:** `cd backend && ./venv/bin/uvicorn main:app --port 8100 --reload` ·
  `cd frontend && npm run dev` → http://localhost:5180 (proxies `/api` and `/auth`).
- **Test:** `cd backend && ./venv/bin/pytest -q` (runs as `vb_app` against `vb_test_db`) ·
  `cd frontend && npm run lint && npm run build`.
- **Two database roles (§6.6):** the app connects as `vb_app` (SELECT/INSERT/UPDATE, **no DELETE**
  except `diagram_layout` and `import_row`); migrations run as `vb_owner` (`MIGRATION_DATABASE_URL`).

## Source of truth (read the code, don't guess)
- **Routing:** `backend/main.py`. `/auth/*` at the root; everything else under one
  `GuardedRouter(prefix="/api/v1")`. Routers declare only their sub-paths.
- **Every route declares exactly one guard** — `backend/routers/guards.py`: `public`,
  `authenticated`, `platform_admin`, `project_ctx(min_role)`, `object_guard(Model, min_role)`,
  `program_ctx(min_role)`. Use `@router.get(path, **guard.route)`. A route without one
  **fails at import**, and `tests/test_route_guards.py` (criterion 49) re-proves it.
- **Visibility has one owner:** `backend/services/access.py` (`visible_project_ids`,
  `require_project`, `require_program`). A project you cannot see is **404, never 403**.
- **Numbers are minted only by** `services/numbering.py::next_number`, at save time. All ten series
  are seeded by `create_project`; a missing series raises — never insert one lazily.
- **Lookups:** `code_master`, two-tier (global + project override), resolved only by
  `services/code_master.resolve`. Send codes, never labels. Seeds: `backend/seeds/`, never Alembic.
- **Brand/theme:** `frontend/src/theme/brand.js` (`BRAND`, `STATUS_COLOR_MAP`, `TOKENS`) →
  `theme.js`. Components read `theme.vars.palette.*` — no hex anywhere else.
- **Strings:** `frontend/src/i18n/en.json` via `t()`. No hard-coded UI text in new screens.
- **Deviations** from the playbook: [docs/PLAYBOOK_DEVIATIONS.md](docs/PLAYBOOK_DEVIATIONS.md).
- **Bugs:** [BUGLOG.md](BUGLOG.md) (`VB-###`). Standing review backlog is VB-005.

## The VB law (enforced in code; `sara` audits it)
1. **No hard delete.** Soft delete (`is_active=false`) everywhere. The only hard deletes are
   `diagram_layout` (D-30) and `purge_project` (Q15, runs as `vb_owner`). The app role has no
   DELETE grant, so this fails at the database, not in review.
2. **Baselines are immutable** — every `baseline_*` table gets the `fn_reject_modification()`
   trigger, and shadows are **generated** by `services/baseline_shadow.py`, never hand-written.
3. **Audit columns, soft delete and `row_version` are born with every business table**
   (`models/base.py::AuditMixin`, `alembic/vb_ops.py::audit_columns`). `updated_at` is set by the
   `fn_set_updated_at()` trigger — never `onupdate=`. Stale `row_version` → 409.
4. **A process is `is_process`, never `level_no = 5`** (D-23). The literal is banned in code.
5. **Branch on behaviour, never on a code** — FR type and RACI (`code_master.behaviour_code`,
   D-27/Q7). `== 'INTERFACE'` against a type code is a finding.
6. **Derived values are never accepted from a request body**: `created_by`, `effort_days`,
   `exposure_score`, `row_version` increments, numbers.
7. **The bare word `role` is banned** in tables, models and routes: `org_role` vs
   `project_role_code`.
8. **One import pipeline** (`bulk.py`: validate → preview → commit) for every import, flow JSON
   included. **One canvas component** for process flow, DFD and ERD.
9. **Untrusted text renders as text.** `dangerouslySetInnerHTML` / `innerHTML` fail lint (§14.5).
10. **Every new table** is added to `models/__init__.py` (autogenerate only sees what is imported)
    and gets its migration **one per commit**, reversible; a destructive one pauses for Ben.

## Parallel sessions (up to ~20 a day)
- **One git worktree per slice.** Branch from `main`; merge back through review.
- **Migrations only on `main`, in order.** A slice branch that needs a table rebases onto the
  latest `main` before creating its migration, so revision ids never fork. Two slices never
  add migrations at the same time — coordinate on `main`.
- **This file is the shared rulebook.** A rule learned in one session lands here (via
  `rules-check-drift`) so the other nineteen follow it.

## Delegation
- **Schema changes → `apple`** before code. **`sara`** before any commit touching auth, access,
  grants, baselines, imports or the migration chain. **`test-runner` / `ui-verifier`** before
  claiming a change works. **`bug-hunter`** for a failure with an unknown cause.

## Landmines
1. `TRUNCATE app_user … CASCADE` also empties `code_master` (its audit columns reference
   `app_user`) — the test harness re-seeds after every wipe; do the same in any script.
2. `audit_event` is append-only by grant **and** trigger; even the owner role cannot UPDATE it.
3. `request.client.host` is not always an IP — `services/audit.py` stores only valid addresses.
4. `code_master.created_by` is nullable **only** because seeded library rows have no author.
5. Start Vite with the frontend folder as root (`npm run dev` from `frontend/`); run from the repo
   root it serves 404s.
