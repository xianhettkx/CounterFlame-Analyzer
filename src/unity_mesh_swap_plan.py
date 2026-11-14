"""Static model-swap plan and invariant checks for CounterFlame target weapons.

This module deliberately separates the *decision logic* (pure Python, testable
without UnityPy) from the UnityPy adapter that reads serialized objects from an
IPA. A model swap here means repointing a renderer's ``m_Mesh`` reference to a
different Mesh object; it is not a texture override.

Scope boundaries (enforced by design):
- No server inventory, entitlement, matchmaking, anti-cheat, network, or
  runtime-injection code is touched.
- The plan only proposes reference-level changes inside a local serialized file.
- Animation clips, the Avatar, bone Transforms, the renderer's GameObject and
  its Transform hierarchy are treated as references that must be preserved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# Only this plan status may enter the in-memory rewrite / serialization path.
# ``needs_runtime_verification`` must never be auto-promoted to writable.
APPLY_WRITABLE_PLAN_STATUS = "reference_swap_eligible"

# Reference fields that a mesh swap must NOT rewrite. Kept here so the report
# and the prototype can list the same invariant surface.
PRESERVED_REFERENCES = (
    "m_GameObject",
    "m_Bones",
    "m_RootBone",
    "Transform.m_Father",
    "Transform.m_Children",
    "Animator.m_Controller",
    "Avatar",
    "m_Materials",  # preserved unless an explicit material remap is planned separately
)


@dataclass
class MeshModelRecord:
    """Static facts about a Mesh serialized object and its owning renderer."""

    mesh_path_id: int
    mesh_name: str
    renderer_type: str  # MeshFilter | SkinnedMeshRenderer
    skin_key: str = ""
    side: str = ""
    gameobject_name: str = ""
    vertex_count: int = 0
    uv_count: int = 0
    weight_entries: int = 0
    bone_indices_entries: int = 0
    bind_pose_count: int = 0
    submesh_count: int = 0
    renderer_bone_count: int = 0
    renderer_owner_count: int = 0
    renderer_bone_names: list[str] = field(default_factory=list)
    bind_pose_signature: str = ""
    root_bone_name: str = ""
    material_names: list[str] = field(default_factory=list)
    mesh_is_readable: Optional[bool] = None
    notes: list[str] = field(default_factory=list)

    @property
    def is_skinned(self) -> bool:
        return self.renderer_type == "SkinnedMeshRenderer"


@dataclass
class CheckResult:
    check: str
    passed: bool
    detail: str


@dataclass
class SwapPlan:
    source_mesh: MeshModelRecord
    target_renderer: MeshModelRecord
    checks: list[CheckResult] = field(default_factory=list)
    preserved_references: tuple[str, ...] = PRESERVED_REFERENCES
    status: str = "blocked"  # blocked | reference_swap_eligible | needs_runtime_verification

    @property
    def blocking_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


def _check(plan: SwapPlan, check: str, passed: bool, detail: str) -> None:
    plan.checks.append(CheckResult(check=check, passed=passed, detail=detail))


def mesh_role(mesh_name: str) -> str:
    """Conservative role classifier; never equate body, magazine, drop, or view models."""
    name = (mesh_name or "").strip().lower()
    if "mag" in name:
        return "magazine"
    if "drop" in name:
        return "dropped_weapon"
    if name.startswith("tps_"):
        return "third_person_weapon"
    if name.startswith("w_"):
        return "world_weapon"
    if name.startswith("v_"):
        return "first_person_weapon"
    return f"unclassified:{name}"


def evaluate_swap(source: MeshModelRecord, target: MeshModelRecord) -> SwapPlan:
    """Compare a candidate source Mesh against the renderer it would replace.

    ``source`` is the Mesh that would be referenced; ``target`` describes the
    existing base renderer/Mesh being replaced.
    """
    plan = SwapPlan(source_mesh=source, target_renderer=target)

    _check(
        plan,
        "renderer_family",
        source.renderer_type == target.renderer_type,
        f"source={source.renderer_type} target={target.renderer_type}",
    )

    _check(
        plan,
        "renderer_side_match",
        not source.side or not target.side or source.side == target.side,
        f"source side={source.side or 'unknown'} target side={target.side or 'unknown'}",
    )

    source_role = mesh_role(source.mesh_name)
    target_role = mesh_role(target.mesh_name)
    _check(
        plan,
        "mesh_role_match",
        source_role == target_role,
        f"source role={source_role} target role={target_role}",
    )

    _check(
        plan,
        "submesh_material_alignment",
        source.submesh_count == 0 or source.submesh_count == len(source.material_names)
        or source.submesh_count == target.submesh_count,
        f"source submeshes={source.submesh_count} materials={len(source.material_names)}; "
        f"target submeshes={target.submesh_count} materials={len(target.material_names)}",
    )

    if target.is_skinned:
        _check(
            plan,
            "source_has_skin_weights",
            source.weight_entries > 0,
            f"source weight_entries={source.weight_entries}",
        )
        _check(
            plan,
            "bone_count_match",
            source.renderer_bone_count == target.renderer_bone_count,
            f"source bones={source.renderer_bone_count} target bones={target.renderer_bone_count}",
        )
        _check(
            plan,
            "bindpose_count_match",
            source.bind_pose_count == target.bind_pose_count,
            f"source bindposes={source.bind_pose_count} target bindposes={target.bind_pose_count}",
        )

        _check(
            plan,
            "bone_order_match",
            bool(source.renderer_bone_names and target.renderer_bone_names)
            and source.renderer_bone_names == target.renderer_bone_names,
            "ordered renderer bone names match"
            if source.renderer_bone_names and target.renderer_bone_names
            and source.renderer_bone_names == target.renderer_bone_names
            else "ordered renderer bone names differ or could not be fully resolved",
        )
        _check(
            plan,
            "bindpose_data_match",
            bool(source.bind_pose_signature and target.bind_pose_signature)
            and source.bind_pose_signature == target.bind_pose_signature,
            "bind-pose matrix signatures match"
            if source.bind_pose_signature and target.bind_pose_signature
            and source.bind_pose_signature == target.bind_pose_signature
            else "bind-pose matrix signatures differ or could not be computed",
        )
        _check(
            plan,
            "root_bone_present",
            bool(target.root_bone_name),
            f"target root bone={target.root_bone_name!r}",
        )
    else:
        _check(
            plan,
            "static_attachment_via_transform",
            True,
            "MeshFilter attachment is resolved through the parent Transform hierarchy; "
            "no per-vertex skin weights are required, but the world attach point must be preserved.",
        )

    # Readability is an informational flag, not a blocker for a reference swap:
    # stripped iOS meshes are commonly m_IsReadable=false yet still render from
    # streamed data. A missing/decode-failed stream is recorded in notes instead.
    _check(
        plan,
        "readable_geometry",
        True,
        f"source m_IsReadable={source.mesh_is_readable}",
    )

    if plan.blocking_checks:
        plan.status = "blocked"
    elif target.is_skinned:
        # Bone order, bind-pose correctness and deformation can only be confirmed
        # on an actual device/editor session; static serialization is not enough.
        plan.status = "needs_runtime_verification"
    else:
        plan.status = "reference_swap_eligible"

    return plan


def record_readiness(record: MeshModelRecord) -> tuple[str, list[str]]:
    """Single-record static gate. Returns (status, reasons).

    A record is ``blocked`` when a structural gate fails; such records must be
    skipped by any apply path and must not be force-swapped. ``needs_runtime_verification``
    means the static layout looks consistent but deformation/attach point still
    need on-device or editor confirmation.
    """
    reasons: list[str] = []

    if record.renderer_type not in ("MeshFilter", "SkinnedMeshRenderer", "MeshRenderer"):
        reasons.append(f"unknown renderer type: {record.renderer_type}")

    if record.is_skinned and record.weight_entries <= 0:
        reasons.append(
            "skinned renderer but decoded skin weight entries are 0; "
            "skeleton binding cannot be verified from serialized data"
        )

    if record.renderer_owner_count > 1:
        reasons.append(
            f"mesh is referenced by {record.renderer_owner_count} renderer owners; "
            "the exact renderer/skeleton instance must be selected before any swap"
        )

    if not record.material_names:
        reasons.append("no material slot resolved on the renderer or its sibling MeshRenderer")

    if record.is_skinned and record.bind_pose_count == 0:
        reasons.append("skinned mesh has no bind poses")

    if record.is_skinned and record.renderer_bone_count == 0:
        reasons.append("skinned renderer has no bone Transform references")

    for note in record.notes:
        if note.startswith("MeshHandler"):
            reasons.append(f"geometry stream decode failed: {note}")

    if reasons:
        return "blocked", reasons
    if record.is_skinned:
        return "needs_runtime_verification", []
    return "eligible_for_reference_review", []


def readiness_allows_apply(status: str) -> bool:
    """A single-record readiness status that may feed the apply gate.

    ``blocked`` always fails. ``needs_runtime_verification`` and
    ``eligible_for_reference_review`` are not blocked on static facts, but the
    pair plan still has to reach ``reference_swap_eligible`` before any write.
    """
    return status != "blocked"


def summarize_manifests(records: list[MeshModelRecord]) -> dict[str, Any]:
    """Compact JSON-friendly summary used by the prototype report."""
    return {
        "record_count": len(records),
        "skinned": [r.mesh_path_id for r in records if r.is_skinned],
        "static_filter": [r.mesh_path_id for r in records if not r.is_skinned],
        "preserved_references": list(PRESERVED_REFERENCES),
    }
