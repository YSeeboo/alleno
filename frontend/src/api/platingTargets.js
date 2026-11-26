import { createPartVariant, findOrCreateVariant } from './parts'
import { createCompositePlatingTarget, getCompositePlatingTarget } from './plating'

export async function lookupPlatingTarget(part, code) {
  const { data } = await (part.is_composite
    ? getCompositePlatingTarget(part.id, code)
    : findOrCreateVariant(part.id, { color_code: code }))
  return data
}

export async function createPlatingTarget(part, code) {
  if (part.is_composite) return (await createCompositePlatingTarget(part.id, code)).data
  const { data } = await createPartVariant(part.id, { color_code: code })
  return { part: data, created: true }
}

export function compositeTargetConfirmation(info) {
  return `新名称：${info.suggested_name}\n新编号：${info.suggested_id}\n单位：${info.unit}（与发出件一致）\n\n复制原组合 BOM，保留子件编号和用量，不改变库存。`
}
