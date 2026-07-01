import { buildApiUrl } from './runtimeConfig'

export interface RuntimeModelRecord {
  id: string
  key: string
  name: string
  label: string
  provider: string
  model: string
  base_url: string
  enabled: boolean
  available: boolean
  configured: boolean
  is_default: boolean
  api_key_configured: boolean
  api_key_display: string
  created_at?: string
  updated_at?: string
}

export interface LegacyImportSummary {
  version: number
  source: string
  status: 'imported' | 'imported_incomplete' | 'not_found' | 'skipped_existing_models_file' | 'recreated_after_invalid_file' | 'unknown' | string
  checked_at: string
  legacy_config_found: boolean
  existing_models_file: boolean
  imported_count: number
  available_count: number
  imported_model_ids: string[]
  message: string
}

export interface ModelsResponse {
  status: string
  version: number
  file_path: string
  default_model_id: string
  legacy_import?: LegacyImportSummary
  models: RuntimeModelRecord[]
  message?: string
}

export interface ModelProbeResult {
  ok: boolean
  code: 'ok' | 'model_not_configured' | 'connection_failed' | string
  message: string
  latency_ms?: number
  missing_fields?: string[]
}

export interface ModelProbeResponse {
  status: string
  model_id: string
  probe: ModelProbeResult
  message?: string
}

export interface ModelMutationPayload {
  id?: string
  name: string
  model: string
  base_url: string
  api_key?: string
  enabled: boolean
  provider?: string
}

async function parseModelsResponse(response: Response): Promise<ModelsResponse> {
  const text = await response.text()
  let data = {} as ModelsResponse
  try {
    data = text ? JSON.parse(text) as ModelsResponse : {} as ModelsResponse
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

async function parseModelProbeResponse(response: Response): Promise<ModelProbeResponse> {
  const text = await response.text()
  let data = {} as ModelProbeResponse
  try {
    data = text ? JSON.parse(text) as ModelProbeResponse : {} as ModelProbeResponse
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

export async function fetchModels(baseOverride?: string): Promise<ModelsResponse> {
  const response = await fetch(buildApiUrl('/api/models', baseOverride), {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  })
  return parseModelsResponse(response)
}

export async function createModel(model: ModelMutationPayload, baseOverride?: string): Promise<ModelsResponse> {
  const response = await fetch(buildApiUrl('/api/models', baseOverride), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ model }),
  })
  return parseModelsResponse(response)
}

export async function updateModel(modelId: string, model: ModelMutationPayload, baseOverride?: string): Promise<ModelsResponse> {
  const response = await fetch(buildApiUrl(`/api/models/${encodeURIComponent(modelId)}`, baseOverride), {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ model }),
  })
  return parseModelsResponse(response)
}

export async function deleteModel(modelId: string, baseOverride?: string): Promise<ModelsResponse> {
  const response = await fetch(buildApiUrl(`/api/models/${encodeURIComponent(modelId)}`, baseOverride), {
    method: 'DELETE',
    headers: {
      Accept: 'application/json',
    },
  })
  return parseModelsResponse(response)
}

export async function setDefaultModel(modelId: string, baseOverride?: string): Promise<ModelsResponse> {
  const response = await fetch(buildApiUrl(`/api/models/${encodeURIComponent(modelId)}/default`, baseOverride), {
    method: 'POST',
    headers: {
      Accept: 'application/json',
    },
  })
  return parseModelsResponse(response)
}

export async function probeModelConnection(modelId: string, baseOverride?: string): Promise<ModelProbeResponse> {
  const response = await fetch(buildApiUrl(`/api/models/${encodeURIComponent(modelId)}/probe`, baseOverride), {
    method: 'POST',
    headers: {
      Accept: 'application/json',
    },
  })
  return parseModelProbeResponse(response)
}
