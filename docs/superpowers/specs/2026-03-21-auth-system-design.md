# Auth System Design (登录与用户管理)

## 目标

为 Allen Shop 增加登录认证和用户管理功能，提升数据安全性。

## 核心决策

- **认证方式**：JWT Token，有效期 30 天
- **权限模型**：模块级权限，按功能页面划分
- **权限与聚合页**：看板等聚合页面按自身权限独立控制，不受其他模块权限过滤（方案 A）
- **admin 用户**：默认拥有全部权限，应用启动时自动创建（如不存在）
- **用户删除**：软删除（is_active = false），被删除用户无法登录
- **密码存储**：bcrypt 哈希，永不存明文
- **只提供登录，不提供注册**：用户在后台"用户管理"页面中创建

---

## 数据模型

### User 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | 自增主键 | |
| username | String | 唯一, 非空 | 账号 |
| password_hash | String | 非空 | bcrypt 哈希后的密码 |
| owner | String | 非空 | 持有者（账号属于谁） |
| permissions | JSON | 默认 [] | 权限列表，如 `["parts", "orders"]` |
| is_admin | Boolean | 默认 false | 为 true 时忽略 permissions，拥有全部权限 |
| is_active | Boolean | 默认 true | 为 false 时无法登录（软删除） |
| created_at | DateTime | 非空 | 创建时间 |

### 初始化

应用启动时（lifespan 中），如果 `admin` 用户不存在，自动创建：
- username: `admin`
- password: `bronforwin12`（bcrypt 哈希存储）
- is_admin: true
- owner: `管理员`

---

## 权限定义

| 权限 key | 对应模块 | 控制的路由前缀 |
|----------|----------|---------------|
| `kanban` | 进度看板 | /kanban |
| `dashboard` | 数据看板 | /dashboard |
| `parts` | 配件管理 | /parts |
| `jewelries` | 饰品管理 | /jewelries |
| `orders` | 订单管理 | /orders |
| `purchase_orders` | 配件采购 | /purchase-orders |
| `plating` | 电镀单 | /plating |
| `handcraft` | 手工单 | /handcraft |
| `inventory` | 库存总表 | /inventory |
| `inventory_log` | 库存流水 | /inventory-log |
| `users` | 用户管理 | /users |

- admin 用户自动拥有全部权限，不受 permissions 字段限制
- 普通用户只能访问 permissions 中列出的模块

---

## 后端 API

### 认证接口

| 接口 | 方法 | 说明 | 权限要求 |
|------|------|------|---------|
| `/api/auth/login` | POST | 登录，返回 JWT token | 无需登录 |
| `/api/auth/me` | GET | 获取当前用户信息 | 需登录 |

**POST /api/auth/login**
- 请求：`{ "username": "admin", "password": "xxx" }`
- 成功：`{ "token": "xxx", "user": { ... } }`
- 失败：HTTP 401 `{ "detail": "账号/密码错误" }`

**GET /api/auth/me**
- 返回当前登录用户的信息（id、username、owner、permissions、is_admin）

### 用户管理接口

| 接口 | 方法 | 说明 | 权限要求 |
|------|------|------|---------|
| `/api/users` | GET | 用户列表 | `users` |
| `/api/users` | POST | 创建用户 | `users` |
| `/api/users/{id}` | PUT | 修改用户 | `users` |
| `/api/users/{id}` | DELETE | 删除用户（软删除） | `users` |

**业务规则**：
- admin 用户不可删除、不可修改权限和 is_admin 状态
- 创建用户时 username 不可重复
- 修改用户时密码字段选填，留空表示不修改

### 依赖注入

- `get_current_user(token)` — 解析 JWT，查询用户，未登录或 token 失效返回 401
- `require_permission(perm_key)` — 工厂函数，返回依赖，检查当前用户是否有对应权限，admin 跳过检查，无权限返回 403

### 权限与 API 路由映射

每个现有 API 路由添加 `Depends(require_permission("xxx"))` 依赖：

| API 前缀 | 需要的权限 |
|----------|-----------|
| `/api/parts` | `parts` |
| `/api/jewelries` | `jewelries` |
| `/api/orders` | `orders` |
| `/api/purchase-orders` | `purchase_orders` |
| `/api/plating` | `plating` |
| `/api/handcraft` | `handcraft` |
| `/api/inventory` | `inventory` |
| `/api/inventory/log` | `inventory_log` |
| `/api/kanban` | `kanban` |
| `/api/users` | `users` |

---

## 前端

### 登录页 (`/login`)

- 独立全屏页面，不使用 DefaultLayout
- 账号输入框 + 密码输入框 + 登录按钮
- 登录失败：提示 "账号/密码错误"
- 登录成功：token 存入 localStorage，跳转到用户第一个有权限的页面
- 已登录状态访问 /login 自动跳转

### 路由守卫

- 全局前置守卫 `router.beforeEach`
- 未登录 → 重定向到 /login（/login 本身除外）
- 已登录但无当前页面权限 → 重定向到第一个有权限的页面
- 使用 `/api/auth/me` 验证 token 有效性（首次加载时）

### Axios 拦截器

- 请求拦截器：自动在 Header 添加 `Authorization: Bearer <token>`
- 响应拦截器：收到 401 时清除 token，跳转到 /login

### Pinia Store (`useAuthStore`)

- state：`user`（当前用户信息）、`token`
- actions：`login()`、`logout()`、`fetchUser()`
- getters：`hasPermission(key)`、`isLoggedIn`

### 导航栏改造 (DefaultLayout.vue)

- 菜单项根据用户权限过滤，无权限的菜单隐藏
- 底部新增"管理"分组，包含"用户管理"（需 `users` 权限）
- Header 右上角显示当前用户名 + 退出登录按钮

### 用户管理页 (`/users`)

- 标题 "用户管理" + 【新建用户】按钮
- 表格列：账号名、持有者、权限（NTag 标签展示）、操作（修改/删除）
- admin 行：不显示删除按钮，修改时权限不可编辑

### 新建/修改用户弹窗

- 账号：必填，新建时可编辑，修改时只读
- 密码：新建时必填，修改时选填（留空不修改）
- 持有者：必填
- 权限：NCheckboxGroup 勾选，admin 用户不显示此项
- 确定 / 取消

---

## 新增依赖

### 后端
- `PyJWT` — JWT 生成与验证
- `bcrypt` — 密码哈希

### 前端
- 无新增依赖（Pinia 已安装未使用，Naive UI 组件库已包含所有需要的 UI 组件）

---

## 新增/修改文件清单

### 后端（新增）
- `models/user.py` — User 模型
- `schemas/user.py` — 请求/响应 schema
- `services/user.py` — 用户 CRUD + 密码哈希
- `services/auth.py` — JWT 生成/验证、登录逻辑
- `api/auth.py` — 登录、获取当前用户
- `api/users.py` — 用户管理 CRUD
- `api/deps.py` — `get_current_user`、`require_permission` 依赖

### 后端（修改）
- `models/__init__.py` — 注册 User 模型
- `main.py` — 注册 auth、users 路由；lifespan 中初始化 admin 用户
- `config.py` — 新增 `JWT_SECRET_KEY` 配置项
- `api/parts.py` 等现有路由 — 添加权限依赖

### 前端（新增）
- `frontend/src/views/login/LoginPage.vue` — 登录页
- `frontend/src/views/users/UserList.vue` — 用户管理页
- `frontend/src/stores/auth.js` — Pinia auth store
- `frontend/src/api/auth.js` — 登录/用户信息 API
- `frontend/src/api/users.js` — 用户管理 API

### 前端（修改）
- `frontend/src/router/index.js` — 添加 /login、/users 路由 + 路由守卫
- `frontend/src/api/index.js` — 添加 token 请求拦截器 + 401 响应处理
- `frontend/src/layouts/DefaultLayout.vue` — 菜单权限过滤 + 用户管理入口 + 退出登录
