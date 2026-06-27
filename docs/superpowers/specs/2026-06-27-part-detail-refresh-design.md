# 配件详情页刷新 — 设计文档

- 日期：2026-06-27
- 分支：`feat/part-detail-refresh`
- Mockup：`docs/superpowers/mockups/part-detail-mockup.html`

## 1. 背景与目标

`frontend/src/views/parts/PartDetail.vue` 仍是旧 Naive 默认视觉(`n-card 标题 + n-descriptions bordered + n-h2`、残留旧品牌红/蓝),与已刷新的 PartList(ink+emerald、统计卡、eyebrow 分区)不一致;且存在功能缺口:看不到变体家族、不能就地编辑、添加子配件只能一个个加。

本设计:(1) 视觉对齐 PartList;(2) 新增**变体家族**区(变体感知);(3) 顶部统计卡;(4) 基本信息**就地编辑**;(5) 子配件 BOM 改为**批量多选 + 暂存 + 复制 BOM**。

## 2. 关键决策(已与用户对齐)

| 决策点 | 结论 |
|---|---|
| 视觉 | 对齐 PartList:左上返回 + 面包屑 + 标题区、统计卡、eyebrow 分区、ink+emerald、去旧红蓝 |
| 返回键 | 放**左上角**(面包屑上方);面包屑「配件管理」亦可回列表 |
| 基本信息编辑 | 保留就地编辑,入口为「基本信息」分区标题右侧的「✎ 编辑」小按钮(非右上大按钮),仅改基本信息字段 |
| 变体家族 | 新增区:根件+全部变体一张表,当前行高亮,可互跳;无变体则隐藏该区;组合件不支持变体故无此区 |
| 统计卡 | 当前库存 / 单件成本 / 子配件数 / 变体数 |
| 子配件添加 | 批量:搜索多选 → 暂存表(每行可改用量,默认 1) → 一次「批量添加 N 项」 |
| 用量 | 默认 1,加入后可在暂存表逐行即改 |
| 复制 BOM | 保留「复制其他配件 BOM」加速器:选源件 → 拉其 BOM 预填暂存表 → 微调 → 批量提交 |

## 3. 页面结构(自上而下)

1. **左上「← 返回」** → 面包屑「商品 / 配件管理 / 配件详情」。
2. **标题区**:配件名 + 编号 chip + 类目 tag + 「根件 / 变体」标签。
3. **统计卡(4)**:当前库存(低于阈值标红) / 单件成本(副标「采购+穿珠+电镀」) / 子配件数 / 变体数。
4. **基本信息**(eyebrow,右侧「✎ 编辑」):编号、配件、图片、类目、颜色(色点)、单位、默认电镀工艺、组合件(是/否)、关联原色配件(父件链接)、单件成本(构成 + 「价格历史」入口,沿用现有 cost log popover)。
5. **变体家族**(eyebrow,仅当有变体时显示)：表格 列=颜色(色点+标签)/ 编号(后缀高亮)/ 单件成本 / 库存(低标红)/ →跳转;当前件高亮 + 「当前」标识,根件标「根」。
6. **子配件 BOM**(eyebrow,右侧「📋 复制其他配件 BOM」)：已有 BOM 表(编号/子配件/每单位用量内联编辑/删除)+ 批量添加面板。
7. **库存流水**(eyebrow)：时间 / 变动数量(涨绿跌红)/ 原因 / 备注。

## 4. 后端变更

仅新增**一个批量 BOM 端点**;其余全复用现有接口。

### 4.1 批量设置子配件 BOM

`services/part_bom.py` 新增:

```python
def set_part_bom_batch(db: Session, parent_part_id: str, items: list[dict]) -> list:
    """批量 upsert 子配件 BOM。items: [{"child_part_id": str, "qty_per_unit": float}, ...]
    复用 set_part_bom 的单条校验逻辑;任一条非法则整体回滚(异常冒泡 → get_db 回滚)。"""
    results = []
    for it in items:
        results.append(set_part_bom(db, parent_part_id, it["child_part_id"], it["qty_per_unit"]))
    return results
```

`schemas/part_bom.py` 新增:

```python
class PartBomBatchItem(BaseModel):
    child_part_id: str
    qty_per_unit: float = Field(..., gt=0)

class PartBomBatchSet(BaseModel):
    items: list[PartBomBatchItem]
```

`api/parts.py` 新增端点(挂在 parts 权限下,与现有 BOM 端点一致):

```python
@router.post("/{part_id}/bom/batch")
def api_set_part_bom_batch(part_id: str, body: PartBomBatchSet, db: Session = Depends(get_db)):
    with service_errors():
        return set_part_bom_batch(db, part_id, [i.model_dump() for i in body.items])
```

前端 API 包装 `frontend/src/api/parts.js`：`export const setPartBomBatch = (partId, items) => api.post(\`/parts/${partId}/bom/batch\`, { items })`

**单条 `set_part_bom` 的既有校验**(自环、子件存在、组合件规则等)在批量里逐条沿用,无需重复实现。

### 4.2 全部复用(不改)

- `getPart` / `updatePart`(基本信息读 + 就地编辑写)
- `getPartVariants`(变体家族:从变体查返回「根+全部变体」,从根件查只返回变体)
- `getPartBom` / `deletePartBom`(已有 BOM 表;复制 BOM = 对源件调 `getPartBom`)
- `getStock` / `getStockLog`(库存 + 流水)
- 价格历史 `getPartCostLogs`(沿用现有 popover)

## 5. 前端变更(`PartDetail.vue` 重写)

复用 PartList 的设计 token 与类(`.page-top/.stat-strip/.chip/.btn-ink/.btn-outline` 等),分区头沿用 eyebrow（`.sec-h .t` + 右侧 `.r-acts`）。

### 5.1 变体家族组装(前端逻辑)

```
fam = await getPartVariants(id)          // 根查→只变体；变体查→[根]+全部变体
if (part.parent_part_id == null)         // 当前是根件
    family = [part, ...fam]
else                                     // 当前是变体
    family = fam                         // 已含根+全部变体
family 按 id 排序；标记 current = (row.id === id)；标记 root = (row.parent_part_id == null)
变体数 = family.length - 1
若 family.length <= 1 → 不渲染「变体家族」区
```

### 5.2 基本信息就地编辑

「✎ 编辑」打开编辑表单(模态或就地切换),字段 = 名称/颜色/单位/规格/单件成本三项(采购·穿珠·电镀)/默认电镀工艺/图片;类目锁定;变体的颜色锁定。提交调 `updatePart(id, data)`,成功后刷新基本信息 + 统计卡(成本/库存可能变)。复用 PartList 编辑弹窗的字段与锁定规则(避免两套逻辑漂移)。

### 5.3 子配件批量添加面板

- **搜索多选**:输入框搜配件(名称/编号),回车或点选把配件加入「暂存表」;已选项显示为可移除 chip;排除当前件自身与已在 BOM 中的件。
- **暂存表**:每行 = 子配件(图+名+编号) / 每单位用量(内联 `n-input-number`,默认 1,可改) / 删除。
- **批量添加 N 项**:校验(用量 > 0)后调 `setPartBomBatch(id, items)`,成功后清空暂存、刷新 BOM 表 + 子配件数统计。
- **复制其他配件 BOM**:点「📋 复制其他配件 BOM」→ 选一个源配件 → `getPartBom(源)` 把其子件 + 用量预填进暂存表(去重已存在的)→ 用户微调 → 走同一个「批量添加」。
- 已有 BOM 表保留现有的内联改用量 / 删除(沿用 `setPartBom` 单条 + `deletePartBom`)。

## 6. 边界与规则

- 仅前端重写 + 一个批量端点;不动库存模型、变体模型、电镀/手工逻辑。
- 「批量添加」整体事务:任一条非法(用量≤0、子件不存在、触发组合件/自环规则)→ 整批回滚并报错。
- 变体家族纯展示 + 跳转;不在此处编辑变体。
- 组合件:无变体家族区(组合件不支持变体);子配件 BOM 为其主体。
- 编辑只覆盖基本信息;BOM、库存、变体各有自己的操作区,不归「✎ 编辑」管。

## 7. 不做（YAGNI）

- 不做 BOM 行拖拽排序、版本历史。
- 不做变体在详情页就地新建/改色(仍在列表「加变体」做)。
- 不为「复制 BOM」单独加后端端点(前端 `getPartBom` + 批量端点足够)。
- 不改 `/parts/{id}/bom`、`/variants` 等现有接口签名。

## 8. 测试要点

- 后端:`set_part_bom_batch` 批量 upsert 成功;含一条非法用量/不存在子件 → 整批回滚(无部分写入);空 items 列表的处理;端点 200 返回结果列表。
- 后端回归:单条 `set_part_bom` / `get_part_bom` / `delete_part_bom_item` 不受影响。
- 前端:`npm run build` 通过;变体家族在「根件视角 / 变体视角 / 无变体」三态正确(无变体隐藏区、当前行高亮、互跳);批量添加把多选项一次写入并刷新;复制 BOM 预填暂存表;就地编辑改基本信息后刷新统计卡;返回在左上、视觉对齐 PartList。
