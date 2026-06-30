<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import CareerOverviewHero from '../../components/career-planning/CareerOverviewHero.vue'
import CareerInsightSidebar from '../../components/career-planning/CareerInsightSidebar.vue'
import { useCareerPlanningStore } from '../../stores/careerPlanning'

const store = useCareerPlanningStore()
const router = useRouter()

async function handleRefresh() {
  try {
    await store.loadDashboard({ force: true })
  } catch (error) {
    store.error = error instanceof Error ? error.message : '刷新职业规划失败'
  }
}

async function handleGenerate() {
  try {
    await store.createPlan({
      target_role: store.targetRole,
      career_goal: store.careerGoal,
      horizon_months: store.horizonMonths,
      refresh: true,
    })
  } catch (error) {
    store.error = error instanceof Error ? error.message : '生成职业规划失败'
  }
}

function handleSelectPlan(planId: number) {
  store.selectPlan(planId)
}

// Phase 4: 资源闭环 → 点击侧边栏推荐章节 → 跳转文档库对应位置
function handleOpenDoc(payload: { docId: string; sectionIdx: number; reason: string }) {
  router.push({
    name: 'career-planning-docs',
    query: {
      doc_id: payload.docId,
      section_idx: String(payload.sectionIdx),
      reason: payload.reason || '',
    },
  })
}

// Phase 4: 侧边栏快捷收藏
async function handleToggleFavorite(docId: string) {
  try {
    await store.toggleDocFavorite(docId)
  } catch (error) {
    store.error = error instanceof Error ? error.message : '更新收藏失败'
  }
}

/**
 * Phase 5: 顶部证据样例。取自 profile.evidence_samples 的前 3 条,
 * 在 Hero 的 2×2 网格中作为"数据来源与证据"单元的展示数据。
 */
const topEvidenceForGrid = computed(() => {
  const samples = (store.profile?.evidence_samples || []) as Array<{
    session_id?: string
    turn_id?: string
    turn_no?: number
    dimension?: string
    score?: number
    evidence?: string
  }>
  return samples.slice(0, 3)
})

/**
 * Phase 5: 是否展示"推荐文档章节"侧边栏。
 * 当后端返回 doc_recommendations 或用户已收藏过文档时显示。
 */
const shouldShowDocSidebar = computed(() => {
  return (store.docRecommendations && store.docRecommendations.length > 0) ||
    (store.favoriteDocIds && store.favoriteDocIds.length > 0)
})
</script>

<template>
  <section class="space-y-4">
    <!--
      Phase 5: 4 个单元(能力画像 / 数据来源与证据 / 资源建议 / 计划历史)
      已下沉到 CareerOverviewHero 内部的 2×2 网格 CareerOverviewInsightGrid,
      本页面仅保留 Hero + 资源闭环入口(推荐文档章节)。
    -->
    <CareerOverviewHero
      :profile="store.profile"
      :stats="store.stats"
      :target-role="store.targetRole"
      :career-goal="store.careerGoal"
      :horizon-months="store.horizonMonths"
      :generating="store.generating"
      :recommendations="store.recommendations"
      :plans="store.plans"
      :current-plan="store.currentPlan"
      :source-snapshot="store.profile?.source_snapshot || null"
      :top-evidence-for-grid="topEvidenceForGrid"
      @update:target-role="store.targetRole = $event"
      @update:career-goal="store.careerGoal = $event"
      @update:horizon-months="store.horizonMonths = $event"
      @refresh="handleRefresh"
      @generate="handleGenerate"
      @select-plan="handleSelectPlan"
      @open-doc="handleOpenDoc"
    />

    <!--
      资源闭环入口: 推荐文档章节(仅在有数据时展示)
    -->
    <div v-if="shouldShowDocSidebar" class="grid gap-4">
      <CareerInsightSidebar
        :doc-recommendations="store.docRecommendations"
        :favorite-doc-ids="store.favoriteDocIds"
        @open-doc="handleOpenDoc"
        @toggle-favorite="handleToggleFavorite"
      />
    </div>
  </section>
</template>
