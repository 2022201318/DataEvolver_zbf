/**
 * 从 orchestration 归档 + 当前 live 编排构建 DAG 标签页（编排1/编排2…）。
 * 仅使用 kind=orchestration 的归档作为重试记录，不包含 iteration/round 快照重复。
 */
import type { WorkflowTokensResponse } from '../api/client'
import type { DagResult } from '../types'
import type { CanvasDagTab, OrchestrationArchiveArtifact } from './canvasRowTypes'
import { parseDagFromApi } from './buildRoundRowHelpers'

type Attempt = {
  dag: DagResult
  isValid: boolean
  issueCount: number
  issuePreview: string[]
  summarySuffix?: string
  attemptOrder: number
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
  if (v && typeof v === 'object') {
    const o = v as Record<string, unknown>
    if (typeof o.description === 'string') return o.description
    try {
      return JSON.stringify(v)
    } catch {
      return String(v)
    }
  }
  return String(v)
}

function extractValidation(
  orchestration: Record<string, unknown> | null | undefined
): { isValid: boolean; issueCount: number; issues: string[] } {
  if (!orchestration) return { isValid: true, issueCount: 0, issues: [] }
  const issues: string[] = []
  const cs = orchestration.constrained_search
  if (cs && typeof cs === 'object') {
    const vr = (cs as Record<string, unknown>).validation_result
    if (vr && typeof vr === 'object') {
      const raw = (vr as Record<string, unknown>).validation_issues
      if (Array.isArray(raw)) issues.push(...raw.map(normalizeIssueText))
    }
  }
  const dagVal = orchestration.dag_validation as Record<string, unknown> | undefined
  const dagIssues = dagVal?.validation_issues
  if (Array.isArray(dagIssues)) {
    for (const it of dagIssues) {
      const s = normalizeIssueText(it)
      if (s && !issues.includes(s)) issues.push(s)
    }
  }
  const issueCount = toNumber(dagVal?.issue_count) ?? issues.length
  const isValid =
    dagVal?.is_valid === false ? false : (toBool(dagVal?.is_valid) ?? issues.length === 0)
  return { isValid: isValid !== false, issueCount: Math.max(0, Math.round(issueCount)), issues }
}

function dagSignature(dag: DagResult | null | undefined): string {
  if (!dag) return ''
  const names = (dag.execution_order ?? dag.nodes.map((n) => n.node_id))
    .map((id) => {
      const node = dag.nodes.find((n) => n.node_id === id)
      return node?.node_name ?? id
    })
    .join('>')
  return names
}

function pushAttempt(attempts: Attempt[], next: Omit<Attempt, 'issuePreview'> & { issuePreview?: string[] }) {
  const sig = dagSignature(next.dag)
  const dup = attempts.find((a) => dagSignature(a.dag) === sig && a.isValid === next.isValid)
  if (dup) return
  attempts.push({ ...next, issuePreview: next.issuePreview ?? [] })
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

export function buildOrchestrationDagTabs(args: {
  roundId: number
  isZh: boolean
  orchestrationArchives: OrchestrationArchiveArtifact[]
  liveOrchestration?: Record<string, unknown> | null
  liveOrchestrationRevision?: number
  tokens?: WorkflowTokensResponse | null
}): { dagTabs: CanvasDagTab[]; activeDagTabId?: number } {
  const attempts: Attempt[] = []
  const orchTokens = tokensForSteps(args.tokens ?? null, ['orchestration', 'operator_evolution'])

  args.orchestrationArchives
    .filter((a) => Math.round(a.round) === args.roundId && a.orchestration)
    .sort((a, b) => (a.orchestration_revision ?? 0) - (b.orchestration_revision ?? 0))
    .forEach((a) => {
      const dag = parseDagFromApi(a.orchestration?.dag)
      if (!dag) return
      const val = extractValidation(a.orchestration ?? null)
      pushAttempt(attempts, {
        dag,
        isValid: val.isValid,
        issueCount: val.issueCount,
        issuePreview: val.issues.slice(0, 4),
        summarySuffix:
          typeof a.orchestration_revision === 'number'
            ? args.isZh
              ? `归档 rev ${a.orchestration_revision}`
              : `archive rev ${a.orchestration_revision}`
            : undefined,
        attemptOrder: a.orchestration_revision ?? attempts.length,
      })
    })

  if (args.liveOrchestration) {
    const dag = parseDagFromApi(args.liveOrchestration.dag)
    if (dag) {
      const val = extractValidation(args.liveOrchestration)
      pushAttempt(attempts, {
        dag,
        isValid: val.isValid,
        issueCount: val.issueCount,
        issuePreview: val.issues.slice(0, 4),
        attemptOrder: args.liveOrchestrationRevision ?? 9999,
      })
    }
  }

  attempts.sort((a, b) => a.attemptOrder - b.attemptOrder)

  const dagTabs: CanvasDagTab[] = attempts.map((attempt, i) => {
    const issueHint =
      !attempt.isValid && attempt.issuePreview.length
        ? ` · ${attempt.issuePreview[0].slice(0, 80)}`
        : ''
    return {
      id: i + 1,
      title: args.isZh ? `编排${i + 1}` : `Orchestration ${i + 1}`,
      status: attempt.isValid ? 'passed' : 'failed',
      summary: attempt.isValid
        ? args.isZh
          ? `DAG 校验通过${attempt.summarySuffix ? `（${attempt.summarySuffix}）` : ''}`
          : `DAG validation passed${attempt.summarySuffix ? ` (${attempt.summarySuffix})` : ''}`
        : args.isZh
          ? `DAG 校验未通过（问题 ${attempt.issueCount}）${issueHint}`
          : `DAG validation failed (${attempt.issueCount} issues)${issueHint}`,
      metrics: { sec: 0, tokens: orchTokens },
      nodes: attempt.dag.execution_order ?? [],
      dag: attempt.dag,
    }
  })

  let activeDagTabId: number | undefined
  for (let i = dagTabs.length - 1; i >= 0; i--) {
    if (dagTabs[i].status === 'passed') {
      activeDagTabId = dagTabs[i].id
      break
    }
  }

  return {
    dagTabs,
    activeDagTabId: activeDagTabId ?? dagTabs[dagTabs.length - 1]?.id,
  }
}
