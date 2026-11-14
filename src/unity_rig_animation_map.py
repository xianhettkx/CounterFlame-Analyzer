#!/usr/bin/env python3
"""Read-only target weapon rig, bone, AnimatorController, and AnimationClip map."""
from __future__ import annotations
import argparse, json, zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

TARGET_TERMS=("butterfly","flip","ak47","awp","deagle","m4a4","m4a1","specialist","glove_ct","knife")
GRAPH_TYPES={"AnimatorController","AnimatorStateMachine","AnimatorState","AnimatorStateTransition","BlendTree","AnimationClip"}

def ptr_fields(value:Any,prefix:str="",depth:int=0):
    if depth>8 or value is None or isinstance(value,(str,bytes,int,float,bool)): return
    if (hasattr(value,"m_PathID") and hasattr(value,"m_FileID")) or (hasattr(value,"path_id") and hasattr(value,"file_id")):
        try:
            pid=int(getattr(value,"m_PathID",getattr(value,"path_id",0)))
            fid=int(getattr(value,"m_FileID",getattr(value,"file_id",0)))
            if pid: yield {"field":prefix,"file_id":fid,"path_id":pid}
        except Exception: pass
        return
    if isinstance(value,(list,tuple)):
        for i,item in enumerate(value): yield from ptr_fields(item,f"{prefix}[{i}]",depth+1)
        return
    if isinstance(value,dict):
        for k,item in value.items(): yield from ptr_fields(item,f"{prefix}.{k}",depth+1)
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
            for key in getattr(type(value),"__slots__",()):
                if isinstance(key,str) and not key.startswith("_"):
                    try: attrs[key]=getattr(value,key)
                    except Exception: pass
        if not attrs: return
    for key,item in attrs.items():
        if not key.startswith("_"):
            yield from ptr_fields(item,f"{prefix}.{key}" if prefix else key,depth+1)

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("ipa"); p.add_argument("--out",default="reports"); a=p.parse_args()
    try: import UnityPy
    except ImportError as exc: raise RuntimeError("UnityPy missing") from exc
    out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(a.ipa,"r") as zf:
        asset_path=next((n for n in zf.namelist() if n.endswith("/resources.assets")),None)
        if not asset_path: raise RuntimeError("resources.assets not found")
        env=UnityPy.load(zf.read(asset_path))
    objects={int(o.path_id):o for o in env.objects}; meta={}
    for pid,obj in objects.items():
        typ=getattr(getattr(obj,"type",None),"name","Unknown")
        try: name=str(obj.peek_name() or "")
        except Exception: name=""
        meta[pid]={"path_id":pid,"type":typ,"name":name}
    transform_map={}
    for pid,obj in objects.items():
        if meta[pid]["type"]!="Transform": continue
        try: refs=list(ptr_fields(obj.read()))
        except Exception: refs=[]
        go=next((r for r in refs if r["field"]=="m_GameObject"),None)
        father=next((r for r in refs if r["field"]=="m_Father"),None)
        children=[r for r in refs if r["field"].startswith("m_Children[")]
        transform_map[pid]={"transform_path_id":pid,"gameobject_path_id":go["path_id"] if go else None,"gameobject_name":meta.get(go["path_id"],{}).get("name","") if go else "","father_transform_path_id":father["path_id"] if father else None,"child_transform_path_ids":[x["path_id"] for x in children]}
    # Collect target skinned meshes and their bone Transform references.
    skeleton_groups={}
    for pid,obj in objects.items():
        if meta[pid]["type"]!="SkinnedMeshRenderer": continue
        try: refs=list(ptr_fields(obj.read()))
        except Exception: continue
        mesh=next((r for r in refs if r["field"]=="m_Mesh" and r["file_id"]==0),None)
        if not mesh: continue
        mesh_info=meta.get(mesh["path_id"],{})
        mesh_name=mesh_info.get("name","")
        if not any(t in mesh_name.lower() for t in TARGET_TERMS): continue
        bone_ptrs=[r for r in refs if r["field"].startswith("m_Bones[") and r["file_id"]==0]
        root=next((r for r in refs if r["field"]=="m_RootBone" and r["file_id"]==0),None)
        bones=[]
        for b in bone_ptrs:
            tr=transform_map.get(b["path_id"],{})
            bones.append({"transform_path_id":b["path_id"],"gameobject_path_id":tr.get("gameobject_path_id"),"bone_name":tr.get("gameobject_name","")})
        root_info=transform_map.get(root["path_id"],{}) if root else {}
        key=(mesh_name,tuple(x["bone_name"] for x in bones),root_info.get("gameobject_name",""))
        item=skeleton_groups.setdefault(key,{"mesh_name":mesh_name,"mesh_path_id":mesh["path_id"],"root_bone_name":root_info.get("gameobject_name",""),"bone_count":len(bones),"bones":bones,"renderer_path_ids":[]})
        item["renderer_path_ids"].append(pid)
    skeletons=[]
    for item in skeleton_groups.values():
        item["renderer_instance_count"]=len(item["renderer_path_ids"]); skeletons.append(item)
    # Trace Animator -> Controller -> StateMachine/State/BlendTree -> AnimationClip pointers.
    controller_groups={}
    for pid,obj in objects.items():
        if meta[pid]["type"]!="Animator": continue
        try: refs=list(ptr_fields(obj.read()))
        except Exception: continue
        ctrl=next((r for r in refs if r["field"]=="m_Controller" and r["file_id"]==0),None)
        go=next((r for r in refs if r["field"]=="m_GameObject" and r["file_id"]==0),None)
        if not ctrl: continue
        ctrl_info=meta.get(ctrl["path_id"],{})
        ctrl_name=ctrl_info.get("name","")
        if not any(t in ctrl_name.lower() for t in TARGET_TERMS): continue
        key=ctrl["path_id"]
        group=controller_groups.setdefault(key,{"controller":ctrl_info,"animator_path_ids":[],"gameobjects":[]})
        group["animator_path_ids"].append(pid)
        if go: group["gameobjects"].append(meta.get(go["path_id"],{}).get("name",""))
    controller_graphs=[]
    for ctrl_id,group in controller_groups.items():
        queue=[ctrl_id]; seen=set(); nodes=[]; clips={}
        while queue:
            current=queue.pop(0)
            if current in seen or current not in objects: continue
            seen.add(current); obj=objects[current]; info=meta[current]
            if info["type"] not in GRAPH_TYPES: continue
            try: refs=list(ptr_fields(obj.read()))
            except Exception as exc:
                nodes.append({"object":info,"read_error":f"{type(exc).__name__}: {exc}"[:200]}); continue
            resolved=[]
            for ref in refs:
                target=meta.get(ref["path_id"],{"path_id":ref["path_id"],"type":"external_or_unindexed","name":""})
                resolved.append({**ref,**target})
                if ref["file_id"]==0 and target["type"] in GRAPH_TYPES and ref["path_id"] not in seen:
                    queue.append(ref["path_id"])
                if target["type"]=="AnimationClip":
                    clips[ref["path_id"]]=target
            nodes.append({"object":info,"references":resolved})
        group["animator_path_ids"]=sorted(set(group["animator_path_ids"]))
        group["gameobjects"]=sorted(set(x for x in group["gameobjects"] if x))
        group["graph_node_count"]=len(nodes)
        group["animation_clips"]=sorted(clips.values(),key=lambda x:x["name"].lower())
        group["nodes"]=nodes
        controller_graphs.append(group)
    report={"tool":"CounterFlame Rig and Animation Map","schema_version":1,"asset_path":asset_path,"serialized_object_count":len(objects),"transform_count":len(transform_map),"target_skeleton_group_count":len(skeletons),"target_skeletons":skeletons,"target_animator_controller_count":len(controller_graphs),"animator_controller_graphs":controller_graphs,"limitations":["Static serialized rig/controller graph only; does not prove runtime playback or equip behavior.","Some custom MonoBehaviour data may require IL2CPP type metadata.","No IPA contents are modified."]}
    (out/"unity_rig_animation_map.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"[OK] Rig/animation map: transforms={len(transform_map)}, skeleton groups={len(skeletons)}, controllers={len(controller_graphs)}")
    for x in controller_graphs: print(f"[ANIM] {x['controller'].get('name')} clips={len(x['animation_clips'])}")
    return 0
if __name__=="__main__": raise SystemExit(main())
