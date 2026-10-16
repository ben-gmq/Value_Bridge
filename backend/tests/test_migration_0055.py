"""Migration 0055 (slice11_schema §7; sara H1): the downgrade refuses while a baseline was frozen at hash spec 4 —
even one holding no lines, whose digest still includes the lines entry — and while a person wrote or changed a line.
A clean downgrade and re-upgrade restores the table."""
import pytest
from alembic import command

from tests.test_baseline import freeze, scope
from tests.test_br_lines import add
from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture


def test_a_clean_downgrade_and_upgrade_round_trip(client, ed, owner):
    command.downgrade(_cfg(), "0054")
    assert not q(owner, "SELECT 1 FROM information_schema.tables WHERE table_name = 'br_requirement_line'")
    command.upgrade(_cfg(), "head")
    assert q(owner, "SELECT 1 FROM information_schema.tables WHERE table_name = 'baseline_br_requirement_line'")


def test_a_spec_4_baseline_without_lines_still_refuses_the_downgrade(client, ed, owner):
    scope(client, ed)
    assert freeze(client, ed)["baseline"]["hash_spec_version"] == 4
    assert q(owner, "SELECT count(*) FROM baseline_br_requirement_line")[0][0] == 0
    with pytest.raises(Exception, match="hash spec 4"):
        command.downgrade(_cfg(), "0054")
    assert q(owner, "SELECT 1 FROM information_schema.tables WHERE table_name = 'br_requirement_line'")


def test_a_line_a_person_wrote_refuses_the_downgrade(client, ed, owner):
    br = scope(client, ed)["br1"]
    add(client, ed, br)
    with pytest.raises(Exception, match="written or changed by people"):
        command.downgrade(_cfg(), "0054")
    # a line the backfill wrote is not a person's: with its marker in place, the same row no longer blocks
    lid = q(owner, "SELECT br_requirement_line_id FROM br_requirement_line")[0][0]
    x(owner, "INSERT INTO audit_event (event_type, project_id, detail) VALUES ('BR_LINES_BACKFILLED', :p, "
             "jsonb_build_object('count', 1, 'line_ids', jsonb_build_array(CAST(:l AS bigint))))", p=ed["p"], l=lid)
    command.downgrade(_cfg(), "0054")
    assert not q(owner, "SELECT 1 FROM information_schema.tables WHERE table_name = 'br_requirement_line'")
