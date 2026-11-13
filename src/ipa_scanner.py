#!/usr/bin/env python3
"""Read-only inventory and Addressables catalog scanner for Unity IPA files.

The IPA is treated as a ZIP archive. No archive members are extracted to disk.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

try:
    # Package import (e.g. tests importing src.ipa_scanner).
    from .bundle_inspector import inspect_header
except ImportError:
    # Direct script execution: python src/ipa_scanner.py ...
    from bundle_inspector import inspect_header

TEXT_LIMIT = 64 * 1024 * 1024
CATALOG_NAMES = {"catalog.json", "catalog.bin", "catalog.hash", "settings.json"}


def safe_json_read(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> Any:
    if info.file_size > TEXT_LIMIT:
        raise ValueError(f"Refusing oversized JSON member ({info.file_size} bytes)")
    raw = zf.read(info)
    return json.loads(raw.decode("utf-8-sig"))


def walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from walk_strings(k)
            yield from walk_strings(v)
    elif isinstance(value, list):
        for item in value:
            yield from walk_strings(item)


def extract_internal_ids(data: Any) -> list[str]:
    found: list[str] = []
    if isinstance(data, dict):
        ids = data.get("m_InternalIds")
        if isinstance(ids, list):
            found.extend(x for x in ids if isinstance(x, str))
        # Some builds wrap catalog content in an outer object.
        for value in data.values():
            if isinstance(value, (dict, list)):
                found.extend(extract_internal_ids(value))
    elif isinstance(data, list):
        for value in data:
            found.extend(extract_internal_ids(value))
    return list(dict.fromkeys(found))


def classify_path(path: str) -> str:
    p = path.lower()
    if p.endswith(".bundle") or ".bundle?" in p:
        return "bundle"
    if "catalog" in p:
        return "catalog"
    if "settings.json" in p:
        return "settings"
    return "other"


def clean_internal_path(value: str) -> str:
    # Addressables RuntimePath placeholders are not physical ZIP paths.
    value = value.replace("{UnityEngine.AddressableAssets.Addressables.RuntimePath}/", "")
    return value.lstrip("/")


def build_html(report: dict[str, Any]) -> str:
    summary = report["summary"]
    rows = []
    for item in report["catalogs"]:
        rows.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                html.escape(item["ipa_path"]),
                item.get("internal_id_count", "—"),
                item.get("bundle_id_count", "—"),
                html.escape(item.get("parse_status", "not parsed")),
            )
        )
    missing = "".join(
        f"<li>{html.escape(x)}</li>" for x in report.get("catalog_path_missing_from_ipa", [])[:300]
    ) or "<li>None</li>"
    return """<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>CounterFlame IPA Analysis</title>
<style>
body{{font:15px -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#18202a}}
h1{{font-size:25px}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px}}
.card{{border:1px solid #d9dee7;border-radius:12px;padding:14px}}.n{{font-size:24px;font-weight:700}}
small{{color:#667085}}table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;padding:9px;border-bottom:1px solid #e5e7eb;overflow-wrap:anywhere}}
.warn{{background:#fff8e6;padding:12px;border-radius:10px}}
</style><body>
<h1>CounterFlame IPA Analysis</h1>
<p><small>Generated: {generated}</small></p>
<div class="grid">
<div class="card"><small>IPA entries</small><div class="n">{entries}</div></div>
<div class="card"><small>Total uncompressed size</small><div class="n">{size}</div></div>
<div class="card"><small>Catalog JSON files</small><div class="n">{catalogs}</div></div>
<div class="card"><small>Catalog bundle IDs</small><div class="n">{bundles}</div></div>
<div class="card"><small>Physical bundle entries</small><div class="n">{physical}</div></div>
<div class="card"><small>Matched target paths</small><div class="n">{matched}</div></div>
</div>
<h2>Catalog files</h2><table><tr><th>IPA path</th><th>Internal IDs</th><th>Bundle IDs</th><th>Status</th></tr>{rows}</table>
<h2>Catalog paths not found as IPA entries</h2>
<p class="warn">A catalog path is only a reference. “Not found” can occur when the catalog points to remote content, uses transformed paths, or the archive layout differs. A match still does not prove the bundle's internal Unity assets.</p>
<ul>{missing}</ul>
<h2>Interpretation limits</h2><ul>
<li>This is a read-only ZIP and JSON inventory; it does not modify the IPA.</li>
<li>Catalog path matches do not prove dependency relationships or inner asset identity.</li>
<li>UnityFS bundle contents are not fully decoded by this first version.</li>
</ul></body></html>""".format(
        generated=html.escape(report["generated_utc"]),
        entries=summary["ipa_entry_count"],
        size=html.escape(summary["total_uncompressed_size_human"]),
        catalogs=summary["catalog_json_count"],
        bundles=summary["catalog_bundle_id_count"],
        physical=summary["physical_bundle_entry_count"],
        matched=summary["catalog_paths_matched_to_ipa"],
        rows="".join(rows),
        missing=missing,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def human_bytes(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{n} B"


def scan_ipa(ipa_path: Path, output_dir: Path, targets_path: Path | None = None) -> dict[str, Any]:
    if not ipa_path.is_file():
        raise FileNotFoundError(f"IPA file not found: {ipa_path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(ipa_path, "r") as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        names = {i.filename for i in infos}
        by_lower = {i.filename.lower(): i for i in infos}
        physical_bundles = [i for i in infos if i.filename.lower().endswith(".bundle")]
        candidate_catalogs = [
            i for i in infos
            if PurePosixPath(i.filename).name.lower() == "catalog.json"
        ]
        catalog_reports = []
        all_internal_ids: list[str] = []
        all_catalog_paths: list[str] = []
        for info in candidate_catalogs:
            item: dict[str, Any] = {
                "ipa_path": info.filename,
                "file_size": info.file_size,
                "parse_status": "ok",
            }
            try:
                data = safe_json_read(zf, info)
                ids = extract_internal_ids(data)
                bundle_ids = [x for x in ids if classify_path(x) == "bundle"]
                item.update({
                    "internal_id_count": len(ids),
                    "bundle_id_count": len(bundle_ids),
                    "top_level_keys": list(data.keys())[:80] if isinstance(data, dict) else [],
                })
                all_internal_ids.extend(ids)
                all_catalog_paths.extend(bundle_ids)
            except Exception as exc:
                item["parse_status"] = f"error: {type(exc).__name__}: {exc}"
            catalog_reports.append(item)

        unique_catalog_paths = list(dict.fromkeys(all_catalog_paths))
        matched = []
        missing = []
        for raw in unique_catalog_paths:
            candidate = clean_internal_path(raw)
            # Exact path first; then suffix match to account for RuntimePath prefixes.
            if candidate in names:
                matched.append({"catalog_path": raw, "ipa_entry": candidate, "match": "exact"})
            else:
                suffix_hits = [n for n in names if n.endswith("/" + candidate) or n == candidate]
                if len(suffix_hits) == 1:
                    matched.append({"catalog_path": raw, "ipa_entry": suffix_hits[0], "match": "suffix"})
                else:
                    missing.append(raw)

        targets = {}
        if targets_path and targets_path.is_file():
            targets = json.loads(targets_path.read_text(encoding="utf-8"))
        skin_results = []
        for skin in targets.get("skins", []):
            key = skin["skin_key"].lower()
            hits = [x for x in unique_catalog_paths if key in x.lower()]
            ipa_hits = []
            for hit in hits:
                candidate = clean_internal_path(hit)
                direct = candidate in names
                suffix = [n for n in names if n.endswith("/" + candidate)]
                ipa_hits.append({
                    "catalog_path": hit,
                    "ipa_entry_match": direct or len(suffix) == 1,
                    "matched_ipa_entry": candidate if direct else (suffix[0] if len(suffix) == 1 else None),
                })
            skin_results.append({
                "skin_key": skin["skin_key"],
                "display_name": skin["display_name"],
                "expected_bundle_count": skin.get("expected_bundle_count"),
                "catalog_bundle_path_count": len(hits),
                "catalog_paths": ipa_hits,
                "status": "catalog_reference_found" if hits else "not_found_in_catalog",
                "warning": "Catalog references are not proof of internal asset contents or runtime loading.",
            })

        catalog_hashes = [
            {"ipa_path": i.filename, "size": i.file_size}
            for i in infos if PurePosixPath(i.filename).name.lower() == "catalog.hash"
        ]
        settings_files = [
            {"ipa_path": i.filename, "size": i.file_size}
            for i in infos if PurePosixPath(i.filename).name.lower() == "settings.json"
        ]
        total_size = sum(i.file_size for i in infos)
        report = {
            "tool": "CounterFlame Analyzer",
            "schema_version": 1,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "input": {
                "filename": ipa_path.name,
                "size_bytes": ipa_path.stat().st_size,
                "sha256": sha256_file(ipa_path),
            },
            "summary": {
                "ipa_entry_count": len(infos),
                "total_uncompressed_size": total_size,
                "total_uncompressed_size_human": human_bytes(total_size),
                "physical_bundle_entry_count": len(physical_bundles),
                "catalog_json_count": len(candidate_catalogs),
                "catalog_internal_id_count": len(set(all_internal_ids)),
                "catalog_bundle_id_count": len(unique_catalog_paths),
                "catalog_paths_matched_to_ipa": len(matched),
                "catalog_paths_not_found_in_ipa": len(missing),
            },
            "catalogs": catalog_reports,
            "catalog_hash_files": catalog_hashes,
            "settings_files": settings_files,
            "physical_bundles": [
                {
                    "ipa_path": i.filename,
                    "size_bytes": i.file_size,
                    "header": inspect_header(zf.open(i, "r")),
                }
                for i in physical_bundles
            ],
            "catalog_path_matches": matched,
            "catalog_path_missing_from_ipa": missing,
            "target_skins": skin_results,
            "limitations": [
                "IPA is scanned as a ZIP archive; members are not extracted.",
                "m_InternalIds are path references, not a dependency graph.",
                "Catalog path match does not prove bundle inner asset identity.",
                "UnityFS/SerializedFile internals are not decoded in this version.",
                "Remote Addressables content may not be packaged inside the IPA.",
            ],
        }

    (output_dir / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_dir / "bundle_inventory.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["ipa_path", "size_bytes"])
        writer.writerows((x["ipa_path"], x["size_bytes"]) for x in report["physical_bundles"])
    with (output_dir / "target_skin_validation.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["skin_key", "display_name", "catalog_path_count", "status", "catalog_path", "ipa_entry_match", "matched_ipa_entry"])
        for skin in skin_results:
            if skin["catalog_paths"]:
                for p in skin["catalog_paths"]:
                    writer.writerow([skin["skin_key"], skin["display_name"], skin["catalog_bundle_path_count"], skin["status"], p["catalog_path"], p["ipa_entry_match"], p["matched_ipa_entry"] or ""])
            else:
                writer.writerow([skin["skin_key"], skin["display_name"], 0, skin["status"], "", False, ""])
    (output_dir / "report.html").write_text(build_html(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only CounterFlame IPA scanner")
    parser.add_argument("ipa", help="Path to the .ipa file")
    parser.add_argument("--out", default="reports", help="Output directory (default: reports)")
    parser.add_argument("--targets", default="config/target_skins.json", help="Target skin JSON")
    args = parser.parse_args()
    try:
        report = scan_ipa(Path(args.ipa), Path(args.out), Path(args.targets))
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    s = report["summary"]
    print("[OK] Analysis complete")
    print(f"IPA entries: {s['ipa_entry_count']}")
    print(f"Physical bundles: {s['physical_bundle_entry_count']}")
    print(f"Catalog bundle IDs: {s['catalog_bundle_id_count']}")
    print(f"Matched catalog paths: {s['catalog_paths_matched_to_ipa']}")
    print(f"Reports: {args.out}/analysis.json, report.html, bundle_inventory.csv, target_skin_validation.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
