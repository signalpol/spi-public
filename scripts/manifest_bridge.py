"""
Manifest Bridge v0.3.

Reads director_approval.json from 'main' ONLY.
Reads publication_manifest.json + all 15 assets from approved_source_commit ONLY.
Writes only to .bridge_staging/ -- never touches incoming/ directly.

Pure validation functions (validate_*) take already-fetched dicts/bytes and
contain no network calls, so they are unit-testable in isolation. Only
main() performs actual GitHub API I/O.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

SPIN_REPO = "signalpol/spi-spin"
ALLOWED_EXT = {".png", ".docx", ".md", ".json"}
API_TIMEOUT = 20  # seconds

MANIFEST_SCHEMA = "SPI-PUBLICATION-MANIFEST-v0.3"
APPROVAL_SCHEMA = "SPI-DIRECTOR-APPROVAL-v0.2"
ALLOWED_SEARCH_GATE = {"PASS", "PASS_WITH_LIMITATIONS", "BLOCKED", "ESCALATED_TO_DIRECTOR"}
ALLOWED_ENGINE_STATUS = {"ENGINE_EXECUTED", "MANUAL_MAPPING"}

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ISO8601_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)

REQUIRED_ASSET_NAMES = [
    "KR_01_Election_Dashboard.png", "KR_02_International_Conflict_Dashboard.png",
    "KR_03_Core_Signals_Issues.png", "KR_04A_SEFM_Detailed_Report.docx",
    "KR_04B_SICAM_Detailed_Report.docx", "EN_01_Election_Dashboard.png",
    "EN_02_International_Conflict_Dashboard.png", "EN_03_Core_Signals_Issues.png",
    "EN_04A_SEFM_Detailed_Report.docx", "EN_04B_SICAM_Detailed_Report.docx",
    "KR_Morning_Intelligence_Briefing.md", "EN_Morning_Intelligence_Briefing.md",
    "primary_sources.md", "qa_result.md", "revision_record.md",
]
REQUIRED_BRIDGE_KEYS = {
    "kr/report.md", "kr/dashboard-election.png", "kr/dashboard-conflict.png",
    "kr/dashboard-signals.png", "en/report.md", "en/dashboard-election.png",
    "en/dashboard-conflict.png", "en/dashboard-signals.png",
}


class BridgeBlocked(Exception):
    pass


def fail(msg: str) -> None:
    raise BridgeBlocked(msg)


def safe_path(p: str, date_str: str) -> None:
    if p.startswith("/") or ".." in p.split("/"):
        fail(f"unsafe path: {p}")
    if not p.startswith(f"production/{date_str}/"):
        fail(f"path outside production/{date_str}/: {p}")
    if Path(p).suffix not in ALLOWED_EXT:
        fail(f"disallowed extension: {p}")


# ---------------------------------------------------------------------------
# Pure validation functions (no network I/O -- unit-testable)
# ---------------------------------------------------------------------------

def validate_approval(approval: dict, director_login: str) -> None:
    if approval.get("schema_version") != APPROVAL_SCHEMA:
        fail(f"approval schema_version mismatch: {approval.get('schema_version')!r}")
    if approval.get("status") != "APPROVED":
        fail(f"director_approval.status = {approval.get('status')!r}")

    ref = approval.get("approved_source_commit", "")
    if not COMMIT_SHA_RE.match(ref or ""):
        fail(f"approved_source_commit is not a 40-char lowercase hex SHA: {ref!r}")

    approved_hash = approval.get("approved_manifest_sha256", "")
    if not SHA256_RE.match(approved_hash or ""):
        fail(f"approved_manifest_sha256 is not a 64-char lowercase hex value: {approved_hash!r}")

    login = approval.get("approved_by_login")
    if login != director_login:
        fail(f"approved_by_login ({login!r}) != required DIRECTOR_GITHUB_LOGIN ({director_login!r})")

    approved_at = approval.get("approved_at", "")
    if not ISO8601_RE.match(approved_at or ""):
        fail(f"approved_at is not a valid ISO-8601 timestamp: {approved_at!r}")

    pr_number = approval.get("approval_pr_number")
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number <= 0:
        fail(f"approval_pr_number must be a positive integer: {pr_number!r}")

    merge_sha = approval.get("approval_merge_commit_sha", "")
    if not COMMIT_SHA_RE.match(merge_sha or ""):
        fail(f"approval_merge_commit_sha is not a 40-char lowercase hex SHA: {merge_sha!r}")


def validate_manifest_header(manifest: dict, date_str: str) -> None:
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        fail(f"manifest schema_version mismatch: {manifest.get('schema_version')!r}")
    if manifest.get("production_date") != date_str:
        fail(f"manifest.production_date ({manifest.get('production_date')}) != requested ({date_str})")
    gate = manifest.get("search_gate_status")
    if gate not in ALLOWED_SEARCH_GATE:
        fail(f"search_gate_status not allowed: {gate!r}")
    if gate != "PASS":
        fail(f"search_gate_status is {gate!r}, not PASS -- bridge refuses to proceed")
    for engine in ("sefm", "sicam"):
        v = manifest.get("engine_status", {}).get(engine)
        if v not in ALLOWED_ENGINE_STATUS:
            fail(f"engine_status.{engine} not allowed: {v!r}")


def validate_asset_set(manifest: dict, date_str: str) -> list[dict]:
    assets = manifest.get("assets", [])
    actual_paths = [a["path"] for a in assets]
    if len(actual_paths) != len(set(actual_paths)):
        fail("duplicate asset paths in manifest")
    expected_paths = {f"production/{date_str}/{name}" for name in REQUIRED_ASSET_NAMES}
    if set(actual_paths) != expected_paths:
        fail(f"asset set mismatch. missing={expected_paths - set(actual_paths)} "
             f"extra={set(actual_paths) - expected_paths}")
    for asset in assets:
        safe_path(asset["path"], date_str)
        sha = asset.get("sha256", "")
        if not SHA256_RE.match(sha or ""):
            fail(f"asset sha256 not 64-char lowercase hex: {asset['path']}")
        size = asset.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            fail(f"size_bytes must be a positive integer: {asset['path']} = {size!r}")
    return assets


def validate_public_subset(manifest: dict, verified_paths: set[str]) -> dict:
    subset = manifest.get("public_bridge_subset", {})
    if set(subset.keys()) != REQUIRED_BRIDGE_KEYS:
        fail(f"public_bridge_subset key mismatch. missing={REQUIRED_BRIDGE_KEYS - set(subset.keys())} "
             f"extra={set(subset.keys()) - REQUIRED_BRIDGE_KEYS}")
    source_paths = list(subset.values())
    if len(source_paths) != len(set(source_paths)):
        fail("public_bridge_subset maps two or more keys to the same source asset")
    for source_path in source_paths:
        if source_path not in verified_paths:
            fail(f"public_bridge_subset references unverified asset: {source_path}")
    return subset


# ---------------------------------------------------------------------------
# Network I/O (not unit-tested directly; exercised via integration/manual runs)
# ---------------------------------------------------------------------------

def gh_request(url: str, token: str, params: dict | None = None) -> dict:
    import requests
    try:
        r = requests.get(url, params=params, timeout=API_TIMEOUT,
                          headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    except requests.exceptions.Timeout:
        fail(f"GitHub API timeout: {url}")
    except requests.exceptions.RequestException as e:
        fail(f"GitHub API request failed: {url} ({e})")
    if r.status_code != 200:
        fail(f"GitHub API error {r.status_code} for {url}: {r.text[:300]}")
    return r.json()


def gh_get_at_ref(path: str, ref: str, token: str) -> bytes:
    meta = gh_request(f"https://api.github.com/repos/{SPIN_REPO}/contents/{path}", token, params={"ref": ref})
    blob = gh_request(meta["git_url"], token)
    if blob.get("encoding") != "base64":
        fail(f"unexpected blob encoding for {path}: {blob.get('encoding')!r} (expected base64)")
    try:
        return base64.b64decode(blob["content"])
    except Exception as e:
        fail(f"base64 decode failed for {path}: {e}")


def reset_staging() -> Path:
    staging = Path(".bridge_staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    return staging


def main() -> int:
    token = os.environ["SPI_SPIN_READONLY_TOKEN"]
    date_str = os.environ["PRODUCTION_DATE"]
    director_login = os.environ["DIRECTOR_GITHUB_LOGIN"]
    staging = reset_staging()

    try:
        approval = json.loads(gh_get_at_ref(f"production/{date_str}/director_approval.json", "main", token))
        validate_approval(approval, director_login)
        ref = approval["approved_source_commit"]

        manifest_bytes = gh_get_at_ref(f"production/{date_str}/publication_manifest.json", ref, token)
        actual_manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
        if actual_manifest_hash != approval["approved_manifest_sha256"]:
            fail("manifest hash at approved_source_commit does not match approved_manifest_sha256")

        manifest = json.loads(manifest_bytes)
        validate_manifest_header(manifest, date_str)
        validate_asset_set(manifest, date_str)

        verified_bytes = {}
        for asset in manifest["assets"]:
            data = gh_get_at_ref(asset["path"], ref, token)
            if hashlib.sha256(data).hexdigest() != asset["sha256"]:
                fail(f"hash mismatch: {asset['path']}")
            if len(data) != asset["size_bytes"]:
                fail(f"size mismatch: {asset['path']}")
            verified_bytes[asset["path"]] = data

        print(f"Full 15-asset verification PASSED for {date_str} @ {ref}")

        subset = validate_public_subset(manifest, set(verified_bytes.keys()))

        for incoming_rel, source_path in subset.items():
            out = staging / incoming_rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(verified_bytes[source_path])

        incoming_manifest = {
            "version": "1.0", "date": date_str, "edition": "morning",
            "approved": True, "language": ["kr", "en"], "files": sorted(subset.keys()),
        }
        (staging / "manifest.json").write_text(
            json.dumps(incoming_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"Staged {len(subset)} public files + manifest.json in .bridge_staging/")
        return 0

    except BridgeBlocked as e:
        print(f"BLOCKED: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
