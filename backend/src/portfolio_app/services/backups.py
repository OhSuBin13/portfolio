import re
import sqlite3
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path

STARTUP_BACKUP_MIN_INTERVAL_SECONDS = 300

BACKUP_NAME_RE = re.compile(
    r"^portfolio-"
    r"(?P<date>\d{8})-"
    r"(?P<time>\d{6})-"
    r"(?P<microsecond>\d{6})-"
    r"(?P<reason>[A-Za-z0-9_-]+?)"
    r"(?:-\d+)?"
    r"\.sqlite$"
)


def _safe_reason(reason: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", reason.strip()).strip("-")
    return normalized or "backup"


def _backup_target(*, backup_dir: Path, reason: str) -> Path:
    safe_reason = _safe_reason(reason)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = backup_dir / f"portfolio-{timestamp}-{safe_reason}.sqlite"
    suffix = 1
    while target.exists():
        target = backup_dir / f"portfolio-{timestamp}-{safe_reason}-{suffix}.sqlite"
        suffix += 1

    return target


def _backup_name_match(path: Path) -> re.Match[str] | None:
    return BACKUP_NAME_RE.match(path.name)


def _metadata_from_filename(path: Path) -> tuple[str, str] | None:
    match = _backup_name_match(path)
    if match is None:
        return None

    try:
        timestamp = datetime.strptime(
            f"{match['date']}{match['time']}{match['microsecond']}",
            "%Y%m%d%H%M%S%f",
        )
    except ValueError:
        return None

    return match["reason"], timestamp.isoformat(timespec="seconds")


def _is_service_owned_backup(path: Path) -> bool:
    return _metadata_from_filename(path) is not None


def _backup_files(backup_dir: Path) -> list[Path]:
    return [
        path for path in backup_dir.iterdir() if path.is_file() and _is_service_owned_backup(path)
    ]


def create_backup(*, db_path: Path, backup_dir: Path, reason: str) -> Path:
    if not db_path.exists():
        raise FileNotFoundError("데이터베이스 파일을 찾을 수 없습니다.")

    backup_dir.mkdir(parents=True, exist_ok=True)
    target = _backup_target(backup_dir=backup_dir, reason=reason)
    temp_target = target.with_name(f".{target.name}.tmp")
    source: sqlite3.Connection | None = None
    destination: sqlite3.Connection | None = None

    try:
        source = sqlite3.connect(db_path)
        destination = sqlite3.connect(temp_target)
        source.backup(destination)
        destination.close()
        destination = None
        source.close()
        source = None
        temp_target.replace(target)
    except Exception:
        if destination is not None:
            destination.close()
        if source is not None:
            source.close()
        with suppress(OSError):
            temp_target.unlink()
        raise

    return target


def prune_backups(*, backup_dir: Path, keep: int = 30) -> list[Path]:
    if not backup_dir.exists():
        return []

    backups = sorted(
        _backup_files(backup_dir),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    keep_count = max(0, keep)
    deleted_paths: list[Path] = []
    for path in backups[keep_count:]:
        path.unlink()
        deleted_paths.append(path)

    return deleted_paths


def record_backup(
    db: sqlite3.Connection,
    *,
    backup_path: Path,
    reason: str,
    created_at: str | None = None,
) -> sqlite3.Row:
    created = created_at or datetime.now().isoformat(timespec="seconds")
    cursor = db.execute(
        """
        insert into backups(path, reason, created_at)
        values (?, ?, ?)
        """,
        (str(backup_path), reason, created),
    )
    row = db.execute(
        """
        select path, reason, created_at
        from backups
        where id = ?
        """,
        (cursor.lastrowid,),
    ).fetchone()
    if row is None:
        raise sqlite3.DatabaseError("생성된 백업 정보를 찾을 수 없습니다.")
    db.commit()
    return row


def delete_backup_records(db: sqlite3.Connection, paths: list[Path]) -> None:
    if not paths:
        return

    db.executemany("delete from backups where path = ?", [(str(path),) for path in paths])
    db.commit()


def reconcile_backup_records(db: sqlite3.Connection, *, backup_dir: Path) -> None:
    rows = db.execute("select id, path from backups").fetchall()
    stale_ids = [(row["id"],) for row in rows if not Path(row["path"]).exists()]
    if stale_ids:
        db.executemany("delete from backups where id = ?", stale_ids)

    recorded_paths = {row["path"] for row in db.execute("select path from backups").fetchall()}
    if backup_dir.exists():
        for path in _backup_files(backup_dir):
            if str(path) in recorded_paths:
                continue
            metadata = _metadata_from_filename(path)
            if metadata is None:
                continue
            reason, created_at = metadata
            db.execute(
                """
                insert into backups(path, reason, created_at)
                values (?, ?, ?)
                """,
                (str(path), reason, created_at),
            )
            recorded_paths.add(str(path))

    db.commit()


def list_backup_records(db: sqlite3.Connection, *, backup_dir: Path) -> list[sqlite3.Row]:
    return db.execute(
        """
        select path, reason, created_at
        from backups
        order by created_at desc, id desc
        """
    ).fetchall()


def create_recorded_backup(
    db: sqlite3.Connection,
    *,
    db_path: Path,
    backup_dir: Path,
    reason: str,
    keep: int = 30,
) -> sqlite3.Row:
    backup_path = create_backup(db_path=db_path, backup_dir=backup_dir, reason=reason)
    try:
        row = record_backup(db, backup_path=backup_path, reason=reason)
    except sqlite3.Error:
        with suppress(OSError):
            backup_path.unlink()
        raise

    deleted_paths = prune_backups(backup_dir=backup_dir, keep=keep)
    delete_backup_records(db, deleted_paths)
    reconcile_backup_records(db, backup_dir=backup_dir)
    return row


def create_startup_backup_if_needed(
    db: sqlite3.Connection,
    *,
    db_path: Path,
    backup_dir: Path,
    min_interval_seconds: int = STARTUP_BACKUP_MIN_INTERVAL_SECONDS,
) -> sqlite3.Row | None:
    reconcile_backup_records(db, backup_dir=backup_dir)
    row = db.execute(
        """
        select path, created_at
        from backups
        where reason = 'startup'
        order by created_at desc, id desc
        limit 1
        """
    ).fetchone()
    if row is not None and Path(row["path"]).exists():
        try:
            created_at = datetime.fromisoformat(str(row["created_at"]))
        except ValueError:
            created_at = None
        if created_at is not None and datetime.now() - created_at <= timedelta(
            seconds=max(0, min_interval_seconds)
        ):
            return None

    return create_recorded_backup(
        db,
        db_path=db_path,
        backup_dir=backup_dir,
        reason="startup",
    )
