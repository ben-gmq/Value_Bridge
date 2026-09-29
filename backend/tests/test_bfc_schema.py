"""Slice 1 — the rules the database itself carries for the BFC, requirements, data entities and
their links (§5.3, D-2, D-23, D-24, D-24a, S1-1…S1-7). Services come later; these prove the
backstop holds even when a service is wrong."""
import pytest
from sqlalchemy import MetaData, text
from sqlalchemy.exc import IntegrityError

from models import BfcNodeDataEntity, BfcNodeOrgRole, BrDataEntity, BrOrgRole
from services.baseline_shadow import shadow_table


def _code(db, category, code):
    return db.execute(text("SELECT code_id FROM code_master WHERE category = :c AND code = :k "
                           "AND project_id IS NULL"), {"c": category, "k": code}).scalar_one()


def _refused(db, fn):
    with pytest.raises(IntegrityError):
        fn()
    db.rollback()


class W:
    """A tiny raw-SQL world: one project, one actor. Every insert goes in as vb_app."""

    def __init__(self, db, world, project="p_solo"):
        self.db, self.p, self.u = db, world[project], world["users"]["owner"]

    def ins(self, table, **cols):
        cols = {"project_id": self.p, "created_by": self.u, **cols}
        names = ", ".join(cols)
        binds = ", ".join(f":{k}" for k in cols)
        pk = {"business_requirement": "br_id"}.get(table, f"{table}_id")
        return self.db.execute(text(f"INSERT INTO {table} ({names}) VALUES ({binds}) RETURNING {pk}"),
                               cols).scalar_one()

    def node(self, parent=None, level=1, seq=1, process=False, code=None, name=None):
        return self.ins("bfc_node", parent_bfc_node_id=parent, level_no=level, seq_no=seq,
                        is_process=process, hier_code=code or f"{level}.{seq}.{parent}",
                        node_name=name or f"n{level}{seq}{parent}")

    def step(self, seq=1):
        """L1 (at position `seq`) → L2 → L3 process step."""
        a = self.node(seq=seq)
        b = self.node(parent=a, level=2)
        return self.node(parent=b, level=3, process=True)

    def de(self, n=1):
        return self.ins("data_entity", de_number=f"DE-{n:04d}", de_name=f"Entity {n}")

    def br(self, node, n=1):
        return self.ins("business_requirement", bfc_node_id=node, br_number=f"BR-{n:04d}",
                        status_code_id=_code(self.db, "BR_STATUS", "DRAFT"))

    def io(self, node, de, direction):
        return self.ins("bfc_node_data_entity", bfc_node_id=node, data_entity_id=de, direction=direction)

    def unit_role(self):
        unit = self.ins("org_unit", level_no=1, seq_no=1, org_unit_code="U", org_unit_name="U",
                        level_code_id=_code(self.db, "ORG_UNIT_LEVEL", "DEPARTMENT"))
        return self.ins("org_role", org_unit_id=unit, org_role_code="R", org_role_name="R")

    def raci(self, table, owner_col, owner, org_role, code, behaviour):
        return self.ins(table, **{owner_col: owner}, org_role_id=org_role,
                        raci_code_id=_code(self.db, "RACI_TYPE", code), raci_behaviour=behaviour)


# ---- bfc_node: D-23 and sibling order -------------------------------------------------------

def test_l1_nodes_cannot_share_a_position(db, world):
    w = W(db, world)
    w.node(seq=1, code="01")
    _refused(db, lambda: w.node(seq=1, code="02"))


def test_a_process_has_no_children(db, world):
    w = W(db, world)
    step = w.step()
    _refused(db, lambda: w.node(parent=step, level=4))


def test_process_level_rules(db, world):
    w = W(db, world)
    a = w.node()
    _refused(db, lambda: w.node(parent=a, level=2, process=True))      # a process is L3+
    a = w.node()
    b = w.node(parent=a, level=2)
    c = w.node(parent=b, level=3)
    d = w.node(parent=c, level=4)
    _refused(db, lambda: w.node(parent=d, level=5, process=False))     # L5 is always a process


def test_two_phase_reorder_swaps_siblings_and_codes(db, world):
    """S1-2 / S1-3: negative seq phase, then a temporary code, then the final codes."""
    w = W(db, world)
    a = w.node(seq=1, code="01")
    b = w.node(seq=2, code="02")
    db.execute(text("UPDATE bfc_node SET seq_no = -seq_no, hier_code = '~' || bfc_node_id "
                    "WHERE bfc_node_id IN (:a, :b)"), {"a": a, "b": b})
    db.execute(text("UPDATE bfc_node SET seq_no = CASE bfc_node_id WHEN :a THEN 2 ELSE 1 END, "
                    "hier_code = CASE bfc_node_id WHEN :a THEN '02' ELSE '01' END "
                    "WHERE bfc_node_id IN (:a, :b)"), {"a": a, "b": b})
    db.commit()
    got = dict(db.execute(text("SELECT bfc_node_id, hier_code FROM bfc_node")).all())
    assert got == {a: "02", b: "01"}


def test_link_to_another_projects_node_is_refused(db, world):
    w, other = W(db, world), W(db, world, "p_fin")
    foreign_step = other.step()
    de = w.de()
    db.commit()
    _refused(db, lambda: w.io(foreign_step, de, "I"))


# ---- business_requirement: D-2 -------------------------------------------------------------

def test_br_only_on_a_live_process_and_one_per_node(db, world):
    w = W(db, world)
    plain = w.node()
    _refused(db, lambda: w.br(plain))
    step = w.step()
    w.br(step, 1)
    _refused(db, lambda: w.br(step, 2))


def test_process_with_a_live_br_cannot_be_demoted(db, world):
    w = W(db, world)
    step = w.step()
    w.br(step)
    db.commit()
    _refused(db, lambda: db.execute(text("UPDATE bfc_node SET is_process = false WHERE bfc_node_id = :n"),
                                    {"n": step}))


def test_br_status_must_be_a_br_status_code(db, world):
    w = W(db, world)
    step = w.step()
    _refused(db, lambda: w.ins("business_requirement", bfc_node_id=step, br_number="BR-0001",
                               status_code_id=_code(db, "ISSUE_STATUS", "OPEN")))


# ---- step I/O licences BR CRUD and external flows: D-24 ------------------------------------

def test_crud_needs_step_io_in_the_matching_direction(db, world):
    w = W(db, world)
    step, de = w.step(), w.de()
    br = w.br(step)
    db.commit()
    crud = lambda c: w.ins("br_data_entity", br_id=br, bfc_node_id=step, data_entity_id=de, crud_code=c)
    _refused(db, lambda: crud("R"))                  # no I/O yet
    w.io(step, de, "O")
    db.commit()
    _refused(db, lambda: crud("R"))                  # R reads: needs an input
    crud("C")                                        # C writes: the output licenses it
    db.commit()


def test_crud_row_must_carry_its_brs_own_node(db, world):
    w = W(db, world)
    step, other_step, de = w.step(), w.step(seq=2), w.de()
    br = w.br(step)
    w.io(other_step, de, "O")
    db.commit()
    _refused(db, lambda: w.ins("br_data_entity", br_id=br, bfc_node_id=other_step,
                               data_entity_id=de, crud_code="C"))


def test_retiring_step_io_is_refused_while_crud_depends_on_it(db, world):
    w = W(db, world)
    step, de = w.step(), w.de()
    br = w.br(step)
    io = w.io(step, de, "O")
    w.ins("br_data_entity", br_id=br, bfc_node_id=step, data_entity_id=de, crud_code="U")
    db.commit()
    _refused(db, lambda: db.execute(text("UPDATE bfc_node_data_entity SET is_active = false "
                                         "WHERE bfc_node_data_entity_id = :i"), {"i": io}))


def test_external_flow_named_de_needs_step_io_but_unnamed_does_not(db, world):
    w = W(db, world)
    step, de = w.step(), w.de()
    ext = w.ins("external_entity", ext_number="EXT-0001", ext_name="Bank")
    db.commit()
    flow = lambda d: w.ins("bfc_node_external_flow", bfc_node_id=step, external_entity_id=ext,
                           direction="I", data_entity_id=d)
    _refused(db, lambda: flow(de))
    flow(None)
    db.commit()
    _refused(db, lambda: flow(None))                 # grain is NULLS NOT DISTINCT: restore, never re-insert


# ---- RACI keys on behaviour: VB law 5 ------------------------------------------------------

def test_one_accountable_and_one_responsible_per_step(db, world):
    w = W(db, world)
    step, r1 = w.step(), w.unit_role()
    r2 = w.ins("org_role", org_unit_id=db.execute(text("SELECT org_unit_id FROM org_role WHERE "
                                                       "org_role_id = :r"), {"r": r1}).scalar_one(),
               org_role_code="R2", org_role_name="R2")
    w.raci("bfc_node_org_role", "bfc_node_id", step, r1, "A", "ACCOUNTABLE")
    w.raci("bfc_node_org_role", "bfc_node_id", step, r1, "R", "RESPONSIBLE")
    db.commit()
    _refused(db, lambda: w.raci("bfc_node_org_role", "bfc_node_id", step, r2, "A", "ACCOUNTABLE"))
    _refused(db, lambda: w.raci("bfc_node_org_role", "bfc_node_id", step, r2, "R", "RESPONSIBLE"))


def test_raci_behaviour_must_match_the_code(db, world):
    """The service copies behaviour from the code; the FK refuses a copy that disagrees."""
    w = W(db, world)
    step, role = w.step(), w.unit_role()
    br = w.br(step)
    db.commit()
    _refused(db, lambda: w.raci("br_org_role", "br_id", br, role, "C", "ACCOUNTABLE"))


# ---- data_field ----------------------------------------------------------------------------

def test_fk_field_must_point_into_the_referenced_entity(db, world):
    w = W(db, world)
    order, customer, other = w.de(1), w.de(2), w.de(3)
    cust_id = w.ins("data_field", data_entity_id=customer, seq_no=1, field_name="id",
                    is_primary_key=True, pk_ordinal=1)
    db.commit()
    fk = lambda ref_de: w.ins("data_field", data_entity_id=order, seq_no=1, field_name="customer_id",
                              is_foreign_key=True, ref_data_entity_id=ref_de, ref_data_field_id=cust_id,
                              fk_group_no=1)
    _refused(db, lambda: fk(other))
    fk(customer)
    db.commit()


def test_data_type_must_be_a_field_data_type(db, world):
    w = W(db, world)
    de = w.de()
    _refused(db, lambda: w.ins("data_field", data_entity_id=de, seq_no=1, field_name="x",
                               data_type_code_id=_code(db, "BR_STATUS", "DRAFT")))


def test_retired_field_name_can_be_reused(db, world):
    """S1-6."""
    w = W(db, world)
    de = w.de()
    f = w.ins("data_field", data_entity_id=de, seq_no=1, field_name="Amount")
    db.commit()
    _refused(db, lambda: w.ins("data_field", data_entity_id=de, seq_no=2, field_name=" amount"))
    db.execute(text("UPDATE data_field SET is_active = false WHERE data_field_id = :f"), {"f": f})
    w.ins("data_field", data_entity_id=de, seq_no=2, field_name="Amount")
    db.commit()


# ---- S1-5: link tables keep their link in a baseline shadow ---------------------------------

@pytest.mark.parametrize("model, link_cols", [
    (BfcNodeDataEntity, {"bfc_node_id", "data_entity_id", "direction"}),
    (BrDataEntity, {"br_id", "data_entity_id", "crud_code", "bfc_node_id"}),
    (BfcNodeOrgRole, {"bfc_node_id", "org_role_id", "raci_code_id", "raci_behaviour"}),
    (BrOrgRole, {"br_id", "org_role_id", "raci_code_id", "raci_behaviour"}),
])
def test_link_table_shadow_keeps_the_link(model, link_cols):
    shadow = shadow_table(model.__table__, MetaData(), baseline_fk=False)
    assert link_cols <= {c.name for c in shadow.columns}


# ---- sara L5: every hand-written guard FK is proven, not only two ---------------------------

def _demote(db, node):
    db.execute(text("UPDATE bfc_node SET is_process = false WHERE bfc_node_id = :n"), {"n": node})


@pytest.mark.parametrize("dependent", ["step_io", "step_raci", "external_flow"])
def test_process_with_a_live_step_link_cannot_be_demoted(db, world, dependent):
    w = W(db, world)
    step = w.step()
    if dependent == "step_io":
        w.io(step, w.de(), "I")
    elif dependent == "step_raci":
        w.raci("bfc_node_org_role", "bfc_node_id", step, w.unit_role(), "C", "CONSULTED")
    else:
        ext = w.ins("external_entity", ext_number="EXT-0001", ext_name="Bank")
        w.ins("bfc_node_external_flow", bfc_node_id=step, external_entity_id=ext, direction="O")
    db.commit()
    _refused(db, lambda: _demote(db, step))


@pytest.mark.parametrize("table, owner_col", [("bfc_node_org_role", "bfc_node_id"),
                                              ("br_org_role", "br_id")])
def test_raci_to_another_projects_org_role_is_refused(db, world, table, owner_col):
    w, other = W(db, world), W(db, world, "p_fin")
    step = w.step()
    owner = step if owner_col == "bfc_node_id" else w.br(step)
    foreign_role = other.unit_role()
    db.commit()
    _refused(db, lambda: w.raci(table, owner_col, owner, foreign_role, "C", "CONSULTED"))


def test_bfc_seq_range(db, world):
    w = W(db, world)
    w.node(seq=-99, code="NEG")
    db.commit()
    for i, bad in enumerate((0, 100, -100)):
        _refused(db, lambda bad=bad, i=i: w.node(seq=bad, code=f"B{i}"))


def test_field_seq_range(db, world):
    w = W(db, world)
    de = w.de()
    w.ins("data_field", data_entity_id=de, seq_no=999, field_name="last")
    db.commit()
    for i, bad in enumerate((0, 1000, -1000)):
        _refused(db, lambda bad=bad, i=i: w.ins("data_field", data_entity_id=de, seq_no=bad,
                                                field_name=f"f{i}"))
