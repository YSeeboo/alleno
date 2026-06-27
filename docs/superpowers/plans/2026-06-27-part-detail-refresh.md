# 配件详情页刷新 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 刷新配件详情页(视觉对齐 PartList、统计卡、变体家族、基本信息就地编辑),并把子配件添加从「逐个加」改成「批量多选 + 暂存 + 复制 BOM」,后端新增一个批量 BOM 端点。

**Architecture:** 后端新增 `set_part_bom_batch`(先校验全部、再逐条写,保证原子性)+ `POST /{part_id}/bom/batch` 端点。前端重写 `PartDetail.vue`:复用 PartList 的 ink+emerald token 与 eyebrow 分区;变体家族由 `getPartVariants` 组装;基本信息就地编辑复用 PartList 编辑字段集;子配件区改为多选暂存批量提交 + 复制其他配件 BOM。

**Tech Stack:** FastAPI + SQLAlchemy；pytest;Vue 3.5 + Naive UI;前端 `npm run build` 作验证门。

## Global Constraints

- 服务层纯函数,`db.flush()`(不 commit);业务错误 `raise ValueError`(API 经 `service_errors()` → 400)。— CLAUDE.md
- 批量添加**原子**:任一条非法(用量≤0、子件不存在、自环、循环、批内重复)→ 整批不写入。实现为「先校验全部、再写全部」。— 设计 §6
- 仅新增 `POST /{part_id}/bom/batch`;不改 `/parts/{id}/bom`、`/parts/{id}/variants` 等现有接口签名。— 设计 §7
- 基本信息可编辑字段:名称/颜色/单位/规格/单件成本三项(purchase_cost·bead_cost·plating_cost)/默认电镀工艺(plating_process)/图片;**类目锁定**;**变体的颜色锁定**。— 设计 §5.2
- 视觉对齐 PartList:左上返回 + 面包屑、统计卡、eyebrow 分区、ink(#1A1D21)+emerald(#1E7A5A),去旧红(#ffd6d6)/蓝(#2080f0/#1890ff)。— 设计 §2
- 变体家族:根件查 `getPartVariants` 返回「仅变体」→ family=[当前,...变体];变体查返回「根+全部变体」→ family=该列表;family.length<=1 则隐藏该区。— 设计 §5.1
- 提交信息结尾:`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- 设计文档:`docs/superpowers/specs/2026-06-27-part-detail-refresh-design.md`;Mockup:`docs/superpowers/mockups/part-detail-mockup.html`

---

### Task 1: 后端批量 BOM 端点

**Files:**
- Modify: `services/part_bom.py`(新增 `set_part_bom_batch`)
- Modify: `schemas/part_bom.py`(新增 `PartBomBatchItem` / `PartBomBatchSet`)
- Modify: `api/parts.py`(新增 `POST /{part_id}/bom/batch`)
- Test: `tests/test_part_bom.py`

**Interfaces:**
- Consumes: 现有 `set_part_bom(db, parent_part_id, child_part_id, qty_per_unit)`、`_would_create_cycle(db, parent_part_id, child_part_id)`、`Part`、`service_errors`。
- Produces:
  - `set_part_bom_batch(db, parent_part_id: str, items: list[dict]) -> list` —— items 每项 `{"child_part_id": str, "qty_per_unit": float}`;先校验全部再写。
  - `POST /api/parts/{part_id}/bom/batch`,body `PartBomBatchSet{items: [PartBomBatchItem{child_part_id, qty_per_unit>0}]}`,返回写入结果列表。前端 Task 3 依赖此端点。

- [ ] **Step 1: 写失败测试**

`tests/test_part_bom.py` 末尾追加(复用文件顶部已有的 `from models.part import Part` 与 `_setup_parts`):

```python
def test_set_part_bom_batch_adds_all(client, db):
    parent, children = _setup_parts(db)
    resp = client.post(f"/api/parts/{parent.id}/bom/batch", json={
        "items": [
            {"child_part_id": children[0].id, "qty_per_unit": 1.0},
            {"child_part_id": children[1].id, "qty_per_unit": 2.0},
            {"child_part_id": children[2].id, "qty_per_unit": 4.0},
        ]
    })
    assert resp.status_code == 200
    assert len(resp.json()) == 3
    got = client.get(f"/api/parts/{parent.id}/bom")
    assert len(got.json()) == 3


def test_set_part_bom_batch_invalid_child_is_atomic(client, db):
    parent, children = _setup_parts(db)
    resp = client.post(f"/api/parts/{parent.id}/bom/batch", json={
        "items": [
            {"child_part_id": children[0].id, "qty_per_unit": 1.0},
            {"child_part_id": "PJ-X-NOPE", "qty_per_unit": 1.0},
        ]
    })
    assert resp.status_code == 400
    # atomic: the valid item must NOT have been written
    got = client.get(f"/api/parts/{parent.id}/bom")
    assert len(got.json()) == 0


def test_set_part_bom_batch_self_ref_rejected(client, db):
    parent, _children = _setup_parts(db)
    resp = client.post(f"/api/parts/{parent.id}/bom/batch", json={
        "items": [{"child_part_id": parent.id, "qty_per_unit": 1.0}]
    })
    assert resp.status_code == 400


def test_set_part_bom_batch_duplicate_in_batch_rejected(client, db):
    parent, children = _setup_parts(db)
    resp = client.post(f"/api/parts/{parent.id}/bom/batch", json={
        "items": [
            {"child_part_id": children[0].id, "qty_per_unit": 1.0},
            {"child_part_id": children[0].id, "qty_per_unit": 2.0},
        ]
    })
    assert resp.status_code == 400


def test_set_part_bom_batch_zero_qty_rejected(client, db):
    parent, children = _setup_parts(db)
    resp = client.post(f"/api/parts/{parent.id}/bom/batch", json={
        "items": [{"child_part_id": children[0].id, "qty_per_unit": 0}]
    })
    assert resp.status_code == 422
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_part_bom.py -k batch -v`
Expected: FAIL（端点不存在 / `set_part_bom_batch` 未定义）

- [ ] **Step 3: 加 schema**

`schemas/part_bom.py`,在 `PartBomSet` 之后追加:

```python
class PartBomBatchItem(BaseModel):
    child_part_id: str
    qty_per_unit: float = Field(gt=0)


class PartBomBatchSet(BaseModel):
    items: list[PartBomBatchItem]
```

- [ ] **Step 4: 实现服务(先校验全部,再写全部)**

`services/part_bom.py`,在 `set_part_bom` 之后追加:

```python
def set_part_bom_batch(db: Session, parent_part_id: str, items: list[dict]) -> list:
    """批量 upsert 子配件 BOM。先校验全部条目(原子:校验失败则一条不写),再逐条写。"""
    parent = db.query(Part).filter_by(id=parent_part_id).first()
    if not parent:
        raise ValueError(f"配件 {parent_part_id} 不存在")
    seen = set()
    for it in items:
        cid = it["child_part_id"]
        if cid == parent_part_id:
            raise ValueError("配件不能引用自身作为子配件")
        if cid in seen:
            raise ValueError(f"子配件 {cid} 在本批次中重复")
        seen.add(cid)
        if not db.query(Part).filter_by(id=cid).first():
            raise ValueError(f"配件 {cid} 不存在")
        if _would_create_cycle(db, parent_part_id, cid):
            raise ValueError("不能添加此子配件关系，会形成循环引用")
    return [set_part_bom(db, parent_part_id, it["child_part_id"], it["qty_per_unit"]) for it in items]
```

- [ ] **Step 5: 加端点**

`api/parts.py`:把 import 行扩为同时引入 schema 与服务:

```python
from schemas.part_bom import PartBomSet, PartBomBatchSet
from services.part_bom import set_part_bom, get_part_bom, delete_part_bom_item, set_part_bom_batch
```

在现有 `api_set_part_bom`(`POST /{part_id}/bom`)之后追加:

```python
@router.post("/{part_id}/bom/batch")
def api_set_part_bom_batch(part_id: str, body: PartBomBatchSet, db: Session = Depends(get_db)):
    with service_errors():
        return set_part_bom_batch(db, part_id, [i.model_dump() for i in body.items])
```

（确认 `api/parts.py` 顶部已 import `service_errors`;若无则从 `api._errors` 引入,与其他端点一致。）

- [ ] **Step 6: 运行测试确认通过**

Run: `pytest tests/test_part_bom.py -k batch -v`
Expected: PASS（5 个）

- [ ] **Step 7: BOM 回归**

Run: `pytest tests/test_part_bom.py tests/test_api_bom.py -q`
Expected: 全部 PASS

- [ ] **Step 8: 提交**

```bash
git add services/part_bom.py schemas/part_bom.py api/parts.py tests/test_part_bom.py
git commit -m "feat(parts): batch set_part_bom endpoint (validate-all-then-write)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: 前端 PartDetail 视觉刷新 + 统计卡 + 变体家族 + 基本信息就地编辑

**Files:**
- Modify: `frontend/src/views/parts/PartDetail.vue`
- 参考:`frontend/src/views/parts/PartList.vue`(token/类、编辑字段集),Mockup `docs/superpowers/mockups/part-detail-mockup.html`

**Interfaces:**
- Consumes(均已存在):`getPart`、`updatePart`、`getPartVariants`、`getStock`、`getStockLog`、`getPartCostLogs`、`listParts`、`getPartBom`(本任务保留现有子配件表的读)。
- Produces:刷新后的查看 + 基本信息就地编辑;`子配件`区暂保留**现状**实现(Task 3 再改)。

无前端单测;验证门 = `cd frontend && npm run build` 成功 + 对照 mockup。

- [ ] **Step 1: 顶部 + 统计卡 + eyebrow 骨架**

把 `<template>` 顶部(`n-space 返回 + n-h2` 与三个 `n-card`)替换为 PartList 风格结构:左上 `← 返回`(`router.back()`)→ 面包屑「商品 / 配件管理 / 配件详情」→ 标题区(`part.name` + 编号 chip + 类目 tag + `part.parent_part_id ? '变体' : '根件'` 标签)。从 `PartList.vue` `<style>` 复制需要的类(`.page-top/.stat-strip/.stat-card/.btn-ink/.btn-outline` 等),并按 mockup 加 `.sec/.sec-h/.t/.r-acts/.sbtn/.kv` 等(见 mockup `<style>`,可直接搬)。

统计卡(4):
```html
<div class="stat-strip">
  <div class="stat-card"><div class="stat-label">当前库存</div><div class="stat-value" :class="{ 'stat-danger': stock < 10 }">{{ stock }}</div></div>
  <div class="stat-card"><div class="stat-label">单件成本</div><div class="stat-value">¥{{ part.unit_cost != null ? fmtMoney(part.unit_cost) : '-' }}</div></div>
  <div class="stat-card"><div class="stat-label">子配件</div><div class="stat-value">{{ partBomList.length }}</div></div>
  <div class="stat-card"><div class="stat-label">变体</div><div class="stat-value">{{ variantCount }}</div></div>
</div>
```

- [ ] **Step 2: 基本信息(key-value 网格)+ 价格历史沿用**

把基本信息从 `n-descriptions bordered` 改为 mockup 的 `.kv` 网格,字段:编号、配件、图片(去掉 `#ffd6d6` 边框,用中性 `1px solid var(--line)`)、类目、颜色(色点 + 标签)、单位、默认电镀工艺、组合件(`part.is_composite ? '是' : '否'`)、关联原色配件(父件链接,蓝色改 emerald)、单件成本(沿用现有 `costBreakdown` + `costLogs` 的 popover,触发样式改成 emerald 胶囊)。分区头右侧放「✎ 编辑」按钮(`.sec-h .r-acts`)。

- [ ] **Step 3: script — 变体家族组装 + 计数**

```js
import { getPartVariants } from '@/api/parts'   // 确认已在 import 列表
const variantFamily = ref([])
const variantCount = computed(() => Math.max(0, variantFamily.value.length - 1))
async function loadVariantFamily() {
  try {
    const { data: fam } = await getPartVariants(partId.value)
    if (part.value && part.value.parent_part_id == null) {
      variantFamily.value = [part.value, ...fam]      // 根件:fam 仅变体
    } else {
      variantFamily.value = fam                        // 变体:fam 含根+全部变体
    }
    variantFamily.value.sort((a, b) => a.id.localeCompare(b.id))
  } catch (_) { variantFamily.value = [] }
}
```
在 `onMounted` 里 `part.value` 就绪后调用 `loadVariantFamily()`。变体家族行需要库存:对家族每个 id 调用 `batchGetStock('part', ids)`(`@/api/inventory`,PartList 已用)填充 `stock`,或复用单个 `getStock`(家族通常很小)。

- [ ] **Step 4: 变体家族区(模板)**

`v-if="variantFamily.length > 1"` 时渲染一张表:列 颜色(色点 `badgeOfLabel?` 可省,直接用 `part.color` 文本 + 中性点)/ 编号(后缀高亮)/ 单件成本 / 库存(<10 标红)/ →(`router.push('/parts/'+row.id)`);`row.id === partId` 高亮「当前」,`row.parent_part_id == null` 标「根」。无变体不渲染该区(组合件天然无变体)。

- [ ] **Step 5: 基本信息就地编辑**

「✎ 编辑」打开编辑(`n-modal` 或就地表单),字段与锁定**对齐 PartList 的编辑弹窗**:名称 / 颜色(`editingIsVariant`= `!!part.parent_part_id` 时禁用)/ 单位 / 规格 / 单件成本三项(`purchase_cost`/`bead_cost`/`plating_cost`,`n-input-number` precision 7)/ 默认电镀工艺 / 图片(复用 `ImageUploadModal`,kind `part`);类目只读展示、不可改。提交:
```js
async function saveBasicInfo() {
  const { category, ...data } = editForm   // 不提交 category
  await updatePart(partId.value, data)
  message.success('已保存')
  const { data: fresh } = await getPart(partId.value)
  part.value = fresh
  // 成本可能变 → 价格历史可后台刷新
  getPartCostLogs(partId.value).then(r => { costLogs.value = r.data }).catch(() => {})
  showEdit.value = false
}
```

- [ ] **Step 6: 保留库存流水区(eyebrow 化)**

库存流水表沿用现有 `logColumns` 数据,外层换成 eyebrow 分区;变动数量颜色 emerald(`#1E7A5A`)/ danger(`#E5484D`)统一。子配件区本任务**保持现状实现不动**(Task 3 改)。

- [ ] **Step 7: 构建验证**

Run: `cd frontend && npm run build`
Expected: 成功。

- [ ] **Step 8: 对照 mockup 自检**

返回在左上、统计卡四项、基本信息无旧红蓝、变体家族三态(根/变体/无变体)、「✎ 编辑」可改基本信息并刷新。

- [ ] **Step 9: 提交**

```bash
git add frontend/src/views/parts/PartDetail.vue
git commit -m "feat(parts-ui): refresh PartDetail visuals + stat strip + variant family + inline edit

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: 前端 PartDetail 子配件区 — 批量多选暂存 + 复制 BOM

**Files:**
- Modify: `frontend/src/api/parts.js`(加 `setPartBomBatch` 包装)
- Modify: `frontend/src/views/parts/PartDetail.vue`(子配件区)
- 参考:Mockup(子配件 BOM 区)

**Interfaces:**
- Consumes:`POST /{part_id}/bom/batch`(Task 1);现有 `getPartBom`、`deletePartBom`、`setPartBom`(保留已有 BOM 行的内联改用量/删)、`listParts`(候选配件)。
- Produces:子配件区改为搜索多选 + 暂存表(可改用量,默认 1)+ 「批量添加 N 项」+ 「复制其他配件 BOM」。

验证门 = `npm run build` + 对照 mockup。

- [ ] **Step 1: API 包装**

`frontend/src/api/parts.js` 末尾追加:
```js
export const setPartBomBatch = (partId, items) => api.post(`/parts/${partId}/bom/batch`, { items })
```

- [ ] **Step 2: 暂存状态 + 候选**

在 `PartDetail.vue` `<script>` 增加:
```js
import { setPartBomBatch } from '@/api/parts'
const staged = ref([])          // [{ child_part_id, child_part_name, child_part_image, qty_per_unit }]
const batchSubmitting = ref(false)
// 候选 = childPartOptions(已有)排除自身 + 已在 BOM + 已暂存
const stageableOptions = computed(() => {
  const taken = new Set([...partBomList.value.map(b => b.child_part_id), ...staged.value.map(s => s.child_part_id)])
  return childPartOptions.value.filter(o => !taken.has(o.value))
})
function stagePart(opt) {
  if (!opt) return
  staged.value.push({ child_part_id: opt.value, child_part_name: opt.name, child_part_image: opt.image, qty_per_unit: 1 })
}
function unstage(i) { staged.value.splice(i, 1) }
async function submitBatch() {
  if (staged.value.length === 0) return
  batchSubmitting.value = true
  try {
    await setPartBomBatch(partId.value, staged.value.map(s => ({ child_part_id: s.child_part_id, qty_per_unit: s.qty_per_unit })))
    message.success(`已添加 ${staged.value.length} 项`)
    staged.value = []
    await loadPartBom()
  } catch (e) { message.error(e.response?.data?.detail || '批量添加失败') }
  finally { batchSubmitting.value = false }
}
```

- [ ] **Step 3: 复制其他配件 BOM**

```js
async function copyBomFrom(sourceId) {
  if (!sourceId) return
  const { data } = await getPartBom(sourceId)
  const taken = new Set([...partBomList.value.map(b => b.child_part_id), ...staged.value.map(s => s.child_part_id)])
  for (const b of data) {
    if (b.child_part_id === partId.value || taken.has(b.child_part_id)) continue
    staged.value.push({ child_part_id: b.child_part_id, child_part_name: b.child_part_name, child_part_image: b.child_part_image, qty_per_unit: b.qty_per_unit })
    taken.add(b.child_part_id)
  }
  message.success('已预填到待添加列表,可微调后提交')
}
```
入口:子配件分区头右侧「📋 复制其他配件 BOM」按钮 → 打开一个选择源配件的 `n-select`(filterable,options 用 `childPartOptions`)→ 选定调 `copyBomFrom(id)`。

- [ ] **Step 4: 模板 — 子配件区改造**

把现有「`n-divider 添加子配件` + 单选 + 单数量 + 确认添加」整段替换为(参考 mockup):已有 BOM 表保留(沿用 `bomColumns` 的内联改用量/删)+ 批量面板:多选搜索(`n-select` filterable + `@update:value=stagePart` 后清空,options=`stageableOptions`,`render-label=renderOptionWithImage`)→ 暂存表(`n-data-table` 或简单表:子配件名+图、`n-input-number` 改 `qty_per_unit`(min 0.01)、删除按钮 `unstage(i)`)→ 底部「清空」(`staged=[]`)+「批量添加 {{ staged.length }} 项」(`submitBatch`,`:disabled="staged.length===0"`,`:loading="batchSubmitting"`)。

- [ ] **Step 5: 构建验证**

Run: `cd frontend && npm run build`
Expected: 成功。

- [ ] **Step 6: 对照 mockup 自检**

多选把配件加入暂存表、逐行可改用量、「批量添加 N 项」一次写入并刷新 BOM;「复制其他配件 BOM」预填暂存表;候选正确排除自身/已有/已暂存;非法批次报错不部分写入(Task 1 已保证)。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/api/parts.js frontend/src/views/parts/PartDetail.vue
git commit -m "feat(parts-ui): batch multi-select staging + copy-BOM for sub-parts

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage(对照设计文档):**
- §3 结构(返回左上/面包屑/标题/统计卡/eyebrow)→ Task 2 ✅
- §4.1 批量端点(validate-then-write)→ Task 1 ✅;§4.2 全复用 → Task 2/3 未改现有接口 ✅
- §5.1 变体家族组装(三态)→ Task 2 Step 3/4 ✅
- §5.2 基本信息就地编辑(字段/锁定)→ Task 2 Step 5 ✅
- §5.3 子配件批量 + 复制 BOM → Task 3 ✅
- §6 原子性 → Task 1(validate-then-write)+ 测试 `*_atomic` ✅
- §7 YAGNI(不加复制端点、不改现有接口、不做变体就地新建)→ 计划未涉及 ✅

**Placeholder scan:** 无 TBD/TODO;后端步骤含完整代码与命令;前端因文件大,采用「定位+替换片段 + 关键逻辑代码 + build 门」,与既往前端任务一致;mockup 的 `<style>` 类可直接搬用。

**Type consistency:** `set_part_bom_batch(db, parent_part_id, items)` 在 Task 1 定义、端点与前端 `setPartBomBatch(partId, items)` 一致;`staged` 行字段 `{child_part_id, qty_per_unit, ...}` 与端点 items 一致;`variantFamily`/`variantCount`/`loadVariantFamily` 命名自洽;基本信息编辑字段与 §5.2/PartList 一致。

---

## Execution Handoff

计划已保存到 `docs/superpowers/plans/2026-06-27-part-detail-refresh.md`。
