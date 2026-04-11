import api from './index'

export const listParts = (params) => api.get('/parts/', { params })
export const getPart = (id) => api.get(`/parts/${id}`)
export const createPart = (data) => api.post('/parts/', data)
export const updatePart = (id, data) => api.patch(`/parts/${id}`, data)
export const deletePart = (id) => api.delete(`/parts/${id}`)
export const importPartsExcel = (file) =>
  api.post('/parts/import', file, {
    params: { filename: file.name },
    headers: {
      'Content-Type': file.type || 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    },
  })
export const downloadPartsImportTemplate = () =>
  api.get('/parts/import-template', {
    responseType: 'blob',
  })
export const createPartVariant = (partId, data) => api.post(`/parts/${partId}/create-variant`, data)
export const getPartVariants = (partId) => api.get(`/parts/${partId}/variants`)
export const getColorVariants = () => api.get('/parts/color-variants')
export const findOrCreateVariant = (partId, data) => api.post(`/parts/${partId}/find-or-create-variant`, data)
export const getPartCostLogs = (partId) => api.get(`/parts/${partId}/cost-logs`)
export const batchUpdatePartCosts = (data) => api.post('/parts/batch-update-costs', data)
export const getPartBom = (partId) => api.get(`/parts/${partId}/bom`)
export const setPartBom = (partId, data) => api.post(`/parts/${partId}/bom`, data)
export const deletePartBom = (bomId) => api.delete(`/parts/bom/${bomId}`)
