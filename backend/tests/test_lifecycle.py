"""FK_LIVENESS coverage (§5.4.15, §7.12): DEPENDENTS / PARENTS are derived from the models, and
every FK between business tables is either covered or deliberately excluded."""
from models import Base, DataField, OrgRole, OrgUnit
from services import lifecycle


def test_every_business_fk_is_covered_or_excluded():
    covered = {(ln.child.__table__.name, ln.parent.__table__.name) for ln in lifecycle.LINKS}
    missing = []
    for t in Base.metadata.sorted_tables:
        if "is_active" not in t.c:
            continue
        for fk in t.foreign_key_constraints:
            target = fk.referred_table
            if target.name in lifecycle.EXCLUDED_TARGETS or "is_active" not in target.c:
                continue
            if (t.name, target.name) not in covered:
                missing.append(f"{t.name}.{fk.name} -> {target.name}")
    assert missing == []


def test_the_easy_to_miss_links_are_there():
    """sara L7: a field referenced by another field, and a role under its unit."""
    assert any(ln.child is DataField and ("ref_data_field_id", "data_field_id") in ln.pairs
               for ln in lifecycle.dependents_of(DataField))
    assert any(ln.child is OrgRole for ln in lifecycle.dependents_of(OrgUnit))


def test_links_never_match_on_guard_columns():
    for ln in lifecycle.LINKS:
        assert not {p for _, p in ln.pairs} & lifecycle.GUARD_TARGET_COLUMNS, ln
