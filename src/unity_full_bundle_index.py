#!/usr/bin/env python3
"""Read-only Unity object, CAB dependency, and non-bundle asset index."""
from __future__ import annotations
import argparse, csv, json, zipfile
from collections import Counter
from pathlib import Path
from typing import Any

MODEL_TYPES = {"GameObject","Transform","Mesh","SkinnedMeshRenderer","MeshRenderer","MeshFilter","Animator","Avatar","AnimationClip","Animation","Material","MonoBehaviour"}
CANDIDATE_EXTS = {".assets",".asset",".resource",".ress",".dat",".bytes",".unity3d"}

def inspect_unity_data(data: bytes, UnityPy: Any) -> dict[str, Any]:
    env=UnityPy.load(data); counts: Counter[str]=Counter()
    objects=[]; versions=set(); bundle_metadata=[]; external_files=[]; serialized_files=[]
    for cab_key,cab_obj in getattr(env,"cabs",{}).items():
        serialized_files.append({"key":str(cab_key),"name":str(getattr(cab_obj,"name","") or ""),"file_name":str(getattr(cab_obj,"file_name","") or ""),"unity_version":str(getattr(cab_obj,"unity_version","") or ""),"source":"env.cabs"})
    for file_key,file_obj in getattr(env,"files",{}).items():
        serialized_files.append({"key":str(file_key),"name":str(getattr(file_obj,"name","") or ""),"file_name":str(getattr(file_obj,"file_name","") or ""),"unity_version":str(getattr(file_obj,"unity_version","") or ""),"source":"env.files"})
        for ext in getattr(file_obj,"externals",[]) or []:
            external_files.append({"file_name":str(getattr(ext,"path","") or getattr(ext,"name","") or ""),"guid":str(getattr(ext,"guid","") or ""),"type":str(getattr(ext,"type","") or "")})
    for obj in env.objects:
        t=getattr(getattr(obj,"type",None),"name","Unknown"); counts[t]+=1
        version=getattr(getattr(obj,"assets_file",None),"unity_version",None)
        if version: versions.add(str(version))
        try: name=str(obj.peek_name() or "")
        except Exception: name=""
        objects.append({"type":t,"path_id":int(getattr(obj,"path_id",0)),"name":name})
        if t=="AssetBundle":
            try:
                data_obj=obj.read(); containers=[]
                for item in getattr(data_obj,"m_Container",[]) or []:
                    try: key,ptr=item
                    except Exception: key,ptr="",item
                    containers.append({"key":str(key),"file_id":int(getattr(ptr,"file_id",0)),"path_id":int(getattr(ptr,"path_id",0))})
                bundle_metadata.append({"assetbundle_name":str(getattr(data_obj,"m_AssetBundleName","") or ""),"dependencies":[str(x) for x in (getattr(data_obj,"m_Dependencies",[]) or [])],"container_count":len(containers),"containers":containers[:5000]})
            except Exception as exc: bundle_metadata.append({"metadata_error":f"{type(exc).__name__}: {exc}"[:300]})
    return {"decode_status":"decoded","unity_versions":sorted(versions),"object_count":sum(counts.values()),"type_counts":dict(sorted(counts.items())),"objects":objects,"assetbundle_metadata":bundle_metadata,"external_files":external_files,"serialized_files":serialized_files}

def run(ipa:Path,out:Path)->dict[str,Any]:
    try: import UnityPy
    except ImportError as exc: raise RuntimeError("UnityPy missing; install requirements.txt") from exc
    out.mkdir(parents=True,exist_ok=True); rows=[]; nonbundle=[]
    with zipfile.ZipFile(ipa,"r") as zf:
        infos=[i for i in zf.infolist() if not i.is_dir()]
        paths=[i.filename for i in infos if i.filename.lower().endswith(".bundle")]; total=len(paths)
        for index,path in enumerate(paths,1):
            row={"ipa_path":path,"bundle_size_bytes":zf.getinfo(path).file_size,"decode_status":"decode_error","unity_versions":[],"object_count":0,"type_counts":{},"objects":[],"assetbundle_metadata":[],"external_files":[],"serialized_files":[],"error":""}
            try: row.update(inspect_unity_data(zf.read(path),UnityPy))
            except Exception as exc: row["error"]=f"{type(exc).__name__}: {exc}"[:500]
            rows.append(row)
            if index%100==0 or index==total: print(f"[{index}/{total}] bundles indexed",flush=True)
        candidates=[i for i in infos if not i.filename.lower().endswith(".bundle") and Path(i.filename).suffix.lower() in CANDIDATE_EXTS and i.file_size<=256*1024*1024]
        for index,info in enumerate(candidates,1):
            entry={"ipa_path":info.filename,"size_bytes":info.file_size,"decode_status":"not_unity_or_unreadable","unity_versions":[],"object_count":0,"type_counts":{},"objects":[],"error":""}
            try:
                raw=zf.read(info); entry["header_hex"]=raw[:24].hex()
                result=inspect_unity_data(raw,UnityPy)
                entry.update({k:result[k] for k in ("decode_status","unity_versions","object_count","type_counts","objects","serialized_files","external_files")})
            except Exception as exc: entry["error"]=f"{type(exc).__name__}: {exc}"[:400]
            nonbundle.append(entry)
            print(f"[non-bundle {index}/{len(candidates)}] {info.filename}",flush=True)
    key_to_path={}
    for row in rows:
        for sf in row.get("serialized_files",[]):
            for key in (sf.get("key",""),sf.get("name",""),sf.get("file_name","")):
                if key: key_to_path[key.lower()]=row["ipa_path"]
    dependency_edges=[]
    for row in rows:
        for meta in row.get("assetbundle_metadata",[]):
            for dep in meta.get("dependencies",[]):
                dependency_edges.append({"source_bundle":row["ipa_path"],"dependency_id":dep,"matched_bundle":key_to_path.get(dep.lower())})
    model_hits=[r for r in rows+nonbundle if any(k in r.get("type_counts",{}) for k in ("Mesh","GameObject","SkinnedMeshRenderer","MeshRenderer","MeshFilter","Animator","Avatar","AnimationClip"))]
    report={"tool":"CounterFlame Full Unity Asset Index","schema_version":4,"mode":"read_only_full_object_names_cab_dependency_and_nonbundle_asset_index","ipa_filename":ipa.name,"bundle_count":len(rows),"decoded_bundle_count":sum(r["decode_status"]=="decoded" for r in rows),"failed_bundle_count":sum(r["decode_status"]!="decoded" for r in rows),"nonbundle_candidate_count":len(nonbundle),"nonbundle_decoded_count":sum(r["decode_status"]=="decoded" for r in nonbundle),"nonbundle_candidates":nonbundle,"model_candidate_bundle_count":len(model_hits),"model_candidate_bundles":model_hits,"dependency_edge_count":len(dependency_edges),"dependency_edges":dependency_edges,"dependency_edges_resolved":sum(bool(x["matched_bundle"]) for x in dependency_edges),"limitations":["Static object inventory and dependency metadata only; does not prove runtime loading or equip behavior.","Only non-bundle files with Unity asset-like extensions and size up to 256 MiB are probed.","No IPA contents are modified, rebuilt, injected, or re-signed.","MonoBehaviour custom fields may require matching IL2CPP type metadata."]}
    (out/"unity_full_bundle_index.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    with (out/"unity_full_bundle_index.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f); w.writerow(["ipa_path","bundle_size_bytes","decode_status","object_count","unity_versions","type_counts","objects","assetbundle_metadata","external_files","serialized_files","error"])
        for r in rows: w.writerow([r["ipa_path"],r["bundle_size_bytes"],r["decode_status"],r["object_count"],";".join(r["unity_versions"]),json.dumps(r["type_counts"],ensure_ascii=False),json.dumps(r["objects"],ensure_ascii=False),json.dumps(r["assetbundle_metadata"],ensure_ascii=False),json.dumps(r["external_files"],ensure_ascii=False),json.dumps(r["serialized_files"],ensure_ascii=False),r["error"]])
    with (out/"unity_nonbundle_asset_candidates.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f); w.writerow(["ipa_path","size_bytes","decode_status","object_count","unity_versions","type_counts","objects","error"])
        for r in nonbundle: w.writerow([r["ipa_path"],r["size_bytes"],r["decode_status"],r["object_count"],";".join(r["unity_versions"]),json.dumps(r["type_counts"],ensure_ascii=False),json.dumps(r["objects"],ensure_ascii=False),r["error"]])
    return report

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("ipa"); p.add_argument("--out",default="reports"); a=p.parse_args()
    r=run(Path(a.ipa),Path(a.out)); print("[OK] Full Unity asset index complete"); print(f"Bundles: {r['bundle_count']} decoded {r['decoded_bundle_count']}"); print(f"Non-bundle candidates: {r['nonbundle_candidate_count']} decoded {r['nonbundle_decoded_count']}"); print(f"Model candidates: {r['model_candidate_bundle_count']}"); print(f"Dependency edges: {r['dependency_edge_count']} (resolved {r['dependency_edges_resolved']})"); print(f"Errors: {r['failed_bundle_count']}"); return 0
if __name__=="__main__": raise SystemExit(main())
