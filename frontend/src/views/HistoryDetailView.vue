<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchSessionDetail } from '../services/interview'
import { useInterviewStore } from '../stores/interview'
import type { SessionDetail } from '../types'
import ChatMessage from '../components/ChatMessage.vue'
import ScoreCircle from '../components/ScoreCircle.vue'
import RetryInterviewDialog from '../components/RetryInterviewDialog.vue'
import CatLoading from '../components/CatLoading.vue'
import { ArrowLeft, Briefcase, Clock, BarChart3, RotateCcw, FileBarChart } from 'lucide-vue-next'

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
const showRetryDialog = ref(false)

// 历史简历文件名（弹窗展示用）
const resumeFileName = ref('')

async function openRetryDialog() {
  if (!detail.value) return
  // 预拉取简历文件名
  try {
    const sessionId = route.params.sessionId as string
    const resume = await import('../services/interview').then(m => m.fetchSessionResume(sessionId))
    resumeFileName.value = resume?.file_name || '历史简历'
  } catch {
    resumeFileName.value = '历史简历'
  }
  showRetryDialog.value = true
}

async function handleRetryConfirm(choice: 'keep' | 'upload', file?: File) {
  showRetryDialog.value = false
  retrying.value = true
  try {
    const sessionId = route.params.sessionId as string
    await interview.applyHistoryConfig(sessionId, detail.value!.session, choice === 'upload')
    if (choice === 'upload' && file) {
      interview.config.resumeFile = file
    }
    await interview.startInterview()
    router.push('/interview')
  } catch (e: any) {
    alert('面试启动失败：' + (e.message || '请确保后端已启动'))
  } finally {
    retrying.value = false
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
    <!-- 再面一次加载遮罩 -->
    <CatLoading
      v-if="retrying"
      message="正在唤醒 AI 面试官，解析简历中喵~"
      :thinking-text="interview.thinkingText"
      :stage="interview.thinkingStage"
    />
    <!-- 顶部返回 -->
    <button @click="router.push('/history')"
      class="inline-flex items-center gap-1.5 text-sm text-slate-500 dark:text-white/50 hover:text-primary dark:hover:text-indigo-300 transition-colors mb-4">
      <ArrowLeft class="w-4 h-4" /> 返回历史列表
    </button>

    <div v-if="loading" class="text-center py-20 text-slate-400 dark:text-white/40">加载中...</div>
    <div v-else-if="error" class="text-center py-20 text-red-500">{{ error }}</div>
    <template v-else-if="detail">
      <!-- 元信息卡片 -->
      <div class="meta-card mb-6">
        <div class="flex flex-wrap items-center gap-3">
          <div class="flex items-center gap-2">
            <Briefcase class="w-4 h-4 text-primary" />
            <span class="font-bold text-slate-800 dark:text-white/90">{{ detail.session.position || '未知岗位' }}</span>
          </div>
          <span v-if="detail.session.interview_style"
            class="ui-badge ui-badge-subtle">
            {{ detail.session.interview_style }}
          </span>
          <span v-if="detail.session.metadata?.type && typeMap[detail.session.metadata.type]"
            class="ui-badge ui-badge-info">
            {{ typeMap[detail.session.metadata.type] }}
          </span>
          <span v-if="detail.session.metadata?.diff && diffMap[detail.session.metadata.diff]"
            class="ui-badge ui-badge-info">
            {{ diffMap[detail.session.metadata.diff] }}
          </span>
          <span v-if="detail.session.metadata?.vad"
            class="ui-badge ui-badge-info">
            语音检测
          </span>
          <span v-if="detail.session.metadata?.deep"
            class="ui-badge ui-badge-subtle">
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
          class="flex flex-col items-center gap-1 p-3 rounded-2xl bg-white/70 dark:bg-white/5 border border-slate-100 dark:border-white/5">
          <ScoreCircle :score="ev.score" />
          <span class="text-xs font-medium text-slate-600 dark:text-white/60">{{ ev.dimension }}</span>
          <span v-if="ev.comment && !ev.comment.includes('待 AI')" class="text-[10px] text-slate-400 dark:text-white/30 text-center leading-tight">{{ ev.comment }}</span>
        </div>
      </div>

      <!-- 查看评估报告 -->
      <div v-if="detail.stats?.evaluations?.length" class="mb-6 text-center">
        <button @click="router.push(`/report/${route.params.sessionId}`)"
          class="ui-btn ui-btn-primary px-6 py-2.5 text-sm font-medium">
          <FileBarChart class="w-4 h-4" /> 查看完整评估报告
        </button>
      </div>

      <!-- 对话回放 -->
      <div class="space-y-4">
        <ChatMessage v-for="(m, i) in messages" :key="i" :role="m.role" :content="m.content" />
      </div>
      <div v-if="!messages.length" class="text-center py-10 text-slate-400 dark:text-white/40">暂无对话记录</div>

      <!-- 再面一次 -->
      <div class="mt-8 text-center">
        <button @click="openRetryDialog" :disabled="retrying"
          class="ui-btn ui-btn-primary px-6 py-2.5 text-sm font-medium disabled:opacity-50">
          <RotateCcw class="w-4 h-4" :class="{ 'animate-spin': retrying }" />
          {{ retrying ? '启动面试中...' : '再面一次' }}
        </button>
        <p class="mt-2 text-xs text-slate-400 dark:text-white/30">选择简历后直接进入面试房间</p>
      </div>

      <!-- 再面一次弹窗 -->
      <RetryInterviewDialog
        :visible="showRetryDialog"
        :file-name="resumeFileName"
        @confirm="handleRetryConfirm"
        @cancel="showRetryDialog = false"
      />
    </template>
  </div>
</template>

<style scoped>
@reference "tailwindcss";

.meta-card {
  @apply p-4 rounded-2xl border;
  background: rgba(255, 255, 255, 0.82);
  border-color: rgba(148, 163, 184, 0.28);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  box-shadow: 0 10px 32px rgba(15, 23, 42, 0.08);
}
:where(.dark) .meta-card {
  background: #1A1A24;
  border-color: rgba(255, 255, 255, 0.1);
}
</style>
