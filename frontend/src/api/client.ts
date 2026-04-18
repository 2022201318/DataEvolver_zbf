/**
 * 真实后端请求（与 docs/FRONTEND_API.md 对齐）
 */
import type {
  ApiOperatorEntry,
  OperatorItem,
  OperatorsListResponse,
  StartSessionResponse,
  UnderstandingResult,
} from '../types'

export function getApiBaseUrl(): string {
  const v = import.meta.env.VITE_API_BASE_URL
  if (typeof v === 'string' && v.trim()) return v.replace(/\/$/, '')
  return 'http://127.0.0.1:8000'
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: string
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/**
 * 上传用户文件并写入服务端 `data/manifest.jsonl` 对应记录。
 * multipart 字段名需与后端 `POST /api/sessions/start` 一致。
 */
export async function startSessionUpload(formData: FormData): Promise<StartSessionResponse> {
  const url = `${getApiBaseUrl()}/api/sessions/start`
  const res = await fetch(url, {
    method: 'POST',
    body: formData,
  })
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as StartSessionResponse
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export interface SaveLlmPayload {
  provider_mode: 'openai-official' | 'third-party'
  model: string
  temperature: number
  max_tokens: number
  api_key: string
  base_url: string
}

export interface SaveLlmResponse {
  ok: boolean
  paths?: { config_json: string; api_keys_json: string; api_config_json: string }
}

/** 与 `GET /api/config/llm` 响应一致，供设置面板拉取服务端已保存项（不含明文密钥） */
export interface LlmSettingsFromServer {
  provider_mode: 'openai-official' | 'third-party'
  model: string
  temperature: number
  max_tokens: number
  base_url: string
  api_key_configured: boolean
  api_key_masked: string
  timeout: number
}

/** 从服务端读取当前 LLM 配置（与仓库 `config/` 一致），用于前端与后端对齐 */
export async function fetchLlmConfigFromServer(): Promise<LlmSettingsFromServer> {
  const url = `${getApiBaseUrl()}/api/config/llm`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as LlmSettingsFromServer
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

/** 将模型设置写入 `config/config.json`（llm）、`config/api_keys.json`、`config/api_config.json` */
export async function saveLlmConfigToServer(payload: SaveLlmPayload): Promise<SaveLlmResponse> {
  const url = `${getApiBaseUrl()}/api/config/save-llm`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as SaveLlmResponse
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export async function fetchPipelineSession(pipelineId: string): Promise<{ ok: boolean; pipeline_id: string; record: Record<string, unknown> }> {
  const url = `${getApiBaseUrl()}/api/pipeline/${encodeURIComponent(pipelineId)}/session`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as { ok: boolean; pipeline_id: string; record: Record<string, unknown> }
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export interface PipelinePreviewResponse {
  ok: boolean
  pipeline_id: string
  kind: string
  file_index: number
  relative_path: string
  lines: string[]
  truncated_lines?: boolean
  truncated_chars?: boolean
  error?: string | null
}

/** Raw / Seed / 描述文件前几行预览 */
export async function fetchPipelinePreview(
  pipelineId: string,
  kind: 'raw' | 'seed' | 'description',
  opts?: { index?: number; max_lines?: number }
): Promise<PipelinePreviewResponse> {
  const q = new URLSearchParams()
  if (opts?.index != null) q.set('index', String(opts.index))
  if (opts?.max_lines != null) q.set('max_lines', String(opts.max_lines))
  const qs = q.toString()
  const url = `${getApiBaseUrl()}/api/pipeline/${encodeURIComponent(pipelineId)}/preview/${kind}${qs ? `?${qs}` : ''}`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as PipelinePreviewResponse
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export interface UnderstandResponse {
  ok: boolean
  pipeline_id: string
  result: UnderstandingResult
}

export async function runPipelineUnderstand(
  pipelineId: string,
  body?: { mode?: 'auto' | 'stub' | 'llm' }
): Promise<UnderstandResponse> {
  const url = `${getApiBaseUrl()}/api/pipeline/${encodeURIComponent(pipelineId)}/understand`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: body?.mode ?? 'auto' }),
  })
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as UnderstandResponse
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export async function fetchUnderstandingResult(pipelineId: string): Promise<{ ok: boolean; data: UnderstandingResult }> {
  const url = `${getApiBaseUrl()}/api/pipeline/${encodeURIComponent(pipelineId)}/understanding/result`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as { ok: boolean; data: UnderstandingResult }
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

/** 合并后的算子池（系统 + 用户/进化），见 `docs/FRONTEND_API.md` */
export async function fetchOperators(): Promise<OperatorsListResponse> {
  const url = `${getApiBaseUrl()}/api/operators/`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as OperatorsListResponse
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

/** 将 API 条目转为画布 `OperatorItem`（`user` → UI `evolved` 以区分用户注册表算子） */
export function mapApiOperatorsToPoolItems(entries: ApiOperatorEntry[], lang: 'zh' | 'en'): OperatorItem[] {
  return entries.map((e) => ({
    id: e.name,
    name: e.name,
    description: e.description,
    source: e.source === 'user' ? 'evolved' : 'base',
    category: lang === 'zh' && e.category_label_zh ? e.category_label_zh : e.category_label,
    category_id: e.category_id,
    input_keys: e.input_keys ? [...e.input_keys] : [],
    output_keys: e.output_keys ? [...e.output_keys] : [],
    requires_llm: e.requires_llm,
    card_variant: e.card_variant,
  }))
}

// --- Workflow：分步推进（与 `docs/FRONTEND_API.md` 一致）---

export interface WorkflowStateDto {
  pipeline_id: string
  step_index: number
  steps_completed: string[]
  last_message: string
  updated_at: string
  dag_evolution_cycles?: number
  understanding_revision?: number
  orchestration_revision?: number
  round?: number
  quality_passed?: boolean
  ready_for_full_run?: boolean
  next_action?: string
  step_order: string[]
  is_complete: boolean
}

export interface WorkflowArtifactsFlags {
  understanding: boolean
  orchestration: boolean
  instantiation: boolean
  trial_run: boolean
  pipeline_run: boolean
  quality_check: boolean
  experience: boolean
}

export interface WorkflowStateResponse {
  ok: boolean
  pipeline_id: string
  state: WorkflowStateDto
  artifacts: WorkflowArtifactsFlags
}

export interface WorkflowArtifactHistoryEntry {
  [key: string]: unknown
}

export interface WorkflowRoundSnapshot {
  kind?: string
  round?: number
  quality_passed?: boolean
  archived_at?: string
  paths?: Record<string, string>
  summary?: {
    understanding_done?: boolean
    dag_node_count?: number
    instantiation_steps?: number
    sample_score?: number | null
    experience_text?: string
  }
  [key: string]: unknown
}

export interface WorkflowArtifactHistoryResponse {
  ok: boolean
  pipeline_id: string
  index_path: string
  entries: WorkflowArtifactHistoryEntry[]
  round_snapshots?: WorkflowRoundSnapshot[]
}

export interface WorkflowRerunResponse {
  ok: boolean
  pipeline_id: string
  rerun_from: string
  step_index: number
  artifacts_touched: string[]
  next_command?: string
}

export interface WorkflowTokensResponse {
  total_input_tokens?: number
  total_output_tokens?: number
  total_tokens?: number
  by_workflow_step?: Record<string, { input_tokens?: number; output_tokens?: number; total_tokens?: number }>
  by_operation?: Record<string, { input_tokens?: number; output_tokens?: number; total_tokens?: number }>
  for_frontend?: { token_series?: Array<Record<string, unknown>> }
  events?: Array<Record<string, unknown>>
  [key: string]: unknown
}

/** FastAPI HTTPException(detail=dict) 形如 `{ "detail": { ... } }` */
export interface WorkflowAdvanceFailureBody {
  ok: false
  error: string
  step: string
  message: string
  pipeline_id: string
  state: WorkflowStateDto
}

/**
 * 解析 workflow advance 422 或其它 FastAPI JSON 错误体，供 Toast 展示。
 * `bodyText` 一般为 `ApiError.detail`（整段响应文本）。
 */
export function parseFastApiErrorBody(bodyText: string | undefined): {
  userMessage: string
  step?: string
  workflowFailure: WorkflowAdvanceFailureBody | null
} {
  if (!bodyText?.trim()) {
    return { userMessage: 'Request failed', workflowFailure: null }
  }
  try {
    const j = JSON.parse(bodyText) as { detail?: unknown }
    const d = j.detail
    if (d && typeof d === 'object' && d !== null && 'message' in d) {
      const o = d as Record<string, unknown>
      const step = typeof o.step === 'string' ? o.step : undefined
      const message = typeof o.message === 'string' ? o.message : String(o.message ?? '')
      if (o.error === 'workflow_step_failed' && step) {
        return {
          userMessage: `[${step}] ${message}`,
          step,
          workflowFailure: d as unknown as WorkflowAdvanceFailureBody,
        }
      }
      if (step) {
        return { userMessage: `[${step}] ${message}`, step, workflowFailure: null }
      }
      return { userMessage: message || bodyText.slice(0, 280), workflowFailure: null }
    }
    if (typeof j.detail === 'string') {
      return { userMessage: j.detail, workflowFailure: null }
    }
  } catch {
    /* 非 JSON */
  }
  return { userMessage: bodyText.slice(0, 320), workflowFailure: null }
}

export async function fetchWorkflowState(pipelineId: string): Promise<WorkflowStateResponse> {
  const url = `${getApiBaseUrl()}/api/workflow/${encodeURIComponent(pipelineId)}/state`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as WorkflowStateResponse
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export async function fetchArtifactHistory(
  pipelineId: string,
  limit = 80
): Promise<WorkflowArtifactHistoryResponse> {
  const q = new URLSearchParams()
  q.set('limit', String(limit))
  const url = `${getApiBaseUrl()}/api/workflow/${encodeURIComponent(pipelineId)}/artifact-history?${q.toString()}`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as WorkflowArtifactHistoryResponse
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export async function rerunWorkflowFromStep(
  pipelineId: string,
  step: string
): Promise<WorkflowRerunResponse> {
  const url = `${getApiBaseUrl()}/api/workflow/${encodeURIComponent(pipelineId)}/rerun`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ step }),
  })
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as WorkflowRerunResponse
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export async function fetchWorkflowTokens(
  pipelineId: string,
  opts?: { include_events?: boolean; max_events?: number }
): Promise<WorkflowTokensResponse> {
  const q = new URLSearchParams()
  if (opts?.include_events) q.set('include_events', 'true')
  if (opts?.max_events != null) q.set('max_events', String(opts.max_events))
  const qs = q.toString()
  const url = `${getApiBaseUrl()}/api/workflow/${encodeURIComponent(pipelineId)}/tokens${qs ? `?${qs}` : ''}`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as WorkflowTokensResponse
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export interface AdvanceWorkflowBody {
  force_reset_state?: boolean
  pipeline_run_execution_mode?: 'in_process' | 'subprocess'
  pipeline_run_subprocess_fallback_in_process?: boolean
  pipeline_run_subprocess_timeout_sec?: number
}

export interface AdvanceWorkflowResponse {
  ok: boolean
  pipeline_id: string
  done: boolean
  step?: string
  detail?: Record<string, unknown>
  state: WorkflowStateDto
  message?: string
}

/**
 * 推进一步。若当前步失败，服务端返回 **422**，`detail` 常为对象（含 `step`、`message`、`state`），
 * 且 **不会**推进 `step_index`；前端应解析 `ApiError` 的响应体或 `detail` 字段做阶段提示与重试。
 */
export async function advanceWorkflow(
  pipelineId: string,
  body: AdvanceWorkflowBody = {}
): Promise<AdvanceWorkflowResponse> {
  const url = `${getApiBaseUrl()}/api/workflow/${encodeURIComponent(pipelineId)}/advance`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      force_reset_state: body.force_reset_state ?? false,
      pipeline_run_execution_mode: body.pipeline_run_execution_mode ?? 'in_process',
      pipeline_run_subprocess_fallback_in_process: body.pipeline_run_subprocess_fallback_in_process ?? true,
      pipeline_run_subprocess_timeout_sec: body.pipeline_run_subprocess_timeout_sec ?? 600,
    }),
  })
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as AdvanceWorkflowResponse
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export async function resetWorkflowState(
  pipelineId: string
): Promise<{ ok: boolean; pipeline_id: string; state_removed: boolean }> {
  const url = `${getApiBaseUrl()}/api/workflow/${encodeURIComponent(pipelineId)}/reset`
  const res = await fetch(url, { method: 'POST' })
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as { ok: boolean; pipeline_id: string; state_removed: boolean }
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export async function resetWorkflowForDebug(
  pipelineId: string
): Promise<{ ok: boolean; pipeline_id: string; state: WorkflowStateDto; artifacts_cleared: string[] }> {
  const url = `${getApiBaseUrl()}/api/workflow/${encodeURIComponent(pipelineId)}/reset-for-debug`
  const res = await fetch(url, { method: 'POST' })
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as { ok: boolean; pipeline_id: string; state: WorkflowStateDto; artifacts_cleared: string[] }
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

// --- Pipeline：编排 / 实例化 / 执行 / 试运行 / 质检 / 经验 ---

export interface RunPipelinePayload {
  max_input_records?: number | null
  llm_max_records_per_step?: number
  execution_mode?: 'in_process' | 'subprocess'
  subprocess_fallback_in_process?: boolean
  subprocess_timeout_sec?: number
}

export interface PipelineRunReport {
  pipeline_id?: string
  status?: string
  meta?: Record<string, unknown>
  steps?: unknown[]
  output_jsonl?: string
  output_record_count?: number
  failed_step?: unknown
  error?: string | null
  warnings?: unknown[]
  [key: string]: unknown
}

export async function runPipeline(
  pipelineId: string,
  payload: RunPipelinePayload = {}
): Promise<{ ok: boolean; pipeline_id: string; report: PipelineRunReport }> {
  const url = `${getApiBaseUrl()}/api/pipeline/${encodeURIComponent(pipelineId)}/run`
  return postPipelineRun(url, payload)
}

/** 与页面历史路径 `.../run-full` 一致，行为同 `runPipeline`。 */
export async function runPipelineFull(
  pipelineId: string,
  payload: RunPipelinePayload = {}
): Promise<{ ok: boolean; pipeline_id: string; report: PipelineRunReport }> {
  const url = `${getApiBaseUrl()}/api/pipeline/${encodeURIComponent(pipelineId)}/run-full`
  return postPipelineRun(url, payload)
}

async function postPipelineRun(
  url: string,
  payload: RunPipelinePayload
): Promise<{ ok: boolean; pipeline_id: string; report: PipelineRunReport }> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      max_input_records: payload.max_input_records ?? null,
      llm_max_records_per_step: payload.llm_max_records_per_step ?? 32,
      execution_mode: payload.execution_mode ?? 'in_process',
      subprocess_fallback_in_process: payload.subprocess_fallback_in_process ?? true,
      subprocess_timeout_sec: payload.subprocess_timeout_sec ?? 600,
    }),
  })
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as { ok: boolean; pipeline_id: string; report: PipelineRunReport }
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export async function fetchOrchestrationFull(
  pipelineId: string
): Promise<{ ok: boolean; pipeline_id: string; relative_path: string; data: Record<string, unknown> }> {
  const url = `${getApiBaseUrl()}/api/pipeline/${encodeURIComponent(pipelineId)}/orchestration`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as { ok: boolean; pipeline_id: string; relative_path: string; data: Record<string, unknown> }
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export async function fetchOrchestrationDag(pipelineId: string): Promise<Record<string, unknown>> {
  const url = `${getApiBaseUrl()}/api/pipeline/${encodeURIComponent(pipelineId)}/orchestration/dag`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as Record<string, unknown>
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export async function fetchInstantiationBundle(
  pipelineId: string
): Promise<{ ok: boolean; pipeline_id: string; relative_path: string; data: Record<string, unknown> }> {
  const url = `${getApiBaseUrl()}/api/pipeline/${encodeURIComponent(pipelineId)}/instantiation`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as { ok: boolean; pipeline_id: string; relative_path: string; data: Record<string, unknown> }
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export async function fetchInstantiationSteps(
  pipelineId: string,
  opts?: { include_code?: boolean }
): Promise<{
  ok: boolean
  pipeline_id: string
  relative_path: string
  meta?: unknown
  total_steps: number
  steps: Record<string, unknown>[]
}> {
  const q = new URLSearchParams()
  if (opts?.include_code) q.set('include_code', 'true')
  const qs = q.toString()
  const url = `${getApiBaseUrl()}/api/pipeline/${encodeURIComponent(pipelineId)}/instantiation/steps${qs ? `?${qs}` : ''}`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as {
      ok: boolean
      pipeline_id: string
      relative_path: string
      meta?: unknown
      total_steps: number
      steps: Record<string, unknown>[]
    }
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export async function fetchPipelineRunLatest(pipelineId: string): Promise<{
  ok: boolean
  pipeline_id: string
  latest: Record<string, unknown> | null
  report: PipelineRunReport | null
}> {
  const url = `${getApiBaseUrl()}/api/pipeline/${encodeURIComponent(pipelineId)}/run/latest`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as {
      ok: boolean
      pipeline_id: string
      latest: Record<string, unknown> | null
      report: PipelineRunReport | null
    }
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export async function fetchTrialResult(
  pipelineId: string
): Promise<{ ok: boolean; pipeline_id: string; relative_path: string; data: Record<string, unknown> }> {
  const url = `${getApiBaseUrl()}/api/pipeline/${encodeURIComponent(pipelineId)}/trial`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as { ok: boolean; pipeline_id: string; relative_path: string; data: Record<string, unknown> }
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export async function fetchQualityCheck(
  pipelineId: string
): Promise<{ ok: boolean; pipeline_id: string; relative_path: string; data: Record<string, unknown> }> {
  const url = `${getApiBaseUrl()}/api/pipeline/${encodeURIComponent(pipelineId)}/quality-check`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as { ok: boolean; pipeline_id: string; relative_path: string; data: Record<string, unknown> }
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}

export async function fetchExperience(
  pipelineId: string
): Promise<{ ok: boolean; pipeline_id: string; relative_path: string; data: Record<string, unknown> }> {
  const url = `${getApiBaseUrl()}/api/pipeline/${encodeURIComponent(pipelineId)}/experience`
  const res = await fetch(url)
  const text = await res.text()
  if (!res.ok) {
    throw new ApiError(res.status, `Request failed: ${res.status}`, text)
  }
  try {
    return JSON.parse(text) as { ok: boolean; pipeline_id: string; relative_path: string; data: Record<string, unknown> }
  } catch {
    throw new ApiError(res.status, 'Invalid JSON response', text)
  }
}
