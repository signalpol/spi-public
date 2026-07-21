from __future__ import annotations
import json
import shutil
from pathlib import Path

def archive_path_for(manifest: dict, archive_root: Path) -> Path:
    year, month, day = manifest["date"].split("-")
    return archive_root / year / month / day / manifest["edition"]

def create_archive(manifest: dict, incoming_dir: Path, archive_root: Path) -> Path:
    archive_dir = archive_path_for(manifest, archive_root)
    if archive_dir.exists():
        raise FileExistsError(f"Archive already exists: {archive_dir}")
    images_dir = archive_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=False)
    for rel_path in manifest["files"]:
        src = incoming_dir / rel_path
        lang = rel_path.split("/")[0]
        if rel_path.endswith(".md"):
            dest = archive_dir / f"{lang}-report.md"
        else:
            dest = images_dir / f"{lang}-{Path(rel_path).name}"
        shutil.copy2(src, dest)
    (archive_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return archive_dir
