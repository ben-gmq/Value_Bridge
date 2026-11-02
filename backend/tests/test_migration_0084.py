"""Migration 0084 (decision; docs/slice_decisions_spec.md §5, §9 criterion 10). Down refuses while a decision exists
(evidential); up refuses a project's own PM_DIMENSION code (the list becomes company-only)."""
import pytest
from alembic import command

from tests.test_decision_api import dec
from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture


def table_exists(owner) -> bool:
    return bool(q(owner, "SELECT to_regclass('public.decision') IS NOT NULL")[0][0])


def test_down_and_up_again(client, ed, owner):
    command.downgrade(_cfg(), "0083")
    assert not table_exists(owner)
    assert not q(owner, "SELECT count(*) FROM pg_proc WHERE proname IN ('fn_decision_reject', 'fn_decision_stamp')")[0][0]
    command.upgrade(_cfg(), "0084")
    assert table_exists(owner)
    assert q(owner, "SELECT has_table_privilege('vb_app', 'decision', 'UPDATE') OR "
                    "has_table_privilege('vb_app', 'decision', 'DELETE') OR "
                    "has_table_privilege('vb_app', 'decision', 'TRUNCATE')")[0][0] is False
    assert q(owner, "SELECT has_table_privilege('vb_app', 'decision', 'INSERT')")[0][0] is True


def test_a_decision_refuses_the_downgrade(client, ed, owner):
    dec(client, ed)
    head = q(owner, "SELECT version_num FROM alembic_version")[0][0]
    with pytest.raises(Exception, match="decisions exist"):
        command.downgrade(_cfg(), "0083")
    assert table_exists(owner) and q(owner, "SELECT version_num FROM alembic_version")[0][0] == head


def test_a_project_dimension_code_refuses_the_upgrade_by_name(client, ed, owner):
    command.downgrade(_cfg(), "0083")
    x(owner, "INSERT INTO code_master (project_id, category, code, label) VALUES (:p, 'PM_DIMENSION', 'LOCAL', 'L')",
      p=ed["p"])
    with pytest.raises(Exception, match=f"{ed['p']}:LOCAL"):
        command.upgrade(_cfg(), "0084")
    assert not table_exists(owner)
    x(owner, "UPDATE code_master SET is_active = false, category = 'ISSUE_TYPE' WHERE code = 'LOCAL' "
             "AND category = 'PM_DIMENSION'")                                          # resolved by hand: it re-runs
