// Standalone design fixtures. No business API, credentials or persisted state.
export const SCENES = [
  { id: 'order', label: '订单 · 添加商品', title: '批量添加商品', context: '订单详情 / OR-20261122-018 / 商品明细', eyebrow: 'ORDER / PRODUCT LINES', description: '先选商品，再填写订购数量和单价；客户货号不在添加时填写，可在订单详情中统一维护。', kinds: ['jewelry', 'part'], fields: ['qty', 'unit', 'price'], note: '同款可点“再加一行”分开录入；不同单位分别统计。添加不会扣料、预留或出货。', impact: '每一行独立保存数量与单价，不自动合并同款。客户货号可在订单详情中统一维护。' },
  { id: 'plating', label: '电镀单 · 增加配件', title: '批量增加电镀配件', context: '电镀单详情 / PL-20261122-006 / 电镀明细', eyebrow: 'PLATING / OUTGOING PARTS', description: '按行设置发出数量和电镀颜色，核对颜色对应配件后，再统一加入明细。', kinds: ['part'], fields: ['qty', 'unit', 'color'], note: '颜色对应配件按行核对；缺少对应配件时提示处理，不自动新建。', impact: '本次仅增加待发出明细，不自动确认发出或改变库存。' },
  { id: 'output', label: '手工单 · 添加产出', title: '批量添加产出', context: '手工单详情 / HC-20261122-012 / 制作产出', eyebrow: 'HANDCRAFT / OUTPUT', description: '可跨“饰品 / 组合配件”选择产出，逐行填写数量，单位默认沿用商品资料。', kinds: ['jewelry', 'assembly'], fields: ['qty', 'unit'], note: '跨类型切换不丢失已选项；产出关联材料的影响将在待添加区提示。', impact: '演示：新增产出会关联其 BOM 材料。正式开发需区分已有 / 新增材料，不重复追加。' },
  { id: 'material', label: '手工单 · 添加配件', title: '批量添加配件', context: '手工单详情 / HC-20261122-012 / 配件明细', eyebrow: 'HANDCRAFT / MATERIALS', description: '勾选本次需要的配件，批量填数量；每行还可单独填写重量与备注。', kinds: ['part'], fields: ['qty', 'unit'], note: '本提案演示“从配件库选择”；原有“最近导入”批量入口保留，不用这个方案替代。', impact: '保留配件资料中的默认单位；重量为可选项，不填写时保持为空。' },
  { id: 'bom', label: '饰品 · 添加 BOM 配件', title: '批量添加 BOM 配件', context: '饰品详情 / J-1001 珍珠叠戴项链 / BOM 用料', eyebrow: 'JEWELRY / BILL OF MATERIALS', description: '为每 1 条饰品设置配件用量，支持 4 位小数。只维护独立 BOM，不改变库存。', kinds: ['part'], fields: ['qty', 'unit'], note: '这里填写的是“每 1 条饰品用多少”，不是采购数量。已在 BOM 中的配件不能重复加入。', impact: '只更新当前饰品的独立 BOM，不调整库存，也不回写其他商品的用料。' },
  { id: 'purchase', label: '采购单 · 追加配件', title: '批量追加采购配件', context: '采购单详情 / PO-20261122-009 / 采购明细', eyebrow: 'PURCHASE / PARTS', description: '补充发现的同类入口：可一次选择多项配件，再逐行填写数量、单价和备注。', kinds: ['part'], fields: ['qty', 'unit', 'price'], note: '采购数量、单位、7 位小数单价分别维护；单据状态与成本确认在正式开发中保留。', impact: '这里仅模拟追加配件的交互；不会真实入库或更新配件成本。' },
]

export const PLANS = [
  { id: 'A', name: '左选右编', short: '边挑边填，已选明细始终可见', description: '左侧配件库 + 右侧可编辑清单。选品、数量和业务字段同屏完成，适合大多数日常添加。', fit: '推荐作为通用方案' },
  { id: 'B', name: '图片选品', short: '先看款式，暂存后统一完善', description: '大图卡片识别款式，底部暂存已选商品；点“完善明细”集中填写。适合看图挑饰品。', fit: '适合款式辨识优先' },
  { id: 'C', name: '分步批量', short: '先选一批，再专心填写明细', description: '第一步只选品，第二步用宽表核对和填写。信息不挤在一起，更适合字段多、一次添加多项。', fit: '适合电镀、订单等复杂录入' },
]

export const KIND_LABELS = { jewelry: '饰品', part: '配件', assembly: '组合配件' }
// Match the existing plating page's common / more color chips (services/part.py).
export const COLORS = [
  { value: 'G', label: '金色', common: true },
  { value: 'S', label: '白K', common: true },
  { value: 'RG', label: '玫瑰金', common: true },
  { value: 'K14', label: '14K金', common: false },
  { value: 'SV', label: '银色', common: false },
]
export const PRODUCTS = [
  { id: 'J-1001', name: '珍珠叠戴项链', kind: 'jewelry', unit: '条', price: '32.5', stock: 128, bomCount: 4, shape: 'necklace', tone: 'pearl' },
  { id: 'J-1002', name: '圆环珍珠耳饰', kind: 'jewelry', unit: '对', price: '18.8', stock: 260, bomCount: 3, shape: 'earrings', tone: 'pearl' },
  { id: 'J-1003', name: '细链锆石手链', kind: 'jewelry', unit: '条', price: '15.6', stock: 86, bomCount: 3, shape: 'bracelet', tone: 'gold' },
  { id: 'J-1004', name: '蝴蝶吊坠项链', kind: 'jewelry', unit: '条', price: '26', stock: 72, bomCount: 5, shape: 'necklace', tone: 'gold' },
  { id: 'J-1005', name: '花瓣镶钻耳钉', kind: 'jewelry', unit: '对', price: '21.2', stock: 190, bomCount: 4, shape: 'earrings', tone: 'silver' },
  { id: 'J-1006', name: '双层链条手链', kind: 'jewelry', unit: '条', price: '16.8', stock: 140, bomCount: 2, shape: 'bracelet', tone: 'silver' },
  { id: 'P-2001', name: '龙虾扣 12mm', kind: 'part', unit: '个', price: '0.1234567', stock: 8600, shape: 'clasp', tone: 'gold', colors: ['G', 'S', 'RG', 'K14', 'SV'], existingBom: true },
  { id: 'P-2002', name: '开口圈 5mm', kind: 'part', unit: '个', price: '0.025', stock: 24000, shape: 'rings', tone: 'gold', colors: ['G', 'S', 'RG', 'K14', 'SV'] },
  { id: 'P-2003', name: '天然淡水珍珠 6mm', kind: 'part', unit: '颗', price: '0.85', stock: 6800, shape: 'pearls', tone: 'pearl', colors: ['G'] },
  { id: 'P-2004', name: '细蛇骨链 1.2mm', kind: 'part', unit: '米', price: '2.68', stock: 1560, shape: 'chain', tone: 'silver', colors: ['G', 'S'] },
  { id: 'P-2005', name: '水滴锆石吊坠', kind: 'part', unit: '个', price: '1.35', stock: 3200, shape: 'pendant', tone: 'silver', colors: ['G', 'S', 'RG', 'K14', 'SV'] },
  { id: 'P-2006', name: '耳针 925 银', kind: 'part', unit: '对', price: '0.68', stock: 9800, shape: 'pins', tone: 'silver', colors: ['G', 'S', 'RG', 'K14', 'SV'] },
  { id: 'P-2007', name: '延长链 5cm', kind: 'part', unit: '条', price: '0.36', stock: 5200, shape: 'chain', tone: 'gold', colors: ['G', 'S', 'RG', 'K14', 'SV'] },
  { id: 'P-2008', name: '贝壳花片 10mm', kind: 'part', unit: '片', price: '0.52', stock: 4100, shape: 'flower', tone: 'pearl', colors: ['G', 'S'] },
  { id: 'C-3001', name: '珍珠耳坠组合件', kind: 'assembly', unit: '对', price: '3.6', stock: 520, bomCount: 3, shape: 'earrings', tone: 'pearl' },
  { id: 'C-3002', name: '镶钻花朵组合件', kind: 'assembly', unit: '个', price: '2.2', stock: 760, bomCount: 4, shape: 'flower', tone: 'gold' },
]

export function sceneProducts(scene) {
  return PRODUCTS.filter(product => scene.kinds.includes(product.kind))
}
export function unavailable(product, scene) {
  return scene.id === 'bom' && product.existingBom === true
}
export function makeRow(product, scene, key) {
  return { key, productId: product.id, qty: scene.id === 'bom' ? '1' : '100', unit: product.unit, price: product.price, color: 'G', weight: '', weightUnit: 'kg', note: '' }
}
export function rowErrors(row, scene) {
  const errors = [], product = PRODUCTS.find(item => item.id === row.productId)
  if (!product || !scene.kinds.includes(product.kind) || unavailable(product, scene)) return ['当前场景不可添加此商品']
  if (scene.id === 'bom') {
    if (!/^\d+(?:\.\d{1,4})?$/.test(row.qty) || Number(row.qty) <= 0 || Number(row.qty) > 999999.9999) errors.push('每单位用量须大于 0，最多 4 位小数')
  } else if (!/^\d+$/.test(row.qty) || Number(row.qty) < 1 || !Number.isSafeInteger(Number(row.qty))) errors.push('请填写大于 0 的整数数量')
  if (scene.fields.includes('price') && !/^\d+(?:\.\d{1,7})?$/.test(row.price)) errors.push('请填写非负单价，最多 7 位小数（可填 0）')
  if (!row.unit.trim()) errors.push('请选择单位')
  if (scene.id === 'plating' && !product.colors?.includes(row.color)) errors.push(`${row.color} 对应配件尚未建立，请先处理对应配件或改选颜色`)
  if (['plating', 'material', 'output'].includes(scene.id) && row.weight !== '' && (!/^\d+(?:\.\d+)?$/.test(row.weight) || !Number.isFinite(Number(row.weight)) || Number(row.weight) < 0)) errors.push('重量须为空或非负数')
  return errors
}

// Integer fixed-point demo totals, preserving the application's seven price decimals.
export function lineAmount(row) {
  if (!/^\d+$/.test(row.qty) || !/^\d+(?:\.\d{1,7})?$/.test(row.price)) return null
  const [whole, fraction = ''] = row.price.split('.')
  return (BigInt(whole) * 10000000n + BigInt(fraction.padEnd(7, '0'))) * BigInt(row.qty)
}
export function money(value) {
  if (value === null) return '待填写'
  const rounded = (value + 50000n) / 100000n
  return `${(rounded / 100n).toLocaleString('zh-CN')}.${String(rounded % 100n).padStart(2, '0')}`
}
export function quantitySummary(rows) {
  const grouped = new Map()
  for (const row of rows) {
    const qty = Number(row.qty)
    if (row.qty.trim() && Number.isFinite(qty) && qty > 0) grouped.set(row.unit, (grouped.get(row.unit) || 0) + qty)
  }
  return [...grouped].map(([unit, qty]) => `${Number(qty.toFixed(4)).toLocaleString('zh-CN')} ${unit}`).join(' / ') || '尚未填写数量'
}

export function productImage(product) {
  const gold = product.tone === 'silver' ? '#aeb9bb' : '#b99b60', shadow = product.tone === 'silver' ? '#7e8e93' : '#967b42'
  const pearl = (x, y, r = 7) => `<circle cx="${x}" cy="${y}" r="${r}" fill="url(#pearl)" stroke="#d9d3c5" stroke-width=".8"/>`
  const ring = (x, y, r, ry = r) => `<ellipse cx="${x}" cy="${y}" rx="${r}" ry="${ry}" fill="none" stroke="url(#metal)" stroke-width="3.5"/>`
  let artwork = ''
  if (product.shape === 'necklace') {
    artwork = `<path d="M43 24 C30 111 130 111 117 24" fill="none" stroke="url(#metal)" stroke-width="2.8"/><path d="M51 22 C36 97 124 97 109 22" fill="none" stroke="${gold}" stroke-width="1.4"/>`
    if (product.tone === 'pearl') artwork += Array.from({ length: 13 }, (_, i) => { const a = Math.PI * (.13 + i * .74 / 12); return pearl(80 - 36 * Math.cos(a), 36 + 48 * Math.sin(a), 4.6) }).join('')
    else artwork += `<path d="M80 86 Q59 64 67 88 Q57 105 80 96 Q102 104 93 87 Q99 65 80 86Z" fill="url(#metal)"/><circle cx="80" cy="91" r="3" fill="#fcfcf4"/>`
  } else if (product.shape === 'earrings') artwork = [55, 105].map(x => `${ring(x, 51, 15, 20)}${pearl(x, 79, 10)}<circle cx="${x}" cy="30" r="3.5" fill="${gold}"/>`).join('')
  else if (product.shape === 'bracelet') artwork = `${ring(80, 62, 36, 29)}${ring(80, 64, 33, 26)}${pearl(107, 80, 6)}<path d="M42 50L50 42M106 39L115 46" stroke="#f1e2bb" stroke-width="4"/>`
  else if (product.shape === 'clasp') artwork = `<g transform="rotate(28 80 60)"><path d="M75 35 C48 35 48 83 75 84 C96 86 102 58 90 45 L83 50 C92 66 83 77 75 74 C62 72 63 45 76 45Z" fill="url(#metal)" stroke="${shadow}" stroke-width="1"/>${ring(76, 27, 7)}${ring(75, 93, 6)}<path d="M86 44L95 37" stroke="${gold}" stroke-width="5" stroke-linecap="round"/></g>`
  else if (product.shape === 'rings') artwork = `${ring(61, 48, 17)}${ring(95, 63, 18)}${ring(65, 83, 16)}`
  else if (product.shape === 'pearls') artwork = [[57, 44], [86, 42], [108, 64], [80, 71], [52, 78], [91, 96]].map(([x, y]) => pearl(x, y, 12)).join('')
  else if (product.shape === 'chain') artwork = Array.from({ length: 10 }, (_, i) => `<g transform="rotate(${i % 2 ? 35 : -25} ${43 + i * 8} ${42 + i * 4})">${ring(43 + i * 8, 42 + i * 4, 5, 9)}</g>`).join('')
  else if (product.shape === 'pendant') artwork = `${ring(80, 30, 5)}<path d="M80 36 C26 85 67 108 92 92 C118 77 91 48 80 36Z" fill="url(#metal)"/><path d="M80 43 C39 83 69 99 88 87 C107 75 88 52 80 43Z" fill="#e9ede6"/><path d="M80 44 L66 78 L88 88 L80 44 L99 76 L66 78" fill="none" stroke="#fff" stroke-width="1.3"/>`
  else if (product.shape === 'pins') artwork = [61, 100].map(x => `<path d="M${x} 48L${x + 8} 91" stroke="url(#metal)" stroke-width="3"/>${pearl(x, 43, 8)}${ring(x + 6, 83, 6, 3)}`).join('')
  else artwork = Array.from({ length: 5 }, (_, i) => `<ellipse cx="80" cy="48" rx="9" ry="17" transform="rotate(${i * 72} 80 64)" fill="${product.tone === 'pearl' ? 'url(#pearl)' : 'url(#metal)'}" stroke="#c9bd9b" stroke-width=".5"/>`).join('') + pearl(80, 64, 5)
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="160" height="124" viewBox="0 0 160 124"><defs><radialGradient id="bg"><stop stop-color="#faf8f1"/><stop offset="1" stop-color="#eeeae0"/></radialGradient><linearGradient id="metal" x2="1" y2="1"><stop stop-color="${shadow}"/><stop offset=".35" stop-color="${gold}"/><stop offset=".55" stop-color="#f2e7c9"/><stop offset=".8" stop-color="${gold}"/><stop offset="1" stop-color="${shadow}"/></linearGradient><radialGradient id="pearl" cx=".32" cy=".3"><stop stop-color="#fffef9"/><stop offset=".5" stop-color="#f6f3e7"/><stop offset="1" stop-color="#cfc9ba"/></radialGradient></defs><rect width="160" height="124" fill="url(#bg)"/><ellipse cx="80" cy="105" rx="38" ry="4" fill="#bfb59a" opacity=".11"/>${artwork}</svg>`
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}
