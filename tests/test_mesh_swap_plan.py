import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.unity_mesh_swap_plan import (
    MeshModelRecord,
    evaluate_swap,
    record_readiness,
    PRESERVED_REFERENCES,
)
from src import unity_mesh_swap_prototype as proto
from src.unity_mesh_swap_prototype import (
    ReferenceDriftError,
    apply_reference_swap,
    assert_no_reference_drift,
    atomic_write_bytes,
    decide_apply,
    snapshot_renderer_references,
    snapshot_animator_controller,
)


def glove(pid, bones, bind, weights=10050, materials=("glove_specialist_left", "glove_specialist_right")):
    return MeshModelRecord(
        mesh_path_id=pid,
        mesh_name=f"v_glove_ct_specialist_{pid}",
        renderer_type="SkinnedMeshRenderer",
        gameobject_name="v_glove_ct_specialist",
        vertex_count=10050,
        uv_count=10050,
        weight_entries=weights,
        bone_indices_entries=weights,
        bind_pose_count=bind,
        submesh_count=3,
        renderer_bone_count=bones,
        root_bone_name="v_weapon.Bip01_L_Forearm",
        material_names=list(materials),
        mesh_is_readable=True,
    )


def knife(pid, bones=56, weights=0):
    return MeshModelRecord(
        mesh_path_id=pid,
        mesh_name=f"v_knife_{pid}",
        renderer_type="SkinnedMeshRenderer",
        gameobject_name="v_knife_t_v_knife_flip_reference",
        vertex_count=3059,
        uv_count=3059,
        weight_entries=weights,
        bone_indices_entries=3059,
        bind_pose_count=56,
        submesh_count=1,
        renderer_bone_count=bones,
        root_bone_name="",
        material_names=["knife_flip"],
        mesh_is_readable=True,
    )


def static_filter(pid):
    return MeshModelRecord(
        mesh_path_id=pid,
        mesh_name=f"tps_Butterfly_{pid}",
        renderer_type="MeshFilter",
        gameobject_name="Butterfly",
        vertex_count=3741,
        submesh_count=1,
        material_names=["butterfly_vanilla_tps_Diffuse"],
        mesh_is_readable=False,
    )


class MeshSwapPlanTests(unittest.TestCase):
    def test_matching_skinned_pair_needs_runtime_verification(self):
        plan = evaluate_swap(glove(2217, 67, 67), glove(2000, 67, 67))
        self.assertEqual(plan.status, "needs_runtime_verification")
        self.assertEqual(plan.blocking_checks, [])
        self.assertIn("m_Bones", plan.preserved_references)
        self.assertIn("Animator.m_Controller", plan.preserved_references)

    def test_bone_count_mismatch_blocks(self):
        plan = evaluate_swap(glove(2217, 67, 67), glove(2215, 99, 99))
        self.assertEqual(plan.status, "blocked")
        self.assertTrue(any(c.check == "bone_count_match" and not c.passed for c in plan.checks))

    def test_source_without_skin_weights_blocked_for_skinned_target(self):
        plan = evaluate_swap(knife(2233, weights=0), glove(2217, 67, 67))
        self.assertEqual(plan.status, "blocked")
        self.assertTrue(any(c.check == "source_has_skin_weights" and not c.passed for c in plan.checks))

    def test_renderer_family_mismatch_blocks(self):
        plan = evaluate_swap(static_filter(2048), glove(2217, 67, 67))
        self.assertEqual(plan.status, "blocked")
        self.assertTrue(any(c.check == "renderer_family" and not c.passed for c in plan.checks))

    def test_static_filter_pair_is_reference_swap_eligible(self):
        plan = evaluate_swap(static_filter(2048), static_filter(2053))
        self.assertEqual(plan.status, "reference_swap_eligible")
        self.assertTrue(any(c.check == "static_attachment_via_transform" for c in plan.checks))

    def test_plan_record_carries_no_texture_payload_field(self):
        # A model-swap record must not be confused with a Texture2D override:
        # there is no image_data / payload byte field on the plan record.
        record = glove(2217, 67, 67)
        self.assertFalse(hasattr(record, "image_data"))
        self.assertFalse(hasattr(record, "m_Texture"))

    def test_preserved_references_cover_animation_and_hierarchy(self):
        for required in (
            "m_GameObject",
            "m_Bones",
            "m_RootBone",
            "Transform.m_Father",
            "Animator.m_Controller",
            "Avatar",
            "m_Materials",
        ):
            self.assertIn(required, PRESERVED_REFERENCES)

    def test_skinned_record_with_weights_passes_static_gate(self):
        status, reasons = record_readiness(glove(2217, 67, 67))
        self.assertEqual(status, "needs_runtime_verification")
        self.assertEqual(reasons, [])

    def test_skinned_record_without_decoded_weights_is_blocked(self):
        status, reasons = record_readiness(knife(2233, weights=0))
        self.assertEqual(status, "blocked")
        self.assertTrue(any("skin weight" in r for r in reasons))

    def test_decode_failure_is_blocked_not_force_swapped(self):
        broken = static_filter(2048)
        broken.notes.append("MeshHandler: Vertex data access out of bounds")
        status, reasons = record_readiness(broken)
        self.assertEqual(status, "blocked")
        self.assertTrue(any("decode" in r for r in reasons))

    def test_static_clean_record_is_reference_review_eligible(self):
        clean = static_filter(2053)
        clean.material_names = ["agent_ak47_default_tps_Diffuse"]
        status, reasons = record_readiness(clean)
        self.assertEqual(status, "eligible_for_reference_review")
        self.assertEqual(reasons, [])

    def test_missing_material_slot_is_blocked(self):
        no_mat = glove(2217, 67, 67)
        no_mat.material_names = []
        status, reasons = record_readiness(no_mat)
        self.assertEqual(status, "blocked")
        self.assertTrue(any("material slot" in r for r in reasons))


class ReferenceSnapshotTests(unittest.TestCase):
    @staticmethod
    def _ptr(pid):
        return SimpleNamespace(m_FileID=0, m_PathID=pid)

    def test_snapshot_captures_gameobject_bones_root_materials(self):
        data = SimpleNamespace(
            m_GameObject=self._ptr(10),
            m_Bones=[self._ptr(1), self._ptr(2)],
            m_RootBone=self._ptr(3),
            m_Materials=[self._ptr(4)],
        )
        snap = snapshot_renderer_references(data)
        self.assertEqual(snap["m_GameObject"], {"file_id": 0, "path_id": 10})
        self.assertEqual([b["path_id"] for b in snap["m_Bones"]], [1, 2])
        self.assertEqual(snap["m_RootBone"]["path_id"], 3)
        self.assertEqual([m["path_id"] for m in snap["m_Materials"]], [4])

    def test_bone_mutation_is_detected_as_reference_drift(self):
        data = SimpleNamespace(
            m_GameObject=self._ptr(10),
            m_Bones=[self._ptr(1), self._ptr(2)],
            m_RootBone=self._ptr(3),
            m_Materials=[self._ptr(4)],
        )
        before = snapshot_renderer_references(data)
        data.m_Bones = [self._ptr(99)]  # forbidden mutation
        after = snapshot_renderer_references(data)
        self.assertNotEqual(before, after)

    def _hierarchy(self, parent_animator_count=1):
        class Obj:
            def __init__(self, t, d):
                self.type = SimpleNamespace(name=t)
                self._d = d
            def read(self):
                return self._d

        def go(components):
            return SimpleNamespace(m_Component=[
                SimpleNamespace(component=self._ptr(pid)) for pid in components
            ])

        objs = {
            10: Obj("GameObject", go([11])),
            11: Obj("Transform", SimpleNamespace(
                m_GameObject=self._ptr(10), m_Father=self._ptr(21), m_Children=[]
            )),
            20: Obj("GameObject", go([21] + list(range(30, 30 + parent_animator_count)))),
            21: Obj("Transform", SimpleNamespace(
                m_GameObject=self._ptr(20), m_Father=self._ptr(0), m_Children=[self._ptr(11)]
            )),
        }
        for i in range(parent_animator_count):
            objs[30 + i] = Obj("Animator", SimpleNamespace(
                m_Controller=self._ptr(40 + i), m_Avatar=self._ptr(50 + i)
            ))
        return objs

    def test_animator_controller_snapshot_roundtrip(self):
        snapshot = snapshot_animator_controller(self._hierarchy(), 10)
        self.assertEqual([n["gameobject_path_id"] for n in snapshot["nodes"]], [10, 20])
        self.assertEqual(snapshot["nodes"][1]["animators"][0]["controller"],
                         {"file_id": 0, "path_id": 40})

    def test_parent_animator_is_captured_even_when_renderer_object_has_none(self):
        snapshot = snapshot_animator_controller(self._hierarchy(), 10)
        self.assertEqual(snapshot["nodes"][0]["animators"], [])
        self.assertEqual(len(snapshot["nodes"][1]["animators"]), 1)
        self.assertEqual(snapshot["nodes"][1]["animators"][0]["avatar"],
                         {"file_id": 0, "path_id": 50})

    def test_multiple_parent_animators_are_all_captured(self):
        snapshot = snapshot_animator_controller(self._hierarchy(parent_animator_count=2), 10)
        self.assertEqual(
            [a["controller"]["path_id"] for a in snapshot["nodes"][1]["animators"]],
            [40, 41],
        )

    def test_parent_animator_controller_drift_is_detected(self):
        objs = self._hierarchy()
        before = snapshot_animator_controller(objs, 10)
        objs[30]._d.m_Controller = self._ptr(999)
        after = snapshot_animator_controller(objs, 10)
        self.assertNotEqual(before, after)
        snap = {"m_GameObject": self._ptr(10), "m_Bones": [], "m_RootBone": None,
                "m_Materials": []}
        with self.assertRaises(ReferenceDriftError):
            assert_no_reference_drift(snap, snap, before, after)

    def test_parent_animator_drift_during_mesh_repoint_aborts(self):
        objs = self._hierarchy()
        class MutatingMeshRef:
            def __init__(self):
                self.m_FileID = 0
                self._path_id = 999
            @property
            def m_PathID(self):
                return self._path_id
            @m_PathID.setter
            def m_PathID(self, value):
                self._path_id = value
                objs[30]._d.m_Controller = _ptr(777)

        data = SimpleNamespace(
            m_GameObject=self._ptr(10), m_Bones=[], m_RootBone=None,
            m_Materials=[], m_Mesh=MutatingMeshRef(),
        )
        with self.assertRaises(ReferenceDriftError):
            proto.perform_reference_swap(data, objs, 400)
        self.assertEqual(data.m_Mesh.m_PathID, 400)

    def test_missing_transform_fails_closed(self):
        objs = self._hierarchy()
        objs[10]._d.m_Component = []
        with self.assertRaises(ReferenceDriftError):
            snapshot_animator_controller(objs, 10)

    def test_transform_parent_cycle_fails_closed(self):
        objs = self._hierarchy()
        objs[21]._d.m_Father = self._ptr(11)
        with self.assertRaises(ReferenceDriftError):
            snapshot_animator_controller(objs, 10)

    def test_atomic_replace_failure_preserves_existing_file(self):
        import os
        from unittest.mock import patch
        tmp = Path(tempfile.mkdtemp())
        target = tmp / "resources.assets"
        target.write_bytes(b"original")
        with patch.object(os, "replace", side_effect=OSError("simulated replace failure")):
            with self.assertRaises(OSError):
                atomic_write_bytes(target, b"replacement")
        self.assertEqual(target.read_bytes(), b"original")
        self.assertEqual([p.name for p in tmp.iterdir()], ["resources.assets"])


def _ptr(pid):
    return SimpleNamespace(m_FileID=0, m_PathID=pid)


class _FileData:
    """Stand-in for a UnityPy renderer object read in memory."""

    def __init__(self, go, bones, root, mats, mesh):
        self.m_GameObject = go
        self.m_Bones = bones
        self.m_RootBone = root
        self.m_Materials = mats
        self.m_Mesh = mesh
        self.saved = False

    def save(self):
        self.saved = True


class _Obj:
    def __init__(self, type_name, data=None, path_id=0):
        self.type = SimpleNamespace(name=type_name)
        self._data = data
        self.path_id = path_id

    def read(self):
        return self._data


class _Env:
    def __init__(self, payload=b"serialized-payload"):
        self.file = SimpleNamespace(save=lambda: payload)


def _build_world(renderer_pid, mesh_pid, data):
    go_pid, mat_pid = 100, 200
    transform_pid = 101
    objs = {
        go_pid: _Obj("GameObject", SimpleNamespace(m_Component=[
            SimpleNamespace(component=_ptr(transform_pid))
        ]), go_pid),
        transform_pid: _Obj("Transform", SimpleNamespace(
            m_GameObject=_ptr(go_pid), m_Father=_ptr(0), m_Children=[]
        ), transform_pid),
        mat_pid: _Obj("Material", SimpleNamespace(m_Name="mat"), mat_pid),
        renderer_pid: _Obj("MeshFilter", data, renderer_pid),
        mesh_pid: _Obj("Mesh", None, mesh_pid),
    }
    return objs, go_pid, mat_pid


class ApplyGateTests(unittest.TestCase):
    def test_decide_apply_eligible_static_pair(self):
        decision = decide_apply(static_filter(400), static_filter(999))
        self.assertTrue(decision["eligible"])
        self.assertEqual(decision["plan_status"], "reference_swap_eligible")
        self.assertEqual(decision["source_readiness"], "eligible_for_reference_review")
        self.assertEqual(decision["target_readiness"], "eligible_for_reference_review")

    def test_decide_apply_skinned_pair_not_promoted_to_eligible(self):
        decision = decide_apply(glove(2217, 67, 67), glove(2000, 67, 67))
        self.assertFalse(decision["eligible"])
        self.assertEqual(decision["plan_status"], "needs_runtime_verification")

    def test_decide_apply_blocked_source_collects_reasons(self):
        decision = decide_apply(knife(2233, weights=0), glove(2217, 67, 67))
        self.assertFalse(decision["eligible"])
        self.assertTrue(decision["reasons"])
        self.assertTrue(any("skin weight" in r for r in decision["reasons"]))

    def test_blocked_source_does_not_write_asset(self):
        tmp = Path(tempfile.mkdtemp())
        out = tmp / "resources.assets"
        data = _FileData(_ptr(100), [_ptr(1)], _ptr(2), [_ptr(200)], _ptr(999))
        objs, _, _ = _build_world(300, 400, data)
        fragment = apply_reference_swap(
            _Env(), objs, 300, 400, out,
            source_record=knife(2233, weights=0),
            target_record=glove(2217, 67, 67),
        )
        self.assertFalse(fragment["applied"])
        self.assertFalse(out.exists())
        self.assertEqual(fragment["applied_plan"]["status"], "blocked")
        self.assertTrue(fragment["skipped"][0]["reasons"])
        self.assertFalse(data.saved)

    def test_needs_runtime_verification_does_not_write_asset(self):
        tmp = Path(tempfile.mkdtemp())
        out = tmp / "resources.assets"
        data = _FileData(_ptr(100), [_ptr(1)], _ptr(2), [_ptr(200)], _ptr(999))
        objs, _, _ = _build_world(300, 400, data)
        fragment = apply_reference_swap(
            _Env(), objs, 300, 400, out,
            source_record=glove(2217, 67, 67),
            target_record=glove(2000, 67, 67),
        )
        self.assertFalse(fragment["applied"])
        self.assertFalse(out.exists())
        self.assertEqual(fragment["applied_plan"]["status"], "needs_runtime_verification")
        self.assertFalse(data.saved)

    def test_reference_drift_aborts_before_write(self):
        tmp = Path(tempfile.mkdtemp())
        out = tmp / "resources.assets"
        data = _FileData(_ptr(100), [], None, [_ptr(200)], _ptr(999))
        objs, _, _ = _build_world(300, 400, data)

        def _boom(*_a, **_k):
            raise ReferenceDriftError("bones drifted")

        original = proto.perform_reference_swap
        proto.perform_reference_swap = _boom
        try:
            with self.assertRaises(ReferenceDriftError):
                apply_reference_swap(
                    _Env(), objs, 300, 400, out,
                    source_record=static_filter(400),
                    target_record=static_filter(999),
                )
        finally:
            proto.perform_reference_swap = original
        self.assertFalse(out.exists())
        self.assertFalse(data.saved)

    def test_eligible_pair_writes_asset_atomically(self):
        tmp = Path(tempfile.mkdtemp())
        out = tmp / "resources.assets"
        data = _FileData(_ptr(100), [], None, [_ptr(200)], _ptr(999))
        objs, _, _ = _build_world(300, 400, data)
        fragment = apply_reference_swap(
            _Env(b"bin-payload"), objs, 300, 400, out,
            source_record=static_filter(400),
            target_record=static_filter(999),
        )
        self.assertTrue(fragment["applied"])
        self.assertTrue(out.exists())
        self.assertEqual(out.read_bytes(), b"bin-payload")
        # m_Mesh PPtr is repointed; no leftover temp file remains.
        self.assertEqual(data.m_Mesh.m_PathID, 400)
        self.assertTrue(data.saved)
        self.assertEqual([p.name for p in tmp.iterdir()], ["resources.assets"])

    def test_mesh_is_the_only_changed_reference(self):
        tmp = Path(tempfile.mkdtemp())
        out = tmp / "resources.assets"
        data = _FileData(_ptr(100), [_ptr(1), _ptr(2)], _ptr(3), [_ptr(4)], _ptr(999))
        objs, _, _ = _build_world(300, 400, data)
        fragment = apply_reference_swap(
            _Env(), objs, 300, 400, out,
            source_record=static_filter(400),
            target_record=static_filter(999),
        )
        self.assertEqual(fragment["preserved_before"], fragment["preserved_after"])
        for field in ("m_GameObject", "m_Bones", "m_RootBone", "m_Materials"):
            self.assertEqual(
                fragment["preserved_before"][field], fragment["preserved_after"][field]
            )
        # The renderer's current mesh PPtr is the only reference that moved.
        self.assertNotEqual(data.m_Mesh.m_PathID, 999)


class ReferenceGuardTests(unittest.TestCase):
    def test_identical_snapshots_pass(self):
        snap = {
            "m_GameObject": {"file_id": 0, "path_id": 10},
            "m_Bones": [{"file_id": 0, "path_id": 1}],
            "m_RootBone": {"file_id": 0, "path_id": 3},
            "m_Materials": [{"file_id": 0, "path_id": 4}],
        }
        assert_no_reference_drift(snap, snap, {"path_id": 30}, {"path_id": 30})

    def test_bone_mutation_is_detected(self):
        before = {
            "m_GameObject": {"file_id": 0, "path_id": 10},
            "m_Bones": [{"file_id": 0, "path_id": 1}],
            "m_RootBone": None,
            "m_Materials": [],
        }
        after = dict(before)
        after["m_Bones"] = [{"file_id": 0, "path_id": 99}]
        with self.assertRaises(ReferenceDriftError):
            assert_no_reference_drift(before, after, None, None)

    def test_material_mutation_is_detected(self):
        before = {"m_GameObject": None, "m_Bones": [], "m_RootBone": None,
                  "m_Materials": [{"path_id": 4}]}
        after = dict(before)
        after["m_Materials"] = [{"path_id": 77}]
        with self.assertRaises(ReferenceDriftError):
            assert_no_reference_drift(before, after, None, None)

    def test_animator_controller_mutation_is_detected(self):
        snap = {"m_GameObject": None, "m_Bones": [], "m_RootBone": None, "m_Materials": []}
        with self.assertRaises(ReferenceDriftError):
            assert_no_reference_drift(snap, snap, {"path_id": 30}, {"path_id": 31})

    def test_atomic_write_replaces_without_temp_left(self):
        tmp = Path(tempfile.mkdtemp())
        target = tmp / "a.bin"
        atomic_write_bytes(target, b"one")
        self.assertEqual(target.read_bytes(), b"one")
        atomic_write_bytes(target, b"two")
        self.assertEqual(target.read_bytes(), b"two")
        self.assertEqual([p.name for p in tmp.iterdir()], ["a.bin"])


if __name__ == "__main__":
    unittest.main()
