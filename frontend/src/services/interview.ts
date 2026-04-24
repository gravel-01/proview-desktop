import api from './api'
import type {
  InterviewConfig,
  SetupResponse,
  ChatResponse,
  EndResponse,
  SessionListItem,
  SessionDetail,
  HistoryQuota,
} from '../types'
import { fetchSSE, type SSECallbacks } from './sse'
import { normalizeJobTitle, normalizeSessionDetail, normalizeSessionListItem } from '../utils/jobTitle'
import { buildApiUrl } from './runtimeConfig'

export interface HealthStatus {
  status: string
  data_service: { connected: boolean; url: string | null }
  agent_available: boolean
  ocr_available: boolean
}

export async function fetchHealth(): Promise<HealthStatus> {
  const { data } = await api.get<HealthStatus>('/api/health')
  return data
}

export async function setupInterview(config: InterviewConfig): Promise<SetupResponse> {
  const formData = new FormData()
  formData.append('job_title', normalizeJobTitle(config.jobTitle))
  formData.append('style', config.style)
  formData.append('interview_type', config.interviewType)
  formData.append('difficulty', config.difficulty)
  formData.append('feature_vad', String(config.featureVad))
  formData.append('feature_deep', String(config.featureDeep))
  formData.append('model_provider', config.modelProvider)
  if (config.jobRequirements?.trim()) {
    formData.append('job_requirements', config.jobRequirements.trim())
  }
  if (config.resumeFile) {
    formData.append('resume', config.resumeFile)
  } else if (config.resumeOcrText) {
    formData.append('resume_ocr_text', config.resumeOcrText)
  }
  const { data } = await api.post<SetupResponse>('/api/setup', formData)
  return data
}

export async function sendMessage(message: string): Promise<ChatResponse> {
  const { data } = await api.post<ChatResponse>('/api/chat', { message })
  return data
}

export async function endInterview(saveHistory = true): Promise<EndResponse> {
  const { data } = await api.post<EndResponse>('/api/end', { save_history: saveHistory })
  return data
}

/** 语音识别：发送 PCM 音频 Blob，返回识别文本 */
export async function speechToText(audioBlob: Blob, format = 'pcm', rate = 16000): Promise<string> {
  const formData = new FormData()
  formData.append('audio', audioBlob, 'audio.pcm')
  formData.append('format', format)
  formData.append('rate', String(rate))
  const { data } = await api.post<{ status: string; text: string }>('/api/speech/stt', formData)
  if (data.status !== 'success') throw new Error(data.text || 'STT 失败')
  return data.text
}

export interface SpeechCorrection {
  original: string
  corrected: string
}

/** 语音文本清洗：LLM 纠正技术术语的语音误识别 */
export async function polishSpeechText(text: string): Promise<{ text: string; corrections: SpeechCorrection[] }> {
  try {
    const { data } = await api.post<{ status: string; text: string; corrections: SpeechCorrection[] }>('/api/speech/polish', { text })
    if (data.status === 'success') return { text: data.text, corrections: data.corrections }
  } catch { /* 静默降级 */ }
  return { text, corrections: [] }
}

/** 语音合成：发送文本，返回 wav 音频 ArrayBuffer */
export async function textToSpeech(text: string, per = 4115, spd = 5): Promise<ArrayBuffer> {
  const { data } = await api.post('/api/speech/tts', { text, per, spd }, {
    responseType: 'arraybuffer'
  })
  return data
}

/** 语音试听（无需认证） */
export async function ttsPreview(text: string, per = 4115, spd = 5): Promise<ArrayBuffer> {
  const { data } = await api.post('/api/speech/tts-preview', { text, per, spd }, {
    responseType: 'arraybuffer'
  })
  return data
}

/** 获取当前用户最近一条有 OCR 结果的简历 */
export async function fetchLatestResume(): Promise<{ ocr_result: string; file_name?: string; session_id?: string } | null> {
  try {
    const { data } = await api.get<{ ocr_result: string; file_name?: string; session_id?: string } | null>('/api/history/resume/latest')
    return data
  } catch {
    return null
  }
}

export interface ResumeRecord {
  id: number
  session_id: string
  file_name: string
  file_path: string
  upload_time: string
  file_kind?: 'image' | 'pdf' | 'docx' | 'doc' | 'other'
  preview_page_count?: number
  can_preview?: boolean
  preview_cover_url?: string
  preview_image_urls?: string[]
}

/** 获取当前用户的所有简历列表 */
export async function fetchMyResumes(): Promise<ResumeRecord[]> {
  try {
    const { data } = await api.get<ResumeRecord[]>('/api/my-resumes')
    return data
  } catch {
    return []
  }
}

/** 获取简历文件预览 URL */
export function getResumeFileUrl(resumeId: number): string {
  return buildApiUrl(`/api/my-resumes/${resumeId}/file`)
}

export function getResumePreviewUrl(resumeId: number, page = 1): string {
  return buildApiUrl(`/api/my-resumes/${resumeId}/preview/${page}`)
}

export async function deleteMyResume(resumeId: number): Promise<void> {
  await api.delete(`/api/my-resumes/${resumeId}`)
}

/** 获取当前用户的面试历史列表 */
export async function fetchSessionHistory(): Promise<SessionListItem[]> {
  const { data } = await api.get<SessionListItem[]>('/api/history/sessions')
  return data.map(normalizeSessionListItem)
}

export async function fetchHistoryQuota(): Promise<HistoryQuota> {
  const { data } = await api.get<HistoryQuota>('/api/history/quota')
  return data
}

/** 获取某次面试的完整详情 */
export async function fetchSessionDetail(sessionId: string): Promise<SessionDetail> {
  const { data } = await api.get<SessionDetail>(`/api/history/sessions/${sessionId}`)
  return normalizeSessionDetail(data)
}

export async function deleteSessionHistory(sessionId: string): Promise<{ status: string; quota?: HistoryQuota }> {
  const { data } = await api.delete<{ status: string; quota?: HistoryQuota }>(`/api/history/sessions/${sessionId}`)
  return data
}

/** 获取某次面试关联的简历 OCR 文本 */
export async function fetchSessionResume(sessionId: string): Promise<{ ocr_result: string; file_name?: string; session_id?: string } | null> {
  try {
    const { data } = await api.get<{ ocr_result: string; file_name?: string; session_id?: string } | null>(`/api/history/resume/${sessionId}`)
    return data
  } catch {
    return null
  }
}

/** 流式面试初始化：通过 SSE 实时输出 LLM 思考过程 */
export async function setupInterviewStream(
  config: InterviewConfig,
  callbacks: SSECallbacks,
  jwt?: string,
  signal?: AbortSignal
): Promise<void> {
  const formData = new FormData()
  formData.append('job_title', normalizeJobTitle(config.jobTitle))
  formData.append('style', config.style)
  formData.append('interview_type', config.interviewType)
  formData.append('difficulty', config.difficulty)
  formData.append('feature_vad', String(config.featureVad))
  formData.append('feature_deep', String(config.featureDeep))
  formData.append('model_provider', config.modelProvider)
  if (config.jobRequirements?.trim()) {
    formData.append('job_requirements', config.jobRequirements.trim())
  }
  if (config.resumeFile) {
    formData.append('resume', config.resumeFile)
  } else if (config.resumeOcrText) {
    formData.append('resume_ocr_text', config.resumeOcrText)
  }
  const headers: Record<string, string> = {}
  if (jwt) headers['Authorization'] = `Bearer ${jwt}`
  await fetchSSE(buildApiUrl('/api/setup-stream'), formData, callbacks, headers, signal)
}

/** 流式结束面试：通过 SSE 实时输出评估思考过程 */
export async function endInterviewStream(
  token: string,
  saveHistory: boolean,
  callbacks: SSECallbacks,
  signal?: AbortSignal,
): Promise<void> {
  await fetchSSE(buildApiUrl('/api/end-stream'), { save_history: saveHistory }, callbacks, {
    'Authorization': `Bearer ${token}`,
  }, signal)
}

/** 流式对话：通过 SSE 实时输出 LLM 思维链 */
export async function sendMessageStream(
  message: string,
  token: string,
  callbacks: SSECallbacks,
  signal?: AbortSignal
): Promise<void> {
  await fetchSSE(buildApiUrl('/api/chat-stream'), JSON.stringify({ message }), callbacks, {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  }, signal)
}

export async function stopChatStream(): Promise<{ status: string }> {
  const { data } = await api.post<{ status: string }>('/api/chat-stop')
  return data
}
