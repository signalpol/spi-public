from __future__ import annotations
import hashlib
import json
import shutil
from pathlib import Path


def archive_path_for(manifest: dict, archive_root: Path) -> Path:
    year, month, day = manifest["date"].split("-")
    return archive_root / year / month / day / manifest["edition"]


def _file_integrity(path: Path) -> dict:
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def create_archive(manifest: dict, incoming_dir: Path, archive_root: Path) -> Path:
    """Unchanged behavior for existing callers: copies incoming/ files into a
    dated archive directory and writes manifest.json there.

    Minimal addition (v0.4, Director-approved): the written manifest.json now
    also includes an "assets_integrity" list recording each archived file's
    relative path, SHA-256, and size_bytes, computed from the archived copy
    itself. This does not change archive_path_for(), the directory layout,
    or the return value, so existing callers (publish.py) are unaffected.
    """
    archive_dir = archive_path_for(manifest, archive_root)
    if archive_dir.exists():
        raise FileExistsError(f"Archive already exists: {archive_dir}")
    images_dir = archive_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=False)

    assets_integrity = []
    for rel_path in manifest["files"]:
        src = incoming_dir / rel_path
        lang = rel_path.split("/")[0]
        if rel_path.endswith(".md"):
            dest = archive_dir / f"{lang}-report.md"
        else:
            dest = images_dir / f"{lang}-{Path(rel_path).name}"
        shutil.copy2(src, dest)
        integrity = _file_integrity(dest)
        assets_integrity.append({
            "source_rel_path": rel_path,
            "archived_path": str(dest.relative_to(archive_dir)),
            "sha256": integrity["sha256"],
            "size_bytes": integrity["size_bytes"],
        })

    manifest_with_integrity = dict(manifest)
    manifest_with_integrity["assets_integrity"] = assets_integrity
    (archive_dir / "manifest.json").write_text(
        json.dumps(manifest_with_integrity, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return archive_dir
