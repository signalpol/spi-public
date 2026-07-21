#!/usr/bin/env python3
"""SPI Auto Publisher v1.0.

Validates an approved package in incoming/, archives reports and dashboard
images by date, updates machine-readable indexes, and clears the staging
package only after successful publication.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import date as Date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming"
PACKAGE = INCOMING / "publication"
MANIFEST = INCOMING / "manifest.json"
INDEX = ROOT / "reports" / "archive-index.json"
LATEST = ROOT / "reports" / "latest.json"

LANGUAGES = {"KR", "EN"}
DASHBOARD_TYPES = {"election", "conflicts", "signals"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class PublishError(RuntimeError):
    pass


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists() and default is not None:
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PublishError(f"Missing required file: {path.relative_to(ROOT)}") from exc
    except json.JSONDecodeError as exc:
        raise PublishError(f"Invalid JSON: {path.relative_to(ROOT)}: {exc}") from exc


def parse_date(value: Any) -> Date:
    try:
        return Date.fromisoformat(str(value))
    except ValueError as exc:
        raise PublishError("manifest.date must be YYYY-MM-DD") from exc


def source_file(name: Any) -> Path:
    if not isinstance(name, str) or not name.strip():
        raise PublishError("Every publication item requires a filename")
    path = (PACKAGE / name).resolve()
    if path.parent != PACKAGE.resolve():
        raise PublishError(f"Unsafe filename: {name}")
    if not path.is_file():
        raise PublishError(f"Missing package file: incoming/publication/{name}")
    return path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def copy_verified(source: Path, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    if digest(source) != digest(destination):
        raise PublishError(f"Integrity verification failed: {destination.relative_to(ROOT)}")
    return {
        "path": destination.relative_to(ROOT).as_posix(),
        "sha256": digest(destination),
        "bytes": destination.stat().st_size,
    }


def main() -> int:
    manifest = read_json(MANIFEST)
    if not isinstance(manifest, dict):
        raise PublishError("manifest.json must contain a JSON object")
    if manifest.get("approved") is not True:
        raise PublishError("Publication blocked: manifest.approved must be true")

    publication_date = parse_date(manifest.get("date"))
    date_text = publication_date.isoformat()
    year, month = str(publication_date.year), f"{publication_date.month:02d}"

    reports = manifest.get("reports")
    dashboards = manifest.get("dashboards")
    if not isinstance(reports, list) or not reports:
        raise PublishError("At least one report is required")
    if not isinstance(dashboards, list) or not dashboards:
        raise PublishError("At least one dashboard is required")

    published: list[dict[str, Any]] = []
    seen_destinations: set[str] = set()

    for item in reports:
        if not isinstance(item, dict):
            raise PublishError("Each report entry must be an object")
        language = str(item.get("language", "")).upper()
        if language not in LANGUAGES:
            raise PublishError(f"Unsupported report language: {language}")
        source = source_file(item.get("file"))
        if source.suffix.lower() != ".md":
            raise PublishError("Reports must use the .md extension")
        destination = ROOT / "reports" / year / month / f"{date_text}-{language}.md"
        key = destination.as_posix()
        if key in seen_destinations:
            raise PublishError(f"Duplicate destination: {key}")
        seen_destinations.add(key)
        record = copy_verified(source, destination)
        record.update({"kind": "report", "language": language})
        published.append(record)

    for item in dashboards:
        if not isinstance(item, dict):
            raise PublishError("Each dashboard entry must be an object")
        dashboard_type = str(item.get("type", "")).lower()
        language = str(item.get("language", "")).upper()
        if dashboard_type not in DASHBOARD_TYPES:
            raise PublishError(f"Unsupported dashboard type: {dashboard_type}")
        if language not in LANGUAGES:
            raise PublishError(f"Unsupported dashboard language: {language}")
        source = source_file(item.get("file"))
        extension = source.suffix.lower()
        if extension not in IMAGE_EXTENSIONS:
            raise PublishError(f"Unsupported image extension: {extension}")
        destination = ROOT / "dashboards" / dashboard_type / year / month / f"{date_text}-{language}{extension}"
        key = destination.as_posix()
        if key in seen_destinations:
            raise PublishError(f"Duplicate destination: {key}")
        seen_destinations.add(key)
        record = copy_verified(source, destination)
        record.update({"kind": "dashboard", "type": dashboard_type, "language": language})
        published.append(record)

    edition = str(manifest.get("edition", "morning")).lower()
    entry = {"date": date_text, "edition": edition, "files": published}
    index = read_json(INDEX, default={"schema_version": "1.0", "publications": []})
    if not isinstance(index, dict) or not isinstance(index.get("publications"), list):
        raise PublishError("reports/archive-index.json has an invalid structure")

    index["publications"] = [
        old for old in index["publications"]
        if not (old.get("date") == date_text and old.get("edition") == edition)
    ]
    index["publications"].append(entry)
    index["publications"].sort(key=lambda row: (row.get("date", ""), row.get("edition", "")), reverse=True)
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LATEST.write_text(json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    MANIFEST.unlink()
    shutil.rmtree(PACKAGE)
    print(f"Published {len(published)} files for {date_text} ({edition}).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublishError as exc:
        print(f"PUBLISH FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
