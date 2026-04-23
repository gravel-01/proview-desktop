<script setup lang="ts">
import { computed } from 'vue'
import {
  BriefcaseBusiness,
  FilePlus2,
  GraduationCap,
  Lightbulb,
  ListTodo,
  Plus,
  Sparkles,
  Target,
  Trash2,
} from 'lucide-vue-next'
import { useResumeQuestionnaireStore } from '../../stores/resumeQuestionnaire'
import { hasMeaningfulQuestionnaireData } from '../../utils/prompt-serializer'

const emit = defineEmits(['optimize-now'])

const store = useResumeQuestionnaireStore()
const defaultResumeStyle = '简洁专业（外企风格）'

function parseTagInput(value: string, limit?: number) {
  const items = Array.from(
    new Set(
      value
        .split(/[,\n，、]/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  )
  return typeof limit === 'number' ? items.slice(0, limit) : items
}

const targetIndustriesInput = computed({
  get: () => store.formData.targetIndustries.join('，'),
  set: (value: string) => {
    store.formData.targetIndustries = parseTagInput(value)
  },
})

const optimizationGoalsInput = computed({
  get: () => store.formData.optimizationGoals.join('，'),
  set: (value: string) => {
    store.formData.optimizationGoals = parseTagInput(value, 3)
  },
})

const optimizationStrategiesInput = computed({
  get: () => store.formData.optimizationStrategies.join('，'),
  set: (value: string) => {
    store.formData.optimizationStrategies = parseTagInput(value)
  },
})

const educationHighlightsInput = computed({
  get: () => store.formData.education.highlights.join('，'),
  set: (value: string) => {
    store.formData.education.highlights = parseTagInput(value)
  },
})

const hasQuestionnaireContent = computed(() => hasMeaningfulQuestionnaireData(store.formData))

const filledSectionCount = computed(() => {
  let count = 0
  if (store.formData.targetRole.trim() || store.formData.targetIndustries.length || store.formData.targetCompanyType.trim() || store.formData.currentExperienceBase.trim()) count += 1
  if (
    store.formData.optimizationGoals.length
    || (store.formData.hasJd && store.formData.jdContent?.trim())
    || store.formData.resumeStyle !== defaultResumeStyle
    || store.formData.optimizationStrategies.length
  ) count += 1
  if (store.formData.workExperiences.some((exp) => exp.companyName.trim() || exp.jobTitle.trim() || exp.outcomeImprovement?.trim() || exp.implicitOutcomes?.length)) count += 1
  if (store.formData.skills.some((skill) => skill.name.trim()) || store.formData.education.school.trim() || store.formData.education.major.trim() || store.formData.education.highlights.length) count += 1
  if (store.formData.additionalAdvantages.trim()) count += 1
  return count
})

function addSkill() {
  store.formData.skills.push({
    name: '',
    level: '熟悉',
  })
}

function resetQuestionnaire() {
  store.reset()
}
</script>

<template>
  <div class="questionnaire-panel">
    <div class="questionnaire-head">
      <div>
        <p class="section-kicker">按需补充</p>
        <h3 class="text-xl font-bold text-slate-900 dark:text-white">你的偏好会怎样影响优化</h3>
        <p class="mt-2 max-w-3xl text-sm leading-6 text-slate-500 dark:text-slate-400">
          这里更适合补充“目标方向、成果表达、JD 要求、风格偏好”等信息。AI 会参考这些内容，但不会因为你没填就阻止优化。
        </p>
      </div>
      <div class="head-badges">
        <span class="status-chip" :class="hasQuestionnaireContent ? 'status-chip-active' : 'status-chip-idle'">
          {{ hasQuestionnaireContent ? `已填写 ${filledSectionCount}/5 个模块` : '当前为空，不影响直接优化' }}
        </span>
        <button type="button" class="reset-btn" @click="resetQuestionnaire">清空问卷</button>
      </div>
    </div>

    <div class="questionnaire-grid">
      <section class="question-card">
        <div class="card-head">
          <div class="card-icon card-icon-blue">
            <Target class="h-4 w-4" />
          </div>
          <div>
            <h4 class="card-title">目标方向</h4>
            <p class="card-desc">让优化结果更贴近你真正想投递的方向。</p>
          </div>
        </div>

        <div class="field-grid">
          <label class="field-block">
            <span class="field-label">目标岗位</span>
            <input v-model="store.formData.targetRole" type="text" class="field-input" placeholder="如：前端开发工程师 / 产品经理" />
          </label>
          <label class="field-block">
            <span class="field-label">当前经验阶段</span>
            <select v-model="store.formData.currentExperienceBase" class="field-input">
              <option value="">未指定</option>
              <option>应届生 / 在校</option>
              <option>0-1年</option>
              <option>1-3年</option>
              <option>3-5年</option>
              <option>5年以上</option>
            </select>
          </label>
          <label class="field-block">
            <span class="field-label">目标行业</span>
            <input v-model="targetIndustriesInput" type="text" class="field-input" placeholder="如：互联网，AI，企业服务" />
          </label>
          <label class="field-block">
            <span class="field-label">目标公司类型</span>
            <select v-model="store.formData.targetCompanyType" class="field-input">
              <option value="">未指定</option>
              <option>大厂（如互联网头部公司）</option>
              <option>中型公司</option>
              <option>初创公司</option>
              <option>外企</option>
              <option>不确定</option>
            </select>
          </label>
        </div>
      </section>

      <section class="question-card">
        <div class="card-head">
          <div class="card-icon card-icon-indigo">
            <Sparkles class="h-4 w-4" />
          </div>
          <div>
            <h4 class="card-title">优化重点</h4>
            <p class="card-desc">告诉 AI 这次更应该突出什么。</p>
          </div>
        </div>

        <div class="space-y-4">
          <label class="field-block">
            <span class="field-label">核心优化诉求</span>
            <input
              v-model="optimizationGoalsInput"
              type="text"
              class="field-input"
              placeholder="最多 3 项，如：突出项目成果，提高通过率，强化关键词匹配"
            />
          </label>
          <label class="field-block">
            <span class="field-label">简历风格</span>
            <select v-model="store.formData.resumeStyle" class="field-input">
              <option value="简洁专业（外企风格）">简洁专业（外企风格）</option>
              <option value="成果导向（互联网推荐）">成果导向（互联网推荐）</option>
              <option value="技术深度（技术岗）">技术深度（技术岗）</option>
              <option value="内容全面（传统行业）">内容全面（传统行业）</option>
            </select>
          </label>
          <label class="field-block">
            <span class="field-label">特殊策略</span>
            <input
              v-model="optimizationStrategiesInput"
              type="text"
              class="field-input"
              placeholder="如：强调业务结果，弱化重复描述，英文表达更专业"
            />
          </label>
        </div>
      </section>

      <section class="question-card card-wide">
        <div class="card-head">
          <div class="card-icon card-icon-amber">
            <ListTodo class="h-4 w-4" />
          </div>
          <div>
            <h4 class="card-title">JD 与工作经历补充</h4>
            <p class="card-desc">如果你想让 AI 更准确地改写成果表达，这一块最有价值。</p>
          </div>
        </div>

        <div class="space-y-4">
          <div class="rounded-2xl border border-slate-200/80 bg-slate-50/70 p-4 dark:border-white/8 dark:bg-white/4">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p class="field-label">是否有明确岗位 JD</p>
                <p class="mt-1 text-xs text-slate-400 dark:text-slate-500">填写后会按 JD 要求优先做关键词和 ATS 匹配。</p>
              </div>
              <div class="flex items-center gap-3 text-sm text-slate-600 dark:text-slate-300">
                <label class="inline-flex items-center gap-2">
                  <input v-model="store.formData.hasJd" :value="true" type="radio" class="accent-primary" />
                  有
                </label>
                <label class="inline-flex items-center gap-2">
                  <input v-model="store.formData.hasJd" :value="false" type="radio" class="accent-primary" />
                  没有
                </label>
              </div>
            </div>
            <textarea
              v-if="store.formData.hasJd"
              v-model="store.formData.jdContent"
              rows="5"
              class="field-input mt-4 min-h-[132px]"
              placeholder="可直接粘贴岗位 JD，AI 会按职责、关键词和技能要求来优化简历。"
            />
          </div>

          <div class="space-y-3">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p class="field-label">经历补充</p>
                <p class="mt-1 text-xs text-slate-400 dark:text-slate-500">可以只补 1-2 段最关键经历，不需要把整份简历都重填。</p>
              </div>
              <button type="button" class="inline-action-btn" @click="store.addWorkExperience">
                <Plus class="h-4 w-4" />
                添加经历
              </button>
            </div>

            <div v-if="!store.formData.workExperiences.length" class="empty-state">
              暂未补充经历。你可以直接开始优化，或只添加最想强化的一两段经历。
            </div>

            <article
              v-for="exp in store.formData.workExperiences"
              :key="exp.id"
              class="experience-card"
            >
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p class="text-sm font-semibold text-slate-800 dark:text-white">经历补充</p>
                  <p class="mt-1 text-xs text-slate-400 dark:text-slate-500">补充真实信息，方便 AI 更准确地重写成果。</p>
                </div>
                <button type="button" class="text-sm font-medium text-red-500 transition hover:text-red-600" @click="store.removeWorkExperience(exp.id)">
                  <Trash2 class="mr-1 inline h-4 w-4" />
                  删除
                </button>
              </div>

              <div class="field-grid mt-4">
                <label class="field-block">
                  <span class="field-label">公司名称</span>
                  <input v-model="exp.companyName" type="text" class="field-input" placeholder="公司 / 团队名称" />
                </label>
                <label class="field-block">
                  <span class="field-label">职位名称</span>
                  <input v-model="exp.jobTitle" type="text" class="field-input" placeholder="如：前端开发工程师" />
                </label>
                <label class="field-block">
                  <span class="field-label">开始时间</span>
                  <input v-model="exp.startDate" type="text" class="field-input" placeholder="YYYY.MM" />
                </label>
                <label class="field-block">
                  <span class="field-label">结束时间</span>
                  <input v-model="exp.endDate" type="text" class="field-input" placeholder="YYYY.MM / 至今" />
                </label>
              </div>

              <div class="mt-4 grid gap-4 lg:grid-cols-[1fr_auto]">
                <label class="field-block">
                  <span class="field-label">成果表达偏好</span>
                  <select v-model="exp.hasSpecificOutcome" class="field-input">
                    <option value="NOT_SURE">还没有明确想法</option>
                    <option value="YES_DATA">有明确数据成果</option>
                    <option value="YES_NO_DATA">有成果但没有量化数据</option>
                  </select>
                </label>
                <label class="field-block lg:w-40">
                  <span class="field-label">管理人数</span>
                  <input v-model.number="exp.managementCount" type="number" min="0" class="field-input" placeholder="可选" />
                </label>
              </div>

              <textarea
                v-if="exp.hasSpecificOutcome === 'YES_DATA'"
                v-model="exp.outcomeImprovement"
                rows="3"
                class="field-input mt-4 min-h-[108px]"
                placeholder="如：推动核心转化率提升 25%，主导搭建组件平台支撑 12 个业务团队。"
              />

              <div v-else-if="exp.hasSpecificOutcome === 'YES_NO_DATA'" class="mt-4 rounded-2xl border border-amber-200/80 bg-amber-50/70 p-4 dark:border-amber-400/15 dark:bg-amber-400/8">
                <p class="field-label">这段经历更希望突出哪些影响</p>
                <div class="mt-3 flex flex-wrap gap-3 text-sm text-slate-600 dark:text-slate-300">
                  <label class="checkbox-pill"><input v-model="exp.implicitOutcomes" type="checkbox" value="提升了效率" class="accent-primary" /> 提升了效率</label>
                  <label class="checkbox-pill"><input v-model="exp.implicitOutcomes" type="checkbox" value="减少了错误" class="accent-primary" /> 减少了错误</label>
                  <label class="checkbox-pill"><input v-model="exp.implicitOutcomes" type="checkbox" value="优化了流程" class="accent-primary" /> 优化了流程</label>
                  <label class="checkbox-pill"><input v-model="exp.implicitOutcomes" type="checkbox" value="协同更顺畅" class="accent-primary" /> 协同更顺畅</label>
                </div>
              </div>
            </article>
          </div>
        </div>
      </section>

      <section class="question-card">
        <div class="card-head">
          <div class="card-icon card-icon-emerald">
            <BriefcaseBusiness class="h-4 w-4" />
          </div>
          <div>
            <h4 class="card-title">技能与教育</h4>
            <p class="card-desc">补充你希望被强调的关键词和教育亮点。</p>
          </div>
        </div>

        <div class="space-y-4">
          <div class="rounded-2xl border border-slate-200/80 bg-slate-50/70 p-4 dark:border-white/8 dark:bg-white/4">
            <div class="mb-3 flex items-center justify-between gap-3">
              <p class="field-label">技能清单</p>
              <button type="button" class="inline-action-btn" @click="addSkill">
                <Plus class="h-4 w-4" />
                添加技能
              </button>
            </div>
            <div v-if="!store.formData.skills.length" class="empty-state">
              暂未补充技能关键词。
            </div>
            <div v-for="(skill, index) in store.formData.skills" :key="index" class="grid gap-3 pt-3 first:pt-0 sm:grid-cols-[1fr_140px_auto]">
              <input v-model="skill.name" type="text" class="field-input" placeholder="如：Vue 3 / Python / 增长分析" />
              <select v-model="skill.level" class="field-input">
                <option value="了解">了解</option>
                <option value="熟悉">熟悉</option>
                <option value="熟练">熟练</option>
                <option value="精通">精通</option>
              </select>
              <button type="button" class="inline-action-btn inline-action-danger" @click="store.formData.skills.splice(index, 1)">
                删除
              </button>
            </div>
          </div>

          <div class="rounded-2xl border border-slate-200/80 bg-slate-50/70 p-4 dark:border-white/8 dark:bg-white/4">
            <div class="flex items-center gap-2">
              <GraduationCap class="h-4 w-4 text-emerald-500" />
              <p class="field-label">教育补充</p>
            </div>
            <div class="field-grid mt-4">
              <label class="field-block">
                <span class="field-label">学校</span>
                <input v-model="store.formData.education.school" type="text" class="field-input" placeholder="学校名称" />
              </label>
              <label class="field-block">
                <span class="field-label">学历</span>
                <select v-model="store.formData.education.degree" class="field-input">
                  <option value="专科">专科</option>
                  <option value="本科">本科</option>
                  <option value="硕士">硕士</option>
                  <option value="博士">博士</option>
                </select>
              </label>
              <label class="field-block">
                <span class="field-label">专业</span>
                <input v-model="store.formData.education.major" type="text" class="field-input" placeholder="如：计算机科学与技术" />
              </label>
              <label class="field-block">
                <span class="field-label">教育亮点</span>
                <input v-model="educationHighlightsInput" type="text" class="field-input" placeholder="如：奖学金，排名前 10%，竞赛获奖" />
              </label>
            </div>
          </div>
        </div>
      </section>

      <section class="question-card">
        <div class="card-head">
          <div class="card-icon card-icon-rose">
            <Lightbulb class="h-4 w-4" />
          </div>
          <div>
            <h4 class="card-title">附加亮点</h4>
            <p class="card-desc">给 AI 更多上下文，例如开源、证书、博客、副业或个人品牌。</p>
          </div>
        </div>

        <textarea
          v-model="store.formData.additionalAdvantages"
          rows="8"
          class="field-input min-h-[220px]"
          placeholder="如：长期维护某开源项目；有技术博客；英语可直接面试；有跨团队项目 owner 经验。"
        />
      </section>
    </div>

    <div class="questionnaire-footer">
      <div class="flex min-w-0 items-center gap-3">
        <div class="footer-icon">
          <FilePlus2 class="h-4 w-4" />
        </div>
        <div class="min-w-0">
          <p class="truncate text-sm font-semibold text-slate-800 dark:text-white">问卷中的结构化字段（如学校/专业/技能）会用于覆盖更新，其他内容作为偏好参考。</p>
          <p class="mt-1 text-xs text-slate-400 dark:text-slate-500">
            你可以继续使用上方主按钮，也可以直接用下面这个快捷入口开始优化。
          </p>
        </div>
      </div>
      <button type="button" class="footer-cta" @click="emit('optimize-now')">
        <Sparkles class="h-4 w-4" />
        用当前偏好开始优化
      </button>
    </div>
  </div>
</template>

<style scoped>
@reference "tailwindcss";

.questionnaire-panel {
  @apply space-y-6 rounded-[28px] border p-5 sm:p-6;
  background:
    radial-gradient(circle at top left, rgba(59, 130, 246, 0.08), transparent 28%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 250, 252, 0.98) 100%);
  border-color: rgba(226, 232, 240, 0.9);
}

.dark .questionnaire-panel {
  background:
    radial-gradient(circle at top left, rgba(96, 165, 250, 0.1), transparent 28%),
    linear-gradient(180deg, rgba(12, 16, 25, 0.98) 0%, rgba(7, 10, 18, 0.98) 100%);
  border-color: rgba(255, 255, 255, 0.08);
}

.questionnaire-head {
  @apply flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between;
}

.section-kicker {
  @apply text-[11px] font-semibold uppercase tracking-[0.24em];
  color: rgb(59, 130, 246);
}

.head-badges {
  @apply flex flex-wrap items-center gap-3;
}

.status-chip {
  @apply inline-flex items-center rounded-full px-3 py-1.5 text-xs font-semibold;
}

.status-chip-active {
  background: rgba(16, 185, 129, 0.14);
  color: rgb(5, 150, 105);
}

.status-chip-idle {
  background: rgba(226, 232, 240, 0.9);
  color: rgb(100, 116, 139);
}

.dark .status-chip-active {
  background: rgba(16, 185, 129, 0.18);
  color: rgb(110, 231, 183);
}

.dark .status-chip-idle {
  background: rgba(255, 255, 255, 0.06);
  color: rgb(148, 163, 184);
}

.reset-btn {
  @apply inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-medium transition-colors;
  border-color: rgba(226, 232, 240, 0.95);
  color: rgb(100, 116, 139);
  background: rgba(255, 255, 255, 0.82);
}

.reset-btn:hover {
  border-color: rgba(79, 70, 229, 0.28);
  color: rgb(79, 70, 229);
}

.dark .reset-btn {
  border-color: rgba(255, 255, 255, 0.08);
  color: rgb(203, 213, 225);
  background: rgba(255, 255, 255, 0.03);
}

.questionnaire-grid {
  @apply grid gap-4 xl:grid-cols-2;
}

.question-card {
  @apply rounded-[24px] border p-5;
  background: rgba(255, 255, 255, 0.72);
  border-color: rgba(226, 232, 240, 0.9);
}

.dark .question-card {
  background: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.08);
}

.card-wide {
  @apply xl:col-span-2;
}

.card-head {
  @apply mb-5 flex items-start gap-3;
}

.card-icon {
  @apply flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl text-white;
}

.card-icon-blue {
  background: linear-gradient(135deg, #2563eb 0%, #38bdf8 100%);
}

.card-icon-indigo {
  background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
}

.card-icon-amber {
  background: linear-gradient(135deg, #f59e0b 0%, #f97316 100%);
}

.card-icon-emerald {
  background: linear-gradient(135deg, #10b981 0%, #14b8a6 100%);
}

.card-icon-rose {
  background: linear-gradient(135deg, #f43f5e 0%, #fb7185 100%);
}

.card-title {
  @apply text-base font-semibold text-slate-900 dark:text-white;
}

.card-desc {
  @apply mt-1 text-sm text-slate-500 dark:text-slate-400;
}

.field-grid {
  @apply grid gap-4 md:grid-cols-2;
}

.field-block {
  @apply block;
}

.field-label {
  @apply text-sm font-medium text-slate-700 dark:text-slate-200;
}

.field-input {
  @apply mt-2 w-full rounded-2xl border px-4 py-3 text-sm outline-none transition-colors;
  border-color: rgba(203, 213, 225, 0.9);
  background: rgba(255, 255, 255, 0.95);
  color: rgb(15, 23, 42);
}

.field-input:focus {
  border-color: rgba(79, 70, 229, 0.55);
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.12);
}

.dark .field-input {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(15, 23, 42, 0.78);
  color: rgb(226, 232, 240);
}

.inline-action-btn {
  @apply inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-medium transition-colors;
  border-color: rgba(79, 70, 229, 0.18);
  color: rgb(79, 70, 229);
  background: rgba(79, 70, 229, 0.08);
}

.inline-action-btn:hover {
  background: rgba(79, 70, 229, 0.14);
}

.inline-action-danger {
  border-color: rgba(248, 113, 113, 0.18);
  color: rgb(220, 38, 38);
  background: rgba(254, 226, 226, 0.8);
}

.dark .inline-action-danger {
  border-color: rgba(248, 113, 113, 0.18);
  background: rgba(127, 29, 29, 0.22);
  color: rgb(252, 165, 165);
}

.empty-state {
  @apply rounded-2xl border border-dashed px-4 py-6 text-center text-sm;
  border-color: rgba(203, 213, 225, 0.9);
  color: rgb(100, 116, 139);
  background: rgba(248, 250, 252, 0.74);
}

.dark .empty-state {
  border-color: rgba(255, 255, 255, 0.08);
  color: rgb(148, 163, 184);
  background: rgba(255, 255, 255, 0.03);
}

.experience-card {
  @apply rounded-[24px] border p-4;
  border-color: rgba(226, 232, 240, 0.9);
  background: rgba(255, 255, 255, 0.92);
}

.dark .experience-card {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
}

.checkbox-pill {
  @apply inline-flex items-center gap-2 rounded-full border px-3 py-2;
  border-color: rgba(226, 232, 240, 0.95);
  background: rgba(255, 255, 255, 0.86);
}

.dark .checkbox-pill {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
}

.questionnaire-footer {
  @apply flex flex-col gap-4 rounded-[24px] border p-4 lg:flex-row lg:items-center lg:justify-between;
  border-color: rgba(226, 232, 240, 0.9);
  background: rgba(248, 250, 252, 0.94);
}

.dark .questionnaire-footer {
  border-color: rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
}

.footer-icon {
  @apply flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl text-white;
  background: linear-gradient(135deg, #0ea5e9 0%, #2563eb 100%);
}

.footer-cta {
  @apply inline-flex items-center justify-center gap-2 rounded-2xl px-4 py-3 text-sm font-semibold text-white transition-all;
  background: linear-gradient(135deg, #4f46e5 0%, #4338ca 100%);
  box-shadow: 0 14px 30px rgba(79, 70, 229, 0.24);
}

.footer-cta:hover {
  transform: translateY(-1px);
  box-shadow: 0 18px 34px rgba(79, 70, 229, 0.28);
}
</style>
