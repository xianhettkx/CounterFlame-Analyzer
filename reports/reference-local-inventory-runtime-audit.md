# Reference local-inventory runtime audit

Date: 2026-11-14

## Acquisition and verification

- Reference IPA: `CS2._1.4.1_.5.8.78.2.ipa`
- Expected and verified IPA SHA-256: `7b20f04d493c60cf5e215c0a82050fa691105fc47a0748e46e55cc3078f9cc9f`
- GitHub Actions run: `43598083409` — completed successfully.
- Evidence artifact: `reference-inventory-runtime-evidence`, artifact ID `14114894188`.
- Extracted dylib: `Payload/CounterFlame.app/Frameworks/CounterFlameKAlert551.dylib`, 600,544 bytes, SHA-256 `8b7ff814bddbd0b7a2d15d98b7419055e8ebfa1938ff5a3ecef43e44c9b364fe`.
- Extracted IL2CPP metadata: `Payload/CounterFlame.app/Data/Managed/Metadata/global-metadata.dat`, 11,669,008 bytes.
- Extracted UnityFramework: 66,461,632 bytes.
- Extracted app Info.plist: 2,132 bytes.

## What the static evidence supports

The reference dylib contains printable strings naming an inventory integration layer, including:

- Namespaces/types: `ScarletWork.Inventory`, `ScarletWork.Arsenal`, `ArsenalCollection`, `PrefsInventoryData`, `InventoryManager`, `InventoryController`.
- Inventory operations: `GetInventory`, `SetInventory`, `ClearInventory`, `CreateItems`, `NormalizeEquipMarkers`, `OfflineEquip`, `AddInventoryItems`.
- Cosmetic/preview operations: `Visualize`, `SetWeapon`, `SetSkin`, `GetSkin`, `GetStatTrak`, `GetStickers`.
- Local persistence/config markers: `PlayerPrefs`, `cf-local-preview`, `inventory-config-v5.json`, `inventoryRaw`, `equipmentPreferences`, `CFKAlert551PersistentInventoryInitializedV5`.
- Preview restoration log strings mention cold-start restore, menu/ready weapon preview rebinding, and round weapon skin reapplication.

The original game's IL2CPP metadata also contains inventory and cosmetic-related names such as `Inventory`, `AddInventoryItems`, `RemoveLocalInventoryItem`, `EditInventoryItem`, `SetGloves`, `ApplyWeaponMaterial`, `ApplyStickers`, `InventoryTile`, `InventorySelect`, and `InventoryEquip`. This suggests the game already has native inventory and cosmetic presentation systems that the reference extension interacts with.

## Important limits

This is static string/metadata evidence, not proof of executed behavior. No runtime tracing, full control-flow reconstruction, or on-device test was performed. It does not establish that a particular method is safe to call or that a copied binary would work in the stock app.

The reference dylib is a third-party modification module and contains unrelated features and integrations. Do not transplant the dylib wholesale. This audit does not alter the IPA, server inventory, entitlements, matchmaking, anti-cheat, gameplay values, device identity, or remote verification.

## Safe next engineering step

Build a separate local-only cosmetic preview prototype using the stock game's existing model/material catalog and an isolated preview data source. Keep it read-only with respect to account/server inventory and clearly label virtual items as local preview. First validate one cosmetic in a standalone preview scene; expand to the catalog only after the rendering path and compatibility are verified. Do not patch the live client binary until there is a documented, authorized integration point and a reproducible test.

## Mach-O linkage check (2026-11-14)

A follow-up extraction run completed successfully:

- GitHub Actions run: `43598690232` — success.
- Evidence artifact: `reference-inventory-runtime-evidence`, artifact ID `14115396427`.
- The reference app executable `CounterFlame` contains an `LC_LOAD_DYLIB` entry for `@executable_path/Frameworks/CounterFlameKAlert551.dylib`.
- The referenced dylib is present at that exact bundle-relative path in the IPA.
- The dylib's own `LC_ID_DYLIB` install-name string is `/Library/MobileSubstrate/DynamicLibraries/CounterFlameKAlert551.dylib`.

**Interpretation:** the app executable explicitly declares a direct dynamic-library dependency on the bundled dylib. Therefore, the earlier assumption that the module must be loaded only by an external MobileSubstrate injector is not supported. The MobileSubstrate path is the dylib's install-name identity; it does not override the executable's `@executable_path/Frameworks` load command. This static result still does not prove successful runtime loading, signing validity, or execution on a non-jailbroken device.

The linkage JSON is included in artifact `14115396427` as `macho-linkage-analysis.json`. The corrected parser was validated by a successful Actions run.

## Stock-versus-reference executable linkage comparison (2026-11-14)

A separate workflow downloaded and SHA-256-verified the stock IPA, extracted both app executables, and parsed their Mach-O load commands. The run completed successfully:

- GitHub Actions run: `43598852365`.
- Evidence artifact: `reference-inventory-runtime-evidence`, artifact ID `14115332326`.
- Reference executable: `CounterFlame`, 66,368 bytes.
- Stock executable: `CounterFlame-stock`, 66,368 bytes.
- Reference executable has `LC_LOAD_DYLIB @executable_path/Frameworks/CounterFlameKAlert551.dylib`.
- Stock executable has no load command for `CounterFlameKAlert551.dylib`.
- The reference dylib is present in the reference IPA at `Frameworks/CounterFlameKAlert551.dylib`; its install-name identity is `/Library/MobileSubstrate/DynamicLibraries/CounterFlameKAlert551.dylib`.

**Conclusion:** the reference package differs from stock at the main executable's dynamic-library dependency table: the reference executable explicitly loads the bundled module, while the stock executable does not. The install-name string is a separate piece of metadata and should not be mistaken for proof that the module is loaded only through an external injector. This is static linkage evidence only; it does not prove runtime success, signing compatibility, or behavior on a stock iOS device.
