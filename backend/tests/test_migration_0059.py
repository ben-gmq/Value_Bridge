"""Migration 0059 (wave 1g, G-1): project_code_visibility. A clean downgrade and re-upgrade round-trips; once any row
exists — a code hidden now, or one hidden and since unhidden — the downgrade refuses."""
import pytest
from alembic import command

from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture

EXISTS = "SELECT 1 FROM information_schema.tables WHERE table_name = 'project_code_visibility'"


def test_a_clean_downgrade_and_upgrade_round_trip(client, ed, owner):
    command.downgrade(_cfg(), "0058")
    assert not q(owner, EXISTS)
    command.upgrade(_cfg(), "head")
    assert q(owner, EXISTS)


@pytest.mark.parametrize("hidden", [True, False])
def test_a_visibility_row_refuses_the_downgrade(client, ed, owner, hidden):
    code = q(owner, "SELECT code_id FROM code_master WHERE project_id IS NULL AND category = 'BR_PRIORITY' "
                    "ORDER BY code_id LIMIT 1")[0][0]
    user = q(owner, "SELECT app_user_id FROM app_user ORDER BY app_user_id LIMIT 1")[0][0]
    x(owner, "INSERT INTO project_code_visibility (project_id, code_id, created_by, is_active) VALUES (:p, :c, :u, :h)",
      p=ed["p"], c=code, u=user, h=hidden)
    with pytest.raises(Exception, match="projects have hidden codes"):
        command.downgrade(_cfg(), "0058")
    assert q(owner, EXISTS)
