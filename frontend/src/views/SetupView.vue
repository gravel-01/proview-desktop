<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useInterviewStore } from '../stores/interview'
import type { InterviewConfig } from '../types'
import {
  Play,
  Volume2,
  Loader,
  Upload,
  Cpu,
  FileCheck,
  RefreshCw,
  Sparkles,
  ListChecks,
  Dumbbell,
  Library,
} from 'lucide-vue-next'
import CatLoading from '../components/CatLoading.vue'
import CustomSelect from '../components/CustomSelect.vue'
import JobTagPicker from '../components/JobTagPicker.vue'
import { ttsPreview, fetchLatestResume } from '../services/interview'
import { isReusableOcrText } from '../utils/ocr'

const router = useRouter()
const store = useInterviewStore()
const loading = computed(() => store.isSettingUp)

// ===== 配置选项定义 =====
const styleOptions = [
  { value: 'default', label: '标准模式', desc: '专业均衡，客观评估', emoji: '📘' },
  { value: 'strict', label: '高压模式', desc: '追问更深，要求更高', emoji: '🎯' },
  { value: 'friendly', label: '温和引导', desc: '更适合练习和热身', emoji: '🌤' },
  { value: 'technical_deep', label: '技术深挖', desc: '关注原理和实现细节', emoji: '🧠' },
  { value: 'behavioral', label: '行为面试', desc: '聚焦经历表达与 STAR', emoji: '🗣' },
  { value: 'system_design', label: '系统设计', desc: '考察架构设计与权衡', emoji: '🏗' },
  { value: 'rapid_fire', label: '快问快答', desc: '强调知识广度和反应速度', emoji: '⚡' },
  { value: 'project_focused', label: '项目追问', desc: '重点深挖项目细节', emoji: '📂' },
]

const typeOptions = [
  { value: 'technical', label: '技术面', desc: '代码能力与技术深度', emoji: '💻' },
  { value: 'hr', label: 'HR面', desc: '职业动机与稳定性', emoji: '🤝' },
  { value: 'manager', label: '主管面', desc: '业务理解与协作能力', emoji: '📋' },
]

const difficultyOptions = [
  { value: 'junior', label: '初级', desc: '基础概念与常见实践', emoji: '🌱' },
  { value: 'mid', label: '中级', desc: '实战经验与原理理解', emoji: '🚀' },
  { value: 'senior', label: '高级', desc: '架构能力与系统思考', emoji: '🧭' },
] as const

const difficultyIndex = computed(() => {
  const i = difficultyOptions.findIndex((d) => d.value === store.config.difficulty)
  return i >= 0 ? i : 1
})

const difficultyFillPct = computed(() => {
  const max = difficultyOptions.length - 1
  if (max <= 0) return '0%'
  return `${(difficultyIndex.value / max) * 100}%`
})

function setDifficultyIndex(index: number) {
  const o = difficultyOptions[index]
  if (o) store.config.difficulty = o.value as InterviewConfig['difficulty']
}

function onDifficultyRangeInput(e: Event) {
  const v = Number((e.target as HTMLInputElement).value)
  if (!Number.isNaN(v)) setDifficultyIndex(v)
}
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

const speedOptions = [
  { label: '0.5x', spd: 2 },
  { label: '0.75x', spd: 3 },
  { label: '1x', spd: 5 },
  { label: '1.25x', spd: 7 },
  { label: '1.5x', spd: 9 },
  { label: '2x', spd: 12 },
]

const PREVIEW_TEXT = '你好，我是你的AI面试官，准备好开始面试了吗？'

const modelOptions = [
  { value: 'deepseek', label: 'DeepSeek', desc: '深度求索，代码能力强', emoji: '🧠' },
  { value: 'ernie', label: '文心一言', desc: '百度大模型，中文理解优秀', emoji: '🌐' },
  { value: 'ernie-thinking', label: '文心（深度思考）', desc: '开启思维链，回复更慢但更深入', emoji: '🔮' },
  // { value: 'deepseek-reasoner', label: 'DeepSeek R1', desc: '推理模型，逻辑分析强', emoji: '⚡' },
]

/** 展示型：本轮训练题库侧重点分布（与后端策略呼应，非实时计算） */
const bankRows = [
  { label: '简历压力链', pct: 38 },
  { label: '技术纵深', pct: 34 },
  { label: '行为与协作', pct: 28 },
] as const

// 语音试听
const previewPlaying = ref(false)
const previewLoading = ref(false)
let previewAudioCtx: AudioContext | null = null
let previewSource: AudioBufferSourceNode | null = null

function stopPreview() {
  if (previewSource) {
    try { previewSource.stop() } catch { /* already stopped */ }
    previewSource = null
  }
  previewPlaying.value = false
}

async function playPreview() {
  if (previewPlaying.value) { stopPreview(); return }
  previewLoading.value = true
  try {
    const wavBuffer = await ttsPreview(PREVIEW_TEXT, store.config.voicePer, store.config.voiceSpd)
    if (!previewAudioCtx) previewAudioCtx = new AudioContext()
    const audioBuf = await previewAudioCtx.decodeAudioData(wavBuffer)
    stopPreview()
    previewSource = previewAudioCtx.createBufferSource()
    previewSource.buffer = audioBuf
    previewSource.connect(previewAudioCtx.destination)
    previewSource.onended = () => { previewPlaying.value = false }
    previewSource.start()
    previewPlaying.value = true
  } catch (e: any) {
    console.error('试听失败:', e)
    console.error('试听失败:', e)
    alert('语音试听失败，请确保后端已启动')
  } finally {
    previewLoading.value = false
  }
}

function setStyle(val: string) { store.config.style = val as InterviewConfig['style'] }

async function startInterview() {
  if (!store.config.jobTitle.trim()) { alert('请输入目标岗位'); return }
  try {
    await store.startInterview()
    router.push('/interview')
  } catch (e: any) {
    alert('服务连接失败，请确保 Flask 后端已启动。' + (e.message || ''))
  }
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  store.config.resumeFile = input.files?.[0] || null
  // 选了新文件就清掉历史简历
  if (store.config.resumeFile) {
    store.config.resumeOcrText = undefined
    store.config.resumeFileName = undefined
  }
}

function clearHistoryResume() {
  store.config.resumeOcrText = undefined
  store.config.resumeFileName = undefined
}

// 进入配置页时，自动加载用户最近的简历（如果当前没有已加载的简历）
onMounted(async () => {
  if (store.config.resumeFile || store.config.resumeOcrText) return
  try {
    const resume = await fetchLatestResume()
    const latestOcrText = resume?.ocr_result || ''
    if (isReusableOcrText(latestOcrText)) {
      store.config.resumeOcrText = latestOcrText
      store.config.resumeFileName = resume?.file_name || '历史简历'
    }
  } catch { /* 静默 */ }
})
</script>

<template>
  <div class="setup-page fade-in mx-auto min-h-full max-w-5xl pb-10">
    <CatLoading
      v-if="loading"
      variant="corner"
      message="AI 面试官正在准备中"
      :stage="store.thinkingStage"
      :thinking-text="store.thinkingText"
    />

    <!-- 概述 -->
    <div class="setup-hero setup-tilt-card setup-enter mb-8 rounded-3xl border border-gray-200/60 bg-white/80 p-6 shadow-sm backdrop-blur-xl sm:p-8 dark:border-white/10 dark:bg-slate-950/75" style="--enter-delay: 0ms">
      <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div class="min-w-0">
          <span class="setup-badge setup-badge--hero mb-4 inline-flex items-center gap-2">
            <Sparkles class="setup-icon-glow h-4 w-4" />
            面试配置
          </span>
          <h2 class="setup-title-gradient text-2xl font-extrabold tracking-tight sm:text-3xl">
            配置专属面试房间
          </h2>
          <p class="mt-3 max-w-2xl text-sm font-medium leading-relaxed text-gray-600 dark:text-slate-400">
            柔和浅色系界面，设定岗位与风格后，AI 将结合简历生成追问链路与训练侧重。
          </p>
        </div>
        <div class="shrink-0 text-right">
          <p class="setup-rainbow-stat text-2xl font-black tabular-nums sm:text-3xl">1–3</p>
          <p class="text-xs font-semibold text-gray-500 dark:text-slate-400">总问题数（首轮）</p>
        </div>
      </div>
    </div>

    <form class="setup-form space-y-6" @submit.prevent="startInterview">
      <!-- 问卷问题链：模型 + 简历 -->
      <section class="setup-enter space-y-3" style="--enter-delay: 80ms">
        <div class="flex flex-wrap items-center gap-3">
          <span class="setup-badge"><ListChecks class="h-3.5 w-3.5 opacity-90" /> 问卷问题链</span>
          <span class="setup-divider-line hidden h-4 w-px sm:block" />
          <span class="text-xs font-medium text-gray-500 dark:text-slate-400">大模型与简历共同决定首轮问题骨架</span>
        </div>
        <div class="grid grid-cols-1 gap-5 md:grid-cols-2">
          <div class="config-card setup-mini setup-mini--blue setup-tilt-card group">
            <span class="setup-corner setup-corner--tl" aria-hidden="true" />
            <span class="setup-corner setup-corner--br" aria-hidden="true" />
            <label class="config-label flex items-center gap-2">
              <Cpu class="setup-icon-glow h-3.5 w-3.5" /> AI 大模型
            </label>
            <div class="setup-selector-enter flex flex-wrap gap-2">
              <button
                v-for="m in modelOptions"
                :key="m.value"
                type="button"
                class="setup-sel setup-sel-model"
                :class="store.config.modelProvider === m.value ? 'setup-sel-model--on' : 'setup-sel-model--off'"
                @click="store.config.modelProvider = m.value"
              >
                <span class="setup-sel-model__shine" aria-hidden="true" />
                <span class="setup-sel-model__inner relative z-[1] inline-flex items-center gap-1.5">
                  <span class="setup-emoji setup-sel-model__ico">{{ m.emoji }}</span> {{ m.label }}
                </span>
              </button>
            </div>
            <p class="text-helper mt-2">{{ modelOptions.find((m) => m.value === store.config.modelProvider)?.desc }}</p>
          </div>
          <div class="config-card setup-mini setup-mini--rose setup-tilt-card group">
            <span class="setup-corner setup-corner--tl" aria-hidden="true" />
            <span class="setup-corner setup-corner--br" aria-hidden="true" />
            <label class="config-label flex items-center gap-2">
              <Upload class="setup-icon-glow h-3.5 w-3.5" /> 上传简历
              <span class="text-helper font-normal">PDF / 图片</span>
            </label>
            <div v-if="store.config.resumeOcrText && !store.config.resumeFile" class="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div class="flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-emerald-200/80 bg-emerald-50/90 px-3 py-2.5 dark:border-emerald-500/25 dark:bg-emerald-950/25">
                <FileCheck class="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                <span class="truncate text-sm text-emerald-800 dark:text-emerald-300">已加载: {{ store.config.resumeFileName || '历史简历' }}</span>
              </div>
              <button type="button" class="ui-btn ui-btn-secondary shrink-0 px-3 py-2.5 text-xs font-medium whitespace-nowrap" @click="clearHistoryResume">
                <RefreshCw class="h-3.5 w-3.5" /> 重新上传
              </button>
            </div>
            <input
              v-else
              type="file"
              accept=".pdf,.png,.jpg,.jpeg"
              class="w-full cursor-pointer text-sm file:mr-3 file:rounded-full file:border-0 file:bg-blue-500/10 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-blue-700 hover:file:bg-blue-500/16 dark:file:bg-indigo-500/15 dark:file:text-indigo-200 dark:hover:file:bg-indigo-500/25"
              @change="onFileChange"
            />
          </div>
        </div>
      </section>

      <!-- 目标岗位 -->
      <section class="setup-enter config-card setup-tilt-card space-y-1" style="--enter-delay: 160ms">
        <label class="config-label">目标岗位</label>
        <JobTagPicker v-model="store.config.jobTitle" :default-expanded="true" />
      </section>

      <!-- 面试问题：轮次 + 难度 -->
      <section class="setup-enter space-y-3" style="--enter-delay: 220ms">
        <div class="flex flex-wrap items-center gap-3">
          <span class="setup-badge setup-badge--violet"><Sparkles class="h-3.5 w-3.5 opacity-90" /> 面试问题</span>
          <span class="setup-divider-line hidden h-4 w-px sm:block" />
          <span class="text-xs font-medium text-gray-500 dark:text-slate-400">轮次与难度影响追问深度与话术风格</span>
        </div>
        <div class="grid grid-cols-1 gap-5 md:grid-cols-2">
          <div class="config-card setup-mini setup-mini--violet setup-tilt-card group">
            <span class="setup-corner setup-corner--tl" aria-hidden="true" />
            <span class="setup-corner setup-corner--br" aria-hidden="true" />
            <label class="config-label">面试轮次</label>
            <div class="setup-selector-enter flex flex-wrap gap-2">
              <button
                v-for="t in typeOptions"
                :key="t.value"
                type="button"
                class="setup-sel setup-sel-type"
                :class="store.config.interviewType === t.value ? 'setup-sel-type--on' : 'setup-sel-type--off'"
                @click="store.config.interviewType = t.value"
              >
                <span class="setup-sel-type__pulse" aria-hidden="true" />
                <span class="relative z-[1] inline-flex min-h-10 min-w-10 flex-col items-center justify-center gap-0.5 px-2 text-center">
                  <span class="text-base leading-none">{{ t.emoji }}</span>
                  <span class="setup-sel-type__txt">{{ t.label }}</span>
                </span>
              </button>
            </div>
            <p class="text-helper mt-2">{{ typeOptions.find((t) => t.value === store.config.interviewType)?.desc }}</p>
          </div>
          <div class="config-card setup-mini setup-mini--amber setup-tilt-card group">
            <span class="setup-corner setup-corner--tl" aria-hidden="true" />
            <span class="setup-corner setup-corner--br" aria-hidden="true" />
            <label class="config-label">难度级别</label>
            <div class="setup-selector-enter setup-diff mt-1">
              <div class="setup-diff__track-wrap">
                <div class="setup-diff__track" aria-hidden="true">
                  <div class="setup-diff__fill" :style="{ width: difficultyFillPct }" />
                </div>
                <input
                  class="setup-diff__range"
                  type="range"
                  min="0"
                  max="2"
                  step="1"
                  :value="difficultyIndex"
                  @input="onDifficultyRangeInput"
                />
              </div>
              <div class="setup-diff__labels mt-3 flex flex-wrap gap-2">
                <button
                  v-for="(d, i) in difficultyOptions"
                  :key="d.value"
                  type="button"
                  class="setup-sel"
                  :class="difficultyIndex === i ? 'setup-sel-model--on' : 'setup-sel-model--off'"
                  @click="setDifficultyIndex(i)"
                >
                  <span class="setup-sel-model__shine" aria-hidden="true" />
                  <span class="relative z-[1] inline-flex items-center gap-1.5 text-sm font-medium">
                    <span class="setup-emoji">{{ d.emoji }}</span> {{ d.label }}
                  </span>
                </button>
              </div>
            </div>
            <p class="text-helper mt-2">{{ difficultyOptions.find((d) => d.value === store.config.difficulty)?.desc }}</p>
          </div>
        </div>
      </section>

      <!-- 面试风格 -->
      <section class="setup-enter config-card setup-tilt-card" style="--enter-delay: 300ms">
        <label class="config-label">面试风格</label>
        <div class="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          <button
            v-for="s in styleOptions"
            :key="s.value"
            type="button"
            class="style-card-btn setup-style-cell"
            :class="store.config.style === s.value ? 'style-card-active' : 'style-card-idle'"
            @click="setStyle(s.value)"
          >
            <span class="setup-style-glow" aria-hidden="true" />
            <div class="relative z-[1] mb-1 text-lg">{{ s.emoji }}</div>
            <div class="style-card-title relative z-[1]">{{ s.label }}</div>
            <div class="style-card-desc relative z-[1]">{{ s.desc }}</div>
          </button>
        </div>
      </section>

      <!-- 训练模式 -->
      <section class="setup-enter" style="--enter-delay: 380ms">
        <div class="mb-3 flex flex-wrap items-center gap-3">
          <span class="setup-badge setup-badge--mint"><Dumbbell class="h-3.5 w-3.5 opacity-90" /> 训练模式</span>
          <span class="setup-divider-line hidden h-4 w-px sm:block" />
          <span class="text-xs font-medium text-gray-500 dark:text-slate-400">可选加压与防卡壳策略</span>
        </div>
        <div class="setup-float-card config-card relative overflow-hidden border border-gray-200/60 dark:border-white/10">
          <span class="setup-float-halo" aria-hidden="true" />
          <span class="setup-float-pulse" aria-hidden="true" />
          <label class="config-label relative z-[1]">训练功能</label>
          <div class="relative z-[1] flex flex-wrap gap-5">
            <label class="inline-flex cursor-pointer select-none items-center gap-2">
              <input v-model="store.config.featureDeep" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary focus:ring-2 focus:ring-indigo-500/30 dark:border-white/20" />
              <span class="text-secondary-label">简历压力深挖</span>
              <span class="text-helper">连环追问，识别注水</span>
            </label>
            <label class="inline-flex cursor-pointer select-none items-center gap-2">
              <input v-model="store.config.featureVad" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary focus:ring-2 focus:ring-indigo-500/30 dark:border-white/20" />
              <span class="text-secondary-label">柔性防卡壳</span>
              <span class="text-helper">卡壳时给予提示引导</span>
            </label>
          </div>
        </div>
      </section>

      <!-- AI 面试题库（展示） -->
      <section class="setup-enter overflow-hidden rounded-3xl border border-gray-200/60 bg-white/75 shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-slate-950/70" style="--enter-delay: 460ms">
        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200/50 bg-gradient-to-r from-sky-100/90 via-indigo-50/90 to-violet-100/80 px-5 py-4 dark:border-white/10 dark:from-slate-900/90 dark:via-indigo-950/80 dark:to-slate-900/90">
          <span class="flex items-center gap-2 text-sm font-extrabold text-gray-800 dark:text-slate-100">
            <Library class="h-4 w-4 text-sky-600 dark:text-sky-300" />
            AI 面试题库 · 本轮侧重
          </span>
          <span class="setup-rainbow-stat text-sm font-black">动态生成</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full min-w-[320px] text-left text-sm">
            <thead>
              <tr class="text-xs font-bold tracking-wide text-gray-500 uppercase dark:text-slate-400">
                <th class="px-5 py-3">维度</th>
                <th class="px-5 py-3">覆盖权重</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in bankRows" :key="row.label" class="setup-table-row border-t border-gray-100/80 dark:border-white/6">
                <td class="px-5 py-3.5 font-semibold text-gray-700 dark:text-slate-200">{{ row.label }}</td>
                <td class="px-5 py-3.5">
                  <div class="flex items-center gap-3">
                    <div class="setup-progress-bg h-2.5 flex-1 overflow-hidden rounded-full">
                      <div class="setup-progress-fill h-full rounded-full" :style="{ width: `${row.pct}%` }" />
                    </div>
                    <span class="setup-rainbow-stat w-10 shrink-0 text-right text-xs font-black tabular-nums">{{ row.pct }}%</span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- 语音 -->
      <section class="setup-enter config-card setup-tilt-card" style="--enter-delay: 540ms">
        <label class="config-label inline-flex items-center gap-2">
          <Volume2 class="setup-icon-glow h-3.5 w-3.5" /> AI 面试官语音
        </label>
        <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <span class="text-helper mb-1.5 block">音色</span>
            <CustomSelect v-model="store.config.voicePer" :options="voiceOptions" placeholder="选择音色" />
          </div>
          <div>
            <span class="text-helper mb-1.5 block">语速</span>
            <div class="setup-selector-enter flex flex-wrap gap-1.5">
              <button
                v-for="s in speedOptions"
                :key="s.spd"
                type="button"
                class="setup-sel setup-sel-model px-3 py-1.5 text-xs font-semibold"
                :class="store.config.voiceSpd === s.spd ? 'setup-sel-model--on' : 'setup-sel-model--off'"
                @click="store.config.voiceSpd = s.spd"
              >
                <span class="setup-sel-model__shine" aria-hidden="true" />
                <span class="relative z-[1]">{{ s.label }}</span>
              </button>
            </div>
          </div>
        </div>
        <button
          type="button"
          class="mt-3 inline-flex items-center gap-2 rounded-xl border px-4 py-2 text-sm font-medium transition-all disabled:opacity-50"
          :class="previewPlaying ? 'ui-btn-danger' : 'ui-btn-outline'"
          :disabled="previewLoading"
          @click="playPreview"
        >
          <Loader v-if="previewLoading" class="h-4 w-4 animate-spin" />
          <Volume2 v-else class="h-4 w-4" />
          {{ previewLoading ? '加载中...' : previewPlaying ? '停止试听' : '试听当前语音' }}
        </button>
      </section>

      <!-- CTA -->
      <div class="setup-enter pt-2" style="--enter-delay: 620ms">
        <button type="submit" class="setup-cta" :disabled="loading">
          <span class="setup-cta__pulse" aria-hidden="true" />
          <span class="setup-cta__spin" aria-hidden="true" />
          <span class="setup-cta__shine setup-cta__shine--a" aria-hidden="true" />
          <span class="setup-cta__shine setup-cta__shine--b" aria-hidden="true" />
          <span class="setup-cta__corners" aria-hidden="true" />
          <span class="setup-cta__ripple" aria-hidden="true" />
          <span class="setup-cta__particles" aria-hidden="true">
            <span v-for="n in 8" :key="n" class="setup-cta__particle" :style="{ '--a': `${(n - 1) * 45}deg` }" />
          </span>
          <span class="setup-cta__inner relative z-[2] flex items-center justify-center gap-2 font-extrabold">
            <Play class="h-5 w-5" />
            {{ loading ? '系统初始化中...' : '开始面试准备训练' }}
          </span>
        </button>
        <button v-if="loading" type="button" class="ui-btn ui-btn-danger mt-3 w-full rounded-2xl px-4 py-3 text-sm font-medium" @click="store.cancelSetup">
          取消当前初始化
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
@reference "tailwindcss";

.setup-page {
  perspective: 1400px;
}

/* 暗黑模式色彩规范 */
.dark {
  --bg-elevated-1: #1a1a24;
  --bg-elevated-0: #0f0f15;
  --text-primary: rgba(255, 255, 255, 0.95);
  --text-secondary: rgba(255, 255, 255, 0.65);
  --text-tertiary: rgba(255, 255, 255, 0.4);
  --border-default: rgba(255, 255, 255, 0.1);
  --border-hover: rgba(255, 255, 255, 0.2);
}

.setup-title-gradient {
  background: linear-gradient(120deg, #111827 0%, #4b5563 40%, #6b7280 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.dark .setup-title-gradient {
  background: linear-gradient(120deg, #f8fafc 0%, #cbd5e1 55%, #94a3b8 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.setup-badge {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  overflow: hidden;
  border-radius: 9999px;
  border: 1px solid rgba(229, 231, 235, 0.85);
  background: linear-gradient(90deg, rgba(219, 234, 254, 0.95), rgba(250, 245, 255, 0.9), rgba(253, 242, 248, 0.92));
  padding: 0.35rem 0.85rem;
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #4338ca;
}
.setup-badge::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(105deg, transparent, rgba(255, 255, 255, 0.55), transparent);
  transform: translateX(-120%);
  animation: setup-badge-shine 3.2s ease-in-out infinite;
}
.setup-badge--hero {
  background: linear-gradient(90deg, rgba(254, 243, 199, 0.9), rgba(224, 242, 254, 0.92), rgba(252, 231, 243, 0.9));
  color: #6d28d9;
}
.setup-badge--violet {
  color: #5b21b6;
}
.setup-badge--mint {
  background: linear-gradient(90deg, rgba(204, 251, 241, 0.95), rgba(224, 242, 254, 0.9), rgba(250, 245, 255, 0.9));
  color: #0f766e;
}
.dark .setup-badge {
  border-color: rgba(255, 255, 255, 0.12);
  color: #c4b5fd;
  background: linear-gradient(90deg, rgba(30, 58, 138, 0.35), rgba(76, 29, 149, 0.32), rgba(131, 24, 67, 0.28));
}
.dark .setup-badge--mint {
  color: #5eead4;
}

@keyframes setup-badge-shine {
  0%,
  100% {
    transform: translate3d(-130%, 0, 0);
    opacity: 0;
  }
  40% {
    opacity: 0.7;
  }
  55% {
    transform: translate3d(130%, 0, 0);
    opacity: 0;
  }
}

.setup-divider-line {
  background: linear-gradient(180deg, rgba(59, 130, 246, 0.15), rgba(139, 92, 246, 0.35), rgba(236, 72, 153, 0.15));
  filter: blur(0.3px);
}

.setup-rainbow-stat {
  background: linear-gradient(90deg, #3b82f6, #6366f1, #8b5cf6, #db2777, #ec4899);
  background-size: 180% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: setup-rainbow-move 5s ease-in-out infinite, setup-stat-breath 2.8s ease-in-out infinite;
  will-change: background-position, opacity;
}

@keyframes setup-rainbow-move {
  0%,
  100% {
    background-position: 0% 50%;
  }
  50% {
    background-position: 100% 50%;
  }
}
@keyframes setup-stat-breath {
  0%,
  100% {
    opacity: 0.88;
  }
  50% {
    opacity: 1;
  }
}

.setup-enter {
  opacity: 0;
  transform: translate3d(0, 36px, 0) rotateX(10deg);
  animation: setup-enter-up 0.85s cubic-bezier(0.22, 1, 0.36, 1) forwards;
  animation-delay: var(--enter-delay, 0ms);
  will-change: transform, opacity;
}
@keyframes setup-enter-up {
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0) rotateX(0deg);
  }
}

.setup-tilt-card {
  transform-style: preserve-3d;
  transition:
    transform 0.5s cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 0.45s ease,
    border-color 0.35s ease;
  will-change: transform;
}
.setup-tilt-card:hover {
  transform: translate3d(0, -8px, 0) rotateX(3deg) rotateY(-3deg);
  box-shadow:
    0 28px 50px rgba(15, 23, 42, 0.12),
    0 0 0 1px rgba(99, 102, 241, 0.12),
    0 0 40px rgba(59, 130, 246, 0.08);
  border-color: rgba(129, 140, 248, 0.35);
}
.dark .setup-tilt-card:hover {
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.45);
  border-color: rgba(129, 140, 248, 0.25);
}

.setup-mini {
  position: relative;
  overflow: hidden;
}
.setup-mini::before {
  content: '';
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 0.5s ease;
  pointer-events: none;
}
.setup-mini--blue::before {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.12), rgba(99, 102, 241, 0.08), transparent 65%);
}
.setup-mini--rose::before {
  background: linear-gradient(135deg, rgba(244, 114, 182, 0.12), rgba(251, 191, 36, 0.06), transparent 65%);
}
.setup-mini--violet::before {
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.14), rgba(59, 130, 246, 0.08), transparent 65%);
}
.setup-mini--amber::before {
  background: linear-gradient(135deg, rgba(251, 191, 36, 0.14), rgba(244, 114, 182, 0.08), transparent 65%);
}
.setup-mini:hover::before {
  opacity: 1;
}

.setup-corner {
  position: absolute;
  width: 52px;
  height: 52px;
  border-radius: 9999px;
  filter: blur(20px);
  opacity: 0;
  transition: opacity 0.45s ease;
  pointer-events: none;
}
.group:hover .setup-corner {
  opacity: 0.55;
}
.setup-corner--tl {
  top: -18px;
  left: -12px;
  background: radial-gradient(circle, rgba(56, 189, 248, 0.55), transparent 70%);
}
.setup-corner--br {
  bottom: -20px;
  right: -10px;
  background: radial-gradient(circle, rgba(236, 72, 153, 0.45), transparent 70%);
}

.setup-emoji {
  display: inline-block;
  transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.setup-sel:hover .setup-emoji {
  transform: rotate(-6deg) scale(1.12);
}

.setup-icon-glow {
  color: #6366f1;
  filter: drop-shadow(0 2px 8px rgba(99, 102, 241, 0.25));
  animation: setup-icon-float 2.1s ease-in-out infinite;
}
@keyframes setup-icon-float {
  0%,
  100% {
    transform: translate3d(0, 0, 0);
  }
  50% {
    transform: translate3d(0, -2px, 0);
  }
}

.setup-style-cell {
  position: relative;
  overflow: hidden;
}
.setup-style-glow {
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 0.45s ease;
  background: linear-gradient(130deg, rgba(59, 130, 246, 0.14), rgba(139, 92, 246, 0.12), rgba(236, 72, 153, 0.12));
  pointer-events: none;
}
.setup-style-cell:hover .setup-style-glow {
  opacity: 1;
}
.setup-style-cell:hover {
  transform: scale(1.03);
  box-shadow: 0 12px 28px rgba(99, 102, 241, 0.12);
}

.setup-float-card {
  transform-style: preserve-3d;
}
.setup-float-halo {
  pointer-events: none;
  position: absolute;
  inset: -40%;
  background: radial-gradient(circle at 30% 20%, rgba(59, 130, 246, 0.12), transparent 45%),
    radial-gradient(circle at 80% 80%, rgba(236, 72, 153, 0.1), transparent 48%);
  opacity: 0;
  transition: opacity 0.45s ease;
}
.setup-float-card:hover .setup-float-halo {
  opacity: 1;
}
.setup-float-pulse {
  pointer-events: none;
  position: absolute;
  inset: 0;
  border-radius: inherit;
  box-shadow: 0 0 0 0 rgba(99, 102, 241, 0.22);
  opacity: 0;
  animation: setup-float-pulse 3s ease-in-out infinite;
}
.setup-float-card:hover .setup-float-pulse {
  opacity: 1;
}
@keyframes setup-float-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(99, 102, 241, 0);
  }
  50% {
    box-shadow: 0 0 0 18px rgba(99, 102, 241, 0);
  }
}

.setup-table-row {
  transition: background 0.35s ease;
}
.setup-table-row:hover {
  background: linear-gradient(90deg, rgba(239, 246, 255, 0.85), rgba(250, 245, 255, 0.65), rgba(253, 242, 248, 0.55));
}
.dark .setup-table-row:hover {
  background: rgba(255, 255, 255, 0.04);
}

.setup-progress-bg {
  background: rgba(226, 232, 240, 0.85);
}
.dark .setup-progress-bg {
  background: rgba(255, 255, 255, 0.08);
}
.setup-progress-fill {
  position: relative;
  overflow: hidden;
  background: linear-gradient(90deg, #3b82f6, #4f46e5, #7c3aed, #db2777, #ec4899);
  background-size: 200% 100%;
  animation: setup-bar-shift 4s linear infinite;
}
.setup-progress-fill::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(105deg, transparent, rgba(255, 255, 255, 0.45), transparent);
  transform: translateX(-100%);
  animation: setup-bar-glint 2.2s ease-in-out infinite;
}
@keyframes setup-bar-shift {
  0% {
    background-position: 0% 50%;
  }
  100% {
    background-position: 200% 50%;
  }
}
@keyframes setup-bar-glint {
  0% {
    transform: translate3d(-100%, 0, 0);
  }
  100% {
    transform: translate3d(100%, 0, 0);
  }
}

.setup-cta {
  position: relative;
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 1.25rem;
  border: 1px solid rgba(255, 255, 255, 0.35);
  padding: 1.15rem 1.25rem;
  color: #fff;
  background: linear-gradient(90deg, #3b82f6, #8b5cf6, #ec4899);
  cursor: pointer;
  transform-style: preserve-3d;
  transition:
    transform 0.4s cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 0.4s ease;
  box-shadow:
    0 20px 44px rgba(59, 130, 246, 0.28),
    0 10px 28px rgba(236, 72, 153, 0.18);
  will-change: transform;
}
.setup-cta:disabled {
  cursor: not-allowed;
  opacity: 0.55;
  transform: none;
  box-shadow: none;
}
.setup-cta:not(:disabled):hover {
  transform: translate3d(0, -8px, 0) scale(1.06) rotateX(5deg);
  box-shadow:
    0 28px 56px rgba(59, 130, 246, 0.35),
    0 16px 40px rgba(236, 72, 153, 0.25);
}
.setup-cta__pulse {
  position: absolute;
  inset: -30%;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.22), transparent 55%);
  opacity: 0.35;
  animation: setup-cta-pulse 3s ease-in-out infinite;
  pointer-events: none;
}
@keyframes setup-cta-pulse {
  0%,
  100% {
    opacity: 0.28;
    transform: scale(0.92);
  }
  50% {
    opacity: 0.62;
    transform: scale(1.05);
  }
}
.setup-cta__spin {
  position: absolute;
  inset: -60%;
  background: conic-gradient(from 0deg, rgba(59, 130, 246, 0.35), rgba(139, 92, 246, 0.35), rgba(236, 72, 153, 0.35), rgba(59, 130, 246, 0.35));
  opacity: 0.22;
  animation: setup-cta-spin 10s linear infinite;
  pointer-events: none;
}
@keyframes setup-cta-spin {
  to {
    transform: rotate(360deg);
  }
}
.setup-cta__shine {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 38%;
  pointer-events: none;
  background: linear-gradient(105deg, transparent, rgba(255, 255, 255, 0.55), transparent);
  opacity: 0.55;
}
.setup-cta__shine--a {
  left: -60%;
  animation: setup-cta-shine-a 4.5s ease-in-out infinite;
}
.setup-cta__shine--b {
  right: -60%;
  animation: setup-cta-shine-b 4.5s ease-in-out infinite;
}
@keyframes setup-cta-shine-a {
  0% {
    transform: translate3d(-20%, 0, 0);
  }
  100% {
    transform: translate3d(320%, 0, 0);
  }
}
@keyframes setup-cta-shine-b {
  0% {
    transform: translate3d(20%, 0, 0);
  }
  100% {
    transform: translate3d(-320%, 0, 0);
  }
}
.setup-cta__corners::before,
.setup-cta__corners::after {
  content: '';
  position: absolute;
  width: 72px;
  height: 72px;
  border-radius: 9999px;
  filter: blur(28px);
  pointer-events: none;
  opacity: 0.45;
  animation: setup-cta-corner-breath 2.6s ease-in-out infinite;
}
.setup-cta__corners::before {
  top: -28px;
  left: -18px;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.55), transparent 70%);
}
.setup-cta__corners::after {
  bottom: -32px;
  right: -20px;
  background: radial-gradient(circle, rgba(236, 72, 153, 0.5), transparent 70%);
  animation-delay: 0.4s;
}
@keyframes setup-cta-corner-breath {
  0%,
  100% {
    opacity: 0.35;
    transform: scale(0.9);
  }
  50% {
    opacity: 0.65;
    transform: scale(1.05);
  }
}
.setup-cta__ripple {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.setup-cta__ripple::before,
.setup-cta__ripple::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  border: 1px solid rgba(255, 255, 255, 0.45);
  opacity: 0;
  animation: setup-cta-ripple 3.2s ease-out infinite;
}
.setup-cta__ripple::after {
  animation-delay: 1.1s;
}
@keyframes setup-cta-ripple {
  0% {
    transform: scale(0.92);
    opacity: 0.45;
  }
  100% {
    transform: scale(1.12);
    opacity: 0;
  }
}
.setup-cta__particles {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.35s ease;
}
.setup-cta:hover:not(:disabled) .setup-cta__particles {
  opacity: 1;
}
.setup-cta__particle {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 5px;
  height: 5px;
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.85);
  opacity: 0;
  transform: translate3d(-50%, -50%, 0);
  animation: none;
}
.setup-cta:hover:not(:disabled) .setup-cta__particle {
  animation: setup-cta-burst 0.75s ease-out forwards;
}
.setup-cta__particle:nth-child(1) {
  animation-delay: 0ms;
}
.setup-cta__particle:nth-child(2) {
  animation-delay: 40ms;
}
.setup-cta__particle:nth-child(3) {
  animation-delay: 80ms;
}
.setup-cta__particle:nth-child(4) {
  animation-delay: 120ms;
}
.setup-cta__particle:nth-child(5) {
  animation-delay: 160ms;
}
.setup-cta__particle:nth-child(6) {
  animation-delay: 200ms;
}
.setup-cta__particle:nth-child(7) {
  animation-delay: 240ms;
}
.setup-cta__particle:nth-child(8) {
  animation-delay: 280ms;
}
@keyframes setup-cta-burst {
  0% {
    opacity: 1;
    transform: translate3d(-50%, -50%, 0) rotate(var(--a)) translate3d(0, 0, 0) scale(0.4);
  }
  100% {
    opacity: 0;
    transform: translate3d(-50%, -50%, 0) rotate(var(--a)) translate3d(0, -52px, 0) scale(1);
  }
}

.config-card {
  @apply rounded-2xl border p-5;
  background: rgba(255, 255, 255, 0.8);
  border-color: rgba(229, 231, 235, 0.65);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
  transition:
    border-color 0.35s ease,
    box-shadow 0.45s ease,
    background 0.35s ease;
}
.config-card:hover {
  border-color: rgba(129, 140, 248, 0.28);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.1);
}
.dark .config-card {
  background: rgba(12, 15, 23, 0.88);
  border-color: rgba(255, 255, 255, 0.08);
  box-shadow: none;
}
.dark .config-card:hover {
  border-color: rgba(129, 140, 248, 0.22);
}

.config-label {
  @apply block text-sm font-bold mb-3;
  color: rgb(51, 65, 85);
}
.dark .config-label {
  color: var(--text-primary);
}

.config-input {
  @apply w-full px-4 py-3 rounded-xl border outline-none transition-all;
  background: transparent;
  border-color: rgb(203, 213, 225);
  color: rgb(15, 23, 42);
}
.dark .config-input {
  /* 暗色模式：输入框背景比卡片更深 */
  background: var(--bg-elevated-0);
  border-color: var(--border-default);
  color: var(--text-primary);
}
.config-input::placeholder {
  color: rgb(148, 163, 184);
}
.dark .config-input::placeholder {
  color: var(--text-tertiary);
}
.config-input:focus {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-primary) 30%, transparent);
}
.dark .config-input:focus {
  border-color: var(--border-hover);
}

/* —— 配置页：柔和选择器（方案 A 天蓝主导） —— */
.setup-selector-enter {
  animation: setup-selector-pop 0.4s cubic-bezier(0.22, 1, 0.36, 1) both;
}
@keyframes setup-selector-pop {
  from {
    opacity: 0;
    transform: translate3d(0, 10px, 0) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0) scale(1);
  }
}

.setup-sel {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  cursor: pointer;
  border-radius: 0.5rem;
  transition:
    transform 0.25s ease-out,
    background 0.3s ease-out,
    border-color 0.3s ease-out,
    box-shadow 0.3s ease-out,
    color 0.3s ease-out;
}
.setup-sel:active {
  transform: scale(0.98);
}

.setup-sel-model {
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  font-weight: 500;
}
.setup-sel-model--off {
  border: 1px solid #e5e7eb;
  background: #ffffff;
  color: #6b7280;
}
.setup-sel-model--off:hover {
  background: linear-gradient(135deg, rgba(224, 242, 254, 0.4) 0%, #ffffff 100%);
  border-color: #bae6fd;
  transform: translate3d(0, -2px, 0);
  box-shadow: 0 2px 8px rgba(147, 197, 253, 0.12);
}
.setup-sel-model--on {
  border: 1.5px solid #a5b4fc;
  color: #4c1d95;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(165, 180, 252, 0.15);
  background: linear-gradient(135deg, rgba(219, 234, 254, 0.95) 0%, rgba(224, 231, 255, 0.95) 50%, rgba(243, 232, 255, 0.95) 100%);
}
.setup-sel-model--on::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: rgba(255, 255, 255, 0.5);
  pointer-events: none;
}
.setup-sel-model__shine {
  position: absolute;
  inset: 0;
  z-index: 0;
  background: linear-gradient(105deg, transparent, rgba(255, 255, 255, 0.22), transparent);
  animation: setup-model-shine 2s linear infinite;
  pointer-events: none;
}
@keyframes setup-model-shine {
  0% {
    transform: translate3d(-100%, 0, 0);
  }
  100% {
    transform: translate3d(100%, 0, 0);
  }
}
.setup-sel-model--on .setup-sel-model__ico {
  animation: setup-ico-float 2.2s ease-in-out infinite;
}
@keyframes setup-ico-float {
  0%,
  100% {
    transform: translate3d(0, 0, 0);
  }
  50% {
    transform: translate3d(0, -2px, 0);
  }
}

.dark .setup-sel-model--off {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.12);
  color: #94a3b8;
}
.dark .setup-sel-model--off:hover {
  background: rgba(30, 58, 138, 0.25);
  border-color: rgba(125, 211, 252, 0.35);
  color: #e2e8f0;
}
.dark .setup-sel-model--on {
  color: #e9d5ff;
  border-color: rgba(165, 180, 252, 0.55);
  background: linear-gradient(135deg, rgba(30, 58, 138, 0.55), rgba(49, 46, 129, 0.5), rgba(76, 29, 149, 0.45));
}
.dark .setup-sel-model--on::before {
  background: rgba(255, 255, 255, 0.08);
}

.setup-sel-type {
  min-height: 2.75rem;
  min-width: 3.25rem;
  padding: 0.35rem 0.45rem;
  border-radius: 0.75rem;
}
.setup-sel-type__txt {
  font-size: 0.7rem;
  font-weight: 500;
  line-height: 1.1;
  max-width: 4rem;
}
.setup-sel-type--off {
  border: 1px solid #e5e7eb;
  background: #ffffff;
  color: #6b7280;
  font-size: 1rem;
}
.setup-sel-type--off:hover {
  transform: scale(1.08);
  box-shadow: 0 4px 12px rgba(147, 197, 253, 0.18);
  border-color: #cbd5e1;
}
.setup-sel-type--on {
  border: 2px solid #93c5fd;
  background: linear-gradient(135deg, #bfdbfe 0%, #c7d2fe 50%, #ddd6fe 100%);
  color: #3730a3;
  font-weight: 700;
  box-shadow: 0 4px 12px rgba(147, 197, 253, 0.22);
}
.setup-sel-type--on::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: rgba(255, 255, 255, 0.3);
  pointer-events: none;
}
.setup-sel-type__pulse {
  position: absolute;
  inset: -3px;
  border-radius: inherit;
  border: 2px solid #93c5fd;
  opacity: 0;
  pointer-events: none;
  animation: setup-type-pulse 2s ease-out infinite;
}
@keyframes setup-type-pulse {
  0% {
    transform: scale(1);
    opacity: 0.38;
  }
  100% {
    transform: scale(1.32);
    opacity: 0;
  }
}
.setup-sel-type--on:hover {
  transform: scale(1.1);
  box-shadow: 0 6px 16px rgba(147, 197, 253, 0.3);
}
.dark .setup-sel-type--off {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.12);
  color: #94a3b8;
}
.dark .setup-sel-type--off:hover {
  border-color: rgba(125, 211, 252, 0.35);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.35);
  color: #e2e8f0;
}
.dark .setup-sel-type--on {
  color: #e0e7ff;
  border-color: rgba(147, 197, 253, 0.55);
  background: linear-gradient(135deg, rgba(30, 64, 175, 0.45), rgba(55, 48, 163, 0.42), rgba(76, 29, 149, 0.4));
}

.setup-diff__track-wrap {
  position: relative;
  height: 36px;
  display: flex;
  align-items: center;
}
.setup-diff__track {
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  height: 8px;
  transform: translateY(-50%);
  border-radius: 9999px;
  background: #f3f4f6;
  overflow: hidden;
  pointer-events: none;
}
.dark .setup-diff__track {
  background: rgba(255, 255, 255, 0.08);
}
.setup-diff__fill {
  height: 100%;
  border-radius: 9999px;
  background: linear-gradient(90deg, #93c5fd, #a5b4fc, #c4b5fd);
  transition: width 0.3s ease-out;
}
.setup-diff__range {
  position: relative;
  z-index: 2;
  width: 100%;
  height: 36px;
  margin: 0;
  background: transparent;
  -webkit-appearance: none;
  appearance: none;
  cursor: pointer;
}
.setup-diff__range:focus {
  outline: none;
}
.setup-diff__range::-webkit-slider-runnable-track {
  height: 8px;
  background: transparent;
  border: none;
}
.setup-diff__range::-moz-range-track {
  height: 8px;
  background: transparent;
  border: none;
}
.setup-diff__range::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 22px;
  height: 22px;
  margin-top: -7px;
  border-radius: 9999px;
  border: 2px solid #a5b4fc;
  background:
    radial-gradient(circle at 50% 50%, #38bdf8 0 32%, #a78bfa 33% 55%, #ffffff 56% 100%);
  box-shadow:
    0 2px 8px rgba(165, 180, 252, 0.35),
    0 0 0 6px rgba(165, 180, 252, 0.12);
  animation: setup-thumb-glow 2s ease-in-out infinite;
}
.setup-diff__range::-moz-range-thumb {
  width: 22px;
  height: 22px;
  border-radius: 9999px;
  border: 2px solid #a5b4fc;
  background: radial-gradient(circle at 50% 50%, #38bdf8 0 32%, #a78bfa 33% 55%, #ffffff 56% 100%);
  box-shadow: 0 2px 8px rgba(165, 180, 252, 0.35);
}
@keyframes setup-thumb-glow {
  0%,
  100% {
    box-shadow:
      0 2px 8px rgba(165, 180, 252, 0.35),
      0 0 0 6px rgba(165, 180, 252, 0.12);
  }
  50% {
    box-shadow:
      0 2px 10px rgba(165, 180, 252, 0.45),
      0 0 0 10px rgba(165, 180, 252, 0.06);
  }
}

/* 椋庢牸鍗＄墖鎸夐挳 */
.style-card-btn {
  @apply rounded-xl border p-3 text-left;
  transition:
    transform 0.35s cubic-bezier(0.22, 1, 0.36, 1),
    border-color 0.25s ease,
    box-shadow 0.35s ease,
    background-color 0.25s ease;
  will-change: transform;
}
.style-card-active {
  border-color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 5%, transparent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-primary) 30%, transparent);
}
.style-card-idle {
  border-color: rgb(226, 232, 240);
  background: transparent;
}
.style-card-idle:hover {
  border-color: rgb(203, 213, 225);
  background: rgb(248, 250, 252);
}
.dark .style-card-idle {
  border-color: var(--border-default);
  background: transparent;
}
.dark .style-card-idle:hover {
  border-color: var(--border-hover);
  background: rgba(255, 255, 255, 0.03);
}
.style-card-title {
  @apply text-sm font-bold;
  color: rgb(51, 65, 85);
}
.dark .style-card-title {
  color: var(--text-primary);
}
.style-card-desc {
  @apply text-xs mt-0.5;
  color: rgb(148, 163, 184);
}
.dark .style-card-desc {
  color: var(--text-tertiary);
}

/* 杈呭姪鏂囧瓧 */
.text-helper {
  @apply text-xs;
  color: rgb(148, 163, 184);
}
.dark .text-helper {
  color: var(--text-tertiary);
}

.text-secondary-label {
  @apply text-sm;
  color: rgb(71, 85, 105);
}
.dark .text-secondary-label {
  color: var(--text-secondary);
}

/* 鏂囦欢涓婁紶 */
input[type="file"] {
  color: rgb(100, 116, 139);
}
.dark input[type="file"] {
  color: var(--text-secondary);
}

select.config-input {
  @apply dark:[&>option]:bg-slate-900;
}

@media (prefers-reduced-motion: reduce) {
  .setup-enter,
  .setup-selector-enter,
  .setup-rainbow-stat,
  .setup-badge::after,
  .setup-progress-fill,
  .setup-progress-fill::after,
  .setup-cta__pulse,
  .setup-cta__spin,
  .setup-cta__shine,
  .setup-cta__ripple::before,
  .setup-cta__ripple::after,
  .setup-float-pulse,
  .setup-icon-glow,
  .setup-sel-model__shine,
  .setup-sel-type__pulse,
  .setup-diff__range::-webkit-slider-thumb,
  .setup-diff__range::-moz-range-thumb,
  .setup-sel-model--on .setup-sel-model__ico {
    animation: none !important;
  }
  .setup-enter {
    opacity: 1;
    transform: none;
  }
  .setup-tilt-card:hover,
  .setup-cta:not(:disabled):hover,
  .setup-style-cell:hover {
    transform: none;
  }
}
</style>
