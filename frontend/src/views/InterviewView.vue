<script lang="ts">
export default { name: 'InterviewView' }
</script>

<script setup lang="ts">
import { ref, onMounted, onActivated } from 'vue'
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
const endError = ref('')

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
}

function closeEndDialog() {
  showEndDialog.value = false
  endError.value = ''
  if (store.canEnterInterviewRoom) {
    aiViz.value?.startTimer()
  }
}

async function confirmEnd(saveHistory: boolean) {
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
      <div class="w-full max-w-lg rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl dark:border-white/10 dark:bg-[#11131c]">
        <h3 class="text-xl font-bold text-slate-900 dark:text-white">结束面试</h3>
        <p class="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
          你可以选择保存本次面试历史，保存后才会生成评估报告；如果不保存，本次对话和报告都会被释放，不占用数据库空间。
        </p>

        <div class="mt-4 rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600 dark:bg-white/5 dark:text-slate-300">
          保存本次面试后会继续生成评估报告并跳转到报告页；不保存则直接结束本次面试，不保留报告内容。
        </div>

        <p v-if="endError" class="mt-3 text-sm text-rose-500">{{ endError }}</p>

        <div class="mt-6 flex flex-col gap-3 sm:flex-row">
          <button
            type="button"
            class="flex-1 rounded-2xl border border-slate-200 px-4 py-3 text-sm font-medium text-slate-600 transition hover:bg-slate-50 dark:border-white/10 dark:text-slate-200 dark:hover:bg-white/5"
            @click="closeEndDialog"
          >
            继续面试
          </button>
          <button
            type="button"
            class="flex-1 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-700 transition hover:bg-amber-100 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-300"
            @click="confirmEnd(false)"
          >
            不保存，直接结束
          </button>
          <button
            type="button"
            class="flex-1 rounded-2xl bg-primary px-4 py-3 text-sm font-medium text-white transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
            @click="confirmEnd(true)"
          >
            保存并生成报告
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
