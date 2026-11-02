"""Migration 0081 (control_rule; docs/slice_control_a_spec.md §2, §11; sara M3). The downgrade is the one thing standing
between a downgrade and the loss of thresholds a client agreed: it refuses while any project rule has been edited, and
lets unedited rows go (they are house copies seeds.seed_control_rules recreates)."""
import pytest
from alembic import command

from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture


def table_exists(owner) -> bool:
    return bool(q(owner, "SELECT to_regclass('public.control_rule') IS NOT NULL")[0][0])


def test_unedited_copies_go_with_the_table_and_the_upgrade_recreates_it(client, ed, owner):
    assert q(owner, "SELECT count(*) FROM control_rule WHERE project_id IS NOT NULL")[0][0] > 0
    command.downgrade(_cfg(), "0080")
    assert not table_exists(owner)
    command.upgrade(_cfg(), "0081")
    assert table_exists(owner)
    assert q(owner, "SELECT count(*) FROM control_rule")[0][0] == 0      # the seed puts the house tier back


def test_an_edited_rule_refuses_the_downgrade_and_keeps_the_table(client, ed, owner):
    x(owner, "UPDATE control_rule SET threshold_value = 9, change_rationale = 'Client agreed', row_version = 2 "
             "WHERE project_id = :p AND analysis_code = 'coverage'", p=ed["p"])
    head = q(owner, "SELECT version_num FROM alembic_version")[0][0]
    with pytest.raises(Exception, match="edited project control rule"):
        command.downgrade(_cfg(), "0080")
    assert table_exists(owner)
    assert q(owner, "SELECT version_num FROM alembic_version")[0][0] == head
    assert q(owner, "SELECT threshold_value FROM control_rule WHERE project_id = :p AND analysis_code = 'coverage'",
             p=ed["p"])[0][0] == 9
