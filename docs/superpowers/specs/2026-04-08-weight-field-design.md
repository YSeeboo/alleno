# 发出/收回重量字段 设计文档

## 背景

电镀和手工的发出/收回需要记录物料重量，用于核对和对账。

## 数据模型

以下 4 个表各增加 2 个字段：

| 表 | 新增字段 |
|----|---------|
| `plating_order_item` | `weight` Numeric(10,4) nullable, `weight_unit` String nullable (默认 "g") |
| `handcraft_part_item` | 同上 |
| `handcraft_jewelry_item` | 同上 |
| `plating_receipt_item` | 同上 |
| `handcraft_receipt_item` | 同上 |

`weight_unit` 取值：`"g"` 或 `"kg"`。

## 列位置

重量列位于**发出数量列之后**。

## Schema 变更

所有相关的 Create/Response schemas 增加：
- `weight: float | None = None`
- `weight_unit: str | None = None`

## API 变更

无新增接口，现有的创建/更新接口自动支持新字段（通过 schema 传入）。

## PDF 导出

电镀单和手工单的 PDF 导出增加"重量"列：
- 位于数量列之后
- 显示格式：`{weight} {weight_unit}`（如 "150 g"、"1.2 kg"）
- 缩短备注栏为重量列留出空间

## 前端

电镀单详情页和手工单详情页的发出/收回表格：
- 在数量列之后增加"重量"列
- 重量值：数字输入框
- 重量单位：下拉选择 g / kg
- 收回单创建/详情页同步增加重量列
