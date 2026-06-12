<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { Activity, CheckCircle2, Clock3, ListTodo } from 'lucide-vue-next'
import CareerTaskBoard from '../../components/career-planning/CareerTaskBoard.vue'
import { useCareerPlanningStore } from '../../stores/careerPlanning'

const store = useCareerPlanningStore()
const selectedTaskId = ref<number | null>(null)

watch(
  () => store.tasks,
  () => {
    selectedTaskId.value = store.tasks.find((task) => task.status !== 'completed')?.id || store.tasks[0]?.id || null
  },
  { immediate: true },
)

const stats = computed(() => {
  const total = store.tasks.length
  const completed = store.tasks.filter(t => t.status === 'completed').length
  const inProgress = total - completed
  // 任务页平均进度与 dashboard.stats.progress_rate 口径一致，
  // 避免 dashboard / roadmap / tasks 三处进度数字相互矛盾。
  const avgProgress = typeof store.stats?.progress_rate === 'number' ? store.stats.progress_rate : 0
  return { total, completed, inProgress, avgProgress }
})

async function markTaskComplete(taskId: number) {
  try {
    await store.patchTask(taskId, { status: 'completed', progress: 100, note: '由任务追踪页完成' })
  } catch (error) {
    store.error = error instanceof Error ? error.message : '更新任务失败'
  }
}

async function addProgress(taskId: number) {
  try {
    const task = store.getTaskById(taskId)
    const nextProgress = Math.min(100, (task?.progress || 0) + 25)
    await store.logTask(taskId, { progress: nextProgress, note: '推进了阶段性任务' })
  } catch (error) {
    store.error = error instanceof Error ? error.message : '记录任务进度失败'
  }
}

function handleSelectTask(taskId: number) {
  selectedTaskId.value = taskId
}
</script>

<template>
  <section class="career-tasks-page space-y-5">
    <div class="career-tasks-page__hero ui-card">
      <div>
        <span class="ui-section-badge">任务追踪</span>
        <h1 class="ui-page-title mt-4 text-3xl">把每个里程碑拆成可执行任务并持续推进</h1>
        <p class="ui-page-subtitle mt-3 max-w-2xl text-sm leading-7">
          聚焦当前正在做的事项，支持逐条记录进度、快速标记完成，并持续沉淀阶段性动作。
        </p>
      </div>

      <div class="career-tasks-page__stats">
        <div class="career-tasks-page__stat">
          <div class="career-tasks-page__stat-icon">
            <ListTodo class="h-4 w-4" />
          </div>
          <div>
            <span class="career-tasks-page__stat-label">总任务</span>
            <strong class="career-tasks-page__stat-value">{{ stats.total }}</strong>
          </div>
        </div>

        <div class="career-tasks-page__stat">
          <div class="career-tasks-page__stat-icon career-tasks-page__stat-icon--success">
            <CheckCircle2 class="h-4 w-4" />
          </div>
          <div>
            <span class="career-tasks-page__stat-label">已完成</span>
            <strong class="career-tasks-page__stat-value">{{ stats.completed }}</strong>
          </div>
        </div>

        <div class="career-tasks-page__stat">
          <div class="career-tasks-page__stat-icon career-tasks-page__stat-icon--warning">
            <Clock3 class="h-4 w-4" />
          </div>
          <div>
            <span class="career-tasks-page__stat-label">进行中</span>
            <strong class="career-tasks-page__stat-value">{{ stats.inProgress }}</strong>
          </div>
        </div>

        <div class="career-tasks-page__stat">
          <div class="career-tasks-page__stat-icon">
            <Activity class="h-4 w-4" />
          </div>
          <div>
            <span class="career-tasks-page__stat-label">平均进度</span>
            <strong class="career-tasks-page__stat-value">{{ stats.avgProgress }}%</strong>
          </div>
        </div>
      </div>
    </div>

    <div class="career-tasks-page__progress ui-card-soft">
      <div class="mb-2 flex items-center justify-between">
        <p class="text-sm font-semibold text-slate-700 dark:text-white">整体完成进度</p>
        <p class="text-sm font-bold text-indigo-600 dark:text-indigo-300">{{ stats.total > 0 ? Math.round((stats.completed / stats.total) * 100) : 0 }}%</p>
      </div>
      <div class="career-tasks-page__bar">
        <div class="career-tasks-page__bar-fill" :style="{ width: `${stats.total > 0 ? (stats.completed / stats.total) * 100 : 0}%` }"></div>
      </div>
    </div>

    <CareerTaskBoard
      :tasks="store.tasks"
      :selected-task-id="selectedTaskId"
      @select-task="handleSelectTask"
      @complete-task="markTaskComplete"
      @add-progress="addProgress"
    />
  </section>
</template>

<style scoped>
.career-tasks-page__hero {
  position: relative;
  overflow: hidden;
  display: grid;
  gap: 1.1rem;
  padding: 1.6rem;
}

.career-tasks-page__hero::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 14% 18%, rgba(59, 130, 246, 0.14), transparent 28%),
    radial-gradient(circle at 88% 22%, rgba(99, 102, 241, 0.1), transparent 24%);
  pointer-events: none;
}

.career-tasks-page__stats {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.career-tasks-page__stat {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  border-radius: 1.2rem;
  border: 1px solid var(--ui-border-subtle);
  background: var(--ui-surface-raised);
  padding: 1rem;
  box-shadow: var(--ui-shadow-sm);
}

.career-tasks-page__stat-icon {
  display: inline-flex;
  width: 2.5rem;
  height: 2.5rem;
  align-items: center;
  justify-content: center;
  border-radius: 0.95rem;
  background: rgba(59, 130, 246, 0.12);
  color: var(--ui-accent-strong);
  flex-shrink: 0;
}

.career-tasks-page__stat-icon--success {
  background: rgba(16, 185, 129, 0.12);
  color: var(--ui-success);
}

.career-tasks-page__stat-icon--warning {
  background: rgba(245, 158, 11, 0.14);
  color: var(--ui-warning);
}

.career-tasks-page__stat-label {
  display: block;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ui-text-muted);
}

.career-tasks-page__stat-value {
  display: block;
  margin-top: 0.4rem;
  font-size: 1.4rem;
  font-weight: 900;
  color: var(--ui-text-primary);
}

.career-tasks-page__progress {
  padding: 1rem;
}

.career-tasks-page__bar {
  height: 0.7rem;
  overflow: hidden;
  border-radius: 9999px;
  background: rgba(148, 163, 184, 0.18);
}

.career-tasks-page__bar-fill {
  height: 100%;
  border-radius: 9999px;
  background: linear-gradient(90deg, #3b82f6, #4f46e5);
  transition: width 300ms ease;
}

.dark .career-tasks-page__stat {
  background: rgba(15, 23, 42, 0.72);
}

@media (max-width: 960px) {
  .career-tasks-page__stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .career-tasks-page__stats {
    grid-template-columns: 1fr;
  }
}
</style>
