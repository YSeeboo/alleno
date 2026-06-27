# 电镀颜色新增 14K金 / 银色 + 颜色单一来源化 — 设计文档

- 日期：2026-06-27
- 分支：`feat/plating-colors-14k-silver`
- Mockup：`docs/superpowers/mockups/plating-colors-mockup.html`

## 1. 背景与目标

电镀颜色当前为 3 个:`G`(金色) / `S`(白K) / `RG`(玫瑰金),定义在后端 `services/part.py` 的 `COLOR_VARIANTS`,经 `/parts/color-variants` 暴露。需新增两个**不常用**颜色:

- **14K金**,code = `K14`
- **银色**,code = `SV`(与 `S`=白K 是两种不同材质,不可复用 `S`)

同时解决一个既有问题:虽然后端是单一来源,**前端三个文件把颜色映射又各自硬编码了一遍**,加颜色容易漏改。本设计:(1) 新增两色;(2) 把颜色做成「后端单一来源 + 前端派生」;(3) 按「常用/不常用」分层展示,让不常用色不挤占常用路径。

## 2. 关键决策(已与用户对齐)

| 决策点 | 结论 |
|---|---|
| 新增颜色与 code | 14K金=`K14`、银色=`SV`(进变体 ID 后缀与主键,永久) |
| 银色 vs 白K | 两种不同材质,各自独立 code/色块 |
| 展示分层 | 常用色(G/S/RG)直显;不常用色(K14/SV)收进「更多 ▾」展开 |
| 分层数据来源 | 后端 `COLOR_VARIANTS` 每条加 `common` 标记驱动,前端不写死哪些常用 |
| 色块 hex | 14K金 `#CBA94B`、银色 `#9AA7B0`(初值,可后续微调) |
| 工艺名 method | K14→`14K金`、SV→`银` |
| 前端去硬编码 | 三处(PlatingCreate / PlatingDetail / PartList)改为从接口列表派生所有映射;PartList 由硬编码改为也拉接口 |

## 3. 后端变更

### 3.1 `COLOR_VARIANTS` 富化 + 加两色

`services/part.py`,把每条记录从 `{code, label}` 扩成带 `method` / `badge` / `common`,并加两条:

```python
COLOR_VARIANTS = [
    {"code": "G",   "label": "金色",   "method": "金",     "badge": "#DAA520", "common": True},
    {"code": "S",   "label": "白K",    "method": "白K",    "badge": "#C0C0C0", "common": True},
    {"code": "RG",  "label": "玫瑰金", "method": "玫瑰金", "badge": "#B76E79", "common": True},
    {"code": "K14", "label": "14K金",  "method": "14K金",  "badge": "#CBA94B", "common": False},
    {"code": "SV",  "label": "银色",   "method": "银",     "badge": "#9AA7B0", "common": False},
]
```

顺序即展示顺序(常用在前)。

### 3.2 既有派生项自动跟随(无需改动,需回归验证)

以下都由 `COLOR_VARIANTS` 派生,加列后自动包含两色:
- `COLOR_SUFFIXES = [v["label"] for v in COLOR_VARIANTS]` → 含 `14K金 / 银色`
- `COLOR_CODES = {v["code"]: v["label"]}` → 含 `K14 / SV`
- `_LABEL_TO_CODE = {v["label"]: v["code"]}`
- 孤儿变体名正则 `_COLOR_PLUS_SPEC_NAME_REGEX`(基于 `COLOR_SUFFIXES`)
- `_is_color_variant` / `_looks_like_orphan_variant_name`

变体创建链路(`create_part_variant` → `_validate_variant_request` → `_next_variant_id` → `_build_variant_name`)读取 `v["code"]` / `v["label"]`,新增的 `method/badge/common` 三个键对这些逻辑是惰性的(不被读取),不影响现有行为。新增两色后:
- 14K金变体 ID 形如 `PJ-DZ-00001-K14`,名称后缀 `…_14K金`
- 银色变体 ID `…-SV`,名称后缀 `…_银色`

### 3.3 API

`/parts/color-variants`(`api/parts.py:54`)直接返回 `COLOR_VARIANTS`,故新字段(`method/badge/common`)与两条新记录会自动随接口下发,前端即可消费。**无需改 API 代码。**

## 4. 前端变更(去硬编码 + 分层)

目标:三个文件不再硬编码任何颜色映射,全部从 `getColorVariants()` 返回的列表派生;渲染按 `common` 分两层。

### 4.1 派生映射(替换硬编码)

从接口列表 `cvs`(每项 `{code,label,method,badge,common}`)派生现有各 map:
- `BADGE_COLORS` = `Object.fromEntries(cvs.map(c => [c.code, c.badge]))`
- `COLOR_CODE_TO_METHOD` = `{[c.code]: c.method}`
- `METHOD_TO_CODE` = `{[c.method]: c.code}`
- `COLOR_LABEL_TO_CODE` / `COLOR_CODE_REVERSE` = `{[c.label]: c.code}`
- `COLOR_SUFFIX_MAP`(`_金色`→code)= `{['_'+c.label]: c.code}`
- `VARIANT_COLORS`(PartList 加变体选项)= `cvs.map(c => ({ code: c.code, label: `${c.label} ${c.code}`, badge: c.badge, common: c.common }))`

常用/不常用拆分:`commonColors = cvs.filter(c => c.common)`;`moreColors = cvs.filter(c => !c.common)`。

### 4.2 `PlatingCreate.vue`

- 删除 `BADGE_COLORS / COLOR_CODE_TO_METHOD / COLOR_LABEL_TO_CODE` 及内联 `{_金色:G,...}` 硬编码,改用 §4.1 派生(基于已拉取的 `colorVariants`)。
- 颜色 chip 渲染分两层:常用色直接渲染;末尾加「更多 ▾」按钮,点开渲染 `moreColors` 的 chip。其余选色/工艺联动逻辑不变(选 K14 工艺=`14K金`,SV=`银`)。

### 4.3 `PlatingDetail.vue`

- 删除 `BADGE_COLORS / COLOR_SUFFIX_MAP / COLOR_CODE_TO_METHOD / METHOD_TO_CODE / COLOR_LABEL_TO_CODE` 硬编码,改用 §4.1 派生(基于已拉取的 `colorVariantList`)。
- 明细行内 chip(`columns` 的颜色列 render):常用色直显 + 「⋯」展开不常用,避免撑爆行宽。展开态可用一个 `ref(Set)`(按行 id)管理,或行内局部状态。

### 4.4 `PartList.vue`

- 当前**硬编码** `VARIANT_COLORS` / `COLOR_CODE_REVERSE`;改为在 `onMounted`(或 load)中调用 `getColorVariants()` 拉取,再按 §4.1 派生。
- 「加颜色变体」选项列表分两层:常用三色直列 + 「＋ 更多颜色 ▾」展开 14K金/银色。
- `existingVariantColors` 等基于 `COLOR_CODE_REVERSE` 的逻辑改用派生 map。

## 5. 边界与规则

- 颜色的五个属性(`code/label/method/badge/common`)集中在后端一处;以后加颜色或调整常用集,只改 `COLOR_VARIANTS` 一行,三处页面自动生效。
- `code` 进变体主键、永久且可见;`K14/SV` 已定,不再变。
- 不触碰库存、订单、电镀状态机;仅颜色清单 + 展示。
- 历史数据无需迁移:新增色只影响「新建变体 / 新建电镀颜色选择」,旧记录不受影响。

## 6. 不做(YAGNI)

- 不做颜色的增删改管理 UI(颜色仍是代码常量,极少变动)。
- 不把颜色迁到数据库表。
- 不调整现有 G/S/RG 的 code、label 或既有变体数据。
- 不改 `/parts/color-variants` 的接口签名(仅多带字段)。

## 7. 测试要点

- 后端:`COLOR_VARIANTS` 含 5 条;`COLOR_CODES` / `COLOR_SUFFIXES` 含 `K14/SV` 与 `14K金/银色`;`create_part_variant(part, color_code="K14")` 生成 ID 后缀 `-K14`、名称后缀 `_14K金`;`SV` 同理;非法 code 仍报错。
- 后端回归:现有 G/S/RG 变体创建、孤儿名检测不受影响。
- 前端:`npm run build` 通过;三处页面颜色 chip 渲染为「常用 + 更多」,色块/工艺名来自接口;PlatingDetail 行内 chip 不撑爆;PartList 加变体可选到 14K金/银色并生成正确 ID。
