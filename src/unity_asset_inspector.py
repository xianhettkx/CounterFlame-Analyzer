#!/usr/bin/env python3
"""Read-only UnityPy inventory for target-skin AssetBundles inside an IPA."""
from __future__ import annotations

import argparse
import csv
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

INTERESTING_TYPES = {
    "AssetBundle", "GameObject", "Transform", "Mesh", "SkinnedMeshRenderer",
    "MeshRenderer", "MeshFilter", "Material", "Texture2D", "Sprite",
    "AnimationClip", "Animator", "Avatar", "MonoBehaviour", "Shader",
    "SkinnedMeshRenderer", "Texture2DArray",
}


def clean_path(value: str) -> str:
    prefix = "{UnityEngine.AddressableAssets.Addressables.RuntimePath}/"
    return value.replace(prefix, "").lstrip("/")


def select_target_paths(catalog: dict[str, Any], targets: dict[str, Any]) -> list[dict[str, str]]:
    ids = catalog.get("m_InternalIds", [])
    if not isinstance(ids, list):
        return []
    skins = targets.get("skins", [])
    selected: dict[str, dict[str, str]] = {}
    for skin in skins:
        key = str(skin.get("skin_key", "")).lower()
        if not key:
            continue
        for raw in ids:
            if not isinstance(raw, str) or not raw.lower().endswith(".bundle"):
                continue
            if key in raw.lower():
                selected[clean_path(raw)] = {
                    "skin_key": key,
                    "display_name": str(skin.get("display_name", key)),
                    "catalog_path": raw,
                }
    return [selected[k] for k in sorted(selected)]


def inspect_bundle_bytes(data: bytes, UnityPy: Any) -> dict[str, Any]:
    env = UnityPy.load(data)
    type_counts: Counter[str] = Counter()
    objects = []
    unity_versions = set()
    for obj in env.objects:
        type_name = getattr(getattr(obj, "type", None), "name", "Unknown")
        type_counts[type_name] += 1
        assets_file = getattr(obj, "assets_file", None)
        version = getattr(assets_file, "unity_version", None)
        if version:
            unity_versions.add(str(version))
        if type_name not in INTERESTING_TYPES:
            continue
        try:
            name = obj.peek_name()
        except Exception:
            name = None
        objects.append({
            "type": type_name,
            "path_id": int(getattr(obj, "path_id", 0)),
            "name": str(name) if name else "",
        })
    return {
        "decode_status": "decoded",
        "unity_versions": sorted(unity_versions),
        "object_count": sum(type_counts.values()),
        "type_counts": dict(sorted(type_counts.items())),
        "objects": objects,
    }


def inspect_ipa(ipa_path: Path, out_dir: Path, targets_path: Path) -> dict[str, Any]:
    try:
        import UnityPy
    except ImportError as exc:
        raise RuntimeError("UnityPy is not installed. Install requirements.txt first.") from exc

    targets = json.loads(targets_path.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ipa_path, "r") as zf:
        catalogs = [
            name for name in zf.namelist()
            if name.lower().endswith("/catalog.json") or name.lower() == "catalog.json"
        ]
        if not catalogs:
            raise ValueError("No catalog.json found in IPA")
        catalog = json.loads(zf.read(catalogs[0]).decode("utf-8-sig"))
        selected = select_target_paths(catalog, targets)
        zip_names = set(zf.namelist())
        rows = []
        for item in selected:
            path = item["catalog_path"]
            if path not in zip_names:
                suffix_hits = [n for n in zip_names if n.endswith("/" + path)]
                ipa_path_in_zip = suffix_hits[0] if len(suffix_hits) == 1 else None
            else:
                ipa_path_in_zip = path
            row = {
                **item,
                "ipa_path": ipa_path_in_zip or "",
                "bundle_size_bytes": 0,
                "decode_status": "not_found",
                "unity_versions": [],
                "object_count": 0,
                "type_counts": {},
                "objects": [],
                "error": "",
            }
            if ipa_path_in_zip:
                info = zf.getinfo(ipa_path_in_zip)
                row["bundle_size_bytes"] = info.file_size
                try:
                    # Read one selected bundle at a time; never extract or modify the IPA.
                    result = inspect_bundle_bytes(zf.read(info), UnityPy)
                    row.update(result)
                except Exception as exc:
                    row["decode_status"] = "decode_error"
                    row["error"] = f"{type(exc).__name__}: {exc}"[:1000]
            rows.append(row)

    report = {
        "tool": "CounterFlame Unity Asset Inspector",
        "schema_version": 1,
        "mode": "read_only_target_bundle_inventory",
        "ipa_filename": ipa_path.name,
        "target_bundle_count": len(rows),
        "decoded_bundle_count": sum(x["decode_status"] == "decoded" for x in rows),
        "failed_bundle_count": sum(x["decode_status"] == "decode_error" for x in rows),
        "not_found_bundle_count": sum(x["decode_status"] == "not_found" for x in rows),
        "bundles": rows,
        "limitations": [
            "This pass inventories decoded Unity object types and names only.",
            "It does not modify, rebuild, inject, or re-sign the IPA.",
            "Object presence alone does not prove runtime dependency or skin equip behavior.",
            "MonoBehaviour custom fields may require matching IL2CPP type metadata to decode fully.",
        ],
    }
    (out_dir / "unity_asset_inventory.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (out_dir / "unity_asset_inventory.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "skin_key", "display_name", "decode_status", "bundle_size_bytes",
            "object_count", "unity_versions", "type_counts", "ipa_path", "error",
        ])
        for row in rows:
            writer.writerow([
                row["skin_key"], row["display_name"], row["decode_status"],
                row["bundle_size_bytes"], row["object_count"],
                ";".join(row["unity_versions"]),
                json.dumps(row["type_counts"], ensure_ascii=False),
                row["ipa_path"], row["error"],
            ])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only target Unity AssetBundle inventory")
    parser.add_argument("ipa")
    parser.add_argument("--out", default="reports")
    parser.add_argument("--targets", default="config/target_skins.json")
    args = parser.parse_args()
    try:
        report = inspect_ipa(Path(args.ipa), Path(args.out), Path(args.targets))
    except Exception as exc:
        print(f"[ERROR] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print("[OK] Unity object inventory complete")
    print(f"Target bundles: {report['target_bundle_count']}")
    print(f"Decoded: {report['decoded_bundle_count']}")
    print(f"Decode errors: {report['failed_bundle_count']}")
    print(f"Not found: {report['not_found_bundle_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
