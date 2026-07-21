"""SPI Auto Publisher v1.0 (Candidate)."""
from __future__ import annotations
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate import check_gate
from archive import create_archive, archive_path_for
from latest import update_latest
from logger import write_log

ROOT = Path(__file__).resolve().parent.parent
INCOMING_DIR = ROOT / "incoming"
PUBLICATION_DIR = ROOT / "publication"
ARCHIVE_DIR = ROOT / "archive"
LOGS_DIR = ROOT / "logs"

class PublishError(Exception):
    pass

def load_manifest(manifest_path: Path) -> dict:
    if not manifest_path.exists():
        raise PublishError(f"Manifest not found: {manifest_path}")
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PublishError(f"Manifest Parse Error: {e}") from e

def copy_to_publication(manifest: dict) -> None:
    for rel_path in manifest["files"]:
        src = INCOMING_DIR / rel_path
        dest = PUBLICATION_DIR / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

def run(manifest_path: Path, dry_run: bool) -> int:
    edition = "unknown"
    try:
        manifest = load_manifest(manifest_path)
        edition = manifest.get("edition", "unknown")
        gate = check_gate(manifest, INCOMING_DIR)
        if not gate.passed:
            write_log(LOGS_DIR, edition=edition, status="FAILED", archive=False, dry_run=dry_run, reason=gate.reason)
            print(f"[GATE FAIL] {gate.reason}")
            return 1
        print(f"[GATE PASS] {', '.join(gate.checked)}")
        if dry_run:
            write_log(LOGS_DIR, edition=edition, status="SUCCESS", archive=False, dry_run=True)
            print("[DRY RUN] Gate passed. No publication/archive/latest changes.")
            return 0
        archive_path = archive_path_for(manifest, ARCHIVE_DIR)
        if archive_path.exists():
            reason = f"Archive already exists: {archive_path}"
            write_log(LOGS_DIR, edition=edition, status="FAILED", archive=False, dry_run=False, reason=reason)
            print(f"[ERROR] {reason}")
            return 1
        copy_to_publication(manifest)
        create_archive(manifest, INCOMING_DIR, ARCHIVE_DIR)
        update_latest(manifest, PUBLICATION_DIR)
        write_log(LOGS_DIR, edition=edition, status="SUCCESS", archive=True, dry_run=False)
        print("[COMPLETE] Publish completed")
        return 0
    except Exception as e:
        write_log(LOGS_DIR, edition=edition, status="FAILED", archive=False, dry_run=dry_run, reason=str(e))
        print(f"[ERROR] {e}")
        return 1

def main() -> None:
    parser = argparse.ArgumentParser(description="SPI Auto Publisher v1.0")
    parser.add_argument("--manifest", type=Path, default=INCOMING_DIR / "manifest.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run(args.manifest, args.dry_run))

if __name__ == "__main__":
    main()
