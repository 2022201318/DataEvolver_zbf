/**
 * 将 workflow state + 各阶段 API 产物合并为画布用 EvolutionRow（单管线单行，与后端 STEP_ORDER 对齐）。
 */
import type { WorkflowRoundSnapshot, WorkflowStateResponse, WorkflowTokensResponse } from '../api/client'
import type { DagResult, JudgeResult, UnderstandingResult } from '../types'


export type CanvasMetric = { sec: number; tokens: number }

export type CanvasDagTab = {
  id: number
  title: string
  status: 'passed' | 'failed'
  summary: string
  metrics: CanvasMetric
  nodes: string[]
  /** 单轮完整 DAG（有则画布分页优先展示） */
  dag?: DagResult | null
}

export type CanvasInstantiationCard = {
  id: string
  name: string
  summary: string
  code: string
  metrics: CanvasMetric
}

export type CanvasEvolutionRow = {
  id: number
  understandingDone: boolean
  understandingMetrics?: CanvasMetric
  dagTabs: CanvasDagTab[]
  activeDagTabId?: number
  instantiationCards: CanvasInstantiationCard[]
  sampleScore?: number
  sampleMetrics?: CanvasMetric
  experience?: string
  experienceMetrics?: CanvasMetric
  needNext: boolean
  completed: boolean
}

export interface LiveArtifactsForCanvas {
  understanding: UnderstandingResult | null
  dag: DagResult | null
  orchestrationValidation: { is_valid: boolean; validation_issues: string[] } | null
  judge: JudgeResult | null
  experienceBullets: string[]
}

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
    quality: Record<string, unknown> | null
    trial: Record<string, unknown> | null
    experience: Record<string, unknown> | null
    tokens: WorkflowTokensResponse | null
    history: { round_snapshots?: WorkflowRoundSnapshot[]; entries?: Array<Record<string, unknown>> } | null
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

  const dagTabs: CanvasDagTab[] = []
  let tabId = 0
  if (orchestrationDone) {
    tabId++
    dagTabs.push({
      id: tabId,
      title: isZh ? '编排' : 'Orchestration',
      status: 'passed',
      summary: isZh ? '编排结果已写入 data/orchestration_results' : 'Orchestration saved to disk',
      metrics: { sec: 0, tokens: tokensForSteps(opts.tokens, ['orchestration']) },
      nodes: dagParsed?.execution_order ?? [],
      // 关键：把 DAG 快照固化在当前轮 tab，避免进入下一轮后因全局 dag 为空导致上一轮 DAG 消失。
      dag: dagParsed ?? undefined,
    })
  }
  if (hasOrchestrationValidation) {
    const ok = dagVal?.is_valid !== false
    tabId++
    dagTabs.push({
      id: tabId,
      title: isZh ? 'DAG 校验' : 'DAG validation',
      status: ok ? 'passed' : 'failed',
      summary: ok
        ? isZh
          ? '注册表契约与 DAG 一致性校验通过'
          : 'Registry + DAG validation passed'
        : isZh
          ? `校验未通过（问题数: ${dagVal?.issue_count ?? '—'}）`
          : `Validation failed (issues: ${dagVal?.issue_count ?? '—'})`,
      metrics: { sec: 0, tokens: tokensForSteps(opts.tokens, ['orchestration']) },
      nodes: dagParsed?.execution_order ?? [],
      dag: dagParsed ?? undefined,
    })
  }
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
  if (opts.instantiationSteps?.length) {
    opts.instantiationSteps.forEach((s, i) => {
      const op = String(s.operator_name ?? s.operator ?? `step_${i + 1}`)
      instCards.push({
        id: `step-${i}-${op}`,
        name: op,
        summary: String(s.intermediate_summary ?? s.description ?? ''),
        code: String(s.code ?? ''),
        metrics: { sec: 0, tokens: Math.round(instTokens / Math.max(1, opts.instantiationSteps?.length ?? 1)) },
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

  const row: CanvasEvolutionRow = {
    id: roundId,
    understandingDone: completed.has('understanding') || artifacts.understanding,
    understandingMetrics:
      completed.has('understanding') || artifacts.understanding
        ? { sec: 0, tokens: understandingTokens }
        : undefined,
    dagTabs,
    activeDagTabId: dagTabs.length ? dagTabs[dagTabs.length - 1].id : undefined,
    instantiationCards: instCards,
    sampleScore,
    sampleMetrics:
      sampleScore !== undefined ? { sec: 0, tokens: trialTokens + qualityTokens } : trialDone ? { sec: 0, tokens: trialTokens } : undefined,
    // 经验卡片仅在“本轮 experience 步骤完成”后展示，避免把上一轮经验误显示到当前轮。
    experience: experienceDone ? expText || undefined : undefined,
    experienceMetrics: experienceDone ? { sec: 0, tokens: experienceTokens } : undefined,
    needNext: !canRunFullByJudge && trialDone && needPipelineEvolution,
    completed: canRunFullByJudge,
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
  snaps.forEach((s) => {
    const round = toNumber(s.round)
    if (typeof round !== 'number' || !Number.isFinite(round) || round < 1) return
    const rid = Math.max(1, Math.round(round))
    // 历史只显示“当前轮之前”的轮次，避免 round=1 时误出现多行。
    if (rid >= roundId) return
    const summary = s.summary && typeof s.summary === 'object' ? s.summary : {}
    const uDone = Boolean((summary as Record<string, unknown>).understanding_done)
    const dagNodeCount = Math.max(0, Math.round(toNumber((summary as Record<string, unknown>).dag_node_count) ?? 0))
    const instStepCount = Math.max(0, Math.round(toNumber((summary as Record<string, unknown>).instantiation_steps) ?? 0))
    const score = toNumber((summary as Record<string, unknown>).sample_score)
    const exp = (summary as Record<string, unknown>).experience_text
    const expText = typeof exp === 'string' ? exp : ''

    const dagTabs: CanvasDagTab[] =
      dagNodeCount > 0
        ? [
            {
              id: 1,
              title: isZh ? '编排(历史)' : 'Orchestration (history)',
              status: 'passed',
              summary: isZh ? `已归档 DAG 节点数: ${dagNodeCount}` : `Archived DAG nodes: ${dagNodeCount}`,
              metrics: { sec: 0, tokens: 0 },
              nodes: [],
            },
          ]
        : []
    const instantiationCards: CanvasInstantiationCard[] = Array.from({ length: instStepCount }).map((_, i) => ({
      id: `hist-r${rid}-inst-${i + 1}`,
      name: isZh ? `历史实例化步骤 ${i + 1}` : `Historical Instantiation ${i + 1}`,
      summary: isZh ? '由轮次快照恢复' : 'Recovered from round snapshot',
      code: '',
      metrics: { sec: 0, tokens: 0 },
    }))
    const qualityPassedSnap = toBool(s.quality_passed)
    historyRows.push({
      id: rid,
      understandingDone: uDone,
      understandingMetrics: uDone ? { sec: 0, tokens: 0 } : undefined,
      dagTabs,
      activeDagTabId: dagTabs[0]?.id,
      instantiationCards,
      sampleScore: typeof score === 'number' ? Math.max(0, Math.min(100, Math.round(score))) : undefined,
      sampleMetrics: typeof score === 'number' ? { sec: 0, tokens: 0 } : undefined,
      experience: expText || undefined,
      experienceMetrics: expText ? { sec: 0, tokens: 0 } : undefined,
      // 历史轮次若当时未通过，则应显示回流到下一轮（橙线）。
      needNext: qualityPassedSnap === false,
      completed: true,
    })
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
