# Local Cosmetic Preview

This branch adds a standalone, offline-friendly cosmetic selection page at `tools/local-armory/index.html`.

## Current verified scope
- Six cosmetic mappings already present in `config/local_skin_pseudo_entity_map.json`: Butterfly Knife | Marble Fade, Specialist Gloves | Pillow Punchers, AWP | Dragon Lore, AK-47 | Neon Revolution, M4A4 | The Emperor, and Desert Eagle | Code Red.
- Search, category filtering, local selection persistence, and JSON export.
- No external libraries, CDN, network requests, runtime injection, or IPA mutation.

## Important boundary
This is a local catalog/preview selector, **not** an in-game unlock. It does not change server inventory, account entitlements, matchmaking, anti-cheat, or other players' view. The six entries are not evidence of a complete game-wide skin catalog. Additional skins must be discovered and mapped from the exact IPA before being labelled verified. The existing model-swap audit currently approves zero writable model-swap plans; do not claim model replacement or live rendering is complete.

## Use
Open `tools/local-armory/index.html` in a browser. Choose a cosmetic and export the local JSON selection. The browser stores only the selected key in localStorage.
