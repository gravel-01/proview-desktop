import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  appendCareerTaskLog,
  generateCareerPlan,
  getCareerDashboard,
  getCareerDocRecommendations,
  getCareerDocReadState,
  getCareerDocs,
  getCareerPlan,
  getCareerPlanningErrorMessage,
  listCareerDocFavorites,
  listCareerPlans,
  markCareerDocRead,
  toggleCareerDocFavorite,
  updateCareerTask,
} from '../services/careerPlanning'
import type {
  CareerDashboardData,
  CareerDocRecommendation,
  CareerMarkDocReadPayload,
  CareerPlanningDocument,
  CareerPlan,
  CareerTask,
  GenerateCareerPlanPayload,
  UpdateCareerTaskPayload,
} from '../types/career-planning'

export const useCareerPlanningStore = defineStore('careerPlanning', () => {
  const dashboard = ref<CareerDashboardData | null>(null)
  const plans = ref<CareerPlan[]>([])
  const loading = ref(false)
  const generating = ref(false)
  const docsLoading = ref(false)
  const error = ref('')
  const docsError = ref('')
  const targetRole = ref('')
  const careerGoal = ref('')
  const horizonMonths = ref(6)
  const documents = ref<CareerPlanningDocument[]>([])

  const currentPlan = computed(() => dashboard.value?.current_plan || plans.value[0] || null)
  const profile = computed(() => dashboard.value?.profile || null)
  const milestones = computed(() => dashboard.value?.milestones || [])
  const tasks = computed(() => dashboard.value?.tasks || [])
  const recommendations = computed(() => dashboard.value?.recommendations || [])
  /**
   * Phase 3: the LLM outcome block mirrored from the backend ``GenerationOutcome``.
   * ``null`` when the dashboard has not loaded yet or when no LLM provider is
   * registered. Components should treat every field as best-effort.
   */
  const llm = computed(() => dashboard.value?.llm || null)
  /**
   * Phase 4: section-level doc recommendations served by
   * ``/api/career/docs/recommend``. The list is the primary surface for
   * the new "为你推荐" panel and the resource-closure loop.
   */
  const docRecommendations = computed<CareerDocRecommendation[]>(
    () => dashboard.value?.doc_recommendations || [],
  )
  const favoriteDocIds = computed<string[]>(() => dashboard.value?.favorite_doc_ids || [])
  const stats = computed(() => dashboard.value?.stats || {
    plan_count: 0,
    active_task_count: 0,
    completed_task_count: 0,
    progress_rate: 0,
  })

  function applyDashboard(data: CareerDashboardData) {
    dashboard.value = data
    plans.value = data.plans || []
    if (data.profile && typeof data.profile === 'object' && 'target_role' in data.profile) {
      targetRole.value = String((data.profile as { target_role?: string }).target_role || targetRole.value)
    }
  }

  async function loadDashboard(options?: { force?: boolean }) {
    loading.value = true
    error.value = ''
    try {
      const response = await getCareerDashboard({ force: options?.force })
      if (response.status !== 'success') {
        throw new Error(response.message || '加载职业规划失败')
      }
      applyDashboard(response.data)
    } catch (err) {
      error.value = getCareerPlanningErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  async function refreshPlans(options?: { force?: boolean }) {
    try {
      const response = await listCareerPlans({ force: options?.force })
      if (response.status === 'success') {
        plans.value = response.data.plans || []
      }
    } catch (err) {
      error.value = getCareerPlanningErrorMessage(err)
    }
  }

  async function loadDocs(options?: { force?: boolean }) {
    docsLoading.value = true
    docsError.value = ''
    try {
      const response = await getCareerDocs({ force: options?.force })
      if (response.status !== 'success') {
        throw new Error(response.message || '加载职业规划文档失败')
      }
      documents.value = response.data.documents || []
    } catch (err) {
      docsError.value = getCareerPlanningErrorMessage(err)
    } finally {
      docsLoading.value = false
    }
  }

  async function createPlan(payload?: GenerateCareerPlanPayload) {
    generating.value = true
    error.value = ''
    try {
      const response = await generateCareerPlan({
        target_role: payload?.target_role ?? targetRole.value,
        career_goal: payload?.career_goal ?? careerGoal.value,
        horizon_months: payload?.horizon_months ?? horizonMonths.value,
        refresh: payload?.refresh ?? true,
      })
      if (response.status !== 'success') {
        throw new Error(response.message || '生成职业规划失败')
      }
      applyDashboard(response.data)
      return response.data
    } catch (err) {
      error.value = getCareerPlanningErrorMessage(err)
      throw err
    } finally {
      generating.value = false
    }
  }

  async function patchTask(taskId: number, payload: UpdateCareerTaskPayload) {
    const response = await updateCareerTask(taskId, payload)
    if (response.status !== 'success') {
      throw new Error(response.message || '更新任务失败')
    }
    applyDashboard(response.data)
    return response.data
  }

  async function logTask(taskId: number, payload: UpdateCareerTaskPayload) {
    const response = await appendCareerTaskLog(taskId, payload)
    if (response.status !== 'success') {
      throw new Error(response.message || '记录任务进度失败')
    }
    applyDashboard(response.data)
    return response.data
  }

  /**
   * Phase 2: refresh the dashboard with the selected plan's detail
   * payload (plan / milestones / tasks / logs). The previous
   * implementation only swapped ``current_plan`` in memory which
   * desynced with persisted progress.
   */
  async function selectPlan(planId: number) {
    const selected = plans.value.find((plan) => plan.id === planId)
    if (!selected) {
      error.value = '未找到对应的计划，请刷新后再试。'
      return
    }
    loading.value = true
    error.value = ''
    try {
      const response = await getCareerPlan(planId)
      if (response.status !== 'success') {
        throw new Error(response.message || '加载计划详情失败')
      }
      const existing = dashboard.value
      const profile = existing?.profile || null
      const recommendations = (() => {
        const raw = (response.data.plan as { recommendation_json?: unknown }).recommendation_json
        if (Array.isArray(raw)) return raw as CareerDashboardData['recommendations']
        if (typeof raw === 'string') {
          try { return JSON.parse(raw) } catch { return [] }
        }
        return []
      })()
      applyDashboard({
        ...(existing || {}),
        profile: profile || {},
        plans: plans.value,
        current_plan: response.data.plan,
        milestones: response.data.milestones || [],
        tasks: response.data.tasks || [],
        logs: response.data.logs || [],
        recommendations: recommendations || [],
        stats: existing?.stats || {
          plan_count: plans.value.length,
          active_task_count: 0,
          completed_task_count: 0,
          progress_rate: 0,
        },
      })
    } catch (err) {
      error.value = getCareerPlanningErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  function getTaskById(taskId: number): CareerTask | undefined {
    return tasks.value.find((task) => task.id === taskId)
  }

  // ----------------------------------------------------------------
  // Phase 4: resource-closure actions (markDocRead / toggleDocFavorite)
  // ----------------------------------------------------------------

  /**
   * Persist a doc reading event. When ``completed`` is true and a
   * ``task_id`` is provided, the backend will also advance the linked
   * task's progress; the store then refreshes the dashboard so the UI
   * reflects the new task state.
   */
  async function markDocRead(payload: CareerMarkDocReadPayload) {
    const response = await markCareerDocRead(payload)
    if (response.status !== 'success') {
      throw new Error(response.message || '记录阅读进度失败')
    }
    // The task linked to this read event may have moved; refresh the
    // dashboard in the background so the progress bar stays in sync.
    if (payload.completed && payload.task_id) {
      loadDashboard({ force: true }).catch(() => {
        /* swallow — surfaced via store error */
      })
    }
    return response.data
  }

  /**
   * Toggle the favourite flag for a doc. Updates the
   * ``favoriteDocIds`` local set so the heart icon flips immediately;
   * the dashboard refresh is not strictly required because the next
   * ``loadDashboard`` call will resync.
   */
  async function toggleDocFavorite(docId: string) {
    const response = await toggleCareerDocFavorite(docId)
    if (response.status !== 'success') {
      throw new Error(response.message || '更新收藏失败')
    }
    const favorited = Boolean(response.data?.favorited)
    if (dashboard.value) {
      const ids = new Set(dashboard.value.favorite_doc_ids || [])
      if (favorited) ids.add(docId)
      else ids.delete(docId)
      dashboard.value = { ...dashboard.value, favorite_doc_ids: [...ids] }
    }
    return favorited
  }

  /**
   * Re-fetch the list of favourite doc ids. Useful for boot-time
   * hydration after a page reload (the dashboard payload is
   * authoritative but the user may want to refresh independently).
   */
  async function refreshFavorites() {
    const response = await listCareerDocFavorites({ force: true })
    if (response.status === 'success' && dashboard.value) {
      dashboard.value = {
        ...dashboard.value,
        favorite_doc_ids: response.data?.doc_ids || [],
      }
    }
  }

  /**
   * Fetch the recommender output for the current plan and cache it on
   * the dashboard so the UI can render the "为你推荐" panel without
   * firing its own request.
   */
  async function refreshDocRecommendations(planId?: number) {
    const response = await getCareerDocRecommendations(
      { planId, limit: 4 },
      { force: true },
    )
    if (response.status === 'success' && dashboard.value) {
      dashboard.value = {
        ...dashboard.value,
        doc_recommendations: response.data?.recommendations || [],
      }
    }
  }

  /**
   * Read the persisted read state for a single doc. Used by the docs
   * page to render the "已读 / 未读" pill.
   */
  async function fetchDocReadState(docId: string) {
    return getCareerDocReadState(docId, { force: true })
  }

  return {
    dashboard,
    plans,
    loading,
    generating,
    docsLoading,
    error,
    docsError,
    targetRole,
    careerGoal,
    horizonMonths,
    documents,
    currentPlan,
    profile,
    milestones,
    tasks,
    recommendations,
    stats,
    llm,
    docRecommendations,
    favoriteDocIds,
    loadDashboard,
    refreshPlans,
    loadDocs,
    createPlan,
    patchTask,
    logTask,
    selectPlan,
    getTaskById,
    markDocRead,
    toggleDocFavorite,
    refreshFavorites,
    refreshDocRecommendations,
    fetchDocReadState,
  }
})
