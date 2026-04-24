<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Cpu,
  FileCheck,
  LayoutGrid,
  Layers3,
  Loader,
  Play,
  RefreshCw,
  Upload,
  Volume2,
  X,
} from 'lucide-vue-next'
import { useInterviewStore } from '../stores/interview'
import type { InterviewConfig } from '../types'
import CatLoading from '../components/CatLoading.vue'
import CustomSelect from '../components/CustomSelect.vue'
import JobTagPicker from '../components/JobTagPicker.vue'
import StageDeck from '../components/StageDeck.vue'
import { fetchLatestResume, ttsPreview } from '../services/interview'
import { isReusableOcrText } from '../utils/ocr'

interface ArrangementPreset {
  id: string
  emoji: string
  kicker: string
  label: string
  desc: string
  focus: string
  rhythm: string
  cue: string
  interviewType: InterviewConfig['interviewType']
  difficulty: InterviewConfig['difficulty']
  style: InterviewConfig['style']
}

const router = useRouter()
const store = useInterviewStore()
const loading = computed(() => store.isSettingUp)

const styleOptions = [
  { value: 'default', label: '标准模式', desc: '专业均衡，客观评估', emoji: '📘' },
  { value: 'strict', label: '高压模式', desc: '追问更深，要求更高', emoji: '🎯' },
  { value: 'friendly', label: '温和引导', desc: '更适合练习和热身', emoji: '🌤' },
  { value: 'technical_deep', label: '技术深挖', desc: '关注原理和实现细节', emoji: '🧠' },
  { value: 'behavioral', label: '行为面试', desc: '聚焦经历表达与 STAR', emoji: '🗣' },
  { value: 'system_design', label: '系统设计', desc: '考察架构设计与权衡', emoji: '🏗' },
  { value: 'rapid_fire', label: '快问快答', desc: '强调知识广度和反应速度', emoji: '⚡' },
  { value: 'project_focused', label: '项目追问', desc: '重点深挖项目细节', emoji: '📂' },
] as const

const typeOptions = [
  { value: 'technical', label: '技术面', desc: '代码能力与技术深度', emoji: '💻' },
  { value: 'hr', label: 'HR面', desc: '职业动机与稳定性', emoji: '🤝' },
  { value: 'manager', label: '主管面', desc: '业务理解与协作能力', emoji: '📋' },
] as const

const difficultyOptions = [
  { value: 'junior', label: '初级', desc: '基础概念与常见实践', emoji: '🌱' },
  { value: 'mid', label: '中级', desc: '实战经验与原理理解', emoji: '🚀' },
  { value: 'senior', label: '高级', desc: '架构能力与系统思考', emoji: '🧭' },
] as const

const voiceOptions = [
  { value: 4100, label: '度小雯（臻品女声）' },
  { value: 4117, label: '度小鹿（臻品女声）' },
  { value: 4115, label: '度小贤（臻品男声）' },
  { value: 4003, label: '度逍遥（臻品男声）' },
  { value: 4106, label: '度博文（新闻男声）' },
  { value: 5003, label: '度逍遥（精品男声）' },
  { value: 0, label: '度小美（基础女声）' },
  { value: 1, label: '度小宇（基础男声）' },
]

const fallbackVoiceOption = { value: 4100, label: '度小雯（臻品女声）' }

const speedOptions = [
  { label: '0.5x', spd: 2 },
  { label: '0.75x', spd: 3 },
  { label: '1x', spd: 5 },
  { label: '1.25x', spd: 7 },
  { label: '1.5x', spd: 9 },
  { label: '2x', spd: 12 },
] as const

const modelOptions = [
  { value: 'deepseek', label: 'DeepSeek', desc: '深度求索，代码能力强', emoji: '🧠' },
  { value: 'ernie', label: '文心一言', desc: '百度大模型，中文理解优秀', emoji: '🌐' },
  { value: 'ernie-thinking', label: '文心（深度思考）', desc: '开启思维链，回复更慢但更深入', emoji: '🔮' },
] as const

const interviewPresets: ArrangementPreset[] = [
  {
    id: 'warmup',
    emoji: '🧊',
    kicker: '热身上场',
    label: '轻压热身局',
    desc: '先用温和引导建立节奏，适合刚开始练习表达和破冰。',
    focus: '技术面 + 初级',
    rhythm: '引导式追问',
    cue: '适合首轮准备或快速热身',
    interviewType: 'technical',
    difficulty: 'junior',
    style: 'friendly',
  },
  {
    id: 'deep-dive',
    emoji: '🚀',
    kicker: '核心考察',
    label: '技术深挖局',
    desc: '围绕原理、实现细节和项目拆解追问，强调真实技术深度。',
    focus: '技术面 + 中级',
    rhythm: '连续下钻',
    cue: '更适合验证项目真实性和原理掌握',
    interviewType: 'technical',
    difficulty: 'mid',
    style: 'technical_deep',
  },
  {
    id: 'salary',
    emoji: '💰',
    kicker: '谈薪演练',
    label: '谈薪练习局',
    desc: '围绕薪资、涨幅空间、福利结构和 offer 预期进行表达与博弈练习。',
    focus: 'HR 面 + 中级',
    rhythm: '谈判表达',
    cue: '适合冲刺 offer 阶段前的谈薪表达训练',
    interviewType: 'hr',
    difficulty: 'mid',
    style: 'behavioral',
  },
  {
    id: 'system',
    emoji: '🏗️',
    kicker: '架构压测',
    label: '系统设计局',
    desc: '把场景拉到高阶架构与取舍，考查方案能力和系统化表达。',
    focus: '技术面 + 高级',
    rhythm: '架构权衡',
    cue: '适合准备高级岗或架构岗',
    interviewType: 'technical',
    difficulty: 'senior',
    style: 'system_design',
  },
  {
    id: 'behavior',
    emoji: '🗣️',
    kicker: '表达校准',
    label: '行为表达局',
    desc: '围绕 STAR、稳定性、团队协作和动机表达组织追问。',
    focus: 'HR 面 + 中级',
    rhythm: '故事复盘',
    cue: '适合优化经历讲述和职业动机',
    interviewType: 'hr',
    difficulty: 'mid',
    style: 'behavioral',
  },
  {
    id: 'leadership',
    emoji: '📈',
    kicker: '业务视角',
    label: '主管复盘局',
    desc: '聚焦项目结果、协作推进与业务理解，强调候选人判断力。',
    focus: '主管面 + 高级',
    rhythm: '结果导向',
    cue: '适合冲刺负责人或高级执行岗',
    interviewType: 'manager',
    difficulty: 'senior',
    style: 'project_focused',
  },
]

const PREVIEW_TEXT = '你好，我是你的AI面试官，准备好开始面试了吗？'

const previewPlaying = ref(false)
const previewLoading = ref(false)
const arrangementGridExpanded = ref(false)
const arrangementPanelExpanded = ref(false)
const launchConfigOpen = ref(false)
const launchStepIndex = ref(0)
const preferredArrangementPresetId = ref('')
const resumeInputRef = ref<HTMLInputElement | null>(null)
let launchTouchStartX: number | null = null
let previewAudioCtx: AudioContext | null = null
let previewSource: AudioBufferSourceNode | null = null

const launchSteps = [
  {
    id: 'job-title',
    title: '目标岗位',
    desc: '先确认应聘方向',
  },
  {
    id: 'job-jd',
    title: 'JD 要求',
    desc: '再补充岗位要求',
  },
  {
    id: 'voice',
    title: '语音配置',
    desc: '最后确认音色与语速',
  },
] as const

const currentTypeOption = computed(() => (
  typeOptions.find(item => item.value === store.config.interviewType) || typeOptions[0]
))

const currentDifficultyOption = computed(() => (
  difficultyOptions.find(item => item.value === store.config.difficulty) || difficultyOptions[0]
))

const currentStyleOption = computed(() => (
  styleOptions.find(item => item.value === store.config.style) || styleOptions[0]
))

const currentModelOption = computed(() => (
  modelOptions.find(item => item.value === store.config.modelProvider) || modelOptions[0]
))

const currentVoiceOption = computed(() => (
  voiceOptions.find(item => item.value === store.config.voicePer) || fallbackVoiceOption
))

const currentVoiceLabelCompact = computed(() => currentVoiceOption.value.label.split('（')[0] || currentVoiceOption.value.label)

const isLaunchProfileReady = computed(() => !!store.config.jobTitle.trim())
const hasLaunchJobRequirements = computed(() => !!(store.config.jobRequirements || '').trim())

const launchTrackStyle = computed(() => ({
  transform: `translateX(-${launchStepIndex.value * 100}%)`,
}))

const launchStepSummary = computed(() => {
  if (launchStepIndex.value === 0) {
    return '先确认目标岗位，后面的 JD 和语音配置都会围绕这个岗位展开。'
  }
  if (launchStepIndex.value === 1) {
    return 'JD 要求是可选补充，适合粘贴岗位职责、技术栈、年限和加分项。'
  }
  return `当前将以 ${currentArrangementCard.value.label} 开始，岗位 ${store.config.jobTitle.trim() || '待确认'}，语音 ${currentVoiceLabelCompact.value}。`
})

const arrangementPresetMatches = computed(() => interviewPresets.filter(preset => (
  preset.interviewType === store.config.interviewType
  && preset.difficulty === store.config.difficulty
  && preset.style === store.config.style
)))

const arrangementCards = computed(() => [
  ...interviewPresets,
  {
    id: 'custom',
    emoji: '⚙️',
    kicker: '自由编排',
    label: '当前组合态',
    desc: '当前配置未完全命中预设，继续使用下方精调区就能拼出你自己的面试节奏。',
    focus: `${currentTypeOption.value.label} + ${currentDifficultyOption.value.label}`,
    rhythm: currentStyleOption.value.label,
    cue: '保留所有已有字段与启动逻辑，只重构布局和切换方式',
  },
])

const arrangementFallbackCard = {
  id: 'custom',
  emoji: '⚙️',
  kicker: '自由编排',
  label: '当前组合态',
  desc: '当前配置未完全命中预设，继续使用下方精调区就能拼出你自己的面试节奏。',
  focus: '组合待确认',
  rhythm: '精调中',
  cue: '保留所有已有字段与启动逻辑，只重构布局和切换方式',
}

const arrangementCardId = computed({
  get: () => {
    const matches = arrangementPresetMatches.value
    if (!matches.length) return 'custom'
    if (preferredArrangementPresetId.value && matches.some(item => item.id === preferredArrangementPresetId.value)) {
      return preferredArrangementPresetId.value
    }
    return matches[0]?.id || 'custom'
  },
  set: (value: string) => {
    handleArrangementSelect(value)
  },
})

const currentArrangementCard = computed(() => {
  const matchedId = arrangementCardId.value
  return arrangementCards.value.find(card => card.id === matchedId) || arrangementCards.value[0] || arrangementFallbackCard
})

const hasResumeSelection = computed(() => !!store.config.resumeFile || !!store.config.resumeOcrText)

const shouldShowArrangementDetail = computed(() => (
  arrangementPanelExpanded.value || arrangementCardId.value === 'custom'
))

const resumeStatusLabel = computed(() => {
  if (store.config.resumeFile) return store.config.resumeFile.name
  if (store.config.resumeOcrText) return store.config.resumeFileName || '已接入历史简历'
  return '未接入简历'
})

const confirmSummaryItems = computed(() => [
  { label: '当前模型', value: currentModelOption.value.label },
  { label: '当前编排', value: `${currentTypeOption.value.label} / ${currentDifficultyOption.value.label} / ${currentStyleOption.value.label}` },
  { label: '岗位画像', value: store.config.jobTitle.trim() || '岗位待填写' },
  { label: '简历状态', value: resumeStatusLabel.value },
])

function setStyle(value: string) {
  store.config.style = value as InterviewConfig['style']
}

function handleArrangementSelect(id: string) {
  if (id === 'custom') {
    arrangementPanelExpanded.value = true
    return
  }

  const preset = interviewPresets.find(item => item.id === id)
  if (!preset) return

  preferredArrangementPresetId.value = id
  store.config.interviewType = preset.interviewType
  store.config.difficulty = preset.difficulty
  setStyle(preset.style)
}

function stopPreview() {
  if (previewSource) {
    try { previewSource.stop() } catch { /* already stopped */ }
    previewSource = null
  }
  previewPlaying.value = false
}

function validateLaunchProfile(showAlert = true) {
  if (!store.config.jobTitle.trim()) {
    if (showAlert) alert('请输入目标岗位')
    return false
  }

  return true
}

function isLaunchStepLocked(index: number) {
  return index > 0 && !isLaunchProfileReady.value
}

function setLaunchStep(nextIndex: number, { silent = false }: { silent?: boolean } = {}) {
  const boundedIndex = Math.max(0, Math.min(nextIndex, launchSteps.length - 1))
  if (boundedIndex > 0 && !validateLaunchProfile(!silent)) return false
  if (boundedIndex < launchStepIndex.value) stopPreview()
  launchStepIndex.value = boundedIndex
  return true
}

function nextLaunchStep() {
  if (launchStepIndex.value === 0 && !isLaunchProfileReady.value) return false
  return setLaunchStep(launchStepIndex.value + 1)
}

function prevLaunchStep() {
  return setLaunchStep(launchStepIndex.value - 1, { silent: true })
}

function openLaunchConfig() {
  if (loading.value) return
  launchStepIndex.value = 0
  launchConfigOpen.value = true
}

function closeLaunchConfig() {
  if (loading.value) return
  stopPreview()
  launchStepIndex.value = 0
  launchConfigOpen.value = false
}

function handleLaunchTouchStart(event: TouchEvent) {
  launchTouchStartX = event.changedTouches[0]?.clientX ?? null
}

function handleLaunchTouchEnd(event: TouchEvent) {
  if (launchTouchStartX === null) return
  const endX = event.changedTouches[0]?.clientX ?? launchTouchStartX
  const deltaX = endX - launchTouchStartX
  launchTouchStartX = null

  if (Math.abs(deltaX) < 52) return
  if (deltaX < 0) {
    nextLaunchStep()
    return
  }
  prevLaunchStep()
}

async function playPreview() {
  if (previewPlaying.value) {
    stopPreview()
    return
  }

  previewLoading.value = true
  try {
    const wavBuffer = await ttsPreview(PREVIEW_TEXT, store.config.voicePer, store.config.voiceSpd)
    if (!previewAudioCtx) previewAudioCtx = new AudioContext()
    const audioBuf = await previewAudioCtx.decodeAudioData(wavBuffer)

    stopPreview()
    previewSource = previewAudioCtx.createBufferSource()
    previewSource.buffer = audioBuf
    previewSource.connect(previewAudioCtx.destination)
    previewSource.onended = () => {
      previewPlaying.value = false
    }
    previewSource.start()
    previewPlaying.value = true
  } catch (error) {
    console.error('试听失败:', error)
    alert('语音试听失败，请确保后端已启动')
  } finally {
    previewLoading.value = false
  }
}

function buildStartInterviewErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message.trim() : String(error || '').trim()
  if (!message || message === '[object Object]') {
    return '服务连接失败，请确保 Flask 后端已启动。'
  }
  if (/Failed to fetch|NetworkError|Load failed|ERR_CONNECTION_REFUSED/i.test(message)) {
    return '服务连接失败，请确保 Flask 后端已启动。'
  }
  return `面试启动失败：${message}`
}

async function startInterview() {
  if (!validateLaunchProfile()) {
    launchStepIndex.value = 0
    return
  }

  stopPreview()
  try {
    await store.startInterview()
    launchConfigOpen.value = false
    router.push('/interview')
  } catch (error) {
    alert(buildStartInterviewErrorMessage(error))
  }
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  store.setUploadedResume(input.files?.[0] || null)
}

function triggerResumePicker() {
  if (!resumeInputRef.value) return
  resumeInputRef.value.value = ''
  resumeInputRef.value.click()
}

function replaceResume() {
  if (store.config.resumeOcrText && !store.config.resumeFile) {
    clearHistoryResume()
  }
  triggerResumePicker()
}

function clearHistoryResume() {
  store.clearResumeSelection()
}

onMounted(async () => {
  if (store.config.resumeSelection === 'none') return
  if (store.config.resumeFile || store.config.resumeOcrText) return

  try {
    const resume = await fetchLatestResume()
    const latestOcrText = resume?.ocr_result || ''
    if (isReusableOcrText(latestOcrText)) {
      store.setReusedResume(latestOcrText, {
        fileName: resume?.file_name || '历史简历',
        sourceSessionId: resume?.session_id,
        selection: 'auto-latest',
      })
    }
  } catch {
    // 静默保留原行为
  }
})

onBeforeUnmount(() => {
  stopPreview()
})
</script>

<template>
  <div class="setup-page fade-in min-h-full mx-auto max-w-[1100px]">
    <CatLoading
      v-if="loading"
      variant="corner"
      message="AI 面试官正在准备中"
      :stage="store.thinkingStage"
      :thinking-text="store.thinkingText"
    />

    <form class="setup-form" @submit.prevent="openLaunchConfig">
      <section class="setup-section setup-section--lead">
        <div class="setup-section__head">
          <div class="setup-section__badge">
            <Layers3 class="h-4 w-4" />
            面试编排
          </div>
          <div class="setup-section__actions">
            <span class="setup-section__hint hidden md:inline-block">轮次、难度和面试风格共同决定提问节奏与压迫感。</span>
            <button
              type="button"
              class="setup-section__toggle"
              @click="arrangementGridExpanded = !arrangementGridExpanded"
            >
              <LayoutGrid class="h-3.5 w-3.5" />
              <span>{{ arrangementGridExpanded ? '收起场景' : '展开全部场景' }}</span>
            </button>
          </div>
        </div>

        <div class="setup-surface setup-surface--stage">
          <StageDeck
            v-model="arrangementCardId"
            :expanded="arrangementGridExpanded"
            :items="arrangementCards"
            :card-width="324"
            :card-height="224"
            :card-radius="26"
          >
            <template #card="{ item, active }">
              <div class="setup-scenario-card" :class="item.id === 'custom' ? 'setup-scenario-card--custom' : ''">
                <div v-if="item.id === 'custom'" class="setup-scenario-card__flare" aria-hidden="true"></div>
                <div class="setup-scenario-card__top">
                  <div class="setup-scenario-card__avatar">{{ item.emoji }}</div>
                  <span class="setup-scenario-card__state" :class="active ? 'setup-scenario-card__state--active' : ''">
                    {{ active ? '当前' : item.id === 'custom' ? 'Custom' : 'Preset' }}
                  </span>
                </div>
                <div class="setup-scenario-card__body">
                  <p class="setup-scenario-card__kicker">{{ item.kicker }}</p>
                  <h3 class="setup-scenario-card__title">{{ item.label }}</h3>
                  <p class="setup-scenario-card__desc">{{ item.desc }}</p>
                  <div class="setup-scenario-card__tags">
                    <span class="setup-scenario-card__tag">{{ item.focus }}</span>
                    <span class="setup-scenario-card__tag">{{ item.rhythm }}</span>
                  </div>
                  <div v-if="item.id === 'custom'" class="setup-scenario-card__hint">
                    展开配置面板
                  </div>
                </div>
              </div>
            </template>
          </StageDeck>
        </div>

        <div class="setup-arrangement__selection">
          <div class="setup-arrangement__selection-copy">
            <span class="setup-arrangement__selection-label">当前场景</span>
            <div class="setup-arrangement__selection-main">
              <strong class="setup-arrangement__selection-title">{{ currentArrangementCard.label }}</strong>
              <span class="setup-arrangement__selection-meta">
                {{ currentTypeOption.label }} / {{ currentDifficultyOption.label }} / {{ currentStyleOption.label }}
              </span>
            </div>
          </div>
          <button
            type="button"
            class="setup-inline-toggle"
            @click="arrangementPanelExpanded = !arrangementPanelExpanded"
          >
            <span>{{ shouldShowArrangementDetail ? '收起精调配置' : '展开精调配置' }}</span>
            <ChevronDown class="h-4 w-4 transition-transform" :class="shouldShowArrangementDetail ? 'rotate-180' : ''" />
          </button>
        </div>

        <Transition name="deck-detail">
          <div v-if="shouldShowArrangementDetail" class="setup-arrangement-panel">
            <div class="setup-arrangement-panel__row">
              <div class="setup-arrangement-panel__block setup-arrangement-panel__block--compact">
                <label class="config-label">面试轮次</label>
                <div class="flex flex-wrap gap-2">
                  <button
                    v-for="option in typeOptions"
                    :key="option.value"
                    type="button"
                    class="chip-btn"
                    :class="store.config.interviewType === option.value ? 'chip-active' : 'chip-idle'"
                    @click="store.config.interviewType = option.value"
                  >
                    <span>{{ option.emoji }}</span>
                    {{ option.label }}
                  </button>
                </div>
                <p class="text-helper mt-3">{{ currentTypeOption.desc }}</p>
              </div>

              <div class="setup-arrangement-panel__block">
                <label class="config-label">难度级别</label>
                <div class="flex flex-wrap gap-2">
                  <button
                    v-for="option in difficultyOptions"
                    :key="option.value"
                    type="button"
                    class="chip-btn"
                    :class="store.config.difficulty === option.value ? 'chip-active' : 'chip-idle'"
                    @click="store.config.difficulty = option.value"
                  >
                    <span>{{ option.emoji }}</span>
                    {{ option.label }}
                  </button>
                </div>
                <p class="text-helper mt-3">{{ currentDifficultyOption.desc }}</p>
              </div>
            </div>

            <div class="setup-arrangement-panel__block">
              <div class="setup-arrangement-panel__title-row">
                <div>
                  <label class="config-label mb-1">面试风格</label>
                  <p class="text-helper">预设负责快速切换节奏，下方仍保留现有字段的精调能力。</p>
                </div>
                <span class="setup-inline-pill">{{ currentStyleOption.label }}</span>
              </div>
              <div class="grid grid-cols-2 gap-3 xl:grid-cols-4">
                <button
                  v-for="option in styleOptions"
                  :key="option.value"
                  type="button"
                  class="style-card-btn"
                  :class="store.config.style === option.value ? 'style-card-active' : 'style-card-idle'"
                  @click="setStyle(option.value)"
                >
                  <div class="text-lg">{{ option.emoji }}</div>
                  <div class="style-card-title mt-2">{{ option.label }}</div>
                  <div class="style-card-desc">{{ option.desc }}</div>
                </button>
              </div>
            </div>

            <div class="setup-arrangement-panel__foot">
              当前版本只重构展示与切换方式，不新增“保存为新场景卡片”的业务能力。
            </div>
          </div>
        </Transition>
      </section>

      <section class="setup-section">
        <div class="setup-section__head">
          <div class="setup-section__badge">
            <Cpu class="h-4 w-4" />
            模型与简历
          </div>
          <span class="setup-section__hint">先确定提问引擎，再决定 AI 可参考的候选人信息。</span>
        </div>

        <div class="setup-dual-grid">
          <article class="setup-surface-card">
            <div class="setup-card-header">
              <h3 class="setup-card-title">
                <Cpu class="h-4 w-4 text-slate-400" />
                AI 大模型
              </h3>
            </div>
            <div class="setup-model-pills">
              <button
                v-for="option in modelOptions"
                :key="option.value"
                type="button"
                class="setup-model-pill"
                :class="store.config.modelProvider === option.value ? 'setup-model-pill--active' : 'setup-model-pill--idle'"
                @click="store.config.modelProvider = option.value"
              >
                <span class="setup-model-pill__dot"></span>
                {{ option.label }}
              </button>
            </div>
            <p class="text-helper mt-4">{{ currentModelOption.desc }}</p>
          </article>

          <article class="setup-surface-card">
            <div class="setup-resume-head">
              <h3 class="setup-card-title">
                <Upload class="h-4 w-4 text-slate-400" />
                上传简历
              </h3>
              <span class="text-helper">PDF / Word(.docx) / Markdown / TXT / 图片</span>
            </div>

            <input
              ref="resumeInputRef"
              type="file"
              accept=".pdf,.docx,.md,.markdown,.txt,.png,.jpg,.jpeg,.bmp,.webp,.heic,.heif"
              class="sr-only"
              @change="onFileChange"
            />

            <div v-if="hasResumeSelection" class="setup-resume-state">
              <div class="setup-resume-state__file">
                <div class="setup-resume-state__icon">
                  <FileCheck class="h-4 w-4" />
                </div>
                <span class="setup-resume-state__name">
                  {{ store.config.resumeFile ? '已选择' : '已加载' }}: {{ resumeStatusLabel }}
                </span>
              </div>
              <button type="button" class="setup-resume-state__action" @click="replaceResume">
                <RefreshCw class="h-3 w-3" />
                改为上传其他简历
              </button>
            </div>

            <button v-else type="button" class="setup-upload-trigger" @click="triggerResumePicker">
              选择并上传简历
            </button>

            <p class="text-helper mt-3">支持继续复用历史 OCR 简历，也可随时替换为新的本地文件。</p>
          </article>
        </div>
      </section>

      <section class="setup-start-card">
        <div class="setup-start-card__orb setup-start-card__orb--right" aria-hidden="true"></div>
        <div class="setup-start-card__orb setup-start-card__orb--left" aria-hidden="true"></div>

        <div class="setup-start-card__inner">
          <div class="setup-start-card__copy">
            <span class="setup-start-card__eyebrow">启动前确认</span>
            <h2 class="setup-start-card__title">准备开始沉浸式面试</h2>
            <p class="setup-start-card__desc">
              页面上只保留核心面试配置。点击开始后会先用三张步骤卡依次确认目标岗位、JD 要求和语音设置，再按现有流程初始化房间并进入面试界面。
            </p>
            <p class="setup-start-card__note">
              下一步先确认目标岗位，再补充 JD，最后切到语音配置。当前记忆：{{ store.config.jobTitle.trim() || '你想要应聘的岗位' }} / {{ hasLaunchJobRequirements ? 'JD 已补充' : 'JD 可选' }} / {{ currentVoiceLabelCompact }}
            </p>
            <div class="setup-start-card__summary">
              <span v-for="item in confirmSummaryItems" :key="item.label" class="setup-start-card__pill">
                {{ item.label }} · {{ item.value }}
              </span>
            </div>
          </div>

          <div class="setup-start-card__actions">
            <button type="submit" class="ui-btn ui-btn-primary setup-start-card__btn" :disabled="loading">
              <Play class="h-5 w-5" />
              <span>{{ loading ? '系统初始化中...' : '开始沉浸式面试' }}</span>
            </button>

            <button
              v-if="loading"
              type="button"
              class="ui-btn ui-btn-secondary setup-start-card__cancel"
              @click="store.cancelSetup"
            >
              取消当前初始化
            </button>
          </div>
        </div>
      </section>
    </form>

    <Transition name="launch-sheet">
      <div v-if="launchConfigOpen" class="setup-launch-layer" @click.self="closeLaunchConfig">
        <div class="setup-launch-sheet">
          <div class="setup-launch-sheet__grabber" aria-hidden="true"></div>
          <div class="setup-launch-sheet__head">
            <div>
              <span class="setup-start-card__eyebrow">开始前最后一步</span>
              <div class="setup-launch-sheet__title-row">
                <h3 class="setup-launch-sheet__title">按步骤确认岗位画像与语音配置</h3>
                <span class="setup-launch-sheet__step-count">步骤 {{ launchStepIndex + 1 }} / {{ launchSteps.length }}</span>
              </div>
              <p class="setup-launch-sheet__desc">先确认目标岗位，再补充 JD 要求，最后切到语音配置；只改展示顺序，不改底层启动流程。</p>
            </div>
            <button
              type="button"
              class="setup-launch-sheet__close"
              :disabled="loading"
              @click="closeLaunchConfig"
            >
              <X class="h-4 w-4" />
            </button>
          </div>

          <div class="setup-launch-sheet__steps">
            <button
              v-for="(step, index) in launchSteps"
              :key="step.id"
              type="button"
              class="setup-launch-sheet__step"
              :class="launchStepIndex === index ? 'setup-launch-sheet__step--active' : ''"
              :disabled="loading || isLaunchStepLocked(index)"
              @click="setLaunchStep(index)"
            >
              <span class="setup-launch-sheet__step-index">{{ index + 1 }}</span>
              <span class="setup-launch-sheet__step-copy">
                <strong class="setup-launch-sheet__step-label">{{ step.title }}</strong>
                <span class="setup-launch-sheet__step-desc">{{ step.desc }}</span>
              </span>
            </button>
          </div>

          <div
            class="setup-launch-stage-shell"
            @touchstart.passive="handleLaunchTouchStart"
            @touchend="handleLaunchTouchEnd"
          >
            <button
              type="button"
              class="setup-launch-stage__nav setup-launch-stage__nav--left"
              :disabled="launchStepIndex === 0 || loading"
              @click="prevLaunchStep"
            >
              <ChevronLeft class="h-4 w-4" />
            </button>
            <button
              type="button"
              class="setup-launch-stage__nav setup-launch-stage__nav--right"
              :disabled="launchStepIndex === launchSteps.length - 1 || loading || !isLaunchProfileReady"
              @click="nextLaunchStep"
            >
              <ChevronRight class="h-4 w-4" />
            </button>

            <div class="setup-launch-stage__viewport">
              <div class="setup-launch-track" :style="launchTrackStyle">
                <article class="setup-surface-card custom-scroll setup-launch-card">
                  <div class="setup-launch-card__summary">
                    <p class="setup-launch-card__note">先锁定应聘岗位方向，后续 JD 和语音设置都围绕这个岗位展开。</p>
                    <span class="setup-inline-pill">{{ isLaunchProfileReady ? '岗位已确认' : '等待岗位输入' }}</span>
                  </div>

                  <div class="setup-role-summary">
                    <div class="min-w-0">
                      <span class="setup-role-summary__eyebrow">当前目标</span>
                      <div class="setup-role-summary__main">
                        <strong class="setup-role-summary__title">{{ store.config.jobTitle.trim() || '你想要应聘的岗位' }}</strong>
                        <span class="setup-role-summary__note">
                          {{ store.config.jobTitle.trim() ? '可在下方继续修改岗位标签或输入更准确的名称。' : '可在下方直接输入或点击岗位标签进行选择。' }}
                        </span>
                      </div>
                    </div>
                    <span class="setup-inline-pill">{{ isLaunchProfileReady ? '可进入下一步' : '请先选择岗位' }}</span>
                  </div>

                  <div class="setup-role-picker">
                    <JobTagPicker v-model="store.config.jobTitle" :default-expanded="true" />
                    <p v-if="!isLaunchProfileReady" class="setup-role-picker__hint">请先填写应聘岗位后再继续配置。</p>
                  </div>
                </article>

                <article class="setup-surface-card custom-scroll setup-launch-card">
                  <div class="setup-launch-card__summary">
                    <p class="setup-launch-card__note">这一张卡只负责补充岗位要求，AI 会把它作为追问重点和评分参考。</p>
                    <span class="setup-inline-pill">{{ hasLaunchJobRequirements ? 'JD 已补充' : '可跳过' }}</span>
                  </div>

                  <div class="setup-role-summary">
                    <div class="min-w-0">
                      <span class="setup-role-summary__eyebrow">岗位参考</span>
                      <div class="setup-role-summary__main">
                        <strong class="setup-role-summary__title">{{ store.config.jobTitle.trim() || '你想要应聘的岗位' }}</strong>
                        <span class="setup-role-summary__note">
                          {{ hasLaunchJobRequirements ? '已补充岗位要求，AI 会结合 JD 组织追问。' : '这一步可选；如果不填，AI 会仅依据岗位名和简历继续面试。' }}
                        </span>
                      </div>
                    </div>
                    <span class="setup-inline-pill">{{ hasLaunchJobRequirements ? '已补充内容' : '可直接下一步' }}</span>
                  </div>

                  <div class="setup-jd-shell">
                    <div class="setup-jd-shell__inner">
                      <label class="config-label">岗位要求 / 职位描述（可选）</label>
                      <textarea
                        v-model="store.config.jobRequirements"
                        class="config-input min-h-[220px] resize-y"
                        placeholder="可粘贴岗位职责、技术栈要求、年限要求、加分项等。AI 会把这部分作为考察重点和评分基准，不会当成候选人已经具备的经历。"
                      />
                      <div class="setup-jd-shell__foot">
                        <span class="text-helper">建议直接粘贴 JD 原文，尤其是核心职责、必备技能、经验年限和加分项。</span>
                      </div>
                    </div>
                  </div>
                </article>

                <article class="setup-surface-card setup-surface-card--voice setup-launch-card setup-launch-card--voice">
                  <div class="setup-launch-card__summary">
                    <p class="setup-launch-card__note">岗位画像确认后，再决定音色和语速；这里不再重复步骤标题，只保留当前配置摘要。</p>
                    <span class="setup-inline-pill">{{ currentVoiceLabelCompact }}</span>
                  </div>

                  <div class="setup-voice-block">
                    <div class="setup-voice-block__head">
                      <div>
                        <h3 class="setup-field-title">
                          <Volume2 class="h-4 w-4 text-slate-400" />
                          AI 面试官语音
                        </h3>
                        <p class="text-helper mt-1">先确认音色和语速，保证下拉候选列表完整显示后再继续调整其他项。</p>
                      </div>
                      <span class="setup-inline-pill">{{ currentVoiceLabelCompact }}</span>
                    </div>

                    <div class="setup-voice-row">
                      <div class="setup-voice-field setup-voice-field--select">
                        <span class="text-helper mb-1.5 block">音色</span>
                        <div class="setup-voice-select">
                          <CustomSelect
                            v-model="store.config.voicePer"
                            :options="voiceOptions"
                            placeholder="选择音色"
                          />
                        </div>
                      </div>

                      <div class="setup-voice-field setup-voice-field--speed">
                        <span class="text-helper mb-1.5 block">语速</span>
                        <div class="setup-speed-bar">
                          <button
                            v-for="option in speedOptions"
                            :key="option.spd"
                            type="button"
                            class="setup-speed-bar__btn"
                            :class="store.config.voiceSpd === option.spd ? 'setup-speed-bar__btn--active' : ''"
                            @click="store.config.voiceSpd = option.spd"
                          >
                            {{ option.label }}
                          </button>
                        </div>
                      </div>

                      <button
                        type="button"
                        class="setup-preview-btn inline-flex items-center justify-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-medium transition-all disabled:opacity-50"
                        :class="previewPlaying
                          ? 'bg-red-50 text-red-600 border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-500/30'
                          : 'bg-indigo-50 text-indigo-600 border-indigo-200 hover:bg-indigo-100 dark:bg-primary/5 dark:text-indigo-400 dark:border-indigo-500/30 dark:hover:bg-primary/10 dark:hover:border-indigo-400/50'"
                        :disabled="previewLoading"
                        @click="playPreview"
                      >
                        <Loader v-if="previewLoading" class="h-4 w-4 animate-spin" />
                        <Volume2 v-else class="h-4 w-4" />
                        {{ previewLoading ? '加载中...' : previewPlaying ? '停止试听' : '试听当前语音' }}
                      </button>
                    </div>
                  </div>
                </article>
              </div>
            </div>
          </div>

          <div class="setup-launch-sheet__foot">
            <div class="setup-launch-sheet__summary-block">
              <p class="setup-launch-sheet__summary">{{ launchStepSummary }}</p>
              <p class="setup-launch-sheet__gesture">支持左右滑动切换卡片，也可直接点击上方步骤按钮。</p>
            </div>
            <div class="setup-launch-sheet__actions">
              <button
                v-if="loading"
                type="button"
                class="ui-btn ui-btn-secondary"
                @click="store.cancelSetup"
              >
                取消当前初始化
              </button>
              <button
                v-else
                type="button"
                class="ui-btn ui-btn-secondary"
                @click="launchStepIndex === 0 ? closeLaunchConfig() : prevLaunchStep()"
              >
                <ChevronLeft v-if="launchStepIndex > 0" class="h-4 w-4" />
                <span>{{ launchStepIndex === 0 ? '稍后再配' : '返回上一步' }}</span>
              </button>
              <button
                v-if="launchStepIndex < launchSteps.length - 1"
                type="button"
                class="ui-btn ui-btn-primary"
                :disabled="loading || !isLaunchProfileReady"
                @click="nextLaunchStep"
              >
                <span>{{ launchStepIndex === 0 ? '下一步：JD 要求' : '下一步：语音配置' }}</span>
                <ChevronRight class="h-5 w-5" />
              </button>
              <button
                v-else
                type="button"
                class="ui-btn ui-btn-primary"
                :disabled="loading || !isLaunchProfileReady"
                @click="startInterview"
              >
                <Play class="h-5 w-5" />
                <span>{{ loading ? '系统初始化中...' : '确认进入面试' }}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
@reference "tailwindcss";

.setup-page {
  padding-bottom: 2rem;
}

.setup-form {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.setup-section--lead .setup-section__head {
  margin-bottom: 1.2rem;
}

.setup-section--lead .setup-section__badge {
  padding: 0.55rem 1rem;
  font-size: 0.98rem;
}

.setup-surface.setup-surface--stage {
  padding: 0.35rem 3.75rem 0.5rem;
  border: none;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  overflow: visible;
}

.setup-surface.setup-surface--stage :deep(.stage-deck__viewport--carousel) {
  min-height: calc(var(--deck-card-height) + 28px);
}

.setup-surface.setup-surface--stage :deep(.stage-deck__card) {
  border-color: rgba(226, 232, 240, 0.96);
  background: #ffffff;
  box-shadow: 0 18px 36px rgba(15, 23, 42, 0.08);
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

.setup-surface.setup-surface--stage :deep(.stage-deck__card-wrap:hover .stage-deck__card),
.setup-surface.setup-surface--stage :deep(.stage-deck__card--active) {
  border-color: rgba(129, 140, 248, 0.36);
  box-shadow:
    0 24px 48px rgba(15, 23, 42, 0.12),
    0 0 0 1px rgba(129, 140, 248, 0.08);
}

.setup-surface.setup-surface--stage :deep(.stage-deck__nav) {
  border-color: rgba(226, 232, 240, 0.96);
  background: #ffffff;
  color: #475569;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
}

.setup-surface.setup-surface--stage :deep(.stage-deck__nav:hover) {
  border-color: rgba(129, 140, 248, 0.36);
  background: #ffffff;
  color: #4338ca;
  box-shadow: 0 16px 32px rgba(15, 23, 42, 0.12);
}

.setup-hero {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.5rem;
  overflow: hidden;
  padding: 2rem;
}

.setup-hero::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 12% 18%, rgba(59, 130, 246, 0.12), transparent 28%),
    radial-gradient(circle at 86% 14%, rgba(244, 114, 182, 0.1), transparent 24%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.18), rgba(248, 250, 252, 0.08));
  pointer-events: none;
}

.setup-hero__main,
.setup-hero__stats {
  position: relative;
  z-index: 1;
}

.setup-hero__main {
  flex: 1;
  min-width: 0;
}

.setup-hero__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1.4rem;
}

.setup-hero__meta-chip,
.setup-inline-pill,
.setup-start-card__pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border-radius: 9999px;
  border: 1px solid rgba(226, 232, 240, 0.88);
  background: #ffffff;
  padding: 0.52rem 0.85rem;
  font-size: 0.76rem;
  font-weight: 700;
  color: #475569;
}

.setup-hero__stats {
  display: grid;
  width: min(100%, 260px);
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.setup-hero-stat {
  display: flex;
  min-height: 116px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  border-radius: 1.4rem;
  border: 1px solid rgba(226, 232, 240, 0.86);
  background: rgba(248, 250, 252, 0.78);
  padding: 1rem;
  text-align: center;
}

.setup-hero-stat__label {
  font-size: 0.74rem;
  font-weight: 700;
  color: #94a3b8;
}

.setup-hero-stat__value {
  font-size: 2rem;
  line-height: 1;
  font-weight: 800;
  color: #0f172a;
}

.setup-section__head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
  padding: 0 0.5rem;
}

.setup-section__badge {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  border-radius: 9999px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: #ffffff;
  padding: 0.45rem 0.85rem;
  font-size: 0.9rem;
  font-weight: 700;
  color: #4f46e5;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
}

.setup-section__actions {
  display: flex;
  align-items: center;
  gap: 0.85rem;
}

.setup-section__hint {
  font-size: 0.84rem;
  color: #94a3b8;
}

.setup-section__toggle,
.setup-inline-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  border-radius: 0.85rem;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: #ffffff;
  padding: 0.72rem 0.95rem;
  font-size: 0.78rem;
  font-weight: 700;
  color: #475569;
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    color 180ms ease,
    background-color 180ms ease;
}

.setup-section__toggle:hover,
.setup-inline-toggle:hover {
  transform: translateY(-1px);
  border-color: rgba(129, 140, 248, 0.34);
  color: #4338ca;
  background: #ffffff;
}

.setup-surface,
.setup-surface-card,
.setup-arrangement-panel,
.setup-start-card {
  position: relative;
  overflow: hidden;
  border-radius: 2rem;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: #ffffff;
  box-shadow: 0 14px 32px rgba(15, 23, 42, 0.05);
}

.setup-surface {
  padding: 1.5rem 1.2rem;
  background: #ffffff;
}

.setup-surface-card {
  padding: 1.5rem;
}

.setup-surface-card--voice {
  overflow: visible;
  z-index: 12;
}

.setup-surface-card--voice:focus-within {
  z-index: 24;
}

.setup-dual-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.setup-scenario-card {
  position: relative;
  display: flex;
  height: 100%;
  min-height: calc(200px - 2rem);
  flex-direction: column;
}

.setup-scenario-card__flare {
  position: absolute;
  right: -1.2rem;
  bottom: -1.4rem;
  width: 6.5rem;
  height: 6.5rem;
  border-radius: 9999px;
  background: radial-gradient(circle, rgba(148, 163, 184, 0.16) 0%, rgba(255, 255, 255, 0) 70%);
  opacity: 0.85;
  pointer-events: none;
}

.setup-scenario-card__top {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.setup-scenario-card__avatar {
  display: inline-flex;
  width: 2.5rem;
  height: 2.5rem;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: #ffffff;
  font-size: 1.25rem;
}

.setup-scenario-card__state {
  display: inline-flex;
  align-items: center;
  border-radius: 9999px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: #ffffff;
  padding: 0.35rem 0.65rem;
  font-size: 0.68rem;
  font-weight: 700;
  color: #64748b;
}

.setup-scenario-card__state--active {
  border-color: rgba(199, 210, 254, 0.96);
  background: #ffffff;
  color: #4338ca;
}

.setup-scenario-card__body {
  position: relative;
  z-index: 1;
  display: flex;
  flex: 1;
  flex-direction: column;
  margin-top: 0.9rem;
}

.setup-scenario-card__kicker {
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #94a3b8;
}

.setup-scenario-card__title {
  margin-top: 0.45rem;
  font-size: 1.06rem;
  font-weight: 800;
  color: #0f172a;
}

.setup-scenario-card__desc {
  margin-top: 0.45rem;
  font-size: 0.8rem;
  line-height: 1.65;
  color: #64748b;
}

.setup-scenario-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-top: auto;
  padding-top: 0.9rem;
}

.setup-scenario-card__tag {
  display: inline-flex;
  align-items: center;
  border-radius: 0.5rem;
  background: rgba(248, 250, 252, 0.95);
  padding: 0.26rem 0.5rem;
  font-size: 0.66rem;
  font-weight: 600;
  color: #64748b;
}

.setup-scenario-card__hint {
  display: inline-flex;
  align-items: center;
  margin-top: auto;
  padding-top: 0.85rem;
  font-size: 0.74rem;
  font-weight: 700;
  color: #4f46e5;
}

.setup-arrangement__selection {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 1rem;
  padding: 0 0.5rem;
}

.setup-arrangement__selection-copy {
  min-width: 0;
}

.setup-arrangement__selection-label {
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #94a3b8;
}

.setup-arrangement__selection-main {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.65rem;
  margin-top: 0.35rem;
}

.setup-arrangement__selection-title {
  font-size: 1rem;
  font-weight: 800;
  color: #0f172a;
}

.setup-arrangement__selection-meta {
  font-size: 0.82rem;
  color: #64748b;
}

.setup-arrangement-panel {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-top: 1rem;
  padding: 1.4rem;
}

.setup-arrangement-panel__row {
  display: grid;
  grid-template-columns: 5fr 7fr;
  gap: 1rem;
}

.setup-arrangement-panel__block {
  border-radius: 1.35rem;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: #ffffff;
  padding: 1.1rem;
}

.setup-arrangement-panel__title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.setup-arrangement-panel__foot {
  padding-top: 0.2rem;
  font-size: 0.8rem;
  color: #94a3b8;
}

.setup-card-header,
.setup-resume-head,
.setup-role-summary,
.setup-voice-block__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.setup-card-title,
.setup-field-title {
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  font-size: 0.95rem;
  font-weight: 800;
  color: #0f172a;
}

.setup-model-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1rem;
}

.setup-model-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  border-radius: 9999px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  padding: 0.72rem 1rem;
  font-size: 0.86rem;
  font-weight: 700;
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    background-color 180ms ease,
    color 180ms ease,
    box-shadow 180ms ease;
}

.setup-model-pill__dot {
  width: 0.55rem;
  height: 0.55rem;
  border-radius: 9999px;
  background: currentColor;
  opacity: 0.75;
}

.setup-model-pill--idle {
  color: #64748b;
  background: #ffffff;
}

.setup-model-pill--idle:hover {
  transform: translateY(-1px);
  border-color: rgba(129, 140, 248, 0.24);
  background: #ffffff;
}

.setup-model-pill--active {
  color: #4338ca;
  border-color: rgba(129, 140, 248, 0.35);
  background: rgba(238, 242, 255, 0.92);
  box-shadow: 0 0 0 2px rgba(129, 140, 248, 0.14);
}

.setup-resume-head {
  margin-bottom: 1rem;
}

.setup-resume-state {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  border-radius: 1rem;
  border: 1px solid rgba(134, 239, 172, 0.54);
  background: rgba(240, 253, 244, 0.86);
  padding: 0.82rem 0.9rem;
}

.setup-resume-state__file {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0.7rem;
}

.setup-resume-state__icon {
  display: inline-flex;
  width: 2rem;
  height: 2rem;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 0.75rem;
  background: rgba(220, 252, 231, 0.96);
  color: #16a34a;
}

.setup-resume-state__name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.84rem;
  font-weight: 700;
  color: #15803d;
}

.setup-resume-state__action,
.setup-upload-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  border-radius: 0.9rem;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: rgba(255, 255, 255, 0.92);
  padding: 0.78rem 1rem;
  font-size: 0.8rem;
  font-weight: 700;
  color: #475569;
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    background-color 180ms ease,
    color 180ms ease;
}

.setup-resume-state__action:hover,
.setup-upload-trigger:hover {
  transform: translateY(-1px);
  border-color: rgba(129, 140, 248, 0.32);
  color: #4338ca;
  background: rgba(248, 250, 252, 0.98);
}

.setup-upload-trigger {
  width: 100%;
  min-height: 3.1rem;
  justify-content: center;
}

.setup-role-summary {
  margin-bottom: 1.25rem;
}

.setup-role-summary__eyebrow {
  display: inline-flex;
  align-items: center;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #94a3b8;
}

.setup-role-summary__main {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin-top: 0.4rem;
}

.setup-role-summary__title {
  font-size: clamp(1.15rem, 2vw, 1.35rem);
  line-height: 1.3;
  font-weight: 800;
  color: #0f172a;
}

.setup-role-summary__note {
  font-size: 0.82rem;
  color: #64748b;
}

.setup-role-picker {
  margin-bottom: 1.25rem;
}

.setup-role-picker__hint {
  margin-top: 0.85rem;
  font-size: 0.82rem;
  font-weight: 600;
  color: #64748b;
}

.setup-jd-shell {
  border-radius: 1.35rem;
  border: none;
  background: transparent;
  padding: 0;
}

.setup-jd-shell__inner {
  border-radius: 1.2rem;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: #ffffff;
  padding: 1rem;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6);
}

.setup-jd-shell__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding-top: 0.8rem;
  margin-top: 0.75rem;
  border-top: 1px solid rgba(241, 245, 249, 0.96);
}

.setup-voice-block,
.setup-training-block {
  position: relative;
}

.setup-voice-block {
  z-index: 3;
}

.setup-training-block {
  z-index: 1;
}

.setup-voice-block + .setup-training-block {
  margin-top: 1.5rem;
  padding-top: 1.5rem;
  border-top: 1px solid rgba(226, 232, 240, 0.82);
}

.setup-training-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.setup-training-option {
  position: relative;
  display: block;
}

.setup-training-option__input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.setup-training-option__card {
  display: flex;
  align-items: flex-start;
  gap: 0.8rem;
  min-height: 100%;
  border-radius: 1rem;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: #ffffff;
  padding: 1rem;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.02);
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    background-color 180ms ease,
    box-shadow 180ms ease;
}

.setup-training-option:hover .setup-training-option__card {
  transform: translateY(-1px);
  border-color: rgba(129, 140, 248, 0.24);
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.05);
}

.setup-training-option__mark {
  position: relative;
  display: inline-flex;
  width: 1.2rem;
  height: 1.2rem;
  flex: none;
  border-radius: 0.4rem;
  border: 1px solid rgba(203, 213, 225, 0.96);
  background: rgba(255, 255, 255, 0.98);
}

.setup-training-option__mark::after {
  content: '';
  position: absolute;
  inset: 0.26rem;
  border-radius: 0.18rem;
  background: rgba(255, 255, 255, 0.98);
  opacity: 0;
  transform: scale(0.5);
  transition:
    opacity 160ms ease,
    transform 160ms ease;
}

.setup-training-option__input:checked + .setup-training-option__card {
  border-color: rgba(129, 140, 248, 0.32);
  background: #ffffff;
  box-shadow:
    0 0 0 2px rgba(129, 140, 248, 0.12),
    0 12px 24px rgba(79, 70, 229, 0.06);
}

.setup-training-option__input:checked + .setup-training-option__card .setup-training-option__mark {
  border-color: #4f46e5;
  background: #4f46e5;
}

.setup-training-option__input:checked + .setup-training-option__card .setup-training-option__mark::after {
  opacity: 1;
  transform: scale(1);
}

.setup-training-option__copy {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.setup-voice-row {
  display: flex;
  align-items: flex-end;
  gap: 1rem;
  margin-top: 1rem;
}

.setup-voice-field {
  min-width: 0;
}

.setup-voice-field--select {
  flex: 1;
}

.setup-voice-field--speed {
  flex: 1.1;
}

.setup-speed-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  border-radius: 0.95rem;
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: #ffffff;
  padding: 0.3rem;
}

.setup-speed-bar__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 3.1rem;
  border-radius: 0.7rem;
  padding: 0.48rem 0.7rem;
  font-size: 0.74rem;
  font-weight: 700;
  color: #64748b;
  transition:
    background-color 180ms ease,
    color 180ms ease,
    box-shadow 180ms ease;
}

.setup-speed-bar__btn:hover {
  background: rgba(248, 250, 252, 0.92);
}

.setup-speed-bar__btn--active {
  background: #ffffff;
  color: #4338ca;
  box-shadow:
    inset 0 0 0 1px rgba(199, 210, 254, 0.92),
    0 6px 16px rgba(79, 70, 229, 0.05);
}

.setup-voice-select {
  position: relative;
  z-index: 24;
}

.setup-surface-card--voice :deep(.custom-select-wrapper) {
  z-index: 24;
}

.setup-surface-card--voice :deep(.custom-select-dropdown) {
  z-index: 60;
}

.setup-preview-btn {
  flex: none;
  min-width: 10rem;
  box-shadow: 0 10px 24px rgba(79, 70, 229, 0.08);
}

.setup-start-card {
  padding: 1.85rem 2rem;
  background: #ffffff;
}

.setup-start-card__orb {
  display: none;
}

.setup-start-card__orb--right {
  top: -2.2rem;
  right: -2.2rem;
  background: rgba(196, 181, 253, 0.42);
}

.setup-start-card__orb--left {
  left: -2.2rem;
  bottom: -2.2rem;
  background: rgba(165, 180, 252, 0.34);
}

.setup-start-card__inner {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.5rem;
}

.setup-start-card__copy {
  min-width: 0;
}

.setup-start-card__eyebrow {
  display: inline-flex;
  align-items: center;
  border-radius: 9999px;
  border: 1px solid rgba(199, 210, 254, 0.88);
  background: #ffffff;
  padding: 0.42rem 0.8rem;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #4f46e5;
}

.setup-start-card__title {
  margin-top: 1rem;
  font-size: clamp(1.6rem, 2vw, 2rem);
  font-weight: 800;
  color: #0f172a;
}

.setup-start-card__desc {
  max-width: 40rem;
  margin-top: 0.75rem;
  font-size: 0.92rem;
  line-height: 1.75;
  color: #64748b;
}

.setup-start-card__note {
  margin-top: 0.9rem;
  font-size: 0.82rem;
  font-weight: 600;
  color: #475569;
}

.setup-start-card__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 0.7rem;
  margin-top: 1.2rem;
}

.setup-start-card__actions {
  display: flex;
  min-width: min(100%, 280px);
  flex-direction: column;
  gap: 0.8rem;
}

.setup-start-card__btn,
.setup-start-card__cancel {
  width: 100%;
  justify-content: center;
}

.setup-launch-layer {
  position: fixed;
  inset: 0;
  z-index: 70;
  display: flex;
  align-items: flex-end;
  justify-content: stretch;
  padding: 1.4rem 1.25rem 1.1rem;
  background: rgba(15, 23, 42, 0.08);
}

.setup-launch-sheet {
  position: relative;
  display: flex;
  flex-direction: column;
  width: min(100%, 1120px);
  height: min(88vh, 980px);
  max-height: calc(100vh - 1rem);
  margin: 0 auto;
  border-radius: 2rem;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: #ffffff;
  box-shadow:
    0 20px 52px rgba(15, 23, 42, 0.12),
    0 0 0 1px rgba(255, 255, 255, 0.6);
  padding: 0.95rem 1.45rem 1rem;
}

.setup-launch-sheet::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.54),
    0 0 28px rgba(148, 163, 184, 0.16);
}

.setup-launch-sheet__grabber {
  width: 4rem;
  height: 0.34rem;
  margin: 0 auto 1rem;
  border-radius: 9999px;
  background: rgba(148, 163, 184, 0.34);
}

.setup-launch-sheet__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.setup-launch-sheet__title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.setup-launch-sheet__title {
  margin-top: 0.95rem;
  font-size: clamp(1.35rem, 2vw, 1.75rem);
  font-weight: 800;
  color: #0f172a;
}

.setup-launch-sheet__step-count {
  display: inline-flex;
  flex: none;
  align-items: center;
  border-radius: 9999px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: #ffffff;
  padding: 0.48rem 0.8rem;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #64748b;
}

.setup-launch-sheet__desc {
  margin-top: 0.45rem;
  font-size: 0.88rem;
  line-height: 1.7;
  color: #64748b;
}

.setup-launch-sheet__steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.85rem;
  margin-top: 1.1rem;
}

.setup-launch-sheet__step {
  display: flex;
  align-items: flex-start;
  gap: 0.85rem;
  border-radius: 1.2rem;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: #ffffff;
  padding: 0.95rem 1rem;
  text-align: left;
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    box-shadow 180ms ease,
    background-color 180ms ease;
}

.setup-launch-sheet__step:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: rgba(129, 140, 248, 0.26);
  box-shadow: 0 10px 22px rgba(15, 23, 42, 0.06);
}

.setup-launch-sheet__step:disabled {
  cursor: not-allowed;
  opacity: 0.58;
  box-shadow: none;
}

.setup-launch-sheet__step--active {
  border-color: rgba(129, 140, 248, 0.34);
  box-shadow:
    0 0 0 2px rgba(129, 140, 248, 0.12),
    0 12px 24px rgba(15, 23, 42, 0.05);
}

.setup-launch-sheet__step-index {
  display: inline-flex;
  width: 2rem;
  height: 2rem;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: rgba(248, 250, 252, 0.96);
  font-size: 0.82rem;
  font-weight: 800;
  color: #64748b;
}

.setup-launch-sheet__step--active .setup-launch-sheet__step-index {
  border-color: rgba(199, 210, 254, 0.92);
  background: rgba(238, 242, 255, 0.94);
  color: #4338ca;
}

.setup-launch-sheet__step-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.18rem;
}

.setup-launch-sheet__step-label {
  font-size: 0.86rem;
  font-weight: 800;
  color: #0f172a;
}

.setup-launch-sheet__step-desc {
  font-size: 0.74rem;
  line-height: 1.5;
  color: #94a3b8;
}

.setup-launch-sheet__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 9999px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: rgba(255, 255, 255, 0.92);
  color: #64748b;
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    color 180ms ease,
    background-color 180ms ease;
}

.setup-launch-sheet__close:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: rgba(129, 140, 248, 0.34);
  color: #4338ca;
}

.setup-launch-sheet__close:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.setup-launch-sheet__panel {
  margin-top: 1.25rem;
  padding: 1.35rem 1.4rem;
}

.setup-launch-stage-shell {
  position: relative;
  flex: 1 1 auto;
  min-height: 0;
  margin-top: 1.05rem;
  overflow: visible;
  padding: 0.28rem 3.15rem 0.4rem;
}

.setup-launch-stage__viewport {
  height: 100%;
  min-height: 100%;
  padding: 0.35rem 0.45rem 0.55rem;
  overflow: hidden;
}

.setup-launch-track {
  display: flex;
  height: 100%;
  width: 100%;
  align-items: stretch;
  transition: transform 280ms cubic-bezier(0.4, 0, 0.2, 1);
  will-change: transform;
}

.setup-launch-card {
  box-sizing: border-box;
  width: 100%;
  min-width: 100%;
  min-height: 0;
  max-height: 100%;
  overflow-y: auto;
  padding: 1.45rem 1.45rem 1.55rem;
  box-shadow: 0 16px 34px rgba(15, 23, 42, 0.08);
}

.setup-launch-card__summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
  padding-bottom: 0.95rem;
  border-bottom: 1px solid rgba(241, 245, 249, 0.96);
}

.setup-launch-card__note {
  max-width: 34rem;
  font-size: 0.83rem;
  line-height: 1.65;
  color: #64748b;
}

.setup-launch-card--voice {
  overflow: visible;
  isolation: isolate;
}

.setup-launch-card--voice .setup-launch-card__summary {
  margin-bottom: 1.15rem;
}

.setup-launch-card--voice .setup-voice-block {
  z-index: 4;
}

.setup-launch-card--voice .setup-training-block {
  z-index: 1;
}

.setup-launch-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.15rem;
}

.setup-launch-stage__nav {
  position: absolute;
  top: 50%;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.75rem;
  height: 2.75rem;
  border-radius: 9999px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: #ffffff;
  color: #475569;
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.08);
  transform: translateY(-50%);
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    color 180ms ease,
    box-shadow 180ms ease;
}

.setup-launch-stage__nav:hover:not(:disabled) {
  transform: translateY(-50%) scale(1.03);
  border-color: rgba(129, 140, 248, 0.34);
  color: #4338ca;
  box-shadow: 0 16px 30px rgba(15, 23, 42, 0.12);
}

.setup-launch-stage__nav:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  box-shadow: none;
}

.setup-launch-stage__nav--left {
  left: 0.15rem;
}

.setup-launch-stage__nav--right {
  right: 0.15rem;
}

.setup-launch-sheet__section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.setup-launch-sheet__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 1rem;
}

.setup-launch-sheet__summary {
  font-size: 0.84rem;
  color: #64748b;
}

.setup-launch-sheet__summary-block {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.32rem;
}

.setup-launch-sheet__gesture {
  font-size: 0.74rem;
  color: #94a3b8;
}

.setup-launch-sheet__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.75rem;
}

.config-label {
  @apply mb-3 block text-sm font-bold;
  color: #334155;
}

.config-input {
  @apply w-full rounded-2xl border px-4 py-3 outline-none transition-all;
  background: rgba(255, 255, 255, 0.94);
  border-color: rgba(203, 213, 225, 0.92);
  color: #0f172a;
}

.config-input::placeholder {
  color: #94a3b8;
}

.config-input:focus {
  border-color: rgba(99, 102, 241, 0.48);
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.12);
}

.chip-btn {
  @apply inline-flex items-center gap-1.5 rounded-2xl border px-3 py-2 text-sm font-medium transition-all;
}

.chip-active {
  border-color: rgba(99, 102, 241, 0.38);
  color: #4338ca;
  background: #ffffff;
  box-shadow: 0 0 0 2px rgba(129, 140, 248, 0.12);
}

.chip-idle {
  border-color: rgba(226, 232, 240, 0.92);
  color: #475569;
  background: rgba(255, 255, 255, 0.88);
}

.chip-idle:hover {
  transform: translateY(-1px);
  border-color: rgba(129, 140, 248, 0.28);
  background: rgba(255, 255, 255, 0.98);
}

.style-card-btn {
  @apply rounded-2xl border p-3 text-left transition-all;
  position: relative;
  overflow: hidden;
  border-color: rgba(226, 232, 240, 0.9);
  background: #ffffff;
}

.style-card-btn::before {
  content: '';
  position: absolute;
  inset: 0;
  opacity: 0;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.06), rgba(255, 255, 255, 0));
  transition: opacity 200ms ease;
  pointer-events: none;
}

.style-card-active {
  border-color: rgba(129, 140, 248, 0.34);
  box-shadow: 0 0 0 2px rgba(129, 140, 248, 0.12);
}

.style-card-active::before,
.style-card-btn:hover::before {
  opacity: 1;
}

.style-card-idle:hover {
  transform: translateY(-1px);
  border-color: rgba(129, 140, 248, 0.24);
}

.style-card-title {
  @apply text-sm font-bold;
  position: relative;
  color: #334155;
}

.style-card-desc {
  @apply mt-0.5 text-xs;
  position: relative;
  color: #94a3b8;
}

.text-helper {
  @apply text-xs;
  color: #94a3b8;
}

.text-secondary-label {
  @apply text-sm font-semibold;
  color: #475569;
}

.deck-detail-enter-active,
.deck-detail-leave-active {
  transition: all 0.24s ease;
}

.deck-detail-enter-from,
.deck-detail-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

.launch-sheet-enter-active,
.launch-sheet-leave-active {
  transition: opacity 0.24s ease;
}

.launch-sheet-enter-from,
.launch-sheet-leave-to {
  opacity: 0;
}

.launch-sheet-enter-from .setup-launch-sheet,
.launch-sheet-leave-to .setup-launch-sheet {
  transform: translateY(56px);
}

.dark .setup-hero::before {
  background:
    radial-gradient(circle at 12% 18%, rgba(59, 130, 246, 0.16), transparent 28%),
    radial-gradient(circle at 86% 14%, rgba(244, 114, 182, 0.12), transparent 24%),
    linear-gradient(135deg, rgba(30, 41, 59, 0.28), rgba(49, 46, 129, 0.22));
}

.dark .setup-hero__meta-chip,
.dark .setup-inline-pill,
.dark .setup-start-card__pill,
.dark .setup-hero-stat,
.dark .setup-section__toggle,
.dark .setup-inline-toggle,
.dark .setup-model-pill--idle,
.dark .setup-speed-bar,
.dark .setup-speed-bar__btn:hover {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.05);
}

.dark .setup-hero-stat__label,
.dark .setup-section__hint,
.dark .text-helper,
.dark .setup-scenario-card__kicker,
.dark .setup-arrangement__selection-label {
  color: #94a3b8;
}

.dark .setup-hero-stat__value,
.dark .setup-card-title,
.dark .setup-field-title,
.dark .setup-role-summary__title,
.dark .setup-arrangement__selection-title,
.dark .setup-start-card__title,
.dark .style-card-title,
.dark .config-label {
  color: rgba(255, 255, 255, 0.96);
}

.dark .setup-section__badge,
.dark .setup-start-card__eyebrow,
.dark .setup-scenario-card__state--active,
.dark .setup-model-pill--active,
.dark .setup-speed-bar__btn--active,
.dark .chip-active {
  background: rgba(99, 102, 241, 0.18);
  color: #c4b5fd;
}

.dark .setup-surface,
.dark .setup-surface-card,
.dark .setup-arrangement-panel,
.dark .setup-start-card {
  border-color: rgba(255, 255, 255, 0.08);
  background: linear-gradient(180deg, rgba(12, 15, 23, 0.92) 0%, rgba(9, 12, 20, 0.96) 100%);
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.34);
}

.dark .setup-surface {
  background: rgba(15, 23, 42, 0.52);
}

.dark .setup-surface.setup-surface--stage {
  border: none;
  background: transparent;
  box-shadow: none;
}

.dark .setup-surface.setup-surface--stage :deep(.stage-deck__card) {
  border-color: rgba(255, 255, 255, 0.08);
  background: linear-gradient(180deg, rgba(11, 14, 24, 0.94) 0%, rgba(8, 11, 19, 0.96) 100%);
  box-shadow:
    0 24px 48px rgba(0, 0, 0, 0.34),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.dark .setup-surface.setup-surface--stage :deep(.stage-deck__card-wrap:hover .stage-deck__card),
.dark .setup-surface.setup-surface--stage :deep(.stage-deck__card--active) {
  border-color: rgba(129, 140, 248, 0.3);
  box-shadow:
    0 24px 52px rgba(0, 0, 0, 0.4),
    0 0 0 1px rgba(129, 140, 248, 0.18);
}

.dark .setup-surface.setup-surface--stage :deep(.stage-deck__nav) {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(15, 23, 42, 0.82);
  color: #cbd5e1;
  box-shadow: 0 16px 30px rgba(0, 0, 0, 0.28);
}

.dark .setup-surface.setup-surface--stage :deep(.stage-deck__nav:hover) {
  border-color: rgba(129, 140, 248, 0.28);
  background: rgba(30, 41, 59, 0.92);
  color: #c4b5fd;
}

.dark .setup-section__toggle:hover,
.dark .setup-inline-toggle:hover,
.dark .setup-model-pill--idle:hover,
.dark .setup-resume-state__action:hover,
.dark .setup-upload-trigger:hover {
  border-color: rgba(129, 140, 248, 0.28);
  color: #c4b5fd;
  background: rgba(255, 255, 255, 0.08);
}

.dark .setup-scenario-card__avatar,
.dark .setup-scenario-card__state,
.dark .setup-scenario-card__tag,
.dark .setup-arrangement-panel__block,
.dark .setup-jd-shell,
.dark .setup-training-option__card,
.dark .setup-resume-state__action,
.dark .setup-upload-trigger {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
}

.dark .setup-jd-shell {
  border-color: transparent;
  background: transparent;
}

.dark .setup-scenario-card__title,
.dark .setup-scenario-card__hint,
.dark .setup-scenario-card__state--active,
.dark .setup-start-card__eyebrow,
.dark .setup-model-pill--active,
.dark .setup-speed-bar__btn--active {
  color: #c4b5fd;
}

.dark .setup-scenario-card__desc,
.dark .setup-arrangement__selection-meta,
.dark .setup-role-summary__note,
.dark .setup-start-card__desc,
.dark .style-card-desc {
  color: rgba(255, 255, 255, 0.44);
}

.dark .setup-start-card__note,
.dark .setup-launch-sheet__close:hover:not(:disabled) {
  color: #c4b5fd;
}

.dark .setup-model-pill--idle,
.dark .setup-resume-state__action,
.dark .setup-upload-trigger,
.dark .setup-speed-bar__btn,
.dark .text-secondary-label,
.dark .setup-hero__meta-chip,
.dark .setup-inline-pill,
.dark .setup-start-card__pill,
.dark .setup-scenario-card__state,
.dark .setup-scenario-card__tag {
  color: #cbd5e1;
}

.dark .setup-resume-state {
  border-color: rgba(34, 197, 94, 0.26);
  background: rgba(6, 78, 59, 0.24);
}

.dark .setup-resume-state__icon {
  background: rgba(22, 163, 74, 0.18);
  color: #4ade80;
}

.dark .setup-resume-state__name {
  color: #86efac;
}

.dark .setup-launch-layer {
  background: rgba(2, 6, 23, 0.22);
}

.dark .setup-launch-sheet {
  border-color: rgba(255, 255, 255, 0.08);
  background: linear-gradient(180deg, rgba(11, 14, 24, 0.98) 0%, rgba(8, 11, 19, 0.98) 100%);
  box-shadow:
    0 -24px 72px rgba(0, 0, 0, 0.42),
    0 -1px 0 rgba(255, 255, 255, 0.04);
}

.dark .setup-launch-sheet::before {
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.04),
    0 0 24px rgba(67, 56, 202, 0.14);
}

.dark .setup-launch-sheet__grabber {
  background: rgba(148, 163, 184, 0.24);
}

.dark .setup-launch-sheet__summary,
.dark .setup-launch-sheet__desc,
.dark .setup-launch-sheet__gesture,
.dark .setup-launch-sheet__step-desc {
  color: rgba(255, 255, 255, 0.5);
}

.dark .setup-launch-sheet__title,
.dark .setup-launch-sheet__step-label {
  color: rgba(255, 255, 255, 0.96);
}

.dark .setup-launch-sheet__step,
.dark .setup-launch-sheet__step-count,
.dark .setup-launch-stage__nav {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
}

.dark .setup-launch-sheet__step:hover:not(:disabled),
.dark .setup-launch-stage__nav:hover:not(:disabled) {
  border-color: rgba(129, 140, 248, 0.28);
  background: rgba(255, 255, 255, 0.08);
}

.dark .setup-launch-sheet__step--active {
  border-color: rgba(129, 140, 248, 0.34);
  box-shadow:
    0 0 0 2px rgba(129, 140, 248, 0.14),
    0 16px 30px rgba(0, 0, 0, 0.24);
}

.dark .setup-launch-sheet__step-index {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  color: #cbd5e1;
}

.dark .setup-launch-sheet__step--active .setup-launch-sheet__step-index {
  border-color: rgba(129, 140, 248, 0.3);
  background: rgba(99, 102, 241, 0.16);
  color: #c4b5fd;
}

.dark .setup-launch-sheet__step-count,
.dark .setup-launch-stage__nav {
  color: #cbd5e1;
}

.dark .setup-launch-sheet__close {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  color: #cbd5e1;
}

.dark .setup-jd-shell__inner {
  border-color: rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.03);
}

.dark .setup-jd-shell__foot,
.dark .setup-voice-block + .setup-training-block {
  border-color: rgba(255, 255, 255, 0.08);
}

.dark .setup-role-summary__eyebrow,
.dark .setup-launch-card__note {
  color: #94a3b8;
}

.dark .setup-launch-card__summary {
  border-color: rgba(255, 255, 255, 0.08);
}

.dark .config-input {
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.9);
}

.dark .config-input::placeholder {
  color: rgba(255, 255, 255, 0.36);
}

.dark .config-input:focus {
  border-color: rgba(129, 140, 248, 0.5);
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.18);
}

.dark .style-card-btn,
.dark .chip-idle {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  color: #cbd5e1;
}

.dark .style-card-idle:hover,
.dark .chip-idle:hover {
  border-color: rgba(129, 140, 248, 0.3);
  background: rgba(255, 255, 255, 0.07);
}

.dark .style-card-active {
  border-color: rgba(129, 140, 248, 0.34);
  box-shadow: 0 0 0 2px rgba(129, 140, 248, 0.14);
}

.dark .setup-training-option__mark {
  border-color: rgba(255, 255, 255, 0.16);
  background: rgba(255, 255, 255, 0.04);
}

.dark .setup-training-option__input:checked + .setup-training-option__card {
  border-color: rgba(129, 140, 248, 0.34);
  background: rgba(99, 102, 241, 0.12);
}

.dark .setup-start-card {
  background:
    linear-gradient(135deg, rgba(30, 41, 59, 0.92), rgba(11, 14, 24, 0.98), rgba(49, 46, 129, 0.2));
}

.dark .setup-start-card__orb--right {
  background: rgba(129, 140, 248, 0.18);
}

.dark .setup-start-card__orb--left {
  background: rgba(99, 102, 241, 0.16);
}

@media (max-width: 960px) {
  .setup-hero,
  .setup-section__head,
  .setup-arrangement__selection,
  .setup-arrangement-panel__title-row,
  .setup-launch-sheet__head,
  .setup-launch-sheet__title-row,
  .setup-launch-sheet__foot,
  .setup-launch-sheet__section-head,
  .setup-launch-card__head,
  .setup-role-summary,
  .setup-resume-head,
  .setup-start-card__inner {
    flex-direction: column;
    align-items: flex-start;
  }

  .setup-hero__stats,
  .setup-dual-grid,
  .setup-arrangement-panel__row,
  .setup-training-options {
    width: 100%;
    grid-template-columns: 1fr;
  }

  .setup-start-card__actions {
    min-width: 0;
    width: 100%;
  }

  .setup-launch-sheet__actions {
    width: 100%;
    justify-content: stretch;
  }

  .setup-launch-sheet__actions > button {
    flex: 1 1 0;
  }

  .setup-preview-btn {
    width: 100%;
  }

  .setup-launch-stage__nav {
    display: none;
  }
}

@media (max-width: 720px) {
  .setup-page {
    padding-bottom: 1.5rem;
  }

  .setup-hero,
  .setup-surface,
  .setup-surface-card,
  .setup-arrangement-panel,
  .setup-start-card,
  .setup-launch-sheet {
    padding: 1.2rem;
  }

  .setup-launch-sheet {
    border-radius: 1.6rem;
    height: min(90vh, 820px);
    padding-top: 0.85rem;
  }

  .setup-surface.setup-surface--stage {
    padding: 0.2rem 0 0.25rem;
  }

  .setup-launch-stage-shell {
    padding: 0.15rem 0 0.25rem;
  }

  .setup-launch-stage__viewport {
    padding: 0.3rem 0.15rem 0.4rem;
  }

  .setup-voice-row {
    flex-direction: column;
    align-items: stretch;
  }

  .setup-resume-state {
    flex-direction: column;
    align-items: stretch;
  }

  .setup-resume-state__action {
    width: 100%;
  }
}

@media (max-width: 640px) {
  .setup-hero__stats {
    grid-template-columns: 1fr 1fr;
  }

  .setup-section__actions {
    width: 100%;
    justify-content: space-between;
  }

  .setup-arrangement__selection-main,
  .setup-start-card__summary {
    flex-direction: column;
    align-items: flex-start;
  }

  .setup-launch-layer {
    padding: 0.5rem;
    align-items: flex-end;
  }

  .setup-launch-sheet {
    width: 100%;
    border-radius: 1.35rem;
  }

  .setup-launch-sheet__steps {
    grid-template-columns: 1fr;
  }

  .setup-launch-sheet__actions {
    flex-direction: column-reverse;
  }
}
</style>
