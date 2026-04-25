<script setup lang="ts">
import { ref, computed, onBeforeUnmount, onMounted, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useThemeStore } from './stores/theme'
import { useInterviewStore } from './stores/interview'
import BlobBackground from './components/BlobBackground.vue'
import {
  Bot, Settings,
  Sun, Moon, ArrowLeft, MessageSquare, BookOpen, Sparkles, FilePlus2, History, FileUser, ChevronLeft,
  SlidersHorizontal, ClipboardList, Map as MapIcon, Check, GripVertical
} from 'lucide-vue-next'

const CatLoading = defineAsyncComponent(() => import('./components/CatLoading.vue'))

const theme = useThemeStore()
const interview = useInterviewStore()
const router = useRouter()
const route = useRoute()
const isRouteLoading = ref(false)
const pendingRouteName = ref('')
const isDesktop = typeof window !== 'undefined' && Boolean(window.proviewDesktop?.isDesktop)
const SIDEBAR_COLLAPSED_KEY = 'proview:sidebar-collapsed'
const DESKTOP_ZOOM_KEY = 'proview:desktop-zoom-factor'
const NAV_SORT_STATE_KEY = 'proview:nav-sort-state'
const DESKTOP_ZOOM_MIN = 0.8
const DESKTOP_ZOOM_MAX = 1.15
const DESKTOP_ZOOM_STEP = 0.05

function safeStorageGet(key: string): string {
  try {
    return localStorage.getItem(key) || ''
  } catch {
    return ''
  }
}

function safeStorageSet(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Ignore storage write failures (e.g. file:// with blocked storage).
  }
}

const isSidebarCollapsed = ref(safeStorageGet(SIDEBAR_COLLAPSED_KEY) === '1')
const desktopZoomFactor = ref(1)
let routeLoadingTimer: ReturnType<typeof setTimeout> | null = null
type SortableGroup = '面试流程' | '工具箱'
type NavItem = {
  name: string
  icon: any
  label: string
  path: string
  group: SortableGroup
  routeName?: string
  disabled?: boolean
}
type ItemRenderEntry =
  | { kind: 'item'; item: NavItem }
const defaultGroupOrder: SortableGroup[] = ['面试流程', '工具箱']
const defaultItemOrder: Record<SortableGroup, string[]> = {
  '面试流程': ['setup', 'history', 'interview', 'report', 'summary'],
  '工具箱': ['resume-optimizer', 'resume-builder', 'my-resumes', 'career-planning'],
}
const isNavSortMode = ref(false)
const navGroupOrder = ref<SortableGroup[]>([...defaultGroupOrder])
const navItemOrder = ref<Record<SortableGroup, string[]>>({
  '面试流程': [...defaultItemOrder['面试流程']],
  '工具箱': [...defaultItemOrder['工具箱']],
})
const draggingGroup = ref<SortableGroup | null>(null)
const draggingItem = ref<{ group: SortableGroup; name: string } | null>(null)
const armedGroupDrag = ref<SortableGroup | null>(null)
const dragOverGroup = ref<SortableGroup | null>(null)
const dragOverItem = ref<{ group: SortableGroup; name: string } | null>(null)
const sidebarScrollRef = ref<HTMLElement | null>(null)
const dragPreviewItem = ref<NavItem | null>(null)
const dragPreviewStyle = ref<Record<string, string>>({})
const dragShiftMap = ref<Record<string, number>>({})
const sortModeHintMessage = ref('')
let sortModeHintTimer: ReturnType<typeof setTimeout> | null = null
let autoScrollRaf: number | null = null
let autoScrollVelocity = 0
let dragOverUpdateRaf: number | null = null
let pendingDragOverGroup: SortableGroup | null = null
let pendingDragOverItem: { group: SortableGroup; name: string } | null = null
let pendingAutoScrollClientY: number | null = null
let pointerDraggingItemHeight = 0
let pointerDraggingOffsetX = 0
let pointerDraggingOffsetY = 0
let pointerDraggingActive = false
let pointerArmedDrag: { group: SortableGroup; name: string; startX: number; startY: number } | null = null
let pointerArmedItem: NavItem | null = null
let pointerArmedSourceRect: DOMRect | null = null
let pointerDragStartClientY = 0
let pointerDragStartIndex = -1
let pointerDragCurrentIndex = -1
let pointerDragOutsideList = false
let pointerLastAppliedTargetIndex = -1
let lastReorderCalcClientX = 0
let lastReorderCalcClientY = 0
let lastDropTarget: { group: SortableGroup; name: string } | null = null
const DRAG_CONFIG = {
  // Start dragging only after pointer moved this many px. Recommended: 5-8.
  activationDistancePx: 9,
  // Recompute insertion only when pointer moved enough since last calc. Recommended: 3-6.
  reorderMinDistancePx: 6,
  // Limit insertion index delta per frame to avoid multi-level jumps. Recommended: 1-2.
  maxIndexStepPerFrame: 1,
  // Swap only after crossing this ratio of item height to reduce sensitivity. Recommended: 0.55-0.75.
  swapThresholdRatio: 0.68,
  // Sidebar edge auto-scroll trigger distance. Recommended: 60-90.
  autoScrollEdgeThresholdPx: 72,
  // Sidebar edge auto-scroll max speed per frame. Recommended: 8-14.
  autoScrollMaxSpeedPx: 10,
} as const
const navItemElementMap = new Map<string, HTMLElement>()

onMounted(() => {
  interview.rehydrateInterviewSession()
  restoreNavSortState()
  if (!isDesktop) {
    return
  }

  const storedZoom = Number.parseFloat(safeStorageGet(DESKTOP_ZOOM_KEY))
  const initialZoom = Number.isFinite(storedZoom)
    ? storedZoom
    : (window.proviewDesktop?.getZoomFactor?.() || 1)

  applyDesktopZoom(initialZoom)
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
const desktopZoomPercent = computed(() => `${Math.round(desktopZoomFactor.value * 100)}%`)
const canZoomOutDesktop = computed(() => desktopZoomFactor.value > DESKTOP_ZOOM_MIN + 0.001)
const canZoomInDesktop = computed(() => desktopZoomFactor.value < DESKTOP_ZOOM_MAX - 0.001)

function clampDesktopZoom(factor: number) {
  if (!Number.isFinite(factor)) {
    return 1
  }
  return Math.min(DESKTOP_ZOOM_MAX, Math.max(DESKTOP_ZOOM_MIN, +factor.toFixed(2)))
}

function applyDesktopZoom(factor: number) {
  const nextFactor = clampDesktopZoom(factor)
  desktopZoomFactor.value = window.proviewDesktop?.setZoomFactor?.(nextFactor) || nextFactor
  safeStorageSet(DESKTOP_ZOOM_KEY, String(desktopZoomFactor.value))
}

function zoomOutDesktop() {
  applyDesktopZoom(desktopZoomFactor.value - DESKTOP_ZOOM_STEP)
}

function zoomInDesktop() {
  applyDesktopZoom(desktopZoomFactor.value + DESKTOP_ZOOM_STEP)
}

function resetDesktopZoom() {
  applyDesktopZoom(1)
}

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

const navItemsSource = computed<NavItem[]>(() => [
  { name: 'setup', icon: SlidersHorizontal, label: '面试配置', path: '/', group: '面试流程' },
  { name: 'history', icon: History, label: '面试历史', path: '/history', group: '面试流程' },
  { name: 'interview', icon: MessageSquare, label: '面试房间', path: '/interview', disabled: !interview.canEnterInterviewRoom, group: '面试流程' },
  { name: 'report', icon: ClipboardList, label: '评估报告', path: '/report', group: '面试流程' },
  { name: 'summary', icon: BookOpen, label: '面经总结', path: '/summary', group: '面试流程' },
  { name: 'resume-optimizer', icon: Sparkles, label: '简历优化', path: '/resume-optimizer', group: '工具箱' },
  { name: 'resume-builder', icon: FilePlus2, label: '简历生成', path: '/resume-builder', group: '工具箱' },
  { name: 'my-resumes', icon: FileUser, label: '我的简历', path: '/my-resumes', group: '工具箱' },
  { name: 'career-planning', icon: MapIcon, label: '职业规划', routeName: 'career-planning-overview', path: '/career-planning/overview', group: '工具箱' },
])

const settingsNavItem = { name: 'runtime-config', icon: Settings, label: '应用设置', path: '/config' }
const groupedNavItems = computed(() => {
  const grouped = {
    '面试流程': [] as NavItem[],
    '工具箱': [] as NavItem[],
  }
  const sourceMap = new Map(navItemsSource.value.map(item => [item.name, item]))

  for (const group of defaultGroupOrder) {
    const validNames = defaultItemOrder[group]
    const desiredNames = navItemOrder.value[group]
    const normalizedNames = desiredNames
      .filter(name => validNames.includes(name))
      .concat(validNames.filter(name => !desiredNames.includes(name)))

    grouped[group] = normalizedNames
      .map(name => sourceMap.get(name))
      .filter((item): item is NavItem => item !== undefined && item.group === group)
  }

  return grouped
})
const navItems = computed(() => navGroupOrder.value.flatMap(group => groupedNavItems.value[group]))
const sortableGroups = computed(() => navGroupOrder.value.map(group => ({
  name: group,
  items: groupedNavItems.value[group],
})))

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

function handleNavItemClick(item: NavItem) {
  if (isNavSortMode.value) {
    showSortModeHint()
    return
  }
  navigateTo(item)
}

function getSortableNavItemClass(item: { name: string; disabled?: boolean }) {
  if (isNavSortMode.value) {
    return item.disabled ? 'app-nav-button--disabled' : 'app-nav-button--active'
  }
  return getNavItemClass(
    item,
    'app-nav-button--active',
    'app-nav-button--idle',
    'app-nav-button--disabled'
  )
}

function getNavItemClass(item: { name: string; disabled?: boolean }, activeClass: string, idleClass: string, disabledClass: string) {
  if (currentNav.value === item.name) return activeClass
  if (item.disabled) return disabledClass
  return idleClass
}

function handleThemeToggle(e: MouseEvent) {
  theme.toggle(e.currentTarget as HTMLElement)
}

function setThemeMode(mode: 'light' | 'dark', e: MouseEvent) {
  const wantsDark = mode === 'dark'
  if (theme.isDark === wantsDark) return
  theme.toggle(e.currentTarget as HTMLElement)
}

function toggleSidebarTheme(e: MouseEvent) {
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
  safeStorageSet(SIDEBAR_COLLAPSED_KEY, isSidebarCollapsed.value ? '1' : '0')
}

function toggleNavSortMode() {
  isNavSortMode.value = !isNavSortMode.value
  draggingGroup.value = null
  draggingItem.value = null
  dragPreviewItem.value = null
  dragPreviewStyle.value = {}
  dragShiftMap.value = {}
  dragOverGroup.value = null
  dragOverItem.value = null
  clearDragArming()
}

function persistNavSortState() {
  safeStorageSet(NAV_SORT_STATE_KEY, JSON.stringify({
    groupOrder: navGroupOrder.value,
    itemOrder: navItemOrder.value,
  }))
}

function restoreNavSortState() {
  const raw = safeStorageGet(NAV_SORT_STATE_KEY)
  if (!raw) return

  try {
    const parsed = JSON.parse(raw) as {
      groupOrder?: SortableGroup[]
      itemOrder?: Partial<Record<SortableGroup, string[]>>
    }
    if (Array.isArray(parsed.groupOrder)) {
      const normalizedGroupOrder = parsed.groupOrder
        .filter(group => defaultGroupOrder.includes(group))
        .concat(defaultGroupOrder.filter(group => !parsed.groupOrder?.includes(group)))
      navGroupOrder.value = normalizedGroupOrder as SortableGroup[]
    }
    if (parsed.itemOrder && typeof parsed.itemOrder === 'object') {
      navItemOrder.value = {
        '面试流程': normalizeOrder(parsed.itemOrder['面试流程'], defaultItemOrder['面试流程']),
        '工具箱': normalizeOrder(parsed.itemOrder['工具箱'], defaultItemOrder['工具箱']),
      }
    }
  } catch {
    navGroupOrder.value = [...defaultGroupOrder]
    navItemOrder.value = {
      '面试流程': [...defaultItemOrder['面试流程']],
      '工具箱': [...defaultItemOrder['工具箱']],
    }
  }
}

function normalizeOrder(value: string[] | undefined, defaults: string[]) {
  if (!Array.isArray(value)) return [...defaults]
  return value
    .filter(name => defaults.includes(name))
    .concat(defaults.filter(name => !value.includes(name)))
}

function onGroupDragStart(group: SortableGroup, event: DragEvent) {
  if (!isNavSortMode.value || armedGroupDrag.value !== group) return
  draggingGroup.value = group
  dragOverGroup.value = group
  const source = event.currentTarget as HTMLElement | null
  if (source && event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setDragImage(source, 24, 24)
  }
}

function onGroupDrop(targetGroup: SortableGroup) {
  if (!isNavSortMode.value || !draggingGroup.value) return
  if (draggingGroup.value !== targetGroup) {
    const order = [...navGroupOrder.value]
    const from = order.indexOf(draggingGroup.value)
    const to = order.indexOf(targetGroup)
    if (from >= 0 && to >= 0) {
      const [moved] = order.splice(from, 1)
      if (!moved) return
      order.splice(to, 0, moved)
      navGroupOrder.value = order
    }
  }
  draggingGroup.value = null
  dragOverGroup.value = null
  armedGroupDrag.value = null
  stopAutoScroll()
  persistNavSortState()
}

function onItemDragStart(group: SortableGroup, itemName: string, event: DragEvent) {
  // Menu item sorting now uses pointer-driven drag for smoother preview.
  event.preventDefault()
  if (!isNavSortMode.value) return
  void group
  void itemName
}

function onItemDrop(group: SortableGroup) {
  flushDragOverUpdates()
  if (!isNavSortMode.value || !draggingItem.value) return
  if (draggingItem.value.group !== group) return
  if (pointerDragOutsideList) {
    draggingItem.value = null
    dragOverItem.value = null
    stopAutoScroll()
    return
  }
  const order = [...navItemOrder.value[group]]
  const from = order.indexOf(draggingItem.value.name)
  if (from < 0) return
  const orderWithoutDragged = order.filter(name => name !== draggingItem.value?.name)
  const targetIndex = Math.max(0, Math.min(orderWithoutDragged.length, pointerDragCurrentIndex))
  if (targetIndex !== from) {
    orderWithoutDragged.splice(targetIndex, 0, draggingItem.value.name)
    navItemOrder.value[group] = orderWithoutDragged
    persistNavSortState()
  }
  draggingItem.value = null
  dragOverItem.value = null
  stopAutoScroll()
}

function onSortableSectionDrop(group: SortableGroup) {
  if (draggingGroup.value) {
    onGroupDrop(group)
    return
  }
  if (draggingItem.value?.group === group) {
    onItemDrop(group)
  }
}

function onSortableSectionDragOver(group: SortableGroup) {
  pendingDragOverGroup = group
  if (draggingItem.value?.group === group) {
    pendingDragOverItem = null
  }
  scheduleDragOverUpdates()
}

function onSortableSectionDragOverWithEvent(group: SortableGroup, event: DragEvent) {
  onSortableSectionDragOver(group)
  pendingAutoScrollClientY = event.clientY
  scheduleDragOverUpdates()
}

function onNavItemDragOver(group: SortableGroup, itemName: string, event: DragEvent) {
  if (!isNavSortMode.value || !draggingItem.value || draggingItem.value.group !== group || pointerDraggingActive) return
  pendingDragOverItem = { group, name: itemName }
  pendingAutoScrollClientY = event.clientY
  scheduleDragOverUpdates()
}

function armGroupDrag(group: SortableGroup, event: MouseEvent) {
  if (!isNavSortMode.value) return
  event.stopPropagation()
  armedGroupDrag.value = group
}

function clearDragArming() {
  flushDragOverUpdates()
  armedGroupDrag.value = null
  pointerArmedDrag = null
  pointerArmedItem = null
  pointerArmedSourceRect = null
  dragOverGroup.value = null
  dragOverItem.value = null
  dragShiftMap.value = {}
  dragPreviewItem.value = null
  dragPreviewStyle.value = {}
  pointerDraggingItemHeight = 0
  pointerDraggingOffsetX = 0
  pointerDraggingOffsetY = 0
  pointerDragStartClientY = 0
  pointerDragStartIndex = -1
  pointerDragCurrentIndex = -1
  pointerDragOutsideList = false
  pointerLastAppliedTargetIndex = -1
  pointerDraggingActive = false
  lastDropTarget = null
  window.removeEventListener('mousemove', onWindowPointerMove)
  window.removeEventListener('mouseup', onWindowPointerUp)
  stopAutoScroll()
}

function scheduleDragOverUpdates() {
  if (dragOverUpdateRaf !== null) return
  dragOverUpdateRaf = requestAnimationFrame(() => {
    dragOverUpdateRaf = null
    applyPendingDragOverUpdates()
  })
}

function applyPendingDragOverUpdates() {
  if (pendingDragOverGroup !== null && dragOverGroup.value !== pendingDragOverGroup) {
    dragOverGroup.value = pendingDragOverGroup
  }
  if (pendingDragOverItem !== null) {
    const current = dragOverItem.value
    if (!current || current.group !== pendingDragOverItem.group || current.name !== pendingDragOverItem.name) {
      dragOverItem.value = pendingDragOverItem
    }
  } else if (draggingItem.value && dragOverItem.value !== null) {
    dragOverItem.value = null
  }
  if (pendingAutoScrollClientY !== null) {
    updateAutoScrollByClientY(pendingAutoScrollClientY)
  }
  pendingDragOverGroup = null
  pendingDragOverItem = null
  pendingAutoScrollClientY = null
  applyItemDragTransforms()
}

function flushDragOverUpdates() {
  if (dragOverUpdateRaf !== null) {
    cancelAnimationFrame(dragOverUpdateRaf)
    dragOverUpdateRaf = null
  }
  applyPendingDragOverUpdates()
}

function stopAutoScroll() {
  autoScrollVelocity = 0
  if (autoScrollRaf !== null) {
    cancelAnimationFrame(autoScrollRaf)
    autoScrollRaf = null
  }
}

function runAutoScroll() {
  if (!sidebarScrollRef.value || autoScrollVelocity === 0) {
    stopAutoScroll()
    return
  }
  sidebarScrollRef.value.scrollTop += autoScrollVelocity
  autoScrollRaf = requestAnimationFrame(runAutoScroll)
}

function updateAutoScroll(event: DragEvent) {
  updateAutoScrollByClientY(event.clientY)
}

function updateAutoScrollByClientY(clientY: number) {
  if (!isNavSortMode.value || (!draggingItem.value && !draggingGroup.value)) {
    stopAutoScroll()
    return
  }
  const container = sidebarScrollRef.value
  if (!container) return

  const rect = container.getBoundingClientRect()
  const y = clientY
  const threshold = DRAG_CONFIG.autoScrollEdgeThresholdPx
  const maxSpeed = DRAG_CONFIG.autoScrollMaxSpeedPx
  let nextVelocity = 0

  if (y < rect.top + threshold) {
    const ratio = Math.max(0, (rect.top + threshold - y) / threshold)
    nextVelocity = -Math.max(1, Math.round(maxSpeed * ratio))
  } else if (y > rect.bottom - threshold) {
    const ratio = Math.max(0, (y - (rect.bottom - threshold)) / threshold)
    nextVelocity = Math.max(1, Math.round(maxSpeed * ratio))
  }

  if (nextVelocity === 0) {
    stopAutoScroll()
    return
  }
  autoScrollVelocity = nextVelocity
  if (autoScrollRaf === null) {
    autoScrollRaf = requestAnimationFrame(runAutoScroll)
  }
}

function makeNavItemKey(group: SortableGroup, itemName: string) {
  return `${group}::${itemName}`
}

function setNavItemRef(group: SortableGroup, itemName: string, el: unknown) {
  const key = makeNavItemKey(group, itemName)
  if (!el) {
    navItemElementMap.delete(key)
    return
  }
  if (el instanceof HTMLElement) {
    navItemElementMap.set(key, el)
    return
  }
  if (typeof el === 'object' && el !== null && '$el' in el) {
    const root = (el as { $el?: unknown }).$el
    if (root instanceof HTMLElement) {
      navItemElementMap.set(key, root)
    }
  }
}

function onItemGripPointerDown(group: SortableGroup, itemName: string, event: MouseEvent) {
  if (!isNavSortMode.value) return
  if (event.button !== 0) return
  const source = navItemElementMap.get(makeNavItemKey(group, itemName))
  const item = groupedNavItems.value[group].find(entry => entry.name === itemName)
  if (!source || !item) return

  event.stopPropagation()
  pointerArmedSourceRect = source.getBoundingClientRect()
  pointerArmedItem = item
  pointerArmedDrag = { group, name: itemName, startX: event.clientX, startY: event.clientY }
  pointerDraggingActive = false
  window.addEventListener('mousemove', onWindowPointerMove)
  window.addEventListener('mouseup', onWindowPointerUp)
}

function startPointerItemDrag(event: MouseEvent) {
  if (!pointerArmedDrag || !pointerArmedItem || !pointerArmedSourceRect) return
  const rect = pointerArmedSourceRect
  pointerDraggingOffsetX = pointerArmedDrag.startX - rect.left
  pointerDraggingOffsetY = pointerArmedDrag.startY - rect.top
  pointerDraggingItemHeight = rect.height
  draggingItem.value = { group: pointerArmedDrag.group, name: pointerArmedDrag.name }
  dragOverItem.value = { group: pointerArmedDrag.group, name: pointerArmedDrag.name }
  const groupOrder = navItemOrder.value[pointerArmedDrag.group]
  pointerDragStartIndex = groupOrder.indexOf(pointerArmedDrag.name)
  pointerDragCurrentIndex = pointerDragStartIndex
  pointerLastAppliedTargetIndex = pointerDragStartIndex
  pointerDragOutsideList = false
  pointerDragStartClientY = event.clientY
  dragPreviewItem.value = pointerArmedItem
  dragPreviewStyle.value = {
    width: `${Math.round(rect.width)}px`,
    left: `${Math.round(event.clientX - pointerDraggingOffsetX)}px`,
    top: `${Math.round(event.clientY - pointerDraggingOffsetY)}px`,
    transform: 'translate3d(0, 0, 0) rotate(-1deg) scale(1.02)',
  }
  lastReorderCalcClientX = event.clientX
  lastReorderCalcClientY = event.clientY
  lastDropTarget = { group: pointerArmedDrag.group, name: pointerArmedDrag.name }
  pointerArmedDrag = null
  pointerArmedItem = null
  pointerArmedSourceRect = null
  pointerDraggingActive = true
  applyItemDragTransforms()
}

function onWindowPointerMove(event: MouseEvent) {
  if (!pointerDraggingActive) {
    if (!pointerArmedDrag) return
    const deltaX = event.clientX - pointerArmedDrag.startX
    const deltaY = event.clientY - pointerArmedDrag.startY
    const distance = Math.hypot(deltaX, deltaY)
    if (distance < DRAG_CONFIG.activationDistancePx) {
      return
    }
    event.preventDefault()
    startPointerItemDrag(event)
  }
  if (!draggingItem.value) return
  const nextLeft = event.clientX - pointerDraggingOffsetX
  const nextTop = event.clientY - pointerDraggingOffsetY
  dragPreviewStyle.value = {
    ...dragPreviewStyle.value,
    left: `${Math.round(nextLeft)}px`,
    top: `${Math.round(nextTop)}px`,
  }

  const dragState = draggingItem.value
  const container = sidebarScrollRef.value
  if (!container) return
  const containerRect = container.getBoundingClientRect()
  const movementDistance = Math.hypot(event.clientX - lastReorderCalcClientX, event.clientY - lastReorderCalcClientY)
  if (movementDistance < DRAG_CONFIG.reorderMinDistancePx) {
    return
  }
  lastReorderCalcClientX = event.clientX
  lastReorderCalcClientY = event.clientY
  if (
    event.clientX < containerRect.left ||
    event.clientX > containerRect.right ||
    event.clientY < containerRect.top ||
    event.clientY > containerRect.bottom
  ) {
    pointerDragOutsideList = true
    setPointerDropTargetByIndex(dragState.group, dragState.name, pointerDragStartIndex)
    return
  }
  pointerDragOutsideList = false
  const nextIndex = resolveSteadyDropIndex(dragState.group, dragState.name, event.clientY)
  setPointerDropTargetByIndex(dragState.group, dragState.name, nextIndex, event.clientY)
}

function resolveSteadyDropIndex(group: SortableGroup, itemName: string, clientY: number) {
  const order = navItemOrder.value[group]
  const total = order.length
  const currentIndex = pointerDragCurrentIndex >= 0 ? pointerDragCurrentIndex : order.indexOf(itemName)
  const startIndex = pointerDragStartIndex >= 0 ? pointerDragStartIndex : order.indexOf(itemName)
  if (total <= 1 || currentIndex < 0 || startIndex < 0 || pointerDraggingItemHeight <= 0) {
    return Math.max(0, currentIndex)
  }
  const deltaY = clientY - pointerDragStartClientY
  const threshold = pointerDraggingItemHeight * DRAG_CONFIG.swapThresholdRatio
  const rawSteps = deltaY >= 0
    ? Math.floor((deltaY + threshold) / pointerDraggingItemHeight)
    : Math.ceil((deltaY - threshold) / pointerDraggingItemHeight)
  const desiredIndex = Math.min(total - 1, Math.max(0, startIndex + rawSteps))
  const deltaIndex = desiredIndex - currentIndex
  if (Math.abs(deltaIndex) <= DRAG_CONFIG.maxIndexStepPerFrame) {
    return desiredIndex
  }
  return currentIndex + Math.sign(deltaIndex) * DRAG_CONFIG.maxIndexStepPerFrame
}

function isSameDropTarget(
  a: { group: SortableGroup; name: string } | null,
  b: { group: SortableGroup; name: string } | null
) {
  if (!a && !b) return true
  if (!a || !b) return false
  return a.group === b.group && a.name === b.name
}

function setPointerDropTargetByIndex(group: SortableGroup, draggingName: string, targetIndex: number, clientY?: number) {
  const order = navItemOrder.value[group]
  if (!order.length) return
  const clampedIndex = Math.max(0, Math.min(order.length - 1, targetIndex))
  if (clampedIndex === pointerLastAppliedTargetIndex) {
    pendingAutoScrollClientY = typeof clientY === 'number' ? clientY : null
    scheduleDragOverUpdates()
    return
  }
  pointerDragCurrentIndex = clampedIndex
  pointerLastAppliedTargetIndex = clampedIndex
  const orderWithoutDragged = order.filter(name => name !== draggingName)
  const target: { group: SortableGroup; name: string } | null = clampedIndex >= orderWithoutDragged.length
    ? null
    : { group, name: orderWithoutDragged[clampedIndex] || '' }
  if (target && !target.name) return
  if (!isSameDropTarget(lastDropTarget, target)) {
    lastDropTarget = target ? { ...target } : null
  }
  pendingDragOverGroup = draggingItem.value?.group || null
  pendingDragOverItem = target ? { ...target } : null
  pendingAutoScrollClientY = typeof clientY === 'number' ? clientY : null
  scheduleDragOverUpdates()
}

function onWindowPointerUp() {
  if (!pointerDraggingActive) {
    clearDragArming()
    return
  }
  if (draggingItem.value) {
    onItemDrop(draggingItem.value.group)
  }
  clearDragArming()
}

function applyItemDragTransforms() {
  if (!draggingItem.value || pointerDraggingItemHeight <= 0) {
    dragShiftMap.value = {}
    return
  }
  const { group, name } = draggingItem.value
  const order = navItemOrder.value[group]
  const fromIndex = order.indexOf(name)
  if (fromIndex < 0) {
    dragShiftMap.value = {}
    return
  }
  const orderWithoutDragged = order.filter(itemName => itemName !== name)
  const safeTargetIndex = Math.max(0, Math.min(orderWithoutDragged.length, pointerDragCurrentIndex))
  const projected = [...orderWithoutDragged]
  projected.splice(safeTargetIndex, 0, name)
  const projectedIndexMap = new Map(projected.map((itemName, index) => [itemName, index]))
  const nextShiftMap: Record<string, number> = {}
  for (let index = 0; index < order.length; index += 1) {
    const itemName = order[index]
    if (!itemName) continue
    if (itemName === name) continue
    const projectedIndex = projectedIndexMap.get(itemName)
    if (typeof projectedIndex !== 'number') continue
    const shift = (projectedIndex - index) * pointerDraggingItemHeight
    if (shift !== 0) {
      nextShiftMap[makeNavItemKey(group, itemName)] = shift
    }
  }
  dragShiftMap.value = nextShiftMap
}

function getSortableItemInlineStyle(group: SortableGroup, itemName: string) {
  const key = makeNavItemKey(group, itemName)
  const shift = dragShiftMap.value[key] || 0
  const isDraggingCurrent = draggingItem.value?.group === group && draggingItem.value.name === itemName
  return {
    transform: `translate3d(0, ${shift}px, 0)`,
    opacity: isDraggingCurrent ? '0' : '1',
    transition: pointerDraggingActive
      ? 'transform 0.2s cubic-bezier(0.2, 0.9, 0.4, 1.1), opacity 0.12s ease-out'
      : 'transform 0.2s ease-out, opacity 0.15s ease-out',
    willChange: 'transform',
  }
}

function getItemRenderEntries(group: SortableGroup, items: NavItem[]): ItemRenderEntry[] {
  void group
  return items.map(item => ({ kind: 'item' as const, item }))
}

function showSortModeHint(message = '请拖拽右侧图标进行排序') {
  sortModeHintMessage.value = message
  if (sortModeHintTimer) {
    clearTimeout(sortModeHintTimer)
  }
  sortModeHintTimer = setTimeout(() => {
    sortModeHintMessage.value = ''
    sortModeHintTimer = null
  }, 1800)
}

onBeforeUnmount(() => {
  clearRouteLoadingTimer()
  flushDragOverUpdates()
  window.removeEventListener('mousemove', onWindowPointerMove)
  window.removeEventListener('mouseup', onWindowPointerUp)
  stopAutoScroll()
  if (sortModeHintTimer) {
    clearTimeout(sortModeHintTimer)
    sortModeHintTimer = null
  }
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
      class="app-sidebar z-20 hidden min-h-0 flex-col overflow-visible transition-[width] duration-300 md:flex"
      :class="[isSidebarCollapsed ? 'w-[80px]' : 'w-[280px]', { 'app-sidebar--collapsed': isSidebarCollapsed }]"
    >
      <button
        type="button"
        class="app-sidebar__toggle"
        :title="isSidebarCollapsed ? '展开导航栏' : '折叠导航栏'"
        @click="toggleSidebar"
      >
        <ChevronLeft class="app-sidebar__toggle-icon h-4 w-4" />
      </button>

      <div class="app-sidebar__header flex h-20 shrink-0 items-center" :class="isSidebarCollapsed ? 'px-3' : 'px-6'">
        <div class="flex min-w-0 flex-1 items-center" :class="isSidebarCollapsed ? 'justify-center' : 'gap-3'">
          <div class="app-logo-mark flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl text-white">
            <Bot class="w-5 h-5" />
          </div>
          <span
            v-if="!isSidebarCollapsed"
            class="app-logo-text truncate text-xl font-bold tracking-tight"
          >
            ProView AI
          </span>
        </div>
      </div>

      <div
        ref="sidebarScrollRef"
        class="app-sidebar__scroll custom-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain"
        @dragover="updateAutoScroll"
        @drop="stopAutoScroll"
        @dragleave="stopAutoScroll"
      >
        <nav class="app-sidebar__nav flex flex-col gap-6 px-5 pb-4 pt-5">
          <button
            type="button"
            class="app-top-chip inline-flex w-full items-center justify-center gap-2 rounded-full px-4 py-2 text-sm font-semibold"
            :class="[
              isSidebarCollapsed ? 'px-2' : '',
              {
                'app-top-chip--active': isNavSortMode,
                'app-top-chip--done': isNavSortMode,
              }
            ]"
            :title="isNavSortMode ? '完成编辑并恢复点击跳转' : '进入编辑排序模式'"
            @click="toggleNavSortMode"
          >
            <span class="app-top-chip__content">
              <component
                :is="isNavSortMode ? Check : SlidersHorizontal"
                class="h-[18px] w-[18px] shrink-0 transition-transform duration-200 group-hover:scale-105"
                :class="{ 'app-top-chip__icon--done': isNavSortMode }"
              />
              <span v-if="!isSidebarCollapsed" class="truncate">{{ isNavSortMode ? '完成编辑' : '编辑排序' }}</span>
            </span>
          </button>

          <div
            v-if="isNavSortMode && !isSidebarCollapsed"
            class="app-nav-group-title"
            title="拖拽每行右侧图标可调整条目顺序，拖拽分组标题右侧图标可调整分组顺序"
          >
            {{ sortModeHintMessage || '编辑模式：拖拽条目右侧图标进行排序' }}
          </div>

          <section
            v-for="group in sortableGroups" :key="group.name"
            class="flex flex-col gap-1"
            :class="{
              'rounded-xl border border-dashed border-slate-400/60 bg-slate-100/40 dark:border-slate-500/70 dark:bg-slate-800/35': isNavSortMode && dragOverGroup === group.name,
              'opacity-80': isNavSortMode && draggingGroup === group.name
            }"
            :draggable="isNavSortMode && armedGroupDrag === group.name"
            @dragstart="onGroupDragStart(group.name, $event)"
            @dragend="clearDragArming"
            @dragover.prevent="onSortableSectionDragOverWithEvent(group.name, $event)"
            @dragleave="dragOverGroup = draggingGroup"
            @drop="onSortableSectionDrop(group.name)"
          >
            <div
              v-if="!isSidebarCollapsed"
              class="app-nav-group-title flex items-center justify-between gap-2"
              @click="isNavSortMode && showSortModeHint('请拖拽分组标题右侧图标排序')"
            >
              <span class="truncate">{{ group.name }}</span>
              <button
                v-if="isNavSortMode"
                type="button"
                class="inline-flex h-5 w-5 shrink-0 items-center justify-center"
                title="拖拽调整分组顺序"
                @mousedown="armGroupDrag(group.name, $event)"
              >
                <GripVertical class="h-4 w-4" />
              </button>
            </div>
            <TransitionGroup
              tag="div"
              class="flex flex-col gap-1"
              move-class="transition-transform duration-200 ease-out"
            >
              <template v-for="entry in getItemRenderEntries(group.name, group.items)" :key="entry.item.name">
                <button
                  @click="handleNavItemClick(entry.item)"
                  class="app-nav-button group flex items-center py-3 text-sm font-medium transition-all duration-200 will-change-transform"
                  :class="[
                    isSidebarCollapsed ? 'justify-center px-0' : 'gap-3 px-4',
                    getSortableNavItemClass(entry.item),
                    isNavSortMode && draggingItem && draggingItem.group === group.name && draggingItem.name === entry.item.name
                      ? 'opacity-60 shadow-lg'
                      : '',
                    isNavSortMode && dragOverItem && dragOverItem.group === group.name && dragOverItem.name === entry.item.name
                      ? 'ring-1 ring-slate-400/70 dark:ring-slate-500/80'
                      : ''
                  ]"
                  :ref="el => setNavItemRef(group.name, entry.item.name, el)"
                  :style="getSortableItemInlineStyle(group.name, entry.item.name)"
                  :disabled="!isNavSortMode && entry.item.disabled"
                  :title="isSidebarCollapsed ? (isNavSortMode ? `${entry.item.label}（拖拽排序）` : entry.item.label) : undefined"
                  @dragstart="onItemDragStart(group.name, entry.item.name, $event)"
                  @dragend="clearDragArming"
                  @dragover.prevent="onNavItemDragOver(group.name, entry.item.name, $event)"
                  @dragleave="dragOverItem = draggingItem"
                  @drop="onItemDrop(group.name)"
                >
                  <component :is="entry.item.icon" class="h-[18px] w-[18px] shrink-0 transition-transform group-hover:scale-105" />
                  <span v-if="!isSidebarCollapsed && !isNavSortMode" class="truncate">{{ entry.item.label }}</span>
                  <span v-else-if="!isSidebarCollapsed" class="truncate">{{ entry.item.label }} · 拖拽排序</span>
                  <button
                    v-if="isNavSortMode"
                    type="button"
                    class="ml-auto inline-flex h-5 w-5 shrink-0 items-center justify-center"
                    title="拖拽调整顺序"
                    @mousedown="onItemGripPointerDown(group.name, entry.item.name, $event)"
                  >
                    <GripVertical class="h-4 w-4" />
                  </button>
                </button>
              </template>
            </TransitionGroup>
          </section>

          <section class="flex flex-col gap-1">
            <div v-if="!isSidebarCollapsed" class="app-nav-group-title">系统</div>
            <button
              @click="goLanding"
              class="app-nav-button group flex items-center py-3 text-sm font-medium app-nav-button--idle"
              :class="isSidebarCollapsed ? 'justify-center px-0' : 'gap-3 px-4'"
              :title="isSidebarCollapsed ? '返回介绍页' : undefined"
            >
              <ArrowLeft class="h-[18px] w-[18px] shrink-0 transition-transform group-hover:scale-105" />
              <span v-if="!isSidebarCollapsed" class="truncate">返回介绍页</span>
            </button>
            <button
              @click="openSettings"
              class="app-nav-button group flex items-center py-3 text-sm font-medium"
              :class="[
                isSidebarCollapsed ? 'justify-center px-0' : 'gap-3 px-4',
                isSettingsRoute ? 'app-nav-button--active' : 'app-nav-button--idle'
              ]"
              :title="isSidebarCollapsed ? '应用设置' : undefined"
            >
              <Settings class="h-[18px] w-[18px] shrink-0 transition-transform group-hover:scale-105" />
              <span v-if="!isSidebarCollapsed" class="truncate">应用设置</span>
            </button>
          </section>
        </nav>
      </div>

      <div class="app-sidebar__footer shrink-0" :class="isSidebarCollapsed ? 'px-3 pb-6 pt-4' : 'px-5 pb-6 pt-4'">
        <div v-if="!isSidebarCollapsed" class="app-sidebar-theme">
          <span class="app-sidebar-theme__label">{{ theme.isDark ? '深色' : '浅色' }}</span>
          <div class="app-sidebar-theme__actions">
            <button
              type="button"
              class="app-sidebar-theme__option"
              :class="{ 'app-sidebar-theme__option--active': !theme.isDark }"
              :aria-pressed="!theme.isDark"
              title="切换到浅色主题"
              @click="setThemeMode('light', $event)"
            >
              <Sun class="h-4 w-4" />
            </button>
            <button
              type="button"
              class="app-sidebar-theme__option"
              :class="{ 'app-sidebar-theme__option--active': theme.isDark }"
              :aria-pressed="theme.isDark"
              title="切换到深色主题"
              @click="setThemeMode('dark', $event)"
            >
              <Moon class="h-4 w-4" />
            </button>
          </div>
        </div>
        <div v-if="isDesktop && !isSidebarCollapsed" class="app-sidebar-zoom">
          <span class="app-sidebar-theme__label">界面缩放</span>
          <div class="app-sidebar-zoom__actions">
            <button
              type="button"
              class="app-sidebar-zoom__button"
              :disabled="!canZoomOutDesktop"
              title="缩小界面"
              @click="zoomOutDesktop"
            >
              -
            </button>
            <button
              type="button"
              class="app-sidebar-zoom__value"
              :disabled="desktopZoomFactor === 1"
              title="恢复默认缩放"
              @click="resetDesktopZoom"
            >
              {{ desktopZoomPercent }}
            </button>
            <button
              type="button"
              class="app-sidebar-zoom__button"
              :disabled="!canZoomInDesktop"
              title="放大界面"
              @click="zoomInDesktop"
            >
              +
            </button>
          </div>
        </div>
        <button
          v-if="isSidebarCollapsed"
          type="button"
          class="app-sidebar-theme-collapsed"
          :title="theme.isDark ? '切换到浅色主题' : '切换到深色主题'"
          :aria-pressed="theme.isDark"
          @click="toggleSidebarTheme"
        >
          <Sun v-if="theme.isDark" class="h-5 w-5" />
          <Moon v-else class="h-5 w-5" />
        </button>
        <div v-if="isDesktop && isSidebarCollapsed" class="app-sidebar-zoom-collapsed">
          <button
            type="button"
            class="app-sidebar-zoom__button"
            :disabled="!canZoomOutDesktop"
            title="缩小界面"
            @click="zoomOutDesktop"
          >
            -
          </button>
          <button
            type="button"
            class="app-sidebar-zoom__value app-sidebar-zoom__value--compact"
            :disabled="desktopZoomFactor === 1"
            title="恢复默认缩放"
            @click="resetDesktopZoom"
          >
            {{ Math.round(desktopZoomFactor * 100) }}
          </button>
          <button
            type="button"
            class="app-sidebar-zoom__button"
            :disabled="!canZoomInDesktop"
            title="放大界面"
            @click="zoomInDesktop"
          >
            +
          </button>
        </div>
      </div>
    </aside>

    <!-- ================== 移动端：底部 Tab ================== -->
    <nav v-if="!isGuestPage" class="app-mobile-nav fixed bottom-0 left-0 right-0 z-50 pb-2 pt-2 md:hidden">
      <div class="flex justify-around">
        <button
          v-for="item in navItems" :key="item.name"
          @click="handleNavItemClick(item)"
          class="app-mobile-tab flex flex-col items-center p-2"
          :class="getNavItemClass(
            item,
            'app-mobile-tab--active',
            'app-mobile-tab--idle',
            'app-mobile-tab--disabled'
          )"
          :disabled="!isNavSortMode && item.disabled"
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

    <div
      v-if="dragPreviewItem"
      class="app-nav-drag-preview pointer-events-none fixed z-[120] flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold"
      :style="dragPreviewStyle"
    >
      <component :is="dragPreviewItem.icon" class="h-[18px] w-[18px] shrink-0" />
      <span class="truncate">{{ dragPreviewItem.label }}</span>
    </div>

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
  --sidebar-bg: var(--ui-sidebar-bg);
  --sidebar-border: var(--ui-sidebar-border);
  --sidebar-text: var(--ui-sidebar-text);
  --sidebar-text-soft: var(--ui-sidebar-text-soft);
  --sidebar-text-muted: var(--ui-sidebar-text-muted);
  --sidebar-hover-bg: var(--ui-sidebar-hover-bg);
  --sidebar-active-bg: var(--ui-sidebar-active-bg);
  --sidebar-indicator: var(--ui-sidebar-indicator);
  --sidebar-logo-bg: var(--ui-sidebar-logo-bg);
  --sidebar-logo-fg: var(--ui-sidebar-logo-fg);
  background: var(--ui-shell-background);
  color: var(--ui-text-primary);
}

.app-sidebar {
  position: relative;
  border-right: 1px solid var(--sidebar-border);
  background: var(--sidebar-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  box-shadow: var(--ui-shadow-md);
}

.app-sidebar::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.1) 0%, rgba(255, 255, 255, 0) 22%);
}

.app-sidebar__toggle {
  position: absolute;
  top: 28px;
  right: -12px;
  z-index: 30;
  display: inline-flex;
  height: 24px;
  width: 24px;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--sidebar-border);
  border-radius: 9999px;
  background: var(--ui-surface-raised);
  color: var(--sidebar-text-muted);
  cursor: pointer;
  box-shadow: var(--ui-shadow-sm);
  transition:
    color 180ms ease,
    background-color 180ms ease,
    border-color 180ms ease,
    box-shadow 180ms ease;
}

.app-sidebar__toggle:hover {
  color: var(--sidebar-text);
  background: var(--ui-surface-3);
  border-color: var(--ui-border-strong);
  box-shadow: var(--ui-shadow-md);
}

.app-sidebar__toggle-icon {
  transition: transform 220ms ease;
}

.app-sidebar--collapsed .app-sidebar__toggle-icon {
  transform: rotate(180deg);
}

.app-sidebar__header {
  position: relative;
  border-bottom: 1px solid var(--sidebar-border);
}

.app-logo-mark {
  background: var(--sidebar-logo-bg);
  color: var(--sidebar-logo-fg);
  transition: background-color 220ms ease, color 220ms ease;
}

.app-logo-text {
  color: var(--sidebar-text);
  transition: color 220ms ease;
}

.app-top-chip,
.app-theme-switch,
.app-sidebar-theme-collapsed {
  border: 1px solid var(--ui-border-default);
  background: var(--ui-surface-floating);
  color: var(--ui-text-secondary);
  cursor: pointer;
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  box-shadow: var(--ui-shadow-sm);
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    box-shadow 180ms ease,
    color 180ms ease,
    background-color 180ms ease;
}

.app-top-chip,
.app-theme-switch {
  border-radius: 9999px;
}

.app-top-chip:hover,
.app-theme-switch:hover,
.app-sidebar-theme-collapsed:hover {
  transform: translateY(-1px);
  border-color: var(--ui-border-strong);
  background: var(--ui-surface-raised);
  color: var(--ui-text-primary);
  box-shadow: var(--ui-shadow-md);
}

.app-top-chip:hover,
.app-theme-switch:hover {
  border-radius: 9999px;
}

.app-top-chip--active {
  color: var(--ui-text-primary);
  border-color: var(--ui-border-strong);
  background: var(--ui-surface-3);
  box-shadow: var(--ui-shadow-sm);
}

.app-top-chip--done {
  color: var(--ui-accent-strong);
  border-color: color-mix(in srgb, var(--ui-accent-strong) 28%, var(--ui-border-default));
  background: color-mix(in srgb, var(--ui-accent-soft) 62%, var(--ui-surface-floating));
  box-shadow: 0 8px 22px color-mix(in srgb, var(--ui-accent-strong) 18%, transparent);
}

.app-top-chip--done:hover {
  color: var(--ui-accent-strong);
  border-color: color-mix(in srgb, var(--ui-accent-strong) 36%, var(--ui-border-strong));
  background: color-mix(in srgb, var(--ui-accent-soft) 74%, var(--ui-surface-raised));
}

.app-top-chip__content {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  min-width: 0;
}

.app-top-chip__icon--done {
  transform: scale(1.05);
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
  font-size: 0.8rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ui-text-muted);
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
  border: 1px solid var(--ui-border-subtle);
  background: var(--ui-surface-3);
  box-shadow: inset 0 1px 2px rgba(255, 255, 255, 0.1);
  overflow: hidden;
}

.app-theme-switch__track-icon {
  position: relative;
  z-index: 1;
  transition: opacity 180ms ease, color 180ms ease;
}

.app-theme-switch__track-icon--sun {
  color: var(--ui-text-muted);
}

.app-theme-switch__track-icon--moon {
  color: var(--ui-accent-strong);
  opacity: 0.5;
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
  border: 1px solid var(--ui-border-subtle);
  background: var(--ui-surface-raised);
  color: var(--ui-text-secondary);
  box-shadow: var(--ui-shadow-sm);
  transition:
    transform 220ms ease,
    background 220ms ease,
    color 220ms ease,
    border-color 220ms ease,
    box-shadow 220ms ease;
}

.app-theme-switch--dark .app-theme-switch__label {
  color: var(--ui-text-secondary);
}

.app-theme-switch--dark .app-theme-switch__track {
  background: var(--ui-surface-2);
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.18);
}

.app-theme-switch--dark .app-theme-switch__track-icon--sun {
  color: var(--ui-text-muted);
  opacity: 0.38;
}

.app-theme-switch--dark .app-theme-switch__track-icon--moon {
  color: var(--ui-accent-strong);
  opacity: 1;
}

.app-theme-switch--dark .app-theme-switch__thumb {
  transform: translateX(36px);
  border-color: rgba(127, 151, 186, 0.28);
  background: var(--ui-accent-soft);
  color: var(--ui-accent-strong);
  box-shadow: var(--ui-shadow-sm);
}

.app-nav-group-title {
  margin-bottom: 0.75rem;
  padding-left: 0.5rem;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--sidebar-text-muted);
  white-space: nowrap;
  overflow: hidden;
}

.app-nav-button {
  position: relative;
  overflow: hidden;
  width: 100%;
  border: 1px solid transparent;
  border-radius: 0.75rem;
  background: transparent;
  text-align: left;
  white-space: nowrap;
  transition:
    color 220ms ease,
    background-color 220ms ease,
    border-color 220ms ease;
}

.app-nav-button--idle {
  color: var(--sidebar-text-soft);
}

.app-nav-button--idle:hover {
  color: var(--sidebar-text);
  background: var(--sidebar-hover-bg);
}

.app-nav-button--active {
  color: var(--sidebar-text);
  background: var(--sidebar-active-bg);
  border-color: var(--sidebar-border);
  font-weight: 600;
}

.app-nav-button--active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 15%;
  width: 3px;
  height: 70%;
  border-radius: 0 9999px 9999px 0;
  background: var(--sidebar-indicator);
}

.app-nav-button--disabled {
  color: var(--sidebar-text-soft);
  opacity: 0.5;
  cursor: not-allowed;
}

.app-nav-button--disabled:hover {
  color: var(--sidebar-text-soft);
  background: transparent;
}

.app-sidebar__footer {
  position: relative;
  border-top: 1px solid var(--sidebar-border);
}

.app-sidebar-theme {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  border: 1px solid var(--sidebar-border);
  border-radius: 9999px;
  background: var(--ui-surface-2);
  padding: 0.5rem;
  box-shadow: var(--ui-shadow-sm);
  transition: background-color 220ms ease, border-color 220ms ease, box-shadow 220ms ease;
}

.app-sidebar-zoom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-top: 0.75rem;
  border: 1px solid var(--sidebar-border);
  border-radius: 9999px;
  background: var(--ui-surface-2);
  padding: 0.5rem;
  box-shadow: var(--ui-shadow-sm);
}

.app-sidebar-theme__label {
  padding-left: 0.45rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--sidebar-text-soft);
  white-space: nowrap;
}

.app-sidebar-theme__actions,
.app-sidebar-zoom__actions,
.app-sidebar-zoom-collapsed {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  border-radius: 9999px;
  background: var(--ui-surface-3);
  padding: 0.25rem;
}

.app-sidebar-zoom-collapsed {
  margin-top: 0.75rem;
  justify-content: center;
}

.app-sidebar-theme__option {
  display: inline-flex;
  height: 2rem;
  width: 2rem;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  border: 1px solid transparent;
  color: var(--sidebar-text-muted);
  cursor: pointer;
  transition: background-color 220ms ease, color 220ms ease, box-shadow 220ms ease, border-color 220ms ease;
}

.app-sidebar-zoom__button,
.app-sidebar-zoom__value {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 2rem;
  min-width: 2rem;
  border-radius: 9999px;
  border: 1px solid transparent;
  color: var(--sidebar-text-muted);
  cursor: pointer;
  transition: background-color 220ms ease, color 220ms ease, box-shadow 220ms ease, border-color 220ms ease;
}

.app-sidebar-zoom__value {
  min-width: 3.6rem;
  padding: 0 0.7rem;
  font-size: 0.78rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.app-sidebar-zoom__value--compact {
  min-width: 2.7rem;
  padding: 0 0.45rem;
}

.app-sidebar-theme__option:hover {
  color: var(--sidebar-text);
  background: var(--ui-surface-raised);
  border-color: var(--ui-border-subtle);
}

.app-sidebar-zoom__button:hover,
.app-sidebar-zoom__value:hover {
  color: var(--sidebar-text);
  background: var(--ui-surface-raised);
  border-color: var(--ui-border-subtle);
}

.app-sidebar-theme__option--active {
  background: var(--sidebar-text);
  color: var(--sidebar-bg);
  box-shadow: var(--ui-shadow-sm);
}

.app-sidebar-zoom__button:disabled,
.app-sidebar-zoom__value:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.app-sidebar-theme-collapsed {
  display: flex;
  height: 2.5rem;
  width: 2.5rem;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  margin-inline: auto;
}

.app-sidebar--collapsed .app-sidebar__nav {
  padding-left: 0.75rem;
  padding-right: 0.75rem;
}

.app-sidebar--collapsed .app-nav-button {
  padding-left: 0;
  padding-right: 0;
}

.app-sidebar--collapsed .app-nav-button--active::before {
  left: 0;
}

.app-mobile-nav {
  border-top: 1px solid var(--ui-border-default);
  background: var(--ui-surface-floating);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  box-shadow: var(--ui-shadow-md);
}

.app-mobile-tab {
  position: relative;
  transition: color 180ms ease, transform 180ms ease;
}

.app-mobile-tab--active {
  color: var(--ui-accent-strong);
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
  background: var(--ui-accent);
}

.app-mobile-tab--idle {
  color: var(--ui-text-secondary);
}

.app-mobile-tab--idle:hover {
  color: var(--ui-text-primary);
  transform: translateY(-1px);
}

.app-mobile-tab--disabled {
  color: var(--ui-text-muted);
}

.app-nav-drag-preview {
  border: 1px solid var(--ui-border-default);
  background: var(--ui-surface-floating);
  color: var(--ui-text-primary);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 18px 35px rgba(15, 23, 42, 0.24);
  transform-origin: center;
  will-change: transform, top, left;
}

.app-main {
  background: transparent;
  transition: background-color 220ms ease;
}

.app-main--clean {
  background: var(--ui-main-clean-bg);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
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
