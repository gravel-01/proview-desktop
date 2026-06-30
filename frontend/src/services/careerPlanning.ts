import api from './api'
import type {
  CareerDashboardResponse,
  CareerDocReadStatePayload,
  CareerDocRecommendation,
  CareerDocSection,
  CareerDocsResponse,
  CareerDocumentResponse,
  CareerListPlansResponse,
  CareerMarkDocReadPayload,
  CareerMarkDocReadResult,
  CareerPlanDetailResponse,
  GenerateCareerPlanPayload,
  UpdateCareerTaskPayload,
} from '../types/career-planning'

export interface CareerRequestOptions {
  force?: boolean
}

type CacheEntry<T> = {
  expiresAt: number
  promise?: Promise<T>
  value?: T
}

const CAREER_CACHE_TTL_MS = 30_000
const careerCache = new Map<string, CacheEntry<unknown>>()

function cacheKey(method: string, url: string, payload?: unknown) {
  return `${method}:${url}:${JSON.stringify(payload ?? {})}`
}

function isCacheFresh(entry: CacheEntry<unknown>) {
  return Boolean(entry.value) && entry.expiresAt > Date.now()
}

function clearCareerCache(prefix?: string) {
  if (!prefix) {
    careerCache.clear()
    return
  }

  for (const key of careerCache.keys()) {
    if (key.includes(prefix)) {
      careerCache.delete(key)
    }
  }
}

function normalizeCareerApiError(error: unknown) {
  if (error && typeof error === 'object' && 'response' in error) {
    const response = (error as { response?: { data?: { message?: string; error?: string } } }).response
    return response?.data?.message || response?.data?.error || '职业规划服务请求失败'
  }
  return error instanceof Error ? error.message : '职业规划服务请求失败'
}

function normalizeGeneratePayload(payload: GenerateCareerPlanPayload = {}): Required<GenerateCareerPlanPayload> {
  const horizonRaw = Number(payload.horizon_months ?? 6)
  const parsedHorizon = Number.isFinite(horizonRaw) ? Math.trunc(horizonRaw) : 6
  return {
    target_role: String(payload.target_role ?? '').trim(),
    career_goal: String(payload.career_goal ?? '').trim(),
    horizon_months: Math.min(12, Math.max(3, parsedHorizon || 6)),
    refresh: Boolean(payload.refresh ?? true),
  }
}

async function readCareerResource<T>(method: 'GET', url: string, loader: () => Promise<T>, options: CareerRequestOptions = {}) {
  const key = cacheKey(method, url)
  const existing = careerCache.get(key) as CacheEntry<T> | undefined

  if (!options.force && existing && isCacheFresh(existing)) {
    return existing.value as T
  }

  if (!options.force && existing?.promise) {
    return existing.promise
  }

  const pending = loader().then((value) => {
    careerCache.set(key, { value, expiresAt: Date.now() + CAREER_CACHE_TTL_MS })
    return value
  })

  careerCache.set(key, { promise: pending, expiresAt: Date.now() + CAREER_CACHE_TTL_MS })
  return pending
}

function invalidateCareerCache(prefix?: string) {
  clearCareerCache(prefix)
}

/**
 * Normalize and centralize career-planning API failures for the UI layer.
 */
export function getCareerPlanningErrorMessage(error: unknown) {
  return normalizeCareerApiError(error)
}

/**
 * Fetch the current dashboard snapshot. Results are cached briefly to reduce
 * repeat network traffic when users switch between sub-pages.
 */
export async function getCareerDashboard(options: CareerRequestOptions = {}) {
  return readCareerResource('GET', '/api/career/dashboard', async () => {
    const response = await api.get<CareerDashboardResponse>('/api/career/dashboard')
    return response.data
  }, options)
}

/**
 * Load the plan list used by the roadmap/sidebar views.
 */
export async function listCareerPlans(options: CareerRequestOptions = {}) {
  return readCareerResource('GET', '/api/career/plans', async () => {
    const response = await api.get<CareerListPlansResponse>('/api/career/plans')
    return response.data
  }, options)
}

/**
 * Load the career document catalog.
 */
export async function getCareerDocs(options: CareerRequestOptions = {}) {
  return readCareerResource('GET', '/api/career/docs', async () => {
    const response = await api.get<CareerDocsResponse>('/api/career/docs')
    return response.data
  }, options)
}

/**
 * Load a single document detail view.
 */
export async function getCareerDoc(docId: string, options: CareerRequestOptions = {}) {
  return readCareerResource('GET', `/api/career/docs/${docId}`, async () => {
    const response = await api.get<CareerDocumentResponse>(`/api/career/docs/${docId}`)
    return response.data
  }, options)
}

/**
 * Submit a new generation request after coercing the payload into the backend's
 * expected shape.
 */
export async function generateCareerPlan(payload: GenerateCareerPlanPayload) {
  const normalized = normalizeGeneratePayload(payload)
  const response = await api.post<CareerDashboardResponse>('/api/career/plans/generate', normalized)
  invalidateCareerCache()
  return response.data
}

export async function getCareerPlan(planId: number) {
  const response = await api.get<CareerPlanDetailResponse>(`/api/career/plans/${planId}`)
  return response.data
}

export async function updateCareerTask(taskId: number, payload: UpdateCareerTaskPayload) {
  const response = await api.patch<CareerDashboardResponse>(`/api/career/tasks/${taskId}`, payload)
  invalidateCareerCache()
  return response.data
}

export async function appendCareerTaskLog(taskId: number, payload: UpdateCareerTaskPayload) {
  const response = await api.post<CareerDashboardResponse>(`/api/career/tasks/${taskId}/logs`, payload)
  invalidateCareerCache()
  return response.data
}

// ---------------------------------------------------------------------------
// Phase 4: resource-closure (doc library → task → user behaviour)
// ---------------------------------------------------------------------------

export interface CareerDocRecommendationsParams {
  planId?: number
  limit?: number
  scoreThreshold?: number
}

export interface CareerDocSectionsResponse {
  status: string
  data: {
    sections: CareerDocSection[]
  }
  message?: string
}

export interface CareerDocRecommendationsResponse {
  status: string
  data: {
    recommendations: CareerDocRecommendation[]
  }
  message?: string
}

export interface CareerDocReadStateResponse {
  status: string
  data: CareerDocReadStatePayload & { doc_id: string }
  message?: string
}

export interface CareerDocMarkReadResponse {
  status: string
  data: CareerMarkDocReadResult
  message?: string
}

export interface CareerDocFavoritesResponse {
  status: string
  data: {
    doc_ids: string[]
  }
  message?: string
}

export interface CareerTaskDocsResponse {
  status: string
  data: {
    task_id: number
    docs: Array<{ doc_id: string; section_idx: number; reason: string }>
  }
  message?: string
}

/**
 * Fetch the section-level recommender output for a plan. The default
 * plan is the user's active plan; pass `planId` to override.
 */
export async function getCareerDocRecommendations(
  params: CareerDocRecommendationsParams = {},
  options: CareerRequestOptions = {},
) {
  const search = new URLSearchParams()
  if (params.planId) search.set('plan_id', String(params.planId))
  if (params.limit) search.set('limit', String(params.limit))
  if (params.scoreThreshold) search.set('score_threshold', String(params.scoreThreshold))
  const qs = search.toString()
  const url = `/api/career/docs/recommend${qs ? `?${qs}` : ''}`
  return readCareerResource('GET', url, async () => {
    const response = await api.get<CareerDocRecommendationsResponse>(url)
    return response.data
  }, options)
}

/**
 * Load the full index of doc sections (with structured tags). Used by
 * the docs page to render the catalogue locally without re-fetching
 * every time the recommender runs.
 */
export async function getCareerDocSections(options: CareerRequestOptions = {}) {
  return readCareerResource('GET', '/api/career/docs/sections', async () => {
    const response = await api.get<CareerDocSectionsResponse>('/api/career/docs/sections')
    return response.data
  }, options)
}

/**
 * Persist a reading event (section scrolled to the end / "mark as read"
 * button). When `completed=true` the backend also advances the linked
 * task's progress.
 */
export async function markCareerDocRead(payload: CareerMarkDocReadPayload) {
  const response = await api.post<CareerDocMarkReadResponse>(
    `/api/career/docs/${encodeURIComponent(payload.doc_id)}/progress`,
    {
      section_idx: payload.section_idx,
      read_seconds: payload.read_seconds ?? 0,
      completed: payload.completed ?? false,
      task_id: payload.task_id ?? null,
    },
  )
  invalidateCareerCache()
  return response.data
}

/**
 * Read the persisted read state for one document.
 */
export async function getCareerDocReadState(docId: string, options: CareerRequestOptions = {}) {
  return readCareerResource('GET', `/api/career/docs/${encodeURIComponent(docId)}/progress`, async () => {
    const response = await api.get<CareerDocReadStateResponse>(
      `/api/career/docs/${encodeURIComponent(docId)}/progress`,
    )
    return response.data
  }, options)
}

/**
 * Toggle the favourite flag for a document. Returns the new state.
 */
export async function toggleCareerDocFavorite(docId: string) {
  const response = await api.post<{
    status: string
    data: { doc_id: string; favorited: boolean }
    message?: string
  }>(`/api/career/docs/${encodeURIComponent(docId)}/favorite`)
  invalidateCareerCache()
  return response.data
}

/**
 * List all favourite doc ids for the current user.
 */
export async function listCareerDocFavorites(options: CareerRequestOptions = {}) {
  return readCareerResource('GET', '/api/career/docs/favorites', async () => {
    const response = await api.get<CareerDocFavoritesResponse>('/api/career/docs/favorites')
    return response.data
  }, options)
}

/**
 * Manually link a doc section to a task. Used by the "添加为资源" button
 * in the docs panel; the recommender also calls this internally when
 * persisting a plan.
 */
export async function linkCareerTaskDoc(
  taskId: number,
  payload: { doc_id: string; section_idx: number; reason?: string },
) {
  const response = await api.post<{ status: string; data: { task_id: number; doc_id: string; section_idx: number; reason: string } }>(
    `/api/career/tasks/${taskId}/link-docs`,
    payload,
  )
  invalidateCareerCache()
  return response.data
}

/**
 * List the doc sections linked to a task.
 */
export async function getCareerTaskDocs(taskId: number, options: CareerRequestOptions = {}) {
  return readCareerResource('GET', `/api/career/tasks/${taskId}/docs`, async () => {
    const response = await api.get<CareerTaskDocsResponse>(`/api/career/tasks/${taskId}/docs`)
    return response.data
  }, options)
}

export { invalidateCareerCache, normalizeCareerApiError }
