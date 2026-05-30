import api from './index'

/**
 * Fetch distinct customer names for the picker.
 * @param {string|undefined} query Optional substring filter (case-insensitive)
 * @param {number} limit Max results (default 50)
 * @returns Promise<AxiosResponse<string[]>>
 */
export const getCustomerNames = (query, limit = 50) =>
  api.get('/customers/names', { params: { q: query || undefined, limit } })
