"""Slice 16: the baseline archive writer (spec §7, §10 criteria 1–4, 16–19; §17 R6/R9/R10/R18/R19; schema §6). Grade 2
(spec §13): a missing file shows as owed, so the proof is that a written row always names a file that verifies, that
the Python recompute is the SQL hash on every shadow column, and that a tampered or swapped file fails by name."""
import json
import os
import threading


import pytest
from sqlalchemy import Text, cast, create_engine, func, literal, select, text

from config import get_settings
from models import AuditEvent, BaselineArchive, SHADOW_TABLES
from scripts.stamp_instance import stamp
from services import archive
from services.archive_store import AlreadyExists, LocalKeys, LocalStore, key_name
from services.freeze_set import CURRENT_HASH_SPEC, FREEZE_SET, at_spec, columns_for, hash_sql
from tests.conftest import OWNER_URL
from tests.test_baseline import approve, bid, freeze, scope
from tests.test_function_requirement_api import fr
from tests.test_phasing_api import depend, put_split, wave
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture
from tests.test_solution_api import link, sol

INSTANCE = "test-a"


@pytest.fixture
def arch(tmp_path, monkeypatch):
    """A stamped database and this test's own archive and key folders (S9); the wipe un-stamps."""
    stamp(OWNER_URL, INSTANCE, restamp=False)
    s = get_settings()
    monkeypatch.setattr(s, "vb_instance_id", INSTANCE)
    monkeypatch.setattr(s, "vb_archive_dir", str(tmp_path / "files"))
    monkeypatch.setattr(s, "vb_archive_key_dir", str(tmp_path / "keys"))
    return LocalStore(tmp_path / "files"), LocalKeys(tmp_path / "keys")


def rows(db, b):
    db.expire_all()
    return {r.archive_part: r for r in db.scalars(select(BaselineArchive).where(BaselineArchive.baseline_id == b))}


def rich(client, ed):
    """Scope, solutions with a link, an FR, a wave split and a dependency: rows in most shadows."""
    w = scope(client, ed)
    a, c = sol(client, ed, "A"), sol(client, ed, "C")
    link(client, ed, w["br1"]["br_id"], a["solution_id"])
    fr(client, ed, solution_id=a["solution_id"])
    put_split(client, ed, a, [(wave(client, ed, "W1"), 100)])
    depend(client, ed, a, c)
    return w


def ids(r):
    return {"instance_id": INSTANCE, "project_id": r.project_id, "baseline_id": r.baseline_id,
            "archive_part": r.archive_part, "file_seq": r.file_seq}


def test_a_freeze_writes_its_file_and_an_approval_its_signoff(client, ed, db, arch):
    """Criterion 1: after the freeze the SCOPE row is written and the file is stored under its ids-only name; the
    approval writes the SIGNOFF file the same way."""
    store, _ = arch
    rich(client, ed)
    b = bid(freeze(client, ed))
    r = rows(db, b)["SCOPE"]
    assert r.written_at is not None and r.object_name == f"{INSTANCE}/{ed['p']}/{b}.json.enc"
    assert r.key_ref == f"{key_name(INSTANCE, ed['p'])}@1" and store.exists(r.object_name)
    assert len(store.get(r.object_name)) == r.byte_size and r.last_error is None
    approve(client, ed, b)
    s = rows(db, b)["SIGNOFF"]
    assert s.object_name == f"{INSTANCE}/{ed['p']}/{b}.signoff.json.enc" and s.written_at is not None
    v = archive.verify_file(store.get(s.object_name), arch[1], ids(s))
    assert v["ok"] and v["plaintext"]["header"]["client_approver_name"] is not None
    assert db.scalar(select(func.count()).select_from(AuditEvent)
                     .where(AuditEvent.event_type == "ARCHIVE_WRITTEN")) == 2


def test_the_file_holds_every_frozen_row_and_recomputes_without_a_database(client, ed, db, arch):
    """Criterion 2 / 155: decrypted, the file lists every table of the baseline's spec (empty ones too), holds each
    frozen row once, and its row hashes and digest recompute in Python to the frozen values."""
    store, keys = arch
    rich(client, ed)
    b = bid(freeze(client, ed))
    r = rows(db, b)["SCOPE"]
    v = archive.verify_file(store.get(r.object_name), keys, ids(r))
    assert v["ok"], v["first_mismatch"]
    p = v["plaintext"]
    assert [t["table"] for t in p["tables"]] == [e.table for e in at_spec(CURRENT_HASH_SPEC)]
    for t in p["tables"]:
        st = SHADOW_TABLES[t["table"]]
        frozen = dict(db.execute(select(st.c.source_id, st.c.content_hash).where(st.c.baseline_id == b)).all())
        assert {x["source_id"]: x["content_hash"] for x in t["rows"]} == frozen, t["table"]
    assert {"bfc_node", "business_requirement", "br_solution", "function_requirement", "effort_rate", "phase",
            "solution_phase", "solution_dependency"} <= {t["table"] for t in p["tables"] if t["rows"]}
    assert p["content_digest"] == p["header"]["content_digest"] and p["algorithm"] == archive.ALGORITHM


SAMPLE = {"INTEGER": "42", "BIGINT": "9007199254740993", "SMALLINT": "7", "NUMERIC": "12.50", "BOOLEAN": "true",
          "DATE": "2026-10-21", "TEXT": "Ünïcode — 日本 \x1f end", "VARCHAR": "B\x1e:7 x"}


def _sample(type_) -> str:
    name = type_.compile().split("(")[0].upper()
    if name.endswith("[]"):
        return "{STARTED,DATA_IN}"
    return SAMPLE.get(name, SAMPLE["TEXT"])


@pytest.mark.parametrize("e", FREEZE_SET, ids=lambda e: e.table)
def test_the_python_hash_is_the_sql_hash_on_every_shadow_column(db, e):
    """Spec §7: the Python recompute mirrors freeze_set.hash_sql — every hashed column of every shadow, at its own
    type, with a value (multibyte text and the separators included) and with NULL."""
    st = SHADOW_TABLES[e.table]
    cols = columns_for(e, CURRENT_HASH_SPEC)
    for nulls in (False, True):
        exprs = [cast(literal(None if nulls else _sample(st.c[c].type)), st.c[c].type) for c in cols]
        got = db.execute(select(hash_sql(exprs), *[cast(x, Text) for x in exprs])).one()
        assert archive.row_hash(list(got[1:])) == got[0], (e.table, nulls)


def test_a_changed_byte_a_resealed_edit_or_swapped_ids_fail_and_nothing_is_overwritten(client, ed, db, arch):
    """Criteria 3 and 19: a flipped byte does not decrypt; an edit re-sealed under the right key names the table and
    source id; ids swapped in the envelope or against the record fail; the store refuses a second write."""
    store, keys = arch
    rich(client, ed)
    b = bid(freeze(client, ed))
    r = rows(db, b)["SCOPE"]
    blob = store.get(r.object_name)
    env = json.loads(blob)
    flipped = bytearray(blob)
    i = blob.index(b'"ciphertext":"') + 20
    flipped[i] = ord("A") if flipped[i] != ord("A") else ord("B")
    assert archive.verify_file(bytes(flipped), keys, ids(r))["first_mismatch"] == "ciphertext: does not decrypt"
    p = archive.verify_file(blob, keys, ids(r))["plaintext"]
    t = next(t for t in p["tables"] if t["table"] == "business_requirement")
    t["rows"][0]["columns"]["br_number"] += "9"
    resealed = archive.seal(p, ids(r), r.key_ref, keys)
    assert archive.verify_file(resealed, keys, ids(r))["first_mismatch"] == \
        f"business_requirement source_id {t['rows'][0]['source_id']}: content_hash"
    assert archive.verify_file(blob, keys, {**ids(r), "baseline_id": b + 1})["first_mismatch"] == "envelope: baseline_id"
    swapped = json.dumps({**env, "baseline_id": b + 1}).encode()
    assert archive.verify_file(swapped, keys)["first_mismatch"] == "ciphertext: does not decrypt"
    with pytest.raises(AlreadyExists):
        store.put_once(r.object_name, b"other")
    assert store.get(r.object_name) == blob and not os.access(store.root / r.object_name, os.W_OK)


def test_a_writer_failure_never_fails_the_freeze_and_the_backlog_writes_it_later(client, ed, db, arch, monkeypatch):
    """Criterion 4, R10, R19: the freeze stands; the row stays owed with a fixed message and one audit row; it waits
    6 hours, then the backlog command writes it."""
    store, keys = arch

    def boom(*a, **k):
        raise RuntimeError("client text that must not be stored")
    real_seal = archive.seal
    monkeypatch.setattr(archive, "seal", boom)
    scope(client, ed)
    b = bid(freeze(client, ed))
    r = rows(db, b)["SCOPE"]
    assert r.written_at is None and r.attempt_count == 1 and r.last_error == "RuntimeError: unexpected error"
    assert archive.write_pending(store, keys) == {"written": 0, "adopted": 0, "failed": 0}      # waits 6 h
    with create_engine(OWNER_URL).begin() as c:
        c.execute(text("UPDATE baseline_archive SET last_attempt_at = now() - interval '7 hours'"))
    assert archive.write_pending(store, keys)["failed"] == 1
    assert db.scalar(select(func.count()).select_from(AuditEvent)
                     .where(AuditEvent.event_type == "ARCHIVE_FAILED")) == 1                    # same error: once
    monkeypatch.setattr(archive, "seal", real_seal)
    with create_engine(OWNER_URL).begin() as c:
        c.execute(text("UPDATE baseline_archive SET last_attempt_at = now() - interval '7 hours'"))
    assert archive.write_pending(store, keys)["written"] == 1
    r = rows(db, b)["SCOPE"]
    assert r.written_at is not None and r.last_error is None and r.attempt_count == 3


def test_a_file_stored_but_not_recorded_is_verified_and_adopted(client, ed, db, arch, monkeypatch):
    """Criterion 17 (R9): the store kept the file, the record did not commit; the next run adopts that file."""
    store, keys = arch
    monkeypatch.setattr(get_settings(), "vb_archive_dir", None)            # the freeze leaves it owed
    scope(client, ed)
    b = bid(freeze(client, ed))

    real = archive.audit.record

    def lost(db_, event_type, **k):                    # the record of the stored file fails to commit
        if event_type == "ARCHIVE_WRITTEN":
            raise ConnectionError("the database went away")
        real(db_, event_type, **k)
    monkeypatch.setattr(archive.audit, "record", lost)
    assert archive.write_pending(store, keys)["failed"] == 1                   # sara L1: recorded, not raised
    monkeypatch.setattr(archive.audit, "record", real)
    name = f"{INSTANCE}/{ed['p']}/{b}.json.enc"
    r = rows(db, b)["SCOPE"]
    assert store.exists(name) and r.written_at is None and r.last_error == "ConnectionError: unexpected error"
    with create_engine(OWNER_URL).begin() as c:
        c.execute(text("UPDATE baseline_archive SET last_attempt_at = now() - interval '7 hours'"))
    assert archive.write_pending(store, keys) == {"written": 0, "adopted": 1, "failed": 0}
    r = rows(db, b)["SCOPE"]
    assert r.object_name == name and r.byte_size == len(store.get(name))


def test_the_writer_refuses_a_database_stamped_for_another_instance(client, ed, db, arch, monkeypatch):
    """sara H1 (R8, S9): a prod copy restored elsewhere writes nothing under prod's names, from any entry point."""
    store, keys = arch
    monkeypatch.setattr(get_settings(), "vb_archive_dir", None)
    scope(client, ed)
    bid(freeze(client, ed))
    monkeypatch.setattr(get_settings(), "vb_instance_id", "uat-1")
    with pytest.raises(archive.instance.NotStamped, match="stamped 'test-a'"):
        archive.write_pending(store, keys)
    assert not store.root.exists() and not keys.root.exists()


def test_two_writers_create_one_key(arch):
    """Criterion 18 (R16): racing first writes end up under one recorded version; a key is never replaced."""
    _, keys = arch
    refs, go = [], threading.Barrier(8)

    def first():
        go.wait()
        refs.append(keys.current_ref(INSTANCE, 99, create=True))
    threads = [threading.Thread(target=first) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert set(refs) == {f"{key_name(INSTANCE, 99)}@1"} and len(list(keys.root.iterdir())) == 1


@pytest.mark.parametrize("under", ["current", "prior"])
def test_a_tombstoned_project_gets_no_key_and_no_file(client, ed, db, arch, under, monkeypatch):
    """Criterion 16 (R4, S6): a tombstone under this id or a prior one stops the writer before any key is made."""
    store, keys = arch
    if under == "prior":
        stamp(OWNER_URL, "test-b", restamp=True)
        monkeypatch.setattr(get_settings(), "vb_instance_id", "test-b")
    store.put_once(f"{INSTANCE}/purged/{ed['p']}", b'{"project_purge_id": 1}')
    scope(client, ed)
    b = bid(freeze(client, ed))
    r = rows(db, b)["SCOPE"]
    assert r.written_at is None and r.last_error.startswith("Tombstoned:")
    assert not keys.root.exists() or not list(keys.root.iterdir())


def test_without_archive_folders_the_row_stays_owed(client, ed, db, monkeypatch):
    """A host with no archive folders configured (a dev machine) freezes as before; the file stays owed, visibly."""
    monkeypatch.setattr(get_settings(), "vb_archive_dir", None)
    scope(client, ed)
    b = bid(freeze(client, ed))
    r = rows(db, b)["SCOPE"]
    assert r.written_at is None and r.attempt_count == 0
    assert r.last_error is None
