import api from './index'

// 获取看板数据（三行）
export const getKanban = (params) =>
  api.get('/kanban', { params }) // type: 'all'|'plating'|'handcraft', status, page, page_size

// 获取厂家详情
export const getVendorDetail = (vendor_name, order_type) =>
  api.get(`/kanban/vendor/${encodeURIComponent(vendor_name)}`, { params: { order_type } })

// 提交收回
export const submitReturn = (data) =>
  api.post('/kanban/return', data)
  // data: { vendor_name, order_type, items: [{item_id, item_type, qty}] }

// 搜索厂家名（收回弹窗下拉用）
export const searchVendors = (params) =>
  api.get('/kanban/vendors', { params }) // order_type?, q?

// 搜索配件编号（模糊搜索）
export const searchParts = (params) =>
  api.get('/parts/', { params })

// 搜索饰品编号
export const searchJewelries = (params) =>
  api.get('/jewelries/', { params })
