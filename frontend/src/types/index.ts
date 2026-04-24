export type ResumeSelection = 'auto-latest' | 'none' | 'uploaded-file' | 'reused-text'

export interface InterviewConfig {
  jobTitle: string
  jobRequirements?: string
  style: 'default' | 'strict' | 'friendly' | 'technical_deep' | 'behavioral' | 'system_design' | 'rapid_fire' | 'project_focused'
  interviewType: string
  difficulty: string
  featureVad: boolean
  featureDeep: boolean
  resumeFile: File | null
  resumeOcrText?: string
  resumeFileName?: string
  resumeSelection: ResumeSelection
  resumeSourceSessionId?: string
  voicePer: number
  voiceSpd: number
  modelProvider: string
}

export interface ChatMessage {
  id: number
  role: 'user' | 'ai' | 'system'
  content: string
  timestamp: number
  /** 语音纠错信息（纠错完成后填充） */
  corrections?: Array<{ original: string; corrected: string }>
}

export interface DebugStep {
  tool: string
  tool_input: string | Record<string, unknown>
  log?: string
  observation: string
}

export interface DebugInfo {
  system_prompt: string
  chat_history: Array<{ role: string; content: string }>
  intermediate_steps: DebugStep[]
  agent_mode: string
  tools_available: string[]
  prompt_source?: string
  resume_summary?: string
  ocr_raw_text?: string
  ocr_status?: 'not_called' | 'success' | 'error' | 'unavailable'
  rag_context?: string
  rag_details?: {
    query?: string
    job_title?: string
    difficulty?: string
    interview_type?: string
    style?: string
    stage?: string
    status?: 'not_started' | 'matched' | 'empty' | 'error'
    error?: string
    counts?: {
      jobs: number
      questions: number
      scripts: number
    }
    jobs?: Array<{
      id?: string
      document?: string
      metadata?: Record<string, unknown>
    }>
    questions?: Array<{
      id?: string
      document?: string
      metadata?: Record<string, unknown>
    }>
    scripts?: Array<{
      id?: string
      document?: string
      metadata?: Record<string, unknown>
    }>
  }
  model_provider?: string
  model_name?: string
  model_label?: string
  data_service?: {
    connected: boolean
    url: string | null
  }
}

export interface DebugLogEntry {
  stage: string
  time: string
  info: DebugInfo
}

export interface SessionStats {
  turn_count: number
  evaluations: Array<{ dimension: string; score: number; comment: string }>
  avg_score: number
}

export interface SetupResponse {
  status: string
  token: string
  session_id: string
  system_message: string
  parse_result: string
  ai_response: string
  ocr_text?: string
  debug_info: DebugInfo
}

export interface ChatResponse {
  response: string
  debug_info: DebugInfo
}

export interface EndResponse {
  status: string
  session_id?: string
  saved?: boolean
  report_available?: boolean
  stats?: SessionStats
  message?: string
  strengths?: string
  weaknesses?: string
  summary?: string
  quota?: HistoryQuota
}

export interface SessionListItem {
  session_id: string
  position: string | null
  interview_style: string | null
  start_time: string | null
  end_time: string | null
  status: string | null
  metadata?: Record<string, any>
  eval_strengths?: string
  eval_weaknesses?: string
  eval_summary?: string
}

export interface SessionDetail {
  session: SessionListItem
  messages: Array<{ role: string; content: string; timestamp: string }>
  stats: SessionStats
}

export interface HistoryQuota {
  saved_count: number
  max_saved: number | null
  remaining: number | null
  can_save: boolean
}

export * from './career-planning'
