import api from './index'

export const listSuppliers = (params) => api.get('/suppliers/', { params })
export const createSupplier = (data) => api.post('/suppliers/', data)
export const updateSupplier = (id, data) => api.patch(`/suppliers/${id}`, data)
export const deleteSupplier = (id) => api.delete(`/suppliers/${id}`)
