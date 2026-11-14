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
