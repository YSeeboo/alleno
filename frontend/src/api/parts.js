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
