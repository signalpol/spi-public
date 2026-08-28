"""
Rollback script v0.3 -- NOT wired to any workflow trigger (inactive by
design; manual/local execution only until explicitly activated by a
separate Director decision).

Atomicity strategy:
  - publication/kr, publication/en are replaced via a same-filesystem
    new-dir + rename swap (not delete-then-copytree), with the previous
    mirror preserved as a backup until the swap fully succeeds.
  - publication/latest.json is replaced via write-temp-file + os.replace()
    (atomic on POSIX for same-filesystem renames).
  - On ANY failure before the final swap/replace, the live
    publication/kr, publication/en, publication/latest.json are left
    completely untouched.

Integrity: uses archive manifest.json's "assets_integrity" field
(added in archive.py v0.4 patch) to verify each archived file's
SHA-256 + size before it is used to reconstruct the live mirror.
"""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent


class RollbackError(Exception):
    pass


def _sha256_and_size(path: Path) -> tuple[str, int]:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def archive_dir_for(date_str: str, edition: str = "morning") -> Path:
    y, m, d = date_str.split("-")
    return ROOT / "archive" / y / m / d / edition


def _archived_path_for(archive_dir: Path, rel_path: str) -> Path:
    lang = rel_path.split("/")[0]
    if rel_path.endswith(".md"):
        return archive_dir / f"{lang}-report.md"
    return archive_dir / "images" / f"{lang}-{Path(rel_path).name}"


def load_and_verify_approval(approval_path: Path) -> dict:
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    if approval.get("status") != "APPROVED":
        raise RollbackError(f"rollback_approval.status = {approval.get('status')!r}, not APPROVED")
    for field in ("target_date", "target_archive_manifest_sha256"):
        if not approval.get(field):
            raise RollbackError(f"rollback_approval missing required field: {field}")
    return approval


def load_and_verify_target_manifest(target_date: str, expected_hash: str) -> dict:
    archive_dir = archive_dir_for(target_date)
    manifest_path = archive_dir / "manifest.json"
    if not manifest_path.is_file():
        raise RollbackError(f"no archive found for target_date {target_date}: {manifest_path}")
    manifest_bytes = manifest_path.read_bytes()
    actual_hash = hashlib.sha256(manifest_bytes).hexdigest()
    if actual_hash != expected_hash:
        raise RollbackError(
            f"target archive manifest hash mismatch: expected {expected_hash}, got {actual_hash}"
        )
    manifest = json.loads(manifest_bytes)
    if "assets_integrity" not in manifest:
        raise RollbackError(
            "target archive manifest.json has no 'assets_integrity' field -- "
            "cannot verify per-file hashes. Refusing to roll back to a pre-v0.4 archive."
        )
    return manifest


def stage_verified_files(manifest: dict, staging_dir: Path) -> None:
    archive_dir = archive_dir_for(manifest["date"], manifest["edition"])
    integrity_by_source = {a["source_rel_path"]: a for a in manifest["assets_integrity"]}

    for rel_path in manifest["files"]:
        integrity = integrity_by_source.get(rel_path)
        if integrity is None:
            raise RollbackError(f"assets_integrity has no entry for {rel_path}")
        src = _archived_path_for(archive_dir, rel_path)
        if not src.is_file():
            raise RollbackError(f"archived file missing: {src}")
        actual_hash, actual_size = _sha256_and_size(src)
        if actual_hash != integrity["sha256"] or actual_size != integrity["size_bytes"]:
            raise RollbackError(
                f"archived file {src} failed integrity check "
                f"(expected sha256={integrity['sha256']} size={integrity['size_bytes']}, "
                f"got sha256={actual_hash} size={actual_size})"
            )
        dest = staging_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def atomic_swap_lang_dir(lang: str, staging_dir: Path) -> None:
    """Same-filesystem new-dir + rename swap, with backup preserved until
    the swap fully succeeds. On any exception, the caller's except-block
    is responsible for restoring from *_backup if a partial swap occurred."""
    live = ROOT / "publication" / lang
    new_dir = ROOT / "publication" / f"{lang}_new_tmp"
    backup_dir = ROOT / "publication" / f"{lang}_backup_tmp"

    if new_dir.exists():
        shutil.rmtree(new_dir)
    shutil.copytree(staging_dir / lang, new_dir)

    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    if live.exists():
        os.rename(live, backup_dir)
    os.rename(new_dir, live)
    if backup_dir.exists():
        shutil.rmtree(backup_dir)


def restore_lang_dir_from_backup(lang: str) -> None:
    live = ROOT / "publication" / lang
    backup_dir = ROOT / "publication" / f"{lang}_backup_tmp"
    new_dir = ROOT / "publication" / f"{lang}_new_tmp"
    if new_dir.exists():
        shutil.rmtree(new_dir)
    if backup_dir.exists() and not live.exists():
        os.rename(backup_dir, live)


def atomic_replace_latest_json(payload: dict) -> None:
    target = ROOT / "publication" / "latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_name, target)  # atomic on POSIX, same filesystem
    except Exception:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise


def append_rollback_audit_entry(manifest: dict, approval: dict, current_date: str) -> None:
    index_path = ROOT / "reports" / "archive-index.json"
    index = (
        json.loads(index_path.read_text(encoding="utf-8"))
        if index_path.exists()
        else {"schema_version": "SPI-ARCHIVE-INDEX-v0.1", "entries": []}
    )
    index["entries"].append({
        "date": manifest["date"],
        "edition": manifest["edition"],
        "version": manifest["version"],
        "archive_path": str(archive_dir_for(manifest["date"], manifest["edition"]).relative_to(ROOT)),
        "recorded_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "event": "ROLLBACK",
        "rolled_back_from": current_date,
        "target_archive_manifest_sha256": approval["target_archive_manifest_sha256"],
        "approved_by_login": approval.get("approved_by_login"),
        "approval_pr_number": approval.get("approval_pr_number"),
    })
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def run(approval_path: Path) -> int:
    try:
        approval = load_and_verify_approval(approval_path)
        target_date = approval["target_date"]
        manifest = load_and_verify_target_manifest(target_date, approval["target_archive_manifest_sha256"])

        staging_dir = ROOT / ".rollback_staging"
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_dir.mkdir()
        stage_verified_files(manifest, staging_dir)

        swapped = []
        try:
            for lang in ("kr", "en"):
                atomic_swap_lang_dir(lang, staging_dir)
                swapped.append(lang)

            atomic_replace_latest_json({
                "date": manifest["date"], "edition": manifest["edition"],
                "version": manifest["version"], "status": "published",
            })
        except Exception:
            for lang in swapped:
                restore_lang_dir_from_backup(lang)
            raise

        append_rollback_audit_entry(manifest, approval, current_date=approval.get("current_date", "unknown"))
        shutil.rmtree(staging_dir)
        print(f"Rollback complete: publication/kr,en and latest.json now reflect {target_date}")
        return 0

    except RollbackError as e:
        print(f"BLOCKED: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(run(ROOT / "production_rollback" / "PENDING" / "rollback_approval.json"))
