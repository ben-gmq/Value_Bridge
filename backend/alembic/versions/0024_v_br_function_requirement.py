"""v_br_function_requirement — BR → FR, derived through BR_SOLUTION, never stored (D-7, §7.5).

Slice 6a, docs/slice6a_schema.md §2: the design's SQL plus bs.project_id; security_invoker so it
reads with the caller's rights; INSERT/UPDATE revoked (0001's default privileges grant them).
An FR with no solution never appears (D-28). No SQLAlchemy model.

Revision ID: 0024
Revises: 0023
"""
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE VIEW v_br_function_requirement WITH (security_invoker = true) AS
        SELECT bs.project_id,
               bs.br_id,
               fr.fr_id,
               fr.fr_number,
               fr.fr_type_code_id,
               fr.fr_type_behaviour,
               s.solution_id,
               s.category_code_id AS solution_category_code_id
        FROM   br_solution bs
        JOIN   solution s              ON s.solution_id = bs.solution_id
        JOIN   function_requirement fr ON fr.solution_id = s.solution_id
        WHERE  bs.is_active AND s.is_active AND fr.is_active
    """)
    op.execute("REVOKE INSERT, UPDATE ON v_br_function_requirement FROM vb_app")


def downgrade() -> None:
    op.execute("DROP VIEW v_br_function_requirement")
