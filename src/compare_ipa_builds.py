#!/usr/bin/env python3
"""Read-only structural diff between stock and reference CounterFlame IPAs."""
import hashlib, json, os, urllib.request, zipfile
from pathlib import Path

FILES = {
    "stock": ("https://github.com/xianhettkx/CounterFlame-Analyzer/releases/download/ipa-v1/CounterFlame-1.4.1-c7-ios.2.ipa",
              "6c3e740ca379c5daf55f635e1228414230ca4acb7608cd7b35e7f5c0e0d952d3"),
    "reference": ("https://github.com/xianhettkx/CounterFlame-Analyzer/releases/download/ipa-v1/CS2._1.4.1_.5.8.78.2.ipa",
                 "7b20f04d493c60cf5e215c0a82050fa691105fc47a0748e46e55cc3078f9cc9f"),
}
def download(name, url, expected):
    path = Path(f"{name}.ipa")
    h=hashlib.sha256(); total=0
    req=urllib.request.Request(url, headers={"User-Agent":"CounterFlame-IPA-Diff/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r, path.open("wb") as f:
        while True:
            b=r.read(8*1024*1024)
            if not b: break
            f.write(b); h.update(b); total+=len(b)
    got=h.hexdigest()
    print(f"{name}: {total} bytes sha256={got}")
    if got != expected: raise SystemExit(f"{name} SHA256 mismatch")
    return path

stock=download("stock", *FILES["stock"])
ref=download("reference", *FILES["reference"])
with zipfile.ZipFile(stock) as a, zipfile.ZipFile(ref) as b:
    A={i.filename:i for i in a.infolist() if not i.is_dir()}
    B={i.filename:i for i in b.infolist() if not i.is_dir()}
    common=sorted(A.keys() & B.keys())
    only_a=sorted(A.keys()-B.keys()); only_b=sorted(B.keys()-A.keys())
    changed=[]; key=[]
    for n in common:
        x,y=A[n],B[n]
        if x.file_size != y.file_size or x.CRC != y.CRC:
            changed.append({"path":n,"stock_size":x.file_size,"reference_size":y.file_size,
                            "stock_crc":f"{x.CRC:08x}","reference_crc":f"{y.CRC:08x}"})
    critical_tokens=("resources.assets","global-metadata.dat","UnityFramework","CounterFlame.app/CounterFlame",
                     "catalog.json","settings.json","Info.plist","embedded.mobileprovision")
    critical=[x for x in changed if any(t.lower() in x["path"].lower() for t in critical_tokens)]
    out={"stock_entries":len(A),"reference_entries":len(B),"common_entries":len(common),
         "only_stock":only_a,"only_reference":only_b,"changed_count":len(changed),
         "changed_entries":changed,"critical_changed_entries":critical,
         "interpretation":"A changed executable/metadata suggests client-build changes; changed Addressables catalog/bundles suggests content mapping or asset changes. Hash/CRC diff alone does not prove the runtime unlock path."}
    Path("reports").mkdir(exist_ok=True)
    Path("reports/ipa_build_diff.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
    lines=["# Stock vs reference IPA structural diff","",
           f"- Stock entries: {len(A)}",f"- Reference entries: {len(B)}",
           f"- Common entries: {len(common)}",f"- Changed entries: {len(changed)}",
           f"- Only stock: {len(only_a)}",f"- Only reference: {len(only_b)}","",
           "## Critical changed entries",""]
    lines += [f"- `{x['path']}` ({x['stock_size']} → {x['reference_size']} bytes)" for x in critical] or ["- None"]
    lines += ["","## All changed entries",""] + [f"- `{x['path']}` ({x['stock_size']} → {x['reference_size']} bytes)" for x in changed]
    Path("reports/ipa_build_diff.md").write_text("\n".join(lines),encoding="utf-8")
    print(f"changed={len(changed)} critical={len(critical)}")
