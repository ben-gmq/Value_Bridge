"""Test harness. Runs against vb_test_db: migrations as vb_owner, the app as vb_app — so a
missing grant fails a test instead of hiding behind owner privileges."""
import os
from pathlib import Path

from dotenv import dotenv_values

_env = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
os.environ["DATABASE_URL"] = _env["TEST_DATABASE_URL"]
os.environ["MIGRATION_DATABASE_URL"] = _env["TEST_MIGRATION_DATABASE_URL"]
os.environ["ALLOWED_EMAIL_DOMAINS"] = "example.test"
os.environ["ALLOW_FIRST_RUN_SETUP"] = "true"
os.environ.setdefault("JWT_SECRET_KEY", _env["JWT_SECRET_KEY"])
os.environ.setdefault("ROW_TOKEN_KEY", _env["ROW_TOKEN_KEY"])

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
                  "AS_IS", "WBS", "BENEFIT", "RISK", "CHANGE_REQUEST"]
# D-70 (slice13_schema §2.8 "fixture risk"): the test projects keep today's D-38 rule on both charts, as every project
# existing at the 13b deploy does, so the freeze tests built on "trigger + output" keep their meaning. A new project
# with no dfd_rule in its body starts with the recommended set (tests/test_dfd_rule.py covers that default).
TODAYS_RULE = {"TO_BE": ["STARTED", "DATA_OUT"], "AS_IS": ["STARTED", "DATA_OUT"]}
DATA_TABLES = ("audit_event", "user_access_grant", "project_sequence", "project", "program",
               "client", "app_user")


@pytest.fixture(scope="session", autouse=True)
def schema():
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    os.environ["VB_ALEMBIC_URL"] = OWNER_URL
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    _seed_library()
    yield


def _seed_library():
    from seeds.seed_code_master import seed
    from seeds.seed_project_templates import seed as seed_templates
    with SessionLocal() as s:
        seed(s)
        seed_templates(s)


@pytest.fixture(autouse=True)
def clean():
    """Wipe data between tests as the owner (the app role cannot TRUNCATE, by design)."""
    yield
    eng = create_engine(OWNER_URL)
    with eng.begin() as c:
        # CASCADE also empties code_master, project-scoped rows included (its audit columns reference
        # app_user), together with every row that references a code — so the library is re-seeded
        # after every wipe. (A DELETE of project codes *before* this failed once FRs used a project
        # FR type, Slice 6b-2; it is not needed at all.)
        c.execute(text(f"TRUNCATE {', '.join(DATA_TABLES)} RESTART IDENTITY CASCADE"))
    eng.dispose()
    _seed_library()


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
