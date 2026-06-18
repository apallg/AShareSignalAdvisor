import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

api.interceptors.response.use(
  res => res.data,
  err => {
    const msg = err.response?.data?.detail || err.message
    if (Array.isArray(msg)) {
      const parts = msg.map(x => typeof x === 'string' ? x : (x.msg || JSON.stringify(x)))
      throw new Error(parts.join('; '))
    }
    throw new Error(msg)
  }
)

export default api
