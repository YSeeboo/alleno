import api from './index'

export const listTemplates = () => api.get('/jewelry-templates/')
export const getTemplate = (id) => api.get(`/jewelry-templates/${id}`)
export const createTemplate = (data) => api.post('/jewelry-templates/', data)
export const updateTemplate = (id, data) => api.patch(`/jewelry-templates/${id}`, data)
export const deleteTemplate = (id) => api.delete(`/jewelry-templates/${id}`)
export const applyTemplate = (templateId, jewelryId) => api.post(`/jewelry-templates/${templateId}/apply/${jewelryId}`)
