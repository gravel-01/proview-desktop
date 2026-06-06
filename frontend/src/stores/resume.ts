import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ResumeSection, ResumeSuggestion, BuilderData, ResumeReportContext } from '../types/resume'
import type { ResumeDocument, TemplateId } from '../types/resume-builder'
import * as resumeApi from '../services/resume'
import { assertValidResumeFile } from '../utils/resumeFile'

export type ResumePhase = 'upload' | 'analyzing' | 'review' | 'exporting' | 'done'

/** section type 对应 builder module type 映射 */
const SECTION_TO_MODULE_TYPE: Record<string, string> = {
  education: 'education',
  experience: 'work',
  projects: 'project',
  skills: 'skills',
  certifications: 'certificates',
}

export const useResumeStore = defineStore('resume', () => {
  const phase = ref<ResumePhase>('upload')
  const token = ref('')
  const ocrText = ref('')
  const sections = ref<ResumeSection[]>([])
  const suggestions = ref<ResumeSuggestion[]>([])
  const images = ref<Record<string, string>>({})
  const error = ref('')
  const skipOcr = ref(false)
  const builderDocument = ref<ResumeDocument | null>(null)
  const reportContext = ref<ResumeReportContext | null>(null)
  // 流式思考过程
  const thinkingText = ref('')
  const thinkingStage = ref('')

  const pendingCount = computed(() => suggestions.value.filter(s => s.status === 'PENDING').length)
  const acceptedCount = computed(() => suggestions.value.filter(s => s.status === 'ACCEPTED').length)
  const rejectedCount = computed(() => suggestions.value.filter(s => s.status === 'REJECTED').length)

  function buildReportThinkingText(context: ResumeReportContext | null) {
    if (!context) return ''

    const lines = ['[历史面试评估]']

    if (context.position) {
      lines.push(`面试岗位: ${context.position}`)
    }

    if (typeof context.avgScore === 'number') {
      lines.push(`综合评分: ${context.avgScore.toFixed(1)}`)
    }

    if (context.summary) {
      lines.push(`总结: ${context.summary}`)
    }

    if (context.strengths) {
      lines.push(`优势: ${context.strengths}`)
    }

    if (context.weaknesses) {
      lines.push(`待改进: ${context.weaknesses}`)
    }

    if (context.evaluations.length) {
      lines.push('分项评估:')
      for (const item of context.evaluations) {
        const scoreText = typeof item.score === 'number' ? `${item.score}/10` : '-'
        const commentText = item.comment ? `，${item.comment}` : ''
        lines.push(`- ${item.dimension}: ${scoreText}${commentText}`)
      }
    }

    lines.push('', '---', '')
    return lines.join('\n')
  }

  function isEphemeralQuestionnaireContext(context: ResumeReportContext) {
    return (
      context.sessionId.startsWith('local-')
      && !context.position
      && typeof context.avgScore !== 'number'
      && !context.summary
      && !context.strengths
      && !context.weaknesses
      && context.evaluations.length === 0
    )
  }

  function setQuestionnaireContext(questionnaireStr: string | null) {
    const nextQuestionnaire = questionnaireStr?.trim() || ''

    if (!nextQuestionnaire) {
      if (!reportContext.value) return

      if (isEphemeralQuestionnaireContext(reportContext.value)) {
        reportContext.value = null
        return
      }

      delete reportContext.value.questionnaireContext
      return
    }

    if (!reportContext.value) {
      reportContext.value = {
        sessionId: 'local-' + Date.now(),
        evaluations: [],
        questionnaireContext: nextQuestionnaire,
      }
      return
    }

    reportContext.value.questionnaireContext = nextQuestionnaire
  }

  async function analyzeResume(file: File, jobTitle: string, modelProvider = '') {
    try {
      assertValidResumeFile(file)
    } catch (e: any) {
      error.value = e?.message || '不支持的简历文件'
      phase.value = 'upload'
      return
    }

    phase.value = 'analyzing'
    skipOcr.value = false
    error.value = ''
    thinkingText.value = buildReportThinkingText(reportContext.value)
    thinkingStage.value = ''
    try {
      await resumeApi.analyzeResumeStream(file, jobTitle, {
        onStage: (stage) => { thinkingStage.value = stage },
        onThinking: (chunk) => { thinkingText.value += chunk },
        onDone: (data) => {
          if (data.status !== 'success') {
            error.value = '分析失败'
            phase.value = 'upload'
            return
          }
          token.value = data.token
          resumeApi.setResumeToken(data.token)
          ocrText.value = data.ocr_text
          sections.value = data.sections
          suggestions.value = data.suggestions
          images.value = data.images || {}
          if (data.builder_data) initBuilderDocument(data.builder_data)
          thinkingText.value = ''
          thinkingStage.value = ''
          phase.value = 'review'
        },
        onError: (msg) => {
          error.value = msg || '分析失败'
          thinkingText.value = ''
          thinkingStage.value = ''
          phase.value = 'upload'
        },
      }, reportContext.value, modelProvider)
    } catch (e: any) {
      error.value = e?.message || '分析失败'
      thinkingText.value = ''
      thinkingStage.value = ''
      phase.value = 'upload'
    }
  }

  /** 使用已有 OCR 文本直接分析（跳过 OCR，复用面试结果） */
  async function analyzeFromOcr(ocrTextInput: string, jobTitle: string, modelProvider = '') {
    phase.value = 'analyzing'
    skipOcr.value = true
    error.value = ''
    thinkingText.value = buildReportThinkingText(reportContext.value)
    thinkingStage.value = ''
    try {
      await resumeApi.analyzeResumeWithOcrStream(ocrTextInput, jobTitle, {
        onStage: (stage) => { thinkingStage.value = stage },
        onThinking: (chunk) => { thinkingText.value += chunk },
        onDone: (data) => {
          if (data.status !== 'success') {
            error.value = '分析失败'
            phase.value = 'upload'
            return
          }
          token.value = data.token
          resumeApi.setResumeToken(data.token)
          ocrText.value = data.ocr_text
          sections.value = data.sections
          suggestions.value = data.suggestions
          images.value = data.images || {}
          if (data.builder_data) initBuilderDocument(data.builder_data)
          thinkingText.value = ''
          thinkingStage.value = ''
          phase.value = 'review'
        },
        onError: (msg) => {
          error.value = msg || '分析失败'
          thinkingText.value = ''
          thinkingStage.value = ''
          phase.value = 'upload'
        },
      }, reportContext.value, modelProvider)
    } catch (e: any) {
      error.value = e?.message || '分析失败'
      thinkingText.value = ''
      thinkingStage.value = ''
      phase.value = 'upload'
    }
  }

  function initBuilderDocument(data: BuilderData) {
    builderDocument.value = {
      id: 'resume-opt-' + Date.now(),
      mode: 'general',
      targetJd: '',
      settings: {
        templateId: data.detectedTemplate || 'classic',
        themeColor: '#4F46E5',
        fontFamily: 'default',
        fontSize: 14,
        lineHeight: 1.6,
        marginMm: 18,
        photoShow: true,
      },
      basicInfo: data.basicInfo,
      modules: data.modules,
      polishSuggestions: [],
    }
  }

  function findBuilderModule(section: ResumeSection) {
    if (!builderDocument.value) return null
    const moduleType = SECTION_TO_MODULE_TYPE[section.type]
    if (!moduleType) return null
    return builderDocument.value.modules.find(m => m.type === moduleType) || null
  }

  function setTemplateId(id: TemplateId) {
    if (builderDocument.value) {
      builderDocument.value.settings.templateId = id
    }
  }

  function setThemeColor(color: string) {
    if (builderDocument.value) {
      builderDocument.value.settings.themeColor = color
    }
  }

  function setFontSize(size: number) {
    if (builderDocument.value) {
      builderDocument.value.settings.fontSize = size
    }
  }

  function setLineHeight(lh: number) {
    if (builderDocument.value) {
      builderDocument.value.settings.lineHeight = lh
    }
  }

  function acceptSuggestion(suggestionId: string) {
    const sug = suggestions.value.find(s => s.suggestionId === suggestionId)
    if (!sug) return
    sug.status = 'ACCEPTED'
    // 替换 section 中的内容
    const sec = sections.value.find(s => s.id === sug.targetBlockId)
    if (sec) {
      sec.content = sec.content.replace(sug.originalText, sug.suggestedText)
      // 同步到 builderDocument
      syncSuggestionToBuilder(sug, sec)
    }
  }

  function syncSuggestionToBuilder(sug: ResumeSuggestion, section: ResumeSection) {
    const mod = findBuilderModule(section)
    if (!mod) return

    if (mod.entries?.length) {
      for (const entry of mod.entries) {
        if (entry.detail && entry.detail.includes(sug.originalText)) {
          entry.detail = entry.detail.replace(sug.originalText, sug.suggestedText)
          break
        }
      }
    } else if (mod.content !== undefined) {
      mod.content = (mod.content || '').replace(sug.originalText, sug.suggestedText)
    }
  }

  function rejectSuggestion(suggestionId: string) {
    const sug = suggestions.value.find(s => s.suggestionId === suggestionId)
    if (sug) sug.status = 'REJECTED'
  }

  function updateSectionContent(sectionId: string, content: string) {
    const sec = sections.value.find(s => s.id === sectionId)
    if (!sec) return

    sec.content = content

    const mod = findBuilderModule(sec)
    if (!mod) return

    if (mod.entries?.length === 1) {
      const [entry] = mod.entries
      if (entry) {
        entry.detail = content
        return
      }
    }

    if (mod.content !== undefined) {
      mod.content = content
    }
  }

  function updateSectionTitle(sectionId: string, title: string) {
    const sec = sections.value.find(s => s.id === sectionId)
    if (!sec) return

    sec.title = title

    if (!builderDocument.value) return

    if (sec.type === 'personal_info') {
      builderDocument.value.basicInfo.name = title
      return
    }

    const mod = findBuilderModule(sec)
    if (mod) mod.title = title
  }

  function reorderSections(fromIndex: number, toIndex: number) {
    const moved = sections.value.splice(fromIndex, 1)[0]
    if (moved) sections.value.splice(toIndex, 0, moved)
  }

  async function exportPdf() {
    phase.value = 'exporting'
    error.value = ''

    try {
      let blob: Blob

      if (builderDocument.value) {
        // 模板渲染导出：获取预览区域的 HTML
        const el = document.querySelector('.resume-renderer')
        if (el) {
          const styles = Array.from(document.querySelectorAll('style'))
            .map(s => s.outerHTML).join('\n')
          const html = `<!DOCTYPE html><html><head><meta charset="utf-8">${styles}
            <style>
              @page { size: A4; margin: 0; }
              html, body { margin: 0; padding: 0; width: 794px; }
              .resume-renderer { width: 794px; }
              h2,h3,h4,.section-title { break-after: avoid; orphans: 3; widows: 3; }
              li, p { break-inside: avoid; }
            </style>
            </head><body>${el.outerHTML}</body></html>`
          blob = await resumeApi.exportHtmlPdf(html)
        } else {
          // fallback 到 sections 导出
          blob = await resumeApi.exportResumePdf(sections.value)
        }
      } else {
        blob = await resumeApi.exportResumePdf(sections.value)
      }

      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'optimized_resume.pdf'
      a.click()
      URL.revokeObjectURL(url)
      phase.value = 'done'
    } catch (e: any) {
      error.value = e?.response?.data?.message || e.message || '导出失败'
      phase.value = 'review'
    }
  }

  function updatePhoto(dataUrl: string) {
    if (builderDocument.value) {
      builderDocument.value.basicInfo.photoUrl = dataUrl
    }
  }

  function setReportContext(nextContext: ResumeReportContext | null) {
    reportContext.value = nextContext
  }

  function reset() {
    resumeApi.clearResumeToken()
    phase.value = 'upload'
    token.value = ''
    ocrText.value = ''
    sections.value = []
    suggestions.value = []
    images.value = {}
    error.value = ''
    skipOcr.value = false
    builderDocument.value = null
    reportContext.value = null
    thinkingText.value = ''
    thinkingStage.value = ''
  }

  return {
    phase, token, ocrText, sections, suggestions, images, error, skipOcr,
    builderDocument, reportContext, thinkingText, thinkingStage,
    pendingCount, acceptedCount, rejectedCount,
    analyzeResume, analyzeFromOcr, acceptSuggestion, rejectSuggestion,
    updateSectionContent, updateSectionTitle, reorderSections,
    setTemplateId, exportPdf, reset, updatePhoto, setThemeColor, setFontSize, setLineHeight,
    setReportContext, setQuestionnaireContext
  }
})
