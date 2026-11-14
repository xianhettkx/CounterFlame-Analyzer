# CounterFlame reference IPA — native inventory and skin runtime findings

Source: read-only static string audit of the reference IPA's added
`CounterFlameKAlert551.dylib` (600,544 bytes; SHA-256
`8b7ff814bddbd0b7a2d15d98b7419055e8ebfa1938ff5a3ecef43e44c9b364fe`).
No binary was executed or modified.

## High-confidence observations

The dylib contains Unity IL2CPP reflection entry points and game type names:

- `ScarletWork.Inventory`, `ScarletWork.Arsenal`, `InventoryManager`,
  `InventoryController`, `PrefsInventoryData`, `PrefsPlayerData`,
  `PlayerPrefs`, `Inventory`.
- Inventory method names: `GetInventory`, `SetInventory`,
  `ClearInventory`, `CreateItems`, `NormalizeEquipMarkers`,
  `AddInventoryItems`.
- Weapon/cosmetic method names: `Visualize`, `SetWeapon`, `SetSide`,
  `SetSkin`, `GetSkin`, `GetStatTrak`, `GetStickers`.
- Native inventory markers: `CFKAlert551NativeInventoryEnabledV4`,
  `CFKAlert551NativeInventoryOriginalRawV4`, `cf-local-preview`,
  `CFKAlert551LastCosmetic`.
- Inventory config names: `inventory-config-v5.json`,
  `CounterFlame.KAlert551.InventoryConfig.v5`, `inventoryRaw`,
  `equipmentPreferences`, `catalogCount`, `enabled`.

This is strong evidence that the injected library contains a local inventory/cosmetic
integration layer which calls into the game's IL2CPP inventory and weapon APIs.
It is not merely a texture replacement.

## Runtime restoration evidence

The dylib includes these exact diagnostic strings:

- `[CF-KAlert551] configuration snapshot saved (%@)`
- `[CF-KAlert551] menu/ready weapon preview rebound after equipment update`
- `[CF-KAlert551] cold-start skin restore complete: inventory=%lu preview=%lu attempts=%lu`
- `[CF-KAlert551] round weapon skin reapplied: %@ state=%d pass=%lu`
- `[CF-KAlert551] training cosmetic snapshot restored`
- `[CF-KAlert551] complete catalog indexed: %lu unique item definitions`

The strings indicate intended persistence, catalog indexing, menu preview rebinding,
startup restoration, and round-state reapplication. Static strings do not prove
that each code path succeeds in a live game.

## Floating UI and category labels

The dylib contains `allInventoryButton`, `allInventory`, `inventory`,
`page`, `detail`, and `option`, plus visible category labels:

- `Weapons`
- `Knives`
- `Gloves`
- `Paints`
- `Cases`
- `Cards`

It also contains Objective-C UI members for `UIButton`, `UITableView`,
`closeButton`, `positionButton`, `opacitySlider`, and `allInventoryButton`.
This is consistent with a floating control panel and a separate inventory browser.

## Chinese-language evidence

The dylib contains these exact strings:

- `[CF-AutoFill] Simplified Chinese language slot persisted before Unity startup`
- `[CF-AutoFill] selected localized language slot 0`
- `[CF-AutoFill] Simplified Chinese UI.Text font=%lu translated=%lu`
- `[CF-AutoFill] resolved built-in Simplified-Chinese compatible font`
- `[CF-AutoFill] Simplified Chinese translated %lu TextMeshPro objects`
- `notosanssc`, `notosanscjksc`, `pingfang`, `heiti`

This supports the presence of a Chinese-language selection/translation routine and
font fallback logic inside the plugin. It does not establish translation coverage
or prove that every game screen is translated.

## Existing local skin assets

The stock IPA already contains the six requested skin bundle families and their
texture/material assets. The separately generated target material map identifies
the following first-person model/renderer groups:

| Skin | Base model family |
|---|---|
| Butterfly Knife — Marble Fade | `v_knife_t_v_knife_flip_reference` |
| Specialist Gloves — Pillow Punchers | `v_glove_ct_specialist` |
| AWP — Dragon Lore | `v_snip_awp_awp_model`, `v_snip_awp_reference` |
| AK-47 — Neon Revolution | `v_rif_ak47_reference*` |
| M4A4 — The Emperor | `v_rif_m4a1_reference1..4` |
| Desert Eagle — Code Red | `v_pist_deagle_deagle_model`, `v_pist_deagle_reference` |

The skin material bundles and the shared base weapon renderers are separate
resource relationships. Replacing only a texture cannot reproduce the runtime
inventory/equip behavior.

## Safe next implementation boundary

For a local visual-only build, keep the analysis and any future changes limited to:

1. Read-only catalog inspection and local asset mapping.
2. A standalone local preview/inventory configuration for the six named cosmetics.
3. Texture/material preview and language-resource analysis.
4. Validation that no server inventory, account entitlement, matchmaking, anti-cheat,
   aim, recoil, damage, device identity, or remote verification behavior is altered.

Do not transplant the third-party dylib wholesale: its strings also expose unrelated
combat manipulation, device identity, remote verification, and Telegram binding
features. This report intentionally does not reconstruct or reproduce those paths.

## Limits

This report is based on printable strings and static Unity asset metadata. It does not
disassemble native control flow, establish exact button-to-method call paths, or prove
runtime behavior. The strings are evidence of compiled identifiers/log messages, not
a substitute for executing the game.
