import api from './index'

// 获取「至少有 1 个含分拣信息订单」的商家名列表
export const getCargoSortingSuppliers = () =>
  api.get('/handcraft/suppliers-with-sorting')

// 按商家列出该商家的分拣订单（已过滤无客户行），分页
export const listCargoSortingOrders = (supplierName, { limit = 15, offset = 0 } = {}) =>
  api.get('/handcraft/sorting', {
    params: { supplier_name: supplierName, limit, offset },
  })

// 通过回执编号查询单个订单的分拣视图（大小写不敏感）
// 200 with order view (breakdown 可能为空 []) | 404 if code not found
export const getCargoSortingByReceiptCode = (code) =>
  api.get(`/handcraft/sorting/by-receipt-code/${encodeURIComponent(code)}`)
