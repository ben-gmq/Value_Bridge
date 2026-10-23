"""Where archive files and project keys live (slice16 spec §7, schema §6; §15a storage consequence; §17 R14, R16).

Two small interfaces, so the writer runs unchanged on a local folder now and on Blob Storage + Key Vault with D-35:
- ArchiveStore.put_once / get / exists / names — write-once by rights: create and read, never overwrite. Only the
  DELETE_ARCHIVE job deletes, and it is not here.
- ProjectKeys.wrap / unwrap / destroy — one key per project per instance, named `vb-<instance>-proj-<project_id>` (ids only),
  created if absent and never replaced; every ref is versioned (`<name>@<version>`), so two writers racing on a
  first freeze end up under the same recorded version (criterion 18). Key material never enters the database.

Local: files under VB_ARCHIVE_DIR created O_EXCL, fsynced with their folder, then made read-only; keys as one
file per version under VB_ARCHIVE_KEY_DIR, owner-only. Both folders sit outside the repo."""
import os
import re
from pathlib import Path

from cryptography.hazmat.primitives.keywrap import aes_key_unwrap, aes_key_wrap

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{2,39}/(purged|[0-9]+)/[0-9a-z][0-9a-z.\-]*$")     # ids only (R8)
REF = re.compile(r"^(vb-[a-z0-9][a-z0-9-]{2,39}-proj-[0-9]+)@([0-9]+)$")


class AlreadyExists(Exception):
    """put_once on a name that is already stored: the store never overwrites."""


class KeyMissing(Exception):
    """unwrap with a key ref whose key is gone (destroyed, or another instance's)."""


def key_name(instance_id: str, project_id: int) -> str:
    return f"vb-{instance_id}-proj-{project_id}"


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _create_once(path: Path, data: bytes, mode: int) -> None:
    """Write a private temporary file in full, fsync it, set the final mode, then hard-link it to the final name —
    atomic, and refused if the name exists (FileExistsError) — so a crash or a short write never leaves a partial
    file under the final name (sara M1). Then fsync the folder."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.parent / f".tmp-{os.getpid()}-{os.urandom(6).hex()}"
    try:
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
            f.write(data)                                          # buffered: a short write raises
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.link(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    _fsync_dir(path.parent)


class LocalStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, name: str) -> Path:
        if not NAME.match(name) or ".." in name:
            raise ValueError("not an archive object name")
        return self.root / name

    def put_once(self, name: str, data: bytes) -> None:
        try:
            _create_once(self._path(name), data, 0o444)
        except FileExistsError as exc:
            raise AlreadyExists(name) from exc

    def get(self, name: str) -> bytes:
        return self._path(name).read_bytes()

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def names(self, prefix: str) -> list[str]:
        """Every stored name under `<instance>/<project_id>/` (the purge's proof that a destroyed key reads nothing)."""
        folder = self.root / prefix.rstrip("/")
        if not folder.is_dir():
            return []
        return sorted(f"{prefix.rstrip('/')}/{p.name}" for p in folder.iterdir()
                      if p.is_file() and not p.name.startswith(".tmp-"))


class LocalKeys:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _versions(self, name: str) -> list[int]:
        if not self.root.exists():
            return []
        return sorted(int(p.name.rsplit("@", 1)[1]) for p in self.root.glob(f"{name}@*"))

    def current_ref(self, instance_id: str, project_id: int, create: bool) -> str | None:
        """The newest version's ref; with `create`, version 1 is made if the project has none (O_EXCL, so a racing
        writer's key wins and is read back — never replaced)."""
        name = key_name(instance_id, project_id)
        found = self._versions(name)
        if found:
            return f"{name}@{found[-1]}"
        if not create:
            return None
        try:
            _create_once(self.root / f"{name}@1", os.urandom(32), 0o400)
        except FileExistsError:
            pass
        return f"{name}@1"

    def _key(self, ref: str) -> bytes:
        if not REF.match(ref):
            raise KeyMissing("not a key ref")
        try:
            return (self.root / ref).read_bytes()
        except FileNotFoundError as exc:
            raise KeyMissing(ref) from exc

    def wrap(self, ref: str, data_key: bytes) -> bytes:
        return aes_key_wrap(self._key(ref), data_key)

    def unwrap(self, ref: str, wrapped: bytes) -> bytes:
        return aes_key_unwrap(self._key(ref), wrapped)

    def destroy(self, name: str) -> bool:
        """Remove every version of one project key (Key Vault: delete, then purge — Q-71). Only the owner-run purge
        calls this, after its commit. Returns whether any version was there."""
        if not REF.match(f"{name}@1"):
            raise ValueError("not a key name")
        found = self._versions(name)
        for v in found:
            (self.root / f"{name}@{v}").unlink()
        if found:
            _fsync_dir(self.root)
        return bool(found)


def from_settings(settings) -> tuple[LocalStore, LocalKeys] | None:
    """The configured store and keys, or None where archiving is not set up (a dev machine): the rows stay owed,
    visibly, until a configured run writes them."""
    if not settings.vb_archive_dir or not settings.vb_archive_key_dir:
        return None
    return LocalStore(settings.vb_archive_dir), LocalKeys(settings.vb_archive_key_dir)
