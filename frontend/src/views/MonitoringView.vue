<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  Activity,
  AlertCircle,
  Brain,
  CheckCircle2,
  Clock3,
  DollarSign,
  Eye,
  RefreshCw,
  ServerCog,
  Wrench,
  X,
} from 'lucide-vue-next'
import {
  fetchMonitoringCosts,
  fetchMonitoringLatency,
  fetchMonitoringModels,
  fetchMonitoringOverview,
  fetchMonitoringRecentTraces,
  fetchMonitoringStatus,
  fetchMonitoringTools,
  fetchMonitoringTraceDetail,
} from '../services/monitoring'
import type {
  MonitoringCostsData,
  MonitoringEnvelope,
  MonitoringLatencyData,
  MonitoringModelBucket,
  MonitoringModelsData,
  MonitoringObservation,
  MonitoringOverviewData,
  MonitoringRecentTracesData,
  MonitoringStatusData,
  MonitoringToolsData,
  MonitoringTraceDetail,
  MonitoringTraceSummary,
} from '../types/monitoring'
import {
  DEFAULT_PRICING_VARIABLES,
  evaluatePricingFormula,
} from '../utils/pricingFormula'

interface PricingRule {
  formula: string
  currency: string
}

const PRICING_RULES_STORAGE_KEY = 'proview.monitoring.pricingRules.v1'
const pricingCurrencies = ['USD', 'CNY', 'EUR', 'JPY', 'credits']

const hoursOptions = [1, 6, 24, 72, 168]
const selectedHours = ref(24)
const loading = ref(false)
const detailLoading = ref(false)
const error = ref('')
const selectedTraceId = ref('')
const pricingRules = ref<Record<string, PricingRule>>({})
const pricingMessage = ref('')
let pricingMessageTimer: ReturnType<typeof setTimeout> | null = null

const status = ref<MonitoringEnvelope<MonitoringStatusData> | null>(null)
const overview = ref<MonitoringEnvelope<MonitoringOverviewData> | null>(null)
const tools = ref<MonitoringEnvelope<MonitoringToolsData> | null>(null)
const models = ref<MonitoringEnvelope<MonitoringModelsData> | null>(null)
const latency = ref<MonitoringEnvelope<MonitoringLatencyData> | null>(null)
const costs = ref<MonitoringEnvelope<MonitoringCostsData> | null>(null)
const traces = ref<MonitoringEnvelope<MonitoringRecentTracesData> | null>(null)
const traceDetail = ref<MonitoringEnvelope<MonitoringTraceDetail> | null>(null)

const currentRange = computed(() => overview.value?.range || traces.value?.range || null)
const traceList = computed(() => traces.value?.data?.traces || [])
const toolList = computed(() => tools.value?.data?.tools || [])
const modelList = computed(() => models.value?.data?.models || [])
const observationList = computed(() => traceDetail.value?.data?.observations || [])

const statusTone = computed(() => {
  if (!status.value) return 'idle'
  if (!status.value.configured || !status.value.available) return 'error'
  return 'success'
})

const overviewMetrics = computed(() => [
  {
    label: 'Traces',
    value: formatInteger(overview.value?.data?.trace_count),
    caption: 'Agent 执行',
    icon: Activity,
  },
  {
    label: 'LLM Calls',
    value: formatInteger(overview.value?.data?.llm_call_count),
    caption: '模型调用',
    icon: Brain,
  },
  {
    label: 'Tool Calls',
    value: formatInteger(overview.value?.data?.tool_call_count),
    caption: '工具调用',
    icon: Wrench,
  },
  {
    label: 'Success',
    value: formatPercent(overview.value?.data?.success_rate),
    caption: '成功率',
    icon: CheckCircle2,
  },
])

const latencyMetrics = computed(() => [
  { label: 'Trace AVG', value: formatMs(latency.value?.data?.avg_trace_latency_ms) },
  { label: 'Trace P95', value: formatMs(latency.value?.data?.p95_trace_latency_ms) },
  { label: 'LLM AVG', value: formatMs(latency.value?.data?.avg_llm_latency_ms) },
  { label: 'LLM P95', value: formatMs(latency.value?.data?.p95_llm_latency_ms) },
])

const costMetrics = computed(() => [
  { label: 'Input Tokens', value: formatInteger(costs.value?.data?.input_tokens) },
  { label: 'Output Tokens', value: formatInteger(costs.value?.data?.output_tokens) },
  { label: 'Total Tokens', value: formatInteger(costs.value?.data?.total_tokens) },
  { label: 'Avg / Trace', value: formatNumber(costs.value?.data?.avg_tokens_per_trace) },
])

const pricingEstimates = computed(() =>
  modelList.value.map((model) => {
    const rule = getPricingRule(model.model)
    const variables = buildPricingVariables(model)
    return {
      model,
      rule,
      variables,
      result: evaluatePricingFormula(rule.formula, variables),
    }
  }),
)

const estimatedCostTotal = computed(() =>
  pricingEstimates.value.reduce((total, estimate) => (
    estimate.result.ok && typeof estimate.result.value === 'number'
      ? total + estimate.result.value
      : total
  ), 0),
)

const configuredPricingCount = computed(() =>
  pricingEstimates.value.filter((estimate) => estimate.rule.formula.trim()).length,
)

const pricingVariableNames = computed(() => {
  const variables = new Set(DEFAULT_PRICING_VARIABLES)
  for (const model of modelList.value) {
    for (const key of Object.keys(model.usage_details || {})) {
      variables.add(key)
    }
  }
  return Array.from(variables)
})

function formatInteger(value: number | null | undefined) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '0'
  return new Intl.NumberFormat('zh-CN').format(Math.round(value))
}

function formatNumber(value: number | null | undefined) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-'
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(value)
}

function formatMs(value: number | null | undefined) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-'
  if (value >= 1000) return `${(value / 1000).toFixed(2)}s`
  return `${Math.round(value)}ms`
}

function formatMoney(value: number | null | undefined, digits = 6) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '0.0000'
  return value.toFixed(digits)
}

function formatPercent(value: number | null | undefined) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-'
  return `${Math.round(value * 100)}%`
}

function formatTime(value: string | null | undefined) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}:${String(date.getSeconds()).padStart(2, '0')}`
}

function compactTraceId(value: string | null | undefined) {
  if (!value) return '-'
  return value.length > 12 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value
}

function businessValue(trace: MonitoringTraceSummary | null | undefined, key: string) {
  const value = trace?.business_context?.[key]
  if (value === null || typeof value === 'undefined' || value === '') return '-'
  return String(value)
}

function traceBusinessLabel(trace: MonitoringTraceSummary) {
  return businessValue(trace, 'interaction_type')
}

function observationTypeClass(type: string | null | undefined) {
  const normalized = String(type || '').toLowerCase()
  if (normalized === 'generation') return 'monitoring-pill--model'
  if (normalized === 'tool') return 'monitoring-pill--tool'
  if (normalized === 'agent') return 'monitoring-pill--agent'
  return 'monitoring-pill--muted'
}

function statusClass(value: string | null | undefined) {
  return value === 'success' ? 'monitoring-status--success' : 'monitoring-status--warning'
}

function getPricingRule(modelName: string): PricingRule {
  return pricingRules.value[modelName] || { formula: '', currency: 'USD' }
}

function buildPricingVariables(model: MonitoringModelBucket) {
  const variables: Record<string, number> = {
    input_tokens: model.input_tokens || 0,
    output_tokens: model.output_tokens || 0,
    total_tokens: model.total_tokens || 0,
    call_count: model.call_count || 0,
    cache_hit_tokens: 0,
    cache_miss_tokens: 0,
    langfuse_cost: model.total_cost || 0,
  }

  for (const [key, value] of Object.entries(model.usage_details || {})) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      variables[key] = value
    }
  }

  return variables
}

function loadPricingRules() {
  try {
    const raw = localStorage.getItem(PRICING_RULES_STORAGE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return
    pricingRules.value = Object.fromEntries(
      Object.entries(parsed).filter(([, value]) => (
        value
        && typeof value === 'object'
        && typeof (value as PricingRule).formula === 'string'
        && typeof (value as PricingRule).currency === 'string'
      )),
    ) as Record<string, PricingRule>
  } catch {
    pricingRules.value = {}
  }
}

function persistPricingRules() {
  localStorage.setItem(PRICING_RULES_STORAGE_KEY, JSON.stringify(pricingRules.value))
  pricingMessage.value = '公式已保存'
  if (pricingMessageTimer) clearTimeout(pricingMessageTimer)
  pricingMessageTimer = setTimeout(() => {
    pricingMessage.value = ''
  }, 1600)
}

function updatePricingRule(modelName: string, patch: Partial<PricingRule>) {
  pricingRules.value = {
    ...pricingRules.value,
    [modelName]: {
      ...getPricingRule(modelName),
      ...patch,
    },
  }
  persistPricingRules()
}

function updatePricingFormula(modelName: string, event: Event) {
  updatePricingRule(modelName, { formula: readEventValue(event) })
}

function updatePricingCurrency(modelName: string, event: Event) {
  updatePricingRule(modelName, { currency: readEventValue(event) })
}

function readEventValue(event: Event) {
  return (event.target as HTMLInputElement | HTMLSelectElement | null)?.value || ''
}

async function loadDashboard() {
  loading.value = true
  error.value = ''
  const query = { hours: selectedHours.value, limit: 100 }

  try {
    const [
      statusResult,
      overviewResult,
      toolsResult,
      modelsResult,
      latencyResult,
      costsResult,
      tracesResult,
    ] = await Promise.all([
      fetchMonitoringStatus(),
      fetchMonitoringOverview(query),
      fetchMonitoringTools(query),
      fetchMonitoringModels(query),
      fetchMonitoringLatency(query),
      fetchMonitoringCosts(query),
      fetchMonitoringRecentTraces({ hours: selectedHours.value, limit: 20 }),
    ])

    status.value = statusResult
    overview.value = overviewResult
    tools.value = toolsResult
    models.value = modelsResult
    latency.value = latencyResult
    costs.value = costsResult
    traces.value = tracesResult
  } catch (err) {
    error.value = err instanceof Error ? err.message : '监控数据加载失败'
  } finally {
    loading.value = false
  }
}

async function openTrace(trace: MonitoringTraceSummary) {
  selectedTraceId.value = trace.trace_id
  detailLoading.value = true
  traceDetail.value = null
  try {
    traceDetail.value = await fetchMonitoringTraceDetail(trace.trace_id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Trace 详情加载失败'
  } finally {
    detailLoading.value = false
  }
}

function closeTraceDetail() {
  selectedTraceId.value = ''
  traceDetail.value = null
}

function observationTitle(observation: MonitoringObservation) {
  return observation.name || observation.model || observation.type || observation.id
}

onMounted(() => {
  loadPricingRules()
  loadDashboard()
})
</script>

<template>
  <div class="monitoring-page fade-in">
    <section class="monitoring-hero">
      <div class="monitoring-hero__copy">
        <span class="ui-section-badge">
          <Activity class="h-4 w-4" />
          Agent 监控
        </span>
        <h1 class="ui-page-title mt-4 text-3xl sm:text-4xl">Langfuse 运行监控</h1>
        <p class="ui-page-subtitle mt-3 max-w-3xl text-sm leading-7">
          这里聚合 Agent trace、模型调用、工具链路、Token 和延迟，用于快速判断运行状态。
        </p>
      </div>
      <div class="monitoring-hero__actions">
        <label class="monitoring-select">
          <span>时间范围</span>
          <select v-model.number="selectedHours" @change="loadDashboard">
            <option v-for="hours in hoursOptions" :key="hours" :value="hours">
              最近 {{ hours }} 小时
            </option>
          </select>
        </label>
        <button type="button" class="monitoring-button monitoring-button--primary" :disabled="loading" @click="loadDashboard">
          <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': loading }" />
          刷新
        </button>
      </div>
    </section>

    <section class="monitoring-status-panel">
      <div class="monitoring-status-panel__item">
        <ServerCog class="h-5 w-5" />
        <div>
          <p class="monitoring-label">Langfuse 状态</p>
          <strong :class="['monitoring-status-text', `monitoring-status-text--${statusTone}`]">
            {{ status?.available ? '可用' : '不可用' }}
          </strong>
        </div>
      </div>
      <div class="monitoring-status-panel__item">
        <Clock3 class="h-5 w-5" />
        <div>
          <p class="monitoring-label">查询窗口</p>
          <strong>{{ currentRange ? `${formatTime(currentRange.start)} - ${formatTime(currentRange.end)}` : '-' }}</strong>
        </div>
      </div>
      <div class="monitoring-status-panel__item">
        <AlertCircle class="h-5 w-5" />
        <div>
          <p class="monitoring-label">错误数</p>
          <strong>{{ formatInteger(overview?.data?.error_count) }}</strong>
        </div>
      </div>
    </section>

    <section v-if="error" class="monitoring-alert">
      {{ error }}
    </section>

    <section class="monitoring-grid monitoring-grid--metrics">
      <article v-for="metric in overviewMetrics" :key="metric.label" class="monitoring-metric">
        <div class="monitoring-metric__icon">
          <component :is="metric.icon" class="h-5 w-5" />
        </div>
        <p class="monitoring-label">{{ metric.label }}</p>
        <strong>{{ metric.value }}</strong>
        <span>{{ metric.caption }}</span>
      </article>
    </section>

    <section class="monitoring-grid monitoring-grid--main">
      <article class="monitoring-section">
        <div class="monitoring-section__head">
          <div>
            <p class="monitoring-label">模型与 Token</p>
            <h2>模型调用</h2>
          </div>
          <Brain class="h-5 w-5" />
        </div>
        <div v-if="!modelList.length" class="monitoring-empty">当前时间范围内没有模型调用。</div>
        <div v-else class="monitoring-list">
          <div v-for="model in modelList" :key="model.model" class="monitoring-model-row">
            <div>
              <strong>{{ model.model }}</strong>
              <span>{{ model.call_count }} calls · {{ formatMs(model.avg_latency_ms) }} avg</span>
            </div>
            <div class="monitoring-model-row__tokens">
              <b>{{ formatInteger(model.total_tokens) }}</b>
              <span>tokens</span>
            </div>
          </div>
        </div>
      </article>

      <article class="monitoring-section">
        <div class="monitoring-section__head">
          <div>
            <p class="monitoring-label">成本与用量</p>
            <h2>Token 汇总</h2>
          </div>
          <DollarSign class="h-5 w-5" />
        </div>
        <div class="monitoring-mini-grid">
          <div v-for="item in costMetrics" :key="item.label" class="monitoring-mini">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
        <div class="monitoring-cost-note">
          <span>Langfuse Cost</span>
          <strong>{{ formatMoney(costs?.data?.total_cost) }}</strong>
        </div>
        <div class="monitoring-cost-note">
          <span>Estimated Cost</span>
          <strong>{{ formatMoney(estimatedCostTotal) }}</strong>
        </div>
        <p class="monitoring-note">已配置 {{ configuredPricingCount }} 个模型的自定义公式。</p>
        <p v-if="costs?.data?.cost_note" class="monitoring-note">{{ costs.data.cost_note }}</p>
      </article>

      <article class="monitoring-section">
        <div class="monitoring-section__head">
          <div>
            <p class="monitoring-label">工具链路</p>
            <h2>工具调用</h2>
          </div>
          <Wrench class="h-5 w-5" />
        </div>
        <div v-if="!toolList.length" class="monitoring-empty">当前时间范围内没有工具调用。</div>
        <div v-else class="monitoring-list">
          <div v-for="tool in toolList" :key="tool.tool_name" class="monitoring-tool-row">
            <div>
              <strong>{{ tool.tool_name }}</strong>
              <span>{{ tool.call_count }} calls · {{ tool.error_count }} errors</span>
            </div>
            <b>{{ formatMs(tool.avg_latency_ms) }}</b>
          </div>
        </div>
      </article>

      <article class="monitoring-section">
        <div class="monitoring-section__head">
          <div>
            <p class="monitoring-label">延迟</p>
            <h2>性能摘要</h2>
          </div>
          <Clock3 class="h-5 w-5" />
        </div>
        <div class="monitoring-mini-grid">
          <div v-for="item in latencyMetrics" :key="item.label" class="monitoring-mini">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
      </article>
    </section>

    <section class="monitoring-section monitoring-section--wide">
      <div class="monitoring-section__head">
        <div>
          <p class="monitoring-label">自定义成本估算</p>
          <h2>模型定价公式</h2>
        </div>
        <DollarSign class="h-5 w-5" />
      </div>
      <p class="monitoring-note">
        公式只支持数字、变量、四则运算和括号；结果作为 dashboard 估算值，不改写 Langfuse 原始成本。
      </p>
      <div class="monitoring-variable-list">
        <span v-for="variable in pricingVariableNames" :key="variable">{{ variable }}</span>
      </div>
      <div v-if="!pricingEstimates.length" class="monitoring-empty">当前时间范围内没有可配置定价的模型。</div>
      <div v-else class="monitoring-pricing-list">
        <div v-for="estimate in pricingEstimates" :key="estimate.model.model" class="monitoring-pricing-row">
          <div class="monitoring-pricing-row__summary">
            <strong>{{ estimate.model.model }}</strong>
            <span>
              {{ formatInteger(estimate.model.input_tokens) }} input ·
              {{ formatInteger(estimate.model.output_tokens) }} output ·
              {{ formatInteger(estimate.model.total_tokens) }} total
            </span>
          </div>
          <div class="monitoring-pricing-controls">
            <label class="monitoring-field monitoring-field--currency">
              <span>货币</span>
              <select :value="estimate.rule.currency" @change="updatePricingCurrency(estimate.model.model, $event)">
                <option v-for="currency in pricingCurrencies" :key="currency" :value="currency">{{ currency }}</option>
              </select>
            </label>
            <label class="monitoring-field">
              <span>公式</span>
              <input
                :value="estimate.rule.formula"
                type="text"
                spellcheck="false"
                placeholder="(input_tokens * 0.14 + output_tokens * 2.19) / 1000000"
                @input="updatePricingFormula(estimate.model.model, $event)"
              />
            </label>
          </div>
          <div class="monitoring-pricing-result" :class="{ 'monitoring-pricing-result--error': estimate.rule.formula && !estimate.result.ok }">
            <span>估算成本</span>
            <strong v-if="estimate.result.ok">{{ formatMoney(estimate.result.value) }} {{ estimate.rule.currency }}</strong>
            <strong v-else>-</strong>
            <em v-if="estimate.rule.formula && !estimate.result.ok">{{ estimate.result.error }}</em>
            <em v-else-if="!estimate.rule.formula">填写公式后自动计算</em>
          </div>
        </div>
      </div>
      <p v-if="pricingMessage" class="monitoring-note">{{ pricingMessage }}</p>
    </section>

    <section class="monitoring-section monitoring-section--wide">
      <div class="monitoring-section__head">
        <div>
          <p class="monitoring-label">最近 Trace</p>
          <h2>执行记录</h2>
        </div>
        <Eye class="h-5 w-5" />
      </div>
      <div v-if="!traceList.length" class="monitoring-empty">当前时间范围内没有 trace。</div>
      <div v-else class="monitoring-table">
        <button
          v-for="trace in traceList"
          :key="trace.trace_id"
          type="button"
          class="monitoring-trace-row"
          :class="{ 'monitoring-trace-row--active': selectedTraceId === trace.trace_id }"
          @click="openTrace(trace)"
        >
          <span>{{ formatTime(trace.timestamp) }}</span>
          <strong>{{ trace.name || 'Trace' }}</strong>
          <span>{{ formatMs(trace.duration_ms) }}</span>
          <span>
            <i v-if="traceBusinessLabel(trace) !== '-'">{{ traceBusinessLabel(trace) }}</i>
            <i v-for="tool in trace.tool_names || []" :key="tool">{{ tool }}</i>
          </span>
          <span :class="['monitoring-status', statusClass(trace.status)]">{{ trace.status }}</span>
          <code>{{ compactTraceId(trace.trace_id) }}</code>
        </button>
      </div>
    </section>

    <aside v-if="selectedTraceId" class="monitoring-detail">
      <div class="monitoring-detail__panel">
        <div class="monitoring-detail__head">
          <div>
            <p class="monitoring-label">Trace Detail</p>
            <h2>{{ traceDetail?.data?.name || compactTraceId(selectedTraceId) }}</h2>
          </div>
          <button type="button" class="monitoring-icon-button" @click="closeTraceDetail">
            <X class="h-5 w-5" />
          </button>
        </div>

        <div v-if="detailLoading" class="monitoring-empty">加载 Trace 详情...</div>
        <template v-else-if="traceDetail?.data">
          <div class="monitoring-detail__summary">
            <div>
              <span>Duration</span>
              <strong>{{ formatMs(traceDetail.data.duration_ms) }}</strong>
            </div>
            <div>
              <span>Status</span>
              <strong>{{ traceDetail.data.status }}</strong>
            </div>
            <div>
              <span>Tools</span>
              <strong>{{ traceDetail.data.tool_names?.join(', ') || '-' }}</strong>
            </div>
            <div>
              <span>Session</span>
              <strong>{{ compactTraceId(traceDetail.data.session_id) }}</strong>
            </div>
            <div>
              <span>Interaction</span>
              <strong>{{ businessValue(traceDetail.data, 'interaction_type') }}</strong>
            </div>
            <div>
              <span>Model</span>
              <strong>{{ businessValue(traceDetail.data, 'model_provider') }}</strong>
            </div>
          </div>

          <div class="monitoring-observation-list">
            <div v-for="observation in observationList" :key="observation.id" class="monitoring-observation">
              <span :class="['monitoring-pill', observationTypeClass(observation.type)]">{{ observation.type }}</span>
              <div>
                <strong>{{ observationTitle(observation) }}</strong>
                <span>{{ formatMs(observation.duration_ms) }} · {{ observation.model || 'no model' }}</span>
              </div>
              <code v-if="observation.usage?.total">{{ observation.usage.total }} tokens</code>
            </div>
          </div>
        </template>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.monitoring-page {
  display: grid;
  gap: 1.25rem;
  padding-bottom: 2rem;
}

.monitoring-hero,
.monitoring-status-panel,
.monitoring-section,
.monitoring-metric,
.monitoring-detail__panel {
  border: 1px solid var(--ui-border-default);
  background: var(--ui-surface-1);
  box-shadow: var(--ui-shadow-md);
}

.monitoring-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  border-radius: var(--ui-radius-lg);
  padding: 1.5rem;
}

.monitoring-hero__actions {
  display: flex;
  align-items: end;
  gap: 0.75rem;
}

.monitoring-select {
  display: grid;
  gap: 0.4rem;
  font-size: 0.78rem;
  font-weight: 800;
  color: var(--ui-text-muted);
}

.monitoring-select select {
  min-width: 150px;
  border-radius: 0.9rem;
  border: 1px solid var(--ui-border-default);
  background: var(--ui-surface-raised);
  color: var(--ui-text-primary);
  padding: 0.75rem 0.9rem;
  outline: none;
}

.monitoring-button,
.monitoring-icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--ui-border-default);
  background: var(--ui-surface-raised);
  color: var(--ui-text-primary);
  transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
}

.monitoring-button {
  gap: 0.5rem;
  border-radius: 0.9rem;
  padding: 0.78rem 1rem;
  font-size: 0.9rem;
  font-weight: 800;
}

.monitoring-button:hover:not(:disabled),
.monitoring-icon-button:hover {
  transform: translateY(-1px);
  border-color: var(--ui-border-strong);
  box-shadow: var(--ui-shadow-sm);
}

.monitoring-button:disabled {
  opacity: 0.62;
  cursor: not-allowed;
}

.monitoring-button--primary {
  background: var(--ui-accent);
  color: #fff;
  border-color: transparent;
}

.monitoring-status-panel {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
  border-radius: var(--ui-radius-md);
  padding: 0.9rem;
}

.monitoring-status-panel__item,
.monitoring-mini,
.monitoring-model-row,
.monitoring-tool-row,
.monitoring-observation,
.monitoring-detail__summary > div {
  border: 1px solid var(--ui-border-subtle);
  background: var(--ui-surface-raised);
}

.monitoring-status-panel__item {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  border-radius: 1rem;
  padding: 0.9rem;
  min-width: 0;
}

.monitoring-label {
  font-size: 0.72rem;
  font-weight: 900;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ui-text-muted);
}

.monitoring-status-text--success {
  color: var(--ui-success);
}

.monitoring-status-text--error {
  color: var(--ui-danger);
}

.monitoring-status-text--idle {
  color: var(--ui-text-secondary);
}

.monitoring-alert {
  border-radius: 1rem;
  border: 1px solid rgba(244, 63, 94, 0.2);
  background: var(--ui-danger-soft);
  padding: 0.9rem 1rem;
  color: var(--ui-danger);
  font-weight: 700;
}

.monitoring-grid {
  display: grid;
  gap: 1rem;
}

.monitoring-grid--metrics {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.monitoring-grid--main {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.monitoring-metric {
  border-radius: var(--ui-radius-md);
  padding: 1rem;
}

.monitoring-metric__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.95rem;
  background: var(--ui-accent-soft);
  color: var(--ui-accent-strong);
}

.monitoring-metric strong {
  display: block;
  margin-top: 0.65rem;
  font-size: 1.65rem;
  line-height: 1;
  font-weight: 900;
  color: var(--ui-text-primary);
}

.monitoring-metric span,
.monitoring-model-row span,
.monitoring-tool-row span,
.monitoring-note,
.monitoring-observation span {
  color: var(--ui-text-secondary);
  font-size: 0.82rem;
}

.monitoring-section {
  border-radius: var(--ui-radius-md);
  padding: 1rem;
}

.monitoring-section--wide {
  overflow: hidden;
}

.monitoring-section__head,
.monitoring-detail__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.monitoring-section__head h2,
.monitoring-detail__head h2 {
  margin-top: 0.25rem;
  font-size: 1.08rem;
  font-weight: 900;
  color: var(--ui-text-primary);
}

.monitoring-list,
.monitoring-observation-list {
  display: grid;
  gap: 0.75rem;
  margin-top: 1rem;
}

.monitoring-model-row,
.monitoring-tool-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  border-radius: 1rem;
  padding: 0.85rem;
}

.monitoring-model-row > div,
.monitoring-tool-row > div {
  display: grid;
  gap: 0.25rem;
  min-width: 0;
}

.monitoring-model-row strong,
.monitoring-tool-row strong,
.monitoring-observation strong {
  color: var(--ui-text-primary);
  font-weight: 850;
}

.monitoring-model-row__tokens {
  text-align: right;
}

.monitoring-model-row__tokens b,
.monitoring-tool-row b {
  color: var(--ui-accent-strong);
}

.monitoring-mini-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
  margin-top: 1rem;
}

.monitoring-mini {
  border-radius: 1rem;
  padding: 0.85rem;
}

.monitoring-mini span,
.monitoring-cost-note span {
  display: block;
  font-size: 0.72rem;
  font-weight: 800;
  color: var(--ui-text-muted);
}

.monitoring-mini strong,
.monitoring-cost-note strong {
  display: block;
  margin-top: 0.35rem;
  color: var(--ui-text-primary);
  font-size: 1rem;
  font-weight: 900;
}

.monitoring-cost-note {
  margin-top: 0.9rem;
  border-top: 1px solid var(--ui-border-subtle);
  padding-top: 0.85rem;
}

.monitoring-note {
  margin-top: 0.55rem;
  line-height: 1.6;
}

.monitoring-variable-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin-top: 0.75rem;
}

.monitoring-variable-list span {
  border-radius: 9999px;
  background: var(--ui-accent-soft);
  color: var(--ui-accent-strong);
  padding: 0.28rem 0.6rem;
  font-size: 0.76rem;
  font-weight: 850;
}

.monitoring-pricing-list {
  display: grid;
  gap: 0.75rem;
  margin-top: 1rem;
}

.monitoring-pricing-row {
  display: grid;
  grid-template-columns: minmax(170px, 0.75fr) minmax(260px, 1.4fr) minmax(150px, 0.65fr);
  align-items: start;
  gap: 0.85rem;
  border-radius: 1rem;
  border: 1px solid var(--ui-border-subtle);
  background: var(--ui-surface-raised);
  padding: 0.9rem;
}

.monitoring-pricing-row__summary,
.monitoring-pricing-result {
  display: grid;
  gap: 0.28rem;
  min-width: 0;
}

.monitoring-pricing-row__summary strong,
.monitoring-pricing-result strong {
  color: var(--ui-text-primary);
  font-weight: 900;
  overflow-wrap: anywhere;
}

.monitoring-pricing-row__summary span,
.monitoring-pricing-result span,
.monitoring-pricing-result em,
.monitoring-field span {
  color: var(--ui-text-secondary);
  font-size: 0.8rem;
}

.monitoring-pricing-controls {
  display: grid;
  grid-template-columns: minmax(88px, 0.25fr) minmax(180px, 1fr);
  gap: 0.65rem;
}

.monitoring-field {
  display: grid;
  gap: 0.35rem;
  min-width: 0;
}

.monitoring-field input,
.monitoring-field select {
  width: 100%;
  min-height: 2.4rem;
  border-radius: 0.8rem;
  border: 1px solid var(--ui-border-default);
  background: var(--ui-surface-1);
  color: var(--ui-text-primary);
  padding: 0.58rem 0.7rem;
  font-size: 0.86rem;
  outline: none;
}

.monitoring-field input:focus,
.monitoring-field select:focus {
  border-color: var(--ui-accent);
  box-shadow: 0 0 0 3px var(--ui-accent-soft);
}

.monitoring-pricing-result {
  justify-items: end;
  text-align: right;
}

.monitoring-pricing-result em {
  font-style: normal;
}

.monitoring-pricing-result--error strong,
.monitoring-pricing-result--error em {
  color: var(--ui-danger);
}

.monitoring-empty {
  margin-top: 1rem;
  border: 1px dashed var(--ui-border-default);
  border-radius: 1rem;
  padding: 1rem;
  color: var(--ui-text-secondary);
  font-size: 0.9rem;
}

.monitoring-table {
  display: grid;
  gap: 0.55rem;
  margin-top: 1rem;
}

.monitoring-trace-row {
  display: grid;
  grid-template-columns: 120px minmax(150px, 1fr) 86px minmax(140px, 1fr) 88px 130px;
  align-items: center;
  gap: 0.75rem;
  border-radius: 1rem;
  border: 1px solid var(--ui-border-subtle);
  background: var(--ui-surface-raised);
  padding: 0.85rem;
  text-align: left;
  transition: border-color 180ms ease, background-color 180ms ease, transform 180ms ease;
}

.monitoring-trace-row:hover,
.monitoring-trace-row--active {
  transform: translateY(-1px);
  border-color: var(--ui-border-strong);
  background: var(--ui-accent-soft);
}

.monitoring-trace-row span,
.monitoring-trace-row code {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ui-text-secondary);
  font-size: 0.82rem;
}

.monitoring-trace-row strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ui-text-primary);
}

.monitoring-trace-row i {
  display: inline-flex;
  max-width: 100%;
  border-radius: 9999px;
  background: var(--ui-accent-soft);
  padding: 0.18rem 0.5rem;
  color: var(--ui-accent-strong);
  font-style: normal;
  font-weight: 800;
}

.monitoring-status {
  width: fit-content;
  border-radius: 9999px;
  padding: 0.25rem 0.55rem;
  font-weight: 850;
}

.monitoring-status--success {
  color: var(--ui-success);
  background: var(--ui-success-soft);
}

.monitoring-status--warning {
  color: var(--ui-warning);
  background: var(--ui-warning-soft);
}

.monitoring-detail {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: flex;
  justify-content: flex-end;
  background: rgba(15, 23, 42, 0.24);
  padding: 1rem;
}

.monitoring-detail__panel {
  width: min(720px, 100%);
  overflow-y: auto;
  border-radius: var(--ui-radius-lg);
  padding: 1.15rem;
}

.monitoring-icon-button {
  width: 2.4rem;
  height: 2.4rem;
  border-radius: 9999px;
}

.monitoring-detail__summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
  margin-top: 1rem;
}

.monitoring-detail__summary > div {
  border-radius: 1rem;
  padding: 0.85rem;
}

.monitoring-detail__summary span {
  color: var(--ui-text-muted);
  font-size: 0.72rem;
  font-weight: 800;
}

.monitoring-detail__summary strong {
  display: block;
  margin-top: 0.3rem;
  color: var(--ui-text-primary);
  font-weight: 900;
}

.monitoring-observation {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.75rem;
  border-radius: 1rem;
  padding: 0.85rem;
}

.monitoring-observation > div {
  display: grid;
  gap: 0.25rem;
  min-width: 0;
}

.monitoring-observation code {
  color: var(--ui-accent-strong);
  font-size: 0.8rem;
  font-weight: 800;
}

.monitoring-pill {
  width: fit-content;
  border-radius: 9999px;
  padding: 0.28rem 0.55rem;
  font-size: 0.72rem;
  font-weight: 900;
}

.monitoring-pill--model {
  background: var(--ui-info-soft);
  color: var(--ui-info);
}

.monitoring-pill--tool {
  background: var(--ui-success-soft);
  color: var(--ui-success);
}

.monitoring-pill--agent {
  background: var(--ui-accent-soft);
  color: var(--ui-accent-strong);
}

.monitoring-pill--muted {
  background: var(--ui-surface-3);
  color: var(--ui-text-secondary);
}

@media (max-width: 1080px) {
  .monitoring-grid--metrics,
  .monitoring-grid--main,
  .monitoring-status-panel {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .monitoring-trace-row {
    grid-template-columns: 110px minmax(130px, 1fr) 80px 90px;
  }

  .monitoring-pricing-row {
    grid-template-columns: 1fr;
  }

  .monitoring-pricing-result {
    justify-items: start;
    text-align: left;
  }

  .monitoring-trace-row span:nth-of-type(3),
  .monitoring-trace-row code {
    display: none;
  }
}

@media (max-width: 720px) {
  .monitoring-hero,
  .monitoring-hero__actions,
  .monitoring-section__head,
  .monitoring-detail__head {
    flex-direction: column;
    align-items: stretch;
  }

  .monitoring-grid--metrics,
  .monitoring-grid--main,
  .monitoring-status-panel,
  .monitoring-mini-grid,
  .monitoring-detail__summary {
    grid-template-columns: 1fr;
  }

  .monitoring-trace-row {
    grid-template-columns: 1fr;
  }

  .monitoring-trace-row span:nth-of-type(3),
  .monitoring-trace-row code {
    display: block;
  }

  .monitoring-observation {
    grid-template-columns: 1fr;
  }

  .monitoring-pricing-controls {
    grid-template-columns: 1fr;
  }
}
</style>
