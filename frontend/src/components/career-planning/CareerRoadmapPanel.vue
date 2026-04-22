<script setup lang="ts">
import { Layers3, CheckCircle2, Circle, Clock } from 'lucide-vue-next'
import type { CareerMilestone } from '../../types/career-planning'

defineProps<{
  milestones: CareerMilestone[]
}>()

function getStatusConfig(status: string) {
  if (status === 'completed') {
    return {
      icon: CheckCircle2,
      color: 'text-blue-700 dark:text-blue-300',
      bg: 'bg-sky-100 dark:bg-blue-500/20',
      border: 'border-blue-200 dark:border-blue-500/30',
    }
  } else if (status === 'in_progress') {
    return {
      icon: Clock,
      color: 'text-sky-700 dark:text-sky-300',
      bg: 'bg-sky-100 dark:bg-sky-500/20',
      border: 'border-sky-200 dark:border-sky-500/30',
    }
  }
  return {
    icon: Circle,
    color: 'text-slate-400 dark:text-slate-500',
    bg: 'bg-slate-100 dark:bg-white/10',
    border: 'border-slate-200 dark:border-white/10',
  }
}

const gradients = [
  'from-sky-400 to-blue-500',
  'from-sky-500 to-blue-600',
  'from-blue-400 to-blue-600',
  'from-sky-400 to-blue-500',
  'from-sky-500 to-blue-600',
  'from-blue-400 to-blue-600',
]
</script>

<script lang="ts">
export default {
  name: 'CareerRoadmapPanel',
}
</script>

<template>
  <section class="ui-card rounded-3xl p-5">
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-sky-100 to-blue-100 text-[#1e40af] shadow-[0_8px_24px_rgba(59,130,246,0.06)]">
          <Layers3 class="h-5 w-5" />
        </div>
        <div>
          <h2 class="text-xl font-black text-slate-900 dark:text-white">阶段路线图</h2>
          <p class="text-sm text-slate-500 dark:text-slate-400">按里程碑推进，优先完成最关键的能力补齐和作品沉淀。</p>
        </div>
      </div>
      <div class="ui-card-soft flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300">
        {{ milestones.length }} 个阶段
      </div>
    </div>

    <!-- 时间轴容器 -->
    <div class="relative mt-6">
      <!-- 连接线 -->
      <div class="absolute left-1/2 top-0 h-full w-0.5 -translate-x-1/2 bg-gradient-to-b from-sky-400 via-blue-500 to-blue-600 opacity-20 dark:opacity-30 md:hidden"></div>
      
      <!-- 桌面端：横向三列 -->
      <div class="hidden md:grid md:grid-cols-3 gap-4">
        <article
          v-for="(milestone, index) in milestones"
          :key="milestone.id"
          class="group relative rounded-2xl border-2 p-5 transition-all duration-300 hover:-translate-y-1 hover:shadow-xl"
          :class="[
            getStatusConfig(milestone.status).border,
            milestone.status === 'completed' 
              ? 'bg-gradient-to-br from-sky-50/40 to-white dark:from-blue-500/10 dark:to-[#0C0F17]' 
              : 'bg-white/80 dark:bg-[#0C0F17]/80'
          ]"
        >
          <!-- 阶段指示器 -->
          <div class="absolute -top-3 left-4 flex items-center gap-2">
            <span 
              class="flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold text-white shadow-lg"
              :class="`bg-gradient-to-br ${gradients[index % gradients.length]}`"
            >
              {{ index + 1 }}
            </span>
            <span 
                class="ui-badge"
                :class="milestone.status === 'completed' ? 'ui-badge-info' : milestone.status === 'in_progress' ? 'ui-badge-subtle' : 'ui-badge-subtle'"
            >
              {{ milestone.month_label }}
            </span>
          </div>

          <!-- 状态图标 -->
          <div class="absolute -right-2 -top-2 flex h-8 w-8 items-center justify-center rounded-full bg-white shadow-md dark:bg-[#0C0F17] dark:shadow-none" :class="getStatusConfig(milestone.status).color">
            <component :is="getStatusConfig(milestone.status).icon" class="h-4 w-4" />
          </div>

          <!-- 内容 -->
          <div class="pt-4">
            <h3 class="text-base font-bold text-slate-900 dark:text-white group-hover:text-blue-700 dark:group-hover:text-blue-300 transition-colors">
              {{ milestone.title }}
            </h3>
            <p class="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
              {{ milestone.description }}
            </p>
            
            <!-- 标签 -->
            <div class="mt-4 flex items-center justify-between">
              <span 
                class="ui-badge"
                :class="milestone.status === 'completed' ? 'ui-badge-info' : milestone.status === 'in_progress' ? 'ui-badge-subtle' : 'ui-badge-subtle'"
              >
                {{ milestone.status === 'completed' ? '已完成' : milestone.status === 'in_progress' ? '进行中' : '待开始' }}
              </span>
              <span class="text-xs text-slate-400 dark:text-slate-500">{{ milestone.target_date }}</span>
            </div>
          </div>
        </article>
      </div>

      <!-- 移动端：垂直时间轴 -->
      <div class="relative md:hidden">
        <div class="absolute left-5 top-0 h-full w-0.5 bg-gradient-to-b from-sky-400 via-blue-500 to-blue-600"></div>
        
        <div class="space-y-4">
          <article
            v-for="(milestone, index) in milestones"
            :key="milestone.id"
            class="relative ml-0 rounded-2xl border-2 p-4 transition-all duration-300"
            :class="[
              getStatusConfig(milestone.status).border,
              milestone.status === 'completed' 
                ? 'bg-gradient-to-br from-sky-50/40 to-white dark:from-blue-500/10 dark:to-[#0C0F17]' 
                : 'bg-white/80 dark:bg-[#0C0F17]/80'
            ]"
          >
            <div class="absolute -left-4 top-4 flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold text-white shadow-lg" :class="`bg-gradient-to-br ${gradients[index % gradients.length]}`">
              {{ index + 1 }}
            </div>
            
            <div class="ml-2 flex items-start justify-between gap-3">
              <div class="flex-1 pt-1">
                <div class="flex items-center gap-2 mb-1">
                  <span class="ui-badge ui-badge-info">
                    {{ milestone.month_label }}
                  </span>
                </div>
                <h3 class="text-sm font-bold text-slate-900 dark:text-white">{{ milestone.title }}</h3>
                <p class="mt-1 text-xs leading-relaxed text-slate-600 dark:text-slate-400 line-clamp-2">{{ milestone.description }}</p>
              </div>
              <div class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full" :class="getStatusConfig(milestone.status).bg">
                <component :is="getStatusConfig(milestone.status).icon" class="h-3.5 w-3.5" :class="getStatusConfig(milestone.status).color" />
              </div>
            </div>
          </article>
        </div>
      </div>
    </div>
  </section>
</template>
