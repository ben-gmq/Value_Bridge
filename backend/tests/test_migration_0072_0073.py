"""Migrations 0072 (project_purge) and 0073 (project_purge_key): a clean round trip, and each downgrade refuses while
its table holds a record — a purge record is kept forever."""
import pytest
from alembic import command

from tests.admin_team import forget_grants
from tests.test_migration_0053 import _cfg, owner, q  # noqa: F401 — owner is a fixture
from tests.test_project_purge_record import approved, promote, record_key, two  # noqa: F401 — two is a fixture

TABLES = ("SELECT count(*) FROM information_schema.tables WHERE table_name IN ('project_purge', 'project_purge_key')")


def test_a_clean_downgrade_and_upgrade_round_trip(owner):
    command.downgrade(_cfg(), "0071")
    assert q(owner, TABLES)[0][0] == 0
    command.upgrade(_cfg(), "head")
    assert q(owner, TABLES)[0][0] == 2


def test_a_request_refuses_the_0072_downgrade(two, owner):
    promote(owner, two["a2"])
    approved(owner, two, "DELETE")
    forget_grants(owner)                                                   # slice 17: past 0076 first
    with pytest.raises(Exception, match="purge requests exist"):
        command.downgrade(_cfg(), "0071")
    assert q(owner, TABLES)[0][0] == 2


def test_records_refuse_the_downgrade(two, owner):
    promote(owner, two["a2"])
    pp = approved(owner, two, "DELETE")
    record_key(owner, pp, two["p"], f"vb-test-a-proj-{two['p']}")
    forget_grants(owner)
    with pytest.raises(Exception, match="purge key records exist"):
        command.downgrade(_cfg(), "0072")
    assert q(owner, TABLES)[0][0] == 2
