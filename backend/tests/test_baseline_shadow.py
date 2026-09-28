"""The shadow generator and its parity check (§6.1, §13). Exercised on a foundation table so
slice 5 only has to add the frozen entities."""
from sqlalchemy import Column, MetaData, String, Table

from models import Client
from services.baseline_shadow import parity_problems, shadow_table


def test_shadow_drops_audit_and_pk_and_adds_snapshot_columns():
    shadow = shadow_table(Client.__table__, MetaData(), baseline_fk=False)
    assert {c.name for c in shadow.columns} == {
        "baseline_client_id", "baseline_id", "source_id", "client_code", "client_name", "industry"}
    assert parity_problems(Client.__table__, shadow) == []


def test_parity_catches_a_live_column_added_without_its_shadow():
    md = MetaData()
    live = Table("thing", md, Column("thing_id", String, primary_key=True), Column("name", String))
    shadow = shadow_table(live, md, baseline_fk=False)
    live.append_column(Column("new_field", String))
    assert parity_problems(live, shadow) == ["baseline_thing: missing ['new_field']"]
