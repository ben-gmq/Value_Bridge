"""Carrying out an approved DELETE removal (slice16 spec §7 purge.execute, §10 criteria 6–8, 10–12; schema §4, §7, §8,
§12.5; Q-69 b, Q-72, Q-75, S7, S8). Runs only on the owner connection (MIGRATION_DATABASE_URL), from
scripts/purge_project.py — never from the app (design §6.6: no HTTP route deletes).

One transaction: lock the request and the project, check every rule again, ask the operator to type
`<client code>/<project code>`, name the project in `vb.purge_project_id` (the scoped bypass, migration 0074), classify
every table, count, delete child before parent with each count checked, prove that nothing else moved, record the key
names, mark the request executed (the 0072 guard re-checks four eyes, the 24 hours and two live admins at that moment)
and write PROJECT_PURGED. Any failure rolls all of it back and leaves the request open.

After the commit, `destroy_keys` writes the tombstone and destroys the project's keys (approved by Ben 2026-10-22);
a key it could not destroy stays `destroyed_at IS NULL` — "keys outstanding", visible and retryable (schema §7 step 6).
Not here yet: the ARCHIVE run (project file first) and the DELETE_ARCHIVE run."""
import getpass
import json
import socket
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy import text
from sqlalchemy.engine import Connection

from services.archive_store import REF, key_name

# Tables that hold rows of a project which survive its removal (schema §8).
KEEP = ("project_purge", "project_purge_key")
# Tables with no project_id and no reference towards a project; the classifier proves the claim every run.
NO_PROJECT_DATA = ("alembic_version", "app_user", "client", "platform_admin_grant", "program", "program_member",
                   "project_template_component", "vb_instance", "vb_instance_setting_log")
LIBRARY = "code_master"


def _library_refs_clear(c: Connection, fks, p: int) -> None:
    """A table that holds no project data may point at the company code library, never at this project's overrides."""
    for child, parent, ccols, pcols in fks:
        if child in NO_PROJECT_DATA and parent == LIBRARY:
            hit = c.scalar(text(f"SELECT count(*) FROM {child} WHERE ({', '.join(ccols)}) IN "
                                f"(SELECT {', '.join(pcols)} FROM {LIBRARY} WHERE project_id = :p)"), {"p": p})
            if hit:
                raise Refused(f"{child} points at {hit} of this project's code-list overrides.")


class Refused(Exception):
    """A rule stopped the run before anything was deleted; the message says which."""


@dataclass
class Plan:
    purge_id: int
    project_id: int
    client_code: str
    client_name: str
    project_code: str
    project_name: str
    reason: str
    latest_baseline: str | None
    counts: dict[str, int] = field(default_factory=dict)       # rows of this project, per table, before
    totals: dict[str, int] = field(default_factory=dict)       # all rows, per table, before

    @property
    def expected(self) -> str:
        return f"{self.client_code}/{self.project_code}"


def _one(c: Connection, sql: str, **kw):
    return c.execute(text(sql), kw).one_or_none()


def _live_admin(c: Connection, uid: int | None) -> bool:
    return uid is not None and bool(c.scalar(text(
        "SELECT is_active AND is_platform_admin FROM app_user WHERE app_user_id = :u"), {"u": uid}))


def _check_request(c: Connection, purge_id: int, executor_id: int):
    """Criterion 6 and S7, read again inside the transaction; the 0072 guard checks the same at execution."""
    pp = _one(c, "SELECT project_purge_id, purge_kind, project_id, reason, requested_by_user_id, approved_by_user_id, "
                 "approved_single_owner, "
                 "approved_at, cancelled_at, executed_at, (approved_at <= now() - interval '24 hours' OR repurge_of_purge_id IS NOT NULL) AS aged "
                 "FROM project_purge WHERE project_purge_id = :i FOR UPDATE", i=purge_id)
    if pp is None or pp.cancelled_at is not None or pp.executed_at is not None:
        raise Refused("There is no open removal request with that number.")
    if pp.purge_kind != "DELETE":
        raise Refused(f"This script carries out DELETE requests only; {pp.purge_kind} is not built yet.")
    if pp.approved_at is None:
        raise Refused("The request has no second platform admin's approval.")
    if not pp.aged:
        raise Refused("The approval is less than 24 hours old.")
    quorum = c.scalar(text("SELECT public.fn_approvers_required()"))     # 0079: 1 only on a single-owner install
    if pp.approved_single_owner and quorum == 2:                            # A-Q5
        raise Refused("This request was approved alone under the single-owner setting, which is now off: a second "
                      "platform admin must approve it again.")
    if pp.approved_by_user_id == pp.requested_by_user_id and not pp.approved_single_owner:
        raise Refused("The requester approved their own request.")
    if not (_live_admin(c, pp.requested_by_user_id) and _live_admin(c, pp.approved_by_user_id)):
        raise Refused("The requester or the approver is no longer a live platform admin.")
    if c.scalar(text("SELECT count(*) FROM app_user WHERE is_active AND is_platform_admin")) < quorum:
        raise Refused("Fewer than two live platform admins.")
    if not _live_admin(c, executor_id):
        raise Refused("The person running the removal is not a live platform admin.")
    if executor_id == pp.requested_by_user_id and quorum == 2:             # A-Q2: a sole admin may run it under 1
        raise Refused("The requester cannot also run the removal.")
    return pp


# ---- classifying every table (schema §7 step 2, §8) -----------------------------------------------------------

@dataclass
class Classified:
    predicates: dict[str, str]           # DELETE table → SQL selecting this project's rows (:p is the project id)
    steps: list[str | tuple[str, ...]]   # the delete order; a tuple is one strongly connected set, one statement
    library_refs: list                   # NO_PROJECT_DATA references to code_master, checked on the data
    own: dict[str, str]                  # the proof's rule, independent of `predicates` where a project_id exists


def _catalog(c: Connection):
    tables = [r[0] for r in c.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1"))]
    cols = {}
    for t, col in c.execute(text("SELECT table_name, column_name FROM information_schema.columns "
                                 "WHERE table_schema = 'public'")):
        cols.setdefault(t, set()).add(col)
    fks = c.execute(text(
        "SELECT conrelid::regclass::text, confrelid::regclass::text, "
        "ARRAY(SELECT a.attname FROM unnest(conkey) WITH ORDINALITY k(n, i) JOIN pg_attribute a "
        "      ON a.attrelid = conrelid AND a.attnum = k.n ORDER BY k.i), "
        "ARRAY(SELECT a.attname FROM unnest(confkey) WITH ORDINALITY k(n, i) JOIN pg_attribute a "
        "      ON a.attrelid = confrelid AND a.attnum = k.n ORDER BY k.i) "
        "FROM pg_constraint WHERE contype = 'f' AND connamespace = 'public'::regnamespace ORDER BY conname")).all()
    shadows = {r[0] for r in c.execute(text(
        "SELECT DISTINCT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
        "JOIN pg_proc f ON f.oid = t.tgfoid WHERE f.proname = 'fn_reject_modification_purgeable'"))}
    return tables, cols, fks, shadows


# The only DELETE triggers a deleted table may carry: the guards that ask fn_purge_allows (0074, 0075).
DELETE_GUARDS = ("fn_reject_modification_purgeable", "fn_baseline_header_guard", "fn_baseline_archive_guard",
                 "fn_reject_modification_audit_purgeable")


def _no_side_effects(c: Connection, deleted: set[str]) -> None:
    """sara M-A: the proof counts rows, so a delete must change nothing it does not count. Refuse a reference into a
    deleted table that cascades or sets values on delete, and any other DELETE trigger on a deleted table."""
    cascades = c.execute(text(
        "SELECT conname, conrelid::regclass::text, confrelid::regclass::text FROM pg_constraint "
        "WHERE contype = 'f' AND connamespace = 'public'::regnamespace AND confdeltype NOT IN ('a', 'r')")).all()
    bad = [f"{n} ({ch} → {pa})" for n, ch, pa in cascades if pa in deleted]
    triggers = c.execute(text(
        "SELECT t.tgname, c.relname, f.proname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
        "JOIN pg_proc f ON f.oid = t.tgfoid WHERE NOT t.tgisinternal AND (t.tgtype & 8) <> 0 "
        "AND c.relnamespace = 'public'::regnamespace")).all()
    bad += [f"trigger {n} on {t}" for n, t, fn in triggers if t in deleted and fn not in DELETE_GUARDS]
    if bad:
        raise Refused(f"A delete would change rows the proof cannot see: {bad}")


def classify(c: Connection) -> Classified:
    """Every table in exactly one of DELETE, KEEP, NO_PROJECT_DATA, or the run stops. DELETE predicates come from a
    small rule: project_id; a frozen shadow by its baseline; otherwise through a reference to a DELETE table."""
    tables, cols, fks, shadows = _catalog(c)
    unknown_lists = (set(KEEP) | set(NO_PROJECT_DATA)) - set(tables)
    if unknown_lists:
        raise Refused(f"The keep lists name tables that do not exist: {sorted(unknown_lists)}")
    preds: dict[str, str] = {}
    for t in tables:
        if t in KEEP or t in NO_PROJECT_DATA:
            continue
        if t in shadows:
            preds[t] = "baseline_id IN (SELECT baseline_id FROM baseline WHERE project_id = :p)"
        elif "project_id" in cols.get(t, ()):
            preds[t] = "project_id = :p"
    # A table without project_id is deleted through its reference to a DELETE table (import_row → import_batch).
    changed = True
    while changed:
        changed = False
        for child, parent, ccols, pcols in fks:
            if child in preds or child in KEEP or child in NO_PROJECT_DATA or child == parent or parent not in preds:
                continue
            preds[child] = (f"({', '.join(ccols)}) IN (SELECT {', '.join(pcols)} FROM {parent} "
                            f"WHERE {preds[parent]})")
            changed = True
    left = [t for t in tables if t not in preds and t not in KEEP and t not in NO_PROJECT_DATA]
    if left:
        raise Refused(f"Tables in no list — add each to the delete rule or a keep list first: {left}")
    # NO_PROJECT_DATA must hold no reference towards a project, transitively (S8: not created_by → app_user).
    # code_master mixes the company library with project overrides: a reference to it is allowed only while no row
    # points at this project's overrides (checked on the data in `_library_refs_clear`, before anything is deleted).
    linked = (set(preds) | set(KEEP)) - {LIBRARY}
    for child, parent, *_ in fks:
        if child in NO_PROJECT_DATA and parent in linked:
            raise Refused(f"{child} is listed as holding no project data but references {parent}.")
    for t in NO_PROJECT_DATA:
        if {"project_id", "baseline_id"} & cols.get(t, set()):
            raise Refused(f"{t} is listed as holding no project data but has a project or baseline column.")
    _no_side_effects(c, set(preds))
    # The proof does not trust the delete rule: a table with its own project_id is checked by that column alone.
    own = {t: "project_id = :p" if "project_id" in cols.get(t, ()) else w for t, w in preds.items()}
    return Classified(preds, _order(list(preds), fks),
                      [f for f in fks if f[0] in NO_PROJECT_DATA and f[1] == LIBRARY], own)


def _order(names: list[str], fks) -> list[str | tuple[str, ...]]:
    """Children before parents; a strongly connected set (project ⇄ code_master) comes back as one group."""
    edges = {t: set() for t in names}                    # t → the tables it references
    for child, parent, *_ in fks:
        if child in edges and parent in edges and child != parent:
            edges[child].add(parent)
    groups = _scc(names, edges)
    gid = {t: i for i, g in enumerate(groups) for t in g}
    deps = {i: {gid[p] for t in g for p in edges[t]} - {i} for i, g in enumerate(groups)}
    order, done = [], set()
    while len(done) < len(groups):
        ready = sorted((i for i in deps if i not in done
                        and not any(i in deps[j] for j in deps if j not in done and j != i)),
                       key=lambda i: groups[i][0])
        if not ready:
            raise Refused("The delete order has a cycle the grouping missed.")
        for i in ready:
            order.append(groups[i])
            done.add(i)
    return [g[0] if len(g) == 1 else tuple(g) for g in order]


def _scc(names, edges) -> list[list[str]]:
    index, low, stack, on, out = {}, {}, [], set(), []

    def visit(v):
        index[v] = low[v] = len(index)
        stack.append(v)
        on.add(v)
        for w in sorted(edges[v]):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            g = []
            while True:
                w = stack.pop()
                on.discard(w)
                g.append(w)
                if w == v:
                    break
            out.append(sorted(g))

    for n in sorted(names):
        if n not in index:
            visit(n)
    return out


# ---- the run ----------------------------------------------------------------------------------------------------

def _count(c: Connection, t: str, where: str, p: int) -> int:
    return c.scalar(text(f"SELECT count(*) FROM {t} WHERE {where}"), {"p": p})


def _delete(c: Connection, step, preds: dict[str, str], p: int) -> dict[str, int]:
    """One statement per table, or chained CTEs for a strongly connected set (FKs checked at statement end)."""
    if isinstance(step, str):
        return {step: c.execute(text(f"DELETE FROM {step} WHERE {preds[step]}"), {"p": p}).rowcount}
    ctes = ", ".join(f"d{i} AS (DELETE FROM {t} WHERE {preds[t]} RETURNING 1)" for i, t in enumerate(step))
    sel = ", ".join(f"(SELECT count(*) FROM d{i})" for i in range(len(step)))
    got = c.execute(text(f"WITH {ctes} SELECT {sel}"), {"p": p}).one()
    return dict(zip(step, got))


def _instance(c: Connection) -> str:
    """sara H2: the database's stamp must equal this host's VB_INSTANCE_ID (as the server and the writer require), so
    a restored copy still stamped as production can never destroy production's keys."""
    from config import get_settings
    configured = get_settings().vb_instance_id
    stamped = c.scalar(text("SELECT instance_id FROM vb_instance"))
    if not configured or stamped is None:
        raise Refused("VB_INSTANCE_ID is not set or the database is not stamped (scripts.stamp_instance).")
    if stamped != configured:
        raise Refused(f"VB_INSTANCE_ID is {configured!r} but this database is stamped {stamped!r}: "
                      "re-stamp it deliberately first.")
    return stamped


def _key_names(c: Connection, p: int, instance: str) -> dict[str, list[str]]:
    """Read before baseline_archive goes (S8): every key ref of the project's files, plus this instance's name. A ref
    naming another project's key stops the run (sara H1: the app role can write an owed row's key_ref)."""
    names: dict[str, set[str]] = {key_name(instance, p): set()}
    # sara L-c: a cancelled ARCHIVE's project file keeps naming its key (schema §12.5); collect that one too.
    for (ref,) in c.execute(text("SELECT key_ref FROM baseline_archive WHERE project_id = :p AND key_ref IS NOT NULL "
                                 "UNION SELECT archive_key_ref FROM project_purge WHERE project_id = :p "
                                 "AND archive_key_ref IS NOT NULL"), {"p": p}):
        m = REF.match(ref)
        if not m:
            raise Refused(f"An archive file names a key the script cannot read: {ref!r}")
        if not m.group(1).endswith(f"-proj-{p}"):
            raise Refused(f"An archive record of this project names another project's key: {ref!r} — stop and call IS.")
        names.setdefault(m.group(1), set()).add(ref)
    return {n: sorted(refs) for n, refs in sorted(names.items())}


def execute(c: Connection, purge_id: int, executor_email: str, confirm: Callable[[Plan], str]) -> Plan:
    """The whole removal in the caller's open transaction on the owner connection; the caller commits. `confirm`
    shows the plan to the operator and returns what they typed."""
    if c.scalar(text("SELECT session_user")) != "vb_owner":
        raise Refused("Run this as the owner role (MIGRATION_DATABASE_URL), never as the app.")
    c.execute(text("SET LOCAL search_path = pg_catalog, public"))                      # sara L-b: bare table names
    instance = _instance(c)
    executor = c.scalar(text("SELECT app_user_id FROM app_user WHERE lower(email) = lower(:e)"), {"e": executor_email})
    if executor is None:
        raise Refused("No user with that email.")
    pp = _check_request(c, purge_id, executor)
    p = pp.project_id
    proj = _one(c, "SELECT p.project_code, p.project_name, cl.client_code, cl.client_name FROM project p "
                   "JOIN client cl USING (client_id) WHERE p.project_id = :p FOR UPDATE OF p", p=p)
    if proj is None:
        raise Refused("The project is already gone.")
    latest = _one(c, "SELECT major_no || '.' || minor_no FROM baseline WHERE project_id = :p "
                     "ORDER BY major_no DESC, minor_no DESC LIMIT 1", p=p)
    tables = classify(c)
    preds = tables.predicates
    _library_refs_clear(c, tables.library_refs, p)
    plan = Plan(purge_id, p, proj.client_code, proj.client_name, proj.project_code, proj.project_name, pp.reason,
                latest[0] if latest else None)
    own_before = {}
    for t in preds:
        plan.counts[t] = _count(c, t, preds[t], p)
        plan.totals[t] = c.scalar(text(f"SELECT count(*) FROM {t}"))
        own_before[t] = _count(c, t, tables.own[t], p)
    if (confirm(plan) or "").strip() != plan.expected:                                 # R3: the client's code too
        raise Refused(f"The typed code did not match {plan.expected}; nothing was deleted.")
    c.execute(text("SELECT set_config('vb.purge_project_id', :p, true)"), {"p": str(p)})
    keys = _key_names(c, p, instance)
    for step in tables.steps:
        got = _delete(c, step, preds, p)
        for t, n in got.items():
            if n != plan.counts[t]:
                raise Refused(f"{t}: deleted {n} rows, counted {plan.counts[t]} — rolled back.")
    for t in preds:                                     # step 5: prove, by the independent rule where there is one
        if _count(c, t, tables.own[t], p) != 0:
            raise Refused(f"{t} still holds rows of the project — rolled back.")
        total = c.scalar(text(f"SELECT count(*) FROM {t}"))
        if total != plan.totals[t] - own_before[t]:
            raise Refused(f"{t} lost rows of another project — rolled back.")
    for name, refs in keys.items():
        c.execute(text("INSERT INTO project_purge_key (project_purge_id, key_name, key_refs) VALUES (:i, :n, :r)"),
                  {"i": purge_id, "n": name, "r": refs})
    c.execute(text("UPDATE project_purge SET executed_at = now(), executed_by_user_id = :u, updated_by = :u, "
                   "row_version = row_version + 1 WHERE project_purge_id = :i"), {"u": executor, "i": purge_id})
    detail = {"project_purge_id": purge_id, "purged_project_id": p, "purge_kind": "DELETE",
              "project_code": proj.project_code, "client_code": proj.client_code, "reason": pp.reason,
              "requested_by_user_id": pp.requested_by_user_id, "approved_by_user_id": pp.approved_by_user_id,
              "counts": {t: n for t, n in plan.counts.items() if n}, "os_user": getpass.getuser(),
              "host": socket.gethostname(), "keys_to_destroy": sorted(keys)}
    c.execute(text("INSERT INTO audit_event (event_type, app_user_id, target_table, target_id, detail) "
                   "VALUES ('PROJECT_PURGED', :u, 'project_purge', :i, CAST(:d AS jsonb))"),
              {"u": executor, "i": purge_id, "d": json.dumps(detail, sort_keys=True)})
    return plan


# ---- after the commit: the tombstone, then the keys (schema §6, §7 step 6; spec §10 criterion 9; Q-71, S2) --------

@dataclass
class KeyResult:
    key_name: str
    destroyed: bool
    was_present: bool | None = None
    proof_object_name: str | None = None
    note: str = ""


def _envelope_key(store, obj: str) -> str | None:
    """The key name an envelope names, or None for anything that is not one (sara M1: never raise on a stray object)."""
    try:
        env = json.loads(store.get(obj))
        m = REF.match(env.get("key_ref", "")) if isinstance(env, dict) else None
    except (ValueError, OSError, TypeError):
        return None
    return m.group(1) if m else None


def _proof_before(store, keys, files: list[str], name: str) -> tuple[str | None, bool]:
    """sara M1: choose the proof file before destroying. Returns (file, read-before): a file of this key that
    decrypts now — or, on a retry where the key is already gone, one that already fails with the key unavailable."""
    from services.archive import verify_file
    gone = None
    for obj in files:
        if _envelope_key(store, obj) != name:
            continue
        why = verify_file(store.get(obj), keys)["first_mismatch"]
        if why != "key: unavailable" and not (why or "").startswith(("envelope", "ciphertext")):
            return obj, True
        if why == "key: unavailable" and gone is None:
            gone = obj
    return gone, False


def destroy_keys(eng, purge_id: int, executor_email: str, store, keys) -> list[KeyResult]:
    """For an executed DELETE: write the tombstone (so no writer ever makes a key or a file for this project again),
    then destroy this project's own key on this instance, prove a stored file that decrypted before no longer does,
    and record it — one transaction per key, so a failure leaves it outstanding and this can simply be run again.
    The database guard (0073) lets a key be marked destroyed only by its executed DELETE."""
    from services.archive import verify_file
    with eng.connect() as lock:                                          # sara L2: one run at a time per request
        if lock.scalar(text("SELECT session_user")) != "vb_owner":
            raise Refused("Run this as the owner role (MIGRATION_DATABASE_URL), never as the app.")
        if not lock.scalar(text("SELECT pg_try_advisory_lock(hashtext('vb_purge_keys'), CAST(:i AS integer))"), {"i": purge_id}):
            raise Refused("Another run is destroying this request's keys right now.")
        try:
            with eng.begin() as c:
                instance = _instance(c)                                  # sara H2: this host's id, checked
                pp = _one(c, "SELECT project_purge_id, purge_kind, project_id, executed_at, repurge_of_purge_id "
                             "FROM project_purge WHERE project_purge_id = :i", i=purge_id)
                if pp is None or pp.purge_kind != "DELETE" or pp.executed_at is None:
                    raise Refused("Keys are destroyed only for a DELETE removal that has been carried out.")
                executor = c.scalar(text("SELECT app_user_id FROM app_user WHERE lower(email) = lower(:e) "
                                         "AND is_active AND is_platform_admin"), {"e": executor_email})
                if executor is None:
                    raise Refused("The person running the removal is not a live platform admin.")
                rows = c.execute(text("SELECT key_name FROM project_purge_key WHERE project_purge_id = :i "
                                      "AND destroyed_at IS NULL ORDER BY key_name"), {"i": purge_id}).scalars().all()
            own = key_name(instance, pp.project_id)                      # sara H1: exactly this project's key
            tomb = f"{instance}/purged/{pp.project_id}"
            if store.exists(tomb):
                named = json.loads(store.get(tomb)).get("project_purge_id")
                if named not in (purge_id, pp.repurge_of_purge_id):        # sara L4: a re-purge's old tombstone
                    raise Refused(f"A tombstone for this project names another removal: {tomb}")
            else:
                store.put_once(tomb, json.dumps({"project_purge_id": purge_id, "purge_kind": "DELETE",
                                                 "executed_at": pp.executed_at.isoformat()}, sort_keys=True).encode())
            files = store.names(f"{instance}/{pp.project_id}/")
            out = []
            for name in rows:
                if name != own:                                          # S2 and H1: never another key
                    out.append(KeyResult(name, False, note="not destroyed: not this project's key on this instance "
                                                           "— for the operator"))
                    continue
                proof, read_before = _proof_before(store, keys, files, name)
                was_present = keys.destroy(name)
                if proof is not None and verify_file(store.get(proof), keys)["first_mismatch"] != "key: unavailable":
                    raise Refused(f"{proof} still decrypts after its key was destroyed — stop and call IS.")
                with eng.begin() as c:
                    n = c.execute(text("UPDATE project_purge_key SET destroyed_at = now(), was_present = :w, "
                                       "destroyed_by_purge_id = :i, proof_object_name = :o, "
                                       "row_version = row_version + 1 WHERE project_purge_id = :i AND key_name = :n "
                                       "AND destroyed_at IS NULL"),
                                  {"w": was_present, "i": purge_id, "o": proof, "n": name}).rowcount
                    if n != 1:
                        raise Refused(f"The record of key {name} changed under this run.")
                out.append(KeyResult(name, True, was_present, proof,
                                     "" if read_before or proof is None else "proof file was already unreadable"))
            _keys_destroyed_event(eng, purge_id, pp.project_id, executor)
            return out
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(hashtext('vb_purge_keys'), CAST(:i AS integer))"), {"i": purge_id})


def _keys_destroyed_event(eng, purge_id: int, project_id: int, executor: int) -> None:
    """sara L1: once no key of the request is outstanding, one PURGE_KEYS_DESTROYED event, written from the records."""
    with eng.begin() as c:
        left = c.scalar(text("SELECT count(*) FROM project_purge_key WHERE project_purge_id = :i "
                             "AND destroyed_at IS NULL"), {"i": purge_id})
        done = c.scalar(text("SELECT count(*) FROM audit_event WHERE event_type = 'PURGE_KEYS_DESTROYED' "
                             "AND target_table = 'project_purge' AND target_id = :i"), {"i": purge_id})
        if left or done:
            return
        keys_ = [dict(r._mapping) for r in c.execute(text(
            "SELECT key_name, was_present, proof_object_name, destroyed_at::text FROM project_purge_key "
            "WHERE project_purge_id = :i ORDER BY key_name"), {"i": purge_id})]
        c.execute(text("INSERT INTO audit_event (event_type, app_user_id, target_table, target_id, detail) "
                       "VALUES ('PURGE_KEYS_DESTROYED', :u, 'project_purge', :i, CAST(:d AS jsonb))"),
                  {"u": executor, "i": purge_id, "d": json.dumps(
                      {"project_purge_id": purge_id, "purged_project_id": project_id, "keys": keys_},
                      sort_keys=True)})


def remove(eng, purge_id: int, executor_email: str, confirm: Callable[[Plan], str], store, keys,
           on_removed: Callable[[Plan], None] | None = None):
    """The whole operator run: the removal in one transaction, then — only once it has committed — the keys. Nothing
    is destroyed when the removal is refused or fails. `on_removed` hears of the commit before the key phase starts
    (the script prints it, so an operator never mistakes a key failure for "nothing happened" — sara L3, N1)."""
    if store is None or keys is None:
        raise Refused("VB_ARCHIVE_DIR and VB_ARCHIVE_KEY_DIR must be set: the run ends by destroying the project's keys.")
    with eng.begin() as c:
        plan = execute(c, purge_id, executor_email, confirm)
    if on_removed:
        on_removed(plan)
    return plan, destroy_keys(eng, purge_id, executor_email, store, keys)


