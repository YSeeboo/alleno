# 货物分拣页 设计文档

**日期**：2026-05-17
**作者**：ycb（设计）+ Claude（记录）
**状态**：待实现

## 背景

手工单（HandcraftOrder）模型已经有 `receipt_code` 字段，且回执 PDF 已经渲染了"客户分拣"表。分拣车间需要一个**移动端为主**的页面，让分拣员通过回执编号或商家快速查看某个手工单下的"每个饰品分别要发给哪些客户、各多少件"。

本期 v1 **纯只读**，不做"标记已分拣"之类的进度追踪。

## 用户与权限

- 使用者：**分拣员**（车间角色），主要在手机上使用
- 新增权限位 `sorting`，独立于 `handcraft`
  - 分拣员账号通常只勾 `sorting`，看不到"手工发出/手工回收"等管理页面
  - 给已有 `handcraft` 权限的管理员**不自动赋予** `sorting` —— 在用户管理界面手动勾选

## 范围 / 数据规则

### 何时出现在分拣页

一个手工单在该页面出现的充要条件：**至少存在一行 `HandcraftJewelryItem`，其客户名能解析为非空字符串**。

客户名解析规则（沿用现有 `get_handcraft_jewelry_breakdown`）：
1. 行的 `customer_name` 非空非空白字符串 —— 手填客户名
2. 否则若该行有 `OrderItemLink` 关联到某 `Order`，且 `Order.customer_name` 非空非空白 —— 取之
3. 否则 = 不可解析，该行不计入分拣信息

判定基于**最终解析值**，不是某个字段单独看。

**订单状态不限**：pending / processing / completed 都可能出现（用户决策）。

### 行级过滤

页面上只渲染**客户名可解析**的行；同一订单内"无客户行"对用户隐身。

### 分组

按饰品分组（与现有 `get_handcraft_jewelry_breakdown` 返回形状一致）。每个饰品组：
- 饰品图、饰品编号、饰品名
- 该组内**每客户一行**「客户名 × 数量」（不在客户上做合并去重）

## UI 设计

### 路由 / 导航

- 路由路径：`/cargo-sorting`
- 路由 `meta.perm: 'sorting'`
- 注册到 `ROUTE_PERMISSION_MAP` 和 `PERMISSION_ROUTE_ORDER`
- 侧边栏位置：「手工单」分组的**第 3 个子菜单**（手工发出、手工回收之后）
- 图标：`assets/icons/分拣.svg` → 封装为 `components/icons/SortingIcon.vue`
- 菜单标签：「货物分拣」

### 页面骨架（手机优先，375px 设计基准）

自上而下：

1. **粘性头部（sticky top）**
   - 第 1 行：搜索输入框 + 「搜索」按钮
   - 第 2 行：商家筛选触发按钮
2. **结果区**：纵向滚动卡片流

### 顶部交互

| 元素 | 行为 |
|---|---|
| 搜索框 | placeholder「输入回执编号」；回车 = 点搜索；输入前 `trim()` + `toUpperCase()` |
| 搜索按钮 | 调 `GET /handcraft/by-receipt-code/{code}`；命中渲染单卡；404 → toast「无此回执编号：XXXX」；**结果区保留上次状态**（避免错字清空） |
| 商家按钮 | 未选时显示「按商家筛选 ▾」；已选时显示「商家：张师傅 ▾」并加可清除「×」 |
| 商家底部抽屉 | 唤起时调 `GET /handcraft/suppliers-with-sorting`；选中即关闭并触发列表请求 |

**互斥规则**：点击「搜索」按钮（无论结果命中或 404）即清空商家选择；选中商家即清空搜索框。两种状态不可同时持有。

### 结果卡片

每个手工单一张卡：

- 卡顶：`回执编号`（大字粗体）+ 右侧状态徽章
- 副信息：`商家名 · N 个饰品`
- 饰品列表（每饰品组一行）：
  - 左：饰品图，**72×72**，圆角 8
  - 右上：饰品名（粗体）
  - 右中：饰品编号（小字灰）
  - 右下：客户列表，**每客户一行**「客户名 × 数量」

### 状态徽章

- `completed` → 绿色，文案「已完成」
- `pending` / `processing` → 灰色，文案分别「待发出」/「已发出」

### 图片放大

- 点饰品图 → 全屏遮罩 + 居中大图（最大 90vw × 90vh，等比缩放）
- 点图外区域或右上 × 关闭
- 用 Naive UI `<n-image-preview>`（沿用项目其它页面的现成 pattern）

### 缺省态

| 场景 | 显示 |
|---|---|
| 初始（无搜索、无商家） | 居中插画 + 文案「输入回执编号或选择商家查看分拣信息」 |
| 商家已选但无分拣订单 | 「该商家暂无含分拣信息的手工单」 |
| 搜索无结果 | toast 提示，结果区**保持上次状态** |

### 商家有多单的处理

- 全展开纵向排列，**每页最多 15 单**，按 `created_at desc`
- 超出显示「**加载更多**」显式按钮在结果区末尾（不做无限滚动，避免误触发）

### 移动端额外要求

- 头部 sticky
- 所有可触控区 ≥ 44px（搜索按钮、商家按钮、抽屉项、饰品图）
- 抽屉支持向下滑动关闭（Naive UI `n-drawer` 自带）
- v1 不做下拉刷新

## 后端实现

### 数据模型

**无新表、无新字段**。

### 服务层（`services/handcraft.py`）

新增：

```python
def _has_sorting_info(db: Session, hc_id: str) -> bool:
    """订单中至少有一行客户名可解析。"""

def list_suppliers_with_sorting(db: Session) -> list[str]:
    """所有至少有一个含分拣信息的手工单的商家名，去重。"""

def list_handcraft_orders_with_sorting(
    db: Session,
    supplier_name: str,
    limit: int = 15,
    offset: int = 0,
) -> list[dict]:
    """返回该商家的手工单列表，每单嵌入已过滤无客户行的 breakdown，
    按 created_at desc 排序。"""
```

修改：`get_handcraft_jewelry_breakdown` 增加可选参数 `only_with_customer: bool = False`，true 时跳过所有 customer 解析为 None 的 entry，并跳过没有任何 entry 的饰品组。现有调用方不传参 = 行为不变。

### API 层（`api/handcraft.py`）

新增两个端点（都使用 `Depends(require_perm("sorting"))`）：

```
GET /handcraft/sorting?supplier_name=张师傅&limit=15&offset=0
   → 422 if supplier_name missing or empty
   → { "orders": [...breakdowns...], "has_more": bool }
   has_more 用来驱动前端「加载更多」按钮：true 表示后端还有更多记录可拉
GET /handcraft/suppliers-with-sorting
   → { "suppliers": ["张师傅", "李工厂", ...] }
```

同时给 `GET /handcraft/by-receipt-code/{code}` **追加** `sorting` 权限（保持原有 `handcraft` 权限不变）—— 即两个权限任一可访问。这样分拣员能搜索，手工单管理员也能用。

`/handcraft/sorting` 和 `/handcraft/suppliers-with-sorting` **只接受** `sorting` 权限（不接受 `handcraft`）—— 管理员需要进货物分拣页时也得勾上 `sorting`。这保证「分拣页」是一个明确独立的权限边界。

### 权限注册

- 在权限枚举/默认权限列表里加 `sorting`
- 用户管理界面（前端 + 后端 schema）增加该权限的勾选项

### 边角处理

- `customer_name` 空串与 NULL 等价 —— SQL 与 Python 层都做 `IS NOT NULL AND TRIM != ''`
- 一行同时手填 + 关联订单 → 手填覆盖（沿用现有规则）
- 商家名严格相等匹配，不做全角/半角归一化（与项目其它页面一致）

## 前端实现

### 文件清单

新增：

- `frontend/src/components/icons/SortingIcon.vue`
- `frontend/src/views/cargo-sorting/CargoSorting.vue`（主页面）
- `frontend/src/views/cargo-sorting/SortingCard.vue`（单订单卡片）
- `frontend/src/views/cargo-sorting/SupplierSheet.vue`（商家底部抽屉）

修改：

- `frontend/src/router/index.js` —— 注册路由 + 权限映射
- `frontend/src/layouts/DefaultLayout.vue` —— 「手工单」分组下加菜单项
- API 客户端层（项目现有 axios 封装）—— 新增 3 个方法

### 组件职责

- `CargoSorting.vue`：管状态（searchCode / selectedSupplier / orders / loading / hasMore），管 3 个接口调用，渲染头部 + 缺省态 + 卡片列表 + 加载更多按钮
- `SortingCard.vue`：纯展示，props 取一个 order 的 breakdown 数据；内部用 `n-image-preview` 实现点击放大
- `SupplierSheet.vue`：`n-drawer placement="bottom"`，加载并展示商家列表，点击 emit 选中

## 测试

### 后端（`tests/test_api_handcraft.py` 追加）

- `list_handcraft_orders_with_sorting` happy path：混合"有分拣 / 无分拣"的数据，验证过滤
- `list_suppliers_with_sorting` 只返回有分拣订单的商家
- 商家不存在 / 商家无分拣单 → `{"orders": [], "has_more": false}`
- `limit + offset` 分页正确：恰好 15 单 → `has_more=false`；16 单第一页 → `has_more=true`
- `supplier_name` 缺失或空 → 422
- `customer_name` 空串和 NULL 视为同义
- 无 `sorting` 权限 → 403；有 `handcraft` 没 `sorting` → 也不能访问列表接口
- `by-receipt-code` 接口：`sorting` 权限可访问，`handcraft` 权限同样可访问

### 前端

无单测（项目现状）。手测清单：
- 三个缺省态全部覆盖
- 搜索 / 商家筛选互斥
- 搜索无结果时结果区不被清空
- 加载更多按钮在 ≤15 单时不出现、>15 单时出现且分页正确
- 图片放大遮罩点击外部关闭
- 真机移动端验证触控区、sticky 头部、抽屉滑动

## 实现顺序（供写计划阶段参考）

1. 后端 service 函数 + 单测
2. 后端 API 路由 + 权限装饰器 + 单测
3. 权限位前后端注册 + 用户管理 UI 接入
4. 前端 router / sidebar / icon 接入（空页面跑通权限）
5. 前端组件实现（main → card → sheet）
6. 联调 + 移动端真机测试

## 非目标 / 显式 out of scope

- 不做"已分拣"勾选 / 进度记录（v1 纯只读）
- 不做下拉刷新、无限滚动
- 不做模糊搜索、不做多字段（如客户名、饰品名）搜索
- 不做商家名归一化
- 不做导出 / 打印（已有 PDF 路径）
