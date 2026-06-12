<script setup lang="ts">
import CareerOverviewHero from '../../components/career-planning/CareerOverviewHero.vue'
import CareerInsightSidebar from '../../components/career-planning/CareerInsightSidebar.vue'
import { useCareerPlanningStore } from '../../stores/careerPlanning'

const store = useCareerPlanningStore()

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
</script>

<template>
  <section class="space-y-4">
    <CareerOverviewHero
      :profile="store.profile"
      :stats="store.stats"
      :target-role="store.targetRole"
      :career-goal="store.careerGoal"
      :horizon-months="store.horizonMonths"
      :generating="store.generating"
      @update:target-role="store.targetRole = $event"
      @update:career-goal="store.careerGoal = $event"
      @update:horizon-months="store.horizonMonths = $event"
      @refresh="handleRefresh"
      @generate="handleGenerate"
    />

    <div v-if="store.recommendations.length || (store.plans && store.plans.length > 1)" class="grid gap-4 lg:grid-cols-3">
      <CareerInsightSidebar
        :profile="store.profile"
        :recommendations="store.recommendations"
        :plans="store.plans"
        :current-plan="store.currentPlan"
        @select-plan="handleSelectPlan"
      />
    </div>
  </section>
</template>