# 饰品大图 设计文档

## 背景

订单需要生成饰品大图 PDF 供内部生产参考，每个饰品以大图+关键信息的方式展示，方便工人识别。

## 功能设计

### 入口

订单详情页饰品清单区域，新增【生成饰品大图】按钮。

### 输出格式

- **PDF 下载**：点击按钮直接下载 PDF
- **网页预览**：点击按钮旁的预览入口，在新标签页中打开预览

### 布局

- 纸张：A4 纵向
- **自动排版**：根据图片原始宽高比自适应布局，使用 CSS Flexbox wrap
- 图片保持原始比例，不拉伸不裁剪，**不压缩图片质量**
- 每个饰品卡片内容（从上到下）：
  - 饰品图片（占卡片 ≥ 80% 高度）
  - 文字区域（≤ 卡片 20% 高度）：数量、单价（订单中的 unit_price）、客户货号（如有）、备注（如有）
- 自动分页
- 页面顶部显示：订单号 + 客户名

### 图片处理

- 图片使用原始 URL 引用（HTML 中 `<img src>`），不下载不压缩
- 无图片的饰品显示占位框 + "暂无图片"文字

### 技术方案

使用 HTML + CSS 生成布局，weasyprint 将 HTML 转为 PDF。HTML 预览和 PDF 共用同一套模板。

## API

### 新增接口

**GET `/orders/{order_id}/jewelry-poster-pdf`** — 下载饰品大图 PDF

```
Response: application/pdf (bytes)
```

**GET `/orders/{order_id}/jewelry-poster-preview`** — 网页预览（返回 HTML）

```
Response: text/html
```

## 后端实现

新建 `services/jewelry_poster.py`：

- 生成 HTML 字符串（CSS Flexbox 自适应布局）
- PDF：`weasyprint.HTML(string=html).write_pdf()`
- 预览：直接返回同一份 HTML
- 系统依赖：`pip install weasyprint`，服务器需安装 `libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0`（Ubuntu）或 `brew install pango`（macOS）

## 前端

### 订单详情页

在饰品清单卡片的 header-extra 区域，添加两个按钮：
- 【下载饰品大图】→ 调用 PDF 接口下载
- 【预览饰品大图】→ 新标签页打开预览 HTML
