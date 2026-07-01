import type { LegacyImportSummary, RuntimeModelRecord } from './models'

const API_BASE_URL_STORAGE_KEY = 'proview_runtime_api_base_url'

export interface RuntimeConfigFieldSnapshot {
  label: string
  secret: boolean
  configured: boolean
  value: string
  display_value: string
  description: string
}

export interface RuntimeConfigResponse {
  status: string
  env_file_path: string
  models_file_path?: string
  legacy_import?: LegacyImportSummary
  fields: Record<string, RuntimeConfigFieldSnapshot>
  models: RuntimeModelRecord[]
  default_model_id?: string
  speech_available: boolean
  message?: string
}

export function normalizeApiBaseUrl(value: string): string {
  const trimmed = String(value || '').trim()
  if (!trimmed) {
    return ''
  }
  return trimmed.replace(/\/+$/, '')
}

export function getRuntimeApiBaseUrl(): string {
  try {
    const stored = typeof localStorage === 'undefined'
      ? ''
      : localStorage.getItem(API_BASE_URL_STORAGE_KEY) || ''
    if (stored.trim()) {
      return normalizeApiBaseUrl(stored)
    }
  } catch {
    // Ignore storage access failures.
  }

  return normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL || '')
}

export function setRuntimeApiBaseUrl(value: string): string {
  const normalized = normalizeApiBaseUrl(value)
  try {
    if (typeof localStorage !== 'undefined') {
      if (normalized) {
        localStorage.setItem(API_BASE_URL_STORAGE_KEY, normalized)
      } else {
        localStorage.removeItem(API_BASE_URL_STORAGE_KEY)
      }
    }
  } catch {
    // Ignore storage access failures.
  }
  return normalized
}

export function describeRuntimeApiBaseUrl(value?: string): string {
  const normalized = normalizeApiBaseUrl(value ?? getRuntimeApiBaseUrl())
  return normalized || '同源地址 / Vite 代理'
}

export function buildApiUrl(path: string, baseOverride?: string): string {
  if (/^https?:\/\//i.test(path)) {
    return path
  }

  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const base = normalizeApiBaseUrl(baseOverride ?? getRuntimeApiBaseUrl())
  return base ? `${base}${normalizedPath}` : normalizedPath
}

async function parseRuntimeConfigResponse(response: Response): Promise<RuntimeConfigResponse> {
  const text = await response.text()
  let data = {} as RuntimeConfigResponse
  try {
    data = text ? JSON.parse(text) as RuntimeConfigResponse : {} as RuntimeConfigResponse
  } catch {
    if (!response.ok) {
      throw new Error(text || `HTTP ${response.status}`)
    }
  }
  if (!response.ok || data.status === 'error') {
    throw new Error(data.message || `HTTP ${response.status}`)
  }
  return data
}

export async function fetchRuntimeConfig(baseOverride?: string): Promise<RuntimeConfigResponse> {
  const response = await fetch(buildApiUrl('/api/runtime-config', baseOverride), {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  })
  return parseRuntimeConfigResponse(response)
}

export async function saveRuntimeConfig(
  fields: Record<string, string>,
  baseOverride?: string,
): Promise<RuntimeConfigResponse> {
  const response = await fetch(buildApiUrl('/api/runtime-config', baseOverride), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ fields }),
  })
  return parseRuntimeConfigResponse(response)
}

export async function probeApiHealth(baseUrl: string): Promise<void> {
  const response = await fetch(buildApiUrl('/api/health', baseUrl), {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  })

  const text = await response.text()
  let data: Record<string, unknown> = {}
  try {
    data = text ? JSON.parse(text) as Record<string, unknown> : {}
  } catch {
    // Ignore invalid JSON and fall back to HTTP status below.
  }

  if (!response.ok || data.status !== 'ok') {
    const message = typeof data.message === 'string' && data.message
      ? data.message
      : `连接失败: HTTP ${response.status}`
    throw new Error(message)
  }
}
