<script setup lang="ts">
import { CheckCircle2, Clock, ListTodo, Zap, BookOpen, Target, Code, GraduationCap, List, ExternalLink } from 'lucide-vue-next'
import type { CareerTask } from '../../types/career-planning'

defineProps<{
  tasks: CareerTask[]
  selectedTaskId: number | null
}>()

const emit = defineEmits<{
  'select-task': [taskId: number]
  'complete-task': [taskId: number]
  'add-progress': [taskId: number]
  // Phase 4: task → doc section 跳转事件
  'open-doc': [{ docId: string; sectionIdx: number; reason: string }]
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
  if (progress >= 100) return 'from-sky-500 to-indigo-500'
  if (progress >= 75) return 'from-indigo-500 to-cyan-500'
  if (progress >= 50) return 'from-cyan-500 to-sky-500'
  if (progress >= 25) return 'from-slate-500 to-sky-500'
  return 'from-slate-400 to-slate-500'
}
</script>

<script lang="ts">
export default {
  name: 'CareerTaskBoard',
}
</script>

<template>
  <section class="rounded-3xl border border-slate-200/85 bg-white/90 p-5 shadow-[0_18px_48px_rgba(15,23,42,0.08)] dark:border-white/10 dark:bg-[#0F1420]/92">
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <div class="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white/90 text-indigo-600 dark:border-white/10 dark:bg-white/10 dark:text-indigo-300">
          <ListTodo class="h-5 w-5" />
        </div>
        <div>
          <h2 class="text-xl font-black text-slate-900 dark:text-white">执行任务</h2>
          <p class="text-sm text-slate-500 dark:text-slate-400">把规划拆成具体动作，逐项完成并记录进度。</p>
        </div>
      </div>
      <div class="flex items-center gap-2 rounded-full border border-slate-200 bg-white/80 px-3 py-1.5 text-xs font-semibold text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
        {{ tasks.length }} 项任务
      </div>
    </div>

    <div class="mt-5 space-y-3">
      <article
        v-for="task in tasks"
        :key="task.id"
        class="group relative cursor-pointer rounded-2xl border p-4 transition-all duration-200"
        :class="selectedTaskId === task.id
          ? 'border-indigo-300 bg-sky-50/84 shadow-[0_14px_30px_rgba(79,70,229,0.12)] dark:border-indigo-400/40 dark:bg-indigo-500/14 dark:shadow-none'
          : 'border-slate-200/80 bg-white/84 hover:border-indigo-300 hover:shadow-md dark:border-white/10 dark:bg-[#111827]/78 dark:hover:border-indigo-500/30'"
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
                  <stop offset="0%" :class="task.progress >= 75 ? 'stop-color-indigo-500' : task.progress >= 50 ? 'stop-color-cyan-500' : task.progress >= 25 ? 'stop-color-slate-500' : 'stop-color-slate-400'" />
                  <stop offset="100%" :class="task.progress >= 75 ? 'stop-color-cyan-500' : task.progress >= 50 ? 'stop-color-sky-500' : task.progress >= 25 ? 'stop-color-sky-500' : 'stop-color-slate-500'" />
                </linearGradient>
              </defs>
            </svg>
          </div>

          <!-- 中间：内容 -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <span
                class="rounded-full px-2 py-0.5 text-[10px] font-bold"
                :class="task.status === 'completed'
                  ? 'bg-sky-100 text-sky-700 dark:bg-sky-500/20 dark:text-sky-300'
                  : 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300'"
              >
                {{ task.task_type_label }}
              </span>
              <span class="text-[10px] text-slate-400">{{ task.progress || 0 }}%</span>
            </div>
            <h3 class="text-base font-bold text-slate-900 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors line-clamp-1">
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

            <!-- Phase 4: 任务 → 文档章节 关联跳转按钮（resource_refs 由后端 tag_resource_to_task 派生） -->
            <div
              v-if="task.resource_refs && task.resource_refs.length"
              class="mt-3 rounded-xl border border-indigo-200/70 bg-indigo-50/60 p-2.5 dark:border-indigo-500/30 dark:bg-indigo-500/10"
              data-testid="task-resource-refs"
            >
              <div class="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-indigo-600 dark:text-indigo-300">
                <BookOpen class="h-3 w-3" />
                推荐资源 · {{ task.resource_refs.length }} 条
              </div>
              <div class="flex flex-wrap gap-1.5">
                <button
                  v-for="ref in task.resource_refs"
                  :key="`${ref.doc_id}-${ref.section_idx}`"
                  @click.stop="emit('open-doc', { docId: ref.doc_id, sectionIdx: ref.section_idx, reason: ref.reason })"
                  class="group inline-flex max-w-full items-center gap-1 rounded-full border border-indigo-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-indigo-700 shadow-sm transition hover:border-indigo-400 hover:bg-indigo-100 hover:text-indigo-900 dark:border-indigo-500/40 dark:bg-indigo-500/15 dark:text-indigo-200 dark:hover:bg-indigo-500/25"
                  :title="ref.reason"
                >
                  <span class="truncate">📚 {{ ref.reason || '查看文档' }}</span>
                  <ExternalLink class="h-3 w-3 shrink-0 opacity-60 group-hover:opacity-100" />
                </button>
              </div>
            </div>

            <!-- 底部信息 -->
            <div class="mt-3 flex items-center justify-between text-xs">
              <div class="flex items-center gap-3">
                <span 
                  class="flex items-center gap-1"
                  :class="task.status === 'completed' ? 'text-sky-600 dark:text-sky-400' : 'text-slate-500 dark:text-slate-400'"
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
              class="flex items-center justify-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm transition-all hover:border-indigo-300 hover:text-indigo-600 hover:shadow-md dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:border-indigo-500/30"
            >
              <Zap class="h-3 w-3" />
              +25%
            </button>
            <button
              v-if="task.status !== 'completed'"
              @click.stop="emit('complete-task', task.id)"
              class="flex items-center justify-center gap-1 rounded-xl border border-indigo-300 bg-sky-50 px-3 py-2 text-xs font-semibold text-indigo-900 shadow-[0_14px_30px_rgba(79,70,229,0.12)] transition-all hover:shadow-[0_16px_34px_rgba(79,70,229,0.16)] dark:border-indigo-400/40 dark:bg-indigo-500/14 dark:text-white"
            >
              <CheckCircle2 class="h-3 w-3" />
              完成
            </button>
            <div 
              v-else
              class="flex h-[42px] items-center justify-center rounded-xl bg-sky-100 px-3 text-xs font-semibold text-sky-700 dark:bg-sky-500/20 dark:text-sky-300"
            >
              ✓ 已完成
            </div>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>
