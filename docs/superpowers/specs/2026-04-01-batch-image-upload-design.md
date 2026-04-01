# 导入配件后批量补图 设计文档

## 背景

当前导入配件后需要逐个打开编辑弹窗上传图片，操作繁琐。优化为：导入完成后直接弹出补图界面，平铺显示无图片的配件，支持点击后粘贴截图上传。

## 功能设计

### 触发流程

1. 用户点击"导入配件"→ 选择 Excel → 导入成功
2. 导入成功后弹出提示："是否为没有图片的配件上传图片？"
3. 选择"是"→ 弹出批量补图弹窗
4. 选择"否"→ 关闭，回到配件列表

### 批量补图弹窗

**数据来源：** 导入接口返回的 `results` 数组中筛选出没有图片的配件（`part.image` 为空）。

**显示列：**

| 列 | 说明 |
|----|------|
| 配件编号 | part_id |
| 配件名称 | name |
| 图片 | 点击上传区域 |

**图片上传区域交互：**
- 默认显示为虚线框 + "点击粘贴" 提示
- 点击该区域 → 区域获得焦点（高亮边框）
- 用户 Ctrl+V 粘贴截图 → 自动压缩 → 上传 OSS → 显示缩略图
- 上传成功后缩略图右上角显示 × 删除按钮，点击清除图片
- 上传过程中显示 loading 状态
- 每行独立上传，互不影响

**上传逻辑：** 复用现有 `uploadImageToOss({ kind: "part", file, entityId: part_id })`，上传成功后调用 `PATCH /parts/{part_id}` 更新 image 字段。

**弹窗底部：** 只有一个【完成】按钮，点击关闭弹窗并刷新配件列表。

### 后端变更

无。现有接口已满足：
- `import_parts_excel` 返回 `results` 含每个配件的 `part_id`
- `uploadImageToOss` + `PATCH /parts/{part_id}` 可更新图片
- 前端根据 `results` 中的 `part_id` 查询配件是否有图片即可（可在导入响应中增加 `image` 字段，或导入后批量查询）

### 导入响应优化

在 `import_parts_excel` 返回的 `results` 每项中增加 `image` 字段（当前已有 `part_id` 和 `name`），这样前端无需额外请求即可判断哪些配件需要补图。

修改 `services/part_import.py` 中 results.append 部分：
```python
results.append({
    "row_number": plan["row"].row_number,
    "part_id": part.id,
    "name": part.name,
    "image": part.image,  # 新增
    "action": action,
    "stock_added": qty,
})
```
