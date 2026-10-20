"""Migrations 0065 (phase), 0066 (solution_phase) and 0067 (solution_dependency), each with its shadow. A clean
downgrade and re-upgrade round-trips; each downgrade refuses while a baseline frozen at hash spec 6 exists (its digest
includes all three entries, even with no rows) and while its own tables hold a row, a retired one included. 0067
always downgrades first, so its spec-6 guard is the one a spec-6 baseline reaches; the rows guards are reached per
table by giving only that table a row."""
import pytest
from alembic import command

from tests.test_baseline import freeze, scope
from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture
from tests.test_phasing_api import depend, put_split, wave
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture
from tests.test_solution_api import sol

TABLES = ("SELECT count(*) FROM information_schema.tables WHERE table_name IN ('phase', 'solution_phase', "
          "'solution_dependency', 'baseline_phase', 'baseline_solution_phase', 'baseline_solution_dependency')")


def test_a_clean_downgrade_and_upgrade_round_trip(client, ed, owner):
    command.downgrade(_cfg(), "0064")
    assert q(owner, TABLES)[0][0] == 0
    command.upgrade(_cfg(), "head")
    assert q(owner, TABLES)[0][0] == 6


def test_a_spec_6_baseline_without_waves_refuses_the_downgrade(client, ed, owner):
    scope(client, ed)
    assert freeze(client, ed)["baseline"]["hash_spec_version"] == 6
    with pytest.raises(Exception, match="hash spec 6"):
        command.downgrade(_cfg(), "0066")
    assert q(owner, TABLES)[0][0] == 6


@pytest.mark.parametrize("target, kind, message", [("0066", "dependency", "solution dependencies exist"),
                                                   ("0065", "split", "wave splits exist"),
                                                   ("0064", "wave", "waves exist")])
def test_rows_refuse_the_downgrade(client, ed, owner, target, kind, message):
    a, b = sol(client, ed, "A"), sol(client, ed, "B")
    w = wave(client, ed, "W1")
    if kind == "dependency":
        assert depend(client, ed, a, b).status_code == 201
        x(owner, "UPDATE solution_dependency SET is_active = false")        # a retired row still blocks
    elif kind == "split":
        assert put_split(client, ed, a, [(w, 100)]).status_code == 200
        command.downgrade(_cfg(), "0066")                                    # nothing in 0067's tables
    else:
        command.downgrade(_cfg(), "0065")                                    # nothing in 0066's or 0067's
    with pytest.raises(Exception, match=message):
        command.downgrade(_cfg(), target)
    command.upgrade(_cfg(), "head")
    assert q(owner, TABLES)[0][0] == 6
