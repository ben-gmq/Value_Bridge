"""Slice 16: this database's archive identity (schema §3.4, §12.7; spec §17 R8, §18 S6, S9). A wrong identity writes
one environment's files under another's names, so the guard is proven at the database and the start-up check
refuses every mismatch."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from scripts.stamp_instance import stamp
from services import instance
from tests.conftest import OWNER_URL


@pytest.fixture
def owner():
    eng = create_engine(OWNER_URL)
    yield eng
    eng.dispose()


def refused(eng, sql, **params) -> str:
    with pytest.raises(DBAPIError) as e, eng.begin() as c:
        c.execute(text(sql), params)
    return str(e.value.orig)


def test_the_start_up_check_refuses_every_mismatch(db):
    with pytest.raises(instance.NotStamped, match="no archive identity"):
        instance.check_startup(db, "test-a")
    stamp(OWNER_URL, "test-a", restamp=False)
    with pytest.raises(instance.NotStamped, match="not set"):
        instance.check_startup(db, None)
    with pytest.raises(instance.NotStamped, match="stamped 'test-a'"):
        instance.check_startup(db, "test-b")
    assert instance.check_startup(db, "test-a") == "test-a"


def test_a_restamp_keeps_every_prior_id_and_nothing_else_changes_it(db, owner):
    stamp(OWNER_URL, "prod-1", restamp=False)
    with pytest.raises(SystemExit, match="Already stamped"):
        stamp(OWNER_URL, "uat-1", restamp=False)
    stamp(OWNER_URL, "uat-1", restamp=True)
    stamp(OWNER_URL, "dev-1", restamp=True)
    assert instance.ids(db) == ["dev-1", "prod-1", "uat-1"]
    assert "never takes back" in refused(owner, "UPDATE vb_instance SET instance_id = 'prod-1', "
                                                "prior_instance_ids = prior_instance_ids || instance_id::text")
    assert "not allowed" in refused(owner, "DELETE FROM vb_instance")
    assert "appends the old one" in refused(owner, "UPDATE vb_instance SET instance_id = 'x-1'")
    assert "appends the old one" in refused(owner, "UPDATE vb_instance SET prior_instance_ids = '{}'")
    assert "ck_vi_instance_id" in refused(
        owner, "UPDATE vb_instance SET instance_id = 'Bad/Name', prior_instance_ids = prior_instance_ids || instance_id")


def test_the_app_role_only_reads_it(db):
    assert db.scalar(text("SELECT has_table_privilege('vb_app', 'vb_instance', 'SELECT')"))
    assert not any(db.scalar(text(f"SELECT has_table_privilege('vb_app', 'vb_instance', '{p}')"))
                   for p in ("INSERT", "UPDATE", "DELETE"))
