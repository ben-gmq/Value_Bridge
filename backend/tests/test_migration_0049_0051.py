"""Slice 10b migrations on real data (docs/slice10b_schema.md §3, §9; Grade 1 for the backfill).

The suite's schema fixture migrates an empty database, so here a world is built through the API at head
(before any direct link exists), the chain is stepped back to 0048, the OLD view is read, and the chain is
upgraded again: every derived BR → FR path must come back as exactly one live link, step-retired paths as
retired links a step restore brings back, retired FRs not at all. Then: each downgrade refuses once a row the
backfill did not write exists, and a re-run after a downgrade neither duplicates rows nor audit events."""
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from tests.conftest import BACKEND, OWNER_URL
from tests.test_baseline import bid, freeze, scope
from tests.test_function_requirement_api import fr
from tests.test_scope_api import API, ed, node  # noqa: F401 — ed is a fixture
from tests.test_solution_api import link, sol
from tests.test_step_retire import _br, restore, retire


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


def world(client, ed):
    """Two BRs answered by SOL-1, one also by SOL-2; FRs tagged SOL-1 (two), SOL-2 (one), none (one, D-28);
    a third step whose pairing a step retire took; a retired FR tagged SOL-1."""
    a = node(client, ed, "Sales")
    g = node(client, ed, "Order to cash", a["bfc_node_id"])
    steps = [node(client, ed, n, g["bfc_node_id"], is_process=True) for n in ("Take", "Approve", "Ship")]
    brs = [_br(client, ed, s["bfc_node_id"]) for s in steps]
    s1, s2 = sol(client, ed, "Approval matrix"), sol(client, ed, "Credit check")
    for br in brs:
        assert link(client, ed, br["br_id"], s1["solution_id"]).status_code == 201
    assert link(client, ed, brs[0]["br_id"], s2["solution_id"]).status_code == 201
    f1 = fr(client, ed, name="Order form", solution_id=s1["solution_id"])
    f2 = fr(client, ed, name="Order report", fr_type="REPORT", solution_id=s1["solution_id"])
    f3 = fr(client, ed, name="Credit batch", fr_type="BATCH", solution_id=s2["solution_id"])
    fr(client, ed, name="Loose form")                                         # no solution: untraced
    gone = fr(client, ed, name="Old form", solution_id=s1["solution_id"])
    cur = client.get(f"{API}/function-requirements/{gone['fr_id']}", headers=ed["h"]).json()
    assert client.delete(f"{API}/function-requirements/{gone['fr_id']}", headers=ed["h"],
                         params={"row_version": cur["row_version"]}).status_code == 204
    assert retire(client, ed, steps[2]["bfc_node_id"]).status_code == 204       # takes BR-3 ↔ SOL-1 with it
    return {"steps": steps, "brs": brs, "s1": s1, "s2": s2, "frs": (f1, f2, f3), "gone": gone}


def test_backfill_equals_the_old_view_and_keeps_step_retired_paths(client, ed, owner):
    w = world(client, ed)
    cfg = _cfg()
    command.downgrade(cfg, "0048")
    old = {tuple(r) for r in q(owner, "SELECT project_id, br_id, fr_id FROM v_br_function_requirement")}
    assert len(old) == 2 * 2 + 1                     # BR-1, BR-2 × (form, report) + BR-1 × credit batch
    command.upgrade(cfg, "head")
    live = q(owner, "SELECT project_id, br_id, fr_id, coverage_note, created_by FROM br_function_requirement "
                    "WHERE is_active")
    assert {(p, b, f) for p, b, f, _, _ in live} == old and len(live) == len(old)       # none lost, none invented
    assert {n for *_, n, _ in live} == {None}
    authors = {r[0] for r in q(owner, "SELECT DISTINCT created_by FROM br_solution")}
    assert {c for *_, c in live} <= authors
    # step-retired: BR-3 ↔ SOL-1 → retired links to the live FRs tagged SOL-1, stamped like the pairing
    dead = q(owner, "SELECT l.br_id, l.fr_id, l.deleted_at = bs.deleted_at FROM br_function_requirement l "
                    "JOIN br_solution bs ON bs.br_id = l.br_id WHERE NOT l.is_active")
    f1, f2, _ = w["frs"]
    assert {(b, f) for b, f, _ in dead} == {(w["brs"][2]["br_id"], f1["fr_id"]), (w["brs"][2]["br_id"], f2["fr_id"])}
    assert all(same for *_, same in dead)
    assert not q(owner, "SELECT 1 FROM br_function_requirement WHERE fr_id = :f", f=w["gone"]["fr_id"])  # Q-9
    ev = q(owner, "SELECT project_id, app_user_id, detail FROM audit_event WHERE event_type = 'BR_FR_BACKFILLED'")
    assert len(ev) == 1 and ev[0][0] == ed["p"] and ev[0][1] is None
    assert ev[0][2]["count"] == len(old) + 2 and ev[0][2]["live"] == len(old)
    # the view now reads the links, and the interface list's BR column follows it
    assert {tuple(r) for r in q(owner, "SELECT project_id, br_id, fr_id FROM v_br_function_requirement")} == old
    # undoing the pre-10b step retire brings its links back with it (Q-8)
    assert restore(client, ed, w["steps"][2]["bfc_node_id"]).status_code == 200
    back = client.get(f"{API}/business-requirements/{w['brs'][2]['br_id']}/function-requirements",
                      headers=ed["h"]).json()
    assert {r["fr_id"] for r in back} == {f1["fr_id"], f2["fr_id"]}


def test_a_rerun_after_a_downgrade_adds_nothing_twice(client, ed, owner):
    world(client, ed)
    cfg = _cfg()
    command.downgrade(cfg, "0048")
    command.upgrade(cfg, "head")
    before = q(owner, "SELECT count(*) FROM br_function_requirement")[0][0]
    command.downgrade(cfg, "0050")                   # view back to the 0024 body; rows stay
    command.upgrade(cfg, "head")
    assert q(owner, "SELECT count(*) FROM br_function_requirement")[0][0] == before
    assert q(owner, "SELECT count(*) FROM audit_event WHERE event_type = 'BR_FR_BACKFILLED'")[0][0] == 1


def test_downgrades_refuse_once_a_person_made_a_link_or_a_baseline_froze_one(client, ed, owner):
    w = scope(client, ed)
    f = fr(client, ed)
    r = client.post(f"{API}/business-requirements/{w['br1']['br_id']}/function-requirements", headers=ed["h"],
                    json={"fr_id": f["fr_id"]})
    assert r.status_code == 201, r.text
    cfg = _cfg()
    with pytest.raises(Exception, match="downgrade refused"):
        command.downgrade(cfg, "0048")               # 0049 refuses: a link the backfill did not write
    command.upgrade(cfg, "head")
    bid(freeze(client, ed))
    with pytest.raises(Exception, match="downgrade refused"):
        command.downgrade(cfg, "0049")               # 0050 refuses: frozen links are evidence
    assert q(owner, "SELECT count(*) FROM br_function_requirement")[0][0] == 1
