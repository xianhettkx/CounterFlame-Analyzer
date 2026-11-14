#!/usr/bin/env python3
"""Read-only renderer-owner, Transform-parent, and ancestor-Animator audit."""
from __future__ import annotations
import argparse
import json
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any


def value(obj: Any, key: str, default=None):
    try:
        return getattr(obj, key)
    except Exception:
        return default


def pptr(obj: Any):
    if obj is None:
        return None
    try:
        file_id = int(value(obj, "m_FileID", 0) or 0)
        path_id = int(value(obj, "m_PathID", 0) or 0)
        if path_id == 0:
            return None
        return {"file_id": file_id, "path_id": path_id}
    except Exception:
        return None


def component_ptr(pair: Any):
    comp = value(pair, "component", None)
    if comp is None and isinstance(pair, (list, tuple)) and len(pair) > 1:
        comp = pair[1]
    return pptr(comp)


def object_name(objs: dict[int, Any], pid: int) -> str:
    obj = objs.get(pid)
    if obj is None:
        return ""
    try:
        name = obj.peek_name()
        if name:
            return str(name)
    except Exception:
        pass
    try:
        return str(value(obj.read(), "m_Name", "") or "")
    except Exception:
        return ""


def gameobject_components(objs: dict[int, Any], go_pid: int):
    go_obj = objs.get(go_pid)
    if go_obj is None or go_obj.type.name != "GameObject":
        raise ValueError(f"GameObject {go_pid} is missing")
    go_data = go_obj.read()
    found = []
    for pair in value(go_data, "m_Component", []) or []:
        ref = component_ptr(pair)
        if ref and ref["file_id"] == 0 and ref["path_id"] in objs:
            found.append((ref["path_id"], objs[ref["path_id"]]))
    return go_data, found


def owner_hierarchy(objs: dict[int, Any], go_pid: int):
    nodes = []
    seen = set()
    current_go = go_pid
    error = ""
    while current_go:
        if current_go in seen:
            error = "Transform.m_Father cycle"
            break
        seen.add(current_go)
        try:
            go_data, components = gameobject_components(objs, current_go)
        except Exception as exc:
            error = f"GameObject read failed: {type(exc).__name__}: {exc}"
            break
        transforms = [(pid, obj) for pid, obj in components if obj.type.name == "Transform"]
        if len(transforms) != 1:
            error = f"expected one Transform, found {len(transforms)} on GameObject {current_go}"
            break
        transform_pid, transform_obj = transforms[0]
        try:
            transform_data = transform_obj.read()
        except Exception as exc:
            error = f"Transform {transform_pid} read failed: {type(exc).__name__}: {exc}"
            break

        animators = []
        for animator_pid, animator_obj in components:
            if animator_obj.type.name != "Animator":
                continue
            try:
                animator_data = animator_obj.read()
                controller = pptr(value(animator_data, "m_Controller", None))
                avatar = pptr(value(animator_data, "m_Avatar", None))
                animators.append({
                    "animator_path_id": animator_pid,
                    "controller": controller,
                    "controller_name": object_name(objs, controller["path_id"]) if controller and controller["file_id"] == 0 else "",
                    "avatar": avatar,
                })
            except Exception as exc:
                animators.append({"animator_path_id": animator_pid, "error": f"{type(exc).__name__}: {exc}"})

        father = pptr(value(transform_data, "m_Father", None))
        nodes.append({
            "gameobject_path_id": current_go,
            "gameobject_name": str(value(go_data, "m_Name", "") or ""),
            "transform_path_id": transform_pid,
            "father": father,
            "animators": animators,
        })
        if not father or father["path_id"] == 0:
            break
        if father["file_id"] != 0 or father["path_id"] not in objs:
            error = f"unresolved parent Transform {father}"
            break
        parent_obj = objs[father["path_id"]]
        if parent_obj.type.name != "Transform":
            error = f"parent pointer {father['path_id']} is not Transform"
            break
        try:
            parent_data = parent_obj.read()
            parent_go = pptr(value(parent_data, "m_GameObject", None))
        except Exception as exc:
            error = f"parent Transform read failed: {type(exc).__name__}: {exc}"
            break
        if not parent_go or parent_go["file_id"] != 0:
            error = "parent Transform has no local GameObject"
            break
        current_go = parent_go["path_id"]
    return {"nodes": nodes, "error": error}


def renderer_owner(objs: dict[int, Any], renderer_pid: int, renderer_obj: Any, mesh_pid: int):
    data = renderer_obj.read()
    go_ref = pptr(value(data, "m_GameObject", None))
    if not go_ref or go_ref["file_id"] != 0 or go_ref["path_id"] not in objs:
        return {
            "renderer_path_id": renderer_pid,
            "renderer_type": renderer_obj.type.name,
            "gameobject_path_id": go_ref,
            "error": "renderer GameObject unresolved",
        }
    go_pid = go_ref["path_id"]
    materials = []
    for mat_ref_obj in value(data, "m_Materials", []) or []:
        mat_ref = pptr(mat_ref_obj)
        materials.append({
            "path_id": mat_ref["path_id"] if mat_ref else 0,
            "name": object_name(objs, mat_ref["path_id"]) if mat_ref and mat_ref["file_id"] == 0 else "",
            "file_id": mat_ref["file_id"] if mat_ref else 0,
        })
    bones = []
    for bone_obj in value(data, "m_Bones", []) or []:
        bone_ref = pptr(bone_obj)
        bone_name = ""
        if bone_ref and bone_ref["file_id"] == 0 and bone_ref["path_id"] in objs:
            bone_obj2 = objs[bone_ref["path_id"]]
            try:
                bone_data = bone_obj2.read()
                bone_go = pptr(value(bone_data, "m_GameObject", None))
                if bone_go and bone_go["file_id"] == 0:
                    bone_name = object_name(objs, bone_go["path_id"])
            except Exception:
                pass
        bones.append({"path_id": bone_ref["path_id"] if bone_ref else 0, "name": bone_name})
    root_ref = pptr(value(data, "m_RootBone", None))
    root_name = ""
    if root_ref and root_ref["file_id"] == 0 and root_ref["path_id"] in objs:
        try:
            root_data = objs[root_ref["path_id"]].read()
            root_go = pptr(value(root_data, "m_GameObject", None))
            if root_go and root_go["file_id"] == 0:
                root_name = object_name(objs, root_go["path_id"])
        except Exception:
            pass
    return {
        "renderer_path_id": renderer_pid,
        "renderer_type": renderer_obj.type.name,
        "mesh_path_id": mesh_pid,
        "gameobject_path_id": go_pid,
        "gameobject_name": object_name(objs, go_pid),
        "materials": materials,
        "bone_count": len(bones),
        "bone_names_resolved": sum(1 for b in bones if b["name"]),
        "bone_names": [b["name"] for b in bones],
        "root_bone_path_id": root_ref["path_id"] if root_ref else 0,
        "root_bone_name": root_name,
        "hierarchy": owner_hierarchy(objs, go_pid),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ipa")
    parser.add_argument("--manifest", default="config/local_skin_pseudo_entity_map.json")
    parser.add_argument("--out", default="reports/mesh_swap_prototype_run/renderer_owner_context")
    args = parser.parse_args()

    import UnityPy
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    targets = {}
    for skin in manifest.get("skins", []):
        for side in ("first_person", "third_person"):
            slot = skin.get(side, {})
            ids = []
            if slot.get("mesh_path_id"):
                ids.append(int(slot["mesh_path_id"]))
            ids.extend(int(x) for x in slot.get("mesh_path_ids", []))
            for pid in ids:
                targets[pid] = {"skin_key": skin["key"], "side": side}

    with zipfile.ZipFile(args.ipa, "r") as zf:
        asset_path = next((n for n in zf.namelist() if n.endswith("/resources.assets")), None)
        if not asset_path:
            raise RuntimeError("resources.assets not found")
        env = UnityPy.load(zf.read(asset_path))

    objs = {int(obj.path_id): obj for obj in env.objects}
    owners_by_mesh = {pid: [] for pid in targets}
    for renderer_pid, obj in objs.items():
        if obj.type.name not in ("MeshFilter", "SkinnedMeshRenderer", "MeshRenderer"):
            continue
        try:
            data = obj.read()
        except Exception:
            continue
        mesh_ref = pptr(value(data, "m_Mesh", None))
        if not mesh_ref or mesh_ref["file_id"] != 0 or mesh_ref["path_id"] not in owners_by_mesh:
            continue
        try:
            owners_by_mesh[mesh_ref["path_id"]].append(
                renderer_owner(objs, renderer_pid, obj, mesh_ref["path_id"])
            )
        except Exception as exc:
            owners_by_mesh[mesh_ref["path_id"]].append({
                "renderer_path_id": renderer_pid,
                "renderer_type": obj.type.name,
                "error": f"{type(exc).__name__}: {exc}",
            })

    rows = []
    for mesh_pid, owners in owners_by_mesh.items():
        signatures = []
        for owner in owners:
            sig = (
                owner.get("renderer_type", ""),
                tuple(owner.get("bone_names", [])),
                owner.get("root_bone_name", ""),
                tuple(x.get("name", "") for x in owner.get("materials", [])),
                tuple((n.get("gameobject_name", ""), tuple(a.get("controller_name", "") for a in n.get("animators", [])))
                      for n in owner.get("hierarchy", {}).get("nodes", [])),
            )
            signatures.append(sig)
        rows.append({
            "mesh_path_id": mesh_pid,
            **targets[mesh_pid],
            "owner_count": len(owners),
            "distinct_owner_signature_count": len(set(signatures)),
            "owners": owners,
        })

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "tool": "CounterFlame Renderer Owner Context Audit",
        "schema_version": 1,
        "asset_path": asset_path,
        "target_mesh_count": len(targets),
        "renderer_owner_count": sum(len(x["owners"]) for x in rows),
        "meshes": rows,
        "limitations": [
            "Read-only serialized owner, hierarchy, material, and Animator mapping.",
            "Does not prove which prefab/renderer is active in a live match.",
            "No IPA bytes, inventory, entitlement, network, or anti-cheat data modified.",
        ],
    }
    (out / "renderer_owner_context.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "target_meshes": len(targets),
        "renderer_owners": report["renderer_owner_count"],
        "report": str(out / "renderer_owner_context.json"),
    }))


if __name__ == "__main__":
    main()
