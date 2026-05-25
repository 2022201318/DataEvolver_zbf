/**
 * 从 artifact_history 轮次快照构建画布行（DAG / 实例化 / 评估），与 live API 数据隔离。
 */
import type { WorkflowRoundSnapshot } from '../api/client'
import type { DagResult, JudgeResult, UnderstandingResult } from '../types'
import type {
  CanvasEvolutionRow,
  CanvasInstantiationCard,
  CanvasMetric,
  IterationHistoryArtifact,
  LiveArtifactsForCanvas,
  OrchestrationArchiveArtifact,
  RoundHistoryArtifact,
} from './canvasRowTypes'
import { buildOrchestrationDagTabs } from './buildOrchestrationDagTabs'

function toNumber(v: unknown): number | undefined {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string' && v.trim()) {
    const n = Number(v)
    if (Number.isFinite(n)) return n
  }
  return undefined
}

function toBool(v: unknown): boolean | undefined {
  if (typeof v === 'boolean') return v
  if (typeof v === 'string') {
    const s = v.trim().toLowerCase()
    if (s === 'true') return true
    if (s === 'false') return false
  }
  return undefined
}

function normalizeIssueText(v: unknown): string {
  if (typeof v === 'string') return v
  try {
    return JSON.stringify(v)
  } catch {
    return String(v)
  }
}

function scoreFromSampleMetrics(metrics: unknown): number | undefined {
  if (!metrics || typeof metrics !== 'object') return undefined
  const vals = Object.values(metrics as Record<string, unknown>)
    .map((v) => toNumber(v))
    .filter((v): v is number => typeof v === 'number')
  if (!vals.length) return undefined
  const avg = vals.reduce((a, b) => a + b, 0) / vals.length
  return Math.max(0, Math.min(100, Math.round(avg * 100)))
}

export function parseDagFromApi(dag: unknown): DagResult | null {
  if (!dag || typeof dag !== 'object') return null
  const d = dag as Record<string, unknown>
  const nodesRaw = d.nodes
  const edgesRaw = d.edges
  if (!Array.isArray(nodesRaw) || !Array.isArray(edgesRaw)) return null

  const nodes = nodesRaw.map((n: unknown, i: number) => {
    const x = (n && typeof n === 'object' ? n : {}) as Record<string, unknown>
    return {
      node_id: String(x.node_id ?? x.id ?? `node_${i}`),
      node_name: String(x.node_name ?? x.name ?? 'operator'),
      description: x.description != null ? String(x.description) : undefined,
      input_keys: Array.isArray(x.input_keys) ? x.input_keys.map(String) : [],
      output_keys: Array.isArray(x.output_keys) ? x.output_keys.map(String) : [],
    }
  })

  const edges = edgesRaw.map((e: unknown) => {
    const x = (e && typeof e === 'object' ? e : {}) as Record<string, unknown>
    return {
      from_node: String(x.from_node ?? x.source ?? ''),
      to_node: String(x.to_node ?? x.target ?? ''),
      data_flow:
        x.data_flow && typeof x.data_flow === 'object'
          ? (x.data_flow as { from_outputs?: string[]; to_inputs?: string[] })
          : undefined,
    }
  })

  const orderRaw = d.execution_order
  const execution_order = Array.isArray(orderRaw) ? orderRaw.map(String) : nodes.map((n) => n.node_id)

  return { nodes, edges, execution_order, total_nodes: nodes.length, total_edges: edges.length }
}

function judgeFromQuality(q: Record<string, unknown> | null): JudgeResult | null {
  if (!q) return null
  const insights = q.critical_insights
  return {
    has_differences: Boolean(q.has_differences),
    overall_assessment: q.overall_assessment != null ? String(q.overall_assessment) : '',
    critical_insights: Array.isArray(insights) ? insights.map(String) : [],
    implicit_quality_requirements:
      q.implicit_quality_requirements && typeof q.implicit_quality_requirements === 'object'
        ? (q.implicit_quality_requirements as Record<string, unknown>)
        : undefined,
  }
}

function judgeFromTrial(trial: Record<string, unknown> | null): JudgeResult | null {
  if (!trial || typeof trial !== 'object') return null
  const pe = trial.llm_pilot_evaluation
  if (!pe || typeof pe !== 'object') return null
  const jr = (pe as Record<string, unknown>).judge_result
  if (!jr || typeof jr !== 'object') return null
  const j = jr as Record<string, unknown>
  const insights = j.critical_insights
  return {
    has_differences: Boolean(j.has_differences),
    overall_assessment: j.overall_assessment != null ? String(j.overall_assessment) : '',
    critical_insights: Array.isArray(insights) ? insights.map(String) : [],
    implicit_quality_requirements:
      j.implicit_quality_requirements && typeof j.implicit_quality_requirements === 'object'
        ? (j.implicit_quality_requirements as Record<string, unknown>)
        : undefined,
  }
}

export function extractOrchestrationValidation(
  orchestration: Record<string, unknown> | null | undefined
): { is_valid: boolean; validation_issues: string[] } | null {
  if (!orchestration) return null
  const validationIssues: string[] = []
  const cs = orchestration.constrained_search
  if (cs && typeof cs === 'object') {
    const vr = (cs as Record<string, unknown>).validation_result
    if (vr && typeof vr === 'object') {
      const issues = (vr as Record<string, unknown>).validation_issues
      if (Array.isArray(issues)) validationIssues.push(...issues.map(normalizeIssueText))
    }
  }
  const dagVal = orchestration.dag_validation as Record<string, unknown> | undefined
  const isValid = dagVal?.is_valid !== false && (toBool(dagVal?.is_valid) ?? validationIssues.length === 0)
  return { is_valid: isValid !== false, validation_issues: validationIssues }
}

export function buildInstantiationCardsFromSteps(
  stepsRaw: unknown,
  instTokens: number,
  idPrefix: string
): CanvasInstantiationCard[] {
  if (!Array.isArray(stepsRaw)) return []
  const steps = stepsRaw.filter((s) => s && typeof s === 'object') as Record<string, unknown>[]
  return steps.map((step, i) => {
    const op = String(step.operator_name ?? step.operator ?? `step_${i + 1}`)
    return {
      id: `${idPrefix}-step-${i}-${op}`,
      name: op,
      summary: String(step.intermediate_summary ?? step.description ?? ''),
      code: String(step.code ?? ''),
      metrics: {
        sec: 0,
        tokens: Math.round(instTokens / Math.max(1, steps.length)),
      },
    }
  })
}

export function buildRowUiFromArtifacts(args: {
  understanding?: Record<string, unknown> | null
  orchestration?: Record<string, unknown> | null
  quality_check?: Record<string, unknown> | null
  trial?: Record<string, unknown> | null
  experience?: Record<string, unknown> | null
}): LiveArtifactsForCanvas {
  const understanding = (args.understanding ?? null) as UnderstandingResult | null
  const orchestration = args.orchestration ?? null
  const dag = parseDagFromApi(orchestration?.dag)
  const orchestrationValidation = extractOrchestrationValidation(orchestration)
  const judge = judgeFromQuality(args.quality_check ?? null) ?? judgeFromTrial(args.trial ?? null)
  const expText =
    args.experience && args.experience.experience_text != null
      ? String(args.experience.experience_text)
      : ''
  return {
    understanding,
    dag,
    orchestrationValidation,
    judge,
    experienceBullets: expText ? [expText] : [],
  }
}

export function buildFrozenRoundRow(
  roundId: number,
  roundArtifact: RoundHistoryArtifact | undefined,
  snap: WorkflowRoundSnapshot,
  opts: {
    isZh: boolean
    orchestrationArchives: OrchestrationArchiveArtifact[]
    iterations: IterationHistoryArtifact[]
    metrics?: Partial<Record<'understanding' | 'orchestration' | 'instantiation' | 'trial' | 'quality' | 'experience', CanvasMetric>>
  }
): CanvasEvolutionRow {
  const summary = snap.summary && typeof snap.summary === 'object' ? snap.summary : {}
  const uDone = Boolean((summary as Record<string, unknown>).understanding_done)

  const tabBundle = buildOrchestrationDagTabs({
    roundId,
    isZh: opts.isZh,
    orchestrationArchives: opts.orchestrationArchives,
    liveOrchestration: roundArtifact?.orchestration ?? null,
    tokens: null,
  })
  const dagTabs = tabBundle.dagTabs
  const preferredActiveDagTabId = tabBundle.activeDagTabId

  const instStepsRaw = roundArtifact?.instantiation?.steps
  const instStepCount = Array.isArray(instStepsRaw)
    ? instStepsRaw.length
    : Math.max(0, Math.round(toNumber((summary as Record<string, unknown>).instantiation_steps) ?? 0))

  const instantiationCards =
    Array.isArray(instStepsRaw) && instStepsRaw.length > 0
      ? buildInstantiationCardsFromSteps(instStepsRaw, 0, `hist-r${roundId}`)
      : Array.from({ length: instStepCount }).map((_, i) => ({
          id: `hist-r${roundId}-inst-${i + 1}`,
          name: opts.isZh ? `历史实例化步骤 ${i + 1}` : `Historical Instantiation ${i + 1}`,
          summary: opts.isZh ? '由轮次快照恢复' : 'Recovered from round snapshot',
          code: '',
          metrics: { sec: 0, tokens: 0 },
        }))

  const qualityData = roundArtifact?.quality_check
  const trialData = roundArtifact?.trial
  const score =
    toNumber(qualityData?.pilot_overall_score) ??
    scoreFromSampleMetrics(qualityData?.sample_metrics_0_1) ??
    toNumber((trialData?.llm_pilot_evaluation as Record<string, unknown> | undefined)?.overall_score) ??
    toNumber((summary as Record<string, unknown>).sample_score)

  const expFromRound = roundArtifact?.experience?.experience_text
  const exp = typeof expFromRound === 'string' ? expFromRound : (summary as Record<string, unknown>).experience_text
  const expText = typeof exp === 'string' ? exp : ''
  const qualityPassedSnap = toBool(roundArtifact?.quality_passed ?? snap.quality_passed)
  const expSource = roundArtifact?.experience?.source
  const experienceMeta = expText
    ? {
        llm_used: false,
        source_kind: typeof expSource === 'string' ? expSource : 'rule_aggregation',
        detail: opts.isZh
          ? '经验由质检/试运行/Pilot 结果规则聚合生成，非 LLM 逐步调用'
          : 'Experience is rule-aggregated from QC/trial/Pilot, not LLM step-by-step',
      }
    : undefined
  const rowUi = buildRowUiFromArtifacts({
    understanding: roundArtifact?.understanding,
    orchestration: roundArtifact?.orchestration,
    quality_check: roundArtifact?.quality_check,
    trial: roundArtifact?.trial,
    experience: roundArtifact?.experience,
  })

  const m = opts.metrics ?? {}
  return {
    id: roundId,
    understandingDone: uDone,
    understandingMetrics: uDone ? m.understanding ?? { sec: 0, tokens: 0 } : undefined,
    dagTabs,
    activeDagTabId: preferredActiveDagTabId ?? (dagTabs.length ? dagTabs[dagTabs.length - 1].id : undefined),
    instantiationCards,
    sampleScore: typeof score === 'number' ? Math.max(0, Math.min(100, Math.round(score))) : undefined,
    sampleMetrics: typeof score === 'number' ? m.trial ?? m.quality ?? { sec: 0, tokens: 0 } : undefined,
    experience: expText || undefined,
    experienceMetrics: expText ? m.experience ?? { sec: 0, tokens: 0 } : undefined,
    experienceMeta,
    needNext: qualityPassedSnap === false,
    completed: true,
    rowUi,
  }
}
