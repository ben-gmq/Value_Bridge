"""Migration 0068 on real data (slice16 schema §3.1 / §12.3, Q-77; sara M2): the backfill owes one SCOPE file per
existing baseline, authored by its freezer, and one SIGNOFF file per approved one, authored by its approver; the
downgrade refuses once any file is written, and a clean downgrade and re-upgrade owes exactly the same files.
Migration 0069 (vb_instance): its downgrade refuses once the database is stamped."""
import pytest
from alembic import command

from scripts.stamp_instance import stamp
from tests.conftest import OWNER_URL
from tests.test_baseline import approve, bid, freeze, scope
from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture

OWED = ("SELECT a.baseline_id, a.archive_part, a.file_seq, a.project_id, a.format_version, a.written_at, "
        "a.created_by = CASE a.archive_part WHEN 'SCOPE' THEN b.frozen_by_user_id ELSE b.approved_by_user_id END "
        "FROM baseline_archive a JOIN baseline b USING (baseline_id) ORDER BY 1, 2")
WRITE = ("UPDATE baseline_archive SET object_name = 't/x.json.enc', file_sha256 = repeat('a', 64), byte_size = 10, "
         "key_ref = 'k@1', written_at = now() WHERE baseline_id = :b AND archive_part = 'SCOPE'")


def test_the_backfill_owes_every_existing_baseline_its_files(client, ed, owner):
    scope(client, ed)
    b1 = bid(freeze(client, ed))
    approve(client, ed, b1)
    b2 = bid(freeze(client, ed))
    command.downgrade(_cfg(), "0067")
    assert q(owner, "SELECT to_regclass('baseline_archive')")[0][0] is None
    command.upgrade(_cfg(), "0068")
    p = ed["p"]
    assert q(owner, OWED) == [(b1, "SCOPE", 1, p, 1, None, True), (b1, "SIGNOFF", 1, p, 1, None, True),
                              (b2, "SCOPE", 1, p, 1, None, True)]


def test_a_written_file_refuses_the_downgrade(client, ed, owner):
    scope(client, ed)
    b = bid(freeze(client, ed))
    x(owner, WRITE, b=b)
    with pytest.raises(Exception, match="downgrade refused"):
        command.downgrade(_cfg(), "0067")
    assert q(owner, "SELECT count(*) FROM baseline_archive WHERE written_at IS NOT NULL")[0][0] == 1


def test_a_stamped_database_refuses_the_0069_downgrade(owner):
    """0069: the restore identity is never dropped with a stamp on it."""
    stamp(OWNER_URL, "test-a", restamp=False)
    with pytest.raises(Exception, match="stamped: downgrade refused"):
        command.downgrade(_cfg(), "0068")
    assert q(owner, "SELECT instance_id FROM vb_instance") == [("test-a",)]
