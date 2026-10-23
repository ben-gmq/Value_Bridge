"""Shared migration helpers. The conventions live here once, not in every revision.

Append-only: revisions replay these on every upgrade, so changing a helper rewrites every
migration that already used it. Add a new helper instead of editing an old one."""
from alembic import op
import sqlalchemy as sa


def audit_columns() -> list[sa.Column]:
    """§5.1 — every business table is born with these (never retrofitted, §13)."""
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("app_user.app_user_id"), nullable=False),
        sa.Column("updated_by", sa.BigInteger, sa.ForeignKey("app_user.app_user_id")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by", sa.BigInteger, sa.ForeignKey("app_user.app_user_id")),
        sa.Column("row_version", sa.Integer, nullable=False, server_default="1"),
    ]


def updated_at_trigger(table: str) -> None:
    op.execute(
        f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at()"
    )


def drop_updated_at_trigger(table: str) -> None:
    op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table}")


def live_guard(name: str, value: bool) -> sa.Column:
    """§5.4.7(1): a generated guard that carries `value` while the row is live and NULL once
    retired, so a composite FK through it applies only to live rows (MATCH SIMPLE)."""
    return sa.Column(name, sa.Boolean,
                     sa.Computed(f"CASE WHEN is_active THEN {str(value).upper()} END", persisted=True))


def category_column(name: str, category: str) -> sa.Column:
    """S1-4: a generated constant naming the code_master category a code FK must belong to.
    Paired with an FK to code_master (code_id, category) — uq_code_category_target."""
    return sa.Column(name, sa.String(40), sa.Computed(f"'{category}'", persisted=True),
                     nullable=False)


def presence_columns() -> list[sa.Column]:
    """S2-6: the four audit columns without soft delete or row_version — for the documented
    hard-deleted presentation tables (diagram_layout, D-30, A-52). Not for business rows."""
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("app_user.app_user_id"), nullable=False),
        sa.Column("updated_by", sa.BigInteger, sa.ForeignKey("app_user.app_user_id")),
    ]


def live_tag(name: str, value: str, length: int = 20) -> sa.Column:
    """§5.4.8 guard: the text `value` while the row is live, NULL once retired — the string form of
    live_guard, for a guard FK onto a text key (fr_interface.fr_type_behaviour → 'INTERFACE')."""
    return sa.Column(name, sa.String(length),
                     sa.Computed(f"CASE WHEN is_active THEN '{value}' END", persisted=True))


def immutable_guards(table: str) -> None:
    """A-7, criteria 26/55: a frozen row is never updated or deleted — the reject trigger for every role,
    and no UPDATE grant for the app (it never had DELETE or TRUNCATE). No TRUNCATE trigger (S8-2).
    DR8-S1: rows may be inserted only into a baseline whose header was written in the same transaction
    (fn_shadow_insert_guard, created by 0048), so nothing is ever appended to an existing baseline."""
    op.execute(f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
               f"FOR EACH ROW EXECUTE FUNCTION fn_reject_modification()")
    op.execute(f"CREATE TRIGGER trg_{table}_insert_guard AFTER INSERT ON {table} "
               f"REFERENCING NEW TABLE AS new_rows FOR EACH STATEMENT EXECUTE FUNCTION fn_shadow_insert_guard()")
    op.execute(f"REVOKE UPDATE ON {table} FROM vb_app")


def immutable_guards_v2(table: str) -> None:
    """immutable_guards from migration 0074 on (slice16 schema §4): the same guards, but the reject trigger calls
    fn_reject_modification_purgeable(), which lets the owner-run purge of one approved, aged request delete this
    project's frozen rows and nothing else. A shadow made with the old helper makes a purge fail loudly, never skip."""
    op.execute(f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
               f"FOR EACH ROW EXECUTE FUNCTION fn_reject_modification_purgeable()")
    op.execute(f"CREATE TRIGGER trg_{table}_insert_guard AFTER INSERT ON {table} "
               f"REFERENCING NEW TABLE AS new_rows FOR EACH STATEMENT EXECUTE FUNCTION fn_shadow_insert_guard()")
    op.execute(f"REVOKE UPDATE ON {table} FROM vb_app")


def drop_immutable_guards(table: str) -> None:
    op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_insert_guard ON {table}")
    op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
