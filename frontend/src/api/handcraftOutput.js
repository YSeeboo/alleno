import api from './index'

const config = params => ({ params, _silentError: true })
export const getHandcraftOutputOverview = params => api.get('/handcraft-summary/output-overview', config(params))
export const getHandcraftOutputOptions = params => api.get('/handcraft-summary/output-options', config(params))
export const getHandcraftOutputSources = params => api.get('/handcraft-summary/output-sources', config(params))
export const getHandcraftOutputReceipts = (sourceId, params) => api.get(`/handcraft-summary/output-sources/${sourceId}/receipts`, config(params))
