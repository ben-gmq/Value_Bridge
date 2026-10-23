"""Test harness. Runs against vb_test_db: migrations as vb_owner, the app as vb_app — so a
missing grant fails a test instead of hiding behind owner privileges."""
import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

_env = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
# pytest-xdist (`-n 4`): each worker runs against its own test database, `<TEST db>_<worker>` (e.g. vb_test_db_gw0),
# created beforehand by scripts/make_test_worker_dbs.sh — the suite wipes its database, so workers never share one.
_worker = os.environ.get("PYTEST_XDIST_WORKER")
_app_url, _owner_url = make_url(_env["TEST_DATABASE_URL"]), make_url(_env["TEST_MIGRATION_DATABASE_URL"])
# The session starts by downgrading the database to nothing (sara M3): refuse anything that is not one test database.
if "test" not in (_app_url.database or "") or _app_url.database != _owner_url.database:
    raise SystemExit(f"TEST_DATABASE_URL / TEST_MIGRATION_DATABASE_URL must name the same test database "
                     f"(got {_app_url.database!r} / {_owner_url.database!r}) — refusing to run.")


def _for_worker(url) -> str:
    return (url.set(database=f"{url.database}_{_worker}") if _worker else url).render_as_string(hide_password=False)


os.environ["DATABASE_URL"] = _for_worker(_app_url)
os.environ["MIGRATION_DATABASE_URL"] = _for_worker(_owner_url)
os.environ["ALLOWED_EMAIL_DOMAINS"] = "example.test"
os.environ["ALLOW_FIRST_RUN_SETUP"] = "true"
# Ben 2026-10-23 (docs/test_speed_proposal_2026-10-23.md, option A): every connection this test process opens — app,
# owner, alembic — commits without waiting for the disk. libpq reads PGOPTIONS per connection, so only these sessions
# change; the server, its other databases and the app's own setting do not. A crash can lose the last moment of test
# data (never corrupt it), and every run wipes it anyway. Measured: ~25-35% off the full run.
os.environ["PGOPTIONS"] = f"{os.environ.get('PGOPTIONS', '')} -c synchronous_commit=off".strip()
# slice 16 (S9): never a host's archive folders or identity; archive tests stamp and set their own temporary ones
for _k in ("VB_INSTANCE_ID", "VB_ARCHIVE_DIR", "VB_ARCHIVE_KEY_DIR"):
    os.environ[_k] = ""
os.environ.setdefault("JWT_SECRET_KEY", _env["JWT_SECRET_KEY"])
os.environ.setdefault("ROW_TOKEN_KEY", _env["ROW_TOKEN_KEY"])

import bcrypt  # noqa: E402

# Tests only (this file is loaded by pytest alone): the cheapest bcrypt cost, 4 rounds, for every hash the app makes
# under test — ~1 ms instead of ~200 ms, and the suite creates and logs in several users per test. The app's own
# cost (bcrypt's default, 12) is unchanged everywhere else; verify reads the cost from the hash it checks. Patched
# before any app module is imported, so the login timing equaliser's dummy hash is cheap here too.
_real_gensalt = bcrypt.gensalt
bcrypt.gensalt = lambda rounds=12, prefix=b"2b": _real_gensalt(4, prefix)

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from database import SessionLocal  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
OWNER_URL = os.environ["MIGRATION_DATABASE_URL"]
# Every component on: a test project behaves as a pre-7a project did (D-37 backfill, Q-9).
ALL_COMPONENTS = ["SOLUTION", "FUNCTION_REQUIREMENT", "APPLICATION", "EFFORT", "ISSUE", "TO_BE_DFD",
                  "AS_IS", "WBS", "BENEFIT", "RISK", "CHANGE_REQUEST", "PHASING"]
# D-70 (slice13_schema §2.8 "fixture risk"): the test projects keep today's D-38 rule on both charts, as every project
# existing at the 13b deploy does, so the freeze tests built on "trigger + output" keep their meaning. A new project
# with no dfd_rule in its body starts with the recommended set (tests/test_dfd_rule.py covers that default).
TODAYS_RULE = {"TO_BE": ["STARTED", "DATA_OUT"], "AS_IS": ["STARTED", "DATA_OUT"]}


# The seeded library (code lists and template contents). Seeded once per session through the real seed commands,
# copied into a side schema, and copied back after every wipe in one statement each — the same rows, ids included,
# as re-running the seeds after RESTART IDENTITY produced (Ben 2026-10-16: the suite took ~1 h, 2.8 s of every test
# was this re-seed).
LIBRARY = ("code_master", "project_template_component")       # in FK order
SNAPSHOT = "vb_test_snapshot"
_owner_engine = None


def owner_engine():
    global _owner_engine
    if _owner_engine is None:
        _owner_engine = create_engine(OWNER_URL)
    return _owner_engine


@pytest.fixture(scope="session", autouse=True)
def schema():
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    os.environ["VB_ALEMBIC_URL"] = OWNER_URL
    with owner_engine().begin() as c:
        drop_states(c)                                       # sara HIGH: no saved state outlives its session
    _step_through(cfg)
    _seed_library()
    with owner_engine().begin() as c:
        c.execute(text(f"DROP SCHEMA IF EXISTS {SNAPSHOT} CASCADE; CREATE SCHEMA {SNAPSHOT}"))
        for t in LIBRARY:
            c.execute(text(f"CREATE TABLE {SNAPSHOT}.{t} AS SELECT * FROM {t}"))
    yield
    with owner_engine().begin() as c:
        drop_states(c)
    owner_engine().dispose()


# Slice 17 (test-only deviation, beside the other grant bypasses on VB-005): a test world records its first admin's grant
# (0078's trigger), and 0076's downgrade rightly refuses to drop grant records it did not write. A migration test steps
# below 0076 to prove an OLDER migration, so a downgrade that PASSES THROUGH 0076 first empties the grant record — and
# only that one (sara MEDIUM-1: a 0078-or-later downgrade still meets the real rows). 0076's own refusal test keeps them
# (`keep_grants`). Caveat (sara LOW-2): going back up through 0076 rebuilds the grants from the audit history, so their
# dates become the audit events' and a LEGACY asker the event's actor — a test that steps down and up must not rely on
# grant ages or makers afterwards.
_real_downgrade = command.downgrade
_KEEP_GRANTS = {"on": False}


def _crosses_0076(cfg, revision) -> bool:
    from alembic.script import ScriptDirectory
    with owner_engine().connect() as c:
        if not c.execute(text("SELECT to_regclass('public.platform_admin_grant')")).scalar():
            return False
        current = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
    script = ScriptDirectory.from_config(cfg)
    target = {"-1": script.get_revision(current).down_revision, "base": None}.get(revision, revision)
    removed = [s.revision for s in script.iterate_revisions(current, target)]       # current down to, not incl., target
    return "0076" in removed


def _downgrade(cfg, revision, *a, **kw):
    if not _KEEP_GRANTS["on"] and _crosses_0076(cfg, revision):
        with owner_engine().begin() as c:
            c.execute(text("TRUNCATE platform_admin_grant"))
    return _real_downgrade(cfg, revision, *a, **kw)


command.downgrade = _downgrade


@pytest.fixture
def keep_grants():
    """For a test that proves 0076's downgrade refusal: grant records stay through the downgrade."""
    _KEEP_GRANTS["on"] = True
    yield
    _KEEP_GRANTS["on"] = False


def _step_through(cfg) -> None:
    """Every migration down to base and back up to head, ONE REVISION PER COMMAND. alembic/env.py runs a multi-step
    command in a single transaction, so `downgrade base` held a lock on every table and index at once; four xdist
    workers doing it together overflowed the server's shared lock table ("out of shared memory", slice 14). Each
    step now commits, holding only its own table's locks. Same revisions, same order, same coverage."""
    import sys
    from alembic.script import ScriptDirectory
    if str(BACKEND / "alembic") not in sys.path:                     # the revisions import vb_ops, as env.py allows
        sys.path.insert(0, str(BACKEND / "alembic"))
    chain = [s.revision for s in ScriptDirectory.from_config(cfg).walk_revisions()]       # head first
    with owner_engine().connect() as c:
        current = c.execute(text("SELECT to_regclass('public.alembic_version') IS NOT NULL")).scalar() and \
            c.execute(text("SELECT version_num FROM alembic_version")).scalar()
    if current:
        # A run killed before its teardown leaves rows behind, and the downgrades that guard kept records (purge
        # requests 0072/0073, grant records 0076) rightly refuse to drop them. This is a test database whose every
        # table goes on the way down anyway: start from empty.
        with owner_engine().begin() as c:
            tables = c.execute(text("SELECT string_agg(quote_ident(tablename), ', ') FROM pg_tables "
                                    "WHERE schemaname = 'public' AND tablename <> 'alembic_version'")).scalar()
            if tables:
                c.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    for _ in chain[chain.index(current):] if current in chain else []:
        command.downgrade(cfg, "-1")
    for rev in reversed(chain):
        command.upgrade(cfg, rev)


def _seed_library():
    from seeds.seed_code_master import seed
    from seeds.seed_project_templates import seed as seed_templates
    with SessionLocal() as s:
        seed(s)
        seed_templates(s)


def _fingerprint(c, schema_name: str, t: str) -> str:
    return c.execute(text(f"SELECT md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) "
                          f"FROM {schema_name}.{t} x")).scalar()


def _dirty_tables(c) -> set[str]:
    """Every non-library table holding a row or whose identity sequence has been drawn from (a rolled-back insert
    still advances it), so a wipe restarts exactly what the test touched and the next test sees the same fresh ids
    the full wipe gave. The library counts as dirty when its rows differ from the snapshot."""
    tables = [r[0] for r in c.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'"))
        if r[0] not in LIBRARY]
    probe = " UNION ALL ".join(f"SELECT '{t}' WHERE EXISTS (SELECT 1 FROM public.{t})" for t in tables)
    dirty = {r[0] for r in c.execute(text(probe))}
    dirty |= {r[0] for r in c.execute(text(
        "SELECT d.refobjid::regclass::text FROM pg_sequences s "
        "JOIN pg_class q ON q.relname = s.sequencename AND q.relnamespace = 'public'::regnamespace "
        "JOIN pg_depend d ON d.objid = q.oid AND d.deptype IN ('a', 'i') "
        "WHERE s.schemaname = 'public' AND s.last_value IS NOT NULL")) if r[0] not in LIBRARY}
    dirty |= {t for t in LIBRARY if _fingerprint(c, "public", t) != _fingerprint(c, SNAPSHOT, t)}
    return dirty


def _restore_library(c) -> None:
    """Copy the snapshot back with its ids, and leave each identity where the seed command left it (next = max + 1)."""
    for t in LIBRARY:
        cols = ", ".join(r[0] for r in c.execute(text(
            "SELECT s.column_name FROM information_schema.columns s JOIN information_schema.columns p "
            "ON p.table_schema = 'public' AND p.table_name = s.table_name AND p.column_name = s.column_name "
            "WHERE s.table_schema = :s AND s.table_name = :t AND p.is_generated <> 'ALWAYS' "
            "ORDER BY s.ordinal_position"), {"s": SNAPSHOT, "t": t}))
        c.execute(text(f"INSERT INTO {t} ({cols}) OVERRIDING SYSTEM VALUE SELECT {cols} FROM {SNAPSHOT}.{t}"))
    _reset_library_ids(c)


# The one reference cycle in the schema: a project's own code-list overrides point at the project
# (code_master.project_id), and the project points at its status code (project.status_code_id). The wipe breaks it by
# deleting the project-tier codes just before the projects (every row using one is the project's, so already gone).
CODE_CYCLE = ("code_master", "project")


def _delete_order(c, tables: set[str]) -> list[str] | None:
    """Children before parents among `tables` (FKs from the catalog, self-references and CODE_CYCLE's
    code_master → project edge ignored); None on any other cycle."""
    edges = [e for e in c.execute(text(
        "SELECT conrelid::regclass::text, confrelid::regclass::text FROM pg_constraint "
        "WHERE contype = 'f' AND connamespace = 'public'::regnamespace")).all() if tuple(e) != CODE_CYCLE]
    parents = {t: {p for ch, p in edges if ch == t and p in tables and p != t} for t in tables}
    order, left = [], set(tables)
    while left:
        leaves = sorted(t for t in left if not any(t in parents[o] for o in left if o != t))   # nothing left points here
        if not leaves:
            return None
        order += leaves
        left -= set(leaves)
    return order


@pytest.fixture(autouse=True)
def clean():
    """Wipe data between tests as the owner (the app role cannot DELETE everywhere, by design).

    Only what the test touched is wiped, by DELETE children-first, and its identities restarted, giving the next test
    the same fresh ids a full wipe gave. Ben 2026-10-23 (docs/test_speed_proposal_2026-10-23.md, option C): TRUNCATE
    made PostgreSQL force every emptied table and index file to disk, one after another — 645 ms for the baseline group
    alone, 674 s of a full run — where DELETE of the same rows takes ~1 ms. The tables whose own triggers refuse DELETE
    (audit_event, the baseline header and shadows, the purge and grant records, vb_instance) have those triggers off
    for this one transaction only, as the owner, on a test database; nothing else sees them off. A library the test
    changed (sara M1) is deleted with the rest and copied back from its snapshot. TRUNCATE remains only for a cycle of
    references among the touched tables. The wipe then proves itself: every table empty, every identity restarted, the
    library equal to its snapshot — or the run stops."""
    yield
    with owner_engine().begin() as c:
        c.execute(text("SET LOCAL lock_timeout = '10s'"))           # sara LOW: a held lock fails, never hangs
        _wipe(c)


def _wipe(c) -> None:
    """clean()'s wipe, inside the caller's owner transaction (restore_state uses it too)."""
    dirty = _dirty_tables(c)
    if not dirty:
        return
    library = dirty & set(LIBRARY)
    tables = dirty | (set(LIBRARY) if library else set())
    order = _delete_order(c, tables)
    if order is None:                                    # an FK cycle among the touched tables: the full wipe
        c.execute(text(f"TRUNCATE {', '.join(sorted(tables | set(LIBRARY)))} RESTART IDENTITY CASCADE"))
        _restore_library(c)
    else:
        guards = _own_triggers(c, tables, on_delete=True)
        for t, g in guards:
            c.execute(text(f"ALTER TABLE {t} DISABLE TRIGGER {g}"))
        for t in order:
            if t == "project" and "code_master" in tables:              # CODE_CYCLE: the overrides go first
                c.execute(text("DELETE FROM code_master WHERE project_id IS NOT NULL"))
            c.execute(text(f"DELETE FROM {t}"))
        for t, g in guards:
            c.execute(text(f"ALTER TABLE {t} ENABLE TRIGGER {g}"))
        for (seq,) in c.execute(text(
                "SELECT pg_get_serial_sequence(a.attrelid::regclass::text, a.attname) FROM pg_attribute a "
                "WHERE a.attidentity <> '' AND NOT a.attisdropped AND a.attnum > 0 "
                "AND a.attrelid::regclass::text = ANY(:t)"), {"t": sorted(tables - set(LIBRARY))}).all():
            c.execute(text(f"ALTER SEQUENCE {seq} RESTART"))
        if library:
            _restore_library(c)
        else:
            _reset_library_ids(c)                        # sara L1: a rolled-back library insert used ids too
    left = _dirty_tables(c)
    if left:
        raise RuntimeError(f"the wipe left rows or used ids in {sorted(left)}: the next test would not start fresh")


def _own_triggers(c, tables, on_delete: bool = False) -> list[tuple[str, str]]:
    """The tables' own (not FK) triggers — only those that fire on DELETE when `on_delete`."""
    return [tuple(r) for r in c.execute(text(
        "SELECT c.relname, t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
        "WHERE c.relnamespace = 'public'::regnamespace AND NOT t.tgisinternal AND c.relname = ANY(:t) "
        "AND t.tgenabled = 'O' "                             # sara LOW: ENABLE puts back 'O'; touch nothing else
        "AND (NOT :d OR (t.tgtype & 8) <> 0) ORDER BY 1, 2"), {"t": sorted(tables), "d": on_delete})]


# ---- a fixture built once per worker, restored for every later test (Ben 2026-10-23, test speed) ----------------------
# A fixture whose world takes seconds to build through the services (test_purge_run's showcase: ~8-12 s, 31 tests)
# builds it in its first test, saves every row and id counter beside the database, and in every later test restores
# them in place of the rebuild. The restore proves itself: every saved table row-for-row equal to the copy (md5 of each
# row), no other table holding a row, every id counter where the build left it — or the test stops. Only the owner, on a
# test database, inside one transaction, with the tables' own triggers off for the copy back (the guards and the
# updated_at stamp would refuse or alter it; the FK checks stay on). The copies are named `s_<table>` (sara HIGH: a
# migration test that looks a table up by name in any schema must never find a copy), and every vb_test_state_*
# schema is dropped at the start and end of a session. A saved state must hold nothing near a time limit: its
# timestamps are as old as the build, up to one worker's run (sara LOW).
STATE_PREFIX = "vb_test_state_"
_STATES: dict[str, list[str]] = {}


def drop_states(c) -> None:
    for (s,) in c.execute(text("SELECT nspname FROM pg_namespace WHERE nspname LIKE :p"),
                          {"p": STATE_PREFIX.replace("_", r"\_") + "%"}).all():
        c.execute(text(f"DROP SCHEMA {s} CASCADE"))
    _STATES.clear()


def _cols(c, schema_name: str, copy: str, t: str) -> str:
    """The columns the copy `schema_name.copy` shares with public.t, generated ones left out."""
    return ", ".join(r[0] for r in c.execute(text(
        "SELECT s.column_name FROM information_schema.columns s JOIN information_schema.columns p "
        "ON p.table_schema = 'public' AND p.table_name = :t AND p.column_name = s.column_name "
        "WHERE s.table_schema = :s AND s.table_name = :copy AND p.is_generated <> 'ALWAYS' "
        "ORDER BY s.ordinal_position"), {"s": schema_name, "copy": copy, "t": t}))


def has_state(name: str) -> bool:
    return name in _STATES


def save_state(name: str) -> None:
    """Save every non-library row (and the project-tier code overrides) and every id counter, once per worker."""
    s = f"{STATE_PREFIX}{name}"
    with owner_engine().begin() as c:
        # sara MEDIUM: a restore puts the library back to its snapshot, so a build that changed it cannot be saved.
        changed = [t for t in LIBRARY if _fingerprint_shared(c, "public", t) != _fingerprint_shared(c, SNAPSHOT, t)]
        if changed:
            raise RuntimeError(f"state {name}: the build changed the shared library ({changed}); it cannot be saved")
        tables = sorted(r[0] for r in c.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'"))
            if r[0] not in LIBRARY)
        c.execute(text(f"DROP SCHEMA IF EXISTS {s} CASCADE; CREATE SCHEMA {s}"))
        kept = []
        for t in tables:
            if c.execute(text(f"SELECT EXISTS (SELECT 1 FROM public.{t})")).scalar():
                c.execute(text(f"CREATE TABLE {s}.s_{t} AS SELECT * FROM public.{t}"))
                kept.append(t)
        c.execute(text(f"CREATE TABLE {s}.s_code_master AS SELECT * FROM public.code_master WHERE project_id IS NOT NULL"))
        c.execute(text(f"CREATE TABLE {s}.s_sequences AS SELECT schemaname || '.' || sequencename AS seq, last_value "
                       "FROM pg_sequences WHERE schemaname = 'public'"))
    _STATES[name] = kept


def _fingerprint_shared(c, schema_name: str, t: str) -> str:
    """The library's shared rows only: a project's own code overrides are part of a saved state, not the library."""
    where = " WHERE x.project_id IS NULL" if t == "code_master" else ""
    return c.execute(text(f"SELECT md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) "
                          f"FROM {schema_name}.{t} x{where}")).scalar()


def restore_state(name: str) -> None:
    s, tables = f"{STATE_PREFIX}{name}", _STATES[name]
    with owner_engine().begin() as c:
        c.execute(text("SET LOCAL lock_timeout = '10s'"))           # sara LOW: a held lock fails, never hangs
        _wipe(c)
        order = _delete_order(c, set(tables) | {"code_master"})
        if order is None:
            raise RuntimeError(f"state {name}: its tables form a reference cycle; it cannot be restored")
        triggers = _own_triggers(c, set(tables) | {"code_master"})
        for t, g in triggers:
            c.execute(text(f"ALTER TABLE {t} DISABLE TRIGGER {g}"))
        for t in reversed(order):                            # parents first
            if t in tables:
                cols = _cols(c, s, f"s_{t}", t)
                c.execute(text(f"INSERT INTO public.{t} ({cols}) OVERRIDING SYSTEM VALUE SELECT {cols} FROM {s}.s_{t}"))
            if t == "project":                               # CODE_CYCLE: the overrides after their projects
                cols = _cols(c, s, "s_code_master", "code_master")
                c.execute(text(f"INSERT INTO public.code_master ({cols}) OVERRIDING SYSTEM VALUE "
                               f"SELECT {cols} FROM {s}.s_code_master"))
        for t, g in triggers:
            c.execute(text(f"ALTER TABLE {t} ENABLE TRIGGER {g}"))
        for seq, last in c.execute(text(f"SELECT seq, last_value FROM {s}.s_sequences")).all():
            c.execute(text("SELECT setval(:q, :v, :called)"), {"q": seq, "v": last or 1, "called": last is not None})
        # The proof.
        for t in tables + ["code_master"]:
            where = " WHERE project_id IS NOT NULL" if t == "code_master" else ""
            diff = c.execute(text(
                f"SELECT count(*) FROM ((SELECT md5(x::text) FROM public.{t} x{where} EXCEPT ALL "
                f"SELECT md5(y::text) FROM {s}.s_{t} y) UNION ALL (SELECT md5(y::text) FROM {s}.s_{t} y EXCEPT ALL "
                f"SELECT md5(x::text) FROM public.{t} x{where})) d")).scalar()
            if diff:
                raise RuntimeError(f"state {name}: {t} differs from its saved copy in {diff} row(s)")
        others = [r[0] for r in c.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'"))
            if r[0] not in tables and r[0] not in LIBRARY]
        extra = [t for t in others if c.execute(text(f"SELECT EXISTS (SELECT 1 FROM public.{t})")).scalar()]
        if extra:
            raise RuntimeError(f"state {name}: rows outside the saved copy in {sorted(extra)}")
        moved = c.execute(text(
            f"SELECT count(*) FROM {s}.s_sequences v JOIN pg_sequences p "
            "ON p.schemaname || '.' || p.sequencename = v.seq WHERE p.last_value IS DISTINCT FROM v.last_value")).scalar()
        if moved:
            raise RuntimeError(f"state {name}: {moved} id counter(s) differ from the saved copy")


def _reset_library_ids(c) -> None:
    """Each library identity back to max + 1 (where the seed left it), whatever a test drew from it."""
    for t in LIBRARY:
        for col, seq in c.execute(text(
                "SELECT a.attname, pg_get_serial_sequence(:t, a.attname) FROM pg_attribute a "
                "WHERE a.attrelid = CAST(:t AS regclass) AND a.attidentity <> '' AND NOT a.attisdropped "
                "AND a.attnum > 0"), {"t": t}).all():
            c.execute(text(f"SELECT setval(:q, max({col}), true) FROM {t} HAVING count(*) > 0"), {"q": seq})


# Ben 2026-10-16 (pytest.ini): the everyday `pytest` leaves these out; `pytest -m ""` (before every merge) runs them.
# Chosen by measured duration, never by importance: every one still runs before anything merges.
SLOW_FILES = ("test_migration_",)
SLOW_TESTS = ()


@pytest.hookimpl(tryfirst=True)              # before -m filters on the mark
def pytest_collection_modifyitems(items):
    for item in items:
        if item.path.name.startswith(SLOW_FILES) or item.nodeid.split("::", 1)[-1] in SLOW_TESTS:
            item.add_marker(pytest.mark.slow)


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


# ---- world-building helpers ---------------------------------------------------------------

PW = "correct-horse-battery"


def login(client, email, remember=False) -> dict:
    r = client.post("/auth/login", json={"email": email, "password": PW, "remember_me": remember})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def world(client):
    """An admin, a client with a program of two projects plus one standalone project, and four
    staff users (D-40): owner, editor and outsider are USERs, reviewer a VIEWER. Every project is
    unrestricted; a test that needs a wall restricts one (restrict())."""
    r = client.post("/auth/setup", json={"email": "admin@example.test", "display_name": "Admin",
                                         "password": PW})
    assert r.status_code == 201, r.text
    admin = login(client, "admin@example.test")
    users = {}
    for name in ("owner", "editor", "reviewer", "outsider"):
        r = client.post("/api/v1/users", headers=admin, json={
            "email": f"{name}@example.test", "display_name": name.title(), "initial_password": PW,
            "user_kind": "VIEWER" if name == "reviewer" else "USER"})
        assert r.status_code == 201, r.text
        users[name] = r.json()["app_user_id"]
    c = client.post("/api/v1/clients", headers=admin,
                    json={"client_code": "ACME", "client_name": "Acme"}).json()
    other = client.post("/api/v1/clients", headers=admin,
                        json={"client_code": "BETA", "client_name": "Beta"}).json()
    prog = client.post("/api/v1/programs", headers=admin, json={
        "client_id": c["client_id"], "program_code": "CSR27", "program_name": "Core renewal"}).json()

    def project(code, program_id=None, client_id=c["client_id"]):
        r = client.post("/api/v1/projects", headers=admin, json={
            "client_id": client_id, "project_code": code, "project_name": code.title(),
            "program_id": program_id, "component_codes": ALL_COMPONENTS, "is_restricted": False,
            "dfd_rule": TODAYS_RULE})
        assert r.status_code == 201, r.text
        return r.json()["project_id"]

    return {
        "admin": admin, "users": users, "client_id": c["client_id"],
        "other_client_id": other["client_id"], "program_id": prog["program_id"],
        "p_sales": project("SALES", prog["program_id"]),
        "p_fin": project("FIN", prog["program_id"]),
        "p_solo": project("SOLO"),
        "p_beta": project("BETA1", client_id=other["client_id"]),
    }


def restrict(client, admin, project_id, members: dict[int, str] | None = None) -> None:
    """Make a project restricted (OR-6) with these members {user_id: EDIT|VIEW}: preview, confirm."""
    for uid, level in (members or {}).items():
        r = client.post(f"/api/v1/projects/{project_id}/members", headers=admin,
                        json={"user_id": uid, "access_level": level})
        assert r.status_code == 201, r.text
    url = f"/api/v1/projects/{project_id}/restriction"
    prev = client.put(url, headers=admin, json={"is_restricted": True})
    assert prev.status_code == 200, prev.text
    r = client.put(url, headers=admin, json={"is_restricted": True, "confirm_hash": prev.json()["confirm_hash"]})
    assert r.status_code == 200 and r.json()["applied"], r.text
