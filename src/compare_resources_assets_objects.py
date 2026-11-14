#!/usr/bin/env python3
"""Read-only Unity serialized-object diff for stock/reference resources.assets."""
from __future__ import annotations
import hashlib, json, zipfile
from pathlib import Path

STOCK = "https://github.com/xianhettkx/CounterFlame-Analyzer/releases/download/ipa-v1/CounterFlame-1.4.1-c7-ios.2.ipa"
REFERENCE = "https://github.com/xianhettkx/CounterFlame-Analyzer/releases/download/ipa-v1/CS2._1.4.1_.5.8.78.2.ipa"
STOCK_SHA = "6c3e740ca379c5daf55f635e1228414230ca4acb7608cd7b35e7f5c0e0d952d3"
REFERENCE_SHA = "7b20f04d493c60cf5e215c0a82050fa691105fc47a0748e46e55cc3078f9cc9f"
TARGET = "Payload/CounterFlame.app/Data/resources.assets"

def index_assets(data: bytes, UnityPy):
    env = UnityPy.load(data)
    result = {}
    errors = []
    for obj in env.objects:
        typ = getattr(getattr(obj, "type", None), "name", "Unknown")
        pid = int(getattr(obj, "path_id", 0))
        try:
            name = obj.peek_name() or ""
        except Exception:
            name = ""
        try:
            raw = obj.get_raw_data()
            digest = hashlib.sha256(raw).hexdigest()
            raw_size = len(raw)
        except Exception as exc:
            digest = None
            raw_size = None
            errors.append({"path_id": pid, "type": typ, "error": type(exc).__name__})
        entry = {
            "path_id": pid, "type": typ, "name": str(name),
            "sha256": digest, "raw_size": raw_size,
        }
        if typ == "MonoBehaviour" and str(name) == "LocalizationSettings":
            try:
                entry["type_tree"] = obj.read_typetree()
            except Exception as exc:
                entry["type_tree_error"] = f"{type(exc).__name__}: {exc}"
        result[(pid, typ)] = entry
    return result, errors

def main():
    import urllib.request
    import UnityPy
    out = Path("reports")
    out.mkdir(exist_ok=True)
    indexed = {}
    for label, url, expected in (
        ("stock", STOCK, STOCK_SHA), ("reference", REFERENCE, REFERENCE_SHA)
    ):
        path = Path(label + ".ipa")
        if not path.exists():
            req = urllib.request.Request(url, headers={"User-Agent": "CounterFlame-AssetDiff/1.0"})
            with urllib.request.urlopen(req, timeout=300) as response, path.open("wb") as f:
                while True:
                    chunk = response.read(8 * 1024 * 1024)
                    if not chunk: break
                    f.write(chunk)
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
                h.update(chunk)
        if h.hexdigest() != expected:
            raise SystemExit(f"{label} IPA SHA-256 mismatch: {h.hexdigest()}")
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.endswith(TARGET)]
            if len(names) != 1:
                raise SystemExit(f"{label}: expected exactly one {TARGET}, found {len(names)}")
            data = zf.read(names[0])
        indexed[label], errors = index_assets(data, UnityPy)
        indexed[label + "_errors"] = errors
        print(f"{label}: indexed {len(indexed[label])} objects; raw-data errors={len(errors)}")
    a, b = indexed["stock"], indexed["reference"]
    keys_a, keys_b = set(a), set(b)
    added = [b[k] for k in sorted(keys_b - keys_a)]
    removed = [a[k] for k in sorted(keys_a - keys_b)]
    changed = []
    for k in sorted(keys_a & keys_b):
        x, y = a[k], b[k]
        if x["sha256"] != y["sha256"] or x["name"] != y["name"]:
            changed.append({"stock": x, "reference": y})
    def normalize(value, depth=0):
        if depth > 12:
            return repr(value)[:300]
        if isinstance(value, dict):
            return {str(k): normalize(v, depth + 1) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalize(v, depth + 1) for v in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, bytes):
            return {"bytes_length": len(value), "hex_prefix": value[:32].hex()}
        return repr(value)[:500]

    def flatten(value, prefix=""):
        out = {}
        if isinstance(value, dict):
            for key, child in value.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                out.update(flatten(child, path))
        elif isinstance(value, list):
            out[prefix + ".__length__"] = len(value)
            for i, child in enumerate(value[:500]):
                out.update(flatten(child, f"{prefix}[{i}]"))
        else:
            out[prefix] = value
        return out

    tree_diffs = []
    for key in sorted(keys_a & keys_b):
        x, y = a[key], b[key]
        if "type_tree" in x or "type_tree" in y:
            tx, ty = normalize(x.get("type_tree")), normalize(y.get("type_tree"))
            fx, fy = flatten(tx or {}), flatten(ty or {})
            fields = []
            for field in sorted(set(fx) | set(fy)):
                if fx.get(field, "__MISSING__") != fy.get(field, "__MISSING__"):
                    fields.append({
                        "field": field,
                        "stock": fx.get(field, "__MISSING__"),
                        "reference": fy.get(field, "__MISSING__"),
                    })
            tree_diffs.append({
                "path_id": key[0], "type": key[1],
                "name": x.get("name") or y.get("name"),
                "stock_error": x.get("type_tree_error"),
                "reference_error": y.get("type_tree_error"),
                "changed_field_count": len(fields),
                "changed_fields": fields[:2000],
            })

    report = {
        "type_tree_diffs": tree_diffs,
        "scope": "Read-only UnityPy serialized-object comparison; no IPA modification.",
        "asset_path": TARGET,
        "stock_object_count": len(a),
        "reference_object_count": len(b),
        "added_object_count": len(added),
        "removed_object_count": len(removed),
        "changed_object_count": len(changed),
        "added_objects": added,
        "removed_objects": removed,
        "changed_objects": changed,
        "stock_raw_data_errors": indexed["stock_errors"],
        "reference_raw_data_errors": indexed["reference_errors"],
        "limitations": [
            "Raw object hashes identify serialized-object changes but do not interpret runtime behavior.",
            "Some Unity object types may not expose raw data through UnityPy.",
            "A changed object is not proof of a skin unlock or entitlement change."
        ]
    }
    (out / "resources_assets_object_diff.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Stock vs reference resources.assets object diff", "",
        f"- Stock objects: {len(a)}",
        f"- Reference objects: {len(b)}",
        f"- Added: {len(added)}",
        f"- Removed: {len(removed)}",
        f"- Changed: {len(changed)}",
        f"- Raw-data extraction errors: {len(indexed['stock_errors'])} stock / {len(indexed['reference_errors'])} reference", "",
        "## Added / removed / changed objects", ""
    ]
    for label, rows in (("Added", added), ("Removed", removed)):
        lines.append(f"### {label}")
        lines.extend([f"- {x['type']} path_id={x['path_id']} name={x['name']!r}" for x in rows] or ["- None"])
        lines.append("")
    lines.append("### Changed")
    lines.extend([
        f"- {x['stock']['type']} path_id={x['stock']['path_id']} "
        f"name={x['stock']['name']!r} -> {x['reference']['name']!r}; "
        f"sha256 {str(x['stock']['sha256'])[:12]} -> {str(x['reference']['sha256'])[:12]}"
        for x in changed
    ] or ["- None"])
    lines += ["", "## Type-tree field differences", ""]
    for tree in tree_diffs:
        lines.append(f"- {tree['name']} path_id={tree['path_id']}: {tree['changed_field_count']} changed fields")
        lines.extend([
            f"  - {x['field']}: {str(x['stock'])[:180]!r} -> {str(x['reference'])[:180]!r}"
            for x in tree["changed_fields"][:100]
        ])
    if not tree_diffs:
        lines.append("- No readable type-tree differences were found.")
    lines += ["", "## Limits", "",
        "This is a static serialized-object diff. It does not establish why an object changed,",
        "whether the game uses it at runtime, or whether an account/server recognizes any inventory state."]
    (out / "resources_assets_object_diff.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] object diff: added={len(added)} removed={len(removed)} changed={len(changed)}")

if __name__ == "__main__":
    main()
