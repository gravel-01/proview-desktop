<script setup lang="ts">
import { computed } from 'vue'
import { Clock, FileText, RefreshCcw, Rocket, Sparkles, Star, TrendingUp } from 'lucide-vue-next'
import type { CareerDashboardStats, CareerProfile } from '../../types/career-planning'
import { useCareerPlanningStore } from '../../stores/careerPlanning'

const props = defineProps<{
  profile: CareerProfile | Record<string, unknown> | null
  stats: CareerDashboardStats
  targetRole: string
  careerGoal: string
  horizonMonths: number
  generating: boolean
}>()

const emit = defineEmits<{
  'update:target-role': [value: string]
  'update:career-goal': [value: string]
  'update:horizon-months': [value: number]
  refresh: []
  generate: []
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

const interestTags = computed(() => {
  try {
    const raw = profileData.value?.interest_tags
    if (!raw || typeof raw !== 'string') return [] as string[]
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return typeof profileData.value?.interest_tags === 'string'
      ? [profileData.value.interest_tags]
      : []
  }
})

const numericScore = computed(() => {
  const n = Number(profileData.value?.overall_score ?? 0)
  if (Number.isNaN(n)) return 0
  return Math.min(10, Math.max(0, n))
})

const scoreDisplay = computed(() => numericScore.value.toFixed(1))

const ringRadius = 52
const ringCirc = computed(() => 2 * Math.PI * ringRadius)
const ringDashOffset = computed(() => {
  const pct = Math.min(1, numericScore.value / 10)
  return ringCirc.value * (1 - pct)
})

const filledStars = computed(() => Math.round((numericScore.value / 10) * 5))

const profileRows = computed(() => {
  const p = profileData.value
  const sessions = p?.sessions
  return [
    { label: '职位意向', value: p?.target_role?.trim() || '—', important: true },
    { label: '当前阶段', value: p?.current_stage?.trim() || '—', important: false },
    { label: '规划完成率', value: `${props.stats.progress_rate}%`, important: false, rainbow: true },
    {
      label: '兴趣方向',
      value: interestTags.value.length ? interestTags.value.join('、') : '—',
      important: false,
    },
    {
      label: '来源摘要',
      value: p?.source_summary?.trim() || '—',
      important: false,
    },
    {
      label: '关联训练',
      value: typeof sessions === 'number' && sessions > 0 ? `已关联 ${sessions} 次面试/训练` : '暂无关联记录',
      important: false,
      isMeta: true,
    },
  ]
})

const barHeights = computed(() => {
  const max = Math.max(1, store.stats.plan_count, store.stats.active_task_count, store.stats.completed_task_count)
  return {
    plans: Math.round((store.stats.plan_count / max) * 100),
    active: Math.round((store.stats.active_task_count / max) * 100),
    done: Math.round((store.stats.completed_task_count / max) * 100),
  }
})

const targetRoleSuggestions = [
  '数据湖架构师',
  '报表自动化工程师',
  '数字健康产品经理',
  '向量数据库工程师',
  '老年科技产品经理',
  'Vue 前端工程师（外包）',
  '客户关系管理系统工程师',
  '无人机飞控工程师',
]

const careerGoalSuggestions = [
  '6 个月内拿到目标岗位 offer',
  '3 个月补齐核心短板并完成作品集',
  '围绕目标岗位完成 2 个可展示项目',
  '持续面试复盘，提升通过率',
]

const horizonSuggestions = [3, 6, 9, 12]

const targetRoleToneClasses = [
  'border-sky-200/90 bg-sky-50/90 text-slate-800 hover:border-sky-300 hover:bg-sky-100/80 dark:border-sky-500/20 dark:bg-sky-500/10 dark:text-slate-100 dark:hover:border-sky-400/40 dark:hover:bg-sky-500/15',
  'border-teal-200/90 bg-teal-50/90 text-slate-800 hover:border-teal-300 hover:bg-teal-100/80 dark:border-teal-500/20 dark:bg-teal-500/10 dark:text-slate-100 dark:hover:border-teal-400/40 dark:hover:bg-teal-500/15',
  'border-cyan-200/90 bg-cyan-50/90 text-slate-800 hover:border-cyan-300 hover:bg-cyan-100/80 dark:border-cyan-500/20 dark:bg-cyan-500/10 dark:text-slate-100 dark:hover:border-cyan-400/40 dark:hover:bg-cyan-500/15',
  'border-emerald-200/90 bg-emerald-50/90 text-slate-800 hover:border-emerald-300 hover:bg-emerald-100/80 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-slate-100 dark:hover:border-emerald-400/40 dark:hover:bg-emerald-500/15',
]

const targetRoleSelectedToneClasses = [
  'border-sky-500 bg-sky-100 text-sky-950 shadow-[0_14px_34px_-22px_rgba(14,165,233,0.65)] dark:border-sky-300/70 dark:bg-sky-500/20 dark:text-white',
  'border-teal-500 bg-teal-100 text-teal-950 shadow-[0_14px_34px_-22px_rgba(20,184,166,0.58)] dark:border-teal-300/70 dark:bg-teal-500/20 dark:text-white',
  'border-cyan-500 bg-cyan-100 text-cyan-950 shadow-[0_14px_34px_-22px_rgba(6,182,212,0.58)] dark:border-cyan-300/70 dark:bg-cyan-500/20 dark:text-white',
  'border-emerald-500 bg-emerald-100 text-emerald-950 shadow-[0_14px_34px_-22px_rgba(16,185,129,0.58)] dark:border-emerald-300/70 dark:bg-emerald-500/20 dark:text-white',
]

const careerGoalToneClasses = [
  'border-amber-200/90 bg-amber-50/90 text-slate-800 hover:border-amber-300 hover:bg-amber-100/80 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-slate-100 dark:hover:border-amber-400/40 dark:hover:bg-amber-500/15',
  'border-orange-200/90 bg-orange-50/90 text-slate-800 hover:border-orange-300 hover:bg-orange-100/80 dark:border-orange-500/20 dark:bg-orange-500/10 dark:text-slate-100 dark:hover:border-orange-400/40 dark:hover:bg-orange-500/15',
  'border-rose-200/90 bg-rose-50/90 text-slate-800 hover:border-rose-300 hover:bg-rose-100/80 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-slate-100 dark:hover:border-rose-400/40 dark:hover:bg-rose-500/15',
  'border-lime-200/90 bg-lime-50/90 text-slate-800 hover:border-lime-300 hover:bg-lime-100/80 dark:border-lime-500/20 dark:bg-lime-500/10 dark:text-slate-100 dark:hover:border-lime-400/40 dark:hover:bg-lime-500/15',
]

const careerGoalSelectedToneClasses = [
  'border-amber-500 bg-amber-100 text-amber-950 shadow-[0_14px_34px_-22px_rgba(245,158,11,0.58)] dark:border-amber-300/70 dark:bg-amber-500/20 dark:text-white',
  'border-orange-500 bg-orange-100 text-orange-950 shadow-[0_14px_34px_-22px_rgba(249,115,22,0.58)] dark:border-orange-300/70 dark:bg-orange-500/20 dark:text-white',
  'border-rose-500 bg-rose-100 text-rose-950 shadow-[0_14px_34px_-22px_rgba(244,63,94,0.5)] dark:border-rose-300/70 dark:bg-rose-500/20 dark:text-white',
  'border-lime-500 bg-lime-100 text-lime-950 shadow-[0_14px_34px_-22px_rgba(132,204,22,0.5)] dark:border-lime-300/70 dark:bg-lime-500/20 dark:text-white',
]

const horizonToneClasses = [
  'border-emerald-200/90 bg-emerald-50/90 text-slate-800 hover:border-emerald-300 hover:bg-emerald-100/80 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-slate-100 dark:hover:border-emerald-400/40 dark:hover:bg-emerald-500/15',
  'border-teal-200/90 bg-teal-50/90 text-slate-800 hover:border-teal-300 hover:bg-teal-100/80 dark:border-teal-500/20 dark:bg-teal-500/10 dark:text-slate-100 dark:hover:border-teal-400/40 dark:hover:bg-teal-500/15',
  'border-lime-200/90 bg-lime-50/90 text-slate-800 hover:border-lime-300 hover:bg-lime-100/80 dark:border-lime-500/20 dark:bg-lime-500/10 dark:text-slate-100 dark:hover:border-lime-400/40 dark:hover:bg-lime-500/15',
  'border-cyan-200/90 bg-cyan-50/90 text-slate-800 hover:border-cyan-300 hover:bg-cyan-100/80 dark:border-cyan-500/20 dark:bg-cyan-500/10 dark:text-slate-100 dark:hover:border-cyan-400/40 dark:hover:bg-cyan-500/15',
]

const horizonSelectedToneClasses = [
  'border-emerald-500 bg-emerald-100 text-emerald-950 shadow-[0_14px_34px_-22px_rgba(16,185,129,0.58)] dark:border-emerald-300/70 dark:bg-emerald-500/20 dark:text-white',
  'border-teal-500 bg-teal-100 text-teal-950 shadow-[0_14px_34px_-22px_rgba(20,184,166,0.58)] dark:border-teal-300/70 dark:bg-teal-500/20 dark:text-white',
  'border-lime-500 bg-lime-100 text-lime-950 shadow-[0_14px_34px_-22px_rgba(132,204,22,0.5)] dark:border-lime-300/70 dark:bg-lime-500/20 dark:text-white',
  'border-cyan-500 bg-cyan-100 text-cyan-950 shadow-[0_14px_34px_-22px_rgba(6,182,212,0.58)] dark:border-cyan-300/70 dark:bg-cyan-500/20 dark:text-white',
]

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
  <section class="coh-root space-y-6">
    <!-- 有简历版训练 徽章 -->
    <div
      class="coh-badge-enter relative inline-flex overflow-hidden rounded-full border border-indigo-200/40 px-6 py-3 shadow-md will-change-transform"
      style="
        background: linear-gradient(
          135deg,
          rgba(224, 242, 254, 0.4) 0%,
          rgba(243, 232, 255, 0.4) 50%,
          rgba(254, 242, 242, 0.4) 100%
        );
      "
    >
      <span class="coh-badge-shine pointer-events-none absolute inset-0 opacity-20" aria-hidden="true" />
      <Sparkles class="coh-icon-float relative z-[1] mr-2 h-4 w-4 shrink-0 text-blue-500" />
      <span class="relative z-[1] text-sm font-semibold text-blue-900 dark:text-sky-100">有简历版训练</span>
    </div>

    <div class="grid gap-6 lg:grid-cols-3 lg:items-start">
      <!-- 主内容卡片 + 表格 -->
      <div class="coh-main-card group relative lg:col-span-2">
        <div
          class="pointer-events-none absolute inset-0 rounded-2xl bg-gradient-to-br from-white via-sky-50/10 to-violet-50/10 opacity-90 dark:from-white/5 dark:via-sky-500/5 dark:to-violet-500/5"
          aria-hidden="true"
        />
        <div
          class="relative overflow-hidden rounded-2xl border border-gray-200/70 bg-white/85 px-5 py-6 shadow-[0_20px_50px_rgba(59,130,246,0.08)] backdrop-blur-xl transition-[transform,box-shadow] duration-300 will-change-transform dark:border-white/10 dark:bg-slate-900/75 dark:shadow-[0_24px_60px_rgba(0,0,0,0.35)] sm:px-6 sm:py-7 lg:hover:-translate-y-3 lg:hover:shadow-[0_30px_70px_rgba(139,92,246,0.12)]"
          style="transform-style: preserve-3d"
        >
          <div class="coh-main-shine pointer-events-none absolute inset-0 opacity-20" aria-hidden="true" />
          <header class="relative z-[1] mb-5 flex flex-wrap items-start gap-3">
            <div class="flex items-center gap-2">
              <span
                class="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-violet-600 text-white shadow-md"
              >
                <FileText class="coh-icon-spin h-5 w-5" />
              </span>
              <Sparkles class="h-5 w-5 text-sky-500 dark:text-sky-300" />
            </div>
            <div class="min-w-0 flex-1">
              <h2
                class="bg-gradient-to-r from-gray-900 via-gray-800 to-gray-700 bg-clip-text text-lg font-bold text-transparent dark:from-white dark:via-slate-100 dark:to-slate-300"
              >
                从简历和面试结果提取你的职业画像
              </h2>
              <p class="mt-2 max-w-2xl text-sm leading-relaxed text-[#6b7280] dark:text-slate-400">
                将简历、面试历史与评估合并为可跟踪面板；在此查看结构化摘要，并在下方快速调整目标与周期。
              </p>
            </div>
          </header>

          <div
            class="coh-table-wrap relative overflow-hidden rounded-xl border border-gray-200/50 bg-white/90 dark:border-white/10 dark:bg-slate-950/40"
          >
            <div
              class="pointer-events-none absolute right-0 top-0 h-40 w-40 rounded-full bg-rose-200/[0.03] dark:bg-rose-500/10"
              aria-hidden="true"
            />
            <div
              class="pointer-events-none absolute bottom-0 left-0 h-36 w-36 rounded-full bg-cyan-200/[0.03] dark:bg-cyan-500/10"
              aria-hidden="true"
            />
            <div class="relative overflow-x-auto">
              <table class="coh-table min-w-full text-left text-sm">
                <thead>
                  <tr
                    class="coh-row-head border-b-2 border-sky-200 bg-gradient-to-br from-sky-100/50 to-indigo-100/50 dark:border-sky-500/30 dark:from-sky-500/15 dark:to-indigo-500/15"
                  >
                    <th class="px-6 py-3.5 text-xs font-semibold uppercase tracking-wide text-[#1e3a8a] dark:text-sky-100">
                      字段
                    </th>
                    <th class="px-6 py-3.5 text-xs font-semibold uppercase tracking-wide text-[#1e3a8a] dark:text-sky-100">
                      内容
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(row, idx) in profileRows"
                    :key="row.label"
                    class="coh-table-row group/row border-b border-gray-100 transition-colors duration-200 dark:border-white/5"
                    :style="{ animationDelay: `${idx * 0.05}s` }"
                  >
                    <td class="relative px-6 py-4 align-top text-[#4b5563] dark:text-slate-400">
                      <span class="coh-row-accent" aria-hidden="true" />
                      {{ row.label }}
                    </td>
                    <td
                      class="px-6 py-4 align-top font-medium text-gray-900 dark:text-slate-100"
                      :class="
                        row.rainbow
                          ? 'coh-rainbow-num text-lg font-bold tabular-nums'
                          : row.important
                            ? 'bg-gradient-to-r from-blue-700 to-indigo-700 bg-clip-text text-transparent dark:from-sky-300 dark:to-indigo-300'
                            : ''
                      "
                    >
                      <span v-if="row.isMeta" class="inline-flex items-center gap-1.5 text-xs text-gray-500 dark:text-slate-400">
                        <Clock class="h-3.5 w-3.5 shrink-0" />
                        {{ row.value }}
                      </span>
                      <span v-else>{{ row.value }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <!-- 小屏：表格仍横向滚动；卡片式可后续增强 -->
          </div>
        </div>
      </div>

      <!-- 右侧评分卡 -->
      <div class="coh-score-enter relative lg:sticky lg:top-4">
        <div
          class="relative overflow-hidden rounded-2xl border border-indigo-200/60 bg-white/85 p-6 shadow-2xl shadow-indigo-200/40 backdrop-blur-xl dark:border-indigo-500/25 dark:bg-slate-900/80 dark:shadow-black/40"
        >
          <div
            class="pointer-events-none absolute inset-0 bg-gradient-to-br from-blue-50/30 via-violet-50/20 to-white dark:from-blue-500/10 dark:via-violet-500/10 dark:to-transparent"
            aria-hidden="true"
          />
          <div class="relative flex flex-col items-center text-center">
            <p class="mb-1 flex items-center justify-center gap-1.5 text-xs font-medium text-gray-500 dark:text-slate-400">
              <TrendingUp class="h-3.5 w-3.5 bg-gradient-to-br from-blue-500 to-violet-600 bg-clip-text text-transparent" />
              总分
            </p>

            <div class="relative mx-auto mt-1 h-44 w-44">
              <svg class="absolute inset-0 -rotate-90 text-sky-200/40 dark:text-slate-700" viewBox="0 0 120 120" aria-hidden="true">
                <defs>
                  <linearGradient id="cohRingGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#0284c7" />
                    <stop offset="50%" stop-color="#4f46e5" />
                    <stop offset="100%" stop-color="#7c3aed" />
                  </linearGradient>
                </defs>
                <circle cx="60" cy="60" :r="ringRadius" fill="none" stroke="currentColor" stroke-width="8" />
                <circle
                  cx="60"
                  cy="60"
                  :r="ringRadius"
                  fill="none"
                  stroke="url(#cohRingGrad)"
                  stroke-width="8"
                  stroke-linecap="round"
                  :stroke-dasharray="ringCirc"
                  :stroke-dashoffset="ringDashOffset"
                  class="transition-[stroke-dashoffset] duration-1000 ease-out"
                />
              </svg>
              <div class="absolute inset-0 flex flex-col items-center justify-center pt-1">
                <span
                  class="coh-score-num text-5xl font-extrabold tabular-nums sm:text-6xl"
                  :class="
                    numericScore > 0
                      ? 'bg-gradient-to-br from-blue-600 via-indigo-600 to-violet-600 bg-clip-text text-transparent'
                      : 'bg-gradient-to-br from-gray-400 via-gray-500 to-gray-400 bg-clip-text text-transparent'
                  "
                >
                  {{ scoreDisplay }}
                </span>
                <span v-if="numericScore <= 0" class="coh-score-glow pointer-events-none absolute bottom-6 h-10 w-24 rounded-full bg-gradient-to-r from-sky-400/30 to-violet-400/30 blur-xl" aria-hidden="true" />
              </div>
            </div>

            <div v-if="numericScore <= 0" class="mt-2 max-w-[220px] text-xs leading-relaxed text-gray-500 dark:text-slate-400">
              开始训练后将显示评分
            </div>
            <div v-else class="coh-score-glow-active pointer-events-none absolute top-1/2 h-16 w-32 -translate-y-1/2 rounded-full bg-gradient-to-r from-blue-400/25 to-violet-400/25 blur-2xl" aria-hidden="true" />

            <div class="mt-4 flex justify-center gap-1">
              <Star
                v-for="i in 5"
                :key="i"
                class="h-5 w-5"
                :class="
                  i <= filledStars
                    ? 'coh-star fill-amber-400 text-amber-400 drop-shadow-sm dark:fill-amber-300 dark:text-amber-300'
                    : 'text-gray-200 dark:text-slate-600'
                "
                :stroke-width="1.5"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 快速选择 + 表单（保留交互） -->
    <div class="coh-form-enter grid gap-6 lg:grid-cols-[1fr_320px]">
      <div class="ui-card-soft space-y-4 rounded-2xl border border-gray-200/60 bg-white/70 p-4 backdrop-blur-md dark:border-white/10 dark:bg-slate-900/50">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p class="text-sm font-bold text-gray-900 dark:text-white">快速选择</p>
            <p class="text-xs text-gray-500 dark:text-slate-400">点击卡片即可填入表单</p>
          </div>
          <span class="ui-badge ui-badge-subtle px-3 py-1 text-xs">单选卡片</span>
        </div>

        <div class="space-y-2">
          <div class="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500 dark:text-slate-400">目标岗位</div>
          <div class="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <button
              v-for="(role, index) in targetRoleSuggestions"
              :key="role"
              type="button"
              class="group relative overflow-hidden rounded-xl border px-3 py-2.5 text-left transition duration-200"
              :class="[
                pickTone(targetRoleToneClasses, targetRoleSelectedToneClasses, index, isSelectedText(normalizedTargetRole, role)),
                isSelectedText(normalizedTargetRole, role) ? 'translate-y-[-1px]' : 'hover:translate-y-[-1px]',
              ]"
              @click="setTargetRole(role)"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="truncate text-xs font-semibold leading-5">{{ role }}</span>
                <span
                  class="h-2 w-2 shrink-0 rounded-full transition"
                  :class="isSelectedText(normalizedTargetRole, role) ? 'bg-sky-600 dark:bg-sky-300' : 'bg-gray-300 dark:bg-slate-600'"
                />
              </div>
            </button>
          </div>
        </div>

        <div class="space-y-2">
          <div class="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500 dark:text-slate-400">职业目标</div>
          <div class="grid gap-2 sm:grid-cols-2">
            <button
              v-for="(goal, index) in careerGoalSuggestions"
              :key="goal"
              type="button"
              class="rounded-xl border px-3 py-2.5 text-left transition duration-200"
              :class="[
                pickTone(careerGoalToneClasses, careerGoalSelectedToneClasses, index, isSelectedText(normalizedCareerGoal, goal)),
                isSelectedText(normalizedCareerGoal, goal) ? 'translate-y-[-1px]' : 'hover:translate-y-[-1px]',
              ]"
              @click="setCareerGoal(goal)"
            >
              <div class="flex items-start gap-2">
                <span
                  class="mt-0.5 h-2 w-2 shrink-0 rounded-full transition"
                  :class="isSelectedText(normalizedCareerGoal, goal) ? 'bg-amber-600 dark:bg-amber-300' : 'bg-gray-300 dark:bg-slate-600'"
                />
                <span class="text-xs font-semibold leading-4">{{ goal }}</span>
              </div>
            </button>
          </div>
        </div>

        <div class="space-y-2">
          <div class="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500 dark:text-slate-400">规划周期</div>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="(month, index) in horizonSuggestions"
              :key="month"
              type="button"
              class="inline-flex min-w-[4rem] items-center justify-center rounded-full border px-3 py-1.5 text-xs font-semibold transition"
              :class="[
                pickTone(horizonToneClasses, horizonSelectedToneClasses, index, isSelectedNumber(horizonMonths, month)),
                isSelectedNumber(horizonMonths, month) ? 'translate-y-[-1px]' : 'hover:translate-y-[-1px]',
              ]"
              @click="setHorizonMonths(month)"
            >
              {{ month }}个月
            </button>
          </div>
        </div>

        <div class="grid gap-3 sm:grid-cols-3">
          <label class="space-y-1">
            <span class="text-xs font-semibold text-gray-600 dark:text-slate-300">目标岗位</span>
            <input :value="targetRole" type="text" placeholder="输入目标..." class="ui-input px-3 py-2 text-xs" @input="emitTargetRole" />
          </label>
          <label class="space-y-1">
            <span class="text-xs font-semibold text-gray-600 dark:text-slate-300">职业目标</span>
            <input :value="careerGoal" type="text" placeholder="输入目标..." class="ui-input px-3 py-2 text-xs" @input="emitCareerGoal" />
          </label>
          <label class="space-y-1">
            <span class="text-xs font-semibold text-gray-600 dark:text-slate-300">周期（月）</span>
            <input :value="horizonMonths" type="number" min="3" max="12" class="ui-input px-3 py-2 text-xs" @input="emitHorizonMonths" />
          </label>
        </div>
      </div>

      <!-- 底部数据项卡片列 -->
      <div class="space-y-3">
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class="ui-btn ui-btn-secondary px-3 py-2 text-xs font-semibold"
            @click="emit('refresh')"
          >
            <RefreshCcw class="h-3.5 w-3.5" />
            刷新
          </button>
          <button
            type="button"
            class="ui-btn ui-btn-primary px-4 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="generating"
            @click="emit('generate')"
          >
            <Rocket class="h-3.5 w-3.5" />
            {{ generating ? '生成中...' : '重新生成规划' }}
          </button>
        </div>

        <div
          class="coh-mini group relative overflow-hidden rounded-lg border border-gray-200/80 bg-white/70 p-4 transition-transform duration-200 will-change-transform hover:-translate-y-1 hover:scale-[1.02] dark:border-white/10 dark:bg-slate-900/50"
        >
          <div
            class="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
            style="background: linear-gradient(135deg, rgba(224, 242, 254, 0.35), rgba(243, 232, 255, 0.25))"
          />
          <div class="relative flex items-center gap-2">
            <span class="coh-icon-float inline-flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-sky-500 to-indigo-600 text-white shadow">
              💪
            </span>
            <p class="text-xs font-bold text-gray-800 dark:text-white">优势能力</p>
          </div>
          <div class="relative mt-2 flex flex-wrap gap-1">
            <span v-for="tag in strengthTags" :key="tag" class="ui-badge ui-badge-success">{{ tag }}</span>
            <span v-if="!strengthTags.length" class="text-[10px] text-gray-400">暂无数据</span>
          </div>
        </div>

        <div
          class="coh-mini group relative overflow-hidden rounded-lg border border-gray-200/80 bg-white/70 p-4 transition-transform duration-200 will-change-transform hover:-translate-y-1 hover:scale-[1.02] dark:border-white/10 dark:bg-slate-900/50"
        >
          <div
            class="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
            style="background: linear-gradient(135deg, rgba(254, 243, 199, 0.4), rgba(243, 232, 255, 0.25))"
          />
          <div class="relative flex items-center gap-2">
            <span class="coh-icon-float inline-flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500 to-rose-500 text-white shadow">
              🎯
            </span>
            <p class="text-xs font-bold text-gray-800 dark:text-white">待提升项</p>
          </div>
          <div class="relative mt-2 flex flex-wrap gap-1">
            <span v-for="tag in gapTags" :key="tag" class="ui-badge ui-badge-warning">{{ tag }}</span>
            <span v-if="!gapTags.length" class="text-[10px] text-gray-400">暂无数据</span>
          </div>
        </div>

        <div
          class="coh-mini group relative overflow-hidden rounded-lg border border-gray-200/80 bg-white/70 p-4 transition-transform duration-200 will-change-transform hover:-translate-y-1 hover:scale-[1.02] dark:border-white/10 dark:bg-slate-900/50"
        >
          <div
            class="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
            style="background: linear-gradient(135deg, rgba(224, 242, 254, 0.3), rgba(204, 251, 241, 0.25))"
          />
          <div class="relative flex items-center gap-2">
            <span class="coh-icon-float inline-flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-cyan-500 text-white shadow">
              📊
            </span>
            <p class="text-xs font-bold text-gray-800 dark:text-white">数据摘要</p>
          </div>
          <div class="relative mt-3 flex h-16 items-end justify-center gap-3 px-2">
            <div class="flex flex-col items-center gap-1">
              <div
                class="coh-bar w-6 rounded-t-md bg-gradient-to-t from-sky-600 to-indigo-500 shadow-sm transition-[height] duration-500"
                :style="{ height: `${Math.max(12, barHeights.plans)}%` }"
              />
              <span class="text-[10px] text-gray-500">计划</span>
            </div>
            <div class="flex flex-col items-center gap-1">
              <div
                class="coh-bar w-6 rounded-t-md bg-gradient-to-t from-violet-600 to-fuchsia-500 shadow-sm transition-[height] duration-500"
                :style="{ height: `${Math.max(12, barHeights.active)}%` }"
              />
              <span class="text-[10px] text-gray-500">活跃</span>
            </div>
            <div class="flex flex-col items-center gap-1">
              <div
                class="coh-bar w-6 rounded-t-md bg-gradient-to-t from-emerald-600 to-teal-500 shadow-sm transition-[height] duration-500"
                :style="{ height: `${Math.max(12, barHeights.done)}%` }"
              />
              <span class="text-[10px] text-gray-500">完成</span>
            </div>
          </div>
          <div class="relative mt-2 space-y-1.5 text-[11px]">
            <div class="flex justify-between">
              <span class="text-gray-500">计划总数</span>
              <span class="font-semibold text-gray-800 dark:text-slate-200">{{ store.stats.plan_count }} 个</span>
            </div>
            <div class="flex justify-between">
              <span class="text-gray-500">已完成任务</span>
              <span class="bg-gradient-to-r from-sky-600 to-emerald-600 bg-clip-text font-bold text-transparent">
                {{ store.stats.completed_task_count }} 个
              </span>
            </div>
            <div class="flex justify-between">
              <span class="text-gray-500">当前活跃</span>
              <span class="font-semibold text-indigo-600 dark:text-indigo-300">{{ store.stats.active_task_count }} 个</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
@reference "tailwindcss";

@media (prefers-reduced-motion: reduce) {
  .coh-main-card,
  .coh-score-enter,
  .coh-form-enter,
  .coh-badge-enter,
  .coh-table-row,
  .coh-icon-float,
  .coh-icon-spin,
  .coh-main-shine,
  .coh-badge-shine,
  .coh-score-glow-active,
  .coh-star {
    animation: none !important;
  }
  .coh-main-card .group:hover > div {
    transform: none !important;
  }
}

.coh-badge-enter {
  animation: coh-fade-up 0.75s cubic-bezier(0.215, 0.61, 0.355, 1) both;
  will-change: transform, opacity;
}
.coh-main-card > div:last-child {
  animation: coh-card-enter 1s cubic-bezier(0.215, 0.61, 0.355, 1) both;
  animation-delay: 0.1s;
  will-change: transform, opacity;
}
@media (min-width: 1024px) {
  .coh-main-card:hover > div:last-child {
    transform: translate3d(0, -12px, 0) perspective(900px) rotateX(3deg) rotateY(-3deg) scale3d(1.01, 1.01, 1);
  }
}

.coh-score-enter {
  animation: coh-score-in 1s cubic-bezier(0.215, 0.61, 0.355, 1) both;
  animation-delay: 0.4s;
  will-change: transform, opacity;
}
.coh-form-enter {
  animation: coh-fade-up 0.85s cubic-bezier(0.215, 0.61, 0.355, 1) both;
  animation-delay: 0.2s;
}

@keyframes coh-fade-up {
  from {
    opacity: 0;
    transform: translate3d(0, 14px, 0);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}
@keyframes coh-card-enter {
  from {
    opacity: 0;
    transform: translate3d(0, 60px, 0) perspective(800px) rotateX(-15deg);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0) perspective(800px) rotateX(0);
  }
}
@keyframes coh-score-in {
  from {
    opacity: 0;
    transform: translate3d(24px, 0, 0) scale(0.94);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0) scale(1);
  }
}

.coh-badge-shine {
  background: linear-gradient(
    105deg,
    transparent,
    rgba(255, 255, 255, 0.7),
    transparent
  );
  animation: coh-shine-x 3s linear infinite;
}
.coh-main-shine {
  background: linear-gradient(
    105deg,
    transparent,
    rgba(255, 255, 255, 0.55),
    transparent
  );
  animation: coh-shine-x 4.5s linear infinite;
}
@keyframes coh-shine-x {
  0% {
    transform: translate3d(-100%, 0, 0);
  }
  100% {
    transform: translate3d(100%, 0, 0);
  }
}

.coh-icon-float {
  animation: coh-float-y 2s ease-in-out infinite;
  will-change: transform;
}
@keyframes coh-float-y {
  0%,
  100% {
    transform: translate3d(0, 0, 0);
  }
  50% {
    transform: translate3d(0, -2px, 0);
  }
}

.coh-icon-spin {
  animation: coh-spin-slow 22s linear infinite;
  will-change: transform;
}
@keyframes coh-spin-slow {
  to {
    transform: rotate(360deg);
  }
}

.coh-table-row {
  animation: coh-row-in 0.45s cubic-bezier(0.215, 0.61, 0.355, 1) both;
  background: rgba(255, 255, 255, 0.45);
}
.dark .coh-table-row {
  background: rgba(15, 23, 42, 0.25);
}
@keyframes coh-row-in {
  from {
    opacity: 0;
    transform: translate3d(0, 8px, 0);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}

.coh-row-accent {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  border-radius: 0 4px 4px 0;
  background: linear-gradient(180deg, #38bdf8, #6366f1, #a855f7);
  opacity: 0;
  transform: scaleY(0.6);
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}
.coh-table-row:hover {
  background: linear-gradient(90deg, rgba(224, 242, 254, 0.3), rgba(243, 232, 255, 0.2)) !important;
}
.coh-table-row:hover .coh-row-accent {
  opacity: 1;
  transform: scaleY(1);
}

.coh-score-num {
  animation: coh-breathe 2s ease-in-out infinite;
  will-change: opacity;
}
@keyframes coh-breathe {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.72;
  }
}

.coh-score-glow-active {
  animation: coh-glow-pulse 3s ease-in-out infinite;
  will-change: opacity;
}
@keyframes coh-glow-pulse {
  0%,
  100% {
    opacity: 0.2;
  }
  50% {
    opacity: 0.42;
  }
}

.coh-star {
  animation: coh-star-twinkle 2.4s ease-in-out infinite;
  animation-delay: calc(var(--i, 0) * 0.12s);
  will-change: opacity, transform;
}
.coh-star:nth-child(1) {
  --i: 0;
}
.coh-star:nth-child(2) {
  --i: 1;
}
.coh-star:nth-child(3) {
  --i: 2;
}
.coh-star:nth-child(4) {
  --i: 3;
}
.coh-star:nth-child(5) {
  --i: 4;
}
@keyframes coh-star-twinkle {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.75;
    transform: scale(1.06);
  }
}

.coh-rainbow-num {
  background-image: linear-gradient(90deg, #0284c7, #4f46e5, #7c3aed);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: coh-breathe 2s ease-in-out infinite;
  will-change: opacity;
}

.coh-bar {
  min-height: 6px;
  max-height: 52px;
  will-change: height;
}
</style>
