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
    _step_through(cfg)
    _seed_library()
    with owner_engine().begin() as c:
        c.execute(text(f"DROP SCHEMA IF EXISTS {SNAPSHOT} CASCADE; CREATE SCHEMA {SNAPSHOT}"))
        for t in LIBRARY:
            c.execute(text(f"CREATE TABLE {SNAPSHOT}.{t} AS SELECT * FROM {t}"))
    yield
    owner_engine().dispose()


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


def _delete_order(c, tables: set[str]) -> list[str] | None:
    """Children before parents among `tables` (FKs from the catalog, self-references ignored); None on a cycle."""
    edges = c.execute(text(
        "SELECT conrelid::regclass::text, confrelid::regclass::text FROM pg_constraint "
        "WHERE contype = 'f' AND connamespace = 'public'::regnamespace")).all()
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
    """Wipe data between tests as the owner (the app role cannot TRUNCATE or DELETE everywhere, by design).

    Only what the test touched is wiped: TRUNCATE ... CASCADE from app_user reaches every table (they all carry audit
    columns), which cost ~1.5-3.5 s per test even when empty. So the append-only tables (audit_event, the baseline
    header and shadows — their triggers refuse DELETE) are truncated as one group, the other touched tables are
    DELETEd children-first, and their identities restarted, giving the next test the same fresh ids the full wipe
    gave. The library is copied back from its snapshot only when the test changed it."""
    yield
    with owner_engine().begin() as c:
        dirty = _dirty_tables(c)
        if not dirty:
            return
        frozen = {t for t in dirty if t == "audit_event" or t == "baseline" or t.startswith("baseline_")}
        if frozen - {"audit_event"}:
            frozen |= {r[0] for r in c.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'baseline%'"))}
        if frozen:
            c.execute(text(f"TRUNCATE {', '.join(sorted(frozen))} RESTART IDENTITY CASCADE"))   # sara M2: a future FK to baseline
        rest = dirty - frozen
        # The library changed (sara M1), or the touched tables form an FK cycle: the full wipe, then the snapshot back.
        order = None if rest & set(LIBRARY) else _delete_order(c, rest)
        if order is None:
            c.execute(text(f"TRUNCATE {', '.join(sorted(rest | set(LIBRARY)))} RESTART IDENTITY CASCADE"))
            _restore_library(c)
            return
        for t in order:
            c.execute(text(f"DELETE FROM {t}"))
        for (seq,) in c.execute(text(
                "SELECT pg_get_serial_sequence(a.attrelid::regclass::text, a.attname) FROM pg_attribute a "
                "WHERE a.attidentity <> '' AND NOT a.attisdropped AND a.attnum > 0 "
                "AND a.attrelid::regclass::text = ANY(:t)"), {"t": sorted(rest)}).all():
            c.execute(text(f"ALTER SEQUENCE {seq} RESTART"))
        _reset_library_ids(c)                                # sara L1: a rolled-back library insert used ids too


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
