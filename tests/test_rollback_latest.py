import hashlib
import importlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

FILES = [
    "kr/report.md", "kr/dashboard-election.png", "kr/dashboard-conflict.png", "kr/dashboard-signals.png",
    "en/report.md", "en/dashboard-election.png", "en/dashboard-conflict.png", "en/dashboard-signals.png",
]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_target_archive(root: Path, date_str, content_tag, edition="morning", version="1.0"):
    """Builds an archive/{date}/ with a manifest.json that includes a valid
    assets_integrity block (as produced by the v0.4-patched archive.py),
    plus a *current* live publication/kr,en mirror with DIFFERENT content
    so a rollback has something real to change."""
    y, m, d = date_str.split("-")
    archive_dir = root / "archive" / y / m / d / edition
    images_dir = archive_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    assets_integrity = []
    for rel in FILES:
        content = f"{content_tag}-{rel}".encode()
        lang = rel.split("/")[0]
        if rel.endswith(".md"):
            dest = archive_dir / f"{lang}-report.md"
        else:
            dest = images_dir / f"{lang}-{Path(rel).name}"
        dest.write_bytes(content)
        assets_integrity.append({
            "source_rel_path": rel,
            "archived_path": str(dest.relative_to(archive_dir)),
            "sha256": _sha256(content),
            "size_bytes": len(content),
        })

    manifest = {
        "version": version, "date": date_str, "edition": edition,
        "approved": True, "language": ["kr", "en"], "files": FILES,
        "assets_integrity": assets_integrity,
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    (archive_dir / "manifest.json").write_bytes(manifest_bytes)
    return manifest, _sha256(manifest_bytes)


def build_live_current_mirror(root: Path, content_tag="CURRENT"):
    for rel in FILES:
        p = root / "publication" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(f"{content_tag}-{rel}".encode())
    (root / "publication" / "latest.json").write_text(
        json.dumps({"date": "2026-08-02", "edition": "morning", "version": "1.0", "status": "published"}),
        encoding="utf-8",
    )


def build_approval(root: Path, target_date, target_hash, current_date="2026-08-02"):
    approval = {
        "schema_version": "SPI-ROLLBACK-APPROVAL-v0.2",
        "status": "APPROVED",
        "current_date": current_date,
        "target_date": target_date,
        "requested_reason": "test rollback",
        "approved_by_login": "director-login",
        "approved_at": "2026-08-02T11:00:00+09:00",
        "target_archive_manifest_sha256": target_hash,
        "approval_pr_number": 5,
        "approval_merge_commit_sha": "c090e42dc6093cce322489d39d33f1e49cd75bf8",
    }
    path = root / "production_rollback" / current_date / "rollback_approval.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(approval), encoding="utf-8")
    return path


@pytest.fixture()
def module(tmp_path, monkeypatch):
    import rollback_latest as rb
    importlib.reload(rb)
    monkeypatch.setattr(rb, "ROOT", tmp_path)
    return rb


def test_successful_rollback_restores_target_content(tmp_path, module):
    _, target_hash = build_target_archive(tmp_path, "2026-07-31", "OLD")
    build_live_current_mirror(tmp_path, "CURRENT")
    approval_path = build_approval(tmp_path, "2026-07-31", target_hash)

    rc = module.run(approval_path)
    assert rc == 0

    for rel in FILES:
        content = (tmp_path / "publication" / rel).read_bytes()
        assert content == f"OLD-{rel}".encode()

    latest = json.loads((tmp_path / "publication" / "latest.json").read_text())
    assert latest["date"] == "2026-07-31"

    index = json.loads((tmp_path / "reports" / "archive-index.json").read_text())
    rollback_entries = [e for e in index["entries"] if e["event"] == "ROLLBACK"]
    assert len(rollback_entries) == 1
    assert rollback_entries[0]["rolled_back_from"] == "2026-08-02"
    assert rollback_entries[0]["approved_by_login"] == "director-login"


def test_rollback_not_approved_blocks_and_leaves_current_untouched(tmp_path, module):
    _, target_hash = build_target_archive(tmp_path, "2026-07-31", "OLD")
    build_live_current_mirror(tmp_path, "CURRENT")
    approval_path = build_approval(tmp_path, "2026-07-31", target_hash)
    approval = json.loads(approval_path.read_text())
    approval["status"] = "PENDING"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    rc = module.run(approval_path)
    assert rc == 1
    for rel in FILES:
        content = (tmp_path / "publication" / rel).read_bytes()
        assert content == f"CURRENT-{rel}".encode()


def test_rollback_hash_mismatch_blocks(tmp_path, module):
    _, target_hash = build_target_archive(tmp_path, "2026-07-31", "OLD")
    build_live_current_mirror(tmp_path, "CURRENT")
    approval_path = build_approval(tmp_path, "2026-07-31", "0" * 64)  # wrong hash

    rc = module.run(approval_path)
    assert rc == 1
    for rel in FILES:
        content = (tmp_path / "publication" / rel).read_bytes()
        assert content == f"CURRENT-{rel}".encode()


def test_rollback_missing_target_archive_blocks(tmp_path, module):
    build_live_current_mirror(tmp_path, "CURRENT")
    approval_path = build_approval(tmp_path, "2026-01-01", "a" * 64)

    rc = module.run(approval_path)
    assert rc == 1


def test_rollback_tampered_archived_file_blocks_before_touching_live(tmp_path, module):
    _, target_hash = build_target_archive(tmp_path, "2026-07-31", "OLD")
    # tamper an archived file AFTER manifest was hashed, so its recorded
    # assets_integrity no longer matches the file on disk
    (tmp_path / "archive" / "2026" / "07" / "31" / "morning" / "kr-report.md").write_bytes(b"TAMPERED")
    build_live_current_mirror(tmp_path, "CURRENT")
    approval_path = build_approval(tmp_path, "2026-07-31", target_hash)

    rc = module.run(approval_path)
    assert rc == 1
    for rel in FILES:
        content = (tmp_path / "publication" / rel).read_bytes()
        assert content == f"CURRENT-{rel}".encode()


def test_rollback_archive_missing_assets_integrity_blocks(tmp_path, module):
    # Simulate a pre-v0.4 archive with no assets_integrity field
    y, m, d = "2026", "07", "20"
    archive_dir = tmp_path / "archive" / y / m / d / "morning"
    archive_dir.mkdir(parents=True)
    manifest = {"version": "1.0", "date": "2026-07-20", "edition": "morning",
                "approved": True, "language": ["kr", "en"], "files": FILES}
    manifest_bytes = json.dumps(manifest).encode()
    (archive_dir / "manifest.json").write_bytes(manifest_bytes)
    target_hash = _sha256(manifest_bytes)

    build_live_current_mirror(tmp_path, "CURRENT")
    approval_path = build_approval(tmp_path, "2026-07-20", target_hash)

    rc = module.run(approval_path)
    assert rc == 1
    for rel in FILES:
        content = (tmp_path / "publication" / rel).read_bytes()
        assert content == f"CURRENT-{rel}".encode()
