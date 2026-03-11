import axios from 'axios'
import { createDiscreteApi } from 'naive-ui'

const { message } = createDiscreteApi(['message'])

const api = axios.create({
  baseURL: 'http://localhost:8000/api',
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const detail = err.response?.data?.detail
    const msg = Array.isArray(detail)
      ? detail.map((d) => d.msg).join('; ')
      : detail || '请求失败'
    message.error(msg)
    return Promise.reject(err)
  }
)

export default api
