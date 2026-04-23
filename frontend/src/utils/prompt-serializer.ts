import type { ResumeQuestionnaireSchema } from '../types/resume-questionnaire'

const DEFAULT_RESUME_STYLE = '简洁专业（外企风格）'

function normalizeList(values: string[] | undefined): string[] {
  return Array.from(new Set((values || []).map((item) => item.trim()).filter(Boolean)))
}

function hasMeaningfulWorkExperience(data: ResumeQuestionnaireSchema): boolean {
  return data.workExperiences.some((exp) => (
    Boolean(exp.companyName?.trim())
    || Boolean(exp.jobTitle?.trim())
    || Boolean(exp.startDate?.trim())
    || Boolean(exp.endDate?.trim())
    || Boolean(exp.outcomeImprovement?.trim())
    || Boolean(exp.managementCount)
    || Boolean(exp.implicitOutcomes?.length)
  ))
}

export function hasMeaningfulQuestionnaireData(data: ResumeQuestionnaireSchema): boolean {
  const targetIndustries = normalizeList(data.targetIndustries)
  const optimizationGoals = normalizeList(data.optimizationGoals)
  const optimizationStrategies = normalizeList(data.optimizationStrategies)
  const educationHighlights = normalizeList(data.education?.highlights)
  const validSkills = (data.skills || []).filter((skill) => skill.name.trim())

  return Boolean(
    data.targetRole.trim()
    || targetIndustries.length
    || data.targetCompanyType.trim()
    || data.currentExperienceBase.trim()
    || optimizationGoals.length
    || (data.hasJd && data.jdContent?.trim())
    || hasMeaningfulWorkExperience(data)
    || validSkills.length
    || data.education?.school.trim()
    || data.education?.major.trim()
    || educationHighlights.length
    || (data.resumeStyle && data.resumeStyle !== DEFAULT_RESUME_STYLE)
    || optimizationStrategies.length
    || data.additionalAdvantages.trim()
  )
}

export function generateQuestionnairePromptContext(data: ResumeQuestionnaireSchema): string {
  const targetIndustries = normalizeList(data.targetIndustries)
  const optimizationGoals = normalizeList(data.optimizationGoals)
  const optimizationStrategies = normalizeList(data.optimizationStrategies)
  const educationHighlights = normalizeList(data.education?.highlights)
  const validSkills = (data.skills || []).filter((skill) => skill.name.trim())

  const workExperienceLines = data.workExperiences.flatMap((exp, index) => {
    const lines: string[] = []
    const titleLine = [exp.companyName?.trim(), exp.jobTitle?.trim()].filter(Boolean).join(' / ')
    const periodLine = [exp.startDate?.trim(), exp.endDate?.trim()].filter(Boolean).join(' - ')

    if (!titleLine && !periodLine && !exp.outcomeImprovement?.trim() && !exp.implicitOutcomes?.length) {
      return []
    }

    lines.push(`- 经历 ${index + 1}: ${titleLine || '未命名经历'}${periodLine ? ` (${periodLine})` : ''}`)

    if (exp.isManagement) {
      lines.push(`  管理职责: 是${exp.managementCount ? `，管理人数约 ${exp.managementCount} 人` : ''}`)
    }

    if (exp.hasSpecificOutcome === 'YES_DATA' && exp.outcomeImprovement?.trim()) {
      lines.push(`  期望突出成果: ${exp.outcomeImprovement.trim()}`)
    } else if (exp.implicitOutcomes?.length) {
      lines.push(`  期望突出影响: ${exp.implicitOutcomes.join('、')}`)
    }

    return lines
  })

  const lines: string[] = ['---【用户个性化简历优化问卷意图注入】---']
  const overrideRules: string[] = []

  if (data.targetRole.trim() || targetIndustries.length || data.targetCompanyType.trim()) {
    lines.push(`1. 求职定位：${[data.targetRole.trim(), data.targetCompanyType.trim(), targetIndustries.join(' / ')].filter(Boolean).join(' ｜ ')}`)
  }

  if (data.currentExperienceBase.trim()) {
    lines.push(`2. 当前阶段：${data.currentExperienceBase.trim()}`)
  }

  if (optimizationGoals.length) {
    lines.push(`3. 本次优化重点：${optimizationGoals.join('、')}`)
  }

  if (data.resumeStyle && data.resumeStyle !== DEFAULT_RESUME_STYLE) {
    lines.push(`4. 期望风格：${data.resumeStyle}`)
  }

  if (optimizationStrategies.length) {
    lines.push(`5. 特殊优化策略：${optimizationStrategies.join('、')}`)
  }

  if (validSkills.length) {
    lines.push('6. 希望强调的技能：')
    lines.push(...validSkills.map((skill) => `- ${skill.name.trim()} (${skill.level})`))
    overrideRules.push('若原简历技能与本问卷技能冲突或重复，请以问卷技能清单为准进行替换/重排，不要并列堆叠。')
  }

  if (data.education.school.trim() || data.education.major.trim() || educationHighlights.length) {
    lines.push(`7. 教育背景补充：${[data.education.school.trim(), data.education.degree, data.education.major.trim()].filter(Boolean).join(' ')}`)
    if (educationHighlights.length) {
      lines.push(`- 教育亮点：${educationHighlights.join('、')}`)
    }
    overrideRules.push('若问卷中填写了学校/学历/专业，请覆盖原简历同类字段，不要把新旧学校或专业拼接在一起。')
  }

  if (data.additionalAdvantages.trim()) {
    lines.push('8. 其他补充优势：')
    lines.push(data.additionalAdvantages.trim())
  }

  if (workExperienceLines.length) {
    lines.push('', '【用户补充的工作经历重点】', ...workExperienceLines)
  }

  if (data.hasJd && data.jdContent?.trim()) {
    lines.push(
      '',
      '【目标岗位 JD 分析要求】',
      '用户提供 JD 内容如下：',
      '"""',
      data.jdContent.trim(),
      '"""',
      '请针对以上 JD 的岗位职责和核心技能要求进行高优先级关键词匹配和 ATS 优化。',
    )
  }

  if (overrideRules.length) {
    lines.push('', '【字段覆盖规则（严格执行）】', ...overrideRules)
  }

  lines.push(
    '-------------------------------------',
    '以上内容来自用户主动填写的可选意向问卷。结构化字段按“覆盖规则”执行，其余内容作为优化偏好；禁止脱离原简历事实虚构。',
  )

  return lines.join('\n')
}
