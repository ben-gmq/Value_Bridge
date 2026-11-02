"""VB-005 Control-C3 L1 + L2: "untraced" has one definition (`services/fr_trace.py`) and every place that shows it
agrees — the FR register's untraced view, the control panel's `fr_unlinked` row, the effort summary's untraced line and
the scope summary's traced / without-BR totals. Grade 2: a wrong count reaches a steering meeting.

The states that used to tell the readers apart are staged straight in the database (a link left live on a retired BR
cannot be made through the API — `step_retire.OWNED_BY_BR` retires it with the BR), so the test proves the readers
agree even if that cascade ever breaks."""
from sqlalchemy import text

from tests.conftest import owner_engine
from tests.test_br_fr import lnk, two_brs
from tests.test_control import panel, row
from tests.test_function_requirement_api import fr
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture


def _untraced_everywhere(client, ed) -> dict:
    p, h = ed["p"], ed["h"]
    reg = client.get(f"{API}/projects/{p}/function-requirements?unlinked=true", headers=h)
    reg_retired = client.get(f"{API}/projects/{p}/function-requirements?unlinked=true&include_retired=true", headers=h)
    eff = client.get(f"{API}/projects/{p}/effort-summary", headers=h)
    scope = client.get(f"{API}/projects/{p}/scope-summary", headers=h)
    for r in (reg, reg_retired, eff, scope):
        assert r.status_code == 200, r.text
    totals = scope.json()["totals"]
    return {"register": len(reg.json()), "register_with_retired_tick": len(reg_retired.json()),
            "panel": int(float(row(panel(client, ed), "fr_unlinked")["measured"])),
            "effort": eff.json()["untraced"]["count"],
            "scope": totals["frs_without_br"], "scope_traced": totals["frs_traced"]}


def test_every_reader_counts_the_same_untraced_frs(client, ed):
    br1, br2, _, _ = two_brs(client, ed)
    a, b, c, d = (fr(client, ed, n) for n in ("Traced", "Live link, retired BR", "Never linked", "Retired"))
    lnk(client, ed, br1, a)
    lnk(client, ed, br2, b)
    with owner_engine().begin() as conn:
        # b: its BR retired but the link left live — only "live link to a LIVE BR" counts as traced.
        conn.execute(text(f"UPDATE business_requirement SET is_active = false WHERE br_id = {br2['br_id']}"))
        # d: a retired, never-linked FR — not untraced work, even with "show retired" ticked (L2).
        conn.execute(text(f"UPDATE function_requirement SET is_active = false WHERE fr_id = {d['fr_id']}"))
    assert _untraced_everywhere(client, ed) == {"register": 2, "register_with_retired_tick": 2, "panel": 2,
                                                "effort": 2, "scope": 2, "scope_traced": 1}


def test_the_retired_tick_still_lists_retired_frs_on_the_other_views(client, ed):
    f = fr(client, ed, "Gone")
    with owner_engine().begin() as conn:
        conn.execute(text(f"UPDATE function_requirement SET is_active = false WHERE fr_id = {f['fr_id']}"))
    r = client.get(f"{API}/projects/{ed['p']}/function-requirements?include_retired=true", headers=ed["h"])
    assert r.status_code == 200 and [x["fr_id"] for x in r.json()] == [f["fr_id"]]
