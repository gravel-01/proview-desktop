<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useCareerPlanningStore } from '../../stores/careerPlanning'
import type {
  CareerDocRecommendation,
  CareerMarkDocReadPayload,
  CareerPlanningDocument,
} from '../../types/career-planning'

const props = defineProps<{
  documents: CareerPlanningDocument[]
  loading: boolean
  error: string
}>()

const emit = defineEmits<{
  (e: 'retry'): void
  (e: 'open-doc', payload: { docId: string; sectionIdx: number }): void
  // Phase 4: 把 jumpToSection 函数下发给父页面（用于资源闭环下钻）
  (e: 'register-jump', fn: (docId: string, sectionIdx: number) => void): void
}>()

const store = useCareerPlanningStore()

// 状态管理
const activeDocId = ref('')
const activeSectionIdx = ref(0)
const searchQuery = ref('')
const selectedCategory = ref<string>('全部')
const favoriteOnly = ref(false)

// 用户交互状态（本地存储 + 后端双写）
const favoriteIds = ref<Set<string>>(new Set())
const readProgress = ref<Record<string, number>>({})
const readHistory = ref<Record<string, string>>({})
// 阶段四：后端返回的「为你推荐」section 列表（来自 dashboard）
const recommendedSections = ref<CareerDocRecommendation[]>([])
// 阶段四：阅读事件正在持久化时的乐观更新标记
const pendingEventDocIds = ref<Set<string>>(new Set())
const markReadError = ref('')

// 从 localStorage 加载用户状态（向后兼容：旧用户的阅读进度保留在 localStorage）
watch(() => props.documents, (documents) => {
  if (!documents.length) return

  // 加载收藏状态
  const savedFavorites = localStorage.getItem('career_doc_favorites')
  if (savedFavorites) {
    try {
      favoriteIds.value = new Set(JSON.parse(savedFavorites))
    } catch {
      favoriteIds.value = new Set()
    }
  }

  // 加载阅读进度
  const savedProgress = localStorage.getItem('career_doc_progress')
  if (savedProgress) {
    try {
      readProgress.value = JSON.parse(savedProgress)
    } catch {
      readProgress.value = {}
    }
  }

  // 加载阅读历史
  const savedHistory = localStorage.getItem('career_doc_history')
  if (savedHistory) {
    try {
      readHistory.value = JSON.parse(savedHistory)
    } catch {
      readHistory.value = {}
    }
  }

  // 后端 favorite_doc_ids 覆盖 localStorage（权威源）
  if (store.favoriteDocIds?.length) {
    favoriteIds.value = new Set(store.favoriteDocIds)
    localStorage.setItem('career_doc_favorites', JSON.stringify([...favoriteIds.value]))
  }

  // 设置默认选中的文档
  if (!activeDocId.value || !documents.some((doc) => doc.id === activeDocId.value)) {
    activeDocId.value = documents[0]?.id || ''
  }
}, { immediate: true })

onMounted(() => {
  // 取一次后端的 favorites，确保与 localStorage 同步
  store.refreshFavorites().catch(() => {/* 静默失败 */})
  // Phase 4: 暴露 jumpToSection 给父页面（资源闭环下钻）
  emit('register-jump', (docId, sectionIdx) => {
    jumpToSection(docId, sectionIdx)
  })
})

// 同步 store 中的 favorites / recommendations → 本地 ref
watch(() => store.favoriteDocIds, (ids) => {
  if (Array.isArray(ids)) {
    favoriteIds.value = new Set(ids)
    localStorage.setItem('career_doc_favorites', JSON.stringify(ids))
  }
}, { deep: true })

watch(() => store.docRecommendations, (recs) => {
  if (Array.isArray(recs)) {
    recommendedSections.value = recs
  }
}, { immediate: true, deep: true })

// 获取所有分类
const categories = computed(() => {
  const cats = ['全部', '求职攻略', '进阶技巧', '职业发展']
  return cats
})

// 筛选后的文档列表
const filteredDocuments = computed(() => {
  let docs = props.documents

  // 分类筛选
  if (selectedCategory.value !== '全部') {
    docs = docs.filter(doc => doc.category === selectedCategory.value)
  }

  // 收藏筛选
  if (favoriteOnly.value) {
    docs = docs.filter(doc => favoriteIds.value.has(doc.id))
  }

  // 搜索筛选
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase()
    docs = docs.filter(doc =>
      doc.title.toLowerCase().includes(query) ||
      doc.subtitle.toLowerCase().includes(query) ||
      doc.summary.toLowerCase().includes(query) ||
      doc.tags.some(tag => tag.toLowerCase().includes(query))
    )
  }

  return docs
})

watch(filteredDocuments, (documents) => {
  if (!documents.length) {
    activeDocId.value = ''
    return
  }

  if (!documents.some((doc) => doc.id === activeDocId.value)) {
    activeDocId.value = documents[0]?.id || ''
  }
}, { immediate: true })

// 当前激活的文档
const activeDocument = computed(() =>
  props.documents.find(doc => doc.id === activeDocId.value) || null
)

// 阶段四：基于 profile 的 section 推荐（来自 dashboard 内嵌的 doc_recommendations）
const relevantRecommendations = computed(() => recommendedSections.value)

// 阶段四：兜底推荐（tags 相似度），仅在 server-side 推荐为空时使用
const fallbackRecommendations = computed(() => {
  if (!activeDocument.value || relevantRecommendations.value.length > 0) return []
  const activeTags = new Set(activeDocument.value.tags)
  return props.documents
    .filter(doc => doc.id !== activeDocId.value)
    .map(doc => ({
      ...doc,
      matchScore: doc.tags.filter(tag => activeTags.has(tag)).length
    }))
    .sort((a, b) => b.matchScore - a.matchScore)
    .slice(0, 2)
})

// 阶段四：切换文档时定位到指定 section，并滚动到锚点
function jumpToSection(docId: string, sectionIdx: number) {
  activeDocId.value = docId
  const idx = Math.max(0, sectionIdx || 0)
  activeSectionIdx.value = idx
  emit('open-doc', { docId, sectionIdx: idx })
  // 等待 DOM 更新后滚动到目标 section 锚点
  nextTick(() => {
    const targetId = `doc-section-${docId}-${idx}`
    const el = document.getElementById(targetId)
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  })
}

// 收藏功能（localStorage + 后端 toggle）
async function toggleFavorite(docId: string) {
  // 乐观更新
  if (favoriteIds.value.has(docId)) {
    favoriteIds.value.delete(docId)
  } else {
    favoriteIds.value.add(docId)
  }
  favoriteIds.value = new Set(favoriteIds.value)
  localStorage.setItem('career_doc_favorites', JSON.stringify([...favoriteIds.value]))
  try {
    await store.toggleDocFavorite(docId)
  } catch (err) {
    // 失败时回滚
    if (favoriteIds.value.has(docId)) {
      favoriteIds.value.delete(docId)
    } else {
      favoriteIds.value.add(docId)
    }
    favoriteIds.value = new Set(favoriteIds.value)
    localStorage.setItem('career_doc_favorites', JSON.stringify([...favoriteIds.value]))
  }
}

// 阶段四：阅读事件 → 后端 POST /progress
async function reportReadEvent(payload: CareerMarkDocReadPayload) {
  markReadError.value = ''
  if (pendingEventDocIds.value.has(payload.doc_id)) return
  pendingEventDocIds.value.add(payload.doc_id)
  try {
    await store.markDocRead(payload)
  } catch (err) {
    markReadError.value = err instanceof Error ? err.message : '记录阅读进度失败'
  } finally {
    pendingEventDocIds.value.delete(payload.doc_id)
  }
}

// 阶段四：标记 section 已读 → 触发后端持久化 + 任务进度推进
function markSectionCompleted(docId: string, sectionIdx: number, taskId?: number) {
  readProgress.value[docId] = Math.max(readProgress.value[docId] || 0, Math.round(((sectionIdx + 1) / Math.max(1, activeDocument.value?.sections.length || 1)) * 100))
  readHistory.value[docId] = new Date().toISOString()
  localStorage.setItem('career_doc_progress', JSON.stringify(readProgress.value))
  localStorage.setItem('career_doc_history', JSON.stringify(readHistory.value))
  reportReadEvent({
    doc_id: docId,
    section_idx: sectionIdx,
    read_seconds: 0,
    completed: true,
    task_id: taskId,
  })
}

// 阅读进度（localStorage：兜底；后端 completed 只由显式标记触发）
function updateProgress(docId: string, progress: number) {
  readProgress.value[docId] = progress
  readHistory.value[docId] = new Date().toISOString()
  localStorage.setItem('career_doc_progress', JSON.stringify(readProgress.value))
  localStorage.setItem('career_doc_history', JSON.stringify(readHistory.value))
}

watch(activeDocument, (document) => {
  if (!document) return
  if (typeof readProgress.value[document.id] !== 'number') {
    updateProgress(document.id, 0)
  }
}, { immediate: true })

// 分享功能
function shareDocument(doc: CareerPlanningDocument) {
  const shareData = {
    title: `${doc.title} - ProView AI Interviewer`,
    text: doc.summary,
    url: window.location.href
  }

  if (navigator.share) {
    navigator.share(shareData).catch(() => {
      copyToClipboard(shareData.url)
    })
  } else {
    copyToClipboard(`${shareData.title}\n${shareData.text}\n${shareData.url}`)
  }
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text).then(() => {
    alert('链接已复制到剪贴板')
  })
}

// 获取难度颜色
function getDifficultyColor(difficulty: string) {
  const colors: Record<string, string> = {
    '入门': 'border border-slate-200 bg-white text-slate-600 dark:border-white/10 dark:bg-white/10 dark:text-slate-300',
    '进阶': 'border border-slate-200 bg-white text-slate-600 dark:border-white/10 dark:bg-white/10 dark:text-slate-300',
    '中级': 'border border-slate-200 bg-white text-slate-600 dark:border-white/10 dark:bg-white/10 dark:text-slate-300',
    '高级': 'border border-slate-200 bg-white text-slate-600 dark:border-white/10 dark:bg-white/10 dark:text-slate-300'
  }
  return colors[difficulty] || colors['入门']
}

// 获取分类图标
function getCategoryIcon(icon: string) {
  const icons: Record<string, string> = {
    'book-open': '📚',
    'cpu': '🤖',
    'map': '🗺️',
    'graduation-cap': '🎓',
    'trending-up': '📈',
    'bot': '💬'
  }
  return icons[icon] || '📄'
}

// 阶段四：阅读状态徽标
function readStateLabel(rec?: CareerDocRecommendation) {
  if (!rec) return ''
  if (rec.read_state === 'completed') return '已读'
  if (rec.read_state === 'in_progress') return '阅读中'
  return '未读'
}

function readStateClass(rec?: CareerDocRecommendation) {
  const state = rec?.read_state
  if (state === 'completed') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/15 dark:text-emerald-200'
  }
  if (state === 'in_progress') {
    return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/15 dark:text-amber-200'
  }
  return 'border-slate-200 bg-slate-50 text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300'
}
</script>

<template>
  <section class="rounded-3xl border border-slate-200/85 bg-white/90 p-6 shadow-[0_18px_48px_rgba(15,23,42,0.08)] dark:border-white/10 dark:bg-[#0C0F17]/90">
    <!-- 顶部标题区 -->
    <div class="mb-6 flex items-start justify-between gap-4">
      <div>
        <h2 class="text-2xl font-black text-slate-900 dark:text-white">学习中心</h2>
        <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">
          求职必读指南，AI面试技巧，职业发展路径
        </p>
      </div>
      <div class="flex items-center gap-2">
        <span class="rounded-full border border-slate-200 bg-white/80 px-3 py-1 text-xs font-semibold text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
          {{ filteredDocuments.length }} 篇精选内容
        </span>
      </div>
    </div>

    <!-- 文档类别快捷入口 - 横向长卡片 -->
    <div class="mb-6 grid gap-3 sm:grid-cols-3">
      <div
        v-for="doc in filteredDocuments"
        :key="doc.id"
        @click="activeDocId = doc.id"
        class="group cursor-pointer rounded-2xl border p-4 transition-all duration-200"
        :class="activeDocument?.id === doc.id
          ? 'border-indigo-300 bg-sky-50/84 shadow-[0_14px_30px_rgba(79,70,229,0.12)] dark:border-indigo-400/40 dark:bg-indigo-500/14 dark:shadow-none'
          : 'border-slate-200/90 bg-white/85 hover:border-indigo-300 hover:shadow-[0_14px_30px_rgba(79,70,229,0.1)] dark:border-white/10 dark:bg-white/5 dark:hover:border-indigo-500/30'"
      >
        <div class="flex items-start gap-3">
          <div
            class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-2xl shadow-sm dark:border-white/10 dark:bg-white/10"
          >
            {{ getCategoryIcon(doc.cover_icon) }}
          </div>
          <div class="min-w-0 flex-1">
            <h3 class="font-bold text-slate-900 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400">
              {{ doc.title }}
            </h3>
            <p class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              {{ doc.subtitle }}
            </p>
          </div>
        </div>
        <!-- 简介内容 -->
        <p class="mt-3 text-xs text-slate-600 dark:text-slate-400 line-clamp-2 leading-relaxed">
          {{ doc.summary }}
        </p>
        <!-- 标签信息 -->
        <div class="mt-3 flex flex-wrap items-center gap-2">
          <span 
            class="rounded-full px-2 py-0.5 text-[10px] font-semibold"
            :class="getDifficultyColor(doc.difficulty)"
          >
            {{ doc.difficulty }}
          </span>
          <span class="flex items-center gap-1 text-[10px] text-slate-400">
            <span>⏱️</span>
            <span>{{ doc.read_time }}分钟</span>
          </span>
          <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-white/10 dark:text-slate-300">
            {{ doc.category }}
          </span>
        </div>
        <!-- 收藏按钮 -->
        <div class="mt-3 flex items-center justify-between">
          <div class="flex flex-wrap gap-1">
            <span
              v-for="tag in doc.tags.slice(0, 3)"
              :key="tag"
              class="rounded-full bg-indigo-50 px-1.5 py-0.5 text-[9px] font-medium text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300"
            >
              {{ tag }}
            </span>
          </div>
          <button
            @click.stop="toggleFavorite(doc.id)"
            class="shrink-0 rounded-full p-1.5 transition hover:bg-rose-100 dark:hover:bg-rose-500/20"
            :class="favoriteIds.has(doc.id) ? 'text-rose-500' : 'text-slate-300 hover:text-rose-500'"
          >
            {{ favoriteIds.has(doc.id) ? '❤️' : '🤍' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 搜索和筛选栏 -->
    <div class="mb-6 flex flex-wrap items-center gap-3">
      <!-- 搜索框 -->
      <div class="relative flex-1 min-w-[200px]">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索文档..."
          class="w-full rounded-xl border border-slate-200/90 bg-white/85 px-4 py-2.5 pl-10 text-sm text-slate-900 placeholder-slate-400 transition focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100 dark:border-white/10 dark:bg-white/5 dark:text-white dark:placeholder-slate-500"
        />
        <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">🔍</span>
      </div>

      <!-- 分类标签 -->
      <div class="flex flex-wrap gap-2">
        <button
          v-for="cat in categories"
          :key="cat"
          @click="selectedCategory = cat"
          class="rounded-full px-4 py-1.5 text-xs font-semibold transition"
          :class="selectedCategory === cat
            ? 'border border-indigo-300 bg-sky-50 text-indigo-900 dark:border-indigo-400/40 dark:bg-indigo-500/14 dark:text-white'
            : 'border border-slate-200 bg-white/80 text-slate-600 hover:bg-slate-100 dark:border-white/10 dark:bg-white/10 dark:text-slate-300'"
        >
          {{ cat }}
        </button>
      </div>
      
      <!-- 收藏筛选 -->
      <button
        @click="favoriteOnly = !favoriteOnly"
        class="flex items-center gap-1.5 rounded-full px-4 py-1.5 text-xs font-semibold transition"
        :class="favoriteOnly 
          ? 'border border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-400/40 dark:bg-rose-500/15 dark:text-rose-200' 
          : 'border border-slate-200 bg-white/80 text-slate-600 hover:bg-slate-100 dark:border-white/10 dark:bg-white/10 dark:text-slate-300'"
      >
        <span>❤️</span>
        <span>我的收藏</span>
      </button>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="flex items-center justify-center py-12">
      <div class="h-8 w-8 animate-spin rounded-full border-3 border-indigo-200 border-t-indigo-600"></div>
      <span class="ml-3 text-sm text-slate-500">正在加载文档库...</span>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="rounded-xl border border-rose-200 bg-rose-50 p-5 text-center dark:border-rose-500/30 dark:bg-rose-500/10">
      <p class="font-semibold text-rose-700 dark:text-rose-200">{{ error }}</p>
      <button
        @click="$emit('retry')"
        class="mt-3 rounded-lg bg-rose-500 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-600"
      >
        重试
      </button>
    </div>

    <!-- 阶段四：为你推荐 section 区（来自 dashboard.doc_recommendations） -->
    <div
      v-if="!loading && !error && relevantRecommendations.length"
      class="mb-6 rounded-2xl border border-indigo-200/80 bg-indigo-50/40 p-4 dark:border-indigo-500/30 dark:bg-indigo-500/10"
    >
      <div class="mb-3 flex items-center justify-between">
        <h3 class="text-sm font-bold text-indigo-700 dark:text-indigo-200">
          🎯 为你推荐的章节
        </h3>
        <span class="text-[10px] text-indigo-500/80">基于你的 gap &amp; 任务类型</span>
      </div>
      <div class="grid gap-2 sm:grid-cols-2">
        <button
          v-for="rec in relevantRecommendations"
          :key="`${rec.doc_id}-${rec.section_idx}`"
          @click="jumpToSection(rec.doc_id, rec.section_idx)"
          class="group flex flex-col items-start gap-2 rounded-xl border border-white/60 bg-white/80 p-3 text-left shadow-sm transition hover:border-indigo-300 hover:shadow-md dark:border-white/10 dark:bg-white/5"
        >
          <div class="flex w-full items-center justify-between gap-2">
            <span class="truncate text-sm font-semibold text-slate-900 dark:text-white">
              {{ rec.section_heading }}
            </span>
            <span
              class="shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium"
              :class="readStateClass(rec)"
            >
              {{ readStateLabel(rec) }}
            </span>
          </div>
          <span class="truncate text-[11px] text-slate-500 dark:text-slate-400">
            {{ rec.doc_title }} · 匹配分 {{ rec.score.toFixed(2) }}
          </span>
          <span class="line-clamp-2 text-xs text-slate-600 dark:text-slate-300">
            {{ rec.reason }}
          </span>
        </button>
      </div>
      <p v-if="markReadError" class="mt-2 text-[11px] text-rose-500">{{ markReadError }}</p>
    </div>

    <!-- 主内容区 - 文档详情展开区域 -->
    <div v-if="activeDocument" class="space-y-4">
      <!-- 文档详情卡片 -->
      <div 
        class="overflow-hidden rounded-2xl border border-slate-200/85 bg-white shadow-[0_18px_48px_rgba(15,23,42,0.08)] dark:border-white/10 dark:bg-[#0C0F17]"
      >
        <!-- 详情头部 -->
        <div class="relative border-b border-slate-200/85 bg-[linear-gradient(180deg,rgba(255,255,255,0.9)_0%,rgba(248,250,252,0.9)_100%)] p-5 text-slate-900 dark:border-white/10 dark:bg-[linear-gradient(180deg,rgba(10,10,15,0.92)_0%,rgba(12,15,23,0.94)_100%)] dark:text-white">
          <div class="absolute -right-6 -top-6 h-28 w-28 rounded-full bg-indigo-200/25 dark:bg-indigo-400/10"></div>
          <div class="relative">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-bold text-slate-700 dark:border-white/10 dark:bg-white/10 dark:text-slate-200">
                  {{ activeDocument.difficulty }}
                </span>
                <span class="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                  ⏱️ {{ activeDocument.read_time }}分钟阅读
                </span>
              </div>
              <div class="flex items-center gap-2">
                <button
                  @click="toggleFavorite(activeDocument.id)"
                  class="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 backdrop-blur-sm transition hover:border-rose-300 hover:text-rose-600 dark:border-white/10 dark:bg-white/10 dark:text-slate-200 dark:hover:border-rose-400/40 dark:hover:text-rose-300"
                >
                  {{ favoriteIds.has(activeDocument.id) ? '已收藏' : '收藏' }}
                </button>
                <button
                  @click="shareDocument(activeDocument)"
                  class="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 backdrop-blur-sm transition hover:border-indigo-300 hover:text-indigo-600 dark:border-white/10 dark:bg-white/10 dark:text-slate-200 dark:hover:border-indigo-400/40 dark:hover:text-indigo-300"
                >
                  分享
                </button>
              </div>
            </div>
            
            <h2 class="mt-3 text-xl font-black">{{ activeDocument.title }}</h2>
            <p class="mt-1 text-sm text-slate-600 dark:text-slate-400">{{ activeDocument.subtitle }}</p>
            
            <!-- 标签 -->
            <div class="mt-3 flex flex-wrap gap-2">
              <span 
                v-for="tag in activeDocument.tags" 
                :key="tag"
                class="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-xs font-medium text-slate-600 dark:border-white/10 dark:bg-white/10 dark:text-slate-300"
              >
                {{ tag }}
              </span>
            </div>
          </div>
        </div>

        <!-- 文档内容 -->
        <div class="p-5 space-y-5">
          <div
            v-for="(section, sectionIdx) in activeDocument.sections"
            :key="section.heading"
            :id="`doc-section-${activeDocument.id}-${sectionIdx}`"
            :class="activeSectionIdx === sectionIdx ? 'rounded-xl ring-2 ring-indigo-200 dark:ring-indigo-500/40 p-3' : ''"
          >
            <div class="flex items-center justify-between gap-3">
              <h3 class="text-base font-bold text-slate-900 dark:text-white">{{ section.heading }}</h3>
              <!-- 阶段四：标记章节已读按钮 -->
              <button
                @click="markSectionCompleted(activeDocument.id, sectionIdx)"
                class="shrink-0 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-semibold text-emerald-700 transition hover:bg-emerald-100 dark:border-emerald-500/30 dark:bg-emerald-500/15 dark:text-emerald-200"
              >
                ✅ 标记本节已读
              </button>
            </div>

            <div class="mt-2 space-y-2">
              <p
                v-for="(para, pIdx) in section.paragraphs"
                :key="pIdx"
                class="text-sm leading-relaxed text-slate-600 dark:text-slate-300"
              >
                {{ para }}
              </p>
            </div>

            <!-- 要点列表 -->
            <ul v-if="section.bullets?.length" class="mt-3 space-y-1.5">
              <li
                v-for="(bullet, bIdx) in section.bullets"
                :key="bIdx"
                class="flex items-start gap-2.5 text-sm text-slate-600 dark:text-slate-300"
              >
                <span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-500"></span>
                <span>{{ bullet }}</span>
              </li>
            </ul>

            <!-- 行动项 -->
            <div
              v-if="section.action_items?.length"
              class="mt-3 rounded-xl bg-indigo-50 p-3 dark:bg-indigo-500/10"
            >
              <h4 class="flex items-center gap-2 text-sm font-bold text-indigo-700 dark:text-indigo-300">
                <span>立即行动</span>
              </h4>
              <ul class="mt-2 space-y-1">
                <li
                  v-for="(item, iIdx) in section.action_items"
                  :key="iIdx"
                  class="flex items-start gap-2 text-sm text-indigo-600 dark:text-indigo-400"
                >
                  <span class="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400"></span>
                  <span>{{ item }}</span>
                </li>
              </ul>
            </div>
          </div>
        </div>

        <!-- 相关推荐 -->
        <div v-if="fallbackRecommendations.length > 0" class="border-t border-slate-200/80 p-4 dark:border-white/10">
          <h4 class="mb-3 flex items-center gap-2 text-sm font-bold text-slate-700 dark:text-slate-200">
            <span>相关推荐</span>
          </h4>
          <div class="grid gap-2 sm:grid-cols-2">
            <div
              v-for="doc in fallbackRecommendations"
              :key="doc.id"
              @click="activeDocId = doc.id"
              class="flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3 transition hover:border-indigo-300 hover:bg-indigo-50/50 dark:border-white/10 dark:bg-white/5 dark:hover:border-indigo-500/30"
            >
              <div
                class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-lg dark:border-white/10 dark:bg-white/10"
              >
                {{ getCategoryIcon(doc.cover_icon) }}
              </div>
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-semibold text-slate-900 dark:text-white">{{ doc.title }}</p>
                <p class="text-xs text-slate-500">{{ doc.difficulty }} · {{ doc.read_time }}分钟</p>
              </div>
              <span class="text-slate-400">→</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 无选中文档时的提示 -->
    <div 
      v-else
      class="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-slate-50/50 py-12 dark:border-slate-600 dark:bg-white/5"
    >
      <p class="text-4xl">📚</p>
      <p class="mt-3 text-sm text-slate-500 dark:text-slate-400">
        {{ filteredDocuments.length ? '点击上方文档卡片查看详情' : '没有符合当前筛选条件的文档' }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.line-clamp-1 {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
