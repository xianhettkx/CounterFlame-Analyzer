# CounterFlame target mesh export QA

## Scope

This QA checks the exported OBJ geometry and PNG texture files from the exact CounterFlame 1.4.1 IPA analyzed by this repository. It is a static export validation, not a runtime game test.

## Overall result

- OBJ meshes: 30
- Total OBJ face records: 224,004
- PNG textures: 22
- Texture dimensions: all 1024 × 1024 RGBA
- Every OBJ contains vertex positions, UV coordinates, and normals.
- The OBJ export currently has no original Unity material assignments embedded; the new `skin_previews/` package adds a clearly labeled single-albedo MTL preview per skin.

## Selected first-person preview meshes

| Skin | Mesh path ID | Vertices | Faces | OBJ groups |
|---|---:|---:|---:|---:|
| Butterfly Knife | Marble Fade | 2233 | 3,059 | 3,232 | 2 |
| Specialist Gloves | Pillow Punchers | 2217 | 10,050 | 16,400 | 4 |
| AWP | Dragon Lore | 2114 | 20,864 | 21,916 | 3 |
| AK-47 | Neon Revolution | 2014 | 12,179 | 13,069 | 2 |
| M4A4 | The Emperor | 1926 | 4,060 | 3,567 | 2 |
| Desert Eagle | Code Red | 2112 | 10,315 | 8,829 | 2 |

## Texture preview bindings

| Skin | Selected main-color texture |
|---|---|
| Butterfly Knife | Marble Fade | `butterfly_marblefade_cs2` |
| Specialist Gloves | Pillow Punchers | `glove_specialist_left` |
| AWP | Dragon Lore | `awp_dragonlore_cs2` |
| AK-47 | Neon Revolution | `ak47_neonrevolution_cs2` |
| M4A4 | The Emperor | `m4a4_emperor_cs2` |
| Desert Eagle | Code Red | `deagle_codered_cs2` |

## UV and material caveats

- Some source UV coordinates are outside the 0–1 range (including negative V values and values above 1). They are preserved from UnityPy's mesh export rather than normalized. OBJ/MTL viewers generally repeat textures by default; the preview MTL therefore uses the texture as a repeatable albedo map.
- This is a single-albedo preview only. It does not reproduce Unity's shader graph, texture transforms, normal maps, masks, specular/roughness response, transparent scope materials, or lighting.
- A few meshes include multiple OBJ groups/submeshes. The preview applies one selected albedo to all groups, so small secondary components may look incorrect.
- OBJ is static geometry: it does not preserve the Unity skeleton, skin weights, bind poses, or animation clips. Those remain documented separately in `unity_rig_animation_map.json`.
- The custom skin material references were identified in skin-specific bundles; the base weapon meshes and renderer bindings are stored in shared serialized assets. The preview combines these two statically verified sides for inspection only. It does not alter or rebuild the IPA.

## Conclusion

The exported files are suitable for static UV and silhouette inspection. They are not a drop-in replacement bundle and do not establish that a skin can be equipped or rendered in a live match.
