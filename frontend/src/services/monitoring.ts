import api from './api'
import type {
  MonitoringCostsData,
  MonitoringEnvelope,
  MonitoringLatencyData,
  MonitoringModelsData,
  MonitoringOverviewData,
  MonitoringRecentTracesData,
  MonitoringStatusData,
  MonitoringToolsData,
  MonitoringTraceDetail,
} from '../types/monitoring'

export interface MonitoringQuery {
  hours?: number
  limit?: number
}

function params(query: MonitoringQuery = {}) {
  return {
    hours: query.hours ?? 24,
    limit: query.limit ?? 100,
  }
}

export async function fetchMonitoringStatus() {
  const response = await api.get<MonitoringEnvelope<MonitoringStatusData>>('/api/monitoring/status')
  return response.data
}

export async function fetchMonitoringOverview(query: MonitoringQuery = {}) {
  const response = await api.get<MonitoringEnvelope<MonitoringOverviewData>>('/api/monitoring/overview', {
    params: params(query),
  })
  return response.data
}

export async function fetchMonitoringTools(query: MonitoringQuery = {}) {
  const response = await api.get<MonitoringEnvelope<MonitoringToolsData>>('/api/monitoring/tools', {
    params: params(query),
  })
  return response.data
}

export async function fetchMonitoringModels(query: MonitoringQuery = {}) {
  const response = await api.get<MonitoringEnvelope<MonitoringModelsData>>('/api/monitoring/models', {
    params: params(query),
  })
  return response.data
}

export async function fetchMonitoringLatency(query: MonitoringQuery = {}) {
  const response = await api.get<MonitoringEnvelope<MonitoringLatencyData>>('/api/monitoring/latency', {
    params: params(query),
  })
  return response.data
}

export async function fetchMonitoringCosts(query: MonitoringQuery = {}) {
  const response = await api.get<MonitoringEnvelope<MonitoringCostsData>>('/api/monitoring/costs', {
    params: params(query),
  })
  return response.data
}

export async function fetchMonitoringRecentTraces(query: MonitoringQuery = {}) {
  const response = await api.get<MonitoringEnvelope<MonitoringRecentTracesData>>('/api/monitoring/traces/recent', {
    params: params(query),
  })
  return response.data
}

export async function fetchMonitoringTraceDetail(traceId: string) {
  const response = await api.get<MonitoringEnvelope<MonitoringTraceDetail>>(`/api/monitoring/traces/${traceId}`)
  return response.data
}
