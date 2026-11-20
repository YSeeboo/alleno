import * as D from './domain.js'

let state = D.createState()
let view = 'order', orderId = 'OR-1042', tab = 'details', bomMode = 'task'
let context = {}, shipping = null, toastTimer, returnFocus = null
const app = document.querySelector('#app'), modal = document.querySelector('#modal')
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]))
const money = value => `¥${Number(value).toFixed(2)}`
const order = () => D.currentOrder(state, orderId)
const tag = (text, color = '') => `<span class="tag ${color}">${esc(text)}</span>`
const btn = (text, action, id = '', cls = 'text', disabled = false) => `<button type="button" class="${cls}" data-action="${action}" data-id="${esc(id)}" ${disabled ? 'disabled' : ''}>${esc(text)}</button>`
const sub = text => `<span class="sub">${esc(text)}</span>`
const table = (head, rows) => `<div class="table-wrap"><table><thead><tr>${head.map(text => `<th scope="col">${text}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`
const card = (title, body, actions = '', foot = '') => `<section class="card"><div class="card-head"><h2>${title}</h2>${actions}</div>${body}${foot ? `<div class="card-foot">${foot}</div>` : ''}</section>`
const product = line => `<div class="product"><img src="${D.products[line.product].image}" alt=""><div><strong>${esc(D.products[line.product].name)}</strong>${sub(`${D.products[line.product].id} · ${line.id}`)}${sub(`客户货号 ${line.code || '—'}`)}</div></div>`
const field = (label, name, value = '', type = 'text', extra = '') => `<label class="field">${esc(label)}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`
const textarea = (label, name, value) => `<label class="field">${esc(label)}<textarea name="${name}" rows="3" maxlength="2000">${esc(value)}</textarea></label>`
const select = (label, name, options, value, extra = '') => `<label class="field">${esc(label)}<select name="${name}" ${extra}>${options.map(([id, text]) => `<option value="${esc(id)}" ${id === value ? 'selected' : ''}>${esc(text)}</option>`).join('')}</select></label>`
const footer = text => `<button type="button" data-action="close">取消</button><button type="submit" class="primary">${esc(text)}</button>`

const icons = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  order: '<path d="M6 3h12v18H6zM9 7h6M9 11h6M9 15h4"/>',
  box: '<path d="m3 7 9-4 9 4v11l-9 4-9-4zM3 7l9 4 9-4M12 11v11M7 5l10 4"/>',
  truck: '<path d="M3 5h12v12H3zM15 9h4l3 4v4h-7M6 17v1m12-1v1"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>',
  gem: '<path d="m3 8 4-5h10l4 5-9 13zM3 8h18M7 3l5 18 5-18"/>',
  people: '<circle cx="9" cy="7" r="3"/><path d="M3 21v-4a6 6 0 0 1 12 0v4M16 4a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 5v2"/>',
}
const icon = key => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[key] || icons.box}</svg>`

function sidebar() {
  const item = (label, key, action) => action ? `<button class="nav-item ${view === action ? 'active' : ''}" data-action="navigate" data-id="${action}">${icon(key)}${label}</button>` : `<div class="nav-item inert">${icon(key)}${label}</div>`
  return `<div class="mobile-shade" data-action="menu"></div><button class="mobile-trigger" data-action="menu" aria-label="打开或关闭菜单">☰</button>
    <aside class="sidebar" aria-label="工作台导航"><div class="brand"><img src="../../favicon-white.png" alt="AL">ALLENOP</div><nav class="nav">
    ${item('进度看板', 'grid')}${item('仪表盘', 'grid')}<div class="nav-label">基础资料</div>${item('配件管理', 'box')}${item('饰品管理', 'gem')}${item('结构与搭配', 'gem')}
    <div class="nav-label">生产</div>${item('订单管理', 'order', 'order')}${item('库存备货', 'box', 'readiness')}${item('出货管理', 'truck', 'shipments')}${item('配件采购', 'box')}${item('电镀管理', 'gem')}${item('手工管理', 'people')}
    <div class="nav-label">库存与设置</div>${item('库存总表', 'box')}${item('库存流水', 'order')}${item('商家管理', 'people')}
    </nav><div class="side-user"><span class="avatar">演</span><div>演示用户<small>独立原型 · 非真实账号</small></div></div></aside>`
}

function render() {
  const opened = new Set([...app.querySelectorAll('details[open]')].map(el => el.id))
  app.innerHTML = `${sidebar()}<main id="main" tabindex="-1"><div class="demo-notice">${tag('整合 Demo', 'green')}<span>虚构数据 · 刷新重置</span><span class="demo-description">／ 不连接真实系统</span>${btn('重置演示', 'reset')}</div>${view === 'order' ? renderOrder() : renderGlobal()}</main>`
  for (const el of app.querySelectorAll('details')) if (opened.has(el.id)) el.open = true
}

function renderOrder() {
  const o = order(), canEdit = D.editable(o), status = D.stage(o)
  return `<header class="heading"><div class="breadcrumb">生产 / 订单管理 / ${esc(o.id)}</div><div class="title-row"><h1>${esc(o.id)} <span>/ ${esc(o.customer)}</span></h1><div class="actions">${tag(status, status === '已完成' ? 'green' : 'amber')}${btn('＋ 新建出货单', 'new-shipment', o.id, 'primary', !canEdit)}</div></div></header>
    <div class="toolbar"><span class="muted">一张订单，统一管理需求、生产与交付</span><select aria-label="切换演示订单" id="order-picker">${state.orders.map(item => `<option value="${item.id}" ${item.id === o.id ? 'selected' : ''}>${item.id} · ${esc(item.customer)}${item.requiresReview ? '（待核对示例）' : item.legacy ? '（历史完成示例）' : ''}</option>`).join('')}</select></div>
    <div class="tabs" role="tablist" aria-label="订单工作区"><button id="tab-details" role="tab" aria-selected="${tab === 'details'}" aria-controls="order-panel" tabindex="${tab === 'details' ? 0 : -1}" data-action="tab" data-id="details">订单详情</button><button id="tab-production" role="tab" aria-selected="${tab === 'production'}" aria-controls="order-panel" tabindex="${tab === 'production' ? 0 : -1}" data-action="tab" data-id="production">生产安排</button></div>
    <div id="order-panel" role="tabpanel" aria-labelledby="tab-${tab}">${tab === 'details' ? detailsPage(o) : productionPage(o)}</div>`
}

function detailsPage(o) {
  const completed = o.lines.filter(line => line.shipped >= line.qty).length, canEdit = D.editable(o)
  const info = card('基本信息', `<div class="card-body info-grid"><dl><dt>客户</dt><dd>${esc(o.customer)}</dd></dl><dl><dt>创建日期</dt><dd>${esc(o.date)}</dd></dl><dl><dt>交货日期</dt><dd>${esc(o.due)}</dd></dl><dl><dt>订单总额（含包装费）</dt><dd>${money(D.total(o))}</dd></dl></div>
    <div class="delivery"><strong>${o.legacy ? '历史实发未核实' : `已全部发货 ${completed} / ${o.lines.length} 项`}</strong>${!o.legacy ? `<meter min="0" max="100" value="${o.lines.reduce((sum, line) => sum + line.shipped / line.qty, 0) / o.lines.length * 100}" aria-label="各明细出货比例平均值"></meter>` : ''}<p>${o.legacy ? '不根据旧状态、生产回收推算实际出货。' : '部分发货不计入完成项；全部明细足量出货后自动完成。'}</p></div>`, btn('编辑资料', 'edit-info', '', 'text', !canEdit))
  const r = o.requirements
  const requirements = `<details class="card" id="requirements"><summary><h2>订单要求</h2><span class="summary-hint">${r.barcode ? '需要贴条码' : '无需条码'} · 唛头 · 备注</span></summary><div class="card-body"><div class="requirements"><div><span class="muted">条码要求</span><p>${esc(r.barcode ? r.barcodeText : '无需贴条码')}</p></div><div><span class="muted">唛头要求</span><p>${esc(r.shippingMark || '未填写')}</p></div><div class="wide"><span class="muted">订单备注</span><p>${esc(r.note || '未填写')}</p></div></div><div class="actions">${btn('编辑订单要求', 'requirements', '', 'text', !canEdit)}${btn('查看包装参考图', 'reference-image')}</div></div></details>`
  const rows = o.lines.map(line => {
    const n = D.lineNumbers(state, line)
    return `<tr><td>${product(line)}</td><td>${line.qty} ${D.products[line.product].unit}${sub(`单价 ${money(line.price)}`)}</td><td>${money(line.price * line.qty)}</td><td>${n.planned}${sub('制作计划')}</td><td>${o.legacy ? '未核实' : line.reserved}${sub(`公共可用 ${D.balance(state, line.product).free}`)}</td><td>${o.legacy ? '未核实' : `<strong class="${line.shipped >= line.qty ? 'green' : ''}">${line.shipped}</strong>`}${sub(o.legacy ? '不自动补记' : `剩余待发 ${n.remaining}`)}</td><td><div class="row-actions">${btn('编辑明细', 'edit-line', line.id, 'text', !canEdit)}${btn('预留库存', 'reserve', line.id, 'text', !canEdit || n.gap === 0)}${line.reserved ? btn('取消预留', 'release', line.id, 'text', !canEdit) : ''}${btn('安排制作', 'arrange', line.id, 'text', !canEdit || line.product === 'chain' || line.qty - line.shipped - n.planned <= 0)}</div></td></tr>`
  })
  const lines = card('商品明细', table(['商品 / 客户货号', '订购数量 / 单价', '金额', '生产安排', '已预留待发', '已出货', '操作'], rows), `<div class="actions">${btn('查看生产安排 →', 'tab', 'production')}${btn('＋ 添加商品', 'add-line', '', 'small', !canEdit)}</div>`, '商品资料和交付数量在同一张明细表中管理；同款不同客户货号保留独立行。生产安排不代表有库存，也不与现货相加。')
  const shipments = card('出货记录', shipmentTable(state.shipments.filter(s => s.orderId === o.id)), btn('新建出货单', 'new-shipment', o.id, 'text', !canEdit))
  const fees = `<details class="card" id="fees"><summary><h2>费用与成本</h2><span class="summary-hint">包装费 ${money(o.packaging)} · 估算与实际分开</span></summary><div class="card-body two-col"><div><h3>订单费用</h3><div class="cost-list"><div><span>商品金额</span><span>${money(D.total(o) - o.packaging)}</span></div><div><span>包装费 ${btn('编辑', 'packaging', '', 'text', !canEdit)}</span><span>${money(o.packaging)}</span></div><div class="cost-total"><span>订单总额</span><span>${money(D.total(o))}</span></div></div></div><div><h3>成本信息</h3><p class="muted">${o.legacy ? '原有成本记录按来源保留，不用旧完成状态补算实际成本。' : '当前仅可查看 BOM 理论用量；加工与实耗尚未结齐，实际成本待核算。'}</p>${tag('不完整 · 不显示虚假利润', 'amber')}${btn('查看 BOM 用量 →', 'bom-link')}</div></div></details>`
  const activity = `<details class="card" id="activity"><summary><h2>操作记录</h2><span class="summary-hint">资料修改、生产安排、预留与出货分别记录</span></summary><div class="card-body"><ul class="timeline">${state.events.filter(e => e.detail.includes(o.id)).slice(0, 8).map(e => `<li><strong>${esc(e.title)}</strong><p>${esc(e.detail)} · ${esc(e.time)}</p></li>`).join('') || '<li><strong>暂无本单操作记录</strong></li>'}</ul></div></details>`
  const review = o.requiresReview ? `<div class="alert warning"><strong>本单历史实发数量待核对</strong><p>资料与生产记录可查看。核对前暂停新增出货，避免重复记账；其他正常订单不需要此步骤。</p>${btn('核对历史实发', 'verify')}</div>` : ''
  return `${info}${requirements}${review}${lines}${shipments}${fees}${activity}`
}

function shipmentTable(shipments) {
  if (!shipments.length) return '<div class="empty">暂无出货记录。供应商回收不会记作客户出货。</div>'
  return table(['出货单 / 日期', '订单', '状态', '本次明细', '物流信息', '操作'], shipments.map(s => `<tr><td>${esc(s.id)}${sub(s.date)}</td><td>${btn(s.orderId, 'open-order', s.orderId)}</td><td>${tag({ draft: '待确认草稿', confirmed: '已确认出货', void: '已作废' }[s.status], s.status === 'confirmed' ? 'green' : s.status === 'draft' ? 'amber' : '')}</td><td>${s.lines.map(e => {
    const line = D.currentOrder(state, s.orderId).lines.find(l => l.id === e.lineId)
    return `${esc(D.products[line.product].name)} ${e.qty} ${D.products[line.product].unit}`
  }).join('<br>')}</td><td>${esc(s.tracking || '未填写')}</td><td>${btn(s.status === 'draft' ? '核对并确认' : '查看详情', 'shipment', s.id)}</td></tr>`))
}

function productionPage(o) {
  const canEdit = D.editable(o)
  const demand = card('本单制作需求', table(['商品 / 客户货号', '订购', '已安排计划', '未安排需求', '操作'], o.lines.map(line => {
    const n = D.lineNumbers(state, line), gap = Math.max(0, line.qty - line.shipped - n.planned)
    return `<tr><td>${product(line)}</td><td>${line.qty} ${D.products[line.product].unit}</td><td>${n.planned}</td><td>${o.legacy ? '待核对' : gap}${sub('扣除实发与已有计划')}</td><td>${btn(line.product === 'chain' ? '选择电镀来源' : '＋ 安排手工制作', line.product === 'chain' ? 'plating-candidates' : 'arrange', line.id, 'text', !canEdit || !gap)}</td></tr>`
  })), '', '安排只建立制作计划；不会自动发料、预留成品、入库或记入客户出货。已有成品可以直接出货，无需先安排生产。')
  const tasks = state.tasks.filter(task => o.lines.some(line => task.allocations[line.id]))
  const sources = card('关联生产任务', tasks.length ? table(['加工单 / 商家', '产出商品', '阶段', '本单计划', '整条计划 / 实收 / 损耗', '其他订单 / 公共计划', '操作'], tasks.map(task => {
    const own = o.lines.reduce((n, line) => n + (task.allocations[line.id] || 0), 0), allocated = Object.values(task.allocations).reduce((a, b) => a + b, 0)
    return `<tr><td>${btn(D.taskLabel(task), 'task', task.id)}${sub(task.supplier)}${task.id !== D.taskLabel(task) ? sub(`独立产出 ${task.id}`) : ''}</td><td>${esc(D.products[task.product].name)}</td><td>${tag(D.taskStage(task), task.status === 'pending' ? 'amber' : 'blue')}</td><td><strong class="green">${own}</strong> ${D.products[task.product].unit}</td><td>${task.qty} / ${task.received} / ${task.loss}${task.loss ? sub('存在损耗，需核对交付缺口') : ''}</td><td>${allocated - own} / ${task.qty - allocated}${sub('公共计划不等于现货')}</td><td>${btn('调整本单分配', 'allocate', task.id, 'text', !canEdit || !['pending', 'processing'].includes(task.status))}</td></tr>`
  })) : '<div class="empty">暂无明确数量的制作安排；历史关联不会自动转换为份额。</div>', btn('从已有任务分配', 'candidates', '', 'text', !canEdit))
  const needs = D.materialNeeds(state, o.id)
  let bom
  if (bomMode === 'task') {
    bom = needs.length ? table(['制作单 / 订单商品', '所需配件', '本次需求', '现货已安排', '待电镀计划', '已发料', '状态 / 操作'], needs.map(n => `<tr><td>${btn(D.taskLabel(n.task), 'task', n.task.id)}${sub(`${n.line.code} · ${n.quantity} ${D.products[n.line.product].unit}`)}</td><td>${esc(D.materials[n.material].name)}${sub(D.materials[n.material].id)}</td><td>${n.required} ${D.materials[n.material].unit}${sub(`单件用量 ${n.per}`)}</td><td>${n.source.stock}</td><td>${n.planned}</td><td>${n.source.issued}</td><td>${tag(n.stage, n.uncovered || n.review ? 'amber' : 'green')}${sub(`尚未安排 ${n.uncovered}`)}${btn('调整备料来源', 'source', n.id, 'text', !canEdit || n.task.status !== 'pending')}</td></tr>`)) : '<div class="empty">安排制作后，在这里按具体任务展开 BOM 备料。也可切换查看整单理论用量。</div>'
  } else {
    const summary = [['necklace', 'clasp', 1], ['earrings', 'hook', 2]].map(([p, material, per]) => {
      const quantity = o.lines.filter(l => l.product === p).reduce((n, l) => n + l.qty, 0)
      return quantity ? `<tr><td>${esc(D.materials[material].name)}${sub(D.materials[material].id)}</td><td>${quantity * per} ${D.materials[material].unit}</td><td>${esc(D.products[p].name)}${sub(`单件用量 ${per} × 订购 ${quantity}`)}</td><td>${state.materialStock[material]}${sub('整库账面量，非本单独占')}</td></tr>` : ''
    }).filter(Boolean)
    bom = summary.length ? table(['配件', '整单理论需求', '用量来源', '现货参考'], summary) : '<div class="empty">本单为直接销售配件，无饰品 BOM 需求。</div>'
  }
  const bomCard = card('配件备料与 BOM', `<div class="card-body"><p class="section-note">理论用量、备料计划与实际发料分开查看；配件不会算作成品现货。不同单位不混加。</p></div>${bom}`, `<div class="segmented" aria-label="BOM 展示方式">${btn('按制作任务', 'bom-mode', 'task', bomMode === 'task' ? 'active' : '')}${btn('订单 BOM 汇总', 'bom-mode', 'order', bomMode === 'order' ? 'active' : '')}</div>`, '本页提供备料来源的上下文；实际发料、回收、损耗和付款仍在对应加工单中处理，不新增一套重复凭据。')
  const refs = state.references.filter(r => r.orderId === o.id)
  const references = refs.length ? `<details class="card" id="references"><summary><h2>关联记录待核对</h2><span class="summary-hint">${refs.length} 条缺少数量份额，仅本单显示</span></summary><div class="card-body">${refs.map(r => `<p>${tag(r.label)} ${esc(r.id)} · 明细 ${esc(r.lineId)}</p><p class="muted">${esc(r.detail)}</p>`).join('')}<p class="muted">记录就地保留，不另设操作流程；核清数量后才可纳入计划。</p></div></details>` : ''
  return `${demand}${sources}${bomCard}${references}`
}

function renderGlobal() {
  const readiness = view === 'readiness'
  const title = readiness ? '库存备货' : '出货管理'
  const body = readiness ? table(['订单 / 客户', '商品 / 客户货号', '剩余待发', '本行预留', '公共可用', '尚待备货', '操作'], state.orders.filter(D.editable).flatMap(o => o.lines.map(line => {
    const n = D.lineNumbers(state, line)
    return `<tr><td>${btn(o.id, 'open-order', o.id)}${sub(o.customer)}</td><td>${product(line)}</td><td>${n.remaining} ${D.products[line.product].unit}</td><td>${line.reserved}</td><td>${D.balance(state, line.product).free}</td><td class="amber">${n.gap}</td><td>${btn('预留库存', 'reserve', line.id, 'text', !n.gap)}${line.reserved ? `<br>${btn('取消预留', 'release', line.id)}` : ''}</td></tr>`
  }))) : shipmentTable(state.shipments)
  return `<header class="heading"><div class="breadcrumb">生产 / ${title}</div><div class="title-row"><h1>${title}</h1>${!readiness ? btn('＋ 新建出货单', 'new-shipment', orderId, 'primary', !D.editable(order())) : ''}</div></header><div class="alert">${readiness ? '跨订单集中备货。这里与订单详情使用同一份明细预留；预留不改变实物库存。' : '跨订单查看出货凭据。订单内创建的出货单同步出现在这里，不需要重复录入。'}</div>${card(readiness ? '订单待发明细' : '出货记录', body)}${btn('← 返回当前订单', 'navigate', 'order')}`
}

function toast(text) {
  const el = document.querySelector('#toast')
  el.textContent = text
  el.classList.add('visible')
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => el.classList.remove('visible'), 3200)
}

function showModal(title, body, kind = '', buttons = '', wide = false) {
  if (!modal.open) {
    const el = document.activeElement
    returnFocus = el?.dataset.action ? { action: el.dataset.action, id: el.dataset.id || '' } : null
  }
  modal.className = wide ? 'wide' : ''
  modal.innerHTML = `<form id="demo-form" data-kind="${kind}"><div class="dialog-head"><h2 id="dialog-title">${esc(title)}</h2><button type="button" data-action="close" aria-label="关闭弹窗">×</button></div><div class="modal-error alert error" role="alert"></div><div class="dialog-body">${body}</div><div class="dialog-footer">${buttons || '<button type="button" data-action="close">关闭</button>'}</div></form>`
  if (!modal.open) modal.showModal()
  else modal.querySelector('input:not([disabled]), select:not([disabled]), button')?.focus()
}

function closeModal(refresh = false) {
  modal.close()
  if (refresh) render()
}
modal.addEventListener('close', () => {
  if (returnFocus) [...app.querySelectorAll('[data-action]')].find(el => el.dataset.action === returnFocus.action && (el.dataset.id || '') === returnFocus.id)?.focus()
})
modal.addEventListener('click', event => { if (event.target === modal) closeModal() })

function getLine(id) {
  for (const o of state.orders) {
    const line = o.lines.find(l => l.id === id)
    if (line) return { o, line }
  }
  throw new Error('明细不存在')
}

function lineDialog(id = '') {
  const o = order(), line = o.lines.find(l => l.id === id)
  context = { id }
  const locked = line && D.lineProtected(state, line)
  showModal(line ? '编辑商品明细' : '添加商品', `${line ? `<div class="alert">明细 ${esc(line.id)} 的身份保持不变。${locked ? '已有业务记录，不能替换商品或直接删除。' : '未执行的明细可以修改商品或移除。'}</div>` : '<p class="section-note">同款也新增独立行，不自动合并客户货号。</p>'}<div class="form-grid">${select('商品', 'product', Object.entries(D.products).map(([key, p]) => [key, `${p.id} · ${p.name}`]), line?.product || 'necklace', locked ? 'disabled' : '')}${field('客户货号', 'code', line?.code || '', 'text', 'maxlength="80"')}${field('订购数量', 'qty', line?.qty || '', 'number', 'required min="1" max="1000000" step="1"')}${field('单价（元）', 'price', line?.price ?? '', 'number', 'required min="0" max="1000000" step="0.01"')}</div>`, 'line', `${line ? btn('删除此明细', 'remove-line', id, 'text danger', locked) : ''}${footer('保存明细')}`)
}

function arrangeDialog(id) {
  const { o, line } = getLine(id)
  orderId = o.id
  context = { id }
  const open = Math.max(0, line.qty - line.shipped - D.lineNumbers(state, line).planned)
  showModal('为此明细安排手工制作', `<div class="alert">${esc(o.id)} · ${esc(line.code)} · 明细 ${esc(line.id)}<br>只新增制作计划，不发料、不预留、不入库、不计客户出货。</div>${product(line)}${field('手工商家', 'supplier', '', 'text', 'required maxlength="80" list="supplier-list"')}<datalist id="supplier-list"><option value="青禾手作"><option value="拾光工坊"></datalist><div class="form-grid">${field(`整条产出计划（${D.products[line.product].unit}）`, 'planned', '', 'number', 'required min="1" step="1"')}${field(`安排给本行（${D.products[line.product].unit}）`, 'qty', '', 'number', `required min="1" max="${open}" step="1"`)}</div><p class="section-note">本行尚未安排 ${open} ${D.products[line.product].unit}。多做的部分保留为公共未分配计划，不是现货。制作物料见「配件备料与 BOM」。</p>${select('制作单处理方式', 'target', [['new', '新建独立手工单（默认）']], 'new')}<p class="section-note">输入商家后，可明确选择追加到该商家的待发出单。追加只新增产出行，不合并或改写原明细；不按同商家、同一天自动合单。</p>`, 'arrange', footer('保存制作安排'))
}

function candidates(lineId = '') {
  const o = order()
  const matches = state.tasks.filter(t => o.lines.some(l => l.product === t.product && (!lineId || l.id === lineId)))
  showModal('选择已有生产任务', `<p class="section-note">先选择任务，再明确本单每行的数量。其他订单份额不在这里修改。</p>${table(['加工单', '商家 / 目标商品', '整条计划', '未分配', '操作'], matches.map(t => `<tr><td>${esc(D.taskLabel(t))}${t.id !== D.taskLabel(t) ? sub(`独立产出 ${t.id}`) : ''}</td><td>${esc(t.supplier)}${sub(D.products[t.product].name)}</td><td>${t.qty}</td><td>${t.qty - Object.values(t.allocations).reduce((a, b) => a + b, 0)}</td><td>${btn('分配给本单', 'allocate', t.id)}</td></tr>`))}`, '', '', true)
}

function allocationDialog(id) {
  const task = state.tasks.find(t => t.id === id), o = order()
  context = { id }
  const ownIds = o.lines.map(l => l.id)
  const other = Object.entries(task.allocations).filter(([lineId]) => !ownIds.includes(lineId)).reduce((n, [, qty]) => n + qty, 0)
  showModal('调整本单生产分配', `<div class="alert">${esc(D.taskLabel(task))} · ${esc(task.supplier)}<br>整条计划 ${task.qty}，其他订单已安排 ${other}；本单不能覆盖其他订单的份额。</div>${o.lines.filter(l => l.product === task.product).map(l => field(`${l.code || D.products[l.product].name} · 明细 ${l.id}`, `allocation-${l.id}`, task.allocations[l.id] || 0, 'number', 'required min="0" step="1"')).join('')}<p class="section-note">未分配部分是公共制作计划，不是已入库现货。</p>`, 'allocation', footer('保存本单分配'))
}

function sourceDialog(id) {
  const n = D.materialNeeds(state, orderId).find(item => item.id === id)
  if (!n) throw new Error('备料需求不存在')
  context = { id }
  const tasks = state.materialTasks.filter(t => t.material === n.material)
  showModal('调整配件备料来源', `<div class="alert">${esc(D.taskLabel(n.task))} · ${esc(n.line.code)}<br>${esc(D.materials[n.material].name)}：本次需求 ${n.required} ${D.materials[n.material].unit}，已发料 ${n.source.issued}。</div>${field('从现货安排', 'stock', n.source.stock, 'number', `required min="0" max="${D.materialAvailability(state, n.material, id)}" step="1"`)}<p class="section-note">可安排公共配件 ${D.materialAvailability(state, n.material, id)}；不会占用其他订单已安排的材料。</p><h3>从电镀计划安排</h3>${tasks.map(t => field(`${t.id} · ${t.supplier} · 尚可安排 ${t.qty - t.received - t.loss - D.materialPlatingUsed(state, t.id, id)}`, `plating-${t.id}`, n.source.plating[t.id] || 0, 'number', 'required min="0" step="1"')).join('')}<p class="section-note">这只是配件来源计划。电镀回收、实际发料和成品回收分别记录，不能计入客户出货。</p>`, 'sourcing', footer('保存备料来源'))
}

function shipmentEntry(id) {
  const o = D.editableOrder(state, id)
  shipping = { orderId: id, entries: [], tracking: '', note: '', id: null }
  entryDialog(o)
}

function entryDialog(o) {
  showModal('新建出货单 · 选择实际明细', `<div class="alert">${esc(o.id)} · ${esc(o.customer)}<br>不自动勾选、不预填实发数量；无需关联生产单。保存草稿不占库、不扣库。</div>${table(['选择', '商品 / 客户货号', '剩余待发', '本行预留 / 公共', '本次实发'], o.lines.map(l => `<tr><td><input type="checkbox" name="selected" value="${l.id}" aria-label="选择明细 ${l.id}" ${shipping.entries.some(e => e.lineId === l.id) ? 'checked' : ''} ${l.shipped >= l.qty ? 'disabled' : ''}></td><td>${product(l)}</td><td>${l.qty - l.shipped} ${D.products[l.product].unit}</td><td>${l.reserved} / ${D.balance(state, l.product).free}</td><td><input class="shipment-input" type="number" name="qty-${l.id}" aria-label="明细 ${l.id} 本次实发" value="${shipping.entries.find(e => e.lineId === l.id)?.qty || ''}" min="1" max="${l.qty - l.shipped}" step="1" ${shipping.entries.some(e => e.lineId === l.id) ? '' : 'disabled'}></td></tr>`))}<div class="form-grid">${field('物流信息（可选）', 'tracking', shipping.tracking, 'text', 'maxlength="200"')}${field('出货备注（可选）', 'note', shipping.note, 'text', 'maxlength="500"')}</div>`, 'shipment-entry', '<button type="button" data-action="close">取消</button><button type="submit" value="draft">保存草稿</button><button type="submit" class="primary" value="review">下一步，核对实物</button>', true)
}

function reviewDialog() {
  const o = D.currentOrder(state, shipping.orderId)
  let warning = ''
  try { D.checkShipment(state, o.id, shipping.entries, true) } catch (error) { warning = error.message }
  const rows = shipping.entries.map(e => {
    const l = o.lines.find(l => l.id === e.lineId)
    return `<tr><td>${product(l)}</td><td><strong>${e.qty} ${D.products[l.product].unit}</strong></td><td>${l.reserved}</td><td>${D.balance(state, l.product).free}</td></tr>`
  })
  showModal(shipping.id ? `核对出货草稿 ${shipping.id}` : '新建出货单 · 核对并确认', `<div class="alert">${esc(o.id)} · ${esc(o.customer)}<br>确认时优先消耗所选明细的预留，其余使用公共现货，不挪用其他明细或订单的预留。</div><div class="review-lines">${table(['实际出货商品', '本次实发', '本行预留', '公共可用'], rows)}</div><div class="alert ${warning ? 'warning' : ''}">${warning ? esc(warning) : '当前数量与库存校验通过，最终确认时会再次校验。'}</div><p class="section-note">物流：${esc(shipping.tracking || '未填写')}<br>备注：${esc(shipping.note || '无')}</p><div class="actions">${btn('登记真实入库后返回', 'inbound')}${shipping.id ? btn('作废此草稿', 'void-shipment', shipping.id, 'text danger') : ''}</div><p class="section-note">仅用于确有实物但尚未入账的情况，不按缺口自动造库存。</p><label class="check-label"><input type="checkbox" name="actual" ${warning ? 'disabled' : ''}>我已核对实际货物与本次数量，确认将扣减库存并计入订单出货。</label>`, 'shipment-review', `${!shipping.id ? btn('返回修改', 'shipment-back', '', '') : ''}<button type="button" data-action="save-draft">${shipping.id ? '保留草稿并关闭' : '保存草稿'}</button><button type="submit" class="primary" id="confirm-shipment" disabled>确认实际出货</button>`, true)
}

function saveShippingDraft() {
  if (!shipping.id) shipping.id = D.draftShipment(state, { orderId: shipping.orderId, lines: shipping.entries, tracking: shipping.tracking, note: shipping.note }).id
  return shipping.id
}

function showShipment(id) {
  const s = state.shipments.find(item => item.id === id)
  if (!s) throw new Error('出货单不存在')
  if (s.status === 'draft') {
    shipping = { orderId: s.orderId, entries: s.lines.map(e => ({ ...e })), id: s.id, note: s.note, tracking: s.tracking }
    reviewDialog()
    return
  }
  const o = D.currentOrder(state, s.orderId)
  showModal(`出货单 ${s.id}`, `<div class="alert">${s.status === 'confirmed' ? '已确认出货，已扣减库存；不能通过修改订单状态回库。' : '草稿已作废，没有库存变动。'}</div>${table(['商品明细', '实发数量'], s.lines.map(e => { const l = o.lines.find(l => l.id === e.lineId); return `<tr><td>${product(l)}</td><td>${e.qty} ${D.products[l.product].unit}</td></tr>` }))}<p>物流：${esc(s.tracking || '未填写')}<br>备注：${esc(s.note || '无')}</p>`, '', '', true)
}

function navigate() {
  if (modal.open) modal.close()
  const parts = location.hash.slice(1).split('/')
  view = ['readiness', 'shipments'].includes(parts[0]) ? parts[0] : 'order'
  if (view === 'order') {
    orderId = state.orders.some(o => o.id === parts[1]) ? parts[1] : 'OR-1042'
    tab = parts[2] === 'production' ? 'production' : 'details'
  }
  document.body.classList.remove('menu-open')
  render()
}
function go(target = view, id = orderId, section = tab) {
  const hash = target === 'order' ? `#order/${id}/${section}` : `#${target}`
  if (location.hash === hash) navigate()
  else location.hash = hash
}
window.addEventListener('hashchange', navigate)

document.addEventListener('click', event => {
  const el = event.target.closest('[data-action]')
  if (!el || el.disabled) return
  const { action, id } = el.dataset
  try {
    switch (action) {
      case 'menu': document.body.classList.toggle('menu-open'); break
      case 'close': closeModal(); break
      case 'reset':
        showModal('重置演示数据', '<p>仅恢复本 Demo 的虚构数据，不影响真实系统。刷新页面也会恢复初始状态。</p>', 'reset', footer('重置演示'))
        break
      case 'navigate': go(id); break
      case 'open-order': go('order', id, 'details'); break
      case 'tab': go('order', orderId, id); break
      case 'bom-link': bomMode = 'order'; go('order', orderId, 'production'); break
      case 'bom-mode': bomMode = id; render(); break
      case 'edit-info':
        showModal('编辑订单资料', `<div class="form-grid">${field('客户名', 'customer', order().customer, 'text', 'required maxlength="80"')}${field('创建日期', 'date', order().date, 'date', 'required')}${field('交货日期', 'due', order().due, 'date', 'required')}</div>`, 'info', footer('保存资料'))
        break
      case 'requirements': {
        const r = order().requirements
        showModal('编辑订单要求', `<label class="check-label"><input type="checkbox" name="barcode" ${r.barcode ? 'checked' : ''}>需要贴条码</label>${textarea('条码文字与要求', 'barcodeText', r.barcodeText)}${textarea('唛头要求', 'shippingMark', r.shippingMark)}${textarea('订单备注', 'note', r.note)}<p class="section-note">参考图在订单要求中查看；此原型不上传真实文件。</p>`, 'requirements', footer('保存要求'))
        break
      }
      case 'reference-image': showModal('包装参考图 · 虚构示例', '<img class="bom-image" src="../assets/necklace-structure.svg" alt="珍珠项链结构与包装参考示意图"><p class="section-note">附件就地放在订单要求中，不需要跳转到独立资料模块。</p>'); break
      case 'edit-line': lineDialog(id); break
      case 'add-line': lineDialog(); break
      case 'remove-line': D.removeLine(state, orderId, id); closeModal(true); toast('未执行明细已移除'); break
      case 'packaging': showModal('编辑包装费', field('本单包装费（元）', 'packaging', order().packaging, 'number', 'required min="0" max="1000000" step="0.01"'), 'packaging', footer('保存包装费')); break
      case 'reserve': case 'release': {
        const { o, line } = getLine(id), release = action === 'release'
        context = { id, release }
        showModal(release ? '取消预留' : '预留库存', `<div class="alert">${esc(o.id)} · ${esc(line.code)}<br>${release ? '只释放待发预留，恢复公共可用量。不是退货，不改变实物库存。' : '只为当前明细留货，不代表已出货，也不改变实物总量。'}</div>${product(line)}<p>剩余待发 ${line.qty - line.shipped} · 本行预留 ${line.reserved} · 公共可用 ${D.balance(state, line.product).free}</p>${field(release ? '本次取消数量' : '本次预留数量', 'qty', '', 'number', 'required min="1" step="1"')}`, 'reservation', footer(release ? '确认取消预留' : '确认预留'))
        break
      }
      case 'arrange': arrangeDialog(id); break
      case 'candidates': candidates(); break
      case 'plating-candidates': candidates(id); break
      case 'allocate': allocationDialog(id); break
      case 'source': sourceDialog(id); break
      case 'task': {
        const t = state.tasks.find(item => item.id === id)
        showModal(`加工单 ${D.taskLabel(t)}`, `<div class="alert">${esc(t.supplier)} · ${esc(D.taskStage(t))}<br>产出 ${esc(t.id)} · 整条计划 ${t.qty} · 实收 ${t.received} · 损耗 ${t.loss} ${D.products[t.product].unit}</div><h3>订单用途</h3>${table(['订单 / 客户货号', '计划份额'], Object.entries(t.allocations).map(([lineId, qty]) => { const { o, line } = getLine(lineId); return `<tr><td>${esc(o.id)} · ${esc(o.customer)}${sub(line.code)}</td><td>${qty}</td></tr>` }))}<p class="section-note">正式功能会在原加工单中保留发出、实收、损耗、付款等操作；此整合原型仅预览任务与订单的追溯，不模拟加工单执行。</p>`, '', '', true)
        break
      }
      case 'verify': showModal('核对本单历史实发', '<div class="alert warning">仅在已有记录确实无法确认实发数量的存量订单中出现。不能根据“已生产”或旧订单状态补造出货。</div><label class="check-label"><input name="verified" type="checkbox" required>我已核对，此订单确无历史实际出货，可以从 0 开始记录。</label><p class="section-note">如果已有历史实发或无法确认，请取消并继续核对原始凭据，不要勾选。此原型不提供无凭据补记。</p>', 'verify', footer('确认核对结果')); break
      case 'new-shipment': shipmentEntry(id); break
      case 'shipment': showShipment(id); break
      case 'shipment-back': entryDialog(D.currentOrder(state, shipping.orderId)); break
      case 'save-draft': saveShippingDraft(); closeModal(true); toast('草稿已保存，未占库、未扣库'); break
      case 'void-shipment': showModal('作废出货草稿', `<p>确认作废 ${esc(id)}？草稿没有库存变动。已确认出货不能用此方式回库。</p>`, 'void', footer('确认作废')); context = { id }; break
      case 'inbound': showModal('登记真实入库 · 完成后返回出货核对', `<div class="alert warning">只登记确有实物的入库。本次不预填缺口，不会自动预留或出货。</div>${select('实际入库商品', 'product', Object.entries(D.products).map(([key, p]) => [key, p.name]), '')}${field('真实入库数量', 'qty', '', 'number', 'required min="1" step="1"')}${select('真实来源', 'reason', [['历史现货补录', '历史现货补录'], ['外购成品', '外购成品'], ['盘点补录', '盘点补录']], '外购成品')}${textarea('来源说明（必填）', 'note', '')}`, 'inbound', `${btn('返回出货核对', 'return-review', '', '')}<button type="submit" class="primary">登记入库并返回核对</button>`); break
      case 'return-review': reviewDialog(); break
    }
  } catch (error) {
    if (modal.open) modal.querySelector('.modal-error').textContent = error.message
    else toast(error.message)
  }
})

document.addEventListener('change', event => {
  const el = event.target
  if (el.id === 'order-picker') { bomMode = 'task'; go('order', el.value, tab) }
  if (el.name === 'selected') {
    const input = modal.querySelector(`[name="qty-${el.value}"]`)
    input.disabled = !el.checked
    input.required = el.checked
    if (el.checked) input.focus()
  }
  if (el.name === 'actual') modal.querySelector('#confirm-shipment').disabled = !el.checked
})

document.addEventListener('input', event => {
  if (event.target.name !== 'supplier' || modal.querySelector('form')?.dataset.kind !== 'arrange') return
  const matches = state.tasks.filter(t => t.type === 'handcraft' && t.status === 'pending' && t.supplier === event.target.value.trim())
    .filter((t, index, items) => items.findIndex(item => D.taskLabel(item) === D.taskLabel(t)) === index)
  modal.querySelector('[name="target"]').innerHTML = `<option value="new">新建独立手工单（默认）</option>${matches.map(t => `<option value="${t.id}">明确追加到 ${D.taskLabel(t)} · ${esc(t.supplier)}</option>`).join('')}`
})

document.addEventListener('keydown', event => {
  if (!event.target.matches('[role="tab"]') || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const next = event.key === 'Home' ? 'details' : event.key === 'End' ? 'production' : tab === 'details' ? 'production' : 'details'
  go('order', orderId, next)
  // hash navigation is asynchronous; focus after the rendered tab has changed.
  requestAnimationFrame(() => document.querySelector(`#tab-${next}`)?.focus())
})

modal.addEventListener('submit', event => {
  event.preventDefault()
  const form = event.target, values = Object.fromEntries(new FormData(form)), kind = form.dataset.kind
  modal.querySelector('.modal-error').textContent = ''
  try {
    switch (kind) {
      case 'reset': state = D.createState(); orderId = 'OR-1042'; tab = 'details'; view = 'order'; bomMode = 'task'; shipping = null; closeModal(); go('order', orderId, tab); toast('已恢复虚构示例'); return
      case 'info': D.editInfo(state, orderId, values); break
      case 'requirements': D.editRequirements(state, orderId, { ...values, barcode: form.elements.barcode.checked }); break
      case 'line': context.id ? D.editLine(state, orderId, context.id, values) : D.addLine(state, orderId, values); break
      case 'packaging': D.editPackaging(state, orderId, values.packaging); break
      case 'reservation': D.reserve(state, context.id, values.qty, context.release); break
      case 'arrange': D.arrange(state, { lineId: context.id, qty: values.qty, planned: values.planned, supplier: values.supplier.trim(), targetId: values.target }); break
      case 'allocation': D.allocate(state, context.id, orderId, Object.fromEntries(Object.entries(values).filter(([key]) => key.startsWith('allocation-')).map(([key, value]) => [key.slice(11), value]))); break
      case 'sourcing': D.sourceMaterial(state, orderId, context.id, { stock: values.stock, plating: Object.fromEntries(Object.entries(values).filter(([key]) => key.startsWith('plating-')).map(([key, value]) => [key.slice(8), value])) }); break
      case 'verify': D.verifyNoShipment(state, orderId, form.elements.verified.checked); break
      case 'shipment-entry': {
        const ids = new FormData(form).getAll('selected')
        const entries = ids.map(lineId => ({ lineId, qty: Number(values[`qty-${lineId}`]) }))
        D.checkShipment(state, shipping.orderId, entries)
        Object.assign(shipping, { entries, tracking: values.tracking, note: values.note })
        if (event.submitter?.value === 'draft') { saveShippingDraft(); closeModal(true); toast('草稿已保存，未占库、未扣库') }
        else reviewDialog()
        return
      }
      case 'shipment-review':
        if (!form.elements.actual.checked) throw new Error('请先核对实际货物并勾选确认')
        D.checkShipment(state, shipping.orderId, shipping.entries, true)
        D.confirm(state, saveShippingDraft())
        closeModal(true); toast('实际出货已确认，库存与订单进度已更新'); return
      case 'void': D.voidDraft(state, context.id); break
      case 'inbound': D.receiveStock(state, values); reviewDialog(); render(); toast('真实入库已登记，请重新核对本次出货'); return
      default: return
    }
    closeModal(true)
    toast('已保存到本次演示，真实数据不受影响')
  } catch (error) { modal.querySelector('.modal-error').textContent = error.message }
})

navigate()
