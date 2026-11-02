"""Control-C piece C3: FRs nobody traced to a requirement — the panel row, its seed, migration 0082
(docs/slice_control_c_spec.md §2.3, §7, §8 tests 5, 6; CC-3). Grade 2: a wrong count reaches a steering meeting and is
corrected once noticed.

Deliberately uncovered: speed at the design bound (the count is the register's own query)."""
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import select, text

from models import ControlRule
from services import control
from tests.conftest import owner_engine
from tests.test_br_fr import lnk, set_components, two_brs
from tests.test_control import edit, panel, row
from tests.test_effort_api import rate
from tests.test_function_requirement_api import fr
from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture


def register_unlinked(client, ed) -> list[int]:
    r = client.get(f"{API}/projects/{ed['p']}/function-requirements?unlinked=true", headers=ed["h"])
    assert r.status_code == 200, r.text
    return [f["fr_id"] for f in r.json()]


# ---- 5. the count (CC-3) ---------------------------------------------------------------------------------------------
def test_the_count_is_the_registers_unlinked_list_and_the_0_5_boundaries(client, ed):
    br1, br2, _, _ = two_brs(client, ed)
    linked, other = fr(client, ed, "Order form"), fr(client, ed, "Credit check")
    lnk(client, ed, br1, linked)
    r = row(panel(client, ed), "fr_unlinked")
    assert (r["measured"], r["verdict"]) == ("1.00", "FLAG")
    assert register_unlinked(client, ed) == [other["fr_id"]]
    lnk(client, ed, br2, other)                                       # every FR traced: equal to 0 is GREEN
    r = row(panel(client, ed), "fr_unlinked")
    assert (r["measured"], r["verdict"]) == ("0.00", "GREEN") and register_unlinked(client, ed) == []
    for i in range(6):
        fr(client, ed, f"Untraced {i}")
    out = panel(client, ed)
    assert (row(out, "fr_unlinked")["measured"], row(out, "fr_unlinked")["verdict"]) == ("6.00", "ESCALATE")
    assert len(register_unlinked(client, ed)) == 6
    edit(client, ed, "fr_unlinked", threshold_value="0", escalate_value="6")       # equal to escalate is FLAG
    assert row(panel(client, ed), "fr_unlinked")["verdict"] == "FLAG"


def test_a_link_to_a_retired_br_or_a_retired_link_counts_as_unlinked_and_a_retired_fr_drops_out(client, ed):
    br1, br2, _, _ = two_brs(client, ed)
    a, b, c = fr(client, ed, "A"), fr(client, ed, "B"), fr(client, ed, "C")
    lnk(client, ed, br1, a)
    lnk(client, ed, br2, b)
    assert row(panel(client, ed), "fr_unlinked")["measured"] == "1.00"             # c
    with owner_engine().begin() as conn:            # stage the states directly: only liveness is read
        conn.execute(text(f"UPDATE business_requirement SET is_active = false WHERE br_id = {br1['br_id']}"))
        conn.execute(text(f"UPDATE br_function_requirement SET is_active = false WHERE fr_id = {b['fr_id']}"))
        conn.execute(text(f"UPDATE function_requirement SET is_active = false WHERE fr_id = {c['fr_id']}"))
    assert row(panel(client, ed), "fr_unlinked")["measured"] == "2.00"             # a, b
    assert sorted(register_unlinked(client, ed)) == sorted([a["fr_id"], b["fr_id"]])


def test_effort_days_stand_beside_the_count_only_when_effort_is_on(client, ed, world):
    set_components(client, world, ed["p"], ["FUNCTION_REQUIREMENT"])     # off before any rate row exists
    f = fr(client, ed, "Rated")
    fr(client, ed, "Unrated")
    r = row(panel(client, ed), "fr_unlinked")
    assert r["measured"] == "2.00" and "effort_days" not in r["figures"]
    set_components(client, world, ed["p"], ["FUNCTION_REQUIREMENT", "EFFORT"])
    assert rate(client, ed, f, "MEDIUM").status_code == 200
    days = client.get(f"{API}/function-requirements/{f['fr_id']}", headers=ed["h"]).json()["effort_days"]
    r = row(panel(client, ed), "fr_unlinked")
    assert r["measured"] == "2.00" and Decimal(r["figures"]["effort_days"]) == Decimal(days) > 0


def test_not_measured_with_the_component_off_or_no_live_fr(client, ed, world):
    r = row(panel(client, ed), "fr_unlinked")
    assert (r["reason"], r["verdict"], r["measured"]) == ("NO_FRS", "NOT_MEASURED", None)
    f = fr(client, ed, "Gone")
    with owner_engine().begin() as conn:
        conn.execute(text(f"UPDATE function_requirement SET is_active = false WHERE fr_id = {f['fr_id']}"))
    assert row(panel(client, ed), "fr_unlinked")["reason"] == "NO_FRS"               # a retired FR is no FR
    set_components(client, world, ed["p"], ["AS_IS"])                     # only live rows block switching it off
    assert row(panel(client, ed), "fr_unlinked")["reason"] == "FUNCTION_REQUIREMENT_OFF"


# ---- 6. seed and panel -----------------------------------------------------------------------------------------------
def test_the_rule_backfills_off_and_measured_and_a_new_project_has_it_on(client, ed, db):
    got = db.scalar(select(ControlRule).where(ControlRule.project_id == ed["p"],
                                              ControlRule.analysis_code == "fr_unlinked"))
    assert got.is_enabled
    house = db.scalar(select(ControlRule).where(ControlRule.project_id.is_(None),
                                                ControlRule.analysis_code == "fr_unlinked"))
    assert (house.comparison, house.threshold_value, house.escalate_value) == ("GT", 0, 5)
    assert house.prescribed_action.startswith("Link or retire before the next freeze")
    with owner_engine().begin() as conn:                         # stage a running project from before C3
        conn.execute(text(f"DELETE FROM control_rule WHERE project_id = {ed['p']} AND analysis_code = 'fr_unlinked'"))
    assert {"project_id": ed["p"], "added": ["fr_unlinked"]} in control.backfill(db, "admin@example.test")["projects"]
    r = row(panel(client, ed), "fr_unlinked")
    assert (r["is_enabled"], r["verdict"], r["off_state"], r["reason"]) == (False, None, "NOT_YET_AGREED", "NO_FRS")


# ---- 5. migration 0082 -----------------------------------------------------------------------------------------------
def test_0082_an_edited_rule_refuses_the_downgrade_and_changes_nothing(client, ed, owner):
    x(owner, "UPDATE control_rule SET threshold_value = 3, change_rationale = 'Client agreed', row_version = 2 "
             "WHERE project_id = :p AND analysis_code = 'fr_unlinked'", p=ed["p"])
    head = q(owner, "SELECT version_num FROM alembic_version")[0][0]
    n = q(owner, "SELECT count(*) FROM control_rule WHERE analysis_code = 'fr_unlinked'")[0][0]
    with pytest.raises(Exception, match="edited fr_unlinked control rule"):
        command.downgrade(_cfg(), "0081")
    assert q(owner, "SELECT version_num FROM alembic_version")[0][0] == head
    assert q(owner, "SELECT count(*) FROM control_rule WHERE analysis_code = 'fr_unlinked'")[0][0] == n >= 2
    assert q(owner, "SELECT threshold_value FROM control_rule WHERE project_id = :p AND analysis_code = 'fr_unlinked'",
             p=ed["p"])[0][0] == 3


def test_0082_unedited_rules_go_with_the_downgrade_and_the_upgrade_takes_them_again(client, ed, owner):
    assert q(owner, "SELECT count(*) FROM control_rule WHERE analysis_code = 'fr_unlinked'")[0][0] >= 2
    others = q(owner, "SELECT count(*) FROM control_rule WHERE analysis_code <> 'fr_unlinked'")[0][0]
    command.downgrade(_cfg(), "0081")
    assert q(owner, "SELECT count(*) FROM control_rule WHERE analysis_code = 'fr_unlinked'")[0][0] == 0
    assert q(owner, "SELECT count(*) FROM control_rule")[0][0] == others              # no other rule touched
    with pytest.raises(Exception, match="ck_ctl_analysis"):
        x(owner, "INSERT INTO control_rule (analysis_code, comparison, threshold_value, is_house_default) "
                 "VALUES ('fr_unlinked', 'GT', 0, true)")
    command.upgrade(_cfg(), "0082")
    x(owner, "INSERT INTO control_rule (analysis_code, comparison, threshold_value, is_house_default) "
             "VALUES ('fr_unlinked', 'GT', 0, true)")
