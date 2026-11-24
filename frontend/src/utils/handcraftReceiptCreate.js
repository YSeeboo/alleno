import { remainingQuantity } from './receiptQuantity.js'
// Reuse the existing receipt calculation: price and each line round to 7 places.
import { receiptLineAmount, summarizeReceiptDraft } from './platingReceiptCreate.js'

export const handcraftSourceKey = item => `${item.is_output ? 'output' : 'material'}_${item.id}`
export const createHandcraftReceiptInput = item => ({
  qty: remainingQuantity(item) || null,
  price: null,
  weight: null,
  weight_unit: 'g',
  unit: item.unit || '个',
})

export function filterHandcraftReceiptSources(items, { keyword = '', dateOn = null, progress = 'all', selectedKeys = new Set() } = {}) {
  const tokens = keyword.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  return items.filter(item => {
    const fields = [item.item_name, item.item_id, item.handcraft_order_id, item.color].map(value => String(value || '').toLocaleLowerCase())
    return (!dateOn || item.created_at?.slice(0, 10) === dateOn)
      && (progress !== 'remaining' || remainingQuantity(item) > 0)
      && (progress !== 'selected' || selectedKeys.has(handcraftSourceKey(item)))
      && tokens.every(token => fields.some(field => field.includes(token)))
  })
}

export const handcraftReceiptLineAmount = receiptLineAmount
export function summarizeHandcraftReceipt(items, inputs) {
  const summary = summarizeReceiptDraft(items.map(item => ({ ...item, id: handcraftSourceKey(item) })), inputs)
  return {
    ...summary,
    overCount: items.filter(item => Number(inputs[handcraftSourceKey(item)]?.qty || 0) > remainingQuantity(item)).length,
  }
}

const isNumber = value => value != null && value !== '' && Number.isFinite(Number(value))
export function handcraftReceiptItemPayload(item, input, supplier) {
  const label = item.item_name || item.item_id || '明细'
  if (item._unavailable) throw new Error(`「${label}」来源已不可用，请移除后重新选择`)
  if (item.supplier_name !== supplier) throw new Error(`「${label}」不属于当前商家，请重新选择`)
  if (!isNumber(input?.qty) || Number(input.qty) <= 0) throw new Error(`请填写「${label}」的实际回收数量`)
  const qty = Number(input.qty)
  if (item.is_output && !Number.isSafeInteger(qty)) throw new Error(`「${label}」的产出回收数量必须为正整数`)
  if (!item.is_output && Math.abs(qty * 10000 - Math.round(qty * 10000)) > 0.000001) throw new Error(`「${label}」的退料数量最多保留 4 位小数`)
  const payload = { [item.is_output ? 'handcraft_jewelry_item_id' : 'handcraft_part_item_id']: item.id, qty, unit: item.unit || '个' }
  if (!item.is_output) return payload
  for (const [key, name] of [['price', '单价'], ['weight', '重量']]) {
    if (input[key] != null && (!isNumber(input[key]) || Number(input[key]) < 0)) throw new Error(`「${label}」的${name}须为非负数，或留空`)
  }
  if (input.weight != null && !['g', 'kg'].includes(input.weight_unit || 'g')) throw new Error(`请核对「${label}」的重量单位`)
  return {
    ...payload,
    price: input.price == null ? null : Number(input.price),
    weight: input.weight == null ? null : Number(input.weight),
    weight_unit: input.weight == null ? null : (input.weight_unit || 'g'),
  }
}
