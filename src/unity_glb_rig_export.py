#!/usr/bin/env python3
"""Export the weighted Specialist glove mesh as a minimal rigged GLB preview."""
from __future__ import annotations
import argparse, json, math, struct, tempfile, zipfile
from pathlib import Path

MESH_ID = 2217
SKIN_KEY = "specialist_pillow"

def val(obj, key, default=None):
    try: return getattr(obj, key)
    except Exception: return default

def vec(obj, keys, default):
    if obj is None: return list(default)
    try: return [float(getattr(obj,k)) for k in keys]
    except Exception: return list(default)

class GLBBuilder:
    def __init__(self):
        self.binary=bytearray()
        self.views=[]
        self.accessors=[]
    def align(self):
        while len(self.binary)%4: self.binary.append(0)
    def view(self, data, target=None):
        self.align()
        offset=len(self.binary)
        self.binary.extend(data)
        item={"buffer":0,"byteOffset":offset,"byteLength":len(data)}
        if target is not None: item["target"]=target
        self.views.append(item)
        return len(self.views)-1
    def accessor(self, data, component_type, count, kind, target=None, minimum=None, maximum=None):
        view=self.view(data,target)
        item={"bufferView":view,"componentType":component_type,"count":count,"type":kind}
        if minimum is not None: item["min"]=minimum
        if maximum is not None: item["max"]=maximum
        self.accessors.append(item)
        return len(self.accessors)-1
    def write(self, path, doc):
        self.align()
        doc["buffers"]=[{"byteLength":len(self.binary)}]
        doc["bufferViews"]=self.views
        doc["accessors"]=self.accessors
        raw=json.dumps(doc,separators=(",",":"),ensure_ascii=False).encode("utf-8")
        while len(raw)%4: raw+=b" "
        binary=bytes(self.binary)
        while len(binary)%4: binary+=b"\0"
        total=12+8+len(raw)+8+len(binary)
        with open(path,"wb") as f:
            f.write(struct.pack("<4sII","glTF",2,total))
            f.write(struct.pack("<I4s",len(raw),b"JSON")); f.write(raw)
            f.write(struct.pack("<I4s",len(binary),b"BIN\0")); f.write(binary)

def floats(values):
    return struct.pack("<"+"f"*len(values),*values)

def uints(values):
    return struct.pack("<"+"I"*len(values),*values)

def ushorts(values):
    return struct.pack("<"+"H"*len(values),*values)

def export(ipa:Path, reports:Path, out:Path):
    import UnityPy
    from UnityPy.helpers.MeshHelper import MeshHandler
    out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(ipa,"r") as zf:
        names=zf.namelist()
        asset_path=next((n for n in names if n.endswith("/resources.assets")),None)
        if not asset_path: raise RuntimeError("resources.assets not found")
        temp=tempfile.TemporaryDirectory(prefix="cf_glb_")
        root=Path(temp.name)
        asset_copy=root/"resources.assets"
        asset_copy.write_bytes(zf.read(asset_path))
        resource_path=next((n for n in names if n.endswith("/resources.assets.resS")),None)
        if not resource_path: resource_path=next((n for n in names if n.endswith("/resources.resource")),None)
        if resource_path:
            data=zf.read(resource_path)
            (root/"resources.assets.resS").write_bytes(data)
            (root/"resources.assets.resource").write_bytes(data)
    env=UnityPy.load(str(asset_copy))
    objects={int(o.path_id):o for o in env.objects}
    mesh_obj=objects.get(MESH_ID)
    if mesh_obj is None or getattr(getattr(mesh_obj,"type",None),"name","")!="Mesh":
        raise RuntimeError(f"target Mesh path ID {MESH_ID} not found")
    mesh=mesh_obj.read()
    handler=MeshHandler(mesh)
    handler.process()
    vertices=getattr(handler,"m_Vertices",None) or []
    normals=getattr(handler,"m_Normals",None) or []
    uvs=getattr(handler,"m_UV0",None) or []
    weights=getattr(handler,"m_BoneWeights",None) or []
    indices=getattr(handler,"m_BoneIndices",None) or []
    if not vertices or not weights or len(vertices)!=len(weights) or len(weights)!=len(indices):
        raise RuntimeError(f"mesh is not fully weighted: vertices={len(vertices)}, weights={len(weights)}, indices={len(indices)}")
    bindposes=val(mesh,"m_BindPose",[]) or []
    renderer_obj=None
    renderer_data=None
    selected_material_names=[]
    for obj in env.objects:
        if getattr(getattr(obj,"type",None),"name","")!="SkinnedMeshRenderer": continue
        try: data=obj.read()
        except Exception: continue
        ptr=val(data,"m_Mesh")
        if int(val(ptr,"m_PathID",0) or 0)!=MESH_ID: continue
        bone_ptrs=val(data,"m_Bones",[]) or []
        if len(bone_ptrs)!=len(bindposes): continue
        mats=val(data,"m_Materials",[]) or []
        names_for_renderer=[]
        for mp in mats:
            mid=int(val(mp,"m_PathID",0) or 0)
            material=objects.get(mid)
            try: names_for_renderer.append(str(val(material.read(),"m_Name","") or "") if material else "")
            except Exception: names_for_renderer.append("")
        if any("glove_specialist" in n.lower() for n in names_for_renderer):
            renderer_obj=obj; renderer_data=data; selected_material_names=names_for_renderer
            break
    if renderer_obj is None:
        raise RuntimeError("No renderer found with a bone count matching bind poses and glove material slots")
    bone_ptrs=val(renderer_data,"m_Bones",[]) or []
    bone_ids=[int(val(p,"m_PathID",0) or 0) for p in bone_ptrs]
    if len(bone_ids)!=len(bindposes) or any(pid not in objects for pid in bone_ids):
        raise RuntimeError("renderer bone array and bind-pose array do not align")
    max_joint=max((int(i) for row,wrow in zip(indices,weights) for i,w in zip(row,wrow) if float(w)>0),default=0)
    if max_joint>=len(bone_ids): raise RuntimeError(f"bone index {max_joint} exceeds renderer bone count {len(bone_ids)}")
    if not normals or len(normals)!=len(vertices): raise RuntimeError("mesh normals missing or count mismatch")
    if not uvs or len(uvs)!=len(vertices): raise RuntimeError("mesh UV0 missing or count mismatch")
    triangles=handler.get_triangles()
    submesh_count=len(triangles)
    if not submesh_count: raise RuntimeError("mesh has no triangle submeshes")
    # Keep each original submesh separate so bare-arm and glove material slots remain distinct.
    submesh_material_names=selected_material_names[:submesh_count]
    if len(submesh_material_names)<submesh_count:
        submesh_material_names += [""]*(submesh_count-len(submesh_material_names))
    # Build all required transform ancestors, preserving renderer.m_Bones order.
    transform_data={}
    parent_map={}
    pending=list(bone_ids)
    while pending:
        pid=pending.pop()
        if pid in transform_data: continue
        obj=objects.get(pid)
        if obj is None or getattr(getattr(obj,"type",None),"name","")!="Transform":
            raise RuntimeError(f"bone Transform {pid} is missing")
        tr=obj.read()
        transform_data[pid]=tr
        parent=val(tr,"m_Father")
        parent_id=int(val(parent,"m_PathID",0) or 0)
        parent_map[pid]=parent_id
        if parent_id and parent_id not in transform_data: pending.append(parent_id)
    # Add a mirror root to convert Unity's left-handed X axis to glTF's right-handed space.
    node_list=[{"name":"UnityToGLTF_XMirror","scale":[-1.0,1.0,1.0],"children":[]}]
    node_index={}
    for pid,tr in transform_data.items():
        game_ptr=val(tr,"m_GameObject")
        game_id=int(val(game_ptr,"m_PathID",0) or 0)
        game_name=""
        if game_id in objects:
            try: game_name=str(val(objects[game_id].read(),"m_Name","") or "")
            except Exception: pass
        node={
            "name":game_name or f"Transform_{pid}",
            "translation":vec(val(tr,"m_LocalPosition"),("x","y","z"),(0,0,0)),
            "rotation":vec(val(tr,"m_LocalRotation"),("x","y","z","w"),(0,0,0,1)),
            "scale":vec(val(tr,"m_LocalScale"),("x","y","z"),(1,1,1)),
            "children":[]
        }
        node_index[pid]=len(node_list)
        node_list.append(node)
    for pid in transform_data:
        parent_id=parent_map.get(pid,0)
        child_index=node_index[pid]
        if parent_id in node_index:
            node_list[node_index[parent_id]]["children"].append(child_index)
        else:
            node_list[0]["children"].append(child_index)
    bone_nodes=[node_index[pid] for pid in bone_ids]
    root_ptr=val(renderer_data,"m_RootBone")
    root_bone_id=int(val(root_ptr,"m_PathID",0) or 0)
    if root_bone_id not in node_index:
        raise RuntimeError("renderer root bone is not part of the resolved hierarchy")
    mesh_node_index=len(node_list)
    node_list.append({"name":"specialist_pillow_skinned_mesh","mesh":0,"skin":0})
    node_list[0]["children"].append(mesh_node_index)
    builder=GLBBuilder()
    positions=[float(c) for v in vertices for c in v]
    pos_min=[min(float(v[i]) for v in vertices) for i in range(3)]
    pos_max=[max(float(v[i]) for v in vertices) for i in range(3)]
    pos_acc=builder.accessor(floats(positions),5126,len(vertices),"VEC3",34962,pos_min,pos_max)
    normal_values=[float(c) for v in normals for c in v[:3]]
    normal_acc=builder.accessor(floats(normal_values),5126,len(normals),"VEC3",34962)
    uv_values=[float(c) for v in uvs for c in v[:2]]
    uv_acc=builder.accessor(floats(uv_values),5126,len(uvs),"VEC2",34962)
    joint_values=[]
    weight_values=[]
    weight_sums=[]
    for row,weight_row in zip(indices,weights):
        js=[int(x) for x in row]
        ws=[max(0.0,float(x)) for x in weight_row]
        total=sum(ws)
        if total>0: ws=[x/total for x in ws]
        joint_values.extend(js); weight_values.extend(ws); weight_sums.append(sum(ws))
    joint_acc=builder.accessor(ushorts(joint_values),5123,len(vertices),"VEC4",34962)
    weight_acc=builder.accessor(floats(weight_values),5126,len(vertices),"VEC4",34962)
    ibm_values=[]
    for matrix in bindposes:
        # Unity serializes Matrix4x4 as e00..e33; glTF MAT4 values are column-major.
        for col in range(4):
            for row in range(4):
                ibm_values.append(float(getattr(matrix,f"e{row}{col}")))
    ibm_acc=builder.accessor(floats(ibm_values),5126,len(bindposes),"MAT4")
    image_name="glove_specialist_left"
    manifest_path=out/"target_asset_export_manifest.json"
    manifest=json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    tex_entry=next((x for x in manifest.get("texture_exports",[]) if x.get("texture_name")==image_name and x.get("file")),None)
    if not tex_entry: raise RuntimeError("glove albedo texture not found in export manifest")
    texture_path=out/tex_entry["file"]
    image_bytes=texture_path.read_bytes()
    image_view=builder.view(image_bytes)
    # One primitive per Unity submesh, with skin albedo applied only to glove material slots.
    materials=[]
    material_index_by_name={}
    texture_used=False
    primitives=[]
    for submesh_index,submesh_tris in enumerate(triangles):
        flat=[]
        for tri in submesh_tris:
            if len(tri)==3:
                a,b,c=[int(x) for x in tri]
                flat.extend([c,b,a])  # reverse winding for the mirrored X root
        if not flat: continue
        indices_acc=builder.accessor(uints(flat),5125,len(flat),"SCALAR",34963,min(flat),max(flat))
        mat_name=submesh_material_names[submesh_index] if submesh_index<len(submesh_material_names) else ""
        use_skin="glove" in mat_name.lower()
        if use_skin: texture_used=True
        key=mat_name or f"submesh_{submesh_index}"
        if key not in material_index_by_name:
            material={
                "name":key,
                "pbrMetallicRoughness":{
                    "baseColorFactor":[1.0,1.0,1.0,1.0] if use_skin else [0.72,0.72,0.72,1.0],
                    "metallicFactor":0.0,
                    "roughnessFactor":0.82
                }
            }
            if use_skin: material["pbrMetallicRoughness"]["baseColorTexture"]={"index":0}
            material_index_by_name[key]=len(materials)
            materials.append(material)
        primitives.append({
            "attributes":{"POSITION":pos_acc,"NORMAL":normal_acc,"TEXCOORD_0":uv_acc,"JOINTS_0":joint_acc,"WEIGHTS_0":weight_acc},
            "indices":indices_acc,"material":material_index_by_name[key],"mode":4
        })
    if not primitives: raise RuntimeError("no triangle primitives were exported")
    doc={
        "asset":{"version":"2.0","generator":"CounterFlame Analyzer"},
        "scene":0,
        "scenes":[{"nodes":[0]}],
        "nodes":node_list,
        "meshes":[{"name":"v_glove_ct_specialist","primitives":primitives}],
        "skins":[{"name":"specialist_glove_skeleton","inverseBindMatrices":ibm_acc,"joints":bone_nodes,"skeleton":node_index[root_bone_id]}],
        "materials":materials,
        "images":[{"name":image_name,"bufferView":image_view,"mimeType":"image/png"}],
        "textures":[{"sampler":0,"source":0}],
        "samplers":[{"magFilter":9729,"minFilter":9987,"wrapS":10497,"wrapT":10497}],
        "sceneExtras":{"source_mesh_path_id":MESH_ID}
    }
    if not texture_used:
        doc.pop("images",None); doc.pop("textures",None); doc.pop("samplers",None)
        doc["materials"]=[{"name":"neutral_preview","pbrMetallicRoughness":{"baseColorFactor":[0.72,0.72,0.72,1.0],"metallicFactor":0.0,"roughnessFactor":0.82}}]
        for primitive in doc["meshes"][0]["primitives"]: primitive["material"]=0
    target_dir=out/"skin_previews"/SKIN_KEY
    target_dir.mkdir(parents=True,exist_ok=True)
    glb_path=target_dir/"specialist_pillow_rigged.glb"
    builder.write(glb_path,doc)
    temp.cleanup()
    report={
        "skin_key":SKIN_KEY,
        "mesh_name":str(val(mesh,"m_Name","") or ""),
        "mesh_path_id":MESH_ID,
        "renderer_path_id":int(renderer_obj.path_id),
        "renderer_bone_count":len(bone_ids),
        "bind_pose_count":len(bindposes),
        "vertex_count":len(vertices),
        "weight_entry_count":len(weights),
        "submesh_count":submesh_count,
        "submesh_material_names":submesh_material_names,
        "bone_weight_sum_min":min(weight_sums) if weight_sums else None,
        "bone_weight_sum_max":max(weight_sums) if weight_sums else None,
        "glb_file":str(glb_path.relative_to(out)),
        "bytes":glb_path.stat().st_size,
        "limitations":["Static bind-pose GLB preview; Unity Animator clips are not embedded.","The custom glove albedo is applied to material slots whose source material name contains 'glove'; other slots use a neutral preview material.","This is a derived preview, not a replacement game bundle. The original IPA remains unchanged."]
    }
    (out/"rigged_glb_export_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    md=["# Rigged GLB preview export","",
        "A rigged GLB preview was exported for Specialist Gloves | Pillow Punchers.",
        f"- Mesh: {report['mesh_name']} (path ID {MESH_ID})",
        f"- Vertices: {len(vertices)}",
        f"- Skin-weight entries: {len(weights)}",
        f"- Renderer bones: {len(bone_ids)}",
        f"- Bind poses: {len(bindposes)}",
        f"- GLB size: {glb_path.stat().st_size} bytes",
        "",
        "This is a static bind-pose preview. The Unity animation clips are documented separately and are not embedded in this GLB.",
        "Other weapon meshes had no decoded skin weights in this pass, so no rigged GLB was fabricated for them.",
        "The IPA was not modified."]
    (out/"rigged_glb_export_report.md").write_text("\n".join(md)+"\n",encoding="utf-8")
    manifest.setdefault("rigged_glb_exports",[]).append(report)
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    archive=out/"counterflame_target_assets.zip"
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in out.rglob("*"):
            if path.is_file() and path!=archive:
                z.write(path,path.relative_to(out).as_posix())
    print(f"[OK] Rigged GLB: {glb_path} ({glb_path.stat().st_size} bytes)")
    print(f"[OK] Bones={len(bone_ids)} vertices={len(vertices)} weights={len(weights)} bindposes={len(bindposes)}")
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("ipa")
    p.add_argument("--reports",default="reports")
    p.add_argument("--out",default="reports/exported")
    a=p.parse_args()
    export(Path(a.ipa),Path(a.reports),Path(a.out))

if __name__=="__main__":
    main()
