<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { BookOpen, LayoutDashboard, ListTodo, Map, Sparkles } from 'lucide-vue-next'
import { useCareerPlanningStore } from '../stores/careerPlanning'

const store = useCareerPlanningStore()
const route = useRoute()
const router = useRouter()

const tabs = [
  { name: 'career-planning-overview', label: '简历分析', icon: LayoutDashboard },
  { name: 'career-planning-roadmap', label: '技能掌握度', icon: Map },
  { name: 'career-planning-tasks', label: '任务追踪', icon: ListTodo },
  { name: 'career-planning-docs', label: '评价结果', icon: BookOpen },
] as const

type CareerPlanningTab = (typeof tabs)[number]

const currentTab = computed<CareerPlanningTab>(() => {
  const routeName = typeof route.name === 'string' ? route.name : ''
  return tabs.find((tab) => tab.name === routeName) || tabs[0]
})

function goTo(routeName: CareerPlanningTab['name']) {
  if (route.name === routeName) return
  router.push({ name: routeName })
}

onMounted(async () => {
  await Promise.all([
    store.loadDashboard(),
    store.loadDocs(),
  ])
})
</script>

<template>
  <div class="cp-page relative isolate overflow-hidden rounded-3xl pb-6">
    <!-- 极简主背景 -->
    <div
      class="pointer-events-none absolute inset-0 bg-gradient-to-br from-sky-50/40 via-white to-violet-50/30 dark:from-slate-950 dark:via-slate-950 dark:to-slate-900"
      aria-hidden="true"
    />
    <div
      class="cp-orb cp-orb-sky pointer-events-none absolute h-[600px] w-[600px] rounded-full blur-3xl"
      aria-hidden="true"
    />
    <div
      class="cp-orb cp-orb-indigo pointer-events-none absolute h-[550px] w-[550px] rounded-full blur-3xl"
      aria-hidden="true"
    />
    <div
      class="pointer-events-none absolute inset-0 opacity-[0.005]"
      style="
        background-image: radial-gradient(rgb(0 0 0 / 1) 1px, transparent 1px);
        background-size: 60px 60px;
      "
      aria-hidden="true"
    />

    <div class="relative z-[1] space-y-6">
      <!-- 顶部标题区 -->
      <section class="cp-hero-enter rounded-2xl border border-gray-200/60 bg-white/80 p-6 shadow-[0_8px_24px_rgba(59,130,246,0.06)] backdrop-blur-xl dark:border-white/10 dark:bg-slate-900/70 sm:p-7">
        <div
          class="pointer-events-none absolute inset-0 rounded-2xl bg-gradient-to-br from-sky-50/20 via-white/10 to-indigo-50/20 dark:from-sky-500/5 dark:via-transparent dark:to-indigo-500/5"
          aria-hidden="true"
        />
        <div class="relative flex flex-col gap-5">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div class="min-w-0 space-y-3">
              <div class="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-gradient-to-r from-sky-50/90 to-white px-3 py-1.5 text-xs font-semibold text-blue-800 dark:border-blue-400/30 dark:from-sky-500/10 dark:to-slate-900 dark:text-blue-200">
                <Sparkles class="h-3.5 w-3.5" />
                职业规划工作台
              </div>
              <div>
                <h1
                  class="max-w-3xl bg-gradient-to-r from-gray-900 via-gray-800 to-gray-700 bg-clip-text text-2xl font-bold leading-tight text-transparent sm:text-3xl dark:from-white dark:via-slate-100 dark:to-slate-300"
                >
                  开启你的职业认知之旅
                </h1>
                <div class="cp-title-bar mx-auto mt-2 h-[3px] w-[40%] max-w-[220px] rounded-full bg-gradient-to-r from-sky-300 via-blue-300 to-indigo-300 sm:mx-0" />
                <p class="mt-3 max-w-2xl text-sm leading-relaxed text-[#6b7280] dark:text-slate-400">
                  从简历与面试数据中提炼画像与路线，在温和、专业的界面里跟踪成长与任务。
                </p>
              </div>
            </div>

            <div
              class="grid min-w-[240px] gap-3 rounded-2xl border border-gray-200/50 bg-white/70 p-4 shadow-md backdrop-blur-md dark:border-white/10 dark:bg-slate-950/50"
            >
              <div class="flex items-center justify-between gap-3">
                <span class="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500 dark:text-slate-500">当前子页面</span>
                <span
                  class="rounded-full border border-blue-200/70 bg-gradient-to-r from-sky-50 to-white px-3 py-1 text-xs font-semibold text-blue-800 dark:border-blue-400/30 dark:from-sky-500/10 dark:to-slate-900 dark:text-blue-100"
                >
                  {{ currentTab.label }}
                </span>
              </div>
              <div class="grid gap-2 text-sm text-gray-600 dark:text-slate-400">
                <div class="flex items-center justify-between">
                  <span>规划状态</span>
                  <span class="font-semibold text-gray-900 dark:text-white">{{ store.currentPlan?.status || '未生成' }}</span>
                </div>
                <div class="flex items-center justify-between">
                  <span>任务总数</span>
                  <span class="font-semibold text-gray-900 dark:text-white">{{ store.stats.active_task_count }}</span>
                </div>
                <div class="flex items-center justify-between">
                  <span>完成率</span>
                  <span class="bg-gradient-to-r from-blue-700 to-indigo-700 bg-clip-text font-bold text-transparent tabular-nums">
                    {{ store.stats.progress_rate }}%
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- 子页面切换 -->
          <div class="grid gap-2 rounded-2xl border border-gray-200/50 bg-white/50 p-2 backdrop-blur-sm dark:border-white/10 dark:bg-slate-950/40 sm:grid-cols-2 lg:grid-cols-4">
            <button
              v-for="tab in tabs"
              :key="tab.name"
              type="button"
              class="cp-tab relative flex min-h-[48px] items-center justify-center gap-2 overflow-hidden rounded-xl px-4 py-3 text-sm font-semibold transition-transform duration-200 will-change-transform active:scale-[0.98]"
              :class="
                currentTab.name === tab.name
                  ? 'cp-tab--active text-[#1e3a8a] shadow-[0_4px_12px_rgba(147,197,253,0.15)] dark:text-blue-100'
                  : 'border border-gray-200 bg-white text-[#6b7280] hover:bg-gradient-to-br hover:from-sky-50/20 hover:to-white dark:border-white/10 dark:bg-slate-900/40 dark:text-slate-300 dark:hover:from-sky-500/10 dark:hover:to-slate-900'
              "
              @click="goTo(tab.name)"
            >
              <span
                v-if="currentTab.name === tab.name"
                class="cp-tab-shine pointer-events-none absolute inset-0 opacity-25"
                aria-hidden="true"
              />
              <component :is="tab.icon" class="relative z-[1] h-4 w-4 shrink-0" />
              <span class="relative z-[1]">{{ tab.label }}</span>
            </button>
          </div>

          <section
            v-if="store.error"
            class="rounded-2xl border border-blue-200/70 bg-sky-50/70 px-4 py-3 text-sm font-semibold text-blue-800 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-200"
          >
            {{ store.error }}
          </section>
        </div>
      </section>

      <router-view />
    </div>
  </div>
</template>

<style scoped>
@reference "tailwindcss";

@media (prefers-reduced-motion: reduce) {
  .cp-orb,
  .cp-hero-enter {
    animation: none !important;
  }
  .cp-tab {
    transition: none !important;
  }
}

.cp-orb {
  will-change: transform, opacity;
  background: radial-gradient(circle at center, rgb(219 234 254 / 0.35), transparent 70%);
}
.cp-orb-sky {
  left: -14%;
  top: -18%;
  background: radial-gradient(circle at center, rgb(224 242 254 / 0.25), transparent 70%);
  animation: cp-float-sky 30s ease-in-out infinite;
}
.cp-orb-indigo {
  right: -12%;
  bottom: -20%;
  background: radial-gradient(circle at center, rgb(237 233 254 / 0.2), transparent 70%);
  animation: cp-float-indigo 28s ease-in-out infinite;
}

@keyframes cp-float-sky {
  0%,
  100% {
    transform: translate3d(0, 0, 0) scale(1);
  }
  50% {
    transform: translate3d(0, -30px, 0) scale(1.1);
  }
}
@keyframes cp-float-indigo {
  0% {
    transform: translate3d(0, 0, 0) scale(1);
  }
  100% {
    transform: translate3d(0, 0, 0) scale(1);
  }
  50% {
    transform: translate3d(0, -25px, 0) scale(1.15);
  }
}

.cp-hero-enter {
  animation: cp-hero-in 0.8s cubic-bezier(0.215, 0.61, 0.355, 1) both;
  will-change: transform, opacity;
}
@keyframes cp-hero-in {
  from {
    opacity: 0;
    transform: translate3d(0, -16px, 0);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}

.cp-tab {
  border-width: 1px;
}
.cp-tab:not(.cp-tab--active):hover {
  transform: translate3d(0, -2px, 0) scale(1.02);
}
.cp-tab--active {
  border: 1.5px solid #93c5fd;
  background-image: linear-gradient(135deg, #dbeafe 0%, #e0e7ff 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.45),
    0 4px 12px rgba(147, 197, 253, 0.15);
  font-weight: 600;
}
.dark .cp-tab--active {
  background-image: linear-gradient(135deg, rgb(30 58 138 / 0.6) 0%, rgb(55 48 163 / 0.55) 100%);
  border-color: rgb(147 197 253 / 0.55);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
}
.cp-tab--active:hover {
  transform: translate3d(0, -3px, 0) scale(1.02);
  box-shadow: 0 8px 20px rgba(147, 197, 253, 0.22);
}
</style>
