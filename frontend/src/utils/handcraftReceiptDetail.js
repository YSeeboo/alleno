import { handcraftSourceKey, filterHandcraftReceiptSources } from './handcraftReceiptCreate.js'
import { summarizePlatingReceipt } from './platingReceiptDetail.js'

export function handcraftReceiptSourceParams(receipt) {
  const items = receipt.items || []
  return {
    supplier_name: receipt.supplier_name,
    include_settled: true,
    exclude_part_item_ids: items.map(row => row.handcraft_part_item_id).filter(id => id != null),
    exclude_jewelry_item_ids: items.map(row => row.handcraft_jewelry_item_id).filter(id => id != null),
  }
}

export function filterAddReceiptSources(sources, { kind, selectedOnly, ...filters }) {
  const scoped = sources.filter(row => kind === 'all' || row.is_output === (kind === 'output'))
  return filterHandcraftReceiptSources(scoped, { ...filters, progress: selectedOnly ? 'selected' : 'all' })
}

// The detail API has always accepted optional price and weight on both source types.
export function additionalReceiptPayload(sources, inputs) {
  return { items: sources.map(row => {
    const input = inputs[handcraftSourceKey(row)]
    const label = row.item_name || row.item_id
    const qty = input?.qty
    if (!Number.isFinite(qty) || qty <= 0) throw new Error(`请填写「${label}」的实际回收数量`)
    if (row.is_output && !Number.isSafeInteger(qty)) throw new Error(`「${label}」的产出回收数量必须为正整数`)
    if (!row.is_output && Number(qty.toFixed(4)) !== qty) throw new Error(`「${label}」的配件回收数量最多保留 4 位小数`)
    for (const [field, name] of [['price', '手工单价'], ['weight', '重量']]) {
      if (input[field] != null && (!Number.isFinite(input[field]) || input[field] < 0)) throw new Error(`「${label}」的${name}必须为非负数，或留空`)
    }
    return {
      [row.is_output ? 'handcraft_jewelry_item_id' : 'handcraft_part_item_id']: row.id,
      qty, unit: input.unit, price: input.price ?? null, weight: input.weight ?? null,
      weight_unit: input.weight == null ? null : input.weight_unit || 'g',
    }
  }) }
}

export function summarizeHandcraftReceiptDetail(items) {
  const { quantities, weightKg } = summarizePlatingReceipt(items)
  const outputCount = items.filter(row => row.handcraft_jewelry_item_id != null).length
  return { quantities, weightKg, outputCount, partCount: items.length - outputCount }
}
