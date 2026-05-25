/**
 * 将 workflow state + 各阶段 API 产物合并为画布用 EvolutionRow（单管线单行，与后端 STEP_ORDER 对齐）。
 */
import type { WorkflowRoundSnapshot, WorkflowStateResponse, WorkflowTokensResponse } from '../api/client'
import type { DagResult, JudgeResult, UnderstandingResult } from '../types'
import type {
  CanvasDagTab,
  CanvasEvolutionRow,
  CanvasInstantiationCard,
  IterationHistoryArtifact,
  LiveArtifactsForCanvas,
  OrchestrationArchiveArtifact,
  RoundHistoryArtifact,
} from './canvasRowTypes'
import { buildFrozenRoundRow, buildRowUiFromArtifacts } from './buildRoundRowHelpers'
import { buildOrchestrationDagTabs } from './buildOrchestrationDagTabs'

export type {
  CanvasDagTab,
  CanvasEvolutionRow,
  CanvasInstantiationCard,
  CanvasMetric,
  IterationHistoryArtifact,
  LiveArtifactsForCanvas,
  OrchestrationArchiveArtifact,
  RoundHistoryArtifact,
} from './canvasRowTypes'

function parseDagFromApi(dag: unknown): DagResult | null {
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

function tokensForSteps(tokens: WorkflowTokensResponse | null, keys: string[]): number {
  const by = tokens?.by_workflow_step
  if (!by) return 0
  return keys.reduce((sum, k) => {
    const cur = by[k]
    if (!cur) return sum
    const t = toNumber(cur.total_tokens)
    if (typeof t === 'number') return sum + t
    return sum + (toNumber(cur.input_tokens) ?? 0) + (toNumber(cur.output_tokens) ?? 0)
  }, 0)
}

export function buildEvolutionRowsFromPipeline(
  wf: WorkflowStateResponse,
  opts: {
    understanding: UnderstandingResult | null
    dagResponse: Record<string, unknown> | null
    instantiationSteps: Record<string, unknown>[] | null
    instantiationMeta?: Record<string, unknown> | null
    quality: Record<string, unknown> | null
    trial: Record<string, unknown> | null
    experience: Record<string, unknown> | null
    tokens: WorkflowTokensResponse | null
    history: { round_snapshots?: WorkflowRoundSnapshot[]; entries?: Array<Record<string, unknown>> } | null
    historyArtifacts?: {
      rounds: RoundHistoryArtifact[]
      iterations: IterationHistoryArtifact[]
      orchestrationArchives: OrchestrationArchiveArtifact[]
    } | null
    lastAdvanceMessage: string
    language: 'zh' | 'en'
  }
): {
  rows: CanvasEvolutionRow[]
  finished: boolean
  canRunFullByJudge: boolean
  live: LiveArtifactsForCanvas
} {
  const isZh = opts.language === 'zh'
  const completed = new Set(wf.state.steps_completed)
  const st = wf.state
  const artifacts = wf.artifacts
  const compatibilityMode = !Array.isArray(st.step_order) || st.step_order.length <= 1
  const roundId = typeof st.round === 'number' && st.round > 0 ? st.round : 1

  const dagParsed = parseDagFromApi(opts.dagResponse?.dag)
  const dagVal = opts.dagResponse?.dag_validation as { is_valid?: boolean; issue_count?: number } | undefined

  const validationIssues: string[] = []
  const cs = opts.dagResponse?.constrained_search
  if (cs && typeof cs === 'object') {
    const vr = (cs as Record<string, unknown>).validation_result
    if (vr && typeof vr === 'object') {
      const issues = (vr as Record<string, unknown>).validation_issues
      if (Array.isArray(issues)) validationIssues.push(...issues.map(normalizeIssueText))
    }
  }

  const orchestrationDone = completed.has('orchestration') || artifacts.orchestration
  const hasOrchestrationValidation =
    orchestrationDone && (Boolean(dagVal) || validationIssues.length > 0)
  const orchestrationValidation =
    hasOrchestrationValidation
      ? {
          is_valid: dagVal?.is_valid !== false,
          validation_issues: validationIssues,
        }
      : null

  const judgeRaw = judgeFromQuality(opts.quality) ?? judgeFromTrial(opts.trial)
  const judge: JudgeResult | null = (() => {
    const base =
      judgeRaw ??
      ({
        has_differences: false,
        overall_assessment: '',
        critical_insights: [],
      } as JudgeResult)
    return base
  })()
  const expText =
    opts.experience && opts.experience.experience_text != null ? String(opts.experience.experience_text) : ''
  const experienceBullets = expText ? [expText] : []

  const tabBundle = buildOrchestrationDagTabs({
    roundId,
    isZh,
    orchestrationArchives: opts.historyArtifacts?.orchestrationArchives ?? [],
    liveOrchestration: orchestrationDone && opts.dagResponse ? opts.dagResponse : null,
    liveOrchestrationRevision:
      typeof st.orchestration_revision === 'number' ? st.orchestration_revision : undefined,
    tokens: opts.tokens,
  })
  const dagTabs: CanvasDagTab[] = [...tabBundle.dagTabs]
  let tabId = dagTabs.length
  const evoTokens = tokensForSteps(opts.tokens, ['operator_evolution'])
  const skipEvoByMessage =
    opts.lastAdvanceMessage.includes('跳过算子进化') ||
    opts.lastAdvanceMessage.toLowerCase().includes('skip') ||
    opts.lastAdvanceMessage.toLowerCase().includes('skipped')
  const shouldShowEvolutionTab = completed.has('operator_evolution') && !skipEvoByMessage && evoTokens > 0
  if (shouldShowEvolutionTab) {
    tabId++
    dagTabs.push({
      id: tabId,
      title: isZh ? '算子进化' : 'Operator evolution',
      status: 'passed',
      summary: opts.lastAdvanceMessage.includes('operator_evolution')
        ? opts.lastAdvanceMessage
        : isZh
          ? '算子级自进化步骤已完成（可能跳过）'
          : 'Operator evolution step finished (may skip)',
      metrics: { sec: 0, tokens: evoTokens },
      nodes: dagParsed?.execution_order ?? [],
      dag: dagParsed ?? undefined,
    })
  }

  const instCards: CanvasInstantiationCard[] = []
  const instTokens = tokensForSteps(opts.tokens, ['instantiation'])
  const instMetaRaw = opts.instantiationMeta && typeof opts.instantiationMeta === 'object' ? opts.instantiationMeta : null
  const llmStepSet = new Set(
    Array.isArray(instMetaRaw?.llm_prompt_generated_steps)
      ? instMetaRaw!.llm_prompt_generated_steps.map(String)
      : []
  )
  const instSkipped =
    opts.lastAdvanceMessage.includes('instantiation: skipped') ||
    opts.lastAdvanceMessage.includes('复用已有实例化')
  const instantiationMeta =
    instMetaRaw || instSkipped || completed.has('instantiation')
      ? {
          reused: instSkipped,
          llm_codegen: llmStepSet.size > 0,
          llm_steps: llmStepSet.size ? [...llmStepSet] : undefined,
          note: typeof instMetaRaw?.note === 'string' ? instMetaRaw.note : undefined,
          source: typeof instMetaRaw?.source === 'string' ? instMetaRaw.source : undefined,
        }
      : undefined
  if (opts.instantiationSteps?.length) {
    opts.instantiationSteps.forEach((s, i) => {
      const op = String(s.operator_name ?? s.operator ?? `step_${i + 1}`)
      instCards.push({
        id: `step-${i}-${op}`,
        name: op,
        summary: String(s.intermediate_summary ?? s.description ?? ''),
        code: String(s.code ?? ''),
        metrics: { sec: 0, tokens: Math.round(instTokens / Math.max(1, opts.instantiationSteps?.length ?? 1)) },
        llmGenerated: llmStepSet.has(op),
      })
    })
  }

  let sampleScore: number | undefined
  const qualityScore = toNumber(opts.quality?.pilot_overall_score)
  const qualityDone = completed.has('quality_check') || artifacts.quality_check
  const trialDone = completed.has('trial_run') || artifacts.trial_run
  // 注意：artifacts.experience 不是按轮次隔离的，直接用会把上一轮经验误显示到当前轮。
  // 仅在兼容旧后端（无 workflow step_order）时回退到 artifacts。
  const experienceDone = completed.has('experience') || (compatibilityMode && artifacts.experience)
  const expSource = opts.experience?.source
  const experienceMeta =
    experienceDone && opts.experience
      ? {
          llm_used: false,
          source_kind: typeof expSource === 'string' ? expSource : 'rule_aggregation',
          detail:
            typeof opts.experience.detail === 'string'
              ? opts.experience.detail
              : opts.language === 'zh'
                ? '经验由质检/试运行/Pilot 结果规则聚合生成，非 LLM 逐步调用'
                : 'Experience is rule-aggregated from QC/trial/Pilot, not LLM step-by-step',
        }
      : undefined

  if (qualityDone && typeof qualityScore === 'number') {
    sampleScore = Math.max(0, Math.min(100, Math.round(qualityScore)))
  } else if (qualityDone) {
    sampleScore = scoreFromSampleMetrics(opts.quality?.sample_metrics_0_1)
  } else {
    const trialPilot = opts.trial?.llm_pilot_evaluation as Record<string, unknown> | undefined
    const trialScore = toNumber(trialPilot?.overall_score)
    if (trialDone && typeof trialScore === 'number') {
      sampleScore = Math.max(0, Math.min(100, Math.round(trialScore)))
    }
  }

  const understandingTokens = tokensForSteps(opts.tokens, ['understanding'])
  const trialTokens = tokensForSteps(opts.tokens, ['trial_run'])
  const qualityTokens = tokensForSteps(opts.tokens, ['quality_check'])
  const experienceTokens = tokensForSteps(opts.tokens, ['experience'])
  const readyForFullRun = Boolean(st.ready_for_full_run)
  const qualityHasDiff = toBool(opts.quality?.has_differences)
  const trialPilot = opts.trial?.llm_pilot_evaluation as Record<string, unknown> | undefined
  const trialRec = String(trialPilot?.recommendation ?? '').trim().toLowerCase()
  const trialJudge =
    trialPilot?.judge_result && typeof trialPilot.judge_result === 'object'
      ? (trialPilot.judge_result as Record<string, unknown>)
      : null
  const trialHasDiff = toBool(trialJudge?.has_differences)
  const judgeHasDiff = typeof judge?.has_differences === 'boolean' ? judge.has_differences : undefined
  const needPipelineEvolution =
    judgeHasDiff === true ||
    (judgeHasDiff === undefined &&
      (qualityHasDiff === true || trialHasDiff === true || trialRec === 'evolve_pipeline' || trialRec === 'iterate_pipeline'))
  const noNeedPipelineEvolution =
    judgeHasDiff === false ||
    (judgeHasDiff === undefined &&
      (qualityHasDiff === false ||
        trialHasDiff === false ||
        trialRec === 'keep_pipeline' ||
        trialRec === 'run_full' ||
        trialRec === 'apply_full'))
  const canRunFullByJudge = readyForFullRun || st.is_complete || (trialDone && noNeedPipelineEvolution && !needPipelineEvolution)

  let preferredActiveDagTabId = tabBundle.activeDagTabId
  const row: CanvasEvolutionRow = {
    id: roundId,
    understandingDone: completed.has('understanding') || artifacts.understanding,
    understandingMetrics:
      completed.has('understanding') || artifacts.understanding
        ? { sec: 0, tokens: understandingTokens }
        : undefined,
    dagTabs,
    activeDagTabId: preferredActiveDagTabId ?? (dagTabs.length ? dagTabs[dagTabs.length - 1].id : undefined),
    instantiationCards: instCards,
    instantiationMeta,
    sampleScore,
    sampleMetrics:
      sampleScore !== undefined ? { sec: 0, tokens: trialTokens + qualityTokens } : trialDone ? { sec: 0, tokens: trialTokens } : undefined,
    // 经验卡片仅在“本轮 experience 步骤完成”后展示，避免把上一轮经验误显示到当前轮。
    experience: experienceDone ? expText || undefined : undefined,
    experienceMetrics: experienceDone ? { sec: 0, tokens: experienceTokens } : undefined,
    experienceMeta,
    needNext: !canRunFullByJudge && trialDone && needPipelineEvolution,
    completed: canRunFullByJudge,
    rowUi: buildRowUiFromArtifacts({
      understanding: opts.understanding as Record<string, unknown> | null,
      orchestration: opts.dagResponse,
      quality_check: opts.quality,
      trial: opts.trial,
      experience: opts.experience,
    }),
  }

  const historyRows: CanvasEvolutionRow[] = []
  const snapsPrimary = Array.isArray(opts.history?.round_snapshots) ? opts.history?.round_snapshots ?? [] : []
  const snapsFallback =
    !snapsPrimary.length && Array.isArray(opts.history?.entries)
      ? opts.history!.entries
          .filter((e) => e && typeof e === 'object' && String((e as Record<string, unknown>).kind ?? '') === 'round_snapshot')
          .map((e) => e as unknown as WorkflowRoundSnapshot)
      : []
  const snaps = snapsPrimary.length ? snapsPrimary : snapsFallback
  const roundArtifactByRound = new Map<number, RoundHistoryArtifact>()
  ;(opts.historyArtifacts?.rounds ?? []).forEach((a) => {
    const k = Math.max(1, Math.round(a.round))
    if (!roundArtifactByRound.has(k)) roundArtifactByRound.set(k, a)
  })
  const archives = opts.historyArtifacts?.orchestrationArchives ?? []
  const iterations = opts.historyArtifacts?.iterations ?? []
  snaps.forEach((s) => {
    const round = toNumber(s.round)
    if (typeof round !== 'number' || !Number.isFinite(round) || round < 1) return
    const rid = Math.max(1, Math.round(round))
    // 历史只显示“当前轮之前”的轮次，避免 round=1 时误出现多行。
    if (rid >= roundId) return
    const roundArtifact = roundArtifactByRound.get(rid)
    historyRows.push(
      buildFrozenRoundRow(rid, roundArtifact, s, {
        isZh,
        orchestrationArchives: archives,
        iterations,
      })
    )
  })

  const byRound = new Map<number, CanvasEvolutionRow>()
  historyRows.forEach((r) => byRound.set(r.id, r))
  byRound.set(row.id, row)
  const rows = [...byRound.values()].sort((a, b) => a.id - b.id)

  const live: LiveArtifactsForCanvas = {
    understanding: opts.understanding,
    dag: dagParsed,
    orchestrationValidation,
    judge,
    experienceBullets,
  }

  return {
    rows,
    finished: canRunFullByJudge,
    canRunFullByJudge,
    live,
  }
}
