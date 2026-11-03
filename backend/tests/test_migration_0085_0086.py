"""Migrations 0085 (benefit, BENEFIT_STATUS behaviours) and 0086 (benefit_solution; docs/slice_benefits_spec.md §5).
Down clears the behaviours and up backfills them by code; a status code 0085 cannot map refuses the upgrade by name;
a benefit or a link refuses the downgrade."""
import pytest
from alembic import command

from tests.test_benefit_api import benefit, put
from tests.test_control import role
from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture
from tests.test_solution_api import sol


def exists(owner, table) -> bool:
    return bool(q(owner, f"SELECT to_regclass('public.{table}') IS NOT NULL")[0][0])


def behaviours(owner) -> dict:
    return {k: b for k, b in q(owner, "SELECT code, behaviour_code FROM code_master WHERE category = 'BENEFIT_STATUS' "
                                      "AND project_id IS NULL")}


def test_down_clears_the_behaviours_and_up_backfills_them_by_code(client, ed, owner):
    before = behaviours(owner)
    assert before["ABANDONED"] == "ABANDONED" and before["FORECAST"] == "LIVE"
    command.downgrade(_cfg(), "0084")
    assert not exists(owner, "benefit") and not exists(owner, "benefit_solution")
    assert not exists(owner, "baseline_benefit")
    assert set(behaviours(owner).values()) == {None}
    command.upgrade(_cfg(), "0086")
    assert exists(owner, "benefit_solution") and behaviours(owner) == before


def test_an_unknown_benefit_status_refuses_the_upgrade_by_name(client, ed, owner):
    command.downgrade(_cfg(), "0084")
    x(owner, "INSERT INTO code_master (category, code, label) VALUES ('BENEFIT_STATUS', 'PARKED', 'Parked')")
    with pytest.raises(Exception, match="PARKED"):
        command.upgrade(_cfg(), "0085")
    assert not exists(owner, "benefit")
    x(owner, "DELETE FROM code_master WHERE category = 'BENEFIT_STATUS' AND code = 'PARKED'")   # test row only


def test_a_benefit_or_a_link_refuses_the_downgrade(client, ed, owner):
    b = benefit(client, ed, role(client, ed))
    put(client, ed, b, sol(client, ed, "Billing"), 10)
    with pytest.raises(Exception, match="benefit links exist"):
        command.downgrade(_cfg(), "0085")
    assert exists(owner, "benefit_solution")
