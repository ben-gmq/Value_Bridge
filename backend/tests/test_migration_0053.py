"""Migration 0053 on real data (slice13_schema §2.8; spec B1, B9; Grade 1 for the backfill): every project — live or
retired — gets exactly today's D-38 rule on both charts, authored by its creator, with one audit event each; the
header guard freezes the new columns; the downgrade refuses while a baseline records a rule or a project chose
another rule, and a re-run after a clean downgrade leaves exactly the same rule."""
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from tests.conftest import BACKEND, OWNER_URL
from tests.test_baseline import freeze, scope
from tests.test_dfd_rule import set_rule
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture


def _cfg() -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    os.environ["VB_ALEMBIC_URL"] = OWNER_URL
    return cfg


@pytest.fixture
def owner():
    eng = create_engine(OWNER_URL)
    yield eng
    command.upgrade(_cfg(), "head")                      # never leave the shared schema behind head
    eng.dispose()


def q(eng, sql, **kw):
    with eng.connect() as c:
        return c.execute(text(sql), kw).all()


def x(eng, sql, **kw):
    with eng.begin() as c:
        c.execute(text(sql), kw)


def test_the_backfill_gives_every_project_todays_rule_inactive_ones_included(client, world, ed, owner):
    x(owner, "UPDATE project SET is_active = false, deleted_at = now() WHERE project_id = :p", p=world["p_beta"])
    command.downgrade(_cfg(), "0052")
    assert not q(owner, "SELECT 1 FROM information_schema.tables WHERE table_name = 'project_dfd_rule'")
    command.upgrade(_cfg(), "head")
    rows = q(owner, "SELECT r.project_id, r.bfc_set_code, r.element_code, r.is_active, r.created_by = p.created_by "
                    "FROM project_dfd_rule r JOIN project p USING (project_id) ORDER BY 1, 2, 3")
    projects = [r[0] for r in q(owner, "SELECT project_id FROM project ORDER BY 1")]
    assert len(projects) == 4 and world["p_beta"] in projects
    assert rows == [(p, s, e, True, True) for p in projects for s in ("AS_IS", "TO_BE") for e in ("DATA_OUT", "STARTED")]
    ev = q(owner, "SELECT project_id, app_user_id, detail FROM audit_event "
                  "WHERE event_type = 'PROJECT_DFD_RULE_BACKFILLED' ORDER BY project_id")
    assert [e[0] for e in ev] == projects and all(e[1] is None for e in ev)
    assert ev[0][2]["rule"] == ["DATA_OUT", "STARTED"] and ev[0][2]["migration"] == "0053"
    assert {e[0]: e[2]["project_is_active"] for e in ev}[world["p_beta"]] is False
    # B1: a freeze that passed before the deploy still passes after it
    scope(client, ed)
    assert freeze(client, ed)["baseline"]["dfd_rule_to_be"] == ["STARTED", "DATA_OUT"]


def pre_13c(monkeypatch):
    """Freeze as the code before slice 13c did (hash spec 2): 0054's downgrade refuses to drop the volume columns
    under a spec-3 baseline (Q-26), so a test that steps the chain back below 0054 freezes the way its era did."""
    from services import freeze_set
    monkeypatch.setattr(freeze_set, "CURRENT_HASH_SPEC", 2)
    monkeypatch.setattr("services.baseline.CURRENT_HASH_SPEC", 2)


def test_the_downgrade_refuses_a_chosen_rule_or_a_recorded_one(client, world, ed, owner, monkeypatch):
    set_rule(client, world, ed["p"], ["STARTED", "DATA_IN", "DATA_OUT"])
    with pytest.raises(Exception, match="0053 downgrade refused: a project chose a DFD rule"):
        command.downgrade(_cfg(), "0052")
    set_rule(client, world, ed["p"], ["STARTED", "DATA_OUT"])
    scope(client, ed)
    pre_13c(monkeypatch)
    freeze(client, ed)
    with pytest.raises(Exception, match="0053 downgrade refused: a baseline records"):
        command.downgrade(_cfg(), "0052")
    assert q(owner, "SELECT count(*) FROM project_dfd_rule WHERE project_id = :p", p=ed["p"])[0][0] == 5


def test_a_clean_round_trip_keeps_the_guard_and_the_rule(client, world, ed, owner):
    command.downgrade(_cfg(), "0052")
    # the 0047 guard body is back: the old frozen columns are still guarded
    body = q(owner, "SELECT prosrc FROM pg_proc WHERE proname = 'fn_baseline_header_guard'")[0][0]
    assert "dfd_rule_to_be" not in body and "content_digest" in body
    command.upgrade(_cfg(), "head")
    body = q(owner, "SELECT prosrc FROM pg_proc WHERE proname = 'fn_baseline_header_guard'")[0][0]
    assert "NEW.dfd_rule_to_be IS DISTINCT FROM OLD.dfd_rule_to_be" in body
    assert "NEW.dfd_rule_as_is IS DISTINCT FROM OLD.dfd_rule_as_is" in body
    grants = q(owner, "SELECT column_name FROM information_schema.column_privileges WHERE table_name = 'baseline' "
                      "AND grantee = 'vb_app' AND privilege_type = 'UPDATE'")
    assert not {"dfd_rule_to_be", "dfd_rule_as_is"} & {g[0] for g in grants}
    assert q(owner, "SELECT count(*) FROM project_dfd_rule WHERE project_id = :p AND is_active", p=ed["p"])[0][0] == 4
