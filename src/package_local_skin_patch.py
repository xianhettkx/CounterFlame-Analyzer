#!/usr/bin/env python3
"""Repack an IPA with a local resources.assets patch and optional localized Unity files."""
from __future__ import annotations
import argparse, hashlib, shutil, zipfile
from copy import copy
from pathlib import Path

CHUNK=8*1024*1024

def sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(CHUNK),b""): h.update(block)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("original_ipa")
    p.add_argument("patched_resources")
    p.add_argument("--patch-dir",default=None,help="Directory containing additional patched IPA entries, preserving their archive paths")
    p.add_argument("--out",default="CounterFlame-Local-Skin-Patch.ipa")
    a=p.parse_args()
    original=Path(a.original_ipa); patched=Path(a.patched_resources); output=Path(a.out)
    patch_dir=Path(a.patch_dir) if a.patch_dir else None
    if not original.is_file() or not patched.is_file():
        raise SystemExit("Original IPA or patched resources.assets file is missing")
    with zipfile.ZipFile(original,"r") as zin:
        candidates=[i for i in zin.infolist() if i.filename.endswith("/resources.assets")]
        if len(candidates)!=1:
            raise SystemExit(f"Expected exactly one resources.assets entry, found {len(candidates)}")
        target=candidates[0].filename
        patched_count=0
        with zipfile.ZipFile(output,"w",allowZip64=True) as zout:
            zout.comment=zin.comment
            for info in zin.infolist():
                new_info=copy(info)
                replacement=(patch_dir / info.filename) if patch_dir else None
                if replacement is not None and not replacement.is_file():
                    replacement=None
                if replacement is None and info.filename==target:
                    replacement=patched
                with zout.open(new_info,"w",force_zip64=True) as dst:
                    if replacement is not None:
                        with replacement.open("rb") as src: shutil.copyfileobj(src,dst,CHUNK)
                        patched_count+=1
                        print(f"[REPACK] {info.filename}",flush=True)
                    else:
                        with zin.open(info,"r") as src: shutil.copyfileobj(src,dst,CHUNK)
    with zipfile.ZipFile(output,"r") as zf:
        bad=zf.testzip()
        if bad: raise SystemExit(f"ZIP integrity check failed at {bad}")
        with zf.open(target) as f:
            h=hashlib.sha256()
            for block in iter(lambda:f.read(CHUNK),b""): h.update(block)
    print(f"[OK] Output IPA: {output} ({output.stat().st_size} bytes)")
    print(f"[OK] Patched archive entries: {patched_count}")
    print(f"[OK] resources.assets SHA256: {h.hexdigest()}")
    print("[NOTE] IPA signature is invalidated by local asset edits; re-sign with your normal iOS sideloading tool.")

if __name__=="__main__": main()
