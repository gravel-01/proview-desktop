<script setup lang="ts">
import { computed } from 'vue'
import { AlertCircle, BarChart3, BrainCircuit, Clock3, Cpu, Database, FileSearch, RefreshCcw, Rocket, ShieldCheck, Sparkles, Target, TrendingUp } from 'lucide-vue-next'
import type { CareerDashboardStats, CareerEvidenceSample, CareerGapDimension, CareerLLMMetadata, CareerPlan, CareerProfile, CareerRecommendation, CareerSourceSnapshot } from '../../types/career-planning'
import CareerOverviewInsightGrid from './CareerOverviewInsightGrid.vue'
import { useCareerPlanningStore } from '../../stores/careerPlanning'

const props = defineProps<{
  profile: CareerProfile | Record<string, unknown> | null
  stats: CareerDashboardStats
  targetRole: string
  careerGoal: string
  horizonMonths: number
  generating: boolean
  // Phase 5: 透传给 2×2 洞察网格（资源建议 / 计划历史 / 证据 / 数据源）
  recommendations?: CareerRecommendation[]
  plans?: CareerPlan[]
  currentPlan?: CareerPlan | Record<string, unknown> | null
  sourceSnapshot?: CareerSourceSnapshot | null
  topEvidenceForGrid?: CareerEvidenceSample[]
}>()

const emit = defineEmits<{
  'update:target-role': [value: string]
  'update:career-goal': [value: string]
  'update:horizon-months': [value: number]
  refresh: []
  generate: []
  // Phase 5: 网格内事件（select-plan / open-doc 透传）
  'select-plan': [planId: number]
  'open-doc': [{ docId: string; sectionIdx: number; reason: string }]
}>()

const store = useCareerPlanningStore()

const profileData = computed<CareerProfile | null>(() => {
  return props.profile && typeof props.profile === 'object' ? (props.profile as unknown as CareerProfile) : null
})

const strengthTags = computed(() => {
  try {
    const tags = store.profile?.strength_tags as string | undefined
    return tags ? JSON.parse(tags) : []
  } catch {
    return []
  }
})

const gapTags = computed(() => {
  try {
    const tags = store.profile?.gap_tags as string | undefined
    return tags ? JSON.parse(tags) : []
  } catch {
    return []
  }
})

/**
 * Phase 2: structured gap dimensions carry severity, sample counts and
 * evidence samples. We fall back to plain gap_tags when the backend
 * has not yet produced them.
 */
const gapDimensions = computed<CareerGapDimension[]>(() => {
  return (profileData.value?.gap_dimensions || []) as CareerGapDimension[]
})

/**
 * Top-3 representative evidence samples that explain why the gap
 * list is the way it is.
 */
const topEvidence = computed<CareerEvidenceSample[]>(() => {
  const list = (profileData.value?.evidence_samples || []) as CareerEvidenceSample[]
  return list.slice(0, 3)
})

const resumeGapSignals = computed<string[]>(() => {
  return (profileData.value?.resume_gap_signals || []) as string[]
})

/**
 * Phase 3: prefer the dashboard-level ``llm`` block (the source of truth
 * mirrored from the backend ``GenerationOutcome``). Fall back to the
 * profile-level ``llm_*`` fields that are surfaced alongside the
 * generation_mode when the dashboard payload was built directly from
 * ``generate_plan`` (no caching layer in between).
 */
const llmBlock = computed<CareerLLMMetadata | null>(() => {
  const block = store.llm
  if (block && typeof block === 'object' && 'attempted' in block) {
    return block as CareerLLMMetadata
  }
  // Fallback: synthesise from profile fields if the dashboard block is
  // missing (e.g. older cache snapshots).
  const generationMode = String(profileData.value?.generation_mode || '')
  if (!generationMode.startsWith('llm')) {
    return null
  }
  const fallbackReason = String(profileData.value?.llm_fallback_reason || '')
  return {
    attempted: true,
    succeeded: generationMode === 'llm',
    model_id: String(profileData.value?.llm_model_id || ''),
    prompt_hash: String(profileData.value?.llm_prompt_hash || ''),
    latency_ms: Number(profileData.value?.llm_latency_ms || 0),
    tokens_in: Number(profileData.value?.llm_tokens_in || 0),
    tokens_out: Number(profileData.value?.llm_tokens_out || 0),
    fallback_reason: fallbackReason,
  }
})

/**
 * Generation mode badge metadata. Maps the 6-state enum to a label, a
 * colour class and a status dot colour. The legacy ``evidence`` value
 * is treated as ``evidence_aware`` for display purposes.
 */
const generationModeMeta: Record<string, { label: string; dot: string; chip: string }> = {
  llm: {
    label: 'LLM 实时生成',
    dot: 'bg-indigo-500',
    chip: 'border-indigo-300/80 bg-indigo-50 text-indigo-700 dark:border-indigo-400/30 dark:bg-indigo-500/14 dark:text-indigo-200',
  },
  llm_fallback: {
    label: 'LLM 已尝试·回落模板',
    dot: 'bg-amber-500',
    chip: 'border-amber-300/80 bg-amber-50 text-amber-700 dark:border-amber-400/30 dark:bg-amber-500/14 dark:text-amber-200',
  },
  evidence_aware: {
    label: '基于真实评价',
    dot: 'bg-emerald-500',
    chip: 'border-emerald-300/80 bg-emerald-50 text-emerald-700 dark:border-emerald-400/30 dark:bg-emerald-500/14 dark:text-emerald-200',
  },
  evidence: {
    label: '基于真实评价',
    dot: 'bg-emerald-500',
    chip: 'border-emerald-300/80 bg-emerald-50 text-emerald-700 dark:border-emerald-400/30 dark:bg-emerald-500/14 dark:text-emerald-200',
  },
  fallback: {
    label: '基础模板（缺评价）',
    dot: 'bg-amber-500',
    chip: 'border-amber-300/80 bg-amber-50 text-amber-700 dark:border-amber-400/30 dark:bg-amber-500/14 dark:text-amber-200',
  },
  empty: {
    label: '数据不足',
    dot: 'bg-rose-500',
    chip: 'border-rose-300/80 bg-rose-50 text-rose-700 dark:border-rose-400/30 dark:bg-rose-500/14 dark:text-rose-200',
  },
}

/** Resolved mode + meta for the badge. */
const generationModeDisplay = computed(() => {
  const raw = String(profileData.value?.generation_mode || '')
  if (!raw) {
    return { key: '', label: '未生成', dot: 'bg-slate-400', chip: '' }
  }
  const meta = generationModeMeta[raw] || {
    label: raw,
    dot: 'bg-slate-400',
    chip: 'border-slate-300/80 bg-slate-50 text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200',
  }
  return { key: raw, ...meta }
})

/** LLM prompt hash shorthand for the badge tooltip. */
const llmBadgeTitle = computed(() => {
  const block = llmBlock.value
  if (!block || !block.attempted) {
    return '当前规划生成未使用 LLM。'
  }
  const modelLabel = block.model_id || '未知模型'
  const latencyLabel = `${Number(block.latency_ms || 0)} ms`
  if (block.succeeded) {
    return `LLM 路径·${modelLabel}·延迟 ${latencyLabel}`
  }
  const reason = block.fallback_reason ? `原因:${block.fallback_reason}` : '已回落至模板'
  return `LLM 路径失败·${modelLabel}·${reason}`
})

/**
 * Token totals and latency display strings. Hidden when the LLM was
 * not invoked, so the right column never shows stale zeros.
 */
const llmLatencyLabel = computed(() => `${Number(llmBlock.value?.latency_ms || 0)} ms`)
const llmTokensLabel = computed(() => {
  const block = llmBlock.value
  if (!block) return ''
  const ti = Number(block.tokens_in || 0)
  const to = Number(block.tokens_out || 0)
  if (ti === 0 && to === 0) return ''
  return `in ${ti} / out ${to}`
})

/** Short, user-facing label for the fallback reason (decodes the dotted code). */
const llmFallbackLabel = computed(() => {
  const raw = String(llmBlock.value?.fallback_reason || '').trim()
  if (!raw) return ''
  const map: Record<string, string> = {
    llm_unavailable: '未配置 LLM',
    llm_exception: '调用异常',
    parse_or_schema_error: '输出无法解析',
    reference_invalid: '引用未通过校验',
    task_too_few: '任务数不足',
  }
  const head = raw.split(':')[0] || raw
  return map[head] || raw
})

const sourceSnapshot = computed<CareerSourceSnapshot | null>(() => {
  return (profileData.value?.source_snapshot || null) as CareerSourceSnapshot | null
})

const sourceSummary = computed(() => sourceSnapshot.value || null)

/** 显示在 Hero 中的"数据来源"摘要行。 */
const sourceSummaryLines = computed<string[]>(() => {
  const snap = sourceSnapshot.value
  if (!snap) {
    return []
  }
  const lines: string[] = []
  if (snap.has_resume) {
    lines.push(`简历:已上传(${snap.resume_gap_signal_count ?? 0}个缺口信号)`)
  } else {
    lines.push('简历:未上传')
  }
  lines.push(`面试:${snap.session_count ?? 0}次(完成 ${snap.completed_session_count ?? 0})`)
  if (typeof snap.evaluation_count === 'number') {
    lines.push(`逐轮评价:${snap.evaluation_count}条`)
  }
  if (typeof snap.low_score_evaluation_count === 'number' && snap.low_score_evaluation_count > 0) {
    lines.push(`低分(${snap.low_score_evaluation_count}条)`)
  }
  if (typeof snap.avg_score === 'number' && snap.avg_score > 0) {
    lines.push(`平均分:${snap.avg_score.toFixed(1)}`)
  }
  if (snap.data_client_kind) {
    lines.push(`数据源:${snap.data_client_kind}`)
  }
  return lines
})

/** Severity chip color mapping for the top gap list. */
const severityTone: Record<string, string> = {
  high: 'border-rose-300/80 bg-rose-50 text-rose-700 dark:border-rose-400/30 dark:bg-rose-500/14 dark:text-rose-200',
  medium: 'border-amber-300/80 bg-amber-50 text-amber-700 dark:border-amber-400/30 dark:bg-amber-500/14 dark:text-amber-200',
  low: 'border-sky-300/80 bg-sky-50 text-sky-700 dark:border-sky-400/30 dark:bg-sky-500/14 dark:text-sky-200',
  none: 'border-emerald-300/80 bg-emerald-50 text-emerald-700 dark:border-emerald-400/30 dark:bg-emerald-500/14 dark:text-emerald-200',
}

const severityLabel: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
  none: '稳',
}

function chipClass(severity: string | undefined): string {
  const key = severity || 'none'
  return severityTone[key] ?? severityTone['none'] ?? ''
}

function chipLabel(severity: string | undefined): string {
  const key = severity || 'none'
  return severityLabel[key] ?? key
}

const targetRoleSuggestions = computed(() => {
  // 仅展示与用户历史相关的候选目标岗位：来自最近一次面试的 position。
  // 避免展示与用户数据无关的硬编码建议（如"数据湖架构师"等）。
  const lastSession = store.dashboard?.current_plan?.target_role
  const profileRole = store.profile?.target_role
  const candidates = [profileRole, lastSession].filter(Boolean) as string[]
  if (!candidates.length) return []
  // 去重并保留最近 4 个
  const unique: string[] = []
  for (const role of candidates) {
    if (!unique.includes(role)) unique.push(role)
    if (unique.length >= 4) break
  }
  return unique
})

const careerGoalSuggestions = [
  '6 个月内拿到目标岗位 offer',
  '3 个月补齐核心短板并完成作品集',
  '围绕目标岗位完成 2 个可展示项目',
  '持续面试复盘，提升通过率',
]

const horizonSuggestions = [3, 6, 9, 12]

const targetRoleToneClasses = [
  'border-slate-200/90 bg-white/90 text-slate-700 hover:border-indigo-300 hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:border-indigo-400/40 dark:hover:bg-white/10',
  'border-slate-200/90 bg-white/90 text-slate-700 hover:border-indigo-300 hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:border-indigo-400/40 dark:hover:bg-white/10',
  'border-slate-200/90 bg-white/90 text-slate-700 hover:border-indigo-300 hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:border-indigo-400/40 dark:hover:bg-white/10',
  'border-slate-200/90 bg-white/90 text-slate-700 hover:border-indigo-300 hover:bg-slate-50 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:border-indigo-400/40 dark:hover:bg-white/10',
]

const targetRoleSelectedToneClasses = [
  'border-indigo-300 bg-sky-50/84 text-indigo-900 shadow-[0_14px_30px_rgba(79,70,229,0.12)] dark:border-indigo-400/40 dark:bg-indigo-500/14 dark:text-white',
  'border-indigo-300 bg-sky-50/84 text-indigo-900 shadow-[0_14px_30px_rgba(79,70,229,0.12)] dark:border-indigo-400/40 dark:bg-indigo-500/14 dark:text-white',
  'border-indigo-300 bg-sky-50/84 text-indigo-900 shadow-[0_14px_30px_rgba(79,70,229,0.12)] dark:border-indigo-400/40 dark:bg-indigo-500/14 dark:text-white',
  'border-indigo-300 bg-sky-50/84 text-indigo-900 shadow-[0_14px_30px_rgba(79,70,229,0.12)] dark:border-indigo-400/40 dark:bg-indigo-500/14 dark:text-white',
]

const careerGoalToneClasses = [...targetRoleToneClasses]

const careerGoalSelectedToneClasses = [...targetRoleSelectedToneClasses]

const horizonToneClasses = [...targetRoleToneClasses]

const horizonSelectedToneClasses = [...targetRoleSelectedToneClasses]

function pickTone(base: string[], selected: string[], index: number, active: boolean) {
  const palette = active ? selected : base
  return palette[index % palette.length]
}

const normalizedTargetRole = computed(() => props.targetRole.trim())
const normalizedCareerGoal = computed(() => props.careerGoal.trim())

function setTargetRole(value: string) {
  emit('update:target-role', value)
}

function setCareerGoal(value: string) {
  emit('update:career-goal', value)
}

function setHorizonMonths(value: number) {
  emit('update:horizon-months', value)
}

function isSelectedText(currentValue: string, candidate: string) {
  return currentValue === candidate.trim()
}

function isSelectedNumber(currentValue: number, candidate: number) {
  return currentValue === candidate
}

function emitTargetRole(event: Event) {
  emit('update:target-role', (event.target as HTMLInputElement).value)
}

function emitCareerGoal(event: Event) {
  emit('update:career-goal', (event.target as HTMLInputElement).value)
}

function emitHorizonMonths(event: Event) {
  emit('update:horizon-months', Number((event.target as HTMLInputElement).value || 6))
}
</script>

<script lang="ts">
export default {
  name: 'CareerOverviewHero',
}
</script>

<template>
  <section class="relative overflow-hidden rounded-3xl border border-slate-200/85 bg-[linear-gradient(180deg,rgba(255,255,255,0.9)_0%,rgba(248,250,252,0.9)_100%)] p-6 shadow-[0_18px_48px_rgba(15,23,42,0.08)] backdrop-blur dark:border-white/10 dark:bg-[linear-gradient(180deg,rgba(10,10,15,0.92)_0%,rgba(12,15,23,0.94)_100%)]">
    <div class="absolute inset-0 bg-[radial-gradient(circle_at_top_right,_rgba(129,140,248,0.12),_transparent_36%),radial-gradient(circle_at_bottom_left,_rgba(56,189,248,0.1),_transparent_30%)]"></div>
    <div class="relative space-y-5">
      <!-- 标题区 -->
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="space-y-2">
          <div class="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/80 px-4 py-2 text-sm font-semibold text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200">
            <Sparkles class="h-4 w-4" />
            职业生涯规划
          </div>
          <div class="space-y-3">
            <h1 class="text-3xl font-black tracking-tight text-slate-900 dark:text-white sm:text-4xl">围绕目标岗位梳理可执行的成长路线。</h1>
            <p class="max-w-3xl text-sm leading-7 text-slate-600 dark:text-slate-400">基于你的简历和最近面试评估结果，生成可跟踪的阶段路线、任务清单和能力差距视图。如果暂时没有结构化评价数据，会先提供基础模板规划。</p>
          </div>
        </div>
        
        <!-- 顶部统计与操作按钮 -->
        <div class="flex flex-wrap items-center gap-3">
          <div class="grid grid-cols-3 gap-2">
            <div class="rounded-xl border border-slate-200/80 bg-white/80 px-3 py-2 text-center dark:border-white/10 dark:bg-white/5">
              <p class="text-[10px] font-semibold uppercase text-slate-500 dark:text-slate-400">目标岗位</p>
              <p class="mt-0.5 text-sm font-black text-slate-800 dark:text-slate-100 truncate max-w-[100px]">{{ profileData?.target_role || '未生成' }}</p>
            </div>
            <div class="rounded-xl border border-slate-200/80 bg-white/80 px-3 py-2 text-center dark:border-white/10 dark:bg-white/5">
              <p class="text-[10px] font-semibold uppercase text-slate-500 dark:text-slate-400">当前阶段</p>
              <p class="mt-0.5 text-sm font-black text-slate-800 dark:text-slate-100 truncate max-w-[100px]">{{ profileData?.current_stage || '等待分析' }}</p>
            </div>
            <div class="rounded-xl border border-slate-200/80 bg-white/80 px-3 py-2 text-center dark:border-white/10 dark:bg-white/5">
              <p class="text-[10px] font-semibold uppercase text-slate-500 dark:text-slate-400">规划进度</p>
              <p class="mt-0.5 text-sm font-black text-indigo-700 dark:text-indigo-300">{{ stats.progress_rate }}%</p>
            </div>
          </div>
          <div class="flex gap-2">
            <!-- 数据来源徽标（第一阶段：清晰告知用户当前规划基于哪些数据） -->
            <div class="hidden items-center gap-1.5 self-center rounded-full border bg-white/80 px-2.5 py-1 text-[10px] font-bold text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300 sm:inline-flex"
                 :class="generationModeDisplay.chip || 'border-slate-200 dark:border-white/10'"
                 :title="llmBadgeTitle">
              <span class="h-1.5 w-1.5 rounded-full"
                    :class="generationModeDisplay.dot"></span>
              <span>{{ generationModeDisplay.label }}</span>
            </div>
            <button
              @click="emit('refresh')"
              class="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 transition hover:border-indigo-300 hover:text-indigo-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200"
            >
              <RefreshCcw class="h-3.5 w-3.5" />
              刷新
            </button>
            <button
              @click="emit('generate')"
              :disabled="generating"
              class="inline-flex items-center gap-2 rounded-xl border border-indigo-300 bg-sky-50 px-4 py-2 text-xs font-semibold text-indigo-900 shadow-[0_14px_30px_rgba(79,70,229,0.12)] transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-60 dark:border-indigo-400/40 dark:bg-indigo-500/14 dark:text-white"
            >
              <Rocket class="h-3.5 w-3.5" />
              {{ generating ? '生成中...' : '重新生成规划' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 主内容区：左侧 [快速选择 + 2×2 洞察网格] + 右侧能力分析 -->
      <div class="grid gap-6 lg:grid-cols-[1fr_320px]">
        <!-- 左侧：快速选择表单 + 2×2 洞察网格（填满左下角空白） -->
        <div class="space-y-4">
          <!-- 快速选择卡片 -->
          <div class="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p class="text-sm font-bold text-slate-900 dark:text-white">快速选择</p>
                <p class="text-xs text-slate-500 dark:text-slate-400">点击卡片即可填入表单</p>
              </div>
              <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400">
                单选卡片
              </span>
            </div>

            <!-- 目标岗位 -->
            <div class="space-y-2">
              <div class="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">目标岗位</div>
              <div class="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                <button
                  v-for="(role, index) in targetRoleSuggestions"
                  :key="role"
                  type="button"
                  @click="setTargetRole(role)"
                  class="group relative overflow-hidden rounded-xl border px-3 py-2.5 text-left transition duration-200"
                  :class="[
                    pickTone(targetRoleToneClasses, targetRoleSelectedToneClasses, index, isSelectedText(normalizedTargetRole, role)),
                    isSelectedText(normalizedTargetRole, role) ? 'translate-y-[-1px]' : 'hover:translate-y-[-1px]',
                  ]"
                >
                  <div class="flex items-center justify-between gap-2">
                    <span class="text-xs font-semibold leading-5 truncate">{{ role }}</span>
                    <span
                      class="h-2 w-2 shrink-0 rounded-full transition"
                      :class="isSelectedText(normalizedTargetRole, role) ? 'bg-sky-600 dark:bg-sky-300' : 'bg-slate-300 dark:bg-slate-600'"
                    ></span>
                  </div>
                </button>
              </div>
            </div>

            <!-- 职业目标 -->
            <div class="space-y-2">
              <div class="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">职业目标</div>
              <div class="grid gap-2 sm:grid-cols-2">
                <button
                  v-for="(goal, index) in careerGoalSuggestions"
                  :key="goal"
                  type="button"
                  @click="setCareerGoal(goal)"
                  class="rounded-xl border px-3 py-2.5 text-left transition duration-200"
                  :class="[
                    pickTone(careerGoalToneClasses, careerGoalSelectedToneClasses, index, isSelectedText(normalizedCareerGoal, goal)),
                    isSelectedText(normalizedCareerGoal, goal) ? 'translate-y-[-1px]' : 'hover:translate-y-[-1px]',
                  ]"
                >
                  <div class="flex items-start gap-2">
                    <span
                      class="mt-0.5 h-2 w-2 shrink-0 rounded-full transition"
                      :class="isSelectedText(normalizedCareerGoal, goal) ? 'bg-amber-600 dark:bg-amber-300' : 'bg-slate-300 dark:bg-slate-600'"
                    ></span>
                    <span class="text-xs font-semibold leading-4">{{ goal }}</span>
                  </div>
                </button>
              </div>
            </div>

            <!-- 周期选择 -->
            <div class="space-y-2">
              <div class="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">规划周期</div>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="(month, index) in horizonSuggestions"
                  :key="month"
                  type="button"
                  @click="setHorizonMonths(month)"
                  class="inline-flex min-w-[4rem] items-center justify-center rounded-full border px-3 py-1.5 text-xs font-semibold transition"
                  :class="[
                    pickTone(horizonToneClasses, horizonSelectedToneClasses, index, isSelectedNumber(horizonMonths, month)),
                    isSelectedNumber(horizonMonths, month) ? 'translate-y-[-1px]' : 'hover:translate-y-[-1px]',
                  ]"
                >
                  {{ month }}个月
                </button>
              </div>
            </div>

            <!-- 输入框 -->
            <div class="grid gap-3 sm:grid-cols-3">
              <label class="space-y-1">
                <span class="text-xs font-semibold text-slate-600 dark:text-slate-300">目标岗位</span>
                <input
                  :value="targetRole"
                  type="text"
                  placeholder="输入目标..."
                  class="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-900 outline-none transition focus:border-indigo-400 focus:bg-white dark:border-white/10 dark:bg-white/5 dark:text-white"
                  @input="emitTargetRole"
                />
              </label>
              <label class="space-y-1">
                <span class="text-xs font-semibold text-slate-600 dark:text-slate-300">职业目标</span>
                <input
                  :value="careerGoal"
                  type="text"
                  placeholder="输入目标..."
                  class="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-900 outline-none transition focus:border-indigo-400 focus:bg-white dark:border-white/10 dark:bg-white/5 dark:text-white"
                  @input="emitCareerGoal"
                />
              </label>
              <label class="space-y-1">
                <span class="text-xs font-semibold text-slate-600 dark:text-slate-300">周期（月）</span>
                <input
                  :value="horizonMonths"
                  type="number"
                  min="3"
                  max="12"
                  class="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-900 outline-none transition focus:border-indigo-400 focus:bg-white dark:border-white/10 dark:bg-white/5 dark:text-white"
                  @input="emitHorizonMonths"
                />
              </label>
            </div>
          </div>

          <!--
            Phase 5 (修订): 4 单元 2×2 洞察网格
            放在「快速选择」卡片下方，填满 Hero 左下角空白，
            形成「看自己 → 看证据 → 学什么 → 走过哪」的有机叙事。
          -->
          <CareerOverviewInsightGrid
            :profile="profile"
            :recommendations="(recommendations || store.recommendations) || []"
            :plans="(plans || store.plans) || []"
            :current-plan="currentPlan || store.currentPlan"
            :source-snapshot="sourceSnapshot || sourceSummary"
            :top-evidence="topEvidenceForGrid || topEvidence"
            @select-plan="(planId) => emit('select-plan', planId)"
            @open-doc="(payload) => emit('open-doc', payload)"
          />
        </div>

        <!-- 右侧：能力分析面板 -->
        <div class="space-y-3">
          <!-- 总体画像分数 -->
          <div class="rounded-2xl border border-slate-200/85 bg-white/85 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)] dark:border-white/10 dark:bg-white/5">
            <div class="flex items-center justify-between">
              <div>
                <p class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">总体画像分数</p>
                <p class="mt-1 text-3xl font-black text-slate-900 dark:text-white">{{ Number(profileData?.overall_score || 0).toFixed(1) }}</p>
              </div>
              <div class="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white/90 text-indigo-600 dark:border-white/10 dark:bg-white/10 dark:text-indigo-300">
                <TrendingUp class="h-5 w-5" />
              </div>
            </div>
            <div class="mt-3 flex gap-2">
              <div class="flex-1 rounded-xl bg-white/80 p-2 text-center dark:bg-[#0B1220]">
                <p class="text-[10px] text-slate-500">任务</p>
                <p class="mt-0.5 text-sm font-bold text-slate-900 dark:text-white">{{ stats.active_task_count }}</p>
              </div>
              <div class="flex-1 rounded-xl bg-white/80 p-2 text-center dark:bg-[#0B1220]">
                <p class="text-[10px] text-slate-500">计划</p>
                <p class="mt-0.5 text-sm font-bold text-slate-900 dark:text-white">{{ stats.plan_count }}</p>
              </div>
              <div class="flex-1 rounded-xl bg-white/80 p-2 text-center dark:bg-[#0B1220]">
                <p class="text-[10px] text-slate-500">完成率</p>
                <p class="mt-0.5 text-sm font-bold text-indigo-600 dark:text-indigo-300">{{ stats.progress_rate }}%</p>
              </div>
            </div>
          </div>

          <!-- 优势能力 -->
          <div class="rounded-2xl border border-slate-200/80 bg-white/84 p-3 dark:border-white/10 dark:bg-white/5">
            <div class="flex items-center gap-2 mb-2">
              <div class="flex h-7 w-7 items-center justify-center rounded-lg bg-sky-100 text-sky-600 dark:bg-sky-500/20 dark:text-sky-300">
                <ShieldCheck class="h-4 w-4" />
              </div>
              <p class="text-xs font-bold text-slate-700 dark:text-white">优势能力</p>
            </div>
            <div class="flex flex-wrap gap-1">
              <span 
                v-for="tag in strengthTags" 
                :key="tag"
                class="rounded-full px-2 py-0.5 text-[10px] font-medium bg-sky-100 text-sky-700 dark:bg-sky-500/20 dark:text-sky-300"
              >
                {{ tag }}
              </span>
              <span v-if="!strengthTags.length" class="text-[10px] text-slate-400">暂无数据</span>
            </div>
          </div>

          <!-- 待提升项 (Phase 2: severity + sample 证据) -->
          <div class="rounded-2xl border border-slate-200/80 bg-white/84 p-3 dark:border-white/10 dark:bg-white/5">
            <div class="flex items-center gap-2 mb-2">
              <div class="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-100 text-amber-600 dark:bg-amber-500/20 dark:text-amber-300">
                <Target class="h-4 w-4" />
              </div>
              <p class="text-xs font-bold text-slate-700 dark:text-white">待提升项</p>
            </div>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="tag in gapTags"
                :key="tag"
                class="rounded-full px-2 py-0.5 text-[10px] font-medium bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300"
              >
                {{ tag }}
              </span>
              <span v-if="!gapTags.length" class="text-[10px] text-slate-400">暂无数据</span>
            </div>
            <!-- Phase 2: severity 排序 + 评价证据 -->
            <div v-if="gapDimensions.length" class="mt-2 space-y-1.5 border-t border-slate-200/60 pt-2 dark:border-white/10">
              <div
                v-for="dim in gapDimensions.slice(0, 3)"
                :key="dim.dimension"
                class="flex items-start gap-2 text-[10px] leading-4"
              >
                <span
                  class="mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-full border px-1.5 py-0.5 text-[9px] font-bold"
                  :class="chipClass(dim.severity)"
                >
                  <span class="h-1.5 w-1.5 rounded-full bg-current opacity-70"></span>
                  {{ chipLabel(dim.severity) }}
                </span>
                <div class="min-w-0 flex-1">
                  <p class="font-semibold text-slate-700 dark:text-slate-200">
                    {{ dim.dimension }}
                    <span class="ml-1 font-normal text-slate-500 dark:text-slate-400">
                      均分 {{ dim.avg_score }} · {{ dim.evaluation_count }} 次评价
                    </span>
                  </p>
                  <p
                    v-if="dim.evidence_samples && dim.evidence_samples[0]"
                    class="mt-0.5 line-clamp-2 text-slate-500 dark:text-slate-400"
                  >
                    "{{ dim.evidence_samples[0] }}"
                  </p>
                </div>
              </div>
            </div>
            <div v-else-if="resumeGapSignals.length" class="mt-2 space-y-1 border-t border-slate-200/60 pt-2 dark:border-white/10">
              <p class="flex items-center gap-1 text-[10px] font-semibold text-slate-500 dark:text-slate-400">
                <FileSearch class="h-3 w-3" />简历缺口信号
              </p>
              <ul class="space-y-0.5 text-[10px] text-slate-500 dark:text-slate-400">
                <li v-for="signal in resumeGapSignals.slice(0, 3)" :key="signal" class="line-clamp-1">· {{ signal }}</li>
              </ul>
            </div>
          </div>

          <!-- 代表证据 (Phase 2) -->
          <div v-if="topEvidence.length" class="rounded-2xl border border-slate-200/80 bg-white/84 p-3 dark:border-white/10 dark:bg-white/5">
            <div class="flex items-center gap-2 mb-2">
              <div class="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-100 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300">
                <FileSearch class="h-4 w-4" />
              </div>
              <p class="text-xs font-bold text-slate-700 dark:text-white">代表证据</p>
              <span class="ml-auto rounded-full bg-slate-100 px-2 py-0.5 text-[9px] font-semibold text-slate-500 dark:bg-white/10 dark:text-slate-400">
                来源:逐轮评价
              </span>
            </div>
            <ol class="space-y-1.5 text-[10px] leading-4">
              <li
                v-for="(ev, idx) in topEvidence"
                :key="`${ev.session_id || ''}-${ev.turn_id || ''}-${idx}`"
                class="rounded-lg border border-slate-200/70 bg-slate-50/70 p-2 dark:border-white/10 dark:bg-white/5"
              >
                <div class="flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
                  <span class="font-mono text-[9px]">{{ ev.dimension || '-' }}</span>
                  <span class="rounded-full bg-rose-50 px-1 text-rose-700 dark:bg-rose-500/20 dark:text-rose-200">
                    {{ ev.score ?? '-' }} 分
                  </span>
                  <span v-if="ev.turn_no" class="ml-auto text-[9px]">第 {{ ev.turn_no }} 轮</span>
                </div>
                <p class="mt-1 line-clamp-2 text-slate-600 dark:text-slate-300">"{{ ev.evidence }}"</p>
                <p v-if="ev.suggestion" class="mt-0.5 line-clamp-1 text-slate-500 dark:text-slate-400">建议:{{ ev.suggestion }}</p>
              </li>
            </ol>
          </div>

          <!-- 数据摘要 -->
          <div class="rounded-2xl border border-slate-200/80 bg-white/80 p-3 dark:border-white/10 dark:bg-white/5">
            <div class="flex items-center gap-2 mb-2">
              <div class="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300">
                <BarChart3 class="h-4 w-4" />
              </div>
              <p class="text-xs font-bold text-slate-700 dark:text-white">数据摘要</p>
            </div>
            <div class="space-y-1.5 text-[11px]">
              <div class="flex justify-between">
                <span class="text-slate-500">计划总数</span>
                <span class="font-semibold text-slate-700 dark:text-slate-200">{{ store.stats.plan_count }} 个</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-500">已完成任务</span>
                <span class="font-semibold text-sky-600 dark:text-sky-300">{{ store.stats.completed_task_count }} 个</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-500">当前活跃</span>
                <span class="font-semibold text-indigo-600">{{ store.stats.active_task_count }} 个</span>
              </div>
            </div>
            <p v-if="profileData?.source_summary" class="mt-2 border-t border-slate-200/60 pt-2 text-[10px] leading-4 text-slate-500 dark:border-white/10 dark:text-slate-400">
              {{ profileData.source_summary }}
            </p>
          </div>

          <!-- Phase 3: LLM 路径明细（仅在 LLM 实际被调用时显示） -->
          <div
            v-if="llmBlock && llmBlock.attempted"
            class="rounded-2xl border border-slate-200/80 bg-white/84 p-3 dark:border-white/10 dark:bg-white/5"
            data-testid="career-llm-summary"
          >
            <div class="flex items-center gap-2 mb-2">
              <div class="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-100 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300">
                <BrainCircuit class="h-4 w-4" />
              </div>
              <p class="text-xs font-bold text-slate-700 dark:text-white">LLM 生成明细</p>
              <span
                class="ml-auto rounded-full px-2 py-0.5 text-[9px] font-semibold"
                :class="llmBlock.succeeded
                  ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-500/14 dark:text-indigo-200'
                  : 'bg-amber-50 text-amber-700 dark:bg-amber-500/14 dark:text-amber-200'"
              >
                {{ llmBlock.succeeded ? '成功' : '回落模板' }}
              </span>
            </div>
            <ul class="space-y-1 text-[10px] leading-4 text-slate-500 dark:text-slate-400">
              <li class="flex items-center gap-1">
                <Cpu class="h-2.5 w-2.5 shrink-0 opacity-60" />
                <span class="truncate">
                  模型:<span class="font-semibold text-slate-700 dark:text-slate-200">{{ llmBlock.model_id || 'fallback' }}</span>
                </span>
              </li>
              <li v-if="llmBlock.prompt_hash" class="flex items-center gap-1">
                <span class="font-mono text-[9px] opacity-60">prompt_hash:</span>
                <span class="font-mono text-[9px] text-slate-700 dark:text-slate-200">{{ llmBlock.prompt_hash }}</span>
              </li>
              <li class="flex items-center gap-1">
                <Clock3 class="h-2.5 w-2.5 shrink-0 opacity-60" />
                <span>延迟:{{ llmLatencyLabel }}</span>
                <span v-if="llmTokensLabel" class="ml-2">tokens {{ llmTokensLabel }}</span>
              </li>
              <li
                v-if="!llmBlock.succeeded && llmFallbackLabel"
                class="flex items-start gap-1 text-amber-700 dark:text-amber-200"
              >
                <AlertCircle class="mt-0.5 h-2.5 w-2.5 shrink-0" />
                <span>回落原因:{{ llmFallbackLabel }}</span>
              </li>
            </ul>
          </div>

          <!-- 数据来源 (Phase 2: 数据源透明化) -->
          <div
            v-if="sourceSummaryLines.length"
            class="rounded-2xl border border-slate-200/80 bg-white/80 p-3 dark:border-white/10 dark:bg-white/5"
            data-testid="career-source-snapshot"
          >
            <div class="flex items-center gap-2 mb-2">
              <div class="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-100 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-300">
                <Database class="h-4 w-4" />
              </div>
              <p class="text-xs font-bold text-slate-700 dark:text-white">数据来源</p>
              <span class="ml-auto rounded-full bg-emerald-50 px-2 py-0.5 text-[9px] font-semibold text-emerald-700 dark:bg-emerald-500/14 dark:text-emerald-200">
                实时聚合
              </span>
            </div>
            <ul class="space-y-0.5 text-[10px] leading-4 text-slate-500 dark:text-slate-400">
              <li v-for="line in sourceSummaryLines" :key="line" class="flex items-center gap-1">
                <AlertCircle class="h-2.5 w-2.5 shrink-0 opacity-50" />
                {{ line }}
              </li>
            </ul>
            <p
              v-if="sourceSummary && sourceSummary.latest_session_at"
              class="mt-2 border-t border-slate-200/60 pt-1.5 text-[9px] text-slate-400 dark:border-white/10"
            >
              最近一次面试:{{ sourceSummary.latest_session_at }}
            </p>
          </div>
        </div>
      </div>

    </div>
  </section>
</template>
