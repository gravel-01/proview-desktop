<script setup lang="ts">
import { computed } from 'vue'
import { BookOpen, ExternalLink, Star } from 'lucide-vue-next'
import type { CareerDocRecommendation } from '../../types/career-planning'

/**
 * Phase 5: 侧边栏只保留"推荐文档章节"。其余 4 个单元（能力画像 /
 * 数据来源与证据 / 资源建议 / 计划历史）已下沉到 Hero 内的
 * CareerOverviewInsightGrid 2×2 网格,本组件只承载资源闭环入口。
 */
const props = defineProps<{
  // Phase 4: 文档推荐 & 收藏(来自 dashboard.doc_recommendations / favorite_doc_ids)
  docRecommendations?: CareerDocRecommendation[]
  favoriteDocIds?: string[]
}>()

const emit = defineEmits<{
  // Phase 4: 点击推荐文档章节 → 跳转到文档库对应位置
  'open-doc': [{ docId: string; sectionIdx: number; reason: string }]
  // Phase 4: 收藏 / 取消收藏(顶栏快捷入口)
  'toggle-favorite': [docId: string]
}>()

// Phase 4: 推荐文档(来自 dashboard.doc_recommendations)
const relevantDocs = computed<CareerDocRecommendation[]>(() => {
  const list = props.docRecommendations || []
  // 按 score 降序、相关任务数降序,确保最有用的章节在最上面
  return [...list].sort((a, b) => {
    const scoreDiff = (b.score ?? 0) - (a.score ?? 0)
    if (Math.abs(scoreDiff) > 0.001) return scoreDiff
    return (b.related_task_ids?.length || 0) - (a.related_task_ids?.length || 0)
  })
})

// Phase 4: 收藏集合(来自 dashboard.favorite_doc_ids)
const favoriteIdSet = computed<Set<string>>(() => new Set(props.favoriteDocIds || []))

function isFavorited(docId: string | undefined): boolean {
  if (!docId) return false
  return favoriteIdSet.value.has(docId)
}

function readStateLabel(rec: CareerDocRecommendation): string {
  if (rec.read_state === 'completed') return '已读'
  if (rec.read_state === 'in_progress') return '阅读中'
  return '未读'
}

function readStateClass(rec: CareerDocRecommendation): string {
  const state = rec.read_state
  if (state === 'completed') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/15 dark:text-emerald-200'
  }
  if (state === 'in_progress') {
    return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/15 dark:text-amber-200'
  }
  return 'border-slate-200 bg-slate-50 text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300'
}

function openDoc(rec: CareerDocRecommendation) {
  emit('open-doc', { docId: rec.doc_id, sectionIdx: rec.section_idx, reason: rec.reason || rec.section_heading || '' })
}

function toggleFavorite(docId: string | undefined) {
  if (!docId) return
  emit('toggle-favorite', docId)
}
</script>

<script lang="ts">
export default {
  name: 'CareerInsightSidebar',
}
</script>

<template>
  <div class="space-y-6">
    <!-- Phase 4: 资源闭环 → 推荐文档章节(基于 gap / skill / task_type 个性化) -->
    <section
      v-if="relevantDocs.length"
      class="rounded-3xl border border-indigo-200/80 bg-indigo-50/40 p-5 shadow-sm dark:border-indigo-500/30 dark:bg-indigo-500/10"
      data-testid="career-doc-recommendations"
    >
      <div class="flex items-center justify-between gap-2">
        <div class="flex items-center gap-3">
          <BookOpen class="h-5 w-5 text-indigo-600" />
          <div>
            <h2 class="text-lg font-black text-indigo-900 dark:text-indigo-200">推荐文档章节</h2>
            <p class="text-[11px] text-indigo-700/80 dark:text-indigo-300/80">
              基于你的 gap 与任务类型 · 共 {{ relevantDocs.length }} 条
            </p>
          </div>
        </div>
        <span class="rounded-full border border-indigo-200 bg-white/80 px-2 py-0.5 text-[10px] font-semibold text-indigo-700 dark:border-indigo-500/40 dark:bg-indigo-500/15 dark:text-indigo-200">
          资源闭环
        </span>
      </div>

      <div class="mt-4 space-y-2.5">
        <article
          v-for="rec in relevantDocs.slice(0, 4)"
          :key="`${rec.doc_id}-${rec.section_idx}`"
          class="group rounded-2xl border border-white/70 bg-white/85 p-3 shadow-sm transition hover:border-indigo-300 hover:shadow-md dark:border-white/10 dark:bg-white/5"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-1.5">
                <span class="truncate text-sm font-bold text-slate-900 dark:text-white">{{ rec.section_heading }}</span>
                <span
                  class="shrink-0 rounded-full border px-1.5 py-0.5 text-[10px] font-medium"
                  :class="readStateClass(rec)"
                >
                  {{ readStateLabel(rec) }}
                </span>
              </div>
              <p class="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                {{ rec.doc_title }} · 匹配分 {{ (rec.score ?? 0).toFixed(2) }}
              </p>
            </div>
            <button
              @click.stop="toggleFavorite(rec.doc_id)"
              class="shrink-0 rounded-full p-1 text-rose-500 transition hover:bg-rose-50 dark:hover:bg-rose-500/15"
              :title="isFavorited(rec.doc_id) ? '取消收藏' : '收藏'"
            >
              <Star class="h-4 w-4" :class="isFavorited(rec.doc_id) ? 'fill-current' : ''" />
            </button>
          </div>

          <p
            v-if="rec.reason"
            class="mt-1.5 line-clamp-2 text-[11px] leading-5 text-slate-600 dark:text-slate-300"
          >
            {{ rec.reason }}
          </p>

          <div class="mt-2 flex items-center justify-between gap-2">
            <p
              v-if="rec.related_task_ids && rec.related_task_ids.length"
              class="truncate text-[10px] text-slate-400 dark:text-slate-500"
            >
              关联任务:{{ rec.related_task_ids.length }} 个
            </p>
            <span v-else class="text-[10px] text-slate-300 dark:text-slate-600">·</span>
            <button
              @click="openDoc(rec)"
              class="inline-flex items-center gap-1 rounded-full bg-indigo-600 px-2.5 py-1 text-[11px] font-semibold text-white shadow-sm transition hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-400"
            >
              <ExternalLink class="h-3 w-3" />
              打开章节
            </button>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>
