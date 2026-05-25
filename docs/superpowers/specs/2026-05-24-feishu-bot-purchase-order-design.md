# 飞书 bot 结构化建采购单设计

日期：2026-05-24

## 背景

机器人当前对接 DeepSeek agent loop，工具偏向通用问答；店主和店员日常**很少**真正用它。问诊后定位到核心症状是"前端建单路径太长"——在加工/采购流程里建单要点 10+ 下下拉、搜索、加行。其中 **采购单** 是店主在供应商现场最痛、最常做的动作：

- 字段闭合（vendor + 多条 part_id/qty/price），结构简单
- 店主多在外、想"打几个字就完事"
- 比起 UI 翻找，**打字反而更快**

把这件事放到飞书 bot 上做（飞书是用户在国内现场可用、卡片交互成熟的平台），既能让 bot 真正承担一个高频核心任务，又是一次试金石——成立后再扩 plating/handcraft 等。

## 范围

**首期只交付：通过飞书 bot 用一条结构化消息建一张采购单。**

包含：
- 结构化文本解析
- 配件与店家校验（含店家模糊匹配）
- 飞书 interactive 卡片预览
- 内联按钮"确认建单 / 取消"
- 创建采购单（复用现有 `create_purchase_order` 服务，连带触发 `add_stock("采购入库")`）

明确不在本期：
- 修改已建采购单（追加 item、改价、改状态）
- 标记付款 / 上传送货图 / 备注字段
- 拍照建单（视觉识别）
- 预览阶段 inline 编辑（用户点错→取消重发，不做卡片内修改）
- 在 Telegram 落同一套（仅飞书首发，做完 API 自然可复用，但首期不交付 Telegram 适配）

## 整体流程

```
用户在飞书向 bot 发一条文本
   │
   ▼
process_feishu_message
   │
   ▼ is_purchase_text(text)?
   ├─ 否 → 走原 DeepSeek agent 路径（无改动）
   └─ 是 → parser → resolver
          │
          ├─ 解析/校验失败 → 错误卡片，结束
          │
          └─ 成功 → 存草稿 → 发预览卡片（带 [确认建单][取消] 按钮）
                              │
                              ▼ 用户点按钮
                          card.action.trigger 进 webhook
                              │
                  ┌───────────┴───────────┐
                  ▼                       ▼
              确认                      取消
              pop 草稿                 pop 草稿
              create_purchase_order    丢弃
              add_stock("采购入库")
              回最终成功卡片            回"已取消"卡片
```

**关键 invariant：confirm 之前不动任何持久化状态。** 解析失败、token 失效、用户点取消——库存、`purchase_order` 表均不变。

## 消息格式

```
李老板
PJ-DZ-0001 100 5
PJ-LT-0003 50 3.5
PJ-X-0012 200 0.8 元
```

- **第 1 行**：店家名（任意非空字符串，不限格式）
- **第 2 行起**：每行一条采购明细
- **每行 3 或 4 个 token**：
  - 3 token：`<part_id> <qty> <price>`
  - 4 token：`<part_id> <qty> <unit> <price>`
- **数字尾缀剥离**：`100个` / `100件` / `100包` → 100；`5元` / `5块` / `￥5` / `¥5.5` → 5 / 5.5
- 缺省 unit = `个`
- 行间多余空白行允许；首尾空白允许

## 模块分解

### `bot/purchase_parser.py`（纯函数，无 DB）

```python
@dataclass
class ParsedItem:
    line_no: int
    raw_line: str
    part_id: str          # 去空格、未补零、未转大小写——严格保持用户输入
    qty: Decimal
    unit: str             # 默认 "个"
    price: Decimal

@dataclass
class ParseError:
    line_no: int          # 0 表示整体性错（如无明细）
    raw_line: str
    reason: str           # 给用户看的中文原因

@dataclass
class ParsedPurchase:
    vendor_name: str
    items: list[ParsedItem]

def is_purchase_text(text: str) -> bool:
    """启发式：≥2 行非空；第 2 行匹配 `\\S+\\s+\\d+(?:\\.\\d+)?\\s+...`；
    第 1 行不匹配 item 模式。"""

def parse_purchase_text(text: str) -> ParsedPurchase | list[ParseError]:
    """逐行解析。任何一行错就收集到 errors（不 short-circuit），
    最后若 errors 非空就一并返回。"""
```

### `bot/purchase_resolver.py`（与 DB 交互）

```python
@dataclass
class ResolvedItem:
    line_no: int
    part_id: str
    part_name: str
    part_image: str | None
    qty: Decimal
    unit: str
    price: Decimal
    amount: Decimal       # qty * price

@dataclass
class ResolvedPurchase:
    vendor_name: str           # 最终用于建单的名字（命中后改写为后台规范名）
    vendor_is_new: bool        # 用于卡片上"新店家"警告
    items: list[ResolvedItem]
    total_amount: Decimal

@dataclass
class ResolveError:
    kind: str                  # "part_not_found" | "vendor_ambiguous"
    detail: dict               # part_not_found: {lines: [{line_no, part_id, raw}]}
                               # vendor_ambiguous: {input, candidates: [...]}

def resolve(db, parsed: ParsedPurchase) -> ResolvedPurchase | ResolveError
```

**part_id 严格匹配**：直接 `Part.id == parsed.part_id`，不归一化不补零不大小写折叠。

**vendor 匹配规则**（按优先级）：
1. exact match → 用该 vendor 名
2. 否则 existing_name 是 input 的子串 → 取最长那个（满足"腾飞商家 → 腾飞"）
3. 否则 input 是 existing_name 的子串 → 候选数 == 1 时直接用；> 1 时返回 `vendor_ambiguous`（让用户打更具体）
4. 都没命中 → vendor_is_new = True，用 input 原样

子串规则中"子串"取最朴素的 `in` 关系，**要求 input 与 existing_name 都 strip() 后非空且长度 ≥ 2**——防止"李"误命中所有以"李"开头的店家。

**part 错误一次性收集**：所有 part_id 一次查 `IN (...)`，找出缺失的所有行返回，不分批不 short-circuit。

### `bot/purchase_draft_store.py`（仅内存）

两张内存表：**草稿表**（未确认）和 **已消费表**（已建单的 token）。

```python
import secrets, time
from threading import RLock

_TTL_SECONDS = 3600
_lock = RLock()

# 草稿表：token -> (data, created_at, sender_open_id)
_drafts: dict[str, tuple[ResolvedPurchase, float, str]] = {}

# 已消费表：token -> (po_id, created_at, sender_open_id)
# 用途：double-confirm 时回 "这张单已建好 CG-XXXX"
_consumed: dict[str, tuple[str, float, str]] = {}

def put(data: ResolvedPurchase, sender_open_id: str) -> str:
    """生成 token 存入草稿表，顺便惰性清理两表过期项。返回 token。"""

def put_with_token(token: str, data: ResolvedPurchase, sender_open_id: str) -> None:
    """create 失败时回滚用：把数据按原 token 写回草稿表。"""

def pop_draft(token: str, sender_open_id: str) -> ResolvedPurchase | None:
    """从草稿表原子取出并删除；未命中 / 过期 / sender 不符返回 None。"""

def mark_consumed(token: str, po_id: str, sender_open_id: str) -> None:
    """confirm 成功后调用，写入已消费表。"""

def get_consumed_po(token: str, sender_open_id: str) -> str | None:
    """double-confirm 时用：返回该 token 已建的 PO id；未命中 / 过期 / sender 不符返回 None。"""
```

### `bot/feishu_card_handler.py`（新）

处理 `card.action.trigger` 事件：

```python
async def handle_card_action(action_value: dict, sender_open_id: str, chat_id: str):
    """
    action_value: {"action": "confirm" | "cancel", "token": "..."}
    """
```

- `confirm`：
  1. `get_consumed_po(token)` 命中 → 回 `这张单已建好 CG-XXXX` 卡片（幂等）
  2. `pop_draft(token)`；为 None → 回 `预览已失效，请重新发送`
  3. 调 `create_purchase_order(db, vendor_name, [...], status="未付款")`
     - 成功 → `mark_consumed(token, po_id)`，回成功卡片
     - 抛 `ValueError` → `put_with_token(token, data)` 回滚草稿，回失败卡片（用户可重点）
     - 抛其它 `Exception` → log，**不回滚**，回"系统错误"卡片（避免脏状态被反复触发）

- `cancel`：
  1. `pop_draft(token)`（不写已消费表）
  2. 回 `已取消` 卡片

### `bot/feishu_cards.py`（新，模板函数）

```python
def render_preview_card(data: ResolvedPurchase, token: str) -> dict
def render_success_card(po_id: str, vendor: str, total: Decimal, item_count: int) -> dict
def render_cancel_card() -> dict
def render_parse_error_card(errors: list[ParseError]) -> dict
def render_resolve_error_card(error: ResolveError) -> dict
def render_token_expired_card() -> dict
def render_already_created_card() -> dict
```

返回 dict（飞书 card schema 2.0）。`render_preview_card` 的两个按钮 `value` 形如：

```json
{"action": "confirm", "token": "abc123"}
{"action": "cancel",  "token": "abc123"}
```

### `bot/handlers.py`（修改）

新增：
```python
async def send_feishu_card(chat_id: str, card: dict) -> None:
    """POST im/v1/messages with msg_type=interactive, content=json.dumps(card)."""
```

`process_feishu_message` 头部插入分发：

```python
async def process_feishu_message(chat_id: str, text: str, sender_open_id: str) -> None:
    if is_purchase_text(text):
        await _process_purchase_text(chat_id, text, sender_open_id)
        return
    # 原 agent 路径不变
    ...
```

`sender_open_id` 需要从 webhook 一直传下来（目前没传，要在 `api/feishu.py` 加一个参数）。

### `api/feishu.py`（修改）

1. webhook 处理函数按 `header.event_type` 分发：
   - `im.message.receive_v1` → 现有逻辑（增加传 sender_open_id）
   - `card.action.trigger`（或 v2 是 `card.action.trigger_v1`，以飞书文档为准） → 调用 `handle_card_action`
2. 卡片回调签名/解密：飞书对 card action 的回调若启用了 v2 加密，要按飞书要求验签。首期假设与 message webhook 同 endpoint 同验签策略，复用已有逻辑。

## 卡片内容

### 预览卡片

```
┌─ 采购单预览 ────────────────┐
│ 店家：腾飞 ✓                  │  ← 命中（exact / 子串）
│ 或：腾飞商家 ⚠ 新店家         │  ← 未命中
│                                │
│ 明细：                         │
│  PJ-DZ-00001 吊坠A             │
│   100 × 个 × 5.00 = 500.00     │
│  PJ-LT-00003 链条B             │
│   50 × 个 × 3.50 = 175.00      │
│  PJ-X-00012 小配件C            │
│   200 × 个 × 0.80 = 160.00     │
│                                │
│ 合计：835.00 元 / 共 3 项       │
│                                │
│  [✅ 确认建单]  [❌ 取消]       │
└────────────────────────────────┘
```

### 成功卡片

```
✅ 采购单已创建
单号：CG-0123
店家：腾飞
合计：835.00 元 / 3 项
[查看详情] → https://<frontend>/purchase-orders/CG-0123
```

### 错误卡片（统一风格）

红色标题 + 行号 + 原因 + 建议。

| 场景 | 标题 | 内容 |
|---|---|---|
| 行格式错 | ❌ 解析失败 | 第 N 行 `<原文>`：`<reason>`（多个错一次性列出） |
| part_id 不存在 | ❌ 配件不存在 | 第 N 行：`<part_id>`（多个错一次性列出） |
| 首行像配件 | ❌ 首行不像店家名 | 首行 `<原文>` 看起来是配件编号，请先写店家 |
| 无明细 | ❌ 没有解析到明细行 | 至少写一条配件 |
| vendor 歧义 | ❌ 店家名歧义 | `<input>` 匹配到多个候选：`<list>`。请打更具体 |
| token 过期 | ⚠ 预览已失效 | 请重新发送 |
| token 已用 | ℹ 这张单已建好 | 单号 `CG-XXXX` |
| 后端错 | ❌ 建单失败 | `<ValueError.args[0]>` |

## 错误处理

**parse 阶段**：所有 `ParseError` 在一张卡片里列出，token 不生成，草稿不存。

**resolve 阶段**：
- part 错：所有缺失 part 在一张卡片里列出，token 不生成。
- vendor 歧义：错卡列候选，token 不生成。
- vendor 新店：**不报错**，预览卡上加 `⚠ 新店家` chip，等用户点确认。

**confirm 阶段**：
- token 不存在 / 过期 → "已失效"卡片
- token 已被消费（已消费集合命中）→ "已建好"卡片
- `create_purchase_order` 抛 `ValueError` → 失败卡片 + 草稿回滚到 store（允许用户回到预览状态再点）
- `create_purchase_order` 抛其它 `Exception` → 异常向上抛到 webhook handler 的全局 except，记 log，回"系统错误"卡片，**草稿不回滚**（防止数据不一致状态被反复触发）

## 测试

### `tests/test_purchase_parser.py`（纯函数）

- 正常 3-token 行
- 正常 4-token 行（含 unit）
- qty 尾缀：`100个`、`100件`、`100包` 都正确剥离
- price 尾缀：`5元`、`5块`、`￥5`、`¥5.5`
- 小数 qty 和 price
- 错行：缺 token / 数字非法 / 空 part_id
- 多行错一次性收集（验证 4 行里 2 行错时返回 2 个 ParseError）
- 第 1 行如果像 item → ParseError(line_no=1)
- 只有 1 行（仅店家）→ ParseError(line_no=0, "无明细")
- `is_purchase_text`：纯 NL 文本（"查一下吊坠库存"）应返回 False

### `tests/test_purchase_resolver.py`（用 `db` fixture）

- part exact 命中
- part 多行多个不存在 → 一次性返回所有缺失行
- vendor exact 命中
- vendor 正向子串："腾飞商家" 输入命中库里 "腾飞"
- vendor 反向子串："腾飞" 输入，库里有 "腾飞商家"——单候选时命中
- vendor 歧义：库里 "腾飞商家" + "腾飞贸易"，输入 "腾飞" → `vendor_ambiguous`
- vendor 全新 → `vendor_is_new=True`，名字原样

### `tests/test_purchase_draft_store.py`

- `put` → `pop_draft` 流转
- `pop_draft` TTL 过期不返回
- 同 token 二次 `pop_draft` 返回 None
- 不同 sender 的 token `pop_draft` 返回 None
- `mark_consumed` 后 `get_consumed_po` 命中；不同 sender 返回 None；TTL 过期返回 None
- `put_with_token` 回滚后再 `pop_draft` 能取到原数据

### `tests/test_api_feishu_purchase.py`（用 `client` fixture）

`send_feishu_message` / `send_feishu_card` / `_get_tenant_access_token` 全部 monkey-patch。

- 模拟 text webhook payload（采购消息）→ 断言 `send_feishu_card` 被调用 1 次 + content 包含预览结构 + 内联按钮 token
- 模拟 text webhook payload（非采购消息，如 "你好"）→ 断言走原 agent 路径（`run_agent` 被调用），`send_feishu_card` 未被调用
- 模拟 card.action.trigger confirm payload → 断言 PO 创建 + 库存 `add_stock("采购入库")` 写入 + 成功卡发出
- 模拟 card.action.trigger cancel payload → 断言无 PO、无 inventory_log、回"已取消"卡片
- 双击 confirm → 第二次返回"已建好"卡片，且只有 1 个 PO
- 输入有 1 行 part_id 不存在 → 错误卡片 + 无 PO + 无 inventory_log

## 配置

无新增 env。复用 `FEISHU_WHITELIST`、tenant_access_token 现有获取逻辑。

## 部署

- 仅后端代码变动 + `bot/` 下新模块
- 飞书后台：将 `card.action.trigger` 事件订阅到同一个 webhook URL（如果尚未订阅）
- 系统服务重启即可生效，无 DB migration

## 后续可扩展（非首期）

- Telegram inline keyboard 适配（复用 parser/resolver/draft_store/cards 抽象层；只新增飞书 vs Telegram 的卡片渲染与按钮回调适配）
- 扩展到 plating / handcraft / order 等单据
- 拍照建单：用 Vision 模型把小票照片转成同样的 `ParsedPurchase`，复用后半段流程
- "新店家"卡片上加 [仍然建] / [取消改名] 二次确认
- vendor 歧义场景用按钮让用户选候选，免去重发
