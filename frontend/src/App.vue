<script setup lang="ts">
import { ref, computed, onBeforeUnmount, onMounted, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useThemeStore } from './stores/theme'
import { useInterviewStore } from './stores/interview'
import { useAuthStore } from './stores/auth'
import BlobBackground from './components/BlobBackground.vue'
import {
  Bot, Settings,
  Sun, Moon, ArrowLeft, MessageSquare, BookOpen, Sparkles, FilePlus2, History, FileUser, ChevronLeft, ChevronRight,
  SlidersHorizontal, ClipboardList, Map
} from 'lucide-vue-next'

const CatLoading = defineAsyncComponent(() => import('./components/CatLoading.vue'))

const theme = useThemeStore()
const interview = useInterviewStore()
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const isRouteLoading = ref(false)
const pendingRouteName = ref('')
const SIDEBAR_COLLAPSED_KEY = 'proview:sidebar-collapsed'
const isSidebarCollapsed = ref(localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1')
let routeLoadingTimer: ReturnType<typeof setTimeout> | null = null

onMounted(() => {
  interview.rehydrateInterviewSession()
})

const isGuestPage = computed(() => route.meta.guest === true)

const routeLoadingMessageMap: Record<string, string> = {
  'runtime-config': '正在加载应用设置页...',
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
  'career-planning': '正在加载职业规划工作台...',
  'career-planning-overview': '正在加载职业规划总览页...',
  'career-planning-roadmap': '正在加载职业规划路线图页...',
  'career-planning-tasks': '正在加载职业规划任务页...',
  'career-planning-docs': '正在加载职业规划文档页...',
}

const routeLoadingMessage = computed(() => {
  const routeName = pendingRouteName.value || (typeof route.name === 'string' ? route.name : '')
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

function startRouteLoading(routeName = '') {
  pendingRouteName.value = routeName
  clearRouteLoadingTimer()
  routeLoadingTimer = setTimeout(() => {
    isRouteLoading.value = true
  }, 120)
}

function finishRouteLoading() {
  clearRouteLoadingTimer()
  isRouteLoading.value = false
  pendingRouteName.value = ''
}

const removeRouteErrorHandler = router.onError(() => {
  finishRouteLoading()
})

const removeRouteLoadingStart = router.beforeEach((to, from) => {
  if (!from.matched.length || to.fullPath === from.fullPath) return
  startRouteLoading(typeof to.name === 'string' ? to.name : '')
})

const removeRouteLoadingEnd = router.afterEach(() => {
  finishRouteLoading()
})

const navItems = computed(() => [
  { name: 'setup', icon: SlidersHorizontal, label: '面试配置', path: '/', group: '面试流程' },
  { name: 'history', icon: History, label: '面试历史', path: '/history', group: '面试流程' },
  { name: 'interview', icon: MessageSquare, label: '面试房间', path: '/interview', disabled: !interview.canEnterInterviewRoom, group: '面试流程' },
  { name: 'report', icon: ClipboardList, label: '评估报告', path: '/report', group: '面试流程' },
  { name: 'summary', icon: BookOpen, label: '面经总结', path: '/summary', group: '面试流程' },
  { name: 'resume-optimizer', icon: Sparkles, label: '简历优化', path: '/resume-optimizer', group: '工具箱' },
  { name: 'resume-builder', icon: FilePlus2, label: '简历生成', path: '/resume-builder', group: '工具箱' },
  { name: 'my-resumes', icon: FileUser, label: '我的简历', path: '/my-resumes', group: '工具箱' },
  { name: 'career-planning', icon: Map, label: '职业规划', routeName: 'career-planning-overview', path: '/career-planning/overview', group: '工具箱' },
])

const settingsNavItem = { name: 'runtime-config', icon: Settings, label: '应用设置', path: '/config' }

const currentNav = computed(() => {
  if (route.name === 'interview') return 'interview'
  if (route.name === 'report' || route.name === 'report-history') return 'report'
  if (route.name === 'summary') return 'summary'
  if (route.name === 'runtime-config') return 'runtime-config'
  if (route.name === 'history' || route.name === 'history-detail') return 'history'
  if (route.name === 'resume-optimizer') return 'resume-optimizer'
  if (route.name === 'resume-builder') return 'resume-builder'
  if (route.name === 'my-resumes') return 'my-resumes'
  if (typeof route.name === 'string' && route.name.startsWith('career-planning')) return 'career-planning'
  return 'setup'
})

const isSettingsRoute = computed(() => route.name === 'runtime-config')
const shouldUseCleanMain = computed(() => !isGuestPage.value)

function navigateTo(item: { name?: string; path: string; routeName?: string; disabled?: boolean }) {
  if (item.disabled) return
  const targetName = item.routeName || item.name || ''
  const targetPath = item.path
  if ((targetName && route.name === targetName) || (!targetName && route.path === targetPath)) {
    return
  }

  startRouteLoading(targetName)

  if (item.routeName) {
    router.push({ name: item.routeName }).catch(() => finishRouteLoading())
    return
  }
  router.push(item.path).catch(() => finishRouteLoading())
}

function getNavItemClass(item: { name: string; disabled?: boolean }, activeClass: string, idleClass: string, disabledClass: string) {
  if (currentNav.value === item.name) return activeClass
  if (item.disabled) return disabledClass
  return idleClass
}

function handleThemeToggle(e: MouseEvent) {
  theme.toggle(e.currentTarget as HTMLElement)
}

function goLanding() {
  const currentPageUrl = window.location.href.split('#')[0]
  const landingUrl = new URL('index.html', currentPageUrl)
  window.location.assign(landingUrl.toString())
}

function openSettings() {
  navigateTo(settingsNavItem)
}

function toggleSidebar() {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
  localStorage.setItem(SIDEBAR_COLLAPSED_KEY, isSidebarCollapsed.value ? '1' : '0')
}

onBeforeUnmount(() => {
  clearRouteLoadingTimer()
  removeRouteErrorHandler()
  removeRouteLoadingStart()
  removeRouteLoadingEnd()
})
</script>

<template>
  <div class="app-shell flex h-screen w-full overflow-hidden font-sans text-slate-900 transition-colors duration-500 dark:text-slate-300">

    <!-- ================== PC端：左侧边栏 ================== -->
    <aside
      v-if="!isGuestPage"
      class="app-sidebar z-20 hidden min-h-0 flex-col overflow-hidden transition-[width] duration-300 md:flex"
      :class="isSidebarCollapsed ? 'w-[92px]' : 'w-[280px]'"
    >
      <!-- Logo -->
      <div class="app-sidebar__header flex h-20 shrink-0 items-center" :class="isSidebarCollapsed ? 'px-3' : 'px-6'">
        <div class="flex min-w-0 flex-1 items-center" :class="isSidebarCollapsed ? 'justify-center' : 'gap-3'">
          <div class="app-logo-mark flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl text-white">
            <Bot class="w-5 h-5" />
          </div>
          <span
            v-if="!isSidebarCollapsed"
            class="app-logo-text truncate text-xl font-extrabold tracking-wide"
          >
            ProView AI
          </span>
        </div>
        <button
          type="button"
          class="app-icon-control inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl"
          :title="isSidebarCollapsed ? '展开导航栏' : '折叠导航栏'"
          @click="toggleSidebar"
        >
          <ChevronRight v-if="isSidebarCollapsed" class="h-4 w-4" />
          <ChevronLeft v-else class="h-4 w-4" />
        </button>
      </div>

      <div class="custom-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <!-- 导航菜单 -->
        <nav class="flex flex-col gap-2 px-4 pb-4 pt-5">
          <div v-if="!isSidebarCollapsed" class="app-nav-group-title mb-2 px-2">面试流程</div>
          <button
            v-for="item in navItems.filter(i => i.group === '面试流程')" :key="item.name"
            @click="navigateTo(item)"
            class="app-nav-button group flex items-center py-3 text-sm font-bold"
            :class="[
              isSidebarCollapsed ? 'justify-center px-3' : 'gap-3 px-4',
              getNavItemClass(
                item,
                'app-nav-button--active',
                'app-nav-button--idle',
                'app-nav-button--disabled'
              )
            ]"
            :disabled="item.disabled"
            :title="isSidebarCollapsed ? item.label : undefined"
          >
            <component :is="item.icon" class="w-5 h-5 transition-transform group-hover:scale-110" />
            <span v-if="!isSidebarCollapsed">{{ item.label }}</span>
          </button>
          <div v-if="!isSidebarCollapsed" class="app-nav-group-title mt-4 mb-2 px-2">工具箱</div>
          <button
            v-for="item in navItems.filter(i => i.group === '工具箱')" :key="item.name"
            @click="navigateTo(item)"
            class="app-nav-button group flex items-center py-3 text-sm font-bold"
            :class="[
              isSidebarCollapsed ? 'justify-center px-3' : 'gap-3 px-4',
              getNavItemClass(
                item,
                'app-nav-button--active',
                'app-nav-button--idle',
                'app-nav-button--disabled'
              )
            ]"
            :disabled="item.disabled"
            :title="isSidebarCollapsed ? item.label : undefined"
          >
            <component :is="item.icon" class="w-5 h-5 transition-transform group-hover:scale-110" />
            <span v-if="!isSidebarCollapsed">{{ item.label }}</span>
          </button>
        </nav>
      </div>

      <!-- 底部控制 -->
      <div class="app-sidebar__footer shrink-0 space-y-2 p-4">
        <button
          @click="goLanding"
          class="app-sidebar-pill flex w-full items-center py-3 text-sm font-semibold"
          :class="isSidebarCollapsed ? 'justify-center px-3' : 'gap-3 px-4'"
          :title="isSidebarCollapsed ? '返回介绍页' : undefined"
        >
          <ArrowLeft class="w-5 h-5" />
          <span v-if="!isSidebarCollapsed">返回介绍页</span>
        </button>
        <button
          @click="openSettings"
          class="app-sidebar-pill flex w-full items-center py-3 text-sm font-semibold"
          :class="[
            isSidebarCollapsed ? 'justify-center px-3' : 'gap-3 px-4',
            isSettingsRoute ? 'app-sidebar-pill--active' : ''
          ]"
          :title="isSidebarCollapsed ? '应用设置' : undefined"
        >
          <Settings class="w-5 h-5" />
          <span v-if="!isSidebarCollapsed">应用设置</span>
        </button>
        <div class="app-user-card rounded-[24px] py-3" :class="isSidebarCollapsed ? 'px-3' : 'px-4'">
          <div class="app-user-card__inner" :class="{ 'app-user-card__inner--collapsed': isSidebarCollapsed }">
            <div class="app-user-card__identity" :class="isSidebarCollapsed ? 'justify-center' : ''">
              <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-500 text-white shadow-md shadow-emerald-500/20">
                <Bot class="h-4 w-4" />
              </div>
              <div v-if="!isSidebarCollapsed" class="min-w-0">
                <p class="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">单机模式</p>
                <p class="mt-1 truncate text-sm font-semibold text-slate-700 dark:text-slate-200">{{ auth.user?.display_name || auth.user?.username || '本地用户' }}</p>
              </div>
            </div>
            <button
              type="button"
              class="app-theme-switch app-theme-switch--embedded"
              :class="[
                { 'app-theme-switch--dark': theme.isDark },
                isSidebarCollapsed ? 'app-theme-switch--compact' : '',
              ]"
              :title="theme.isDark ? '切换到浅色模式' : '切换到深色模式'"
              :aria-pressed="theme.isDark"
              @click="handleThemeToggle"
            >
              <span class="app-theme-switch__label">{{ theme.isDark ? '深色' : '浅色' }}</span>
              <span class="app-theme-switch__track">
                <Sun class="app-theme-switch__track-icon app-theme-switch__track-icon--sun h-3.5 w-3.5" />
                <Moon class="app-theme-switch__track-icon app-theme-switch__track-icon--moon h-3.5 w-3.5" />
                <span class="app-theme-switch__thumb">
                  <Moon v-if="theme.isDark" class="h-3.5 w-3.5" />
                  <Sun v-else class="h-3.5 w-3.5" />
                </span>
              </span>
            </button>
          </div>
        </div>
      </div>
    </aside>

    <!-- ================== 移动端：底部 Tab ================== -->
    <nav v-if="!isGuestPage" class="app-mobile-nav fixed bottom-0 left-0 right-0 z-50 pb-2 pt-2 md:hidden">
      <div class="flex justify-around">
        <button
          v-for="item in navItems" :key="item.name"
          @click="navigateTo(item)"
          class="app-mobile-tab flex flex-col items-center p-2"
          :class="getNavItemClass(
            item,
            'app-mobile-tab--active',
            'app-mobile-tab--idle',
            'app-mobile-tab--disabled'
          )"
          :disabled="item.disabled"
        >
          <component :is="item.icon" class="mb-1 w-5 h-5" />
          <span class="text-[10px] font-bold">{{ item.label }}</span>
        </button>
        <button @click="goLanding" class="app-mobile-tab app-mobile-tab--idle flex flex-col items-center p-2">
          <ArrowLeft class="mb-1 w-5 h-5" />
          <span class="text-[10px] font-bold">介绍页</span>
        </button>
      </div>
    </nav>

    <!-- ================== 右侧主内容区 ================== -->
    <main
      class="app-main custom-scroll relative z-10 min-h-0 flex-1 overflow-y-auto overscroll-contain pb-20 md:pb-0"
      :class="{ 'app-main--clean': shouldUseCleanMain }"
    >
      <BlobBackground v-if="!shouldUseCleanMain" />
      <div class="relative z-10 min-h-full">
        <div v-if="!isGuestPage" class="pointer-events-none absolute right-4 top-4 z-20 flex items-center gap-2 sm:gap-3 md:hidden">
          <button
            type="button"
            class="app-theme-switch pointer-events-auto"
            :class="{ 'app-theme-switch--dark': theme.isDark }"
            :title="theme.isDark ? '切换到浅色模式' : '切换到深色模式'"
            :aria-pressed="theme.isDark"
            @click="handleThemeToggle"
          >
            <span class="app-theme-switch__label hidden sm:inline">{{ theme.isDark ? '深色' : '浅色' }}</span>
            <span class="app-theme-switch__track">
              <Sun class="app-theme-switch__track-icon app-theme-switch__track-icon--sun h-3.5 w-3.5" />
              <Moon class="app-theme-switch__track-icon app-theme-switch__track-icon--moon h-3.5 w-3.5" />
              <span class="app-theme-switch__thumb">
                <Moon v-if="theme.isDark" class="h-3.5 w-3.5" />
                <Sun v-else class="h-3.5 w-3.5" />
              </span>
            </span>
          </button>
          <button
            type="button"
            class="app-top-chip pointer-events-auto inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold md:hidden"
            :class="{ 'app-top-chip--active': isSettingsRoute }"
            @click="openSettings"
          >
            <Settings class="h-4 w-4" />
            <span class="hidden sm:inline">应用设置</span>
          </button>
        </div>
        <div
          class="container mx-auto max-w-7xl px-4 sm:px-8"
          :class="isGuestPage ? 'py-8' : 'pb-8 pt-24 md:py-8'"
        >
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

.app-shell {
  background:
    radial-gradient(920px circle at -10% -12%, rgba(251, 191, 36, 0.14), transparent 46%),
    radial-gradient(860px circle at 108% 4%, rgba(56, 189, 248, 0.12), transparent 48%),
    linear-gradient(135deg, rgba(255, 248, 238, 0.72) 0%, rgba(255, 255, 255, 0.54) 46%, rgba(239, 247, 255, 0.6) 100%);
}

.app-sidebar {
  position: relative;
  border-right: 1px solid rgba(226, 232, 240, 0.75);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.88) 0%, rgba(248, 250, 252, 0.9) 100%);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  box-shadow:
    0 18px 48px rgba(15, 23, 42, 0.08),
    inset -1px 0 0 rgba(255, 255, 255, 0.6);
}

.app-sidebar::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(120% 100% at 0% 0%, rgba(251, 191, 36, 0.08), transparent 34%),
    radial-gradient(110% 100% at 100% 18%, rgba(99, 102, 241, 0.08), transparent 36%),
    radial-gradient(120% 100% at 50% 100%, rgba(244, 114, 182, 0.06), transparent 28%);
}

.app-sidebar__header {
  position: relative;
  border-bottom: 1px solid rgba(226, 232, 240, 0.68);
}

.app-sidebar__header::after {
  content: '';
  position: absolute;
  left: 1.25rem;
  right: 1.25rem;
  bottom: -1px;
  height: 1px;
  border-radius: 9999px;
  background: linear-gradient(90deg, rgba(251, 191, 36, 0.15), rgba(99, 102, 241, 0.18), rgba(244, 114, 182, 0.12));
}

.app-logo-mark {
  background: linear-gradient(135deg, #3b82f6 0%, #6366f1 55%, #ec4899 100%);
  box-shadow:
    0 14px 30px rgba(79, 70, 229, 0.2),
    0 8px 18px rgba(59, 130, 246, 0.16);
}

.app-logo-text {
  color: transparent;
  background-image: linear-gradient(90deg, #1d4ed8 0%, #4f46e5 52%, #be185d 100%);
  -webkit-background-clip: text;
  background-clip: text;
}

.app-icon-control,
.app-sidebar-pill,
.app-top-chip,
.app-top-icon,
.app-theme-switch {
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: rgba(255, 255, 255, 0.82);
  color: #475569;
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    box-shadow 180ms ease,
    color 180ms ease,
    background-color 180ms ease;
}

.app-icon-control:hover,
.app-sidebar-pill:hover,
.app-top-chip:hover,
.app-top-icon:hover,
.app-theme-switch:hover {
  transform: translateY(-1px);
  border-color: rgba(129, 140, 248, 0.42);
  color: #4f46e5;
  box-shadow: 0 14px 30px rgba(79, 70, 229, 0.12);
}

.app-top-chip--active {
  color: #1e3a8a;
  border-color: rgba(129, 140, 248, 0.48);
  background:
    linear-gradient(135deg, rgba(224, 242, 254, 0.74) 0%, rgba(238, 242, 255, 0.8) 55%, rgba(252, 231, 243, 0.72) 100%);
  box-shadow:
    0 14px 30px rgba(79, 70, 229, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.65);
}

.app-sidebar-pill--active {
  color: #1e3a8a;
  border-color: rgba(129, 140, 248, 0.48);
  background:
    linear-gradient(135deg, rgba(224, 242, 254, 0.74) 0%, rgba(238, 242, 255, 0.8) 55%, rgba(252, 231, 243, 0.72) 100%);
  box-shadow:
    0 14px 30px rgba(79, 70, 229, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.65);
}

.app-theme-switch {
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 118px;
  padding: 0.45rem 0.5rem 0.45rem 0.85rem;
  border-radius: 9999px;
}

.app-theme-switch__label {
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #64748b;
}

.app-theme-switch__track {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 74px;
  height: 38px;
  padding: 0 0.55rem;
  border-radius: 9999px;
  background:
    linear-gradient(90deg, rgba(254, 240, 138, 0.7) 0%, rgba(255, 255, 255, 0.92) 48%, rgba(226, 232, 240, 0.92) 100%);
  box-shadow:
    inset 0 1px 2px rgba(255, 255, 255, 0.7),
    inset 0 -1px 3px rgba(148, 163, 184, 0.2);
  overflow: hidden;
}

.app-theme-switch__track-icon {
  position: relative;
  z-index: 1;
  transition: opacity 180ms ease, color 180ms ease;
}

.app-theme-switch__track-icon--sun {
  color: #d97706;
}

.app-theme-switch__track-icon--moon {
  color: #64748b;
  opacity: 0.68;
}

.app-theme-switch__thumb {
  position: absolute;
  top: 4px;
  left: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 9999px;
  background: linear-gradient(135deg, #f59e0b 0%, #f97316 100%);
  color: #fff7ed;
  box-shadow:
    0 8px 18px rgba(249, 115, 22, 0.24),
    inset 0 1px 0 rgba(255, 255, 255, 0.35);
  transition:
    transform 220ms ease,
    background 220ms ease,
    color 220ms ease,
    box-shadow 220ms ease;
}

.app-theme-switch--dark .app-theme-switch__label {
  color: #cbd5e1;
}

.app-theme-switch--dark .app-theme-switch__track {
  background:
    linear-gradient(90deg, rgba(15, 23, 42, 0.96) 0%, rgba(30, 41, 59, 0.92) 52%, rgba(51, 65, 85, 0.88) 100%);
  box-shadow:
    inset 0 1px 2px rgba(15, 23, 42, 0.55),
    inset 0 -1px 3px rgba(15, 23, 42, 0.42);
}

.app-theme-switch--dark .app-theme-switch__track-icon--sun {
  color: #64748b;
  opacity: 0.45;
}

.app-theme-switch--dark .app-theme-switch__track-icon--moon {
  color: #c4b5fd;
  opacity: 1;
}

.app-theme-switch--dark .app-theme-switch__thumb {
  transform: translateX(36px);
  background: linear-gradient(135deg, #1d4ed8 0%, #4338ca 100%);
  color: #dbeafe;
  box-shadow:
    0 10px 22px rgba(29, 78, 216, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.18);
}

.app-nav-group-title {
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #94a3b8;
}

.app-nav-button {
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 1rem;
  background: #ffffff;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.78);
  text-align: left;
  transition:
    transform 220ms ease,
    color 220ms ease,
    background-color 220ms ease,
    box-shadow 220ms ease,
    border-color 220ms ease;
}

.app-nav-button--idle {
  color: #475569;
}

.app-nav-button--idle:hover {
  transform: translateY(-1px);
  color: #334155;
  border-color: rgba(129, 140, 248, 0.26);
  background: #ffffff;
  box-shadow: 0 14px 28px rgba(15, 23, 42, 0.06);
}

.app-nav-button--idle::before {
  content: '';
  position: absolute;
  left: 0.4rem;
  top: 50%;
  width: 2px;
  height: 0;
  border-radius: 9999px;
  transform: translateY(-50%);
  background: linear-gradient(180deg, #38bdf8, #818cf8, #f472b6);
  opacity: 0;
  transition: height 220ms ease, opacity 220ms ease;
}

.app-nav-button--idle:hover::before {
  height: 60%;
  opacity: 0.7;
}

.app-nav-button--active {
  color: #1e3a8a;
  border-color: rgba(129, 140, 248, 0.36);
  background: #ffffff;
  box-shadow:
    0 0 0 2px rgba(129, 140, 248, 0.12),
    0 14px 30px rgba(15, 23, 42, 0.08);
}

.app-nav-button--active::before {
  content: '';
  position: absolute;
  left: 0.35rem;
  top: 50%;
  width: 3px;
  height: 74%;
  border-radius: 9999px;
  transform: translateY(-50%);
  background: linear-gradient(180deg, #38bdf8, #818cf8, #f472b6);
  box-shadow: 0 0 14px rgba(129, 140, 248, 0.35);
}

.app-nav-button--disabled {
  color: #cbd5e1;
  cursor: not-allowed;
}

.app-nav-button--disabled:hover {
  transform: none;
  color: #cbd5e1;
  background: #ffffff;
  box-shadow: none;
}

.app-user-card__inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.9rem;
}

.app-user-card__inner--collapsed {
  flex-direction: column;
  justify-content: center;
}

.app-user-card__identity {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}

.app-sidebar__footer {
  position: relative;
  border-top: 1px solid rgba(226, 232, 240, 0.68);
}

.app-user-card {
  border: 1px solid rgba(226, 232, 240, 0.92);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.82) 0%, rgba(248, 250, 252, 0.92) 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.55);
}

.app-theme-switch--embedded {
  flex-shrink: 0;
}

.app-theme-switch--compact {
  min-width: auto;
  gap: 0;
  padding: 0.35rem;
}

.app-theme-switch--compact .app-theme-switch__label {
  display: none;
}

.app-theme-switch--compact .app-theme-switch__track {
  width: 68px;
  height: 36px;
}

.app-theme-switch--compact .app-theme-switch__thumb {
  width: 28px;
  height: 28px;
}

.app-theme-switch--compact.app-theme-switch--dark .app-theme-switch__thumb {
  transform: translateX(32px);
}

.app-mobile-nav {
  border-top: 1px solid rgba(226, 232, 240, 0.82);
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  box-shadow: 0 -10px 30px rgba(15, 23, 42, 0.08);
}

.app-mobile-tab {
  position: relative;
  transition: color 180ms ease, transform 180ms ease;
}

.app-mobile-tab--active {
  color: #4f46e5;
}

.app-mobile-tab--active::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: -2px;
  width: 24px;
  height: 3px;
  border-radius: 9999px;
  transform: translateX(-50%);
  background: linear-gradient(90deg, #38bdf8, #818cf8, #f472b6);
}

.app-mobile-tab--idle {
  color: #64748b;
}

.app-mobile-tab--idle:hover {
  color: #334155;
  transform: translateY(-1px);
}

.app-mobile-tab--disabled {
  color: #cbd5e1;
}

.app-main {
  background: transparent;
}

.app-main--clean {
  background: #ffffff;
}

:global(html.dark) .app-shell {
  background:
    radial-gradient(920px circle at -10% -12%, rgba(56, 189, 248, 0.14), transparent 44%),
    radial-gradient(840px circle at 108% 4%, rgba(129, 140, 248, 0.14), transparent 46%),
    linear-gradient(160deg, rgba(5, 6, 13, 0.96) 0%, rgba(11, 16, 32, 0.95) 52%, rgba(7, 11, 22, 0.96) 100%);
}

:global(html.dark) .app-sidebar {
  border-right-color: rgba(255, 255, 255, 0.08);
  background:
    linear-gradient(180deg, rgba(10, 10, 15, 0.92) 0%, rgba(12, 15, 23, 0.94) 100%);
  box-shadow:
    0 18px 42px rgba(0, 0, 0, 0.38),
    inset -1px 0 0 rgba(255, 255, 255, 0.03);
}

:global(html.dark) .app-sidebar__header,
:global(html.dark) .app-sidebar__footer {
  border-color: rgba(255, 255, 255, 0.08);
}

:global(html.dark) .app-logo-text {
  background-image: linear-gradient(90deg, #ffffff 0%, #c4b5fd 46%, #7dd3fc 100%);
}

:global(html.dark) .app-icon-control,
:global(html.dark) .app-sidebar-pill,
:global(html.dark) .app-top-chip,
:global(html.dark) .app-top-icon,
:global(html.dark) .app-theme-switch,
:global(html.dark) .app-user-card {
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.04);
  color: #cbd5e1;
}

:global(html.dark) .app-icon-control:hover,
:global(html.dark) .app-sidebar-pill:hover,
:global(html.dark) .app-top-chip:hover,
:global(html.dark) .app-top-icon:hover,
:global(html.dark) .app-theme-switch:hover {
  border-color: rgba(129, 140, 248, 0.4);
  color: #c4b5fd;
  box-shadow: 0 16px 30px rgba(0, 0, 0, 0.28);
}

:global(html.dark) .app-top-chip--active {
  color: #e2e8f0;
  border-color: rgba(129, 140, 248, 0.38);
  background:
    linear-gradient(135deg, rgba(30, 58, 138, 0.42) 0%, rgba(67, 56, 202, 0.34) 55%, rgba(131, 24, 67, 0.28) 100%);
  box-shadow: 0 16px 30px rgba(0, 0, 0, 0.28);
}

:global(html.dark) .app-sidebar-pill--active {
  color: #e2e8f0;
  border-color: rgba(129, 140, 248, 0.38);
  background:
    linear-gradient(135deg, rgba(30, 58, 138, 0.42) 0%, rgba(67, 56, 202, 0.34) 55%, rgba(131, 24, 67, 0.28) 100%);
  box-shadow: 0 16px 30px rgba(0, 0, 0, 0.28);
}

:global(html.dark) .app-nav-group-title {
  color: #64748b;
}

:global(html.dark) .app-nav-button {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  box-shadow: none;
}

:global(html.dark) .app-nav-button--idle {
  color: #94a3b8;
}

:global(html.dark) .app-nav-button--idle:hover {
  color: #e2e8f0;
  border-color: rgba(129, 140, 248, 0.28);
  background: rgba(255, 255, 255, 0.06);
  box-shadow: 0 14px 28px rgba(0, 0, 0, 0.22);
}

:global(html.dark) .app-nav-button--active {
  color: #e2e8f0;
  border-color: rgba(129, 140, 248, 0.34);
  background: rgba(255, 255, 255, 0.08);
  box-shadow:
    0 0 0 2px rgba(129, 140, 248, 0.14),
    0 14px 30px rgba(0, 0, 0, 0.28);
}

:global(html.dark) .app-nav-button--disabled {
  color: #475569;
}

:global(html.dark) .app-nav-button--disabled:hover {
  background: rgba(255, 255, 255, 0.04);
}

:global(html.dark) .app-mobile-nav {
  border-top-color: rgba(255, 255, 255, 0.08);
  background: rgba(10, 10, 15, 0.9);
  box-shadow: 0 -12px 32px rgba(0, 0, 0, 0.3);
}

:global(html.dark) .app-mobile-tab--idle {
  color: #94a3b8;
}

:global(html.dark) .app-mobile-tab--idle:hover {
  color: #e2e8f0;
}

:global(html.dark) .app-main--clean {
  background: #020617;
}

@media (max-width: 639px) {
  .app-theme-switch {
    min-width: auto;
    gap: 0;
    padding: 0.35rem;
  }

  .app-theme-switch__track {
    width: 68px;
    height: 36px;
  }

  .app-theme-switch__thumb {
    width: 28px;
    height: 28px;
  }

  .app-theme-switch--dark .app-theme-switch__thumb {
    transform: translateX(32px);
  }
}
</style>
