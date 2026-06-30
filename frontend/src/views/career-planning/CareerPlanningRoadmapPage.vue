<script setup lang="ts">
import { computed } from 'vue'
import CareerRoadmapPanel from '../../components/career-planning/CareerRoadmapPanel.vue'
import { useCareerPlanningStore } from '../../stores/careerPlanning'

const store = useCareerPlanningStore()

// 阶段完成数与总进度：根据任务聚合，milestone.status 由后端统一计算，
// 不再依赖前端硬性按 milestone.status === 'completed' 计数。
const completedCount = computed(() => store.milestones.filter(m => m.status === 'completed').length)
const progressPercent = computed(() => {
  // 优先使用 stats.progress_rate（已与任务进度同步），fallback 到阶段完成率
  if (typeof store.stats?.progress_rate === 'number' && store.stats.progress_rate >= 0) {
    return store.stats.progress_rate
  }
  if (!store.milestones.length) return 0
  return Math.round((completedCount.value / store.milestones.length) * 100)
})
</script>

<template>
  <section class="career-roadmap-page space-y-5">
    <div class="career-roadmap-page__hero ui-card">
      <div>
        <span class="ui-section-badge">路线图</span>
        <h1 class="ui-page-title mt-4 text-3xl">按阶段展开目标、里程碑和预期结果</h1>
        <p class="ui-page-subtitle mt-3 max-w-2xl text-sm leading-7">
          这是一条从当前状态推进到目标岗位的阶段路线，适合快速检查每个阶段是否已经按计划完成。
        </p>
      </div>

      <div class="career-roadmap-page__stats">
        <div class="career-roadmap-page__stat">
          <span class="career-roadmap-page__stat-label">阶段数</span>
          <strong class="career-roadmap-page__stat-value">{{ store.milestones.length }}</strong>
        </div>
        <div class="career-roadmap-page__stat">
          <span class="career-roadmap-page__stat-label">已完成</span>
          <strong class="career-roadmap-page__stat-value">{{ completedCount }}</strong>
        </div>
        <div class="career-roadmap-page__stat">
          <span class="career-roadmap-page__stat-label">整体进度</span>
          <strong class="career-roadmap-page__stat-value">{{ progressPercent }}%</strong>
        </div>
      </div>
    </div>

    <div class="career-roadmap-page__progress ui-card-soft">
      <div class="mb-2 flex items-center justify-between">
        <p class="text-sm font-semibold text-slate-700 dark:text-white">整体进度</p>
        <p class="text-sm font-bold text-indigo-600 dark:text-indigo-300">{{ progressPercent }}%</p>
      </div>
      <div class="career-roadmap-page__bar">
        <div class="career-roadmap-page__bar-fill" :style="{ width: `${progressPercent}%` }"></div>
      </div>
    </div>

    <CareerRoadmapPanel :milestones="store.milestones" />
  </section>
</template>

<style scoped>
.career-roadmap-page__hero {
  position: relative;
  overflow: hidden;
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(260px, 0.8fr);
  gap: 1.1rem;
  padding: 1.6rem;
}

.career-roadmap-page__hero::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 14% 18%, rgba(59, 130, 246, 0.14), transparent 28%),
    radial-gradient(circle at 88% 20%, rgba(99, 102, 241, 0.12), transparent 24%);
  pointer-events: none;
}

.career-roadmap-page__stats {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-content: end;
}

.career-roadmap-page__stat {
  border-radius: 1.2rem;
  border: 1px solid var(--ui-border-subtle);
  background: var(--ui-surface-raised);
  padding: 1rem;
  box-shadow: var(--ui-shadow-sm);
}

.career-roadmap-page__stat-label {
  display: block;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ui-text-muted);
}

.career-roadmap-page__stat-value {
  display: block;
  margin-top: 0.45rem;
  font-size: 1.4rem;
  font-weight: 900;
  color: var(--ui-text-primary);
}

.career-roadmap-page__progress {
  padding: 1rem;
}

.career-roadmap-page__bar {
  height: 0.7rem;
  overflow: hidden;
  border-radius: 9999px;
  background: rgba(148, 163, 184, 0.18);
}

.career-roadmap-page__bar-fill {
  height: 100%;
  border-radius: 9999px;
  background: linear-gradient(90deg, #3b82f6, #4f46e5);
  transition: width 300ms ease;
}

.dark .career-roadmap-page__stat {
  background: rgba(15, 23, 42, 0.72);
}

@media (max-width: 960px) {
  .career-roadmap-page__hero,
  .career-roadmap-page__stats {
    grid-template-columns: 1fr;
  }
}
</style>
