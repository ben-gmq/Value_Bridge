"""Migrations 0061 (ISSUE_STATUS open / closed behaviour, I-1, deviation 14a) and 0062 (stakeholder). Both round-trip
cleanly; 0061's data step is reversed by its downgrade and refuses a project-tier status (R6); 0062's downgrade
refuses while any stakeholder row exists."""
import pytest
from alembic import command

from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture

BEHAVIOURS = ("SELECT code, behaviour_code FROM code_master WHERE category = 'ISSUE_STATUS' AND project_id IS NULL "
              "ORDER BY code")
SEEDED = [("CLOSED", "CLOSED"), ("DEFERRED", "OPEN"), ("IN_PROGRESS", "OPEN"), ("OPEN", "OPEN"),
          ("RESOLVED", "CLOSED")]
STK = "SELECT 1 FROM information_schema.tables WHERE table_name = 'stakeholder'"


def test_a_clean_downgrade_and_upgrade_round_trip(client, ed, owner):
    assert q(owner, BEHAVIOURS) == SEEDED
    command.downgrade(_cfg(), "0060")
    assert not q(owner, STK)
    assert [b for _, b in q(owner, BEHAVIOURS)] == [None] * 5         # the data step is reversed
    command.upgrade(_cfg(), "head")
    assert q(owner, STK)
    assert q(owner, BEHAVIOURS) == SEEDED                             # and re-applied by code


def test_a_status_without_behaviour_is_refused_by_the_database(client, ed, owner):
    user = q(owner, "SELECT app_user_id FROM app_user ORDER BY app_user_id LIMIT 1")[0][0]
    with pytest.raises(Exception, match="ck_code_behaviour_present"):
        x(owner, "INSERT INTO code_master (category, code, label, created_by) VALUES ('ISSUE_STATUS', 'X', 'X', :u)",
          u=user)
    with pytest.raises(Exception, match="ck_code_issue_status_behaviour"):
        x(owner, "INSERT INTO code_master (category, code, label, behaviour_code, created_by) "
                 "VALUES ('ISSUE_STATUS', 'X', 'X', 'FORM', :u)", u=user)


def test_a_project_tier_status_refuses_the_upgrade(client, ed, owner):
    command.downgrade(_cfg(), "0060")
    user = q(owner, "SELECT app_user_id FROM app_user ORDER BY app_user_id LIMIT 1")[0][0]
    x(owner, "INSERT INTO code_master (project_id, category, code, label, created_by) "
             "VALUES (:p, 'ISSUE_STATUS', 'OPEN', 'Raised', :u)", p=ed["p"], u=user)
    with pytest.raises(Exception, match="project-tier ISSUE_STATUS rows exist"):
        command.upgrade(_cfg(), "0061")
    x(owner, "UPDATE code_master SET project_id = NULL, code = 'OPEN_X' WHERE project_id = :p "
             "AND category = 'ISSUE_STATUS'", p=ed["p"])
    with pytest.raises(Exception, match="unknown ISSUE_STATUS codes"):
        command.upgrade(_cfg(), "0061")
    x(owner, "DELETE FROM code_master WHERE code = 'OPEN_X'")          # owner role; the fixture re-upgrades


def test_a_stakeholder_row_refuses_the_downgrade(client, ed, owner):
    user = q(owner, "SELECT app_user_id FROM app_user ORDER BY app_user_id LIMIT 1")[0][0]
    x(owner, "INSERT INTO stakeholder (project_id, stakeholder_name, created_by, is_active) "
             "VALUES (:p, 'Somchai', :u, false)", p=ed["p"], u=user)
    with pytest.raises(Exception, match="stakeholders exist"):
        command.downgrade(_cfg(), "0061")
    assert q(owner, STK)
