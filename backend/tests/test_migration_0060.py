"""Migration 0060 (D-71; access slice B step 1): program_member. A clean downgrade and re-upgrade round-trips; any row —
live or retired — refuses the downgrade (membership history); a live member blocks retiring its program at the
database (law 1), a retired one does not."""
import pytest
from alembic import command

from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture

EXISTS = "SELECT 1 FROM information_schema.tables WHERE table_name = 'program_member'"


def _member(owner, world, live=True):
    x(owner, "INSERT INTO program_member (program_id, app_user_id, access_level, created_by, is_active) "
             "VALUES (:g, :u, 'EDIT', :u, :live)", g=world["program_id"], u=world["users"]["editor"], live=live)


def test_a_clean_downgrade_and_upgrade_round_trip(client, world, owner):
    command.downgrade(_cfg(), "0059")
    assert not q(owner, EXISTS)
    command.upgrade(_cfg(), "head")
    assert q(owner, EXISTS)


@pytest.mark.parametrize("live", [True, False])
def test_a_membership_refuses_the_downgrade(client, world, owner, live):
    _member(owner, world, live)
    with pytest.raises(Exception, match="program memberships exist"):
        command.downgrade(_cfg(), "0059")
    assert q(owner, EXISTS)


def test_a_live_member_blocks_retiring_the_program(client, world, owner):
    x(owner, "UPDATE project SET program_id = NULL WHERE program_id = :g", g=world["program_id"])
    _member(owner, world)
    with pytest.raises(Exception, match="fk_prgm_live_program"):
        x(owner, "UPDATE program SET is_active = false WHERE program_id = :g", g=world["program_id"])
    x(owner, "UPDATE program_member SET is_active = false WHERE program_id = :g", g=world["program_id"])
    x(owner, "UPDATE program SET is_active = false WHERE program_id = :g", g=world["program_id"])
