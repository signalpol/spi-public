"""
Patch B v0.3 -- Persistence integrity + minimal new artifacts.

Runs AFTER publish.py's non-dry-run success, in the same job/runner.
Does NOT recreate publication/kr,en, archive/{date}/, or publication/latest.json --
those already exist on disk from publish.py's copy_to_publication() /
create_archive() / update_latest(). This script:

  1. Cross-verifies that publication/**, archive/**, and publication/latest.json
     are all mutually consistent with the incoming manifest that triggered
     this run (hash + size + date/edition/version agreement).
  2. Only after all cross-checks pass, writes the two genuinely new
     artifacts: reports/archive-index.json and logs/{date}_publish.json.

If any cross-check fails, nothing new is written and the process exits
non-zero -- the existing publish.py outputs are left exactly as they were
(this script never deletes or modifies publication/**, archive/**, or
publication/latest.json).
"""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent


class PersistenceError(Exception):
    pass


def _sha256_and_size(path: Path) -> tuple[str, int]:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def _archived_path_for(archive_dir: Path, rel_path: str) -> Path:
    lang = rel_path.split("/")[0]
    if rel_path.endswith(".md"):
        return archive_dir / f"{lang}-report.md"
    return archive_dir / "images" / f"{lang}-{Path(rel_path).name}"


def archive_dir_for(manifest: dict) -> Path:
    y, m, d = manifest["date"].split("-")
    return ROOT / "archive" / y / m / d / manifest["edition"]


def verify_integrity(manifest: dict) -> None:
    """Raises PersistenceError with a specific reason on any mismatch."""
    incoming_dir = ROOT / "incoming"
    publication_dir = ROOT / "publication"
    archive_dir = archive_dir_for(manifest)

    files = manifest["files"]
    if len(files) != 8:
        raise PersistenceError(f"expected 8 files in incoming manifest, found {len(files)}")

    # 1) publication/** file set matches incoming manifest exactly, and hash/size match
    for rel_path in files:
        incoming_file = incoming_dir / rel_path
        publication_file = publication_dir / rel_path
        if not incoming_file.is_file():
            raise PersistenceError(f"incoming file missing (should not happen post-gate): {rel_path}")
        if not publication_file.is_file():
            raise PersistenceError(f"publish.py did not create expected publication file: {rel_path}")
        inc_hash, inc_size = _sha256_and_size(incoming_file)
        pub_hash, pub_size = _sha256_and_size(publication_file)
        if inc_hash != pub_hash or inc_size != pub_size:
            raise PersistenceError(
                f"publication/{rel_path} does not match incoming/{rel_path} "
                f"(incoming sha256={inc_hash} size={inc_size}, "
                f"publication sha256={pub_hash} size={pub_size})"
            )

    # 2) archive/** file set matches incoming manifest, and hash/size match
    for rel_path in files:
        incoming_file = incoming_dir / rel_path
        archived_file = _archived_path_for(archive_dir, rel_path)
        if not archived_file.is_file():
            raise PersistenceError(f"create_archive() did not create expected archived file: {archived_file}")
        inc_hash, inc_size = _sha256_and_size(incoming_file)
        arc_hash, arc_size = _sha256_and_size(archived_file)
        if inc_hash != arc_hash or inc_size != arc_size:
            raise PersistenceError(
                f"{archived_file} does not match incoming/{rel_path} "
                f"(incoming sha256={inc_hash} size={inc_size}, "
                f"archived sha256={arc_hash} size={arc_size})"
            )

    # 3) archive manifest.json's date/edition/version/files match incoming manifest
    archive_manifest_path = archive_dir / "manifest.json"
    if not archive_manifest_path.is_file():
        raise PersistenceError(f"archive manifest.json missing: {archive_manifest_path}")
    archive_manifest = json.loads(archive_manifest_path.read_text(encoding="utf-8"))
    for field in ("date", "edition", "version"):
        if archive_manifest.get(field) != manifest.get(field):
            raise PersistenceError(
                f"archive manifest.{field} ({archive_manifest.get(field)!r}) "
                f"!= incoming manifest.{field} ({manifest.get(field)!r})"
            )
    if sorted(archive_manifest.get("files", [])) != sorted(files):
        raise PersistenceError("archive manifest.files does not match incoming manifest.files")

    # 4) publication/latest.json's date/edition/version match incoming manifest
    latest_path = publication_dir / "latest.json"
    if not latest_path.is_file():
        raise PersistenceError(f"publication/latest.json missing: {latest_path}")
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    for field in ("date", "edition", "version"):
        if latest.get(field) != manifest.get(field):
            raise PersistenceError(
                f"publication/latest.json.{field} ({latest.get(field)!r}) "
                f"!= incoming manifest.{field} ({manifest.get(field)!r})"
            )


def write_new_artifacts(manifest: dict) -> None:
    date_str, edition = manifest["date"], manifest["edition"]
    archive_dir = archive_dir_for(manifest)

    index_path = ROOT / "reports" / "archive-index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index = (
        json.loads(index_path.read_text(encoding="utf-8"))
        if index_path.exists()
        else {"schema_version": "SPI-ARCHIVE-INDEX-v0.1", "entries": []}
    )
    if any(
        e["date"] == date_str and e["edition"] == edition and e.get("event", "PUBLISH") == "PUBLISH"
        for e in index["entries"]
    ):
        raise PersistenceError(
            f"reports/archive-index.json already has a PUBLISH entry for {date_str}/{edition}; "
            f"same-day republish is blocked by design (Revision support is a future version)"
        )
    index["entries"].append({
        "date": date_str,
        "edition": edition,
        "version": manifest["version"],
        "archive_path": str(archive_dir.relative_to(ROOT)),
        "recorded_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "event": "PUBLISH",
    })
    index["entries"].sort(key=lambda e: (e["date"], e.get("recorded_at", "")))
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    log_path = ROOT / "logs" / f"{date_str}_publish.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps({
        "production_date": date_str,
        "persisted_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "archive_path": str(archive_dir.relative_to(ROOT)),
        "status": "SUCCESS",
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def run(manifest_path: Path) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        verify_integrity(manifest)
        write_new_artifacts(manifest)
    except PersistenceError as e:
        print(f"FATAL: {e}")
        print("No new artifacts written. Existing publication/, archive/, publication/latest.json left untouched.")
        return 1
    print(f"Persistence recorded for {manifest['date']}/{manifest['edition']}. "
          f"Commit scope: publication/**, archive/**, logs/**, reports/archive-index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(ROOT / "incoming" / "manifest.json"))
