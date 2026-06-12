import re
import shutil
from datetime import datetime
from pathlib import Path


def _safe_reason(reason: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", reason.strip()).strip("-")
    return normalized or "backup"


def create_backup(*, db_path: Path, backup_dir: Path, reason: str) -> Path:
    if not db_path.exists():
        raise FileNotFoundError("데이터베이스 파일을 찾을 수 없습니다.")

    backup_dir.mkdir(parents=True, exist_ok=True)
    safe_reason = _safe_reason(reason)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = backup_dir / f"portfolio-{timestamp}-{safe_reason}.sqlite"
    suffix = 1
    while target.exists():
        target = backup_dir / f"portfolio-{timestamp}-{safe_reason}-{suffix}.sqlite"
        suffix += 1

    shutil.copy2(db_path, target)
    return target


def prune_backups(*, backup_dir: Path, keep: int = 30) -> None:
    if not backup_dir.exists():
        return

    backups = sorted(
        backup_dir.glob("*.sqlite"),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    keep_count = max(0, keep)
    for path in backups[keep_count:]:
        path.unlink()
