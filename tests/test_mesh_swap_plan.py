import unittest
from types import SimpleNamespace

from src.unity_mesh_swap_plan import (
    MeshModelRecord,
    evaluate_swap,
    record_readiness,
    PRESERVED_REFERENCES,
)
from src.unity_mesh_swap_prototype import (
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

    def test_animator_controller_snapshot_roundtrip(self):
        go = SimpleNamespace(m_Component=[SimpleNamespace(component=self._ptr(20))])
        anim = SimpleNamespace(m_Controller=self._ptr(30))

        class Obj:
            def __init__(self, t, d):
                self.type = SimpleNamespace(name=t)
                self._d = d
            def read(self):
                return self._d

        objs = {10: Obj("GameObject", go), 20: Obj("Animator", anim)}
        controller = snapshot_animator_controller(objs, 10)
        self.assertEqual(controller, {"file_id": 0, "path_id": 30})


if __name__ == "__main__":
    unittest.main()
