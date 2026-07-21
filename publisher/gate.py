from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_LANGUAGES = ["kr", "en"]
REQUIRED_DASHBOARDS = ["dashboard-election", "dashboard-conflict", "dashboard-signals"]

@dataclass
class GateResult:
    passed: bool
    reason: str = ""
    checked: list[str] = field(default_factory=list)

    def fail(self, reason: str) -> "GateResult":
        self.passed = False
        self.reason = reason
        return self

def check_gate(manifest: dict, incoming_dir: Path) -> GateResult:
    result = GateResult(True)
    if manifest.get("approved") is not True:
        return result.fail("approved != true")
    result.checked.append("approved=true")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        return result.fail("files list missing or empty")
    if len(files) != len(set(files)):
        return result.fail("duplicate files")
    result.checked.append("no duplicate files")
    missing = [f for f in files if not (incoming_dir / f).is_file()]
    if missing:
        return result.fail(f"Missing File: {', '.join(missing)}")
    result.checked.append(f"all {len(files)} files exist")
    languages = manifest.get("language", [])
    for lang in REQUIRED_LANGUAGES:
        if lang not in languages or not any(f.startswith(f"{lang}/") for f in files):
            return result.fail(f"required language missing: {lang}")
    result.checked.append("kr+en present")
    for lang in REQUIRED_LANGUAGES:
        for dashboard in REQUIRED_DASHBOARDS:
            if not any(f.startswith(f"{lang}/") and dashboard in f for f in files):
                return result.fail(f"required dashboard missing: {lang}/{dashboard}")
    result.checked.append("all required dashboards present")
    return result
