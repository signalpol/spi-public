from __future__ import annotations
import json
from pathlib import Path

def update_latest(manifest: dict, publication_root: Path) -> Path:
    path = publication_root / "latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"date": manifest["date"], "edition": manifest["edition"], "version": manifest["version"], "status": "published"}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
