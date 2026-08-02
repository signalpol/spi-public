import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from publisher.archive import create_archive, archive_path_for


def test_archive_manifest_includes_assets_integrity(tmp_path):
    incoming = tmp_path / "incoming"
    archive_root = tmp_path / "archive"
    (incoming / "kr").mkdir(parents=True)
    (incoming / "en").mkdir(parents=True)

    files = {
        "kr/report.md": b"kr report content",
        "en/report.md": b"en report content",
        "kr/dashboard-election.png": b"kr png bytes",
    }
    for rel, content in files.items():
        (incoming / rel).write_bytes(content)

    manifest = {
        "version": "1.0", "date": "2026-08-02", "edition": "morning",
        "approved": True, "language": ["kr", "en"], "files": list(files.keys()),
    }

    archive_dir = create_archive(manifest, incoming, archive_root)
    assert archive_dir == archive_path_for(manifest, archive_root)

    import json
    written = json.loads((archive_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "assets_integrity" in written
    assert len(written["assets_integrity"]) == 3

    by_source = {a["source_rel_path"]: a for a in written["assets_integrity"]}
    for rel, content in files.items():
        entry = by_source[rel]
        assert entry["sha256"] == hashlib.sha256(content).hexdigest()
        assert entry["size_bytes"] == len(content)
        # the archived file itself must actually exist at archived_path and match
        archived_file = archive_dir / entry["archived_path"]
        assert archived_file.read_bytes() == content


def test_archive_existing_behavior_unchanged_for_callers(tmp_path):
    """publish.py calls create_archive() and only uses the returned path +
    expects manifest.json to exist -- this must keep working unmodified."""
    incoming = tmp_path / "incoming"
    archive_root = tmp_path / "archive"
    (incoming / "kr").mkdir(parents=True)
    (incoming / "kr" / "report.md").write_bytes(b"x")

    manifest = {"version": "1.0", "date": "2026-08-02", "edition": "morning",
                "approved": True, "language": ["kr"], "files": ["kr/report.md"]}

    archive_dir = create_archive(manifest, incoming, archive_root)
    assert (archive_dir / "manifest.json").exists()
    assert (archive_dir / "kr-report.md").exists()


def test_archive_raises_if_already_exists(tmp_path):
    incoming = tmp_path / "incoming"
    archive_root = tmp_path / "archive"
    (incoming / "kr").mkdir(parents=True)
    (incoming / "kr" / "report.md").write_bytes(b"x")
    manifest = {"version": "1.0", "date": "2026-08-02", "edition": "morning",
                "approved": True, "language": ["kr"], "files": ["kr/report.md"]}

    create_archive(manifest, incoming, archive_root)
    import pytest
    with pytest.raises(FileExistsError):
        create_archive(manifest, incoming, archive_root)
