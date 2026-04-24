<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { fetchSessionHistory, fetchHistoryQuota, deleteSessionHistory } from '../services/interview'
import type { SessionListItem, HistoryQuota } from '../types'
import { ChevronRight, Inbox, Trash2 } from 'lucide-vue-next'

const router = useRouter()
const list = ref<SessionListItem[]>([])
const loading = ref(true)
const quota = ref<HistoryQuota | null>(null)
const deletingId = ref('')

const styleMap: Record<string, string> = {
  default: '标准',
  strict: '高压',
  friendly: '温和',
  technical_deep: '技术深挖',
  behavioral: '行为面试',
  system_design: '系统设计',
  rapid_fire: '快问快答',
  project_focused: '项目追问',
}

const diffMap: Record<string, string> = {
  junior: '初级',
  mid: '中级',
  senior: '高级',
}

const typeMap: Record<string, string> = {
  technical: '技术面',
  hr: 'HR面',
  manager: '主管面',
}

function formatTime(iso: string | null) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

async function loadHistory() {
  loading.value = true
  try {
    const [sessions, quotaData] = await Promise.all([
      fetchSessionHistory(),
      fetchHistoryQuota().catch(() => null),
    ])
    list.value = sessions
    quota.value = quotaData
  } catch {
    list.value = []
  }
  loading.value = false
}

async function handleDelete(sessionId: string) {
  if (!window.confirm('删除后会真正移除数据库中的面试记录、评估和关联文件，确认删除吗？')) return
  deletingId.value = sessionId
  try {
    const result = await deleteSessionHistory(sessionId)
    list.value = list.value.filter(item => item.session_id !== sessionId)
    if (result.quota) quota.value = result.quota
  } finally {
    deletingId.value = ''
  }
}

onMounted(loadHistory)
</script>

<template>
  <div class="fade-in min-h-full max-w-5xl mx-auto">
    <section class="history-hero ui-card mb-6 p-6">
      <div class="relative z-[1] flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <span class="ui-section-badge">面试历史</span>
          <h2 class="ui-page-title mt-4 text-3xl">面试历史</h2>
          <p class="ui-page-subtitle mt-2 text-sm font-medium">仅保存的面试会出现在这里，历史记录和报告会一直保留，除非你主动删除。</p>
        </div>
        <div v-if="quota" class="history-quota">
          <p class="history-quota__label">已保存</p>
          <p class="history-quota__value">{{ quota.saved_count }}</p>
          <p v-if="quota.remaining != null" class="history-quota__sub">剩余 {{ quota.remaining }} 条可用额度</p>
        </div>
      </div>
    </section>

    <div v-if="loading" class="ui-empty-state py-20 text-center text-slate-400 dark:text-white/40">加载中...</div>

    <div v-else-if="!list.length" class="ui-empty-state py-20 text-center">
      <Inbox class="mx-auto mb-3 h-12 w-12 text-slate-300 dark:text-white/20" />
      <p class="text-sm text-slate-400 dark:text-white/40">暂无面试记录，结束面试时选择“保存并生成报告”后会显示在这里。</p>
    </div>

    <div v-else class="space-y-3">
      <div v-for="s in list" :key="s.session_id" class="history-card ui-card ui-card-interactive flex items-center gap-4">
        <button
          type="button"
          class="group flex min-w-0 flex-1 items-center gap-4 text-left"
          @click="router.push(`/history/${s.session_id}`)"
        >
          <div class="min-w-0 flex-1">
            <div class="mb-1 flex items-center gap-2">
              <span class="truncate text-sm font-bold text-slate-800 dark:text-white/90">{{ s.position || '未知岗位' }}</span>
              <span
                class="ui-badge inline-block shrink-0"
                :class="s.status === 'completed'
                  ? 'ui-badge-success'
                  : 'ui-badge-warning'"
              >
                {{ s.status === 'completed' ? '已完成' : '进行中' }}
              </span>
            </div>
            <div class="flex flex-wrap items-center gap-2 text-xs text-slate-400 dark:text-white/40">
              <span v-if="styleMap[s.interview_style || '']">{{ styleMap[s.interview_style || ''] }}</span>
              <span
                v-if="s.metadata?.type && typeMap[s.metadata.type]"
                class="ui-badge ui-badge-info"
              >
                {{ typeMap[s.metadata.type] }}
              </span>
              <span
                v-if="s.metadata?.diff && diffMap[s.metadata.diff]"
                class="ui-badge ui-badge-purple"
              >
                {{ diffMap[s.metadata.diff] }}
              </span>
              <span v-if="s.start_time">{{ formatTime(s.start_time) }}</span>
            </div>
          </div>
          <ChevronRight class="h-4 w-4 shrink-0 text-slate-300 transition-colors group-hover:text-primary dark:text-white/20" />
        </button>

        <button
          type="button"
          class="history-delete ui-btn ui-btn-danger h-11 w-11 shrink-0 px-0 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="deletingId === s.session_id"
          @click="handleDelete(s.session_id)"
        >
          <Trash2 class="h-4 w-4" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
@reference "tailwindcss";

.history-card {
  padding: 1rem 1.1rem;
}

.history-hero {
  position: relative;
  overflow: hidden;
}

.history-hero::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 14% 20%, rgba(56, 189, 248, 0.12), transparent 28%),
    radial-gradient(circle at 88% 18%, rgba(244, 114, 182, 0.08), transparent 22%);
  pointer-events: none;
}

.history-quota {
  min-width: 160px;
  border-radius: 1.25rem;
  border: 1px solid rgba(255, 255, 255, 0.55);
  background: rgba(255, 255, 255, 0.66);
  padding: 0.95rem 1rem;
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.history-quota__label {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #94a3b8;
}

.history-quota__value {
  margin-top: 0.55rem;
  font-size: 1.9rem;
  line-height: 1;
  font-weight: 900;
  color: #0f172a;
}

.history-quota__sub {
  margin-top: 0.35rem;
  font-size: 0.78rem;
  color: #64748b;
}

.history-delete {
  border-radius: 1rem;
}

:where(.dark) .history-quota {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
}

:where(.dark) .history-quota__value {
  color: rgba(255, 255, 255, 0.96);
}

:where(.dark) .history-quota__sub {
  color: #94a3b8;
}
</style>
