"""Numbering, database grants and declarative constraints, auth rules, ingress limits."""
import os
from concurrent.futures import ThreadPoolExecutor

import jwt
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from database import SessionLocal
from services import numbering
from tests.conftest import PW, login

APP_URL = os.environ["DATABASE_URL"]


# ---- numbering (§7.1, R2-D14) ---------------------------------------------------------

def test_create_project_seeds_all_ten_series(db, world):
    n = db.execute(text("SELECT count(*) FROM project_sequence WHERE project_id = :p"),
                   {"p": world["p_solo"]}).scalar()
    assert n == 10


def test_next_number_is_unique_under_concurrency(world):
    pid = world["p_solo"]

    def mint(_):
        with SessionLocal() as s:
            n = numbering.next_number(s, pid, "BR")
            s.commit()
            return n

    with ThreadPoolExecutor(max_workers=8) as pool:
        numbers = list(pool.map(mint, range(40)))
    assert len(set(numbers)) == 40
    assert sorted(numbers)[0] == "BR-0001" and sorted(numbers)[-1] == "BR-0040"


def test_missing_series_raises_never_inserts(db):
    with pytest.raises(numbering.MissingSequence):
        numbering.next_number(db, 999_999, "BR")


# ---- database grants (§6.6, R2-S9) ------------------------------------------------------

# §6.6 / D-30: the only table the app may hard-delete from. import_row joins it when it lands.
HARD_DELETE_TABLES = {"diagram_layout"}


def test_app_role_deletes_only_layout_and_audit_is_append_only():
    eng = create_engine(APP_URL)
    with eng.connect() as c:
        rows = c.execute(text(
            "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'vb_app'")).all()
    eng.dispose()
    privs = {(t, p) for t, p in rows}
    assert {t for t, p in privs if p == "DELETE"} == HARD_DELETE_TABLES, \
        "vb_app may DELETE only from the documented hard-delete tables"
    assert not [t for t, p in privs if p == "TRUNCATE"], "vb_app must hold no TRUNCATE"
    assert ("audit_event", "UPDATE") not in privs
    assert ("audit_event", "INSERT") in privs


def test_app_role_cannot_delete_even_by_direct_sql(world):
    eng = create_engine(APP_URL)
    with pytest.raises(DBAPIError):
        with eng.begin() as c:
            c.execute(text("DELETE FROM project WHERE project_id = :p"), {"p": world["p_solo"]})
    with pytest.raises(DBAPIError):                 # soft-deleted, beside the D-30 exception
        with eng.begin() as c:
            c.execute(text("DELETE FROM bfc_node_flow WHERE project_id = :p"), {"p": world["p_solo"]})
    eng.dispose()


def test_retired_code_categories_stay_retired(db):
    """S2-1: FLOW_TYPE left the library; the seed retires it and a re-run changes nothing."""
    from seeds.seed_code_master import LIBRARY, RETIRED_CATEGORIES, seed
    from services import code_master
    assert not {c for c, _, _ in LIBRARY} & set(RETIRED_CATEGORIES)
    seed(db)
    assert code_master.resolve(db, None, "FLOW_TYPE") == []
    assert seed(db) == (0, 0)


# ---- declarative constraints (§5.3) -----------------------------------------------------

def test_second_live_grant_refused_by_database(db, world):
    """The partial unique index is the backstop behind grant_access's 409."""
    role = db.execute(text("SELECT code_id FROM code_master WHERE category='PROJECT_ROLE' "
                           "AND code='EDITOR' AND project_id IS NULL")).scalar()
    uid, admin = world["users"]["editor"], world["users"]["owner"]
    sql = text("INSERT INTO user_access_grant (app_user_id, project_id, project_role_code_id, "
               "granted_by_user_id, created_by) VALUES (:u, :p, :r, :a, :a)")
    db.execute(sql, {"u": uid, "p": world["p_solo"], "r": role, "a": admin})
    with pytest.raises(IntegrityError):
        db.execute(sql, {"u": uid, "p": world["p_fin"], "r": role, "a": admin})
    db.rollback()


def test_project_cannot_join_another_clients_program(db, world):
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE project SET program_id = :g WHERE project_id = :p"),
                   {"g": world["program_id"], "p": world["p_beta"]})
    db.rollback()


def test_program_with_active_projects_cannot_be_retired(db, world):
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE program SET is_active = false WHERE program_id = :g"),
                   {"g": world["program_id"]})
    db.rollback()


def test_audit_event_update_rejected_by_trigger(world):
    owner_eng = create_engine(os.environ["MIGRATION_DATABASE_URL"])
    with pytest.raises(DBAPIError):
        with owner_eng.begin() as c:        # even the owner role is stopped by the trigger
            c.execute(text("UPDATE audit_event SET event_type = 'X'"))
    owner_eng.dispose()


# ---- auth (§7.10, D-11, S4) -------------------------------------------------------------

def test_setup_is_one_shot(client, world):
    r = client.post("/auth/setup", json={"email": "second@example.test", "display_name": "X",
                                         "password": PW})
    assert r.status_code == 409
    assert client.get("/auth/setup").json() == {"setup_required": False}


def test_login_failure_message_does_not_leak(client, world):
    a = client.post("/auth/login", json={"email": "nobody@example.test", "password": PW})
    b = client.post("/auth/login", json={"email": "editor@example.test", "password": "wrong-pass"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_token_carries_subject_only(client, world):
    r = client.post("/auth/login", json={"email": "admin@example.test", "password": PW})
    claims = jwt.decode(r.json()["access_token"], options={"verify_signature": False})
    assert set(claims) == {"sub", "exp"}


def test_non_ftc_address_refused(client, world):
    r = client.post("/api/v1/users", headers=world["admin"], json={
        "email": "someone@client.example", "display_name": "Client", "initial_password": PW})
    assert r.status_code == 422


def test_non_admin_cannot_list_users(client, world):
    editor = login(client, "editor@example.test")
    assert client.get("/api/v1/users", headers=editor).status_code == 403


def test_password_hash_never_serialised(client, world):
    body = client.get("/api/v1/users", headers=world["admin"]).text
    assert "password" not in body


# ---- optimistic concurrency (D-6) and ingress (R2-S8) -----------------------------------

def test_stale_row_version_is_409(client, world):
    url = f"/api/v1/projects/{world['p_solo']}"
    p = client.get(url, headers=world["admin"]).json()
    ok = client.patch(url, headers=world["admin"],
                      json={"row_version": p["row_version"], "project_name": "Renamed"})
    assert ok.status_code == 200 and ok.json()["row_version"] == p["row_version"] + 1
    stale = client.patch(url, headers=world["admin"],
                         json={"row_version": p["row_version"], "project_name": "Again"})
    assert stale.status_code == 409


def test_oversized_body_is_413_before_the_handler(client, world):
    big = "x" * 1_100_000
    r = client.post("/auth/login", content=big, headers={"Content-Type": "application/json"})
    assert r.status_code == 413


# ---- sara fixes -----------------------------------------------------------------------------

def test_setup_is_404_when_switched_off(client, monkeypatch):
    """H1: with ALLOW_FIRST_RUN_SETUP off (the cloud default) setup does not exist."""
    from config import get_settings
    monkeypatch.setattr(get_settings(), "allow_first_run_setup", False)
    assert client.get("/auth/setup").json() == {"setup_required": False}
    r = client.post("/auth/setup", json={"email": "a@example.test", "display_name": "A", "password": PW})
    assert r.status_code == 404


def test_api_docs_are_off_by_default(client):
    """M9."""
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_validation_errors_are_one_detail_string(client, world):
    """M5: the frontend reads `detail` only — it must be a sentence, not a list."""
    r = client.post("/api/v1/clients", headers=world["admin"], json={"client_code": "", "client_name": "X"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    assert "client_code" in r.json()["detail"]


def test_null_name_and_reversed_dates_are_422(client, world):
    """L5."""
    url = f"/api/v1/projects/{world['p_solo']}"
    p = client.get(url, headers=world["admin"]).json()
    assert client.patch(url, headers=world["admin"], json={
        "row_version": p["row_version"], "project_name": None}).status_code == 422
    assert client.patch(url, headers=world["admin"], json={
        "row_version": p["row_version"], "start_date": "2027-03-01", "end_date": "2027-01-01"}).status_code == 422


def test_overlong_email_is_rejected(client, world):
    """M10."""
    r = client.post("/auth/login", json={"email": "a" * 300 + "@example.test", "password": PW})
    assert r.status_code == 422
