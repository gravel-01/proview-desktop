import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { loginUser, registerUser, fetchMe } from '../services/auth'
import type { AuthUser } from '../services/auth'
import { useInterviewStore } from './interview'
import { useResumeStore } from './resume'
import { useResumeQuestionnaireStore } from './resumeQuestionnaire'
import { useResumeBuilderStore } from './resumeBuilder'
import { useNavigationPreferenceStore } from './navigationPreference'
import { markNavPreferenceCompleted } from '../navigation/navPreferenceGate'

const STORAGE_KEY = 'proview_jwt'

function normalizeJwtToken(raw: string | null | undefined) {
  const token = String(raw || '').trim()
  if (!token) return ''
  return token.replace(/^Bearer\s+/i, '').trim()
}

export const useAuthStore = defineStore('auth', () => {
  const jwt = ref(normalizeJwtToken(localStorage.getItem(STORAGE_KEY)))
  const user = ref<AuthUser | null>(null)
  const isLoggedIn = computed(() => !!jwt.value)

  function clearAuthState() {
    jwt.value = ''
    user.value = null
    localStorage.removeItem(STORAGE_KEY)
    markNavPreferenceCompleted(false)
  }

  async function login(username: string, password: string) {
    const res = await loginUser({ username, password })
    jwt.value = normalizeJwtToken(res.token)
    user.value = res.user
    localStorage.setItem(STORAGE_KEY, jwt.value)
    markNavPreferenceCompleted(false)
  }

  async function register(username: string, password: string, displayName?: string) {
    const res = await registerUser({ username, password, display_name: displayName })
    jwt.value = normalizeJwtToken(res.token)
    user.value = res.user
    localStorage.setItem(STORAGE_KEY, jwt.value)
    markNavPreferenceCompleted(false)
  }

  function logout() {
    // 1. 清理认证数据（含导航问卷内存标记，避免下一账号误放行）
    clearAuthState()
    
    // 2. 清理面试相关状态
    const interviewStore = useInterviewStore()
    interviewStore.reset()
    
    // 3. 清理简历优化状态
    const resumeStore = useResumeStore()
    resumeStore.reset()

    // 3.1 清理简历优化问卷状态，避免跨账号残留表单数据
    const questionnaireStore = useResumeQuestionnaireStore()
    questionnaireStore.reset()
    
    // 4. 清理简历生成器状态（包括 localStorage）
    const resumeBuilderStore = useResumeBuilderStore()
    resumeBuilderStore.clearDraft()
    resumeBuilderStore.initBlank()

    // 4.1 清理导航排序偏好状态
    const navigationPreferenceStore = useNavigationPreferenceStore()
    navigationPreferenceStore.reset()
    
    // 5. 清理可能的其他用户相关数据
    // sessionStorage 中与面试相关的数据
    sessionStorage.removeItem('interview_session_id')
    
    // 6. 验证清理效果（开发环境）
    if (import.meta.env.DEV) {
      console.log('[Auth] 登出完成，验证清理状态：')
      console.log('  - localStorage keys:', Object.keys(localStorage))
      console.log('  - sessionStorage keys:', Object.keys(sessionStorage))
      console.log('  - auth.jwt:', jwt.value)
      console.log('  - auth.user:', user.value)
      console.log('  - interview.token:', interviewStore.token)
      console.log('  - resumeBuilder draft:', localStorage.getItem('resume-builder-draft'))
    }
  }

  async function tryRestore() {
    if (!jwt.value) return false
    try {
      user.value = await fetchMe()
      return true
    } catch (error) {
      const status = (error as { response?: { status?: number } })?.response?.status
      const message = error instanceof Error ? error.message : String(error)
      const tokenExpired = status === 401 || status === 403 || /token|unauthorized|认证/i.test(message)

      if (tokenExpired) {
        clearAuthState()
      }

      return false
    }
  }

  return { jwt, user, isLoggedIn, login, register, logout, tryRestore }
})
