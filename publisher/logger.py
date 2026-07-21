from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

LOG_FILENAME = "publication.log.jsonl"

def write_log(logs_dir: Path, *, edition: str, status: str, archive: bool, dry_run: bool, reason: str | None = None) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / LOG_FILENAME
    record = {"time": datetime.now(timezone.utc).astimezone().isoformat(timespec="minutes"), "edition": edition, "status": status, "archive": archive, "dry_run": dry_run}
    if reason:
        record["reason"] = reason
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path
