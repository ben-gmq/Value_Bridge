"""Migrations 0070 (PROJECT_STATUS behaviour) and 0071 (project.closed_on) on real data (slice16 schema §12.3, §12.8;
AR-10, AR-12). Grade 2: a project that never comes due is a missed archive, so the backfill, the CHECK that ties the
clock to a closed status, and the downgrade that refuses to lose a clock are proven directly."""
import pytest
from alembic import command
from sqlalchemy.exc import DBAPIError

from tests.test_components import new_project
from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture

TODAY = "(now() AT TIME ZONE 'Asia/Bangkok')::date"
STATUS = ("SELECT code_id FROM code_master WHERE category = 'PROJECT_STATUS' AND code = :c AND project_id IS NULL")
CLOSED = STATUS.replace(":c", "'CLOSED'")


def test_the_backfill_starts_the_clock_today_and_closes_retired_projects(client, world, owner):
    open_, closed, retired = (new_project(client, world, c, [])["project_id"] for c in ("OPN", "CLS", "RET"))
    command.downgrade(_cfg(), "0069")
    assert q(owner, "SELECT count(*) FROM code_master WHERE category = 'PROJECT_STATUS' "
                    "AND behaviour_code IS NOT NULL")[0][0] == 0
    x(owner, f"UPDATE project SET status_code_id = ({STATUS}) WHERE project_id = :p", c="CLOSED", p=closed)
    x(owner, "UPDATE project SET is_active = false WHERE project_id = :p", p=retired)
    command.upgrade(_cfg(), "0071")
    got = dict((r[0], r[1:]) for r in q(owner, f"SELECT p.project_id, c.code, p.status_behaviour, "
                                               f"p.closed_on = {TODAY} FROM project p JOIN code_master c "
                                               f"ON c.code_id = p.status_code_id"))
    assert got[open_] == ("PLANNING", "OPEN", None)
    assert got[closed] == ("CLOSED", "CLOSED", True)
    assert got[retired] == ("CLOSED", "CLOSED", True)                         # AR-10: retiring closes first


def test_the_database_ties_the_clock_to_a_closed_status(client, world, owner):
    p = new_project(client, world, "P1", [])["project_id"]
    for sql, name in (("UPDATE project SET closed_on = current_date WHERE project_id = :p", "ck_project_closed_on"),
                      (f"UPDATE project SET status_code_id = ({CLOSED}) "
                       "WHERE project_id = :p", "fk_project_status"),
                      (f"UPDATE project SET status_code_id = ({CLOSED}), "
                       "status_behaviour = 'CLOSED' WHERE project_id = :p", "ck_project_closed_on")):
        with pytest.raises(DBAPIError, match=name):
            x(owner, sql, p=p)
    x(owner, f"UPDATE project SET status_code_id = ({CLOSED}), "
             "status_behaviour = 'CLOSED', closed_on = current_date WHERE project_id = :p", p=p)


def test_any_running_clock_refuses_the_downgrade(client, world, owner):
    p = new_project(client, world, "P1", [])["project_id"]
    x(owner, f"UPDATE project SET status_code_id = ({CLOSED}), "
             f"status_behaviour = 'CLOSED', closed_on = {TODAY} + 1 WHERE project_id = :p", p=p)
    with pytest.raises(Exception, match="archive clock that would be lost"):
        command.downgrade(_cfg(), "0070")
    x(owner, f"UPDATE project SET closed_on = {TODAY} WHERE project_id = :p", p=p)
    with pytest.raises(Exception, match="archive clock that would be lost"):     # the backfill day too
        command.downgrade(_cfg(), "0070")
    x(owner, f"UPDATE project SET status_code_id = ({STATUS.replace(':c', repr('PLANNING'))}), "
             "status_behaviour = 'OPEN', closed_on = NULL WHERE project_id = :p", p=p)
    command.downgrade(_cfg(), "0069")                                           # no clock left: it may go
    assert q(owner, "SELECT count(*) FROM information_schema.columns WHERE table_name = 'project' "
                    "AND column_name IN ('closed_on', 'status_behaviour', 'status_category')")[0][0] == 0
