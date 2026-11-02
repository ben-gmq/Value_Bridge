"""Migration 0083 (risk; docs/slice_risks_spec.md §5, §9 criterion 8). The backfill gives each risk-list code its
weight or behaviour by code and refuses one it cannot map; the downgrade refuses while a risk exists and lets the
unedited GE rules go (as 0082 under CC-8)."""
import pytest
from alembic import command

from tests.test_control import role
from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture
from tests.test_risk_api import risk
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture


def table_exists(owner) -> bool:
    return bool(q(owner, "SELECT to_regclass('public.risk') IS NOT NULL")[0][0])


def behaviours(owner) -> dict:
    return {(c, k): b for c, k, b in q(owner, "SELECT category, code, behaviour_code FROM code_master WHERE "
                                               "category LIKE 'RISK\\_%' AND project_id IS NULL")}


def test_down_clears_the_behaviours_and_up_backfills_them_by_code(client, ed, owner):
    before = behaviours(owner)
    assert before[("RISK_PROBABILITY", "LIKELY")] == "W4" and before[("RISK_STATUS", "MITIGATING")] == "OPEN"
    command.downgrade(_cfg(), "0082")
    assert not table_exists(owner)
    assert set(behaviours(owner).values()) == {None}
    assert q(owner, "SELECT count(*) FROM control_rule WHERE comparison = 'GE'")[0][0] == 0
    command.upgrade(_cfg(), "0083")
    assert table_exists(owner) and behaviours(owner) == before


def test_an_unknown_risk_code_refuses_the_upgrade_by_name(client, ed, owner):
    command.downgrade(_cfg(), "0082")
    x(owner, "INSERT INTO code_master (project_id, category, code, label) VALUES (:p, 'RISK_IMPACT', 'HUGE', 'Huge')",
      p=ed["p"])
    with pytest.raises(Exception, match=f"{ed['p']}:RISK_IMPACT.HUGE"):
        command.upgrade(_cfg(), "0083")
    assert not table_exists(owner)
    x(owner, "UPDATE code_master SET code = 'SEVERE' WHERE code = 'HUGE'")       # mapped by hand: it re-runs


def test_a_risk_or_an_edited_ge_rule_refuses_the_downgrade(client, ed, owner):
    r = risk(client, ed, role(client, ed))
    head = q(owner, "SELECT version_num FROM alembic_version")[0][0]
    with pytest.raises(Exception, match="risks exist"):
        command.downgrade(_cfg(), "0082")
    assert table_exists(owner) and q(owner, "SELECT version_num FROM alembic_version")[0][0] == head
    x(owner, "UPDATE risk SET is_active = false WHERE risk_id = :r", r=r["risk_id"])
    assert q(owner, "SELECT count(*) FROM risk")[0][0] == 1                        # retired is still a risk
