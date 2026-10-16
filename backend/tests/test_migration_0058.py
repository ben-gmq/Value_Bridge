"""Migration 0058 (D-71; access slice A step 1): project_member takes ADMIN. A clean downgrade and re-upgrade
round-trips; once any membership — live or retired — holds ADMIN, the downgrade refuses, because narrowing the column
would rewrite membership history."""
import pytest
from alembic import command

from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture


def _check(owner) -> str:
    return q(owner, "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_pm_level'")[0][0]


def test_a_clean_downgrade_and_upgrade_round_trip(client, ed, owner):
    command.downgrade(_cfg(), "0057")
    assert "ADMIN" not in _check(owner)
    command.upgrade(_cfg(), "head")
    assert "ADMIN" in _check(owner)
    assert q(owner, "SELECT character_maximum_length FROM information_schema.columns "
                    "WHERE table_name = 'project_member' AND column_name = 'access_level'")[0][0] == 5


@pytest.mark.parametrize("retired", [False, True])
def test_an_admin_membership_refuses_the_downgrade(client, ed, owner, retired):
    user = q(owner, "SELECT app_user_id FROM app_user WHERE NOT is_platform_admin ORDER BY app_user_id LIMIT 1")[0][0]
    x(owner, "INSERT INTO project_member (project_id, app_user_id, access_level, created_by, is_active) "
             "VALUES (:p, :u, 'ADMIN', :u, :live)", p=ed["p"], u=user, live=not retired)
    with pytest.raises(Exception, match="project admin memberships exist"):
        command.downgrade(_cfg(), "0057")
    assert "ADMIN" in _check(owner)
