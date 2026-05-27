# 飞书 bot 采购单：多关键字名称（右锚定解析）设计

日期：2026-05-27

## 背景

上一期让 bot 支持按名称建采购单，但解析是"左定位"——按空格切，第一个 token 当名称，后面当数量/价格。结果名称**只能是一个 token / 一个关键字**。中等撞名时，单个关键字常命中多个、频繁触发消歧。

`keyword_filter`（平台搜索用的）本就支持多关键字（空格分词、AND 匹配），瓶颈纯在解析方式。本设计把解析改成**右锚定**：行尾固定是"数量 [单位] 价格"，**前面剩下的全部 token 拼成名称/搜索串**，丢给 `keyword_filter` 做多关键字 AND 匹配，从而让用户多打几个词收窄候选、很多时候直接唯一命中、省掉消歧。

参见 `docs/superpowers/specs/2026-05-27-bot-purchase-name-resolution-design.md`（名称解析 + 消歧基础）。

## 范围

只改 `bot/purchase_parser.py`。resolver / draft store / cards / handler **均不改**——`keyword_filter` 已支持多词，名称串原样流过去即可。

不做：按权重/最近排序、缩略图、plating/handcraft、agent。

## 解析规则：从左定位改为右锚定

行 = `<名称…(可多 token)> <数量> [单位] <价格>`。`_parse_item` 新逻辑：

1. `tokens = raw_line.split()`
2. **币种词粘合（保留现有）**：若最后一个 token 是"纯币种词"（`_strip_suffix(tok, _PRICE_SUFFIXES) == ""`，如 `元`/`块`/`￥`/`¥`），并入前一个 token 再丢弃。
3. 粘合后 `len(tokens) < 3` → ParseError（至少需要 名称 数量 价格）。
4. `price_raw = tokens[-1]`。
5. **单位判定**：
   - 若 `len(tokens) >= 4` 且 `tokens[-2]` 恰好是单位词（属于 `_QTY_SUFFIXES = (个, 件, 包)`）→ `unit = tokens[-2]`，`qty_raw = tokens[-3]`，`name_tokens = tokens[:-3]`
   - 否则 → `unit = "个"`，`qty_raw = tokens[-2]`，`name_tokens = tokens[:-2]`
6. `qty = _parse_decimal(qty_raw, _QTY_SUFFIXES)`；None → ParseError("数量无法识别")；`<= 0` → ParseError。
7. `price = _parse_decimal(price_raw, _PRICE_SUFFIXES)`；None → ParseError("单价无法识别")；`< 0` → ParseError。
8. `name_tokens` 为空 → ParseError("名称为空")。
9. `ParsedItem.part_id = " ".join(name_tokens)`（字段名沿用 `part_id`，语义现在是"编号或名称搜索串"；不改字段名以免牵动 resolver/cards）。

**向后兼容验证**（右锚定对旧格式结果不变）：
- `PJ-DZ-0001 100 5` → name="PJ-DZ-0001", qty=100, price=5 ✓
- `PJ-DZ-0001 100 件 5` → tokens[-2]="件" 是单位 → unit=件, qty=100, name="PJ-DZ-0001" ✓
- `PJ-LT-00003 50 3.5 元` → 粘合成 `3.5元` → qty=50, price=3.5 ✓
- `PJ-DZ-0001 100个 5` → qty_raw="100个"→100 ✓

**新增能力**：
- `玫瑰 大 100 5` → name="玫瑰 大", qty=100, price=5
- `玫瑰吊坠 镂空 50 件 3` → name="玫瑰吊坠 镂空", unit=件, qty=50, price=3

**边界**：
- 名称首 token 恰好是单位词（如 `包 玫瑰 100 5`）→ 单位判定只看 `tokens[-2]`（=100，非单位）→ name="包 玫瑰"，正确。
- 名称里夹单位词但不在 `-2` 位（如 `玫瑰 个 100 5`）→ "个" 落在 name 里（name="玫瑰 个"）；单位只识别紧贴价格前那个，与"数量 单位 价格"的位置约定一致。
- 数量位非数字（如 `玫瑰 大 5`，把"大"当数量）→ "大"解析失败 → ParseError("数量无法识别：'大'")，提示明确。

## dispatch 启发式：从"第二 token 是数字"改为"行尾是数量+价格"

多关键字行第二个 token 可能还是个词，现有 `_ITEM_FIRST_TOKEN_RE`（`^\S+\s+\d`）会漏判。改为判断**行尾是否 数量+价格**。

新增 `_looks_like_item_line(line) -> bool`（复用现有 `_strip_suffix`/`_parse_decimal`）：
```
tokens = line.split()；币种词粘合（同 _parse_item 第 2 步）
若 len(tokens) < 3 → 走 PJ- 兜底判定
qpos = -3 if (len>=4 and tokens[-2] in _QTY_SUFFIXES) else -2
price 可解析(_parse_decimal(tokens[-1], _PRICE_SUFFIXES) is not None)
  且 qty 可解析(_parse_decimal(tokens[qpos], _QTY_SUFFIXES) is not None)
  → True；否则 False
另外：line 以 PJ-（忽略大小写）开头 → 也返回 True（保留"编号行即使数量写错也进采购流程、给解析错误卡"的行为）
```

用处：
- `is_purchase_text`：`len(lines) >= 2 and _looks_like_item_line(lines[1])`
- `parse_purchase_text` 里"首行看起来像配件"的判定，也改用 `_looks_like_item_line(vendor_name)`（替换 `_ITEM_FIRST_TOKEN_RE`）

`_ITEM_FIRST_TOKEN_RE` 删除（被 `_looks_like_item_line` 取代）；`_PART_ID_TOKEN_RE`（PJ- 检测）保留并并入 `_looks_like_item_line`。

## resolver / 其它：不改

`_candidates_for(db, token)` 收到的 `token` 现在可能是多词串（如 `"玫瑰 大"`）：
- `db.get(Part, "玫瑰 大")` → None（编号无空格，多词永不误命中编号）
- `Part.name == "玫瑰 大"` → 一般无
- `keyword_filter("玫瑰 大", Part.name)` → `name ILIKE %玫瑰% AND name ILIKE %大%` → 收窄

`_MIN_FUZZY_LEN` 守卫作用于整串长度（"玫瑰 大" 长度 ≥2，通过；单字符 "大" 仍被挡）。多词里夹短词由 AND 收窄，无需逐词加门槛。**resolver 零改动**，但加测试固化该行为。

## 测试

### `tests/test_bot_purchase_parser.py`（扩展）
- 多关键字：`玫瑰 大 100 5` → part_id="玫瑰 大", qty=100, price=5
- 多关键字 + 单位：`玫瑰吊坠 镂空 50 件 3` → part_id="玫瑰吊坠 镂空", unit=件, qty=50, price=3
- 向后兼容回归：现有 4 条（id、id+unit、币种词、qty 后缀）结果不变（确保旧测试全过）
- 名称首 token 是单位词：`包 玫瑰 100 5` → name="包 玫瑰"
- `<3` token → ParseError
- 数量位非数字：`玫瑰 大 5`（被当作 name=玫瑰 qty=大 price=5）→ "数量无法识别"
- `is_purchase_text`：多关键字行 True；纯 NL（"查一下库存"）False；`PJ-DZ-X abc 5`（坏 qty 的编号行）True（走解析给错误卡）
- 首行像 item（`PJ-DZ-0001 100 5` 当首行）→ parse_purchase_text 标"首行看起来是配件"

### `tests/test_bot_purchase_resolver.py`（扩展，固化多词收窄）
- 库里 `玫瑰吊坠大`、`玫瑰吊坠小`；query `"玫瑰吊坠 大"` → 唯一命中 `玫瑰吊坠大`（ResolvedPurchase，不进消歧）

### `tests/test_api_feishu_purchase.py`（扩展）
- 多关键字消息收窄到唯一 → 直接预览卡（不出消歧卡）

## 部署

纯后端、单文件、无 schema 变更、无新 env。systemd 重启生效。
