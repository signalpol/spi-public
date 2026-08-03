import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from gate import check_gate


class PublisherGateTest(unittest.TestCase):
    def package(self, root: Path):
        files = ["kr/report.md", "en/report.md", "kr/dashboard-signals.png", "en/dashboard-signals.png"]
        rows = []
        for rel in files:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("fixture:" + rel).encode())
            rows.append({"path": rel, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size})
        content_hash = "a" * 64
        manifest = {"version": "1.0", "mode": "fast", "date": "2026-08-04", "edition": "morning", "approved": True, "content_sha256": content_hash, "template_version": "spi-signals-1600x900-v1", "files": files, "file_integrity": rows}
        qa = {"status": "PASS", "content_sha256": content_hash, "template_version": "spi-signals-1600x900-v1", "checks": {"content": True, "layout": True}}
        (root / "qa_report.json").write_text(json.dumps(qa), encoding="utf-8")
        return manifest

    def test_valid_fast_package_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = check_gate(self.package(root), root)
            self.assertTrue(result.passed, result.reason)

    def test_tampered_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.package(root)
            (root / "kr/report.md").write_text("tampered")
            self.assertFalse(check_gate(manifest, root).passed)

    def test_failed_qa_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.package(root)
            qa = json.loads((root / "qa_report.json").read_text())
            qa["status"] = "FAIL"
            (root / "qa_report.json").write_text(json.dumps(qa))
            self.assertFalse(check_gate(manifest, root).passed)

    def test_path_traversal_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.package(root)
            manifest["files"].append("../secret")
            self.assertFalse(check_gate(manifest, root).passed)

    def test_full_mode_still_requires_all_dashboards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.package(root)
            manifest["mode"] = "full"
            self.assertFalse(check_gate(manifest, root).passed)


if __name__ == "__main__":
    unittest.main()
