// A creation payload always names a single exact customer-order line. Public
// production is the remaining plan on this NEW output, never physical stock.
export function orderHandcraftPayload({ line, supplier, planned, allocated, materials, targetId = null, note = '', requestKey }) {
  const qty = Number(allocated), total = Number(planned)
  const remaining = Number(line.quantity) - Number(line.allocated)
  if (!supplier?.trim()) throw new Error('请填写手工商家')
  if (!Number.isSafeInteger(qty) || qty <= 0 || qty >= 1000000000 || qty > remaining || !Number.isSafeInteger(total) || total >= 1000000000 || total < qty) throw new Error('请填写有效整数数量，本行安排不能超过剩余需求或整条产出')
  if (!line.unit || !['part', 'jewelry'].includes(line.product_type) || !line.product_id || !Number.isSafeInteger(line.id)) throw new Error('订单明细身份或商品单位不完整，请刷新核对')
  if (!materials.length || materials.some(r => !r.part_id || !r.unit || !/^\d+(?:\.\d{1,4})?$/.test(String(r.qty)) || Number(r.qty) <= 0 || Number(r.qty) >= 1000000)) throw new Error('请核对计划材料与单位；数量须为小于一百万、最多四位小数的正数')
  return { request_key: requestKey, order_item_id: line.id, allocated_quantity: qty,
    supplier_name: supplier.trim(), append_to_order_id: targetId, note,
    parts: materials.map(r => ({ part_id: r.part_id, qty: Number(r.qty), unit: r.unit })),
    jewelries: [{ [line.product_type === 'jewelry' ? 'jewelry_id' : 'part_id']: line.product_id, qty: total, unit: line.unit }] }
}
