#!/usr/bin/env python3
"""Validate the local-only skin mapping manifest without modifying an IPA."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

REQUIRED = {
    "butterfly_marblefade", "specialist_pillow", "awp_dragonlore",
    "ak47_neonrevolution", "m4a4_emperor", "deagle_codered",
}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="config/local_skin_pseudo_entity_map.json")
    parser.add_argument("--out", default="reports/local_skin_mapping_validation.json")
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    rows = manifest.get("skins", [])
    by_key = {row.get("key"): row for row in rows}
    errors = []
    missing = sorted(REQUIRED - set(by_key))
    extra = sorted(set(by_key) - REQUIRED)
    if missing:
        errors.append({"type": "missing_skin_entries", "keys": missing})
    if extra:
        errors.append({"type": "unexpected_skin_entries", "keys": extra})
    for key in sorted(REQUIRED & set(by_key)):
        row = by_key[key]
        for side in ("first_person", "third_person"):
            target = row.get(side) or {}
            if not target.get("mesh") or not target.get("base_materials"):
                errors.append({"type": "incomplete_renderer_mapping", "skin": key, "side": side})
        if not row.get("skin_materials"):
            errors.append({"type": "missing_skin_materials", "skin": key})
        if not row.get("textures"):
            errors.append({"type": "missing_texture_dependencies", "skin": key})
    safety = manifest.get("safety", {})
    for flag in ("server_inventory_modified", "account_entitlements_modified",
                 "network_or_anticheat_modified", "runtime_injection"):
        if safety.get(flag) is not False:
            errors.append({"type": "unsafe_or_undefined_scope", "flag": flag})
    result = {
        "manifest": args.manifest,
        "skin_count": len(rows),
        "required_skin_count": len(REQUIRED),
        "mapping_entries_complete": not errors,
        "activation_status": manifest.get("status", "unspecified"),
        "errors": errors,
        "important_limit": "Static mapping validation only; no IPA mutation or runtime rendering test is performed."
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
