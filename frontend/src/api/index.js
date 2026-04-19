import axios from 'axios'
import { createDiscreteApi } from 'naive-ui'

const { message } = createDiscreteApi(['message'])

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
  paramsSerializer: {
    indexes: null, // serialize arrays as key=1&key=2 (not key[]=1)
  },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const isLoginReq = err.config.url?.includes('/auth/login')
    if (err.response?.status === 401 && !isLoginReq) {
      localStorage.removeItem('token')
      window.location.href = '/login'
      return Promise.reject(err)
    }
    if (isLoginReq) return Promise.reject(err)
    if (err.config?._silentError) return Promise.reject(err)
    const detail = err.response?.data?.detail
    const msg = Array.isArray(detail)
      ? detail.map((d) => d.msg).join('; ')
      : detail || '请求失败'
    message.error(msg)
    return Promise.reject(err)
  }
)

export default api
