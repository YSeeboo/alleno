import * as D from './domain.js'

let state = D.createState(), orderId = 'OR-1042', tab = 'details', context = {}, toastTimer, returnFocus, pendingTabFocus
const tabs = [['details', '商品详情', 'gem'], ['production', '生产安排', 'process'], ['information', '订单信息', 'order']]
const app = document.querySelector('#app'), modal = document.querySelector('#modal')
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]))
const money = value => `¥${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const unitPrice = value => Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 7 })
const order = () => D.currentOrder(state, orderId)
const button = (text, action, id = '', cls = 'text', disabled = false) => `<button type="button" class="${cls}" data-action="${action}" data-id="${esc(id)}" ${disabled ? 'disabled' : ''}>${text}</button>`
const tag = (text, color = '') => `<span class="tag ${color}">${esc(text)}</span>`
const sub = (text, cls = '') => `<span class="sub ${cls}">${esc(text)}</span>`
const qty = (value, unit = '', cls = '') => `<span class="qty ${cls}">${value}<small>${esc(unit)}</small></span>`
const field = (label, name, value = '', type = 'text', extra = '') => `<label class="field">${esc(label)}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`
const textarea = (label, name, value = '') => `<label class="field">${esc(label)}<textarea name="${name}" rows="3" maxlength="2000">${esc(value)}</textarea></label>`
const select = (label, name, options, value, extra = '') => `<label class="field">${esc(label)}<select name="${name}" ${extra}>${options.map(([key, text]) => `<option value="${esc(key)}" ${key === value ? 'selected' : ''}>${esc(text)}</option>`).join('')}</select></label>`
const save = (text = '保存修改') => `${button('取消', 'close', '', '')}<button type="submit" class="primary">${text}</button>`
const table = (headers, rows, cls = '') => `<div class="table-wrap" tabindex="0" role="region" aria-label="${cls === 'product-table' ? '商品明细，可横向滚动' : '数据表格，可横向滚动'}"><table class="${cls}"><thead><tr>${headers.map(([text, className = '']) => `<th scope="col" class="${className}">${text}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`
const sectionHead = (title, count = '', actions = '') => `<div class="section-head"><div class="section-title"><h2>${title}</h2>${count !== '' ? `<span class="count">${count}</span>` : ''}</div><div class="actions">${actions}</div></div>`
const icons = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  order: '<path d="M6 3h12v18H6zM9 7h6M9 11h6M9 15h4"/>',
  box: '<path d="m3 7 9-4 9 4v11l-9 4-9-4zM3 7l9 4 9-4M12 11v11M7 5l10 4"/>',
  truck: '<path d="M3 5h12v12H3zM15 9h4l3 4v4h-7"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>',
  gem: '<path d="m3 8 4-5h10l4 5-9 13zM3 8h18M7 3l5 18 5-18"/>',
  people: '<circle cx="9" cy="7" r="3"/><path d="M3 21v-4a6 6 0 0 1 12 0v4M16 4a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 5v2"/>',
  edit: '<path d="m15 4 5 5M4 20l4-1L21 6l-5-5L3 14l-1 7z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v1"/>',
  tool: '<path d="M14 6a5 5 0 0 0-6 6L2 18l4 4 6-6a5 5 0 0 0 6-6l-4 3-3-3z"/>',
  back: '<path d="m10 5-7 7 7 7M3 12h18"/>',
  process: '<circle cx="5" cy="5" r="2"/><circle cx="19" cy="12" r="2"/><circle cx="5" cy="19" r="2"/><path d="M7 5h4a4 4 0 0 1 4 4v6a4 4 0 0 1-4 4H7M15 12h2"/>',
}
const icon = key => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[key] || icons.box}</svg>`

function sidebar() {
  const item = (text, key, active = false) => active ? button(`${icon(key)}${text}`, 'switch-order', '', 'nav-item active') : `<div class="nav-item">${icon(key)}${text}</div>`
  return `<div class="mobile-shade" data-action="menu"></div><button class="mobile-trigger" data-action="menu" aria-label="打开或关闭菜单" aria-expanded="false" aria-controls="sidebar">☰</button>
    <aside id="sidebar" class="sidebar" aria-label="工作台导航"><div class="brand"><img src="../../favicon-white.png" alt="AL">ALLENOP</div><nav class="nav">
    <div class="nav-label">工作台</div>${item('进度看板', 'grid')}${item('仪表盘', 'grid')}
    <div class="nav-label">商品</div>${item('配件管理', 'box')}${item('饰品管理', 'gem')}${item('结构与搭配', 'gem')}
    <div class="nav-label">生产</div>${item('订单管理', 'order', true)}${item('库存备货', 'box')}${item('出货管理', 'truck')}${item('配件采购', 'box')}${item('待补货清单', 'box')}${item('电镀管理', 'gem')}${item('手工管理', 'people')}${item('货物分拣', 'box')}
    <div class="nav-label">库存</div>${item('库存总表', 'box')}${item('库存流水', 'order')}
    <div class="nav-label">管理</div>${item('商家管理', 'people')}${item('用户管理', 'people')}</nav>
    <div class="side-user"><span class="avatar">演</span><div>演示用户<small>独立预览 · 非真实账号</small></div></div></aside>`
}

function product(line) {
  const p = D.products[line.product]
  return `<div class="product-cell"><img src="${p.image}" alt=""><div>${button(esc(p.name), 'product', line.id, 'product-name')}${sub(`${p.id} · ${line.id}`, 'code')}${sub(`客户货号 ${line.code || '—'}`, 'customer-code')}</div></div>`
}

function ownTasks(o) { return state.tasks.filter(task => o.lines.some(line => task.allocations[line.id])) }
function ownShipments(o) { return state.shipments.filter(s => s.orderId === o.id) }

function render() {
  const opened = new Set([...app.querySelectorAll('details[open]')].map(el => el.id))
  const o = order(), canEdit = D.editable(o)
  app.innerHTML = `${sidebar()}<main id="main" tabindex="-1">
    <div class="demo-strip"><span class="demo-label">UI PREVIEW</span><span>虚构数据 · 刷新重置</span><span class="desktop-note">／ 仅预览，不连接真实系统</span><a href="../order-integration/index.html">对比上一版 ↗</a>${button('重置演示', 'reset', '', 'text quiet')}</div>
    <div class="breadcrumb">生产管理 <span>/</span> 订单管理 <span>/</span> ${esc(o.id)}</div>
    <header class="head"><div><div class="title-line"><h1>订单 ${esc(o.id)}</h1>${tag(D.stage(o), `status ${D.stage(o) === '已完成' ? 'green' : 'amber'}`)}</div><div class="subtitle"><strong>${esc(o.customer)}</strong><span>·</span><span>创建于 ${esc(o.date)}</span></div></div><div class="actions head-actions">${button(`${icon('back')}切换订单`, 'switch-order', '', 'text quiet')}${tab === 'details' ? button(`${icon('plus')}新建出货单`, 'new-shipment', '', 'primary', !canEdit) : ''}</div></header>
    <div class="tabs" role="tablist" aria-label="订单工作区">${tabs.map(([key, label, symbol]) => `<button id="tab-${key}" role="tab" aria-selected="${tab === key}" aria-controls="order-panel" tabindex="${tab === key ? 0 : -1}" data-action="tab" data-id="${key}">${icon(symbol)}${label}</button>`).join('')}<span class="tab-note">商品与交付 · 制作计划 · 订单资料</span></div>
    ${o.legacy ? `<div class="alert warning"><strong>${o.requiresReview ? '本单历史实发数量待核对' : '历史完成订单 · 实发数量未核实'}</strong><p>保留原始记录，不按旧状态或生产回收推算出货。此预览不补记历史实发，也不调整库存。</p>${button('查看核对说明', 'historical')}</div>` : ''}
    <div id="order-panel" role="tabpanel" aria-labelledby="tab-${tab}">${tab === 'details' ? orderStats(o) + detailsPage(o) : tab === 'production' ? productionPage(o) : informationPage(o)}</div>
    </main>`
  for (const el of app.querySelectorAll('details')) if (opened.has(el.id)) el.open = true
}

function orderStats(o) {
  const completed = o.lines.filter(line => line.shipped >= line.qty).length
  return `<div class="stats" aria-label="订单概况">${[
      ['订单总额', money(D.total(o)), '含包装费 ' + money(o.packaging), 'green'],
      ['商品明细', `${o.lines.length}<small>项</small>`, '同款不同货号独立记录', ''],
      ['足量交付', o.legacy ? '待核对' : `${completed}<small>/ ${o.lines.length} 项</small>`, '按每条明细的实际出货', ''],
      ['关联生产单', `${new Set(ownTasks(o).map(D.taskLabel)).size}<small>张</small>`, '生产计划不计入现货', ''],
      ['已确认出货', `${ownShipments(o).filter(s => s.status === 'confirmed').length}<small>笔</small>`, o.legacy ? '仅统计可核实凭据' : '支持按明细分批出货', ''],
    ].map(([label, value, note, color]) => `<div class="stat"><div class="stat-label">${label}</div><div class="stat-value ${color}">${value}</div><div class="stat-note">${note}</div></div>`).join('')}</div>`
}

function detailsPage(o) {
  const canEdit = D.editable(o)
  const rows = o.lines.map(line => {
    const p = D.products[line.product], n = D.lineNumbers(state, line)
    return `<tr><td>${product(line)}</td><td class="num">¥${unitPrice(line.price)}${sub(`小计 ${money(line.qty * line.price)}`)}</td><td class="num">${qty(line.qty, p.unit)}</td><td class="num">${button(String(n.planned), 'line-production', line.id, 'text')}${sub('制作计划')}</td><td class="num">${o.legacy ? '未核实' : qty(line.reserved, p.unit)}${sub(`公共可用 ${D.balance(state, line.product).free}`)}</td><td class="num">${o.legacy ? '未核实' : `${qty(line.shipped, p.unit, 'green')}<progress class="progress" value="${line.shipped}" max="${line.qty}" aria-label="${esc(line.code)} 实发进度"></progress>`}${sub(o.legacy ? '不自动补记' : `待发 ${n.remaining} ${p.unit}`)}</td><td><div class="row-actions">${button('编辑', 'edit-line', line.id, 'text', !canEdit)}<button class="icon-button" data-action="line-actions" data-id="${line.id}" aria-label="${esc(line.code || p.name)} 更多操作">···</button></div></td></tr>`
  })
  const products = `<section class="section">${sectionHead('商品明细', `${o.lines.length} 项`, `${button('查看生产安排 →', 'tab', 'production', 'text secondary-action')}${button(`${icon('tool')}物料工具`, 'materials')}${button(`${icon('plus')}添加商品`, 'add-line', '', 'add', !canEdit)}`)}<div class="table-frame">${table([['商品 / 客户货号'], ['单价 / 金额', 'num'], ['订购数量', 'num'], ['生产安排', 'num'], ['已预留', 'num'], ['已出货', 'num'], ['操作']], rows, 'product-table')}<div class="table-total"><span>商品金额<strong>${money(D.total(o) - o.packaging)}</strong></span><span>包装费<strong>${money(o.packaging)}</strong></span><span>合计<strong>${money(D.total(o))}</strong></span></div></div><p class="table-note">${icon('info')}生产安排、库存预留与实际出货分别记录；每条明细足量出货后，订单才会完成。<span class="mobile-scroll-hint">表格可横向滚动。</span></p></section>`
  const shipments = ownShipments(o)
  const shipmentSection = `<section class="section">${sectionHead('出货记录', shipments.length, button('新建出货单', 'new-shipment', '', 'text', !canEdit))}<div class="list-panel">${shipments.length ? shipments.map(s => `<div class="shipment-row"><span class="shipment-icon">${icon('truck')}</span><div class="shipment-body"><div class="shipment-title">${button(esc(s.id), 'shipment', s.id)}${tag(s.status === 'confirmed' ? '已确认出货' : s.status === 'draft' ? '待确认草稿' : '已作废', s.status === 'confirmed' ? 'green' : 'amber')}</div><p>${s.lines.map(e => { const l = o.lines.find(l => l.id === e.lineId); return `${esc(D.products[l.product].name)} · ${e.qty} ${D.products[l.product].unit}` }).join('<br>')}</p>${sub(s.tracking || '未填写物流')}</div><time>${esc(s.date)}</time></div>`).join('') : '<div class="empty">暂无出货记录</div>'}</div></section>`
  const costSection = `<section class="section">${sectionHead('费用与成本', '', button('查看明细', 'cost'))}<div class="list-panel cost-panel"><div class="cost-row"><span>商品金额</span><strong>${money(D.total(o) - o.packaging)}</strong></div><div class="cost-row"><span>包装费 ${button('编辑', 'packaging', '', 'text', !canEdit)}</span><strong>${money(o.packaging)}</strong></div><div class="cost-row"><span>实际成本</span><span class="muted">待核算</span></div><div class="cost-foot">${tag('成本未结齐', 'amber')}加工与实耗未完整结算，暂不展示实际利润。</div></div></section>`
  return `${products}<div class="bottom-grid">${shipmentSection}${costSection}</div>
    <details class="disclosure" id="activity"><summary>操作记录<span>资料、计划、库存与出货分别留痕</span></summary><div class="disclosure-body"><ul class="timeline">${state.events.filter(e => e.detail.includes(o.id)).map(e => `<li>${esc(e.title)}<p>${esc(e.time)} · ${esc(e.detail)}</p></li>`).join('') || '<li>暂无操作记录</li>'}</ul></div></details>`
}

function informationPage(o) {
  const r = o.requirements, editable = D.editable(o)
  const info = (label, value, cls = '') => `<dl><dt>${label}</dt><dd class="${cls}">${value}</dd></dl>`
  const requirement = (title, text, badge = '', image = false) => `<div class="requirement-item"><div class="requirement-copy"><div class="requirement-heading"><h3>${title}</h3>${badge}</div><p>${esc(text || '未填写')}</p></div>${image ? `<div class="requirement-attachment">${button('<img class="reference-image" src="../assets/necklace-structure.svg" alt="包装参考示意图">', 'reference-image', '', 'attachment-button')}<span>包装参考示意图</span><small>虚构附件 · 点击放大</small></div>` : ''}</div>`
  return `<section class="section information-section">${sectionHead('基本信息', '', button(`${icon('edit')}编辑资料`, 'edit-info', '', 'text', !editable))}<div class="information-grid">${info('订单编号', esc(o.id), 'code')}${info('客户名称', esc(o.customer))}${info('创建日期', esc(o.date))}${info('订单状态', tag(D.stage(o), o.legacy ? 'amber' : 'green'))}${info('订单金额（含包装费）', money(D.total(o)), 'green')}${info('商品明细', `${o.lines.length} 项`)}<div class="information-note">${icon('info')}${o.legacy ? '历史实发未核实，不根据旧状态补造出货。' : '资料修改不改变生产计划、库存或出货记录。'}</div></div></section>
    <section class="section information-section">${sectionHead('订单要求', '', button(`${icon('edit')}编辑订单要求`, 'requirements', '', 'text', !editable))}<div class="requirements-panel">${requirement('条码要求', r.barcode ? r.barcodeText : '无需贴条码', tag(r.barcode ? '需要贴条码' : '无需条码', r.barcode ? 'green' : ''))}${requirement('唛头要求', r.shippingMark)}${requirement('参考图片', '用于核对条码、唛头或包装。本 Demo 仅展示虚构示意图，不上传真实附件。', tag('演示示意'), true)}</div></section>
    <section class="section information-section">${sectionHead('订单备注', '', button('编辑备注', 'requirements', '', 'text', !editable))}<div class="order-note">${esc(r.note || '未填写订单备注')}</div></section>
    <p class="table-note">${icon('info')}本页集中维护订单资料与要求；商品数量和价格在「商品详情」中管理，制作计划在「生产安排」中管理。</p>`
}

function productionPage(o) {
  const tasks = ownTasks(o)
  const needs = D.materialNeeds(state, o.id)
  return `<section class="section">${sectionHead('本单制作需求', o.lines.length, button('配件用量与 BOM', 'materials'))}<div class="table-frame">${table([['商品 / 客户货号'], ['订购', 'num'], ['已安排计划', 'num'], ['剩余未安排', 'num'], ['操作']], o.lines.map(line => { const n = D.lineNumbers(state, line), gap = Math.max(0, line.qty - line.shipped - n.planned); return `<tr><td>${product(line)}</td><td class="num">${qty(line.qty, D.products[line.product].unit)}</td><td class="num">${qty(n.planned)}</td><td class="num">${o.legacy ? '待核对' : qty(gap, '', gap ? 'amber' : '')}</td><td>${button(line.product === 'chain' ? '分配已有电镀计划' : '安排制作', line.product === 'chain' ? 'existing' : 'arrange', line.id, 'text', !D.editable(o) || !gap)}</td></tr>` }))}</div><p class="table-note">${icon('info')}未安排需求仅扣除实发和已有计划，不代表库存缺口。现货可直接出货，无需先安排生产。</p></section>
    <section class="section">${sectionHead('关联生产任务', tasks.length)}<div class="table-frame">${tasks.length ? table([['加工单 / 商家'], ['产出商品'], ['阶段'], ['本单计划', 'num'], ['整条计划 / 实收 / 损耗', 'num'], ['操作']], tasks.map(task => { const own = o.lines.reduce((n, l) => n + (task.allocations[l.id] || 0), 0); return `<tr><td>${button(esc(D.taskLabel(task)), 'task', task.id)}${sub(task.supplier)}</td><td>${esc(D.products[task.product].name)}</td><td>${tag(D.taskStage(task), task.status === 'pending' ? 'amber' : 'green')}</td><td class="num">${qty(own, D.products[task.product].unit, 'green')}</td><td class="num">${task.qty} / ${task.received} / ${task.loss}${sub('实收不等于本单可用库存')}</td><td>${button('查看用途', 'task', task.id)}</td></tr>` })) : '<div class="empty">暂无明确数量的生产安排</div>'}</div></section>
    <section class="section">${sectionHead('配件备料', needs.length, button('查看整单理论用量 →', 'materials'))}<div class="table-frame">${needs.length ? table([['制作单 / 本单货号'], ['所需配件'], ['本次需求', 'num'], ['现货计划 / 待电镀计划', 'num'], ['已发料', 'num'], ['备料状态']], needs.map(n => `<tr><td>${button(esc(D.taskLabel(n.task)), 'task', n.task.id)}${sub(n.line.code)}</td><td>${esc(D.materials[n.material].name)}${sub(D.materials[n.material].id)}</td><td class="num">${qty(n.required, D.materials[n.material].unit)}</td><td class="num">${n.source.stock} / ${n.planned}</td><td class="num">${n.source.issued}</td><td>${tag(n.stage, n.uncovered || n.review ? 'amber' : 'green')}</td></tr>`)) : '<div class="empty">暂无本单制作备料需求</div>'}</div><p class="table-note">配件备料计划、实际发料与成品回收保持独立；不将理论 BOM 记作实耗。</p></section>
    ${state.references.some(r => r.orderId === o.id) ? `<details class="disclosure" id="legacy-production"><summary>早期关联记录待核对<span>不并入当前计划</span></summary><div class="disclosure-body">${state.references.filter(r => r.orderId === o.id).map(r => `<p>${esc(r.id)} · 明细 ${esc(r.lineId)} · ${esc(r.detail)}</p>`).join('')}</div></details>` : ''}`
}

function toast(text) {
  const el = document.querySelector('#toast')
  el.textContent = text; el.classList.add('visible')
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('visible'), 3200)
}
function showModal(title, body, kind = '', footer = '', wide = false) {
  if (!modal.open) returnFocus = document.activeElement?.dataset.action ? { ...document.activeElement.dataset } : null
  modal.className = wide ? 'wide' : ''
  modal.innerHTML = `<form id="demo-form" data-kind="${kind}"><div class="dialog-head"><h2 id="dialog-title">${title}</h2><button type="button" class="icon-button" data-action="close" aria-label="关闭弹窗">×</button></div><div class="modal-error alert error" role="alert"></div><div class="dialog-body">${body}</div><div class="dialog-footer">${footer || button('关闭', 'close', '', '')}</div></form>`
  if (!modal.open) modal.showModal()
  else modal.querySelector('input:not([disabled]), select:not([disabled]), button')?.focus()
}
function closeModal(refresh = false) { modal.close(); if (refresh) render() }
modal.addEventListener('close', () => {
  if (returnFocus) [...app.querySelectorAll('[data-action]')].find(el => el.dataset.action === returnFocus.action && el.dataset.id === returnFocus.id)?.focus()
})
modal.addEventListener('click', event => { if (event.target === modal) closeModal() })

function findLine(id) {
  const line = order().lines.find(line => line.id === id)
  if (!line) throw new Error('当前订单明细不存在')
  return line
}
function lineDialog(id = '') {
  const line = id ? findLine(id) : null, locked = line && D.lineProtected(state, line)
  context = { id }
  showModal(line ? '编辑商品明细' : '添加商品', `${line ? `<p class="help">${esc(orderId)} / 明细 ${esc(line.id)}${locked ? ' · 已有业务记录，保留原商品与明细身份。' : ''}</p>` : '<p class="help">同款不同货号会保留为独立明细，不自动合并。</p>'}<div class="form-grid">${select('商品', 'product', Object.entries(D.products).map(([key, p]) => [key, `${p.id} · ${p.name}`]), line?.product || 'necklace', locked ? 'disabled' : '')}${field('客户货号', 'code', line?.code || '', 'text', 'maxlength="80"')}${field('订购数量', 'qty', line?.qty || '', 'number', 'required min="1" max="1000000" step="1"')}${field('单价（元）', 'price', line ? unitPrice(line.price).replaceAll(',', '') : '', 'number', 'required min="0" max="1000000" step="0.0000001"')}</div><p class="help">单价最多保留 7 位小数。已有实发、预留、生产或草稿约束的数量不能随意减少。</p>`, 'line', `${line ? button('删除此明细', 'remove-line', id, 'text danger', locked || order().lines.length === 1) : ''}${save('保存明细')}`)
}
function productDialog(id) {
  const l = findLine(id), p = D.products[l.product]
  showModal('商品详情', `<div class="product-overview"><img src="${p.image}" alt="${esc(p.name)}"><div><h3>${esc(p.name)}</h3><p class="code">${p.id} · 订单明细 ${esc(l.id)}</p><p>${esc(p.spec)}</p><p>客户货号 ${esc(l.code || '—')}</p></div></div><div class="dialog-metrics">${[['订购数量', l.qty], ['已预留待发', order().legacy ? '未核实' : l.reserved], ['已实际出货', order().legacy ? '未核实' : l.shipped]].map(([label, n]) => `<dl><dt>${label}</dt><dd>${n} <small>${p.unit}</small></dd></dl>`).join('')}</div><h3>价格与金额</h3><p class="help">单价 ¥${unitPrice(l.price)} / ${p.unit}　·　商品小计 ${money(l.price * l.qty)}</p><h3>本单关联生产</h3>${taskTable(ownTasks(order()).filter(t => t.allocations[id]), id)}<p class="help">生产份额是计划，不代表已经为本行入库或预留。</p>`, '', `${button('查看生产安排', 'line-production', id, '')}${button('编辑商品明细', 'edit-line', id, 'primary', !D.editable(order()))}`, true)
}
function taskTable(tasks, lineId) {
  return tasks.length ? table([['加工单 / 商家'], ['本行计划', 'num'], ['阶段']], tasks.map(t => `<tr><td>${button(esc(D.taskLabel(t)), 'task', t.id)}${sub(t.supplier)}</td><td class="num">${t.allocations[lineId]}</td><td>${tag(D.taskStage(t), t.status === 'pending' ? 'amber' : 'green')}</td></tr>`)) : '<div class="empty">本行暂无生产计划</div>'
}
function taskDialog(id) {
  const t = state.tasks.find(t => t.id === id)
  showModal(`加工单 ${esc(D.taskLabel(t))}`, `<div class="alert">${esc(t.supplier)} · ${esc(D.taskStage(t))}<br>整条计划 ${t.qty} · 实收 ${t.received} · 损耗 ${t.loss} ${D.products[t.product].unit}</div><h3>订单用途与数量份额</h3>${table([['订单 / 客户'], ['明细 / 客户货号'], ['计划数量', 'num']], Object.entries(t.allocations).map(([id, n]) => { const o = state.orders.find(o => o.lines.some(l => l.id === id)), l = o.lines.find(l => l.id === id); return `<tr><td>${esc(o.id)}${sub(o.customer)}</td><td>${esc(id)}${sub(l.code)}</td><td class="num">${n}</td></tr>` }))}<p class="help">公共未分配计划 ${t.qty - Object.values(t.allocations).reduce((a, b) => a + b, 0)} ${D.products[t.product].unit}。其他订单份额独立保留，不算作公共现货。此处只预览追溯，不模拟加工单执行。</p>`, '', '', true)
}
function materialsDialog() {
  const o = order(), rows = [['necklace', 'clasp', 1], ['earrings', 'hook', 2]].flatMap(([product, material, per]) => {
    const n = o.lines.filter(l => l.product === product).reduce((sum, l) => sum + l.qty, 0)
    return n ? [`<tr><td>${esc(D.materials[material].name)}${sub(D.materials[material].id)}</td><td class="num">${n * per} ${D.materials[material].unit}</td><td>${esc(D.products[product].name)}${sub(`单件用量 ${per} × 订购 ${n}`)}</td><td class="num">${state.materialStock[material]}${sub('整库账面量')}</td></tr>`] : []
  })
  showModal('物料工具 · 订单 BOM 汇总', `<div class="alert">当前 BOM 理论用量，用于查料与规划，不是实际发料或结算成本。</div>${rows.length ? table([['配件'], ['理论需求', 'num'], ['用量来源'], ['现货参考', 'num']], rows) : '<div class="empty">本单为直接销售配件，无饰品 BOM 用量。</div>'}<p class="help">制作任务的备料来源与实际发料，在「生产安排」中分开查看。裁剪、领料与 PDF 工具仍保留在真实页面；本 Demo 不生成业务凭据。</p>`, '', `${button('查看制作任务备料', 'tab', 'production', 'primary')}`, true)
}
function arrangeDialog(id) {
  const l = findLine(id), gap = Math.max(0, l.qty - l.shipped - D.lineNumbers(state, l).planned)
  context = { id }
  showModal('安排手工制作', `<div class="alert">${esc(l.code)} · 明细 ${esc(id)}<br>只建立制作计划，不自动发料、入库、预留或出货。</div>${field('手工商家', 'supplier', '', 'text', 'required maxlength="80" list="suppliers"')}<datalist id="suppliers"><option value="青禾手作"><option value="拾光工坊"></datalist><div class="form-grid">${field('整条产出计划', 'planned', '', 'number', 'required min="1" step="1"')}${field(`安排给本行（最多 ${gap}）`, 'qty', '', 'number', `required min="1" max="${gap}" step="1"`)}</div><p class="help">多做的数量保留为公共未分配计划，不是可出货现货。</p>${select('制作单处理方式', 'target', [['new', '新建独立手工单（默认）']], 'new')}<p class="help">输入商家后，可明确选择追加到该商家待发出的单据；追加新增独立产出，不合并原明细。</p>`, 'arrange', save('保存制作安排'))
}
function existingDialog(id) {
  const l = findLine(id), tasks = state.tasks.filter(t => t.product === l.product && ['pending', 'processing'].includes(t.status))
  showModal('从已有任务分配', `<p class="help">选择明确的产出后，再为本行填写计划数量。不会覆盖其他订单的份额。</p>${table([['加工单 / 商家'], ['整条计划', 'num'], ['未分配', 'num'], ['操作']], tasks.map(t => `<tr><td>${esc(D.taskLabel(t))}${sub(t.supplier)}</td><td class="num">${t.qty}</td><td class="num">${t.qty - Object.values(t.allocations).reduce((a, b) => a + b, 0)}</td><td>${button('调整本单分配', 'allocate', `${t.id}:${id}`)}</td></tr>`))}`, '', '', true)
}
function shipmentDialog(id) {
  const s = state.shipments.find(s => s.id === id)
  showModal(`出货单 ${esc(id)}`, `<div class="alert">${s.status === 'confirmed' ? '已确认实际出货，已经扣减库存。' : '仅保存草稿，尚未占库或扣库。'}</div>${table([['商品 / 客户货号'], ['本次数量', 'num']], s.lines.map(e => { const l = findLine(e.lineId); return `<tr><td>${product(l)}</td><td class="num">${e.qty} ${D.products[l.product].unit}</td></tr>` }))}<p class="help">${esc(s.date)} · 物流 ${esc(s.tracking || '未填写')}<br>备注 ${esc(s.note || '无')}</p><p class="help">本版专注详情 UI，草稿仅在演示内保存；不会调用真实出货接口。</p>`, '', '', true)
}
function requirementsDialog() {
  const r = order().requirements
  showModal('编辑订单要求', `<label class="check-label"><input name="barcode" type="checkbox" ${r.barcode ? 'checked' : ''}>需要贴条码</label>${textarea('条码要求', 'barcodeText', r.barcodeText)}${textarea('唛头要求', 'shippingMark', r.shippingMark)}${textarea('订单备注', 'note', r.note)}<p class="help">此原型不上传真实附件，修改只保留在当前演示中。</p>`, 'requirements', save())
}

function navigate() {
  const parts = location.hash.slice(1).split('/')
  orderId = state.orders.some(o => o.id === parts[0]) ? parts[0] : 'OR-1042'
  tab = tabs.some(([key]) => key === parts[1]) ? parts[1] : 'details'
  if (modal.open) { returnFocus = null; modal.close() }
  document.body.classList.remove('menu-open'); render()
  if (pendingTabFocus) {
    document.querySelector(`#tab-${pendingTabFocus}`)?.focus()
    pendingTabFocus = null
  }
}
function go(id = orderId, next = tab) {
  const hash = `#${id}/${next}`
  if (location.hash === hash) navigate(); else location.hash = hash
}
window.addEventListener('hashchange', navigate)

document.addEventListener('click', event => {
  const el = event.target.closest('[data-action]')
  if (!el || el.disabled) return
  const { action, id } = el.dataset
  try {
    switch (action) {
      case 'menu': document.querySelector('.mobile-trigger').setAttribute('aria-expanded', String(document.body.classList.toggle('menu-open'))); break
      case 'close': closeModal(); break
      case 'reset': showModal('重置本次演示', '<p class="help">仅恢复此页面的虚构数据，不影响真实系统。刷新页面也会重置。</p>', 'reset', save('重置演示')); break
      case 'switch-order': showModal('切换演示订单', `<div class="order-switch">${state.orders.map(o => button(`<span>${esc(o.id)} · ${esc(o.customer)}${sub(o.requiresReview ? '历史实发待核对示例' : o.legacy ? '历史完成示例' : '正常订单 · 可交互')}</span>${tag(D.stage(o), o.legacy ? 'amber' : 'green')}`, 'open-order', o.id, '')).join('')}</div><p class="help">这些都是虚构订单，不是正式订单列表。</p>`); break
      case 'open-order': go(id, 'details'); break
      case 'tab': pendingTabFocus = id; go(orderId, id); break
      case 'edit-info': showModal('编辑订单资料', `<div class="form-grid">${field('客户名称', 'customer', order().customer, 'text', 'required maxlength="80"')}${field('创建日期', 'date', order().date, 'date', 'required')}</div><p class="help">仅更新资料，不改变商品、生产、库存或出货。</p>`, 'info', save('保存资料')); break
      case 'requirements': requirementsDialog(); break
      case 'reference-image': showModal('包装参考示意图', '<img class="image-preview" src="../assets/necklace-structure.svg" alt="珍珠项链结构与包装参考示意图"><p class="help">虚构示意图，不是真实订单附件。</p>'); break
      case 'product': productDialog(id); break
      case 'edit-line': lineDialog(id); break
      case 'add-line': lineDialog(); break
      case 'remove-line': D.removeLine(state, orderId, id); closeModal(true); toast('已移除演示明细'); break
      case 'line-actions': {
        const l = findLine(id), n = D.lineNumbers(state, l), editable = D.editable(order())
        showModal(`${esc(l.code || D.products[l.product].name)} · 更多操作`, `<div class="action-list">${button('查看商品详情 →', 'product', id, '')}${button('预留公共库存 →', 'reserve', id, '', !editable || !n.gap)}${button('释放本行预留 →', 'release', id, '', !editable || !l.reserved)}${button('查看本行生产 →', 'line-production', id, '')}${button('从已有任务分配 →', 'existing', id, '', !editable)}${l.product !== 'chain' ? button('新建 / 追加制作安排 →', 'arrange', id, '', !editable || l.qty - l.shipped - n.planned <= 0) : ''}</div>`)
        break
      }
      case 'reserve': case 'release': {
        const l = findLine(id), release = action === 'release'
        context = { id, release }
        showModal(release ? '释放本行预留' : '预留公共库存', `<div class="alert">只调整当前明细的待发预留，不改变实物库存，不计入实际出货。</div><p class="help">${esc(l.code)} · 待发 ${l.qty - l.shipped} · 本行预留 ${l.reserved} · 公共可用 ${D.balance(state, l.product).free}</p>${field(release ? '本次释放数量' : '本次预留数量', 'qty', '', 'number', 'required min="1" step="1"')}`, 'reservation', save(release ? '确认释放' : '确认预留'))
        break
      }
      case 'line-production': showModal('本行生产安排', taskTable(ownTasks(order()).filter(t => t.allocations[id]), id), '', button('进入生产安排', 'tab', 'production', 'primary'), true); break
      case 'task': taskDialog(id); break
      case 'materials': materialsDialog(); break
      case 'arrange': arrangeDialog(id); break
      case 'existing': existingDialog(id); break
      case 'allocate': {
        const [taskId, lineId] = id.split(':'), t = state.tasks.find(t => t.id === taskId), l = findLine(lineId)
        context = { taskId, lineId }
        showModal('调整本行生产份额', `<div class="alert">${esc(D.taskLabel(t))} · ${esc(l.code)}<br>只修改当前明细。其他行、其他订单份额独立保留。</div>${field('本行计划数量', 'qty', t.allocations[lineId] || 0, 'number', 'required min="0" step="1"')}`, 'allocation', save('保存本行份额'))
        break
      }
      case 'shipment': shipmentDialog(id); break
      case 'new-shipment':
        showModal('新建出货单 · 演示草稿', `<div class="alert">选择实际明细并填写数量，不自动全选或预填。此 UI Demo 只保存演示草稿，不确认真实出货。</div>${table([['选择'], ['商品 / 客户货号'], ['剩余待发', 'num'], ['本次数量']], order().lines.map(l => `<tr><td><input name="selected" type="checkbox" value="${l.id}" aria-label="选择 ${esc(l.code)}" ${l.shipped >= l.qty ? 'disabled' : ''}></td><td>${product(l)}</td><td class="num">${l.qty - l.shipped}</td><td><input name="qty-${l.id}" class="shipment-input" type="number" min="1" max="${l.qty - l.shipped}" step="1" aria-label="${esc(l.code)} 本次出货数量" disabled></td></tr>`))}<p class="help">公共成品库存可以直接出货，无需关联生产或 BOM。草稿不预留、不扣库。</p>${field('物流信息（可选）', 'tracking', '', 'text', 'maxlength="200"')}`, 'shipment', save('保存演示草稿'), true)
        break
      case 'packaging': showModal('编辑包装费', field('本单包装费（元）', 'packaging', order().packaging, 'number', 'required min="0" max="1000000" step="0.01"'), 'packaging', save()); break
      case 'cost': showModal('费用与成本', `<div class="cost-row"><span>商品金额</span><strong>${money(D.total(order()) - order().packaging)}</strong></div><div class="cost-row"><span>包装费</span><strong>${money(order().packaging)}</strong></div><div class="cost-row"><span>订单总额</span><strong>${money(D.total(order()))}</strong></div><div class="alert warning">实际成本待核算，不展示已结算利润。</div><p class="help">参考报价、BOM 理论成本和实际材料、加工费用分别展示。本次仅预览结构，未虚构结算成本。</p>`, '', button('查看 BOM 理论用量', 'materials', '', '')); break
      case 'historical': showModal('历史实发核对说明', '<div class="alert warning">先核对原始出货凭据。不能将旧完成状态、生产回收或现有库存解释为历史实发。</div><p class="help">已有实发或无法确认时，继续核对。本视觉 Demo 不启用历史订单，不提供无凭据补记，也不调整库存。</p>'); break
    }
  } catch (error) { if (modal.open) modal.querySelector('.modal-error').textContent = error.message; else toast(error.message) }
})

document.addEventListener('change', event => {
  if (event.target.name === 'selected') {
    const input = modal.querySelector(`[name="qty-${event.target.value}"]`)
    input.disabled = !event.target.checked; input.required = event.target.checked
    if (event.target.checked) input.focus()
  }
})
document.addEventListener('input', event => {
  if (event.target.name !== 'supplier' || modal.querySelector('form')?.dataset.kind !== 'arrange') return
  const tasks = state.tasks.filter(t => t.type === 'handcraft' && t.status === 'pending' && t.supplier === event.target.value.trim())
    .filter((t, i, items) => items.findIndex(other => D.taskLabel(other) === D.taskLabel(t)) === i)
  modal.querySelector('[name="target"]').innerHTML = `<option value="new">新建独立手工单（默认）</option>${tasks.map(t => `<option value="${esc(t.id)}">明确追加到 ${esc(D.taskLabel(t))} · ${esc(t.supplier)}</option>`).join('')}`
})
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !modal.open && document.body.classList.contains('menu-open')) {
    document.body.classList.remove('menu-open')
    const trigger = document.querySelector('.mobile-trigger')
    trigger.setAttribute('aria-expanded', 'false'); trigger.focus()
  }
  if (!event.target.matches('[role="tab"]') || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const current = tabs.findIndex(([key]) => key === tab)
  const index = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length
  const next = tabs[index][0]
  pendingTabFocus = next; go(orderId, next)
})
modal.addEventListener('submit', event => {
  event.preventDefault()
  const form = event.target, values = Object.fromEntries(new FormData(form))
  modal.querySelector('.modal-error').textContent = ''
  try {
    switch (form.dataset.kind) {
      case 'reset': state = D.createState(); context = {}; closeModal(); go('OR-1042', 'details'); toast('演示已重置'); return
      case 'info': D.editInfo(state, orderId, values); break
      case 'requirements': D.editRequirements(state, orderId, { ...values, barcode: form.elements.barcode.checked }); break
      case 'line': context.id ? D.editLine(state, orderId, context.id, values) : D.addLine(state, orderId, values); break
      case 'reservation': D.reserve(state, context.id, values.qty, context.release); break
      case 'packaging': D.editPackaging(state, orderId, values.packaging); break
      case 'arrange': D.arrange(state, { lineId: context.id, qty: values.qty, planned: values.planned, supplier: values.supplier.trim(), targetId: values.target }); break
      case 'allocation': {
        const t = state.tasks.find(t => t.id === context.taskId)
        const own = Object.fromEntries(order().lines.filter(l => l.product === t.product).map(l => [l.id, l.id === context.lineId ? values.qty : t.allocations[l.id] || 0]))
        D.allocate(state, t.id, orderId, own); break
      }
      case 'shipment': {
        const lines = new FormData(form).getAll('selected').map(lineId => ({ lineId, qty: Number(values[`qty-${lineId}`]) }))
        D.draftShipment(state, { orderId, lines, tracking: values.tracking, note: 'UI Demo 演示草稿' }); break
      }
      default: return
    }
    closeModal(true); toast('已保存至本次演示，真实数据不受影响')
  } catch (error) { modal.querySelector('.modal-error').textContent = error.message }
})

navigate()
