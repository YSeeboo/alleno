# 订单附加信息 设计文档

## 背景

订单需要记录条码要求、唛头要求和总备注，供内部生产参考。

## 数据模型

Order 表新增 5 个字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| barcode_text | Text, nullable | 条码要求文字 |
| barcode_image | String, nullable | 条码要求图片 URL |
| mark_text | Text, nullable | 唛头要求文字 |
| mark_image | String, nullable | 唛头要求图片 URL |
| note | Text, nullable | 总备注 |

## API

### 修改接口

**PATCH `/orders/{order_id}/extra-info`** — 更新附加信息（随时可编辑，不限状态）

```
Request: {
  barcode_text?: str,
  barcode_image?: str | null,
  mark_text?: str,
  mark_image?: str | null,
  note?: str
}
Response: OrderResponse (含新字段)
```

**GET `/orders/{order_id}`** — 响应中包含新字段

## 前端

### 位置

订单详情页，基本信息卡片和包装费卡片之间，新增"附加信息"卡片。

### 布局

三个区块纵向排列：

**条码要求**
- 左侧：文字输入框（多行 textarea）
- 右侧：图片上传区域（点击上传/粘贴，复用 ImageUploadModal）
- 已有图片时显示缩略图 + 删除按钮

**唛头要求**
- 同条码要求布局

**总备注**
- 全宽 textarea

底部【保存】按钮，一次保存所有附加信息。

### 编辑权限

随时可编辑，不限订单状态。
