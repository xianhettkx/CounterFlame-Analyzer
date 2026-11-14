#!/usr/bin/env python3
"""Read-only ZIP member comparison for two IPA packages."""
import argparse, hashlib, json, zipfile
from pathlib import PurePosixPath

def digest_member(zf, info):
    h = hashlib.sha256()
    with zf.open(info) as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def inventory(path):
    with zipfile.ZipFile(path) as z:
        out = {}
        for info in z.infolist():
            if info.is_dir():
                continue
            out[info.filename] = {
                "size": info.file_size,
                "compressed_size": info.compress_size,
                "sha256": digest_member(z, info),
            }
        return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("original")
    ap.add_argument("candidate")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    left, right = inventory(a.original), inventory(a.candidate)
    names_l, names_r = set(left), set(right)
    added, removed = sorted(names_r-names_l), sorted(names_l-names_r)
    changed = []
    for name in sorted(names_l & names_r):
        if left[name]["sha256"] != right[name]["sha256"]:
            changed.append({"path": name, "original": left[name], "candidate": right[name]})
    focus = sorted(n for n in names_l | names_r if
        n.lower().endswith((".dylib", ".framework")) or
        n.lower().endswith("/info.plist") or
        n.lower().endswith("/resources.assets") or
        n.lower().endswith("/global-metadata.dat") or
        "/raw/aa/ios/" in n.lower())
    result = {
        "original_entries": len(left), "candidate_entries": len(right),
        "added_count": len(added), "removed_count": len(removed), "changed_count": len(changed),
        "added": [{"path":n, **right[n]} for n in added],
        "removed": [{"path":n, **left[n]} for n in removed],
        "changed": changed,
        "focus_paths": [{"path":n, "original":left.get(n), "candidate":right.get(n)} for n in focus],
        "interpretation": "Added/changed package members are static differences only; this does not prove runtime behavior or authorization status."
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({k:result[k] for k in ("original_entries","candidate_entries","added_count","removed_count","changed_count")}, ensure_ascii=False))
    print("Added paths:")
    for item in result["added"]: print("+", item["path"], item["size"])
    print("Removed paths:")
    for item in result["removed"]: print("-", item["path"], item["size"])
    print("Changed paths:")
    for item in result["changed"]: print("*", item["path"], item["original"]["size"], "->", item["candidate"]["size"])
    print("Focus paths:")
    for item in result["focus_paths"]:
        if item["original"] != item["candidate"]:
            print("!", item["path"], "original=", item["original"], "candidate=", item["candidate"])

if __name__ == "__main__":
    main()
