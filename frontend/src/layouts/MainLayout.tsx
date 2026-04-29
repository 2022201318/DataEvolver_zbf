import { ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { LiveArtifactsForCanvas } from '../lib/buildEvolutionRowsFromPipeline'
import { buildEvolutionRowsFromPipeline } from '../lib/buildEvolutionRowsFromPipeline'
import type { ReactNode } from 'react'
import { Database, Eye, Languages, PanelLeftClose, PanelLeftOpen, Play, Save, Settings, Trash2, Upload, UploadCloud, Wand2, X } from 'lucide-react'
import { useAppStore } from '../stores/appStore'
import { EvolutionCanvas } from '../components/EvolutionCanvas'
import {
  advanceWorkflow,
  ApiError,
  fetchArtifactHistory,
  fetchExperience,
  fetchInstantiationSteps,
  fetchLlmConfigFromServer,
  fetchOperators,
  fetchOrchestrationDag,
  fetchPipelineRunLatest,
  fetchPipelinePreview,
  fetchQualityCheck,
  fetchTrialResult,
  fetchUnderstandingResult,
  fetchWorkflowTokens,
  fetchWorkflowState,
  mapApiOperatorsToPoolItems,
  parseFastApiErrorBody,
  resetWorkflowForDebug,
  resetWorkflowState,
  rerunWorkflowFromStep,
  runPipelineFull,
  saveLlmConfigToServer,
  startSessionUpload,
} from '../api'
import type { WorkflowStateDto, WorkflowStateResponse } from '../api'
import type { DagResult, OperatorItem } from '../types'

type Language = 'zh' | 'en'

type Metric = { sec: number; tokens: number }
type DagStatus = 'passed' | 'failed'

interface DagTab {
  id: number
  title: string
  status: DagStatus
  summary: string
  metrics: Metric
  nodes: string[]
  /** 该轮编排 DAG 快照（与画布分页一致） */
  dag?: DagResult
}

interface InstantiationCard {
  id: string
  name: string
  summary: string
  code: string
  metrics: Metric
}

interface EvolutionRow {
  id: number
  understandingDone: boolean
  understandingMetrics?: Metric
  dagTabs: DagTab[]
  activeDagTabId?: number
  instantiationCards: InstantiationCard[]
  sampleScore?: number
  sampleMetrics?: Metric
  experience?: string
  experienceMetrics?: Metric
  needNext: boolean
  completed: boolean
}

type StepTimingMap = Record<string, number>

function timingKey(round: number, step: string): string {
  return `${Math.max(1, round)}:${step}`
}

function stepDuration(timing: StepTimingMap, round: number, step: string): number | undefined {
  const v = timing[timingKey(round, step)]
  return typeof v === 'number' && Number.isFinite(v) ? v : undefined
}

function applyMeasuredDurations(rows: EvolutionRow[], timing: StepTimingMap): EvolutionRow[] {
  return rows.map((row) => {
    const round = Math.max(1, row.id)
    const understandingSec = stepDuration(timing, round, 'understanding')
    const orchSec = stepDuration(timing, round, 'orchestration')
    const evoSec = stepDuration(timing, round, 'operator_evolution')
    const instSec = stepDuration(timing, round, 'instantiation')
    const trialSec = stepDuration(timing, round, 'trial_run')
    const qualitySec = stepDuration(timing, round, 'quality_check')
    const expSec = stepDuration(timing, round, 'experience')
    const sampleSec =
      typeof trialSec === 'number' || typeof qualitySec === 'number'
        ? (trialSec ?? 0) + (qualitySec ?? 0)
        : undefined

    const dagTabs = row.dagTabs.map((tab) => {
      const title = (tab.title || '').toLowerCase()
      let sec = tab.metrics.sec
      if (typeof orchSec === 'number' && (title.includes('编排') || title.includes('orchestration') || title.includes('校验') || title.includes('validation'))) {
        sec = orchSec
      }
      if (typeof evoSec === 'number' && (title.includes('进化') || title.includes('evolution'))) {
        sec = evoSec
      }
      return sec !== tab.metrics.sec ? { ...tab, metrics: { ...tab.metrics, sec } } : tab
    })

    const instantiationCards =
      typeof instSec === 'number' && row.instantiationCards.length > 0
        ? row.instantiationCards.map((card) => ({ ...card, metrics: { ...card.metrics, sec: instSec / row.instantiationCards.length } }))
        : row.instantiationCards

    return {
      ...row,
      understandingMetrics:
        row.understandingMetrics && typeof understandingSec === 'number'
          ? { ...row.understandingMetrics, sec: understandingSec }
          : row.understandingMetrics,
      dagTabs,
      instantiationCards,
      sampleMetrics:
        typeof sampleSec === 'number'
          ? { ...(row.sampleMetrics ?? { sec: 0, tokens: 0 }), sec: sampleSec }
          : row.sampleMetrics,
      experienceMetrics:
        row.experienceMetrics && typeof expSec === 'number'
          ? { ...row.experienceMetrics, sec: expSec }
          : row.experienceMetrics,
    }
  })
}

function makeEntryOnlyRow(round = 1): EvolutionRow {
  return {
    id: Math.max(1, round),
    understandingDone: false,
    dagTabs: [],
    instantiationCards: [],
    needNext: false,
    completed: false,
  }
}

type SettingsTab = 'general' | 'model'
type UploadFileKey = 'raw' | 'seed' | 'description'
type ProviderMode = 'openai-official' | 'third-party'

interface UploadPreviewState {
  raw: string[]
  seed: string[]
  description: string[]
}

/** 上传后数据预览区：每个文件展示文件开头的行数（整行不截断） */
const PREVIEW_LINE_COUNT = 12
const PREVIEW_JSON_KEY_COLORS = [
  'var(--preview-json-key-0)',
  'var(--preview-json-key-1)',
  'var(--preview-json-key-2)',
  'var(--preview-json-key-3)',
] as const

/** 对 JSON/JSONL 行里的 `"key":` 片段做轮换配色，便于扫读 */
function renderLineWithJsonKeyHighlight(line: string, lineKey: string): ReactNode {
  const re = /"([^"\\]|\\.)*"\s*:/g
  const parts: ReactNode[] = []
  let last = 0
  let m: RegExpExecArray | null
  let k = 0
  while ((m = re.exec(line)) !== null) {
    if (m.index > last) parts.push(line.slice(last, m.index))
    parts.push(
      <span key={`${lineKey}-k${k}`} style={{ color: PREVIEW_JSON_KEY_COLORS[k % PREVIEW_JSON_KEY_COLORS.length] }}>
        {m[0]}
      </span>
    )
    k++
    last = m.index + m[0].length
  }
  if (last < line.length) parts.push(line.slice(last))
  return parts.length ? <>{parts}</> : line
}

/** 预览展示前做轻量格式化：优先按完整 JSON，其次按 JSONL 逐行格式化 */
function formatPreviewLinesForDisplay(lines: string[]): string[] {
  const normalized = lines.map((line) => line.replace(/\r$/, ''))
  const joined = normalized.join('\n').trim()
  if (!joined) return []

  try {
    const parsed = JSON.parse(joined)
    return JSON.stringify(parsed, null, 2).split('\n').slice(0, 400)
  } catch {
    /* 非完整 JSON，继续尝试 JSONL/逐行 */
  }

  const out: string[] = []
  for (const line of normalized) {
    const trimmed = line.trim()
    if (!trimmed) {
      out.push('')
      continue
    }
    try {
      const parsed = JSON.parse(trimmed)
      out.push(...JSON.stringify(parsed, null, 2).split('\n'))
    } catch {
      out.push(line)
    }
    if (out.length >= 400) break
  }
  return out.slice(0, 400)
}

/** 侧栏与设置弹窗共用的模型下拉选项 */
const MODEL_OPTIONS = [
  'gpt-4.1-nano',
  'gpt-4.1-mini',
  'gpt-4.1',
  'gpt-4o-mini',
  'gpt-4o',
  'gpt-4o-2024-08-06',
  'gpt-4-turbo',
  'gpt-4-turbo-preview',
  'gpt-3.5-turbo',
  'o1',
  'o1-mini',
  'o3-mini',
  'o4-mini',
] as const

const TEXT: Record<
  Language,
  {
    productSub: string
    uploadArea: string
    rawData: string
    seedData: string
    promptData: string
    uploadRaw: string
    uploadSeed: string
    uploadPrompt: string
    previewArea: string
    noPreviewYet: string
    uploadHint: string
    clickToUpload: string
    reupload: string
    previewButton: string
    previewModalHint: string
    dragOrClick: string
    uploadFormats: string
    uploadedFile: string
    runMode: string
    manual: string
    auto: string
    start: string
    settings: string
    generalSettings: string
    saveSession: string
    loadSession: string
    clearWorkspace: string
    clearConfirm: string
    clearCancel: string
    clearConfirmAction: string
    clearDone: string
    saveDone: string
    loadDone: string
    loadFailed: string
    saveTooltip: string
    loadTooltip: string
    clearTooltip: string
    close: string
    savedSessionName: string
    theme: string
    light: string
    dark: string
    language: string
    chinese: string
    english: string
    modelSettings: string
    apiSettings: string
    backHome: string
    provider: string
    providerMode: string
    openaiOfficial: string
    thirdParty: string
    modelName: string
    modelOptions: string
    apiKey: string
    apiKeySaved: string
    apiKeyServerHint: string
    baseUrl: string
    temperature: string
    maxTokens: string
    operatorPool: string
    operatorHint: string
    pipelineCanvas: string
    progressHint: string
    stepForward: string
    autoBuildRound: string
    totalTime: string
    totalTokens: string
    roundTitle: string
    rawBlock: string
    understanding: string
    operatorEvolution: string
    dagTabs: string
    instantiation: string
    sampleEval: string
    experience: string
    pending: string
    done: string
    checkNeedEvolution: string
    checkPass: string
    llmScore: string
    willIterate: string
    qualityOk: string
    runFullData: string
    runQueuedToast: string
    fullDataToast: string
    sourceBase: string
    sourceEvolved: string
    running: string
    active: string
    autoTag: string
    startSessionTitle: string
    pipelineIdLabel: string
    pipelineIdPlaceholder: string
    metaDomain: string
    metaTaskType: string
    metaLanguage: string
    optionalHint: string
    manifestFormHint: string
    confirmStartRun: string
    pipelineIdRequired: string
    uploadAtLeastOneFile: string
    reuploadFilesHint: string
    startSessionSuccess: string
    startSessionFailed: string
    startSessionSaving: string
    saveLlmToProject: string
    saveLlmSuccess: string
    saveLlmFailed: string
    saveLlmSaving: string
  }
> = {
  zh: {
    productSub: 'Open-source Workflow UI',
    uploadArea: '用户上传区',
    rawData: 'Raw Data',
    seedData: 'Seed Data',
    promptData: '描述 / Prompt',
    uploadRaw: '上传原始数据文件',
    uploadSeed: '上传种子数据文件',
    uploadPrompt: '上传任务描述文件（可选）',
    previewArea: '数据预览',
    noPreviewYet: '尚未上传文件',
    uploadHint: '支持 JSON / JSONL / TXT，上传后可点击预览按钮查看数据内容',
    clickToUpload: '点击上传',
    reupload: '重新上传',
    previewButton: '数据预览',
    previewModalHint: '展示上传文件的前几行内容，便于快速确认数据结构。',
    dragOrClick: '拖拽或点击上传数据文件',
    uploadFormats: '.csv .json .jsonl .txt',
    uploadedFile: '已上传文件',
    runMode: '运行模式',
    manual: '手动',
    auto: '自动',
    start: '启动',
    settings: '设置',
    generalSettings: '常规设置',
    saveSession: '保存',
    loadSession: '上传',
    clearWorkspace: '清除',
    clearConfirm: '确认清除本轮上传文件与中间工作区内容？',
    clearCancel: '取消',
    clearConfirmAction: '确认清除',
    clearDone: '已清除本轮工作区内容。',
    saveDone: '已导出本轮会话文件。',
    loadDone: '会话文件已加载到当前工作区。',
    loadFailed: '会话文件格式不正确，加载失败。',
    saveTooltip: '保存本轮工作区（上传文件 + 演化中间状态）',
    loadTooltip: '加载之前保存的工作区会话文件',
    clearTooltip: '清除本轮上传文件与中间工作区',
    close: '关闭',
    savedSessionName: 'dataevolver.session.json',
    theme: '主题模式',
    light: '白天',
    dark: '黑夜',
    language: '语言',
    chinese: '中文',
    english: 'English',
    modelSettings: '模型设置',
    apiSettings: '模型与服务配置',
    backHome: '返回主页',
    provider: 'Provider',
    providerMode: '服务商',
    openaiOfficial: 'OpenAI 官网',
    thirdParty: '第三方服务商',
    modelName: '模型名称',
    modelOptions: '模型',
    apiKey: 'API Key',
    apiKeySaved: 'API Key 已保存在本地浏览器',
    apiKeyServerHint: '服务端已保存密钥（留空点保存将保留原密钥）',
    baseUrl: 'Base URL（第三方服务可选）',
    temperature: 'Temperature',
    maxTokens: 'Max Tokens',
    operatorPool: '算子池',
    operatorHint: '系统会在算子自进化阶段实时沉淀新算子，自动加入算子池。',
    pipelineCanvas: 'Pipeline 自进化画布',
    progressHint: '点击“推进一步”会按流程自动补全区块内容、新增 DAG 标签、必要时新增下一轮流水线行。',
    stepForward: '推进一步',
    autoBuildRound: '自动补完整轮',
    totalTime: '累计用时',
    totalTokens: '累计 Token',
    roundTitle: '流水线级自进化轮次',
    rawBlock: 'Raw Data',
    understanding: '理解',
    operatorEvolution: '算子级自进化',
    dagTabs: 'DAG 编排结果',
    instantiation: '实例化',
    sampleEval: 'Sample + LLM 评估',
    experience: '经验总结',
    pending: '待执行',
    done: '已完成',
    checkNeedEvolution: '检测结果：需要算子进化',
    checkPass: '检测结果：通过',
    llmScore: 'LLM 评分',
    willIterate: '触发下一轮流水线级迭代',
    qualityOk: '达到目标质量，结束迭代',
    runFullData: '运行全量数据',
    runQueuedToast: '已启动流程推进（前端模拟框架）。',
    fullDataToast: '全量运行已完成，画布已同步。',
    sourceBase: '基础',
    sourceEvolved: '进化',
    running: '运行中',
    active: '当前轮',
    autoTag: '自动新增 Tag',
    startSessionTitle: '保存到项目并启动',
    pipelineIdLabel: 'Pipeline ID（必填）',
    pipelineIdPlaceholder: '例如 my_pipeline_001',
    metaDomain: '领域 domain',
    metaTaskType: '任务类型 task_type',
    metaLanguage: '数据/任务语言 language',
    optionalHint: '选填',
    manifestFormHint:
      '将写入 data/manifest.jsonl：raw/seed 使用上传文件名对应的路径；启动后进入流程推进。',
    confirmStartRun: '确认并上传',
    pipelineIdRequired: '请填写 Pipeline ID',
    uploadAtLeastOneFile: '请先至少上传 Raw / Seed / 描述 中的一项',
    reuploadFilesHint: '当前会话缺少文件本体，请重新上传后再启动',
    startSessionSuccess: '已上传并写入清单，开始推进流程',
    startSessionFailed: '上传或写入清单失败',
    startSessionSaving: '正在上传…',
    saveLlmToProject: '保存设置',
    saveLlmSuccess: '已写入 config/config.json（llm）、config/api_keys.json、config/api_config.json',
    saveLlmFailed: '保存配置失败',
    saveLlmSaving: '正在保存…',
  },
  en: {
    productSub: 'Open-source Workflow UI',
    uploadArea: 'Upload Area',
    rawData: 'Raw Data',
    seedData: 'Seed Data',
    promptData: 'Description / Prompt',
    uploadRaw: 'Upload raw data file',
    uploadSeed: 'Upload seed data file',
    uploadPrompt: 'Upload task description (optional)',
    previewArea: 'Data Preview',
    noPreviewYet: 'No uploaded files yet',
    uploadHint: 'Supports JSON / JSONL / TXT. Click preview after upload to inspect data.',
    clickToUpload: 'Click to upload',
    reupload: 'Reupload',
    previewButton: 'Preview Data',
    previewModalHint: 'Shows the first lines of uploaded files for quick structure checks.',
    dragOrClick: 'Drag or click to upload data file',
    uploadFormats: '.csv .json .jsonl .txt',
    uploadedFile: 'Uploaded',
    runMode: 'Run Mode',
    manual: 'Manual',
    auto: 'Auto',
    start: 'Start',
    settings: 'Settings',
    generalSettings: 'General Settings',
    saveSession: 'Save',
    loadSession: 'Load',
    clearWorkspace: 'Clear',
    clearConfirm: 'Clear uploaded files and intermediate workspace for this run?',
    clearCancel: 'Cancel',
    clearConfirmAction: 'Confirm Clear',
    clearDone: 'Workspace for current run was cleared.',
    saveDone: 'Session file exported.',
    loadDone: 'Session file loaded to current workspace.',
    loadFailed: 'Invalid session file format.',
    saveTooltip: 'Save current workspace snapshot and evolution state',
    loadTooltip: 'Load a previously saved workspace snapshot',
    clearTooltip: 'Clear uploads and intermediate workspace for this run (asks confirmation)',
    close: 'Close',
    savedSessionName: 'dataevolver.session.json',
    theme: 'Theme',
    light: 'Light',
    dark: 'Dark',
    language: 'Language',
    chinese: 'Chinese',
    english: 'English',
    modelSettings: 'Model Settings',
    apiSettings: 'Model & Service Settings',
    backHome: 'Back Home',
    provider: 'Provider',
    providerMode: 'Provider Mode',
    openaiOfficial: 'OpenAI Official',
    thirdParty: 'Third-party Provider',
    modelName: 'Model',
    modelOptions: 'Model',
    apiKey: 'API Key',
    apiKeySaved: 'API key is stored in local browser',
    apiKeyServerHint: 'Server already has a key (leave empty and save to keep it)',
    baseUrl: 'Base URL (optional for third-party)',
    temperature: 'Temperature',
    maxTokens: 'Max Tokens',
    operatorPool: 'Operator Pool',
    operatorHint: 'New operators generated during operator-level evolution will be added in real time.',
    pipelineCanvas: 'Pipeline Self-Evolution Canvas',
    progressHint: 'Use "Step Forward" to auto-fill blocks, add DAG tabs, and create next rows when needed.',
    stepForward: 'Step Forward',
    autoBuildRound: 'Auto Complete Round',
    totalTime: 'Total Time',
    totalTokens: 'Total Tokens',
    roundTitle: 'Pipeline Self-Evolution Round',
    rawBlock: 'Raw Data',
    understanding: 'Understanding',
    operatorEvolution: 'Operator-Level Evolution',
    dagTabs: 'DAG Orchestration Results',
    instantiation: 'Instantiation',
    sampleEval: 'Sample + LLM Evaluation',
    experience: 'Experience Summary',
    pending: 'Pending',
    done: 'Done',
    checkNeedEvolution: 'Check: evolution required',
    checkPass: 'Check: passed',
    llmScore: 'LLM Score',
    willIterate: 'Trigger next pipeline-level iteration',
    qualityOk: 'Target quality reached, stop iterations',
    runFullData: 'Run Full Data',
    runQueuedToast: 'Evolution flow started (frontend scaffold simulation).',
    fullDataToast: 'Full pipeline run finished; canvas synced.',
    sourceBase: 'Base',
    sourceEvolved: 'Evolved',
    running: 'Running',
    active: 'Active',
    autoTag: 'Auto Tag',
    startSessionTitle: 'Save to project & start',
    pipelineIdLabel: 'Pipeline ID (required)',
    pipelineIdPlaceholder: 'e.g. my_pipeline_001',
    metaDomain: '领域 domain (optional)',
    metaTaskType: '任务类型 task_type (optional)',
    metaLanguage: '数据/任务语言 language (optional)',
    optionalHint: 'optional',
    manifestFormHint:
      'Appends to data/manifest.jsonl; raw/seed paths match uploaded filenames. Then the run proceeds.',
    confirmStartRun: 'Confirm & upload',
    pipelineIdRequired: 'Pipeline ID is required',
    uploadAtLeastOneFile: 'Upload at least one of Raw / Seed / Description first',
    reuploadFilesHint: 'Session has no file bytes; re-upload files before starting',
    startSessionSuccess: 'Uploaded and manifest updated; starting flow',
    startSessionFailed: 'Upload or manifest write failed',
    startSessionSaving: 'Uploading…',
    saveLlmToProject: 'Save to project',
    saveLlmSuccess: 'Wrote config/config.json (llm), config/api_keys.json, config/api_config.json',
    saveLlmFailed: 'Failed to save config',
    saveLlmSaving: 'Saving…',
  },
}

export function MainLayout() {
  const runMode = useAppStore((s) => s.runMode)
  const setRunMode = useAppStore((s) => s.setRunMode)
  const upload = useAppStore((s) => s.upload)
  const setUpload = useAppStore((s) => s.setUpload)
  const themeMode = useAppStore((s) => s.themeMode)
  const setThemeMode = useAppStore((s) => s.setThemeMode)
  const language = useAppStore((s) => s.language)
  const setLanguage = useAppStore((s) => s.setLanguage)
  const llmConfig = useAppStore((s) => s.llmConfig)
  const setLlmConfig = useAppStore((s) => s.setLlmConfig)
  const setToast = useAppStore((s) => s.setToast)
  const pipelineId = useAppStore((s) => s.pipelineId)
  const setPipelineId = useAppStore((s) => s.setPipelineId)

  const t = TEXT[language]

  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsTab, setSettingsTab] = useState<SettingsTab>('general')
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false)
  const [actionHover, setActionHover] = useState<'save' | 'load' | 'clear' | null>(null)
  const [providerMode, setProviderMode] = useState<ProviderMode>('openai-official')
  const [apiKeyDraft, setApiKeyDraft] = useState('')
  const [baseUrlDraft, setBaseUrlDraft] = useState('')
  /** 服务端是否已有密钥（GET /api/config/llm，无明文） */
  const [serverKeyHint, setServerKeyHint] = useState<{ configured: boolean; masked: string } | null>(null)

  const [rows, setRows] = useState<EvolutionRow[]>([])
  const [operatorPool, setOperatorPool] = useState<OperatorItem[]>([])
  const [activeRowId, setActiveRowId] = useState(1)
  const [finished, setFinished] = useState(false)
  const [uploadPreview, setUploadPreview] = useState<UploadPreviewState>({
    raw: [],
    seed: [],
    description: [],
  })
  const [previewModalOpen, setPreviewModalOpen] = useState(false)
  const [previewModalTab, setPreviewModalTab] = useState<UploadFileKey>('raw')
  const [startModalOpen, setStartModalOpen] = useState(false)
  const [pipelineIdInput, setPipelineIdInput] = useState('')
  const [metaDomainInput, setMetaDomainInput] = useState('')
  const [metaTaskTypeInput, setMetaTaskTypeInput] = useState('')
  const [metaLanguageInput, setMetaLanguageInput] = useState('')
  const [startSubmitting, setStartSubmitting] = useState(false)
  const [configSaving, setConfigSaving] = useState(false)
  const [liveArtifacts, setLiveArtifacts] = useState<LiveArtifactsForCanvas | null>(null)
  const [workflowBusy, setWorkflowBusy] = useState(false)
  const [workflowApiAvailable, setWorkflowApiAvailable] = useState(true)
  const [workflowExecutingStep, setWorkflowExecutingStep] = useState<string | null>(null)
  const [lastExecutedStep, setLastExecutedStep] = useState<string | null>(null)
  const [stepDurations, setStepDurations] = useState<StepTimingMap>({})
  const [canRunFull, setCanRunFull] = useState(false)
  const [workflowState, setWorkflowState] = useState<WorkflowStateDto | null>(null)
  const [artifactHistoryCount, setArtifactHistoryCount] = useState(0)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  /** 与上传元数据对应的浏览器 File，用于提交后端；会话加载不含文件本体时需重新上传 */
  const uploadFilesRef = useRef<Partial<Record<UploadFileKey, File>>>({})

  const rawInputRef = useRef<HTMLInputElement | null>(null)
  const seedInputRef = useRef<HTMLInputElement | null>(null)
  const descInputRef = useRef<HTMLInputElement | null>(null)
  const sessionInputRef = useRef<HTMLInputElement | null>(null)
  const modelOptions = MODEL_OPTIONS

  const handleSaveLlmConfig = useCallback(async () => {
    setConfigSaving(true)
    try {
      await saveLlmConfigToServer({
        provider_mode: providerMode,
        model: llmConfig.model,
        temperature: llmConfig.temperature,
        max_tokens: llmConfig.maxTokens,
        api_key: apiKeyDraft,
        base_url: baseUrlDraft,
      })
      try {
        const refreshed = await fetchLlmConfigFromServer()
        setServerKeyHint({
          configured: refreshed.api_key_configured,
          masked: refreshed.api_key_masked,
        })
      } catch {
        setServerKeyHint((prev) => prev ?? { configured: true, masked: '' })
      }
      setToast({
        message: t.saveLlmSuccess,
        type: 'success',
      })
    } catch (e) {
      let msg = t.saveLlmFailed
      if (e instanceof ApiError && e.detail) {
        try {
          const j = JSON.parse(e.detail) as { detail?: unknown }
          if (typeof j.detail === 'string') msg = j.detail
          else msg = `${msg}: ${e.detail.slice(0, 200)}`
        } catch {
          msg = `${msg}: ${e.detail.slice(0, 200)}`
        }
      }
      setToast({ message: msg, type: 'error' })
    } finally {
      setConfigSaving(false)
    }
  }, [
    apiKeyDraft,
    baseUrlDraft,
    llmConfig.maxTokens,
    llmConfig.model,
    llmConfig.temperature,
    providerMode,
    setToast,
    t.saveLlmFailed,
    t.saveLlmSuccess,
  ])

  useEffect(() => {
    const storedApiKey = localStorage.getItem('dataevolver.apiKey')
    if (storedApiKey) setApiKeyDraft(storedApiKey)
  }, [])

  useEffect(() => {
    let cancelled = false
    void fetchLlmConfigFromServer()
      .then((data) => {
        if (cancelled) return
        setProviderMode(data.provider_mode)
        setLlmConfig({
          model: data.model,
          temperature: data.temperature,
          maxTokens: data.max_tokens,
          provider: data.provider_mode === 'openai-official' ? 'openai' : 'custom',
        })
        if (data.provider_mode === 'third-party') {
          setBaseUrlDraft(data.base_url)
        } else {
          setBaseUrlDraft('')
        }
        setServerKeyHint({
          configured: data.api_key_configured,
          masked: data.api_key_masked,
        })
      })
      .catch(() => {
        if (cancelled) return
        const storedBaseUrl = localStorage.getItem('dataevolver.baseUrl')
        const storedProviderMode = localStorage.getItem('dataevolver.providerMode')
        if (storedBaseUrl) setBaseUrlDraft(storedBaseUrl)
        if (storedProviderMode === 'openai-official' || storedProviderMode === 'third-party') {
          setProviderMode(storedProviderMode)
        }
        setServerKeyHint(null)
      })
    return () => {
      cancelled = true
    }
  }, [setLlmConfig])

  useEffect(() => {
    localStorage.setItem('dataevolver.apiKey', apiKeyDraft)
  }, [apiKeyDraft])

  useEffect(() => {
    localStorage.setItem('dataevolver.baseUrl', baseUrlDraft)
  }, [baseUrlDraft])

  useEffect(() => {
    localStorage.setItem('dataevolver.providerMode', providerMode)
    setLlmConfig({ provider: providerMode === 'openai-official' ? 'openai' : 'custom' })
  }, [providerMode, setLlmConfig])

  const reloadOperatorPool = useCallback(async () => {
    try {
      const data = await fetchOperators()
      setOperatorPool(mapApiOperatorsToPoolItems(data.operators, language))
    } catch (e) {
      const detail = e instanceof ApiError ? e.detail : String(e)
      setToast({
        message: `${language === 'zh' ? '算子池加载失败' : 'Failed to load operator pool'}${detail ? `: ${detail.slice(0, 160)}` : ''}`,
        type: 'error',
      })
      setOperatorPool([])
    }
  }, [language, setToast])

  useEffect(() => {
    void reloadOperatorPool()
  }, [reloadOperatorPool])

  async function fetchOptional404<T>(fn: () => Promise<T>): Promise<T | null> {
    try {
      return await fn()
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null
      throw e
    }
  }

  const refreshPipelineFromServer = useCallback(
    async (pid: string, timingPatch?: StepTimingMap) => {
      let wf: WorkflowStateResponse | null = null
      try {
        wf = await fetchWorkflowState(pid)
        setWorkflowApiAvailable(true)
      } catch (e) {
        // 兼容旧后端：仅有 session/preview/understanding 接口时，不阻断前端加载。
        if (!(e instanceof ApiError) || e.status !== 404) throw e
        setWorkflowApiAvailable(false)
      }
      const [underRes, dagJson, inst, quality, trial, experience, tokens, _runLatest, _history] = await Promise.all([
        fetchOptional404(() => fetchUnderstandingResult(pid)),
        fetchOptional404(() => fetchOrchestrationDag(pid)),
        fetchOptional404(() => fetchInstantiationSteps(pid, { include_code: true })),
        fetchOptional404(() => fetchQualityCheck(pid)),
        fetchOptional404(() => fetchTrialResult(pid)),
        fetchOptional404(() => fetchExperience(pid)),
        fetchOptional404(() => fetchWorkflowTokens(pid)),
        fetchOptional404(() => fetchPipelineRunLatest(pid)),
        fetchOptional404(() => fetchArtifactHistory(pid, 40)),
      ])
      const understanding = underRes?.data ?? null
      void _runLatest
      setArtifactHistoryCount(_history?.entries?.length ?? 0)
      if (!wf) {
        wf = {
          ok: true,
          pipeline_id: pid,
          state: {
            pipeline_id: pid,
            step_index: 0,
            steps_completed: understanding ? ['understanding'] : [],
            last_message:
              language === 'zh'
                ? '检测到旧版后端：workflow API 不可用，已进入兼容展示模式。'
                : 'Legacy backend detected: workflow API unavailable, using compatibility mode.',
            updated_at: '',
            round: 1,
            quality_passed: false,
            ready_for_full_run: false,
            next_action: 'advance',
            step_order: ['understanding'],
            is_complete: false,
          },
          artifacts: {
            understanding: Boolean(understanding),
            orchestration: Boolean(dagJson),
            instantiation: Boolean(inst?.steps?.length),
            trial_run: Boolean(trial?.data),
            pipeline_run: Boolean(_runLatest?.latest || _runLatest?.report),
            quality_check: Boolean(quality?.data),
            experience: Boolean(experience?.data),
          },
        }
      }
      const built = buildEvolutionRowsFromPipeline(wf, {
        understanding,
        dagResponse: dagJson,
        instantiationSteps: inst?.steps ?? null,
        quality: quality?.data ?? null,
        trial: trial?.data ?? null,
        experience: experience?.data ?? null,
        tokens: tokens ?? null,
        history: _history ?? null,
        lastAdvanceMessage: wf.state.last_message ?? '',
        language,
      })
      const timing = timingPatch ? { ...stepDurations, ...timingPatch } : stepDurations
      const measuredRows = applyMeasuredDurations(built.rows as EvolutionRow[], timing)
      setRows((prev) => {
        const incoming = measuredRows
        if (!incoming.length) return []
        // 后端未返回完整 history 时，保留“已完成的历史轮次”，避免进入下一轮后第一轮被清空。
        if (incoming.length === 1) {
          const cur = incoming[0]
          const prevRoundId = Math.max(0, cur.id - 1)
          const preserved = prev
            .filter((r) => r.id < cur.id)
            .map((r) =>
              r.id === prevRoundId
                ? {
                    ...r,
                    completed: true,
                    needNext: true,
                  }
                : { ...r, completed: true }
            )
          const merged = [...preserved, cur]
          merged.sort((a, b) => a.id - b.id)
          return merged
        }
        return incoming
      })
      setFinished(built.finished)
      setLiveArtifacts(built.live)
      setWorkflowState(wf.state)
      setCanRunFull(Boolean(wf.state.ready_for_full_run || wf.state.is_complete || built.canRunFullByJudge))
      setActiveRowId(built.rows[built.rows.length - 1]?.id ?? 1)
    },
    [language, stepDurations]
  )

  const syncPreviewsFromServer = useCallback(async (pid: string) => {
    const kinds: UploadFileKey[] = ['raw', 'seed', 'description']
    const next: UploadPreviewState = { raw: [], seed: [], description: [] }
    for (const kind of kinds) {
      try {
        const p = await fetchPipelinePreview(pid, kind, { max_lines: PREVIEW_LINE_COUNT })
        if (p.lines?.length) next[kind] = p.lines
      } catch {
        /* 无对应文件或尚未就绪 */
      }
    }
    setUploadPreview((prev) => ({ ...prev, ...next }))
  }, [])

  useEffect(() => {
    if (!pipelineId) {
      setLiveArtifacts(null)
      setWorkflowState(null)
      return
    }
    let cancelled = false
    setWorkflowBusy(true)
    void (async () => {
      try {
        await refreshPipelineFromServer(pipelineId)
      } catch (e) {
        if (!cancelled) {
          const detail = e instanceof ApiError ? e.detail : String(e)
          setToast({
            message:
              (language === 'zh' ? '同步管线状态失败' : 'Failed to sync pipeline state') +
              (detail ? `: ${detail.slice(0, 160)}` : ''),
            type: 'error',
          })
        }
      } finally {
        if (!cancelled) setWorkflowBusy(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [pipelineId, refreshPipelineFromServer, language, setToast])

  const totalMetrics = useMemo(() => {
    let sec = 0
    let tokens = 0
    rows.forEach((row) => {
      if (row.understandingMetrics) {
        sec += row.understandingMetrics.sec
        tokens += row.understandingMetrics.tokens
      }
      row.dagTabs.forEach((tab) => {
        sec += tab.metrics.sec
        tokens += tab.metrics.tokens
      })
      row.instantiationCards.forEach((card) => {
        sec += card.metrics.sec
        tokens += card.metrics.tokens
      })
      if (row.sampleMetrics) {
        sec += row.sampleMetrics.sec
        tokens += row.sampleMetrics.tokens
      }
      if (row.experienceMetrics) {
        sec += row.experienceMetrics.sec
        tokens += row.experienceMetrics.tokens
      }
    })
    return { sec, tokens }
  }, [rows])

  const formatSize = (size: number) => {
    if (size < 1024) return `${size} B`
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
    return `${(size / (1024 * 1024)).toFixed(1)} MB`
  }

  const parsePreviewLines = async (file: File) => {
    const text = await file.text()
    const rawLines = text.split(/\r?\n/)
    const rows = rawLines.filter((line) => line.trim().length > 0).length
    const preview = rawLines.slice(0, PREVIEW_LINE_COUNT)
    return { rows, preview }
  }

  const handleFileSelect =
    (key: UploadFileKey) => async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0]
      if (!file) return
      const { rows: lineCount, preview } = await parsePreviewLines(file)
      uploadFilesRef.current[key] = file
      setUpload({
        [key]: {
          name: file.name,
          size: file.size,
          rows: lineCount,
        },
      })
      setUploadPreview((prev) => ({
        ...prev,
        [key]: preview,
      }))
    }

  const selectDagTab = (rowId: number, tabId: number) => {
    setRows((prev) =>
      prev.map((row) => (row.id === rowId ? { ...row, activeDagTabId: tabId } : row))
    )
  }

  const stepForward = useCallback(async () => {
    if (pipelineId) {
      if (finished) return
      if (!workflowApiAvailable) {
        setToast({
          message:
            language === 'zh'
              ? '当前后端未启用 workflow 接口（/api/workflow/*）。请启动最新版 run_server.py 后再推进。'
              : 'Workflow APIs (/api/workflow/*) are unavailable on current backend. Start latest run_server.py first.',
          type: 'error',
        })
        return
      }
      if (workflowState?.next_action === 'run_full' || workflowState?.ready_for_full_run) {
        setToast({
          message:
            language === 'zh'
              ? '闭环已通过，请点击“应用全量”执行 run-full。'
              : 'Quality loop passed. Click "Apply Pipeline" to run full data.',
          type: 'info',
        })
        return
      }
      setWorkflowBusy(true)
      const order = workflowState?.step_order ?? []
      const idx = workflowState?.step_index ?? 0
      const stepKey = idx >= 0 && idx < order.length ? order[idx] : null
      const roundId = Math.max(1, Number(workflowState?.round ?? 1))
      setWorkflowExecutingStep(stepKey)
      const startedAt = Date.now()
      try {
        const res = await advanceWorkflow(pipelineId)
        const elapsedSec = Math.max(0.01, (Date.now() - startedAt) / 1000)
        const executedStep = (res.step || stepKey || '').trim()
        const timingPatch: StepTimingMap =
          executedStep.length > 0 ? { [timingKey(roundId, executedStep)]: elapsedSec } : {}
        if (executedStep.length > 0) setLastExecutedStep(executedStep)
        if (Object.keys(timingPatch).length > 0) {
          setStepDurations((prev) => ({ ...prev, ...timingPatch }))
        }
        await refreshPipelineFromServer(pipelineId, timingPatch)
        if (res.done) {
          setToast({
            message: language === 'zh' ? '全部流程已完成。' : 'All workflow steps are complete.',
            type: 'success',
          })
        }
      } catch (e) {
        const raw = e instanceof ApiError ? e.detail : String(e)
        const parsed = parseFastApiErrorBody(raw)
        try {
          await refreshPipelineFromServer(pipelineId)
        } catch {
          /* 同步失败时仍展示推进错误 */
        }
        setToast({
          message:
            (language === 'zh' ? '工作流推进失败：' : 'Workflow step failed: ') + parsed.userMessage,
          type: 'error',
        })
      } finally {
        setWorkflowExecutingStep(null)
        setWorkflowBusy(false)
      }
      return
    }
    setToast({
      message: language === 'zh' ? '请先启动会话并上传文件。' : 'Please start a session and upload files first.',
      type: 'info',
    })
  }, [pipelineId, finished, workflowApiAvailable, workflowState, refreshPipelineFromServer, language, setToast])

  const autoCompleteCurrentRound = useCallback(async () => {
    if (pipelineId) {
      if (!workflowApiAvailable) {
        setToast({
          message:
            language === 'zh'
              ? '当前后端未启用 workflow 接口（/api/workflow/*），无法自动推进。'
              : 'Workflow APIs (/api/workflow/*) are unavailable; auto-advance is disabled.',
          type: 'error',
        })
        return
      }
      setWorkflowBusy(true)
      try {
        let guard = 0
        const timingPatch: StepTimingMap = {}
        const baseRound = Math.max(1, Number(workflowState?.round ?? 1))
        while (guard < 32) {
          const wf = await fetchWorkflowState(pipelineId)
          if (wf.state.is_complete || wf.state.ready_for_full_run) break
          const nextKey =
            wf.state.step_index >= 0 && wf.state.step_index < wf.state.step_order.length
              ? wf.state.step_order[wf.state.step_index]
              : null
          const roundId = Math.max(1, Number(wf.state.round ?? 1))
          setWorkflowExecutingStep(nextKey)
          const startedAt = Date.now()
          const adv = await advanceWorkflow(pipelineId)
          const elapsedSec = Math.max(0.01, (Date.now() - startedAt) / 1000)
          const executedStep = (adv.step || nextKey || '').trim()
          if (executedStep.length > 0) {
            timingPatch[timingKey(roundId, executedStep)] = elapsedSec
            setLastExecutedStep(executedStep)
          }
          guard += 1
          if (adv.done) break
          // “自动补完整轮”只跑到当前轮最后一步（experience）为止，不自动进入下一轮 understanding。
          if (executedStep === 'experience') break
          if (Math.max(1, Number(adv.state?.round ?? baseRound)) > baseRound) break
        }
        if (Object.keys(timingPatch).length > 0) {
          setStepDurations((prev) => ({ ...prev, ...timingPatch }))
        }
        await refreshPipelineFromServer(pipelineId, timingPatch)
        setToast({
          message: language === 'zh' ? '自动推进已结束，画布已同步。' : 'Auto-advance finished; canvas synced.',
          type: 'success',
        })
      } catch (e) {
        const raw = e instanceof ApiError ? e.detail : String(e)
        const parsed = parseFastApiErrorBody(raw)
        try {
          await refreshPipelineFromServer(pipelineId)
        } catch {
          /* ignore */
        }
        setToast({
          message:
            (language === 'zh' ? '自动推进失败：' : 'Auto-advance failed: ') + parsed.userMessage,
          type: 'error',
        })
      } finally {
        setWorkflowExecutingStep(null)
        setWorkflowBusy(false)
      }
      return
    }
    setToast({
      message: language === 'zh' ? '请先启动会话并上传文件。' : 'Please start a session and upload files first.',
      type: 'info',
    })
  }, [pipelineId, workflowApiAvailable, workflowState, refreshPipelineFromServer, language, setToast])

  const runAutoModeWorkflow = useCallback(
    async (pid: string) => {
      if (!pid) return
      if (!workflowApiAvailable) {
        setToast({
          message:
            language === 'zh'
              ? '当前后端未启用 workflow 接口（/api/workflow/*），无法自动模式运行。'
              : 'Workflow APIs (/api/workflow/*) are unavailable; auto mode cannot run.',
          type: 'error',
        })
        return
      }
      setWorkflowBusy(true)
      setWorkflowExecutingStep(null)
      try {
        const timingPatch: StepTimingMap = {}
        let guard = 0
        while (guard < 96) {
          const wf = await fetchWorkflowState(pid)
          if (wf.state.ready_for_full_run || wf.state.next_action === 'run_full' || wf.state.is_complete) {
            await runPipelineFull(pid)
            if (Object.keys(timingPatch).length > 0) {
              setStepDurations((prev) => ({ ...prev, ...timingPatch }))
            }
            await refreshPipelineFromServer(pid, timingPatch)
            setToast({
              message: language === 'zh' ? '自动模式已完成（含全量运行）。' : 'Auto mode finished (including full run).',
              type: 'success',
            })
            return
          }
          const order = wf.state.step_order ?? []
          const idx = wf.state.step_index ?? 0
          const stepKey = idx >= 0 && idx < order.length ? order[idx] : null
          const roundId = Math.max(1, Number(wf.state.round ?? 1))
          setWorkflowExecutingStep(stepKey)
          const startedAt = Date.now()
          const adv = await advanceWorkflow(pid)
          const elapsedSec = Math.max(0.01, (Date.now() - startedAt) / 1000)
          const executedStep = (adv.step || stepKey || '').trim()
          if (executedStep) {
            timingPatch[timingKey(roundId, executedStep)] = elapsedSec
            setLastExecutedStep(executedStep)
          }
          guard += 1
          if (adv.done || adv.state?.ready_for_full_run || adv.state?.next_action === 'run_full') {
            continue
          }
        }
        if (Object.keys(timingPatch).length > 0) {
          setStepDurations((prev) => ({ ...prev, ...timingPatch }))
        }
        await refreshPipelineFromServer(pid, timingPatch)
        setToast({
          message:
            language === 'zh'
              ? '自动模式达到步数上限，已停止，请检查当前状态后继续。'
              : 'Auto mode reached max step guard and stopped. Check state before continuing.',
          type: 'info',
        })
      } catch (e) {
        const raw = e instanceof ApiError ? e.detail : String(e)
        const parsed = parseFastApiErrorBody(raw)
        try {
          await refreshPipelineFromServer(pid)
        } catch {
          /* ignore */
        }
        setToast({
          message: (language === 'zh' ? '自动模式失败：' : 'Auto mode failed: ') + parsed.userMessage,
          type: 'error',
        })
      } finally {
        setWorkflowExecutingStep(null)
        setWorkflowBusy(false)
      }
    },
    [workflowApiAvailable, language, refreshPipelineFromServer, setToast]
  )

  const openStartModal = () => {
    const hasMeta = Boolean(upload.raw || upload.seed || upload.description)
    if (!hasMeta) {
      setToast({ message: t.uploadAtLeastOneFile, type: 'error' })
      return
    }
    if (upload.raw && !uploadFilesRef.current.raw) {
      setToast({ message: t.reuploadFilesHint, type: 'error' })
      return
    }
    if (upload.seed && !uploadFilesRef.current.seed) {
      setToast({ message: t.reuploadFilesHint, type: 'error' })
      return
    }
    if (upload.description && !uploadFilesRef.current.description) {
      setToast({ message: t.reuploadFilesHint, type: 'error' })
      return
    }
    setPipelineIdInput(upload.pipelineId ?? '')
    setStartModalOpen(true)
  }

  const submitStartSession = async () => {
    const pid = pipelineIdInput.trim()
    if (!pid) {
      setToast({ message: t.pipelineIdRequired, type: 'error' })
      return
    }
    const fd = new FormData()
    fd.append('pipeline_id', pid)
    if (metaDomainInput.trim()) fd.append('domain', metaDomainInput.trim())
    if (metaTaskTypeInput.trim()) fd.append('task_type', metaTaskTypeInput.trim())
    if (metaLanguageInput.trim()) fd.append('language', metaLanguageInput.trim())
    const raw = uploadFilesRef.current.raw
    const seed = uploadFilesRef.current.seed
    const desc = uploadFilesRef.current.description
    if (raw) fd.append('raw_file', raw, raw.name)
    if (seed) fd.append('seed_file', seed, seed.name)
    if (desc) fd.append('description_file', desc, desc.name)

    setStartSubmitting(true)
    try {
      await startSessionUpload(fd)
      // 上传后同一 pipeline_id 可能残留历史轮次；先重置到第一轮入口，避免旧图回灌。
      try {
        await resetWorkflowForDebug(pid)
      } catch (e) {
        // 兼容旧后端：若没有 reset-for-debug，降级到 reset + rerun。
        if (!(e instanceof ApiError) || e.status !== 404) throw e
        try {
          await resetWorkflowState(pid)
          await rerunWorkflowFromStep(pid, 'understanding')
        } catch (e2) {
          if (!(e2 instanceof ApiError) || e2.status !== 404) throw e2
        }
      }
      setPipelineId(pid)
      setUpload({ pipelineId: pid })
      setRows([makeEntryOnlyRow(1)])
      setActiveRowId(1)
      setFinished(false)
      setCanRunFull(false)
      setLiveArtifacts(null)
      setWorkflowState(null)
      setLastExecutedStep(null)
      setStepDurations({})
      setArtifactHistoryCount(0)
      setStartModalOpen(false)
      setToast({ message: t.startSessionSuccess, type: 'success' })
      setToast({ message: t.runQueuedToast, type: 'info' })
      try {
        await syncPreviewsFromServer(pid)
      } catch {
        /* 预览可选 */
      }
      if (runMode === 'auto') {
        void runAutoModeWorkflow(pid)
      }
    } catch (e) {
      const detail = e instanceof ApiError ? e.detail : String(e)
      setToast({
        message: `${t.startSessionFailed}${detail ? `: ${detail.slice(0, 200)}` : ''}`,
        type: 'error',
      })
    } finally {
      setStartSubmitting(false)
    }
  }

  const runFullData = useCallback(async () => {
    if (pipelineId) {
      if (!canRunFull) {
        setToast({
          message:
            language === 'zh'
              ? '当前尚未通过质检闭环，暂不可执行全量运行。'
              : 'Quality loop is not passed yet, full run is disabled.',
          type: 'error',
        })
        return
      }
      setWorkflowBusy(true)
      try {
        await runPipelineFull(pipelineId)
        await refreshPipelineFromServer(pipelineId)
        setToast({ message: t.fullDataToast, type: 'success' })
      } catch (e) {
        const raw = e instanceof ApiError ? e.detail : String(e)
        const parsed = parseFastApiErrorBody(raw)
        setToast({
          message:
            (language === 'zh' ? '全量运行失败：' : 'Full pipeline run failed: ') + parsed.userMessage,
          type: 'error',
        })
      } finally {
        setWorkflowBusy(false)
      }
      return
    }
    setToast({
      message: language === 'zh' ? '请先加载一个有效 pipeline，再执行全量运行。' : 'Load a valid pipeline before running full data.',
      type: 'error',
    })
  }, [pipelineId, canRunFull, refreshPipelineFromServer, language, setToast, t.fullDataToast])

  const rerunFromCurrentStep = useCallback(async () => {
    if (!pipelineId) return
    const stepOrder = workflowState?.step_order ?? []
    const stepIndex = workflowState?.step_index ?? 0
    const stateMessage = (workflowState?.last_message ?? '').trim()
    const inferredByMessage = stateMessage.includes(':') ? stateMessage.split(':', 1)[0].trim() : ''
    const fallbackStep =
      stepOrder.length === 0
        ? 'understanding'
        : stepIndex <= 0
          ? stepOrder[0]
          : stepIndex >= stepOrder.length
            ? workflowState?.ready_for_full_run || workflowState?.next_action === 'run_full'
              ? 'quality_check'
              : stepOrder[stepOrder.length - 1]
            : stepOrder[stepIndex - 1]
    const targetStep =
      (lastExecutedStep && stepOrder.includes(lastExecutedStep) && lastExecutedStep) ||
      (inferredByMessage && stepOrder.includes(inferredByMessage) && inferredByMessage) ||
      fallbackStep
    setWorkflowBusy(true)
    try {
      await rerunWorkflowFromStep(pipelineId, targetStep)
      setWorkflowExecutingStep(targetStep)
      const startedAt = Date.now()
      const res = await advanceWorkflow(pipelineId)
      const elapsedSec = Math.max(0.01, (Date.now() - startedAt) / 1000)
      const executedStep = (res.step || targetStep || '').trim()
      const roundId = Math.max(1, Number(workflowState?.round ?? 1))
      const timingPatch: StepTimingMap =
        executedStep.length > 0 ? { [timingKey(roundId, executedStep)]: elapsedSec } : {}
      if (Object.keys(timingPatch).length > 0) {
        setStepDurations((prev) => ({ ...prev, ...timingPatch }))
      }
      await refreshPipelineFromServer(pipelineId, timingPatch)
      setLastExecutedStep(executedStep || targetStep)
      setToast({
        message:
          language === 'zh'
            ? `已重跑步骤 ${executedStep || targetStep}。`
            : `Step ${executedStep || targetStep} rerun completed.`,
        type: 'success',
      })
    } catch (e) {
      const detail = e instanceof ApiError ? e.detail : String(e)
      setToast({
        message: `${language === 'zh' ? '重跑失败' : 'Rerun failed'}${detail ? `: ${detail.slice(0, 180)}` : ''}`,
        type: 'error',
      })
    } finally {
      setWorkflowExecutingStep(null)
      setWorkflowBusy(false)
    }
  }, [pipelineId, workflowState, lastExecutedStep, refreshPipelineFromServer, language, setToast])

  const openSessionFileDialog = () => sessionInputRef.current?.click()

  const handleSaveSession = () => {
    const payload = {
      format: 'dataevolver-session-v1',
      savedAt: new Date().toISOString(),
      upload,
      uploadPreview,
      runMode,
      themeMode,
      language,
      llmConfig,
      rows,
      operatorPool,
      activeRowId,
      finished,
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = t.savedSessionName
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    setToast({ message: t.saveDone, type: 'success' })
  }

  const handleLoadSession = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const parsed = JSON.parse(text)
      if (parsed?.format !== 'dataevolver-session-v1') throw new Error('invalid format')
      setUpload(parsed.upload ?? {})
      setUploadPreview(
        parsed.uploadPreview ?? {
          raw: [],
          seed: [],
          description: [],
        }
      )
      if (parsed.runMode === 'manual' || parsed.runMode === 'auto') setRunMode(parsed.runMode)
      if (parsed.themeMode === 'light' || parsed.themeMode === 'dark') setThemeMode(parsed.themeMode)
      if (parsed.language === 'zh' || parsed.language === 'en') setLanguage(parsed.language)
      if (parsed.llmConfig) setLlmConfig(parsed.llmConfig)
      if (Array.isArray(parsed.rows)) setRows(parsed.rows)
      if (Array.isArray(parsed.operatorPool)) setOperatorPool(parsed.operatorPool)
      if (typeof parsed.activeRowId === 'number') setActiveRowId(parsed.activeRowId)
      if (typeof parsed.finished === 'boolean') setFinished(parsed.finished)
      setLastExecutedStep(null)
      const loadedPid = parsed.upload?.pipelineId
      if (typeof loadedPid === 'string' && loadedPid.trim()) setPipelineId(loadedPid.trim())
      else setPipelineId(null)
      setToast({ message: t.loadDone, type: 'success' })
    } catch {
      setToast({ message: t.loadFailed, type: 'error' })
    } finally {
      event.target.value = ''
    }
  }

  const handleClearWorkspace = () => {
    uploadFilesRef.current = {}
    setUpload({})
    setUploadPreview({ raw: [], seed: [], description: [] })
    setPipelineId(null)
    setLiveArtifacts(null)
    setRows([])
    void reloadOperatorPool()
    setActiveRowId(1)
    setLastExecutedStep(null)
    setFinished(false)
    setToast({ message: t.clearDone, type: 'info' })
  }

  const previewTabs = useMemo(
    () =>
      (['raw', 'seed', 'description'] as UploadFileKey[]).filter(
        (key) => Boolean(upload[key]) || uploadPreview[key].length > 0
      ),
    [upload, uploadPreview]
  )

  const openPreviewModal = useCallback(
    (preferred?: UploadFileKey) => {
      if (previewTabs.length === 0) return
      const next = preferred && previewTabs.includes(preferred) ? preferred : previewTabs[0]
      setPreviewModalTab(next)
      setPreviewModalOpen(true)
    },
    [previewTabs]
  )
  const previewDisplayLines = useMemo(
    () => formatPreviewLinesForDisplay(uploadPreview[previewModalTab] ?? []),
    [previewModalTab, uploadPreview]
  )
  useEffect(() => {
    if (!previewModalOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPreviewModalOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [previewModalOpen])

  const renderUploadCard = (
    label: string,
    key: UploadFileKey,
    placeholder: string,
    inputRef: { current: HTMLInputElement | null }
  ) => {
    const fileMeta = upload[key]
    return (
      <label className="block">
        <span className="text-xs text-[var(--text-muted)]">{label}</span>
        <input ref={inputRef} type="file" className="hidden" onChange={handleFileSelect(key)} />
        <div
          className="mt-1 w-full rounded-xl border border-dashed px-2.5 py-2 text-left min-h-[98px] flex items-center gap-3"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
        >
          <div className="w-7 h-7 rounded-lg border flex items-center justify-center shrink-0" style={{ borderColor: 'var(--border)' }}>
            <UploadCloud className="w-3 h-3 text-[var(--de-cyan)]" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[0.95rem] text-[var(--text)] truncate">
              {fileMeta ? fileMeta.name : placeholder}
            </p>
            <p className="text-[10px] text-[var(--text-muted)] mt-0.5">
              {fileMeta ? t.uploadedFile : t.dragOrClick}
            </p>
            {fileMeta && 'rows' in fileMeta && fileMeta.rows !== undefined ? (
              <p className="text-[10px] text-[var(--text-muted)] mt-0.5">
                {fileMeta.rows} rows{fileMeta.size != null ? ` · ${formatSize(fileMeta.size)}` : ''}
              </p>
            ) : (
              <p className="text-[10px] text-[var(--text-muted)] mt-0.5">{t.uploadFormats}</p>
            )}
          </div>
          <div className="w-[92px] shrink-0 flex flex-col gap-1.5">
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="w-full h-8 rounded-lg border text-xs inline-flex items-center justify-center"
              style={{ borderColor: 'var(--border)', background: 'var(--bg-card)', color: 'var(--text-dim)' }}
            >
              {fileMeta ? t.reupload : t.clickToUpload}
            </button>
            {fileMeta && (
              <button
                type="button"
                onClick={() => openPreviewModal(key)}
                className="w-full h-8 rounded-lg border text-xs inline-flex items-center justify-center gap-1.5"
                style={{ borderColor: 'var(--border)', background: 'var(--bg-card)', color: 'var(--text-dim)' }}
              >
                <Eye className="w-3.5 h-3.5" />
                {t.previewButton}
              </button>
            )}
          </div>
        </div>
      </label>
    )
  }

  return (
    <div className="min-h-screen relative z-10 p-4 md:p-6">
      <div
        className="mx-auto max-w-[1560px] h-[calc(100vh-2rem)] md:h-[calc(100vh-3rem)] rounded-3xl border overflow-hidden grid"
            style={{
          borderColor: 'var(--border)',
          background: 'var(--bg-panel)',
          boxShadow: `0 0 0 1px var(--shell-ring), var(--shell-shadow)`,
          gridTemplateColumns: sidebarCollapsed ? '64px minmax(0, 1fr)' : '320px minmax(0, 1fr)',
        }}
      >
        <aside
          className={`h-full flex flex-col border-r py-5 overflow-auto ${sidebarCollapsed ? 'px-2' : 'px-5'}`}
          style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}
        >
          <div className={`mb-6 flex items-center ${sidebarCollapsed ? 'justify-center' : 'justify-between gap-3'}`}>
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center border shrink-0" style={{ borderColor: 'var(--border)' }}>
                <Database className="w-4 h-4 text-[var(--de-cyan)]" />
        </div>
              {!sidebarCollapsed && (
                <div className="min-w-0">
                  <p className="text-lg font-semibold text-[var(--text)] leading-none">多模态数据准备</p>
                  <p className="text-xs text-[var(--text-muted)] mt-1 truncate">{t.productSub}</p>
                </div>
              )}
            </div>
            {!sidebarCollapsed && (
              <button
                type="button"
                className="w-8 h-8 rounded-lg border inline-flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text)]"
                style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
                title={language === 'zh' ? '折叠导航区' : 'Collapse sidebar'}
                onClick={() => setSidebarCollapsed(true)}
              >
                <PanelLeftClose className="w-4 h-4" />
              </button>
            )}
          </div>

          {sidebarCollapsed ? (
            <div className="flex-1 flex flex-col items-center gap-2 pt-1">
              <button
                type="button"
                className="w-10 h-10 rounded-xl border flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text)]"
                style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
                title={language === 'zh' ? '展开导航区' : 'Expand sidebar'}
                onClick={() => setSidebarCollapsed(false)}
              >
                <PanelLeftOpen className="w-4 h-4" />
              </button>
              <button
                type="button"
                className="w-10 h-10 rounded-xl border flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text)]"
                style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
                title={t.start}
                onClick={openStartModal}
              >
                <Play className="w-4 h-4" />
              </button>
              <button
                type="button"
                className="w-10 h-10 rounded-xl border flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text)]"
                style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
                title={t.settings}
                onClick={() => {
                  setSettingsTab('general')
                  setSettingsOpen(true)
                }}
              >
                <Settings className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <>

          <section className="space-y-2">
            <div className="flex items-center gap-2 text-[var(--text-dim)]">
              <UploadCloud className="w-4 h-4" />
              <p className="text-sm font-medium">{t.uploadArea}</p>
          </div>
            <p className="text-[11px] text-[var(--text-muted)] -mt-0.5">{t.uploadHint}</p>

            {renderUploadCard(t.rawData, 'raw', t.uploadRaw, rawInputRef)}
            {renderUploadCard(t.seedData, 'seed', t.uploadSeed, seedInputRef)}
            {renderUploadCard(t.promptData, 'description', t.uploadPrompt, descInputRef)}
          </section>

          <section className="mt-6 space-y-2.5">
            <div className="flex items-center gap-2 text-[var(--text-dim)]">
              <Wand2 className="w-4 h-4" />
              <p className="text-sm font-medium">{t.runMode}</p>
            </div>
            <div className="rounded-xl border p-1 grid grid-cols-2 gap-1" style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}>
            <button
              type="button"
                onClick={() => setRunMode('manual')}
                className="h-9 rounded-lg text-sm transition-colors"
            style={{
                  background: runMode === 'manual' ? 'var(--de-cyan-glow)' : 'transparent',
                  color: runMode === 'manual' ? 'var(--text)' : 'var(--text-dim)',
                }}
              >
                {t.manual}
            </button>
              <button
                type="button"
                onClick={() => setRunMode('auto')}
                className="h-9 rounded-lg text-sm transition-colors"
                style={{
                  background: runMode === 'auto' ? 'var(--de-cyan-glow)' : 'transparent',
                  color: runMode === 'auto' ? 'var(--text)' : 'var(--text-dim)',
                }}
              >
                {t.auto}
              </button>
                </div>
            <button
              type="button"
              onClick={openStartModal}
              className="w-full h-10 rounded-xl text-sm font-medium flex items-center justify-center gap-2"
              style={{
                background: 'linear-gradient(135deg, var(--de-cyan), var(--de-teal))',
                color: themeMode === 'light' ? '#0f172a' : '#022c22',
              }}
            >
              <Play className="w-4 h-4" />
              {t.start}
            </button>
            <div className="relative w-full" onMouseLeave={() => setActionHover(null)}>
              <div className="grid grid-cols-3 gap-2">
                <button
                  type="button"
                  onClick={handleSaveSession}
                  onMouseEnter={() => setActionHover('save')}
                  className="h-9 rounded-xl border text-xs font-medium inline-flex items-center justify-center gap-0.5 px-1.5"
                  style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)', color: 'var(--text-dim)' }}
                >
                  <Save className="w-3.5 h-3.5 shrink-0" />
                  {t.saveSession}
                </button>
                <button
                  type="button"
                  onClick={openSessionFileDialog}
                  onMouseEnter={() => setActionHover('load')}
                  className="h-9 rounded-xl border text-xs font-medium inline-flex items-center justify-center gap-0.5 px-1.5"
                  style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)', color: 'var(--text-dim)' }}
                >
                  <Upload className="w-3.5 h-3.5 shrink-0" />
                  {t.loadSession}
                </button>
                <button
                  type="button"
                  onClick={() => setClearConfirmOpen(true)}
                  onMouseEnter={() => setActionHover('clear')}
                  className="h-9 rounded-xl border text-xs font-medium inline-flex items-center justify-center gap-0.5 px-1.5"
                  style={{ borderColor: 'var(--de-orange-dim)', background: 'var(--bg-panel)', color: 'var(--de-orange)' }}
                >
                  <Trash2 className="w-3.5 h-3.5 shrink-0" />
                  {t.clearWorkspace}
                </button>
                  </div>
              {actionHover && (
                <p
                  className="pointer-events-none absolute left-0 right-0 top-full z-30 mt-1 rounded-lg border px-2 py-1 text-[10px] leading-snug text-center shadow-sm"
                  role="note"
                  style={{
                    borderColor: actionHover === 'clear' ? 'var(--de-orange-dim)' : 'var(--border)',
                    background: 'var(--bg-card)',
                    color: actionHover === 'clear' ? 'var(--de-orange)' : 'var(--text-dim)',
                    wordBreak: 'break-word',
                  }}
                >
                  {actionHover === 'save' && t.saveTooltip}
                  {actionHover === 'load' && t.loadTooltip}
                  {actionHover === 'clear' && t.clearTooltip}
                </p>
              )}
          </div>
            <input
              ref={sessionInputRef}
              type="file"
              accept=".json"
              className="hidden"
              onChange={handleLoadSession}
            />
          </section>

          <div className="mt-auto pt-4">
                  <button
                    type="button"
              className="w-10 h-10 rounded-xl border flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text)]"
              style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
              title={t.settings}
              onClick={() => {
                setSettingsTab('general')
                setSettingsOpen(true)
              }}
            >
              <Settings className="w-4 h-4" />
            </button>
          </div>
            </>
          )}
        </aside>

        <main className="h-full p-5 md:p-6 overflow-auto">
          <EvolutionCanvas
            t={t}
            rows={rows}
            operatorPool={operatorPool}
            totalMetrics={totalMetrics}
            finished={finished}
            pipelineId={pipelineId}
            liveArtifacts={liveArtifacts}
            workflowBusy={workflowBusy}
            workflowExecutingStep={workflowExecutingStep}
            canRunFull={canRunFull}
            workflowState={workflowState}
            artifactHistoryCount={artifactHistoryCount}
            uploadPresence={{
              raw: Boolean(upload.raw || uploadPreview.raw.length),
              seed: Boolean(upload.seed || uploadPreview.seed.length),
              description: Boolean(upload.description || uploadPreview.description.length),
            }}
            onStepForward={stepForward}
            onAutoCompleteRound={autoCompleteCurrentRound}
            onSelectDagTab={selectDagTab}
            onRunFullData={runFullData}
            onRerunFromCurrentStep={rerunFromCurrentStep}
          />
        </main>
      </div>

      {previewModalOpen && (
        <div className="fixed inset-0 z-[58] flex items-center justify-center bg-black/45 p-4">
          <div
            className="w-[min(96vw,1400px)] h-[86vh] rounded-2xl border overflow-hidden flex flex-col"
            style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
          >
            <div className="px-4 py-3 border-b flex items-center justify-between gap-3" style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}>
              <div>
                <p className="text-sm font-semibold text-[var(--text)]">{t.previewArea}</p>
                <p className="text-[11px] text-[var(--text-muted)] mt-0.5">{t.previewModalHint}</p>
              </div>
              <button
                type="button"
                className="w-8 h-8 rounded-lg border inline-flex items-center justify-center text-[var(--text-muted)]"
                style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
                onClick={() => setPreviewModalOpen(false)}
                title={t.close}
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="px-4 pt-3">
              <div className="flex flex-wrap gap-2">
                {previewTabs.map((key) => (
                  <button
                    key={`preview-tab-${key}`}
                    type="button"
                    onClick={() => setPreviewModalTab(key)}
                    className="h-8 px-3 rounded-lg text-xs border"
                    style={{
                      borderColor: previewModalTab === key ? 'var(--de-cyan)' : 'var(--border)',
                      background: previewModalTab === key ? 'var(--de-cyan-glow)' : 'var(--bg-card)',
                      color: previewModalTab === key ? 'var(--text)' : 'var(--text-dim)',
                    }}
                  >
                    {key === 'raw' ? t.rawData : key === 'seed' ? t.seedData : t.promptData}
                  </button>
                ))}
              </div>
            </div>
            <div className="px-4 pb-4 pt-3 flex-1 min-h-0">
              <div className="h-full rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border)', background: 'var(--code-bg)' }}>
                <div className="px-3 py-2 border-b text-xs text-[var(--text-dim)]" style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}>
                  {upload[previewModalTab]?.name ?? t.noPreviewYet}
                </div>
                <div className="preview-lines-scroll h-full overflow-auto px-3 py-2">
                  {(previewDisplayLines.length > 0 ? previewDisplayLines : [t.noPreviewYet]).map((line, idx) => (
                    <p
                      key={`preview-modal-line-${previewModalTab}-${idx}`}
                      className="m-0 text-xs font-mono leading-relaxed break-words whitespace-pre-wrap text-[var(--text-dim)] mb-1.5 last:mb-0"
                    >
                      {renderLineWithJsonKeyHighlight(line, `preview-modal-${previewModalTab}-${idx}`)}
                    </p>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {settingsOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div
            className="w-full max-w-4xl h-[72vh] rounded-3xl border overflow-hidden grid"
            style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)', gridTemplateColumns: '230px minmax(0,1fr)' }}
          >
            <aside className="border-r p-4" style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}>
              <div className="flex items-center justify-between mb-3">
                <p className="text-sm font-semibold text-[var(--text)]">{t.settings}</p>
                <button
                  type="button"
                  className="w-7 h-7 rounded-lg border inline-flex items-center justify-center"
                  style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}
                  onClick={() => setSettingsOpen(false)}
                  title={t.close}
                >
                  <X className="w-4 h-4" />
                </button>
                </div>
              <div className="space-y-2">
                <button
                  type="button"
                  onClick={() => setSettingsTab('general')}
                  className="w-full text-left px-3 py-2 rounded-xl text-sm border"
                      style={{
                    borderColor: settingsTab === 'general' ? 'var(--de-cyan)' : 'var(--border)',
                    background: settingsTab === 'general' ? 'var(--de-cyan-glow)' : 'transparent',
                    color: settingsTab === 'general' ? 'var(--text)' : 'var(--text-dim)',
                  }}
                >
                  {t.generalSettings}
                </button>
                <button
                  type="button"
                  onClick={() => setSettingsTab('model')}
                  className="w-full text-left px-3 py-2 rounded-xl text-sm border"
                        style={{
                    borderColor: settingsTab === 'model' ? 'var(--de-cyan)' : 'var(--border)',
                    background: settingsTab === 'model' ? 'var(--de-cyan-glow)' : 'transparent',
                    color: settingsTab === 'model' ? 'var(--text)' : 'var(--text-dim)',
                        }}
                >
                  {t.modelSettings}
                </button>
                    </div>
            </aside>

            <section className="p-6 overflow-auto">
              {settingsTab === 'general' ? (
                <div className="space-y-6 max-w-2xl">
                  <div>
                    <p className="text-sm text-[var(--text-dim)] mb-2">{t.theme}</p>
                    <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                        onClick={() => setThemeMode('light')}
                        className="h-10 rounded-xl border text-sm"
                        style={{
                          borderColor: themeMode === 'light' ? 'var(--de-cyan)' : 'var(--border)',
                          color: themeMode === 'light' ? 'var(--text)' : 'var(--text-dim)',
                          background: themeMode === 'light' ? 'var(--de-cyan-glow)' : 'transparent',
                        }}
                      >
                        {t.light}
                  </button>
                      <button
                        type="button"
                        onClick={() => setThemeMode('dark')}
                        className="h-10 rounded-xl border text-sm"
                      style={{
                          borderColor: themeMode === 'dark' ? 'var(--de-cyan)' : 'var(--border)',
                          color: themeMode === 'dark' ? 'var(--text)' : 'var(--text-dim)',
                          background: themeMode === 'dark' ? 'var(--de-cyan-glow)' : 'transparent',
                        }}
                      >
                        {t.dark}
                      </button>
                </div>
                  </div>

                  <div>
                    <p className="text-sm text-[var(--text-dim)] mb-2 flex items-center gap-1.5">
                      <Languages className="w-3.5 h-3.5" />
                      {t.language}
                    </p>
                    <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                        onClick={() => setLanguage('zh')}
                        className="h-10 rounded-xl border text-sm"
                        style={{
                          borderColor: language === 'zh' ? 'var(--de-cyan)' : 'var(--border)',
                          color: language === 'zh' ? 'var(--text)' : 'var(--text-dim)',
                          background: language === 'zh' ? 'var(--de-cyan-glow)' : 'transparent',
                        }}
                      >
                        {t.chinese}
                      </button>
                      <button
                        type="button"
                        onClick={() => setLanguage('en')}
                        className="h-10 rounded-xl border text-sm"
                        style={{
                          borderColor: language === 'en' ? 'var(--de-cyan)' : 'var(--border)',
                          color: language === 'en' ? 'var(--text)' : 'var(--text-dim)',
                          background: language === 'en' ? 'var(--de-cyan-glow)' : 'transparent',
                        }}
                      >
                        {t.english}
                      </button>
                </div>
              </div>
                </div>
              ) : (
                <div className="space-y-4 max-w-2xl">
                  <label className="block">
                    <span className="text-sm text-[var(--text-dim)]">{t.providerMode}</span>
                    <select
                      value={providerMode}
                      onChange={(e) => setProviderMode(e.target.value as ProviderMode)}
                      className="mt-1 w-full h-10 rounded-xl border px-3 outline-none"
                      style={{ borderColor: 'var(--border)', background: 'var(--bg-card)', color: 'var(--text)' }}
                    >
                      <option value="openai-official">{t.openaiOfficial}</option>
                      <option value="third-party">{t.thirdParty}</option>
                    </select>
                  </label>
                  <label className="block">
                    <span className="text-sm text-[var(--text-dim)]">{t.modelOptions}</span>
                    <select
                      value={llmConfig.model}
                      onChange={(e) => setLlmConfig({ model: e.target.value })}
                      className="mt-1 w-full h-10 rounded-xl border px-3 outline-none"
                      style={{ borderColor: 'var(--border)', background: 'var(--bg-card)', color: 'var(--text)' }}
                    >
                      {!(MODEL_OPTIONS as readonly string[]).includes(llmConfig.model) && (
                        <option value={llmConfig.model}>{llmConfig.model}</option>
                      )}
                      {modelOptions.map((model) => (
                        <option key={model} value={model}>
                          {model}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block">
                    <span className="text-sm text-[var(--text-dim)]">{t.apiKey}</span>
                    <input
                      type="password"
                      value={apiKeyDraft}
                      onChange={(e) => setApiKeyDraft(e.target.value)}
                      className="mt-1 w-full h-10 rounded-xl border px-3 outline-none"
                      style={{ borderColor: 'var(--border)', background: 'var(--bg-card)', color: 'var(--text)' }}
                      placeholder="sk-..."
                    />
                    {apiKeyDraft && <p className="text-[11px] text-[var(--text-muted)] mt-1">{t.apiKeySaved}</p>}
                    {!apiKeyDraft && serverKeyHint?.configured && (
                      <p className="text-[11px] text-[var(--text-muted)] mt-1">
                        {t.apiKeyServerHint}
                        {serverKeyHint.masked ? (
                          <span className="font-mono"> {serverKeyHint.masked}</span>
                        ) : null}
                      </p>
                    )}
                  </label>
                  {providerMode === 'third-party' && (
                    <label className="block">
                      <span className="text-sm text-[var(--text-dim)]">{t.baseUrl}</span>
                      <input
                        value={baseUrlDraft}
                        onChange={(e) => setBaseUrlDraft(e.target.value)}
                        className="mt-1 w-full h-10 rounded-xl border px-3 outline-none"
                        style={{ borderColor: 'var(--border)', background: 'var(--bg-card)', color: 'var(--text)' }}
                        placeholder="https://api.example.com/v1"
                      />
                    </label>
                  )}
                  <div className="grid grid-cols-2 gap-4">
                    <label className="block">
                      <span className="text-sm text-[var(--text-dim)]">{t.temperature}</span>
                      <div className="mt-2 grid grid-cols-[1fr_76px] gap-2 items-center">
                        <input
                          type="range"
                          min={0}
                          max={2}
                          step={0.1}
                          value={llmConfig.temperature}
                          onChange={(e) => setLlmConfig({ temperature: Number(e.target.value) || 0 })}
                          className="w-full accent-[var(--de-cyan)]"
                        />
                        <input
                          type="number"
                          min={0}
                          max={2}
                          step={0.1}
                          value={llmConfig.temperature}
                          onChange={(e) => setLlmConfig({ temperature: Number(e.target.value) || 0 })}
                          className="h-8 rounded-lg border px-2 text-sm outline-none"
                          style={{ borderColor: 'var(--border)', background: 'var(--bg-card)', color: 'var(--text)' }}
                      />
          </div>
                    </label>
                    <label className="block">
                      <span className="text-sm text-[var(--text-dim)]">{t.maxTokens}</span>
                      <div className="mt-2 grid grid-cols-[1fr_92px] gap-2 items-center">
                        <input
                          type="range"
                          min={256}
                          max={8192}
                          step={256}
                          value={llmConfig.maxTokens}
                          onChange={(e) => setLlmConfig({ maxTokens: Number(e.target.value) || 256 })}
                          className="w-full accent-[var(--de-cyan)]"
                        />
                        <input
                          type="number"
                          min={256}
                          max={8192}
                          step={256}
                          value={llmConfig.maxTokens}
                          onChange={(e) => setLlmConfig({ maxTokens: Number(e.target.value) || 256 })}
                          className="h-8 rounded-lg border px-2 text-sm outline-none"
                          style={{ borderColor: 'var(--border)', background: 'var(--bg-card)', color: 'var(--text)' }}
                      />
        </div>
                    </label>
                </div>
                  <div className="pt-2">
                    <button
                      type="button"
                      onClick={() => void handleSaveLlmConfig()}
                      disabled={configSaving}
                      className="h-10 px-4 rounded-xl text-sm font-medium border inline-flex items-center justify-center gap-2 disabled:opacity-60"
                      style={{ borderColor: 'var(--border)', background: 'var(--bg-card)', color: 'var(--text)' }}
                    >
                      <Save className="w-4 h-4 shrink-0" />
                      {configSaving ? t.saveLlmSaving : t.saveLlmToProject}
                  </button>
                </div>
              </div>
            )}
            </section>
          </div>
        </div>
      )}

      {startModalOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/45 p-4">
          <div
            className="w-full max-w-md max-h-[90vh] overflow-y-auto rounded-2xl border p-5"
            style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
          >
            <p className="text-base font-semibold text-[var(--text)]">{t.startSessionTitle}</p>
            <p className="text-xs text-[var(--text-muted)] mt-1 leading-relaxed">{t.manifestFormHint}</p>
            <div className="mt-4 space-y-3">
              <label className="block">
                <span className="text-xs text-[var(--text-dim)]">{t.pipelineIdLabel}</span>
                <input
                  type="text"
                  value={pipelineIdInput}
                  onChange={(e) => setPipelineIdInput(e.target.value)}
                  placeholder={t.pipelineIdPlaceholder}
                  className="mt-1 w-full h-9 rounded-lg border px-2.5 text-sm outline-none"
                  style={{ borderColor: 'var(--border)', background: 'var(--bg-card)', color: 'var(--text)' }}
                  autoComplete="off"
                />
              </label>
              <label className="block">
                <span className="text-xs text-[var(--text-dim)]">
                  {t.metaDomain}（{t.optionalHint}）
                </span>
                <input
                  type="text"
                  value={metaDomainInput}
                  onChange={(e) => setMetaDomainInput(e.target.value)}
                  className="mt-1 w-full h-9 rounded-lg border px-2.5 text-sm outline-none"
                  style={{ borderColor: 'var(--border)', background: 'var(--bg-card)', color: 'var(--text)' }}
                />
              </label>
              <label className="block">
                <span className="text-xs text-[var(--text-dim)]">
                  {t.metaTaskType}（{t.optionalHint}）
                </span>
                <input
                  type="text"
                  value={metaTaskTypeInput}
                  onChange={(e) => setMetaTaskTypeInput(e.target.value)}
                  className="mt-1 w-full h-9 rounded-lg border px-2.5 text-sm outline-none"
                  style={{ borderColor: 'var(--border)', background: 'var(--bg-card)', color: 'var(--text)' }}
                />
              </label>
              <label className="block">
                <span className="text-xs text-[var(--text-dim)]">
                  {t.metaLanguage}（{t.optionalHint}）
                </span>
                <input
                  type="text"
                  value={metaLanguageInput}
                  onChange={(e) => setMetaLanguageInput(e.target.value)}
                  className="mt-1 w-full h-9 rounded-lg border px-2.5 text-sm outline-none"
                  style={{ borderColor: 'var(--border)', background: 'var(--bg-card)', color: 'var(--text)' }}
                />
              </label>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                className="h-9 px-3 rounded-lg border text-sm"
                style={{ borderColor: 'var(--border)', color: 'var(--text-dim)' }}
                disabled={startSubmitting}
                onClick={() => setStartModalOpen(false)}
              >
                {t.clearCancel}
              </button>
              <button
                type="button"
                className="h-9 px-3 rounded-lg text-sm font-medium disabled:opacity-50"
                style={{ background: 'linear-gradient(135deg, var(--de-cyan), var(--de-teal))', color: themeMode === 'light' ? '#0f172a' : '#022c22' }}
                disabled={startSubmitting}
                onClick={() => void submitStartSession()}
              >
                {startSubmitting ? t.startSessionSaving : t.confirmStartRun}
              </button>
            </div>
          </div>
        </div>
      )}

      {clearConfirmOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/45 p-4">
          <div className="w-full max-w-md rounded-2xl border p-5" style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}>
            <p className="text-base font-semibold text-[var(--text)]">{t.clearWorkspace}</p>
            <p className="text-sm text-[var(--text-dim)] mt-2 leading-6">{t.clearConfirm}</p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                className="h-9 px-3 rounded-lg border text-sm"
                style={{ borderColor: 'var(--border)', color: 'var(--text-dim)' }}
                onClick={() => setClearConfirmOpen(false)}
              >
                {t.clearCancel}
              </button>
              <button
                type="button"
                className="h-9 px-3 rounded-lg text-sm font-medium"
                style={{ background: 'var(--de-orange)', color: 'white' }}
                onClick={() => {
                  setClearConfirmOpen(false)
                  handleClearWorkspace()
                }}
              >
                {t.clearConfirmAction}
              </button>
          </div>
          </div>
        </div>
      )}
    </div>
  )
}
