import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest
from manifest_bridge import (
    BridgeBlocked,
    validate_approval,
    validate_manifest_header,
    validate_asset_set,
    validate_public_subset,
    safe_path,
    REQUIRED_ASSET_NAMES,
    REQUIRED_BRIDGE_KEYS,
)

VALID_LOGIN = "kwan-ok-kim"
VALID_SHA40 = "c090e42dc6093cce322489d39d33f1e49cd75bf8"
VALID_SHA64 = "1720cfd43e770e97df4914c1a163fdeb27914978eacebdbdb1a585361dfb9b42"


def make_valid_approval():
    return {
        "schema_version": "SPI-DIRECTOR-APPROVAL-v0.2",
        "status": "APPROVED",
        "approved_by_login": VALID_LOGIN,
        "approved_at": "2026-08-02T10:30:00+09:00",
        "approved_source_commit": VALID_SHA40,
        "approved_manifest_sha256": VALID_SHA64,
        "approval_pr_number": 12,
        "approval_merge_commit_sha": VALID_SHA40,
    }


def make_valid_manifest(date_str="2026-08-02"):
    assets = [
        {"path": f"production/{date_str}/{name}", "sha256": VALID_SHA64, "size_bytes": 100}
        for name in REQUIRED_ASSET_NAMES
    ]
    subset = {
        "kr/report.md": f"production/{date_str}/KR_Morning_Intelligence_Briefing.md",
        "kr/dashboard-election.png": f"production/{date_str}/KR_01_Election_Dashboard.png",
        "kr/dashboard-conflict.png": f"production/{date_str}/KR_02_International_Conflict_Dashboard.png",
        "kr/dashboard-signals.png": f"production/{date_str}/KR_03_Core_Signals_Issues.png",
        "en/report.md": f"production/{date_str}/EN_Morning_Intelligence_Briefing.md",
        "en/dashboard-election.png": f"production/{date_str}/EN_01_Election_Dashboard.png",
        "en/dashboard-conflict.png": f"production/{date_str}/EN_02_International_Conflict_Dashboard.png",
        "en/dashboard-signals.png": f"production/{date_str}/EN_03_Core_Signals_Issues.png",
    }
    return {
        "schema_version": "SPI-PUBLICATION-MANIFEST-v0.3",
        "production_date": date_str,
        "search_gate_status": "PASS",
        "engine_status": {"sefm": "MANUAL_MAPPING", "sicam": "MANUAL_MAPPING"},
        "assets": assets,
        "public_bridge_subset": subset,
    }


# --- validate_approval ---

def test_approval_valid_passes():
    validate_approval(make_valid_approval(), VALID_LOGIN)  # should not raise


def test_approval_wrong_schema_blocked():
    a = make_valid_approval()
    a["schema_version"] = "SPI-DIRECTOR-APPROVAL-v0.1"
    with pytest.raises(BridgeBlocked, match="schema_version"):
        validate_approval(a, VALID_LOGIN)


def test_approval_not_approved_blocked():
    a = make_valid_approval()
    a["status"] = "PENDING"
    with pytest.raises(BridgeBlocked, match="status"):
        validate_approval(a, VALID_LOGIN)


def test_approval_wrong_login_blocked():
    a = make_valid_approval()
    a["approved_by_login"] = "someone-else"
    with pytest.raises(BridgeBlocked, match="approved_by_login"):
        validate_approval(a, VALID_LOGIN)


def test_approval_bad_source_commit_blocked():
    a = make_valid_approval()
    a["approved_source_commit"] = "not-a-sha"
    with pytest.raises(BridgeBlocked, match="approved_source_commit"):
        validate_approval(a, VALID_LOGIN)


def test_approval_bad_manifest_hash_blocked():
    a = make_valid_approval()
    a["approved_manifest_sha256"] = "short"
    with pytest.raises(BridgeBlocked, match="approved_manifest_sha256"):
        validate_approval(a, VALID_LOGIN)


def test_approval_bad_iso8601_blocked():
    a = make_valid_approval()
    a["approved_at"] = "2026/08/02 10:30"
    with pytest.raises(BridgeBlocked, match="approved_at"):
        validate_approval(a, VALID_LOGIN)


@pytest.mark.parametrize("bad_pr", [0, -1, "12", 1.5, True])
def test_approval_bad_pr_number_blocked(bad_pr):
    a = make_valid_approval()
    a["approval_pr_number"] = bad_pr
    with pytest.raises(BridgeBlocked, match="approval_pr_number"):
        validate_approval(a, VALID_LOGIN)


def test_approval_bad_merge_commit_blocked():
    a = make_valid_approval()
    a["approval_merge_commit_sha"] = "xyz"
    with pytest.raises(BridgeBlocked, match="approval_merge_commit_sha"):
        validate_approval(a, VALID_LOGIN)


# --- validate_manifest_header ---

def test_manifest_header_valid_passes():
    validate_manifest_header(make_valid_manifest(), "2026-08-02")


def test_manifest_schema_version_tampered_blocked():
    m = make_valid_manifest()
    m["schema_version"] = "SPI-PUBLICATION-MANIFEST-v0.2"
    with pytest.raises(BridgeBlocked, match="schema_version"):
        validate_manifest_header(m, "2026-08-02")


def test_manifest_search_gate_fail_blocked():
    m = make_valid_manifest()
    m["search_gate_status"] = "BLOCKED"
    with pytest.raises(BridgeBlocked, match="not PASS"):
        validate_manifest_header(m, "2026-08-02")


def test_manifest_search_gate_illegal_value_blocked():
    m = make_valid_manifest()
    m["search_gate_status"] = "MAYBE"
    with pytest.raises(BridgeBlocked, match="search_gate_status not allowed"):
        validate_manifest_header(m, "2026-08-02")


def test_manifest_engine_status_illegal_value_blocked():
    m = make_valid_manifest()
    m["engine_status"]["sefm"] = "AUTO_MAGIC"
    with pytest.raises(BridgeBlocked, match="engine_status"):
        validate_manifest_header(m, "2026-08-02")


# --- validate_asset_set ---

def test_asset_set_valid_passes():
    m = make_valid_manifest()
    assets = validate_asset_set(m, "2026-08-02")
    assert len(assets) == 15


def test_asset_set_missing_one_blocked():
    m = make_valid_manifest()
    m["assets"] = m["assets"][:-1]
    with pytest.raises(BridgeBlocked, match="asset set mismatch"):
        validate_asset_set(m, "2026-08-02")


def test_asset_set_wrong_date_path_blocked():
    m = make_valid_manifest()
    m["assets"][0]["path"] = "production/2026-08-01/KR_01_Election_Dashboard.png"
    with pytest.raises(BridgeBlocked, match="asset set mismatch"):
        validate_asset_set(m, "2026-08-02")


def test_asset_size_zero_blocked():
    m = make_valid_manifest()
    m["assets"][0]["size_bytes"] = 0
    with pytest.raises(BridgeBlocked, match="size_bytes"):
        validate_asset_set(m, "2026-08-02")


def test_asset_path_traversal_blocked():
    m = make_valid_manifest()
    m["assets"][0]["path"] = "production/2026-08-02/../../../etc/passwd"
    with pytest.raises(BridgeBlocked):
        validate_asset_set(m, "2026-08-02")


# --- validate_public_subset ---

def test_subset_valid_passes():
    m = make_valid_manifest()
    verified = {a["path"] for a in m["assets"]}
    subset = validate_public_subset(m, verified)
    assert set(subset.keys()) == REQUIRED_BRIDGE_KEYS


def test_subset_extra_key_blocked():
    m = make_valid_manifest()
    m["public_bridge_subset"]["kr/extra.png"] = m["public_bridge_subset"]["kr/report.md"]
    verified = {a["path"] for a in m["assets"]}
    with pytest.raises(BridgeBlocked, match="key mismatch"):
        validate_public_subset(m, verified)


def test_subset_missing_key_blocked():
    m = make_valid_manifest()
    del m["public_bridge_subset"]["en/dashboard-signals.png"]
    verified = {a["path"] for a in m["assets"]}
    with pytest.raises(BridgeBlocked, match="key mismatch"):
        validate_public_subset(m, verified)


def test_subset_duplicate_source_blocked():
    m = make_valid_manifest()
    m["public_bridge_subset"]["en/report.md"] = m["public_bridge_subset"]["kr/report.md"]
    verified = {a["path"] for a in m["assets"]}
    with pytest.raises(BridgeBlocked, match="same source asset"):
        validate_public_subset(m, verified)


# --- safe_path ---

def test_safe_path_ok():
    safe_path("production/2026-08-02/KR_01_Election_Dashboard.png", "2026-08-02")


@pytest.mark.parametrize("bad", [
    "/etc/passwd",
    "production/2026-08-02/../secret.png",
    "production/2026-08-01/KR_01_Election_Dashboard.png",
    "production/2026-08-02/malware.exe",
])
def test_safe_path_rejected(bad):
    with pytest.raises(BridgeBlocked):
        safe_path(bad, "2026-08-02")
