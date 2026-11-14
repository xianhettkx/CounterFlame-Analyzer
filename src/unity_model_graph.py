#!/usr/bin/env python3
"""Read-only Unity GameObject/component/mesh/material reference graph."""
from __future__ import annotations
import argparse, json, zipfile
from pathlib import Path
from typing import Any

TARGET_RE = ("butterfly","flip","ak47","awp","deagle","m4a4","m4a1","specialist","glove_ct","dragonlore","neonrevolution","emperor","codered")
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
    # Join renderer references by their owning GameObject to prove Mesh-to-Material assignments.
    go_by_id={pid:info for pid,info in meta.items() if info["type"]=="GameObject"}
    assignment_groups={}
    materials_by_gameobject={}
    for component in renderers:
        refs=component["references"]
        go_ref=next((r for r in refs if r.get("field")=="m_GameObject"),None)
        if not go_ref: continue
        mats=[r.get("name","") for r in refs if r.get("type")=="Material" and "m_Materials" in r.get("field","")]
        if mats:
            materials_by_gameobject.setdefault(go_ref["path_id"],[])
            for mat in mats:
                if mat not in materials_by_gameobject[go_ref["path_id"]]:
                    materials_by_gameobject[go_ref["path_id"]].append(mat)
    for component in renderers:
        refs=component["references"]
        go_ref=next((r for r in refs if r.get("field")=="m_GameObject"),None)
        mesh_ref=next((r for r in refs if r.get("field")=="m_Mesh" and r.get("type")=="Mesh"),None)
        if not go_ref or not mesh_ref: continue
        go_info=go_by_id.get(go_ref["path_id"],{"name":go_ref.get("name",""),"path_id":go_ref["path_id"]})
        go_name=go_info.get("name","")
        mesh_name=mesh_ref.get("name","")
        if not any(t in (go_name+" "+mesh_name).lower() for t in TARGET_RE): continue
        materials=[r.get("name","") for r in refs if r.get("type")=="Material" and "m_Materials" in r.get("field","")]
        if not materials:
            materials=materials_by_gameobject.get(go_ref["path_id"],[])
        key=(go_name,component["object"]["type"],mesh_name,tuple(materials))
        item=assignment_groups.setdefault(key,{"gameobject_name":go_name,"component_type":component["object"]["type"],"mesh_name":mesh_name,"mesh_path_id":mesh_ref["path_id"],"material_names":materials,"gameobject_path_ids":[],"component_path_ids":[]})
        item["gameobject_path_ids"].append(go_ref["path_id"])
        item["component_path_ids"].append(component["object"]["path_id"])
    mesh_assignments=[]
    for item in assignment_groups.values():
        item["instance_count"]=len(item["component_path_ids"])
        mesh_assignments.append(item)
    # Inspect skin-specific material bundles and record their texture pointer targets.
    skin_material_bundles=[]
    with zipfile.ZipFile(a.ipa,"r") as zf:
        skin_bundle_paths=[n for n in zf.namelist() if n.lower().endswith(".bundle") and any(k in n.lower() for k in skin_keys)]
        for bundle_path in skin_bundle_paths:
            try:
                benv=UnityPy.load(zf.read(bundle_path))
                bmap={int(o.path_id):o for o in benv.objects}
                for material_obj in benv.objects:
                    if getattr(getattr(material_obj,"type",None),"name","")!="Material": continue
                    try:
                        material_data=material_obj.read()
                        refs=[]
                        externals=getattr(getattr(material_obj,"assets_file",None),"externals",[]) or []
                        tex_envs=getattr(getattr(material_data,"m_SavedProperties",None),"m_TexEnvs",[]) or []
                        tex_property_names=[]
                        for entry in tex_envs:
                            try: tex_property_names.append(str(entry[0]))
                            except Exception: tex_property_names.append("")
                        for ptr in ptr_fields(material_data):
                            fid=ptr["file_id"]
                            target={"field":ptr["field"],"file_id":fid,"path_id":ptr["path_id"]}
                            prop_match=__import__("re").search(r"m_TexEnvs\\[(\\d+)\\]",ptr["field"])
                            if prop_match:
                                prop_index=int(prop_match.group(1))
                                if prop_index<len(tex_property_names):
                                    target["texture_property"]=tex_property_names[prop_index]
                            if fid==0 and ptr["path_id"] in bmap:
                                target["target_type"]=getattr(getattr(bmap[ptr["path_id"]],"type",None),"name","Unknown")
                                try: target["target_name"]=str(bmap[ptr["path_id"]].peek_name() or "")
                                except Exception: target["target_name"]=""
                            elif fid>0 and fid-1<len(externals):
                                target["external_file"]=str(getattr(externals[fid-1],"path","") or "")
                            refs.append(target)
                        skin_material_bundles.append({"bundle_path":bundle_path,"material_name":str(getattr(material_data,"m_Name","") or ""),"texture_property_count":len(tex_property_names),"references":refs})
                    except Exception as exc:
                        skin_material_bundles.append({"bundle_path":bundle_path,"material_path_id":int(material_obj.path_id),"material_read_error":f"{type(exc).__name__}: {exc}"[:300]})
            except Exception as exc:
                skin_material_bundles.append({"bundle_path":bundle_path,"bundle_read_error":f"{type(exc).__name__}: {exc}"[:300]})
    report={"tool":"CounterFlame Unity Model Graph","schema_version":2,"asset_path":asset_path,"serialized_object_count":len(obj_map),"target_gameobject_count":len(graph),"renderer_component_count":len(renderers),"mesh_assignment_group_count":len(mesh_assignments),"mesh_assignments":mesh_assignments,"skin_material_bundle_count":len(skin_material_bundles),"skin_material_bundles":skin_material_bundles,"target_gameobjects":graph,"skin_metadata_objects":skin_metadata,"renderer_components":renderers,"limitations":["Static serialized reference graph only; does not establish runtime loading or equip behavior.","Skin-specific MonoBehaviour typetrees may require matching IL2CPP type metadata.","No IPA contents are modified."]}
    (out/"unity_model_graph.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"[OK] Model graph: {asset_path}")
    print(f"Serialized objects: {len(obj_map)}")
    print(f"Target GameObjects: {len(graph)}")
    print(f"Renderer/filter/animator components: {len(renderers)}")
    print(f"Report: {out/'unity_model_graph.json'}")
    return 0
if __name__=="__main__": raise SystemExit(main())
