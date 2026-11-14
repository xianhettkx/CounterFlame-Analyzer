#!/usr/bin/env python3
"""Read-only audit of MonoBehaviour script links on target weapon renderers.

This discovers serialized component/script relationships. It does not patch or
inject code, alter server inventory, or claim runtime equip support.
"""
from __future__ import annotations
import argparse, json, zipfile
from pathlib import Path
from typing import Any

TOKENS = ("butterfly","flip","ak47","awp","deagle","m4a4","m4a1","specialist","glove_ct",
          "dragonlore","neonrevolution","emperor","codered","pillow")
SKINS = ("butterfly_marblefade","specialist_pillow","awp_dragonlore",
         "ak47_neonrevolution","m4a4_emperor","deagle_codered")

def ptr_fields(value: Any, prefix: str = "", depth: int = 0):
    if depth > 8 or value is None or isinstance(value,(str,bytes,int,float,bool)):
        return
    if hasattr(value,"m_PathID") and hasattr(value,"m_FileID"):
        try:
            pid=int(value.m_PathID); fid=int(value.m_FileID)
            if pid: yield {"field":prefix,"file_id":fid,"path_id":pid}
        except Exception: pass
        return
    if isinstance(value,(list,tuple)):
        for i,item in enumerate(value):
            yield from ptr_fields(item,f"{prefix}[{i}]",depth+1)
        return
    if isinstance(value,dict):
        for k,item in value.items():
            yield from ptr_fields(item,f"{prefix}.{k}" if prefix else str(k),depth+1)
        return
    try: attrs=vars(value)
    except Exception: return
    for key,item in attrs.items():
        if not key.startswith("_"):
            yield from ptr_fields(item,f"{prefix}.{key}" if prefix else key,depth+1)

def safe_name(obj):
    try: return str(obj.peek_name() or "")
    except Exception: return ""

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("ipa")
    ap.add_argument("--out",default="reports/skin_component_audit")
    ap.add_argument("--asset",default="Payload/CounterFlame.app/Data/resources.assets")
    args=ap.parse_args()
    import UnityPy
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.ipa) as zf:
        matches=[n for n in zf.namelist() if n.endswith("/resources.assets")]
        asset=next((n for n in matches if n.endswith(args.asset)),None) or (matches[0] if matches else None)
        if not asset: raise SystemExit("resources.assets not found")
        env=UnityPy.load(zf.read(asset))
    objects={int(o.path_id):o for o in env.objects}
    meta={pid:{"path_id":pid,"type":getattr(getattr(o,"type",None),"name","Unknown"),"name":safe_name(o)}
          for pid,o in objects.items()}
    def resolve(p):
        pid=p['path_id']; return {**p,**meta.get(pid,{"type":"external_or_unindexed","name":""})}
    rows=[]; seen=set()
    for go in objects.values():
        if getattr(getattr(go,"type",None),"name","")!="GameObject": continue
        go_name=safe_name(go)
        if not any(t in go_name.lower() for t in TOKENS): continue
        try: gd=go.read()
        except Exception: continue
        components=[]
        for p in ptr_fields(getattr(gd,"m_Component",[]),"m_Component"):
            comp=objects.get(p['path_id'])
            if comp is None: continue
            ctype=meta[p['path_id']]["type"]
            if ctype!="MonoBehaviour": continue
            try: data=comp.read()
            except Exception as exc:
                components.append({"component":meta[p['path_id']],"read_error":str(exc)[:250]}); continue
            refs=[resolve(x) for x in ptr_fields(data)]
            script_ref=next((x for x in refs if x.get("field","").endswith("m_Script")),None)
            script=meta.get(script_ref['path_id'],{}) if script_ref else {}
            row={"owner_gameobject":meta[int(go.path_id)],"component":meta[p["path_id]],
                 "script":script,"script_pointer":script_ref,"references":refs}
            try:
                attrs=vars(data)
                row["serialized_field_names"]=sorted(k for k in attrs if not k.startswith("_"))
            except Exception: row["serialized_field_names"]=[]
            components.append(row); seen.add(int(comp.path_id))
        if components:
            rows.append({"gameobject":meta[int(go.path_id)],"monobehaviours":components})
    named=[]
    for obj in objects.values():
        if getattr(getattr(obj,"type",None),"name","")!="MonoBehaviour": continue
        nm=meta[int(obj.path_id)]["name"].lower()
        if not any(k in nm for k in SKINS): continue
        try: data=obj.read(); refs=[resolve(x) for x in ptr_fields(data)]
        except Exception as exc: refs=[{"read_error":str(exc)[:250]}]
        named.append({"component":meta[int(obj.path_id)],"references":refs})
    result={
      "tool":"CounterFlame Skin MonoBehaviour Link Audit","schema_version":1,
      "ipa_asset_path":asset,"target_gameobject_count":len(rows),
      "target_monobehaviour_count":sum(len(x["monobehaviours"]) for x in rows),
      "skin_named_monobehaviour_count":len(named),
      "target_gameobjects":rows,"skin_named_components":named,
      "limitations":[
        "Read-only serialized component and MonoScript reference audit.",
        "IL2CPP method bodies and runtime equip flow are not reconstructed by this report.",
        "Missing custom typetrees may hide serialized fields.",
        "No IPA modification, runtime injection, server inventory change, or anti-cheat bypass."
      ]}
    path=out/"skin_monobehaviour_links.json"
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"target_gameobjects":len(rows),"target_monobehaviours":result["target_monobehaviour_count"],
                      "skin_named_components":len(named),"report":str(path)},ensure_ascii=False))
if __name__=="__main__": main()
