# 电镀颜色新增 14K金 / 银色 + 颜色单一来源化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给电镀颜色新增 14K金(`K14`)、银色(`SV`),并把前端三处硬编码的颜色映射改为从后端单一来源派生、按「常用/不常用」分层展示。

**Architecture:** 后端 `COLOR_VARIANTS` 每条富化为 `{code,label,method,badge,common}` 并加两条新色(既有派生项与变体 ID/名称生成自动跟随;API 无需改)。前端三个文件(PlatingCreate / PlatingDetail / PartList)删除各自硬编码 map,改为从 `/parts/color-variants` 返回的列表内联派生,并按 `common` 渲染「常用直显 + 更多展开」。

**Tech Stack:** FastAPI + SQLAlchemy；pytest;Vue 3.5 + Naive UI;前端 `npm run build` 作验证门。

## Global Constraints

- 新增颜色 code 固定:14K金=`K14`、银色=`SV`(进变体 ID 后缀与主键,永久;不可改、不可复用 `S`)。— 设计 §2
- 颜色五属性集中在后端 `COLOR_VARIANTS` 一处;前端不得新增硬编码颜色 map,一律从接口派生。— 设计 §4
- 色块 hex:14K金 `#CBA94B`、银色 `#9AA7B0`;工艺名 method:K14→`14K金`、SV→`银`。— 设计 §2
- `common`:G/S/RG = `True`,K14/SV = `False`;列表顺序即展示顺序(常用在前)。— 设计 §3.1
- 不触碰库存/订单/电镀状态机;不改 `/parts/color-variants` 接口签名(仅多带字段);不动现有 G/S/RG 的 code/label/既有变体数据。— 设计 §5/§6
- 服务层错误 `raise ValueError`;后端测试用 `db`/`client` fixture。
- 提交信息结尾:`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- 设计文档:`docs/superpowers/specs/2026-06-27-plating-colors-14k-silver-design.md`;Mockup:`docs/superpowers/mockups/plating-colors-mockup.html`

---

### Task 1: 后端 `COLOR_VARIANTS` 富化 + 新增 K14 / SV

**Files:**
- Modify: `services/part.py:11-15`(`COLOR_VARIANTS` 定义)
- Test: `tests/test_part_variants.py`

**Interfaces:**
- Consumes: 现有 `create_part`, `create_part_variant`, `get_part`, `COLOR_VARIANTS`, `COLOR_CODES`, `COLOR_SUFFIXES`。
- Produces: `COLOR_VARIANTS` 为 5 条 dict,每条含 `code,label,method,badge,common`;`create_part_variant(db, root_id, color_code="K14")` → ID 后缀 `-K14`、名称后缀 `_14K金`;`"SV"` → `-SV` / `_银色`。`/parts/color-variants` 返回这 5 条(API 代码不变)。

- [ ] **Step 1: 写失败测试**

在 `tests/test_part_variants.py` 末尾追加:

```python
from services.part import COLOR_VARIANTS, COLOR_CODES, COLOR_SUFFIXES


def test_color_variants_has_five_enriched_entries():
    by_code = {c["code"]: c for c in COLOR_VARIANTS}
    assert set(by_code) == {"G", "S", "RG", "K14", "SV"}
    for c in COLOR_VARIANTS:
        assert set(c) >= {"code", "label", "method", "badge", "common"}
    assert by_code["G"]["common"] is True
    assert by_code["K14"]["common"] is False
    assert by_code["SV"]["common"] is False
    assert by_code["K14"]["label"] == "14K金"
    assert by_code["K14"]["method"] == "14K金"
    assert by_code["K14"]["badge"] == "#CBA94B"
    assert by_code["SV"]["label"] == "银色"
    assert by_code["SV"]["method"] == "银"
    assert by_code["SV"]["badge"] == "#9AA7B0"


def test_color_derived_maps_include_new_colors():
    assert COLOR_CODES["K14"] == "14K金"
    assert COLOR_CODES["SV"] == "银色"
    assert "14K金" in COLOR_SUFFIXES
    assert "银色" in COLOR_SUFFIXES


def test_create_variant_k14(db):
    root = create_part(db, {"name": "吊坠A", "category": "吊坠"})
    v = create_part_variant(db, root.id, color_code="K14")
    assert v.id == f"{root.id}-K14"
    assert v.name == "吊坠A_14K金"
    assert v.color == "14K金"


def test_create_variant_sv(db):
    root = create_part(db, {"name": "吊坠B", "category": "吊坠"})
    v = create_part_variant(db, root.id, color_code="SV")
    assert v.id == f"{root.id}-SV"
    assert v.name == "吊坠B_银色"
    assert v.color == "银色"


def test_create_variant_existing_g_unaffected(db):
    root = create_part(db, {"name": "吊坠C", "category": "吊坠"})
    v = create_part_variant(db, root.id, color_code="G")
    assert v.id == f"{root.id}-G"
    assert v.name == "吊坠C_金色"


def test_create_variant_invalid_code_raises(db):
    root = create_part(db, {"name": "吊坠D", "category": "吊坠"})
    with pytest.raises(ValueError):
        create_part_variant(db, root.id, color_code="ZZ")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_part_variants.py -k "color or k14 or sv" -v`
Expected: FAIL（`COLOR_VARIANTS` 仍只有 3 条 / 无 `method` 等键 / `K14` 不在 `COLOR_CODES`）

- [ ] **Step 3: 富化 `COLOR_VARIANTS` 并加两色**

`services/part.py`,把现有定义:

```python
COLOR_VARIANTS = [
    {"code": "G", "label": "金色"},
    {"code": "S", "label": "白K"},
    {"code": "RG", "label": "玫瑰金"},
]
```

替换为:

```python
COLOR_VARIANTS = [
    {"code": "G",   "label": "金色",   "method": "金",     "badge": "#DAA520", "common": True},
    {"code": "S",   "label": "白K",    "method": "白K",    "badge": "#C0C0C0", "common": True},
    {"code": "RG",  "label": "玫瑰金", "method": "玫瑰金", "badge": "#B76E79", "common": True},
    {"code": "K14", "label": "14K金",  "method": "14K金",  "badge": "#CBA94B", "common": False},
    {"code": "SV",  "label": "银色",   "method": "银",     "badge": "#9AA7B0", "common": False},
]
```

（`COLOR_SUFFIXES`、`COLOR_CODES`、`_LABEL_TO_CODE`、孤儿名正则均派生自此,自动跟随,无需改。）

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_part_variants.py -k "color or k14 or sv or g_unaffected or invalid_code" -v`
Expected: PASS

- [ ] **Step 5: 后端回归(变体 + 电镀相关)**

Run: `pytest tests/test_part_variants.py tests/test_part_cost.py tests/test_plating.py tests/test_api_plating.py -q`
Expected: 全部 PASS（注意:若有**先于本分支就失败**的用例,记录但不算回归——对照 `git stash`/main 判断）

- [ ] **Step 6: 提交**

```bash
git add services/part.py tests/test_part_variants.py
git commit -m "feat(parts): add 14K金/银色 colors and enrich COLOR_VARIANTS (method/badge/common)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: 前端 PlatingCreate 去硬编码 + 颜色分层

**Files:**
- Modify: `frontend/src/views/plating/PlatingCreate.vue`
- 参考:Mockup `docs/superpowers/mockups/plating-colors-mockup.html`(①)

**Interfaces:**
- Consumes: `/parts/color-variants` 现返回每项 `{code,label,method,badge,common}`(Task 1);该文件已 `getColorVariants()` 拉取到 `colorVariants`(ref,line 157;赋值 line 387)。
- Produces: 颜色 chip 按 `common` 分「常用直显 + 更多 ▾」;`BADGE_COLORS`/`COLOR_CODE_TO_METHOD`/`COLOR_LABEL_TO_CODE` 改为从 `colorVariants` 派生。

无前端单测;验证门 = `cd frontend && npm run build` 成功 + 对照 mockup。

- [ ] **Step 1: 删除硬编码常量**

删除这三处硬编码(line ~229-256 附近):
```js
const BADGE_COLORS = { G: '#DAA520', S: '#C0C0C0', RG: '#B76E79' }
const COLOR_CODE_TO_METHOD = { G: '金', S: '白K', RG: '玫瑰金' }
const COLOR_LABEL_TO_CODE = { '金色': 'G', '白K': 'S', '玫瑰金': 'RG' }
```
以及 line ~256 内联的 `{ '_金色': 'G', '_白K': 'S', '_玫瑰金': 'RG' }`(下一步改为派生)。

- [ ] **Step 2: 加派生 computed**

在 `colorVariants` ref 之后加(派生自已拉取的列表):
```js
import { computed } from 'vue'   // 若未引入则补
const badgeOf       = computed(() => Object.fromEntries(colorVariants.value.map(c => [c.code, c.badge])))
const methodOf      = computed(() => Object.fromEntries(colorVariants.value.map(c => [c.code, c.method])))
const codeOfLabel   = computed(() => Object.fromEntries(colorVariants.value.map(c => [c.label, c.code])))
const codeOfSuffix  = computed(() => Object.fromEntries(colorVariants.value.map(c => ['_' + c.label, c.code])))
const commonColors  = computed(() => colorVariants.value.filter(c => c.common))
const moreColors    = computed(() => colorVariants.value.filter(c => !c.common))
const showMoreColors = ref(false)
```
把原来引用 `BADGE_COLORS[x]` → `badgeOf.value[x]`(模板中 `badgeOf[x]`),`COLOR_CODE_TO_METHOD[code]` → `methodOf.value[code]`,`COLOR_LABEL_TO_CODE` → `codeOfLabel.value`,内联后缀 map → `codeOfSuffix.value`。逐处替换其在 `<script>` 与模板中的用法。

- [ ] **Step 3: 模板分层渲染**

把 line 83-100 的单层 `v-for="cv in colorVariants"` chip 行改为两层:常用色直接 `v-for="cv in commonColors"`;末尾加「更多 ▾」按钮 `@click="showMoreColors = !showMoreColors"`;再 `v-if="showMoreColors"` 渲染 `v-for="cv in moreColors"` 的 chip(chip 样式与原一致,`background/color/border` 用 `badgeOf[cv.code]`)。

- [ ] **Step 4: 构建验证**

Run: `cd frontend && npm run build`
Expected: 成功,无报错。

- [ ] **Step 5: 对照 mockup 自检**

颜色行默认只见 G/S/RG + 「更多 ▾」;展开见 K14/SV;选中色块填充正常;选 K14 工艺=`14K金`、SV=`银`。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/plating/PlatingCreate.vue
git commit -m "feat(plating-ui): derive colors from API + tiered picker in PlatingCreate

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: 前端 PlatingDetail 去硬编码 + 行内分层

**Files:**
- Modify: `frontend/src/views/plating/PlatingDetail.vue`
- 参考:Mockup(②)

**Interfaces:**
- Consumes: `/parts/color-variants`(Task 1);该文件已 `getColorVariants()` 拉到 `colorVariantList`(ref,line 656;赋值 line 1768)。
- Produces: 明细行内颜色 chip 按 `common` 分「常用 + ⋯ 展开」;删除 `BADGE_COLORS/COLOR_SUFFIX_MAP/COLOR_CODE_TO_METHOD/METHOD_TO_CODE/COLOR_LABEL_TO_CODE` 硬编码,改为派生。

验证门 = `npm run build` + 对照 mockup。

- [ ] **Step 1: 删除硬编码常量(line ~651-659)**

```js
const BADGE_COLORS = { G: '#DAA520', S: '#C0C0C0', RG: '#B76E79' }
const COLOR_SUFFIX_MAP = { '_金色': 'G', '_白K': 'S', '_玫瑰金': 'RG' }
const COLOR_CODE_TO_METHOD = { G: '金', S: '白K', RG: '玫瑰金' }
const METHOD_TO_CODE = { '金': 'G', '白K': 'S', '玫瑰金': 'RG' }
const COLOR_LABEL_TO_CODE = { '金色': 'G', '白K': 'S', '玫瑰金': 'RG' }
```

- [ ] **Step 2: 加派生(基于 `colorVariantList`)**

```js
const badgeOf      = computed(() => Object.fromEntries(colorVariantList.value.map(c => [c.code, c.badge])))
const methodOf     = computed(() => Object.fromEntries(colorVariantList.value.map(c => [c.code, c.method])))
const codeOfMethod = computed(() => Object.fromEntries(colorVariantList.value.map(c => [c.method, c.code])))
const codeOfLabel  = computed(() => Object.fromEntries(colorVariantList.value.map(c => [c.label, c.code])))
const codeOfSuffix = computed(() => Object.fromEntries(colorVariantList.value.map(c => ['_' + c.label, c.code])))
const commonColors = computed(() => colorVariantList.value.filter(c => c.common))
const moreColors   = computed(() => colorVariantList.value.filter(c => !c.common))
const expandedColorRows = ref(new Set())   // 行内「⋯」展开态(按行 id)
function toggleColorRow(id) { const s = new Set(expandedColorRows.value); s.has(id) ? s.delete(id) : s.add(id); expandedColorRows.value = s }
```
把原对 `BADGE_COLORS/COLOR_SUFFIX_MAP/COLOR_CODE_TO_METHOD/METHOD_TO_CODE/COLOR_LABEL_TO_CODE` 的引用全部替换为对应 `*.value` 派生 map(`COLOR_SUFFIX_MAP` → `codeOfSuffix.value`,`METHOD_TO_CODE` → `codeOfMethod.value`,等)。

- [ ] **Step 3: 行内颜色列分层渲染(render fn,line ~1570-1589)**

把 `colorVariantList.value.map(...)` 渲染改为:先渲染 `commonColors.value` 的 chip;若该行未展开,追加一个「⋯」span(`onClick: () => toggleColorRow(row.id)`);若 `expandedColorRows.value.has(row.id)`,再渲染 `moreColors.value` 的 chip。chip 的 `color/background/border` 用 `badgeOf.value[cv.code]`,文案 `cv.code`,active 判断不变。

- [ ] **Step 4: 构建验证**

Run: `cd frontend && npm run build`
Expected: 成功。

- [ ] **Step 5: 对照 mockup 自检**

明细行常用色直显 + 「⋯」;点开见 K14/SV;不撑爆行宽;选色后工艺名联动。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/plating/PlatingDetail.vue
git commit -m "feat(plating-ui): derive colors from API + inline tiered chips in PlatingDetail

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: 前端 PartList 改拉接口 + 去硬编码 + 加变体分层

**Files:**
- Modify: `frontend/src/views/parts/PartList.vue`
- 参考:Mockup(③)

**Interfaces:**
- Consumes: `/parts/color-variants`(Task 1);`getColorVariants` 已在 `@/api/parts` 导出(`frontend/src/api/parts.js:21`)。
- Produces: PartList 不再硬编码 `VARIANT_COLORS/COLOR_CODE_REVERSE`,改为 `onMounted` 拉接口后派生;「加颜色变体」选项分「常用 + 更多颜色 ▾」。

验证门 = `npm run build` + 对照 mockup。

- [ ] **Step 1: 引入 API 并改为拉取**

确认顶部 `import { ... } from '@/api/parts'` 含 `getColorVariants`(无则补)。新增 ref + 加载:
```js
const colorVariants = ref([])
const codeOfLabel   = computed(() => Object.fromEntries(colorVariants.value.map(c => [c.label, c.code])))
const variantColorOptionsAll = computed(() => colorVariants.value.map(c => ({ code: c.code, label: `${c.label} ${c.code}`, badge: c.badge, common: c.common })))
const commonVariantColors = computed(() => variantColorOptionsAll.value.filter(c => c.common))
const moreVariantColors   = computed(() => variantColorOptionsAll.value.filter(c => !c.common))
const showMoreVariantColors = ref(false)
```
在 `onMounted`(或现有首屏加载处)加:`getColorVariants().then(r => { colorVariants.value = r.data })`。

- [ ] **Step 2: 删除硬编码 + 改引用(line ~416-420, 448)**

删除:
```js
const COLOR_CODE_REVERSE = { '金色': 'G', '白K': 'S', '玫瑰金': 'RG' }
const VARIANT_COLORS = [ { code:'G', label:'金色 G' }, { code:'S', label:'白K S' }, { code:'RG', label:'玫瑰金 RG' } ]
```
把对 `COLOR_CODE_REVERSE` 的引用(如 line 438 `.map(v => COLOR_CODE_REVERSE[v.color])`)改为 `codeOfLabel.value[v.color]`;把基于 `VARIANT_COLORS` 的下拉/选项(line 424、`specVariantColorOptions` line 448)改为基于 `variantColorOptionsAll.value`(或分层的 common/more)。

- [ ] **Step 3: 加变体颜色选项分层渲染**

在编辑弹窗「加颜色变体」处:常用色 `v-for="cv in commonVariantColors"` 直列;加「＋ 更多颜色 ▾」`@click="showMoreVariantColors = !showMoreVariantColors"`;`v-if="showMoreVariantColors"` 渲染 `moreVariantColors`。色点用 `cv.badge`。

- [ ] **Step 4: 构建验证**

Run: `cd frontend && npm run build`
Expected: 成功。

- [ ] **Step 5: 对照 mockup 自检**

加变体处常用三色 + 「更多颜色 ▾」;展开见 14K金/银色;选 14K金生成 `…-K14`、银色 `…-SV`(经 Task 1 后端);现有 G/S/RG 加变体不受影响。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/parts/PartList.vue
git commit -m "feat(parts-ui): fetch colors from API + tiered variant-color options

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage(对照设计文档):**
- §3.1 富化 COLOR_VARIANTS + K14/SV → Task 1 ✅
- §3.2 既有派生项自动跟随(回归)→ Task 1 Step 5 + 测试 `*_derived_maps_*` ✅
- §3.3 API 无需改 → 计划未改 api/parts.py;Task 2/3/4 直接消费 ✅
- §4.1 派生映射替换硬编码 → Task 2/3/4 各自派生 ✅
- §4.2 PlatingCreate 分层 → Task 2 ✅
- §4.3 PlatingDetail 行内分层 → Task 3 ✅
- §4.4 PartList 改拉接口 + 分层 → Task 4 ✅
- §6 YAGNI(不做颜色管理 UI/不迁库/不动现有 G/S/RG)→ 计划未涉及 ✅

**Placeholder scan:** 无 TBD/TODO;后端步骤含完整代码与命令;前端步骤给出确切删除项(带行号)、派生代码、渲染改法与 build 门。前端因文件大,采用「定位+替换片段」而非整文件重写,与既往前端任务一致。

**Type consistency:** 三个前端任务派生 map 命名一致(`badgeOf/methodOf/codeOfLabel/codeOfMethod/codeOfSuffix/commonColors/moreColors`);后端字段名 `method/badge/common` 在 Task 1 定义、Task 2/3/4 消费一致;`K14/SV/14K金/银色/#CBA94B/#9AA7B0/银` 全程一致。

---

## Execution Handoff

计划已保存到 `docs/superpowers/plans/2026-06-27-plating-colors-14k-silver.md`。
