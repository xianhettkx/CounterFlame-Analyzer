#!/usr/bin/env python3
"""Export only the verified target base meshes and their material dependency textures."""
from __future__ import annotations
import argparse, json, re, zipfile, tempfile, shutil
from pathlib import Path
from typing import Any

MESH_IDS = {
    "butterfly_marblefade": [2233, 2048],
    "awp_dragonlore": [2114, 2032, 2045, 1980, 1981],
    "ak47_neonrevolution": [2014, 2122, 2231, 1908, 2043, 2127],
    "m4a4_emperor": [1926, 1930, 1916, 1931, 2062, 1978, 1979],
    "deagle_codered": [2112, 1953, 2050, 1974, 1975],
    "specialist_pillow": [2000, 2215, 2216, 2217, 2115],
}

def safe_name(value: str) -> str:
    value=re.sub(r"[^A-Za-z0-9_.-]+","_",value).strip("._")
    return value or "asset"

def run(ipa: Path, reports: Path, out: Path) -> dict[str, Any]:
    try: import UnityPy
    except ImportError as exc: raise RuntimeError("UnityPy missing") from exc
    full=json.loads((reports/"unity_full_bundle_index.json").read_text(encoding="utf-8"))
    graph=json.loads((reports/"unity_model_graph.json").read_text(encoding="utf-8"))
    material_sources={x["bundle_path"] for x in graph.get("skin_material_bundles",[]) if x.get("material_name")}
    texture_bundles={x.get("matched_bundle") for x in full.get("dependency_edges",[]) if x.get("source_bundle") in material_sources and x.get("matched_bundle")}
    texture_bundles.update(material_sources)
    out.mkdir(parents=True,exist_ok=True)
    mesh_dir=out/"target_meshes"; tex_dir=out/"target_textures"
    mesh_dir.mkdir(exist_ok=True); tex_dir.mkdir(exist_ok=True)
    manifest={"ipa_sha256":None,"mesh_exports":[],"texture_exports":[],"texture_bundle_count":len(texture_bundles),"limitations":["OBJ files contain static mesh geometry; skeletal weights, rig hierarchy, and animation clips are not represented in OBJ.","Texture files are exported as PNG previews without changing the IPA.","No IPA contents are modified or rebuilt."]}
    with zipfile.ZipFile(ipa,"r") as zf:
        names=zf.namelist()
        resources_path=next((n for n in names if n.endswith("/resources.assets")),None)
        if not resources_path: raise RuntimeError("resources.assets not found")
        # Unity stores streamed mesh vertex data beside resources.assets. The IPA names this file
        # resources.resource; provide UnityPy the conventional companion alias it requests.
        resource_path=next((n for n in names if n.endswith("/resources.assets.resS")),None)
        if not resource_path:
            resource_path=next((n for n in names if n.endswith("/resources.resource")),None)
        with tempfile.TemporaryDirectory(prefix="cf_unity_mesh_") as temp_dir:
            temp_root=Path(temp_dir)
            asset_copy=temp_root/"resources.assets"
            asset_copy.write_bytes(zf.read(resources_path))
            if resource_path:
                resource_bytes=zf.read(resource_path)
                (temp_root/"resources.assets.resS").write_bytes(resource_bytes)
                (temp_root/"resources.assets.resource").write_bytes(resource_bytes)
            env=UnityPy.load(str(asset_copy))
            objects={int(o.path_id):o for o in env.objects}
            seen=set()
            for skin,ids in MESH_IDS.items():
                for pid in ids:
                    if pid in seen or pid not in objects: continue
                    seen.add(pid); obj=objects[pid]
                    if getattr(getattr(obj,"type",None),"name","")!="Mesh": continue
                    mesh=obj.read(); name=str(getattr(mesh,"m_Name","") or obj.peek_name() or f"mesh_{pid}")
                    filename=f"{safe_name(skin)}__{safe_name(name)}__{pid}.obj"
                    target=mesh_dir/filename
                    target.write_text(mesh.export(),encoding="utf-8",newline="")
                    manifest["mesh_exports"].append({"skin_key":skin,"path_id":pid,"mesh_name":name,"file":str(Path("target_meshes")/filename),"bytes":target.stat().st_size})
        for index,bundle_path in enumerate(sorted(texture_bundles),1):
            if bundle_path not in zf.namelist(): continue
            try: benv=UnityPy.load(zf.read(bundle_path))
            except Exception as exc:
                manifest["texture_exports"].append({"bundle_path":bundle_path,"error":f"{type(exc).__name__}: {exc}"[:200]}); continue
            skin=next((k for k in MESH_IDS if k in bundle_path.lower()),"shared")
            for obj in benv.objects:
                if getattr(getattr(obj,"type",None),"name","")!="Texture2D": continue
                try:
                    tex=obj.read(); name=str(getattr(tex,"m_Name","") or obj.peek_name() or f"texture_{obj.path_id}")
                    image=tex.image
                    folder=tex_dir/safe_name(skin); folder.mkdir(parents=True,exist_ok=True)
                    filename=f"{safe_name(name)}__{int(obj.path_id)}.png"
                    target=folder/filename
                    image.save(target,format="PNG")
                    manifest["texture_exports"].append({"skin_key":skin,"bundle_path":bundle_path,"path_id":int(obj.path_id),"texture_name":name,"width":int(getattr(tex,"m_Width",0)),"height":int(getattr(tex,"m_Height",0)),"file":str(Path("target_textures")/safe_name(skin)/filename),"bytes":target.stat().st_size})
                except Exception as exc:
                    manifest["texture_exports"].append({"bundle_path":bundle_path,"path_id":int(obj.path_id),"error":f"{type(exc).__name__}: {exc}"[:200]})
    # Build portable OBJ+MTL previews. These are static, unrigged previews; the MTL
    # binds the skin's verified main-color texture to the matching base mesh UVs.
    preview_dir=out/"skin_previews"
    preview_dir.mkdir(exist_ok=True)
    preview_specs={
        "butterfly_marblefade":{"mesh_id":2233,"texture":"butterfly_marblefade_cs2"},
        "specialist_pillow":{"mesh_id":2217,"texture":"glove_specialist_left"},
        "awp_dragonlore":{"mesh_id":2114,"texture":"awp_dragonlore_cs2"},
        "ak47_neonrevolution":{"mesh_id":2014,"texture":"ak47_neonrevolution_cs2"},
        "m4a4_emperor":{"mesh_id":1926,"texture":"m4a4_emperor_cs2"},
        "deagle_codered":{"mesh_id":2112,"texture":"deagle_codered_cs2"},
    }
    mesh_by_id={int(x["path_id"]):x for x in manifest["mesh_exports"]}
    texture_by_name={x["texture_name"]:x for x in manifest["texture_exports"] if x.get("file")}
    manifest["skin_previews"]=[]
    for skin,spec in preview_specs.items():
        mesh_entry=mesh_by_id.get(spec["mesh_id"])
        texture_entry=texture_by_name.get(spec["texture"])
        if not mesh_entry or not texture_entry:
            manifest["skin_previews"].append({"skin_key":skin,"error":"mesh or albedo texture missing","mesh_found":bool(mesh_entry),"texture_found":bool(texture_entry)})
            continue
        skin_dir=preview_dir/safe_name(skin)
        skin_dir.mkdir(exist_ok=True)
        source_obj=out/mesh_entry["file"]
        obj_name=f"{safe_name(skin)}.obj"
        mtl_name=f"{safe_name(skin)}.mtl"
        texture_source=out/texture_entry["file"]
        texture_name=f"{safe_name(spec['texture'])}.png"
        texture_target=skin_dir/texture_name
        shutil.copy2(texture_source,texture_target)
        mtl_text="newmtl SkinAlbedo\nKa 0.15 0.15 0.15\nKd 1.0 1.0 1.0\nKs 0.15 0.15 0.15\nNs 32.0\nd 1.0\nillum 2\nmap_Kd "+texture_name+"\n"
        (skin_dir/mtl_name).write_text(mtl_text,encoding="utf-8")
        source_text=source_obj.read_text(encoding="utf-8",errors="replace")
        lines=source_text.splitlines()
        decorated=[f"mtllib {mtl_name}"]
        for line in lines:
            decorated.append(line)
            if line.startswith("g ") or line.startswith("o "):
                decorated.append("usemtl SkinAlbedo")
        (skin_dir/obj_name).write_text("\n".join(decorated)+"\n",encoding="utf-8")
        manifest["skin_previews"].append({"skin_key":skin,"mesh_name":mesh_entry["mesh_name"],"mesh_path_id":spec["mesh_id"],"texture_name":spec["texture"],"obj":str(Path("skin_previews")/safe_name(skin)/obj_name),"mtl":str(Path("skin_previews")/safe_name(skin)/mtl_name),"texture":str(Path("skin_previews")/safe_name(skin)/texture_name),"note":"Static UV-textured preview only; no skeleton weights or animation."})
    preview_readme="""# Six-skin static 3D previews

Each folder contains one OBJ mesh, an MTL material, and its selected main-color texture. Open the OBJ in a 3D viewer that supports OBJ/MTL and relative texture paths.

These previews are static and unrigged. They are intended to validate UV placement and texture-to-mesh correspondence, not to reproduce the game's runtime shader, normal/specular maps, lighting, skeleton, or animation. The original IPA remains unchanged.
"""
    (preview_dir/"README.md").write_text(preview_readme,encoding="utf-8")

    # Bundle the static rig/animation map and human-readable mapping report with the exported assets.
    for source in (reports/"unity_rig_animation_map.json", reports/"target_model_material_map.md"):
        if source.exists():
            shutil.copy2(source,out/source.name)
    (out/"target_asset_export_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    archive=out/"counterflame_target_assets.zip"
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in out.rglob("*"):
            if path.is_file() and path!=archive:
                z.write(path,path.relative_to(out).as_posix())
    print(f"[OK] Exported {len(manifest['mesh_exports'])} meshes and {len(manifest['texture_exports'])} texture entries")
    print(f"Archive: {archive} ({archive.stat().st_size} bytes)")
    return manifest

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("ipa"); p.add_argument("--reports",default="reports"); p.add_argument("--out",default="reports/exported"); a=p.parse_args()
    m=run(Path(a.ipa),Path(a.reports),Path(a.out))
    print(f"Meshes: {len(m['mesh_exports'])}"); print(f"Textures: {len(m['texture_exports'])}")
    return 0
if __name__=="__main__": raise SystemExit(main())
