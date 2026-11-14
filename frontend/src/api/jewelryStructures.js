import api from './index'

export const listStructures = () => api.get('/jewelry-structures/')
export const createStructure = (data) => api.post('/jewelry-structures/', data)
export const updateStructure = (id, data) =>
  api.put(`/jewelry-structures/${id}`, data)
export const deleteStructure = (id, revision) =>
  api.delete(`/jewelry-structures/${id}`, { params: { revision } })
export const createScheme = (id, data) =>
  api.post(`/jewelry-structures/${id}/schemes`, data)
export const updateScheme = (id, schemeId, data) =>
  api.put(`/jewelry-structures/${id}/schemes/${schemeId}`, data)
export const deleteScheme = (id, schemeId, revision) =>
  api.delete(`/jewelry-structures/${id}/schemes/${schemeId}`, {
    params: { revision },
  })
export const previewStructureBatch = (data) =>
  api.post('/jewelry-structures/preview', data)
export const confirmStructureBatch = (data) =>
  api.post('/jewelry-structures/confirm', data)
export const listStructureBatches = () => api.get('/jewelry-structures/batches')
