"""v_interface_list — the generated interface list (D-27): one row per live interface-behaviour FR.

Slice 6b-2, docs/slice6b_schema.md §6: the design's §5.3 SQL, created like 0024 (security_invoker,
writes revoked). It filters on behaviour, never on a code, so a renamed or added interface type still
lists (criterion 101); an FR with no live detail lists with is_described = false (103).

Revision ID: 0030
Revises: 0029
"""
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE VIEW v_interface_list WITH (security_invoker = true) AS
        SELECT
            fr.project_id,
            fr.fr_id,
            fr.fr_number                        AS interface_number,
            fr.fr_name                          AS interface_name,
            ft.code                             AS fr_type_code,
            ft.label                            AS fr_type_label,
            (fi.fr_id IS NOT NULL)              AS is_described,
            fi.source_application_id,
            sa.application_code                 AS source_application_code,
            sa.application_name                 AS source_application_name,
            fi.target_application_id,
            ta.application_code                 AS target_application_code,
            ta.application_name                 AS target_application_name,
            pat.code AS pattern_code,   pat.label AS pattern_label,
            met.code AS method_code,    met.label AS method_label,
            frq.code AS frequency_code, frq.label AS frequency_label,
            fi.volume_note,
            ARRAY(SELECT de.de_number
                  FROM   fr_interface_data_entity fide
                  JOIN   data_entity de ON de.data_entity_id = fide.data_entity_id
                  WHERE  fide.fr_id = fr.fr_id AND fide.is_active AND de.is_active
                  ORDER  BY de.de_number)       AS data_entity_numbers,
            fr.solution_id,
            s.solution_number,
            ARRAY(SELECT br.br_number
                  FROM   v_br_function_requirement v
                  JOIN   business_requirement br ON br.br_id = v.br_id
                  WHERE  v.fr_id = fr.fr_id AND br.is_active
                  ORDER  BY br.br_number)       AS br_numbers,
            fs.code  AS fulfilment_status_code, fs.label AS fulfilment_status_label,
            fr.complexity_code_id,
            fr.effort_days
        FROM       function_requirement fr
        JOIN       code_master ft  ON ft.code_id  = fr.fr_type_code_id
        LEFT JOIN  fr_interface fi ON fi.fr_id    = fr.fr_id AND fi.is_active
        LEFT JOIN  application sa  ON sa.application_id = fi.source_application_id
        LEFT JOIN  application ta  ON ta.application_id = fi.target_application_id
        LEFT JOIN  code_master pat ON pat.code_id = fi.pattern_code_id
        LEFT JOIN  code_master met ON met.code_id = fi.method_code_id
        LEFT JOIN  code_master frq ON frq.code_id = fi.frequency_code_id
        LEFT JOIN  solution s      ON s.solution_id = fr.solution_id AND s.is_active
        LEFT JOIN  code_master fs  ON fs.code_id  = fr.fulfilment_status_code_id
        WHERE  fr.is_active
        AND    fr.fr_type_behaviour = 'INTERFACE'
    """)
    op.execute("REVOKE INSERT, UPDATE ON v_interface_list FROM vb_app")


def downgrade() -> None:
    op.execute("DROP VIEW v_interface_list")
