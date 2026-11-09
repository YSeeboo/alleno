# 通用底部悬浮操作条

## 范围与复用方式

延续手工单详情的悬浮条，统一单据详情的查看、导出及主操作样式。
原型已确认，现已落地电镀详情；手工单详情同步接入通用按钮，不改变原有事件与状态权限。

- 原型共用样式：`docs/superpowers/mockups/floating-action-bar.css`，新原型直接引用，避免每页复制配色。
- 正式容器为 `frontend/src/components/FloatingActionBar.vue`；语义按钮为 `frontend/src/components/FloatingActionButton.vue`，通过 `variant="secondary | excel | pdf | primary"` 复用配色、焦点及加载反馈。
- 状态权限、导出逻辑、加载状态和事件由业务页面决定；容器不判断单据状态、不发请求。
- 正式容器已支持窄屏换行，并通过 `ResizeObserver` 根据操作条实际高度预留空间。原有非导出页面仍可直接传入 `n-button`，兼容既有插槽用法。

## 容器

| 项目 | 规则 |
| --- | --- |
| 位置 | 主内容区底部居中，`position: sticky; bottom: 0`，不按整个浏览器宽度居中 |
| 外层 | 上下留白 14px，底部叠加 `safe-area-inset-bottom`；层级 20，低于弹窗 |
| 背景 | `#1A1D21`，不加全宽底板或分隔线 |
| 圆角 / 内边距 / 间距 | 14px / 8px 10px / 8px |
| 阴影 | `0 14px 34px rgba(16,20,26,.30)` |
| 点击区域 | 外层穿透，只有深色操作条接收点击，不遮挡两侧内容 |
| 内容占位 | 正式组件按操作条实际高度测量；静态原型桌面预留 64px、四按钮双行移动布局预留 120px，增加行数时同步调整 |

业务提示、归档说明和未收数量放在内容区，不塞入操作条。

## 按钮语义与反馈

统一基础类 `fab-action`；颜色绑定按钮语义，不通过按钮文字或页名匹配。

| 类型 | 变体类 | 默认 | 悬停 / 键盘聚焦 / 按下 |
| --- | --- | --- | --- |
| 查看等次要操作 | 无 | 透明底、`#C0C6CD` 文字 | 淡白底 `#FFFFFF0D`、白字 |
| Excel 导出 | `fab-action--excel` | 同次要操作 | **绿色底 `#1E7A5A`、白字和白色图标** |
| PDF 导出 | `fab-action--pdf` | 同次要操作 | **红色底 `#E5484D`、白字和白色图标** |
| 当前主操作 | `fab-action--primary` | 绿色底 `#1E7A5A`、白字 | 绿色底 `#248D69`、白字 |

- Excel 绿、PDF 红与手工单现有悬停配色保持一致。PDF 红色表达文件类型，不代表危险操作。
- 导出是即时动作，不是可选中标签：鼠标移开后恢复默认，不保留“已选择”背景。
- 键盘 `:focus-visible` 使用同色背景，并额外显示白色焦点环；鼠标点击后不因普通 `:focus` 永久着色。
- 图标跟随文字颜色；仅切换颜色，不改变尺寸或导致按钮位移。
- 动效为颜色过渡 150ms；尊重 `prefers-reduced-motion`。
- 禁用与加载时降低透明度，不触发悬停/按下配色。正式加载按钮应显示进度、保留文案并阻止重复提交；原型的 `aria-busy` 仅演示视觉，业务必须使用原生 `disabled` 或组件等效机制阻止点击。
- 不为导出按钮设置 `aria-pressed`，因为它不是开关。

## 排序与响应式

- 默认顺序：查看相关单据 → 导出 Excel → 导出 PDF → 主操作。
- 主操作最多一个，放在末尾；行级修改、删除等保留在明细区。
- 桌面内容自适应宽度，按钮至少高 40px。
- ≤480px 时换成两列，间距 4px，触控高度至少 44px，顺序和文字不变；隐藏的按钮不占位置。
- 禁止横向挤出页面；更多按钮时要检查窄屏换行及占位，不能仅沿用四按钮高度。
- 状态变化只增减业务入口，不改变 Excel / PDF 的语义和交互颜色；归档页不显示写操作。

## 原型接入示例

```html
<link rel="stylesheet" href="./floating-action-bar.css">
<!-- 页面内容及业务提示 -->
<div class="fab-spacer" aria-hidden="true"></div>
<footer class="fab-bar" aria-label="单据操作">
  <div class="fab-pill">
    <button class="fab-action">查看回收单</button>
    <button class="fab-action fab-action--excel">导出Excel</button>
    <button class="fab-action fab-action--pdf">导出PDF</button>
    <button class="fab-action fab-action--primary">关联回收单</button>
  </div>
</footer>
```

## 正式页面接入示例

```vue
<floating-action-bar aria-label="单据操作">
  <floating-action-button @click="viewReceipts">查看回收单</floating-action-button>
  <floating-action-button variant="excel" :loading="downloadingExcel" @click="exportExcel">导出Excel</floating-action-button>
  <floating-action-button variant="pdf" :loading="downloadingPdf" @click="exportPdf">导出PDF</floating-action-button>
  <floating-action-button v-if="canLink" variant="primary" @click="linkReceipt">关联回收单</floating-action-button>
</floating-action-bar>
```

导入两个组件即可；事件透传给 Naive UI 按钮，加载中使用原生禁用状态阻止重复点击。容器没有业务状态判断。

## 验收要点

1. 默认状态导出按钮为中性灰，不常驻绿底或红底。
2. 实际鼠标悬停 Excel 为绿色，PDF 为红色；移出恢复。
3. Tab 聚焦有相同语义色和可见焦点环，Enter / Space 保留原生按钮行为。
4. 禁用、加载不会误触发导出或出现可操作反馈。
5. 待发出、进行中、完成、归档下的按钮权限不变。
6. 桌面与窄屏滚动时悬浮条可见，无页面横向溢出，滚到底后最后一条内容可完整查看。
