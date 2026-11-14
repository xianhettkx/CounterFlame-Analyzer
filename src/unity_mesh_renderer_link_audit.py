#!/usr/bin/env python3
"""Read-only map of target Mesh objects to Unity render components and GameObjects."""
from __future__ import annotations
import argparse, json, zipfile
from pathlib import Path

TARGETS = {
 "butterfly_marblefade":[2233,2048],
 "specialist_pillow":[2217,2216,2215,2000,2115],
 "awp_dragonlore":[2114,2032,2045,1980,1981],
 "ak47_neonrevolution":[2014,2122,2231,1908,2043,2127],
 "m4a4_emperor":[1926,1930,1916,1931,2062,1978,1979],
 "deagle_codered":[2112,1953,2050,1974,1975],
}
def ptrs(v, field="", depth=0):
 if depth>7 or v is None or isinstance(v,(str,bytes,int,float,bool)): return
 if hasattr(v,"m_PathID") and hasattr(v,"m_FileID"):
  try:
   pid=int(v.m_PathID)
   if pid: yield {"field":field,"path_id":pid,"file_id":int(v.m_FileID)}
  except Exception: pass
  return
 if isinstance(v,(list,tuple)):
  for i,x in enumerate(v): yield from ptrs(x,f"{field}[{i}]",depth+1)
  return
 if isinstance(v,dict):
  for k,x in v.items(): yield from ptrs(x,f"{field}.{k}" if field else str(k),depth+1)
  return
 try: attrs=vars(v)
 except Exception: return
 for k,x in attrs.items():
  if not k.startswith("_"): yield from ptrs(x,f"{field}.{k}" if field else k,depth+1)
def peek(o):
 try:return str(o.peek_name() or "")
 except Exception:return ""
def main():
 p=argparse.ArgumentParser();p.add_argument("ipa");p.add_argument("--out",default="reports/mesh_renderer_audit");p.add_argument("--asset",default="Payload/CounterFlame.app/Data/resources.assets");a=p.parse_args()
 import UnityPy
 with zipfile.ZipFile(a.ipa) as z:
  names=[n for n in z.namelist() if n.endswith("/resources.assets")]
  path=next((n for n in names if n.endswith(a.asset)),names[0] if names else None)
  if not path: raise SystemExit("resources.assets missing")
  env=UnityPy.load(z.read(path))
 objs={int(o.path_id):o for o in env.objects}
 names_by_id={pid:peek(o) for pid,o in objs.items()}
 owners={}
 for pid,o in objs.items():
  if o.type.name!="GameObject": continue
  try:d=o.read()
  except Exception:continue
  for q in ptrs(getattr(d,"m_Component",[]),"m_Component"):
   owners.setdefault(q["path_id"],[]).append({"gameobject_path_id":pid,"gameobject_name":str(getattr(d,"m_Name","") or "")})
 targets={pid:key for key,ids in TARGETS.items() for pid in ids}
 rows=[]
 for pid,o in objs.items():
  typ=o.type.name
  if typ not in ("MeshFilter","SkinnedMeshRenderer","MeshRenderer","Transform"): continue
  try:d=o.read()
  except Exception as e: continue
  refs=list(ptrs(d))
  hit=[r for r in refs if r["path_id"] in targets]
  if not hit: continue
  rows.append({"component_path_id":pid,"component_type":typ,"component_name":peek(o),
   "owners":owners.get(pid,[]),"target_mesh_refs":[{**r,"skin_key":targets[r["path_id"]],"mesh_name":names_by_id.get(r["path_id"],"")} for r in hit],
   "all_refs":refs})
 result={"tool":"Unity target mesh renderer linkage audit","asset":path,
  "target_mesh_count":len(targets),"matched_component_count":len(rows),
  "matches":rows,"target_meshes":[{"path_id":pid,"skin_key":key,"name":names_by_id.get(pid,"")} for pid,key in targets.items()],
  "limitations":["Read-only static serialized references; does not prove runtime skin activation.","No Mesh, Material, inventory, networking, or IPA data modified."]}
 out=Path(a.out);out.mkdir(parents=True,exist_ok=True);f=out/"mesh_renderer_links.json";f.write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps({"target_meshes":len(targets),"matched_components":len(rows),"report":str(f)}))
if __name__=="__main__":main()
