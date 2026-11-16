export function remainingReceiptQuantity(item) {
  return Number((Number(item.qty) - Number(item.received_qty || 0)).toFixed(4))
}

export function createReceiptInput(item) {
  return { qty: remainingReceiptQuantity(item), price: null, weight: null, unit: item.unit || '个' }
}

// Filter the vendor's complete pending list, not the selected receipt rows.
export function filterPendingReceiptItems(items, keyword, dateOn) {
  const tokens = String(keyword || '').trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  return items.filter((item) => {
    const fields = [item.part_id, item.part_name, item.receive_part_id, item.receive_part_name]
      .map((value) => String(value || '').toLocaleLowerCase())
    return (!dateOn || item.created_at?.slice(0, 10) === dateOn)
      && tokens.every((token) => fields.some((field) => field.includes(token)))
  })
}

const isNumber = (value) => value != null && value !== '' && Number.isFinite(Number(value))

// Display-only calculation: the server rounds price, then each line amount to
// seven places (ROUND_HALF_UP). Sum those rounded lines, not floating products.
function scaled(value, places) {
  if (!isNumber(value) || Number(value) < 0) return null
  const match = String(value).match(/^(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$/i)
  if (!match) return null
  const fraction = match[2] || ''
  const exponent = Number(match[3] || 0) - fraction.length + places
  if (Math.abs(exponent) > 40) return null
  const digits = BigInt(match[1] + fraction)
  if (exponent >= 0) return digits * 10n ** BigInt(exponent)
  const divisor = 10n ** BigInt(-exponent)
  return (digits + divisor / 2n) / divisor
}

const fixedAmount = (value) => `${value / 10000000n}.${String(value % 10000000n).padStart(7, '0')}`

export function receiptLineAmount(input) {
  const qty = scaled(input?.qty, 4)
  const price = scaled(input?.price, 7)
  if (qty == null || qty <= 0n || price == null) return null
  return fixedAmount((qty * price + 5000n) / 10000n)
}

export function summarizeReceiptDraft(items, inputs) {
  const quantities = new Map()
  let amount = 0n
  let unpricedCount = 0
  for (const item of items) {
    const input = inputs[item.id]
    const unit = input?.unit || item.unit || '个'
    const qty = isNumber(input?.qty) && Number(input.qty) > 0 ? Number(input.qty) : 0
    quantities.set(unit, (quantities.get(unit) || 0) + qty)
    const line = receiptLineAmount(input)
    if (line == null) unpricedCount++
    else amount += scaled(line, 7)
  }
  return {
    quantities: [...quantities].map(([unit, qty]) => ({ unit, qty: Number(qty.toFixed(4)) })),
    amount: fixedAmount(amount),
    unpricedCount,
  }
}

export function receiptItemPayload(item, input, vendor) {
  const label = item.receive_part_name || item.part_name || item.part_id
  if (item._unavailable) throw new Error(`「${label}」已不在待回收列表，请移除后重新选择`)
  if (item.supplier_name !== vendor) throw new Error(`「${label}」不属于当前商家，请重新选择`)
  if (!isNumber(input?.qty) || Number(input.qty) <= 0) throw new Error(`请填写「${label}」的回收数量`)
  const qty = Number(input.qty)
  if (Math.abs(qty * 10000 - Math.round(qty * 10000)) > 0.000001) throw new Error(`「${label}」的数量最多保留 4 位小数`)
  if (qty > remainingReceiptQuantity(item)) throw new Error(`「${label}」最多可回收 ${remainingReceiptQuantity(item)} ${item.unit || '个'}`)
  for (const [key, name] of [['price', '单价'], ['weight', '重量']]) {
    if (input[key] != null && (!isNumber(input[key]) || Number(input[key]) < 0)) {
      throw new Error(`「${label}」的${name}须为不小于 0 的数字，或留空`)
    }
  }
  return {
    plating_order_item_id: item.id,
    part_id: item.receive_part_id || item.part_id,
    qty,
    weight: input.weight == null ? null : Number(input.weight),
    weight_unit: input.weight == null ? null : (item.weight_unit || 'g'),
    price: input.price == null ? null : Number(input.price),
    unit: input.unit || item.unit || '个',
  }
}
