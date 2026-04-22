<script setup lang="ts">
import { ref, watch, computed } from 'vue'
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
  const avgProgress = total > 0 ? Math.round(store.tasks.reduce((sum, t) => sum + (t.progress || 0), 0) / total) : 0
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
  <section class="space-y-5">
    <!-- 页面标题区 -->
    <div
      class="ui-card relative overflow-hidden rounded-3xl border border-gray-200/60 bg-[linear-gradient(135deg,rgba(224,242,254,0.5)_0%,rgba(219,234,254,0.6)_50%,rgba(255,255,255,0.8)_100%)] p-6 shadow-[0_8px_24px_rgba(59,130,246,0.06)] dark:border-white/10 dark:bg-[linear-gradient(135deg,rgba(15,23,42,0.9)_0%,rgba(30,41,59,0.86)_48%,rgba(15,23,42,0.92)_100%)]"
    >
      <div class="absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white/40 dark:bg-white/10"></div>
      <div class="absolute -bottom-5 -right-5 h-24 w-24 rounded-full bg-white/30 dark:bg-white/5"></div>
      <div class="relative flex items-center justify-between">
        <div>
          <p class="text-xs font-semibold uppercase tracking-widest text-blue-800/80 dark:text-blue-200/80">任务追踪</p>
          <h1 class="mt-2 text-3xl font-black tracking-tight text-blue-900 dark:text-blue-100">把每个里程碑拆成可执行任务并持续推进</h1>
          <p class="mt-2 max-w-xl text-sm text-blue-800/80 dark:text-slate-300">聚焦当下正在做的事情，支持单个任务标记完成、推进进度和记录阶段性备注。</p>
        </div>
        <div class="hidden lg:flex items-center gap-3">
          <div class="flex -space-x-2">
            <div class="h-10 w-10 rounded-full bg-white/20 flex items-center justify-center text-lg backdrop-blur-sm dark:bg-white/10">📋</div>
            <div class="h-10 w-10 rounded-full bg-white/20 flex items-center justify-center text-lg backdrop-blur-sm dark:bg-white/10">🎯</div>
            <div class="h-10 w-10 rounded-full bg-white/20 flex items-center justify-center text-lg backdrop-blur-sm dark:bg-white/10">🚀</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 统计概览卡片 -->
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <div class="ui-card-soft rounded-2xl border border-gray-200/60 bg-white/90 p-4 backdrop-blur-xl dark:border-white/10 dark:bg-slate-900/70">
        <div class="flex items-center gap-2">
          <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-sky-100 to-blue-100 text-blue-800">
            📋
          </div>
          <div>
            <p class="text-2xl font-black text-slate-900 dark:text-white">{{ stats.total }}</p>
            <p class="text-xs text-slate-500 dark:text-slate-400">总任务</p>
          </div>
        </div>
      </div>

      <div class="ui-card-soft rounded-2xl border border-gray-200/60 bg-white/90 p-4 backdrop-blur-xl dark:border-white/10 dark:bg-slate-900/70">
        <div class="flex items-center gap-2">
          <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-sky-100 to-blue-100 text-blue-800">
            ✓
          </div>
          <div>
            <p class="text-2xl font-black text-blue-900 dark:text-blue-200">{{ stats.completed }}</p>
            <p class="text-xs text-slate-500 dark:text-slate-400">已完成</p>
          </div>
        </div>
      </div>

      <div class="ui-card-soft rounded-2xl border border-gray-200/60 bg-white/90 p-4 backdrop-blur-xl dark:border-white/10 dark:bg-slate-900/70">
        <div class="flex items-center gap-2">
          <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-sky-100 to-blue-100 text-blue-800">
            ⏳
          </div>
          <div>
            <p class="text-2xl font-black text-blue-900 dark:text-blue-200">{{ stats.inProgress }}</p>
            <p class="text-xs text-slate-500 dark:text-slate-400">进行中</p>
          </div>
        </div>
      </div>

      <div class="ui-card-soft rounded-2xl border border-gray-200/60 bg-white/90 p-4 backdrop-blur-xl dark:border-white/10 dark:bg-slate-900/70">
        <div class="flex items-center gap-2">
          <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-sky-100 to-blue-100 text-blue-800">
            📊
          </div>
          <div>
            <p class="text-2xl font-black text-blue-900 dark:text-blue-200">{{ stats.avgProgress }}%</p>
            <p class="text-xs text-slate-500 dark:text-slate-400">平均进度</p>
          </div>
        </div>
      </div>
    </div>

    <!-- 进度条概览 -->
    <div class="ui-card-soft rounded-2xl p-4">
      <div class="flex items-center justify-between mb-2">
        <p class="text-sm font-semibold text-slate-700 dark:text-white">整体完成进度</p>
        <p class="text-sm font-bold text-blue-700 dark:text-blue-300">{{ stats.total > 0 ? Math.round((stats.completed / stats.total) * 100) : 0 }}%</p>
      </div>
      <div class="h-3 overflow-hidden rounded-full bg-slate-200 dark:bg-white/10">
        <div 
          class="h-full rounded-full bg-gradient-to-r from-sky-400 to-blue-500 transition-all duration-500"
          :style="{ width: `${stats.total > 0 ? (stats.completed / stats.total) * 100 : 0}%` }"
        ></div>
      </div>
    </div>

    <!-- 任务看板 -->
    <CareerTaskBoard
      :tasks="store.tasks"
      :selected-task-id="selectedTaskId"
      @select-task="handleSelectTask"
      @complete-task="markTaskComplete"
      @add-progress="addProgress"
    />
  </section>
</template>