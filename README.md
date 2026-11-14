# CounterFlame Analyzer

A read-only IPA and Unity Addressables analysis project. The analyzer inventories IPA contents, inspects Addressables catalogs, validates target bundle paths, and produces reports. It does not modify the IPA or interact with game inventory authorization or anti-cheat systems.

## Status
Initial repository scaffold.

## Model-swap audit (branch `feature/mesh-swap-static-prototype`)

- `reports/mesh_model_audit.md` — full local Mesh/Material/Renderer/bone/Animator reference audit, with verified / inferred / unverified evidence levels.
- `src/unity_mesh_swap_plan.py` — offline swap-plan invariant checks (no UnityPy dependency).
- `src/unity_mesh_swap_prototype.py` — audit-only by default; gated `m_Mesh` reference-swap prototype. Does not author new mesh bytes, touch inventory/entitlements/network/anti-cheat, or rebuild bundles.
- Existing `unity_local_skin_patch.py` pipeline replaces Texture2D payloads only; it is not a model swap.
