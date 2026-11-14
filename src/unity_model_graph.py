#!/usr/bin/env python3
"""Read-only Unity GameObject/component/mesh/material reference graph."""
from __future__ import annotations
import argparse, json, zipfile
from pathlib import Path
from typing import Any

TARGET_RE = ("butterfly","ak47","awp","deagle","m4a4","m4a1","specialist","glove_ct","dragonlore","neonrevolution","emperor","codered")
INTERESTING_TYPES = {"GameObject","Transform","MeshFilter","MeshRenderer","SkinnedMeshRenderer","Animator","Mesh","Material","AnimationClip","Avatar","AnimatorController"}

def ptr_fields(value: Any, prefix: str = "", depth: int = 0):
    if depth > 7 or value is None or isinstance(value,(str,bytes,int,float,bool)):
        return
    if (hasattr(value,"m_PathID") and hasattr(value,"m_FileID")) or (hasattr(value,"path_id") and hasattr(value,"file_id")):
        try:
            pid=int(getattr(value,"m_PathID",getattr(value,"path_id",0)))
            fid=int(getattr(value,"m_FileID",getattr(value,"file_id",0)))
            if pid:
                yield {"field":prefix,"file_id":fid,"path_id":pid}
        except Exception:
            pass
        return
    if isinstance(value,(list,tuple)):
        for i,item in enumerate(value):
            yield from ptr_fields(item,f"{prefix}[{i}]",depth+1)
        return
    if isinstance(value,dict):
        for k,item in value.items():
            yield from ptr_fields(item,f"{prefix}.{k}",depth+1)
        return
    try: attrs=vars(value)
    except Exception:
        attrs={}
        for attr in getattr(type(value),"__attrs_attrs__",()):
            key=getattr(attr,"name",None)
            if key:
                try: attrs[key]=getattr(value,key)
                except Exception: pass
        if not attrs:
            return
    for key,item in attrs.items():
        if key.startswith("_"): continue
        yield from ptr_fields(item,f"{prefix}.{key}" if prefix else key,depth+1)

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("ipa"); p.add_argument("--out",default="reports"); p.add_argument("--asset",default="Payload/CounterFlame.app/Data/resources.assets"); a=p.parse_args()
    try: import UnityPy
    except ImportError as exc: raise RuntimeError("UnityPy missing") from exc
    out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(a.ipa,"r") as zf:
        names=zf.namelist()
        asset_path=next((n for n in names if n.endswith("/resources.assets")),None)
        if not asset_path: raise RuntimeError("resources.assets not found in IPA")
        env=UnityPy.load(zf.read(asset_path))
    obj_map={int(o.path_id):o for o in env.objects}
    meta={}
    for pid,obj in obj_map.items():
        typ=getattr(getattr(obj,"type",None),"name","Unknown")
        try: name=str(obj.peek_name() or "")
        except Exception: name=""
        meta[pid]={"path_id":pid,"type":typ,"name":name}
    target_gameobjects=[o for o in obj_map.values() if getattr(getattr(o,"type",None),"name","")=="GameObject" and any(t in meta[int(o.path_id)]["name"].lower() for t in TARGET_RE)]
    graph=[]
    def resolve(ptr):
        pid=ptr["path_id"]
        info=meta.get(pid,{"path_id":pid,"type":"external_or_unindexed","name":""})
        return {**ptr,**info}
    for go in target_gameobjects:
        pid=int(go.path_id); info=meta[pid]
        try: data=go.read()
        except Exception as exc:
            graph.append({"gameobject":info,"error":f"{type(exc).__name__}: {exc}"[:200]}); continue
        components=[]
        for ptr in ptr_fields(getattr(data,"m_Component",[]),"m_Component"):
            resolved=resolve(ptr); component=obj_map.get(ptr["path_id"])
            refs=[]
            if component is not None:
                ctype=meta[ptr["path_id"]]["type"]
                if ctype in INTERESTING_TYPES:
                    try: cdata=component.read(); refs=[resolve(x) for x in ptr_fields(cdata)]
                    except Exception: pass
            components.append({"component":resolved,"references":refs})
        graph.append({"gameobject":info,"components":components})
    skin_metadata=[]
    skin_keys=("butterfly_marblefade","specialist_pillow","awp_dragonlore","ak47_neonrevolution","m4a4_emperor","deagle_codered")
    for obj in obj_map.values():
        typ=getattr(getattr(obj,"type",None),"name","")
        if typ not in {"MonoBehaviour","Material"}: continue
        info=meta[int(obj.path_id)]
        if not any(k in info["name"].lower() for k in skin_keys): continue
        try: data=obj.read(); refs=[resolve(x) for x in ptr_fields(data)]
        except Exception as exc: refs=[{"error":f"{type(exc).__name__}: {exc}"[:200]}]
        skin_metadata.append({"object":info,"references":refs})
    # Also capture direct references on renderers/filters/animators, including those on non-target-named objects.
    renderers=[]
    for obj in obj_map.values():
        typ=getattr(getattr(obj,"type",None),"name","")
        if typ not in {"MeshFilter","MeshRenderer","SkinnedMeshRenderer","Animator","Transform"}: continue
        try: data=obj.read()
        except Exception: continue
        refs=[resolve(x) for x in ptr_fields(data)]
        if typ in {"MeshFilter","MeshRenderer","SkinnedMeshRenderer","Animator"} or any(x["type"]=="Mesh" for x in refs):
            owner=meta[int(obj.path_id)]
            renderers.append({"object":owner,"references":refs})
    report={"tool":"CounterFlame Unity Model Graph","schema_version":1,"asset_path":asset_path,"serialized_object_count":len(obj_map),"target_gameobject_count":len(graph),"renderer_component_count":len(renderers),"target_gameobjects":graph,"skin_metadata_objects":skin_metadata,"renderer_components":renderers,"limitations":["Static serialized reference graph only; does not establish runtime loading or equip behavior.","Only references resolvable within resources.assets are expanded.","No IPA contents are modified."]}
    (out/"unity_model_graph.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"[OK] Model graph: {asset_path}")
    print(f"Serialized objects: {len(obj_map)}")
    print(f"Target GameObjects: {len(graph)}")
    print(f"Renderer/filter/animator components: {len(renderers)}")
    print(f"Report: {out/'unity_model_graph.json'}")
    return 0
if __name__=="__main__": raise SystemExit(main())
