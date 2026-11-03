"""Migrations 0087 (change_request, CR_STATUS behaviours) and 0088 (cr_impact; docs/slice_change_requests_spec.md §3).
Down clears the behaviours and up backfills them by code; a status code 0087 cannot map refuses the upgrade by name;
a change request or an impact row refuses the downgrade; the table CHECKs hold at the database; vb_app has no DELETE."""
import pytest
from alembic import command

from tests.test_change_request_api import analyse, cr_world, raise_cr, seeds
from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture


def exists(owner, table) -> bool:
    return bool(q(owner, f"SELECT to_regclass('public.{table}') IS NOT NULL")[0][0])


def behaviours(owner) -> dict:
    return {k: b for k, b in q(owner, "SELECT code, behaviour_code FROM code_master WHERE category = 'CR_STATUS' "
                                      "AND project_id IS NULL")}


def test_down_clears_the_behaviours_and_up_backfills_them_by_code(client, ed, owner):
    before = behaviours(owner)
    assert before == {"DRAFT": "OPEN", "ANALYSED": "OPEN", "PRICED": "PRICED", "DEFERRED": "DEFERRED",
                      "APPROVED": "APPROVED", "REJECTED": "REJECTED"}
    command.downgrade(_cfg(), "0086")
    assert not exists(owner, "change_request") and not exists(owner, "cr_impact")
    assert set(behaviours(owner).values()) == {None}
    command.upgrade(_cfg(), "0088")
    assert exists(owner, "cr_impact") and behaviours(owner) == before


def test_an_unknown_cr_status_refuses_the_upgrade_by_name(client, ed, owner):
    command.downgrade(_cfg(), "0086")
    x(owner, "INSERT INTO code_master (category, code, label) VALUES ('CR_STATUS', 'PARKED', 'Parked')")
    with pytest.raises(Exception, match="PARKED"):
        command.upgrade(_cfg(), "0087")
    assert not exists(owner, "change_request")
    x(owner, "DELETE FROM code_master WHERE category = 'CR_STATUS' AND code = 'PARKED'")   # test row only
    command.upgrade(_cfg(), "0088")


def test_a_change_request_or_an_impact_refuses_the_downgrade(client, ed, owner):
    w = cr_world(client, ed)
    cr = raise_cr(client, ed, w["v10"])
    seeds(client, ed, cr, [(w["keep"], "MODIFY")])
    analyse(client, ed, cr)
    with pytest.raises(Exception, match="change request impacts exist"):
        command.downgrade(_cfg(), "0087")
    assert exists(owner, "cr_impact")


def test_the_impact_checks_hold_at_the_database(client, ed, owner):
    w = cr_world(client, ed)
    cr = raise_cr(client, ed, w["v10"])
    seeds(client, ed, cr, [(w["keep"], "MODIFY")])
    row = q(owner, "SELECT cr_impact_id FROM cr_impact WHERE is_seed")[0][0]
    for bad, name in (("impacted_br_id = (SELECT br_id FROM business_requirement LIMIT 1)", "ck_cri_one_object"),
                      ("impact_type_code_id = NULL", "ck_cri_seed_has_type"),
                      ("reached_via = 'BR_FR'", "ck_cri_seed_route"),
                      ("value_unit = 'THB'", "ck_cri_value_on_benefit")):
        with pytest.raises(Exception, match=name):
            x(owner, f"UPDATE cr_impact SET {bad} WHERE cr_impact_id = {row}")


def test_the_change_request_checks_hold_at_the_database(client, ed, owner):
    w = cr_world(client, ed)
    cr = raise_cr(client, ed, w["v10"])
    i = cr["change_request_id"]
    for bad, name in (("budget_reference = 'PO-1'", "ck_cr_budget_all_or_none"),
                      ("raised_by_user_id = raised_by_user_id + 1", "ck_cr_raised_by_creator"),
                      ("unrated_fr_count = 0", "ck_cr_price_all_or_none")):
        with pytest.raises(Exception, match=name):
            x(owner, f"UPDATE change_request SET {bad} WHERE change_request_id = {i}")


def test_the_app_role_cannot_delete_either_table(client, ed, owner):
    grants = {(t, p) for t, p in q(owner, "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
                                          "WHERE grantee = 'vb_app' AND table_name IN ('change_request', 'cr_impact')")}
    assert {("change_request", "INSERT"), ("change_request", "UPDATE"), ("cr_impact", "SELECT")} <= grants
    assert not any(p == "DELETE" for _, p in grants)
