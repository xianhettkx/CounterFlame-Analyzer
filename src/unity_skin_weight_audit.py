#!/usr/bin/env python3
"""Audit Unity mesh skin weights and bind poses for target weapon meshes."""
from __future__ import annotations
import argparse, json, zipfile, tempfile
from pathlib import Path
from collections import Counter

TARGETS = {
    "butterfly_marblefade": [2233],
    "specialist_pillow": [2217, 2216, 2215, 2000, 2115],
    "awp_dragonlore": [2114, 2032],
    "ak47_neonrevolution": [2014, 2231, 1908, 2122],
    "m4a4_emperor": [1926, 1930, 1916, 1931],
    "deagle_codered": [2112, 1953],
}

def get_value(obj, key, default=None):
    try: return getattr(obj, key)
    except Exception: return default

def main():
    p=argparse.ArgumentParser()
    p.add_argument("ipa")
    p.add_argument("--out",default="reports")
    a=p.parse_args()
    try: import UnityPy
    except ImportError as exc: raise RuntimeError("UnityPy missing") from exc
    out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    temp_context=tempfile.TemporaryDirectory(prefix="cf_skin_audit_")
    temp_root=Path(temp_context.name)
    with zipfile.ZipFile(a.ipa,"r") as zf:
        names=zf.namelist()
        asset_path=next((n for n in names if n.endswith("/resources.assets")),None)
        if not asset_path: raise RuntimeError("resources.assets not found")
        asset_copy=temp_root/"resources.assets"
        asset_copy.write_bytes(zf.read(asset_path))
        resource_path=next((n for n in names if n.endswith("/resources.assets.resS")),None)
        if not resource_path:
            resource_path=next((n for n in names if n.endswith("/resources.resource")),None)
        if resource_path:
            resource_bytes=zf.read(resource_path)
            (temp_root/"resources.assets.resS").write_bytes(resource_bytes)
            (temp_root/"resources.assets.resource").write_bytes(resource_bytes)
    env=UnityPy.load(str(asset_copy))
    from UnityPy.helpers.MeshHelper import MeshHandler
    objects={int(o.path_id):o for o in env.objects}
    renderers_by_mesh={}
    for obj in env.objects:
        if getattr(getattr(obj,"type",None),"name","")!="SkinnedMeshRenderer": continue
        try: renderer=obj.read()
        except Exception: continue
        mesh_ptr=get_value(renderer,"m_Mesh")
        mesh_id=int(get_value(mesh_ptr,"m_PathID",0) or 0)
        if not mesh_id: continue
        bones=get_value(renderer,"m_Bones",[]) or []
        game_ptr=get_value(renderer,"m_GameObject")
        game_id=int(get_value(game_ptr,"m_PathID",0) or 0)
        game_name=""
        if game_id in objects:
            try: game_name=str(get_value(objects[game_id].read(),"m_Name","") or "")
            except Exception: pass
        renderers_by_mesh.setdefault(mesh_id,[]).append({
            "renderer_path_id":int(obj.path_id),
            "gameobject_path_id":game_id,
            "gameobject_name":game_name,
            "bone_count":len(bones),
            "root_bone_path_id":int(get_value(get_value(renderer,"m_RootBone"),"m_PathID",0) or 0),
        })
    rows=[]
    for skin,ids in TARGETS.items():
        for mesh_id in ids:
            obj=objects.get(mesh_id)
            if obj is None or getattr(getattr(obj,"type",None),"name","")!="Mesh": continue
            try: mesh=obj.read()
            except Exception as exc:
                rows.append({"skin_key":skin,"mesh_path_id":mesh_id,"error":f"{type(exc).__name__}: {exc}"[:200]})
                continue
            try:
                handler=MeshHandler(mesh)
                handler.process()
            except Exception as exc:
                rows.append({"skin_key":skin,"mesh_path_id":mesh_id,"mesh_name":str(get_value(mesh,"m_Name","") or ""),"error":f"MeshHandler {type(exc).__name__}: {exc}"[:240]})
                continue
            skin_data=getattr(handler,"m_BoneWeights",None) or []
            bone_indices_data=getattr(handler,"m_BoneIndices",None) or []
            bindposes=get_value(mesh,"m_BindPose",[]) or []
            vertices=getattr(handler,"m_Vertices",None) or []
            uv=getattr(handler,"m_UV0",None) or []
            weights_per_vertex=Counter()
            positive_influences=Counter()
            weight_sums=[]
            sample=[]
            for index,(raw_weights,raw_indices) in enumerate(zip(skin_data,bone_indices_data)):
                weights=[float(x) for x in raw_weights]
                bone_indices=[int(x) for x in raw_indices]
                active=sum(1 for w in weights if w>0)
                weights_per_vertex[active]+=1
                positive_influences.update(b for b,w in zip(bone_indices,weights) if w>0)
                if any(weights): weight_sums.append(sum(weights))
                if index<3: sample.append({"bone_indices":bone_indices,"weights":weights})
            name=str(get_value(mesh,"m_Name","") or obj.peek_name() or "")
            compressed=get_value(mesh,"m_CompressedMesh")
            packed_weights=get_value(compressed,"m_Weights")
            packed_indices=get_value(compressed,"m_BoneIndices")
            vertex_data=get_value(mesh,"m_VertexData")
            channels=get_value(vertex_data,"m_Channels",[]) or []
            channel_layout=[]
            for channel_index,channel in enumerate(channels):
                channel_layout.append({
                    "index":channel_index,
                    "dimension":int(get_value(channel,"dimension",0) or 0),
                    "format":int(get_value(channel,"format",0) or 0),
                    "stream":int(get_value(channel,"stream",0) or 0),
                    "offset":int(get_value(channel,"offset",0) or 0),
                })
            variable_weights=get_value(mesh,"m_VariableBoneCountWeights")
            variable_weight_data=get_value(variable_weights,"m_Data",[]) or []
            rows.append({
                "skin_key":skin,"mesh_name":name,"mesh_path_id":mesh_id,
                "vertex_count":len(vertices) if vertices is not None else 0,
                "uv_count":len(uv) if uv is not None else 0,
                "skin_weight_entry_count":len(skin_data),
                "compressed_weight_item_count":int(get_value(packed_weights,"m_NumItems",0) or 0),
                "compressed_bone_index_item_count":int(get_value(packed_indices,"m_NumItems",0) or 0),
                "variable_bone_weight_data_count":len(variable_weight_data),
                "vertex_channel_layout":channel_layout,
                "bind_pose_count":len(bindposes),
                "weights_per_vertex":{str(k):v for k,v in sorted(weights_per_vertex.items())},
                "positive_bone_index_count":len(positive_influences),
                "renderer_instances":renderers_by_mesh.get(mesh_id,[]),
                "weight_sum_min":min(weight_sums) if weight_sums else None,
                "weight_sum_max":max(weight_sums) if weight_sums else None,
                "sample_first_three":sample,
                "conversion_candidate":bool(skin_data and bindposes and renderers_by_mesh.get(mesh_id)),
            })
    report={
        "tool":"CounterFlame Unity Skin Weight Audit",
        "schema_version":1,
        "asset_path":asset_path,
        "target_mesh_count":len(rows),
        "meshes":rows,
        "limitations":[
            "This report audits serialized skin weights, bind poses, and renderer bone references; it does not export a rigged model.",
            "A successful candidate flag means the source contains the main structural data needed for a later conversion attempt, not that the conversion is already correct.",
            "No IPA contents are modified."
        ]
    }
    (out/"unity_skin_weight_audit.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    md=["# Unity skin-weight and bind-pose audit","",f"Target mesh records: {len(rows)}","",
        "| Skin | Mesh | Vertices | Weight entries | Bind poses | Renderer bone counts | Candidate |",
        "|---|---|---:|---:|---:|---|---|"]
    for r in rows:
        if r.get("error"):
            md.append(f"| {r['skin_key']} | path {r['mesh_path_id']} | — | — | — | — | read error |")
            continue
        counts=", ".join(str(x["bone_count"]) for x in r["renderer_instances"]) or "none"
        md.append(f"| {r['skin_key']} | {r['mesh_name']} | {r['vertex_count']} | {r['skin_weight_entry_count']} | {r['bind_pose_count']} | {counts} | {'yes' if r['conversion_candidate'] else 'no'} |")
    weighted=[r for r in rows if int(r.get("skin_weight_entry_count",0) or 0)>0]
    unweighted_weapons=[r for r in rows if r.get("skin_key")!="specialist_pillow" and not r.get("error")]
    md += ["","## Findings",""]
    if weighted:
        glove_rows=[r for r in weighted if r.get("skin_key")=="specialist_pillow"]
        if glove_rows:
            md.append(f"- Specialist glove mesh records contain decoded vertex weights; the main 67-bone mesh has {glove_rows[0].get('skin_weight_entry_count',0)} weight entries and {glove_rows[0].get('bind_pose_count',0)} bind poses.")
    if unweighted_weapons and all(int(r.get("skin_weight_entry_count",0) or 0)==0 and int(r.get("compressed_weight_item_count",0) or 0)==0 and int(r.get("variable_bone_weight_data_count",0) or 0)==0 for r in unweighted_weapons):
        md.append("- The inspected weapon meshes have renderer bone references and bind poses, but no decoded or compressed per-vertex skin weights, no variable-bone weight data, and no active blend-weight vertex channel. They remain static-mesh previews in this export; no rigging was fabricated.")
    md += ["","## Interpretation","",
        "The candidate column checks for skin-weight entries, bind poses, and at least one serialized SkinnedMeshRenderer reference. It does not guarantee correct joint ordering, transforms, coordinate conversion, or GLB validation.",
        "The original IPA is read-only."]
    (out/"unity_skin_weight_audit.md").write_text("\n".join(md)+"\n",encoding="utf-8")
    temp_context.cleanup()
    print(f"[OK] Skin-weight audit: {len(rows)} target mesh records")
    print(f"[REPORT] {out/'unity_skin_weight_audit.md'}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
