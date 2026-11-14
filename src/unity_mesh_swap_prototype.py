#!/usr/bin/env python3
"""Local-only, gated prototype for Mesh reference replacement.

This is the minimal viable model-swap prototype. It is deliberately separated
from the existing texture-override pipeline:

* Texture pipeline: ``unity_local_skin_patch.py`` rewrites Texture2D payload
  bytes inside material slots. That is NOT a model swap.
* This prototype: plans / (with an explicit flag) repoints a renderer's
  ``m_Mesh`` PPtr to another Mesh that already exists in the same serialized
  file. It does not author new mesh vertex bytes, does not rebuild
  AssetBundles, and does not touch inventory, entitlements, networking,
  anti-cheat, or runtime injection.

Default mode is audit-only. A reference swap writes nothing unless
``--apply-reference-swap`` is supplied together with an explicit renderer and
mesh path id, and the plan passes every invariant check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
import tempfile
from pathlib import Path
from typing import Any, Optional

try:  # package import under tests; flat import when run as a script
    from .unity_mesh_swap_plan import (
        APPLY_WRITABLE_PLAN_STATUS,
        MeshModelRecord,
        SwapPlan,
        evaluate_swap,
        readiness_allows_apply,
        record_readiness,
        summarize_manifests,
    )
except ImportError:  # pragma: no cover - script entry point
    from unity_mesh_swap_plan import (
        APPLY_WRITABLE_PLAN_STATUS,
        MeshModelRecord,
        SwapPlan,
        evaluate_swap,
        readiness_allows_apply,
        record_readiness,
        summarize_manifests,
    )


class ReferenceDriftError(Exception):
    """Raised when a preserved reference drifts after the m_Mesh repoint.

    No asset bytes are written when this is raised; the abort happens before
    any serialization or file replacement.
    """


# Renderer reference fields that a mesh reference swap must never rewrite.
# (m_BindPose lives on the Mesh itself and travels with the swapped Mesh;
#  it is not a renderer-level reference and is not touched here.)
PRESERVED_RENDERER_FIELDS = ("m_GameObject", "m_Bones", "m_RootBone", "m_Materials")


def snapshot_renderer_references(data: Any) -> dict[str, Any]:
    """Capture the PPtr values that must survive an m_Mesh repoint unchanged."""
    return {
        "m_GameObject": ptr(gv(data, "m_GameObject", None)),
        "m_Bones": [ptr(b) for b in (gv(data, "m_Bones", []) or [])],
        "m_RootBone": ptr(gv(data, "m_RootBone", None)),
        "m_Materials": [ptr(m) for m in (gv(data, "m_Materials", []) or [])],
    }


def _gameobject_components(objs: dict[int, Any], go_pid: int) -> list[tuple[int, Any]]:
    """Return (component path id, object) pairs for a Unity GameObject."""
    if go_pid not in objs:
        raise ReferenceDriftError(f"GameObject {go_pid} is missing; hierarchy cannot be verified")
    try:
        go_data = objs[go_pid].read()
    except Exception as exc:
        raise ReferenceDriftError(f"GameObject {go_pid} cannot be read: {exc}") from exc
    found: list[tuple[int, Any]] = []
    for pair in gv(go_data, "m_Component", []) or []:
        comp = gv(pair, "component", None)
        if comp is None and isinstance(pair, (list, tuple)) and len(pair) > 1:
            comp = pair[1]
        component = ptr(comp)
        if component and component["file_id"] == 0 and component["path_id"] in objs:
            found.append((component["path_id"], objs[component["path_id"]]))
    return found


def snapshot_animator_controller(objs: dict[int, Any], go_pid: int) -> dict[str, Any]:
    """Snapshot Animator/controller/avatar and Transform hierarchy up to the root.

    Unity rigs commonly put Animator on an ancestor GameObject. Walk from the
    renderer GameObject through Transform.m_Father, recording each Transform's
    father/children and every Animator's controller/avatar. Any broken link,
    unreadable node, or cycle fails closed before serialization.
    """
    if not go_pid or go_pid not in objs:
        raise ReferenceDriftError("renderer GameObject is missing; hierarchy cannot be verified")

    nodes: list[dict[str, Any]] = []
    seen_go: set[int] = set()
    current_go = go_pid
    while current_go:
        if current_go in seen_go:
            raise ReferenceDriftError("Transform.m_Father cycle detected; no file written")
        seen_go.add(current_go)

        components = _gameobject_components(objs, current_go)
        transforms = [(pid, obj) for pid, obj in components if obj.type.name == "Transform"]
        if len(transforms) != 1:
            raise ReferenceDriftError(
                f"GameObject {current_go} has {len(transforms)} Transform components; "
                "hierarchy cannot be verified"
            )
        transform_pid, transform_obj = transforms[0]
        try:
            transform_data = transform_obj.read()
        except Exception as exc:
            raise ReferenceDriftError(f"Transform {transform_pid} cannot be read: {exc}") from exc

        father = ptr(gv(transform_data, "m_Father", None))
        children = [ptr(child) for child in (gv(transform_data, "m_Children", []) or [])]
        animators: list[dict[str, Any]] = []
        for component_pid, component_obj in components:
            if component_obj.type.name != "Animator":
                continue
            try:
                animator_data = component_obj.read()
            except Exception as exc:
                raise ReferenceDriftError(
                    f"Animator {component_pid} cannot be read: {exc}"
                ) from exc
            animators.append({
                "animator_path_id": component_pid,
                "controller": ptr(gv(animator_data, "m_Controller", None)),
                "avatar": ptr(gv(animator_data, "m_Avatar", None)),
            })

        nodes.append({
            "gameobject_path_id": current_go,
            "transform_path_id": transform_pid,
            "father": father,
            "children": children,
            "animators": animators,
        })

        if not father or father["path_id"] == 0:
            break
        if father["file_id"] != 0 or father["path_id"] not in objs:
            raise ReferenceDriftError(
                f"Transform {transform_pid} has an unresolved parent reference; no file written"
            )
        parent_transform = objs[father["path_id"]]
        if parent_transform.type.name != "Transform":
            raise ReferenceDriftError("Transform.m_Father does not point to a Transform")
        try:
            parent_transform_data = parent_transform.read()
        except Exception as exc:
            raise ReferenceDriftError(f"Parent Transform cannot be read: {exc}") from exc
        parent_go = ptr(gv(parent_transform_data, "m_GameObject", None))
        if not parent_go or parent_go["file_id"] != 0 or parent_go["path_id"] not in objs:
            raise ReferenceDriftError("Parent Transform has no resolvable GameObject")
        current_go = parent_go["path_id"]

    return {"nodes": nodes}


def gv(obj: Any, key: str, default: Any = None) -> Any:
    try:
        return getattr(obj, key)
    except Exception:
        return default


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes to ``path`` via a same-directory temp file then os.replace.

    The target is only replaced after the temp file is flushed and fsynced;
    any failure leaves the original target untouched and removes the temp file.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".cf_mesh_swap_", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def decide_apply(
    source: MeshModelRecord, target: MeshModelRecord
) -> dict[str, Any]:
    """Evaluate the pair plan and single-record readiness on *both* sides.

    Apply is allowed only when the pair plan reaches
    ``reference_swap_eligible`` and neither side is ``blocked``. A skinned
    pair that still needs runtime verification is **not** promoted; it is
    skipped and never serialized to disk.
    """
    plan = evaluate_swap(source, target)
    source_status, source_reasons = record_readiness(source)
    target_status, target_reasons = record_readiness(target)
    reasons: list[str] = list(source_reasons) + list(target_reasons)
    reasons.extend(c.detail for c in plan.blocking_checks)

    eligible = (
        plan.status == APPLY_WRITABLE_PLAN_STATUS
        and readiness_allows_apply(source_status)
        and readiness_allows_apply(target_status)
    )
    return {
        "plan": plan,
        "plan_status": plan.status,
        "source_readiness": source_status,
        "target_readiness": target_status,
        "reasons": reasons,
        "eligible": eligible,
    }


def assert_no_reference_drift(
    before: dict[str, Any],
    after: dict[str, Any],
    animator_before: Optional[dict[str, Any]],
    animator_after: Optional[dict[str, Any]],
) -> None:
    if before != after:
        raise ReferenceDriftError(
            "reference drift detected after m_Mesh write; bones/root/materials/"
            "GameObject must be unchanged; no file written"
        )
    if animator_before != animator_after:
        raise ReferenceDriftError(
            "Animator controller reference drifted; no file written"
        )


def perform_reference_swap(
    data: Any, objs: dict[int, Any], mesh_pid: int
) -> dict[str, Any]:
    """Repoint ``m_Mesh`` in memory and assert every preserved reference held.

    The only field mutated is the renderer's ``m_Mesh`` PPtr. If any preserved
    renderer reference or the Animator controller drifts, ``ReferenceDriftError``
    is raised before serialization; nothing is written to disk.
    """
    go_ptr = ptr(gv(data, "m_GameObject", None))
    go_pid = go_ptr["path_id"] if go_ptr else 0
    before = snapshot_renderer_references(data)
    animator_before = snapshot_animator_controller(objs, go_pid)

    # The single mutation allowed by this prototype: m_Mesh PPtr.
    data.m_Mesh.m_FileID = 0
    data.m_Mesh.m_PathID = mesh_pid

    after = snapshot_renderer_references(data)
    animator_after = snapshot_animator_controller(objs, go_pid)

    assert_no_reference_drift(before, after, animator_before, animator_after)
    return {
        "before": before,
        "after": after,
        "animator_before": animator_before,
        "animator_after": animator_after,
        "go_pid": go_pid,
    }


def ptr(p: Any) -> Optional[dict[str, int]]:
    if p is None:
        return None
    return {
        "file_id": int(gv(p, "m_FileID", 0) or 0),
        "path_id": int(gv(p, "m_PathID", 0) or 0),
    }


def _mesh_record(objs: dict[int, Any], mesh_pid: int, skin_key: str = "", side: str = "") -> Optional[MeshModelRecord]:
    obj = objs.get(mesh_pid)
    if obj is None:
        return None
    try:
        mesh = obj.read()
    except Exception:
        return MeshModelRecord(mesh_path_id=mesh_pid, mesh_name=obj.peek_name() or "",
                                renderer_type="unknown", skin_key=skin_key, side=side,
                                notes=["mesh read error"])
    name = str(gv(mesh, "m_Name", "") or obj.peek_name() or "")
    record = MeshModelRecord(
        mesh_path_id=mesh_pid,
        mesh_name=name,
        renderer_type="unknown",
        skin_key=skin_key,
        side=side,
        submesh_count=len(gv(mesh, "m_SubMeshes", []) or []),
        bind_pose_count=len(gv(mesh, "m_BindPose", []) or []),
        mesh_is_readable=gv(mesh, "m_IsReadable", None),
    )

    # Hash the actual serialized bind-pose matrices, not only their count.
    bind_pose_rows: list[list[float]] = []
    bind_pose_complete = True
    for matrix in gv(mesh, "m_BindPose", []) or []:
        values: list[float] = []
        for row in range(4):
            for col in range(4):
                value = gv(matrix, f"e{row}{col}", None)
                if value is None:
                    bind_pose_complete = False
                    break
                values.append(float(value))
            if not bind_pose_complete:
                break
        if not bind_pose_complete:
            break
        bind_pose_rows.append(values)
    if bind_pose_complete and bind_pose_rows:
        raw = json.dumps(bind_pose_rows, separators=(",", ":")).encode("utf-8")
        record.bind_pose_signature = hashlib.sha256(raw).hexdigest()
    # MeshHandler decoding is best-effort; weapon streams may be non-readable.
    try:
        from UnityPy.helpers.MeshHelper import MeshHandler

        handler = MeshHandler(mesh)
        handler.process()
        record.vertex_count = len(getattr(handler, "m_Vertices", []) or [])
        record.uv_count = len(getattr(handler, "m_UV0", []) or [])
        record.weight_entries = len(getattr(handler, "m_BoneWeights", []) or [])
        record.bone_indices_entries = len(getattr(handler, "m_BoneIndices", []) or [])
    except Exception as exc:
        record.notes.append(f"MeshHandler: {type(exc).__name__}: {exc}"[:160])

    # Find every owning renderer/filter; shared Mesh objects need explicit owner disambiguation.
    owner_count = 0
    for comp in objs.values():
        if comp.type.name not in ("MeshFilter", "SkinnedMeshRenderer", "MeshRenderer"):
            continue
        try:
            data = comp.read()
        except Exception:
            continue
        mesh_ref = ptr(gv(data, "m_Mesh", None))
        if not mesh_ref or mesh_ref["path_id"] != mesh_pid or mesh_ref["file_id"] != 0:
            continue
        owner_count += 1
        record.renderer_owner_count = owner_count
        go_ref = ptr(gv(data, "m_GameObject", None))
        go_name = ""
        if go_ref and go_ref["path_id"] in objs:
            try:
                go_name = str(gv(objs[go_ref["path_id"]].read(), "m_Name", "") or "")
            except Exception:
                pass
        materials: list[str] = []
        for mp in gv(data, "m_Materials", []) or []:
            m = ptr(mp)
            if m and m["path_id"] in objs:
                try:
                    materials.append(str(gv(objs[m["path_id"]].read(), "m_Name", "") or ""))
                except Exception:
                    materials.append("")
            else:
                materials.append(f"<external {m['file_id']}/{m['path_id']}>" if m else "")
        bones = [ptr(b) for b in gv(data, "m_Bones", []) or []]
        # Preserve ordered bone identity by Transform -> GameObject name.
        bone_names: list[str] = []
        bone_names_complete = bool(bones)
        for bone_ref in bones:
            if not bone_ref or bone_ref["file_id"] != 0 or bone_ref["path_id"] not in objs:
                bone_names_complete = False
                break
            bone_obj = objs[bone_ref["path_id"]]
            if bone_obj.type.name != "Transform":
                bone_names_complete = False
                break
            try:
                bone_data = bone_obj.read()
                bone_go = ptr(gv(bone_data, "m_GameObject", None))
                if not bone_go or bone_go["file_id"] != 0 or bone_go["path_id"] not in objs:
                    bone_names_complete = False
                    break
                bone_name = str(gv(objs[bone_go["path_id"]].read(), "m_Name", "") or "")
                if not bone_name:
                    bone_names_complete = False
                    break
                bone_names.append(bone_name)
            except Exception:
                bone_names_complete = False
                break
        record.renderer_bone_names = bone_names if bone_names_complete else []
        root = ptr(gv(data, "m_RootBone", None))
        root_name = ""
        if root and root["path_id"] in objs:
            try:
                tr = objs[root["path_id"]].read()
                g = ptr(gv(tr, "m_GameObject", None))
                if g and g["path_id"] in objs:
                    root_name = str(gv(objs[g["path_id"]].read(), "m_Name", "") or "")
            except Exception:
                pass
        record.renderer_type = comp.type.name
        record.gameobject_name = go_name
        record.material_names = materials
        record.renderer_bone_count = len(bones)
        record.root_bone_name = root_name
        # MeshFilter does not carry materials; resolve the sibling MeshRenderer
        # on the same GameObject for the material slot list.
        if comp.type.name == "MeshFilter" and go_ref:
            for sib in objs.values():
                if sib.type.name != "MeshRenderer":
                    continue
                try:
                    sd = sib.read()
                    sib_go = ptr(gv(sd, "m_GameObject", None))
                    if not sib_go or sib_go["path_id"] != go_ref["path_id"]:
                        continue
                    sib_mats = []
                    for mp in gv(sd, "m_Materials", []) or []:
                        m = ptr(mp)
                        if m and m["path_id"] in objs:
                            try:
                                sib_mats.append(str(gv(objs[m["path_id"]].read(), "m_Name", "") or ""))
                            except Exception:
                                sib_mats.append("")
                        else:
                            sib_mats.append(f"<external {m['file_id']}/{m['path_id']}>" if m else "")
                    record.material_names = sib_mats
                except Exception:
                    pass
        if record.mesh_is_readable is False:
            note = "m_IsReadable=false; geometry may rely on streamed resource data"
            if note not in record.notes:
                record.notes.append(note)

    if owner_count > 1:
        record.notes.append(
            f"multiple renderer owners: {owner_count}; exact renderer/skeleton instance is ambiguous"
        )
    return record


def apply_reference_swap(
    env: Any,
    objs: dict[int, Any],
    renderer_pid: int,
    mesh_pid: int,
    out_path: Path,
    source_record: Optional[MeshModelRecord] = None,
    target_record: Optional[MeshModelRecord] = None,
) -> dict[str, Any]:
    """Gated, atomic reference-swap orchestrator.

    Returns a report fragment. On any blocked / not-eligible / drift condition
    the function returns ``applied=False`` and **never creates the output
    asset**. Only an eligible plan proceeds: the mutation and reference guards
    run in memory, the payload is serialized and validated in memory, and only
    then is the target file replaced atomically.
    """
    report: dict[str, Any] = {"applied": False, "skipped": []}
    renderer = objs.get(renderer_pid)
    target_mesh = objs.get(mesh_pid)
    if renderer is None or target_mesh is None:
        raise SystemExit("renderer or mesh path id not found in serialized file")
    if target_mesh.type.name != "Mesh":
        raise SystemExit("selected --mesh-pid does not resolve to a Mesh object")

    source = source_record if source_record is not None else _mesh_record(objs, mesh_pid)
    data = renderer.read()
    current = ptr(gv(data, "m_Mesh", None))
    target = (
        target_record
        if target_record is not None
        else (_mesh_record(objs, current["path_id"]) if current else None)
    )
    if source is None or target is None:
        raise SystemExit("could not build swap plan for selected objects")

    decision = decide_apply(source, target)
    plan: SwapPlan = decision["plan"]
    report["applied_plan"] = {
        "renderer_pid": renderer_pid,
        "mesh_pid": mesh_pid,
        "status": plan.status,
        "source_readiness": decision["source_readiness"],
        "target_readiness": decision["target_readiness"],
        "checks": [vars(c) for c in plan.checks],
        "preserved_references": list(plan.preserved_references),
    }

    if not decision["eligible"]:
        # Gate failure: blocked or still needs runtime verification. Skip this
        # model entirely; never write a patch file.
        report["applied"] = False
        report["skipped"].append({
            "mesh_path_id": source.mesh_path_id,
            "mesh_name": source.mesh_name,
            "renderer_pid": renderer_pid,
            "status": plan.status,
            "source_readiness": decision["source_readiness"],
            "target_readiness": decision["target_readiness"],
            "reasons": decision["reasons"],
        })
        report["note"] = (
            "Not eligible for reference swap (blocked or needs runtime "
            "verification); skipped without writing any asset bytes."
        )
        return report

    # In-memory mutation + reference guard; drift aborts before serialization.
    swap = perform_reference_swap(data, objs, mesh_pid)

    data.save()
    payload = env.file.save()
    if not payload:
        raise ReferenceDriftError("serialized payload is empty; refusing to write")

    atomic_write_bytes(Path(out_path), payload)
    report["applied"] = True
    report["patch_file"] = str(out_path)
    report["preserved_before"] = swap["before"]
    report["preserved_after"] = swap["after"]
    report["note"] = (
        "Reference-swap prototype output; re-sign and on-device test required "
        "before any install. No inventory, entitlement, network or anti-cheat "
        "code was modified."
    )
    return report


def load_resources(ipa_path: Path, out: Path) -> tuple[Any, dict[int, Any], Path, tempfile.TemporaryDirectory]:
    import UnityPy

    with zipfile.ZipFile(ipa_path, "r") as zf:
        names = zf.namelist()
        asset_path = next((n for n in names if n.endswith("/resources.assets")), None)
        if asset_path is None:
            raise SystemExit("resources.assets not found in IPA")
        stream_path = next((n for n in names if n.endswith("/resources.assets.resS")), None)
        if stream_path is None:
            stream_path = next((n for n in names if n.endswith("/resources.resource")), None)
        temp = tempfile.TemporaryDirectory(prefix="cf_mesh_swap_")
        root = Path(temp.name)
        main_asset = root / "resources.assets"
        main_asset.write_bytes(zf.read(asset_path))
        if stream_path:
            data = zf.read(stream_path)
            (root / "resources.assets.resS").write_bytes(data)
            (root / "resources.resource").write_bytes(data)
    env = UnityPy.load(str(main_asset))
    objs = {int(o.path_id): o for o in env.objects}
    # Keep the extracted directory alive: UnityPy may lazily read .resS /
    # .resource streams while MeshHandler decodes vertex and skin data.
    return env, objs, main_asset, temp


def plan_cross_swaps(records: list[MeshModelRecord]) -> list[dict[str, Any]]:
    """Pair same-family records and evaluate a reference-swap plan.

    This is an offline feasibility check between stock meshes; it does not
    claim the paired skins are equippable at runtime.
    """
    plans: list[dict[str, Any]] = []
    # Prototype pairs only meshes that belong to the same catalog skin entry.
    # Cross-family pairings (e.g. butterfly TPS mesh vs AK TPS mesh) are not
    # proposed; geometry scale, attach point and bone layout are not comparable.
    by_skin: dict[str, list[MeshModelRecord]] = {}
    for record in records:
        by_skin.setdefault(record.skin_key or record.mesh_name, []).append(record)
    for pool in by_skin.values():
        for source in pool:
            for target in pool:
                if source.mesh_path_id == target.mesh_path_id:
                    continue
                if source.renderer_type != target.renderer_type:
                    continue
                plan: SwapPlan = evaluate_swap(source, target)
                plans.append({
                    "skin_key": source.skin_key,
                    "source_mesh_path_id": source.mesh_path_id,
                    "source_mesh_name": source.mesh_name,
                    "source_side": source.side,
                    "target_mesh_path_id": target.mesh_path_id,
                    "target_mesh_name": target.mesh_name,
                    "target_side": target.side,
                    "status": plan.status,
                    "checks": [vars(c) for c in plan.checks],
                    "preserved_references": list(plan.preserved_references),
                })
    return plans


def main() -> int:
    ap = argparse.ArgumentParser(description="Local-only Mesh reference swap prototype (audit default)")
    ap.add_argument("ipa")
    ap.add_argument("--manifest", default="config/local_skin_pseudo_entity_map.json")
    ap.add_argument("--out", default="reports/mesh_swap_prototype")
    ap.add_argument("--apply-reference-swap", action="store_true",
                     help="Gate: actually rewrite m_Mesh on the selected renderer (no effect otherwise)")
    ap.add_argument("--renderer-pid", type=int, default=0)
    ap.add_argument("--mesh-pid", type=int, default=0)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))

    env, objs, main_asset, temp_dir = load_resources(Path(args.ipa), out)
    pid_meta: dict[int, tuple[str, str]] = {}
    for skin in manifest.get("skins", []):
        skin_key = skin.get("key", "")
        for side in ("first_person", "third_person"):
            slot = skin.get(side) or {}
            if slot.get("mesh_path_id"):
                pid_meta[int(slot["mesh_path_id"])] = (skin_key, side)
            for pid in slot.get("mesh_path_ids", []) or []:
                pid_meta[int(pid)] = (skin_key, side)

    records: list[MeshModelRecord] = []
    for pid, (skin_key, side) in pid_meta.items():
        record = _mesh_record(objs, pid, skin_key=skin_key, side=side)
        if record is not None:
            records.append(record)
    plans = plan_cross_swaps(records)

    readiness: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for record in records:
        status, reasons = record_readiness(record)
        entry = {
            "skin_key": record.skin_key,
            "side": record.side,
            "mesh_path_id": record.mesh_path_id,
            "mesh_name": record.mesh_name,
            "renderer_type": record.renderer_type,
            "status": status,
            "reasons": reasons,
        }
        readiness.append(entry)
        if status == "blocked":
            skipped.append(entry)

    report: dict[str, Any] = {
        "mode": "apply_reference_swap" if args.apply_reference_swap else "audit_only",
        "applied": False,
        "safety": {
            "server_inventory_modified": False,
            "account_entitlements_modified": False,
            "network_or_anticheat_modified": False,
            "runtime_injection": False,
            "texture_payload_replaced": False,
        },
        "records": [vars(r) for r in records],
        "readiness": readiness,
        "skipped": skipped,
        "record_summary": summarize_manifests(records),
        "plans": plans,
        "limitations": [
            "Static serialized reference analysis only; runtime equip/deformation is unverified.",
            "This prototype repoints m_Mesh; it does not author new vertex, weight, or bind-pose data.",
            "Skin bundles in this build contain Material/Texture objects only; no replacement Mesh was found there.",
        ],
    }

    if args.apply_reference_swap:
        if not args.renderer_pid or not args.mesh_pid:
            raise SystemExit("--apply-reference-swap requires --renderer-pid and --mesh-pid")
        # The orchestrator never writes the output asset on blocked,
        # needs_runtime_verification, or reference-drift conditions.
        fragment = apply_reference_swap(
            env,
            objs,
            args.renderer_pid,
            args.mesh_pid,
            out / "resources.assets",
        )
        report["applied"] = fragment["applied"]
        report["applied_plan"] = fragment.get("applied_plan")
        report["note"] = fragment.get("note")
        report["patch_file"] = fragment.get("patch_file")
        report["preserved_before"] = fragment.get("preserved_before")
        report["preserved_after"] = fragment.get("preserved_after")
        report["skipped"].extend(fragment.get("skipped", []))

    (out / "mesh_swap_plan_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "mode": report["mode"],
        "applied": report["applied"],
        "records": len(records),
        "plans": len(plans),
        "blocked": sum(1 for p in plans if p["status"] == "blocked"),
        "skipped": len(skipped),
    }, ensure_ascii=False))
    print(f"[OK] Report: {out / 'mesh_swap_plan_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
