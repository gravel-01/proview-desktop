export type CareerUserId = string | number

export type CareerGapSeverity = 'high' | 'medium' | 'low' | 'none'

/**
 * Phase 3: generation mode is now a 5-state enum. Old values are kept
 * so legacy dashboards continue to render; new states model the LLM
 * pathway and its fallback chain.
 */
export type CareerGenerationMode =
  | 'llm'
  | 'llm_fallback'
  | 'evidence_aware'
  | 'evidence' // legacy phase 2 value
  | 'fallback'
  | 'empty'

/**
 * Phase 3: the LLM block mirrors the backend ``GenerationOutcome`` so
 * the UI can render the model id, latency, and fallback reason without
 * re-deriving anything.
 */
export interface CareerLLMMetadata {
  attempted: boolean
  succeeded: boolean
  model_id: string
  prompt_hash: string
  latency_ms: number
  tokens_in: number
  tokens_out: number
  fallback_reason: string
}

/**
 * Phase 2: structured per-dimension statistics derived from
 * ``build_career_context``. Carries severity, score distribution, and
 * representative evidence / suggestion samples so the frontend can
 * explain "why is this in the gap list".
 */
export interface CareerGapDimension {
  dimension: string
  evaluation_count: number
  avg_score: number
  min_score: number
  max_score: number
  low_score_count: number
  severity: CareerGapSeverity
  evidence_samples: string[]
  suggestion_samples: string[]
  sessions_observed: number
}

/**
 * Per-turn evidence sample, used to render the "代表证据" panel.
 */
export interface CareerEvidenceSample {
  evaluation_id?: string
  session_id?: string
  turn_id?: string
  turn_no?: number
  dimension?: string
  score?: number
  pass_level?: string
  evidence?: string
  suggestion?: string
  evaluator_version?: string
}

/**
 * Resume summary payload sent to the frontend (subset of
 * :class:`ResumeSummary`).
 */
export interface CareerResumeSummary {
  file_name?: string
  resume_id?: number
  upload_time?: string
  ocr_length?: number
  ocr_preview?: string
  gap_signals?: string[]
}

/**
 * Data-source snapshot persisted into the plan and re-hydrated for
 * the dashboard. Drives the "数据来源" badge in the hero card.
 */
export interface CareerSourceSnapshot {
  session_count?: number
  completed_session_count?: number
  turn_count?: number
  answered_turn_count?: number
  evaluation_count?: number
  low_score_evaluation_count?: number
  question_metadata_count?: number
  avg_score?: number
  has_resume?: boolean
  has_any_evidence?: boolean
  has_question_metadata?: boolean
  resume_gap_signal_count?: number
  latest_session_id?: string
  latest_session_at?: string
  earliest_session_at?: string
  data_client_kind?: string
  build_meta?: Record<string, unknown>
}

/**
 * Phase 2 runtime fields carried by the profile. All optional so old
 * dashboard payloads without the new keys keep working.
 */
export interface CareerProfileRuntimeFields {
  generation_mode?: CareerGenerationMode | string
  has_resume?: boolean
  has_evaluations?: boolean
  evaluation_count?: number
  session_count?: number
  gap_dimensions?: CareerGapDimension[]
  strength_dimensions?: CareerGapDimension[]
  resume_gap_signals?: string[]
  source_snapshot?: CareerSourceSnapshot
  context_meta?: Record<string, unknown>
  evidence_samples?: CareerEvidenceSample[]
  suggestion_samples?: Array<{
    session_id?: string
    turn_id?: string
    turn_no?: number
    dimension?: string
    text?: string
  }>
  // Phase 3: LLM metadata mirrored on the profile so the dashboard
  // can render the generation mode without re-fetching the plan row.
  llm_model_id?: string
  llm_prompt_hash?: string
  llm_latency_ms?: number
  llm_tokens_in?: number
  llm_tokens_out?: number
  llm_fallback_reason?: string
  llm_generation_mode?: CareerGenerationMode | string
  llm_current_stage?: string
  llm_overall_score?: number
  llm_gap_tags?: string[]
  llm_strength_tags?: string[]
  llm_summary?: string
}

export interface CareerProfile extends CareerProfileRuntimeFields {
  user_id: CareerUserId
  target_role: string
  current_stage: string
  interest_tags: string
  strength_tags: string
  gap_tags: string
  overall_score: number
  source_summary: string
  sessions?: number
  latest_session_id?: string | null
  resume?: CareerResumeSummary | Record<string, unknown> | null
}

export interface CareerRecommendation {
  type: string
  title: string
  reason: string
  url?: string
}

export interface CareerPlan {
  id: number
  user_id: CareerUserId
  target_role: string
  career_goal: string
  status: string
  horizon_months: number
  summary: string
  assessment_json: Record<string, unknown>
  recommendation_json: CareerRecommendation[]
  created_at: string
  updated_at: string
  // Phase 2 evidence-chain fields
  source_session_ids_json?: string
  source_resume_id?: number | null
  source_snapshot_json?: string
  // Phase 3 LLM fields
  model_id?: string
  prompt_hash?: string
  generation_latency_ms?: number
  generation_tokens_in?: number
  generation_tokens_out?: number
  generation_mode?: CareerGenerationMode | string
}

export interface CareerMilestone {
  id: number
  plan_id: number
  title: string
  description: string
  month_label: string
  status: string
  sort_order: number
  target_date: string
  created_at?: string
  updated_at?: string
  // Phase 2 evidence-chain fields
  success_criteria?: string
  focus_gaps_json?: string
  focus_gaps?: string[]
}

export interface CareerTask {
  id: number
  milestone_id: number
  title: string
  description: string
  task_type: string
  task_type_icon?: string  // e.g. "book-open", "target", "code", "graduation-cap"
  task_type_label?: string // e.g. "技术学习", "面试准备", "项目实践", "课程学习"
  priority: number
  status: string
  progress: number
  due_date: string
  completed_at: string
  created_at?: string
  updated_at?: string
  // Phase 2 evidence-chain fields
  gap_key?: string
  source_evidence?: CareerEvidenceSample[]
  source_evidence_json?: string
  resource_refs_json?: string
  estimated_effort?: string
  success_criteria?: string
  // Phase 4: task → doc section refs (populated by tag_resource_to_task)
  resource_refs?: Array<{
    doc_id: string
    section_idx: number
    reason: string
  }>
}

export interface CareerProgressLog {
  id: number
  task_id: number
  note: string
  progress_delta: number
  created_at: string
}

export interface CareerDashboardStats {
  plan_count: number
  active_task_count: number
  completed_task_count: number
  progress_rate: number
}

export interface CareerPlanningDocSection {
  heading: string
  paragraphs: string[]
  bullets: string[]
  action_items?: string[]
}

export interface CareerPlanningDocument {
  id: string
  title: string
  subtitle: string
  category: string
  categoryIcon: string
  audience: string[]
  summary: string
  cover_gradient: string
  cover_icon: string
  difficulty: '入门' | '进阶' | '中级' | '高级'
  read_time: number
  tags: string[]
  is_featured: boolean
  sections: CareerPlanningDocSection[]
  // 用户交互相关
  is_favorited?: boolean
  read_progress?: number
  last_read_at?: string
}

export interface CareerPlanningDocsCatalog {
  version: string
  updated_at: string
  documents: CareerPlanningDocument[]
}

export interface CareerDashboardData {
  profile: CareerProfile | Record<string, unknown>
  plans: CareerPlan[]
  current_plan: CareerPlan | Record<string, unknown>
  milestones: CareerMilestone[]
  tasks: CareerTask[]
  logs: CareerProgressLog[]
  recommendations: CareerRecommendation[]
  stats: CareerDashboardStats
  // Phase 3: the LLM outcome block (mirrors GenerationOutcome).
  llm?: CareerLLMMetadata
  // Phase 4: section-level doc recommendations + favourite doc ids.
  doc_recommendations?: CareerDocRecommendation[]
  favorite_doc_ids?: string[]
}

export interface CareerDashboardResponse {
  status: string
  data: CareerDashboardData
  message?: string
}

export interface CareerDocsResponse {
  status: string
  data: CareerPlanningDocsCatalog
  message?: string
}

export interface CareerDocumentResponse {
  status: string
  data: CareerPlanningDocument
  message?: string
}

export interface CareerListPlansResponse {
  status: string
  data: {
    plans: CareerPlan[]
  }
  message?: string
}

export interface CareerPlanDetailResponse {
  status: string
  data: {
    plan: CareerPlan
    milestones: CareerMilestone[]
    tasks: CareerTask[]
    logs: CareerProgressLog[]
  }
  message?: string
}

export interface GenerateCareerPlanPayload {
  target_role?: string
  career_goal?: string
  horizon_months?: number
  refresh?: boolean
}

export interface UpdateCareerTaskPayload {
  status?: string
  progress?: number
  note?: string
}

// ---------------------------------------------------------------------------
// Phase 4: resource-closure (doc library → task → user behaviour) types
// ---------------------------------------------------------------------------

export type CareerDocReadState = 'unread' | 'in_progress' | 'completed'

/**
 * A single section-level recommendation produced by the backend
 * recommender. The score is in [0, 1] and `related_task_ids` is the
 * intersection of (user task ids) ∩ (tasks linked to this section).
 */
export interface CareerDocRecommendation {
  doc_id: string
  doc_title: string
  section_idx: number
  section_heading: string
  section_bullets?: string[]
  section_action_items?: string[]
  score: number
  reason: string
  tag_known?: boolean
  read_state?: CareerDocReadState
  read_count?: number
  completed_count?: number
  related_task_ids?: number[]
}

/**
 * Persisted reading state for a single document. The frontend caches
 * this object to avoid re-fetching the events table on every render.
 */
export interface CareerDocReadStatePayload {
  read_count: number
  completed_count: number
  last_read_at: string
}

export interface CareerMarkDocReadPayload {
  doc_id: string
  section_idx: number
  read_seconds?: number
  completed?: boolean
  task_id?: number
}

export interface CareerMarkDocReadResult {
  event_id: number
  doc_id: string
  section_idx: number
  completed: boolean
  task_id?: number | null
  task?: CareerTask | null
}

export interface CareerDocSection {
  doc_id: string
  doc_title: string
  doc_subtitle?: string
  doc_tags: string[]
  doc_is_featured: boolean
  doc_difficulty: string
  doc_read_time: number
  doc_category: string
  section_idx: number
  section_heading: string
  section_paragraphs: string[]
  section_bullets: string[]
  section_action_items: string[]
  section_tags: string[]
  skill_tags: string[]
  gap_tags: string[]
  task_types: string[]
  tag_known: boolean
}
