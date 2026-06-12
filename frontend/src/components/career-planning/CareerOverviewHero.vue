<script setup lang="ts">
import { computed } from 'vue'
import { BarChart3, RefreshCcw, Rocket, ShieldCheck, Sparkles, Target, TrendingUp } from 'lucide-vue-next'
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
            <div class="hidden items-center gap-1.5 self-center rounded-full border border-slate-200 bg-white/80 px-2.5 py-1 text-[10px] font-bold text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300 sm:inline-flex"
                 :title="`简历:${(store.profile as any)?.has_resume ? '已上传' : '未上传'} · 面试:${(store.profile as any)?.session_count ?? 0}次 · 评价:${(store.profile as any)?.evaluation_count ?? 0}条`">
              <span class="h-1.5 w-1.5 rounded-full"
                    :class="{
                      'bg-emerald-500': (store.profile as any)?.generation_mode === 'evidence',
                      'bg-amber-500': (store.profile as any)?.generation_mode === 'fallback',
                      'bg-rose-500': (store.profile as any)?.generation_mode === 'empty',
                      'bg-slate-400': !(store.profile as any)?.generation_mode,
                    }"></span>
              <span>{{
                (store.profile as any)?.generation_mode === 'evidence' ? '基于真实评价' :
                (store.profile as any)?.generation_mode === 'fallback' ? '基础模板（缺评价）' :
                (store.profile as any)?.generation_mode === 'empty' ? '数据不足' : '未生成'
              }}</span>
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

      <!-- 主内容区：左侧表单 + 右侧能力分析 -->
      <div class="grid gap-6 lg:grid-cols-[1fr_320px]">
        <!-- 左侧：快速选择表单 -->
        <div class="space-y-4 rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
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

          <!-- 待提升项 -->
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
        </div>
      </div>
    </div>
  </section>
</template>
