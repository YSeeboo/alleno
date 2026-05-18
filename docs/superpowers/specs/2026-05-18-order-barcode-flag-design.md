# 订单条码标记（has_barcode）设计文档

## 背景

订单已有 `barcode_text` / `barcode_image` 字段，用于存放具体条码内容/图片。但在订单创建阶段，店员往往尚不知道具体条码内容，只想先标记"这单需要贴条码"作为一个**属性**，便于在列表中一眼识别、在生产环节优先安排贴标。

本次改动新增一个独立的布尔属性 `has_barcode`，与具体的 `barcode_text` / `barcode_image` **完全解耦**：可以先勾"有条码"再补内容，也可以只有内容没勾选（两种状态独立合法）。

## 数据模型

`Order` 表新增 1 个字段：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| has_barcode | Boolean, NOT NULL | `false` | 订单是否需要贴条码（属性标记，与 barcode_text/image 解耦） |

不加索引（当前无按此字段过滤的查询）。

## API

### 修改接口

**`POST /orders`** — 创建订单，请求体新增可选字段：

```
Request: {
  customer_name: str,
  created_at?: str,
  items: [...],
  has_barcode?: bool   // 默认 false
}
```

**`PATCH /orders/{order_id}/extra-info`** — 现有接口，请求体新增可选字段：

```
Request: {
  ...,
  has_barcode?: bool   // None 表示不修改，true/false 显式更新
}
```

**`GET /orders/{order_id}` / `GET /orders`** — 响应 schema (`OrderResponse`) 新增 `has_barcode: bool` 字段。

### Service 层

- `services/order.py::create_order(...)` 新增参数 `has_barcode: bool = False`，写入 ORM 实例
- `services/order.py::update_order_extra_info(...)` 新增 `has_barcode: Optional[bool] = None`，仅当非 None 时赋值

业务规则：`has_barcode` 与 `barcode_text` / `barcode_image` 完全独立，**不做联动**（不强制要求、不级联清空）。

## 前端

### OrderCreate.vue（新建订单）

在「创建时间」`n-form-item` 正下方新增一行：

- `n-form-item` 标签留空（保留对齐缩进）
- 内部放 `n-checkbox` + 文案 `需要贴条码`
- 默认未勾选；提交时将 `hasBarcode.value` 作为 `has_barcode` 加入 payload

### OrderList.vue（订单列表）

将「客户名」列从纯文本改为 `render` 函数：

- 渲染客户名文本
- 仅当 `row.has_barcode === true` 时，在客户名右侧追加一个 `n-tag`：
  - 文案：`有条码`
  - 颜色：宝矿力蓝（背景 `#00A0E9`，文字白色）。通过 Naive UI 的自定义颜色 prop 实现：
    ```vue
    <n-tag size="small" :bordered="false"
           :color="{ color: '#00A0E9', textColor: '#fff' }"
           style="margin-left: 8px; font-weight: 600; letter-spacing: 0.5px;">
      有条码
    </n-tag>
    ```

不新增列。其余列保持不变。

### OrderDetail.vue（订单详情）

两处变化：

1. **页头**：客户名右侧条件性渲染同款蓝白「有条码」chip（视觉上与列表一致）。
2. **额外信息编辑区**：
   - 在 `barcode_text` 输入框上方新增一行勾选（label 留空，复用现有 form 布局）
   - 复用现有 `extraInfo` reactive 对象，新增字段 `has_barcode`
   - 保存仍走 `PATCH /orders/{id}/extra-info`，无需新接口

`extraInfo.value.has_barcode` 在 `loadOrder` 时从订单响应中同步：`extraInfo.value.has_barcode = !!o.has_barcode`。

### 移动端

沿用现有 `:label-placement="isMobile ? 'top' : 'left'"`，新加的 form-item 自动跟随，无需额外适配。

## 迁移

在 `database.py::ensure_schema_compat()` 的 `order` 表缺列检查清单中加入：

```python
("has_barcode", "BOOLEAN NOT NULL DEFAULT FALSE"),
```

启动时若 `order` 表无该列，自动执行：

```sql
ALTER TABLE "order" ADD COLUMN has_barcode BOOLEAN NOT NULL DEFAULT FALSE;
```

PostgreSQL 会自动把所有现存行填为 `false`，无需手写回填脚本。

## 测试

### 新增用例

`tests/test_api_orders.py`：

1. `test_create_order_default_has_barcode_false` — 不传 `has_barcode` 时，响应与 DB 中均为 `false`
2. `test_create_order_with_has_barcode_true` — 传 `has_barcode=true` 时，正确持久化
3. `test_order_response_includes_has_barcode_field` — `GET /orders/{id}` 响应包含此字段

`tests/test_api_order_todo.py`（已含 extra-info 测试组）：

4. `test_patch_extra_info_toggles_has_barcode` — 切换 `has_barcode` 不影响 `barcode_text` / `barcode_image`，三者独立

`tests/test_db_compat.py`：

5. 旧 `order` 表（无 `has_barcode` 列）经 `ensure_schema_compat()` 后列存在且默认 `false`

## 边界与不做的事

| 项 | 决策 |
|---|---|
| 与 `barcode_text` / `barcode_image` 联动 | **不做**。三者解耦 |
| 列表按 `has_barcode` 过滤 | **不做**。当前无此需求；YAGNI |
| `has_barcode` 加索引 | **不做**。无过滤查询 |
| 权限 | **沿用订单现有权限**。无新增权限点 |
| Bot / Telegram / Feishu | **不动**。条码属性仅 Web UI 管理 |
| Excel / PDF 导出 | **不在本版本范围** |
| 移动端特殊适配 | **无需**。复用现有响应式 form 布局 |
