<script lang="ts">
export default { name: 'InterviewView' }
</script>

<script setup lang="ts">
import { computed, ref, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { useInterviewStore } from '../stores/interview'
import AiVisualization from '../components/AiVisualization.vue'
import ChatPanel from '../components/ChatPanel.vue'
import CatLoading from '../components/CatLoading.vue'

const router = useRouter()
const store = useInterviewStore()
const aiViz = ref<InstanceType<typeof AiVisualization> | null>(null)
const chatPanel = ref<InstanceType<typeof ChatPanel> | null>(null)
const ending = ref(false)
const endingChoice = ref<'save' | 'discard'>('save')
const showEndDialog = ref(false)
const quotaLoading = ref(false)
const endError = ref('')

const quotaText = computed(() => {
  const quota = store.historyQuota
  if (!quota) return '历史额度加载中'
  return `已保存 ${quota.saved_count}/${quota.max_saved}`
})

const canSaveHistory = computed(() => store.historyQuota?.can_save !== false)

onMounted(async () => {
  if (store.shouldRedirectInterviewToReport) {
    router.replace('/report')
    return
  }

  if (!store.canEnterInterviewRoom) {
    router.replace('/')
    return
  }

  aiViz.value?.startTimer()
})

onActivated(() => {
  if (store.shouldRedirectInterviewToReport) {
    router.replace('/report')
    return
  }

  if (!store.canEnterInterviewRoom) {
    router.replace('/')
    return
  }

  if (store.aiState !== 'idle' && !store.isResponding && !store.isEnding) {
    store.setAiState('idle')
  }
})

async function openEndDialog() {
  chatPanel.value?.stopVoicePlayback()
  aiViz.value?.stopTimer()
  store.setAiState('idle')
  endError.value = ''
  showEndDialog.value = true
  quotaLoading.value = true
  await store.loadHistoryQuota()
  quotaLoading.value = false
}

function closeEndDialog() {
  showEndDialog.value = false
  endError.value = ''
  if (store.canEnterInterviewRoom) {
    aiViz.value?.startTimer()
  }
}

async function confirmEnd(saveHistory: boolean) {
  if (saveHistory && !canSaveHistory.value) return

  ending.value = true
  endingChoice.value = saveHistory ? 'save' : 'discard'
  endError.value = ''

  try {
    const result = await store.endSession(saveHistory)
    showEndDialog.value = false
    if (saveHistory && result?.saved !== false) {
      router.push('/report')
      return
    }
    window.alert(result?.message || '本次面试未保存，评估报告不会生成。')
    router.replace('/')
  } catch (error: any) {
    endError.value = error?.message || '结束面试失败，请稍后重试'
    aiViz.value?.startTimer()
  } finally {
    ending.value = false
  }
}
</script>

<template>
  <div class="relative flex h-[calc(100vh-6rem)] flex-col gap-6 fade-in md:flex-row">
    <CatLoading
      v-if="ending"
      variant="corner"
      :message="endingChoice === 'save' ? '正在保存面试历史并生成评估报告' : '正在结束本次面试'"
      :stage="store.thinkingStage"
      :thinking-text="store.thinkingText"
    />

    <AiVisualization ref="aiViz" @end-interview="openEndDialog" />
    <ChatPanel ref="chatPanel" />

    <div v-if="showEndDialog" class="absolute inset-0 z-30 flex items-center justify-center bg-slate-950/45 px-4">
      <div class="ui-card w-full max-w-lg rounded-3xl p-6 shadow-2xl dark:shadow-black/50">
        <h3 class="text-xl font-bold text-slate-900 dark:text-white">结束面试</h3>
        <p class="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
          你可以选择保存本次面试历史，保存后才会生成评估报告；如果不保存，本次对话和报告都会被释放，不占用数据库空间。
        </p>

        <div class="ui-card-soft mt-4 rounded-2xl px-4 py-3 text-sm text-slate-600 dark:text-slate-300">
          <span v-if="quotaLoading">正在加载历史额度...</span>
          <span v-else>{{ quotaText }}</span>
          <span v-if="store.historyQuota" class="ml-2 text-slate-400 dark:text-slate-500">
            剩余 {{ store.historyQuota.remaining }} 条
          </span>
        </div>

        <p v-if="!quotaLoading && !canSaveHistory" class="mt-3 text-sm text-rose-500">
          你的面试历史已满 15 条，请先去历史页面删除旧记录，再保存新的面试。
        </p>
        <p v-if="endError" class="mt-3 text-sm text-rose-500">{{ endError }}</p>

        <div class="mt-6 flex flex-col gap-3 sm:flex-row">
          <button
            type="button"
            class="ui-btn ui-btn-secondary flex-1 rounded-2xl px-4 py-3 text-sm font-medium"
            @click="closeEndDialog"
          >
            继续面试
          </button>
          <button
            type="button"
            class="ui-btn ui-btn-danger flex-1 rounded-2xl px-4 py-3 text-sm font-medium"
            @click="confirmEnd(false)"
          >
            不保存，直接结束
          </button>
          <button
            type="button"
            class="ui-btn ui-btn-primary flex-1 rounded-2xl px-4 py-3 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="quotaLoading || !canSaveHistory"
            @click="confirmEnd(true)"
          >
            保存并生成报告
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
