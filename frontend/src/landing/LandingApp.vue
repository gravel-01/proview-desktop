<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { animate, inView } from 'motion'
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  FileText,
  MessageSquare,
  Sparkles,
  Target,
  Terminal,
  XCircle,
  Zap,
} from 'lucide-vue-next'

const prefersReduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ?? false

const spotlightRoot = ref<HTMLElement | null>(null)
const termLinePtr = ref(0)
const termCharPtr = ref(0)
const terminalProgress = ref(0)
let terminalTimer: ReturnType<typeof setTimeout> | null = null
let progressTimer: ReturnType<typeof setInterval> | null = null
let resetTimer: ReturnType<typeof setTimeout> | null = null

function onMouseMove(e: MouseEvent) {
  const el = spotlightRoot.value
  if (!el) return
  el.style.setProperty('--mx', `${e.clientX}px`)
  el.style.setProperty('--my', `${e.clientY}px`)
}

const features = [
  {
    icon: FileText,
    title: '简历深度解析',
    description: '上传 PDF 简历即刻获取，OCR + LangChain 自动提取关键信息，生成针对性问题。',
    accent: 'from-amber-500 via-orange-500 to-amber-600',
    glow: 'from-amber-400 to-orange-500',
  },
  {
    icon: MessageSquare,
    title: 'LangChain Agent 驱动',
    description: 'DeepSeek LLM + Google 视频工具集成，多模态智能问答，真实仿真面试流程。',
    accent: 'from-sky-500 via-indigo-500 to-sky-600',
    glow: 'from-sky-400 to-indigo-500',
  },
  {
    icon: Target,
    title: '量化评估报告',
    description: '基于标准量表的评分方式，全方位评估表达、技术能力与Supabase数据留存。',
    accent: 'from-rose-500 via-pink-500 to-rose-600',
    glow: 'from-rose-400 to-pink-500',
  },
]

const steps = [
  { icon: Sparkles, label: '定制概述', desc: '定制简历、风格、上传文件', tint: 'from-blue-500 to-cyan-500' },
  { icon: MessageSquare, label: 'AI 解析训练', desc: 'OCR提取 + 结构语言理解', tint: 'from-purple-500 to-pink-500' },
  { icon: FileText, label: '多轮对话', desc: '自适应问难度覆盖度测试', tint: 'from-pink-500 to-rose-500' },
  { icon: Zap, label: '评估报告', desc: '综合评分与深度改进建议', tint: 'from-orange-500 to-yellow-500' },
]

const beforeIssues = [
  '面试问题重复率高、准备盲目',
  '缺乏即时反馈机制无法大量人工测试',
  '找不到模拟环境，紧张失误高发',
  '通用题目缺针对性低效准备',
]

const afterBenefits = [
  'S1AI 根据简历动态生成、多变题型',
  '每题即时语言+技术双维度反馈',
  '随手实战演练，降低真实面试压力',
  '问题紧贴简历，高频出现正式面试真题',
]

const terminalLines = [
  { type: 'command', text: '> interview_agent.py', gradient: 'from-gray-700 via-gray-800 to-gray-700' },
  { type: 'blank', text: '', gradient: '' },
  { type: 'output', text: '> Init LangChain_Agent --model=gpt4', gradient: 'from-sky-600 via-blue-600 to-indigo-600' },
  { type: 'status', text: '✓ [OCR] 简历解析 (1.2s) - 提取 2,847 个字', gradient: 'from-emerald-600 via-teal-600 to-green-600' },
  { type: 'blank', text: '', gradient: '' },
  { type: 'json', text: '{', gradient: 'from-violet-600 via-purple-600 to-fuchsia-600' },
  { type: 'json', text: '  # Agent.invoke(initial_strategy)...', gradient: 'from-gray-400 via-gray-500 to-gray-400' },
  { type: 'json', text: '  "name": "李* *知识图谱工程师, 5 年ML/LLM经验",', gradient: 'from-rose-600 via-pink-600 to-fuchsia-600' },
  { type: 'json', text: '  "stack": ["PyTorch", "LangChain", "Hugging Face"]', gradient: 'from-indigo-600 via-purple-600 to-violet-600' },
  { type: 'json', text: '}', gradient: 'from-violet-600 via-purple-600 to-fuchsia-600' },
  { type: 'blank', text: '', gradient: '' },
  { type: 'output', text: '> Generating follow-up questions', gradient: 'from-sky-600 via-blue-600 to-cyan-600' },
]

type TerminalLineDef = (typeof terminalLines)[number]

const displayTerminalLines = computed((): TerminalLineDef[] => {
  const ptr = termLinePtr.value
  const cptr = termCharPtr.value
  const out: TerminalLineDef[] = []
  for (let i = 0; i < ptr; i++) {
    out.push(terminalLines[i]!)
  }
  if (ptr < terminalLines.length) {
    const L = terminalLines[ptr]!
    if (L.type === 'blank') {
      out.push(L)
    } else if (cptr > 0) {
      out.push({ ...L, text: L.text.slice(0, cptr) })
    }
  }
  return out
})

const showTerminalCursor = computed(() => {
  if (termLinePtr.value >= terminalLines.length) return false
  const L = terminalLines[termLinePtr.value]
  if (!L || L.type === 'blank') return false
  return termCharPtr.value < L.text.length
})

const showTerminalProgress = computed(() => termLinePtr.value >= terminalLines.length)

function isActiveTypingRow(rowIndex: number) {
  return (
    rowIndex === displayTerminalLines.value.length - 1
    && termLinePtr.value < terminalLines.length
    && terminalLines[termLinePtr.value]?.type !== 'blank'
    && termCharPtr.value > 0
  )
}

function onTrafficEnter(e: MouseEvent) {
  if (prefersReduceMotion) return
  const el = e.currentTarget as HTMLElement
  animate(el, { scale: 1.3 }, { type: 'spring', stiffness: 400, damping: 17 })
}

function onTrafficLeave(e: MouseEvent) {
  if (prefersReduceMotion) return
  const el = e.currentTarget as HTMLElement
  animate(el, { scale: 1 }, { type: 'spring', stiffness: 400, damping: 17 })
}

function clearTerminalTimers() {
  if (terminalTimer) {
    clearTimeout(terminalTimer)
    terminalTimer = null
  }
  if (progressTimer) {
    clearInterval(progressTimer)
    progressTimer = null
  }
  if (resetTimer) {
    clearTimeout(resetTimer)
    resetTimer = null
  }
}

function tickTerminal() {
  if (terminalTimer) {
    clearTimeout(terminalTimer)
    terminalTimer = null
  }
  if (termLinePtr.value >= terminalLines.length) {
    progressTimer = setInterval(() => {
      terminalProgress.value += 2
      if (terminalProgress.value >= 100) {
        terminalProgress.value = 100
        if (progressTimer) {
          clearInterval(progressTimer)
          progressTimer = null
        }
        resetTimer = setTimeout(() => {
          termLinePtr.value = 0
          termCharPtr.value = 0
          terminalProgress.value = 0
          tickTerminal()
        }, 1000)
      }
    }, 30)
    return
  }

  const L = terminalLines[termLinePtr.value]
  if (!L) return

  const charDelay = prefersReduceMotion ? 0 : 20
  const lineGap = prefersReduceMotion ? 120 : 400

  if (L.type === 'blank') {
    terminalTimer = setTimeout(() => {
      termLinePtr.value += 1
      termCharPtr.value = 0
      tickTerminal()
    }, lineGap)
    return
  }

  if (termCharPtr.value < L.text.length) {
    if (prefersReduceMotion) {
      termCharPtr.value = L.text.length
      terminalTimer = setTimeout(tickTerminal, lineGap)
    } else {
      termCharPtr.value += 1
      terminalTimer = setTimeout(tickTerminal, charDelay)
    }
    return
  }

  termLinePtr.value += 1
  termCharPtr.value = 0
  terminalTimer = setTimeout(tickTerminal, lineGap)
}

function animateTerminal() {
  clearTerminalTimers()
  tickTerminal()
}

function setupReveals() {
  const blocks = Array.from(document.querySelectorAll<HTMLElement>('[data-reveal]'))
  if (prefersReduceMotion) return () => {}

  for (const el of blocks) {
    el.style.willChange = 'transform, opacity'
    el.style.transform = 'translate3d(0, 22px, 0)'
    el.style.opacity = '0'
  }

  const cleanups = blocks.map((el) =>
    inView(
      el,
      () => {
        animate(
          el as any,
          { opacity: [0, 1], transform: ['translate3d(0, 22px, 0)', 'translate3d(0, 0, 0)'] } as any,
          { duration: 0.75, easing: [0.22, 1, 0.36, 1] } as any,
        )
        return () => {}
      },
      { margin: '0px 0px -12% 0px' },
    ),
  )

  return () => cleanups.forEach((c) => typeof c === 'function' && c())
}

let cleanupReveals: (() => void) | null = null

onMounted(() => {
  document.body.classList.add('min-h-screen')
  cleanupReveals = setupReveals()
  animateTerminal()
})

onBeforeUnmount(() => {
  cleanupReveals?.()
  clearTerminalTimers()
})
</script>

<template>
  <div
    ref="spotlightRoot"
    class="relative min-h-screen overflow-hidden bg-gradient-to-br from-orange-50/30 via-white to-sky-50/30 text-gray-900"
    @mousemove="onMouseMove"
  >
    <!-- Animated Background Elements -->
    <div class="pointer-events-none fixed inset-0 overflow-hidden">
      <div class="absolute -left-48 -top-48 h-[800px] w-[800px] rounded-full bg-gradient-to-br from-amber-50/50 via-orange-50/40 to-transparent blur-3xl pv-orb-a" />
      <div class="absolute -right-48 top-1/3 h-[700px] w-[700px] rounded-full bg-gradient-to-br from-sky-50/50 via-indigo-50/40 to-transparent blur-3xl pv-orb-b" />
      <div class="absolute bottom-0 left-1/3 h-[600px] w-[600px] rounded-full bg-gradient-to-br from-rose-50/40 via-pink-50/30 to-transparent blur-3xl pv-orb-c" />
      <div class="absolute left-1/2 top-1/2 h-[500px] w-[500px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-gradient-to-br from-teal-50/35 via-emerald-50/25 to-transparent blur-3xl pv-orb-d" />
      <div class="absolute inset-0 opacity-30 pv-wave-a" />
      <div class="absolute inset-0 opacity-20 pv-wave-b" />
      <div
        class="absolute top-1/4 -left-1/4 h-[600px] w-[600px] rounded-full bg-gradient-to-br from-amber-200 to-orange-200 opacity-30 blur-[120px]"
        :class="prefersReduceMotion ? '' : 'pv-blob-a'"
      />
      <div
        class="absolute bottom-1/4 -right-1/4 h-[600px] w-[600px] rounded-full bg-gradient-to-br from-sky-200 to-indigo-200 opacity-30 blur-[120px]"
        :class="prefersReduceMotion ? '' : 'pv-blob-b'"
      />
      <div
        class="absolute top-1/2 left-1/2 h-[400px] w-[400px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-gradient-to-br from-rose-200 to-pink-200 opacity-20 blur-[100px]"
        :class="prefersReduceMotion ? '' : 'pv-blob-c'"
      />
      <div class="absolute inset-0 opacity-[0.012]">
        <div class="absolute inset-0 pv-dot-mesh" />
      </div>
      <div class="absolute inset-0 opacity-[0.008]">
        <div class="absolute inset-0 pv-diagonal-mesh" />
      </div>
      <div class="absolute left-1/4 top-0 h-full w-px bg-gradient-to-b from-transparent via-amber-200/25 to-transparent pv-light-beam-a" />
      <div class="absolute right-1/3 top-0 h-full w-px bg-gradient-to-b from-transparent via-sky-200/25 to-transparent pv-light-beam-b" />
      <span v-for="i in 12" :key="`bg-particle-${i}`" class="pv-bg-particle" :style="{ left: `${10 + i * 7}%`, top: `${18 + (i * 7) % 62}%` }" />
      <div class="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-rose-100/20 via-transparent to-transparent" />
      <div class="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_left,_var(--tw-gradient-stops))] from-teal-100/20 via-transparent to-transparent" />
    </div>

    <!-- Cursor Spotlight Effect -->
    <div class="pointer-events-none fixed inset-0 z-30 pv-spotlight" />

    <!-- Header (keep existing logo mark) -->
    <header class="sticky top-0 z-50 overflow-hidden border-b backdrop-blur-2xl shadow-sm pv-header-shell" data-reveal>
      <div class="absolute inset-0 opacity-30 pv-header-sweep" />
      <div class="mx-auto max-w-6xl px-6 py-6">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-6">
            <!-- IMPORTANT: keep existing logo unchanged -->
            <div class="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-lg shadow-blue-500/30">
              <Bot class="h-7 w-7" />
            </div>
            <span class="bg-gradient-to-r from-blue-700 via-blue-600 to-sky-600 bg-clip-text text-2xl font-bold text-transparent">
              ProView AI
            </span>
          </div>

          <nav class="hidden items-center gap-7 md:flex">
            <a href="#features" class="pv-nav-link text-lg font-semibold text-gray-600">核心功能</a>
            <a href="#workflow" class="pv-nav-link text-lg font-semibold text-gray-600">工作原理</a>
            <a href="#contact" class="pv-nav-link text-lg font-semibold text-gray-600">联系我们</a>
          </nav>
          <a href="/app.html" class="group relative overflow-hidden rounded-2xl px-12 py-5 text-xl font-semibold text-white shadow-lg pv-top-cta">
            <span class="relative z-10">立即开始</span>
            <span class="absolute inset-0 pv-top-cta-shine" />
          </a>
        </div>
      </div>
    </header>

    <!-- Hero Section -->
    <section class="relative px-6 pb-20 pt-16">
      <div class="mx-auto max-w-6xl text-center">
        <div class="text-center">
          <div data-reveal>
            <h1 class="mb-6 text-6xl font-bold leading-[1.05] tracking-[-0.022em] text-gray-900 md:text-7xl">
              <span class="inline-block">
                驱动面试训练的
              </span>
              <br />
              <span class="relative inline-block text-gray-900">
                核心引擎
              </span>
            </h1>
          </div>

          <p class="mx-auto mb-8 max-w-2xl text-xl leading-[1.7] text-gray-600" data-reveal>
            深度整合你的简历，结合量表主题自动创建仿真AI Agent 考核。
          </p>

          <div class="relative mx-auto mt-2 max-w-[860px]" data-reveal>
            <div class="absolute -inset-6 rounded-3xl bg-gradient-to-tr from-amber-500/8 via-rose-500/6 to-sky-500/8 blur-[38px]" />
            <div
              class="pv-terminal-stage group relative [perspective:1400px]"
              :class="{ 'pv-terminal-stage--rm': prefersReduceMotion }"
            >
              <div class="pv-terminal-halo-outer pointer-events-none absolute -inset-10 z-0 rounded-[2.25rem]" aria-hidden="true" />
              <div class="pv-terminal-halo-inner pointer-events-none absolute -inset-5 z-0 rounded-[2rem]" aria-hidden="true" />
              <div class="pv-terminal-float relative z-[1]">
                <div class="pv-terminal-outer-ring rounded-3xl p-px">
                  <div class="pv-terminal-card-shell relative overflow-hidden rounded-[calc(1.5rem-2px)] border border-gray-200/55 bg-white/80 p-1 shadow-xl backdrop-blur-xl">
                    <div class="pv-terminal-inner relative overflow-hidden rounded-[1.35rem] text-left">
                      <div class="relative z-[2] overflow-hidden border-b border-gray-200/45 px-5 pb-3 pt-4 sm:px-6 sm:pb-3.5 sm:pt-5">
                        <div class="pointer-events-none absolute inset-0 z-[1] overflow-hidden pv-terminal-header-scan" aria-hidden="true" />
                        <div class="relative z-[2] flex items-center justify-between">
                          <div class="flex items-center gap-2 text-xs font-mono text-gray-600">
                            <Terminal class="h-4 w-4 shrink-0 text-gray-500" />
                            interview_agent.py
                          </div>
                          <div class="flex gap-2">
                            <span
                              class="pv-traffic-dot pv-traffic-dot--red block h-2.5 w-2.5 rounded-full bg-red-400/90"
                              role="presentation"
                              @mouseenter="onTrafficEnter"
                              @mouseleave="onTrafficLeave"
                            />
                            <span
                              class="pv-traffic-dot pv-traffic-dot--blue block h-2.5 w-2.5 rounded-full bg-sky-400/90"
                              role="presentation"
                              @mouseenter="onTrafficEnter"
                              @mouseleave="onTrafficLeave"
                            />
                            <span
                              class="pv-traffic-dot pv-traffic-dot--green block h-2.5 w-2.5 rounded-full bg-emerald-400/90"
                              role="presentation"
                              @mouseenter="onTrafficEnter"
                              @mouseleave="onTrafficLeave"
                            />
                          </div>
                        </div>
                      </div>

                      <div class="relative z-[2] min-h-[292px] px-5 pb-5 pt-1 sm:px-6 sm:pb-6">
                        <div class="pointer-events-none absolute inset-0 z-0 overflow-hidden rounded-b-[1.35rem]">
                          <div class="pv-terminal-bg-1 absolute inset-0" aria-hidden="true" />
                          <div class="pv-terminal-bg-2 absolute inset-0" aria-hidden="true" />
                          <span
                            v-for="pi in 8"
                            :key="`tp-${pi}`"
                            class="pv-terminal-particle absolute block rounded-full"
                            :style="{ '--tp-i': pi - 1 } as Record<string, number>"
                          />
                        </div>

                        <div class="relative z-[1] mt-4 font-mono text-sm">
                          <template v-for="(line, idx) in displayTerminalLines" :key="`tl-${idx}-${line.type}`">
                            <div v-if="line.type === 'blank'" class="mb-2 h-4" />
                            <div
                              v-else
                              class="pv-terminal-line-row relative mb-2"
                              :class="{
                                'pv-terminal-line--glow': line.type === 'output' || line.type === 'status',
                              }"
                            >
                              <template v-if="isActiveTypingRow(idx)">
                                <span
                                  v-for="(ch, ci) in line.text.split('')"
                                  :key="`c-${idx}-${ci}`"
                                  class="pv-term-char inline bg-gradient-to-r bg-clip-text font-medium text-transparent"
                                  :class="line.gradient"
                                  :style="{ '--cd': ci * 20 } as Record<string, number>"
                                >{{ ch === ' ' ? '\u00a0' : ch }}</span>
                              </template>
                              <span
                                v-else
                                class="inline bg-gradient-to-r bg-clip-text font-medium text-transparent"
                                :class="line.gradient"
                              >{{ line.text }}</span>
                            </div>
                          </template>

                          <span
                            v-if="showTerminalCursor"
                            class="pv-terminal-cursor pv-terminal-cursor-glow ml-1 inline-block align-middle"
                          />

                          <div v-if="showTerminalProgress" class="pv-term-progress-wrap relative mt-4">
                            <div class="mb-3 flex items-center justify-between">
                              <span class="bg-gradient-to-r from-gray-600 via-gray-700 to-gray-600 bg-clip-text text-xs font-medium text-transparent">
                                生成中
                              </span>
                              <span class="pv-term-pct-rainbow text-xs font-mono font-semibold tabular-nums">
                                {{ terminalProgress }}%
                              </span>
                            </div>
                            <div class="pv-term-progress-track relative h-3 w-full overflow-hidden rounded-full shadow-inner">
                              <div class="absolute inset-0 bg-gradient-to-r from-slate-100 via-white to-slate-100" />
                              <div class="pv-term-progress-track-scan pointer-events-none absolute inset-0 opacity-50" aria-hidden="true" />
                              <div
                                class="pv-term-progress-fill relative h-full overflow-hidden rounded-full transition-[width] duration-100 ease-linear"
                                :style="{ width: `${terminalProgress}%` }"
                              >
                                <span class="pointer-events-none absolute inset-0 block overflow-hidden rounded-full" aria-hidden="true">
                                  <span class="pv-term-progress-shine" />
                                </span>
                                <span class="pv-term-progress-cap pointer-events-none absolute right-0 top-1/2 block size-3.5 -translate-y-1/2 translate-x-1/2 rounded-full" aria-hidden="true" />
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Features Section -->
    <section id="features" class="relative overflow-hidden py-22">
      <div class="mx-auto max-w-7xl px-6">
        <div class="mb-14 text-center" data-reveal>
          <div class="mb-6 inline-flex items-center gap-2 rounded-full border border-amber-200 bg-gradient-to-r from-amber-50 to-sky-50 px-4 py-2 shadow-lg relative overflow-hidden">
            <span class="absolute inset-0 pv-pill-sweep" />
            <Sparkles class="h-4 w-4 text-amber-600" />
            <span class="text-xs font-semibold uppercase tracking-wide text-gray-700">核心功能</span>
          </div>
          <h2 class="mb-4 text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-gray-900 via-gray-800 to-gray-700 md:text-5xl">
            三大核心功能
          </h2>
          <p class="mx-auto max-w-2xl text-lg text-gray-600">
            AI驱动的智能面试训练系统，全方位提升你的面试竞争力
          </p>
        </div>

        <div class="grid gap-7 md:grid-cols-3">
          <div v-for="(f, index) in features" :key="f.title" class="group" data-reveal>
            <div class="relative h-full transition-transform duration-500 group-hover:-translate-y-4 group-hover:scale-[1.02]">
              <div class="relative h-full overflow-hidden rounded-3xl border border-gray-200/60 bg-gradient-to-br from-white via-white to-gray-50/30 p-8 backdrop-blur-xl shadow-[0_30px_60px_-15px_rgba(0,0,0,0.08)] pv-feature-card">
                <div class="absolute left-0 right-0 top-0 h-1 bg-gradient-to-r" :class="f.accent" />
                <div class="absolute inset-0 opacity-0 transition-opacity duration-500 group-hover:opacity-[0.04] bg-gradient-to-br"
                     :class="index === 0 ? 'from-amber-500/30 to-orange-500/30' : index === 1 ? 'from-sky-500/30 to-indigo-500/30' : 'from-rose-500/30 to-pink-500/30'"
                />

                <div class="relative z-10">
                  <div class="mb-6">
                    <div class="relative inline-block">
                      <div class="absolute inset-0 rounded-2xl blur-2xl pv-icon-pulse" :class="`bg-gradient-to-br ${f.glow}`" />
                      <div
                        class="relative flex h-20 w-20 items-center justify-center rounded-2xl bg-gradient-to-br shadow-xl transition-transform duration-500 group-hover:scale-[1.15] pv-icon-wiggle"
                        :class="index === 0 ? 'from-amber-500 to-orange-600' : index === 1 ? 'from-sky-500 to-indigo-600' : 'from-rose-500 to-pink-600'"
                      >
                        <component :is="f.icon" class="h-10 w-10 text-white" :stroke-width="1.5" />
                        <span class="absolute inset-0 rounded-2xl bg-gradient-to-tr from-transparent via-white/30 to-transparent pv-shine" />
                      </div>
                    </div>
                  </div>

                  <div class="mb-3 text-sm font-semibold text-gray-400">{{ String(index + 1).padStart(2, '0') }}</div>

                  <h3 class="mb-3 text-xl font-bold text-gray-900">{{ f.title }}</h3>
                  <p class="mb-6 text-sm leading-relaxed text-gray-600">{{ f.description }}</p>

                  <div class="h-1 w-[60px] rounded-full bg-gradient-to-r"
                       :class="index === 0 ? 'from-amber-500 to-orange-500' : index === 1 ? 'from-sky-500 to-indigo-500' : 'from-rose-500 to-pink-500'"
                  />
                </div>

                <div class="absolute -bottom-8 -right-8 h-32 w-32 rounded-full bg-gradient-to-tl from-gray-100/50 to-transparent opacity-50 transition-opacity group-hover:opacity-70" />
              </div>

              <div class="absolute -inset-2 -z-10 rounded-3xl bg-gradient-to-br blur-xl opacity-0 transition-opacity duration-500 group-hover:opacity-100"
                   :class="index === 0 ? 'from-amber-500/20 to-orange-500/20' : index === 1 ? 'from-sky-500/20 to-indigo-500/20' : 'from-rose-500/20 to-pink-500/20'"
              />
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Process Section -->
    <section id="workflow" class="relative px-6 py-22">
      <div class="mx-auto max-w-5xl">
        <div class="mb-16 text-center" data-reveal>
          <h2 class="mb-4 text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-gray-900 via-gray-800 to-gray-700 md:text-5xl">
            极简四步，沉浸式训练
          </h2>
          <p class="text-lg text-gray-600">从意图智取到，全程 AI 驱动，无需人工干预。</p>
        </div>

        <div class="relative">
          <!-- Central flowing line -->
          <div class="absolute left-1/2 top-0 hidden w-1 -translate-x-1/2 md:block pv-timeline">
            <div class="h-full w-full rounded-full bg-gradient-to-b from-blue-400 via-purple-400 to-pink-400" />
            <div class="pv-flow-dot pv-flow-dot--a" />
            <div class="pv-flow-dot pv-flow-dot--b" />
            <div class="pv-flow-dot pv-flow-dot--c" />
            <div v-for="i in 4" :key="i" class="pv-ring" :style="{ top: `${(i - 1) * 25}%` }" />
          </div>

          <div v-for="(s, index) in steps" :key="s.label" class="relative mb-16 flex items-center gap-8 last:mb-0" :class="index % 2 === 0 ? 'md:flex-row' : 'md:flex-row-reverse'" data-reveal>
            <div class="flex-1">
              <div class="group relative overflow-hidden rounded-3xl border border-gray-200/60 bg-gradient-to-br from-white/90 to-white/70 p-7 shadow-xl backdrop-blur-xl transition-transform duration-500 hover:-translate-y-1 hover:scale-[1.03] pv-step-card">
                <div class="absolute inset-0 opacity-0 transition-opacity duration-500 group-hover:opacity-100 bg-gradient-to-br"
                     :class="index === 0 ? 'from-blue-500/5 to-cyan-500/5' : index === 1 ? 'from-purple-500/5 to-pink-500/5' : index === 2 ? 'from-pink-500/5 to-rose-500/5' : 'from-orange-500/5 to-yellow-500/5'"
                />

                <div class="absolute inset-0 rounded-3xl pv-border-shimmer" :style="{ '--pv-shimmer': index === 0 ? 'rgba(59, 130, 246, 0.1)' : index === 1 ? 'rgba(139, 92, 246, 0.1)' : index === 2 ? 'rgba(236, 72, 153, 0.1)' : 'rgba(249, 115, 22, 0.1)' } as any" />

                <div class="relative z-10">
                  <div class="flex items-start gap-4">
                    <div class="relative">
                      <div class="absolute inset-0 rounded-2xl blur-xl pv-icon-pulse" :class="`bg-gradient-to-br ${s.tint}`" />
                      <div class="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br shadow-lg pv-rotate-slow" :class="s.tint">
                        <component :is="s.icon" class="h-8 w-8 text-white" />
                        <span class="absolute inset-0 rounded-2xl bg-gradient-to-r from-transparent via-white/40 to-transparent pv-shine-sweep" />
                      </div>
                    </div>

                    <div class="flex-1">
                      <h3 class="mb-2 text-xl font-bold text-gray-900">{{ s.label }}</h3>
                      <p class="text-sm leading-relaxed text-gray-600">{{ s.desc }}</p>
                    </div>
                  </div>
                </div>

                <div class="absolute right-0 top-0 h-32 w-32 rounded-bl-full bg-gradient-to-br from-gray-100 to-transparent opacity-40 pv-corner-breath" />
                <span v-for="i in 3" :key="i" class="pv-particle"
                      :class="index === 0 ? 'bg-blue-400' : index === 1 ? 'bg-purple-400' : index === 2 ? 'bg-pink-400' : 'bg-orange-400'"
                      :style="{ left: `${20 + (i - 1) * 30}%`, top: `${30 + (i - 1) * 20}%` }"
                />
              </div>
            </div>

            <!-- Center number badge -->
            <div class="absolute left-1/2 hidden -translate-x-1/2 md:flex">
              <div class="relative flex h-10 w-10 items-center justify-center rounded-lg bg-gray-900 shadow-2xl pv-badge-pop">
                <span class="relative z-10 text-sm font-bold text-white">{{ index + 1 }}</span>
                <div class="absolute inset-0 rounded-xl border-2 border-gray-900 pv-step-ring" />
              </div>
            </div>

            <div class="hidden flex-1 md:block" />
          </div>
        </div>
      </div>
    </section>

    <!-- Before/After Comparison -->
    <section class="relative px-6 py-28">
      <div class="mx-auto max-w-6xl">
        <div class="mb-16 text-center" data-reveal>
          <div class="mb-6 inline-flex items-center gap-2 rounded-full border border-violet-200 bg-gradient-to-r from-sky-50 to-rose-50 px-4 py-2 shadow-lg relative overflow-hidden">
            <span class="absolute inset-0 pv-pill-sweep" />
            <Sparkles class="h-4 w-4 text-violet-600" />
            <span class="text-sm font-semibold text-violet-700">效果对比</span>
          </div>
          <h2 class="mb-6 text-5xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-gray-900 via-gray-800 to-gray-700">训练前 vs 训练后</h2>
          <p class="text-xl text-gray-600">体验AI驱动的面试训练带来的质的飞跃</p>
        </div>

        <div class="relative">
          <div class="mb-8 grid gap-8 md:grid-cols-2" data-reveal>
            <div class="text-center">
              <div class="inline-flex items-center gap-3 rounded-xl border border-gray-200 bg-gray-50 px-5 py-2.5 shadow-sm transition-all duration-300 hover:scale-[1.05] hover:shadow-md">
                <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-gray-200">
                  <XCircle class="h-5 w-5 text-gray-600" />
                </div>
                <div class="text-left">
                  <h3 class="text-base font-bold text-gray-900">传统方式</h3>
                  <p class="text-xs text-gray-500">效率低下</p>
                </div>
              </div>
            </div>

            <div class="text-center">
              <div class="inline-flex items-center gap-3 rounded-xl bg-gradient-to-r from-gray-800 to-gray-700 px-5 py-2.5 shadow-lg transition-all duration-300 hover:scale-[1.05] hover:shadow-xl">
                <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-white/20 backdrop-blur-sm">
                  <CheckCircle2 class="h-6 w-6 text-white" />
                </div>
                <div class="text-left">
                  <h3 class="text-base font-bold text-white">ProView AI</h3>
                  <p class="text-xs text-white/80">智能高效</p>
                </div>
              </div>
            </div>
          </div>

          <div class="space-y-4">
            <div v-for="(issue, index) in beforeIssues" :key="issue" class="grid items-center gap-8 md:grid-cols-2" data-reveal>
              <div class="group relative rounded-xl border border-gray-200 bg-white p-5 transition-all duration-300 hover:-translate-x-1 hover:border-gray-300 hover:shadow-lg">
                <div class="flex items-start gap-4">
                  <div class="mt-1 flex-shrink-0">
                    <div class="flex h-5 w-5 items-center justify-center rounded-md bg-gray-100">
                      <XCircle class="h-3.5 w-3.5 text-gray-500" />
                    </div>
                  </div>
                  <p class="flex-1 text-sm leading-relaxed text-gray-700">{{ issue }}</p>
                </div>
                <div class="absolute left-0 top-1/2 h-0 w-1 -translate-y-1/2 rounded-r-full bg-gradient-to-b from-gray-300 to-gray-400 transition-all duration-300 group-hover:h-2/3" />
              </div>

              <div class="group relative rounded-xl border border-sky-200/50 bg-gradient-to-br from-sky-50/40 via-violet-50/35 to-white p-5 shadow-lg transition-transform duration-300 hover:translate-x-1 hover:scale-[1.03] pv-compare-card">
                <div class="flex items-start gap-4">
                    <div class="mt-1 flex-shrink-0">
                    <div class="flex h-5 w-5 items-center justify-center rounded-md bg-gradient-to-br from-blue-500 to-violet-500 transition-transform duration-500 group-hover:rotate-[360deg]">
                      <CheckCircle2 class="h-3.5 w-3.5 text-white" />
                    </div>
                  </div>
                  <p class="flex-1 text-sm font-medium leading-relaxed text-gray-900">{{ afterBenefits[index] }}</p>
                </div>
                <span class="absolute inset-0 rounded-2xl bg-gradient-to-r from-transparent via-white/20 to-transparent pv-shine-sweep-once" />
                <div class="absolute inset-0 rounded-2xl bg-gradient-to-r from-blue-400/0 via-purple-400/0 to-pink-400/0 blur-xl transition-all duration-500 group-hover:from-blue-400/10 group-hover:via-purple-400/10 group-hover:to-pink-400/10" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- CTA Section -->
    <section id="contact" class="relative px-6 py-28">
      <div class="mx-auto max-w-4xl text-center">
        <div data-reveal>
          <h2 class="mb-6 text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-gray-900 via-gray-800 to-gray-700 md:text-5xl">
            准备好接受挑战了吗?
          </h2>
          <p class="pv-cta-subtitle mx-auto mb-9 text-gray-600">
            上传你的简历，以 AI 面试官开启针对性定制化一对一测评，迈向进一步自信与实力的跨越。
          </p>

          <a
            href="/app.html"
            class="group relative inline-flex items-center justify-center gap-3 overflow-hidden rounded-xl px-10 py-3.5 text-base font-semibold text-white shadow-2xl transition-transform duration-300 hover:-translate-y-1 hover:scale-[1.06] pv-hero-cta"
          >
            <span class="absolute inset-0 rounded-xl border-2 border-white/30 pv-ripple-a" />
            <span class="absolute inset-0 rounded-xl border-2 border-white/20 pv-ripple-b" />
            <span class="absolute inset-0 bg-gradient-to-r from-blue-500 via-violet-500 to-pink-500" />
            <span class="absolute inset-0 opacity-0 transition-opacity group-hover:opacity-100 bg-gradient-to-r from-sky-500 via-indigo-500 to-rose-500" />
            <span class="absolute inset-0 bg-gradient-to-r from-transparent via-white/40 to-transparent skew-x-12 pv-bottom-btn-shine" />
            <span v-for="i in 6" :key="`footer-cta-p-${i}`" class="pv-cta-particle" :style="{ '--pv-pi': `${i}` }" />
            <Sparkles class="relative z-10 h-5 w-5" />
            <span class="relative z-10">立即开始</span>
            <ArrowRight class="relative z-10 h-5 w-5 transition-transform duration-300 group-hover:translate-x-1" />
          </a>
        </div>
      </div>
    </section>

    <!-- Footer -->
    <footer class="relative overflow-hidden border-t border-gray-200 px-6 py-12">
      <div class="absolute inset-0 opacity-30 pv-header-sweep" />
      <div class="mx-auto max-w-6xl text-center text-sm text-gray-500">
        <p>© ProView AI Interview</p>
        <p class="mt-1 text-xs text-gray-400">Powered by LangChain / DeepSeek LLM</p>
      </div>
    </footer>
  </div>
</template>

<style>
/* Keep all effects local to landing root */
.pv-spotlight {
  background: radial-gradient(
    600px at var(--mx, 50%) var(--my, 50%),
    rgba(236, 72, 153, 0.08),
    transparent 80%
  );
}

.pv-header-sweep {
  background: linear-gradient(90deg, transparent, rgba(251, 191, 36, 0.05), transparent);
  animation: pv-header-sweep 9s linear infinite;
}

.pv-header-shell {
  background: linear-gradient(to right, rgba(255, 255, 255, 0.72), rgba(254, 243, 199, 0.3), rgba(224, 242, 254, 0.3), rgba(255, 255, 255, 0.72));
  border-color: rgba(251, 191, 36, 0.1);
  box-shadow: 0 1px 3px rgba(251, 191, 36, 0.1), 0 1px 2px rgba(147, 197, 253, 0.1);
}

@keyframes pv-header-sweep {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

.pv-dot-mesh {
  background-image: radial-gradient(circle, #000 1px, transparent 1px);
  background-size: 50px 50px;
}

.pv-diagonal-mesh {
  background-image: repeating-linear-gradient(45deg, transparent, transparent 80px, #000 80px, #000 81px);
}

.pv-wave-a {
  background: linear-gradient(120deg, transparent 0%, rgba(251, 191, 36, 0.05) 50%, transparent 100%);
  animation: pv-wave-a 20s linear infinite;
}

.pv-wave-b {
  background: linear-gradient(240deg, transparent 0%, rgba(147, 197, 253, 0.05) 50%, transparent 100%);
  animation: pv-wave-b 25s linear infinite;
}

@keyframes pv-orb-a {
  0%, 100% { transform: translate3d(0, 0, 0) scale(1) rotate(0deg); }
  50% { transform: translate3d(40px, -45px, 0) scale(1.12) rotate(90deg); }
}
@keyframes pv-orb-b {
  0%, 100% { transform: translate3d(0, 0, 0) scale(1.08) rotate(0deg); }
  50% { transform: translate3d(-45px, 50px, 0) scale(1) rotate(-90deg); }
}
@keyframes pv-orb-c {
  0%, 100% { transform: translate3d(0, 0, 0) scale(1) rotate(0deg); }
  50% { transform: translate3d(35px, -35px, 0) scale(1.16) rotate(180deg); }
}
@keyframes pv-orb-d {
  0%, 100% { transform: translate3d(-50%, -50%, 0) scale(1) rotate(0deg); opacity: 0.3; }
  50% { transform: translate3d(calc(-50% + 12px), calc(-50% - 20px), 0) scale(1.25) rotate(-180deg); opacity: 0.5; }
}
.pv-orb-a { animation: pv-orb-a 30s ease-in-out infinite; }
.pv-orb-b { animation: pv-orb-b 25s ease-in-out infinite; }
.pv-orb-c { animation: pv-orb-c 35s ease-in-out infinite; }
.pv-orb-d { animation: pv-orb-d 28s ease-in-out infinite; }

@keyframes pv-wave-a {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

@keyframes pv-wave-b {
  0% { transform: translateX(100%); }
  100% { transform: translateX(-100%); }
}

@keyframes pv-light-beam-a {
  0%, 100% { opacity: 0.1; transform: scaleY(0.8); }
  50% { opacity: 0.35; transform: scaleY(1.2); }
}
@keyframes pv-light-beam-b {
  0%, 100% { opacity: 0.1; transform: scaleY(1.2); }
  50% { opacity: 0.35; transform: scaleY(0.8); }
}
.pv-light-beam-a { animation: pv-light-beam-a 8s ease-in-out infinite; transform-origin: center; }
.pv-light-beam-b { animation: pv-light-beam-b 10s ease-in-out infinite 2s; transform-origin: center; }

@keyframes pv-bg-particle {
  0%, 100% { transform: translate3d(0, 0, 0) scale(0.8); opacity: 0.1; }
  50% { transform: translate3d(var(--pv-x), var(--pv-y), 0) scale(1.2); opacity: 0.55; }
}
.pv-bg-particle {
  position: absolute;
  width: 6px;
  height: 6px;
  border-radius: 9999px;
  --pv-x: 20px;
  --pv-y: -120px;
  background: rgba(251, 191, 36, 0.35);
  animation: pv-bg-particle calc(9s + (var(--i, 1) * 0.8s)) ease-in-out infinite;
}
.pv-bg-particle:nth-child(4n) {
  width: 5px;
  height: 5px;
  background: rgba(59, 130, 246, 0.35);
  --pv-x: -26px;
  --pv-y: -140px;
}
.pv-bg-particle:nth-child(4n+1) {
  background: rgba(244, 114, 182, 0.35);
  --pv-x: 32px;
  --pv-y: -130px;
}
.pv-bg-particle:nth-child(4n+2) {
  background: rgba(45, 212, 191, 0.35);
  --pv-x: -22px;
  --pv-y: -110px;
}

.pv-nav-link {
  position: relative;
  transition: all 260ms ease;
}

.pv-nav-link::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  bottom: -4px;
  height: 2px;
  transform: scaleX(0);
  transform-origin: center;
  border-radius: 999px;
  background: linear-gradient(90deg, #3b82f6 0%, #8b5cf6 50%, #ec4899 100%);
  transition: transform 240ms ease;
}

.pv-nav-link:hover {
  color: #1e40af;
  text-shadow: 0 0 10px rgba(59,130,246,0.35), 0 0 20px rgba(139,92,246,0.2);
}

.pv-nav-link::before {
  content: "";
  position: absolute;
  inset: -8px;
  z-index: -1;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(224, 242, 254, 0.55), rgba(243, 232, 255, 0.55), rgba(254, 242, 242, 0.55));
  opacity: 0;
  transform: scale(0.85);
  transition: all 220ms ease;
}

.pv-nav-link:hover::before {
  opacity: 1;
  transform: scale(1);
}

.pv-nav-link:hover::after {
  transform: scaleX(1);
}

.pv-top-cta {
  background: linear-gradient(135deg, #f59e0b 0%, #ec4899 50%, #3b82f6 100%);
  transition: transform 260ms ease, box-shadow 260ms ease;
}

.pv-top-cta:hover {
  transform: translateY(-2px) scale(1.05);
  box-shadow: 0 7px 20px rgba(251, 191, 36, 0.32);
}

.pv-top-cta-shine {
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
  transform: translateX(-140%) skewX(12deg);
  transition: transform 500ms ease;
}

.pv-top-cta:hover .pv-top-cta-shine {
  transform: translateX(140%) skewX(12deg);
}

.pv-hero-cta {
  background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 50%, #ec4899 100%);
  box-shadow: 0 10px 34px rgba(99, 102, 241, 0.3);
}

.pv-pill-sweep {
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.6), transparent);
  animation: pv-header-sweep 2s linear infinite;
}

.pv-feature-card:hover {
  transform: perspective(1000px) rotateX(4deg) rotateY(4deg);
  transition: transform 360ms cubic-bezier(0.4, 0, 0.2, 1);
}

.pv-step-card:hover {
  box-shadow: 0 28px 56px -20px rgba(31, 41, 55, 0.18);
}

.pv-terminal-inner {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.72), rgba(255, 255, 255, 0.58));
  border: 1px solid rgba(15, 23, 42, 0.06);
}

/* —— Hero terminal: 3D shell, halos, border, content layers —— */
.pv-terminal-stage {
  transform-style: preserve-3d;
}

.pv-terminal-float {
  transform-origin: 50% 60%;
  animation: pv-term-shell-enter 1s cubic-bezier(0.22, 1, 0.36, 1) both;
  transition:
    transform 0.55s cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 0.55s ease;
}

@keyframes pv-term-shell-enter {
  from {
    opacity: 0;
    transform: translate3d(0, 60px, 0) rotateX(-15deg);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0) rotateX(0deg);
  }
}

.pv-terminal-stage:not(.pv-terminal-stage--rm):hover .pv-terminal-float {
  transform: translate3d(0, -8px, 0) rotateX(2deg) rotateY(2deg);
}

.pv-terminal-card-shell {
  transition:
    box-shadow 0.55s ease,
    transform 0.55s cubic-bezier(0.22, 1, 0.36, 1);
}

.pv-terminal-stage:not(.pv-terminal-stage--rm):hover .pv-terminal-card-shell {
  box-shadow:
    0 22px 56px -20px rgba(100, 116, 139, 0.18),
    0 14px 40px -16px rgba(99, 102, 241, 0.12),
    0 8px 22px -10px rgba(14, 116, 144, 0.1);
}

.pv-terminal-halo-outer {
  background: conic-gradient(
    from 0deg,
    rgba(148, 197, 255, 0.35),
    rgba(199, 210, 254, 0.32),
    rgba(221, 214, 254, 0.34),
    rgba(186, 230, 253, 0.3),
    rgba(148, 197, 255, 0.35)
  );
  opacity: 0.16;
  filter: blur(44px);
  transition: opacity 0.55s ease;
  animation: pv-term-halo-spin 24s linear infinite;
}

.pv-terminal-stage:not(.pv-terminal-stage--rm):hover .pv-terminal-halo-outer {
  opacity: 0.32;
}

@keyframes pv-term-halo-spin {
  to { transform: rotate(360deg); }
}

.pv-terminal-halo-inner {
  background: radial-gradient(circle at 38% 32%, rgba(165, 243, 252, 0.22), transparent 58%),
    radial-gradient(circle at 72% 68%, rgba(199, 210, 254, 0.2), transparent 52%);
  opacity: 0.12;
  filter: blur(26px);
  transition: opacity 0.5s ease;
  animation: pv-term-inner-halo-breathe 5s ease-in-out infinite;
}

.pv-terminal-stage:not(.pv-terminal-stage--rm):hover .pv-terminal-halo-inner {
  opacity: 0.26;
}

@keyframes pv-term-inner-halo-breathe {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}

/* 1px 外环：始终可见（不透明父层），悬停时略增色彩，避免 opacity 把整块终端藏掉 */
.pv-terminal-outer-ring {
  background: linear-gradient(
    135deg,
    rgba(226, 232, 240, 0.95),
    rgba(241, 245, 249, 0.98),
    rgba(226, 232, 240, 0.95)
  );
  background-size: 200% 200%;
  transition: background 0.65s ease, box-shadow 0.55s ease;
  animation: pv-term-border-flow 12s ease infinite;
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.65) inset;
}

.pv-terminal-stage:not(.pv-terminal-stage--rm):hover .pv-terminal-outer-ring {
  background: linear-gradient(
    125deg,
    rgba(186, 198, 234, 0.55),
    rgba(199, 210, 254, 0.5),
    rgba(207, 250, 254, 0.45),
    rgba(199, 210, 254, 0.5),
    rgba(186, 198, 234, 0.55)
  );
}

@keyframes pv-term-border-flow {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}

.pv-terminal-header-scan {
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.4),
    transparent
  );
  transform: translateX(-100%);
  animation: pv-term-header-scan 3s linear infinite;
  animation-delay: 2s;
}

@keyframes pv-term-header-scan {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(200%); }
}

.pv-traffic-dot {
  transform-origin: center;
  will-change: transform;
}

.pv-traffic-dot--red:hover {
  box-shadow: 0 0 20px rgba(248, 113, 113, 0.95);
}
.pv-traffic-dot--blue:hover {
  box-shadow: 0 0 20px rgba(56, 189, 248, 0.95);
}
.pv-traffic-dot--green:hover {
  box-shadow: 0 0 20px rgba(52, 211, 153, 0.95);
}

.pv-terminal-bg-1 {
  background:
    radial-gradient(ellipse 72% 58% at 18% 42%, rgba(148, 163, 184, 0.14), transparent 62%),
    radial-gradient(ellipse 68% 52% at 82% 58%, rgba(165, 180, 252, 0.12), transparent 58%);
  animation: pv-term-bg1-pulse 10s ease-in-out infinite;
}

@keyframes pv-term-bg1-pulse {
  0%, 100% { transform: scale(1); opacity: 0.55; }
  50% { transform: scale(1.08); opacity: 0.75; }
}

.pv-terminal-bg-2 {
  background:
    radial-gradient(circle at 50% 14%, rgba(203, 213, 225, 0.14), transparent 44%),
    radial-gradient(circle at 50% 86%, rgba(186, 230, 253, 0.1), transparent 46%);
  mix-blend-mode: multiply;
  animation: pv-term-bg2-rotate 36s linear infinite;
}

@keyframes pv-term-bg2-rotate {
  to { transform: rotate(360deg); }
}

.pv-terminal-particle {
  width: 5px;
  height: 5px;
  left: calc(6% + var(--tp-i) * 11%);
  top: calc(14% + var(--tp-i) * 9%);
  opacity: 0;
  animation: pv-term-particle-float calc(6s + var(--tp-i) * 0.45s) ease-in-out infinite;
  animation-delay: calc(var(--tp-i) * 0.8s);
}

.pv-terminal-particle:nth-child(4n) {
  background: radial-gradient(circle, rgba(148, 163, 184, 0.55), transparent);
  box-shadow: 0 0 6px rgba(148, 163, 184, 0.25);
}
.pv-terminal-particle:nth-child(4n + 1) {
  background: radial-gradient(circle, rgba(165, 180, 252, 0.5), transparent);
  box-shadow: 0 0 6px rgba(165, 180, 252, 0.22);
}
.pv-terminal-particle:nth-child(4n + 2) {
  background: radial-gradient(circle, rgba(203, 213, 225, 0.55), transparent);
  box-shadow: 0 0 5px rgba(203, 213, 225, 0.22);
}
.pv-terminal-particle:nth-child(4n + 3) {
  background: radial-gradient(circle, rgba(186, 230, 253, 0.45), transparent);
  box-shadow: 0 0 6px rgba(186, 230, 253, 0.2);
}

@keyframes pv-term-particle-float {
  0% {
    transform: translate3d(0, 0, 0) scale(0);
    opacity: 0;
  }
  18% { opacity: 0.55; }
  50% {
    transform: translate3d(calc(-25px + (var(--tp-i) % 3) * 25px), -100px, 0) scale(1.2);
    opacity: 0.38;
  }
  82% { opacity: 0.28; }
  100% {
    transform: translate3d(calc(25px - (var(--tp-i) % 2) * 35px), 0, 0) scale(0);
    opacity: 0;
  }
}

.pv-terminal-line-row:last-child {
  animation: pv-term-line-in 0.34s cubic-bezier(0.22, 1, 0.36, 1) both;
}

@keyframes pv-term-line-in {
  from {
    opacity: 0;
    transform: translateX(-10px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.pv-term-char {
  opacity: 0;
  animation: pv-term-char-in 0.05s ease forwards;
  animation-delay: calc(var(--cd, 0) * 1ms);
}

@keyframes pv-term-char-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

.pv-terminal-line--glow::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  bottom: -2px;
  height: 8px;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(148, 163, 184, 0.18), rgba(165, 180, 252, 0.16), rgba(186, 230, 253, 0.14));
  filter: blur(8px);
  pointer-events: none;
  z-index: -1;
  animation: pv-term-line-glow-breathe 2.4s ease-in-out infinite;
}

@keyframes pv-term-line-glow-breathe {
  0%, 100% { opacity: 0.35; }
  50% { opacity: 0.55; }
}

.pv-term-progress-wrap {
  animation: pv-term-progress-enter 0.55s cubic-bezier(0.22, 1, 0.36, 1) both;
}

@keyframes pv-term-progress-enter {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.pv-term-progress-track-scan {
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.55), transparent);
  animation: pv-term-track-shine 2.4s linear infinite;
}

@keyframes pv-term-track-shine {
  0% { transform: translateX(-60%); }
  100% { transform: translateX(160%); }
}

.pv-term-progress-fill {
  background: linear-gradient(
    90deg,
    #3b82f6,
    #6366f1,
    #8b5cf6,
    #db2777,
    #ec4899
  );
  background-size: 220% 100%;
  animation: pv-term-fill-shift 3s linear infinite;
  box-shadow:
    0 0 14px rgba(59, 130, 246, 0.55),
    0 0 22px rgba(139, 92, 246, 0.35),
    0 0 18px rgba(236, 72, 153, 0.28);
}

@keyframes pv-term-fill-shift {
  0% { background-position: 0% 50%; }
  100% { background-position: 200% 50%; }
}

.pv-term-progress-shine {
  position: absolute;
  inset: 0;
  width: 45%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.65), transparent);
  animation: pv-term-progress-shine-move 1.5s linear infinite;
}

@keyframes pv-term-progress-shine-move {
  0% { transform: translateX(-120%); }
  100% { transform: translateX(220%); }
}

.pv-term-progress-cap {
  background: radial-gradient(circle, rgba(191, 219, 254, 1), rgba(59, 130, 246, 0.35) 55%, transparent 70%);
  box-shadow: 0 0 12px rgba(59, 130, 246, 0.65);
  animation: pv-term-cap-pulse 1s ease-in-out infinite;
}

@keyframes pv-term-cap-pulse {
  0%, 100% {
    opacity: 0.65;
    transform: translateY(-50%) translateX(50%) scale(1);
    box-shadow: 0 0 10px rgba(59, 130, 246, 0.55);
  }
  50% {
    opacity: 1;
    transform: translateY(-50%) translateX(50%) scale(1.28);
    box-shadow: 0 0 18px rgba(139, 92, 246, 0.75);
  }
}

.pv-term-pct-rainbow {
  background: linear-gradient(90deg, #38bdf8, #6366f1, #8b5cf6);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: pv-term-pct-breathe 2s ease-in-out infinite;
}

@keyframes pv-term-pct-breathe {
  0%, 100% { opacity: 1; filter: saturate(1); }
  50% { opacity: 0.62; filter: saturate(1.15); }
}

/* Reduced motion: keep structure, drop heavy motion */
.pv-terminal-stage--rm .pv-terminal-float {
  animation: none;
  opacity: 1;
  transform: none;
}
.pv-terminal-stage--rm .pv-terminal-halo-outer,
.pv-terminal-stage--rm .pv-terminal-halo-inner {
  display: none;
}
.pv-terminal-stage--rm:hover .pv-terminal-float {
  transform: none;
}
.pv-terminal-stage--rm .pv-terminal-bg-1,
.pv-terminal-stage--rm .pv-terminal-bg-2,
.pv-terminal-stage--rm .pv-terminal-particle {
  animation: none !important;
  opacity: 0.35;
}
.pv-terminal-stage--rm .pv-terminal-header-scan {
  animation: none;
  opacity: 0;
}
.pv-terminal-stage--rm .pv-term-char {
  animation: none;
  opacity: 1;
}
.pv-terminal-stage--rm .pv-terminal-line-row:last-child {
  animation: none;
}
.pv-terminal-stage--rm .pv-term-progress-wrap {
  animation: none;
}
.pv-terminal-stage--rm .pv-term-pct-rainbow {
  animation: none;
  opacity: 1;
}
.pv-terminal-stage--rm .pv-term-progress-fill {
  animation: none;
}
.pv-terminal-stage--rm .pv-term-progress-shine,
.pv-terminal-stage--rm .pv-term-progress-cap,
.pv-terminal-stage--rm .pv-term-progress-track-scan {
  animation: none !important;
}

.pv-floating-card {
  animation: pv-float-card 6s ease-in-out infinite;
  transform-style: preserve-3d;
  transition: transform 320ms ease;
}

.pv-floating-card:hover {
  transform: translate3d(0, -8px, 0) rotateX(3deg) rotateY(3deg) scale(1.03);
}

@keyframes pv-float-card {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-12px); }
}

.pv-terminal-cursor {
  width: 2px;
  height: 4px;
  border-radius: 1px;
  vertical-align: middle;
  background: linear-gradient(180deg, #3b82f6 0%, #8b5cf6 100%);
  animation: pv-cursor 0.8s steps(1, end) infinite;
}

.pv-terminal-cursor-glow {
  animation:
    pv-cursor 0.8s steps(1, end) infinite,
    pv-cursor-glow 2.4s ease-in-out infinite;
}

@keyframes pv-cursor {
  0%, 49% { opacity: 1; }
  50%, 100% { opacity: 0; }
}

@keyframes pv-cursor-glow {
  0%, 100% {
    box-shadow: 0 0 6px rgba(59, 130, 246, 0.85), 0 0 14px rgba(139, 92, 246, 0.35);
  }
  50% {
    box-shadow: 0 0 12px rgba(139, 92, 246, 0.95), 0 0 22px rgba(59, 130, 246, 0.45);
  }
}

/* Terminal dots + scanline (kept from original landing) */
@keyframes pv-dots {
  0% { clip-path: inset(0 100% 0 0); }
  100% { clip-path: inset(0 0 0 0); }
}
.pv-dots {
  display: inline-block;
  animation: pv-dots 1.2s steps(3, end) infinite;
  will-change: clip-path;
}

@keyframes pv-scanline {
  0% { transform: translateY(-120%); }
  100% { transform: translateY(120%); }
}
.pv-scanline {
  background: linear-gradient(to bottom, transparent, rgba(251, 146, 60, 0.12), transparent);
  animation: pv-scanline 3.2s ease-in-out infinite;
  will-change: transform;
}

/* Animated gradient bar */
@keyframes pv-gradient-xy {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}
.pv-gradient-xy {
  background-size: 300% 300%;
  animation: pv-gradient-xy 14s ease infinite;
  will-change: background-position;
}

@keyframes pv-blob-a {
  0%, 100% { transform: scale(1); opacity: 0.2; }
  50% { transform: scale(1.2); opacity: 0.4; }
}
@keyframes pv-blob-b {
  0%, 100% { transform: scale(1.2); opacity: 0.2; }
  50% { transform: scale(1); opacity: 0.4; }
}
@keyframes pv-blob-c {
  0% { transform: translate3d(-50%, -50%, 0); }
  50% { transform: translate3d(calc(-50% + 100px), calc(-50% - 100px), 0); }
  100% { transform: translate3d(-50%, -50%, 0); }
}
.pv-blob-a { animation: pv-blob-a 8s infinite; }
.pv-blob-b { animation: pv-blob-b 10s infinite; }
.pv-blob-c { animation: pv-blob-c 12s infinite; }

@keyframes pv-hero-glow {
  0%, 100% { opacity: 0.5; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.1); }
}
.pv-hero-glow {
  background: linear-gradient(90deg, rgba(251, 191, 36, 0.28), rgba(236, 72, 153, 0.28), rgba(56, 189, 248, 0.28));
  animation: pv-hero-glow 3s infinite;
}

@keyframes pv-char-reveal {
  0% { opacity: 0; transform: translateY(20px) rotateX(-90deg); }
  100% { opacity: 1; transform: translateY(0) rotateX(0); }
}
.pv-char-reveal {
  opacity: 0;
  transform-origin: bottom;
  animation: pv-char-reveal 500ms cubic-bezier(0.215, 0.61, 0.355, 1) forwards;
}

@keyframes pv-pulse {
  0%, 100% { transform: scale(1); opacity: 0.4; }
  50% { transform: scale(1.3); opacity: 0.6; }
}
.pv-icon-pulse { animation: pv-pulse 3s infinite; }

@keyframes pv-wiggle {
  0% { transform: rotate(0deg) scale(1); }
  20% { transform: rotate(-10deg) scale(1.05); }
  40% { transform: rotate(10deg) scale(1.05); }
  60% { transform: rotate(-10deg) scale(1.05); }
  80% { transform: rotate(10deg) scale(1.05); }
  100% { transform: rotate(0deg) scale(1); }
}
.group:hover .pv-icon-wiggle { animation: pv-wiggle 0.5s ease; }

@keyframes pv-shine {
  0% { transform: translateX(-100%); opacity: 0; }
  35% { opacity: 1; }
  100% { transform: translateX(100%); opacity: 0; }
}
.pv-shine { animation: pv-shine 1.6s infinite; opacity: 0; }
.group:hover .pv-shine { opacity: 1; }

/* Timeline / flowing line effects */
.pv-timeline { bottom: 0; }
@keyframes pv-flow {
  0% { transform: translate(-50%, 0); opacity: 1; }
  85% { opacity: 1; }
  100% { transform: translate(-50%, 800px); opacity: 0; }
}
.pv-flow-dot {
  position: absolute;
  left: 50%;
  top: 0;
  border-radius: 9999px;
  transform: translate(-50%, 0);
}
.pv-flow-dot--a { width: 12px; height: 12px; background: white; box-shadow: 0 0 18px rgba(251,146,60,0.45); animation: pv-flow 3s linear infinite; }
.pv-flow-dot--b { width: 8px; height: 8px; background: rgba(186,230,253,1); box-shadow: 0 0 14px rgba(56,189,248,0.45); animation: pv-flow 4s linear infinite; animation-delay: 1s; opacity: 0.85; }
.pv-flow-dot--c { width: 10px; height: 10px; background: rgba(251,207,232,1); box-shadow: 0 0 14px rgba(244,114,182,0.45); animation: pv-flow 3.5s linear infinite; animation-delay: 2s; opacity: 0.9; }

@keyframes pv-ring {
  0%, 100% { transform: translateX(-50%) scale(1); opacity: 0.6; }
  50% { transform: translateX(-50%) scale(1.5); opacity: 0; }
}
.pv-ring {
  position: absolute;
  left: 50%;
  width: 32px;
  height: 32px;
  border-radius: 9999px;
  border: 2px solid rgba(255,255,255,0.4);
  transform: translateX(-50%);
  animation: pv-ring 2s infinite;
}
.pv-ring:nth-of-type(1) { animation-delay: 0s; }
.pv-ring:nth-of-type(2) { animation-delay: 0.5s; }
.pv-ring:nth-of-type(3) { animation-delay: 1s; }
.pv-ring:nth-of-type(4) { animation-delay: 1.5s; }

/* Border shimmer for workflow cards */
@keyframes pv-shimmer {
  0% { transform: translateX(-200%); }
  100% { transform: translateX(200%); }
}
.pv-border-shimmer {
  background: linear-gradient(90deg, transparent, var(--pv-shimmer, rgba(59,130,246,0.12)), transparent);
  animation: pv-shimmer 3s linear infinite;
  opacity: 1;
}

@keyframes pv-corner {
  0%, 100% { transform: scale(1); opacity: 0.4; }
  50% { transform: scale(1.1); opacity: 0.6; }
}
.pv-corner-breath { animation: pv-corner 3s infinite; }

@keyframes pv-particle {
  0%, 100% { transform: translateY(0); opacity: 0.3; }
  50% { transform: translateY(-20px); opacity: 0.8; }
}
.pv-particle {
  position: absolute;
  width: 4px;
  height: 4px;
  border-radius: 9999px;
  animation: pv-particle 3s infinite;
}
.pv-particle:nth-of-type(1) { animation-duration: 2s; }
.pv-particle:nth-of-type(2) { animation-duration: 3s; }
.pv-particle:nth-of-type(3) { animation-duration: 4s; }

@keyframes pv-rotate {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
.pv-rotate-slow { animation: pv-rotate 20s linear infinite; }
.pv-rotate-ring { animation: pv-rotate 10s linear infinite; }

@keyframes pv-badge-pulse {
  0%, 100% { transform: scale(1); opacity: 0.5; }
  50% { transform: scale(1.3); opacity: 0.8; }
}
.pv-badge-pulse { animation: pv-badge-pulse 2s infinite; }

/* Badge pop-in feel on hover */
.pv-badge-pop { transition: transform 0.3s ease; }
.pv-badge-pop:hover { transform: scale(1.2) rotate(360deg); }

@keyframes pv-step-ring {
  0%, 100% { transform: scale(1); opacity: 0.5; }
  50% { transform: scale(1.45); opacity: 0; }
}
.pv-step-ring {
  animation: pv-step-ring 1.8s infinite;
}

@keyframes pv-bottom-btn-shine {
  0% { transform: translateX(-160%) skewX(12deg); }
  100% { transform: translateX(180%) skewX(12deg); }
}
.group:hover .pv-bottom-btn-shine { animation: pv-bottom-btn-shine 0.6s ease; }

@keyframes pv-ripple-a {
  0% { transform: scale(1); opacity: 0.55; }
  100% { transform: scale(1.45); opacity: 0; }
}
@keyframes pv-ripple-b {
  0% { transform: scale(1); opacity: 0.45; }
  100% { transform: scale(1.65); opacity: 0; }
}
.pv-ripple-a { animation: pv-ripple-a 2s ease-out infinite; }
.pv-ripple-b { animation: pv-ripple-b 2s ease-out infinite 450ms; }

@keyframes pv-cta-particle {
  0% {
    transform: translate3d(0, 0, 0) scale(0);
    opacity: 0;
  }
  30% { opacity: 1; }
  100% {
    transform: translate3d(calc((var(--pv-pi) - 2.5) * 20px), -70px, 0) scale(1.3);
    opacity: 0;
  }
}
.pv-cta-particle {
  position: absolute;
  left: 50%;
  bottom: 45%;
  width: 5px;
  height: 5px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.7);
  box-shadow: 0 0 12px rgba(255, 255, 255, 0.6);
  opacity: 0;
}
.group:hover .pv-cta-particle {
  animation: pv-cta-particle 1300ms ease-out infinite;
  animation-delay: calc(var(--pv-pi) * 100ms);
}

.pv-compare-card:hover {
  border-color: rgba(139, 92, 246, 0.5);
  box-shadow: 0 20px 45px -20px rgba(139, 92, 246, 0.35);
}

.pv-cta-subtitle {
  max-width: 100%;
  white-space: nowrap;
  line-height: 1.75;
  font-size: clamp(12px, 1.65vw, 18px);
}

/* Shine variants */
.pv-shine-sweep { animation: pv-shine 2s linear infinite; opacity: 1; }
.pv-shine-sweep-once { animation: pv-shine 0.6s ease; opacity: 0; }
.group:hover .pv-shine-sweep-once { opacity: 1; }
</style>

