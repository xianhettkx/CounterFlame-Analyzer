#!/usr/bin/env python3
"""Build a client-local skin texture override patch for the supplied IPA.

Current scope: mapped weapon material slots only; no fake inventory/equip UI,
no renderer rebinding, and no runtime hook. Unmapped first-person/glove slots
remain intentionally untouched until an audit proves their exact dependencies.

This tool only changes local Unity Texture2D payloads referenced by the original
weapon materials. It does not modify inventory, server data, gameplay logic,
anti-cheat, or network authorization. It defaults to audit-only mode.
"""
from __future__ import annotations
import argparse, json, tempfile, zipfile
from pathlib import Path
from typing import Any

TEXTURE_OVERRIDES = {
    "butterfly_marblefade": {"butterfly_vanilla_tps_Diffuse": {"_MainTex":"butterfly_marblefade_paint"}},
    "specialist_pillow": {},
    "awp_dragonlore": {
        "awp": {"_MainTex":"awp_dragonlore_cs2_low"},
        "awp_pbr": {"_MainTex":"awp_dragonlore_cs2","_SpecGlossMap":"awp_awp_dragonlore__cs2_mask"},
    },
    "ak47_neonrevolution": {
        "ak47_default_PBR": {"_MainTex":"ak47_neonrevolution_cs2","_SpecGlossMap":"ak47_ak47_neonrevolution__cs2_mask"},
        "ak47_default_tps_Diffuse": {"_MainTex":"ak47_neonrevolution_cs2_low"},
    },
    "m4a4_emperor": {
        "m4a4": {"_MainTex":"m4a4_emperor_cs2","_SpecGlossMap":"m4a1_m4a4_emperor__cs2_mask"},
        "m4a4_Diffuse": {"_MainTex":"m4a4_emperor_cs2_low"},
        "agent_m4a4_Diffuse": {"_MainTex":"m4a4_emperor_cs2_low"},
    },
    "deagle_codered": {
        "pist_deagle": {"_MainTex":"deagle_codered_cs2","_BumpMap":"deagle_codered_cs2_normal","_SpecGlossMap":"deserteagle_deagle_codered__cs2_mask"},
        "pist_deagle_Diffuse": {"_MainTex":"deagle_codered_cs2_low"},
    },
}

SKINS = {
    "butterfly_marblefade": {
        "label": "Butterfly Knife | Marble Fade",
        "base_materials": ["knife_flip", "butterfly_vanilla_tps_Diffuse"],
        "skin_materials": ["butterfly_marblefade_PBR", "butterfly_marblefade_Diffuse", "butterfly_marblefade_Specular"],
        "material_roles": {"knife_flip":"PBR","butterfly_vanilla_tps_Diffuse":"Diffuse"},
    },
    "specialist_pillow": {
        "label": "Specialist Gloves | Pillow Punchers",
        "base_materials": ["glove_specialist_left", "glove_specialist_right"],
        "skin_materials": ["specialist_pillow_PBR", "specialist_pillow_Diffuse", "specialist_pillow_Specular"],
        "material_roles": {"glove_specialist_left":"PBR","glove_specialist_right":"PBR"},
    },
    "awp_dragonlore": {
        "label": "AWP | Dragon Lore",
        "base_materials": ["awp", "awpScope", "awp_pbr"],
        "skin_materials": ["awp_dragonlore_PBR", "awp_dragonlore_Diffuse", "awp_dragonlore_Specular"],
        "material_roles": {"awp":"PBR","awp_pbr":"PBR"},
    },
    "ak47_neonrevolution": {
        "label": "AK-47 | Neon Revolution",
        "base_materials": ["ak47_default_PBR", "ak47_default_tps_Diffuse"],
        "skin_materials": ["ak47_neonrevolution_PBR", "ak47_neonrevolution_Diffuse", "ak47_neonrevolution_Specular"],
        "material_roles": {"ak47_default_PBR":"PBR","ak47_default_tps_Diffuse":"Diffuse"},
    },
    "m4a4_emperor": {
        "label": "M4A4 | The Emperor",
        "base_materials": ["m4a4", "m4a4_Diffuse", "agent_m4a4_Diffuse"],
        "skin_materials": ["m4a4_emperor_PBR", "m4a4_emperor_Diffuse", "m4a4_emperor_Specular"],
        "material_roles": {"m4a4":"PBR","m4a4_Diffuse":"Diffuse","agent_m4a4_Diffuse":"Diffuse"},
    },
    "deagle_codered": {
        "label": "Desert Eagle | Code Red",
        "base_materials": ["pist_deagle", "pist_deagle_Diffuse"],
        "skin_materials": ["deagle_codered_PBR", "deagle_codered_Diffuse", "deagle_codered_Specular"],
        "material_roles": {"pist_deagle":"PBR","pist_deagle_Diffuse":"Diffuse"},
    },
}

def name_of(obj: Any) -> str:
    try: return str(getattr(obj, "m_Name", "") or "")
    except Exception: return ""

def get_field(obj: Any, key: str, default=None):
    try: return getattr(obj, key)
    except Exception: return default

def texenv_pairs(material: Any):
    saved = get_field(material, "m_SavedProperties")
    envs = get_field(saved, "m_TexEnvs", []) or []
    result=[]
    if isinstance(envs, dict):
        iterator=envs.items()
    else:
        iterator=envs
    for item in iterator:
        try:
            key, value = item
        except Exception:
            continue
        if isinstance(key, bytes):
            key=key.decode("utf-8","replace")
        elif not isinstance(key,str):
            key=str(key)
        result.append((key,value))
    return result

def resolve_texture(ptr):
    if ptr is None: return None
    try: return ptr.deref()
    except Exception:
        try: return ptr.deref()
        except Exception: return None

def object_data(obj):
    try: return obj.read()
    except Exception: return None

def main():
    p=argparse.ArgumentParser()
    p.add_argument("ipa")
    p.add_argument("--out",default="reports/local_skin_patch")
    p.add_argument("--apply",action="store_true",help="Apply verified texture overrides; default is audit-only")
    args=p.parse_args()
    import UnityPy
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    audit={"mode":"apply_local_texture_overrides" if args.apply else "audit_only","skins":{},"limitations":[]}
    with zipfile.ZipFile(args.ipa,"r") as zf:
        names=zf.namelist()
        catalog_path=next((n for n in names if n.lower().endswith("/catalog.json")),None)
        resources_path=next((n for n in names if n.endswith("/resources.assets")),None)
        if not catalog_path or not resources_path:
            raise RuntimeError("IPA catalog.json or resources.assets not found")
        catalog=json.loads(zf.read(catalog_path).decode("utf-8-sig"))
        ids=catalog.get("m_InternalIds",[])
        bundle_paths=[x for x in ids if isinstance(x,str) and x.lower().endswith(".bundle") and any(k in x.lower() for k in SKINS)]
        ipa_set=set(names)
        selected=[]
        for raw in bundle_paths:
            norm=raw.replace("{UnityEngine.AddressableAssets.Addressables.RuntimePath}/","").lstrip("/")
            if norm in ipa_set: selected.append((norm,raw))
            else:
                hits=[n for n in names if n.endswith("/"+norm)]
                if len(hits)==1: selected.append((hits[0],raw))
        # Load the main serialized file and its streamed companion data.
        temp=tempfile.TemporaryDirectory(prefix="cf_local_skin_")
        root=Path(temp.name)
        main_asset=root/"resources.assets"
        main_asset.write_bytes(zf.read(resources_path))
        stream_path=next((n for n in names if n.endswith("/resources.resource")),None)
        if stream_path:
            (root/"resources.assets.resS").write_bytes(zf.read(stream_path))
            (root/"resources.assets.resource").write_bytes(zf.read(stream_path))
        base_env=UnityPy.load(str(main_asset))
        base_materials={}
        for obj in base_env.objects:
            if obj.type.name!="Material": continue
            data=object_data(obj)
            if data is not None:
                nm=name_of(data)
                if nm: base_materials.setdefault(nm,[]).append((obj,data))
        # Scan only the catalog bundles belonging to the six requested skins.
        skin_materials={k:[] for k in SKINS}
        source_textures={}
        for bundle_path,raw in selected:
            skin_key=next((k for k in SKINS if k in raw.lower()),None)
            if not skin_key: continue
            try:
                env=UnityPy.load(zf.read(bundle_path))
                for obj in env.objects:
                    if obj.type.name=="Texture2D":
                        texture_data=object_data(obj)
                        if texture_data is not None:
                            texture_name=name_of(texture_data)
                            if texture_name and texture_name not in source_textures:
                                try:
                                    source_textures[texture_name]={
                                        "data":bytes(texture_data.image_data),
                                        "width":int(texture_data.m_Width),
                                        "height":int(texture_data.m_Height),
                                        "format":texture_data.m_TextureFormat,
                                        "mip_count":int(get_field(texture_data,"m_MipCount",1) or 1),
                                        "bundle":bundle_path,
                                    }
                                except Exception:
                                    pass
                    elif obj.type.name=="Material":
                        data=object_data(obj)
                        if data is not None and name_of(data) in SKINS[skin_key]["skin_materials"]:
                            skin_materials[skin_key].append((name_of(data),data,bundle_path))
            except Exception as exc:
                audit.setdefault("bundle_errors",[]).append({"path":bundle_path,"error":f"{type(exc).__name__}: {exc}"[:200]})
        replacements=[]
        skipped_incompatible=[]
        for skin_key,spec in SKINS.items():
            skin_rows=[]
            source_mats=skin_materials.get(skin_key,[])
            for base_name in spec["base_materials"]:
                for base_obj,base_data in base_materials.get(base_name,[]):
                    base_slots=[]
                    for slot,base_env_data in texenv_pairs(base_data):
                        base_ptr=get_field(base_env_data,"m_Texture")
                        base_tex_obj=resolve_texture(base_ptr)
                        base_tex_data=object_data(base_tex_obj) if base_tex_obj else None
                        base_tex_name=name_of(base_tex_data) if base_tex_data else ""
                        role=spec.get("material_roles",{}).get(base_name)
                        preferred_source=f"{skin_key}_{role}" if role else ""
                        source_candidates=[]
                        for source_name,source_data,source_bundle in source_mats:
                            if preferred_source and source_name!=preferred_source: continue
                            for source_slot,source_env_data in texenv_pairs(source_data):
                                if source_slot!=slot: continue
                                source_ptr=get_field(source_env_data,"m_Texture")
                                source_obj=resolve_texture(source_ptr)
                                source_data_obj=object_data(source_obj) if source_obj else None
                                if source_data_obj is None: continue
                                try:
                                    img=source_data_obj.image
                                    source_candidates.append({
                                        "source_material":source_name,"source_bundle":source_bundle,
                                        "source_texture":name_of(source_data_obj),
                                        "width":int(source_data_obj.m_Width),"height":int(source_data_obj.m_Height),
                                        "_image":img,
                                    })
                                except Exception: continue
                        public_candidates=[]
                        for candidate in source_candidates:
                            public_candidates.append({k:v for k,v in candidate.items() if not k.startswith("_")})
                        row={
                            "base_material":base_name,"base_material_path_id":int(base_obj.path_id),
                            "slot":slot,"base_texture":base_tex_name,
                            "base_texture_path_id":int(get_field(base_ptr,"m_PathID",0) or 0) if base_ptr else 0,
                            "base_texture_file_id":int(get_field(base_ptr,"m_FileID",0) or 0) if base_ptr else 0,
                            "base_dimensions":[int(get_field(base_tex_data,"m_Width",0) or 0),int(get_field(base_tex_data,"m_Height",0) or 0)] if base_tex_data else None,
                            "source_candidates":public_candidates,
                            "planned_source_texture":TEXTURE_OVERRIDES.get(skin_key,{}).get(base_name,{}).get(slot),
                            "planned_source_texture_found":bool(TEXTURE_OVERRIDES.get(skin_key,{}).get(base_name,{}).get(slot) in source_textures) if TEXTURE_OVERRIDES.get(skin_key,{}).get(base_name,{}).get(slot) else False,
                        }
                        skin_rows.append(row)
                        if args.apply and base_tex_data is not None:
                            replacement_name=TEXTURE_OVERRIDES.get(skin_key,{}).get(base_name,{}).get(slot)
                            chosen=source_textures.get(replacement_name) if replacement_name else None
                            if chosen is not None:
                                # Only replace payloads with an identical GPU layout.
                                compatible = (
                                    int(base_tex_data.m_Width) == chosen["width"] and
                                    int(base_tex_data.m_Height) == chosen["height"] and
                                    base_tex_data.m_TextureFormat == chosen["format"] and
                                    len(bytes(base_tex_data.image_data)) == len(chosen["data"])
                                )
                                if not compatible:
                                    skipped_incompatible.append({
                                        "skin_key":skin_key,"base_material":base_name,"slot":slot,
                                        "source_texture":replacement_name,
                                        "base_dimensions":[int(base_tex_data.m_Width),int(base_tex_data.m_Height)],
                                        "source_dimensions":[chosen["width"],chosen["height"]],
                                        "base_format":str(base_tex_data.m_TextureFormat),
                                        "source_format":str(chosen["format"]),
                                        "base_bytes":len(bytes(base_tex_data.image_data)),
                                        "source_bytes":len(chosen["data"]),
                                    })
                                    continue
                                base_tex_data.image_data=chosen["data"]
                                base_tex_data.m_CompleteImageSize=len(chosen["data"])
                                base_tex_data.save()
                                replacements.append({
                                    "skin_key":skin_key,"base_material":base_name,"slot":slot,
                                    "base_texture":base_tex_name,"source_texture":replacement_name,
                                    "source_bundle":chosen["bundle"],
                                    "dimensions_before":row["base_dimensions"],
                                    "dimensions_after":[int(base_tex_data.m_Width),int(base_tex_data.m_Height)],
                                })
            audit["skins"][skin_key]={
                "display_name":spec["label"],
                "target_bundle_count":sum(1 for _,raw in selected if skin_key in raw.lower()),
                "skin_materials_found":sorted({x[0] for x in source_mats}),
                "base_materials_found":sorted(set(spec["base_materials"]) & set(base_materials)),
                "slots":skin_rows,
            }
        if args.apply:
            # Save even when all candidate overrides are rejected: this keeps
            # the original texture data intact instead of producing purple assets.
            output_asset=out/"resources.assets"
            output_asset.write_bytes(base_env.file.save())
            # Verify the modified SerializedFile can be reopened.
            verify=UnityPy.load(str(output_asset))
            if not any(o.type.name=="Material" for o in verify.objects):
                raise RuntimeError("Saved resources.assets failed verification")
            audit["replacements"]=replacements
            audit["skipped_incompatible"]=skipped_incompatible
            audit["patch_file"]="resources.assets"
            audit["patch_sha256"]=__import__("hashlib").sha256(output_asset.read_bytes()).hexdigest()
        audit["source_texture_index"]={k:{"width":v["width"],"height":v["height"],"format":str(v["format"]),"mip_count":v["mip_count"],"bundle":v["bundle"]} for k,v in sorted(source_textures.items())}
        audit["counts"]={
            "target_bundle_paths":len(selected),
            "source_textures_found":len(source_textures),
            "base_material_objects":sum(len(v) for v in base_materials.values()),
            "skin_material_objects":sum(len(v) for v in skin_materials.values()),
            "texture_replacements":len(replacements),
            "incompatible_overrides_skipped":len(skipped_incompatible),
        }
        audit["limitations"]=[
            "This is a local visual texture override only; it does not change inventory ownership, server state, or other players' view.",
            "Only material texture slots with a single unambiguous source candidate are eligible for replacement.",
            "This output is an asset patch, not a re-signed iOS application.",
            "Do not use modified assets to bypass game integrity checks or anti-cheat systems.",
        ]
        (out/"local_skin_patch_audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
        temp.cleanup()
    print(json.dumps(audit["counts"],ensure_ascii=False))
    print(f"[OK] Audit: {out/'local_skin_patch_audit.json'}")
    if args.apply: print(f"[OK] Patch: {out/'resources.assets'}")

if __name__=="__main__": main()
