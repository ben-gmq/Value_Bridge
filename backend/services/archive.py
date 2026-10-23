"""The one archive writer (slice16 spec §7, §15a AR-2, §17 R6/R9/R10/R13/R18/R19, §18 S5; schema §3.1, §6, §12.3).

Every freeze owes a SCOPE file and every client approval a SIGNOFF file (`baseline_archive`, 0068). This writes them:
it re-reads the frozen rows as PostgreSQL text, recomputes every row hash and the digest in Python, seals the result
under the project's key, verifies the exact bytes it is about to store, stores them write-once and only then records
the file — so a written row always names a file that verified. A failure leaves the row owed, visibly, with a fixed
message (never exception text, which may carry client content); the freeze is never touched.

File (one per part of one baseline): a JSON envelope, AES-256-GCM, a fresh data key per file wrapped by the project
key. Ids only outside the ciphertext, and they are the associated data, so a file whose ids were swapped fails
(R18). The plaintext describes itself (R13): hash spec, algorithm, each table's hashed columns, empty tables listed —
readable and checkable without this code base or a database (criterion 155)."""
import base64
import hashlib
import json
import logging
import os
from datetime import timedelta

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Baseline, BaselineArchive
from models.baseline import SHADOW_TABLES
from services import audit, instance
from services.archive_store import AlreadyExists, KeyMissing, key_name
from services.freeze_set import NULL_SENTINEL, SEP, at_spec, columns_for, shadow_columns

log = logging.getLogger(__name__)

FORMAT = "vb-baseline-archive/1"
ALGORITHM = ("content_hash = lowercase hex sha256 of the UTF-8 text formed from the table's hashed_columns in order: "
             "each value as '<length in characters>:<value>' (NULL as U+001E), joined by U+001F. content_digest = "
             "lowercase hex sha256 of one line per table in the listed order, '<table>=' followed by "
             "'<source_id>:<content_hash>' for each row by ascending source_id joined by ',', lines joined by U+000A.")
ENVELOPE_IDS = ("instance_id", "project_id", "baseline_id", "archive_part", "file_seq")
RETRY_AFTER = timedelta(hours=6)            # R10: a failing row waits; it never starves the queue


class ArchiveError(Exception):
    """A known failure: `last_error` is the class name and this fixed message, never data (R19)."""
    message = "the archive file could not be written"

    def __str__(self) -> str:
        return f"{type(self).__name__}: {self.message}"


class DigestMismatch(ArchiveError):
    message = "the frozen rows no longer match the baseline's digest"


class Tombstoned(ArchiveError):
    message = "this project was purged from a database this copy was restored from; no key or file is made"


class VerifyFailed(ArchiveError):
    message = "the sealed file did not verify before it was stored"


class StoredFileMismatch(ArchiveError):
    message = "a file already stored under this name does not verify against this baseline"


class KeyUnavailable(ArchiveError):
    message = "the project key could not be read"


def object_name(instance_id: str, project_id: int, baseline_id: int, part: str, seq: int) -> str:
    """Ids only (R8, schema §12.3): SCOPE `<b>.json.enc`, SIGNOFF `<b>.signoff.json.enc`, `.r<seq>` from seq 2."""
    stem = f"{baseline_id}{'.signoff' if part == 'SIGNOFF' else ''}{f'.r{seq}' if seq > 1 else ''}"
    return f"{instance_id}/{project_id}/{stem}.json.enc"


# ---- the plaintext ---------------------------------------------------------------------------------------------

def _header_text(db: Session, baseline_id: int) -> dict:
    t = Baseline.__table__
    row = db.execute(select(*[cast(c, Text).label(c.name) for c in t.columns])
                     .where(t.c.baseline_id == baseline_id)).mappings().one()
    return dict(row)


def plaintext(db: Session, b: Baseline, part: str) -> dict:
    """What one file holds: the header (every column as text) and, for SCOPE, every frozen row of every table in the
    set at the baseline's hash spec, as text. The SIGNOFF file holds the header alone: the approval set, bound to the
    scope by the content digest it carries."""
    header = _header_text(db, b.baseline_id)
    p = {"format": FORMAT, "archive_part": part, "header": header}
    if part == "SIGNOFF":
        return p
    tables = []
    for e in at_spec(b.hash_spec_version):
        t, cols = SHADOW_TABLES[e.table], shadow_columns(e.table)
        rows = db.execute(select(t.c.source_id, t.c.content_hash, *[cast(t.c[c], Text).label(c) for c in cols])
                          .where(t.c.baseline_id == b.baseline_id).order_by(t.c.source_id)).mappings()
        tables.append({"table": e.table, "hashed_columns": list(columns_for(e, b.hash_spec_version)),
                       "rows": [{"source_id": r["source_id"], "content_hash": r["content_hash"],
                                 "columns": {c: r[c] for c in cols}} for r in rows]})
    return {**p, "hash_spec_version": b.hash_spec_version, "algorithm": ALGORITHM,
            "content_digest": b.content_digest, "tables": tables}


def row_hash(values: list[str | None]) -> str:
    """freeze_set.hash_sql in Python: PostgreSQL's char_length is a count of characters, as len() is."""
    parts = [NULL_SENTINEL if v is None else f"{len(v)}:{v}" for v in values]
    return hashlib.sha256(SEP.join(parts).encode()).hexdigest()


def first_mismatch(p: dict) -> str | None:
    """Recompute every row hash and the digest from the stored text. None when all match, else what failed first:
    the table and source id of a row, or the digest."""
    header = p.get("header") or {}
    if p.get("archive_part") == "SIGNOFF":
        return None if header.get("client_approver_name") is not None else "header: no client approval"
    lines = []
    for t in p["tables"]:
        pairs = []
        for r in sorted(t["rows"], key=lambda r: r["source_id"]):
            if row_hash([r["columns"].get(c) for c in t["hashed_columns"]]) != r["content_hash"]:
                return f"{t['table']} source_id {r['source_id']}: content_hash"
            pairs.append(f"{r['source_id']}:{r['content_hash']}")
        lines.append(f"{t['table']}={','.join(pairs)}")
    digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    if digest != p.get("content_digest") or digest != header.get("content_digest"):
        return "content_digest"
    return None


# ---- the envelope ----------------------------------------------------------------------------------------------

def _b64(x: bytes) -> str:
    return base64.b64encode(x).decode()


def _aad(ids: dict, key_ref: str) -> bytes:
    return json.dumps({"format": FORMAT, **{k: ids[k] for k in ENVELOPE_IDS}, "key_ref": key_ref},
                      sort_keys=True, separators=(",", ":")).encode()


def seal(p: dict, ids: dict, key_ref: str, keys) -> bytes:
    dek, nonce = AESGCM.generate_key(bit_length=256), os.urandom(12)
    body = json.dumps(p, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    env = {"format": FORMAT, **{k: ids[k] for k in ENVELOPE_IDS}, "key_ref": key_ref,
           "wrapped_data_key": _b64(keys.wrap(key_ref, dek)), "nonce": _b64(nonce),
           "ciphertext": _b64(AESGCM(dek).encrypt(nonce, body, _aad(ids, key_ref)))}
    return json.dumps(env, sort_keys=True, separators=(",", ":")).encode()


def verify_file(blob: bytes, keys, expect: dict | None = None) -> dict:
    """Decrypt, check the ids against `expect` (the row or the file name) and the plaintext, recompute every row
    hash and the digest (criteria 2, 3, 19; spec §7). Returns {ok, first_mismatch, key_ref, plaintext}."""
    def bad(why):
        return {"ok": False, "first_mismatch": why, "key_ref": None, "plaintext": None}
    try:
        env = json.loads(blob)
    except ValueError:
        return bad("envelope: not JSON")
    if not isinstance(env, dict) or env.get("format") != FORMAT:
        return bad("envelope: format")
    for k, v in (expect or {}).items():
        if env.get(k) != v:
            return bad(f"envelope: {k}")
    try:
        dek = keys.unwrap(env["key_ref"], base64.b64decode(env["wrapped_data_key"]))
        body = AESGCM(dek).decrypt(base64.b64decode(env["nonce"]), base64.b64decode(env["ciphertext"]),
                                   _aad(env, env["key_ref"]))
        p = json.loads(body)
    except KeyMissing:
        return bad("key: unavailable")
    except (InvalidTag, KeyError, ValueError, TypeError):
        return bad("ciphertext: does not decrypt")      # a changed byte, a swapped id, or the wrong key
    h = p.get("header") or {}
    if p.get("archive_part") != env["archive_part"] or h.get("baseline_id") != str(env["baseline_id"]) \
            or h.get("project_id") != str(env["project_id"]):
        return bad("plaintext: ids")
    why = first_mismatch(p)
    return {"ok": why is None, "first_mismatch": why, "key_ref": env["key_ref"], "plaintext": p}


# ---- the writer ------------------------------------------------------------------------------------------------

def _seal_verified(tx: Session, row: BaselineArchive, store, keys) -> tuple[bytes, str, str, bool]:
    """(stored bytes, object name, key ref, adopted) for one owed row, or an ArchiveError."""
    ids_known = instance.ids(tx)
    if any(store.exists(f"{i}/purged/{row.project_id}") for i in ids_known):
        raise Tombstoned()                                                     # R4, S6: current and prior ids
    b = tx.get(Baseline, row.baseline_id)
    p = plaintext(tx, b, row.archive_part)
    if first_mismatch(p) is not None:
        raise DigestMismatch()
    ids = {"instance_id": ids_known[0], "project_id": row.project_id, "baseline_id": row.baseline_id,
           "archive_part": row.archive_part, "file_seq": row.file_seq}
    name = object_name(ids_known[0], row.project_id, row.baseline_id, row.archive_part, row.file_seq)
    try:
        ref = keys.current_ref(ids_known[0], row.project_id, create=True)
    except OSError as exc:
        raise KeyUnavailable() from exc
    blob = seal(p, ids, ref, keys)
    if not verify_file(blob, keys, ids)["ok"]:                                 # R6: the exact bytes we store
        raise VerifyFailed()
    try:
        store.put_once(name, blob)
        if store.get(name) != blob:                                            # sara M1: what is stored, verified
            raise VerifyFailed()
        return blob, name, ref, False
    except AlreadyExists:                                                      # R9: stored, never recorded
        blob = store.get(name)
        v = verify_file(blob, keys, ids)
        if not v["ok"] or (v["plaintext"]["header"]["content_digest"] != b.content_digest) \
                or not v["key_ref"].startswith(key_name(ids_known[0], row.project_id) + "@"):   # sara L2
            raise StoredFileMismatch()
        return blob, name, v["key_ref"], True


def _owed(baseline_id: int | None):
    q = (select(BaselineArchive).where(BaselineArchive.written_at.is_(None),
                                       or_(BaselineArchive.last_attempt_at.is_(None),
                                           BaselineArchive.last_attempt_at < func.now() - RETRY_AFTER))
         .order_by(BaselineArchive.last_attempt_at.asc().nulls_first(), BaselineArchive.created_at)
         .limit(1).with_for_update(skip_locked=True))
    return q if baseline_id is None else q.where(BaselineArchive.baseline_id == baseline_id)


def _fail(key: tuple, error: str) -> None:
    with SessionLocal() as tx:
        row = tx.scalar(select(BaselineArchive).where(
            BaselineArchive.baseline_id == key[0], BaselineArchive.archive_part == key[1],
            BaselineArchive.file_seq == key[2], BaselineArchive.written_at.is_(None)).with_for_update(skip_locked=True))
        if row is None:
            return
        changed = row.last_error != error
        row.attempt_count += 1
        row.last_attempt_at = func.now()
        row.last_error = error
        row.row_version += 1
        if changed:                                                            # R10: one audit row per new error
            audit.record(tx, "ARCHIVE_FAILED", project_id=row.project_id, target_table="baseline_archive",
                         target_id=row.baseline_id, detail={"archive_part": row.archive_part,
                                                            "file_seq": row.file_seq, "error": error})
        tx.commit()


def write_pending(store, keys, *, limit: int = 50, baseline_id: int | None = None) -> dict:
    """Write up to `limit` owed files, oldest untried first, one transaction each; a row another writer holds is
    skipped. Returns counts by outcome."""
    from config import get_settings
    with SessionLocal() as db:                         # sara H1: never write under another instance's names
        instance.check_startup(db, get_settings().vb_instance_id)
    done = {"written": 0, "adopted": 0, "failed": 0}
    for _ in range(limit):
        with SessionLocal() as tx:
            row = tx.scalar(_owed(baseline_id))
            if row is None:
                break
            key = (row.baseline_id, row.archive_part, row.file_seq)
            try:
                blob, name, ref, adopted = _seal_verified(tx, row, store, keys)
            except Exception as exc:                                           # noqa: BLE001 — recorded, never raised
                tx.rollback()
                error = str(exc) if isinstance(exc, ArchiveError) else f"{type(exc).__name__}: unexpected error"
                log.warning("archive file for baseline %s %s not written: %s", key[0], key[1], error)
                _fail(key, error)
                done["failed"] += 1
                continue
            try:
                row.object_name, row.key_ref = name, ref
                row.file_sha256, row.byte_size = hashlib.sha256(blob).hexdigest(), len(blob)
                row.written_at = row.last_attempt_at = func.now()
                row.attempt_count += 1
                row.last_error = None
                row.row_version += 1
                audit.record(tx, "ARCHIVE_WRITTEN", project_id=row.project_id, target_table="baseline_archive",
                             target_id=row.baseline_id, detail={"archive_part": row.archive_part,
                                                                "file_seq": row.file_seq, "object_name": name,
                                                                "byte_size": len(blob), "adopted": adopted})
                tx.commit()
            except Exception as exc:                                           # noqa: BLE001 — sara L1
                tx.rollback()                                                  # stored, not recorded: adopted later
                _fail(key, f"{type(exc).__name__}: unexpected error")
                done["failed"] += 1
                continue
            done["adopted" if adopted else "written"] += 1
    return done


def write_soon(baseline_id: int) -> None:
    """Right after a freeze or an approval commits: best effort. Where archiving is not configured the row stays
    owed for scripts.write_archives; any failure is logged and recorded on the row, never raised (criterion 4)."""
    from config import get_settings
    from services.archive_store import from_settings
    target = from_settings(get_settings())
    if target is None:
        return
    try:
        write_pending(*target, limit=2, baseline_id=baseline_id)
    except Exception:                                                          # noqa: BLE001
        log.exception("archive writer failed after baseline %s; its files stay owed", baseline_id)
