"""Receipt photos on disk: <receipts dir>/<group id>/<random name>.jpg|webp.

Files are written before the database row is committed and removed only after the row is gone
for good (after the commit). Whatever is left over by a crash in between, a file without a
row, is removed by ``sweep`` once it is older than an hour.
"""

import logging
import os
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.config import get_receipts_dir

logger = logging.getLogger(__name__)

# Files without a row are only removed after this long: an upload may be between writing its
# file and committing its row
ORPHAN_AGE_SECONDS = 60 * 60
_PENDING = "receipt_files_to_remove"
# Only what fahrma writes is ever removed by the cleanup, even if RECEIPTS_DIR points somewhere else by mistake
_OWN_FILE = re.compile(r"^([0-9a-f]{32}\.(jpg|webp)|\.upload-[A-Za-z0-9_]+)$")


def group_dir(group_id: int) -> Path:
    return get_receipts_dir() / str(int(group_id))


def path_of(group_id: int, file: str) -> Path:
    if "/" in file or "\\" in file or file.startswith("."):
        raise ValueError(f"Invalid receipt file name {file!r}")
    return group_dir(group_id) / file


def save(group_id: int, data: bytes, extension: str) -> str:
    """Write the photo durably and return its new file name."""
    directory = group_dir(group_id)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = f"{uuid.uuid4().hex}.{extension}"
    handle, temporary = tempfile.mkstemp(dir=directory, prefix=".upload-")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, directory / name)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return name


def remove(group_id: int, file: str) -> None:
    try:
        path_of(group_id, file).unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove receipt file %s of group %d", file, group_id)


def remove_group(group_id: int) -> None:
    shutil.rmtree(group_dir(group_id), ignore_errors=True)


def remove_after_commit(db: Session, files: list[tuple[int, str]] = (), group_id: int | None = None) -> None:
    """Remove these files (or a whole group's directory) once the session commits; nothing on rollback."""
    pending = db.info.setdefault(_PENDING, [])
    pending.extend(("file", gid, name) for gid, name in files)
    if group_id is not None:
        pending.append(("group", group_id, None))


@event.listens_for(Session, "after_commit")
def _remove_pending(session: Session) -> None:
    pending = session.info.pop(_PENDING, None)
    for kind, group_id, name in pending or ():
        if kind == "group":
            remove_group(group_id)
        else:
            remove(group_id, name)


@event.listens_for(Session, "after_soft_rollback")
def _forget_pending(session: Session, _previous_transaction) -> None:
    session.info.pop(_PENDING, None)


def sweep(db: Session, now: float | None = None) -> int:
    """Remove files (and group directories) the database does not know, if older than an hour."""
    from app.models.group import Group
    from app.models.receipt import Receipt

    root = get_receipts_dir()
    if not root.is_dir():
        return 0
    cutoff = (now if now is not None else time.time()) - ORPHAN_AGE_SECONDS
    known = set(db.scalars(select(Receipt.file)))
    groups = {str(group_id) for group_id in db.scalars(select(Group.id))}
    removed = 0
    for directory in root.iterdir():
        if not directory.is_dir() or not directory.name.isdigit():
            continue
        for path in directory.iterdir():
            if path.name in known or not _OWN_FILE.match(path.name):
                continue
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                logger.warning("Could not remove leftover receipt file %s", path)
        if directory.name not in groups:
            try:
                directory.rmdir()  # only if empty: a new group may be uploading right now
            except OSError:
                pass
    return removed


def run_sweep(session_factory) -> None:
    db = session_factory()
    try:
        removed = sweep(db)
    finally:
        db.close()
    if removed:
        logger.info("Removed %d leftover receipt files", removed)
