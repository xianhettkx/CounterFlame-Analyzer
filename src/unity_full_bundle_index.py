#!/usr/bin/env python3
"""Read-only full AssetBundle object and dependency index."""
from __future__ import annotations
import argparse, csv, json, zipfile
from collections import Counter
from pathlib import Path
from typing import Any

MODEL_TYPES = {"GameObject","Transform","Mesh","SkinnedMeshRenderer","MeshRenderer","MeshFilter","Animator","Avatar","AnimationClip","Animation","Material","MonoBehaviour"}

def inspect_bundle(data: bytes, UnityPy: Any) -> dict[str, Any]:
    env = UnityPy.load(data)
    counts: Counter[str] = Counter()
    objects, versions, bundle_metadata, external_files = [], set(), [], []
    for file_obj in getattr(env, "files", {}).values():
        for ext in getattr(file_obj, "externals", []) or []:
            external_files.append({"file_name": str(getattr(ext,"path","") or getattr(ext,"name","") or ""), "guid": str(getattr(ext,"guid","") or ""), "type": str(getattr(ext,"type","") or "")})
    for obj in env.objects:
        t = getattr(getattr(obj,"type",None),"name","Unknown")
        counts[t] += 1
        version = getattr(getattr(obj,"assets_file",None),"unity_version",None)
        if version: versions.add(str(version))
        if t in MODEL_TYPES:
            try: name = obj.peek_name()
            except Exception: name = ""
            objects.append({"type":t,"path_id":int(getattr(obj,"path_id",0)),"name":str(name or "")})
        if t == "AssetBundle":
            try:
                data_obj = obj.read()
                containers = []
                for item in getattr(data_obj,"m_Container",[]) or []:
                    try: key, ptr = item
                    except Exception: key, ptr = "", item
                    containers.append({"key":str(key),"file_id":int(getattr(ptr,"file_id",0)),"path_id":int(getattr(ptr,"path_id",0))})
                bundle_metadata.append({"assetbundle_name":str(getattr(data_obj,"m_AssetBundleName","") or ""), "dependencies":[str(x) for x in (getattr(data_obj,"m_Dependencies",[]) or [])], "container_count":len(containers), "containers":containers[:5000]})
            except Exception as exc:
                bundle_metadata.append({"metadata_error":f"{type(exc).__name__}: {exc}"[:300]})
    return {"decode_status":"decoded","unity_versions":sorted(versions),"object_count":sum(counts.values()),"type_counts":dict(sorted(counts.items())),"model_objects":objects,"assetbundle_metadata":bundle_metadata,"external_files":external_files}

def run(ipa: Path, out: Path) -> dict[str, Any]:
    try: import UnityPy
    except ImportError as exc: raise RuntimeError("UnityPy missing; install requirements.txt") from exc
    out.mkdir(parents=True,exist_ok=True)
    rows=[]
    with zipfile.ZipFile(ipa,"r") as zf:
        paths=[n for n in zf.namelist() if n.lower().endswith(".bundle")]
        total=len(paths)
        for index,path in enumerate(paths,1):
            row={"ipa_path":path,"bundle_size_bytes":zf.getinfo(path).file_size,"decode_status":"decode_error","unity_versions":[],"object_count":0,"type_counts":{},"model_objects":[],"assetbundle_metadata":[],"external_files":[],"error":""}
            try: row.update(inspect_bundle(zf.read(path),UnityPy))
            except Exception as exc: row["error"]=f"{type(exc).__name__}: {exc}"[:500]
            rows.append(row)
            if index%100==0 or index==total: print(f"[{index}/{total}] bundles indexed",flush=True)
    model_hits=[r for r in rows if any(k in r["type_counts"] for k in ("Mesh","GameObject","SkinnedMeshRenderer","MeshRenderer","MeshFilter","Animator","Avatar","AnimationClip"))]
    report={"tool":"CounterFlame Full Unity Bundle Index","schema_version":2,"mode":"read_only_full_bundle_type_name_and_dependency_index","ipa_filename":ipa.name,"bundle_count":len(rows),"decoded_bundle_count":sum(r["decode_status"]=="decoded" for r in rows),"failed_bundle_count":sum(r["decode_status"]!="decoded" for r in rows),"model_candidate_bundle_count":len(model_hits),"model_candidate_bundles":model_hits,"limitations":["Static object and dependency metadata only; does not prove runtime loading or equip behavior.","AssetBundle container and dependency metadata is recorded where readable.","No IPA contents are modified, rebuilt, injected, or re-signed.","MonoBehaviour custom fields may require matching IL2CPP type metadata."]}
    (out/"unity_full_bundle_index.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    with (out/"unity_full_bundle_index.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f); w.writerow(["ipa_path","bundle_size_bytes","decode_status","object_count","unity_versions","type_counts","model_objects","assetbundle_metadata","external_files","error"])
        for r in rows: w.writerow([r["ipa_path"],r["bundle_size_bytes"],r["decode_status"],r["object_count"],";".join(r["unity_versions"]),json.dumps(r["type_counts"],ensure_ascii=False),json.dumps(r["model_objects"],ensure_ascii=False),json.dumps(r["assetbundle_metadata"],ensure_ascii=False),json.dumps(r["external_files"],ensure_ascii=False),r["error"]])
    return report

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("ipa"); p.add_argument("--out",default="reports"); a=p.parse_args()
    report=run(Path(a.ipa),Path(a.out)); print("[OK] Full bundle index complete"); print(f"Bundles: {report['bundle_count']}"); print(f"Decoded: {report['decoded_bundle_count']}"); print(f"Model candidates: {report['model_candidate_bundle_count']}"); print(f"Errors: {report['failed_bundle_count']}"); return 0
if __name__=="__main__": raise SystemExit(main())
