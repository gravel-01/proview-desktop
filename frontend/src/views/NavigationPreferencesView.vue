<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Sparkles, Settings2, TrendingUp, Gauge } from 'lucide-vue-next'
import { useNavigationPreferenceStore } from '../stores/navigationPreference'
import type { NavPreferences } from '../services/navigationPreference'
import { markNavPreferenceCompleted } from '../router'

const router = useRouter()
const route = useRoute()
const preferenceStore = useNavigationPreferenceStore()

const fromRegister = computed(() => route.query.from === 'register')
const step = ref(0)
const submitError = ref('')
const form = ref<NavPreferences>({
  goal: 'both',
  stage: 'occasional',
  difficulty: 'mid',
  career: 'trend',
})

const questions = [
  {
    key: 'goal',
    title: '通过本系统，您最主要的目标是？',
    icon: Sparkles,
    options: [
      { value: 'improve_interview', label: '提升面试能力' },
      { value: 'optimize_resume', label: '优化简历' },
      { value: 'both', label: '两者并重' },
    ],
  },
  {
    key: 'stage',
    title: '您当前的求职/准备阶段？',
    icon: Settings2,
    options: [
      { value: 'active', label: '正在密集投递与面试' },
      { value: 'preparing', label: '提前准备，尚未投递' },
      { value: 'occasional', label: '在职/在校，偶尔观望' },
      { value: 'self_improve', label: '仅用于自我提升，无求职计划' },
    ],
  },
  {
    key: 'difficulty',
    title: '您期望的面试难度基调？',
    icon: Gauge,
    options: [
      { value: 'junior', label: '初级（适合新手/热身）' },
      { value: 'mid', label: '中级（常规社招水平）' },
      { value: 'senior', label: '高级（对标大厂/专家岗）' },
    ],
  },
  {
    key: 'career',
    title: '您目前对职业规划的需求程度是？',
    icon: TrendingUp,
    options: [
      { value: 'explore', label: '急需职业方向探索' },
      { value: 'advance', label: '希望规划晋升路径' },
      { value: 'trend', label: '关注行业趋势与机会' },
      { value: 'none', label: '暂无职业规划需求' },
    ],
  },
]

const currentQuestion = computed(() => questions[Math.min(step.value, questions.length - 1)]!)
const isLastStep = computed(() => step.value >= questions.length - 1)
const stepLabel = computed(() => `问题 ${step.value + 1} / ${questions.length}`)
const progressPct = computed(() => `${((step.value + 1) / questions.length) * 100}%`)

const MODULE_ROUTE_MAP: Record<string, string> = {
  interview_config: '/',
  interview_history: '/history',
  interview_room: '/interview',
  evaluation_report: '/report',
  experience_summary: '/summary',
  resume_optimize: '/resume-optimizer',
  resume_generate: '/resume-builder',
  my_resume: '/my-resumes',
  career_planning: '/career-planning/overview',
}

function getFirstRankedRoute() {
  const order = preferenceStore.moduleOrder || []
  for (const moduleId of order) {
    const routePath = MODULE_ROUTE_MAP[moduleId]
    if (routePath) return routePath
  }
  return '/'
}

function choose(value: string) {
  const key = currentQuestion.value.key as keyof NavPreferences
  ;(form.value as Record<string, string>)[key] = value
}

function isSelected(value: string) {
  const key = currentQuestion.value.key as keyof NavPreferences
  return (form.value as Record<string, string>)[key] === value
}

function skipCurrent() {
  if (isLastStep.value) {
    submit()
    return
  }
  step.value += 1
}

function nextStep() {
  if (isLastStep.value) {
    submit()
    return
  }
  step.value += 1
}

async function submit() {
  submitError.value = ''
  try {
    await preferenceStore.save(form.value)
    // 保存成功后立即放行路由守卫，避免“点击无反应”。
    markNavPreferenceCompleted(true)
    const targetPath = getFirstRankedRoute()
    if (fromRegister.value) {
      await router.push(targetPath)
      return
    }
    await router.push(targetPath)
  } catch (error) {
    const fallbackMessage = '保存失败，请稍后重试'
    const responseMessage = (error as { response?: { data?: { message?: string } } })?.response?.data?.message
    submitError.value = responseMessage || fallbackMessage
  }
}

/** 底部快捷入口：先持久化当前表单再跳转，否则路由守卫会送回问卷页。 */
async function saveAndNavigate(path: string) {
  submitError.value = ''
  try {
    await preferenceStore.save(form.value)
    markNavPreferenceCompleted(true)
    await router.push(path)
  } catch (error) {
    const fallbackMessage = '保存失败，请稍后重试'
    const responseMessage = (error as { response?: { data?: { message?: string } } })?.response?.data?.message
    submitError.value = responseMessage || fallbackMessage
  }
}

onMounted(async () => {
  try {
    await preferenceStore.load()
    form.value = { ...preferenceStore.preferences }
  } catch {
    form.value = {
      goal: 'both',
      stage: 'occasional',
      difficulty: 'mid',
      career: 'trend',
    }
  }
})
</script>

<template>
  <div class="pv-qx">
    <div class="pv-qx__bg" aria-hidden="true">
      <div class="pv-qx__orb pv-qx__orb--a" />
      <div class="pv-qx__orb pv-qx__orb--b" />
      <div class="pv-qx__dots" />
    </div>

    <div class="pv-qx__wrap">
      <div class="pv-qx__head">
        <h1 class="pv-qx__title">欢迎使用 ProView AI</h1>
        <p class="pv-qx__subtitle">
          两个功能都可在侧边导航随时使用，这里只设置你优先进入哪一边。
        </p>
      </div>

      <div class="pv-qx__card">
        <div class="pv-qx__top">
          <div class="pv-qx__progress">
            <div class="pv-qx__progressRow">
              <span class="pv-qx__stepText">
                <span class="pv-qx__stepTextStrong">{{ step + 1 }}</span> / {{ questions.length }}
              </span>
              <button type="button" class="pv-qx__skip" @click="skipCurrent">
                跳过此题
              </button>
            </div>
            <div class="pv-qx__bar" role="progressbar" :aria-label="stepLabel" :aria-valuenow="step + 1" :aria-valuemin="1" :aria-valuemax="questions.length">
              <div class="pv-qx__barFill" :style="{ width: progressPct }" />
              <div class="pv-qx__barGlow" :style="{ left: progressPct }" aria-hidden="true" />
            </div>
          </div>
        </div>

        <Transition name="pv-qx-swap" mode="out-in">
          <div :key="step" class="pv-qx__body">
            <div class="pv-qx__qRow">
              <div class="pv-qx__qIcon">
                <component :is="currentQuestion.icon" class="h-5 w-5" />
              </div>
              <h2 class="pv-qx__qTitle">{{ currentQuestion.title }}</h2>
            </div>

            <div class="pv-qx__options">
              <button
                v-for="(option, idx) in currentQuestion.options"
                :key="option.value"
                type="button"
                class="pv-qx__opt"
                :class="isSelected(option.value) ? 'pv-qx__opt--on' : 'pv-qx__opt--off'"
                :style="{ '--pv-i': idx } as any"
                @click="choose(option.value)"
              >
                <span class="pv-qx__optMark" aria-hidden="true" />
                <span class="pv-qx__optLabel">{{ option.label }}</span>
              </button>
            </div>
          </div>
        </Transition>

        <div class="pv-qx__footer">
          <div class="pv-qx__btnRow">
            <button
              type="button"
              class="pv-qx__btn pv-qx__btn--prev"
              :disabled="step === 0 || preferenceStore.loading"
              @click="step = Math.max(0, step - 1)"
            >
              上一步
            </button>
            <button
              type="button"
              class="pv-qx__btn pv-qx__btn--next"
              :disabled="preferenceStore.loading"
              @click="nextStep"
            >
              <span class="pv-qx__btnGlow" aria-hidden="true" />
              {{ isLastStep ? (preferenceStore.loading ? '保存中...' : '提交并更新导航') : '下一步' }}
            </button>
          </div>

          <p v-if="submitError" class="pv-qx__error">
            {{ submitError }}
          </p>

          <div class="pv-qx__links">
            <p class="pv-qx__linksHint">已有默认选项，可直接进入对应模块（将保存当前偏好）：</p>
            <div class="pv-qx__linksRow">
              <button
                type="button"
                class="pv-qx__link"
                :disabled="preferenceStore.loading"
                @click="saveAndNavigate('/resume-optimizer')"
              >
                进入简历优化
              </button>
              <span class="pv-qx__sep" aria-hidden="true">·</span>
              <button
                type="button"
                class="pv-qx__link"
                :disabled="preferenceStore.loading"
                @click="saveAndNavigate('/')"
              >
                进入面试配置
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
@reference "tailwindcss";

.pv-qx {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  background: linear-gradient(to bottom right, rgba(240, 249, 255, 0.4), rgba(255, 255, 255, 1), rgba(239, 246, 255, 0.3));
}

.pv-qx__bg {
  pointer-events: none;
  position: absolute;
  inset: 0;
}

.pv-qx__orb {
  position: absolute;
  border-radius: 9999px;
  filter: blur(64px);
  transform: translate3d(0, 0, 0);
  opacity: 1;
}

.pv-qx__orb--a {
  left: -220px;
  top: -220px;
  width: 600px;
  height: 600px;
  background: radial-gradient(circle, rgba(224, 242, 254, 0.22), transparent 65%);
  animation: pv-qx-orb-a 30s ease-in-out infinite;
}

.pv-qx__orb--b {
  right: -200px;
  bottom: -220px;
  width: 500px;
  height: 500px;
  background: radial-gradient(circle, rgba(219, 234, 254, 0.18), transparent 65%);
  animation: pv-qx-orb-b 28s ease-in-out infinite;
}

@keyframes pv-qx-orb-a {
  0%,
  100% {
    transform: translate3d(0, 0, 0) scale(1);
  }
  50% {
    transform: translate3d(0, 30px, 0) scale(1.1);
  }
}

@keyframes pv-qx-orb-b {
  0%,
  100% {
    transform: translate3d(0, 0, 0) scale(1);
  }
  50% {
    transform: translate3d(0, -25px, 0) scale(1.15);
  }
}

.pv-qx__dots {
  position: absolute;
  inset: 0;
  opacity: 0.005;
  background-image: radial-gradient(circle, #111827 0.7px, transparent 0.7px);
  background-size: 60px 60px;
}

.pv-qx__wrap {
  position: relative;
  z-index: 1;
  margin: 0 auto;
  max-width: 900px;
  padding: 44px 16px;
}

.pv-qx__head {
  text-align: center;
  margin-bottom: 20px;
  opacity: 0;
  transform: translate3d(0, 20px, 0);
  animation: pv-qx-fade-up 0.8s cubic-bezier(0.215, 0.61, 0.355, 1) forwards;
  animation-delay: 0.3s;
}

.pv-qx__title {
  font-size: 30px;
  font-weight: 700;
  letter-spacing: -0.02em;
  background: linear-gradient(90deg, #1e3a8a 0%, #1e40af 45%, #1d4ed8 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.pv-qx__subtitle {
  margin-top: 12px;
  font-size: 14px;
  line-height: 1.7;
  color: #6b7280;
  opacity: 0;
  transform: translate3d(0, 12px, 0);
  animation: pv-qx-fade-up 0.8s cubic-bezier(0.215, 0.61, 0.355, 1) forwards;
  animation-delay: 0.4s;
}

@keyframes pv-qx-fade-up {
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}

.pv-qx__card {
  position: relative;
  max-width: 700px;
  margin: 0 auto;
  border-radius: 24px;
  border: 1px solid rgba(229, 231, 235, 0.6);
  background:
    linear-gradient(
      135deg,
      rgba(255, 255, 255, 0.9) 0%,
      rgba(224, 242, 254, 0.25) 30%,
      rgba(219, 234, 254, 0.25) 70%,
      rgba(255, 255, 255, 0.9) 100%
    );
  box-shadow:
    0 18px 50px rgba(15, 23, 42, 0.08),
    0 30px 70px rgba(59, 130, 246, 0.08),
    0 0 100px rgba(147, 197, 253, 0.05);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  padding: 32px;
  min-height: 500px;
  opacity: 0;
  transform: translate3d(0, 50px, 0) rotateX(-12deg) scale(0.96);
  transform-style: preserve-3d;
  animation: pv-qx-card-in 1s cubic-bezier(0.215, 0.61, 0.355, 1) forwards;
  animation-delay: 0.2s;
}

@keyframes pv-qx-card-in {
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0) rotateX(0) scale(1);
  }
}

.pv-qx__top {
  margin-bottom: 18px;
}

.pv-qx__progressRow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.pv-qx__stepText {
  font-size: 12px;
  color: #6b7280;
  font-weight: 600;
}
.pv-qx__stepTextStrong {
  color: #2563eb;
  font-weight: 800;
}

.pv-qx__skip {
  font-size: 14px;
  color: #6b7280;
  transition: transform 0.2s ease, color 0.2s ease;
}
.pv-qx__skip:hover {
  color: #1d4ed8;
  transform: translateY(-1px);
}

.pv-qx__bar {
  position: relative;
  height: 4px;
  border-radius: 9999px;
  background: rgba(243, 244, 246, 1);
  overflow: hidden;
}

.pv-qx__barFill {
  height: 100%;
  border-radius: 9999px;
  background: linear-gradient(90deg, #38bdf8, #3b82f6);
  transition: width 0.6s ease;
}

.pv-qx__barGlow {
  position: absolute;
  top: 50%;
  width: 14px;
  height: 14px;
  transform: translate3d(-50%, -50%, 0);
  border-radius: 9999px;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.35), transparent 60%);
  animation: pv-qx-glow-breathe 2.6s ease-in-out infinite;
  pointer-events: none;
}

@keyframes pv-qx-glow-breathe {
  0%,
  100% {
    opacity: 0.45;
    transform: translate3d(-50%, -50%, 0) scale(0.9);
  }
  50% {
    opacity: 0.85;
    transform: translate3d(-50%, -50%, 0) scale(1.1);
  }
}

.pv-qx__body {
  padding-top: 8px;
}

.pv-qx__qRow {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.pv-qx__qIcon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(224, 242, 254, 0.8), rgba(219, 234, 254, 0.55));
  color: #2563eb;
  box-shadow: 0 10px 26px rgba(59, 130, 246, 0.08);
  animation: pv-qx-icon-float 2s ease-in-out infinite;
}

@keyframes pv-qx-icon-float {
  0%,
  100% {
    transform: translate3d(0, 0, 0);
  }
  50% {
    transform: translate3d(0, -2px, 0);
  }
}

.pv-qx__qTitle {
  font-size: 20px;
  line-height: 1.6;
  font-weight: 600;
  color: #111827;
  margin-top: 2px;
}

.pv-qx__options {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pv-qx__opt {
  position: relative;
  width: 100%;
  text-align: left;
  border-radius: 12px;
  padding: 16px 18px;
  border: 1px solid rgba(229, 231, 235, 1);
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow: 0 1px 8px rgba(15, 23, 42, 0.04);
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease;
  opacity: 0;
  transform: translate3d(-20px, 0, 0);
  animation: pv-qx-opt-in 0.4s ease forwards;
  animation-delay: calc(var(--pv-i, 0) * 100ms);
}

@keyframes pv-qx-opt-in {
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}

.pv-qx__opt:hover {
  transform: translate3d(0, -2px, 0) scale(1.01);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.08);
  border-color: rgba(125, 211, 252, 1);
  background: rgba(255, 255, 255, 0.8);
}

.pv-qx__optMark {
  position: absolute;
  left: 0;
  top: 50%;
  width: 3px;
  height: 0%;
  transform: translateY(-50%);
  border-radius: 9999px;
  background: linear-gradient(180deg, #38bdf8, #3b82f6);
  transition: height 0.3s ease;
}

.pv-qx__opt--on {
  border-width: 2px;
  border-color: rgba(59, 130, 246, 1);
  background: linear-gradient(135deg, rgba(224, 242, 254, 0.5), rgba(219, 234, 254, 0.4));
  box-shadow:
    0 10px 26px rgba(15, 23, 42, 0.08),
    0 4px 16px rgba(59, 130, 246, 0.15);
}
.pv-qx__opt--on .pv-qx__optMark {
  height: 80%;
}
.pv-qx__optLabel {
  font-size: 16px;
  font-weight: 500;
  color: #374151;
  transition: color 0.2s ease, font-weight 0.2s ease;
}
.pv-qx__opt--on .pv-qx__optLabel {
  color: #1e3a8a;
  font-weight: 600;
}

.pv-qx__footer {
  margin-top: 26px;
  padding-top: 18px;
  border-top: 1px solid rgba(229, 231, 235, 0.6);
}

.pv-qx__btnRow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.pv-qx__btn {
  border-radius: 12px;
  padding: 12px 18px;
  font-size: 14px;
  font-weight: 600;
  transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}

.pv-qx__btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.pv-qx__btn--prev {
  background: #ffffff;
  border: 1px solid rgba(229, 231, 235, 1);
  color: #374151;
}
.pv-qx__btn--prev:not(:disabled):hover {
  background: rgba(240, 249, 255, 1);
  border-color: rgba(186, 230, 253, 1);
  color: #1d4ed8;
  transform: translate3d(0, -2px, 0);
}

.pv-qx__btn--next {
  position: relative;
  overflow: hidden;
  color: #ffffff;
  padding-left: 22px;
  padding-right: 22px;
  background: linear-gradient(135deg, #60a5fa 0%, #3b82f6 100%);
  box-shadow: 0 6px 20px rgba(59, 130, 246, 0.25);
}
.pv-qx__btn--next:not(:disabled):hover {
  transform: translate3d(0, -3px, 0) scale(1.05);
  box-shadow: 0 10px 30px rgba(59, 130, 246, 0.35);
}

.pv-qx__btnGlow {
  position: absolute;
  inset: -40%;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.25), transparent 55%);
  opacity: 0.35;
  animation: pv-qx-btn-breathe 3s ease-in-out infinite;
  pointer-events: none;
}
@keyframes pv-qx-btn-breathe {
  0%,
  100% {
    opacity: 0.3;
    transform: scale(0.95);
  }
  50% {
    opacity: 0.6;
    transform: scale(1.05);
  }
}

.pv-qx__error {
  margin-top: 10px;
  font-size: 14px;
  color: #b91c1c;
}

.pv-qx__links {
  margin-top: 18px;
  text-align: center;
}
.pv-qx__linksHint {
  margin-bottom: 10px;
  font-size: 14px;
  color: #6b7280;
}
.pv-qx__linksRow {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  font-size: 14px;
}
.pv-qx__sep {
  color: rgba(156, 163, 175, 1);
}
.pv-qx__link {
  position: relative;
  color: #2563eb;
  transition: color 0.2s ease, transform 0.2s ease;
}
.pv-qx__link::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -3px;
  height: 1.5px;
  background: linear-gradient(90deg, #0ea5e9, #2563eb);
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.3s ease;
}
.pv-qx__link:not(:disabled):hover {
  color: #1d4ed8;
  transform: translate3d(0, -1px, 0);
}
.pv-qx__link:not(:disabled):hover::after {
  transform: scaleX(1);
}
.pv-qx__link:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.pv-qx-swap-enter-active,
.pv-qx-swap-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.pv-qx-swap-enter-from {
  opacity: 0;
  transform: translate3d(30px, 0, 0);
}
.pv-qx-swap-leave-to {
  opacity: 0;
  transform: translate3d(-30px, 0, 0);
}

@media (max-width: 640px) {
  .pv-qx__wrap {
    padding: 28px 14px;
  }
  .pv-qx__card {
    padding: 22px;
    min-height: 520px;
  }
  .pv-qx__title {
    font-size: 24px;
  }
  .pv-qx__qTitle {
    font-size: 18px;
  }
  .pv-qx__optLabel {
    font-size: 14px;
  }
  .pv-qx__btnRow {
    flex-direction: column-reverse;
    align-items: stretch;
  }
  .pv-qx__btn {
    width: 100%;
    justify-content: center;
  }
}

@media (prefers-reduced-motion: reduce) {
  .pv-qx__orb--a,
  .pv-qx__orb--b,
  .pv-qx__qIcon,
  .pv-qx__btnGlow,
  .pv-qx__barGlow,
  .pv-qx__opt {
    animation: none !important;
  }
  .pv-qx__head,
  .pv-qx__subtitle,
  .pv-qx__card {
    animation: none !important;
    opacity: 1;
    transform: none;
  }
}
</style>
