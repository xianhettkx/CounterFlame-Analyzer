# Stock IL2CPP inventory/cosmetic metadata cross-check

Date: 2026-11-14
Source: reference IPA's extracted `global-metadata.dat` (11,669,008 bytes), read-only printable-string scan.

## Relevant stock-game identifiers found

The metadata string table contains the following identifiers (names only; the scan does not recover method bodies or prove call order):

### Inventory and player data
- `PrefsInventoryData`
- `InventoryEquip`
- `InventoryTile`
- `InventorySelect`
- `InventoryController`
- `AddInventoryItems`
- `RemoveLocalInventoryItem`
- `EditInventoryItem`
- `InventoryManager`

### Skin and cosmetic resolution
- `GetSkin`
- `GetSkinUid`
- `GetSkinDefenition` (spelling as present in metadata)
- `IsVanillaSkin`
- `SetSkinName`
- `SetGloves`
- `ApplyWeaponMaterial`
- `TryGetSkin`
- `LoadSkin`
- `RememberSkin`
- `ApplyStickers`
- `GetSkinnedRenderers`

### Catalog and presentation
- `WeaponCatalog`
- `SkinIndex`
- `_skinMaterials`
- `_nearSkins`
- `_farSkins`
- `WeaponMaterialManager`
- `InventoryTile`
- `InventorySelect`
- `InventoryEquip`

## Cross-check against the reference extension

The separate reference dylib contains these matching or complementary names:
- `InventoryManager`, `InventoryController`, `PrefsInventoryData`
- `CreateItems`, `NormalizeEquipMarkers`, `OfflineEquip`, `AddInventoryItems`
- `Visualize`, `SetWeapon`, `SetSkin`, `GetSkin`
- `inventory-config-v5.json`, `inventoryRaw`, `equipmentPreferences`
- `CFKAlert551PersistentInventoryInitializedV5`

This overlap is consistent with the extension integrating with the game's existing inventory and cosmetic presentation layer. It is not sufficient to identify exact signatures, parameter layouts, invocation points, or safe patch locations.

## Engineering conclusion

A skin display requires more than swapping a texture file. The stock game appears to have a catalog/definition layer, equipped-item state, and a material application layer. A safe local-preview prototype should keep virtual item state isolated from account/server inventory and feed only a clearly marked preview path. First validate one existing stock catalog item in an isolated preview; then test a single cosmetic material assignment; only after that consider broader catalog support.

No executable code was modified and no server state, entitlement, matchmaking, anti-cheat, gameplay parameters, or account state was changed. This report is static metadata/string evidence, not a decompilation or runtime verification.
