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


def build_fake_repo(root: Path, date_str="2026-08-02", edition="morning", version="1.0", tamper=None):
    """Builds a fake spi-public tree simulating a successful publish.py run,
    so persist_publication's cross-checks can be exercised without any
    network or real publish.py execution. `tamper` optionally mutates one
    output to force a specific mismatch."""
    incoming = root / "incoming"
    publication = root / "publication"
    y, m, d = date_str.split("-")
    archive_dir = root / "archive" / y / m / d / edition
    images_dir = archive_dir / "images"

    for rel in FILES:
        content = f"content-of-{rel}".encode()
        (incoming / rel).parent.mkdir(parents=True, exist_ok=True)
        (incoming / rel).write_bytes(content)
        (publication / rel).parent.mkdir(parents=True, exist_ok=True)
        (publication / rel).write_bytes(content)
        lang = rel.split("/")[0]
        if rel.endswith(".md"):
            (archive_dir / f"{lang}-report.md").parent.mkdir(parents=True, exist_ok=True)
            (archive_dir / f"{lang}-report.md").write_bytes(content)
        else:
            images_dir.mkdir(parents=True, exist_ok=True)
            (images_dir / f"{lang}-{Path(rel).name}").write_bytes(content)

    manifest = {
        "version": version, "date": date_str, "edition": edition,
        "approved": True, "language": ["kr", "en"], "files": FILES,
    }
    (incoming / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    publication.mkdir(parents=True, exist_ok=True)
    (publication / "latest.json").write_text(
        json.dumps({"date": date_str, "edition": edition, "version": version, "status": "published"}),
        encoding="utf-8",
    )

    if tamper:
        tamper(root, archive_dir, publication)

    return manifest


@pytest.fixture()
def module(tmp_path, monkeypatch):
    """Import persist_publication fresh with ROOT patched to tmp_path."""
    import persist_publication as pp
    importlib.reload(pp)
    monkeypatch.setattr(pp, "ROOT", tmp_path)
    return pp


def test_happy_path_writes_new_artifacts_only(tmp_path, module):
    manifest = build_fake_repo(tmp_path)
    rc = module.run(tmp_path / "incoming" / "manifest.json")
    assert rc == 0
    assert (tmp_path / "reports" / "archive-index.json").exists()
    assert (tmp_path / "logs" / "2026-08-02_publish.json").exists()
    index = json.loads((tmp_path / "reports" / "archive-index.json").read_text())
    assert index["entries"][0]["date"] == "2026-08-02"
    assert index["entries"][0]["event"] == "PUBLISH"


def test_publication_hash_mismatch_blocks_and_writes_nothing(tmp_path, module):
    def tamper(root, archive_dir, publication):
        (publication / "kr" / "report.md").write_bytes(b"TAMPERED")
    build_fake_repo(tmp_path, tamper=tamper)
    rc = module.run(tmp_path / "incoming" / "manifest.json")
    assert rc == 1
    assert not (tmp_path / "reports" / "archive-index.json").exists()
    assert not (tmp_path / "logs").exists()


def test_archive_hash_mismatch_blocks(tmp_path, module):
    def tamper(root, archive_dir, publication):
        (archive_dir / "kr-report.md").write_bytes(b"TAMPERED")
    build_fake_repo(tmp_path, tamper=tamper)
    rc = module.run(tmp_path / "incoming" / "manifest.json")
    assert rc == 1


def test_archive_manifest_version_mismatch_blocks(tmp_path, module):
    def tamper(root, archive_dir, publication):
        m = json.loads((archive_dir / "manifest.json").read_text())
        m["version"] = "9.9"
        (archive_dir / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    build_fake_repo(tmp_path, tamper=tamper)
    rc = module.run(tmp_path / "incoming" / "manifest.json")
    assert rc == 1


def test_latest_json_version_mismatch_blocks(tmp_path, module):
    def tamper(root, archive_dir, publication):
        latest = json.loads((publication / "latest.json").read_text())
        latest["version"] = "9.9"
        (publication / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
    build_fake_repo(tmp_path, tamper=tamper)
    rc = module.run(tmp_path / "incoming" / "manifest.json")
    assert rc == 1


def test_missing_archive_file_blocks(tmp_path, module):
    def tamper(root, archive_dir, publication):
        (archive_dir / "images" / "kr-dashboard-election.png").unlink()
    build_fake_repo(tmp_path, tamper=tamper)
    rc = module.run(tmp_path / "incoming" / "manifest.json")
    assert rc == 1


def test_duplicate_date_publish_blocked(tmp_path, module):
    build_fake_repo(tmp_path)
    rc1 = module.run(tmp_path / "incoming" / "manifest.json")
    assert rc1 == 0
    # Simulate a second run for the same date (e.g. accidental re-trigger)
    rc2 = module.run(tmp_path / "incoming" / "manifest.json")
    assert rc2 == 1
