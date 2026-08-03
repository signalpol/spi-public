from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath

REQUIRED_LANGUAGES = ["kr", "en"]
FULL_DASHBOARDS = ["dashboard-election", "dashboard-conflict", "dashboard-signals"]
FAST_DASHBOARDS = ["dashboard-signals"]
SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass
class GateResult:
    passed: bool
    reason: str = ""
    checked: list[str] = field(default_factory=list)

    def fail(self, reason: str) -> "GateResult":
        self.passed = False
        self.reason = reason
        return self


def safe_path(root: Path, rel: str) -> Path | None:
    candidate = PurePosixPath(rel)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_qa(incoming_dir: Path) -> dict:
    path = incoming_dir / "qa_report.json"
    if not path.is_file():
        raise ValueError("qa_report.json missing")
    try:
        qa = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("qa_report.json invalid") from exc
    if not isinstance(qa, dict):
        raise ValueError("qa_report.json root must be an object")
    return qa


def check_gate(manifest: dict, incoming_dir: Path) -> GateResult:
    result = GateResult(True)
    if manifest.get("approved") is not True:
        return result.fail("approved != true")
    result.checked.append("approved=true")

    mode = manifest.get("mode", "full")
    if mode not in {"fast", "full"}:
        return result.fail("mode must be fast or full")
    result.checked.append(f"mode={mode}")

    try:
        date.fromisoformat(str(manifest.get("date")))
    except ValueError:
        return result.fail("date must be YYYY-MM-DD")
    if manifest.get("edition") not in {"morning", "afternoon", "special"}:
        return result.fail("invalid edition")

    content_hash = manifest.get("content_sha256", "")
    if not SHA256.fullmatch(content_hash):
        return result.fail("invalid content_sha256")

    files = manifest.get("files")
    if not isinstance(files, list) or not files or not all(isinstance(x, str) for x in files):
        return result.fail("files list missing or invalid")
    if len(files) != len(set(files)):
        return result.fail("duplicate files")

    paths: dict[str, Path] = {}
    for rel in files:
        path = safe_path(incoming_dir, rel)
        if path is None:
            return result.fail(f"unsafe path: {rel}")
        if not path.is_file():
            return result.fail(f"Missing File: {rel}")
        paths[rel] = path
    result.checked.extend(["safe paths", f"all {len(files)} files exist"])

    integrity = manifest.get("file_integrity")
    if not isinstance(integrity, list) or len(integrity) != len(files):
        return result.fail("file_integrity incomplete")
    rows = {row.get("path"): row for row in integrity if isinstance(row, dict)}
    if set(rows) != set(files):
        return result.fail("file_integrity paths differ from files")
    for rel, path in paths.items():
        row = rows[rel]
        if row.get("bytes") != path.stat().st_size or row.get("sha256") != digest(path):
            return result.fail(f"integrity mismatch: {rel}")
    result.checked.append("file hashes and byte sizes match")

    for lang in REQUIRED_LANGUAGES:
        if f"{lang}/report.md" not in files:
            return result.fail(f"required report missing: {lang}")
    required_dashboards = FAST_DASHBOARDS if mode == "fast" else FULL_DASHBOARDS
    for lang in REQUIRED_LANGUAGES:
        for dashboard in required_dashboards:
            if not any(PurePosixPath(f).parent == PurePosixPath(lang) and PurePosixPath(f).stem == dashboard for f in files):
                return result.fail(f"required dashboard missing: {lang}/{dashboard}")
    result.checked.append("mode-specific KR+EN package complete")

    try:
        qa = load_qa(incoming_dir)
    except ValueError as exc:
        return result.fail(str(exc))
    if qa.get("status") != "PASS":
        return result.fail("QA status is not PASS")
    if qa.get("content_sha256") != content_hash:
        return result.fail("QA/content hash mismatch")
    checks = qa.get("checks")
    if not isinstance(checks, dict) or not checks or not all(value is True for value in checks.values()):
        return result.fail("QA checks incomplete or failed")
    if qa.get("template_version") != manifest.get("template_version"):
        return result.fail("QA/template version mismatch")
    result.checked.append("QA PASS bound to content and template")
    return result
