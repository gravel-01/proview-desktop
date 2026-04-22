<script setup lang="ts">
import { ref, computed, onBeforeUnmount, onMounted, defineAsyncComponent, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useThemeStore } from './stores/theme'
import { useInterviewStore } from './stores/interview'
import { useAuthStore } from './stores/auth'
import { useNavigationPreferenceStore } from './stores/navigationPreference'
import BlobBackground from './components/BlobBackground.vue'
import {
  Bot, Settings, FileText, Terminal,
  Sun, Moon, ArrowLeft, MessageSquare, BookOpen, Sparkles, FilePlus2, LogOut, History, FileUser, SlidersHorizontal, Plus
} from 'lucide-vue-next'

const CatLoading = defineAsyncComponent(() => import('./components/CatLoading.vue'))
const DebugDrawer = defineAsyncComponent(() => import('./components/DebugDrawer.vue'))

const theme = useThemeStore()
const interview = useInterviewStore()
const auth = useAuthStore()
const navPreference = useNavigationPreferenceStore()
const router = useRouter()
const route = useRoute()
const isDebugOpen = ref(false)
const isRouteLoading = ref(false)
let routeLoadingTimer: ReturnType<typeof setTimeout> | null = null

onMounted(() => {
  interview.rehydrateInterviewSession()
  if (auth.isLoggedIn) {
    navPreference.load().catch(() => {})
  }
})

watch(
  () => auth.isLoggedIn,
  (loggedIn) => {
    if (loggedIn) {
      navPreference.load().catch(() => {})
    } else {
      navPreference.reset()
    }
  },
)

// 登录/注册页不显示侧边栏
const isGuestPage = computed(() => route.meta.guest === true)
const isPreferencePage = computed(() => route.meta.hideAppChrome === true)
const showAppChrome = computed(() => !isGuestPage.value && !isPreferencePage.value)

const routeLoadingMessageMap: Record<string, string> = {
  login: '正在打开登录页...',
  register: '正在打开注册页...',
  setup: '正在加载面试配置页...',
  interview: '正在进入面试房间...',
  report: '正在加载评估报告...',
  'report-history': '正在加载历史报告...',
  summary: '正在整理面经总结...',
  history: '正在加载面试历史...',
  'history-detail': '正在打开历史详情...',
  'resume-optimizer': '正在加载简历优化页...',
  'resume-builder': '正在加载简历生成页...',
  'my-resumes': '正在加载我的简历...',
  'navigation-preferences': '正在加载导航偏好问卷...',
  'career-planning': '正在加载职业规划工作台...',
  'career-planning-overview': '正在加载职业规划总览页...',
  'career-planning-roadmap': '正在加载职业规划路线图页...',
  'career-planning-tasks': '正在加载职业规划任务页...',
  'career-planning-docs': '正在加载职业规划文档页...',
}

const routeLoadingMessage = computed(() => {
  const routeName = typeof route.name === 'string' ? route.name : ''
  return routeLoadingMessageMap[routeName] || '页面加载中，请稍候...'
})

const routeLoadingStage = computed(() => (
  route.meta.guest ? '正在准备页面资源' : '你仍然可以继续滚动和查看当前界面'
))

function clearRouteLoadingTimer() {
  if (routeLoadingTimer) {
    clearTimeout(routeLoadingTimer)
    routeLoadingTimer = null
  }
}

function startRouteLoading() {
  clearRouteLoadingTimer()
  routeLoadingTimer = setTimeout(() => {
    isRouteLoading.value = true
  }, 120)
}

function finishRouteLoading() {
  clearRouteLoadingTimer()
  isRouteLoading.value = false
}

const removeRouteErrorHandler = router.onError(() => {
  finishRouteLoading()
})

const removeRouteLoadingStart = router.beforeResolve(() => {
  startRouteLoading()
})

const removeRouteLoadingEnd = router.afterEach(() => {
  finishRouteLoading()
})

const baseNavItems = computed(() => [
  { moduleId: 'interview_config', name: 'setup', icon: Settings, label: '面试配置', path: '/', group: '面试流程' },
  { moduleId: 'interview_history', name: 'history', icon: History, label: '面试历史', path: '/history', group: '面试流程' },
  { moduleId: 'interview_room', name: 'interview', icon: MessageSquare, label: '面试房间', path: '/interview', disabled: !interview.canEnterInterviewRoom, group: '面试流程' },
  { moduleId: 'evaluation_report', name: 'report', icon: FileText, label: '评估报告', path: '/report', group: '面试流程' },
  { moduleId: 'experience_summary', name: 'summary', icon: BookOpen, label: '面经总结', path: '/summary', group: '面试流程' },
  { moduleId: 'resume_optimize', name: 'resume-optimizer', icon: Sparkles, label: '简历优化', path: '/resume-optimizer', group: '工具箱' },
  { moduleId: 'resume_generate', name: 'resume-builder', icon: FilePlus2, label: '简历生成', path: '/resume-builder', group: '工具箱' },
  { moduleId: 'my_resume', name: 'my-resumes', icon: FileUser, label: '我的简历', path: '/my-resumes', group: '工具箱' },
  { moduleId: 'career_planning', name: 'career-planning', icon: FileText, label: '职业规划', routeName: 'career-planning-overview', path: '/career-planning/overview', group: '工具箱' },
])

const navItems = computed(() => {
  const order = navPreference.moduleOrder
  const orderMap = new Map(order.map((id, index) => [id, index]))
  return [...baseNavItems.value].sort((a, b) => {
    const ai = orderMap.get(a.moduleId) ?? 999
    const bi = orderMap.get(b.moduleId) ?? 999
    return ai - bi
  })
})

const interviewFlowNavItems = computed(() => navItems.value.filter((i) => i.group === '面试流程'))
const toolboxNavItems = computed(() => navItems.value.filter((i) => i.group === '工具箱'))

const currentNav = computed(() => {
  if (route.name === 'interview') return 'interview'
  if (route.name === 'report' || route.name === 'report-history') return 'report'
  if (route.name === 'summary') return 'summary'
  if (route.name === 'history' || route.name === 'history-detail') return 'history'
  if (route.name === 'resume-optimizer') return 'resume-optimizer'
  if (route.name === 'resume-builder') return 'resume-builder'
  if (route.name === 'my-resumes') return 'my-resumes'
  if (typeof route.name === 'string' && route.name.startsWith('career-planning')) return 'career-planning'
  return 'setup'
})

function navigateTo(item: { path: string; routeName?: string; disabled?: boolean }) {
  if (item.disabled) return
  if (item.routeName) {
    router.push({ name: item.routeName })
    return
  }
  router.push(item.path)
}

function getNavItemClass(item: { name: string; disabled?: boolean }, activeClass: string, idleClass: string, disabledClass: string) {
  if (currentNav.value === item.name) return activeClass
  if (item.disabled) return disabledClass
  return idleClass
}

function getDesktopNavClass(item: { name: string; disabled?: boolean }) {
  return getNavItemClass(
    item,
    'app-nav-item app-nav-item-active',
    'app-nav-item app-nav-item-idle',
    'app-nav-item app-nav-item-disabled',
  )
}

function handleThemeToggle(e: MouseEvent) {
  theme.toggle(e.currentTarget as HTMLElement)
}

function goLanding() {
  window.location.href = '/'
}

function quickNewInterview() {
  if (route.name === 'setup') {
    window.scrollTo({ top: 0, behavior: 'smooth' })
    return
  }
  router.push('/')
}

function goPreference() {
  router.push('/navigation-preferences')
}

function handleLogout() {
  auth.logout()
  router.push('/login')
}

onBeforeUnmount(() => {
  clearRouteLoadingTimer()
  removeRouteErrorHandler()
  removeRouteLoadingStart()
  removeRouteLoadingEnd()
})
</script>

<template>
  <div class="app-shell app-shell-gradient flex h-screen w-full overflow-hidden font-sans text-slate-900 transition-colors duration-500 dark:text-slate-300">

    <!-- ================== PC端：左侧边栏 ================== -->
    <aside v-if="showAppChrome" class="app-sidebar app-sidebar-enter z-20 hidden w-64 flex-col justify-between transition-colors md:flex">
      <div>
        <!-- Logo -->
        <div class="relative z-[1] flex h-20 cursor-default items-center gap-3 border-b border-gray-200/60 px-6 dark:border-white/5">
          <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-lg shadow-blue-500/30 dark:shadow-indigo-900/40">
            <Bot class="w-5 h-5" />
          </div>
          <span class="text-xl font-extrabold tracking-wide text-transparent bg-clip-text bg-gradient-to-r from-blue-700 to-indigo-700 dark:from-white dark:to-indigo-200">
            ProView AI
          </span>
        </div>

        <!-- 导航菜单 -->
        <nav class="app-nav-root relative z-[1] flex flex-col gap-2 px-3 pb-2">
          <div class="app-nav-group">
            <div class="app-nav-group-title">面试流程</div>
            <button
              v-for="(item, idx) in interviewFlowNavItems"
              :key="item.name"
              type="button"
              class="group"
              :class="getDesktopNavClass(item)"
              :disabled="item.disabled"
              :style="{ '--nav-stagger': `${idx * 50}ms` }"
              @click="navigateTo(item)"
            >
              <span v-if="currentNav === item.name" class="app-nav-active-sheen" aria-hidden="true" />
              <component :is="item.icon" class="app-nav-icon relative z-[1] h-5 w-5 shrink-0" />
              <span class="relative z-[1]">{{ item.label }}</span>
            </button>
          </div>
          <div class="app-nav-group app-nav-group--tools">
            <div class="app-nav-group-title">工具箱</div>
            <button
              v-for="(item, idx) in toolboxNavItems"
              :key="item.name"
              type="button"
              class="group"
              :class="getDesktopNavClass(item)"
              :style="{ '--nav-stagger': `${(interviewFlowNavItems.length + idx) * 50}ms` }"
              @click="navigateTo(item)"
            >
              <span v-if="currentNav === item.name" class="app-nav-active-sheen" aria-hidden="true" />
              <component :is="item.icon" class="app-nav-icon relative z-[1] h-5 w-5 shrink-0" />
              <span class="relative z-[1]">{{ item.label }}</span>
            </button>
          </div>
        </nav>
      </div>

      <!-- 底部控制 -->
      <div class="relative z-[1] space-y-2 border-t border-slate-100/80 p-4 dark:border-white/5">
        <button
          @click="isDebugOpen = !isDebugOpen"
          class="app-control-btn"
        >
          <Terminal class="w-5 h-5" />
          <span>调试面板</span>
        </button>
        <button
          @click="goPreference"
          class="app-control-btn"
        >
          <SlidersHorizontal class="w-5 h-5" />
          <span>导航排序偏好</span>
        </button>
        <button
          @click="handleThemeToggle"
          class="app-control-btn"
        >
          <Sun v-if="theme.isDark" class="w-5 h-5 text-amber-400" />
          <Moon v-else class="w-5 h-5" />
          <span>{{ theme.isDark ? '浅色模式' : '深色模式' }}</span>
        </button>
        <button
          @click="goLanding"
          class="app-control-btn"
        >
          <ArrowLeft class="w-5 h-5" />
          <span>返回介绍页</span>
        </button>
        <!-- 用户信息 + 退出 -->
        <div v-if="auth.isLoggedIn" class="flex items-center gap-2 rounded-xl px-4 py-3">
          <div class="flex-1 min-w-0">
            <p class="text-sm font-semibold text-slate-700 dark:text-slate-300 truncate">{{ auth.user?.display_name || auth.user?.username }}</p>
          </div>
          <button @click="handleLogout" class="shrink-0 rounded-lg p-1.5 text-slate-400 transition hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20 dark:hover:text-red-300" title="退出登录">
            <LogOut class="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>

    <!-- ================== 移动端：底部 Tab ================== -->
    <nav v-if="showAppChrome" class="app-mobile-nav fixed bottom-0 left-0 right-0 z-50 pb-2 pt-2 md:hidden">
      <div class="flex justify-around">
        <button
          v-for="item in navItems" :key="item.name"
          @click="navigateTo(item)"
          class="app-mobile-tab"
          :class="getNavItemClass(
            item,
            'app-mobile-tab-active',
            'app-mobile-tab-idle',
            'app-mobile-tab-disabled'
          )"
          :disabled="item.disabled"
        >
          <component :is="item.icon" class="mb-1 w-5 h-5" />
          <span class="text-[10px] font-bold">{{ item.label }}</span>
        </button>
        <button @click="handleThemeToggle" class="app-mobile-tab app-mobile-tab-idle">
          <Sun v-if="theme.isDark" class="mb-1 w-5 h-5 text-amber-400" />
          <Moon v-else class="mb-1 w-5 h-5" />
          <span class="text-[10px] font-bold">主题</span>
        </button>
        <button @click="goLanding" class="app-mobile-tab app-mobile-tab-idle">
          <ArrowLeft class="mb-1 w-5 h-5" />
          <span class="text-[10px] font-bold">介绍页</span>
        </button>
      </div>
    </nav>

    <!-- ================== 右侧主内容区 ================== -->
    <main class="relative z-10 flex-1 flex flex-col overflow-y-auto pb-20 md:pb-0 custom-scroll" :class="isPreferencePage ? 'pb-0 md:pb-0' : 'app-main-area'">
      <BlobBackground v-if="!isPreferencePage" />
      <!-- 顶栏：玻璃态 + 扫描光（桌面端） -->
      <header
        v-if="showAppChrome"
        class="app-topbar sticky top-0 z-30 hidden shrink-0 items-center justify-between gap-4 border-b border-gray-200/50 px-6 py-3 md:flex dark:border-white/8"
      >
        <div class="app-topbar-scan pointer-events-none" aria-hidden="true" />
        <div class="flex min-w-0 items-center gap-3">
          <div class="flex h-9 w-9 shrink-0 cursor-default items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-lg shadow-blue-500/30 dark:shadow-indigo-900/40">
            <Bot class="h-4 w-4" />
          </div>
          <div class="min-w-0">
            <p class="truncate text-sm font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-gray-800 via-gray-700 to-gray-600 dark:from-white dark:via-slate-200 dark:to-slate-400">
              AI 面试工作台
            </p>
            <p class="truncate text-xs font-medium text-gray-500 dark:text-slate-400">柔和渐变界面 · 与介绍页一致的体验</p>
          </div>
        </div>
        <button type="button" class="app-btn-new group relative inline-flex shrink-0 items-center gap-2 overflow-hidden rounded-full px-5 py-2.5" @click="quickNewInterview">
          <span class="app-btn-new__wash pointer-events-none absolute inset-0 rounded-full" aria-hidden="true" />
          <span class="app-btn-new__halo pointer-events-none absolute inset-0 rounded-full" aria-hidden="true" />
          <span class="app-btn-new__shine pointer-events-none absolute inset-0 rounded-full" aria-hidden="true" />
          <Plus class="app-btn-new__icon relative z-[1] h-4 w-4" />
          <span class="app-btn-new__label relative z-[1] text-sm font-semibold">新建</span>
        </button>
      </header>
      <div class="relative z-10 min-h-0 flex-1">
        <div :class="isPreferencePage ? 'min-h-screen' : 'container mx-auto max-w-7xl px-4 py-8 sm:px-8'">
          <router-view v-slot="{ Component, route: viewRoute }">
            <keep-alive :include="['InterviewView']">
              <component :is="Component" :key="viewRoute.fullPath" />
            </keep-alive>
          </router-view>
        </div>
      </div>
    </main>

    <CatLoading
      v-if="isRouteLoading"
      variant="corner"
      :blocking="false"
      :message="routeLoadingMessage"
      :stage="routeLoadingStage"
    />

    <DebugDrawer :open="isDebugOpen" @close="isDebugOpen = false" />
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.app-shell-gradient {
  background: linear-gradient(
    135deg,
    color-mix(in srgb, rgb(255 251 235) 55%, white) 0%,
    #ffffff 48%,
    color-mix(in srgb, rgb(240 249 255) 52%, white) 100%
  );
}

.app-sidebar-enter {
  animation: app-sidebar-enter 0.6s ease-out both;
}
@keyframes app-sidebar-enter {
  from {
    opacity: 0;
    transform: translate3d(-14px, 0, 0);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}

.app-sidebar {
  position: relative;
  border-right: 1px solid rgba(229, 231, 235, 0.5);
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  box-shadow: 0 8px 32px rgba(15, 23, 42, 0.05);
}
.app-sidebar::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background: radial-gradient(120% 90% at 50% -8%, rgba(251, 191, 36, 0.07) 0%, rgba(125, 211, 252, 0.06) 28%, transparent 52%);
  opacity: 0.85;
}

.app-nav-root {
  padding-top: 0.5rem;
}
.app-nav-group {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.app-nav-group--tools {
  margin-top: 1.5rem;
}
.app-nav-group-title {
  margin-bottom: 0.5rem;
  padding: 0 0.35rem;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #9ca3af;
  position: relative;
  padding-bottom: 0.45rem;
}
.app-nav-group-title::after {
  content: '';
  position: absolute;
  left: 0.35rem;
  right: 0.35rem;
  bottom: 0;
  height: 1px;
  border-radius: 9999px;
  background: linear-gradient(90deg, rgba(251, 191, 36, 0.15), rgba(244, 114, 182, 0.15));
}

.app-topbar {
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.72) 0%,
    rgba(255, 251, 235, 0.35) 35%,
    rgba(240, 249, 255, 0.38) 65%,
    rgba(255, 255, 255, 0.72) 100%
  );
  backdrop-filter: blur(28px);
  -webkit-backdrop-filter: blur(28px);
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.65) inset;
}
.app-topbar-scan {
  position: absolute;
  inset: 0;
  overflow: hidden;
}
.app-topbar-scan::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  width: 42%;
  left: -100%;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(251, 191, 36, 0.22),
    rgba(253, 186, 116, 0.18),
    transparent
  );
  animation: app-topbar-sweep 8s ease-in-out infinite;
  will-change: transform;
}
@keyframes app-topbar-sweep {
  0% {
    transform: translate3d(0, 0, 0);
  }
  100% {
    transform: translate3d(340%, 0, 0);
  }
}

.app-btn-new {
  border: 1.5px solid #a5b4fc;
  background: transparent;
  box-shadow:
    0 2px 10px rgba(165, 180, 252, 0.18),
    inset 0 1px 2px rgba(255, 255, 255, 0.35);
  transition:
    transform 0.25s ease-out,
    box-shadow 0.25s ease-out,
    border-color 0.25s ease-out;
  will-change: transform;
}
.app-btn-new__wash {
  background: linear-gradient(135deg, #7dd3fc 0%, #a78bfa 50%, #f0abfc 100%);
  opacity: 1;
}
.app-btn-new__wash::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: rgba(255, 255, 255, 0.22);
}
.app-btn-new__halo {
  inset: -35%;
  background: radial-gradient(circle at 50% 50%, rgba(165, 180, 252, 0.35), transparent 58%);
  opacity: 0.28;
  animation: app-btn-new-halo 3s ease-in-out infinite;
}
@keyframes app-btn-new-halo {
  0%,
  100% {
    opacity: 0.2;
    transform: scale(0.92);
  }
  50% {
    opacity: 0.38;
    transform: scale(1.02);
  }
}
.app-btn-new__shine {
  background: linear-gradient(105deg, transparent 0%, rgba(255, 255, 255, 0.45) 45%, transparent 72%);
  opacity: 0;
  animation: app-btn-new-shine 2s ease-in-out infinite;
}
@keyframes app-btn-new-shine {
  0% {
    transform: translate3d(-100%, 0, 0);
    opacity: 0;
  }
  12% {
    opacity: 0.3;
  }
  45% {
    transform: translate3d(100%, 0, 0);
    opacity: 0.3;
  }
  55%,
  100% {
    transform: translate3d(100%, 0, 0);
    opacity: 0;
  }
}
.app-btn-new:hover {
  transform: translate3d(0, -2px, 0) scale(1.03);
  box-shadow:
    0 6px 20px rgba(165, 180, 252, 0.28),
    inset 0 1px 2px rgba(255, 255, 255, 0.35);
  border-color: #93c5fd;
}
.app-btn-new:active {
  transform: scale(0.98);
  transition: transform 0.12s ease-out;
}
.app-btn-new__icon,
.app-btn-new__label {
  color: #312e81;
}

.app-nav-item {
  position: relative;
  z-index: 1;
  display: flex;
  width: 100%;
  align-items: center;
  gap: 0.65rem;
  border-radius: 0.5rem;
  padding: 0.62rem 0.85rem;
  font-size: 14px;
  font-weight: 500;
  background: transparent;
  color: #6b7280;
  cursor: pointer;
  border: none;
  text-align: left;
  transition:
    transform 0.3s ease-out,
    background 0.3s ease-out,
    color 0.3s ease-out,
    box-shadow 0.3s ease-out;
  animation: app-nav-item-enter 0.4s ease-out both;
  animation-delay: calc(0.12s + var(--nav-stagger, 0ms));
  will-change: transform;
}

@keyframes app-nav-item-enter {
  from {
    opacity: 0;
    transform: translate3d(-8px, 0, 0) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0) scale(1);
  }
}

.app-nav-icon {
  color: #6b7280;
  transition: color 0.3s ease-out;
}

.app-nav-item-idle:hover {
  background: linear-gradient(90deg, rgba(240, 249, 255, 0.35) 0%, rgba(245, 243, 255, 0.22) 100%);
  color: #374151;
  transform: scale(1.01);
  box-shadow: none;
}
.app-nav-item-idle:hover .app-nav-icon {
  color: #374151;
}
.app-nav-item-idle:hover::before {
  opacity: 1;
  height: 70%;
}
.app-nav-item-idle::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  width: 2px;
  height: 0;
  border-radius: 9999px;
  transform: translateY(-50%);
  background: linear-gradient(180deg, #bae6fd, #c7d2fe, #ddd6fe);
  opacity: 0;
  transition:
    height 0.4s ease-out,
    opacity 0.3s ease-out;
  pointer-events: none;
}

.app-nav-item-active {
  padding-left: 0.95rem;
  color: #1e3a8a;
  font-weight: 600;
  background:
    linear-gradient(135deg, rgba(224, 242, 254, 0.5) 0%, rgba(243, 232, 255, 0.5) 100%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.35), rgba(255, 255, 255, 0));
  box-shadow:
    0 4px 12px rgba(139, 92, 246, 0.08),
    0 1px 0 rgba(255, 255, 255, 0.6) inset;
  overflow: hidden;
}
.app-nav-item-active .app-nav-icon {
  color: #1e40af;
}
.app-nav-item-active::before {
  content: '';
  position: absolute;
  left: 2px;
  top: 50%;
  width: 3px;
  height: 90%;
  border-radius: 9999px;
  transform: translateY(-50%);
  background: linear-gradient(180deg, #38bdf8, #818cf8, #a78bfa);
  filter: blur(0.5px);
  box-shadow: 0 0 10px rgba(129, 140, 248, 0.35);
  pointer-events: none;
}
.app-nav-item-active::after {
  content: '';
  position: absolute;
  left: 2px;
  top: 50%;
  width: 3px;
  height: 90%;
  border-radius: 9999px;
  transform: translateY(-50%);
  background: linear-gradient(
    180deg,
    transparent 0%,
    rgba(255, 255, 255, 0.55) 50%,
    transparent 100%
  );
  background-size: 100% 200%;
  animation: app-nav-rail-gloss 3s ease-in-out infinite;
  mix-blend-mode: overlay;
  pointer-events: none;
  opacity: 0.5;
}
@keyframes app-nav-rail-gloss {
  0%,
  100% {
    background-position: 0% 0%;
  }
  50% {
    background-position: 0% 100%;
  }
}
.app-nav-active-sheen {
  position: absolute;
  inset: 0;
  z-index: 0;
  border-radius: inherit;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.5), transparent);
  transform: translate3d(-100%, 0, 0);
  animation: app-nav-active-sheen-once 0.85s ease-out 1 forwards;
  pointer-events: none;
}
@keyframes app-nav-active-sheen-once {
  to {
    transform: translate3d(100%, 0, 0);
  }
}

.app-nav-item-disabled {
  color: #d1d5db;
  cursor: not-allowed;
  opacity: 0.85;
}
.app-nav-item-disabled .app-nav-icon {
  color: #d1d5db;
}
.app-nav-item-disabled:hover {
  transform: none;
  background: transparent !important;
  box-shadow: none;
}
.app-nav-item-disabled:hover::before {
  height: 0;
  opacity: 0;
}

.app-control-btn {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 0.75rem;
  border-radius: 0.9rem;
  border: 1px solid rgba(203, 213, 225, 0.55);
  background: rgba(255, 255, 255, 0.72);
  padding: 0.72rem 1rem;
  font-size: 0.875rem;
  font-weight: 600;
  color: #475569;
  transition: all 180ms ease;
}
.app-control-btn:hover {
  transform: translateY(-1px);
  border-color: rgba(129, 140, 248, 0.45);
  color: #4f46e5;
  box-shadow: 0 8px 18px rgba(79, 70, 229, 0.15);
}

.app-mobile-nav {
  border-top: 1px solid rgba(148, 163, 184, 0.25);
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
}
.app-mobile-tab {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.5rem;
  transition: all 180ms ease;
}
.app-mobile-tab-active {
  color: #4f46e5;
}
.app-mobile-tab-idle {
  color: #64748b;
}
.app-mobile-tab-idle:hover {
  color: #334155;
}
.app-mobile-tab-disabled {
  color: #cbd5e1;
}

.app-main-area {
  background: transparent;
}

:global(html.dark) .app-shell-gradient {
  background: #05050a;
}
:global(html.dark) .app-sidebar {
  border-right: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(10, 10, 15, 0.92);
  box-shadow: none;
}
:global(html.dark) .app-nav-item-idle {
  color: #94a3b8;
}
:global(html.dark) .app-nav-item-idle:hover {
  background: rgba(255, 255, 255, 0.06);
  color: #e5e7eb;
  box-shadow: none;
}
:global(html.dark) .app-nav-item-active {
  color: #bfdbfe;
  background: linear-gradient(135deg, rgba(30, 58, 138, 0.45) 0%, rgba(55, 48, 163, 0.4) 100%);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
}
:global(html.dark) .app-nav-item-active .app-nav-icon {
  color: #93c5fd;
}
:global(html.dark) .app-nav-group-title {
  color: #6b7280;
}
:global(html.dark) .app-nav-group-title::after {
  opacity: 0.5;
}
:global(html.dark) .app-btn-new {
  border-color: rgba(129, 140, 248, 0.45);
}
:global(html.dark) .app-btn-new__icon,
:global(html.dark) .app-btn-new__label {
  color: #e0e7ff;
}
:global(html.dark) .app-control-btn {
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.03);
  color: #94a3b8;
}
:global(html.dark) .app-control-btn:hover {
  border-color: rgba(99, 102, 241, 0.5);
  color: #c4b5fd;
  box-shadow: none;
}
:global(html.dark) .app-mobile-nav {
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(10, 10, 15, 0.94);
}
:global(html.dark) .app-mobile-tab-idle {
  color: #94a3b8;
}

:global(html.dark) .app-topbar {
  background: rgba(10, 10, 15, 0.82);
  box-shadow: none;
}
:global(html.dark) .app-topbar-scan::after {
  opacity: 0.35;
}
</style>
