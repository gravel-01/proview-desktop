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
  <div class="fade-in min-h-full max-w-4xl mx-auto">
    <div class="mb-6">
      <h2 class="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl dark:text-white">面试历史</h2>
      <p class="mt-2 text-sm font-medium text-slate-500 dark:text-slate-400">仅保存的面试会出现在这里，你最多可保留 15 条历史记录。</p>
      <p v-if="quota" class="mt-2 text-sm text-primary">已保存 {{ quota.saved_count }}/{{ quota.max_saved }}，剩余 {{ quota.remaining }} 条可用额度</p>
    </div>

    <div v-if="loading" class="py-20 text-center text-slate-400 dark:text-white/40">加载中...</div>

    <div v-else-if="!list.length" class="py-20 text-center">
      <Inbox class="mx-auto mb-3 h-12 w-12 text-slate-300 dark:text-white/20" />
      <p class="text-sm text-slate-400 dark:text-white/40">暂无面试记录，结束面试时选择“保存并生成报告”后会显示在这里。</p>
    </div>

    <div v-else class="space-y-3">
      <div v-for="s in list" :key="s.session_id" class="history-card flex items-center gap-4">
        <button
          type="button"
          class="group flex min-w-0 flex-1 items-center gap-4 text-left"
          @click="router.push(`/history/${s.session_id}`)"
        >
          <div class="min-w-0 flex-1">
            <div class="mb-1 flex items-center gap-2">
              <span class="truncate text-sm font-bold text-slate-800 dark:text-white/90">{{ s.position || '未知岗位' }}</span>
              <span
                class="inline-block shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium"
                :class="s.status === 'completed'
                  ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                  : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'"
              >
                {{ s.status === 'completed' ? '已完成' : '进行中' }}
              </span>
            </div>
            <div class="flex flex-wrap items-center gap-2 text-xs text-slate-400 dark:text-white/40">
              <span v-if="styleMap[s.interview_style || '']">{{ styleMap[s.interview_style || ''] }}</span>
              <span
                v-if="s.metadata?.type && typeMap[s.metadata.type]"
                class="rounded-full bg-blue-50 px-1.5 py-0.5 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400"
              >
                {{ typeMap[s.metadata.type] }}
              </span>
              <span
                v-if="s.metadata?.diff && diffMap[s.metadata.diff]"
                class="rounded-full bg-purple-50 px-1.5 py-0.5 text-purple-600 dark:bg-purple-900/20 dark:text-purple-400"
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
          class="ui-btn ui-btn-danger inline-flex h-10 w-10 shrink-0 items-center justify-center p-0 disabled:cursor-not-allowed disabled:opacity-50"
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
  @apply rounded-2xl border p-4 transition-all;
  background: rgba(255, 255, 255, 0.82);
  border-color: rgba(148, 163, 184, 0.28);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  box-shadow: 0 10px 32px rgba(15, 23, 42, 0.08);
}

.history-card:hover {
  border-color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 3%, white);
}

:where(.dark) .history-card {
  background: #1A1A24;
  border-color: rgba(255, 255, 255, 0.1);
}

:where(.dark) .history-card:hover {
  border-color: color-mix(in srgb, var(--color-primary) 60%, transparent);
  background: rgba(255, 255, 255, 0.03);
}
</style>
