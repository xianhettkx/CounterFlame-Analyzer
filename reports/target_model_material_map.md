# CounterFlame 1.4.1 — Target model and skin material map

## Scan identity

- IPA SHA-256: `6c3e740ca379c5daf55f635e1228414230ca4acb7608cd7b35f7f5c0e0d952d3`
- Unity version: `2021.3.45f1`
- Physical UnityFS bundles: 1,941 decoded, 0 failures
- Non-bundle Unity asset candidates: 47 decoded
- AssetBundle dependency edges: 2,969 / 2,969 resolved to physical IPA entries
- Main model resource file: `Payload/CounterFlame.app/Data/resources.assets`

All Mesh path IDs below are scoped to this exact IPA and `resources.assets`; they are not portable IDs for another build.

## Base model assignments

| Target skin | GameObject / renderer | Mesh object (path ID) | Existing base material |
|---|---|---|---|
| Butterfly Knife | Marble Fade | `v_knife_t_v_knife_flip_reference` / SkinnedMeshRenderer | `v_knife_t_v_knife_flip_reference` (2233) | `knife_flip`; `flipknife_vanilla_tps_Diffuse` |
| Butterfly Knife | Marble Fade | `Butterfly` / MeshFilter | `tps_Butterfly` (2048) | `butterfly_vanilla_tps_Diffuse` |
| AWP | Dragon Lore | `v_snip_awp_awp_model` / SkinnedMeshRenderer | `v_snip_awp_awp_model` (2114) | `awp`, `awpScope` |
| AWP | Dragon Lore | `v_snip_awp_reference` / SkinnedMeshRenderer | `v_snip_awp_reference` (2032) | `awp_pbr`, `scope_lens` |
| AWP | Dragon Lore | `AWP02515` / MeshFilter | `tps_AWP02515` (2045) | `awp_Diffuse` / `agent_awp_Diffuse`, scope material |
| AWP | Dragon Lore | `w_snip_awp` / MeshFilter | `w_snip_awp` (1980) | `awp_pbr`, `scope_lens` |
| AK-47 | Neon Revolution | `v_rif_ak47_reference` / SkinnedMeshRenderer | `v_rif_ak47_reference` (2014; duplicate reference 2122) | `ak47_default_PBR` |
| AK-47 | Neon Revolution | `v_rif_ak47_reference1` / SkinnedMeshRenderer | `v_rif_ak47_reference1` (2231) | `ak47_default_PBR` |
| AK-47 | Neon Revolution | `v_rif_ak47_reference2` / SkinnedMeshRenderer | `v_rif_ak47_reference2` (1908) | `ak47_default_PBR` |
| AK-47 | Neon Revolution | `AK47` / MeshFilter | `tps_AK47` (2043) | `ak47_default_tps_Diffuse` |
| M4A4 | The Emperor | `v_rif_m4a1_reference1` / SkinnedMeshRenderer | `v_rif_m4a1_reference1` (1926) | `m4a4` |
| M4A4 | The Emperor | `v_rif_m4a1_reference2` / SkinnedMeshRenderer | `v_rif_m4a1_reference2` (1930) | `m4a4` |
| M4A4 | The Emperor | `v_rif_m4a1_reference3` / SkinnedMeshRenderer | `v_rif_m4a1_reference3` (1916) | `m4a4` |
| M4A4 | The Emperor | `v_rif_m4a1_reference4` / SkinnedMeshRenderer | `v_rif_m4a1_reference4` (1931) | `m4a4` |
| M4A4 | The Emperor | `M4A402100` / MeshFilter | `tps_M4A402100` (2062) | `m4a4_Diffuse` / `agent_m4a4_Diffuse` |
| M4A4 | The Emperor | `w_rif_m4a1` / MeshFilter | `w_rif_m4a1` (1978) | `m4a4` |
| Desert Eagle | Code Red | `v_pist_deagle_deagle_model` / SkinnedMeshRenderer | `v_pist_deagle_deagle_model` (2112) | `pist_deagle` |
| Desert Eagle | Code Red | `v_pist_deagle_reference` / SkinnedMeshRenderer | `v_pist_deagle_reference` (1953) | `pist_deagle` |
| Desert Eagle | Code Red | `Deagle00400` / MeshFilter | `tps_Deagle00400` (2050) | `pist_deagle_Diffuse` |
| Desert Eagle | Code Red | `w_pist_deagle` / MeshFilter | `w_pist_deagle` (1974) | `pist_deagle` |
| Specialist Gloves | Pillow Punchers | `v_glove_ct_specialist` / SkinnedMeshRenderer | `v_glove_ct_specialist` (2000, 2215, 2216, 2217) | `glove_specialist_left`, `glove_specialist_right` plus hand material |
| Specialist Gloves | Pillow Punchers | `v_glove_ct_specialist_ct` / SkinnedMeshRenderer | `v_glove_ct_specialist_ct` (2115) | `glove_specialist_left`, `glove_specialist_right`, `cthand` |

## Skin material texture bindings

The property names below are read from each Unity Material's `m_SavedProperties.m_TexEnvs`; the referenced CAB IDs were resolved through the bundle dependency graph to the physical IPA paths.

### Butterfly Knife | Marble Fade

- Material objects: `butterfly_marblefade_Diffuse`, `butterfly_marblefade_Specular`, `butterfly_marblefade_PBR`
- `_MainTex`: `butterfly_marblefade_paint.png` (Diffuse/Specular); `butterfly_marblefade_cs2.png` (PBR)
- `_PaintPattern`: shared `smoke2.png`
- `_SpecGlossMap`: `butterfly_butterfly_marblefade__cs2_mask.png`

### Specialist Gloves | Pillow Punchers

- Material objects: `specialist_pillow_Diffuse`, `specialist_pillow_Specular`, `specialist_pillow_PBR`
- `_MainTex`: `glove_specialist_left`
- `_BumpMap`: `glove_specialist_left_normal`
- `_SpecGlossMap`: `gloves_specialist_bigswell_mask.png`

### AWP | Dragon Lore

- Material objects: `awp_dragonlore_Diffuse`, `awp_dragonlore_Specular`, `awp_dragonlore_PBR`
- `_MainTex`: `awp_dragonlore_cs2.png`
- `_BumpMap`: shared `awp_normal.png`
- `_SpecGlossMap`: `awp_awp_dragonlore__cs2_mask.png`

### AK-47 | Neon Revolution

- Material objects: `ak47_neonrevolution_Diffuse`, `ak47_neonrevolution_Specular`, `ak47_neonrevolution_PBR`
- `_MainTex`: `ak47_neonrevolution_cs2.png`
- `_BumpMap`: shared `ak47_normal.png`
- `_SpecGlossMap`: `ak47_ak47_neonrevolution__cs2_mask.png`

### M4A4 | The Emperor

- Material objects: `m4a4_emperor_Diffuse`, `m4a4_emperor_Specular`, `m4a4_emperor_PBR`
- `_MainTex`: `m4a4_emperor_cs2.png` (PBR/Specular); local `m4a4_emperor_cs2_low` (Diffuse)
- `_SpecGlossMap`: `m4a1_m4a4_emperor__cs2_mask.png`

### Desert Eagle | Code Red

- Material objects: `deagle_codered_Diffuse`, `deagle_codered_Specular`, `deagle_codered_PBR`
- `_MainTex`: `deagle_codered_cs2.png`
- `_BumpMap`: `deagle_codered_cs2_normal.png`
- `_SpecGlossMap`: `deserteagle_deagle_codered__cs2_mask.png`

## Interpretation limits

- This establishes static serialized Mesh, renderer, Material, Texture2D, and CAB dependency references inside this IPA.
- It does not prove that a particular skin is loaded, equipped, or rendered in a live match.
- The skin-specific MonoBehaviour records exist, but their custom typetrees could not be decoded reliably with the available metadata.
- No IPA contents were modified, rebuilt, injected, or re-signed.
