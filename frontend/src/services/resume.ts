import axios from 'axios'
import type { ResumeAnalyzeResponse, ResumeReportContext, ResumeSection } from '../types/resume'
import { fetchSSE, type SSECallbacks } from './sse'
import { buildApiUrl, getRuntimeApiBaseUrl } from './runtimeConfig'
import { assertValidResumeFile } from '../utils/resumeFile'

// 独立的 axios 实例（resume 模块有自己的 token）
const resumeApi = axios.create({
  timeout: 180000 // OCR + LLM 分析可能较慢
})

let _resumeToken = ''

export function setResumeToken(token: string) {
  _resumeToken = token
}

export function clearResumeToken() {
  _resumeToken = ''
}

resumeApi.interceptors.request.use((config) => {
  const url = config.url || ''
  if (!/^https?:\/\//i.test(url)) {
    config.baseURL = getRuntimeApiBaseUrl()
  }
  if (_resumeToken) {
    config.headers.Authorization = `Bearer ${_resumeToken}`
  }
  return config
})

export async function analyzeResume(file: File, jobTitle: string, reportContext?: ResumeReportContext | null, modelProvider = ''): Promise<ResumeAnalyzeResponse> {
  assertValidResumeFile(file)
  const formData = new FormData()
  formData.append('resume', file)
  if (jobTitle) formData.append('job_title', jobTitle)
  if (reportContext) formData.append('report_context', JSON.stringify(reportContext))
  if (modelProvider) formData.append('model_provider', modelProvider)
  const { data } = await resumeApi.post<ResumeAnalyzeResponse>('/api/resume/analyze', formData)
  return data
}

/** 使用已有 OCR 文本直接分析（跳过 OCR，复用面试结果） */
export async function analyzeResumeWithOcr(ocrText: string, jobTitle: string, reportContext?: ResumeReportContext | null, modelProvider = ''): Promise<ResumeAnalyzeResponse> {
  const { data } = await resumeApi.post<ResumeAnalyzeResponse>('/api/resume/analyze', {
    ocr_text: ocrText,
    job_title: jobTitle,
    report_context: reportContext || undefined,
    model_provider: modelProvider || undefined,
  })
  return data
}

/** 流式分析简历（上传文件） */
export async function analyzeResumeStream(file: File, jobTitle: string, callbacks: SSECallbacks, reportContext?: ResumeReportContext | null, modelProvider = ''): Promise<void> {
  assertValidResumeFile(file)
  const formData = new FormData()
  formData.append('resume', file)
  if (jobTitle) formData.append('job_title', jobTitle)
  if (reportContext) formData.append('report_context', JSON.stringify(reportContext))
  if (modelProvider) formData.append('model_provider', modelProvider)
  await fetchSSE(buildApiUrl('/api/resume/analyze-stream'), formData, callbacks)
}

/** 流式分析简历（使用已有 OCR 文本） */
export async function analyzeResumeWithOcrStream(ocrText: string, jobTitle: string, callbacks: SSECallbacks, reportContext?: ResumeReportContext | null, modelProvider = ''): Promise<void> {
  await fetchSSE(buildApiUrl('/api/resume/analyze-stream'), {
    ocr_text: ocrText,
    job_title: jobTitle,
    report_context: reportContext || undefined,
    model_provider: modelProvider || undefined,
  }, callbacks)
}

/** 获取当前用户最近一条有 OCR 结果的简历（使用主 api 实例获取 JWT 认证） */
export async function fetchLatestResume(): Promise<{ file_name: string; ocr_result: string; session_id: string } | null> {
  try {
    // 动态导入主 api 实例（带 JWT 认证）
    const { default: mainApi } = await import('./api')
    const { data } = await mainApi.get('/api/history/resume/latest')
    return data
  } catch {
    return null
  }
}

export async function exportResumePdf(sections: ResumeSection[]): Promise<Blob> {
  try {
    const { data } = await resumeApi.post('/api/resume/export', { sections }, {
      responseType: 'blob'
    })
    // 如果后端返回了 JSON 错误（content-type 不是 pdf），解析错误信息
    if (data.type && data.type.includes('application/json')) {
      const text = await data.text()
      const json = JSON.parse(text)
      throw new Error(json.message || '导出失败')
    }
    return data
  } catch (e: any) {
    // axios blob 模式下，错误响应也是 blob，需要特殊处理
    if (e.response?.data instanceof Blob) {
      const text = await e.response.data.text()
      try {
        const json = JSON.parse(text)
        throw new Error(json.message || '导出失败')
      } catch (parseErr) {
        if (parseErr instanceof SyntaxError) throw new Error(text || '导出失败')
        throw parseErr
      }
    }
    throw e
  }
}

export async function exportHtmlPdf(html: string): Promise<Blob> {
  try {
    const { data } = await resumeApi.post('/api/export-html-pdf', { html }, {
      responseType: 'blob'
    })
    if (data.type && data.type.includes('application/json')) {
      const text = await data.text()
      const json = JSON.parse(text)
      throw new Error(json.message || '导出失败')
    }
    return data
  } catch (e: any) {
    if (e.response?.data instanceof Blob) {
      const text = await e.response.data.text()
      try {
        const json = JSON.parse(text)
        throw new Error(json.message || '导出失败')
      } catch (parseErr) {
        if (parseErr instanceof SyntaxError) throw new Error(text || '导出失败')
        throw parseErr
      }
    }
    throw e
  }
}
