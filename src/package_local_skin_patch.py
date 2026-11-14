#!/usr/bin/env python3
"""Repack the original IPA with a locally patched resources.assets file.

The original IPA is never modified. The output is an unsigned local-visual
modification and must be re-signed by the owner's normal sideloading tool.
"""
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
    p.add_argument("--out",default="CounterFlame-Local-Skin-Patch.ipa")
    a=p.parse_args()
    original=Path(a.original_ipa); patched=Path(a.patched_resources); output=Path(a.out)
    if not original.is_file() or not patched.is_file():
        raise SystemExit("Original IPA or patched resources.assets file is missing")
    with zipfile.ZipFile(original,"r") as zin:
        candidates=[i for i in zin.infolist() if i.filename.endswith("/resources.assets")]
        if len(candidates)!=1:
            raise SystemExit(f"Expected exactly one resources.assets entry, found {len(candidates)}")
        target=candidates[0].filename
        with zipfile.ZipFile(output,"w",allowZip64=True) as zout:
            zout.comment=zin.comment
            for info in zin.infolist():
                new_info=copy(info)
                with zout.open(new_info,"w",force_zip64=True) as dst:
                    if info.filename==target:
                        with patched.open("rb") as src: shutil.copyfileobj(src,dst,CHUNK)
                    else:
                        with zin.open(info,"r") as src: shutil.copyfileobj(src,dst,CHUNK)
                print(f"[REPACK] {info.filename}",flush=True) if info.filename==target else None
    # Verify ZIP structure and the exact replacement payload.
    with zipfile.ZipFile(output,"r") as zf:
        bad=zf.testzip()
        if bad: raise SystemExit(f"ZIP verification failed at {bad}")
        with zf.open(target) as f:
            h=hashlib.sha256()
            for block in iter(lambda:f.read(CHUNK),b""): h.update(block)
    patched_hash=sha256(patched)
    if h.hexdigest()!=patched_hash:
        raise SystemExit("Repacked resources.assets hash does not match patch input")
    print(f"[OK] Output IPA: {output} ({output.stat().st_size} bytes)")
    print(f"[OK] Patched resource: {target}")
    print(f"[OK] resources.assets SHA256: {patched_hash}")
    print("[NOTE] IPA signature is invalidated by the local resource edit; re-sign with your normal iOS sideloading tool.")
if __name__=="__main__": main()
