"""Migration 0079 (approvers required as a setting; docs/approvers_setting_spec.md acceptance 9). It round-trips while
nothing was ever approved alone, and its downgrade refuses once something was — the restored two-admin checks would not
hold for those rows, and the record that four eyes were relaxed would go."""
import pytest
from alembic import command
from sqlalchemy import text

from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture

GUARDED = ("fn_project_purge_guard", "fn_platform_admin_grant_guard", "fn_vb_instance_guard", "fn_purge_allows",
           "fn_admin_purge_independent")


def bodies(owner) -> dict:
    return dict(q(owner, "SELECT proname, prosrc FROM pg_proc WHERE proname = ANY(:n)", n=list(GUARDED)))


def setting(owner, **cols):
    with owner.begin() as c:
        c.execute(text("SELECT set_config('vb.operator', 'IS test', true)"))
        for k, v in cols.items():
            c.execute(text(f"UPDATE vb_instance SET {k} = :v"), {"v": v})


def test_0079_round_trips_back_to_the_exact_0078_bodies(owner):
    at_0079 = bodies(owner)
    command.downgrade(_cfg(), "0078")
    at_0078 = bodies(owner)
    assert at_0078.keys() == at_0079.keys() and all(at_0078[k] != at_0079[k] for k in at_0078)
    assert not q(owner, "SELECT to_regclass('public.vb_instance_setting_log')")[0][0]
    assert not q(owner, "SELECT count(*) FROM information_schema.columns WHERE column_name = 'approved_single_owner'")[0][0]
    command.upgrade(_cfg(), "0079")
    assert bodies(owner) == at_0079                                       # the swaps reproduce the same text


def test_the_downgrade_refuses_once_the_setting_was_one(owner):
    x(owner, "INSERT INTO vb_instance (instance_id) VALUES ('test-a')")
    setting(owner, installation_kind="LOCAL_SINGLE_OWNER")
    setting(owner, approvers_required=1)
    setting(owner, approvers_required=2)                                  # back at 2: the log still says it was 1
    with pytest.raises(Exception, match="0079 downgrade refused"):
        command.downgrade(_cfg(), "0078")
    assert q(owner, "SELECT version_num FROM alembic_version")[0][0] == "0079"
