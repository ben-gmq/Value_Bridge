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
DATA_TABLES = ("audit_event", "user_access_grant", "project_sequence", "project", "program",
               "client", "app_user")


@pytest.fixture(scope="session", autouse=True)
def schema():
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    os.environ["VB_ALEMBIC_URL"] = OWNER_URL
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    from seeds.seed_code_master import seed
    with SessionLocal() as db:
        seed(db)
    yield


@pytest.fixture(autouse=True)
def clean():
    """Wipe data between tests as the owner (the app role cannot TRUNCATE, by design)."""
    yield
    eng = create_engine(OWNER_URL)
    with eng.begin() as c:
        c.execute(text("DELETE FROM code_master WHERE project_id IS NOT NULL"))
        # CASCADE also empties code_master (its audit columns reference app_user), so the
        # library is re-seeded after every wipe.
        c.execute(text(f"TRUNCATE {', '.join(DATA_TABLES)} RESTART IDENTITY CASCADE"))
    eng.dispose()
    from seeds.seed_code_master import seed
    with SessionLocal() as s:
        seed(s)


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
    """An admin, a client with a program of two projects plus one standalone project, and
    four users with no grants yet."""
    r = client.post("/auth/setup", json={"email": "admin@example.test", "display_name": "Admin",
                                         "password": PW})
    assert r.status_code == 201, r.text
    admin = login(client, "admin@example.test")
    users = {}
    for name in ("owner", "editor", "reviewer", "outsider"):
        r = client.post("/api/v1/users", headers=admin, json={
            "email": f"{name}@example.test", "display_name": name.title(), "initial_password": PW})
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
            "program_id": program_id})
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
