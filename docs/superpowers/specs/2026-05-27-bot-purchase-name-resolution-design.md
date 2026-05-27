# 飞书 bot 采购单：名称解析 + 消歧设计

日期：2026-05-27

## 背景

现有飞书建采购单流程要求每行第一个 token 是**配件编号**（严格匹配）。痛点：用户得先去平台查编号，采购项一多就很烦，bot 的速度优势归零——还不如平台，因为平台支持名称模糊搜索。

本设计把"名称→编号"的模糊解析搬进 bot：用户可以报名称，bot 模糊匹配；唯一命中直接走预览，命中多个则弹**逐行选择卡片**让用户点选。编号输入继续兼容。

参见前序设计 `docs/superpowers/specs/2026-05-24-feishu-bot-purchase-order-design.md`（解析/预览/确认/建单的基础流程，本设计在其 resolver 与卡片流程上扩展）。

## 范围

**只做 purchase。** plating/handcraft 的名称解析、agent 化、自然语言均不在本期。

包含：
- resolver 支持名称解析（编号 exact → 名称 exact → 名称模糊包含）
- 三态解析结果：全唯一 / 需消歧 / 有缺失
- 逐行消歧卡片 + 选择回调
- 一个 token 串起"消歧中 → 待确认 → 建单"

不做（YAGNI）：合并消歧卡、自动选最佳、按热度/最近排序、名称解析复用到其它单据。

## 解析规则（resolver）

行格式不变：`<编号或名称> <数量> [单位] <价格>`（按空格切，名称为单 token——已确认名称基本不含空格）。

每行第一个 token 解析顺序：
1. **编号 exact**：`Part.id == token`（大小写敏感，兼容老习惯）
2. 查不到 → **名称 exact**：`Part.name == token`
3. 再查不到 → **名称模糊**：复用 `services/_helpers.py` 的 `keyword_filter(token, Part.name)`（= `Part.name ILIKE '%token%'`，大小写不敏感包含）

每行结果：
- **0 个** → 缺失（not_found）
- **1 个**（任一步唯一命中）→ 解析为该 part
- **多个**（仅模糊步可能）→ 歧义（ambiguous），记下候选

> 注：编号 exact 命中即定，不再走名称；名称 exact 命中即定，不再走模糊。只有走到模糊步且 ILIKE 命中 >1 才算歧义。

## 三态结果

`resolve(db, parsed)` 返回从两态扩为三态：

```python
@dataclass
class Candidate:
    part_id: str
    part_name: str
    spec: str | None           # 展示用，区分 大/中/小 等系列
    part_image: str | None

@dataclass
class PendingLine:
    line_no: int
    query: str                 # 用户输入的名称 token
    qty: Decimal
    unit: str
    price: Decimal
    candidates: list[Candidate]
    chosen_part_id: str | None = None   # 消歧后填入

@dataclass
class NeedsDisambiguation:
    vendor_name: str
    vendor_is_new: bool
    resolved_items: list[ResolvedItem]   # 已唯一解析的行
    pending: list[PendingLine]           # 待消歧的行（按 line_no 升序）

# 既有：ResolvedPurchase（全部唯一）、ResolveError（有缺失）
```

`resolve` 判定优先级（从先到后，命中即返回）：
1. **任一行 part not_found → `ResolveError(kind="part_not_found")`**（整单拒绝，保持 all-or-nothing，最该先拦）
2. **vendor 歧义 → `ResolveError(kind="vendor_ambiguous")`**（与现状一致；在进入逐行 part 消歧之前先把 vendor 问题拦掉）
3. 否则有 part ambiguous 行 → `NeedsDisambiguation`
4. 否则全唯一 → `ResolvedPurchase`（与现状一致，直接预览）

vendor 解析逻辑不变（编号路径不影响 vendor 模糊匹配）；消歧阶段不再重解析 vendor（已固定在草稿里）。

候选 `spec` 取 `Part.spec`（无则 None）；展示为 `编号 名称(spec)`，帮用户区分系列。候选按 `part_id` 升序（确定性）。

## 状态机

一条消息进来（`_process_purchase_text`）：

```
parse_purchase_text → resolve
  ├ ResolveError        → 错误卡片，整单拒绝，不存草稿，结束
  ├ NeedsDisambiguation → put 草稿(=该对象) → 发首个 pending 行的消歧卡（带 token）
  └ ResolvedPurchase    → put 草稿(=该对象) → 发预览卡（confirm/cancel，现状不变）
```

**消歧阶段**，每张消歧卡的候选按钮 value：
```json
{"action": "disambiguate", "token": "...", "line_no": 2, "part_id": "PJ-DZ-00001"}
```

`handle_card_action` 的 `disambiguate` 分支：
1. `get_draft(token, sender)` **peek**（不弹出）；为 None → "预览已失效，请重发"
2. 若取出的不是 `NeedsDisambiguation`（已是 ResolvedPurchase / 已处理）→ 幂等兜底：忽略本次选择，重发当前状态对应的卡（已就绪则预览卡）
3. 找到该 `line_no` 的 PendingLine：
   - 已有 `chosen_part_id` → 幂等：忽略，直接推进
   - 否则把 `chosen_part_id` 设为按钮带的 `part_id`（校验该 part_id 在候选内，防伪造）
4. `put_with_token(token, draft)` 写回
5. 找下一个 `chosen_part_id is None` 的 pending：
   - **还有** → 发下一张消歧卡（进度 `(已选+1)/总歧义数`）
   - **没有了** → 组装 `ResolvedPurchase`（resolved_items + 各 pending 的 chosen part 查库构造 ResolvedItem，重算 total）→ `put_with_token` 覆盖为该 ResolvedPurchase → 发预览卡（confirm/cancel，**同一个 token**）

此后 confirm/cancel 完全复用现有流程（confirm 用 `pop_draft` 取出 ResolvedPurchase 建单）。**整个交互一个 token 串到底。**

## 落地改动

| 文件 | 改动 |
|---|---|
| `bot/purchase_resolver.py` | `resolve` 改三态；加名称 exact + 模糊（`keyword_filter`）；新增 `Candidate` / `PendingLine` / `NeedsDisambiguation` |
| `bot/purchase_draft_store.py` | 新增 `get_draft(token, sender)`（peek，不删，带 TTL/sender 校验）；草稿对象现在可能是 `NeedsDisambiguation` 或 `ResolvedPurchase`，store 本身存任意对象、改动极小 |
| `bot/feishu_cards.py` | 新增 `render_disambiguation_card(pending_line, token, progress)`（候选按钮 + 进度 + 行原始名称/数量/价格） |
| `bot/feishu_card_handler.py` | `handle_card_action` 加 `disambiguate` 分支（上面状态机） |
| `bot/handlers.py` | `_process_purchase_text` 处理 `NeedsDisambiguation` 分支 → 发首张消歧卡 |

`is_purchase_text`（dispatch 启发式）**不改**——名称行第二 token 以数字开头，已命中现有 `^\S+\s+\d` 规则。

`bot/purchase_parser.py` **不改**——它只切分、不查库；名称作为第一个 token 原样带出。

## 错误处理 / 边界

- not_found 仍整单拒绝（与现状一致）
- 同名出现在多行 → 按 `line_no` 各自独立消歧
- 消歧中途 token 过期（>1h）→ `get_draft` 返回 None → "预览已失效，请重发"
- 重复点同一候选 / 点已解析的行 → 幂等：已定的行忽略再选，直接推进到当前状态
- 点过期/已转预览的旧消歧卡 → 草稿已是 ResolvedPurchase 或已被 pop → 幂等兜底（重发预览卡 / "已处理"提示），不报错不重复建单
- 按钮带的 `part_id` 必须在该行候选列表内，否则忽略（防构造请求）
- 中途放弃 → 草稿 TTL 自然过期

## 测试

### `tests/test_bot_purchase_resolver.py`（扩展）
- 编号 exact 命中（不走名称）
- 名称 exact 命中（不走模糊）
- 名称模糊唯一命中 → ResolvedPurchase
- 名称模糊多个 → NeedsDisambiguation，pending 含候选、按 part_id 升序
- 0 命中 → ResolveError(part_not_found)
- 混合：部分行唯一 + 部分行歧义 → NeedsDisambiguation，resolved_items 与 pending 分得对
- not_found 优先：既有缺失行又有歧义行 → ResolveError（不是 NeedsDisambiguation）
- 候选携带 spec

### `tests/test_bot_purchase_draft_store.py`（扩展）
- `get_draft` peek 不删除（连续两次都拿得到）
- `get_draft` 的 TTL / sender 校验
- `get_draft` 后 `put_with_token` 覆盖类型（NeedsDisambiguation → ResolvedPurchase）

### `tests/test_bot_feishu_cards.py`（扩展）
- `render_disambiguation_card`：含候选编号/名称/spec、进度、token、按钮 value 带 line_no + part_id；JSON 安全

### `tests/test_api_feishu_purchase.py`（扩展）
- 单行歧义：发消息 → 收消歧卡 → 点候选 → 收预览卡 → confirm → 建单 + 库存
- 多行歧义：连点两次 → 第二次后才出预览卡
- 名称唯一命中：直接出预览卡（不出消歧卡）
- not_found：整单拒绝，不出消歧卡、不建单
- 消歧 token 过期 → 失效提示
- 重复点同一候选 → 幂等，不重复推进/建单
- 伪造 part_id（不在候选内）→ 忽略

## 部署

纯后端，无 schema 变更，无新 env。systemd 重启即生效。
