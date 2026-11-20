import { createState, products, materials, materialNeeds, materialAvailability, materialPlatingUsed, saveMaterialSourcing, locateLine, balance, lineNumbers, orderStage, taskStage, reserveLine, releaseLine, saveAllocation, saveOrderAllocation, arrangeHandcraft, receiveStock, receiveTask, checkShipment, saveDraft, confirmShipment, voidDraft } from './domain.js'

let state = createState()
let filter = 'all'
let search = ''
let sourceOnly = false
let wizard = null
let dialogReturn = null
let toastTimer
const app = document.querySelector('#app')
const modal = document.querySelector('#modal')
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]))
const fulfillmentPercent = order => Math.round(order.lines.reduce((total, line) => total + line.shipped / line.qty, 0) / order.lines.length * 100)
const shipmentCompletion = order => `已全部发货 ${order.lines.filter(line => line.shipped >= line.qty).length} / ${order.lines.length} 项`
const stockByUnit = order => [...new Set(order.lines.map(line => products[line.product].unit))].map(unit => `${order.lines.filter(line => products[line.product].unit === unit).reduce((n, line) => n + line.reserved, 0)} ${unit}`).join(' / ')
const icons = {
  orders: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V2h6v2M9 10h6M9 14h6M9 18h3"/>',
  production: '<path d="M3 21V9l6 3V7l6 3V3h5v18H3zM7 17h1m4 0h1m4 0h1"/>',
  stock: '<path d="M3 7l9-4 9 4-9 4-9-4zm0 0v10l9 4 9-4V7M12 11v10M7 5l10 5"/>',
  ship: '<path d="M3 5h11v13H3zM14 9h4l3 4v5h-7M3 10h7"/><circle cx="7" cy="19" r="2"/><circle cx="18" cy="19" r="2"/>',
  handcraft: '<path d="M7 12V5a2 2 0 014 0v6-8a2 2 0 014 0v8-5a2 2 0 014 0v9c0 4-3 7-7 7-3 0-5-2-7-5l-2-4a2 2 0 013-2l3 3"/>',
  plating: '<path d="M8 3h8M9 3v7l-5 8a2 2 0 002 3h12a2 2 0 002-3l-5-8V3M7 15h10"/>',
  impact: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><path d="M14 6h4v4M6 14v4h4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>', search: '<circle cx="10" cy="10" r="6"/><path d="M15 15l6 6"/>',
  arrow: '<path d="M5 12h14m-6-6l6 6-6 6"/>', check: '<path d="M5 12l4 4L19 6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>', close: '<path d="M6 6l12 12M6 18L18 6"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>', clock: '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
}
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.info}</svg>`
const button = (label, action, data = '', cls = '', symbol = '') => `<button type="button" class="btn ${cls}" data-action="${action}" data-id="${esc(data)}">${symbol ? icon(symbol) : ''}${label}</button>`
const textButton = (label, action, id = '') => button(label, action, id, 'text-btn')
const link = (label, route, cls = '') => `<a class="${cls}" href="#/${route}">${label}</a>`
const tag = (text, color = '') => `<span class="tag ${color}"><i class="dot"></i>${esc(text)}</span>`
const notice = (text, color = '') => `<div class="notice ${color}">${icon('info')}<div>${text}</div></div>`
const product = (key, extra = '') => { const p = products[key]; return `<div class="product"><img src="${p.image}" alt="${esc(p.name)}"><div><strong>${esc(p.name)}</strong><small>${p.id} · ${esc(extra || p.spec)}</small></div></div>` }
const table = (headers, rows, cls = '') => `<div class="table-wrap"><table class="${cls}"><thead><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr></thead><tbody>${rows || `<tr><td colspan="${headers.length}"><div class="empty">没有符合条件的记录</div></td></tr>`}</tbody></table></div>`
const card = (title, subtitle, body, action = '', footer = '') => `<section class="card"><div class="card-header"><div><h2>${title}</h2>${subtitle ? `<p>${subtitle}</p>` : ''}</div>${action}</div>${body}${footer ? `<div class="card-footer">${footer}</div>` : ''}</section>`
const stat = (label, value, unit, foot, symbol, accent = false) => `<div class="stat ${accent ? 'accent' : ''}"><div class="stat-label">${label}${icon(symbol)}</div><div class="stat-value">${value}<span>${unit}</span></div><div class="stat-foot">${foot}</div></div>`
const heading = (title, desc, actions = '', section = '订单履约') => `<div class="breadcrumb">工作台 / ${section}</div><header class="page-head"><div><h1>${title}</h1><p>${desc}</p></div><div class="head-actions">${actions}</div></header>`
const routeParts = () => location.hash.replace(/^#\/?/, '').split('/').filter(Boolean)
const activeOrders = () => state.orders.filter(o => !o.legacy)
const eligibleLines = key => activeOrders().flatMap(order => order.lines.filter(line => !key || line.product === key).map(line => ({ order, line })))
const orderOptions = selected => activeOrders().map(o => `<option value="${o.id}" ${o.id === selected ? 'selected' : ''}>${o.id} · ${o.customer}</option>`).join('')
const tokens = task => `<div class="allocation-list">${Object.entries(task.allocations).map(([id, qty]) => { const { order } = locateLine(state, id); return link(`${order.id} <b>${qty}</b>`, `orders/${order.id}`, 'allocation-token') }).join('')}<span class="allocation-token public">公共备库存 ${task.qty - Object.values(task.allocations).reduce((a, b) => a + b, 0)}</span></div>`
const taskLink = (task, source = '') => `${task.type === 'handcraft' ? 'handcraft' : 'plating'}/${task.id}${source ? `/${source}` : ''}`
const shipmentStatus = s => tag(({ draft: '草稿', confirmed: '已出货', void: '已作废' })[s.status], s.status === 'confirmed' ? 'green' : s.status === 'draft' ? 'amber' : '')
const tabs = items => {
  const modules = new Set(items.map(([, route]) => route.split('/')[0]))
  if (modules.size > 1) {
    return `<nav class="module-shortcuts" aria-label="相关模块快捷入口"><span class="muted">相关模块：</span>${items.filter(([, , active]) => !active).map(([label, route, , symbol]) => link(`${icon(symbol)}${label} ↗`, route, 'btn small')).join('')}</nav>`
  }
  return `<nav class="page-tabs" aria-label="订单内页面">${items.map(([label, route, active, symbol]) => `<a href="#/${route}" class="page-tab ${active ? 'active' : ''}" ${active ? 'aria-current="page"' : ''}>${icon(symbol)}${label}</a>`).join('')}</nav>`
}
const orderTabs = (order, active) => tabs([
  ['需求与履约', `orders/${order.id}`, active === 'detail', 'orders'],
  ['本单生产需求分配', `orders/${order.id}/production`, active === 'production', 'production'],
])

function render() {
  const [page = 'orders', id, source] = routeParts()
  const navItems = [['orders', '客户订单'], ['production', '生产分配'], ['stock', '库存备货'], ['ship', '出货管理'], ['handcraft', '手工管理'], ['plating', '电镀管理'], ['impact', '本次改动总览']]
  let content
  if (page === 'orders') content = id ? source === 'production' ? orderProductionPage(id) : orderDetail(id) : ordersPage()
  else if (page === 'production') content = productionPage()
  else if (page === 'stock') content = stockPage()
  else if (page === 'ship') content = id ? shipmentDetail(id) : shipmentsPage()
  else if (page === 'handcraft' || page === 'plating') content = id ? taskDetail(id, source) : taskList(page)
  else if (page === 'impact') content = impactPage()
  else content = heading('页面未找到', '请选择左侧的 Demo 页面。')
  if (page === 'plating' && !id) content += materialPlatingList()
  if (page === 'handcraft' && id) content += activeOrders().filter(order => !source || order.id === source)
    .filter(order => materialNeeds(state, order.id).some(n => n.task.id === id)).map(order => materialNeedsCard(order, id)).join('')
  app.innerHTML = `<button class="menu-scrim" data-action="menu-close" aria-label="关闭导航"></button><aside class="sidebar"><a class="brand" href="#/orders"><div class="brand-mark">a</div><div><div class="brand-name">ALLEN</div><div class="brand-sub">JEWELRY WORKSPACE</div></div></a><div class="nav-group-label">BUSINESS WORKSPACE</div><nav aria-label="主要导航">${navItems.map(([key, label], i) => `${i === 4 ? '<div class="nav-group-label">PRODUCTION</div>' : i === 6 ? '<div class="nav-group-label">PROTOTYPE</div>' : ''}${link(`${icon(key)}<span>${label}</span>${key === 'ship' ? `<small class="nav-count">${state.shipments.filter(s => s.status === 'draft').length}</small>` : ''}`, key, `nav-link ${page === key ? 'active' : ''}`)}`).join('')}</nav><div class="sidebar-foot"><span class="prototype-badge"><i class="tiny-dot"></i>INTERACTIVE DEMO · V1</span><p>虚构数据 · 与正式业务隔离<br>刷新或重置将恢复初始场景</p></div></aside><div class="shell"><header class="topbar"><div class="top-context"><button class="mobile-menu" data-action="menu" aria-label="打开导航">${icon('menu')}</button><span>ALLEN 工作台</span><span>/</span><b>${navItems.find(i => i[0] === page)?.[1] || '交互原型'}</b></div><div class="top-actions"><span class="offline"><i class="tiny-dot"></i>本地模拟，不连接业务接口</span><button class="top-reset" data-action="reset">重置演示</button><div class="avatar" aria-label="Demo 用户">DE</div></div></header><main id="main" class="main" tabindex="-1">${content}<p class="footer-note">ALLEN · 订单履约优化原型 / 所有名称与记录均为虚构，仅用于方案评审，不代表已上线功能。</p></main></div>`
  document.title = `${navItems.find(i => i[0] === page)?.[1] || '原型'} · ALLEN Demo`
}

function ordersPage() {
  const visible = state.orders.filter(o => (filter === 'all' || (filter === 'legacy' ? o.legacy : !o.legacy && (filter === 'partial' ? orderStage(o) === '部分出货' : orderStage(o) === '待出货'))) && `${o.id} ${o.customer}`.toLowerCase().includes(search.toLowerCase()))
  const rows = visible.map(o => {
    const percent = fulfillmentPercent(o)
    return `<tr><td>${link(o.id, `orders/${o.id}`, 'mono strong')}<div class="subtext">${o.date}</div></td><td><div class="customer"><span class="customer-icon">${o.initials}</span><div>${o.customer}<small>${o.lines.length} 条产品明细</small></div></div></td><td>${tag(orderStage(o), o.legacy ? 'legacy' : percent ? 'amber' : 'blue')}</td><td>${o.legacy ? '<span class="muted">未核实，不补记</span>' : `<div class="progress-cell"><div class="progress-label"><span>${shipmentCompletion(o)}</span><span>${percent}%</span></div><meter min="0" max="100" value="${percent}" aria-label="${o.id} 各明细出货比例平均值"></meter><div class="subtext">部分发货的商品不计入已完成项</div></div>`}</td><td>${o.legacy ? '—' : `${stockByUnit(o)}<div class="subtext">待发预留 · 不混加单位</div>`}</td><td>${o.due}<div class="subtext">${o.legacy ? '旧流程已结束' : '按明细管理分批交付'}</div></td><td>${link('查看订单 →', `orders/${o.id}`)}</td></tr>`
  }).join('')
  const filters = `<div class="filter-bar"><div class="segmented">${[['all', '全部'], ['pending', '待出货'], ['partial', '部分出货'], ['legacy', '历史单据']].map(([key, label]) => `<button data-action="filter" data-id="${key}" class="${filter === key ? 'active' : ''}">${label}</button>`).join('')}</div><label class="search">${icon('search')}<input id="order-search" placeholder="搜索订单号 / 客户" value="${esc(search)}" aria-label="搜索订单号或客户"></label></div>`
  const workflow = `<div class="workflow">${[['客户需求', '明确订单与明细'], ['库存备货', '现货可直接出货'], ['确认出货', '实际扣库并计进度']].map(([title, desc], i) => `${i ? '<i class="workflow-divider"></i>' : ''}<div class="workflow-step ${i === 1 ? 'active' : ''}"><b>${i + 1}</b><div><strong>${title}</strong><small>${desc}</small></div></div>`).join('')}</div>`
  return heading('客户订单', '从客户需求到实际交付，每一步都有清晰的数量依据。', button('新建出货单', 'ship-new', '', 'primary', 'plus'))
    + `<div class="stats">${stat('履约中订单', activeOrders().filter(o => orderStage(o) !== '已完成').length, '单', '生产与交付进度独立呈现', 'orders', true)}${stat('部分出货', activeOrders().filter(o => orderStage(o) === '部分出货').length, '单', '允许先发已有现货', 'ship')}${stat('待确认草稿', state.shipments.filter(s => s.status === 'draft').length, '单', '草稿不占库、不扣库', 'clock')}${stat('历史只读订单', 1, '单', '不自动补出货或库存流水', 'impact')}</div>`
    + card('订单列表', '库存备齐 ≠ 加工结清 ≠ 订单完成', filters + table(['订单编号', '客户 / 明细', '交付状态', '出货进度', '库存备货', '约定交期', '操作'], rows), '', `<span>共 ${visible.length} 单 · 进度为各明细出货比例平均值</span><span>全部明细足量出货后，订单自动完成</span>`)
    + `<div class="two-col">${card('履约路径', '关联加工单是可选追溯，不是出货门槛', workflow + `<div class="card-body"><div class="help-grid"><div class="help-card">${icon('stock')}<h3>没有加工关联，也能发货</h3><p>选择订单明细，填写本次实发；有公共现货即可校验出库，不需要补建电镀或手工单。</p>${textButton('试试手动出货 →', 'ship-new', 'OR-1042')}</div><div class="help-card">${icon('production')}<h3>生产安排，不等于库存占用</h3><p>一条加工明细可分给多个订单；实收进入公共库存，按真实备货再分配给客户。</p>${link('查看生产分配 →', 'production')}</div></div></div>`)}${eventsCard()}</div>`
}

function eventsCard() { return card('最近动态', '本次操作只保留在当前页面内存', `<div class="card-body">${state.events.slice(0, 4).map(e => `<div class="event"><strong>${esc(e.title)}</strong><p>${esc(e.detail)}</p><small>${esc(e.time)}</small></div>`).join('')}</div>`) }

function orderDetail(id) {
  const o = state.orders.find(o => o.id === id)
  if (!o) return heading('订单不存在', '请返回订单列表。')
  const rows = o.lines.map(line => {
    const n = lineNumbers(state, line), tasks = state.tasks.filter(t => t.allocations[line.id])
    const productionAction = line.product !== 'chain' ? textButton('安排手工', 'arrange', line.id) : link('分配电镀需求', `orders/${o.id}/production`)
    return `<tr><td>${product(line.product, line.code)}</td><td>${line.qty}</td><td>${o.legacy ? '待核实' : n.planned}<div class="subtext">历史安排，不与现货相加</div></td><td>${o.legacy ? '—' : line.reserved}</td><td>${o.legacy ? '未核实' : line.shipped}</td><td>${o.legacy ? '—' : `<b class="${n.gap ? 'amber' : 'green'}">${n.gap}</b>`}</td><td>${tasks.map(t => `<div>${link(t.id, taskLink(t, o.id), 'mono')} ${tag(taskStage(t), t.status === 'pending' ? 'blue' : 'green')}<div class="subtext">本行安排 ${t.allocations[line.id]} · 实收 ${t.received} / 损耗 ${t.loss}（整条加工明细）</div></div>`).join('') || '<span class="muted">无加工来源 · 可用现货交付</span>'}</td><td>${o.legacy ? tag('只读', 'legacy') : `${textButton('预留库存', 'reserve', line.id)}<br>${line.reserved ? textButton('取消预留', 'release', line.id) + '<br>' : ''}${productionAction}`}</td></tr>`
  }).join('')
  const tasks = state.tasks.filter(t => o.lines.some(l => t.allocations[l.id]))
  return heading(`${o.id} <span class="muted">/</span> ${o.customer}`, '客户订单详情 · 需求、生产、备货与出货分别核算。', link('返回列表', 'orders', 'btn') + (o.legacy ? '' : button('新建出货单', 'ship-new', id, 'primary', 'plus')))
    + (!o.legacy ? orderTabs(o, 'detail') : '')
    + (o.legacy ? notice('历史已完成 · 旧流程记录仅供查阅。没有可核实的逐笔出货记录，不自动补出货、不补扣库存。', 'warning') : notice('订单仅在全部明细足量出货后完成。无需关联手工 / 电镀，可直接使用已记录的公共现货。'))
    + `<div class="stats">${stat('订购明细', o.lines.length, '项', '保留客户货号与独立明细身份', 'orders')}${stat('出货进度', o.legacy ? '—' : fulfillmentPercent(o), o.legacy ? '' : '%', o.legacy ? '历史状态，不虚构出货数量' : `${shipmentCompletion(o)}<br>部分发货的商品不计入已完成项`, 'ship', true)}${stat('备货状态', o.legacy ? '只读' : o.lines.every(l => !lineNumbers(state, l).gap) ? '已备齐' : '待补齐', '', '仅核算未出货部分的预留', 'stock')}${stat('交付状态', orderStage(o), '', `约定交期 ${o.due}`, 'clock')}</div>`
    + (!o.legacy ? materialSummary(o) : '')
    + card('需求与履约明细', '尚待备货 = 订购 − 已出货 − 已预留待发；生产安排单独展示', table(['产品 / 客户货号', '订购', '生产安排', '已预留待发', '已出货', '尚待备货', '生产任务与阶段', '操作'], rows), '', `<span>${esc(o.note)}</span>`)
    + `<div class="two-col">${card('生产来源', '从本订单进入加工单，突出本单分配行；不代表批次实物追溯', table(['加工单', '商家', '本单安排', '操作'], tasks.map(t => `<tr><td>${link(t.id, taskLink(t, id), 'mono')}</td><td>${t.supplier}</td><td>${o.lines.reduce((n, l) => n + (t.allocations[l.id] || 0), 0)} ${products[t.product].unit}</td><td>${link('查看本单来源 →', taskLink(t, id))}</td></tr>`).join('')))}${card('出货记录', '只展示真实确认记录或草稿，不用加工回收代替出货', shipmentTable(state.shipments.filter(s => s.orderId === id)))}</div>`
}

function orderProductionPage(id) {
  const order = state.orders.find(order => order.id === id)
  if (!order) return heading('订单不存在', '请返回订单列表。', link('返回列表', 'orders', 'btn'))
  if (order.legacy) return orderDetail(id)
  const demandRows = order.lines.map(line => {
    const n = lineNumbers(state, line)
    return `<tr><td>${product(line.product, line.code)}</td><td>${line.qty} ${products[line.product].unit}</td><td>${line.shipped}</td><td>${n.planned}</td><td>${Math.max(0, n.remaining - n.planned)}</td><td>${line.product !== 'chain' ? textButton('安排手工', 'arrange', line.id) : '<span class="muted">在下方选择目标电镀产出</span>'}</td></tr>`
  }).join('')
  const candidates = state.tasks.filter(task => order.lines.some(line => line.product === task.product))
  const taskRows = type => candidates.filter(task => task.type === type).map(task => {
    const own = order.lines.reduce((n, line) => n + (task.allocations[line.id] || 0), 0)
    const total = Object.values(task.allocations).reduce((n, qty) => n + qty, 0)
    return `<tr><td>${link(task.id, taskLink(task, order.id), 'mono strong')}<div class="subtext">${task.supplier}</div>${tag(own ? '已关联本单' : '可选，尚未关联', own ? 'green' : '')}</td><td>${task.type === 'plating' ? `<div class="subtext mono">${esc(task.inputId)} 原色 → ${products[task.product].id} 金色</div>` : ''}${product(task.product)}</td><td>${tag(taskStage(task), task.status === 'pending' ? 'blue' : 'green')}</td><td>${task.qty} ${products[task.product].unit}<div class="subtext">实收 ${task.received} / 损耗 ${task.loss}（整条加工明细）</div></td><td><b class="green">${own}</b></td><td>${total - own}<div class="subtext">只读，不在本单中修改</div></td><td>${task.qty - total}</td><td>${textButton(own ? '调整本单分配' : '分配给本单', 'order-allocation', `${task.id}:${order.id}`)}</td></tr>`
  }).join('')
  const productionCard = (type, title, subtitle, empty) => {
    const rows = taskRows(type)
    return card(title, subtitle, rows ? table(['加工单 / 商家 / 关联', '目标产出', '阶段', '整条计划 / 实收', '本单安排', '其他订单安排', '公共备库存', '操作'], rows) : `<div class="card-body"><p class="muted">${empty}</p></div>`)
  }
  return heading(`${order.id} <span class="muted">/</span> ${order.customer}`, '本单生产需求分配 · 保留当前客户订单上下文，不切换到全局模块。', link('返回订单详情', `orders/${order.id}`, 'btn'), `${link('客户订单', 'orders')} / ${order.id}`)
    + orderTabs(order, 'production')
    + notice('这里只调整当前订单的安排数量；共享加工明细中其他订单的分配只读保留。生产计划不代表库存预留，也不要求每次出货都有生产关联。')
    + card('本单生产需求', '未安排 = 剩余待出货 − 既有生产安排（最低为零）；与现货备货缺口分开核算', table(['产品 / 客户货号', '订购', '已出货', '生产安排', '未安排', '操作'], demandRows))
    + productionCard('handcraft', '手工生产安排', '匹配本单商品的手工产出；区分已关联任务与可选任务', '暂无匹配本单商品的手工任务；饰品可从上方“安排手工”创建计划。')
    + productionCard('plating', '电镀生产安排', '本区仅展示直接作为订单商品的电镀产出；成品上游配件见下方备料区', '暂无直接匹配本单商品的电镀产出；成品上游电镀请查看下方“上游配件备料”。')
    + materialNeedsCard(order)
}

function materialSummary(order) {
  const needs = materialNeeds(state, order.id)
  const pending = needs.filter(n => n.waiting || n.review)
  const text = orderStage(order) === '已完成' ? '本单已全部发货，生产备料记录仅供追溯，不影响订单完成状态。'
    : !needs.length ? '暂无已安排手工对应的配件需求；可使用成品现货出货，不强制补建加工单。'
      : pending.length ? `${pending.length} 项配件备料需关注：${pending.map(n => `${materials[n.material].name}（${n.stage}）`).join('、')}。可能影响后续发料，请查看详情。`
        : '已安排手工对应的示例配件已备齐或已发料；不代表全部 BOM 齐套，也不代表成品已完成。'
  return card('生产备料提醒', '按已安排手工数量展开示例 BOM，与成品库存预留、出货进度分开', `<div class="card-body">${text}</div>`, link('查看配件与电镀 →', `orders/${order.id}/production`, 'btn small'))
}

function materialNeedsCard(order, taskId = '') {
  const needs = materialNeeds(state, order.id).filter(n => !taskId || n.task.id === taskId)
  const body = needs.map(n => {
    const m = materials[n.material]
    const sources = Object.entries(n.source.plating).map(([id, qty]) => {
      const task = state.materialTasks.find(t => t.id === id)
      return `<p>${link(id, `plating/${id}/${order.id}`, 'mono strong')} · ${task.supplier} ${tag(taskStage(task), 'blue')}<br>本项计划使用 <b>${qty} ${m.unit}</b> · 整批计划 ${task.qty} / 实收 ${task.received} / 损耗 ${task.loss}</p>`
    }).join('')
    return `<article class="material-need"><div class="material-need-head"><div><h3>${m.name} <span class="mono muted">${m.id}</span></h3><p>${products[n.line.product].name} · ${n.line.code} · ${link(n.task.id, taskLink(n.task, order.id), 'mono')} · 本单制作 ${n.quantity} ${products[n.line.product].unit}</p></div>${tag(n.stage, n.waiting || n.review ? 'amber' : 'green')}</div>`
      + `<dl class="material-metrics"><div><dt>BOM 配件需求</dt><dd>${n.required} ${m.unit}<small>每${products[n.line.product].unit}用 ${n.per} ${m.unit}</small></dd></div><div><dt>已安排现货</dt><dd>${n.source.stock} ${m.unit}</dd></div><div><dt>已发料</dt><dd>${n.source.issued} ${m.unit}</dd></div><div><dt>尚待备齐</dt><dd>${n.waiting} ${m.unit}<small>电镀计划不算现货</small></dd></div><div><dt>尚未安排来源</dt><dd>${n.uncovered} ${m.unit}</dd></div></dl>`
      + `<div class="material-source">${sources || `<p>${n.waiting ? '尚未关联电镀来源；可安排公共现货或明确选择同目标配件的电镀计划。' : '使用现货或已发料，无需新增电镀单。'}</p>`}</div>`
      + `<div class="material-need-foot"><span>${n.review ? '制作安排已变更，请核对原备料数量，系统不会静默转给其他订单。' : n.source.issued ? '已发料为虚构历史凭据，不会再次扣减当前配件库存。' : '只表示备料用途安排，尚未执行实际领料。'}</span>${n.task.status === 'pending' ? textButton('调整备料来源', 'material-source', `${order.id}|${n.id}`) : '<span class="muted">已发出任务，备料记录只读</span>'}</div></article>`
  }).join('')
  return card(taskId ? `${order.id} · 上游配件备料` : '上游配件备料', '仅按已安排手工数量 × 示例 BOM 用量展开；未安排制作的需求不冒充已备料', body || '<div class="card-body">暂无已安排手工对应的配件需求。可使用成品现货，无需强制补建电镀单。</div>', taskId ? link('查看本单全部备料', `orders/${order.id}/production`, 'btn small') : '')
    + notice('示例 BOM 仅包含金色扣头、金色耳钩，不代表完整物料齐套。电镀关联是已确认的计划用途，不是实物批次追溯；公共同款只是候选，不自动关联。电镀回收、材料发出和完整 BOM 齐套校验未在本 Demo 执行，配件数量不会累计为成品生产或出货数量。')
}

function materialPlatingList() {
  return card('上游配件电镀', '用于成品手工备料，不计入成品生产数量', table(['电镀单 / 商家', '原色 → 目标配件', '阶段', '整批计划 / 实收 / 损耗', '已安排用途 / 公共剩余'], state.materialTasks.map(t => `<tr><td>${link(t.id, `plating/${t.id}`, 'mono strong')}<div class="subtext">${t.supplier}</div></td><td>${materials[t.material].inputId} → ${materials[t.material].id}<div>${materials[t.material].name}</div></td><td>${tag(taskStage(t), 'blue')}</td><td>${t.qty} / ${t.received} / ${t.loss} ${materials[t.material].unit}</td><td>${materialPlatingUsed(state, t.id)} / ${Math.max(0, t.qty - t.received - t.loss - materialPlatingUsed(state, t.id))}</td></tr>`).join('')))
}

function materialTaskDetail(task, source) {
  const m = materials[task.material]
  const rows = activeOrders().flatMap(order => materialNeeds(state, order.id).filter(n => n.source.plating[task.id]).map(n => ({ order, n })))
  return heading(`${task.id} / ${task.supplier}`, `上游配件电镀 · ${m.inputId} 原色 → ${m.id} ${m.name}`, source ? link('返回本单配件备料', `orders/${source}/production`, 'btn') : link('返回电镀列表', 'plating', 'btn'), '生产管理')
    + notice('本页只读展示上游电镀计划。实际配件回收入库、材料领用仍需独立凭据；不会自动记成品回收或客户出货。')
    + `<div class="stats">${stat('整批计划', task.qty, m.unit, '不能将整批数量算给每个客户', 'production')}${stat('整批实收', task.received, m.unit, '仅为配件，不是成品', 'stock')}${stat('已安排用途', materialPlatingUsed(state, task.id), m.unit, '按手工任务与订单明细分别记录', 'orders')}${stat('任务阶段', taskStage(task), '', `确认损耗 ${task.loss} ${m.unit}`, 'clock')}</div>`
    + card('配件用途与客户来源', '高亮当前订单；其他客户数量保持独立，未安排部分为公共备库存', table(['客户订单', '成品需求 / 手工单', '本项计划使用', '配件需求 / 已安排现货', '操作'], rows.map(({ order, n }) => `<tr class="${order.id === source ? 'row-highlight' : ''}"><td>${link(order.id, `orders/${order.id}`)} · ${order.customer}</td><td>${n.line.code} · ${link(n.task.id, taskLink(n.task, order.id), 'mono')}</td><td>${n.source.plating[task.id]} ${m.unit}</td><td>${n.required} / ${n.source.stock} ${m.unit}</td><td>${link('查看本单备料 →', `orders/${order.id}/production`)}</td></tr>`).join('')))
}

function materialSourceDialog(key) {
  const [orderId, id] = key.split('|')
  const n = materialNeeds(state, orderId).find(row => row.id === id)
  if (!n || n.task.status !== 'pending') throw new Error('本项备料不可调整')
  const m = materials[n.material]
  const candidates = state.materialTasks.filter(t => t.material === n.material)
  const quantityInput = (label, name, value, help) => `<div class="field"><label for="material-${name}">${label}</label><input id="material-${name}" name="${name}" type="number" min="0" max="1000000" step="1" value="${value}"><small>${help}</small></div>`
  showDialog('调整配件备料来源', `${orderId} · ${n.task.id} · ${m.name} · 需求 ${n.required} ${m.unit}`,
    notice('只调整当前订单明细的备料计划，不入库、不发料、不改变成品库存或出货数量。未选择的同款电镀单只是候选来源；允许部分安排，其余会提示缺口。')
    + `<div class="form-grid">${quantityInput('安排公共现货', 'stock', n.source.stock, `实物 ${state.materialStock[n.material]} ${m.unit}；扣除其他备料安排后，本项最多可用 ${materialAvailability(state, n.material, id)} ${m.unit}`)}${candidates.map(t => quantityInput(`${t.id} · ${t.supplier} · ${taskStage(t)}`, t.id, n.source.plating[t.id] || 0, `其他备料已安排 ${materialPlatingUsed(state, t.id, id)} ${m.unit}；本项最多可安排 ${Math.max(0, t.qty - t.received - t.loss - materialPlatingUsed(state, t.id, id))} ${m.unit}。实收不计为待回收计划。`)).join('')}</div>`,
    `<small>填 0 可取消该来源安排；不覆盖其他订单</small><div class="actions">${button('返回', 'close')}${button('保存备料来源', 'material-source-save', key, 'primary')}</div>`)
}

function productionPage() {
  return heading('生产需求分配', '按数量安排生产，不再只挂一个订单号；未分配部分保留公共备库存。', link('查看页面影响', 'impact', 'btn')) + tabs([['生产需求分配', 'production', true, 'production'], ['库存备货', 'stock', false, 'stock'], ['出货记录', 'ship', false, 'ship']]) + notice('这里记录“计划为谁做”，不锁定现有库存。加工单结清不代表客户足量；实收和损耗必须分开。') + card('加工产出与需求去向', '同一加工产出明细可分给多个订单，最多不超过计划产出', table(['加工明细 / 商家', '目标产出', '计划 / 实收 / 损耗', '阶段', '需求数量分配', '操作'], state.tasks.map(t => `<tr><td>${link(t.id, taskLink(t), 'mono strong')}<div class="subtext">${t.supplier}</div></td><td>${product(t.product)}</td><td><b>${t.qty}</b> / ${t.received} / ${t.loss}<div class="subtext">单位：${products[t.product].unit}</div></td><td>${tag(taskStage(t), t.status === 'pending' ? 'blue' : 'green')}</td><td>${tokens(t)}</td><td>${textButton('调整数量分配', 'allocation', t.id)}</td></tr>`).join(''))) + `<div class="help-grid"><div class="help-card"><h3>生产安排与现货，不累计为“完成”</h3><p>出货后仍保留原计划作为历史依据。若确认损耗导致客户缺口，使用现货补齐或明确安排补产；不自动生成补单。</p></div><div class="help-card"><h3>电镀按收回目标配件匹配</h3><p>本例发出原色 PJ-0816，产出金色 PJ-0816-G。需求分配匹配金色目标，而非原色材料，不把发料量当作客户交付量。</p></div></div>`
}

function stockPage() {
  const rows = Object.entries(products).map(([key, p]) => { const b = balance(state, key); return `<tr><td>${product(key)}</td><td><b>${b.physical}</b> ${p.unit}</td><td>${b.reserved} ${p.unit}<div class="subtext">不能被其他订单直接使用</div></td><td><b class="green">${b.free}</b> ${p.unit}</td><td>${textButton('登记真实入库', 'inbound', key)}</td></tr>` }).join('')
  const reservationRows = eligibleLines().map(({ order, line }) => `<tr><td>${link(order.id, `orders/${order.id}`, 'mono')}<div class="subtext">${order.customer}</div></td><td>${product(line.product, `${line.id} · ${line.code}`)}</td><td>${line.qty}</td><td>${line.shipped}</td><td>${line.reserved}</td><td class="amber">${lineNumbers(state, line).gap}</td><td>${textButton('预留库存', 'reserve', line.id)}${line.reserved ? ` · ${textButton('取消预留', 'release', line.id)}` : ''}</td></tr>`).join('')
  return heading('库存备货', '预留是为订单留货，不是出库；取消预留只恢复公共可用量，实物库存不变。', button('登记现货入库', 'inbound', '', 'primary', 'plus'))
    + notice('实物存在但没有系统库存记录？先登记真实来源，再继续出货。不会自动补足缺货，也不会伪造加工单。')
    + card('库存可用量', '公共可用 = 实物库存 − 所有订单待发预留；不同单位不相加', table(['产品', '实物库存', '已预留待发', '公共可用', '操作'], rows))
    + card('客户库存预留', '预留绑定具体订单明细；取消后可供其他订单使用，不代表出库或退货', table(['客户订单', '产品 / 明细', '订购', '已出货', '待发预留', '尚待备货', '操作'], reservationRows))
    + card('真实现货入库记录', '独立保留入库凭据；不强制关联加工单', table(['入库编号', '产品', '数量', '来源', '说明'], state.receipts.map(r => `<tr><td class="mono">${r.id}</td><td>${product(r.product)}</td><td>+${r.qty}</td><td>${r.reason}</td><td class="wrap-cell">${esc(r.note)}</td></tr>`).join('')))
}

function shipmentTable(items) { return table(['出货单', '客户订单', '状态', '明细', '操作'], items.map(s => `<tr><td>${link(s.id, `ship/${s.id}`, 'mono strong')}<div class="subtext">${s.date}</div></td><td>${link(s.orderId, `orders/${s.orderId}`, 'mono')}</td><td>${shipmentStatus(s)}</td><td>${s.lines.length} 行<div class="subtext">${s.lines.map(l => `${products[locateLine(state, l.lineId).line.product].name.split(' · ')[0]} ${l.qty}`).join(' / ')}</div></td><td>${link('查看详情 →', `ship/${s.id}`)}</td></tr>`).join('')) }

function shipmentsPage() {
  return heading('出货管理', '手动选择订单明细，按实际数量出货；不要求任何加工单关联。', button('新建出货单', 'ship-new', '', 'primary', 'plus')) + `<div class="stats">${stat('已确认出货', state.shipments.filter(s => s.status === 'confirmed').length, '单', '确认才扣除真实库存', 'ship', true)}${stat('待确认草稿', state.shipments.filter(s => s.status === 'draft').length, '单', '草稿不占用库存', 'orders')}${stat('履约已完成', activeOrders().filter(o => orderStage(o) === '已完成').length, '单', '全部明细足量出货后完成', 'check')}${stat('出货方式', '手动添加', '', '支持现货，不必先分配生产', 'stock')}</div>` + notice('公共现货可直接出货；已分配给其他订单或其他明细的库存不可挪用。库存不足时，必须先登记真实入库或明确调整分配。') + card('出货记录', '保存草稿 → 核对实际明细 → 确认扣库；已出货记录不可直接作废回库', shipmentTable(state.shipments))
}

function shipmentDetail(id) {
  const s = state.shipments.find(s => s.id === id)
  if (!s) return heading('出货单不存在', '请返回出货列表。')
  const o = state.orders.find(o => o.id === s.orderId)
  return heading(s.id, `${o.customer} · ${s.date} · ${s.status === 'draft' ? '草稿未扣库' : s.status === 'confirmed' ? '已确认实物出货' : '已作废，无库存变动'}`, link('返回出货列表', 'ship', 'btn') + (s.status === 'draft' ? button('作废草稿', 'void', id, 'danger') + button('核对并确认出货', 'draft-review', id, 'primary', 'check') : '')) + `<section class="card"><div class="shipment-hero"><span class="hero-icon">${icon(s.status === 'confirmed' ? 'check' : 'ship')}</span><div><h2>${s.status === 'confirmed' ? '出货已确认，库存已扣减' : s.status === 'draft' ? '草稿已保存，尚未占库或扣库' : '草稿已作废'}</h2><p>${s.status === 'confirmed' ? '重复确认不会重复扣库；实际退货需要独立凭据，不可只改状态回库。' : '确认时重新校验订单剩余数量和可用库存，草稿不保证当时仍有货。'}</p></div></div><div class="card-body"><dl class="confirmation-list"><div><dt>客户订单</dt><dd>${link(s.orderId, `orders/${s.orderId}`)} · ${o.customer}</dd></div><div><dt>状态</dt><dd>${shipmentStatus(s)}</dd></div><div><dt>物流信息（可选）</dt><dd>${esc(s.tracking || '未填写')}</dd></div><div><dt>备注</dt><dd>${esc(s.note || '无')}</dd></div></dl></div>${table(['实际出货产品', '订单明细', '本次出货', '加工来源要求'], s.lines.map(e => { const { line } = locateLine(state, e.lineId); return `<tr><td>${product(line.product, line.code)}</td><td class="mono">${e.lineId}</td><td><b>${e.qty}</b> ${products[line.product].unit}</td><td><span class="muted">无强制加工关联 · 使用已入账库存</span></td></tr>` }).join(''))}</section>` + notice(s.status === 'confirmed' ? '本次出库已计入订单履约进度。生产计划保持原记录，不把计划数量再次加到出货或备货中。' : '需要补充真实现货时，可在核对确认步骤选择“登记现货入库并继续”。')
}

function taskList(type) {
  const hand = type === 'handcraft', items = state.tasks.filter(t => t.type === type)
  return heading(hand ? '手工管理' : '电镀管理', hand ? '材料、产出与客户来源分层呈现，生产结清不等于客户订单完成。' : '发出原料与收回目标配件明确区分，按目标产出分配客户需求。', link('查看生产分配', 'production', 'btn'), '生产管理')
    + tabs([[hand ? '手工任务' : '电镀任务', type, true, type], ['需求数量分配', 'production', false, 'production'], ['影响与实施边界', 'impact', false, 'impact']])
    + notice(hand ? '从订单安排制作时默认新建；上游配件可在订单的“本单生产需求分配”查看与安排。' : '直接交付商品与上游备料配件分区展示。付款、加工结清与客户出货三个维度互不替代。')
    + card(hand ? '手工任务列表' : '直接交付商品的电镀任务', '原有列表优化 · 增加来源范围、分配数量与独立结清状态', table(['加工单 / 商家', hand ? '目标产出' : '发出原料 → 目标产出', '任务阶段', '计划 / 实收 / 损耗', '客户来源与公共部分', '操作'], items.map(t => `<tr><td>${link(t.id, taskLink(t), 'mono strong')}<div class="subtext">${t.supplier} · ${t.date}</div></td><td>${!hand ? `<div class="subtext mono">${t.inputId} 原色 →</div>` : ''}${product(t.product)}</td><td>${tag(taskStage(t), t.status === 'pending' ? 'blue' : 'green')}</td><td>${t.qty} / ${t.received} / ${t.loss}<div class="subtext">付款：独立回收单管理</div></td><td>${tokens(t)}</td><td>${link('查看明细 →', taskLink(t))}</td></tr>`).join('')))
    + `<div class="help-grid"><div class="help-card"><h3>${hand ? '材料与产出分开' : '不伪造上下游批次'}</h3><p>${hand ? '本 Demo 按示例 BOM 展开客户制作所需配件，记录现货与电镀的备料计划；不执行领料或发出扣库，新建任务不会悄悄扣材料。' : '上游配件只记录计划用途与虚构历史凭据，不自动记成品回收。关联同一客户需求，不代表已有实物批次追溯。'}</p></div><div class="help-card"><h3>原有能力继续保留</h3><p>独立生产、公共备库存、超量实收、回收凭据与商家付款不取消。实际发料、成本、付款、归档等正式操作，本原型不执行。</p></div></div>`
}

function taskDetail(id, source) {
  const materialTask = state.materialTasks.find(t => t.id === id)
  if (materialTask) return materialTaskDetail(materialTask, source)
  const t = state.tasks.find(t => t.id === id)
  if (!t) return heading('加工单不存在', '请返回生产列表。')
  const hand = t.type === 'handcraft'
  const allocated = Object.values(t.allocations).reduce((a, b) => a + b, 0)
  return heading(`${t.id} <span class="muted">/</span> ${t.supplier}`, `${hand ? '手工' : '电镀'}任务 · ${t.date} · 单条产出明细示例`, link('返回任务列表', t.type, 'btn') + button('调整需求分配', 'allocation', id, 'soft') + (t.status !== 'pending' ? button('登记实际回收', 'task-receive', id, 'primary', 'plus') : ''), '生产管理') + (source ? notice(`来自订单 ${esc(source)}，对应需求行已高亮。${textButton(sourceOnly ? '显示全部客户' : '只看本订单', 'source-toggle')}`) : '') + `<div class="stats">${stat('计划产出', t.qty, products[t.product].unit, '计划不被超量实收改写', 'production')}${stat('实际已收', t.received, products[t.product].unit, '已入账实物，不代表已出货', 'stock', true)}${stat('确认损耗', t.loss, products[t.product].unit, '只用于任务结清，不满足客户需求', 'info')}${stat('任务阶段', taskStage(t), '', t.status === 'pending' ? '尚未发料，不显示等待返回' : '实收 + 损耗 ≥ 计划时结清', 'clock')}</div>` + card(hand ? '产出明细' : '投入与目标产出', '原有详情优化 · 投入、产出、客户分配分别表达', `<div class="card-body"><div class="order-meta">${!hand ? `<span>发出原料<strong class="mono">${t.inputId} 原色链条</strong></span><span>→</span>` : ''}${product(t.product)}<span>需求匹配<strong>${products[t.product].id}</strong></span></div></div>`) + card('客户需求数量分配', '一条产出可分给多个订单；此处是计划归属，不是实收批次或库存锁定', table(['客户订单', '需求明细', '本次安排', '该行已出货', '该行待发预留', '说明'], Object.entries(t.allocations).filter(([id]) => !sourceOnly || !source || locateLine(state, id).order.id === source).map(([id, qty]) => { const { order, line } = locateLine(state, id); return `<tr class="${order.id === source ? 'row-highlight' : ''}"><td>${link(order.id, `orders/${order.id}`, 'mono strong')}<div class="subtext">${order.customer}</div></td><td>${line.id} · ${line.code}</td><td><b>${qty}</b> ${products[t.product].unit}</td><td>${line.shipped}</td><td>${line.reserved}</td><td>${order.id === source ? tag('当前来源', 'green') : '<span class="muted">独立订单需求</span>'}</td></tr>` }).join('')), '', `<span>客户安排 ${allocated} · 公共备库存 ${t.qty - allocated} ${products[t.product].unit}</span><span>公共部分不自动归属任何客户</span>`) + notice(t.loss ? `已有确认损耗 ${t.loss} ${products[t.product].unit}。即使加工任务结清，客户仍须按实际可用库存备货；超收部分也不会自动分给客户。` : '实际回收入公共库存，之后再分配给客户或直接确认出货。加工商费用和付款仍按回收凭据独立处理。', t.loss ? 'warning' : '') + card('本页与相邻功能的影响', '以下入口保留原业务边界，本 Demo 不模拟实际材料发出与付款', `<div class="card-body"><div class="help-grid"><div class="help-card"><h3>${hand ? '客户分拣 / 备货批次' : '回收与对账'}</h3><p>${hand ? '矩阵按确认的数量分配显示客户来源；旧关系只作来源提示，不自动补数量。多客户关联不能重复累计实收、材料和金额。' : '继续独立记录原计划、实际收回、目标配件、图片和费用。超收不改计划、不强制归客户，付款不能代表客户完成。'}</p></div><div class="help-card"><h3>历史与撤销保护</h3><p>旧关联数量待核实；历史已完成订单只读。发料撤回、回收撤回、归档和付款锁定需统一校验真实库存及待发预留，不能绕过占用。</p></div></div></div>`)
}

function impactPage() {
  const items = [
    ['优化现有', '客户订单列表 / 详情', '分开展示生产安排、待发预留、实际出货；全部明细足量出货后完成。增加库存预留、手工安排、分批出货入口，历史完成订单只读。', 'orders'],
    ['新增', '生产需求数量分配', '以加工产出明细与客户订单明细为身份，支持跨订单数量拆分；公共部分单列。生产计划不与实物库存或出货进度相加。', 'production'],
    ['新增', '上游配件备料 / 电镀用途追溯', '订单详情提示备料风险；按已安排手工数量展开示例 BOM，显式安排公共现货或电镀计划；跨订单容量保护，电镀详情可回到本单。仅计划用途，不执行材料收发，不计入成品进度。', 'orders/OR-1042/production'],
    ['新增', '库存备货 / 真实现货入库', '预留库存、取消预留与实物库存分开。取消后恢复公共可用量，不代表出库或退货。没有加工单来源也可登记现货；入库必须填写真实来源和说明，不为出货自动补库存。', 'stock'],
    ['新增', '出货列表 / 新建 / 核对 / 详情', '手动选订单明细，填写本次实发；不要求加工关联。草稿不占库，确认重新校验，优先消耗本明细预留；库存不足可登记真实入库后返回原出货上下文。', 'ship'],
    ['优化现有', '手工创建 / 列表 / 详情', '安排制作默认新建，显式选择同商家同产品待发出任务追加；列表展示客户来源和公共部分，详情按来源高亮。新建只安排计划，不自动发料。', 'handcraft'],
    ['优化现有', '电镀列表 / 详情 / 需求匹配', '明确原料 → 收回目标配件；按目标匹配需求。保留计划、实收、损耗、超收及独立付款，增加数量分配和订单反向入口。', 'plating'],
    ['联动调整', '手工客户分拣 / 配件需求 / 库存扣减入口', '客户分拣需按确认数量适配多客户来源，避免一对多重复统计；手工发料、电镀发料、盘点、回收撤回等统一遵守可用库存和预留规则。这些为正式实施影响，本 Demo 仅说明，不执行材料或资金操作。', null],
    ['兼容保护', '历史关联 / 成本快照 / 付款与归档', '不猜测旧关联数量，不自动补历史出货或库存流水。成本快照不冒充按批次归集的实际成本；既有付款、归档和撤销保护继续保留。', 'orders/OR-0988'],
  ]
  return heading('本次改动总览', '新增页面、现有界面优化和联动影响，一起放到同一套产品逻辑中评审。', link('开始体验 Demo', 'orders', 'btn primary'), '方案评审') + notice('这是独立交互原型，不是正式业务改造。所有数据均为虚构，不读取登录态、不请求业务 API、不写数据库或本地持久化。') + card('页面与功能影响清单', '覆盖可交互页面，并明确未模拟的正式实施范围', items.map(([type, title, desc, route], i) => `<div class="impact-item"><span class="impact-number">${String(i + 1).padStart(2, '0')}</span><div>${tag(type, type === '新增' ? 'green' : 'blue')}<h3 class="section-title">${title}</h3><p>${desc}</p>${route ? link('打开对应页面 →', route, 'text-btn') : ''}</div></div>`).join('')) + card('建议实施顺序', '逐阶段验收，不一次切换库存与历史数据', `<div class="card-body"><div class="roadmap">${[['01', '界面与口径', '先消除名称和状态误导'], ['02', '数量分配', '明确生产计划及历史来源'], ['03', '统一库存预留', '所有扣库入口统一校验'], ['04', '分批出货闭环', '确认扣库、全部出货完成'], ['05', '历史核对', '只读报告与人工确认迁移']].map(([num, title, desc]) => `<div class="help-card"><span class="kicker">PHASE ${num}</span><h3>${title}</h3><p>${desc}</p></div>`).join('')}</div></div>`) + `<div class="help-grid"><div class="help-card"><h3>可以直接体验</h3><p>订单详情、跨订单生产拆分、默认新建 / 显式追加手工、预留库存 / 取消预留、无加工来源手动出货、真实入库、保存草稿、部分 / 全部出货、实际超收、来源高亮和只读历史。</p></div><div class="help-card"><h3>刻意不在 Demo 中实现</h3><p>真实 API、权限、并发事务、数据库迁移、BOM 材料发出、付款 / 运费 / 发票、已出货退货、批次成本与自动历史补录。正式实施时单独设计与回归。</p></div></div>`
}

function showDialog(title, subtitle, body, footer) {
  modal.innerHTML = `<div class="dialog-head"><div><h2 id="dialog-title">${title}</h2><p>${subtitle}</p></div>${button('<span class="sr-only">关闭对话框</span>', 'close', '', 'icon-btn', 'close')}</div><form id="demo-form" novalidate><div class="dialog-body"><div id="form-error" class="error" role="alert"></div>${body}</div><div class="dialog-footer">${footer}</div></form>`
  if (!modal.open) modal.showModal()
  document.body.classList.add('modal-open')
}
function closeDialog() { modal.close(); document.body.classList.remove('modal-open'); dialogReturn = null }
function error(message) { const el = modal.querySelector('#form-error'); if (el) { el.textContent = message; el.scrollIntoView({ block: 'nearest' }) } else toast(message, true) }
function toast(message, bad = false) { clearTimeout(toastTimer); document.querySelector('#notifications').innerHTML = `<div class="toast ${bad ? 'error-toast' : ''}">${esc(message)}</div>`; toastTimer = setTimeout(() => { document.querySelector('#notifications').innerHTML = '' }, 4000) }
const fields = () => Object.fromEntries(new FormData(document.querySelector('#demo-form')))
const formField = (label, name, type = 'text', value = '', help = '') => `<div class="field"><label for="field-${name}">${label}</label><input id="field-${name}" name="${name}" type="${type}" value="${esc(value)}" ${type === 'number' ? 'min="1" max="1000000" step="1" inputmode="numeric"' : ''}>${help ? `<small>${help}</small>` : ''}</div>`

function reserveDialog(id, release = false) {
  const { order, line } = locateLine(state, id), b = balance(state, line.product)
  const explanation = release
    ? '取消后，这部分库存不再为本订单留货，恢复为公共可用库存，可供其他订单使用。实物库存、生产安排和已出货数量均不变；这不是出库或退货。'
    : '从公共可用库存中为本订单留货，其他订单不能直接占用。实物库存不变，不代表已经出货；正常出货会自动消耗预留，无需先取消。'
  showDialog(release ? '取消预留' : '预留库存', `${order.id} · ${order.customer} · ${line.code}`,
    notice(explanation) + product(line.product)
    + `<div class="allocation-totals"><div><small>本行待发预留</small><strong>${line.reserved}</strong></div><div><small>尚待备货</small><strong>${lineNumbers(state, line).gap}</strong></div><div><small>公共可用</small><strong>${b.free}</strong></div></div><div class="section-space">${formField(release ? '本次取消预留数量' : '本次预留数量', 'qty', 'number', '', release ? '可取消部分或全部待发预留，不能超过本行已预留数量。' : '仅从公共可用库存中预留，不占用其他订单或明细的预留。')}</div>`,
    `<small>只调整当前明细的预留，不改变实物库存</small><div class="actions">${button('返回', 'close')}${button(release ? '确认取消预留' : '确认预留', release ? 'release-save' : 'reserve-save', id, 'primary')}</div>`)
}

function allocationDialog(id, orderId = '') {
  const t = state.tasks.find(t => t.id === id)
  const lines = eligibleLines(t.product).filter(({ order }) => !orderId || order.id === orderId)
  showDialog(orderId ? '调整本单生产分配' : '调整生产需求分配', `${orderId ? `${orderId} · ` : ''}${t.id} · ${t.supplier} · 计划 ${t.qty} ${products[t.product].unit}`, notice(orderId ? '仅调整当前订单明细；其他订单的分配固定保留，不会被覆盖。分配后仍需按实际回收和库存备货交付。' : '只调整计划用途，不移动库存。未分配部分归公共备库存；已存在的计划在出货后保留为历史安排。') + product(t.product) + table(['客户订单 / 明细', '订购 / 已出货', '本条安排数量'], lines.map(({ order, line }) => `<tr><td>${order.id} · ${order.customer}<div class="subtext">${line.id} / ${line.code}</div></td><td>${line.qty} / ${line.shipped}</td><td><input class="number-input" type="number" name="${line.id}" min="0" max="${t.qty}" step="1" value="${t.allocations[line.id] || 0}" aria-label="${order.id} ${line.code} 安排数量" data-allocation-input></td></tr>`).join('')) + `<div id="allocation-summary" class="allocation-totals"></div>`, `<small>分配合计不能超过计划 ${t.qty}</small><div class="actions">${button('取消', 'close')}${button(orderId ? '保存本单分配' : '保存数量分配', 'allocation-save', id, 'primary')}</div>`)
  modal.dataset.taskId = id
  modal.dataset.allocationOrderId = orderId
  allocationSummary()
}
function allocationSummary() {
  const t = state.tasks.find(t => t.id === modal.dataset.taskId)
  const orderId = modal.dataset.allocationOrderId
  const other = orderId ? Object.entries(t.allocations).reduce((n, [id, qty]) => n + (locateLine(state, id).order.id === orderId ? 0 : qty), 0) : 0
  const n = [...modal.querySelectorAll('[data-allocation-input]')].reduce((a, el) => a + Number(el.value || 0), 0)
  modal.querySelector('#allocation-summary').innerHTML = `<div><small>计划产出</small><strong>${t.qty}</strong></div><div><small>${orderId ? '本单安排' : '客户安排'}</small><strong>${n}</strong></div>${orderId ? `<div><small>其他订单（固定）</small><strong>${other}</strong></div>` : ''}<div><small>公共备库存</small><strong class="${n + other > t.qty ? 'red' : 'green'}">${t.qty - n - other}</strong></div>`
}

function arrangeDialog(id, selectedSupplier = '青禾手作', values = {}) {
  const { order, line } = locateLine(state, id)
  const open = Math.max(0, line.qty - line.shipped - lineNumbers(state, line).planned)
  const candidates = state.tasks.filter(t => t.type === 'handcraft' && t.status === 'pending' && t.product === line.product && t.supplier === selectedSupplier)
  showDialog('安排手工制作', `${order.id} · ${order.customer} · ${line.code}`, notice('只生成待发出计划。材料 BOM、领料与实际发出仍需在正式手工流程中确认，本 Demo 不模拟扣料。') + product(line.product) + `<div class="form-grid section-space"><div class="field"><label for="arrange-supplier">手工商家</label><select id="arrange-supplier" name="supplier" data-arrange-line="${id}">${['青禾手作', '拾光工坊'].map(s => `<option ${s === selectedSupplier ? 'selected' : ''}>${s}</option>`).join('')}</select></div>${formField('本次制作数量', 'qty', 'number', values.qty || '', `未安排需求 ${open} ${products[line.product].unit}；不把库存预留再算成生产安排。`)}</div><h3 class="section-space">选择生成方式</h3><label class="option-card"><input type="radio" name="targetId" value="new" checked><span><strong>新建手工单 <span class="tag green">默认</span></strong><small>独立创建本次计划，不静默合入任何现有单据。</small></span></label>${candidates.map(t => `<label class="option-card"><input type="radio" name="targetId" value="${t.id}"><span><strong>明确追加到 ${t.id} · ${t.supplier}</strong><small>现有计划 ${t.qty} ${products[t.product].unit} · ${Object.entries(t.allocations).map(([id, qty]) => `${locateLine(state, id).order.id} ${qty}`).join(' / ')} · 公共 ${t.qty - Object.values(t.allocations).reduce((a, b) => a + b, 0)}</small><small>提交会增加该单计划及本客户安排，原有客户数量保持不变。</small></span></label>`).join('') || '<p class="subtext">没有同商家、同产品的可追加待发出明细。</p>'}`, `<small>即使存在可追加单，仍默认新建</small><div class="actions">${button('取消', 'close')}${button('确认安排制作', 'arrange-save', id, 'primary')}</div>`)
}

function inboundDialog(key = 'necklace', back = null) {
  dialogReturn = back
  showDialog('登记真实现货入库', '适用于实际已有但尚未入账的货物；不要求加工单来源。', notice('只有确认实物存在才可入库。不会按缺口预填数量，不自动补足库存；来源说明将独立留档。', 'warning') + `<div class="form-grid"><div class="field"><label for="inbound-product">实际产品</label><select id="inbound-product" name="product">${Object.entries(products).map(([id, p]) => `<option value="${id}" ${id === key ? 'selected' : ''}>${p.id} · ${p.name}（${p.unit}）</option>`).join('')}</select></div>${formField('真实入库数量', 'qty', 'number')}<div class="field"><label for="inbound-reason">真实来源</label><select id="inbound-reason" name="reason"><option value="">请选择来源</option><option>历史现货补录</option><option>外购成品</option><option>盘点补录</option></select></div><div class="field full"><label for="inbound-note">来源说明（必填）</label><textarea id="inbound-note" name="note" placeholder="例如：11 月仓库盘点确认的现货，原记录未入账"></textarea></div></div>`, `<small>仅登记实物入库，不自动确认出货</small><div class="actions">${button(back ? '返回出货核对' : '取消', back ? 'inbound-back' : 'close')}${button(back ? '确认入库并返回' : '确认真实入库', 'inbound-save', '', 'primary')}</div>`)
}

function startWizard(orderId) {
  wizard = { orderId: orderId || activeOrders().find(o => orderStage(o) !== '已完成')?.id || 'OR-1042', lines: [], note: '', tracking: '', step: 1, draftId: null }
  wizardDialog()
}
function captureWizard() {
  wizard.lines = [...modal.querySelectorAll('[name="ship-line"]:checked')].map(el => ({ lineId: el.value, qty: modal.querySelector(`[name="qty-${el.value}"]`).value }))
  wizard.note = modal.querySelector('[name="note"]').value
  wizard.tracking = modal.querySelector('[name="tracking"]').value
}
function wizardDialog() {
  dialogReturn = null
  const o = state.orders.find(o => o.id === wizard.orderId), review = wizard.step === 2
  const steps = `<div class="steps"><span class="step ${!review ? 'active' : ''}"><b>1</b>手动添加明细</span><i></i><span class="step ${review ? 'active' : ''}"><b>2</b>核对并确认</span><i></i><span class="step"><b>3</b>出货记录</span></div>`
  let body
  if (!review) {
    const entries = o.lines.map(line => {
      const selected = wizard.lines.find(l => l.lineId === line.id), p = products[line.product]
      return `<tr><td><input type="checkbox" name="ship-line" value="${line.id}" aria-label="选择 ${p.name}" ${selected ? 'checked' : ''} ${line.qty === line.shipped ? 'disabled' : ''}></td><td>${product(line.product, line.code)}</td><td>${line.qty - line.shipped} ${p.unit}</td><td>${line.reserved} / ${balance(state, line.product).free}</td><td><div class="unit-input"><input class="number-input" name="qty-${line.id}" type="number" min="1" max="${line.qty - line.shipped}" step="1" inputmode="numeric" placeholder="实际数量" aria-label="${p.name} 本次实发" value="${esc(selected?.qty ?? '')}" ${!selected ? 'disabled' : ''}><small>${p.unit}</small></div></td></tr>`
    }).join('')
    body = notice('不需要手工单 / 电镀单。勾选客户订单明细，手动填写本次实际出货数量；不预填或自动选择。')
      + `<div class="field"><label for="shipment-order">客户订单</label><select id="shipment-order" name="orderId" ${wizard.draftId ? 'disabled' : ''}>${orderOptions(o.id)}</select></div>`
      + table(['选择', '产品 / 客户货号', '剩余待发', '本行预留 / 公共可用', '本次实发'], entries, 'shipment-entry')
      + `<div class="form-grid section-space">${formField('物流信息（可选）', 'tracking', 'text', wizard.tracking)}<div class="field"><label for="ship-note">出货备注（可选）</label><input id="ship-note" name="note" value="${esc(wizard.note)}" placeholder="如：现货分批发，独立装袋"></div></div>`
  } else {
    let stockError = ''
    try { checkShipment(state, o.id, wizard.lines, true) } catch (e) { stockError = e.message }
    body = notice('请核对实际发出的产品和数量。确认才会扣库；优先消耗所选明细的预留，其余使用公共现货。') + `<div class="order-meta"><span>客户订单<strong>${o.id}</strong></span><span>客户<strong>${o.customer}</strong></span><span>加工关联<strong>不要求</strong></span></div>` + table(['出货产品', '本次实发', '本行预留', '公共可用'], wizard.lines.map(e => { const { line } = locateLine(state, e.lineId); return `<tr><td>${product(line.product, line.code)}</td><td><b>${e.qty}</b> ${products[line.product].unit}</td><td>${line.reserved}</td><td>${balance(state, line.product).free}</td></tr>` }).join('')) + (stockError ? `<div class="error section-space">${esc(stockError)}</div>` : `<div class="summary-box"><div><strong>当前数量与库存校验通过</strong><small>最终确认时仍会再次校验，不以草稿数据代替实时校验。</small></div>${icon('check')}</div>`) + `<div class="inline-choice">实际有货但未入账？${textButton('登记现货入库并继续 →', 'ship-inbound')}</div><dl class="confirmation-list section-space"><div><dt>物流</dt><dd>${esc(wizard.tracking || '未填写')}</dd></div><div><dt>备注</dt><dd>${esc(wizard.note || '无')}</dd></div></dl><label class="shipment-check"><input id="actual-shipment" type="checkbox">我已核对实际货物与本次出货数量，确认后将扣减库存并计入订单出货进度。</label>`
  }
  showDialog(review ? '核对本次出货' : '新建出货单', review ? '库存不足不能强行确认，不会为发货自动造库存。' : '手动出货 · 公共现货也能交付', body, `<small>${review ? '确认后不可直接作废回库' : '草稿不占库，也不保证之后仍有货'}</small><div class="actions">${button(review ? '返回修改' : '取消', review ? 'ship-back' : 'close')}${!wizard.draftId ? button('保存草稿', 'ship-save-draft') : ''}${button(review ? '确认实际出货' : '下一步 · 核对', review ? 'ship-confirm' : 'ship-next', '', 'primary', review ? 'check' : 'arrow')}</div>`)
  modal.querySelector('.dialog-head').insertAdjacentHTML('afterend', steps)
}

function taskReceiveDialog(id) { const t = state.tasks.find(t => t.id === id); showDialog('登记实际回收', `${t.id} · ${t.supplier}`, notice('按真实实收登记，可超出计划。实收全部进入公共库存，不自动分配客户；原计划与确认损耗不变。') + product(t.product) + `<div class="allocation-totals"><div><small>计划</small><strong>${t.qty}</strong></div><div><small>已收</small><strong>${t.received}</strong></div><div><small>确认损耗</small><strong>${t.loss}</strong></div></div><div class="section-space">${formField('本次真实实收数量', 'qty', 'number', '', `单位：${products[t.product].unit}；本 Demo 不模拟费用和付款。`)}</div>`, `<small>损耗不等于实收；客户出货进度不变</small><div class="actions">${button('取消', 'close')}${button('确认实收入库', 'task-receive-save', id, 'primary')}</div>`) }

const actions = {
  'material-source': materialSourceDialog,
  'material-source-save': key => {
    const [orderId, id] = key.split('|'), values = fields()
    const plating = Object.fromEntries(Object.entries(values).filter(([name]) => name !== 'stock'))
    saveMaterialSourcing(state, orderId, id, { stock: values.stock, plating })
    closeDialog(); render(); toast('配件备料安排已更新，未发料、未入库，成品进度不变')
  },
  menu: () => { app.querySelector('.sidebar').classList.add('open'); app.querySelector('.menu-scrim').classList.add('open') },
  'menu-close': () => { app.querySelector('.sidebar').classList.remove('open'); app.querySelector('.menu-scrim').classList.remove('open') },
  'skip-main': () => document.querySelector('#main').focus(),
  close: () => { if (dialogReturn) { wizard = dialogReturn; wizardDialog() } else closeDialog() },
  reset: () => showDialog('重置演示数据？', '只重置当前原型，不影响正式系统。', '<p>所有模拟分配、入库与出货将清空，恢复初始虚构场景。</p>', `<small>刷新页面也会恢复初始数据</small><div class="actions">${button('取消', 'close')}${button('重置 Demo', 'reset-confirm', '', 'primary')}</div>`),
  'reset-confirm': () => { state = createState(); wizard = null; filter = 'all'; search = ''; closeDialog(); location.hash = '/orders'; render(); toast('已恢复初始虚构数据') },
  filter: id => { filter = id; render() },
  reserve: id => reserveDialog(id), release: id => reserveDialog(id, true),
  'reserve-save': id => { reserveLine(state, id, fields().qty); closeDialog(); render(); toast('库存已预留，实物总量未变') },
  'release-save': id => { releaseLine(state, id, fields().qty); closeDialog(); render(); toast('已取消预留，恢复公共可用；实物总量未变') },
  allocation: allocationDialog,
  'order-allocation': id => { const [taskId, orderId] = id.split(':'); allocationDialog(taskId, orderId) },
  'allocation-save': id => { const orderId = modal.dataset.allocationOrderId; if (orderId) saveOrderAllocation(state, id, orderId, fields()); else saveAllocation(state, id, fields()); closeDialog(); render(); toast(orderId ? '本单分配已保存，其他订单安排保持不变' : '已保存生产数量分配，库存未改变') },
  arrange: arrangeDialog,
  'arrange-save': id => { const task = arrangeHandcraft(state, { ...fields(), lineId: id }); closeDialog(); location.hash = `/${taskLink(task, locateLine(state, id).order.id)}`; render(); toast('待发出制作计划已生成，尚未发料') },
  inbound: key => inboundDialog(key || 'necklace'),
  'inbound-back': () => { if (dialogReturn) { wizard = dialogReturn; wizardDialog() } },
  'inbound-save': () => { const back = dialogReturn; receiveStock(state, fields()); if (back) { wizard = back; wizardDialog(); render() } else { closeDialog(); render() } toast('真实入库已记录，未自动确认出货') },
  'ship-new': startWizard,
  'ship-next': () => { captureWizard(); checkShipment(state, wizard.orderId, wizard.lines); wizard.step = 2; wizardDialog() },
  'ship-back': () => { wizard.step = 1; wizardDialog() },
  'ship-save-draft': () => { if (wizard.step === 1) captureWizard(); const draft = saveDraft(state, wizard); closeDialog(); location.hash = `/ship/${draft.id}`; render(); toast('草稿已保存，没有占用或扣减库存') },
  'ship-inbound': () => inboundDialog(locateLine(state, wizard.lines[0].lineId).line.product, wizard),
  'ship-confirm': () => {
    if (!modal.querySelector('#actual-shipment').checked) throw new Error('请先确认已核对实际货物与出货数量')
    checkShipment(state, wizard.orderId, wizard.lines, true)
    let draft
    if (wizard.draftId) {
      draft = state.shipments.find(s => s.id === wizard.draftId)
      if (draft.status !== 'draft') throw new Error('当前草稿已改变，请重新打开出货记录')
      Object.assign(draft, { lines: wizard.lines.map(l => ({ ...l, qty: Number(l.qty) })), note: wizard.note, tracking: wizard.tracking })
    } else draft = saveDraft(state, wizard)
    confirmShipment(state, draft.id); closeDialog(); location.hash = `/ship/${draft.id}`; render(); toast('出货已确认，库存及订单进度已更新')
  },
  'draft-review': id => { const s = state.shipments.find(s => s.id === id); wizard = { ...s, draftId: id, lines: s.lines.map(l => ({ ...l })), step: 2 }; wizardDialog() },
  void: id => showDialog('作废这张草稿？', `${id} · 仅未确认草稿可作废`, '<p>草稿未占库或扣库，作废不会产生库存变动。已真实出货的记录不能用此方式撤销。</p>', `<small>保留草稿与作废状态供核对</small><div class="actions">${button('取消', 'close')}${button('确认作废草稿', 'void-confirm', id, 'danger')}</div>`),
  'void-confirm': id => { voidDraft(state, id); closeDialog(); render(); toast('草稿已作废，无库存变动') },
  'task-receive': taskReceiveDialog,
  'task-receive-save': id => { receiveTask(state, id, fields().qty); closeDialog(); render(); toast('实际回收已入公共库存，客户出货数量不变') },
  'source-toggle': () => { sourceOnly = !sourceOnly; render() },
}

document.addEventListener('click', event => {
  const el = event.target.closest('[data-action]')
  if (!el || !actions[el.dataset.action]) return
  event.preventDefault()
  try { actions[el.dataset.action](el.dataset.id) } catch (e) { error(e.message) }
})
document.addEventListener('input', event => {
  if (event.target.matches('[data-allocation-input]')) allocationSummary()
  if (event.target.id === 'order-search') { const start = event.target.selectionStart; search = event.target.value; render(); const input = app.querySelector('#order-search'); input.focus(); input.setSelectionRange(start, start) }
})
document.addEventListener('change', event => {
  if (event.target.name === 'ship-line') { const input = modal.querySelector(`[name="qty-${event.target.value}"]`); input.disabled = !event.target.checked; if (event.target.checked) input.focus() }
  if (event.target.id === 'shipment-order') { wizard.orderId = event.target.value; wizard.lines = []; wizard.note = modal.querySelector('[name="note"]').value; wizard.tracking = modal.querySelector('[name="tracking"]').value; wizardDialog() }
  if (event.target.dataset.arrangeLine) arrangeDialog(event.target.dataset.arrangeLine, event.target.value, fields())
})
document.addEventListener('submit', event => event.preventDefault())
modal.addEventListener('close', () => document.body.classList.remove('modal-open'))
modal.addEventListener('cancel', event => { if (dialogReturn) { event.preventDefault(); wizard = dialogReturn; wizardDialog() } })
window.addEventListener('hashchange', () => { filter = 'all'; search = ''; sourceOnly = false; if (modal.open) closeDialog(); render(); window.scrollTo(0, 0) })
render()
