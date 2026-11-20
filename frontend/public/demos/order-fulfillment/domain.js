// Standalone demo domain. No API, storage, authentication, or production imports.
export const products = {
  necklace: { id: 'SP-0218', name: '月光 · 淡水珍珠项链', spec: '14K 金 / 40 + 5 cm', unit: '条', image: '../assets/pearl-necklace.svg', type: '饰品' },
  earrings: { id: 'SP-0326', name: '流光 · 珍珠耳饰', spec: '14K 金 / 一对装', unit: '对', image: './earrings.svg', type: '饰品' },
  chain: { id: 'PJ-0816-G', name: '细圈链条 · 金色', spec: '电镀目标配件 / 14K 金', unit: '条', image: './chain.svg', type: '配件' },
}

// Fictional BOM snapshots: component pieces never count as finished goods.
export const materials = {
  clasp: { id: 'PJ-0901-G', inputId: 'PJ-0901', name: '金色扣头', unit: '个' },
  hook: { id: 'PJ-0902-G', inputId: 'PJ-0902', name: '金色耳钩', unit: '个' },
}
export const demoBom = { necklace: [{ material: 'clasp', per: 1 }], earrings: [{ material: 'hook', per: 2 }] }

export function createState() {
  return {
    orders: [
      { id: 'OR-1042', customer: '栖物生活', initials: '栖', date: '2026-11-18', due: '2026-11-25', note: '分批发货；项链独立装袋，耳饰一对一卡。', lines: [
        { id: 'a1', product: 'necklace', qty: 100, shipped: 20, reserved: 40, code: 'QW-N018' },
        { id: 'a2', product: 'earrings', qty: 60, shipped: 0, reserved: 20, code: 'QW-E026' },
        { id: 'a3', product: 'chain', qty: 120, shipped: 0, reserved: 0, code: '直接销售配件' },
      ] },
      { id: 'OR-1043', customer: 'MORI STUDIO', initials: 'M', date: '2026-11-18', due: '2026-11-28', note: '首批项链优先；不与其他客户混装。', lines: [
        { id: 'b1', product: 'necklace', qty: 80, shipped: 0, reserved: 60, code: 'MR-N018' },
        { id: 'b2', product: 'earrings', qty: 40, shipped: 0, reserved: 0, code: 'MR-E026' },
      ] },
      { id: 'OR-0988', customer: '山间商店', initials: '山', date: '2026-10-20', due: '2026-10-30', legacy: true, note: '旧流程已完成；没有可核实的出货记录，不自动补出库。', lines: [
        { id: 'c1', product: 'necklace', qty: 50, shipped: 0, reserved: 0, code: 'SJ-001' },
      ] },
    ],
    stock: { necklace: 140, earrings: 30, chain: 80 },
    materialStock: { clasp: 30, hook: 50 },
    materialTasks: [
      { id: 'EP-0131', material: 'clasp', supplier: '恒信电镀', qty: 200, received: 0, loss: 0, status: 'processing' },
      { id: 'EP-0132', material: 'hook', supplier: '恒信电镀', qty: 100, received: 0, loss: 0, status: 'pending' },
    ],
    materialSources: {
      'HC-0086:a1:clasp': { stock: 20, issued: 0, plating: { 'EP-0131': 40 } },
      'HC-0086:b1:clasp': { stock: 10, issued: 0, plating: { 'EP-0131': 50 } },
      'HC-0087:a2:hook': { stock: 0, issued: 80, plating: {} },
    },
    tasks: [
      { id: 'HC-0086', type: 'handcraft', supplier: '青禾手作', date: '2026-11-18', product: 'necklace', qty: 300, received: 0, loss: 0, status: 'pending', allocations: { a1: 60, b1: 80 } },
      { id: 'HC-0087', type: 'handcraft', supplier: '拾光工坊', date: '2026-11-17', product: 'earrings', qty: 40, received: 15, loss: 5, status: 'processing', allocations: { a2: 40 } },
      { id: 'EP-0128', type: 'plating', supplier: '恒信电镀', date: '2026-11-17', product: 'chain', inputId: 'PJ-0816', qty: 300, received: 200, loss: 0, status: 'processing', allocations: { a3: 120 } },
    ],
    shipments: [
      { id: 'SH-0001', orderId: 'OR-1042', status: 'confirmed', date: '2026-11-17', note: '首批现货；历史虚构示例', tracking: '顺丰 SF-DEMO-001', lines: [{ lineId: 'a1', qty: 20 }], initial: true },
    ],
    receipts: [],
    events: [{ title: '首批现货已出货', detail: 'OR-1042 · 珍珠项链 20 条，无需关联加工单', time: '11-17 16:30' }],
    nextShipment: 2, nextTask: 90, nextReceipt: 1,
  }
}

export function locateLine(state, lineId) {
  for (const order of state.orders) {
    const line = order.lines.find(item => item.id === lineId)
    if (line) return { order, line }
  }
  throw new Error('订单明细不存在')
}

export function integer(value, name = '数量', allowZero = false) {
  if ((typeof value !== 'number' && typeof value !== 'string') || String(value).trim() === '') throw new Error(`请填写${name}`)
  const qty = Number(value)
  if (!Number.isFinite(qty) || !Number.isInteger(qty) || qty < (allowZero ? 0 : 1) || qty > 1000000) {
    throw new Error(`${name}须为${allowZero ? '非负' : '正'}整数，且不超过 1,000,000`)
  }
  return qty
}

export function balance(state, product, orderId) {
  const reserved = state.orders.flatMap(order => order.lines).filter(line => line.product === product).reduce((sum, line) => sum + line.reserved, 0)
  const own = state.orders.find(order => order.id === orderId)?.lines.filter(line => line.product === product).reduce((sum, line) => sum + line.reserved, 0) || 0
  return { physical: state.stock[product], reserved, own, others: reserved - own, free: Math.max(0, state.stock[product] - reserved) }
}

export function lineNumbers(state, line) {
  const planned = state.tasks.reduce((sum, task) => sum + (task.allocations[line.id] || 0), 0)
  return { remaining: Math.max(0, line.qty - line.shipped), gap: Math.max(0, line.qty - line.shipped - line.reserved), planned }
}

export function orderStage(order) {
  if (order.legacy) return '历史已完成'
  if (order.lines.every(line => line.shipped >= line.qty)) return '已完成'
  if (order.lines.some(line => line.shipped > 0)) return '部分出货'
  return '待出货'
}

export function taskStage(task) {
  if (task.status === 'pending') return '待发出'
  return task.received + task.loss >= task.qty ? '任务结清' : '加工中'
}

export function materialNeeds(state, orderId) {
  const order = state.orders.find(o => o.id === orderId)
  if (!order || order.legacy) return []
  return state.tasks.filter(t => t.type === 'handcraft').flatMap(task => order.lines.flatMap(line =>
    (demoBom[line.product] || []).flatMap(bom => {
      const id = `${task.id}:${line.id}:${bom.material}`
      const source = state.materialSources[id] || { stock: 0, issued: 0, plating: {} }
      const quantity = task.allocations[line.id] || 0
      if (!quantity && !source.stock && !source.issued && !Object.values(source.plating).some(qty => qty > 0)) return []
      const required = quantity * bom.per
      const planned = Object.values(source.plating).reduce((n, qty) => n + qty, 0)
      const ready = source.stock + source.issued
      const uncovered = Math.max(0, required - ready - planned)
      const review = ready + planned > required
      return [{ id, task, line, material: bom.material, per: bom.per, quantity, required, source, planned, ready, uncovered,
        waiting: Math.max(0, required - ready), review,
        stage: review ? '安排有变，需核对' : source.issued >= required && required > 0 ? '已发料' : ready >= required ? '现货已备齐' : uncovered ? '备料未安排齐' : '等待电镀回收' }]
    })))
}

export function materialAvailability(state, material, except = '') {
  const used = Object.entries(state.materialSources).filter(([id]) => id !== except && id.split(':')[2] === material)
    .reduce((n, [, source]) => n + source.stock, 0)
  return Math.max(0, state.materialStock[material] - used)
}

export function materialPlatingUsed(state, taskId, except = '') {
  return Object.entries(state.materialSources).filter(([id]) => id !== except)
    .reduce((n, [, source]) => n + (source.plating[taskId] || 0), 0)
}

export function saveMaterialSourcing(state, orderId, id, values) {
  const need = materialNeeds(state, orderId).find(row => row.id === id)
  if (!need || need.task.status !== 'pending') throw new Error('只能调整本单待发出手工任务的配件备料')
  const stock = integer(values.stock, '现货安排数量', true)
  if (stock > materialAvailability(state, need.material, id)) throw new Error('配件公共可用不足，不能占用其他备料安排')
  const plating = {}
  for (const [taskId, value] of Object.entries(values.plating || {})) {
    const qty = integer(value, '电镀安排数量', true)
    const task = state.materialTasks.find(t => t.id === taskId)
    if (!task || task.material !== need.material) throw new Error('电镀目标配件与 BOM 需求不匹配')
    if (qty > Math.max(0, task.qty - task.received - task.loss - materialPlatingUsed(state, taskId, id))) throw new Error('电镀剩余计划不足，其他订单的安排不可覆盖')
    if (qty) plating[taskId] = qty
  }
  if (stock + need.source.issued + Object.values(plating).reduce((n, qty) => n + qty, 0) > need.required) throw new Error('备料安排不能超过本次 BOM 需求')
  state.materialSources[id] = { stock, issued: need.source.issued, plating }
  event(state, '配件备料安排已更新', `${orderId} · ${need.task.id} · ${materials[need.material].name}；仅调整计划，未发料、未入库、不改变成品进度`)
}

export function reserveLine(state, lineId, amount) {
  const { order, line } = locateLine(state, lineId)
  if (order.legacy) throw new Error('历史单据只读，不自动调整库存')
  const qty = integer(amount)
  const gap = lineNumbers(state, line).gap
  if (qty > gap) throw new Error(`最多还需预留 ${gap} ${products[line.product].unit}`)
  if (qty > balance(state, line.product).free) throw new Error('公共可用库存不足，不能占用其他订单的预留')
  line.reserved += qty
  event(state, '库存已预留', `${order.id} · ${products[line.product].name} ${qty} ${products[line.product].unit}；实物库存不变`)
}

export function releaseLine(state, lineId, amount) {
  const { order, line } = locateLine(state, lineId)
  if (order.legacy) throw new Error('历史单据只读')
  const qty = integer(amount)
  if (qty > line.reserved) throw new Error('取消预留数量不能超过本行已预留数量')
  line.reserved -= qty
  event(state, '已取消库存预留', `${order.id} · 取消预留 ${qty} ${products[line.product].unit}，恢复公共可用；实物库存不变`)
}

export function saveAllocation(state, taskId, values) {
  const task = state.tasks.find(item => item.id === taskId)
  if (!task) throw new Error('加工明细不存在')
  const next = {}
  for (const [lineId, value] of Object.entries(values)) {
    const { order, line } = locateLine(state, lineId)
    if (order.legacy || line.product !== task.product) throw new Error('只能分配给产品一致的有效订单明细')
    const qty = integer(value, '安排数量', true)
    const otherPlans = lineNumbers(state, line).planned - (task.allocations[lineId] || 0)
    // Existing plans remain historical arrangements after shipping; only new increases need open demand.
    const capacity = Math.max(task.allocations[lineId] || 0, line.qty - line.shipped - otherPlans)
    if (qty > capacity) throw new Error(`${order.id} 此明细最多可安排 ${capacity}，不能重复覆盖需求`)
    if (qty) next[lineId] = qty
  }
  if (Object.values(next).reduce((sum, qty) => sum + qty, 0) > task.qty) throw new Error('分配总量超过本条加工计划；请先明确调整加工计划')
  task.allocations = next
  event(state, '生产需求分配已更新', `${taskId} · 未分配部分保留为公共备库存，不移动实物库存`)
}

export function arrangeHandcraft(state, { lineId, qty: amount, supplier, targetId = 'new' }) {
  const { order, line } = locateLine(state, lineId)
  if (order.legacy) throw new Error('历史订单只读')
  const qty = integer(amount, '制作数量')
  if (line.product === 'chain') throw new Error('此示例配件请从电镀任务安排')
  const open = Math.max(0, line.qty - line.shipped - lineNumbers(state, line).planned)
  if (qty > open) throw new Error(`尚未安排的需求只有 ${open}，请勿重复安排`)
  if (!supplier?.trim()) throw new Error('请选择手工商家')
  let task
  if (targetId !== 'new') {
    task = state.tasks.find(item => item.id === targetId)
    if (!task || task.status !== 'pending' || task.type !== 'handcraft' || task.supplier !== supplier || task.product !== line.product) throw new Error('只能追加到同商家、同产品的待发出明细')
    task.qty += qty
    task.allocations[lineId] = (task.allocations[lineId] || 0) + qty
  } else {
    task = { id: `HC-${String(state.nextTask++).padStart(4, '0')}`, type: 'handcraft', supplier, date: '2026-11-18', product: line.product, qty, received: 0, loss: 0, status: 'pending', allocations: { [lineId]: qty } }
    state.tasks.push(task)
  }
  event(state, targetId === 'new' ? '新建待发出手工任务' : '经确认追加到手工任务', `${order.id} → ${task.id} · ${qty} ${products[line.product].unit}；未发料、未扣库`)
  return task
}

export function saveOrderAllocation(state, taskId, orderId, values) {
  const order = state.orders.find(item => item.id === orderId)
  const task = state.tasks.find(item => item.id === taskId)
  if (!order || order.legacy) throw new Error('只能调整当前有效客户订单的生产需求')
  if (!task) throw new Error('加工明细不存在')
  for (const lineId of Object.keys(values)) {
    if (!order.lines.some(line => line.id === lineId)) throw new Error('本单分配不能修改其他订单的需求')
  }
  // Preserve every allocation outside the current order; shared task capacity still applies.
  saveAllocation(state, taskId, { ...task.allocations, ...values })
}

export function receiveStock(state, { product, qty: amount, reason, note }) {
  if (!products[product]) throw new Error('请选择产品')
  const qty = integer(amount, '真实入库数量')
  if (!['历史现货补录', '外购成品', '盘点补录'].includes(reason)) throw new Error('请选择真实来源')
  if (!note?.trim()) throw new Error('请填写来源说明，不能为出货自动造库存')
  state.stock[product] += qty
  const receipt = { id: `IN-${String(state.nextReceipt++).padStart(4, '0')}`, product, qty, reason, note, date: '2026-11-18' }
  state.receipts.unshift(receipt)
  event(state, '真实现货已登记入库', `${receipt.id} · ${products[product].name} ${qty} ${products[product].unit} · ${reason}`)
  return receipt
}

export function receiveTask(state, taskId, amount) {
  const task = state.tasks.find(item => item.id === taskId)
  if (!task || task.status === 'pending') throw new Error('待发出任务不可登记回收；请先实际确认发出')
  const qty = integer(amount, '本次实收数量')
  task.received += qty
  state.stock[task.product] += qty
  event(state, '加工实收已入公共库存', `${task.id} · 实收 ${qty} ${products[task.product].unit}；未自动分给客户，不改变已出货`)
}

export function checkShipment(state, orderId, entries, stockCheck = false) {
  const order = state.orders.find(item => item.id === orderId)
  if (!order || order.legacy) throw new Error('请选择新流程有效订单；历史单据只读')
  if (!entries.length) throw new Error('请至少选择一条订单明细并填写本次出货数量')
  const seen = new Set()
  const byProduct = {}
  const ownByProduct = {}
  for (const entry of entries) {
    if (seen.has(entry.lineId)) throw new Error('同一订单明细不可重复添加')
    seen.add(entry.lineId)
    const line = order.lines.find(item => item.id === entry.lineId)
    if (!line) throw new Error('出货明细必须属于当前客户订单')
    const qty = integer(entry.qty, '本次出货数量')
    if (qty > line.qty - line.shipped) throw new Error(`${products[line.product].name} 超过订单剩余待出货数量`)
    byProduct[line.product] = (byProduct[line.product] || 0) + qty
    ownByProduct[line.product] = (ownByProduct[line.product] || 0) + Math.min(line.reserved, qty)
  }
  if (stockCheck) {
    for (const [product, qty] of Object.entries(byProduct)) {
      const b = balance(state, product, orderId)
      const available = ownByProduct[product] + b.free
      if (qty > available) throw new Error(`${products[product].name} 可出货库存不足（所选明细预留 + 公共可用 ${available}），不能占用其他明细或订单库存`)
    }
  }
  return order
}

export function saveDraft(state, { orderId, lines, note = '', tracking = '' }) {
  checkShipment(state, orderId, lines)
  const draft = { id: `SH-${String(state.nextShipment++).padStart(4, '0')}`, orderId, status: 'draft', date: '2026-11-18', lines: lines.map(item => ({ lineId: item.lineId, qty: Number(item.qty) })), note, tracking }
  state.shipments.unshift(draft)
  event(state, '出货草稿已保存', `${draft.id} · 不扣库、不占库存，确认时重新校验`)
  return draft
}

export function confirmShipment(state, shipmentId) {
  const shipment = state.shipments.find(item => item.id === shipmentId)
  if (!shipment) throw new Error('出货单不存在')
  if (shipment.status === 'confirmed') return shipment // idempotent
  if (shipment.status !== 'draft') throw new Error('已作废草稿不可确认')
  const order = checkShipment(state, shipment.orderId, shipment.lines, true)
  // Validate every row before mutation. Reservations stay tied to exact order-line identities.
  for (const entry of shipment.lines) {
    const line = order.lines.find(item => item.id === entry.lineId)
    const take = Math.min(line.reserved, entry.qty)
    line.reserved -= take
    state.stock[line.product] -= entry.qty
    line.shipped += entry.qty
  }
  shipment.status = 'confirmed'
  event(state, orderStage(order) === '已完成' ? '全部出货，订单自动完成' : '分批出货已确认', `${shipment.id} · ${order.id}；实际库存已扣减，不要求加工单关联`)
  return shipment
}

export function voidDraft(state, shipmentId) {
  const draft = state.shipments.find(item => item.id === shipmentId)
  if (!draft || draft.status !== 'draft') throw new Error('仅草稿可以作废；已出货的真实退货需单独登记')
  draft.status = 'void'
  event(state, '出货草稿已作废', `${shipmentId} · 无库存变动`)
}

function event(state, title, detail) {
  state.events.unshift({ title, detail, time: '刚刚 · Demo' })
}
