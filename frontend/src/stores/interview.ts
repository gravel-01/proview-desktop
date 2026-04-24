import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { ChatMessage, DebugLogEntry, SessionStats, InterviewConfig, SessionListItem, HistoryQuota } from '../types'
import * as interviewApi from '../services/interview'
import type { HealthStatus } from '../services/interview'
import type { EvalDraftUpdate } from '../services/sse'
import { normalizeJobTitle } from '../utils/jobTitle'
import { isReusableOcrText } from '../utils/ocr'

export interface EvalDraft extends EvalDraftUpdate {
  timestamp: number
  completed: boolean
}

type SetupStatus = 'idle' | 'initializing'
type ResponseStatus = 'idle' | 'streaming' | 'stopping'
type EndStatus = 'idle' | 'generating'

const INTERVIEW_SESSION_TOKEN_KEY = 'proview_interview_session_token'
const INTERVIEW_SESSION_STATUS_KEY = 'proview_interview_session_status'
const INTERVIEW_SESSION_ID_KEY = 'interview_session_id'

function isAbortError(error: unknown) {
  return !!error && typeof error === 'object' && 'name' in error && error.name === 'AbortError'
}

function isUnauthorizedError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error)
  return /401|unauthorized|缺少认证 token|无效或过期的 token/i.test(message)
}

function readSessionStorageItem(key: string) {
  try {
    return typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(key)
  } catch {
    return null
  }
}

function writeSessionStorageItem(key: string, value: string) {
  try {
    if (typeof sessionStorage !== 'undefined') {
      sessionStorage.setItem(key, value)
    }
  } catch {
    // Ignore persistence failures.
  }
}

function removeSessionStorageItem(key: string) {
  try {
    if (typeof sessionStorage !== 'undefined') {
      sessionStorage.removeItem(key)
    }
  } catch {
    // Ignore persistence failures.
  }
}

export const useInterviewStore = defineStore('interview', () => {
  const persistedToken = readSessionStorageItem(INTERVIEW_SESSION_TOKEN_KEY) || ''
  const persistedStatus = readSessionStorageItem(INTERVIEW_SESSION_STATUS_KEY) || ''
  const persistedSessionId = readSessionStorageItem(INTERVIEW_SESSION_ID_KEY) || ''

  const token = ref(persistedToken)
  const currentSessionId = ref(persistedSessionId)
  const lastSavedSessionId = ref('')
  const messages = ref<ChatMessage[]>([])
  const debugLogs = ref<DebugLogEntry[]>([])
  const isAiSpeaking = ref(false)
  const aiState = ref<'idle' | 'thinking' | 'speaking'>('idle')
  const interviewStatus = ref<'idle' | 'active' | 'ended'>(persistedToken && persistedStatus !== 'ended' ? 'active' : 'idle')
  const stats = ref<SessionStats | null>(null)
  const evalStrengths = ref('')
  const evalWeaknesses = ref('')
  const evalSummary = ref('')
  const serviceStatus = ref<HealthStatus | null>(null)
  const thinkingText = ref('')
  const thinkingStage = ref('')
  const historyQuota = ref<HistoryQuota | null>(null)
  const lastEndSaved = ref(false)

  const setupStatus = ref<SetupStatus>('idle')
  const responseStatus = ref<ResponseStatus>('idle')
  const endStatus = ref<EndStatus>('idle')

  const evalDrafts = ref<EvalDraft[]>([])
  const evalInProgress = ref(false)
  const currentEvalTurn = ref(0)

  const pipeline = ref<{ type: string; label: string; content: string }[]>([])
  const canEnterInterviewRoom = computed(() => !!token.value && interviewStatus.value !== 'ended')
  const shouldRedirectInterviewToReport = computed(() => interviewStatus.value === 'ended' && lastEndSaved.value && !!stats.value)
  const isSettingUp = computed(() => setupStatus.value === 'initializing')
  const isResponding = computed(() => responseStatus.value === 'streaming' || responseStatus.value === 'stopping')
  const canStopResponse = computed(() => responseStatus.value === 'streaming')
  const isEnding = computed(() => endStatus.value === 'generating')

  const config = ref<InterviewConfig>({
    jobTitle: '',
    jobRequirements: '',
    style: 'strict',
    interviewType: 'technical',
    difficulty: 'mid',
    featureVad: true,
    featureDeep: true,
    resumeFile: null,
    resumeSelection: 'auto-latest',
    voicePer: 4100,
    voiceSpd: 5,
    modelProvider: 'ernie'
  })

  let msgIdCounter = 0
  let setupController: AbortController | null = null
  let responseController: AbortController | null = null
  let endController: AbortController | null = null
  let activeStreamMessageId: number | null = null

  if (token.value && interviewStatus.value === 'active') {
    writeSessionStorageItem(INTERVIEW_SESSION_TOKEN_KEY, token.value)
    writeSessionStorageItem(INTERVIEW_SESSION_STATUS_KEY, 'active')
    if (currentSessionId.value) {
      writeSessionStorageItem(INTERVIEW_SESSION_ID_KEY, currentSessionId.value)
    }
  }

  function clearThinkingState() {
    thinkingText.value = ''
    thinkingStage.value = ''
  }

  function rehydrateInterviewSession() {
    const storedToken = readSessionStorageItem(INTERVIEW_SESSION_TOKEN_KEY) || ''
    const storedStatus = readSessionStorageItem(INTERVIEW_SESSION_STATUS_KEY) || ''
    const storedSessionId = readSessionStorageItem(INTERVIEW_SESSION_ID_KEY) || ''

    if (!storedToken) {
      return false
    }

    token.value = storedToken
    currentSessionId.value = storedSessionId
    interviewStatus.value = storedStatus === 'ended' ? 'ended' : 'active'
    return true
  }

  function persistInterviewSession() {
    if (token.value && interviewStatus.value === 'active') {
      writeSessionStorageItem(INTERVIEW_SESSION_TOKEN_KEY, token.value)
      writeSessionStorageItem(INTERVIEW_SESSION_STATUS_KEY, 'active')
      if (currentSessionId.value) {
        writeSessionStorageItem(INTERVIEW_SESSION_ID_KEY, currentSessionId.value)
      } else {
        removeSessionStorageItem(INTERVIEW_SESSION_ID_KEY)
      }
      return
    }
    removeSessionStorageItem(INTERVIEW_SESSION_TOKEN_KEY)
    removeSessionStorageItem(INTERVIEW_SESSION_STATUS_KEY)
    removeSessionStorageItem(INTERVIEW_SESSION_ID_KEY)
  }

  function clearInterviewSessionStorage() {
    removeSessionStorageItem(INTERVIEW_SESSION_TOKEN_KEY)
    removeSessionStorageItem(INTERVIEW_SESSION_STATUS_KEY)
    removeSessionStorageItem(INTERVIEW_SESSION_ID_KEY)
  }

  function clearResumeSelection() {
    config.value.resumeFile = null
    config.value.resumeOcrText = undefined
    config.value.resumeFileName = undefined
    config.value.resumeSelection = 'none'
    config.value.resumeSourceSessionId = undefined
  }

  function setUploadedResume(file: File | null) {
    if (!file) return
    config.value.resumeFile = file
    config.value.resumeOcrText = undefined
    config.value.resumeFileName = undefined
    config.value.resumeSelection = 'uploaded-file'
    config.value.resumeSourceSessionId = undefined
  }

  function setReusedResume(
    ocrText: string,
    options: {
      fileName?: string
      sourceSessionId?: string
      selection?: InterviewConfig['resumeSelection']
    } = {}
  ) {
    const nextOcrText = ocrText.trim()
    config.value.resumeFile = null
    config.value.resumeOcrText = nextOcrText || undefined
    config.value.resumeFileName = options.fileName || undefined
    config.value.resumeSelection = nextOcrText ? (options.selection || 'reused-text') : 'none'
    config.value.resumeSourceSessionId = options.sourceSessionId || undefined
  }

  function snapshotConfig(): InterviewConfig {
    return {
      ...config.value,
      jobTitle: normalizeJobTitle(config.value.jobTitle),
      resumeFile: config.value.resumeFile,
    }
  }

  function addMessage(role: ChatMessage['role'], content: string) {
    messages.value.push({
      id: ++msgIdCounter,
      role,
      content,
      timestamp: Date.now()
    })
    return msgIdCounter
  }

  function removeMessage(id: number) {
    messages.value = messages.value.filter(message => message.id !== id)
  }

  function updateMessage(id: number, content: string, corrections?: Array<{ original: string; corrected: string }>) {
    const msg = messages.value.find(m => m.id === id)
    if (msg) {
      msg.content = content
      if (corrections) msg.corrections = corrections
    }
  }

  function addDebugLog(stage: string, info: any) {
    if (!info) return
    debugLogs.value.push({
      stage,
      time: new Date().toLocaleTimeString(),
      info
    })
  }

  function setAiState(state: 'idle' | 'thinking' | 'speaking') {
    aiState.value = state
    isAiSpeaking.value = state !== 'idle'
  }

  function addPipelineStep(type: string, label: string, content: string) {
    pipeline.value.push({ type, label, content })
  }

  function clearPipeline() {
    pipeline.value = []
  }

  function addEvalDraft(data: EvalDraftUpdate) {
    evalDrafts.value.push({
      ...data,
      timestamp: Date.now(),
      completed: false
    })
    evalInProgress.value = true
    currentEvalTurn.value = data.turn

    setTimeout(() => {
      const draft = evalDrafts.value.find(d => d.turn === data.turn && !d.completed)
      if (draft) {
        draft.completed = true
        evalInProgress.value = false
      }
    }, 3000)
  }

  function clearEvalDrafts() {
    evalDrafts.value = []
    evalInProgress.value = false
    currentEvalTurn.value = 0
  }

  async function cancelSetup() {
    if (!setupController) return
    setupController.abort()
    setupController = null
    setupStatus.value = 'idle'
    clearThinkingState()
  }

  async function stopResponseGeneration() {
    if (!responseController || !token.value || responseStatus.value !== 'streaming') return
    responseStatus.value = 'stopping'
    try {
      await interviewApi.stopChatStream()
    } catch {
      // The local abort below is still enough to unblock the UI.
    } finally {
      responseController.abort()
    }
  }

  function resetSessionRuntime() {
    setupController?.abort()
    responseController?.abort()
    endController?.abort()
    setupController = null
    responseController = null
    endController = null
    activeStreamMessageId = null

    token.value = ''
    currentSessionId.value = ''
    lastSavedSessionId.value = ''
    messages.value = []
    debugLogs.value = []
    isAiSpeaking.value = false
    aiState.value = 'idle'
    interviewStatus.value = 'idle'
    lastEndSaved.value = false
    stats.value = null
    evalStrengths.value = ''
    evalWeaknesses.value = ''
    evalSummary.value = ''
    clearThinkingState()
    pipeline.value = []
    setupStatus.value = 'idle'
    responseStatus.value = 'idle'
    endStatus.value = 'idle'
    msgIdCounter = 0
    clearEvalDrafts()
    clearInterviewSessionStorage()
  }

  async function startInterview() {
    resetSessionRuntime()
    setupStatus.value = 'initializing'

    const requestConfig = snapshotConfig()
    const controller = new AbortController()
    setupController = controller

    let doneData: any = null
    let streamError = ''

    try {
      await interviewApi.setupInterviewStream(requestConfig, {
        onStage: (stage) => { thinkingStage.value = stage },
        onThinking: (chunk) => { thinkingText.value += chunk },
        onDone: (data) => { doneData = data },
        onError: (msg) => { streamError = msg },
      }, undefined, controller.signal)

      if (streamError) throw new Error(streamError)
      if (!doneData || doneData.status !== 'success') {
        throw new Error(doneData?.message || '\u9762\u8bd5\u521d\u59cb\u5316\u5931\u8d25')
      }

      token.value = doneData.token
      currentSessionId.value = doneData.session_id || ''
      lastSavedSessionId.value = ''
      interviewStatus.value = 'active'
      persistInterviewSession()

      if (requestConfig.resumeFile) {
        setReusedResume(doneData.ocr_text || '', {
          fileName: requestConfig.resumeFile.name,
          sourceSessionId: doneData.session_id || undefined,
          selection: 'reused-text',
        })
      } else if (doneData.ocr_text) {
        setReusedResume(doneData.ocr_text, {
          fileName: requestConfig.resumeFileName,
          sourceSessionId: requestConfig.resumeSourceSessionId,
          selection: requestConfig.resumeSelection === 'auto-latest' ? 'auto-latest' : 'reused-text',
        })
      }
      if (doneData.system_message) addMessage('system', doneData.system_message)
      if (doneData.parse_result) addMessage('system', `\u2728 AI \u6d1e\u5bdf: ${doneData.parse_result}`)
      if (doneData.ai_response) addMessage('ai', doneData.ai_response)

      addDebugLog('\u623f\u95f4\u521d\u59cb\u5316 & \u5524\u9192Agent', doneData.debug_info)
      return doneData.ai_response || ''
    } catch (error) {
      clearThinkingState()
      throw error
    } finally {
      if (setupController === controller) {
        setupController = null
      }
      setupStatus.value = 'idle'
      clearThinkingState()
    }
  }

  async function sendUserMessage(text: string) {
    const msgId = addMessage('user', text)
    const controller = new AbortController()
    responseController = controller
    responseStatus.value = 'streaming'
    activeStreamMessageId = null

    setAiState('thinking')
    clearThinkingState()

    let streamedContent = ''
    let doneData: any = null
    let streamError = ''

    try {
      await interviewApi.sendMessageStream(text, token.value, {
        onStage: (stage) => { thinkingStage.value = stage },
        onThinking: (chunk) => {
          thinkingText.value += chunk
          if (!streamedContent) setAiState('thinking')
        },
        onContent: (chunk) => {
          if (!activeStreamMessageId) {
            activeStreamMessageId = addMessage('ai', '')
          }
          streamedContent += chunk
          updateMessage(activeStreamMessageId, streamedContent)
          setAiState('speaking')
        },
        onEvalDraft: (data) => { addEvalDraft(data) },
        onDone: (data) => { doneData = data },
        onError: (msg) => { streamError = msg },
      }, controller.signal)

      if (streamError) throw new Error(streamError)

      const finalResponse = streamedContent || doneData?.response || ''
      if (!activeStreamMessageId && finalResponse) {
        activeStreamMessageId = addMessage('ai', finalResponse)
      } else if (activeStreamMessageId && finalResponse && finalResponse !== streamedContent) {
        updateMessage(activeStreamMessageId, finalResponse)
      }

      addDebugLog('\u5904\u7406\u5019\u9009\u4eba\u56de\u590d & \u5bfb\u627e\u6f0f\u6d1e', doneData?.debug_info)
      return { response: finalResponse, msgId, interrupted: !!doneData?.interrupted }
    } catch (error) {
      if (isAbortError(error)) {
        if (activeStreamMessageId && !streamedContent.trim()) {
          removeMessage(activeStreamMessageId)
        }
        setAiState('idle')
        return { response: streamedContent, msgId, interrupted: true }
      }

      clearThinkingState()

      if (streamedContent) {
        setAiState('idle')
        return { response: streamedContent, msgId, interrupted: true }
      }

      try {
        const data = await interviewApi.sendMessage(text)
        addDebugLog('处理候选人回复 & 寻找漏洞', data.debug_info)
        if (data.response) addMessage('ai', data.response)
        return { response: data.response, msgId, interrupted: false }
      } catch {
        setAiState('idle')
        addMessage('ai', '网络异常，无法获取 AI 面试官的回应')
        throw error
      }
    } finally {
      clearThinkingState()
      responseStatus.value = 'idle'
      activeStreamMessageId = null
      if (responseController === controller) {
        responseController = null
      }
      setAiState('idle')
    }
  }

  async function loadHistoryQuota() {
    try {
      historyQuota.value = await interviewApi.fetchHistoryQuota()
      return historyQuota.value
    } catch {
      historyQuota.value = null
      return null
    }
  }

  async function endSession(saveHistory = true) {
    endStatus.value = 'generating'
    clearThinkingState()

    const controller = new AbortController()
    endController = controller
    let doneData: any = null
    let streamError = ''

    try {
      await interviewApi.endInterviewStream(token.value, saveHistory, {
        onStage: (stage) => { thinkingStage.value = stage },
        onThinking: (chunk) => { thinkingText.value += chunk },
        onDone: (data) => { doneData = data },
        onError: (msg) => { streamError = msg },
      }, controller.signal)

      if (streamError) throw new Error(streamError)

      if (doneData?.quota) historyQuota.value = doneData.quota
      if (saveHistory && doneData?.saved !== false) {
        const finishedSessionId = doneData?.session_id || currentSessionId.value
        if (doneData?.stats) stats.value = doneData.stats
        evalStrengths.value = doneData?.strengths || ''
        evalWeaknesses.value = doneData?.weaknesses || ''
        evalSummary.value = doneData?.summary || ''
        lastSavedSessionId.value = finishedSessionId || ''
        if (
          finishedSessionId
          && isReusableOcrText(config.value.resumeOcrText || '')
          && !config.value.resumeSourceSessionId
        ) {
          config.value.resumeSourceSessionId = finishedSessionId
        }
        interviewStatus.value = 'ended'
        lastEndSaved.value = true
        clearInterviewSessionStorage()
      } else {
        resetSessionRuntime()
      }
      return doneData
    } catch (error) {
      console.error('结束面试失败:', error)

      if (isUnauthorizedError(error)) {
        clearInterviewSessionStorage()
        throw new Error('面试会话已失效，请重新开始面试')
      }

      if (isAbortError(error) && !token.value) {
        throw new Error('结束请求已中止，当前会话已丢失，请重新开始面试')
      }

      if (!token.value) {
        throw new Error('当前没有可结束的面试会话，请先重新开始面试')
      }

      const data = await interviewApi.endInterview(saveHistory)
      if (data?.quota) historyQuota.value = data.quota
      if (saveHistory && data?.saved !== false) {
        const finishedSessionId = data?.session_id || currentSessionId.value
        if (data.stats) stats.value = data.stats
        evalStrengths.value = data.strengths || ''
        evalWeaknesses.value = data.weaknesses || ''
        evalSummary.value = data.summary || ''
        lastSavedSessionId.value = finishedSessionId || ''
        if (
          finishedSessionId
          && isReusableOcrText(config.value.resumeOcrText || '')
          && !config.value.resumeSourceSessionId
        ) {
          config.value.resumeSourceSessionId = finishedSessionId
        }
        interviewStatus.value = 'ended'
        lastEndSaved.value = true
        clearInterviewSessionStorage()
      } else {
        resetSessionRuntime()
      }
      return data
    } finally {
      clearThinkingState()
      endStatus.value = 'idle'
      if (endController === controller) {
        endController = null
      }
    }
  }

  function reset() {
    resetSessionRuntime()
    historyQuota.value = null
    clearResumeSelection()
    config.value.resumeSelection = 'auto-latest'
  }

  async function checkHealth() {
    try {
      serviceStatus.value = await interviewApi.fetchHealth()
    } catch {
      serviceStatus.value = null
    }
  }

  checkHealth()

  async function applyHistoryConfig(sessionId: string, session: SessionListItem, skipResume = false) {
    const meta = session.metadata || {}
    let ocrText = ''
    let fileName = ''
    if (!skipResume) {
      try {
        const resume = await interviewApi.fetchSessionResume(sessionId)
        const resumeOcrText = resume?.ocr_result || ''
        if (isReusableOcrText(resumeOcrText)) ocrText = resumeOcrText
        if (resume?.file_name) fileName = resume.file_name
      } catch {
        // The explicit error below will guide the user to upload a new resume.
      }

      if (!ocrText) {
        throw new Error('该历史记录没有可复用的简历解析结果，请改为上传新简历。')
      }
    }

    config.value = {
      ...config.value,
      jobTitle: normalizeJobTitle(session.position) || config.value.jobTitle,
      jobRequirements: typeof meta.job_requirements === 'string' ? meta.job_requirements : '',
      style: (session.interview_style || config.value.style) as InterviewConfig['style'],
      interviewType: meta.type || config.value.interviewType,
      difficulty: meta.diff || config.value.difficulty,
      featureVad: meta.vad ?? config.value.featureVad,
      featureDeep: meta.deep ?? config.value.featureDeep,
      resumeFile: null,
      resumeOcrText: ocrText || undefined,
      resumeFileName: fileName || undefined,
      resumeSelection: skipResume ? 'none' : 'reused-text',
      resumeSourceSessionId: skipResume ? undefined : sessionId,
    }
  }

  return {
    token, currentSessionId, lastSavedSessionId, messages, debugLogs, isAiSpeaking, aiState,
    interviewStatus, stats, config, serviceStatus, historyQuota, lastEndSaved,
    evalStrengths, evalWeaknesses, evalSummary,
    canEnterInterviewRoom, shouldRedirectInterviewToReport,
    thinkingText, thinkingStage, pipeline,
    evalDrafts, evalInProgress, currentEvalTurn,
    setupStatus, responseStatus, endStatus,
    isSettingUp, isResponding, canStopResponse, isEnding,
    setUploadedResume, setReusedResume, clearResumeSelection,
    addMessage, removeMessage, updateMessage, addDebugLog, setAiState,
    addPipelineStep, clearPipeline,
    addEvalDraft, clearEvalDrafts, resetSessionRuntime, rehydrateInterviewSession,
    startInterview, cancelSetup, sendUserMessage, stopResponseGeneration,
    endSession, loadHistoryQuota, reset, checkHealth, applyHistoryConfig
  }
})
