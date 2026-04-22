import axios from 'axios'
import { useInterviewStore } from '../stores/interview'
import { useAuthStore } from '../stores/auth'

const AUTH_STORAGE_KEY = 'proview_jwt'

function normalizeBearerToken(raw: string | null | undefined) {
  const token = String(raw || '').trim()
  if (!token) return ''
  return token.replace(/^Bearer\s+/i, '').trim()
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 120000
})

api.interceptors.request.use((config) => {
  const authStore = useAuthStore()
  const interviewStore = useInterviewStore()
  const url = config.url || ''
  // 仅 @require_session 端点使用面试 session token，其余一律用用户 JWT
  const needsSessionToken =
    url.startsWith('/api/chat') ||
    url.startsWith('/api/end') ||
    url.startsWith('/api/speech/') ||
    url.startsWith('/api/resume/export')
  if (needsSessionToken) {
    const interviewToken = normalizeBearerToken(interviewStore.token)
    if (interviewToken) {
      config.headers.Authorization = `Bearer ${interviewToken}`
    } else if (config.headers && 'Authorization' in config.headers) {
      delete config.headers.Authorization
    }
  } else {
    // Some requests may run before store hydration; fallback to localStorage.
    const userJwt = normalizeBearerToken(authStore.jwt || localStorage.getItem(AUTH_STORAGE_KEY))
    if (userJwt) {
      config.headers.Authorization = `Bearer ${userJwt}`
    } else if (config.headers && 'Authorization' in config.headers) {
      delete config.headers.Authorization
    }
  }
  return config
})

export default api
