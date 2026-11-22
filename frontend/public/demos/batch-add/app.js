import { SCENES, PLANS, KIND_LABELS, COLORS, PRODUCTS, sceneProducts, unavailable, makeRow, rowErrors, lineAmount, money, quantitySummary, productImage } from './domain.js'

const $ = selector => document.querySelector(selector)
const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char])
const productById = new Map(PRODUCTS.map(product => [product.id, product]))
const images = new Map(PRODUCTS.map(product => [product.id, productImage(product)]))
const params = new URLSearchParams(location.search)
const state = {
  plan: PLANS.some(plan => plan.id === params.get('plan')) ? params.get('plan') : 'A',
  scene: SCENES.some(scene => scene.id === params.get('scene')) ? params.get('scene') : 'order',
  kind: 'all', query: '', selectedOnly: false, rows: [], step: 1, review: false, attempted: false, serial: 0,
  batchColor: 'G', expandedColors: new Set(),
}
const scene = () => SCENES.find(item => item.id === state.scene)
const product = row => productById.get(row.productId)
const hasWeight = () => ['plating', 'output', 'material'].includes(state.scene)
const hasPrice = () => scene().fields.includes('price')
const img = (item, className = 'thumb') => `<img class="${className}" src="${images.get(item.id)}" alt="" width="42" height="42">`
const rowTotal = row => hasPrice() ? `¥${money(lineAmount(row))}` : `${escape(row.qty || '—')} ${escape(row.unit)}`
const isSelected = id => state.rows.some(row => row.productId === id)
const filtered = () => sceneProducts(scene()).filter(item => (state.kind === 'all' || item.kind === state.kind) && (!state.selectedOnly || isSelected(item.id)) && `${item.id} ${item.name}`.toLowerCase().includes(state.query.trim().toLowerCase()))
let toastTimer

function notify(text) {
  clearTimeout(toastTimer)
  $('#toast').textContent = text
  $('#toast').classList.add('visible')
  toastTimer = setTimeout(() => $('#toast').classList.remove('visible'), 2800)
}
function syncUrl() {
  const url = new URL(location.href)
  url.searchParams.set('plan', state.plan)
  url.searchParams.set('scene', state.scene)
  history.replaceState(null, '', url)
}
function seedRows() {
  state.rows = sceneProducts(scene()).filter(item => !unavailable(item, scene())).slice(0, 2).map(item => makeRow(item, scene(), `row-${++state.serial}`))
}
function renderPlans() {
  $('#plans').innerHTML = PLANS.map(plan => `<button class="plan ${state.plan === plan.id ? 'active' : ''}" data-plan="${plan.id}" aria-pressed="${state.plan === plan.id}"><span class="plan-letter">${plan.id}</span><span class="plan-copy"><span class="plan-title">${plan.name}${plan.id === 'A' ? '<span class="recommended">推荐</span>' : ''}</span><span class="plan-desc">${plan.short}</span></span><span class="plan-radio" aria-hidden="true"></span></button>`).join('')
  $('#scenes').innerHTML = SCENES.map(item => `<button class="scene-button ${state.scene === item.id ? 'active' : ''}" data-scene="${item.id}" aria-pressed="${state.scene === item.id}">${item.label}${item.id === 'purchase' ? '<span class="new-dot" title="盘点补充入口"></span>' : ''}</button>`).join('')
  const plan = PLANS.find(item => item.id === state.plan)
  $('#design-note').innerHTML = `<span class="note-dot"></span><span><strong>${plan.fit}</strong> · ${plan.description}</span>`
}
function renderContext() {
  const current = scene()
  $('#context-path').textContent = current.context
  $('#dialog-eyebrow').textContent = current.eyebrow
  $('#picker-title').textContent = current.title
  $('#scene-description').textContent = current.description
}
function catalogHeader() {
  return `<div class="catalog-top"><div class="search-row"><div class="search-box"><span aria-hidden="true">⌕</span><input id="catalog-search" type="search" placeholder="搜索名称 / 编号，例如：珍珠、P-2002" aria-label="搜索商品名称或编号" value="${escape(state.query)}"><button class="search-clear" data-action="clear-search" aria-label="清空搜索" ${state.query ? '' : 'hidden'}>×</button></div><button class="button small ${state.selectedOnly ? 'soft' : ''}" data-action="selected-only" aria-pressed="${state.selectedOnly}">只看已选</button></div><div class="kind-tabs" aria-label="商品类型筛选"><button class="kind-tab ${state.kind === 'all' ? 'active' : ''}" data-kind="all" aria-pressed="${state.kind === 'all'}">全部 <small>${sceneProducts(scene()).length}</small></button>${scene().kinds.map(kind => `<button class="kind-tab ${state.kind === kind ? 'active' : ''}" data-kind="${kind}" aria-pressed="${state.kind === kind}">${KIND_LABELS[kind]}</button>`).join('')}</div></div><div id="catalog-meta"></div>`
}
function renderCatalogMeta() {
  const visible = filtered(), eligible = visible.filter(item => !unavailable(item, scene())), selectedVisible = eligible.filter(item => isSelected(item.id))
  const hiddenCount = state.rows.filter(row => !visible.some(item => item.id === row.productId)).length
  $('#catalog-meta').innerHTML = `<div class="catalog-meta"><label class="select-all"><input type="checkbox" id="select-visible" aria-label="全选当前筛选结果" ${eligible.length && selectedVisible.length === eligible.length ? 'checked' : ''} ${eligible.length ? '' : 'disabled'}>全选当前筛选结果</label><span>共 ${visible.length} 项${hiddenCount ? ` · <span class="hidden-count">另有 ${hiddenCount} 行已选</span>` : ' · 跨筛选保留已选'}</span></div>`
  $('#select-visible').indeterminate = selectedVisible.length > 0 && selectedVisible.length < eligible.length
}
function catalogRow(item) {
  const disabled = unavailable(item, scene()), selected = isSelected(item.id)
  return `<div class="catalog-row ${selected ? 'chosen' : ''} ${disabled ? 'disabled' : ''}"><input type="checkbox" data-product="${item.id}" aria-label="选择 ${item.name} ${item.id}" ${selected ? 'checked' : ''} ${disabled ? 'disabled' : ''}>${img(item)}<div class="product-info"><strong>${item.name}${disabled ? '<span class="tag">已在 BOM</span>' : ''}</strong><small>${item.id} · ${KIND_LABELS[item.kind]} · ${item.unit}${state.scene === 'output' ? ` · BOM ${item.bomCount} 种材料` : ''}</small></div><div class="product-tail">${hasPrice() ? `¥${item.price}` : `${item.stock.toLocaleString('zh-CN')} ${item.unit}`}<small>${hasPrice() ? '资料单价 / 可逐行修改' : '示例库存 / 不作为选品限制'}</small></div></div>`
}
function productCard(item) {
  const disabled = unavailable(item, scene()), selected = isSelected(item.id)
  return `<label class="product-card ${selected ? 'chosen' : ''}"><input type="checkbox" data-product="${item.id}" aria-label="选择 ${item.name} ${item.id}" ${selected ? 'checked' : ''} ${disabled ? 'disabled' : ''}><span class="card-image">${img(item, '')}</span><strong>${item.name}</strong><small>${item.id} · ${item.unit}${disabled ? ' · 已在 BOM' : ''}</small><span class="card-price">${hasPrice() ? `¥${item.price}` : `${item.stock.toLocaleString('zh-CN')} ${item.unit}`}<span>${hasPrice() ? '参考单价' : '示例库存'}</span></span></label>`
}
function renderCatalogItems() {
  const items = filtered(), target = $('#catalog-items')
  if (!target) return
  target.innerHTML = items.length ? items.map(state.plan === 'B' && !state.review ? productCard : catalogRow).join('') : '<div class="empty"><span>⌕</span>没有匹配的商品<small>试试其他名称或编号；筛选不会清除已选商品。</small></div>'
  renderCatalogMeta()
}
function fieldLabel(field) {
  return ({ qty: state.scene === 'bom' ? '每 1 条用量' : state.scene === 'order' ? '订购数量' : state.scene === 'plating' ? '发出数量' : state.scene === 'output' ? '产出数量' : '数量', unit: '单位', price: '单价（元）', color: '电镀颜色' })[field]
}
function colorPicker(row = null) {
  const scope = row?.key || 'batch', selected = row?.color || state.batchColor
  const expanded = state.expandedColors.has(scope)
  const label = row ? `${product(row).name} 电镀颜色` : '统一电镀颜色'
  const selectedExtra = COLORS.find(color => !color.common && color.value === selected)
  const chip = color => `<button type="button" class="color-chip color-${color.value} ${selected === color.value ? 'is-selected' : ''}" data-color-scope="${scope}" data-color="${color.value}" aria-label="${escape(label)} ${color.label}" aria-pressed="${selected === color.value}" title="${color.value} · ${color.label}">${color.value}</button>`
  return `<div class="color-picker" id="color-picker-${scope}" role="group" aria-label="${escape(label)}">${COLORS.filter(color => color.common).map(chip).join('')}<button type="button" class="color-more ${selectedExtra ? `color-${selectedExtra.value} is-selected` : ''}" data-color-more="${scope}" aria-label="${escape(label)} 更多颜色${selectedExtra ? `，当前${selectedExtra.label}` : ''}" aria-expanded="${expanded}" aria-controls="extra-colors-${scope}">${selectedExtra?.value || '更多'} ${expanded ? '▴' : '▾'}</button><div class="color-extra" id="extra-colors-${scope}" ${expanded ? '' : 'hidden'}>${COLORS.filter(color => !color.common).map(color => `<span>${chip(color)}<small>${color.label}</small></span>`).join('')}</div></div>`
}
function updateColorPicker(scope) {
  const row = scope === 'batch' ? null : state.rows.find(item => item.key === scope)
  const element = document.getElementById(`color-picker-${scope}`)
  if (element && (scope === 'batch' || row)) element.outerHTML = colorPicker(row)
}
function fieldInput(row, field) {
  const item = product(row), id = `field-${row.key}-${field}`, label = escape(`${item.name} ${fieldLabel(field)}`)
  const shared = `id="${id}" data-row="${row.key}" data-field="${field}" aria-label="${label}"`
  if (field === 'color') return colorPicker(row)
  if (field === 'unit') {
    if (['order', 'bom'].includes(state.scene)) return `<input ${shared} value="${escape(row.unit)}" readonly title="沿用商品资料单位">`
    const options = [...new Set([item.unit, '个', '对', '条', '套', '颗', '米', '包', '片', 'g', 'kg'])]
    return `<select ${shared}>${options.map(unit => `<option ${row.unit === unit ? 'selected' : ''}>${unit}</option>`).join('')}</select>`
  }
  return `<input ${shared} type="number" inputmode="decimal" min="${field === 'price' ? '0' : state.scene === 'bom' ? '0.0001' : '1'}" step="${field === 'price' ? '0.0000001' : state.scene === 'bom' ? '0.0001' : '1'}" value="${escape(row[field])}">`
}
function variantHint(row) {
  if (state.scene !== 'plating') return ''
  const exists = product(row).colors.includes(row.color)
  return `<div class="variant-label ${exists ? '' : 'warning'}" data-variant="${row.key}">${exists ? '✓ 对应配件' : '⚠ 尚无对应配件'}：${escape(product(row).name)} · ${escape(row.color)}</div>`
}
function detailsButton(row) {
  if (state.scene === 'bom') return ''
  const count = Number(Boolean(row.note)) + Number(row.weight !== '')
  return `<button class="text-button" data-details="${row.key}">${hasWeight() ? '重量 / 备注' : '备注'}${count ? ` · 已填 ${count} 项` : ' ↗'}</button>`
}
function errorsHtml(row) {
  const errors = rowErrors(row, scene())
  return state.attempted && errors.length ? `<div class="row-error">${errors.map(escape).join('；')}</div>` : ''
}
function updateRowFeedback(row) {
  const element = document.querySelector(`.picker [data-line="${row.key}"]`)
  if (!element) return
  const target = element.tagName === 'TR' ? element.querySelector('td') : element
  target.querySelector('.row-error')?.remove()
  target.insertAdjacentHTML('beforeend', errorsHtml(row))
  element.classList.toggle('invalid', state.attempted && rowErrors(row, scene()).length > 0)
  const variant = element.querySelector('[data-variant]')
  if (variant) variant.outerHTML = variantHint(row)
}
function selectedRow(row) {
  const item = product(row), errors = rowErrors(row, scene())
  return `<article class="selected-row ${state.attempted && errors.length ? 'invalid' : ''}" data-line="${row.key}"><div class="selected-title">${img(item)}<div class="product-info"><strong>${item.name}</strong><small>${item.id} · ${KIND_LABELS[item.kind]}</small></div>${state.scene === 'order' ? `<button class="text-button" data-duplicate="${row.key}">再加一行</button>` : ''}<button class="icon-button" data-remove="${row.key}" aria-label="移除 ${item.name}">×</button></div><div class="selected-fields fields-${scene().fields.length}${state.scene === 'plating' ? ' plating-fields' : ''}">${scene().fields.map(field => field === 'color' ? `<div class="color-field"><span>${fieldLabel(field)}</span>${fieldInput(row, field)}</div>` : `<label for="field-${row.key}-${field}">${fieldLabel(field)}${fieldInput(row, field)}</label>`).join('')}</div>${variantHint(row)}<div class="row-bottom"><span data-amount="${row.key}">${state.scene === 'output' ? `BOM ${item.bomCount} 种关联材料 · 演示` : state.scene === 'bom' ? `每 1 条饰品 · ${rowTotal(row)}` : hasPrice() ? `小计 ${rowTotal(row)}` : '单位可按本次业务调整'}</span>${detailsButton(row)}</div>${errorsHtml(row)}</article>`
}
function batchTools() {
  return `<div class="batch-tools"><span>统一${state.scene === 'bom' ? '用量' : '数量'}</span><input id="batch-qty" type="number" inputmode="decimal" min="${state.scene === 'bom' ? '0.0001' : '1'}" step="${state.scene === 'bom' ? '0.0001' : '1'}" value="${state.scene === 'bom' ? '1' : '100'}" aria-label="统一填写的${state.scene === 'bom' ? '用量' : '数量'}"><button class="text-button" data-action="apply-qty" ${state.rows.length ? '' : 'disabled'}>应用到已选</button>${state.scene === 'plating' ? `<span>颜色</span>${colorPicker()}<button class="text-button" data-action="apply-color" ${state.rows.length ? '' : 'disabled'}>应用</button>` : ''}</div>`
}
function selectedPanel() {
  return `<aside class="selected-panel" aria-label="待添加明细"><div class="selected-head"><div><h3>待添加清单 <span>${state.rows.length}</span></h3><p>初始预选两项示例；可修改，切换方案保留草稿</p></div><button class="text-button danger" data-action="clear-all" ${state.rows.length ? '' : 'disabled'}>清空</button></div>${batchTools()}<div class="selected-scroll" id="selected-items">${state.rows.length ? state.rows.map(selectedRow).join('') : '<div class="empty"><span>＋</span>从左侧选择商品<small>勾选后在这里填写数量与业务信息<br>切换类型或搜索都不会丢失已选内容</small></div>'}</div><div class="impact">${escape(scene().impact)}</div></aside>`
}
function selectionTray() {
  return `<section class="selection-tray" aria-label="已选商品暂存"><div class="tray-head"><div>已暂存 <b>${state.rows.length}</b> 行<small>暂存后仍需完善${hasPrice() ? '数量、单价等' : '数量等'}明细</small></div><div><button class="text-button danger" data-action="clear-all" ${state.rows.length ? '' : 'disabled'}>清空</button><button class="button small soft" data-action="review" ${state.rows.length ? '' : 'disabled'}>完善明细 →</button></div></div><div class="tray-items">${state.rows.length ? state.rows.map(row => `<div class="tray-item">${img(product(row))}<div>${product(row).name}<small>${escape(row.qty)} ${escape(row.unit)}</small></div><button class="icon-button" data-remove="${row.key}" aria-label="移除 ${product(row).name}">×</button></div>`).join('') : '<span class="footer-summary">勾选上方图片，所选款式会保留在这里。</span>'}</div></section>`
}
function reviewTable(readOnly = false) {
  return `<div class="review-table"><table><thead><tr><th>商品 / 编号</th>${scene().fields.map(field => `<th>${fieldLabel(field)}</th>`).join('')}<th>${readOnly ? '备注' : '操作'}</th></tr></thead><tbody>${state.rows.map(row => `<tr data-line="${row.key}" class="${state.attempted && rowErrors(row, scene()).length ? 'invalid' : ''}"><td><div class="review-product">${img(product(row))}<div class="product-info"><strong>${product(row).name}</strong><small>${product(row).id}</small></div></div>${readOnly ? '' : `${variantHint(row)}${errorsHtml(row)}`}</td>${scene().fields.map(field => `<td>${readOnly ? `<span class="result-qty">${escape(row[field]) || '—'}</span>` : `${fieldInput(row, field)}${field === 'price' ? `<small class="variant-label" data-amount="${row.key}">小计 ${rowTotal(row)}</small>` : ''}`}</td>`).join('')}<td>${readOnly ? escape(row.note) || '—' : `<div>${detailsButton(row)}</div>${state.scene === 'order' ? `<button class="text-button" data-duplicate="${row.key}">再加一行</button>` : ''}<button class="text-button danger" data-remove="${row.key}" aria-label="移除 ${product(row).name}">移除</button>`}</td></tr>`).join('')}</tbody></table>${state.rows.length ? '' : '<div class="empty"><span>＋</span>清单为空，请返回选品</div>'}</div>`
}
function reviewContent() {
  return `<div class="review-layout"><div class="selected-head"><div><h3>核对本次添加 <span>${state.rows.length} 行</span></h3><p>${state.scene === 'bom' ? '每 1 条饰品的用料，不是本次入库量' : '逐行填写，或用统一数量快速批量填入'} · 表格可横向滚动</p></div><button class="text-button" data-action="back">← 继续选品</button></div>${batchTools()}${reviewTable()}<div class="impact">${escape(scene().impact)}</div></div>`
}
function steps() {
  return `<nav class="stepper" aria-label="添加步骤"><button class="${state.step === 1 ? 'active' : ''}" data-action="back" ${state.step === 1 ? 'aria-current="step"' : ''}><span class="step-number">${state.step === 2 ? '✓' : '1'}</span>选择商品</button><span class="step-line"></span><button class="${state.step === 2 ? 'active' : ''}" data-action="review" ${state.step === 2 ? 'aria-current="step"' : ''} ${state.rows.length ? '' : 'disabled'}><span class="step-number">2</span>填写并确认</button></nav>`
}
function renderContent({ preserveScroll = false } = {}) {
  const catalogScroll = $('#catalog-items')?.scrollTop || 0, selectedScroll = $('#selected-items')?.scrollTop || 0, reviewScroll = $('.review-table')?.scrollTop || 0
  const content = $('#picker-content')
  if (state.plan === 'A') content.innerHTML = `<div class="split-layout"><section class="catalog" aria-label="商品库">${catalogHeader()}<div class="catalog-scroll" id="catalog-items"></div><div class="catalog-bottom">${escape(scene().note)}</div></section>${selectedPanel()}</div>`
  else if (state.plan === 'B') content.innerHTML = state.review ? reviewContent() : `<section class="visual-layout" aria-label="图片选品库">${catalogHeader()}<div class="card-grid" id="catalog-items"></div>${selectionTray()}</section>`
  else content.innerHTML = `${steps()}${state.step === 2 ? reviewContent() : `<section class="wizard-layout" aria-label="第一步选择商品">${catalogHeader()}<div class="catalog-scroll" id="catalog-items"></div><div class="catalog-bottom">当前已选 ${state.rows.length} 行 · 下一步逐行填写${hasPrice() ? '数量、单价等' : '数量等'}信息</div></section>`}`
  if ($('#catalog-items')) renderCatalogItems()
  renderFooter()
  if (preserveScroll) {
    if ($('#catalog-items')) $('#catalog-items').scrollTop = catalogScroll
    if ($('#selected-items')) $('#selected-items').scrollTop = selectedScroll
    if ($('.review-table')) $('.review-table').scrollTop = reviewScroll
  }
}
function renderFooter() {
  const invalidCount = state.rows.filter(row => rowErrors(row, scene()).length).length
  const isSelectStep = (state.plan === 'B' && !state.review) || (state.plan === 'C' && state.step === 1)
  const total = hasPrice() ? state.rows.reduce((sum, row) => sum + (lineAmount(row) ?? 0n), 0n) : null
  $('#picker-footer').innerHTML = `<div class="footer-summary">已选 <strong>${state.rows.length}</strong> 行${hasPrice() ? ` · 合计 <b>¥${money(total)}</b>` : state.scene === 'bom' ? ' · 按每 1 条饰品计用量' : ''}${invalidCount ? ` · <span class="footer-error">${invalidCount} 行待完善</span>` : ''}<small>${state.scene === 'bom' ? '不同配件的单位与用量分别保存' : quantitySummary(state.rows)}</small></div><div class="footer-actions">${!isSelectStep && state.plan !== 'A' ? '<button class="button" data-action="back">上一步</button>' : '<button class="button" data-action="cancel">取消</button>'}<button class="button primary" data-action="${isSelectStep ? 'review' : 'submit'}" ${state.rows.length ? '' : 'disabled'}>${isSelectStep ? `下一步 · 完善 ${state.rows.length} 行` : `添加 ${state.rows.length} 行`}</button></div>`
}
function renderAll() {
  $('.picker').hidden = false
  $('#result-panel').hidden = true
  renderPlans()
  renderContext()
  renderContent()
  syncUrl()
}
function toggleProduct(id, checked) {
  const item = productById.get(id)
  if (!item || unavailable(item, scene())) return
  if (checked && !isSelected(id)) state.rows.push(makeRow(item, scene(), `row-${++state.serial}`))
  else if (!checked) state.rows = state.rows.filter(row => row.productId !== id)
  renderContent({ preserveScroll: true })
}
function closePreview() {
  $('.picker').hidden = true
  $('#result-panel').hidden = false
  $('#result-panel').className = 'result-panel closed-preview'
  $('#result-panel').innerHTML = '<div class="result-check">＋</div><h2>已关闭添加预览</h2><p>尚未添加任何真实业务数据。演示草稿仍保留，可以重新打开继续体验。</p><button class="button primary" data-action="reopen">重新打开弹窗</button>'
}
function submit() {
  if (!state.rows.length) return
  state.attempted = true
  const invalidRows = state.rows.filter(row => rowErrors(row, scene()).length)
  if (invalidRows.length) {
    renderContent({ preserveScroll: true })
    const first = document.querySelector(`[data-line="${invalidRows[0].key}"]`)
    first?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    first?.querySelector('input:not([readonly]),select')?.focus({ preventScroll: true })
    notify(`还有 ${invalidRows.length} 行需要完善，草稿已保留在当前页面`)
    return
  }
  $('.picker').hidden = true
  $('#result-panel').hidden = false
  $('#result-panel').className = 'result-panel'
  $('#result-panel').innerHTML = `<div class="result-check">✓</div><h2>已模拟添加 ${state.rows.length} 行${state.scene === 'bom' ? ' BOM 配件' : '明细'}</h2><p>这是操作完成后的效果预览，未调用接口，也未改变库存、单据或价格。<br>${escape(scene().impact)}</p>${reviewTable(true)}<button class="button primary" data-action="reopen">返回弹窗，继续对比方案</button> <button class="button" data-action="reset">重置此场景</button>`
  $('#result-panel').scrollIntoView({ block: 'nearest', behavior: 'smooth' })
}
function openDetails(key) {
  const row = state.rows.find(item => item.key === key)
  if (!row) return
  const dialog = $('#row-details')
  dialog.innerHTML = `<header><div><p class="eyebrow">ROW DETAILS</p><h2 id="details-title">${escape(product(row).name)}</h2></div><button class="icon-button" data-close="row-details" aria-label="关闭明细补充">×</button></header><form id="details-form" data-key="${key}"><div class="detail-form"><p class="detail-caption">${product(row).id} · 仅修改本行。选填字段不占据主要选品空间。</p>${hasWeight() ? `<label>重量（可选，留空不填写）<span class="detail-weight"><input name="weight" type="number" min="0" step="any" value="${escape(row.weight)}" aria-label="本行重量"><select name="weightUnit" aria-label="重量单位"><option ${row.weightUnit === 'kg' ? 'selected' : ''}>kg</option><option ${row.weightUnit === 'g' ? 'selected' : ''}>g</option></select></span></label>` : ''}<label>备注（可选）<textarea name="note" placeholder="填写本行的特殊说明">${escape(row.note)}</textarea></label></div><div class="detail-foot"><button type="button" class="button" data-close="row-details">取消</button><button type="submit" class="button primary">保存本行</button></div></form>`
  dialog.showModal()
}

document.addEventListener('click', event => {
  const button = event.target.closest('button')
  if (!button || button.disabled) return
  if (button.dataset.color) {
    const scope = button.dataset.colorScope, row = state.rows.find(item => item.key === scope)
    if (scope === 'batch') state.batchColor = button.dataset.color
    else if (row) row.color = button.dataset.color
    state.expandedColors.delete(scope)
    updateColorPicker(scope)
    if (row) updateRowFeedback(row)
    renderFooter()
    const picker = document.getElementById(`color-picker-${scope}`)
    const focusTarget = picker?.querySelector(`[data-color="${button.dataset.color}"]`)
    const nextFocus = focusTarget?.closest('[hidden]') ? picker?.querySelector('[data-color-more]') : focusTarget
    nextFocus?.focus({ preventScroll: true })
    return
  }
  if (button.dataset.colorMore) {
    const scope = button.dataset.colorMore
    if (state.expandedColors.has(scope)) state.expandedColors.delete(scope)
    else state.expandedColors.add(scope)
    updateColorPicker(scope)
    document.getElementById(`color-picker-${scope}`)?.querySelector('[data-color-more]')?.focus({ preventScroll: true })
    return
  }
  if (button.dataset.plan) {
    state.plan = button.dataset.plan; state.step = 1; state.review = false
    renderAll(); notify('已切换布局，已选商品与填写内容保持不变'); return
  }
  if (button.dataset.scene) {
    state.scene = button.dataset.scene; state.kind = 'all'; state.query = ''; state.selectedOnly = false; state.step = 1; state.review = false; state.attempted = false; state.batchColor = 'G'; state.expandedColors.clear()
    seedRows(); renderAll(); return
  }
  if (button.dataset.kind) { state.kind = button.dataset.kind; renderContent({ preserveScroll: true }); return }
  if (button.dataset.remove) { state.rows = state.rows.filter(row => row.key !== button.dataset.remove); renderContent({ preserveScroll: true }); return }
  if (button.dataset.duplicate) {
    const original = state.rows.find(row => row.key === button.dataset.duplicate)
    state.rows.push({ ...original, key: `row-${++state.serial}` })
    renderContent({ preserveScroll: true }); notify('已新增同款独立行，不覆盖原行的数量与单价'); return
  }
  if (button.dataset.details) { openDetails(button.dataset.details); return }
  if (button.dataset.close) { document.getElementById(button.dataset.close).close(); return }
  if (button.id === 'survey-open') { $('#survey').showModal(); return }
  if (button.id === 'close-picker') { closePreview(); return }
  const action = button.dataset.action
  if (action === 'clear-search') { state.query = ''; renderContent({ preserveScroll: true }); $('#catalog-search')?.focus() }
  else if (action === 'selected-only') { state.selectedOnly = !state.selectedOnly; renderContent({ preserveScroll: true }) }
  else if (action === 'clear-all') { state.rows = []; renderContent({ preserveScroll: true }) }
  else if (action === 'review') { if (!state.rows.length) return; state.review = true; state.step = 2; renderContent() }
  else if (action === 'back') { state.review = false; state.step = 1; renderContent() }
  else if (action === 'cancel') closePreview()
  else if (action === 'reopen') renderAll()
  else if (action === 'reset') { seedRows(); state.attempted = false; state.step = 1; state.review = false; renderAll() }
  else if (action === 'submit') submit()
  else if (action === 'apply-qty') {
    const value = $('#batch-qty').value
    const check = { ...state.rows[0], qty: value }
    if (rowErrors(check, scene()).some(error => /数量|用量/.test(error))) { notify(state.scene === 'bom' ? '请填写有效用量，最多 4 位小数' : '请填写大于 0 的整数数量'); return }
    state.rows.forEach(row => { row.qty = value }); renderContent({ preserveScroll: true }); notify(`已将数量应用到 ${state.rows.length} 行`)
  } else if (action === 'apply-color') {
    const value = state.batchColor
    state.rows.forEach(row => { row.color = value }); renderContent({ preserveScroll: true }); notify('已应用颜色；缺少对应配件的行需要单独处理')
  }
})
document.addEventListener('input', event => {
  const input = event.target
  if (input.id === 'catalog-search') {
    state.query = input.value
    renderCatalogItems()
    $('.search-clear').hidden = !state.query
    return
  }
  if (input.dataset.row && input.dataset.field) {
    const row = state.rows.find(item => item.key === input.dataset.row)
    if (!row) return
    row[input.dataset.field] = input.value
    renderFooter()
    if (state.attempted) updateRowFeedback(row)
    const amount = document.querySelector(`[data-amount="${row.key}"]`)
    if (amount) amount.textContent = hasPrice() ? `小计 ${rowTotal(row)}` : state.scene === 'bom' ? `每 1 条饰品 · ${row.qty || '—'} ${row.unit}` : amount.textContent
  }
})
document.addEventListener('change', event => {
  const input = event.target
  if (input.dataset.product) toggleProduct(input.dataset.product, input.checked)
  else if (input.id === 'select-visible') {
    const eligible = filtered().filter(item => !unavailable(item, scene()))
    if (input.checked) eligible.forEach(item => { if (!isSelected(item.id)) state.rows.push(makeRow(item, scene(), `row-${++state.serial}`)) })
    else { const ids = new Set(eligible.map(item => item.id)); state.rows = state.rows.filter(row => !ids.has(row.productId)) }
    renderContent({ preserveScroll: true })
  } else if (input.dataset.row && input.dataset.field) {
    const row = state.rows.find(item => item.key === input.dataset.row)
    if (row) { row[input.dataset.field] = input.value; updateRowFeedback(row) }
    renderFooter()
  }
})
document.addEventListener('submit', event => {
  if (event.target.id !== 'details-form') return
  event.preventDefault()
  const form = new FormData(event.target), row = state.rows.find(item => item.key === event.target.dataset.key)
  if (!row) return
  row.note = String(form.get('note') ?? '')
  if (hasWeight()) { row.weight = String(form.get('weight') ?? ''); row.weightUnit = String(form.get('weightUnit') ?? 'kg') }
  $('#row-details').close(); renderContent({ preserveScroll: true }); notify('本行补充信息已保留在演示草稿中')
})
for (const dialog of document.querySelectorAll('dialog')) dialog.addEventListener('click', event => { if (event.target === dialog) { const bounds = dialog.getBoundingClientRect(); if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close() } })
seedRows()
renderAll()
