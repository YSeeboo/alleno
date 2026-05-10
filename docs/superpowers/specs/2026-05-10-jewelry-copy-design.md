# 复制饰品功能 — 设计

## 背景

部分饰品没有沉淀到饰品模板（jewelry template），但偶尔需要复用其结构（基本信息 + BOM 配件清单）创建新饰品。当前用户只能"新增饰品"后再到详情页逐项添加 BOM，操作繁琐。

本设计在饰品列表页操作菜单新增"复制"项，一键预填表单 + 同步 BOM。

## 范围

- ✅ 列表页操作菜单（"⋮"）新增"复制"项
- ✅ 复制基本信息（name/image/structure_image/category/color/unit/retail_price/wholesale_price/handcraft_cost）
- ✅ 复制完整 BOM 清单（part_id, qty_per_unit）
- ✅ 弹窗预填表单，用户可改名称/颜色/价格等再保存
- ❌ 不复制库存（inventory_log），新饰品库存从 0 开始
- ❌ 不在详情页提供"复制"按钮（本期暂不做，后续按需扩展）
- ❌ 不复制订单/电镀/手工单等关联记录

## 用户流程

1. 用户在「饰品管理」列表中找到要复制的源饰品
2. 点击该行操作列的"⋮" → 菜单展开「复制 / 删除」
3. 点击"复制"
4. 弹出"复制饰品"模态框：
   - 顶部黄色提示 banner：`从 <源 ID> <源名称> 复制（含 BOM 配件清单）。类目沿用源饰品。`
   - 表单字段以源饰品数据预填
   - 名称字段预填为 `${源名称}-副本`
   - 类目字段禁用，旁注"复制时不可修改"
5. 用户可调整名称/颜色/价格/图片等
6. 点击"保存" → 后端原子创建新饰品 + 复制 BOM
7. 成功后关闭弹窗，跳转到新饰品详情页（沿用「从模板创建」体验）

## 后端

### Schema (`schemas/jewelry.py`)

新增 `JewelryCopyRequest`：

```python
class JewelryCopyRequest(BaseModel):
    name: str  # 必填
    image: Optional[str] = None
    structure_image: Optional[str] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    retail_price: Optional[float] = None
    wholesale_price: Optional[float] = None
    handcraft_cost: Optional[float] = None
    # 注意：不声明 category 字段；即使客户端传入也被 Pydantic 忽略，
    # service 层强制使用源饰品的 category。
```

风格遵循同文件 `JewelryUpdate`，不加 `Field(ge=0)` 校验（与现有 schema 保持一致）。

### Service (`services/jewelry.py`)

新增：

```python
def copy_jewelry(db: Session, source_id: str, override_data: dict) -> Jewelry:
    """从已有饰品复制创建新饰品（基本信息 + BOM）。

    - source_id 不存在 → ValueError
    - category 强制沿用源饰品（override_data 中的 category 被忽略）
    - 库存不复制（inventory_log 不动），新饰品库存从 0 开始
    - status 默认 'active'
    """
```

实现要点：
1. 查 `source = get_jewelry(db, source_id)`，None → `ValueError("Jewelry not found: ...")`
2. 构造 base_data：从 source 复制 name/image/structure_image/category/color/unit/retail_price/wholesale_price/handcraft_cost
3. 把 `override_data` merge 进 base_data，但 **`category` 一律使用 source.category**
4. 调 `create_jewelry(db, base_data)` 得到新饰品（自动按 category 前缀生成 ID）
5. 查源 BOM：`db.query(Bom).filter(Bom.jewelry_id == source_id).all()`
6. 对每条源 BOM，新建 Bom 记录：`Bom(jewelry_id=new.id, part_id=src.part_id, qty_per_unit=src.qty_per_unit)`，`db.add()`
7. `db.flush()`，返回新饰品

### API (`api/jewelries.py`)

新增端点：

```python
@router.post("/{source_id}/copy", response_model=JewelryResponse, status_code=201)
def api_copy_jewelry(source_id: str, payload: JewelryCopyRequest, db: Session = Depends(get_db)):
    with service_errors():
        new_jewelry = copy_jewelry(db, source_id, payload.model_dump(exclude_unset=True))
    return new_jewelry
```

返回 201 + 完整新饰品对象。

## 前端

### API (`frontend/src/api/jewelries.js`)

```js
export const copyJewelry = (sourceId, data) => api.post(`/jewelries/${sourceId}/copy`, data)
```

### `JewelryList.vue`

**状态新增**：

```js
const copySourceId = ref(null)
const copySourceName = ref('')
```

**操作下拉菜单**（columns 里的 actions render）：把 dropdown options 从 `[{ label: '删除', key: 'delete' }]` 改为 `[{ label: '复制', key: 'copy' }, { label: '删除', key: 'delete' }]`，并在 `onSelect` 中分支 `if (key === 'copy') openCopy(row)`。

**新增 `openCopy(row)`**：

```js
const openCopy = (row) => {
  editingId.value = null
  selectedTemplate.value = null
  copySourceId.value = row.id
  copySourceName.value = row.name
  Object.assign(form, {
    name: `${row.name}-副本`,
    image: row.image || '',
    category: row.category && VALID_CATEGORIES.includes(row.category) ? row.category : null,
    color: row.color || '',
    unit: row.unit || null,
    retail_price: row.retail_price ?? null,
    wholesale_price: row.wholesale_price ?? null,
  })
  showModal.value = true
}
```

**修改 `openCreate` / `openEdit`** — 进入时清空 `copySourceId.value = null`。

**Modal 标题**：`editingId ? '编辑饰品' : (copySourceId ? '复制饰品' : '新增饰品')`

**Modal 顶部新增 banner**（仅在 `copySourceId` 不为空时显示）：

```vue
<n-alert v-if="copySourceId" type="warning" style="margin-bottom: 12px;">
  从 <b>{{ copySourceId }} {{ copySourceName }}</b> 复制（含 BOM 配件清单）。类目沿用源饰品。
</n-alert>
```

**类目字段**：禁用条件改为 `:disabled="!!editingId || !!copySourceId"`，提示文案"复制时不可修改"。

**`save()` 三分支**：

```js
if (editingId.value) {
  // 现有更新逻辑
} else if (copySourceId.value) {
  const { category, ...copyData } = form  // 后端忽略 category，前端也不传
  const { data: newJewelry } = await copyJewelry(copySourceId.value, copyData)
  message.success('复制成功')
  copySourceId.value = null
  showModal.value = false
  router.push(`/jewelries/${newJewelry.id}`)
} else if (selectedTemplate.value) {
  // 现有模板创建逻辑
} else {
  // 现有新建逻辑
}
```

## 测试

### 后端 (`tests/test_api_jewelries.py`)

新增用例：

1. **基础复制**：创建源饰品 + 给它配 BOM；调 `POST /jewelries/{id}/copy` → 新饰品 ID 不同、category 相同、BOM 完整复制
2. **新饰品库存为 0**：源饰品有库存日志（手动塞一条 inventory_log），复制后新饰品 stock = 0
3. **源饰品不存在 → 404**
4. **name 缺失 → 422**
5. **override 字段生效**：传入新 name/color/retail_price，新饰品对应字段为新值
6. **category 不能通过 override 改变**：在 payload 里塞 `"category": "单件"`（Pydantic 默认忽略未声明字段）→ 200，新饰品 category 仍为源 category
7. **空 BOM 源饰品**：源饰品没有任何 BOM 行，复制成功，新饰品也无 BOM，不报错

### 前端

手动验证：
- 列表页操作菜单出现"复制"
- 点击后弹窗预填、banner 显示、类目禁用
- 修改名称/价格后保存成功 → 跳转新饰品详情页 → BOM 完整
- 取消后再"新增饰品"，表单为空、banner 不出现、类目可选
- 取消后再"编辑"另一行，表单为该行数据、banner 不出现、类目禁用且文案为"类目不可修改"

## 不在本期范围

- 详情页"复制"按钮（如有需求再扩展）
- 复制订单 / 电镀单 / 手工单
- 跨用户/角色权限差异（沿用现有 jewelry CRUD 权限）
- 批量复制（一次只能复制一项）
