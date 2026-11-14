# Latest Mesh Swap Prototype Audit

- Source IPA: `CounterFlame-1.4.1-c7-ios.2.ipa`
- SHA-256 verified: `6c3e740ca379c5daf55f635e1228414230ca4acb7608cd7b35e7f5c0e0d952d3`
- Unity: `2021.3.45f1`
- Audit workflow: [Run #43617801782](https://github.com/xianhettkx/CounterFlame-Analyzer/actions/runs/43617801782)
- Artifact ID: `14123035162`
- Tested code commit: `069eb347ef9a24421f8afceed30938a3e87965a6`
- Mode: read-only audit; no asset bytes or IPA contents were written.

## Result

| Measure | Result |
|---|---:|
| Mesh records | 30 |
| Candidate pair plans | 62 |
| Writable plans | **0** |
| Blocked pair plans | 62 |
| Readiness blocked | 22 |
| Eligible for reference review (static MeshFilter records only) | 7 |
| Needs runtime verification (skinned record) | 1 |
| Unit tests | **49 passed** |

## Why no model pair is approved

- First-person and third-person models are not interchangeable.
- Weapon bodies, magazines, dropped-weapon models, and handheld third-person models are different roles; the planner now blocks cross-role pairs.
- Skinned candidates must have matching bone counts, exact ordered bone names, and identical bind-pose matrix signatures. Missing signatures fail closed.
- Meshes referenced by multiple renderer owners are marked ambiguous until an exact renderer/skeleton instance is selected.
- Several first-person weapon meshes have decoded vertex data but zero decoded skin-weight entries; those are not approved for a skinned swap.

The previous smaller audit reported 20 apparent static candidates because it did not distinguish model roles. The role gate blocks those false positives. The earlier 15-record report is retained as historical evidence only; this 30-record run is the current result.

## Next technical requirement

A specific renderer instance must be selected and its owner, bone mapping, bind poses, materials, and view/part role verified. Until then, the prototype must remain audit-only. No replacement IPA has been generated, and no live-game activation or device rendering is claimed.
