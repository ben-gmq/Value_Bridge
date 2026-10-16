"""FREEZE_SET as data (slice8_schema §3.1–§4; §7.7 HASH_COLUMNS, D-37 gates).

One entry per frozen table, in freeze (FK) order: its diff area, its hashed columns per hash-spec version,
its position columns (excluded from the hash; they drive MOVED, D-10), and how a diff row is labelled.
`live_select` is the one SELECT both the freeze (INSERT … SELECT) and the live side of a diff read, so a
live hash and a frozen hash are comparable by construction.

content_hash = sha256( concat_ws(E'\\x1f', coalesce(char_length(c::text) || ':' || c::text, E'\\x1e') …) ) in hex:
PostgreSQL's own text form of each value [Q-15], LENGTH-PREFIXED (DR8-L2) so no text can forge a boundary —
"A\\x1fB","C" and "A","B\\x1fC" differ — with \\x1f between values and \\x1e for NULL (a present value always
starts with a digit), so NULL, '' and the sentinel itself never collide.

The baseline's content_digest (DR8-S1, DR8-P2) is sha256 over every entity's ordered source_id:content_hash
list; the freeze computes it from the live set inside its snapshot, checks it against the preview the
person confirmed, stores it on the header, and every read of the baseline recomputes it from the shadows.
The spec version bumps when an existing entity's hashed list changes AND when a new entity joins the set
(slice10b §5.3, Q-14, amending slice8 §4): the new entity registers its list under the new version only
(`since=`), and the digest, the re-hash check and the freeze skip every entity unknown at a baseline's spec,
so a baseline frozen before the entity existed recomputes byte-identical to what it stored.
"""
import hashlib
from dataclasses import dataclass, field

from sqlalchemy import Select, Text, and_, cast, func, literal, not_, select
from sqlalchemy.dialects.postgresql import aggregate_order_by

from models import Base, BfcNode, CodeMaster
from models.baseline import SHADOW_TABLES, SHADOWED
from services import components
from services.baseline_shadow import code_pairs, snapshot_column_names

CURRENT_HASH_SPEC = 4       # 2: br_function_requirement joined the set (slice 10b, D-52)
#                             3: bfc_node gained the volume figures (slice 13c, D-67)
#                             4: slice 11 — br_requirement_line (D-59), br_data_field (D-60b) and br_system_flow
#                                (D-61) joined the set together (S11-6)
SEP, NULL_SENTINEL = "\x1f", "\x1e"


@dataclass(frozen=True)
class FrozenEntity:
    table: str
    area: str                                   # D-50 areas
    hash_columns: dict[int, tuple[str, ...]]
    position_columns: tuple[str, ...] = ()
    label_columns: tuple[str, ...] = ()         # the row's own label
    refs: tuple[tuple[str, str], ...] = ()      # (column, table): ends resolved inside the same side
    step_column: str | None = None              # the column that names the row's step, for the chart filter
    gate: components.Gate = field(default=components.ALWAYS)


def columns_for(e: FrozenEntity, version: int) -> tuple[str, ...] | None:
    """sara L5: the hashed list in force at `version` — the newest list at or below it. An entity that joined
    the set later has none for older versions: it was not frozen at that spec, so a baseline of that spec has
    no rows of it and its digest never included it (slice10b §5.3). Never a SCHEMA_VERSION_MISMATCH."""
    keys = [v for v in e.hash_columns if v <= version]
    return e.hash_columns[max(keys)] if keys else None


def _e(table, area, hashed, position=(), label=(), refs=(), step=None, since=1, more=None) -> FrozenEntity:
    """`since`: the hash spec the entity joined the set at. A new entity bumps CURRENT_HASH_SPEC and passes it.
    `more` {spec: list}: a later list for an entity already in the set (slice13_schema §3.7, F4). A later list
    EXTENDS the earlier one (asserted below), which the cross-spec diff relies on."""
    return FrozenEntity(table, area, {since: tuple(hashed), **{v: tuple(c) for v, c in (more or {}).items()}},
                        tuple(position), tuple(label), tuple(refs), step,
                        components.FREEZE_GATES.get(table, components.ALWAYS))


_BFC_1 = ("bfc_set_code", "is_process", "node_name", "purpose_desc", "data_processing_desc", "performer_kind",
          "performer_org_unit_id", "performer_org_role_id", "performer_application_id", "performer_label")
BFC, DE, BR, SOL, FR, APP, ORG = ("bfc_node", "data_entity", "business_requirement", "solution",
                                  "function_requirement", "application", "org_role")
FREEZE_SET: tuple[FrozenEntity, ...] = (
    _e("org_unit", "ORG", ("org_unit_code", "org_unit_name", "level_code", "description"),
       ("parent_org_unit_id", "level_no", "seq_no"), ("org_unit_code", "org_unit_name")),
    _e("org_role", "ORG", ("org_unit_id", "org_role_code", "org_role_name", "responsibility_desc", "headcount"),
       label=("org_role_code", "org_role_name")),
    _e("bfc_node", "BFC", _BFC_1, ("parent_bfc_node_id", "level_no", "seq_no", "hier_code"), ("hier_code", "node_name"),
       step="bfc_node_id", more={3: _BFC_1 + ("runs_per_period", "volume_period_code", "transactions_per_run",
                                             "transaction_unit_code", "seconds_per_transaction")}),
    _e("data_entity", "DATA", ("de_number", "de_name", "description", "business_owner_note"),
       label=("de_number", "de_name")),
    _e("data_field", "DATA", ("data_entity_id", "field_name", "data_type_code", "length_val", "precision_val",
                              "scale_val", "is_mandatory", "is_primary_key", "pk_ordinal", "is_foreign_key",
                              "ref_data_entity_id", "ref_data_field_id", "fk_group_no", "description"),
       ("seq_no",), ("field_name",), (("data_entity_id", DE),)),
    _e("external_entity", "DFD", ("ext_number", "ext_name", "kind_code", "description"),
       label=("ext_number", "ext_name")),
    _e("process_trigger", "DFD", ("trigger_name", "trigger_kind", "schedule_note", "description"),
       label=("trigger_name",)),
    _e("bfc_node_data_entity", "DFD", ("bfc_node_id", "data_entity_id", "direction", "note"),
       label=("direction",), refs=(("bfc_node_id", BFC), ("data_entity_id", DE)), step="bfc_node_id"),
    _e("bfc_node_org_role", "BFC", ("bfc_node_id", "org_role_id", "raci_code", "raci_behaviour"),
       label=("raci_label",), refs=(("bfc_node_id", BFC), ("org_role_id", ORG)), step="bfc_node_id"),
    _e("bfc_node_external_flow", "DFD", ("bfc_node_id", "external_entity_id", "direction", "data_entity_id",
                                         "flow_label", "note"),
       label=("direction", "flow_label"), refs=(("bfc_node_id", BFC), ("external_entity_id", "external_entity")),
       step="bfc_node_id"),
    _e("bfc_node_trigger", "DFD", ("bfc_node_id", "process_trigger_id", "note"),
       refs=(("bfc_node_id", BFC), ("process_trigger_id", "process_trigger")), step="bfc_node_id"),
    _e(BR, "BR", ("br_number", "bfc_node_id", "br_statement", "business_logic", "output_expectation"),
       label=("br_number",), refs=(("bfc_node_id", BFC),)),
    _e("br_data_entity", "BR", ("br_id", "data_entity_id", "crud_code", "usage_note"),
       label=("crud_code",), refs=(("br_id", BR), ("data_entity_id", DE))),
    _e("br_org_role", "BR", ("br_id", "org_role_id", "raci_code", "raci_behaviour"),
       label=("raci_label",), refs=(("br_id", BR), ("org_role_id", ORG))),
    # D-59 (slice11_schema §5): numbered requirement lines; seq_no is display order, a position column (MOVED).
    _e("br_requirement_line", "BR", ("br_id", "line_no", "line_kind_code", "priority_code", "line_text"),
       ("seq_no",), ("line_no",), (("br_id", BR),), since=4),
    # D-60(b): the attributes a BR uses, C / R / U. Spec 4 with the lines and flows: slice 11 reaches main as one (S11-6).
    _e("br_data_field", "BR", ("br_id", "data_entity_id", "data_field_id", "crud_code", "usage_note"),
       label=("crud_code",), refs=(("br_id", BR), ("data_entity_id", DE), ("data_field_id", "data_field")), since=4),
    _e(APP, "APPLICATION", ("application_code", "application_name", "vendor", "version_label", "app_kind_code",
                            "lifecycle_code", "description"), label=("application_code", "application_name")),
    _e(SOL, "SOLUTION", ("solution_number", "solution_name", "description", "category_code", "status_code",
                         "benefit_note", "effort_note"), label=("solution_number", "solution_name")),
    _e("br_solution", "SOLUTION", ("br_id", "solution_id", "coverage_note"), refs=(("br_id", BR),
                                                                                  ("solution_id", SOL))),
    _e(FR, "FR", ("fr_number", "fr_name", "description", "solution_id", "fr_type_code", "fr_type_behaviour",
                  "complexity_code", "effort_days", "acceptance_note"), label=("fr_number", "fr_name")),
    # D-52 (slice10b §5.2, Q-15): BR ↔ FR, labelled by its ends; joined the set at spec 2.
    _e("br_function_requirement", "FR", ("br_id", "fr_id", "coverage_note"), refs=(("br_id", BR), ("fr_id", FR)),
       since=2),
    _e("fr_interface", "APPLICATION", ("source_application_id", "target_application_id", "pattern_code",
                                       "method_code", "frequency_code", "volume_note"),
       refs=(("source_id", FR), ("source_application_id", APP), ("target_application_id", APP))),
    _e("fr_interface_data_entity", "APPLICATION", ("fr_id", "data_entity_id", "note"),
       refs=(("fr_id", FR), ("data_entity_id", DE))),
    _e("application_solution", "APPLICATION", ("application_id", "solution_id", "allocation_note"),
       refs=(("application_id", APP), ("solution_id", SOL))),
    _e("application_bfc_node", "APPLICATION", ("application_id", "bfc_node_id", "support_note"),
       refs=(("application_id", APP), ("bfc_node_id", BFC)), step="bfc_node_id"),
    _e("effort_rate", "EFFORT", ("fr_type_code", "complexity_code", "standard_days"),
       label=("fr_type_label", "complexity_label")),
    _e("project_component", "SCOPE", ("component_code",), label=("component_label",)),
)
BY_TABLE = {e.table: e for e in FREEZE_SET}
assert tuple(BY_TABLE) == SHADOWED, "FREEZE_SET and models.baseline.SHADOWED disagree"
# Grade 1 (slice10b §5.3): the spec-1 set is history. Every baseline frozen before 10b hashed exactly these 24
# entities; adding one here would change the digest of every one of them. A new entity uses `since=`.
SPEC_1_ENTITIES = ("org_unit", "org_role", "bfc_node", "data_entity", "data_field", "external_entity",
                   "process_trigger", "bfc_node_data_entity", "bfc_node_org_role", "bfc_node_external_flow",
                   "bfc_node_trigger", "business_requirement", "br_data_entity", "br_org_role", "application",
                   "solution", "br_solution", "function_requirement", "fr_interface", "fr_interface_data_entity",
                   "application_solution", "application_bfc_node", "effort_rate", "project_component")
assert tuple(e.table for e in FREEZE_SET if columns_for(e, 1) is not None) == SPEC_1_ENTITIES, \
    "an entity joined the spec-1 set: register it with since=<new spec> and bump CURRENT_HASH_SPEC"
assert all(columns_for(e, CURRENT_HASH_SPEC) is not None for e in FREEZE_SET), "an entity is newer than the spec"
assert all(max(e.hash_columns) <= CURRENT_HASH_SPEC for e in FREEZE_SET), "a hashed list is newer than the spec"
# slice13_schema §3.7: every later list of an entity extends its earlier one, so a cross-spec diff compares two sides
# on the older (shorter) list and never loses an area to SCHEMA_VERSION_MISMATCH.
assert all(later[:len(earlier)] == earlier
           for e in FREEZE_SET
           for earlier, later in zip([e.hash_columns[v] for v in sorted(e.hash_columns)],
                                     [e.hash_columns[v] for v in sorted(e.hash_columns)][1:])), \
    "a later hashed list must extend the earlier one (append only)"


def at_spec(version: int) -> tuple[FrozenEntity, ...]:
    """The entities frozen at hash spec `version`, in freeze order."""
    return tuple(e for e in FREEZE_SET if columns_for(e, version) is not None)


def shadow_columns(table: str) -> list[str]:
    """The non-key columns of baseline_<table>, in shadow order (copied, then code pairs)."""
    live = Base.metadata.tables[table]
    cols = snapshot_column_names(live)
    for p in code_pairs(live):
        cols += [f"{p}_code", f"{p}_label"]
    return cols


def hash_sql(exprs: list):
    parts = [func.coalesce(cast(func.char_length(cast(x, Text)), Text) + literal(":") + cast(x, Text),
                           literal(NULL_SENTINEL)) for x in exprs]
    return func.encode(func.sha256(func.convert_to(func.concat_ws(literal(SEP), *parts), "UTF8")), "hex")


def live_select(e: FrozenEntity, project_id: int, on: frozenset[str],
                version: int | None = None) -> Select | None:
    """The live rows a freeze takes for one entity under the components `on`: source_id, every shadow
    column, content_hash. None when the gate is closed or the entity is not in the set at `version`
    (default CURRENT_HASH_SPEC): the table freezes zero rows."""
    version = CURRENT_HASH_SPEC if version is None else version
    if not e.gate.open(on) or columns_for(e, version) is None:
        return None
    live = Base.metadata.tables[e.table]
    (pk,) = live.primary_key.columns
    cols = {n: live.c[n] for n in snapshot_column_names(live)}
    q_from = live
    for p in code_pairs(live):
        cm = CodeMaster.__table__.alias(f"cm_{p}")
        q_from = q_from.outerjoin(cm, cm.c.code_id == live.c[f"{p}_code_id"])
        cols[f"{p}_code"], cols[f"{p}_label"] = cm.c.code, cm.c.label
    where = [live.c.project_id == project_id, live.c.is_active]
    closed = e.gate.closed_sets(on)
    if closed:
        if e.table == "bfc_node":
            where.append(not_(live.c.bfc_set_code.in_(closed)))
        else:
            node = BfcNode.__table__.alias("step")
            q_from = q_from.join(node, node.c.bfc_node_id == live.c[e.step_column])
            where.append(not_(node.c.bfc_set_code.in_(closed)))
    hashed = [cols[c] for c in columns_for(e, version)]
    return (select(pk.label("source_id"), *[x.label(n) for n, x in cols.items()],
                   hash_sql(hashed).label("content_hash"))
            .select_from(q_from).where(and_(*where)).order_by(pk))


def shadow(table: str):
    return SHADOW_TABLES[table]


def _agg(sub) -> object:
    return select(func.coalesce(func.string_agg(cast(sub.c.source_id, Text) + literal(":") + sub.c.content_hash,
                                                aggregate_order_by(literal(","), sub.c.source_id)), literal("")))


def rehash_mismatches(db, e: FrozenEntity, baseline_id: int, version: int) -> int:
    """sara M3: frozen rows whose stored content_hash no longer matches their own columns. An entity unknown at
    `version` has no list to check against: any row it holds under that baseline is itself a mismatch."""
    t = SHADOW_TABLES[e.table]
    if columns_for(e, version) is None:
        return db.scalar(select(func.count()).select_from(t).where(t.c.baseline_id == baseline_id))
    return db.scalar(select(func.count()).select_from(t).where(
        t.c.baseline_id == baseline_id, hash_sql([t.c[c] for c in columns_for(e, version)]) != t.c.content_hash))


def digest(db, project_id: int, on: frozenset[str], baseline_id: int | None = None,
           version: int | None = None) -> str:
    """content_digest of the live set under `on`, or of one frozen baseline's shadows, over the entities in
    the set at hash spec `version` (default CURRENT_HASH_SPEC; a baseline passes its own hash_spec_version).
    Slice10b §5.3 [Q-14]: an entity unknown at that spec is skipped, never appended as an empty line, so a
    baseline frozen before the entity joined recomputes byte-identical to its stored content_digest."""
    version = CURRENT_HASH_SPEC if version is None else version
    parts = []
    for e in at_spec(version):
        if baseline_id is None:
            q = live_select(e, project_id, on, version)
            agg = "" if q is None else db.scalar(_agg(q.order_by(None).subquery()))
        else:
            t = SHADOW_TABLES[e.table]
            agg = db.scalar(_agg(select(t.c.source_id, t.c.content_hash).where(t.c.baseline_id == baseline_id)
                                 .subquery()))
        parts.append(f"{e.table}={agg}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()
