import api from './index'

export const listDispatchedSummary = (params) =>
  api.get('/plating-summary/dispatched', { params })

export const listReceivedSummary = (params) =>
  api.get('/plating-summary/received', { params })
