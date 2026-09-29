"""Client organisation — the declarative rules the database carries (§5.3 ORG_UNIT, S1-1…S1-6)."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def _code(db, category, code):
    return db.execute(text("SELECT code_id FROM code_master WHERE category = :c AND code = :k "
                           "AND project_id IS NULL"), {"c": category, "k": code}).scalar_one()


def _unit(db, world, *, project="p_solo", parent=None, level=1, seq=1, code="U1",
          level_code=None):
    return db.execute(text(
        "INSERT INTO org_unit (project_id, parent_org_unit_id, level_no, level_code_id, "
        "org_unit_code, org_unit_name, seq_no, created_by) "
        "VALUES (:p, :parent, :lvl, :lc, :code, :code, :seq, :u) RETURNING org_unit_id"),
        {"p": world[project], "parent": parent, "lvl": level, "seq": seq, "code": code,
         "lc": level_code or _code(db, "ORG_UNIT_LEVEL", "DEPARTMENT"),
         "u": world["users"]["owner"]}).scalar_one()


def _refused(db, fn):
    with pytest.raises(IntegrityError):
        fn()
    db.rollback()


def test_l1_units_cannot_share_a_position(db, world):
    """S1-1: NULL parent is one shared parent — the original (parent, seq_no) key let this in."""
    _unit(db, world, seq=1, code="A")
    _refused(db, lambda: _unit(db, world, seq=1, code="B"))


def test_same_position_is_fine_in_another_project(db, world):
    _unit(db, world, seq=1, code="A")
    _unit(db, world, project="p_fin", seq=1, code="A")
    db.commit()


def test_retired_code_can_be_reused_but_live_code_cannot(db, world):
    """S1-6: unique among live units, normalised."""
    first = _unit(db, world, seq=1, code="FIN")
    db.commit()
    _refused(db, lambda: _unit(db, world, seq=2, code=" fin "))
    db.execute(text("UPDATE org_unit SET is_active = false WHERE org_unit_id = :i"), {"i": first})
    _unit(db, world, seq=3, code="FIN")
    db.commit()


def test_level_code_must_be_an_org_unit_level(db, world):
    """S1-4: a code from another category is refused by the database, not only the service."""
    wrong = _code(db, "BR_STATUS", "DRAFT")
    _refused(db, lambda: _unit(db, world, level_code=wrong))


def test_parent_must_be_in_the_same_project(db, world):
    other = _unit(db, world, project="p_fin", code="X")
    db.commit()
    _refused(db, lambda: _unit(db, world, parent=other, level=2, code="Y"))


def test_root_iff_level_one_and_depth_capped(db, world):
    root = _unit(db, world, code="R")
    _refused(db, lambda: _unit(db, world, level=2, seq=2, code="NOPARENT"))
    root = _unit(db, world, code="R")
    _refused(db, lambda: _unit(db, world, parent=root, level=4, code="DEEP"))


def test_seq_range_allows_reorder_phase_but_not_zero_or_hundred(db, world):
    """S1-3: negatives exist mid-reorder; 0 and ±100 never."""
    _unit(db, world, seq=-5, code="NEG")
    db.commit()
    for bad in (0, 100, -100):
        _refused(db, lambda bad=bad: _unit(db, world, seq=bad, code=f"S{bad}"))
