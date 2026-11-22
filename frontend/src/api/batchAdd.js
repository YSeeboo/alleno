import { listParts, getColorVariants } from './parts'
import { listJewelries } from './jewelries'
import { addOrderItem } from './orders'
import { addPlatingItem } from './plating'
import { addHandcraftPart, addHandcraftJewelry } from './handcraft'
import { addPurchaseOrderItem } from './purchaseOrders'
import { setBom } from './bom'
import { batchCatalog } from '@/utils/batchAdd'

export async function loadBatchCatalog(scene) {
  const [parts, jewels, colors] = await Promise.all([
    listParts(), ['order', 'output'].includes(scene) ? listJewelries() : { data: [] },
    scene === 'plating' ? getColorVariants() : { data: [] },
  ])
  return { products: batchCatalog(scene, jewels.data, parts.data), colors: colors.data }
}

export function saveBatchRow(scene, id, payload) {
  switch (scene) {
    case 'order': return addOrderItem(id, payload)
    case 'plating': return addPlatingItem(id, payload)
    case 'material': return addHandcraftPart(id, payload)
    case 'output': return addHandcraftJewelry(id, payload)
    case 'purchase': return addPurchaseOrderItem(id, payload)
    case 'bom': return setBom(id, payload.part_id, payload.qty_per_unit)
    default: throw new Error('未知添加场景')
  }
}
