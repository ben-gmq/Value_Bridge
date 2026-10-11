"""Baseline shadow tables are GENERATED from the live models, never hand-written (§6.1, §13).

For a live table `x`, `baseline_x` holds one row per live row as it stood at one freeze:
  - baseline_x_id (surrogate PK), baseline_id (FK → baseline), source_id (FK → the live PK, NO ACTION)
  - every live column EXCEPT the §5.1 audit columns, the live PK, GENERATED columns and SHADOW_EXCLUDED
  - for every code_master FK `<p>_code_id` (one with a GENERATED `<p>_category` sibling, S1-4): the code
    and label it pointed at, `<p>_code` / `<p>_label`. The code is hashed, the label is display only
    (R2-D3, slice8_schema §1 [Q-1])
  - content_hash: sha256 over the entity's HASH_COLUMNS (services/freeze_set.py, §4)
  - no row_version (snapshots are never updated) and no is_active (A-7)
Every column is nullable except the three snapshot keys and the hash: a snapshot records what WAS.

The shadows were created once as literal DDL (migration 0048, slice8 [Q-4]); a later migration that adds a
column to a shadowed live table adds the shadow column in the same migration. `parity_problems()` compares
names and types, and tests/test_baseline.py runs it against the database.

DR8-D1: a shadow column's TYPE is never ALTERed — ALTER … TYPE rewrites frozen rows without firing the reject
trigger. A type change on a shadowed live column pauses for Ben; if it changes the ::text form of a hashed
column it also bumps freeze_set.CURRENT_HASH_SPEC.
"""
from sqlalchemy import (CHAR, BigInteger, Column, ForeignKey, ForeignKeyConstraint, Identity, Index, MetaData,
                        String, Table, UniqueConstraint)

AUDIT_COLUMNS = frozenset({"created_at", "updated_at", "created_by", "updated_by", "is_active",
                           "deleted_at", "deleted_by", "row_version"})
SNAPSHOT_COLUMNS = ("baseline_id", "source_id", "content_hash")
# Live columns that never reach a snapshot (D-34: a suggestion is a to-do, not agreed scope).
SHADOW_EXCLUDED: dict[str, tuple[str, ...]] = {"function_requirement": ("suggested_br_id",)}
CODE_LEN, LABEL_LEN = 40, 200


def code_pairs(live: Table) -> list[str]:
    """The prefixes `p` of every `<p>_code_id` that is provably a code_master FK: its `<p>_category`
    sibling is a GENERATED column (the S1-4 category guard)."""
    out = []
    for c in live.columns:
        if c.name.endswith("_code_id"):
            p = c.name[: -len("_code_id")]
            cat = live.columns.get(f"{p}_category")
            if cat is not None and cat.computed is not None:
                out.append(p)
    return out


def snapshot_column_names(live: Table) -> list[str]:
    pk = {c.name for c in live.primary_key.columns}
    skip = set(SHADOW_EXCLUDED.get(live.name, ()))
    return [c.name for c in live.columns
            if c.name not in AUDIT_COLUMNS and c.name not in pk and c.computed is None and c.name not in skip]


def _expected(live: Table) -> list[tuple[str, object]]:
    """(name, type) of every non-key shadow column, in shadow order."""
    cols = [(n, live.columns[n].type) for n in snapshot_column_names(live)]
    for p in code_pairs(live):
        cols += [(f"{p}_code", String(CODE_LEN)), (f"{p}_label", String(LABEL_LEN))]
    names = [n for n, _ in cols]
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        raise ValueError(f"baseline_{live.name}: generated columns collide with copied ones: {sorted(dup)}")
    return cols


def shadow_table(live: Table, metadata: MetaData, *, baseline_fk: bool = True,
                 source_fk: bool = True) -> Table:
    """Build baseline_<live> on `metadata`. Column types are copied; constraints are not —
    a snapshot records what WAS, including values later constraints would reject (A-7)."""
    name = f"baseline_{live.name}"
    (pk,) = live.primary_key.columns
    cols = [Column(f"{name}_id", BigInteger, Identity(), primary_key=True),
            Column("baseline_id", BigInteger,
                   ForeignKey("baseline.baseline_id", name=f"fk_{name}_baseline") if baseline_fk else None,
                   nullable=False),
            Column("source_id", BigInteger, nullable=False)]
    cols += [Column(n, t.copy() if hasattr(t, "copy") else t, nullable=True) for n, t in _expected(live)]
    cols.append(Column("content_hash", CHAR(64), nullable=False))
    extra = [UniqueConstraint("baseline_id", "source_id", name=f"uq_{name}_source"),
             Index(f"ix_{name}_source", "source_id")]
    if source_fk:
        extra.append(ForeignKeyConstraint(["source_id"], [f"{live.name}.{pk.name}"], name=f"fk_{name}_source",
                                          ondelete="NO ACTION"))
    return Table(name, metadata, *cols, *extra)


def _type_key(t) -> str:
    """A comparable rendering of a column type: PostgreSQL's name for it, with its length/precision."""
    from sqlalchemy.dialects import postgresql
    return t.compile(dialect=postgresql.dialect()).upper().replace("CHARACTER VARYING", "VARCHAR")


def parity_problems(live: Table, shadow: Table) -> list[str]:
    """The shadow's column names and types must equal what the generator makes from `live` today."""
    expected = {n: _type_key(t) for n, t in _expected(live)}
    expected |= {"baseline_id": "BIGINT", "source_id": "BIGINT", "content_hash": "CHAR(64)",
                 f"baseline_{live.name}_id": "BIGINT"}
    actual = {c.name: _type_key(c.type) for c in shadow.columns}
    out = []
    if set(expected) - set(actual):
        out.append(f"{shadow.name}: missing {sorted(set(expected) - set(actual))}")
    if set(actual) - set(expected):
        out.append(f"{shadow.name}: unexpected {sorted(set(actual) - set(expected))}")
    out += [f"{shadow.name}.{n}: type {actual[n]} != live {expected[n]}"
            for n in sorted(set(expected) & set(actual)) if actual[n] != expected[n]]
    return out
