<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { CareerPlanningDocument } from '../../types/career-planning'

const props = defineProps<{
  documents: CareerPlanningDocument[]
  loading: boolean
  error: string
}>()

// 状态管理
const activeDocId = ref('')
const searchQuery = ref('')
const selectedCategory = ref<string>('全部')
const favoriteOnly = ref(false)

// 用户交互状态（本地存储）
const favoriteIds = ref<Set<string>>(new Set())
const readProgress = ref<Record<string, number>>({})
const readHistory = ref<Record<string, string>>({})

// 从 localStorage 加载用户状态
watch(() => props.documents, (documents) => {
  if (!documents.length) return
  
  // 加载收藏状态
  const savedFavorites = localStorage.getItem('career_doc_favorites')
  if (savedFavorites) {
    favoriteIds.value = new Set(JSON.parse(savedFavorites))
  }
  
  // 加载阅读进度
  const savedProgress = localStorage.getItem('career_doc_progress')
  if (savedProgress) {
    readProgress.value = JSON.parse(savedProgress)
  }
  
  // 加载阅读历史
  const savedHistory = localStorage.getItem('career_doc_history')
  if (savedHistory) {
    readHistory.value = JSON.parse(savedHistory)
  }
  
  // 设置默认选中的文档
  if (!activeDocId.value || !documents.some((doc) => doc.id === activeDocId.value)) {
    activeDocId.value = documents[0]?.id || ''
  }
}, { immediate: true })

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

type DocTheme = {
  cardBg: string
  cardBgActive: string
  border: string
  borderActive: string
  accent: string
  accentSoftBg: string
  title: string
  subtitle: string
  tagBg: string
  tagBorder: string
  tagText: string
  bullet: string
}

const docThemes: DocTheme[] = [
  {
    cardBg: 'linear-gradient(135deg, rgba(224,242,254,0.55) 0%, rgba(255,255,255,0.92) 60%, rgba(219,234,254,0.35) 100%)',
    cardBgActive: 'linear-gradient(135deg, rgba(224,242,254,0.75) 0%, rgba(255,255,255,0.95) 55%, rgba(219,234,254,0.55) 100%)',
    border: 'rgba(191,219,254,0.55)',
    borderActive: 'rgba(147,197,253,0.9)',
    accent: '#2563eb',
    accentSoftBg: 'rgba(224,242,254,0.55)',
    title: '#1e3a8a',
    subtitle: 'rgba(30,64,175,0.75)',
    tagBg: 'rgba(255,255,255,0.72)',
    tagBorder: 'rgba(191,219,254,0.9)',
    tagText: '#1e40af',
    bullet: '#3b82f6',
  },
  {
    cardBg: 'linear-gradient(135deg, rgba(219,234,254,0.55) 0%, rgba(255,255,255,0.92) 60%, rgba(224,242,254,0.35) 100%)',
    cardBgActive: 'linear-gradient(135deg, rgba(219,234,254,0.78) 0%, rgba(255,255,255,0.95) 55%, rgba(224,242,254,0.55) 100%)',
    border: 'rgba(191,219,254,0.55)',
    borderActive: 'rgba(147,197,253,0.9)',
    accent: '#1d4ed8',
    accentSoftBg: 'rgba(219,234,254,0.5)',
    title: '#1e3a8a',
    subtitle: 'rgba(30,58,138,0.72)',
    tagBg: 'rgba(255,255,255,0.72)',
    tagBorder: 'rgba(191,219,254,0.9)',
    tagText: '#1e3a8a',
    bullet: '#2563eb',
  },
  {
    cardBg: 'linear-gradient(135deg, rgba(248,250,252,0.95) 0%, rgba(255,255,255,0.92) 55%, rgba(224,242,254,0.28) 100%)',
    cardBgActive: 'linear-gradient(135deg, rgba(248,250,252,0.98) 0%, rgba(255,255,255,0.95) 50%, rgba(224,242,254,0.45) 100%)',
    border: 'rgba(226,232,240,0.9)',
    borderActive: 'rgba(147,197,253,0.75)',
    accent: '#0ea5e9',
    accentSoftBg: 'rgba(224,242,254,0.45)',
    title: '#0f172a',
    subtitle: 'rgba(30,41,59,0.7)',
    tagBg: 'rgba(255,255,255,0.75)',
    tagBorder: 'rgba(226,232,240,0.95)',
    tagText: '#1e40af',
    bullet: '#0ea5e9',
  },
  {
    cardBg: 'linear-gradient(135deg, rgba(239,246,255,0.95) 0%, rgba(255,255,255,0.92) 58%, rgba(248,250,252,0.6) 100%)',
    cardBgActive: 'linear-gradient(135deg, rgba(239,246,255,0.98) 0%, rgba(255,255,255,0.95) 52%, rgba(248,250,252,0.75) 100%)',
    border: 'rgba(203,213,225,0.75)',
    borderActive: 'rgba(147,197,253,0.75)',
    accent: '#3b82f6',
    accentSoftBg: 'rgba(239,246,255,0.7)',
    title: '#1e3a8a',
    subtitle: 'rgba(30,64,175,0.72)',
    tagBg: 'rgba(255,255,255,0.75)',
    tagBorder: 'rgba(203,213,225,0.85)',
    tagText: '#1e40af',
    bullet: '#3b82f6',
  },
]

function themeIndexForId(id: string) {
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0
  return h % docThemes.length
}

function themeForDoc(doc: CareerPlanningDocument) {
  return docThemes[themeIndexForId(doc.id)]
}

const activeTheme = computed<DocTheme>(() => {
  if (!activeDocument.value) return docThemes[0]
  return themeForDoc(activeDocument.value)
})

// 推荐文档（基于标签相似度）
const recommendedDocs = computed(() => {
  if (!activeDocument.value) return []
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

// 收藏功能
function toggleFavorite(docId: string) {
  if (favoriteIds.value.has(docId)) {
    favoriteIds.value.delete(docId)
  } else {
    favoriteIds.value.add(docId)
  }
  favoriteIds.value = new Set(favoriteIds.value)
  localStorage.setItem('career_doc_favorites', JSON.stringify([...favoriteIds.value]))
}

// 更新阅读进度
function updateProgress(docId: string, progress: number) {
  readProgress.value[docId] = progress
  readHistory.value[docId] = new Date().toISOString()
  localStorage.setItem('career_doc_progress', JSON.stringify(readProgress.value))
  localStorage.setItem('career_doc_history', JSON.stringify(readHistory.value))
}

watch(activeDocument, (document) => {
  if (!document) return
  const currentProgress = readProgress.value[document.id] || 0
  updateProgress(document.id, Math.max(currentProgress, 100))
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
    '入门': 'ui-badge-info',
    '进阶': 'ui-badge-info',
    '中级': 'ui-badge-subtle',
    '高级': 'ui-badge-subtle'
  }
  return `ui-badge ${colors[difficulty] || colors['入门']}`
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
</script>

<template>
  <section class="ui-card rounded-3xl p-6">
    <!-- 顶部标题区 -->
    <div class="mb-6 flex items-start justify-between gap-4">
      <div>
        <h2 class="text-2xl font-black text-slate-900 dark:text-white">📚 学习中心</h2>
        <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">
          求职必读指南，AI面试技巧，职业发展路径
        </p>
      </div>
      <div class="flex items-center gap-2">
        <span class="ui-badge ui-badge-info px-3 py-1 text-xs">
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
        class="group cursor-pointer rounded-2xl border-2 p-4 transition-all duration-200"
        :style="{
          background: activeDocument?.id === doc.id ? themeForDoc(doc).cardBgActive : themeForDoc(doc).cardBg,
          borderColor: activeDocument?.id === doc.id ? themeForDoc(doc).borderActive : themeForDoc(doc).border,
        }"
        :class="activeDocument?.id === doc.id
          ? 'shadow-[0_10px_26px_rgba(59,130,246,0.10)] dark:shadow-none'
          : 'hover:shadow-md dark:bg-[#0B1220]'"
      >
        <div class="flex items-start gap-3">
          <div
            class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-2xl shadow-sm"
            :style="{
              background: themeForDoc(doc).accentSoftBg,
              color: themeForDoc(doc).accent,
            }"
          >
            {{ getCategoryIcon(doc.cover_icon) }}
          </div>
          <div class="min-w-0 flex-1">
            <h3
              class="font-bold dark:text-white"
              :style="{ color: themeForDoc(doc).title }"
            >
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
          <span :class="getDifficultyColor(doc.difficulty)">
            {{ doc.difficulty }}
          </span>
          <span class="flex items-center gap-1 text-[10px] text-slate-400">
            <span>⏱️</span>
            <span>{{ doc.read_time }}分钟</span>
          </span>
          <span class="ui-badge ui-badge-subtle">
            {{ doc.category }}
          </span>
        </div>
        <!-- 收藏按钮 -->
        <div class="mt-3 flex items-center justify-between">
          <div class="flex flex-wrap gap-1">
            <span
              v-for="tag in doc.tags.slice(0, 3)"
              :key="tag"
              class="ui-badge"
              :style="{
                background: themeForDoc(doc).tagBg,
                borderColor: themeForDoc(doc).tagBorder,
                color: themeForDoc(doc).tagText,
              }"
            >
              {{ tag }}
            </span>
          </div>
          <button
            @click.stop="toggleFavorite(doc.id)"
            class="shrink-0 rounded-full p-1.5 transition hover:bg-sky-50 dark:hover:bg-blue-500/20"
            :class="favoriteIds.has(doc.id) ? 'text-blue-500' : 'text-slate-300 hover:text-blue-500'"
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
          class="ui-input pl-10 px-4 py-2.5 text-sm placeholder-slate-400 dark:placeholder-slate-500"
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
            ? 'ui-btn-primary text-white' 
            : 'bg-white text-slate-600 border border-gray-200 hover:bg-sky-50 dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-blue-500/15'"
        >
          {{ cat }}
        </button>
      </div>
      
      <!-- 收藏筛选 -->
      <button
        @click="favoriteOnly = !favoriteOnly"
        class="flex items-center gap-1.5 rounded-full px-4 py-1.5 text-xs font-semibold transition"
        :class="favoriteOnly
          ? 'bg-sky-50 text-blue-700 border border-blue-200 dark:border-blue-400/40 dark:bg-blue-500/15 dark:text-blue-200'
          : 'bg-white text-slate-600 border border-gray-200 hover:bg-sky-50 dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-blue-500/15'"
      >
        <span>❤️</span>
        <span>我的收藏</span>
      </button>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="flex items-center justify-center py-12">
      <div class="h-8 w-8 animate-spin rounded-full border-3 border-blue-200 border-t-blue-600"></div>
      <span class="ml-3 text-sm text-slate-500 dark:text-slate-400">正在加载文档库...</span>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="ui-card-soft rounded-xl border-blue-200 bg-sky-50 p-5 text-center dark:border-blue-500/30 dark:bg-blue-500/10">
      <p class="font-semibold text-blue-700 dark:text-blue-200">{{ error }}</p>
      <button 
        @click="$emit('retry')"
        class="ui-btn ui-btn-primary mt-3 px-4 py-2 text-sm font-semibold"
      >
        重试
      </button>
    </div>

    <!-- 主内容区 - 文档详情展开区域 -->
    <div v-if="activeDocument" class="space-y-4">
      <!-- 文档详情卡片 -->
      <div
        class="ui-card overflow-hidden rounded-2xl border-2 shadow-lg"
        :style="{ borderColor: activeTheme.border }"
      >
        <!-- 详情头部 -->
        <div 
          class="relative p-5"
          :style="{
            color: activeTheme.title,
            background: activeTheme.cardBgActive,
          }"
        >
          <div class="absolute -right-6 -top-6 h-28 w-28 rounded-full bg-white/10 dark:bg-white/5"></div>
          <div class="relative">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span
                  class="ui-badge bg-white/70 dark:bg-white/10"
                  :style="{
                    borderColor: activeTheme.tagBorder,
                    color: activeTheme.tagText,
                  }"
                >
                  {{ activeDocument.difficulty }}
                </span>
                <span class="flex items-center gap-1 text-xs" :style="{ color: activeTheme.subtitle }">
                  ⏱️ {{ activeDocument.read_time }}分钟阅读
                </span>
              </div>
              <div class="flex items-center gap-2">
                <button
                  @click="toggleFavorite(activeDocument.id)"
                  class="ui-badge flex items-center gap-1.5 bg-white/70 px-3 py-1.5 text-xs font-semibold backdrop-blur-sm transition hover:bg-white dark:bg-white/10 dark:hover:bg-white/15"
                  :style="{ borderColor: activeTheme.tagBorder, color: activeTheme.tagText }"
                >
                  {{ favoriteIds.has(activeDocument.id) ? '❤️ 已收藏' : '🤍 收藏' }}
                </button>
                <button
                  @click="shareDocument(activeDocument)"
                  class="ui-badge flex items-center gap-1.5 bg-white/70 px-3 py-1.5 text-xs font-semibold backdrop-blur-sm transition hover:bg-white dark:bg-white/10 dark:hover:bg-white/15"
                  :style="{ borderColor: activeTheme.tagBorder, color: activeTheme.tagText }"
                >
                  📤 分享
                </button>
              </div>
            </div>
            
            <h2 class="mt-3 text-xl font-black">{{ activeDocument.title }}</h2>
            <p class="mt-1 text-sm" :style="{ color: activeTheme.subtitle }">{{ activeDocument.subtitle }}</p>
            
            <!-- 标签 -->
            <div class="mt-3 flex flex-wrap gap-2">
              <span
                v-for="tag in activeDocument.tags" 
                :key="tag"
                class="ui-badge bg-white/70 backdrop-blur-sm dark:bg-white/10"
                :style="{
                  borderColor: activeTheme.tagBorder,
                  color: activeTheme.tagText,
                }"
              >
                {{ tag }}
              </span>
            </div>
          </div>
        </div>

        <!-- 文档内容 -->
        <div class="p-5 space-y-5">
          <div 
            v-for="(section) in activeDocument.sections" 
            :key="section.heading"
          >
            <h3 class="text-base font-bold text-slate-900 dark:text-white">{{ section.heading }}</h3>
            
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
                <span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" :style="{ background: activeTheme.bullet }"></span>
                <span>{{ bullet }}</span>
              </li>
            </ul>

            <!-- 行动项 -->
            <div 
              v-if="section.action_items?.length" 
              class="mt-3 rounded-xl p-3"
              :style="{ background: activeTheme.accentSoftBg }"
            >
              <h4 class="flex items-center gap-2 text-sm font-bold" :style="{ color: activeTheme.tagText }">
                <span>🎯</span>
                <span>立即行动</span>
              </h4>
              <ul class="mt-2 space-y-1">
                <li 
                  v-for="(item, iIdx) in section.action_items" 
                  :key="iIdx"
                  class="flex items-start gap-2 text-sm"
                  :style="{ color: activeTheme.subtitle }"
                >
                  <span class="mt-1 h-1.5 w-1.5 shrink-0 rounded-full" :style="{ background: activeTheme.bullet }"></span>
                  <span>{{ item }}</span>
                </li>
              </ul>
            </div>
          </div>
        </div>

        <!-- 相关推荐 -->
        <div v-if="recommendedDocs.length > 0" class="border-t border-slate-200/80 p-4 dark:border-white/10">
          <h4 class="mb-3 flex items-center gap-2 text-sm font-bold text-slate-700 dark:text-slate-200">
            <span>📖</span>
            <span>相关推荐</span>
          </h4>
          <div class="grid gap-2 sm:grid-cols-2">
            <div
              v-for="doc in recommendedDocs"
              :key="doc.id"
              @click="activeDocId = doc.id"
              class="ui-card-soft flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3 transition hover:border-blue-300 hover:bg-sky-50/60 dark:border-white/10 dark:bg-white/5 dark:hover:border-blue-500/30"
            >
              <div
                class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-lg"
                :style="{
                  background: themeForDoc(doc).accentSoftBg,
                  color: themeForDoc(doc).accent,
                }"
              >
                {{ getCategoryIcon(doc.cover_icon) }}
              </div>
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-semibold text-slate-900 dark:text-white">{{ doc.title }}</p>
                <p class="text-xs text-slate-500 dark:text-slate-400">{{ doc.difficulty }} · {{ doc.read_time }}分钟</p>
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
