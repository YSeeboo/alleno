# 客户货号 设计文档

## 背景

订单饰品清单需要记录客户方的商品编号（客户货号），方便生产和发货对照。部分客户货号为连号（如 MG-02 ~ MG-12），需支持批量快速填入。

## 数据模型

`OrderItem` 表新增 1 个字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| customer_code | String, nullable | 客户货号 |

## API

### 修改接口

**PATCH `/orders/{order_id}/items/{item_id}`** — 更新单个饰品行的客户货号

```
Request: { customer_code: str | null }
Response: OrderItemResponse（含 customer_code）
```

**POST `/orders/{order_id}/items/batch-customer-code`** — 批量填入连号客户货号

```
Request: {
  item_ids: list[int],       // 选中的饰品行 ID
  prefix: str,               // 前缀，如 "MG-"
  start_number: int,          // 起始号，如 2
  padding: int = 2            // 补零位数，如 2 → "02"
}
Response: { updated_count: int }
```

逻辑：将 item_ids 按 OrderItem.id 升序排列，依次赋值 `{prefix}{start_number+i:0{padding}d}`。

**GET `/orders/{order_id}/items`** — 响应中包含 customer_code 字段

## 前端

### 饰品清单表格

- 在"饰品编号"列右侧新增"客户货号"列
- 单元格可直接点击进入编辑状态（inline edit），失焦或回车时保存
- 空值显示为灰色占位文字 "—"

### 批量填入连号

- 饰品清单表格增加勾选列（checkbox）
- 勾选多行后，表格上方出现【批量填入客户货号】按钮
- 点击弹出小弹窗：
  - 前缀输入框（如 "MG-"）
  - 起始号输入框（如 2）
  - 位数选择（默认 2，即补零到 2 位）
  - 预览：MG-02, MG-03, ... MG-06（根据选中行数动态显示）
  - 【确定】【取消】
- 确定后调用批量接口，刷新表格
