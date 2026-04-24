import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type {
  ResumeDocument, ResumeModule, BasicInfo, TemplateSettings,
  TimeRangeEntry,
  ModuleType, TemplatePreset, TemplateId,
} from '../types/resume-builder'
import { MODULE_TYPE_META } from '../types/resume-builder'
import { buildApiUrl } from '../services/runtimeConfig'

const STORAGE_KEY = 'resume-builder-draft'
const PRESETS_KEY = 'resume-builder-presets'

let _idCounter = 0
function uid(prefix = 'id') {
  return `${prefix}_${Date.now().toString(36)}_${(++_idCounter).toString(36)}`
}

function createDefaultSettings(): TemplateSettings {
  return {
    templateId: 'classic',
    themeColor: '#333333',
    fontFamily: 'default',
    fontSize: 13,
    lineHeight: 1.7,
    marginMm: 25,
    photoShow: true,
  }
}

function createDefaultBasicInfo(): BasicInfo {
  return {
    name: '示例候选人', gender: '男', birthday: '1996-06', email: 'candidate@example.com',
    mobile: '138-0000-0000', location: '示例城市', workYears: '3年', photoUrl: '',
  }
}

function createDefaultModules(): ResumeModule[] {
  return [
    {
      id: uid('mod'), type: 'intention', title: '求职意向', visible: true, sortIndex: 0,
      intention: { targetJob: '前端开发工程师', targetCity: '示例城市', salary: '15-25K', availableDate: '随时到岗' },
    },
    {
      id: uid('mod'), type: 'education', title: '教育背景', visible: true, sortIndex: 1,
      entries: [{
        id: uid('ent'), timeStart: '2014-09', timeEnd: '2018-07', isCurrent: false,
        orgName: '华东理工大学', role: '计算机科学与技术 · 本科',
        detail: '主修课程：数据结构与算法、操作系统、计算机网络、数据库系统、软件工程\nGPA 3.6/4.0，获校级二等奖学金 2 次',
      }],
    },
    {
      id: uid('mod'), type: 'work', title: '工作经验', visible: true, sortIndex: 2,
      entries: [
        {
          id: uid('ent'), timeStart: '2021-03', timeEnd: '', isCurrent: true,
          orgName: '示例科技有限公司', role: '高级前端开发工程师',
          detail: '- 负责公司核心电商平台前端架构设计与开发，使用 Vue 3 + TypeScript + Vite 技术栈\n- 主导前端性能优化，首屏加载时间从 3.2s 降至 1.1s，Lighthouse 评分提升至 92 分\n- 搭建组件库与前端工程化体系，统一团队开发规范，提升研发效率 30%\n- 对接后端 RESTful API，实现订单、支付、用户中心等核心业务模块',
        },
        {
          id: uid('ent'), timeStart: '2018-07', timeEnd: '2021-02', isCurrent: false,
          orgName: '示例数据科技有限公司', role: '前端开发工程师',
          detail: '- 参与 B 端数据可视化平台开发，使用 React + ECharts 实现多维度数据看板\n- 负责移动端 H5 页面开发与微信小程序维护\n- 编写单元测试与 E2E 测试，代码覆盖率保持在 85% 以上',
        },
      ],
    },
    {
      id: uid('mod'), type: 'project', title: '项目经验', visible: true, sortIndex: 3,
      entries: [{
        id: uid('ent'), timeStart: '2022-06', timeEnd: '2023-01', isCurrent: false,
        orgName: '智能客服平台', role: '前端负责人',
        detail: '- 基于 Vue 3 + WebSocket 实现实时聊天界面，支持富文本、图片、文件消息\n- 集成 AI 对话能力，实现流式打字效果与对话历史管理\n- 设计可拖拽的工作台布局，支持多会话并行处理，日均服务 5000+ 用户',
      }],
    },
    {
      id: uid('mod'), type: 'skills', title: '技能特长', visible: true, sortIndex: 4,
      content: '- 熟练掌握 Vue 2/3、React、TypeScript，具备大型 SPA 架构设计能力\n- 熟悉 Node.js、Webpack、Vite 等前端工程化工具链\n- 掌握 Git 工作流、CI/CD 流程、Docker 基础运维\n- 良好的英文文档阅读能力（CET-6 530 分）',
    },
    {
      id: uid('mod'), type: 'evaluation', title: '自我评价', visible: true, sortIndex: 5,
      content: '3 年前端开发经验，具备从 0 到 1 搭建前端项目的能力。注重代码质量与工程规范，善于性能优化与技术方案选型。具有良好的沟通协作能力，能够高效推动跨团队合作。对新技术保持热情，持续关注前端生态发展。',
    },
  ]
}

function createBlankDocument(): ResumeDocument {
  return {
    id: uid('doc'),
    mode: 'general',
    targetJd: '',
    settings: createDefaultSettings(),
    basicInfo: createDefaultBasicInfo(),
    modules: createDefaultModules(),
    polishSuggestions: [],
  }
}

export type BuilderPhase = 'editing' | 'polishing' | 'exporting'

export const useResumeBuilderStore = defineStore('resumeBuilder', () => {
  // ===== State =====
  const phase = ref<BuilderPhase>('editing')
  const document = ref<ResumeDocument>(createBlankDocument())
  const previewZoom = ref(0.75)
  const activeModuleId = ref<string | null>(null)
  const isDirty = ref(false)
  const error = ref('')
  const polishDrawerOpen = ref(false)
  const isPolishing = ref(false)

  // ===== Computed =====
  const visibleModules = computed(() =>
    [...document.value.modules].filter(m => m.visible).sort((a, b) => a.sortIndex - b.sortIndex)
  )
  const sortedModules = computed(() =>
    [...document.value.modules].sort((a, b) => a.sortIndex - b.sortIndex)
  )
  const pendingPolishCount = computed(() =>
    document.value.polishSuggestions.filter(s => s.status === 'pending').length
  )

  // ===== Init =====
  function initBlank() {
    document.value = createBlankDocument()
    isDirty.value = false
    error.value = ''
    phase.value = 'editing'
  }

  // ===== BasicInfo =====
  function updateBasicInfo(partial: Partial<BasicInfo>) {
    Object.assign(document.value.basicInfo, partial)
    isDirty.value = true
  }

  // ===== Settings =====
  function updateSettings(partial: Partial<TemplateSettings>) {
    Object.assign(document.value.settings, partial)
    isDirty.value = true
  }
  function setTemplate(id: TemplateId) {
    document.value.settings.templateId = id
    isDirty.value = true
  }

  // ===== Module CRUD =====
  function addModule(type: ModuleType, title?: string) {
    const maxSort = Math.max(0, ...document.value.modules.map(m => m.sortIndex))
    const mod: ResumeModule = {
      id: uid('mod'),
      type,
      title: title || MODULE_TYPE_META[type]?.label || '自定义模块',
      visible: true,
      sortIndex: maxSort + 1,
      ...(['education', 'work', 'project', 'internship', 'campus'].includes(type) ? { entries: [] } : {}),
      ...(type === 'intention' ? { intention: { targetJob: '', targetCity: '', salary: '', availableDate: '' } } : {}),
      ...(type === 'skills' ? { content: '' } : {}),
      ...(['certificates', 'evaluation', 'hobbies', 'custom'].includes(type) ? { content: '' } : {}),
      ...(type === 'hobbies' ? { tags: [] } : {}),
    }
    document.value.modules.push(mod)
    isDirty.value = true
    return mod.id
  }

  function removeModule(moduleId: string) {
    const idx = document.value.modules.findIndex(m => m.id === moduleId)
    if (idx !== -1) {
      document.value.modules.splice(idx, 1)
      isDirty.value = true
    }
  }

  function toggleModuleVisibility(moduleId: string) {
    const mod = document.value.modules.find(m => m.id === moduleId)
    if (mod) { mod.visible = !mod.visible; isDirty.value = true }
  }

  function updateModule(moduleId: string, partial: Partial<ResumeModule>) {
    const mod = document.value.modules.find(m => m.id === moduleId)
    if (mod) { Object.assign(mod, partial); isDirty.value = true }
  }

  function reorderModules(fromIndex: number, toIndex: number) {
    const sorted = [...document.value.modules].sort((a, b) => a.sortIndex - b.sortIndex)
    const moved = sorted.splice(fromIndex, 1)[0]
    if (!moved) return
    sorted.splice(toIndex, 0, moved)
    sorted.forEach((m, i) => { m.sortIndex = i })
    isDirty.value = true
  }

  // ===== Entry CRUD =====
  function addEntry(moduleId: string): string {
    const mod = document.value.modules.find(m => m.id === moduleId)
    if (!mod) return ''
    if (!mod.entries) mod.entries = []
    const entry: TimeRangeEntry = {
      id: uid('ent'), timeStart: '', timeEnd: '', isCurrent: false,
      orgName: '', role: '', detail: '',
    }
    mod.entries.push(entry)
    isDirty.value = true
    return entry.id
  }

  function removeEntry(moduleId: string, entryId: string) {
    const mod = document.value.modules.find(m => m.id === moduleId)
    if (!mod?.entries) return
    const idx = mod.entries.findIndex(e => e.id === entryId)
    if (idx !== -1) { mod.entries.splice(idx, 1); isDirty.value = true }
  }

  function updateEntry(moduleId: string, entryId: string, partial: Partial<TimeRangeEntry>) {
    const mod = document.value.modules.find(m => m.id === moduleId)
    const entry = mod?.entries?.find(e => e.id === entryId)
    if (entry) { Object.assign(entry, partial); isDirty.value = true }
  }

  // ===== AI Polish =====
  function acceptPolish(suggestionId: string) {
    const sug = document.value.polishSuggestions.find(s => s.id === suggestionId)
    if (!sug || sug.status !== 'pending') return
    sug.status = 'accepted'
    const mod = document.value.modules.find(m => m.id === sug.moduleId)
    if (!mod) return
    if (sug.entryId && mod.entries) {
      const entry = mod.entries.find(e => e.id === sug.entryId)
      if (entry && sug.fieldPath in entry) {
        ;(entry as any)[sug.fieldPath] = sug.suggestedText
      }
    } else if (sug.fieldPath === 'content' && mod.content !== undefined) {
      mod.content = mod.content.replace(sug.originalText, sug.suggestedText)
    }
    isDirty.value = true
  }

  function rejectPolish(suggestionId: string) {
    const sug = document.value.polishSuggestions.find(s => s.id === suggestionId)
    if (sug) sug.status = 'rejected'
  }

  // ===== localStorage =====
  function autoSave() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(document.value))
      isDirty.value = false
    } catch { /* quota exceeded */ }
  }

  function loadDraft(): boolean {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return false
      document.value = JSON.parse(raw)
      isDirty.value = false
      return true
    } catch { return false }
  }

  function clearDraft() {
    localStorage.removeItem(STORAGE_KEY)
  }

  // ===== Presets =====
  function getPresets(): TemplatePreset[] {
    try {
      return JSON.parse(localStorage.getItem(PRESETS_KEY) || '[]')
    } catch { return [] }
  }

  function savePreset(name: string) {
    const presets = getPresets()
    presets.push({ id: uid('pre'), name, settings: { ...document.value.settings }, savedAt: Date.now() })
    localStorage.setItem(PRESETS_KEY, JSON.stringify(presets))
  }

  function loadPreset(presetId: string) {
    const preset = getPresets().find(p => p.id === presetId)
    if (preset) { Object.assign(document.value.settings, preset.settings); isDirty.value = true }
  }

  function deletePreset(presetId: string) {
    const presets = getPresets().filter(p => p.id !== presetId)
    localStorage.setItem(PRESETS_KEY, JSON.stringify(presets))
  }

  // ===== Auto-save watcher =====
  watch(document, () => { isDirty.value = true }, { deep: true })

  // ===== Export PDF =====
  async function exportPdf() {
    phase.value = 'exporting'
    error.value = ''
    try {
      // 将简历文档转换为后端需要的 sections 格式
      const sections = convertDocumentToSections()

      const response = await fetch(buildApiUrl('/api/resume/export'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sections }),
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.message || '导出失败')
      }

      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = window.document.createElement('a')
      a.href = url
      a.download = `${document.value.basicInfo.name || '简历'}_${Date.now()}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err: any) {
      error.value = err.message || '导出失败'
      throw err
    } finally {
      phase.value = 'editing'
    }
  }

  function convertDocumentToSections() {
    const sections: any[] = []

    // 基本信息
    const { name, gender, birthday, email, mobile, location, workYears } = document.value.basicInfo
    const contactInfo = [mobile, email, location, workYears].filter(Boolean).join(' | ')
    sections.push({
      type: 'header',
      content: `# ${name}\n\n${gender ? gender + ' | ' : ''}${birthday ? birthday + ' | ' : ''}${contactInfo}`,
    })

    // 遍历所有可见模块
    visibleModules.value.forEach(mod => {
      sections.push({ type: 'section', title: mod.title })

      if (mod.type === 'intention' && mod.intention) {
        const { targetJob, targetCity, salary, availableDate } = mod.intention
        const line = [targetJob, targetCity, salary, availableDate].filter(Boolean).join(' | ')
        sections.push({ type: 'text', content: line })
      } else if (mod.entries?.length) {
        mod.entries.forEach(entry => {
          const timeRange = entry.isCurrent
            ? `${entry.timeStart} - 至今`
            : `${entry.timeStart} - ${entry.timeEnd}`
          sections.push({
            type: 'entry',
            title: entry.orgName,
            subtitle: entry.role,
            time: timeRange,
            content: entry.detail,
          })
        })
      } else if (mod.skillBars?.length) {
        const skillText = mod.skillBars.map(sk => `${sk.name} (${sk.level}%)`).join(' · ')
        sections.push({ type: 'text', content: skillText })
      } else if (mod.tags?.length) {
        sections.push({ type: 'text', content: mod.tags.join('，') })
      } else if (mod.content) {
        sections.push({ type: 'text', content: mod.content })
      }
    })

    return sections
  }

  // ===== AI Polish =====
  async function requestPolish() {
    isPolishing.value = true
    error.value = ''
    document.value.polishSuggestions = []
    try {
      // 调用后端 AI 优化接口
      const response = await fetch(buildApiUrl('/api/resume/polish'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          modules: document.value.modules,
          targetJd: document.value.targetJd,
          mode: document.value.mode,
        }),
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.message || 'AI 优化失败')
      }

      const data = await response.json()

      // 将后端返回的建议转换为前端格式
      document.value.polishSuggestions = data.suggestions.map((sug: any) => ({
        id: sug.id || uid('sug'),
        moduleId: sug.moduleId,
        entryId: sug.entryId || undefined,
        fieldPath: sug.fieldPath,
        originalText: sug.originalText,
        suggestedText: sug.suggestedText,
        reason: sug.reason,
        status: 'pending' as const,
      }))

      // 如果没有建议，提示用户
      if (document.value.polishSuggestions.length === 0) {
        error.value = 'AI 未发现明显可优化的地方，你的简历已经很棒了！'
      }
    } catch (err: any) {
      error.value = err.message || 'AI 优化失败'
      throw err
    } finally {
      isPolishing.value = false
    }
  }

  return {
    // state
    phase, document, previewZoom, activeModuleId, isDirty, error, polishDrawerOpen, isPolishing,
    // computed
    visibleModules, sortedModules, pendingPolishCount,
    // init
    initBlank,
    // basic info
    updateBasicInfo,
    // settings
    updateSettings, setTemplate,
    // modules
    addModule, removeModule, toggleModuleVisibility, updateModule, reorderModules,
    // entries
    addEntry, removeEntry, updateEntry,
    // polish
    acceptPolish, rejectPolish, requestPolish,
    // storage
    autoSave, loadDraft, clearDraft,
    // presets
    getPresets, savePreset, loadPreset, deletePreset,
    // export
    exportPdf,
  }
})
