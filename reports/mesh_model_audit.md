# CounterFlame 本地 Mesh 模型替换审查报告

- 审查日期：2026-11-14
- 审查对象：`https://github.com/xianhettkx/CounterFlame-Analyzer`（main 分支）
- 审查边界：仅本地资源与离线序列化文件分析；**不涉及**服务器库存、付费权限、账号授权、联网校验、反作弊或运行时注入。
- 证据分级：
  - **【已验证】**：本次直接从原版 IPA 序列化文件 / 打包数据中读取到的事实，机器可读证据见 `reports/mesh_model_audit_evidence.json`。
  - **【推测】**：由已验证证据合理推断，但未在设备或编辑器中复核。
  - **【无法验证】**：本地静态分析无法确认（需实机、Unity Editor、未发布的源工程或运行时日志）。

## 1. 结论摘要

1. **现有管线是贴图替换，不是模型替换。** `unity_local_skin_patch.py` 只遍历 `Texture2D` 并重写 `image_data`；全仓库除本次新增的门控原型外，没有任何脚本写入 `m_Mesh`、`m_Materials`、`m_Bones`、`m_RootBone`、`Avatar` 或 Animator 控制器引用。【已验证】
2. 两个优先皮肤的 Addressables 包内**只含 Material 与 Texture2D，不含任何 Mesh**。全量 1,941 个 bundle 中仅 10 个 Mesh 对象，且全部是特勤干员身体部件，没有武器或手套模型。【已验证】
3. 武器/手套基础模型位于主序列化文件 `Data/resources.assets`（329 个 Mesh、1,191 个 SkinnedMeshRenderer、275 个 MeshFilter / 275 个 MeshRenderer）。皮肤包通过材质槽引用这些基础 Mesh，皮肤包本身不携带替换模型。【已验证】
4. 手套 FP 模型是带权重的蒙皮网格（5,314–10,050 顶点、权重与顶点一一对应）；武器 FP 模型在 UnityPy 解码结果中**顶点权重数组为空**（`weight_entries=0`），但渲染器仍挂了 43–57 根骨骼引用。【已验证】
5. OBJ 导出只保留几何（顶点/UV/法线/面/分组），**不保留**骨骼、蒙皮权重、绑定姿态、Avatar、动画控制器、材质 PPtr、GUID、碰撞体、LOD、BlendShape 等序列化信息；不能把 OBJ 当作可直接回写的模型资源。【已验证】
6. 真正可落地的本地模型替换分三级风险方案：同文件 Mesh 引用重定向（低风险 MVP）→ 同文件内写入新 Mesh 字节（高风险，未验证）→ 外部 Addressable 包 + 运行时加载钩子（超出本次安全边界）。【推测 + 已验证现状】
7. 本次在独立分支 `feature/mesh-swap-static-prototype` 上实现了只读规划器与门控原型，单元测试全部通过；原型默认审计模式，对真实原版 IPA 跑通 15 条 Mesh 记录、20 条同皮肤配对计划，未改写任何 IPA 字节。【已验证】

## 2. 审查素材与可访问性

| 素材 | 状态 | 说明 |
|---|---|---|
| 原版 IPA `CounterFlame-1.4.1-c7-ios.2.ipa` | 【已验证】可下载、已在本地解析 | SHA-256 `6c3e740ca379c5daf55f635e1228414230ca4acb7608cd7b35e7f5c0e0d952d3`，1,829,862,971 字节，与 `reports/reference-local-inventory-runtime-audit.md` 记录一致 |
| 参考 IPA `CS2._1.4.1_.5.8.78.2.ipa` | 【已验证】可下载、已校验指纹 | SHA-256 `7b20f04d493c60cf5e215c0a82050fa691105fc47a0748e46e55cc3078f9cc9f`，1,830,224,781 字节 |
| Unity 版本 | 【已验证】 | `2021.3.45f1` |
| `resources.assets` | 【已验证】 | 49,496 个序列化对象；`resources.resource` 35.7 MB 为其流式资源 |
| 已有分析报告 | 【已验证】已通读 | `reports/` 下 6 份 Markdown；本报告对其中关键数字做了独立复核 |

> 未使用任何需要登录的 API 或仓库私有工件；CI 历史构建产物不在本次复核范围。

### 2.1 主序列化文件类型计数（本次复核）

| 类型 | 数量 | 报告原值 | 一致性 |
|---|---:|---:|---|
| Mesh | 329 | 329 | 一致 |
| Transform | 18,726 | 18,726 | 一致 |
| SkinnedMeshRenderer | 1,191 | 1,191 | 一致 |
| MeshFilter | 275 | 275 | 一致 |
| MeshRenderer | 275 | 275 | 一致 |
| Animator | 119 | — | 本次实测 |
| Avatar | 2 | — | 本次实测 |
| AnimationClip | 1,417 | — | 本次实测 |
| Material | 347 | — | 本次实测 |
| Texture2D | 1,560 | — | 本次实测 |
| GameObject | 18,991 | — | 本次实测 |

## 3. 原版武器 Mesh 与目标皮肤 Mesh：资源路径与对象结构

### 3.1 主模型所在位置

【已验证】武器与手套基础模型全部在 `Payload/CounterFlame.app/Data/resources.assets`，流式几何在同目录 `resources.resource`（UnityPy 以 `resources.assets.resS` 别名加载）。皮肤材质/贴图在 `Data/Raw/aa/iOS/...` 的 Addressables bundle 内。

### 3.2 优先目标 Mesh 实测清单

| 皮肤 | 视角 | Mesh PathID | Mesh 对象名 | 渲染器类型 | 顶点 | UV | 权重条目 | 绑定姿态 | 子网格 | 骨骼数 | 根骨骼 |
|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| butterfly_marblefade | FP | 2233 | `v_knife_t_v_knife_flip_reference` | SkinnedMeshRenderer | 3,059 | 3,059 | 0 | 56 | 1 | 56 | 未暴露 |
| butterfly_marblefade | TP | 2048 | `tps_Butterfly` | MeshFilter | 无法解码 | — | — | 0 | 1 | 0 | — |
| specialist_pillow | FP | 2000 | `v_glove_ct_specialist` | SkinnedMeshRenderer | 10,050 | 10,050 | 10,050 | 67 | 3 | 67 | `v_weapon.Bip01_L_Forearm`（另有 `arm_lower_l` 实例） |
| specialist_pillow | FP | 2215 | `v_glove_ct_specialist` | SkinnedMeshRenderer | 5,314 | 5,314 | 5,314 | 99 | 3 | 99 | `v_weapon.Bip01_L_Forearm` |
| specialist_pillow | FP | 2216 | `v_glove_ct_specialist` | SkinnedMeshRenderer | 10,050 | 10,050 | 10,050 | 50 | 3 | 50 | `knife_tip`（异常挂点变体） |
| specialist_pillow | FP | 2217 | `v_glove_ct_specialist` | SkinnedMeshRenderer | 10,050 | 10,050 | 10,050 | 67 | 3 | 67 | `v_weapon.Bip01_L_Forearm` |
| specialist_pillow | TP | 2115 | `v_glove_ct_specialist_ct` | SkinnedMeshRenderer | 6,690 | 6,690 | 6,690 | 99 | 3 | 99 | `v_weapon.Bip01_L_Forearm` |

其余四个基础武器（AWP / AK47 / M4A4 / Deagle）记录见 `mesh_model_audit_evidence.json`：FP 为 SkinnedMeshRenderer，TP 为 MeshFilter；FP 权重条目均为 0，骨骼数 43–57。

### 3.3 与已有报告的差异（本次实测纠正）

- 旧报告 `target_model_material_map.md` 称蝴蝶刀 Mesh 2233 为 13 根骨骼；本次实测渲染器骨骼引用为 **56** 根。【已验证】
- 旧报告称手套为“72 根公共骨架、变体 48/62/67/90/99”；本次实测五个目标网格的骨架布局为 **50 / 67 / 67 / 99 / 99**（2216 为 50 根且根骨骼挂到 `knife_tip`）。【已验证】
- `mesh_export_qa.md` 中 Pillow 2217 行的“Vertices 2217”实际是 PathID 列；实测顶点 10,050、OBJ 面记录 16,400，与同表面数一致。【已验证】
- TP MeshFilter（2048、1980、2043、2062、2050）顶点流在本地 UnityPy 解码失败（`m_DataSize` 为空 / 流式资源解析报 FileNotFoundError），几何数据**无法验证**，不能据此认定其顶点数或权重。【无法验证】

## 4. 引用关系：Mesh / Material / Texture / Renderer / Transform / 骨骼 / Animator

### 4.1 已验证的引用链

```
GameObject
 ├─ Transform (m_Father / m_Children，挂点层级)
 ├─ MeshFilter.m_Mesh ────────────────► Mesh（TP 静态网格）
 ├─ SkinnedMeshRenderer
 │    ├─ m_Mesh ──────────────────────► Mesh（FP 蒙皮网格）
 │    ├─ m_Materials[i] ──────────────► Material
 │    │    └─ m_SavedProperties.m_TexEnvs[slot] ─► Texture2D（可能为外部 bundle PPtr）
 │    ├─ m_Bones[i] ─────────────────► Transform（骨骼链）
 │    └─ m_RootBone ──────────────────► Transform（根骨骼）
 └─ Animator
      └─ m_Controller ────────────────► AnimatorController ─► StateMachine/State ─► AnimationClip
       (Avatar 引用在主文件中仅 2 个：car_1Avatar、Robot KyleAvatar)
```

### 4.2 渲染器到材质的实测槽位

**Butterfly FP（2233）**：`knife_flip`；TP 兄弟 MeshRenderer：`butterfly_vanilla_tps_Diffuse`。【已验证】

**手套 FP 三个子网格材质顺序**（以 2000 / 2217 为例）：
1. `default_handwrap_barearms_PBR`（手臂/包布）
2. `glove_specialist_right`
3. `glove_specialist_left`

变体差异：2215 同槽位；2216 首槽为 `bare_arm_133`；2115 首槽为 `cthand`。【已验证】

### 4.3 Animator / 控制器实测

主文件共 119 个 Animator、63 个控制器。与目标武器相关的控制器（图遍历到的 AnimationClip 计数）：

| 控制器 | Animator 实例数 | 剪辑数 |
|---|---:|---:|
| `butterfly` | 3 | 15 |
| `flip` | 2 | 11 |
| `ak47` | 2 | 6 |
| `ak47_a` | 1 | 5 |
| `awp_a_new` | 2 | 5 |
| `deagle` | 3 | 9 |
| `m4a4` | 3 | 5 |
| `m4a1s` | 2 | 5 |

- 手套条目在清单中控制器为空；本次目标控制器列表中也没有独立手套控制器。【已验证】
- 网格所在 GameObject 上**未直接挂 Animator**；动画控制器挂在更上层的武器/手掌挂点对象上。本次静态遍历沿 `m_Father` 回退到根（`m_Father` 为 0），未在网格节点同层找到 Animator。【已验证】；控制器与具体挂点对象的完整配对【无法验证】（需实机或 Editor）。
- 主文件只有 2 个 Avatar 资源（`car_1Avatar`、`Robot KyleAvatar`），武器手套未出现专用 Avatar。【已验证】

### 4.4 骨骼与权重现状

- 手套蒙皮网格：权重条目数 == 顶点数，骨骼索引条目齐全，绑定姿态数 == 渲染器骨骼数。【已验证】
- 武器 FP 网格：骨骼索引条目存在，但 UnityPy 解码出的权重条目为 0；可能是压缩蒙皮数据未被解码，也可能是刚体绑定。【已验证解码结果；成因无法验证】
- 2216 根骨骼为 `knife_tip`，属于挂点异常变体；交换蒙皮模型时必须单独核对，不能与 67 骨布局混用。【已验证】

## 5. 两个优先皮肤的完整资源依赖

### 5.1 Butterfly Knife | Marble Fade

包路径前缀：`Data/Raw/aa/iOS/inv_skins_assets_inventory/skins/butterfly_marblefade/`

| 材质包 | 槽位 | 解析到的物理包 / 贴图名 |
|---|---|---|
| `butterfly_marblefade_diffuse` | `_MainTex` | `.../butterfly_marblefade/butterfly_marblefade_paint.png_…bundle` → `butterfly_marblefade_paint` |
| `butterfly_marblefade_pbr` | `_MainTex` | `.../butterfly_marblefade/butterfly_marblefade_cs2.png_…bundle` → `butterfly_marblefade_cs2` |
| `butterfly_marblefade_pbr` | `_PaintPattern` | `.../weapons/_surface/paints/smoke2.png_…bundle` → `smoke2` |
| `butterfly_marblefade_pbr` | `_SpecGlossMap` | `.../weapons/_surface/masks/butterfly_butterfly_marblefade__cs2_mask.png_…bundle` → `butterfly_butterfly_marblefade__cs2_mask` |
| `butterfly_marblefade_specular` | `_MainTex` / `_SpecGlossMap` | 同上 paint / mask |

另有独立贴图包：`..._cs2.png`、`..._paint.png`、`..._mask.png`、`..._normal.png`，以及一个未被材质槽引用的 `crimsonweb` OCC 贴图包。【已验证】

### 5.2 Specialist Gloves | Pillow Punchers

包路径前缀：`Data/Raw/aa/iOS/inv_gloves_assets_inventory/gloves/specialist_pillow/`

| 材质包 | 槽位 | 解析到的物理包 / 贴图名 |
|---|---|---|
| `specialist_pillow_diffuse` | `_MainTex` | `glove_specialist_left_…bundle` → `glove_specialist_left` |
| `specialist_pillow_pbr` | `_MainTex` | `glove_specialist_left` |
| `specialist_pillow_pbr` | `_BumpMap` | `glove_specialist_left_normal_…bundle` → `glove_specialist_left_normal` |
| `specialist_pillow_pbr` | `_SpecGlossMap` | `.../weapons/_surface/masks/gloves_specialist_bigswell_mask.png_…bundle` → `gloves_specialist_bigswell_mask`（复用其他手套家族的共享遮罩） |
| `specialist_pillow_specular` | `_MainTex` / `_BumpMap` / `_SpecGlossMap` | 同上三件 |

【已验证】注意：`glove_specialist_right` 材质槽在本皮肤包内未提供右侧贴图包；右侧贴图是否回落到共享默认材质【无法验证】。

### 5.3 皮肤包内是否存在可替换 Mesh

- `butterfly_marblefade` 全部 8 个相关 bundle：**Mesh 对象数 0**。【已验证】
- `specialist_pillow` 全部 5 个相关 bundle：**Mesh 对象数 0**。【已验证】
- 全量 1,941 个 bundle：共 10 个 Mesh，均为特勤干员身体部件（`ctm_gendarmerie_variantd_*`、`tm_balkan_variantl_*`）。【已验证】

## 6. OBJ / GLB 导出丢失了什么

### 6.1 OBJ 实际保留内容（对 2233、2217 等实测）

- 保留：`v` 顶点、`vt` UV、`vn` 法线、`f` 面、`g` 分组（子网格分组）。
- 不包含：`mtllib` / `usemtl`（本次导出未写材质声明），无骨骼层级、无蒙皮权重、无绑定姿态、无动画、无 PPtr 与 GUID 引用、无碰撞体、无 LOD、无 BlendShape。【已验证】

### 6.2 序列化信息丢失清单

| 信息 | OBJ | GLB（静态预览） | GLB（蒙皮预览，仅 2217） |
|---|---|---|---|
| 顶点 / UV / 法线 | 保留 | 保留 | 保留 |
| 骨骼节点层级 | 丢失 | 丢失 | 保留预览骨架 |
| 蒙皮权重 / 绑定姿态 | 丢失 | 丢失 | 保留预览权重 |
| Animator / 控制器 / 剪辑 | 丢失 | 丢失 | 丢失（剪辑不嵌入） |
| 材质 PPtr / Shader / 属性 | 丢失 | 丢失（单白模预览） | 丢失 |
| 文件 GUID / PathID / 外部依赖 | 丢失 | 丢失 | 丢失 |
| 碰撞体 / LOD / BlendShape | 丢失 | 丢失 | 丢失 |

**结论**：OBJ/GLB 只能作为几何与挂点参考，不能作为回写 Unity 的最终模型格式。任何模型替换都必须在序列化层或 Unity Editor 工程内完成，而不是把 OBJ 塞回 bundle。【已验证 + 推测】

## 7. 在 AssetBundle / 序列化文件中安全替换 Mesh 的可行性

### 7.1 必须保持不变的引用（替换 Mesh 时禁止重写）

`m_GameObject`、`m_Bones`、`m_RootBone`、`Transform.m_Father`、`Transform.m_Children`、`Animator.m_Controller`、`Avatar`、`m_Materials`（除非另行规划材质重映射）。【已验证引用存在；保持不变为设计约束】

### 7.2 替换方案分级

#### 方案 A：同序列化文件内 Mesh 引用重定向（低风险，MVP）

- 做法：把渲染器 `m_Mesh` 的 PPtr 指向同一个 `resources.assets` 内已存在的另一个 Mesh 对象；不写入任何新几何字节。
- 前提校验（规划器已实现静态检查）：
  1. 渲染器家族一致（MeshFilter ↔ MeshFilter；SkinnedMeshRenderer ↔ SkinnedMeshRenderer）；
  2. 蒙皮目标：源网格必须有权重、骨骼数一致、绑定姿态数一致、根骨骼存在；
  3. 子网格数与材质槽位数对齐；
  4. 同皮肤/同武器家族内配对（跨家族不提案）。
- 静态结论：手套 2000 ↔ 2217（均 67 骨、10,050 顶点、3 子网格）可进入“需运行时验证”状态；2215 ↔ 2115（均 99 骨）同理；50 骨变体 2216 与其他布局相互阻断；武器 FP 因解码权重为空，蒙皮配对被阻断。【已验证（静态）】
- 写回放行条件：apply 路径仅把 `reference_swap_eligible`（同家族静态 MeshFilter 对）视为可写；蒙皮配对即使静态布局一致也只到 `needs_runtime_verification`，本轮一律跳过、不写资产。【已验证（代码 + 单测）】
- 残余风险：骨骼顺序/绑定姿态正确性、形变、缩放比例、挂点朝向只能在实机或 Editor 内确认。【无法验证】

#### 方案 B：在 `resources.assets` 内写入新 Mesh 字节（高风险，未验证）

- 需要处理：顶点流（`m_VertexData.m_Channels` / 压缩网格 `m_CompressedMesh`）、索引缓冲与索引格式、子网格、绑定姿态、权重、UV 通道、LOD、碰撞体、流式资源 `resources.resource` 的落盘与偏移。
- UnityPy 的对象 `save()` 往返未在本构建上验证；`m_IsReadable=false` 的剥离网格依赖流式几何；TP 网格本地解码已失败。【已验证现状；写入路径无法验证】
- 不建议作为第一步；若要推进，应先在 Editor 工程内导入模型、按原骨架配权、导出与原版相同序列化布局的 Mesh，再做单对象往返冒烟测试。

#### 方案 C：外部 Addressable bundle + 运行时加载钩子（超出本次边界）

- 做法：新 Mesh/材质/预制体打进独立 bundle，由运行时代码按皮肤键加载并替换渲染器。
- 约束：这需要运行时注入点或游戏自带的换装接口；本次不研究、不实现任何挂钩、不触碰网络与库存逻辑。【边界声明】

### 7.3 动画、挂点与对象引用保持要点

- 挂点由父级 Transform 层级决定，Mesh 替换本身不改变层级；只要不动 `m_Father/m_Children`，武器挂点位置保留。【推测，需实机确认】
- 蒙皮形变依赖 `m_Bones` 顺序与绑定姿态；替换模型必须使用同一套骨架命名与顺序，否则会出现拉伸、穿模或根骨骼错位（2216 的 `knife_tip` 挂点就是反例）。【已验证反例 + 推测】
- Animator 控制器与剪辑挂在上层节点；网格引用重定向不会断开控制器，但模型尺寸/骨骼偏移仍可能影响动画表现。【已验证引用结构；表现无法验证】

## 8. 现有打包脚本为什么只能替换贴图（代码证据）

### 8.1 贴图修补脚本 `src/unity_local_skin_patch.py`

- 第 169 行：分支条件为 `obj.type.name == "Texture2D"`；没有 Mesh / Material / Renderer / Transform / Animator 的处理分支。
- 第 176、261 行：读取与写回的字段是 `texture_data.image_data`（贴图字节）。
- 第 238–263 行：兼容性门禁只比对宽、高、格式、字节长度；不存在顶点数、骨骼数、权重、绑定姿态的校验。
- `TEXTURE_OVERRIDES` 映射的是材质槽名 → 贴图名，没有任何 Mesh PathID 映射。【已验证】

### 8.2 IPA 重打包脚本 `src/package_local_skin_patch.py`

- 第 28–43 行：只替换 zip 内唯一的 `resources.assets` 条目；不重建 Addressables bundle，不写入新 Mesh 序列化对象。【已验证】

### 8.3 导出与审计脚本均为只读

- `unity_target_asset_export.py`：调用 `mesh.export()` 写 OBJ 预览，不回写。
- `unity_glb_rig_export.py`：读取 `m_Mesh / m_Bones / m_Materials / m_RootBone` 生成 GLB 预览，不回写。
- `unity_model_graph.py / unity_mesh_renderer_link_audit.py / unity_rig_animation_map.py / unity_skin_weight_audit.py`：只解析引用并生成报告。
- 全仓库 grep 结果：除本次新增原型外，`m_Mesh` 只出现在读取/统计路径；没有任何写回 Mesh 或重定向 Mesh 引用的代码。【已验证】

### 8.4 概念澄清

- **贴图替换**：改 Material 槽指向的 Texture2D 像素数据，网格几何、骨骼、动画完全不变。
- **模型替换**：改渲染器引用的 Mesh 对象（几何/拓扑/蒙皮），或写入新 Mesh 序列化数据。
- 当前产物属于前者；报告与脚本中任何“模型/皮肤”表述若未改动 `m_Mesh`，都不应称为模型替换。【已验证】

## 9. 本次 MVP 分支与验证结果

- 分支：`feature/mesh-swap-static-prototype`（从 main 切出，未合并、未覆盖 main）。
- 新增文件：
  - `src/unity_mesh_swap_plan.py`：纯 Python 规划器与不变量校验（不依赖 UnityPy，可离线单测）。
  - `src/unity_mesh_swap_prototype.py`：UnityPy 只读适配器 + 门控原型；默认审计模式，`--apply-reference-swap` 显式门控后才允许重定向 `m_Mesh`，且阻断任何未通过校验的配对。
  - `tests/test_mesh_swap_plan.py`：规划器不变量与引用快照测试。
  - `reports/mesh_model_audit.md`（本报告）、`reports/mesh_model_audit_evidence.json`（机器可读证据）。
- 测试结果：`python3 -m unittest discover -s tests` → **34 个测试全部通过**。其中原有 6 项（1 个清单测试、5 个扫描器测试）与 main 逐字节一致、零改动；新增 28 项覆盖规划门禁、引用快照、apply 写回路径与原子写入。【已验证，日志见交付物 `test_run.log`】
- 真实 IPA 审计模式运行：15 条 Mesh 记录、20 条同皮肤配对计划；16 条配对阻断，4 条进入“需运行时验证”（2000↔2217、2215↔2115 及其反向）；单模型静态门禁跳过 10 条；未生成任何补丁 IPA。【已验证】
- apply 门禁加固（本轮修复）：只有配对计划达到 `reference_swap_eligible`、且**源 Mesh 与目标渲染器两侧** `record_readiness()` 均不 `blocked` 时才允许进入写回；`blocked` 与 `needs_runtime_verification` 一律跳过，不创建/替换 `resources.assets`，`needs_runtime_verification` 不会被自动升级为通过。门禁原因明确区分：几何流解码失败、缺失材质槽、蒙皮权重缺失、骨骼数 / 绑定姿态不匹配、根骨骼缺失。【已验证（单测覆盖）】
- 引用安全：apply 路径在内存中先对 `m_GameObject / m_Bones / m_RootBone / m_Materials` 以及同层 Animator `m_Controller` 做快照；改写 `m_Mesh` 后逐项比对，任一漂移即 `ReferenceDriftError` 中止且不落盘；唯一允许改写的字段是 `m_Mesh` PPtr。`m_BindPose` 属于 Mesh 自身数据，随被替换 Mesh 携带，渲染器级骨骼引用不动。【已验证（单测覆盖快照与漂移检测）；实机表现无法验证】
- 落盘策略：内存内完成改写、引用断言与序列化，校验通过且序列化载荷非空后，才通过同目录临时文件 `fsync` + `os.replace` 原子替换目标文件；任何失败路径都不触碰目标资产，也不残留临时文件。【已验证（单测覆盖）】
- 原型 `--apply-reference-swap` 路径仅做同文件 PPtr 重定向，不实现新几何字节写入；门禁失败的模型记入 `skipped` 并跳过，不强行替换；本分支未在实机上安装验证，也未声称游戏内显示成功。【已验证（代码路径）；实机表现无法验证】

## 10. 安全边界声明

- 未修改、未尝试修改：服务器库存、账号/付费权限、皮肤解锁条件、反作弊、联网校验、遥测或登录流程。
- 参考 IPA 中的 `CounterFlameKAlert551.dylib` 仅做只读字符串与加载命令复核（`InventoryManager`、`SetSkin`、`OfflineEquip`、`cf-local-preview`、`inventory-config-v5.json` 标记存在；主可执行文件加载命令在参考包中存在、原版包中不存在），未逆向、未挂钩、未注入。【已验证】
- 本报告与原型仅用于本地资源结构分析；任何后续安装级修改都需自行承担合规与设备风险。

## 11. 建议的后续步骤（按优先级）

1. **Editor 骨架对齐验证**：在 Unity Editor 中导入手套 2000/2217 网格，核对 67 骨命名顺序与绑定姿态；确认 2215/2115 的 99 骨布局是否同一骨架。
2. **完成方案 A 静态清单**：为同家族配对补齐骨骼名集合比对、子网格材质槽一致性检查、缩放/包围盒比对；仍保持离线只读。
3. **方案 B 往返冒烟**：选一个无关紧要的测试 Mesh，在序列化层做一次读出→原样写回的往返，验证 UnityPy 保存与流式资源偏移不损坏对象；通过前不接触武器模型。
4. **TP 几何解码修复**：排查 5 个 MeshFilter 网格的流式资源解析（空 `m_DataSize`），补齐顶点/UV/法线证据后再评估 TP 替换。
5. **实机验证必须在隔离设备**：先验证引用重定向不崩溃、挂点与动画正常，再讨论新几何写入；保留原版 IPA 可回滚。
