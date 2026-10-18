"""Migrations 0063 (issue + baseline_issue) and 0064 (issue_br + baseline_issue_br). A clean downgrade and re-upgrade
round-trips; each downgrade refuses while a baseline frozen at hash spec 5 exists (its digest includes both entries,
even with no issue rows) and while its own tables hold a row (sara C M1). 0064 always downgrades first, so its
spec-5 guard is the one these reach; 0063's identical guard is defensive and not separately exercised (sara D L2)."""
import pytest
from alembic import command

from tests.test_baseline import freeze, scope
from tests.test_issue_api import issue, link, stakeholder
from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture

TABLES = "SELECT count(*) FROM information_schema.tables WHERE table_name IN ('issue', 'issue_br', " \
         "'baseline_issue', 'baseline_issue_br')"


def test_a_clean_downgrade_and_upgrade_round_trip(client, ed, owner):
    command.downgrade(_cfg(), "0062")
    assert q(owner, TABLES)[0][0] == 0
    command.upgrade(_cfg(), "head")
    assert q(owner, TABLES)[0][0] == 4


def test_a_spec_5_baseline_without_issues_refuses_both_downgrades(client, ed, owner):
    scope(client, ed)
    assert freeze(client, ed)["baseline"]["hash_spec_version"] == 5
    with pytest.raises(Exception, match="hash spec 5"):
        command.downgrade(_cfg(), "0063")
    with pytest.raises(Exception, match="hash spec 5"):
        command.downgrade(_cfg(), "0062")
    assert q(owner, TABLES)[0][0] == 4


@pytest.mark.parametrize("target, kind, message", [("0063", "link", "issue links exist"),
                                                   ("0062", "issue", "issues exist")])
def test_rows_refuse_the_downgrade(client, ed, owner, target, kind, message):
    w = scope(client, ed)
    s = stakeholder(client, ed, "Anan")
    i = issue(client, ed, s)
    if kind == "link":
        link(client, ed, i, w["br1"])
    else:
        x(owner, "UPDATE issue SET is_active = false")                     # a retired row still blocks
    with pytest.raises(Exception, match=message):
        command.downgrade(_cfg(), target)
    assert q(owner, TABLES)[0][0] == 4
