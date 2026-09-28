"""Baseline shadow tables are GENERATED from the live models, never hand-written (§6.1, §13).

For a live table `x`, `baseline_x` holds one row per live row as it stood at one freeze:
  - baseline_x_id (surrogate PK), baseline_id (FK → baseline), source_id (the live PK value)
  - every live column EXCEPT the §5.1 audit columns and the live PK
  - no row_version (snapshots are never updated) and no is_active (A-7)
Slice 5 calls `shadow_table()` per frozen entity; the CI parity check (§13, §5.4.4) uses
`parity_problems()` so a column added to a live table without its shadow fails the build.
"""
from sqlalchemy import BigInteger, Column, ForeignKey, Identity, MetaData, Table

AUDIT_COLUMNS = frozenset({"created_at", "updated_at", "created_by", "updated_by", "is_active",
                           "deleted_at", "deleted_by", "row_version"})
SNAPSHOT_COLUMNS = ("baseline_id", "source_id")


def snapshot_column_names(live: Table) -> list[str]:
    pk = {c.name for c in live.primary_key.columns}
    return [c.name for c in live.columns
            if c.name not in AUDIT_COLUMNS and c.name not in pk and c.computed is None]


def shadow_table(live: Table, metadata: MetaData, *, baseline_fk: bool = True) -> Table:
    """Build baseline_<live> on `metadata`. Column types are copied; constraints are not —
    a snapshot records what WAS, including values later constraints would reject (A-7)."""
    cols = [Column(f"baseline_{live.name}_id", BigInteger, Identity(), primary_key=True),
            Column("baseline_id", BigInteger,
                   ForeignKey("baseline.baseline_id") if baseline_fk else None, nullable=False),
            Column("source_id", BigInteger, nullable=False)]
    for name in snapshot_column_names(live):
        src = live.columns[name]
        cols.append(Column(name, src.type.copy(), nullable=True))
    return Table(f"baseline_{live.name}", metadata, *cols)


def parity_problems(live: Table, shadow: Table) -> list[str]:
    """Shadow column set must equal live columns − audit − PK − generated + snapshot columns."""
    expected = set(snapshot_column_names(live)) | set(SNAPSHOT_COLUMNS) | {f"baseline_{live.name}_id"}
    actual = {c.name for c in shadow.columns}
    return ([f"{shadow.name}: missing {sorted(expected - actual)}"] if expected - actual else []) + \
           ([f"{shadow.name}: unexpected {sorted(actual - expected)}"] if actual - expected else [])
