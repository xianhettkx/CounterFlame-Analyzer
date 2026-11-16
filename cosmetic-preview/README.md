# Local Cosmetic Preview — implementation status

This branch contains a standalone, offline-only preview sandbox. It is intentionally not a game patch and does not change the game's inventory, entitlements, account state, network traffic, matchmaking, or anti-cheat behavior.

## Verified source asset map

The repository's static audit of the stock 1.4.1 build identified these model/material relationships:

| Preview item | First-person base mesh | Preview texture |
|---|---|---|
| Butterfly Knife — Marble Fade | `v_knife_t_v_knife_flip_reference` | `butterfly_marblefade_cs2.png` |
| Specialist Gloves — Pillow Punchers | `v_glove_ct_specialist` | `glove_specialist_left` |
| AWP — Dragon Lore | `v_snip_awp_awp_model` | `awp_dragonlore_cs2.png` |
| AK-47 — Neon Revolution | `v_rif_ak47_reference1` | `ak47_neonrevolution_cs2.png` |
| M4A4 — The Emperor | `v_rif_m4a1_reference1` | `m4a4_emperor_cs2.png` |
| Desert Eagle — Code Red | `v_pist_deagle_deagle_model` | `deagle_codered_cs2.png` |

These are static asset associations, not proof of runtime equip support. The source audit notes that OBJ exports omit Unity rigging, bind poses, animation, and original material assignments. The current preview should therefore be treated as a visual study, not a drop-in game asset.

## Current prototype

Open `index.html` in a browser. It supports local image import, display-slot labels, color studies, and local JSON presets. User-selected files are read in the browser and are not uploaded.

## Next safe milestones

1. Add a local 3D viewer for user-supplied GLB/GLTF assets.
2. Add per-item preview metadata and texture-slot notes.
3. Validate static previews on iPhone Safari.
4. Keep any game integration out of scope unless an official, documented modding interface explicitly permits it.

## Explicit exclusions

- No fake inventory or fabricated ownership.
- No bypass of paid cosmetics, entitlements, or server authorization.
- No third-party tweak/dylib transplant or runtime injection.
- No aim assistance, wall visibility, recoil/damage manipulation, or other gameplay cheats.
