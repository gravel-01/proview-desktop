# ProView Langfuse Monitoring Module

## Purpose

`backend/monitoring` is the planned home for ProView's custom Agent monitoring system.
Langfuse remains the observability data source for traces, observations, generations,
tool calls, token usage, cost, latency, sessions, and errors. This module turns that
generic observability data into a smaller ProView-specific dashboard API.

The goal is not to duplicate the full Langfuse UI. The goal is to expose the signals
developers need most when debugging ProView Agent behavior:

- Is the Agent running successfully?
- Are LLM calls succeeding?
- Are tools actually being called?
- Which tools or models are slow?
- Where are token and cost spikes coming from?
- Which recent trace should a developer inspect next?

## Non-Goals

- Do not put dashboard query logic in `core/langchain_agent.py`.
- Do not expose `LANGFUSE_SECRET_KEY` to the frontend.
- Do not return full prompts, resumes, or completions by default.
- Do not let monitoring failures affect interview or resume workflows.

## Module Layout

```text
backend/monitoring/
  __init__.py
  config.py
  langfuse_client.py
  langfuse_metrics.py
  schemas.py
  redaction.py
  routes.py
  README.md
```

### `config.py`

Reads monitoring configuration from environment variables:

```env
LANGFUSE_SECRET_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_BASE_URL=
PROVIEW_MONITORING_ENABLED=1
PROVIEW_MONITORING_DEFAULT_HOURS=24
PROVIEW_MONITORING_TIMEOUT_SECONDS=10
PROVIEW_MONITORING_PREVIEW_CHARS=200
PROVIEW_MONITORING_ALLOW_FULL_TRACE=0
```

### `langfuse_client.py`

Owns the Langfuse API boundary. It should handle authentication, base URL,
timeouts, API errors, and graceful degradation.

### `langfuse_metrics.py`

Owns aggregation from Langfuse raw data into ProView dashboard metrics.

### `schemas.py`

Defines stable response envelopes and dashboard data shapes so the frontend is
not coupled to Langfuse raw fields.

### `redaction.py`

Centralizes preview and redaction behavior for prompts, completions, resumes,
phone numbers, emails, tokens, API keys, and authorization headers.

### `routes.py`

Will expose Flask APIs under:

```text
/api/monitoring/...
```

The blueprint is wired into `app.py` in Phase 2 for the minimal backend API.

## API Design

Planned routes:

```text
GET /api/monitoring/status
GET /api/monitoring/overview
GET /api/monitoring/costs
GET /api/monitoring/latency
GET /api/monitoring/tools
GET /api/monitoring/models
GET /api/monitoring/traces/recent
GET /api/monitoring/traces/<trace_id>
```

Common query parameters:

```text
from=2026-05-01T00:00:00Z
to=2026-05-02T00:00:00Z
hours=24
limit=50
```

If no time range is passed, the default should be the most recent
`PROVIEW_MONITORING_DEFAULT_HOURS` hours.

## Response Envelope

Successful response:

```json
{
  "configured": true,
  "available": true,
  "source": "langfuse",
  "range": {
    "start": "2026-05-01T00:00:00Z",
    "end": "2026-05-02T00:00:00Z"
  },
  "data": {},
  "message": ""
}
```

Unconfigured or unavailable response:

```json
{
  "configured": false,
  "available": false,
  "source": "langfuse",
  "range": null,
  "data": null,
  "message": "LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY, or LANGFUSE_BASE_URL is missing"
}
```

## V1 Dashboard Metrics

### Agent Overview

```text
trace_count
observation_count
llm_call_count
tool_call_count
error_count
success_rate
```

### Token And Cost

```text
total_input_tokens
total_output_tokens
total_tokens
total_cost
avg_cost_per_trace
cost_by_model
tokens_by_model
```

### Latency

```text
avg_trace_latency_ms
p95_trace_latency_ms
avg_llm_latency_ms
p95_llm_latency_ms
avg_tool_latency_ms
p95_tool_latency_ms
slowest_traces
slowest_tools
```

### Tools

```text
tool_call_count_by_name
tool_error_count_by_name
tool_avg_latency_by_name
top_tools
recent_tool_calls
```

### Models

```text
llm_call_count_by_model
llm_error_count_by_model
avg_tokens_by_model
avg_latency_by_model
cost_by_model
```

### Recent Traces

```text
trace_id
timestamp
session_id
name
status
duration_ms
model
input_preview
output_preview
token_count
cost
error_preview
```

## Redaction Policy

Dashboard APIs should return previews by default:

```text
input_preview: 200 chars
output_preview: 200 chars
error_preview: 300 chars
```

Default sensitive fields:

```text
authorization
api_key
secret
token
password
resume
email
phone
mobile
身份证
手机号
邮箱
简历
```

Full trace content should require an explicit development-mode flag or future
permission control.

## Development Plan

### Phase 1: Skeleton And Design

Current phase.

- Add module boundary.
- Add configuration helpers.
- Add redaction helpers.
- Add response envelope helpers.
- Add Langfuse client and metric aggregation placeholders.
- Do not wire into `app.py`.

### Phase 2: Minimal Backend API

Implement:

```text
GET /api/monitoring/status
GET /api/monitoring/traces/recent
GET /api/monitoring/traces/<trace_id>
```

Goals:

- Verify Langfuse API connectivity.
- Fetch recent traces.
- Fetch a redacted trace detail.

Current status: implemented.

### Phase 3: Aggregated Metrics

Implement:

```text
GET /api/monitoring/overview
GET /api/monitoring/tools
GET /api/monitoring/costs
GET /api/monitoring/latency
GET /api/monitoring/models
```

Goals:

- Support dashboard summary cards.
- Support tool and model rankings.
- Surface token, cost, latency, and error spikes.

Current status: implemented.

### Phase 4: Frontend Dashboard

Add:

```text
frontend/src/services/monitoring.ts
frontend/src/types/monitoring.ts
frontend/src/views/MonitoringView.vue
```

Suggested layout:

- Top bar: time range, refresh, Langfuse status.
- Overview cards: traces, LLM calls, tool calls, errors, success rate.
- Cost and token section.
- Latency section.
- Tool and model ranking section.
- Recent traces table.
- Trace detail drawer or page.
