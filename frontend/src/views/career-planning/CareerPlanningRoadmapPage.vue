<script setup lang="ts">
import { computed } from 'vue'
import CareerRoadmapPanel from '../../components/career-planning/CareerRoadmapPanel.vue'
import { useCareerPlanningStore } from '../../stores/careerPlanning'

const store = useCareerPlanningStore()

const completedCount = computed(() => store.milestones.filter(m => m.status === 'completed').length)
const progressPercent = computed(() => store.milestones.length ? Math.round((completedCount.value / store.milestones.length) * 100) : 0)
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
          <p class="text-xs font-semibold uppercase tracking-widest text-blue-800/80 dark:text-blue-200/80">路线图</p>
          <h1 class="mt-2 text-3xl font-black tracking-tight text-blue-900 dark:text-blue-100">按阶段展开目标、里程碑和预期结果</h1>
          <p class="mt-2 max-w-xl text-sm text-blue-800/80 dark:text-slate-300">这是一条从当前状态到目标岗位的线性路线，适合快速检查每一阶段是否已经按计划推进。</p>
        </div>
        <div class="hidden lg:flex items-center gap-4">
          <div class="text-center">
            <p class="text-3xl font-black text-blue-900 dark:text-blue-100">{{ completedCount }}/{{ store.milestones.length }}</p>
            <p class="text-xs text-blue-700/80 dark:text-blue-200/80">已完成阶段</p>
          </div>
          <div class="h-12 w-12 rounded-full bg-white/70 flex items-center justify-center dark:bg-white/10">
            <span class="text-xl">📍</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 进度概览 -->
    <div class="ui-card-soft rounded-2xl p-4">
      <div class="flex items-center justify-between mb-2">
        <p class="text-sm font-semibold text-slate-700 dark:text-white">整体进度</p>
        <p class="text-sm font-bold text-blue-700 dark:text-blue-300">{{ progressPercent }}%</p>
      </div>
      <div class="h-2.5 overflow-hidden rounded-full bg-slate-200 dark:bg-white/10">
        <div 
          class="h-full rounded-full bg-gradient-to-r from-sky-400 to-blue-500 transition-all duration-500"
          :style="{ width: `${progressPercent}%` }"
        ></div>
      </div>
    </div>

    <!-- 路线图面板 -->
    <CareerRoadmapPanel :milestones="store.milestones" />
  </section>
</template>