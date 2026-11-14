import { isJewelryType, jewelryUnitOptions } from './jewelryOptions.js'

export function validBomQuantity(value) {
  return /^\d+(\.\d{1,4})?$/.test(String(value)) && Number(value) > 0 && Number(value) < 1000000
}

// Display-only row subtotal, matching the server's Decimal ROUND_HALF_UP at
// seven places. Authoritative material/total costs always come from the API.
export function bomSubtotal(unitCost, quantity) {
  if (unitCost == null || !validBomQuantity(quantity)) return null
  const match = String(unitCost).match(/^(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$/i)
  if (!match) return null
  const fraction = match[2] || ''
  const exponent = Number(match[3] || 0) - fraction.length + 3
  if (Math.abs(exponent) > 40) return null
  const digits = BigInt(match[1] + fraction)
  const [whole, decimal = ''] = String(quantity).split('.')
  const qty = BigInt(whole) * 10000n + BigInt(decimal.padEnd(4, '0'))
  // Multiply first, round once. Rounding the unit cost first loses tiny costs
  // (or rounds a half twice) when quantities are greater than one.
  const product = digits * qty
  const divisor = exponent < 0 ? 10n ** BigInt(-exponent) : 1n
  const subtotal = exponent >= 0
    ? product * 10n ** BigInt(exponent)
    : (product + divisor / 2n) / divisor
  return `${subtotal / 10000000n}.${String(subtotal % 10000000n).padStart(7, '0')}`
}

export function filterJewelryBom(rows, keyword) {
  const tokens = String(keyword || '').trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  return rows.filter((row) => tokens.every((token) =>
    `${row.part_name || ''} ${row.part_id}`.toLocaleLowerCase().includes(token)))
}

export function jewelryInfoPatch(original, form) {
  const name = String(form.name || '').trim()
  if (!name) throw new Error('请填写饰品名称')
  if (name.length > 120) throw new Error('饰品名称最多 120 个字符')
  const patch = {}
  if (form.name !== original.name && name !== original.name) patch.name = name
  // Unchanged legacy values remain untouched. Explicit reclassification only.
  if (form.category !== original.category) {
    if (!isJewelryType(form.category)) throw new Error('请选择饰品类型')
    patch.category = form.category
  }
  if (form.unit !== original.unit) {
    if (!jewelryUnitOptions.some((option) => option.value === form.unit)) throw new Error('请选择计量单位')
    patch.unit = form.unit
  }
  const color = String(form.color || '').trim()
  if (form.color !== (original.color || '') && color !== (original.color || '')) patch.color = color || null
  return patch
}

export function jewelryPricePatch(original, form) {
  const patch = {}
  for (const key of ['retail_price', 'wholesale_price', 'handcraft_cost']) {
    const value = form[key] == null || form[key] === '' ? null : Number(form[key])
    if (value != null && (!Number.isFinite(value) || value < 0)) throw new Error('价格与手工费须为不小于 0 的数字，或留空')
    if (value !== (original[key] ?? null)) patch[key] = value
  }
  return patch
}
