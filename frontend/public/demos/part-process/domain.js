// Isolated, in-memory demo. No requests, database writes, or production imports.
export function initialState() {
  return {
    groups: [
      { id: 'flower', name: '五瓣小花', code: 'PJ-DZ-00001', category: '吊坠', material: '黄铜', size: '12 × 12 mm', unit: '个', shape: 'flower' },
      { id: 'hook', name: '基础耳钩', code: 'PJ-X-00002', category: '小配件', material: '铜', size: '18 mm', unit: '个', shape: 'hook' },
    ],
    parts: [
      { id: 'PJ-DZ-00001', group: 'flower', plating: '原坯', oil: '无', area: '', stock: 300 },
      { id: 'PJ-DZ-00001-G', group: 'flower', plating: '金色', oil: '无', area: '', stock: 200 },
      { id: 'DEMO-P-003', group: 'flower', plating: '金色', oil: '红色', area: '花瓣', stock: 24 },
      { id: 'DEMO-P-004', group: 'flower', plating: '金色', oil: '蓝色', area: '花瓣', stock: 36 },
      { id: 'PJ-X-00002', group: 'hook', plating: '原坯', oil: '无', area: '', stock: 300 },
      { id: 'PJ-X-00002-G', group: 'hook', plating: '金色', oil: '无', area: '', stock: 480 },
      { id: 'PJ-X-00002-S', group: 'hook', plating: '银色', oil: '无', area: '', stock: 160 },
    ],
    orders: [], logs: [], allocations: {}, quantity: 48,
    bom: [{ partId: 'DEMO-P-003', qty: 2 }, { partId: 'PJ-X-00002-G', qty: 2 }],
    serial: 8,
  };
}

export function getPart(state, id) {
  const part = state.parts.find(p => p.id === id);
  if (!part) throw new Error('配件不存在');
  return part;
}
export const specName = p => `${p.plating}${p.oil !== '无' ? ` · ${p.area}${p.oil}点油` : ' · 未点油'}`;
export const available = (state, id) => getPart(state, id).stock - (state.allocations[id] || 0);
const clean = value => String(value ?? '').trim().replace(/\s+/g, ' ');
function positive(value) {
  if (!Number.isSafeInteger(value) || value <= 0) throw new Error('数量必须为正整数');
}

export function createSpec(state, values) {
  const group = state.groups.find(g => g.id === values.group);
  if (!group) throw new Error('基础配件不存在');
  const plating = clean(values.plating), oil = clean(values.oil), area = oil === '无' ? '' : clean(values.area);
  if (!plating || !oil || (oil !== '无' && !area)) throw new Error('请完整填写电镀、点油颜色和点油部位');
  const existing = state.parts.find(p => p.group === group.id && p.plating === plating && p.oil === oil && p.area === area);
  if (existing) return { part: existing, created: false };
  const part = { id: `DEMO-P-${String(state.serial++).padStart(3, '0')}`, group: group.id, plating, oil, area, stock: 0 };
  state.parts.push(part);
  return { part, created: true };
}

export function sendProcessing(state, sourceId, targetId, qty) {
  positive(qty);
  const source = getPart(state, sourceId), target = getPart(state, targetId);
  if (source.id === target.id || source.group !== target.group) throw new Error('请选择同一基础款下、不同的发出和收回规格');
  if (available(state, sourceId) < qty) throw new Error('发出规格的可用库存不足，已分配数量不可再次发出');
  const order = { id: `DEMO-JG-${String(state.orders.length + 1).padStart(3, '0')}`, sourceId, targetId, qty, status: 'processing' };
  source.stock -= qty;
  state.orders.unshift(order);
  state.logs.unshift({ partId: sourceId, qty: -qty, reason: '加工发出', ref: order.id });
  return order;
}

export function receiveProcessing(state, id, good) {
  const order = state.orders.find(o => o.id === id);
  if (!order || order.status !== 'processing') throw new Error('此加工单已结清或不存在');
  if (!Number.isSafeInteger(good) || good < 0 || good > order.qty) throw new Error('合格收回数量必须为 0 到发出数量之间的整数');
  getPart(state, order.targetId).stock += good;
  Object.assign(order, { status: 'completed', good, loss: order.qty - good });
  if (good) state.logs.unshift({ partId: order.targetId, qty: good, reason: '加工收回', ref: order.id });
  return order;
}

export function requirements(state) {
  const totals = new Map();
  for (const row of state.bom) totals.set(row.partId, (totals.get(row.partId) || 0) + row.qty * state.quantity);
  return [...totals].map(([partId, need]) => ({
    part: getPart(state, partId), need,
    reserved: state.allocations[partId] || 0,
    available: available(state, partId),
    shortage: Math.max(0, need - getPart(state, partId).stock),
  }));
}
export function allocate(state) {
  const rows = requirements(state);
  if (rows.some(r => r.shortage > 0)) throw new Error('还有加工规格缺料，请先完成加工并收回');
  if (Object.keys(state.allocations).length) throw new Error('该订单已经分配，请先释放分配');
  state.allocations = Object.fromEntries(rows.map(r => [r.part.id, r.need]));
}
export function updateBom(state, partId, qty) {
  if (Object.keys(state.allocations).length) throw new Error('请先释放订单分配，再修改 BOM');
  positive(qty);
  const part = getPart(state, partId);
  if (part.group !== 'flower') throw new Error('请选择小花配件的具体规格');
  state.bom[0] = { partId, qty };
}
