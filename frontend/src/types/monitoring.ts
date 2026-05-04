export interface MonitoringTimeRange {
  start: string
  end: string
}

export interface MonitoringEnvelope<T> {
  configured: boolean
  available: boolean
  source: string
  range: MonitoringTimeRange | null
  data: T
  message: string
}

export interface MonitoringStatusData {
  enabled: boolean
}

export interface MonitoringTraceSummary {
  trace_id: string
  timestamp: string
  session_id: string | null
  name: string | null
  status: string
  duration_ms: number | null
  input_preview: string
  output_preview: string
  total_cost: number | null
  tags: string[]
  tool_names?: string[]
  business_context?: Record<string, string | number | boolean | null>
}

export interface MonitoringObservation {
  id: string
  trace_id: string
  parent_observation_id: string | null
  name: string | null
  type: string
  level: string | null
  status_message: string | null
  start_time: string | null
  end_time: string | null
  duration_ms: number | null
  model: string | null
  input_preview: string
  output_preview: string
  usage: Record<string, number | string>
  cost: number | null
}

export interface MonitoringTraceDetail extends MonitoringTraceSummary {
  user_id: string | null
  release: string | null
  version: string | null
  environment: string | null
  metadata: Record<string, unknown>
  scores: unknown[]
  observations: MonitoringObservation[]
}

export interface MonitoringOverviewData {
  trace_count: number
  observation_count: number
  llm_call_count: number
  tool_call_count: number
  error_count: number
  success_rate: number | null
  total_cost: number
  avg_trace_latency_ms: number | null
  p95_trace_latency_ms: number | null
  slowest_traces: MonitoringTraceSummary[]
}

export interface MonitoringToolBucket {
  tool_name: string
  call_count: number
  error_count: number
  avg_latency_ms: number | null
  p95_latency_ms: number | null
}

export interface MonitoringToolsData {
  tool_call_count: number
  tool_error_count: number
  tools: MonitoringToolBucket[]
  recent_tool_calls: MonitoringObservation[]
}

export interface MonitoringModelBucket {
  model: string
  call_count: number
  error_count: number
  avg_latency_ms: number | null
  p95_latency_ms: number | null
  total_cost: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
  usage_details?: Record<string, number>
}

export interface MonitoringModelsData {
  llm_call_count: number
  llm_error_count: number
  models: MonitoringModelBucket[]
}

export interface MonitoringLatencyData {
  avg_trace_latency_ms: number | null
  p95_trace_latency_ms: number | null
  avg_llm_latency_ms: number | null
  p95_llm_latency_ms: number | null
  avg_tool_latency_ms: number | null
  p95_tool_latency_ms: number | null
  slowest_traces: MonitoringTraceSummary[]
  slowest_observations: MonitoringObservation[]
}

export interface MonitoringCostsData {
  total_cost: number
  avg_cost_per_trace: number | null
  input_tokens: number
  output_tokens: number
  total_tokens: number
  avg_tokens_per_trace: number | null
  models: MonitoringModelBucket[]
  cost_note: string
}

export interface MonitoringRecentTracesData {
  traces: MonitoringTraceSummary[]
}
