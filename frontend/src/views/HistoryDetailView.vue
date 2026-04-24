<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchSessionDetail, fetchSessionResume } from '../services/interview'
import { useInterviewStore } from '../stores/interview'
import type { SessionDetail } from '../types'
import ChatMessage from '../components/ChatMessage.vue'
import ScoreCircle from '../components/ScoreCircle.vue'
import RetryInterviewDialog from '../components/RetryInterviewDialog.vue'
import CatLoading from '../components/CatLoading.vue'
import { ArrowLeft, Briefcase, Clock, BarChart3, RotateCcw, FileBarChart } from 'lucide-vue-next'
import { isReusableOcrText } from '../utils/ocr'

const route = useRoute()
const router = useRouter()
const interview = useInterviewStore()
const detail = ref<SessionDetail | null>(null)
const loading = ref(true)
const error = ref('')

const messages = computed(() => {
  if (!detail.value) return []
  return detail.value.messages.map(m => ({
    role: (m.role === 'assistant' ? 'ai' : 'user') as 'user' | 'ai',
    content: m.content,
  }))
})

function formatDuration(start: string | null, end: string | null) {
  if (!start || !end) return ''
  const ms = new Date(end).getTime() - new Date(start).getTime()
  const min = Math.floor(ms / 60000)
  return `${min} 分钟`
}

const diffMap: Record<string, string> = {
  junior: '初级', mid: '中级', senior: '高级',
}
const typeMap: Record<string, string> = {
  technical: '技术面', hr: 'HR面', manager: '主管面',
}

const retrying = ref(false)
const retryMode = ref<'keep' | 'upload' | null>(null)
const showRetryDialog = ref(false)
const retryStageText = computed(() => interview.thinkingStage || '正在复用历史配置并唤醒 AI 面试官...')
const retryLoadingMessage = computed(() => (
  retryMode.value === 'upload'
    ? '正在上传并解析新简历，唤醒 AI 面试官...'
    : '正在复用历史配置并唤醒 AI 面试官...'
))

// 历史简历文件名（弹窗展示用）
const resumeFileName = ref('')
const canKeepResume = ref(false)

async function openRetryDialog() {
  if (!detail.value) return
  // 预拉取简历文件名
  try {
    const sessionId = route.params.sessionId as string
    const resume = await fetchSessionResume(sessionId)
    canKeepResume.value = isReusableOcrText(resume?.ocr_result || '')
    resumeFileName.value = resume?.file_name || '历史简历'
  } catch {
    canKeepResume.value = false
    resumeFileName.value = '历史简历'
  }
  showRetryDialog.value = true
}

async function handleRetryConfirm(choice: 'keep' | 'upload', file?: File) {
  showRetryDialog.value = false
  retryMode.value = choice
  retrying.value = true
  try {
    const sessionId = route.params.sessionId as string
    await interview.applyHistoryConfig(sessionId, detail.value!.session, choice === 'upload')
    if (choice === 'upload' && file) {
      interview.setUploadedResume(file)
    }
    await interview.startInterview()
    router.push('/interview')
  } catch (e: any) {
    alert('面试启动失败：' + (e.message || '请确保后端已启动'))
  } finally {
    retrying.value = false
    retryMode.value = null
  }
}

onMounted(async () => {
  try {
    detail.value = await fetchSessionDetail(route.params.sessionId as string)
  } catch {
    error.value = '加载失败，该面试记录可能不存在'
  }
  loading.value = false
})
</script>

<template>
  <div class="fade-in min-h-full max-w-4xl mx-auto pb-10">
    <!-- 再面一次局部加载提示 -->
    <CatLoading
      v-if="retrying"
      variant="corner"
      :message="retryLoadingMessage"
      :thinking-text="interview.thinkingText"
      :stage="retryStageText"
    />
    <!-- 顶部返回 -->
    <button @click="router.push('/history')"
      :disabled="retrying"
      class="ui-btn ui-btn-secondary mb-4 px-4 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-60">
      <ArrowLeft class="w-4 h-4" /> 返回历史列表
    </button>

    <div v-if="loading" class="ui-empty-state text-center py-20 text-slate-400 dark:text-white/40">加载中...</div>
    <div v-else-if="error" class="ui-empty-state text-center py-20 text-red-500">{{ error }}</div>
    <template v-else-if="detail">
      <!-- 元信息卡片 -->
      <div class="detail-hero meta-card ui-card mb-6">
        <div class="flex flex-wrap items-center gap-3">
          <div class="flex items-center gap-2">
            <Briefcase class="w-4 h-4 text-primary" />
            <span class="font-bold text-slate-800 dark:text-white/90">{{ detail.session.position || '未知岗位' }}</span>
          </div>
          <span v-if="detail.session.interview_style"
            class="ui-badge">
            {{ detail.session.interview_style }}
          </span>
          <span v-if="detail.session.metadata?.type && typeMap[detail.session.metadata.type]"
            class="ui-badge ui-badge-info">
            {{ typeMap[detail.session.metadata.type] }}
          </span>
          <span v-if="detail.session.metadata?.diff && diffMap[detail.session.metadata.diff]"
            class="ui-badge ui-badge-purple">
            {{ diffMap[detail.session.metadata.diff] }}
          </span>
          <span v-if="detail.session.metadata?.vad"
            class="ui-badge ui-badge-success">
            语音检测
          </span>
          <span v-if="detail.session.metadata?.deep"
            class="ui-badge ui-badge-warning">
            深度追问
          </span>
          <div v-if="detail.session.start_time" class="flex items-center gap-1.5 text-sm text-slate-500 dark:text-white/50">
            <Clock class="w-3.5 h-3.5" />
            {{ formatDuration(detail.session.start_time, detail.session.end_time) }}
          </div>
          <div v-if="detail.stats?.avg_score" class="flex items-center gap-1.5 text-sm text-slate-500 dark:text-white/50">
            <BarChart3 class="w-3.5 h-3.5" />
            均分 {{ detail.stats.avg_score.toFixed(1) }}
          </div>
        </div>
      </div>

      <!-- 评分维度 -->
      <div v-if="detail.stats?.evaluations?.length" class="mb-6 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
        <div v-for="ev in detail.stats.evaluations" :key="ev.dimension"
          class="detail-score-card flex flex-col items-center gap-1 p-3 rounded-2xl">
          <ScoreCircle :score="ev.score" />
          <span class="text-xs font-medium text-slate-600 dark:text-white/60">{{ ev.dimension }}</span>
          <span v-if="ev.comment && !ev.comment.includes('待 AI')" class="text-[10px] text-slate-400 dark:text-white/30 text-center leading-tight">{{ ev.comment }}</span>
        </div>
      </div>

      <!-- 查看评估报告 -->
      <div v-if="detail.stats?.evaluations?.length" class="mb-6 text-center">
        <button @click="router.push(`/report/${route.params.sessionId}`)"
          :disabled="retrying"
          class="ui-btn ui-btn-primary px-6 py-2.5 text-sm disabled:cursor-not-allowed disabled:opacity-60">
          <FileBarChart class="w-4 h-4" /> 查看完整评估报告
        </button>
      </div>

      <!-- 对话回放 -->
      <div class="detail-chat-wrap ui-card mb-8 space-y-4 p-4 sm:p-5">
        <ChatMessage v-for="(m, i) in messages" :key="i" :role="m.role" :content="m.content" />
      </div>
      <div v-if="!messages.length" class="ui-empty-state text-center py-10 text-slate-400 dark:text-white/40">暂无对话记录</div>

      <!-- 再面一次 -->
      <div class="detail-retry ui-card mt-8 p-6" :class="{ 'detail-retry--busy': retrying }">
        <button @click="openRetryDialog" :disabled="retrying"
          class="ui-btn ui-btn-primary mx-auto flex px-6 py-2.5 text-sm disabled:opacity-50">
          <RotateCcw class="w-4 h-4" :class="{ 'animate-spin': retrying }" />
          {{ retrying ? '启动面试中...' : '再面一次' }}
        </button>
        <p class="mt-2 text-center text-xs text-slate-400 dark:text-white/30">选择简历后直接进入面试房间</p>

        <div v-if="retrying" class="detail-retry-status">
          <p class="detail-retry-status__title">{{ retryStageText }}</p>
          <p class="detail-retry-status__desc">
            当前页面会保持可见，初始化完成后自动进入面试房间，不再切成整页加载页。
          </p>
          <div v-if="interview.thinkingText" class="detail-retry-thinking custom-scroll">
            {{ interview.thinkingText }}
          </div>
        </div>
      </div>

      <!-- 再面一次弹窗 -->
      <RetryInterviewDialog
        :visible="showRetryDialog"
        :file-name="resumeFileName"
        :can-keep-resume="canKeepResume"
        @confirm="handleRetryConfirm"
        @cancel="showRetryDialog = false"
      />
    </template>
  </div>
</template>

<style scoped>
@reference "tailwindcss";

.meta-card {
  @apply p-5 rounded-[28px];
  position: relative;
  overflow: hidden;
}

.detail-hero::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 14% 20%, rgba(56, 189, 248, 0.12), transparent 28%),
    radial-gradient(circle at 88% 18%, rgba(244, 114, 182, 0.08), transparent 22%);
  pointer-events: none;
}

.detail-score-card {
  border: 1px solid rgba(226, 232, 240, 0.85);
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.04);
}

.detail-chat-wrap {
  position: relative;
}

.detail-retry {
  position: relative;
  overflow: hidden;
}

.detail-retry--busy {
  border-color: rgba(96, 165, 250, 0.28);
  box-shadow:
    0 20px 44px rgba(59, 130, 246, 0.1),
    inset 0 1px 0 rgba(255, 255, 255, 0.52);
}

.detail-retry::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(239, 246, 255, 0.24), rgba(245, 243, 255, 0.2), transparent 70%);
  pointer-events: none;
}

.detail-retry-status {
  position: relative;
  z-index: 1;
  margin-top: 1rem;
  border-radius: 1.25rem;
  border: 1px solid rgba(191, 219, 254, 0.9);
  background: rgba(248, 250, 252, 0.82);
  padding: 1rem;
  text-align: left;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.detail-retry-status__title {
  color: #1d4ed8;
  font-size: 0.92rem;
  font-weight: 700;
}

.detail-retry-status__desc {
  margin-top: 0.35rem;
  color: #64748b;
  font-size: 0.78rem;
  line-height: 1.55;
}

.detail-retry-thinking {
  margin-top: 0.75rem;
  max-height: 10rem;
  overflow-y: auto;
  border-radius: 1rem;
  border: 1px solid rgba(191, 219, 254, 0.85);
  background: rgba(255, 255, 255, 0.72);
  padding: 0.8rem 0.9rem;
  color: #334155;
  font-size: 0.76rem;
  line-height: 1.65;
  white-space: pre-wrap;
}

:where(.dark) .meta-card {
  background: transparent;
}

:where(.dark) .detail-score-card {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
}

:where(.dark) .detail-retry--busy {
  border-color: rgba(96, 165, 250, 0.24);
  box-shadow:
    0 18px 36px rgba(0, 0, 0, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

:where(.dark) .detail-retry-status {
  border-color: rgba(96, 165, 250, 0.2);
  background: rgba(15, 23, 42, 0.46);
}

:where(.dark) .detail-retry-status__title {
  color: #93c5fd;
}

:where(.dark) .detail-retry-status__desc {
  color: rgba(226, 232, 240, 0.68);
}

:where(.dark) .detail-retry-thinking {
  border-color: rgba(96, 165, 250, 0.16);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(226, 232, 240, 0.82);
}
</style>
