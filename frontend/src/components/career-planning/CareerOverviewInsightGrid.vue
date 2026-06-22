<script setup lang="ts">
/**
 * Phase 5: 2×2 洞察网格
 * ----------------------------------------------------------------
 * 把分散在 Hero 右栏 + InsightSidebar 中的 4 个核心洞察单元
 * （能力画像 / 数据来源与证据 / 资源建议 / 计划历史）收敛到主
 * Hero 下方，以 2×2 网格呈现：
 *
 *   ┌──────────────┬──────────────┐
 *   │ ① 能力画像   │ ② 数据来源与证据 │
 *   ├──────────────┼──────────────┤
 *   │ ③ 资源建议   │ ④ 计划历史   │
 *   └──────────────┴──────────────┘
 *
 * 设计原则：
 * - 只读展示：不引入新的写操作；事件 `select-plan` / `open-doc` 透传
 *   到父页面，由 store 完成更新
 * - 容错友好：所有 prop 都有空态；类型不一致时降级为 [] / 0
 * - 可扩展：预留 `insights` 槽位，phase 6+ 可注入 LLM 生成的洞察
 *   卡片（不影响现有 4 单元）
 */
import { computed } from 'vue'
import { Database, FileSearch, FileText, Sparkles, Target } from 'lucide-vue-next'
import type {
  CareerEvidenceSample,
  CareerPlan,
  CareerProfile,
  CareerRecommendation,
  CareerSourceSnapshot,
} from '../../types/career-planning'

// ---------------------------------------------------------------------------
// Props / Emits
// ---------------------------------------------------------------------------

const props = defineProps<{
  profile: CareerProfile | Record<string, unknown> | null
  recommendations: CareerRecommendation[]
  plans: CareerPlan[]
  currentPlan: CareerPlan | Record<string, unknown> | null
  sourceSnapshot?: CareerSourceSnapshot | null
  topEvidence?: CareerEvidenceSample[]
}>()

const emit = defineEmits<{
  'select-plan': [planId: number]
  'open-doc': [{ docId: string; sectionIdx: number; reason: string }]
}>()

// ---------------------------------------------------------------------------
// 数据解析（容错：所有 JSON 字段失败 → []，不抛错）
// ---------------------------------------------------------------------------

const profileData = computed<CareerProfile | null>(() => {
  return props.profile && typeof props.profile === 'object' ? (props.profile as unknown as CareerProfile) : null
})

/** 优势 tag：来自 profile.strength_tags (JSON 字符串) */
const strengthTags = computed<string[]>(() => {
  try {
    const raw = profileData.value?.strength_tags
    if (!raw) return []
    return typeof raw === 'string' ? JSON.parse(raw) : Array.isArray(raw) ? raw : []
  } catch {
    return []
  }
})

/** 差距 tag：来自 profile.gap_tags (JSON 字符串) */
const gapTags = computed<string[]>(() => {
  try {
    const raw = profileData.value?.gap_tags
    if (!raw) return []
    return typeof raw === 'string' ? JSON.parse(raw) : Array.isArray(raw) ? raw : []
  } catch {
    return []
  }
})

/** 当前 plan id（用于历史高亮） */
const currentPlanId = computed<number | null>(() => {
  const cp = props.currentPlan
  if (!cp || typeof cp !== 'object') return null
  return (cp as unknown as CareerPlan).id ?? null
})

/** 代表证据：默认 3 条；store/profile 缺数据时为空 */
const evidenceList = computed<CareerEvidenceSample[]>(() => {
  return (props.topEvidence || []).slice(0, 3)
})

/** 数据源 bullets：把 sourceSnapshot 拍平成可展示的多行 */
const sourceBulletLines = computed<string[]>(() => {
  const snap = props.sourceSnapshot
  if (!snap) return []
  const lines: string[] = []
  if (snap.has_resume) {
    lines.push('简历:已上传')
  } else {
    lines.push('简历:未上传(将走基础模板)')
  }
  lines.push(`面试:${snap.session_count ?? 0} 次(完成 ${snap.completed_session_count ?? 0})`)
  if (typeof snap.evaluation_count === 'number') {
    lines.push(`逐轮评价:${snap.evaluation_count} 条`)
  }
  if (typeof snap.low_score_evaluation_count === 'number' && snap.low_score_evaluation_count > 0) {
    lines.push(`低分 (<7):${snap.low_score_evaluation_count} 条`)
  }
  if (typeof snap.avg_score === 'number' && snap.avg_score > 0) {
    lines.push(`平均分:${snap.avg_score.toFixed(1)}`)
  }
  if (snap.data_client_kind) {
    lines.push(`数据源:${snap.data_client_kind}`)
  }
  return lines
})

/** 计划历史：最多 6 条，按 id 倒序 */
const planList = computed<CareerPlan[]>(() => {
  return (props.plans || []).slice(0, 6)
})

/** 资源建议：最多 3 条，避免首屏过长 */
const recommendationList = computed<CareerRecommendation[]>(() => {
  return (props.recommendations || []).slice(0, 3)
})

// ---------------------------------------------------------------------------
// 事件回调
// ---------------------------------------------------------------------------

function handleSelectPlan(planId: number) {
  emit('select-plan', planId)
}
</script>

<script lang="ts">
export default {
  name: 'CareerOverviewInsightGrid',
}
</script>

<template>
  <!-- 2×2 洞察网格：在 lg 视口下双列，sm 视口下单列堆叠 -->
  <div
    class="grid gap-3 sm:grid-cols-1 lg:grid-cols-2"
    data-testid="career-overview-insight-grid"
  >
    <!-- ① 能力画像 -->
    <section
      class="flex flex-col gap-2.5 rounded-2xl border border-slate-200/85 bg-white/90 p-4 shadow-sm dark:border-white/10 dark:bg-[#0C0F17]/90"
      data-testid="insight-cell-profile"
    >
      <header class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-100 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300">
            <Target class="h-4 w-4" />
          </span>
          <h3 class="text-sm font-black text-slate-900 dark:text-white">能力画像</h3>
        </div>
        <span class="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400">
          Profile
        </span>
      </header>

      <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <div>
          <p class="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">优势标签</p>
          <div class="mt-1.5 flex flex-wrap gap-1">
            <span
              v-for="tag in strengthTags.slice(0, 6)"
              :key="`s-${tag}`"
              class="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-200"
            >
              {{ tag }}
            </span>
            <span v-if="!strengthTags.length" class="text-[10px] text-slate-400">等待真实评价数据</span>
          </div>
        </div>
        <div>
          <p class="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">差距标签</p>
          <div class="mt-1.5 flex flex-wrap gap-1">
            <span
              v-for="tag in gapTags.slice(0, 6)"
              :key="`g-${tag}`"
              class="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-500/20 dark:text-amber-200"
            >
              {{ tag }}
            </span>
            <span v-if="!gapTags.length" class="text-[10px] text-slate-400">暂无真实数据</span>
          </div>
        </div>
      </div>

      <p
        v-if="profileData?.source_summary"
        class="rounded-xl bg-slate-50 p-2.5 text-[11px] leading-5 text-slate-600 dark:bg-white/5 dark:text-slate-300 line-clamp-2"
      >
        {{ profileData.source_summary }}
      </p>
    </section>

    <!-- ② 数据来源与证据 -->
    <section
      class="flex flex-col gap-2.5 rounded-2xl border border-slate-200/85 bg-white/90 p-4 shadow-sm dark:border-white/10 dark:bg-[#0C0F17]/90"
      data-testid="insight-cell-source"
    >
      <header class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-100 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-300">
            <Database class="h-4 w-4" />
          </span>
          <h3 class="text-sm font-black text-slate-900 dark:text-white">数据来源与证据</h3>
        </div>
        <span class="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400">
          Evidence
        </span>
      </header>

      <div v-if="sourceBulletLines.length" class="rounded-xl bg-slate-50 p-2.5 dark:bg-white/5">
        <p class="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          <FileSearch class="h-3 w-3" />数据来源
        </p>
        <ul class="mt-1.5 space-y-0.5 text-[11px] leading-5 text-slate-600 dark:text-slate-300">
          <li v-for="line in sourceBulletLines" :key="line" class="flex items-start gap-1.5">
            <span class="mt-1 h-1 w-1 shrink-0 rounded-full bg-emerald-500"></span>
            <span>{{ line }}</span>
          </li>
        </ul>
      </div>
      <p v-else class="rounded-xl bg-slate-50 p-2.5 text-[11px] leading-5 text-slate-500 dark:bg-white/5 dark:text-slate-400">
        等待后端聚合数据源快照。
      </p>

      <div v-if="evidenceList.length" class="space-y-1.5">
        <p class="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">代表证据</p>
        <ol class="space-y-1.5">
          <li
            v-for="(ev, idx) in evidenceList"
            :key="`${ev.session_id || ''}-${ev.turn_id || ''}-${idx}`"
            class="rounded-xl border border-slate-200/80 bg-slate-50/70 p-2.5 text-[11px] leading-5 dark:border-white/10 dark:bg-white/5"
          >
            <div class="flex flex-wrap items-center gap-1.5 text-[10px] text-slate-500 dark:text-slate-400">
              <span class="rounded-full bg-indigo-50 px-1.5 py-0.5 font-mono text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-200">
                {{ ev.dimension || '-' }}
              </span>
              <span class="rounded-full bg-rose-50 px-1.5 py-0.5 text-rose-700 dark:bg-rose-500/20 dark:text-rose-200">
                {{ ev.score ?? '-' }} 分
              </span>
              <span v-if="ev.turn_no">第 {{ ev.turn_no }} 轮</span>
            </div>
            <p class="mt-1 line-clamp-2 text-slate-700 dark:text-slate-200">"{{ ev.evidence }}"</p>
          </li>
        </ol>
      </div>
    </section>

    <!-- ③ 资源建议 -->
    <section
      class="flex flex-col gap-2.5 rounded-2xl border border-slate-200/85 bg-white/90 p-4 shadow-sm dark:border-white/10 dark:bg-[#0C0F17]/90"
      data-testid="insight-cell-recommendations"
    >
      <header class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="flex h-7 w-7 items-center justify-center rounded-lg bg-sky-100 text-sky-600 dark:bg-sky-500/20 dark:text-sky-300">
            <FileText class="h-4 w-4" />
          </span>
          <h3 class="text-sm font-black text-slate-900 dark:text-white">资源建议</h3>
        </div>
        <span class="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400">
          Resources
        </span>
      </header>

      <div v-if="recommendationList.length" class="space-y-2">
        <article
          v-for="rec in recommendationList"
          :key="rec.title"
          class="rounded-xl border border-slate-200/80 bg-slate-50/70 p-2.5 dark:border-white/10 dark:bg-white/5"
        >
          <p class="text-[10px] font-bold uppercase tracking-wide text-indigo-600 dark:text-indigo-300">
            {{ rec.type }}
          </p>
          <h4 class="mt-1 text-sm font-bold text-slate-900 dark:text-white line-clamp-1">
            {{ rec.title }}
          </h4>
          <p class="mt-1 text-[11px] leading-5 text-slate-600 dark:text-slate-400 line-clamp-2">
            {{ rec.reason }}
          </p>
        </article>
      </div>
      <p v-else class="rounded-xl bg-slate-50 p-3 text-[11px] leading-5 text-slate-500 dark:bg-white/5 dark:text-slate-400">
        等待生成职业规划后展示学习资源 / 课程 / 项目建议。
      </p>
    </section>

    <!-- ④ 计划历史 -->
    <section
      class="flex flex-col gap-2.5 rounded-2xl border border-slate-200/85 bg-white/90 p-4 shadow-sm dark:border-white/10 dark:bg-[#0C0F17]/90"
      data-testid="insight-cell-plans"
    >
      <header class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="flex h-7 w-7 items-center justify-center rounded-lg bg-purple-100 text-purple-600 dark:bg-purple-500/20 dark:text-purple-300">
            <Sparkles class="h-4 w-4" />
          </span>
          <h3 class="text-sm font-black text-slate-900 dark:text-white">计划历史</h3>
        </div>
        <span class="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400">
          {{ planList.length }} 条
        </span>
      </header>

      <div v-if="planList.length" class="space-y-1.5">
        <button
          v-for="plan in planList"
          :key="plan.id"
          type="button"
          @click="handleSelectPlan(plan.id)"
          class="w-full rounded-xl border px-3 py-2 text-left transition"
          :class="currentPlanId === plan.id
            ? 'border-indigo-300 bg-indigo-50 dark:border-indigo-500/40 dark:bg-indigo-500/15'
            : 'border-slate-200 bg-slate-50 hover:border-indigo-300 dark:border-white/10 dark:bg-white/5 dark:hover:border-indigo-500/40'"
        >
          <div class="flex items-center justify-between gap-2">
            <p class="truncate text-[12px] font-bold text-slate-900 dark:text-white">
              {{ plan.target_role }}
            </p>
            <span
              v-if="currentPlanId === plan.id"
              class="shrink-0 rounded-full bg-indigo-600 px-1.5 py-0.5 text-[9px] font-bold text-white"
            >
              当前
            </span>
          </div>
          <p class="mt-0.5 line-clamp-1 text-[10px] text-slate-500 dark:text-slate-400">
            {{ plan.summary || '无摘要' }}
          </p>
          <div class="mt-1 flex items-center gap-1.5 text-[9px] text-slate-400">
            <span>{{ plan.status || '-' }}</span>
            <span>·</span>
            <span>{{ plan.horizon_months || 0 }} 个月</span>
          </div>
        </button>
      </div>
      <p v-else class="rounded-xl bg-slate-50 p-3 text-[11px] leading-5 text-slate-500 dark:bg-white/5 dark:text-slate-400">
        暂无历史规划，点击「重新生成规划」开始第一份。
      </p>
    </section>
  </div>
</template>
