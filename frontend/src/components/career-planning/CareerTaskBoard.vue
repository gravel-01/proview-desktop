<script setup lang="ts">
import { CheckCircle2, Clock, Zap, BookOpen, Target, Code, GraduationCap, List } from 'lucide-vue-next'
import type { CareerTask } from '../../types/career-planning'

defineProps<{
  tasks: CareerTask[]
  selectedTaskId: number | null
}>()

const emit = defineEmits<{
  'select-task': [taskId: number]
  'complete-task': [taskId: number]
  'add-progress': [taskId: number]
}>()

// Icon component mapping based on backend task_type_icon field
const iconComponents = {
  'book-open': BookOpen,
  'target': Target,
  'code': Code,
  'graduation-cap': GraduationCap,
  'list': List,
}

function getTaskTypeIconComponent(iconName?: string) {
  return iconComponents[iconName as keyof typeof iconComponents] || List
}

function getProgressColor(progress: number) {
  if (progress >= 75) return 'from-blue-500 to-blue-600'
  if (progress >= 50) return 'from-sky-500 to-blue-500'
  if (progress >= 25) return 'from-sky-400 to-blue-400'
  return 'from-slate-400 to-slate-500'
}
</script>

<script lang="ts">
export default {
  name: 'CareerTaskBoard',
}
</script>

<template>
  <section class="ui-card rounded-3xl p-5">
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-sky-100 to-blue-100 text-[#1e40af] shadow-[0_8px_24px_rgba(59,130,246,0.06)]">
          📋
        </div>
        <div>
          <h2 class="text-xl font-black text-slate-900 dark:text-white">执行任务</h2>
          <p class="text-sm text-slate-500 dark:text-slate-400">把规划拆成具体动作，逐项完成并记录进度。</p>
        </div>
      </div>
      <div class="ui-card-soft flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300">
        {{ tasks.length }} 项任务
      </div>
    </div>

    <div class="mt-5 space-y-3">
      <article
        v-for="task in tasks"
        :key="task.id"
        class="group relative rounded-2xl border-2 p-4 transition-all duration-200 cursor-pointer"
        :class="selectedTaskId === task.id 
          ? 'border-blue-300 bg-sky-50/40 shadow-[0_8px_24px_rgba(59,130,246,0.1)] dark:border-blue-500/40 dark:bg-blue-500/10 dark:shadow-none'
          : 'border-slate-200/80 bg-white/85 hover:border-blue-300 hover:shadow-md dark:border-white/10 dark:bg-[#0C0F17]/80 dark:hover:border-blue-500/30'"
        @click="emit('select-task', task.id)"
      >
        <div class="flex items-start gap-4">
          <!-- 左侧：类型图标 + 进度环 -->
          <div class="relative shrink-0">
            <div class="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 dark:bg-white/10">
              <component :is="getTaskTypeIconComponent(task.task_type_icon)" class="h-6 w-6 text-slate-600 dark:text-slate-300" />
            </div>
            <!-- 进度环 -->
            <svg class="absolute -bottom-1 -right-1 h-6 w-6 -rotate-90 transform" viewBox="0 0 36 36">
              <circle
                cx="18" cy="18" r="15"
                fill="none"
                stroke="currentColor"
                stroke-width="3"
                class="text-slate-200 dark:text-white/20"
              />
              <circle
                cx="18" cy="18" r="15"
                fill="none"
                stroke="url(#progressGradient)"
                stroke-width="3"
                stroke-linecap="round"
                :stroke-dasharray="`${(task.progress || 0) * 0.942} 100`"
                class="transition-all duration-500"
              />
              <defs>
                <linearGradient id="progressGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" :class="task.progress >= 75 ? 'stop-color-blue-500' : task.progress >= 50 ? 'stop-color-sky-500' : task.progress >= 25 ? 'stop-color-sky-400' : 'stop-color-slate-400'" />
                  <stop offset="100%" :class="task.progress >= 75 ? 'stop-color-blue-700' : task.progress >= 50 ? 'stop-color-blue-600' : task.progress >= 25 ? 'stop-color-blue-500' : 'stop-color-slate-500'" />
                </linearGradient>
              </defs>
            </svg>
          </div>

          <!-- 中间：内容 -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <span 
                class="ui-badge"
                :class="task.status === 'completed' 
                  ? 'ui-badge-success' 
                  : 'ui-badge-info'"
              >
                {{ task.task_type_label }}
              </span>
              <span class="text-[10px] text-slate-400">{{ task.progress || 0 }}%</span>
            </div>
            <h3 class="text-base font-bold text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-300 transition-colors line-clamp-1">
              {{ task.title }}
            </h3>
            <p class="mt-1 text-sm leading-relaxed text-slate-600 dark:text-slate-400 line-clamp-2">
              {{ task.description }}
            </p>
            
            <!-- 进度条 -->
            <div class="mt-3 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-white/10">
              <div 
                class="h-full rounded-full bg-gradient-to-r transition-all duration-500"
                :class="getProgressColor(task.progress || 0)"
                :style="{ width: `${task.progress || 0}%` }"
              ></div>
            </div>
            
            <!-- 底部信息 -->
            <div class="mt-3 flex items-center justify-between text-xs">
              <div class="flex items-center gap-3">
                <span 
                  class="flex items-center gap-1"
                  :class="task.status === 'completed' ? 'text-blue-700 dark:text-blue-300' : 'text-slate-500 dark:text-slate-400'"
                >
                  <component 
                    :is="task.status === 'completed' ? CheckCircle2 : Clock" 
                    class="h-3.5 w-3.5" 
                  />
                  {{ task.status === 'completed' ? '已完成' : '进行中' }}
                </span>
                <span class="text-slate-400 dark:text-slate-500">截止：{{ task.due_date }}</span>
              </div>
            </div>
          </div>

          <!-- 右侧：操作按钮 -->
          <div class="flex shrink-0 flex-col gap-2">
            <button
              v-if="task.status !== 'completed'"
              @click.stop="emit('add-progress', task.id)"
              class="ui-btn ui-btn-secondary px-3 py-2 text-xs font-semibold"
            >
              <Zap class="h-3 w-3" />
              +25%
            </button>
            <button
              v-if="task.status !== 'completed'"
              @click.stop="emit('complete-task', task.id)"
              class="ui-btn ui-btn-primary px-3 py-2 text-xs font-semibold"
            >
              <CheckCircle2 class="h-3 w-3" />
              完成
            </button>
            <div 
              v-else
              class="flex h-[42px] items-center justify-center rounded-xl bg-sky-100 px-3 text-xs font-semibold text-blue-700 dark:bg-blue-500/20 dark:text-blue-300"
            >
              ✓ 已完成
            </div>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>
