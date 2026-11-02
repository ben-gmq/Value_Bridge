"""Slice Risks piece C: the `risk_register` control rule (docs/slice_risks_spec.md §6, §9 criteria 7–8; RK-2, RK-5;
design §7.13 "exposure ≥ 12 open, ≥ 16 escalate"). Grade 2: a wrong colour reaches a steering meeting.

Deliberately uncovered: the panel's speed with more than 500 risks (one indexed aggregate, ix_risk_open)."""
import pytest
from alembic import command
from sqlalchemy import select, text

from models import ControlRule
from services import control
from tests.conftest import ALL_COMPONENTS, owner_engine
from tests.test_br_fr import set_components
from tests.test_control import edit, panel, role, row
from tests.test_issue_api import stakeholder
from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture
from tests.test_risk_api import edit as edit_risk, promote, risk
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture


def measured(client, ed) -> tuple:
    r = row(panel(client, ed), "risk_register")
    return r["measured"], r["verdict"], r["reason"]


# ---- 7. the headline -------------------------------------------------------------------------------------------------
def test_highest_open_exposure_with_12_flag_and_16_escalate_equal_included(client, ed):
    assert measured(client, ed) == (None, "NOT_MEASURED", "NO_OPEN_RISKS")           # none open: never 0
    owner_ = role(client, ed)
    r = risk(client, ed, owner_, p="POSSIBLE", i="MAJOR")                           # 3 x 4 = 12
    assert measured(client, ed) == ("12.00", "FLAG", None)
    edit_risk(client, ed, r, impact_code="MODERATE")                                # 9
    risk(client, ed, owner_, "Second", p="UNLIKELY", i="SEVERE")                     # 2 x 5 = 10
    assert measured(client, ed) == ("10.00", "GREEN", None)
    top = risk(client, ed, owner_, "Top", p="LIKELY", i="MAJOR")                     # 16
    assert measured(client, ed) == ("16.00", "ESCALATE", None)
    out = row(panel(client, ed), "risk_register")["figures"]
    assert (out["open_count"], out["open_without_target"]) == (3, 3)
    edit_risk(client, ed, top, status_code="MITIGATING")                            # still open
    assert measured(client, ed)[0] == "16.00"
    edit_risk(client, ed, top, status_code="CLOSED")
    assert measured(client, ed) == ("10.00", "GREEN", None)


def test_a_materialised_or_retired_risk_drops_out_and_the_component_off_is_not_measured(client, ed, world):
    owner_ = role(client, ed)
    r = risk(client, ed, owner_, p="ALMOST_CERTAIN", i="SEVERE")
    promote(client, ed, r, stakeholder(client, ed))
    assert measured(client, ed) == (None, "NOT_MEASURED", "NO_OPEN_RISKS")
    gone = risk(client, ed, owner_, "Gone", p="LIKELY", i="MAJOR")
    rv = client.get(f"/api/v1/risks/{gone['risk_id']}", headers=ed["h"]).json()["row_version"]
    assert client.delete(f"/api/v1/risks/{gone['risk_id']}", headers=ed["h"],
                         params={"row_version": rv}).status_code == 204
    assert measured(client, ed)[2] == "NO_OPEN_RISKS"
    with owner_engine().begin() as conn:                     # RISK off needs no live risk; the promoted one is live
        conn.execute(text(f"UPDATE risk SET is_active = false WHERE project_id = {ed['p']}"))
    set_components(client, world, ed["p"], [c for c in ALL_COMPONENTS if c != "RISK"])
    assert measured(client, ed) == (None, "NOT_MEASURED", "RISK_OFF")


def test_a_client_edit_of_the_numbers_is_read_with_ge(client, ed):
    owner_ = role(client, ed)
    risk(client, ed, owner_, p="LIKELY", i="MODERATE")                              # 12
    edit(client, ed, "risk_register", threshold_value="15", escalate_value="20")
    assert measured(client, ed) == ("12.00", "GREEN", None)
    edit(client, ed, "risk_register", threshold_value="12", escalate_value="12.5")
    assert measured(client, ed) == ("12.00", "FLAG", None)


# ---- 8. seed and migration -------------------------------------------------------------------------------------------
def test_the_rule_backfills_off_and_measured_and_a_new_project_has_it_on(client, ed, db):
    got = db.scalar(select(ControlRule).where(ControlRule.project_id == ed["p"],
                                              ControlRule.analysis_code == "risk_register"))
    assert got.is_enabled and got.comparison == "GE"
    house = db.scalar(select(ControlRule).where(ControlRule.project_id.is_(None),
                                                ControlRule.analysis_code == "risk_register"))
    assert (house.comparison, house.threshold_value, house.escalate_value) == ("GE", 12, 16)
    assert house.prescribed_action == "Mitigation owner + date; steering if unmitigated"
    with owner_engine().begin() as conn:                         # stage a running project from before the slice
        conn.execute(text(f"DELETE FROM control_rule WHERE project_id = {ed['p']} AND analysis_code = 'risk_register'"))
    assert {"project_id": ed["p"], "added": ["risk_register"]} in control.backfill(db, "admin@example.test")["projects"]
    r = row(panel(client, ed), "risk_register")
    assert (r["is_enabled"], r["verdict"], r["off_state"], r["reason"]) == (False, None, "NOT_YET_AGREED",
                                                                             "NO_OPEN_RISKS")


@pytest.mark.slow
def test_0083_an_edited_ge_rule_refuses_the_downgrade_and_changes_nothing(client, ed, owner):
    x(owner, "UPDATE control_rule SET threshold_value = 10, change_rationale = 'Client agreed', row_version = 2 "
             "WHERE project_id = :p AND analysis_code = 'risk_register'", p=ed["p"])
    head = q(owner, "SELECT version_num FROM alembic_version")[0][0]
    with pytest.raises(Exception, match="edited GE control rule"):
        command.downgrade(_cfg(), "0082")
    assert q(owner, "SELECT version_num FROM alembic_version")[0][0] == head
    assert q(owner, "SELECT threshold_value FROM control_rule WHERE project_id = :p AND analysis_code = 'risk_register'",
             p=ed["p"])[0][0] == 10
