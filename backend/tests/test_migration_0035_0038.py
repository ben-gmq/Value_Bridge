"""The D-40 data steps on real grant data (sara 7b M1): 0035 user kinds, 0037 the grant copy, 0038 the
soft revoke with its audit rows and the revoked privilege. The suite's schema fixture migrates an empty
database, so without this the one-way change of who sees what would run on live data untested.

Steps the test database back to 0034, seeds grants as the owner, upgrades to head, and asserts."""
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from tests.conftest import BACKEND, OWNER_URL


def _cfg() -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    os.environ["VB_ALEMBIC_URL"] = OWNER_URL
    return cfg


def _seed(c) -> dict:
    one = lambda sql, **kw: c.execute(text(sql), kw).scalar_one()  # noqa: E731
    user = lambda email, admin=False, by=None: one(  # noqa: E731
        "INSERT INTO app_user (email, password_hash, display_name, is_platform_admin, created_by) "
        "VALUES (:e, 'x', :e, :a, :b) RETURNING app_user_id", e=email, a=admin, b=by)
    admin = user("mig.admin@example.test", True)
    u = {"admin": admin, "owner": user("mig.owner@example.test", by=admin),
         "reviewer": user("mig.reviewer@example.test", by=admin), "none": user("mig.none@example.test", by=admin)}
    role = {}
    for code in ("OWNER", "EDITOR", "REVIEWER"):
        role[code] = one("INSERT INTO code_master (category, code, label, is_system) "
                         "VALUES ('PROJECT_ROLE', :c, :c, true) ON CONFLICT DO NOTHING RETURNING code_id", c=code)
    status = one("SELECT code_id FROM code_master WHERE category = 'PROJECT_STATUS' AND code = 'PLANNING' "
                 "AND project_id IS NULL")
    client = one("INSERT INTO client (client_code, client_name, created_by) VALUES ('MIG', 'Mig', :a) "
                 "RETURNING client_id", a=admin)
    prog = one("INSERT INTO program (client_id, program_code, program_name, created_by) "
               "VALUES (:c, 'MIGP', 'Mig program', :a) RETURNING program_id", c=client, a=admin)
    proj = lambda code, program=None: one(  # noqa: E731
        "INSERT INTO project (client_id, program_id, project_code, project_name, status_code_id, created_by) "
        "VALUES (:c, :g, :p, :p, :s, :a) RETURNING project_id", c=client, g=program, p=code, s=status, a=admin)
    p = {"solo": proj("MSOLO"), "in1": proj("MIN1", prog), "in2": proj("MIN2", prog), "gone": proj("MGONE", prog)}
    c.execute(text("UPDATE project SET is_active = false, deleted_at = now() WHERE project_id = :p"), {"p": p["gone"]})
    grant = lambda user_id, role_code, project=None, program=None: one(  # noqa: E731
        "INSERT INTO user_access_grant (app_user_id, project_id, program_id, project_role_code_id, "
        "granted_by_user_id, created_by) VALUES (:u, :p, :g, :r, :a, :a) RETURNING user_access_grant_id",
        u=user_id, p=project, g=program, r=role[role_code], a=admin)
    g = {"owner": grant(u["owner"], "OWNER", project=p["solo"]),
         "reviewer": grant(u["reviewer"], "REVIEWER", program=prog)}
    return {"u": u, "p": p, "g": g, "admin": admin}


@pytest.fixture
def migrated():
    cfg = _cfg()
    command.downgrade(cfg, "0034")
    eng = create_engine(OWNER_URL)
    try:
        with eng.begin() as c:
            world = _seed(c)
        command.upgrade(cfg, "head")
        yield world, eng
    finally:
        command.upgrade(cfg, "head")                  # never leave the shared schema behind head
        eng.dispose()


def test_0035_to_0038_turn_live_grants_into_kinds_members_and_revoked_history(migrated, db):
    w, eng = migrated
    u, p, g = w["u"], w["p"], w["g"]
    with eng.connect() as c:
        kinds = dict(c.execute(text("SELECT app_user_id, user_kind FROM app_user WHERE email LIKE 'mig.%'")).all())
        assert kinds == {u["admin"]: "USER", u["owner"]: "USER", u["reviewer"]: "VIEWER", u["none"]: "VIEWER"}
        members = c.execute(text(
            "SELECT project_id, app_user_id, access_level, member_note, created_by FROM project_member "
            "ORDER BY project_id")).all()
        assert [(m.project_id, m.app_user_id, m.access_level) for m in members] == [
            (p["solo"], u["owner"], "EDIT"), (p["in1"], u["reviewer"], "VIEW"), (p["in2"], u["reviewer"], "VIEW")]
        assert members[0].member_note == f"from grant #{g['owner']} (D-40)" and members[0].created_by == w["admin"]
        grants = c.execute(text("SELECT is_active, deleted_at FROM user_access_grant")).all()
        assert all(not r.is_active and r.deleted_at is not None for r in grants) and len(grants) == 2
        revoked = c.execute(text("SELECT target_id, detail FROM audit_event WHERE event_type = 'ACCESS_REVOKED' "
                                 "ORDER BY target_id")).all()
        assert [r.target_id for r in revoked] == sorted(g.values())
        assert {r.detail["role"] for r in revoked} == {"OWNER", "REVIEWER"}
        assert all(r.detail["migration"] == "0038" for r in revoked)
    # the app role can no longer write the history (0038)
    for sql in ("UPDATE user_access_grant SET updated_at = now()",
                "INSERT INTO user_access_grant (app_user_id, project_id, project_role_code_id, granted_by_user_id, "
                "created_by) VALUES (1, 1, 1, 1, 1)"):
        with pytest.raises(ProgrammingError):
            db.execute(text(sql))
        db.rollback()
