import { Fragment, useEffect, useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import {
  AlertCircle,
  ArrowRight,
  BarChart3,
  Brain,
  CheckCircle2,
  Clock,
  Code2,
  Cpu,
  Database,
  FastForward,
  FileJson2,
  GitBranch,
  HardDrive,
  Lightbulb,
  Network,
  Play,
  Rocket,
  ShieldCheck,
  Sparkles,
  X,
  Zap,
} from 'lucide-react'
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { WorkflowStateDto } from '../api'
import type { DagResult, JudgeResult, OperatorItem, UnderstandingResult } from '../types'
import type { LiveArtifactsForCanvas } from '../lib/buildEvolutionRowsFromPipeline'
import { resolveDagForRow } from '../lib/resolveDagForRow'

type Metric = { sec: number; tokens: number }

function dagTabStatusMark(tab: DagTab): string {
  if (tab.status === 'passed') return ' ✓'
  if (tab.status === 'failed') return ' ✗'
  return ''
}

function dagTabStyle(tab: DagTab, activeId: number | undefined): CSSProperties {
  const active = tab.id === activeId
  const failed = tab.status === 'failed'
  return {
    borderColor: active ? (failed ? 'var(--de-orange)' : 'var(--de-cyan)') : failed ? 'color-mix(in srgb, var(--de-orange) 55%, var(--border))' : 'var(--border)',
    background: active
      ? failed
        ? 'color-mix(in srgb, var(--de-orange) 12%, transparent)'
        : 'var(--de-cyan-glow)'
      : failed
        ? 'color-mix(in srgb, var(--de-orange) 6%, transparent)'
        : 'transparent',
    color: failed ? 'var(--de-orange)' : 'var(--text-dim)',
    fontWeight: active ? 600 : 400,
  }
}

type DagStatus = 'passed' | 'failed'

interface DagTab {
  id: number
  title: string
  status: DagStatus
  summary: string
  metrics: Metric
  /** 该轮编排涉及的算子名（无完整 dag 时可生成线性子图） */
  nodes?: string[]
  /** 该轮完整 DAG 快照（优先于 nodes） */
  dag?: DagResult
}

interface InstantiationCard {
  id: string
  name: string
  summary: string
  code: string
  metrics: Metric
  llmGenerated?: boolean
}

interface InstantiationMeta {
  reused?: boolean
  llm_codegen?: boolean
  llm_steps?: string[]
  note?: string
  source?: string
}

interface ExperienceMeta {
  llm_used?: boolean
  source_kind?: string
  detail?: string
}

interface EvolutionRow {
  id: number
  understandingDone: boolean
  understandingMetrics?: Metric
  dagTabs: DagTab[]
  activeDagTabId?: number
  instantiationCards: InstantiationCard[]
  instantiationMeta?: InstantiationMeta
  sampleScore?: number
  sampleMetrics?: Metric
  experience?: string
  experienceMetrics?: Metric
  experienceMeta?: ExperienceMeta
  needNext: boolean
  completed: boolean
  rowUi?: LiveArtifactsForCanvas
}

interface CanvasText {
  operatorPool: string
  operatorHint: string
  sourceBase: string
  sourceEvolved: string
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
}

/** 详情弹窗与种子区共用的数据层 */
type CanvasUiBundle = {
  understanding: UnderstandingResult
  dag: DagResult
  orchVal: { is_valid: boolean; validation_issues: string[] }
  judge: JudgeResult
  experiences: string[]
}

const EMPTY_UNDERSTANDING: UnderstandingResult = {
  basic_information: {},
  schema_analysis: {},
  dataset_level_delta: {},
}
const EMPTY_DAG: DagResult = { nodes: [], edges: [], execution_order: [], total_nodes: 0, total_edges: 0 }
const EMPTY_ORCH_VALIDATION = { is_valid: false, validation_issues: [] as string[] }
const EMPTY_JUDGE: JudgeResult = {
  has_differences: false,
  overall_assessment: '',
  critical_insights: [],
  implicit_quality_requirements: {},
}

function resolveRowUi(row: EvolutionRow | undefined, global: CanvasUiBundle): CanvasUiBundle {
  if (!row?.rowUi) return global
  const r = row.rowUi
  // 已完成轮次：只读 rowUi 快照，禁止回退到 global live 数据（避免后一轮污染前一轮）
  if (row.completed) {
    return {
      understanding: (r.understanding ?? EMPTY_UNDERSTANDING) as UnderstandingResult,
      dag: r.dag ?? EMPTY_DAG,
      orchVal: r.orchestrationValidation ?? EMPTY_ORCH_VALIDATION,
      judge: r.judge ?? EMPTY_JUDGE,
      experiences:
        r.experienceBullets.length > 0
          ? [...r.experienceBullets]
          : row.experience?.trim()
            ? [row.experience]
            : [],
    }
  }
  return {
    understanding: (r.understanding ?? global.understanding) as UnderstandingResult,
    dag: r.dag ?? global.dag,
    orchVal: r.orchestrationValidation ?? global.orchVal,
    judge: r.judge ?? global.judge,
    experiences: r.experienceBullets.length > 0 ? [...r.experienceBullets] : global.experiences,
  }
}

interface EvolutionCanvasProps {
  t: CanvasText
  rows: EvolutionRow[]
  operatorPool: OperatorItem[]
  totalMetrics: Metric
  finished: boolean
  /** 后端管线 id；有值时表示与 API 同步展示 */
  pipelineId?: string | null
  /** GET workflow + 各阶段产物映射后的结构化数据 */
  liveArtifacts?: LiveArtifactsForCanvas | null
  workflowState?: WorkflowStateDto | null
  workflowBusy?: boolean
  workflowExecutingStep?: string | null
  canRunFull?: boolean
  artifactHistoryCount?: number
  onStepForward: () => void | Promise<void>
  onAutoCompleteRound: () => void | Promise<void>
  onSelectDagTab: (rowId: number, tabId: number) => void
  onRunFullData: () => void | Promise<void>
  onRerunFromCurrentStep?: () => void | Promise<void>
  /** 左侧导航已上传的文件类型，用于流水线入口卡片轻量展示 */
  uploadPresence?: { raw: boolean; seed: boolean; description: boolean }
}

const edgeStyle = { stroke: '#5b7389', strokeWidth: 2 }
type Accent = 'default' | 'new' | 'replaced' | 'reused'

interface CanvasNodeData {
  [key: string]: unknown
  label: JSX.Element
  title: string
  role: string
  io: string
  reason: string
  gain: string
  tag: Accent
  introducedIn?: number
}

function metricText(metric?: Metric) {
  return metric ? `${metric.sec}s · ${metric.tokens} tk` : ''
}

/** 流水线大阶段节点视觉态（见 docs/CANVAS_UX_PRINCIPLES.md §1） */
type PipelineVisualState = 'pending' | 'active' | 'done' | 'error'

function pipelineNodeChrome(state: PipelineVisualState): { border: string; background: string; boxShadow: string } {
  switch (state) {
    case 'pending':
      return {
        border: '1px solid color-mix(in srgb, var(--border) 88%, transparent)',
        background: 'color-mix(in srgb, var(--bg-panel) 55%, transparent)',
        boxShadow: 'none',
      }
    case 'active':
      return {
        border: '1px solid color-mix(in srgb, var(--de-cyan) 55%, var(--border))',
        background: 'color-mix(in srgb, var(--de-cyan) 5%, var(--bg-panel))',
        boxShadow:
          '0 0 0 1px color-mix(in srgb, var(--de-cyan) 35%, transparent), 0 0 22px color-mix(in srgb, var(--de-cyan) 18%, transparent)',
      }
    case 'done':
      return {
        border: '1px solid color-mix(in srgb, var(--de-green) 28%, var(--border))',
        background: 'color-mix(in srgb, var(--de-green) 4%, var(--bg-panel))',
        boxShadow: 'none',
      }
    case 'error':
      return {
        border: '1px solid color-mix(in srgb, var(--de-orange) 45%, var(--border))',
        background: 'color-mix(in srgb, var(--de-orange) 5%, var(--bg-panel))',
        boxShadow: '0 0 0 1px color-mix(in srgb, var(--de-orange) 22%, transparent)',
      }
    default:
      return pipelineNodeChrome('pending')
  }
}

function getPipelineBlockState(
  row: EvolutionRow,
  block: 'raw' | 'understanding' | 'dag' | 'inst' | 'sample' | 'exp',
  activeRow: EvolutionRow | undefined
): PipelineVisualState {
  if (!activeRow) return row.completed ? 'done' : 'pending'
  if (row.id !== activeRow.id) {
    if (row.completed) return 'done'
    if (row.id > activeRow.id) return 'pending'
    return 'done'
  }
  const hasPassedDag = row.dagTabs.some((tab) => tab.status === 'passed')
  const dagFailedWithoutPass = row.dagTabs.some((tab) => tab.status === 'failed') && !hasPassedDag

  switch (block) {
    case 'raw':
      return 'done'
    case 'understanding':
      if (!row.understandingDone) return 'active'
      return 'done'
    case 'dag':
      if (!row.understandingDone) return 'pending'
      if (dagFailedWithoutPass) return 'error'
      if (!hasPassedDag) return 'active'
      return 'done'
    case 'inst':
      if (!hasPassedDag) return 'pending'
      if (row.instantiationCards.length === 0) return 'active'
      return 'done'
    case 'sample':
      if (row.instantiationCards.length === 0) return 'pending'
      if (row.sampleScore === undefined) return 'active'
      return 'done'
    case 'exp':
      if (row.sampleScore === undefined) return 'pending'
      if (!row.experience) return 'active'
      return 'done'
    default:
      return 'pending'
  }
}

/** 内层算子子图：与算子池相同的 category 色与 requires_llm 标记（§2.3 / §2.4） */
function EmbeddedOperatorSubDag({
  dag,
  operatorPool,
  caption,
  compact = false,
}: {
  dag: DagResult
  operatorPool: OperatorItem[]
  caption: string
  compact?: boolean
}) {
  const order = dag.execution_order?.length ? dag.execution_order : dag.nodes.map((n) => n.node_id)
  const nodesById = Object.fromEntries(dag.nodes.map((n) => [n.node_id, n]))

  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{ borderColor: 'var(--border)', background: 'color-mix(in srgb, var(--bg-panel) 97%, transparent)' }}
    >
      <p className={compact ? 'text-[10px] text-[var(--text-muted)] px-2 py-1 border-b' : 'text-xs text-[var(--text-muted)] px-3 py-2 border-b'} style={{ borderColor: 'var(--border)' }}>
        {caption}
      </p>
      <div className={compact ? 'flex items-center gap-1 px-2 py-2 overflow-x-auto' : 'flex items-center gap-2 px-3 py-3 overflow-x-auto'}>
        {order.map((id, idx) => {
          const n = nodesById[id]
          if (!n) return null
          const op = operatorPool.find((o) => o.name === n.node_name)
          const kind = op ? inferOperatorKind(op) : inferOperatorKind({ name: n.node_name, description: n.description ?? '', source: 'base' } as OperatorItem)
          const accent = operatorKindStyle(kind)
          return (
            <Fragment key={id}>
              {idx > 0 ? (
                <div className="shrink-0 flex items-center gap-1.5 px-0.5">
                  <span className="text-[9px] text-[var(--text-muted)] font-mono">{idx}</span>
                  <ArrowRight className={compact ? 'w-3 h-3 shrink-0 text-[var(--text-muted)]' : 'w-4 h-4 shrink-0 text-[var(--de-cyan)]'} aria-hidden />
                </div>
              ) : null}
              <div
                className={compact ? 'shrink-0 rounded-md px-2 py-1 border min-w-0 max-w-[7.5rem]' : 'shrink-0 rounded-xl px-3 py-2 border min-w-[12rem] max-w-[14rem] shadow-sm'}
                style={{ borderColor: accent.border, background: accent.background }}
                title={n.description}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className={compact ? 'text-[10px] font-semibold text-[var(--text)] truncate' : 'text-xs font-semibold text-[var(--text)] truncate'}>{n.node_name}</p>
                  <span className="text-[9px] text-[var(--text-muted)] font-mono shrink-0">{n.node_id}</span>
                </div>
                <div className="flex items-center gap-1 mt-1">
                  <span className={compact ? 'text-[9px] font-medium truncate' : 'text-[10px] font-medium truncate'} style={{ color: accent.dot }}>
                    {op?.category?.trim() || n.node_name.split('_')[0]}
                  </span>
                  {(op?.requires_llm ?? n.node_name.includes('llm')) ? (
                    <span
                      className={compact ? 'text-[8px] px-0.5 rounded text-[var(--de-orange)] shrink-0' : 'text-[9px] px-1 py-0.5 rounded border text-[var(--de-orange)] shrink-0'}
                      style={compact ? undefined : { borderColor: 'color-mix(in srgb, var(--de-orange) 45%, var(--border))' }}
                    >
                      LLM
                    </span>
                  ) : null}
                </div>
                {!compact ? <p className="text-[10px] text-[var(--text-dim)] mt-1.5 line-clamp-2 leading-snug">{n.description ?? '-'}</p> : null}
              </div>
            </Fragment>
          )
        })}
      </div>
    </div>
  )
}

/** 由名称/source 推断算子类型，用于卡片配色（后续可在 OperatorItem 上显式加 kind 覆盖） */
type OperatorKind = 'io' | 'transform' | 'quality' | 'llm' | 'evolved'

function inferOperatorKind(op: OperatorItem): OperatorKind {
  const cid = op.category_id
  if (cid === 'bridge') return 'evolved'
  if (cid === 'io') return 'io'
  if (cid === 'semantic') return 'llm'
  if (cid === 'quality') return 'quality'
  if (cid === 'structure' || cid === 'control') return 'transform'
  if (op.source === 'evolved') return 'evolved'
  const n = op.name.toLowerCase()
  if (n.startsWith('clean') || n.includes('read') || n.includes('write')) return 'io'
  if (n.startsWith('filter') || n.includes('gate') || n.includes('quality')) return 'quality'
  if (n.includes('llm') || n.includes('gen') || n.includes('reason') || n.includes('enrich')) return 'llm'
  if (n.startsWith('map') || n.includes('norm') || n.includes('schema')) return 'transform'
  return 'transform'
}

function OperatorKindIcon({ kind, color }: { kind: OperatorKind; color: string }) {
  const cls = 'w-2.5 h-2.5 shrink-0'
  switch (kind) {
    case 'io':
      return <HardDrive className={cls} style={{ color }} aria-hidden />
    case 'transform':
      return <GitBranch className={cls} style={{ color }} aria-hidden />
    case 'quality':
      return <ShieldCheck className={cls} style={{ color }} aria-hidden />
    case 'llm':
      return <Cpu className={cls} style={{ color }} aria-hidden />
    case 'evolved':
    default:
      return <Sparkles className={cls} style={{ color }} aria-hidden />
  }
}

function operatorKindStyle(kind: OperatorKind): { border: string; background: string; dot: string } {
  switch (kind) {
    case 'io':
      return {
        border: 'var(--de-cyan)',
        background: 'color-mix(in srgb, var(--de-cyan) 14%, var(--bg-card))',
        dot: 'var(--de-cyan)',
      }
    case 'transform':
      return {
        border: '#8b5cf6',
        background: 'color-mix(in srgb, #8b5cf6 12%, var(--bg-card))',
        dot: '#8b5cf6',
      }
    case 'quality':
      return {
        border: 'var(--de-orange)',
        background: 'color-mix(in srgb, var(--de-orange) 12%, var(--bg-card))',
        dot: 'var(--de-orange)',
      }
    case 'llm':
      return {
        border: 'var(--de-green)',
        background: 'color-mix(in srgb, var(--de-green) 12%, var(--bg-card))',
        dot: 'var(--de-green)',
      }
    case 'evolved':
    default:
      return {
        border: 'var(--de-cyan)',
        background: 'linear-gradient(145deg, color-mix(in srgb, var(--de-cyan) 16%, var(--bg-card)), color-mix(in srgb, var(--de-teal) 10%, var(--bg-card)))',
        dot: 'var(--de-teal)',
      }
  }
}

function OperatorDetailModal({
  op,
  onClose,
  local,
  t,
  categoryLabel,
  kind,
  accent,
  isZh,
}: {
  op: OperatorItem
  onClose: () => void
  local: Record<string, string>
  t: CanvasText
  categoryLabel: string
  kind: OperatorKind
  accent: ReturnType<typeof operatorKindStyle>
  isZh: boolean
}) {
  return (
    <div className="fixed inset-0 z-[58] flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" onClick={onClose}>
      <div
        className="w-full max-w-lg max-h-[85vh] overflow-hidden flex flex-col rounded-3xl border shadow-2xl"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <header
          className="flex items-start justify-between gap-3 px-5 py-4 border-b shrink-0"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}
        >
          <div className="min-w-0">
            <p className="text-[10px] font-medium uppercase tracking-wide mb-1" style={{ color: accent.dot }}>
              {local.opDetailBadge}
            </p>
            <h2 className="text-base font-semibold text-[var(--text)] break-all leading-snug">{op.name}</h2>
            <div className="flex flex-wrap items-center gap-2 mt-2">
              <span
                className="text-[11px] px-2 py-0.5 rounded-lg border font-medium"
                style={{ borderColor: accent.border, color: accent.dot, background: accent.background }}
              >
                {categoryLabel}
              </span>
              <span className="text-[11px] text-[var(--text-muted)]">
                {op.source === 'evolved' ? t.sourceEvolved : t.sourceBase}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 w-9 h-9 rounded-xl border inline-flex items-center justify-center"
            style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}
            aria-label={local.close}
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        <div className="overflow-y-auto px-5 py-4 space-y-4 text-sm">
          <section>
            <p className="text-xs text-[var(--text-muted)] mb-1.5 flex items-center gap-1.5">
              <FileJson2 className="w-3.5 h-3.5" />
              {local.opDesc}
            </p>
            <p className="text-[var(--text-dim)] leading-relaxed">{op.description}</p>
          </section>

          {op.updatedAt ? (
            <section className="flex items-center gap-2 text-xs text-[var(--text-dim)]">
              <Clock className="w-3.5 h-3.5 text-[var(--text-muted)]" />
              <span className="text-[var(--text-muted)]">{local.opUpdated}</span>
              <span>{op.updatedAt}</span>
            </section>
          ) : null}

          {op.input_keys && op.output_keys ? (
            <section className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border)' }}>
              <p className="text-[10px] px-3 py-2 border-b font-medium text-[var(--text-muted)]" style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}>
                {local.opRegistry}
              </p>
              <div className="p-3 space-y-2 text-xs text-[var(--text-dim)]">
                {op.category_id ? (
                  <p>
                    <span className="text-[var(--text-muted)]">category_id</span>: {op.category_id}
                  </p>
                ) : null}
                <p className="flex items-center gap-2">
                  <Zap className="w-3.5 h-3.5 text-[var(--de-orange)]" />
                  <span className="text-[var(--text-muted)]">{local.opRequiresLlm}</span>
                  <span>{op.requires_llm ? (isZh ? '是' : 'Yes') : isZh ? '否' : 'No'}</span>
                </p>
                <div className="text-[10px] font-mono rounded-lg p-2 overflow-x-auto" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
                  <div>in: [{op.input_keys.join(', ')}]</div>
                  <div>out: [{op.output_keys.join(', ')}]</div>
                </div>
              </div>
            </section>
          ) : null}

          <section className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border)' }}>
            <p className="text-[10px] px-3 py-2 border-b text-[var(--text-muted)]" style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}>
              {local.opMetaJson}
            </p>
            <pre className="p-3 text-[10px] font-mono text-[var(--text-dim)] overflow-x-auto max-h-40">
              {JSON.stringify(
                {
                  id: op.id,
                  name: op.name,
                  category: op.category ?? categoryLabel,
                  category_id: op.category_id ?? null,
                  card_variant: op.card_variant ?? null,
                  inferred_kind: kind,
                  source: op.source,
                  requires_llm: op.requires_llm ?? null,
                  input_keys: op.input_keys ?? null,
                  output_keys: op.output_keys ?? null,
                  updatedAt: op.updatedAt ?? null,
                },
                null,
                2
              )}
            </pre>
          </section>
        </div>

        <footer className="px-5 py-3 border-t flex justify-end shrink-0" style={{ borderColor: 'var(--border)' }}>
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-5 rounded-xl border text-sm"
            style={{ borderColor: 'var(--border)', color: 'var(--text-dim)' }}
          >
            {local.close}
          </button>
        </footer>
      </div>
    </div>
  )
}

function blockNode(
  id: string,
  x: number,
  y: number,
  title: string,
  content: string[],
  meta: Omit<CanvasNodeData, 'label'>,
  visualState: PipelineVisualState,
  width = 220,
  height = 140,
  labelOverride?: ReactNode,
  running = false,
  runningText = 'Running'
): Node {
  const chrome = pipelineNodeChrome(visualState)
  const baseLabel =
    labelOverride ?? (
      <div>
        <div style={{ fontWeight: 600, marginBottom: 6 }}>{title}</div>
        {content.map((line, i) => (
          <div key={`${id}-L${i}`} style={{ color: 'var(--text-dim)', marginBottom: 4 }}>
            {line}
          </div>
        ))}
      </div>
    )

  return {
    id,
    position: { x, y },
    style: {
      width,
      minHeight: height,
      height: 'auto',
      borderRadius: 14,
      border: chrome.border,
      background: chrome.background,
      color: 'var(--text)',
      padding: 10,
      fontSize: 12,
      boxShadow: chrome.boxShadow,
    },
    data: {
      label: running ? (
        <div>
          <div
            className="mb-2 inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px]"
            style={{ borderColor: 'var(--de-cyan)', color: 'var(--de-cyan)', background: 'var(--de-cyan-glow)' }}
          >
            <Cpu className="h-3 w-3 animate-spin" />
            <span>{runningText}</span>
          </div>
          {baseLabel}
        </div>
      ) : (
        baseLabel
      ),
      ...meta,
    },
  }
}

/** 编排卡片内方形 DAG 子图（算子自进化核心展示，尺寸显著大于其它阶段卡片） */
const ORCH_DAG_SUBGRAPH_MAX_SIDE_PX = 440
const ORCH_DAG_SUBGRAPH_MIN_SIDE_PX = 300
const ORCH_DAG_CELL_UNIT_PX = 78
const ORCH_DAG_CELL_GAP_PX = 14

/** 根据 DAG 规模估算编排卡片尺寸（方形子图 + 标题区） */
function computeOrchestrationDagCardMetrics(dag: DagResult): {
  cardWidth: number
  cardHeight: number
  subgraphSide: number
} {
  const order = dag.execution_order?.length ? dag.execution_order : dag.nodes.map((n) => n.node_id)
  const n = Math.max(1, order.length)
  const cols = Math.max(1, Math.round(Math.sqrt(n)))
  const rows = Math.ceil(n / cols)
  const maxDim = Math.max(cols, rows)
  const side = Math.min(
    ORCH_DAG_SUBGRAPH_MAX_SIDE_PX,
    Math.max(
      ORCH_DAG_SUBGRAPH_MIN_SIDE_PX,
      ORCH_DAG_CELL_UNIT_PX * maxDim + ORCH_DAG_CELL_GAP_PX * (maxDim - 1)
    )
  )
  const cardWidth = Math.min(580, side + 44)
  const titleBlock = 52
  const cardHeight = titleBlock + 12 + side + 28
  return { cardWidth, cardHeight, subgraphSide: side }
}

/** 流水线画布内嵌：方形网格 + 执行序连线，仅展示算子名与类别色 */
function OrchestrationDagGridView({
  dag,
  operatorPool,
  isZh,
  subgraphSidePx,
}: {
  dag: DagResult
  operatorPool: OperatorItem[]
  isZh: boolean
  /** 与 computeOrchestrationDagCardMetrics 一致，避免子图被 maxHeight 压扁 */
  subgraphSidePx: number
}) {
  const kindShort = (k: OperatorKind) =>
    ({
      io: isZh ? 'I/O' : 'I/O',
      transform: isZh ? '变换' : 'Tf',
      quality: isZh ? '质检' : 'QA',
      llm: 'LLM',
      evolved: isZh ? '进化' : 'Ev',
    })[k]

  const order = dag.execution_order?.length ? dag.execution_order : dag.nodes.map((n) => n.node_id)
  const nodesById = Object.fromEntries(dag.nodes.map((n) => [n.node_id, n]))
  const n = Math.max(1, order.length)
  const cols = Math.max(1, Math.round(Math.sqrt(n)))
  const rows = Math.ceil(n / cols)

  const gridPosPct = (index: number) => {
    const col = index % cols
    const row = Math.floor(index / cols)
    const cw = 100 / cols
    const rh = 100 / rows
    return { x: (col + 0.5) * cw, y: (row + 0.5) * rh }
  }

  return (
    <div
      className="relative w-full overflow-hidden rounded-xl"
      style={{
        aspectRatio: '1 / 1',
        maxHeight: subgraphSidePx,
        background: 'color-mix(in srgb, var(--bg-panel) 92%, transparent)',
        border: '1px solid color-mix(in srgb, var(--de-cyan) 22%, var(--border))',
      }}
    >
      <svg className="absolute inset-0 h-full w-full pointer-events-none" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
        {order.slice(0, -1).map((_, i) => {
          const a = gridPosPct(i)
          const b = gridPosPct(i + 1)
          return (
            <line
              key={`dag-edge-${i}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke="var(--de-cyan)"
              strokeOpacity={0.42}
              strokeWidth={0.85}
            />
          )
        })}
      </svg>
      <div
        className="relative z-[1] grid h-full w-full p-2"
        style={{
          gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
          gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))`,
          gap: 8,
        }}
      >
        {order.map((id, i) => {
          const node = nodesById[id]
          if (!node) return null
          const op = operatorPool.find((o) => o.name === node.node_name)
          const kind = op
            ? inferOperatorKind(op)
            : inferOperatorKind({ name: node.node_name, description: node.description ?? '', source: 'base' } as OperatorItem)
          const accent = operatorKindStyle(kind)
          const cat = (op?.category?.trim() || kindShort(kind)).slice(0, 14)
          const col = i % cols
          const row = Math.floor(i / cols)
          return (
            <div
              key={id}
              className="flex min-h-0 min-w-0 items-center justify-center"
              style={{ gridColumn: col + 1, gridRow: row + 1 }}
            >
              <div
                className="w-full max-w-[9rem] rounded-lg border px-1.5 py-1.5 text-center shadow-sm"
                style={{ borderColor: accent.border, background: accent.background }}
              >
                <p className="truncate text-[11px] font-semibold leading-tight text-[var(--text)]">{node.node_name}</p>
                <p className="truncate text-[9px] font-semibold leading-tight" style={{ color: accent.dot }}>
                  {cat}
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function parseRowBlock(nodeId: string, rows: EvolutionRow[]) {
  const [rowPart, ...rest] = nodeId.split('-')
  const block = rest.join('-') || 'raw'
  if (!rowPart?.startsWith('r')) return { row: undefined as EvolutionRow | undefined, block, rowId: NaN }
  const rowId = Number(rowPart.replace('r', ''))
  return { row: rows.find((r) => r.id === rowId), block, rowId }
}

function modalTitleForNode(nodeId: string, rows: EvolutionRow[], t: CanvasText) {
  const { row, block } = parseRowBlock(nodeId, rows)
  const map: Record<string, string> = {
    raw: t.rawBlock,
    understanding: t.understanding,
    dag: t.dagTabs,
    inst: t.instantiation,
    sample: t.sampleEval,
    exp: t.experience,
  }
  if (!row) return t.pipelineCanvas
  return `${t.roundTitle} ${row.id} · ${map[block] ?? block}`
}

function ExperienceDraftEditor({ initial, hint }: { initial: string; hint: string }) {
  const [value, setValue] = useState(initial)
  useEffect(() => {
    setValue(initial)
  }, [initial])
  return (
    <div className="space-y-2">
      <p className="text-[10px] text-[var(--text-muted)] leading-snug">{hint}</p>
      <textarea
        className="w-full min-h-[120px] rounded-lg border px-3 py-2 text-xs leading-relaxed outline-none resize-y"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-card)', color: 'var(--text)' }}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        spellCheck={false}
      />
    </div>
  )
}

/** 点击画布节点后居中展示，按节点类型差异化结构 */
function NodeDetailCenterModal({
  nodeId,
  onClose,
  rows,
  t,
  local,
  isZh,
  onSelectDagTab,
  scoreDelta,
  operatorPool,
  canvasUi,
}: {
  nodeId: string | null
  onClose: () => void
  rows: EvolutionRow[]
  t: CanvasText
  local: Record<string, string>
  isZh: boolean
  onSelectDagTab: (rowId: number, tabId: number) => void
  scoreDelta: number
  operatorPool: OperatorItem[]
  canvasUi: CanvasUiBundle
}) {
  const { row, block, rowId } = useMemo(() => {
    if (!nodeId) return { row: undefined as EvolutionRow | undefined, block: '', rowId: NaN }
    return parseRowBlock(nodeId, rows)
  }, [nodeId, rows])

  const rowUi = useMemo(() => resolveRowUi(row, canvasUi), [row, canvasUi])

  if (!nodeId) return null
  const activeDag =
    row?.dagTabs.find((tab) => tab.id === row?.activeDagTabId) ?? row?.dagTabs?.[Math.max(0, (row?.dagTabs?.length ?? 1) - 1)]
  const rowDagResolved = row ? resolveDagForRow(row, rowUi.dag) : rowUi.dag

  const metricRow = (m?: Metric) =>
    m ? (
      <div className="flex items-center gap-2 text-xs text-[var(--text-dim)]">
        <Clock className="w-3.5 h-3.5 shrink-0 text-[var(--de-cyan)]" />
        <span>
          {local.completedAt}: {m.sec}s · {m.tokens} tok
        </span>
      </div>
    ) : (
      <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
        <Clock className="w-3.5 h-3.5" />
        {t.pending}
      </div>
    )

  let body: ReactNode = null

  if (!row) {
    body = <p className="text-xs text-[var(--text-dim)]">—</p>
  } else if (block === 'raw') {
    body = (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text)]">
          <Database className="w-5 h-5 text-[var(--de-cyan)]" />
          {t.rawBlock}
        </div>
        <p className="text-xs text-[var(--text-dim)]">
          {isZh ? '本轮流水线的数据入口；与 Seed 对齐前的原始样本基线。' : 'Pipeline entry; raw baseline before seed alignment.'}
        </p>
        <div className="rounded-lg border p-2 font-mono text-[10px] text-[var(--text-muted)]" style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}>
          {`{ "round": ${row.id}, "role": "raw_stream", "status": "${row.completed ? 'done' : 'active'}" }`}
        </div>
      </div>
    )
  } else if (block === 'understanding') {
    const bi = rowUi.understanding.basic_information
    const sa = rowUi.understanding.schema_analysis ?? {}
    const rawFields = Array.isArray(sa.raw_fields) ? (sa.raw_fields as string[]) : []
    const seedFields = Array.isArray(sa.seed_fields) ? (sa.seed_fields as string[]) : []
    const newFields = Array.isArray(sa.new_fields) ? (sa.new_fields as string[]) : []
    const delta = rowUi.understanding.dataset_level_delta ?? {}
    const qualityGaps = Array.isArray(delta.quality_gaps) ? (delta.quality_gaps as string[]) : []
    body = (
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text)]">
            <Brain className="w-5 h-5 text-[var(--de-cyan)]" />
            {t.understanding}
          </div>
          {metricRow(row.understandingMetrics)}
        </div>
        {(rowUi.understanding.language || rowUi.understanding.language_label) && (
          <p className="text-xs text-[var(--text-dim)]">
            <span className="text-[var(--text-muted)]">{isZh ? '语言 / language' : 'Language'}: </span>
            <span className="font-medium text-[var(--text)]">
              {rowUi.understanding.language_label ?? rowUi.understanding.language}
              {rowUi.understanding.language && rowUi.understanding.language_label
                ? ` (${rowUi.understanding.language})`
                : ''}
            </span>
          </p>
        )}
        <p className="text-xs font-medium text-[var(--text)] flex items-center gap-1">
          <Lightbulb className="w-3.5 h-3.5 text-[var(--de-orange)]" />
          {local.thinking}
        </p>
        <p className="text-xs text-[var(--text-dim)] leading-relaxed">
          {bi?.transformation_direction} → {bi?.quality_standards}
        </p>
        <div>
          <p className="text-[10px] text-[var(--text-muted)] mb-1">{isZh ? '处理目标 processing_targets' : 'Processing targets'}</p>
          <div className="flex flex-wrap gap-1.5">
            {(bi?.processing_targets ?? []).map((x) => (
              <span key={x} className="text-[10px] px-2 py-0.5 rounded-full border" style={{ borderColor: 'var(--de-cyan)', color: 'var(--de-cyan)' }}>
                {x}
              </span>
            ))}
          </div>
        </div>
        <div className="rounded-lg border p-2 space-y-2" style={{ borderColor: 'var(--border)', background: 'color-mix(in srgb, var(--bg-panel) 98%, transparent)' }}>
          <p className="text-[10px] font-medium text-[var(--text-muted)]">{local.schemaSummary}</p>
          <ul className="text-[11px] text-[var(--text-dim)] space-y-1.5">
            <li>
              <span className="text-[var(--text-muted)]">{local.schemaRaw}: </span>
              {rawFields.length ? rawFields.join(', ') : '—'}
            </li>
            <li>
              <span className="text-[var(--text-muted)]">{local.schemaSeed}: </span>
              {seedFields.length ? seedFields.join(', ') : '—'}
            </li>
            <li>
              <span className="text-[var(--text-muted)]">{local.schemaNew}: </span>
              {newFields.length ? newFields.join(', ') : isZh ? '（无）' : '(none)'}
            </li>
          </ul>
        </div>
        {qualityGaps.length > 0 && (
          <div className="rounded-lg border p-2" style={{ borderColor: 'var(--border)', background: 'color-mix(in srgb, var(--bg-panel) 98%, transparent)' }}>
            <p className="text-[10px] font-medium text-[var(--text-muted)] mb-1.5">{local.datasetDeltaTitle}</p>
            <ul className="text-[11px] text-[var(--text-dim)] list-disc pl-4 space-y-0.5">
              {qualityGaps.map((g) => (
                <li key={g}>{g}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    )
  } else if (block === 'dag') {
    body = (
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text)]">
            <Network className="w-5 h-5 text-[var(--de-cyan)]" />
            {t.operatorEvolution} / {t.dagTabs}
          </div>
          {metricRow(activeDag?.metrics)}
        </div>
        <EmbeddedOperatorSubDag dag={rowDagResolved} operatorPool={operatorPool} caption={local.subDagCaption} />
        <div className="rounded-lg border px-2 py-2" style={{ borderColor: 'var(--border)', background: 'color-mix(in srgb, var(--bg-panel) 98%, transparent)' }}>
          <p className="text-[10px] text-[var(--text-muted)] mb-1.5">{local.validationTitle}</p>
          <div className="flex items-center gap-2 text-xs text-[var(--text)]">
            {rowUi.orchVal.is_valid ? (
              <CheckCircle2 className="w-4 h-4 shrink-0 text-[var(--de-green)]" />
            ) : (
              <AlertCircle className="w-4 h-4 shrink-0 text-[var(--de-orange)]" />
            )}
            <span>{rowUi.orchVal.is_valid ? local.validationValid : local.validationInvalid}</span>
          </div>
          {(rowUi.orchVal.validation_issues?.length ?? 0) > 0 ? (
            <ul className="mt-2 text-[10px] text-[var(--text-dim)] space-y-1 list-disc pl-4">
              {rowUi.orchVal.validation_issues.map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          ) : null}
        </div>
        <div className="grid md:grid-cols-2 gap-2">
          <div className="rounded-lg border p-2.5" style={{ borderColor: 'var(--border)', background: 'color-mix(in srgb, var(--bg-panel) 99%, transparent)' }}>
            <p className="text-[10px] text-[var(--text-muted)] mb-1.5 flex items-center gap-1">
              <BarChart3 className="w-3 h-3" />
              {local.evalSummary}
            </p>
            <p className="text-xs text-[var(--text-dim)] leading-relaxed">{rowUi.judge.overall_assessment || '—'}</p>
            <div className="mt-2 text-[10px] text-[var(--text-muted)]">
              {local.judgeGap}: <span className="text-[var(--text)]">{String(rowUi.judge.has_differences)}</span>
            </div>
          </div>
          <div className="rounded-lg border p-2.5" style={{ borderColor: 'var(--border)', background: 'color-mix(in srgb, var(--bg-panel) 99%, transparent)' }}>
            <p className="text-[10px] text-[var(--text-muted)] mb-1.5 flex items-center gap-1">
              <Lightbulb className="w-3 h-3" />
              {t.experience}
            </p>
            <ul className="space-y-1 text-[10px] text-[var(--text-dim)] list-disc pl-4">
              {[
                ...(rowUi.judge.critical_insights ?? []).slice(0, 2),
                ...rowUi.experiences.slice(0, 3),
              ]
                .slice(0, 5)
                .map((x) => (
                  <li key={x}>{x}</li>
                ))}
            </ul>
          </div>
        </div>
        {row.dagTabs.length > 0 && (
          <div>
            <p className="text-[10px] text-[var(--text-muted)] mb-1.5">{local.switchTab}</p>
            <div className="flex flex-wrap gap-1.5">
              {row.dagTabs.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => onSelectDagTab(rowId, tab.id)}
                  className="text-[10px] px-2 py-1 rounded-lg border transition-colors"
                  style={dagTabStyle(tab, row.activeDagTabId)}
                >
                  {tab.title}
                  {dagTabStatusMark(tab)}
                </button>
              ))}
            </div>
          </div>
        )}
        <p
          className="text-xs"
          style={{
            color: activeDag?.status === 'failed' ? 'var(--de-orange)' : 'var(--text-dim)',
          }}
        >
          {activeDag?.summary}
        </p>
        <div className="rounded-lg border p-2" style={{ borderColor: 'var(--border)', background: 'color-mix(in srgb, var(--bg-panel) 99%, transparent)' }}>
          <p className="text-[10px] text-[var(--text-muted)] mb-2 flex items-center gap-1">
            <Network className="w-3 h-3" />
            {local.dagStructure}
          </p>
          <ul className="space-y-1.5 text-[10px] text-[var(--text-dim)]">
            {rowDagResolved.nodes.map((n) => (
              <li key={n.node_id} className="flex items-start gap-2">
                <CheckCircle2 className="w-3 h-3 shrink-0 mt-0.5 text-[var(--de-green)]" />
                <span>
                  <span className="font-mono text-[var(--text)]">{n.node_name}</span>
                  <span className="text-[var(--text-muted)]"> · {n.description}</span>
                  <span className="block text-[var(--text-muted)] mt-0.5">
                    in: [{(n.input_keys ?? []).join(', ')}] → out: [{(n.output_keys ?? []).join(', ')}]
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-lg border p-2" style={{ borderColor: 'var(--border)', background: 'color-mix(in srgb, var(--bg-panel) 99%, transparent)' }}>
          <p className="text-[10px] text-[var(--text-muted)] mb-2">{local.dagEdges}</p>
          <ul className="space-y-1 text-[10px] text-[var(--text-dim)]">
            {rowDagResolved.edges.map((e) => (
              <li key={`${e.from_node}-${e.to_node}`} className="flex items-center gap-1 font-mono">
                <span>{e.from_node}</span>
                <ArrowRight className="w-3 h-3 text-[var(--de-cyan)]" />
                <span>{e.to_node}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    )
  } else if (block === 'inst') {
    body = (
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text)]">
            <Code2 className="w-5 h-5 text-[var(--de-orange)]" />
            {t.instantiation}
          </div>
          <span className="text-[10px] text-[var(--text-muted)]">
            {row.instantiationCards.length} {local.instCards}
          </span>
        </div>
        {row.instantiationMeta ? (
          <p
            className="text-[10px] rounded-lg border px-2 py-1.5"
            style={{
              borderColor: 'var(--border)',
              color: row.instantiationMeta.reused ? 'var(--de-orange)' : 'var(--text-dim)',
              background: 'color-mix(in srgb, var(--bg-panel) 96%, transparent)',
            }}
          >
            {row.instantiationMeta.reused
              ? isZh
                ? '实例化：复用已有产物（未调用 LLM）'
                : 'Instantiation: reused existing artifacts (no LLM)'
              : row.instantiationMeta.llm_codegen
                ? isZh
                  ? `实例化：LLM 参与步骤 — ${(row.instantiationMeta.llm_steps ?? []).join(', ') || '是'}`
                  : `Instantiation: LLM steps — ${(row.instantiationMeta.llm_steps ?? []).join(', ') || 'yes'}`
                : isZh
                  ? row.instantiationMeta.note ??
                    '实例化：内置算子模板委托（本 DAG 未触发 LLM 写码）'
                  : row.instantiationMeta.note ??
                    'Instantiation: builtin delegate templates (no LLM codegen for this DAG)'}
          </p>
        ) : null}
        <EmbeddedOperatorSubDag dag={rowDagResolved} operatorPool={operatorPool} caption={local.subDagCaption} compact />
        <div className="space-y-3 max-h-[50vh] overflow-y-auto pr-1">
          {row.instantiationCards.length === 0 ? (
            <p className="text-xs text-[var(--text-muted)]">{t.pending}</p>
          ) : (
            row.instantiationCards.map((card, i) => {
              return (
                <div key={card.id} className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border)' }}>
                  <div className="flex items-center justify-between gap-2 px-3 py-2 border-b text-xs" style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}>
                    <span className="font-medium text-[var(--text)] flex items-center gap-1.5">
                      <Code2 className="w-3.5 h-3.5 text-[var(--de-cyan)]" />
                      {card.name}
                      {card.llmGenerated ? (
                        <span className="text-[9px] px-1 rounded border" style={{ borderColor: 'var(--de-cyan)', color: 'var(--de-cyan)' }}>
                          LLM
                        </span>
                      ) : null}
                    </span>
                    <span className="text-[10px] text-[var(--text-muted)]">{metricText(card.metrics)}</span>
                  </div>
                  <div className="grid md:grid-cols-[1fr_minmax(0,200px)] gap-2 p-2">
                    <pre
                      className="text-[10px] font-mono p-2 rounded-lg overflow-x-auto max-h-48 overflow-y-auto"
                      style={{
                        background: 'var(--code-bg)',
                        border: '1px solid var(--border)',
                        color: 'var(--text-dim)',
                      }}
                    >
                      {card.code || '# code'}
                    </pre>
                    <div className="rounded-lg border p-2 text-[10px] space-y-1" style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}>
                      <div className="flex items-center gap-1 text-[var(--text-muted)]">
                        <FileJson2 className="w-3 h-3" />
                        {local.jsonSpec}
                      </div>
                      <pre className="font-mono text-[var(--text-dim)] whitespace-pre-wrap break-all">
                        {JSON.stringify(
                          {
                            operator: card.name,
                            step_index: i + 1,
                            summary: card.summary,
                            tokens: card.metrics.tokens,
                          },
                          null,
                          2
                        )}
                      </pre>
                    </div>
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>
    )
  } else if (block === 'sample') {
    body = (
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text)]">
            <BarChart3 className="w-5 h-5 text-[var(--de-teal)]" />
            {t.sampleEval}
          </div>
          {metricRow(row.sampleMetrics)}
        </div>
        <div
          className="flex items-center gap-3 rounded-xl border p-3"
          style={{ borderColor: 'var(--border)', background: 'color-mix(in srgb, var(--bg-panel) 98%, transparent)' }}
        >
          <div className="text-2xl font-bold text-[var(--de-cyan)]">{row.sampleScore ?? '—'}</div>
          <div className="text-xs text-[var(--text-dim)]">
            <p>{t.llmScore}</p>
            <p className="text-[10px] text-[var(--text-muted)] mt-1">
              {local.improve} {scoreDelta >= 0 ? '+' : ''}
              {scoreDelta}
            </p>
          </div>
        </div>
        <div className="rounded-lg border p-2" style={{ borderColor: 'var(--border)', background: 'color-mix(in srgb, var(--bg-panel) 98%, transparent)' }}>
          <p className="text-[10px] text-[var(--text-muted)] mb-1 flex items-center gap-1">
            <BarChart3 className="w-3 h-3" />
            {local.evalSummary}
          </p>
          <p className="text-xs text-[var(--text-dim)] leading-relaxed">{rowUi.judge.overall_assessment}</p>
          <div className="mt-2 flex items-center gap-2 text-[10px]">
            <AlertCircle className="w-3.5 h-3.5 text-[var(--de-orange)]" />
            <span className="text-[var(--text-muted)]">{local.judgeGap}:</span>
            <span className="text-[var(--text)]">{String(rowUi.judge.has_differences)}</span>
          </div>
        </div>
        <div>
          <p className="text-[10px] text-[var(--text-muted)] mb-1.5 flex items-center gap-1">
            <Lightbulb className="w-3 h-3" />
            {local.insights}
          </p>
          <ul className="space-y-1.5">
            {(rowUi.judge.critical_insights ?? []).map((ins) => (
              <li
                key={ins}
                className="text-xs text-[var(--text-dim)] flex gap-2 rounded-lg border px-2 py-1.5"
                style={{ borderColor: 'color-mix(in srgb, var(--border) 90%, transparent)' }}
              >
                <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-[var(--de-green)] mt-0.5" />
                {ins}
              </li>
            ))}
          </ul>
        </div>
      </div>
    )
  } else if (block === 'exp') {
    body = (
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text)]">
            <Lightbulb className="w-5 h-5 text-[var(--de-orange)]" />
            {t.experience}
          </div>
          {metricRow(row.experienceMetrics)}
        </div>
        {row.experienceMeta ? (
          <p className="text-[10px] text-[var(--text-muted)] mb-2">
            {row.experienceMeta.detail ??
              (isZh ? '经验为规则聚合，非 LLM 逐步生成' : 'Experience is rule-aggregated, not LLM-generated')}
          </p>
        ) : null}
        <ExperienceDraftEditor initial={row.experience ?? ''} hint={local.expReflowHint} />
        <div className="rounded-lg border p-2" style={{ borderColor: 'var(--border)', background: 'color-mix(in srgb, var(--bg-panel) 98%, transparent)' }}>
          <p className="text-[10px] text-[var(--text-muted)] mb-1 flex items-center gap-1">
            <FileJson2 className="w-3.5 h-3.5" />
            {local.memory} · JSON
          </p>
          <pre className="text-[10px] font-mono max-h-32 overflow-auto" style={{ color: 'var(--text-muted)' }}>
            {JSON.stringify(
              {
                next_round_constraints: rowUi.experiences,
                implicit_quality: rowUi.judge.implicit_quality_requirements,
                iterate: row.needNext,
              },
              null,
              2
            )}
          </pre>
        </div>
      </div>
    )
  } else {
    body = <p className="text-xs text-[var(--text-dim)]">—</p>
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl max-h-[88vh] overflow-hidden flex flex-col rounded-2xl border shadow-2xl"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-2 border-b px-4 py-3" style={{ borderColor: 'var(--border)' }}>
          <h3 className="text-sm font-semibold text-[var(--text)] pr-6 leading-snug">{modalTitleForNode(nodeId, rows, t)}</h3>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-lg p-1.5 hover:opacity-80"
            style={{ color: 'var(--text-muted)' }}
            aria-label={local.close}
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="overflow-y-auto p-4">{body}</div>
        <div className="border-t px-4 py-2 flex justify-end" style={{ borderColor: 'var(--border)' }}>
          <button
            type="button"
            onClick={onClose}
            className="h-8 px-4 rounded-lg border text-xs"
            style={{ borderColor: 'var(--border)', color: 'var(--text-dim)' }}
          >
            {local.close}
          </button>
        </div>
      </div>
    </div>
  )
}

export function EvolutionCanvas({
  t,
  rows,
  operatorPool,
  totalMetrics,
  finished,
  pipelineId = null,
  liveArtifacts = null,
  workflowState = null,
  workflowBusy = false,
  workflowExecutingStep = null,
  canRunFull = false,
  artifactHistoryCount: _artifactHistoryCount = 0,
  onStepForward,
  onAutoCompleteRound,
  onSelectDagTab,
  onRunFullData,
  onRerunFromCurrentStep,
  uploadPresence = { raw: false, seed: false, description: false },
}: EvolutionCanvasProps) {
  const [viewMode, setViewMode] = useState<'dag' | 'timeline'>('dag')
  const [detailModalNodeId, setDetailModalNodeId] = useState<string | null>(null)
  const [hoverNodeId, setHoverNodeId] = useState<string | null>(null)
  const [operatorDetailId, setOperatorDetailId] = useState<string | null>(null)
  const [operatorPoolCollapsed, setOperatorPoolCollapsed] = useState(false)
  const [insightRoundOverride, setInsightRoundOverride] = useState<number | null>(null)
  const [openRunSummary, setOpenRunSummary] = useState(false)
  const [metricsOpen, setMetricsOpen] = useState(false)

  const isZh = /推进|全量/.test(t.stepForward + t.runFullData)

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (detailModalNodeId) {
        e.preventDefault()
        setDetailModalNodeId(null)
        return
      }
      if (operatorDetailId) {
        e.preventDefault()
        setOperatorDetailId(null)
        return
      }
      if (openRunSummary) {
        e.preventDefault()
        setOpenRunSummary(false)
        return
      }
      if (metricsOpen) {
        e.preventDefault()
        setMetricsOpen(false)
      }
    }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [detailModalNodeId, operatorDetailId, openRunSummary, metricsOpen])

  const canvasUi = useMemo<CanvasUiBundle>(() => {
    if (!liveArtifacts) {
      return {
        understanding: EMPTY_UNDERSTANDING,
        dag: EMPTY_DAG,
        orchVal: EMPTY_ORCH_VALIDATION,
        judge: EMPTY_JUDGE,
        experiences: [],
      }
    }
    return {
      understanding: liveArtifacts.understanding ?? EMPTY_UNDERSTANDING,
      dag: liveArtifacts.dag ?? EMPTY_DAG,
      orchVal: liveArtifacts.orchestrationValidation ?? EMPTY_ORCH_VALIDATION,
      judge: liveArtifacts.judge ?? EMPTY_JUDGE,
      experiences: liveArtifacts.experienceBullets.length > 0 ? [...liveArtifacts.experienceBullets] : [],
    }
  }, [liveArtifacts])

  const local = {
    globalStatus: isZh ? '全局状态' : 'Global Status',
    phase: isZh ? '当前阶段' : 'Current Stage',
    iteration: isZh ? '当前轮次' : 'Current Iteration',
    quality: isZh ? '当前质量' : 'Quality',
    continueEvolve: isZh ? '继续演化' : 'Continue Evolution',
    readyToRun: isZh ? '可运行全量' : 'Ready for Full Run',
    manualCheck: isZh ? '建议人工介入' : 'Manual Review Suggested',
    dagView: isZh ? 'Pipeline DAG 视图' : 'Pipeline DAG View',
    timelineView: isZh ? 'Evolution Timeline 视图' : 'Evolution Timeline View',
    seedSpec: isZh ? 'Seed Profile' : 'Seed Profile',
    memory: isZh ? 'Experience Memory' : 'Experience Memory',
    nodeRole: isZh ? '节点职责' : 'Node Role',
    inputOutput: isZh ? '输入/输出示例' : 'Input/Output',
    whyNeeded: isZh ? '为什么需要' : 'Why Needed',
    qualityGain: isZh ? '质量贡献' : 'Quality Contribution',
    qualityPanel: isZh ? '质量对齐' : 'Quality Alignment',
    runSummary: isZh ? '全量运行前摘要' : 'Run Summary',
    cancel: isZh ? '取消' : 'Cancel',
    confirmRun: isZh ? '确认运行' : 'Confirm Run',
    estCost: isZh ? '预计全量成本' : 'Estimated Full Cost',
    estDuration: isZh ? '预计处理时长' : 'Estimated Duration',
    improve: isZh ? '较上一轮' : 'vs Previous',
    applyPipeline: isZh ? '应用当前 Pipeline 到全量数据' : 'Apply Current Pipeline to Full Data',
    evolveOneMore: isZh ? '再演化一轮' : 'Evolve One More Round',
    nodeDelta: isZh ? '节点变化' : 'Node Delta',
    constraints: isZh ? '新增约束' : 'New Constraints',
    structureReq: isZh ? '结构要求' : 'Structure',
    formatReq: isZh ? '格式要求' : 'Format',
    qualityReq: isZh ? '质量目标' : 'Quality',
    applied: isZh ? '已生效' : 'Applied',
    evidence: isZh ? '证据' : 'Evidence',
    inputSample: isZh ? '输入样本' : 'Input Sample',
    outputSample: isZh ? '输出样本' : 'Output Sample',
    trend: isZh ? '趋势' : 'Trend',
    estTokenDelta: isZh ? '本轮新增 Token' : 'Token Delta',
    valueHint: isZh ? '收益判断' : 'Value Signal',
    high: isZh ? '高' : 'High',
    medium: isZh ? '中' : 'Medium',
    low: isZh ? '低' : 'Low',
    detailPanel: isZh ? '节点详情' : 'Node Details',
    hoverTip: isZh ? '悬浮预览' : 'Hover Preview',
    introducedIn: isZh ? '引入轮次' : 'Introduced In',
    metricWindow: isZh ? 'Token/时间统计' : 'Token/Time Stats',
    hide: isZh ? '隐藏' : 'Hide',
    show: isZh ? '展开' : 'Show',
    perRound: isZh ? '分轮统计' : 'Per Iteration',
    basedOn: isZh ? '基于真实接口语义' : 'Backed by real interface semantics',
    judgeGap: isZh ? '是否存在差距' : 'Has Differences',
    insightCount: isZh ? '关键洞察数' : 'Insights',
    expCount: isZh ? '经验条目数' : 'Experience Items',
    instCards: isZh ? '个步骤' : 'steps',
    pipelineLegendActive: isZh ? '进行中' : 'Active',
    pipelineLegendDone: isZh ? '已完成' : 'Done',
    pipelineLegendPending: isZh ? '待执行' : 'Pending',
    pipelineLegendError: isZh ? '需关注' : 'Attention',
    validationTitle: isZh ? '约束搜索验证 constrained_search' : 'Constrained search validation',
    validationValid: isZh ? '校验通过' : 'Valid',
    validationInvalid: isZh ? '未通过' : 'Invalid',
    schemaSummary: isZh ? 'schema_analysis 要点' : 'Schema highlights',
    schemaRaw: isZh ? '原始字段' : 'Raw fields',
    schemaSeed: isZh ? 'Seed 字段' : 'Seed fields',
    schemaNew: isZh ? '新增字段' : 'New fields',
    datasetDeltaTitle: isZh ? 'dataset_level_delta' : 'Dataset-level delta',
    subDagCaption: isZh ? '当前编排算子子图' : 'Operator sub-DAG (pool-aligned chips)',
    expReflowHint: isZh
      ? '可编辑经验摘要；接入 advance API 后将写入 data/experiences 并回流至下一轮理解（当前仅本地草稿）。'
      : 'Editable experience; with advance API will persist to data/experiences and feed next understanding (local draft now).',
    issueTags: isZh ? '问题类型' : 'Issue Tags',
    runApproval: isZh ? '运行批准' : 'Run Approval',
    runNow: isZh ? '确认应用并运行' : 'Confirm Apply & Run',
    completedAt: isZh ? '完成耗时' : 'Elapsed',
    thinking: isZh ? '思路与要点' : 'Reasoning',
    dagStructure: isZh ? 'DAG 结构' : 'DAG Structure',
    codeImpl: isZh ? '代码实现' : 'Code',
    jsonSpec: isZh ? 'JSON 规格' : 'JSON Spec',
    evalSummary: isZh ? '评估摘要' : 'Evaluation',
    insights: isZh ? '关键洞察' : 'Insights',
    switchTab: isZh ? '切换编排版本' : 'Switch DAG version',
    close: isZh ? '关闭' : 'Close',
    roundPrefix: isZh ? '轮次' : 'Round',
    opDetailBadge: isZh ? '算子' : 'Operator',
    opDesc: isZh ? '说明' : 'Description',
    opUpdated: isZh ? '最近更新' : 'Last updated',
    opRegistry: isZh ? '注册信息' : 'Registry',
    opRequiresLlm: isZh ? '需要 LLM' : 'Requires LLM',
    opMetaJson: isZh ? '结构化元数据' : 'Structured metadata',
    opFieldCategory: isZh ? '类别' : 'Category',
    sectionGlobalSub: isZh ? '阶段、质量、算子池与运行控制总览' : 'Phase, quality, operator pool & run controls',
    runningStep: isZh ? '执行中步骤' : 'Running Step',
    sectionPipeline: isZh ? '流水线画布' : 'Pipeline Canvas',
    sectionPipelineSub: isZh ? '多轮 DAG 流程与步骤节点（可点击看详情）' : 'Multi-round DAG flow & steps (click for details)',
    sectionDetails: isZh ? '关键细节' : 'Key Details',
    sectionDetailsSub: isZh
      ? '种子规格、经验与质量指标——按轮次对照上面流水线'
      : 'Seed spec, experience & quality — align with rounds above',
    detailFollowActive: isZh ? '当前活跃轮' : 'Active round',
    detailRoundLabel: isZh ? '轮次' : 'Round',
    seedGlobalNote: isZh ? '全局对齐目标（作用于所有轮次）' : 'Global alignment target (all rounds)',
    seedGlobalBadge: isZh ? '全局' : 'Global',
    expForRound: isZh ? '本轮经验摘要' : 'Experience this round',
    qualityForRound: isZh ? '本轮质量快照' : 'Quality snapshot',
    noRoundData: isZh ? '暂无该轮数据' : 'No data for this round',
    rerunFromCurrentStep: isZh ? '重跑当前步骤' : 'Rerun current step',
  }

  const allScores = rows
    .map((row) => row.sampleScore)
    .filter((score): score is number => typeof score === 'number')
  const currentScore = allScores[allScores.length - 1] ?? 0
  const prevScore = allScores.length > 1 ? allScores[allScores.length - 2] : 0
  const scoreDelta = currentScore - prevScore

  const activeRow = rows.find((row) => !row.completed) ?? rows[rows.length - 1]
  const currentIteration =
    typeof workflowState?.round === 'number' && workflowState.round > 0
      ? workflowState.round
      : activeRow?.id ?? rows.length
  const displayedRound =
    rows.find((r) => r.id === (insightRoundOverride ?? activeRow?.id ?? rows[0]?.id)) ?? rows[rows.length - 1]

  const phaseFromWorkflowState = useMemo(() => {
    if (!workflowState) return null
    if (workflowState.ready_for_full_run || workflowState.next_action === 'run_full' || workflowState.is_complete) {
      return 'Ready'
    }
    const order = Array.isArray(workflowState.step_order) ? workflowState.step_order : []
    const idx = workflowState.step_index
    if (idx < 0 || idx >= order.length) return 'Idle'
    const step = order[idx]
    const map: Record<string, string> = {
      understanding: 'Understanding',
      orchestration: 'Orchestration',
      operator_evolution: 'Evolution',
      instantiation: 'Instantiation',
      trial_run: 'Trial',
      quality_check: 'Quality Check',
      experience: 'Experience',
    }
    return map[step] ?? 'Idle'
  }, [workflowState])

  const phase = (() => {
    if (phaseFromWorkflowState) return phaseFromWorkflowState
    if (!activeRow) return 'Idle'
    if (!activeRow.understandingDone) return 'Understanding'
    if (!activeRow.dagTabs.some((tab) => tab.status === 'passed')) return 'Orchestration'
    if (activeRow.instantiationCards.length === 0) return 'Instantiation'
    if (activeRow.sampleScore === undefined) return 'Trial'
    if (!activeRow.experience) return 'Evolution'
    return finished ? 'Ready' : 'Evolution'
  })()

  const recommendation = (() => {
    if (canRunFull || finished) return local.readyToRun
    if (workflowState) {
      if (workflowState.ready_for_full_run || workflowState.next_action === 'run_full') return local.readyToRun
      if (
        workflowState.next_action === 'advance' &&
        (workflowState.round ?? 1) > 1 &&
        workflowState.quality_passed === false
      ) {
        return local.continueEvolve
      }
      if ((workflowState.last_message ?? '').includes('re-orchestrate')) return local.continueEvolve
      return local.manualCheck
    }
    if (scoreDelta > 3) return local.continueEvolve
    return local.manualCheck
  })()

  const runningStepLabel = useMemo(() => {
    if (!workflowExecutingStep) return null
    const map: Record<string, string> = isZh
      ? {
          understanding: '理解',
          orchestration: '编排',
          operator_evolution: '算子进化',
          instantiation: '实例化',
          trial_run: '试运行',
          quality_check: '质检',
          experience: '经验回流',
        }
      : {
          understanding: 'Understanding',
          orchestration: 'Orchestration',
          operator_evolution: 'Operator Evolution',
          instantiation: 'Instantiation',
          trial_run: 'Trial Run',
          quality_check: 'Quality Check',
          experience: 'Experience',
        }
    return map[workflowExecutingStep] ?? workflowExecutingStep
  }, [workflowExecutingStep, isZh])

  /* 本版暂不展示：本轮新增 Token、收益判断（恢复时取消注释并取消下方 JSX 注释）
  const tokenDelta = rows.length > 1 ? Math.floor(totalMetrics.tokens / rows.length) : totalMetrics.tokens
  const valueSignal = scoreDelta >= 8 ? local.high : scoreDelta >= 3 ? local.medium : local.low
  */

  const experienceItems = [
    ...(canvasUi.judge.critical_insights ?? []).slice(0, 2),
    ...canvasUi.experiences.slice(0, 2),
  ].slice(0, 4)

  const snapshotScore =
    typeof displayedRound?.sampleScore === 'number' ? displayedRound.sampleScore : undefined
  const qualityBarsSnapshot = useMemo(
    () =>
      typeof snapshotScore === 'number'
        ? [
            {
              key: 'training',
              name: 'Training Readiness',
              value: Math.min(96, Math.max(45, snapshotScore)),
            },
            {
              key: 'seed',
              name: 'Seed Alignment',
              value: Math.min(98, Math.max(48, snapshotScore + 2)),
            },
            {
              key: 'explain',
              name: 'Explanation Quality',
              value: Math.min(97, Math.max(42, snapshotScore - 1)),
            },
            {
              key: 'redundancy',
              name: 'Redundancy',
              value: Math.max(8, 100 - Math.min(95, snapshotScore + 6)),
            },
          ]
        : [],
    [snapshotScore]
  )

  const hoverNodeInfo = useMemo(() => {
    if (!hoverNodeId) return null
    const [rid, block] = hoverNodeId.split('-')
    const rowId = Number(rid.replace('r', ''))
    const row = rows.find((item) => item.id === rowId)
    const map: Record<string, string> = {
      raw: t.rawBlock,
      understanding: t.understanding,
      dag: t.dagTabs,
      inst: t.instantiation,
      sample: t.sampleEval,
      exp: t.experience,
    }
    return {
      title: map[block] ?? hoverNodeId,
      brief: `I${rowId} · ${row?.completed ? t.done : t.pending}`,
    }
  }, [hoverNodeId, rows, t])

  /** Token/时间面板：按迭代、按流水线步骤拆分 */
  const pipelineMetricsBreakdown = useMemo(() => {
    return rows.map((row) => {
      const steps: { id: string; label: string; sec: number | null; tokens: number | null }[] = []

      steps.push({
        id: `r${row.id}-understanding`,
        label: t.understanding,
        sec: row.understandingMetrics != null ? row.understandingMetrics.sec : null,
        tokens: row.understandingMetrics != null ? row.understandingMetrics.tokens : null,
      })

      if (row.dagTabs.length === 0) {
        steps.push({
          id: `r${row.id}-dag-pending`,
          label: isZh ? `${t.dagTabs}（待开始）` : `${t.dagTabs} (pending)`,
          sec: null,
          tokens: null,
        })
      } else {
        row.dagTabs.forEach((tab) => {
          steps.push({
            id: `r${row.id}-dag-${tab.id}`,
            label: isZh ? `${t.dagTabs} · ${tab.title}` : `${t.dagTabs} · ${tab.title}`,
            sec: tab.metrics.sec,
            tokens: tab.metrics.tokens,
          })
        })
      }

      if (row.instantiationCards.length === 0) {
        steps.push({
          id: `r${row.id}-inst-pending`,
          label: isZh ? `${t.instantiation}（待开始）` : `${t.instantiation} (pending)`,
          sec: null,
          tokens: null,
        })
      } else {
        row.instantiationCards.forEach((card) => {
          steps.push({
            id: `r${row.id}-inst-${card.id}`,
            label: isZh ? `${t.instantiation} · ${card.name}` : `${t.instantiation} · ${card.name}`,
            sec: card.metrics.sec,
            tokens: card.metrics.tokens,
          })
        })
      }

      steps.push({
        id: `r${row.id}-sample`,
        label: t.sampleEval,
        sec: row.sampleMetrics != null ? row.sampleMetrics.sec : null,
        tokens: row.sampleMetrics != null ? row.sampleMetrics.tokens : null,
      })

      steps.push({
        id: `r${row.id}-exp`,
        label: t.experience,
        sec: row.experienceMetrics != null ? row.experienceMetrics.sec : null,
        tokens: row.experienceMetrics != null ? row.experienceMetrics.tokens : null,
      })

      const subtotalSec =
        (row.understandingMetrics?.sec ?? 0) +
        row.dagTabs.reduce((sum, tab) => sum + tab.metrics.sec, 0) +
        row.instantiationCards.reduce((sum, card) => sum + card.metrics.sec, 0) +
        (row.sampleMetrics?.sec ?? 0) +
        (row.experienceMetrics?.sec ?? 0)
      const subtotalTokens =
        (row.understandingMetrics?.tokens ?? 0) +
        row.dagTabs.reduce((sum, tab) => sum + tab.metrics.tokens, 0) +
        row.instantiationCards.reduce((sum, card) => sum + card.metrics.tokens, 0) +
        (row.sampleMetrics?.tokens ?? 0) +
        (row.experienceMetrics?.tokens ?? 0)

      return { rowId: row.id, steps, subtotalSec, subtotalTokens }
    })
  }, [rows, t, isZh])

  const flow = useMemo(() => {
    const nodes: Node[] = []
    const edges: Edge[] = []
    const pipelineLevelLabel = isZh ? 'Pipeline-level 进化' : 'Pipeline-level evolution'
    const activeRowForCanvas = rows.find((r) => !r.completed) ?? rows[rows.length - 1]
    const runningBlockForStep = (step: string | null | undefined): 'understanding' | 'dag' | 'inst' | 'sample' | 'exp' | null => {
      if (!step) return null
      if (step === 'understanding') return 'understanding'
      if (step === 'orchestration' || step === 'operator_evolution') return 'dag'
      if (step === 'instantiation') return 'inst'
      if (step === 'trial_run' || step === 'quality_check') return 'sample'
      if (step === 'experience') return 'exp'
      return null
    }
    const runningBlock = workflowBusy ? runningBlockForStep(workflowExecutingStep) : null
    const runningText = isZh ? '执行中...' : 'Running...'
    const GAP = 44
    let yCursor = 40

    rows.forEach((row) => {
      const rowDag = resolveDagForRow(row, resolveRowUi(row, canvasUi).dag)
      const dagCardMetrics = computeOrchestrationDagCardMetrics(rowDag)
      const rowPitch = Math.max(420, dagCardMetrics.cardHeight + 140)
      const y = yCursor
      yCursor += rowPitch
      const prefix = `r${row.id}`
      let xCursor = 40

      const rawLabel = (
        <div className="min-w-0">
          <p className="text-[11px] font-semibold leading-tight text-[var(--text)]">
            {t.roundTitle} {row.id} · {isZh ? '流水线入口' : 'Pipeline entry'}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {(
              [
                { k: 'raw' as const, on: uploadPresence.raw, lab: 'R' },
                { k: 'seed' as const, on: uploadPresence.seed, lab: 'S' },
                { k: 'description' as const, on: uploadPresence.description, lab: 'D' },
              ] as const
            ).map((s) => (
              <span
                key={s.k}
                className="inline-flex min-w-[1.5rem] items-center justify-center rounded-md border px-1.5 py-0.5 text-[9px] font-bold tabular-nums"
                style={{
                  borderColor: s.on ? 'color-mix(in srgb, var(--de-cyan) 55%, var(--border))' : 'var(--border)',
                  color: s.on ? 'var(--de-cyan)' : 'var(--text-muted)',
                  background: s.on ? 'color-mix(in srgb, var(--de-cyan) 10%, transparent)' : 'transparent',
                  opacity: s.on ? 1 : 0.45,
                }}
              >
                {s.lab}
              </span>
            ))}
          </div>
          <p className="mt-2 text-[10px] leading-snug text-[var(--text-muted)]">
            {isZh ? '数据详情见左侧预览' : 'See preview on the left'}
          </p>
        </div>
      )

      const showRawEntry = row.id === 1
      let prevNodeId: string | null = null
      if (showRawEntry) {
        const rawW = 200
        const rawH = 118
        nodes.push(
          blockNode(
            `${prefix}-raw`,
            xCursor,
            y,
            `${t.roundTitle} ${row.id} · ${t.rawBlock}`,
            [],
            {
              title: t.rawBlock,
              role: isZh ? '入口' : 'Entry',
              io: isZh ? 'R / S / D' : 'R / S / D',
              reason: isZh ? '详情见左侧预览' : 'See left preview',
              gain: '—',
              tag: 'reused',
              introducedIn: row.id,
            },
            getPipelineBlockState(row, 'raw', activeRowForCanvas),
            rawW,
            rawH,
            rawLabel,
            false,
            runningText
          )
        )
        prevNodeId = `${prefix}-raw`
        xCursor += rawW + GAP
      }

      const undW = 220
      const undH = 104
      const showUnderstanding = row.id > 1 || row.understandingDone
      if (showUnderstanding) {
        nodes.push(
          blockNode(
            `${prefix}-understanding`,
            xCursor,
            y,
            t.understanding,
            [row.understandingDone ? t.done : t.pending, metricText(row.understandingMetrics)].filter(Boolean),
            {
              title: t.understanding,
              role: isZh ? '抽取 seed 目标规范' : 'Extract seed target specification',
              io: isZh ? 'raw+seed → profile' : 'raw+seed → profile',
              reason: isZh ? '将质量差距转为可执行约束。' : 'Convert quality gaps into executable constraints.',
              gain: isZh ? '后续编排更稳定。' : 'Stabilize later orchestration.',
              tag: 'reused',
              introducedIn: row.id,
            },
            getPipelineBlockState(row, 'understanding', activeRowForCanvas),
            undW,
            undH,
            undefined,
            runningBlock === 'understanding' && row.id === activeRowForCanvas?.id,
            runningText
          )
        )
        if (prevNodeId) {
          edges.push({
            id: `${prefix}-e-under`,
            source: prevNodeId,
            target: `${prefix}-understanding`,
            animated: true,
            markerEnd: { type: MarkerType.ArrowClosed },
            style: edgeStyle,
          })
        }
        prevNodeId = `${prefix}-understanding`
        xCursor += undW + GAP
      }

      const activeTab =
        row.dagTabs.find((tab) => tab.id === row.activeDagTabId) ?? row.dagTabs[row.dagTabs.length - 1]
      const dagLabel = (
        <div className="min-w-0">
          <p className="mb-2 text-xs font-semibold leading-snug text-[var(--text)]">
            {t.operatorEvolution} · {t.dagTabs}
          </p>
          {row.dagTabs.length > 0 ? (
            <div
              className="mb-2 flex flex-wrap gap-1.5"
              role="tablist"
              aria-label={isZh ? '编排轮次' : 'Orchestration rounds'}
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => e.stopPropagation()}
            >
              {row.dagTabs.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={tab.id === row.activeDagTabId}
                  onMouseDown={(e) => e.stopPropagation()}
                  onClick={(e) => {
                    e.stopPropagation()
                    onSelectDagTab(row.id, tab.id)
                  }}
                  className="rounded-lg border px-2 py-1 text-[10px] transition-colors"
                  style={dagTabStyle(tab, row.activeDagTabId)}
                >
                  {tab.title}
                  {dagTabStatusMark(tab)}
                </button>
              ))}
            </div>
          ) : null}
          <OrchestrationDagGridView
            dag={rowDag}
            operatorPool={operatorPool}
            isZh={isZh}
            subgraphSidePx={dagCardMetrics.subgraphSide}
          />
        </div>
      )
      if (row.dagTabs.length > 0) {
        nodes.push(
          blockNode(
            `${prefix}-dag`,
            xCursor,
            y,
            `${t.operatorEvolution} / ${t.dagTabs}`,
            [],
            {
              title: t.dagTabs,
              role: isZh ? '编排+检查+修复' : 'Orchestrate + validate + repair',
              io: activeTab ? `${activeTab.title} · ${activeTab.status}` : t.pending,
              reason: isZh ? 'dependency / interface / DAG' : 'dependency / interface / DAG',
              gain: isZh ? '可执行 DAG' : 'Executable DAG',
              tag: row.dagTabs.length > 1 ? 'new' : 'reused',
              introducedIn: row.id,
            },
            getPipelineBlockState(row, 'dag', activeRowForCanvas),
            dagCardMetrics.cardWidth,
            dagCardMetrics.cardHeight,
            dagLabel,
            runningBlock === 'dag' && row.id === activeRowForCanvas?.id,
            runningText
          )
        )
        edges.push({
          id: `${prefix}-e-dag`,
          source: prevNodeId ?? `${prefix}-understanding`,
          target: `${prefix}-dag`,
          animated: true,
          markerEnd: { type: MarkerType.ArrowClosed },
          style: edgeStyle,
        })
        prevNodeId = `${prefix}-dag`
        xCursor += dagCardMetrics.cardWidth + GAP
      }

      const instW = 384
      const instH = row.instantiationCards.length === 0 ? 120 : 56 + row.instantiationCards.length * 76
      const instLabel = (
        <div className="min-w-0 flex flex-col">
          <p
            className="text-xs font-semibold tracking-tight text-[var(--text)] pb-2 mb-0 border-b"
            style={{ borderColor: 'color-mix(in srgb, var(--border) 90%, transparent)' }}
          >
            {t.instantiation}
          </p>
          <div className="mt-2.5 space-y-2">
            {row.instantiationCards.length === 0 ? (
              <p className="text-[11px] text-[var(--text-muted)] leading-snug">{t.pending}</p>
            ) : (
              row.instantiationCards.map((card, instIdx) => (
                <div
                  key={card.id}
                  className="rounded-xl border px-2.5 py-2 shadow-sm"
                  style={{
                    borderColor: 'color-mix(in srgb, var(--de-cyan) 18%, var(--border))',
                    background: 'color-mix(in srgb, var(--bg-panel) 94%, transparent)',
                  }}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-[9px] font-bold uppercase tracking-wider text-[var(--text-muted)] tabular-nums shrink-0">
                      {instIdx + 1}
                    </span>
                    <p className="min-w-0 flex-1 text-[11px] font-semibold leading-snug text-[var(--text)]">{card.name}</p>
                  </div>
                  <p className="text-[10px] text-[var(--text-dim)] leading-relaxed mt-1.5 line-clamp-3">{card.summary}</p>
                  <p className="text-[9px] text-[var(--text-muted)] mt-1.5 pt-1.5 border-t font-mono tabular-nums" style={{ borderColor: 'var(--border)' }}>
                    {metricText(card.metrics)}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>
      )
      if (row.instantiationCards.length > 0) {
        nodes.push(
          blockNode(
            `${prefix}-inst`,
            xCursor,
            y,
            t.instantiation,
            [],
            {
              title: t.instantiation,
              role: isZh ? '代码实例化' : 'Code instantiation',
              io: isZh ? `input: DAG  output: ${row.instantiationCards.length} cards` : `input: DAG  output: ${row.instantiationCards.length} cards`,
              reason: isZh ? '验证逻辑可落地运行。' : 'Validate executable implementation.',
              gain: isZh ? '降低全量运行风险。' : 'Reduce full-run risk.',
              tag: row.instantiationCards.length > 0 ? 'replaced' : 'default',
              introducedIn: row.id,
            },
            getPipelineBlockState(row, 'inst', activeRowForCanvas),
            instW,
            instH,
            instLabel,
            runningBlock === 'inst' && row.id === activeRowForCanvas?.id,
            runningText
          )
        )
        edges.push({
          id: `${prefix}-e-inst`,
          source: prevNodeId ?? `${prefix}-dag`,
          target: `${prefix}-inst`,
          animated: true,
          markerEnd: { type: MarkerType.ArrowClosed },
          style: edgeStyle,
        })
        prevNodeId = `${prefix}-inst`
        xCursor += instW + GAP
      }

      const sampleLlmParagraph =
        canvasUi.judge.overall_assessment?.trim() ||
        (canvasUi.judge.critical_insights ?? []).slice(0, 2).join(' ').trim() ||
        (isZh ? '（评估摘要将在质量检查完成后由 LLM 生成）' : '(LLM assessment summary appears after quality check.)')

      const sampleW = 268
      const sampleH = row.sampleScore === undefined ? 112 : 198
      const sampleLabel = (
        <div className="min-w-0 flex flex-col">
          <p
            className="text-xs font-semibold tracking-tight text-[var(--text)] pb-2 mb-0 border-b"
            style={{ borderColor: 'color-mix(in srgb, var(--border) 90%, transparent)' }}
          >
            {t.sampleEval}
          </p>
          {row.sampleScore === undefined ? (
            <p className="text-[11px] text-[var(--text-muted)] mt-2.5 leading-snug">{t.pending}</p>
          ) : (
            <>
              <div className="mt-3 flex flex-col gap-0.5">
                <span className="text-[11px] font-medium text-[var(--text-muted)]">{t.llmScore}</span>
                <span
                  className="text-[2.25rem] font-bold tabular-nums leading-none tracking-tight"
                  style={{ color: 'var(--de-cyan)' }}
                >
                  {row.sampleScore}
                </span>
                {row.sampleMetrics ? (
                  <span className="text-[11px] text-[var(--text-muted)] mt-1 font-mono">{metricText(row.sampleMetrics)}</span>
                ) : null}
              </div>
              <p
                className="text-[11px] leading-relaxed text-[var(--text-dim)] mt-3 pt-3 border-t"
                style={{ borderColor: 'color-mix(in srgb, var(--border) 90%, transparent)' }}
              >
                {sampleLlmParagraph}
              </p>
            </>
          )}
        </div>
      )
      if (row.sampleScore !== undefined) {
        nodes.push(
          blockNode(
            `${prefix}-sample`,
            xCursor,
            y,
            t.sampleEval,
            [],
            {
              title: t.sampleEval,
              role: isZh ? '小样本质量判断' : 'Sample quality judgment',
              io: `${t.llmScore}: ${row.sampleScore ?? '-'}`,
              reason: (canvasUi.judge.critical_insights ?? [])[0] ?? '-',
              gain: isZh ? '决定是否继续演化。' : 'Decide whether to continue evolution.',
              tag: 'reused',
              introducedIn: row.id,
            },
            getPipelineBlockState(row, 'sample', activeRowForCanvas),
            sampleW,
            sampleH,
            sampleLabel,
            runningBlock === 'sample' && row.id === activeRowForCanvas?.id,
            runningText
          )
        )
        edges.push({
          id: `${prefix}-e-sample`,
          source: prevNodeId ?? `${prefix}-inst`,
          target: `${prefix}-sample`,
          animated: true,
          markerEnd: { type: MarkerType.ArrowClosed },
          style: edgeStyle,
        })
        prevNodeId = `${prefix}-sample`
        xCursor += sampleW + GAP
      }

      const expW = 360
      const expH = row.experience ? 168 : 108
      const expLabel = (
        <div className="min-w-0 flex flex-col">
          <p
            className="text-xs font-semibold tracking-tight text-[var(--text)] pb-2 mb-0 border-b"
            style={{ borderColor: 'color-mix(in srgb, var(--border) 90%, transparent)' }}
          >
            {t.experience}
          </p>
          {!row.experience ? (
            <p className="text-[11px] text-[var(--text-muted)] mt-2.5 leading-snug">{t.pending}</p>
          ) : (
            <div className="mt-2.5 space-y-2">
              <div
                className="rounded-xl border px-2.5 py-2.5"
                style={{
                  borderColor: 'color-mix(in srgb, var(--de-orange) 22%, var(--border))',
                  background: 'color-mix(in srgb, var(--bg-panel) 96%, transparent)',
                }}
              >
                <p className="text-[11px] leading-relaxed text-[var(--text-dim)]">{row.experience}</p>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 text-[10px]">
                <span
                  className="font-semibold"
                  style={{ color: row.needNext ? 'var(--de-orange)' : 'var(--de-green)' }}
                >
                  {row.needNext ? t.willIterate : t.qualityOk}
                </span>
                {row.experienceMetrics ? (
                  <span className="text-[var(--text-muted)] font-mono tabular-nums">{metricText(row.experienceMetrics)}</span>
                ) : null}
              </div>
            </div>
          )}
        </div>
      )
      if (row.experience) {
        nodes.push(
          blockNode(
            `${prefix}-exp`,
            xCursor,
            y,
            t.experience,
            [],
            {
              title: t.experience,
              role: isZh ? '经验回流约束' : 'Experience feedback constraints',
              io: canvasUi.experiences[0] ?? '-',
              reason: isZh ? '将评估差距回写下一轮。' : 'Feed evaluation gaps into next round.',
              gain: isZh ? '迭代越跑越准。' : 'Improve quality across iterations.',
              tag: row.needNext ? 'new' : 'reused',
              introducedIn: row.id,
            },
            getPipelineBlockState(row, 'exp', activeRowForCanvas),
            expW,
            expH,
            expLabel,
            runningBlock === 'exp' && row.id === activeRowForCanvas?.id,
            runningText
          )
        )
        edges.push({
          id: `${prefix}-e-exp`,
          source: prevNodeId ?? `${prefix}-sample`,
          target: `${prefix}-exp`,
          animated: true,
          markerEnd: { type: MarkerType.ArrowClosed },
          style: edgeStyle,
        })
        prevNodeId = `${prefix}-exp`
      }

      if (row.needNext) {
        const nextTarget = row.id + 1 > 1 ? `r${row.id + 1}-understanding` : `r${row.id + 1}-raw`
        edges.push({
          id: `${prefix}-to-next`,
          source: prevNodeId ?? `${prefix}-understanding`,
          target: nextTarget,
          type: 'smoothstep',
          animated: true,
          markerEnd: { type: MarkerType.ArrowClosed },
          style: { ...edgeStyle, stroke: 'var(--de-orange)', strokeWidth: 2.75 },
          label: pipelineLevelLabel,
          labelStyle: {
            fill: 'var(--de-orange)',
            fontSize: 9,
            fontWeight: 700,
          },
          labelBgStyle: { fill: 'var(--bg-card)', fillOpacity: 0.92 },
          labelBgPadding: [4, 8] as [number, number],
          labelBgBorderRadius: 8,
        })
      }
    })

    return { nodes, edges }
  }, [rows, t, isZh, canvasUi, uploadPresence, operatorPool, onSelectDagTab, workflowBusy, workflowExecutingStep])

  const operatorKindLabel = (k: OperatorKind) =>
    ({
      io: isZh ? 'I/O' : 'I/O',
      transform: isZh ? '变换' : 'Transform',
      quality: isZh ? '质检' : 'Quality',
      llm: isZh ? 'LLM' : 'LLM',
      evolved: isZh ? '进化' : 'Evolved',
    })[k]

  const operatorDetailOp = operatorDetailId ? operatorPool.find((o) => o.id === operatorDetailId) : undefined

  return (
    <section
      className="rounded-2xl border px-3 py-3 pb-24 min-h-[calc(100vh-7.5rem)] flex flex-col overflow-visible relative"
      style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
    >
      {/* ① 算子池 */}
      <div className="pb-2 shrink-0">
        <div className="evolution-operator-pool-shell">
          <div className="evolution-operator-pool-shimmer" aria-hidden />
          <div className="evolution-operator-pool-glow" aria-hidden />
          <div className="evolution-operator-pool-particles" aria-hidden />
          <div className="relative z-[1]">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-[var(--text)]">{t.operatorPool}</p>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setOperatorPoolCollapsed((v) => !v)}
                  className="text-[10px] px-2 py-0.5 rounded-md border"
                  style={{ borderColor: 'var(--border)', color: 'var(--text-muted)', background: 'color-mix(in srgb, var(--bg-panel) 55%, transparent)' }}
                >
                  {operatorPoolCollapsed ? (isZh ? '展开' : 'Expand') : isZh ? '折叠' : 'Collapse'}
                </button>
                <span
                  className="text-[10px] tabular-nums px-1.5 py-0.5 rounded-md text-[var(--text-muted)]"
                  style={{ background: 'color-mix(in srgb, var(--bg-panel) 55%, transparent)' }}
                >
                  {operatorPool.length}
                </span>
              </div>
            </div>
            <p className="text-[10px] text-[var(--text-muted)] mt-0.5 leading-snug line-clamp-2">{t.operatorHint}</p>
            <div className="evolution-operator-pool-scroll" style={{ display: operatorPoolCollapsed ? 'none' : undefined }}>
              <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8 gap-1">
                {operatorPool.map((op) => {
                  const kind = inferOperatorKind(op)
                  const accent = operatorKindStyle(kind)
                  const categoryText = op.category?.trim() || operatorKindLabel(kind)
                  return (
                    <button
                      key={op.id}
                      type="button"
                      onClick={() => setOperatorDetailId(op.id)}
                      title={`${op.name} · ${categoryText}`}
                      className="relative z-[1] text-left rounded-md pl-1.5 pr-6 pt-1 pb-1 min-h-[2.15rem] transition-[transform,box-shadow] hover:brightness-[1.06] active:scale-[0.98] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--de-cyan)]"
                      style={{
                        border: `1px solid color-mix(in srgb, ${accent.dot} 38%, color-mix(in srgb, var(--border) 60%, transparent))`,
                        background: accent.background,
                      }}
                    >
                      <span
                        className="absolute right-0.5 top-0.5 w-[1.125rem] h-[1.125rem] rounded flex items-center justify-center"
                        style={{ background: `color-mix(in srgb, ${accent.dot} 28%, transparent)` }}
                        aria-hidden
                      >
                        <OperatorKindIcon kind={kind} color={accent.dot} />
                      </span>
                      <p className="text-[10px] font-semibold text-[var(--text)] leading-tight line-clamp-2 pr-0.5 break-all">
                        {op.name}
                      </p>
                      <p
                        className="text-[9px] mt-0.5 truncate font-medium leading-tight text-[var(--text-muted)]"
                        style={{ color: accent.dot }}
                      >
                        {categoryText}
                      </p>
                    </button>
                  )
                })}
              </div>
            </div>
          </div>
        </div>

        {operatorDetailOp ? (
          <OperatorDetailModal
            op={operatorDetailOp}
            onClose={() => setOperatorDetailId(null)}
            local={local}
            t={t}
            categoryLabel={operatorDetailOp.category?.trim() || operatorKindLabel(inferOperatorKind(operatorDetailOp))}
            kind={inferOperatorKind(operatorDetailOp)}
            accent={operatorKindStyle(inferOperatorKind(operatorDetailOp))}
            isZh={isZh}
          />
        ) : null}
      </div>

      {/* ② 流水线画布 */}
      <div className="pb-4 pt-1 flex-1 flex flex-col min-h-[min(640px,calc(100vh-14rem))]">
        <h2 className="text-sm font-bold text-[var(--text)] tracking-tight">{local.sectionPipeline}</h2>
        <p className="text-[10px] text-[var(--text-muted)] mt-0.5 leading-snug max-w-2xl">{local.sectionPipelineSub}</p>
        {pipelineId ? (
          <p className="text-[10px] text-[var(--de-cyan)] mt-1 font-mono">pipeline_id: {pipelineId}</p>
        ) : null}
        <div
          className="h-1 rounded-full mt-3 mb-3"
          style={{
            background: 'linear-gradient(90deg, var(--de-teal), transparent 70%)',
          }}
        />
        <div className="flex items-center justify-between mb-2 gap-2 flex-wrap shrink-0">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setViewMode('dag')}
              className="px-3 h-8 rounded-lg text-xs transition-colors"
              style={{
                color: viewMode === 'dag' ? 'var(--text)' : 'var(--text-dim)',
                background: viewMode === 'dag' ? 'var(--de-cyan-glow)' : 'color-mix(in srgb, var(--bg-card) 70%, transparent)',
              }}
            >
              {local.dagView}
            </button>
            <button
              type="button"
              onClick={() => setViewMode('timeline')}
              className="px-3 h-8 rounded-lg text-xs transition-colors"
              style={{
                color: viewMode === 'timeline' ? 'var(--text)' : 'var(--text-dim)',
                background: viewMode === 'timeline' ? 'var(--de-cyan-glow)' : 'color-mix(in srgb, var(--bg-card) 70%, transparent)',
              }}
            >
              {local.timelineView}
            </button>
          </div>
          <p className="text-xs text-[var(--text-dim)]">{t.progressHint}</p>
        </div>
        <div className="flex items-center gap-2 mb-2 text-[10px] shrink-0 flex-wrap">
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[var(--text-dim)]"
            style={{
              borderColor: 'color-mix(in srgb, var(--de-cyan) 45%, var(--border))',
              boxShadow: '0 0 0 1px color-mix(in srgb, var(--de-cyan) 28%, transparent), 0 0 14px color-mix(in srgb, var(--de-cyan) 12%, transparent)',
            }}
          >
            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: 'var(--de-cyan)' }} aria-hidden />
            {local.pipelineLegendActive}
          </span>
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[var(--text-dim)]"
            style={{ borderColor: 'color-mix(in srgb, var(--de-green) 35%, var(--border))' }}
          >
            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: 'var(--de-green)' }} aria-hidden />
            {local.pipelineLegendDone}
          </span>
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[var(--text-muted)]" style={{ borderColor: 'var(--border)' }}>
            <span className="w-1.5 h-1.5 rounded-full shrink-0 bg-[var(--border)]" aria-hidden />
            {local.pipelineLegendPending}
          </span>
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[var(--text-dim)]"
            style={{ borderColor: 'color-mix(in srgb, var(--de-orange) 40%, var(--border))' }}
          >
            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: 'var(--de-orange)' }} aria-hidden />
            {local.pipelineLegendError}
          </span>
        </div>

        <div
          className="relative w-full rounded-xl overflow-hidden h-[min(640px,calc(100vh-16rem))] min-h-[480px]"
          style={{ boxShadow: '0 0 0 1px color-mix(in srgb, var(--border) 55%, transparent)', background: 'var(--bg-card)' }}
        >
          {viewMode === 'dag' ? (
            <ReactFlowProvider>
              <ReactFlow
                className="h-full w-full"
                style={{ width: '100%', height: '100%' }}
                nodes={flow.nodes}
                edges={flow.edges}
                fitView
                minZoom={0.2}
                maxZoom={1.8}
                zoomOnScroll={false}
                zoomOnPinch
                defaultEdgeOptions={{ animated: true, markerEnd: { type: MarkerType.ArrowClosed } }}
                onNodeClick={(_event, node: Node) => {
                  setDetailModalNodeId(node.id)
                }}
                onNodeMouseEnter={(_event, node: Node) => setHoverNodeId(node.id)}
                onNodeMouseLeave={() => setHoverNodeId(null)}
              >
                <Background gap={20} size={1} color="#304255" />
                <MiniMap
                  pannable
                  zoomable
                  style={{
                    width: 100,
                    height: 68,
                    background: 'var(--bg-card)',
                    borderRadius: 8,
                    boxShadow: '0 1px 8px color-mix(in srgb, black 12%, transparent)',
                  }}
                />
                <Controls showInteractive />
              </ReactFlow>
            </ReactFlowProvider>
          ) : (
            <div className="h-full min-h-[480px] max-h-[min(640px,calc(100vh-16rem))] overflow-auto p-2 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {rows.map((row, i) => {
                const prev = i > 0 ? rows[i - 1] : undefined
                const delta =
                  typeof row.sampleScore === 'number' && typeof prev?.sampleScore === 'number'
                    ? row.sampleScore - prev.sampleScore
                    : null
                return (
                <div
                  key={row.id}
                  className="rounded-xl p-3 cursor-pointer transition-[box-shadow,opacity] hover:opacity-95"
                  style={{
                    border: '1px solid color-mix(in srgb, var(--border) 88%, transparent)',
                    background: 'color-mix(in srgb, var(--bg-panel) 96%, transparent)',
                    boxShadow: '0 0 0 1px color-mix(in srgb, var(--de-teal) 12%, transparent)',
                  }}
                  onClick={() => setDetailModalNodeId(`r${row.id}-dag`)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      setDetailModalNodeId(`r${row.id}-dag`)
                    }
                  }}
                  role="button"
                  tabIndex={0}
                >
                  <p className="text-xs text-[var(--text-muted)]">
                    {local.roundPrefix} {row.id}
                  </p>
                  <div className="mt-2 text-xs text-[var(--text-dim)] space-y-1">
                    <p>
                      1) {t.understanding}: {row.understandingDone ? t.done : t.pending}
                    </p>
                    <p>
                      2) {t.dagTabs}: {row.dagTabs.length} tags
                    </p>
                    <p>
                      3) {t.instantiation}: {row.instantiationCards.length}
                    </p>
                    <p>
                      4) {t.sampleEval}: {row.sampleScore ?? '-'}
                      {delta != null ? ` (${delta >= 0 ? '+' : ''}${delta} vs I${prev?.id})` : ''}
                    </p>
                    <p>
                      5) {t.experience}: {row.experience ? t.done : t.pending}
                    </p>
                    <div className="pt-1 mt-1 border-t" style={{ borderColor: 'var(--border)' }}>
                      <p>
                        {local.nodeDelta}: +{Math.max(1, row.dagTabs.length)} / {isZh ? '替换' : 'replaced'}{' '}
                        {row.instantiationCards.length > 0 ? 1 : 0}
                      </p>
                      <p>
                        {local.constraints}: {row.experience ? 2 : 0}
                      </p>
                    </div>
                  </div>
                </div>
              )})}
            </div>
          )}

          {hoverNodeInfo && viewMode === 'dag' && (
            <div
              className="absolute left-3 top-3 rounded-lg px-2 py-1.5 text-[10px] z-20 pointer-events-none"
              style={{
                background: 'color-mix(in srgb, var(--bg-panel) 92%, transparent)',
                boxShadow: '0 4px 14px color-mix(in srgb, black 14%, transparent)',
              }}
            >
              <p className="text-[var(--text)]">{hoverNodeInfo.title}</p>
              <p className="text-[var(--text-muted)]">{hoverNodeInfo.brief}</p>
            </div>
          )}
        </div>
      </div>

      <div
        className="shrink-0 h-[3px] rounded-full my-3 mx-0.5"
        style={{
          background:
            'linear-gradient(90deg, transparent, color-mix(in srgb, var(--de-green) 50%, var(--border)), color-mix(in srgb, var(--de-orange) 45%, var(--border)), transparent)',
        }}
        aria-hidden
      />

      {/* ③ 关键细节（与轮次联动） */}
      <div className="pt-1 pb-3 shrink-0">
        <h2 className="text-sm font-bold text-[var(--text)] tracking-tight">{local.sectionDetails}</h2>
        <p className="text-[10px] text-[var(--text-muted)] mt-0.5 leading-snug max-w-3xl">{local.sectionDetailsSub}</p>
        <div
          className="h-1 rounded-full mt-3 mb-3"
          style={{
            background: 'linear-gradient(90deg, var(--de-orange), transparent 75%)',
          }}
        />

        <div className="flex flex-wrap items-center gap-1.5 mb-4">
          <button
            type="button"
            onClick={() => {
              setInsightRoundOverride(null)
              setViewMode('dag')
            }}
            className="text-[10px] px-2.5 py-1 rounded-lg border font-medium transition-colors"
            style={{
              borderColor: insightRoundOverride === null ? 'var(--de-cyan)' : 'var(--border)',
              background: insightRoundOverride === null ? 'var(--de-cyan-glow)' : 'transparent',
              color: 'var(--text-dim)',
            }}
          >
            {local.detailFollowActive}
            {activeRow?.id != null ? ` · I${activeRow.id}` : ''}
          </button>
          {rows.map((row) => {
            const selected = insightRoundOverride === row.id
            return (
              <button
                key={row.id}
                type="button"
                onClick={() => {
                  setInsightRoundOverride(row.id)
                  setViewMode('dag')
                }}
                className="text-[10px] px-2.5 py-1 rounded-lg border transition-colors"
                style={{
                  borderColor: selected ? 'var(--de-orange)' : 'var(--border)',
                  background: selected ? 'color-mix(in srgb, var(--de-orange) 14%, transparent)' : 'transparent',
                  color: 'var(--text-dim)',
                }}
              >
                {local.detailRoundLabel} {row.id}
                {row.completed ? ' ✓' : ''}
              </button>
            )
          })}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <div
            className="rounded-xl p-3 border"
            style={{ borderColor: 'color-mix(in srgb, var(--de-cyan) 35%, var(--border))', background: 'color-mix(in srgb, var(--bg-card) 92%, transparent)' }}
          >
            <div className="flex items-center justify-between gap-2 mb-1">
              <p className="section-label mb-0">{local.seedSpec}</p>
              <span
                className="text-[9px] font-semibold px-1.5 py-0.5 rounded-md shrink-0"
                style={{ background: 'var(--de-cyan-glow)', color: 'var(--de-cyan)' }}
              >
                {local.seedGlobalBadge}
              </span>
            </div>
            <p className="text-[9px] text-[var(--text-muted)] mb-2">{local.seedGlobalNote}</p>
            <div className="text-xs text-[var(--text-dim)] space-y-2">
              <div>
                <p className="text-[var(--text-muted)]">{local.structureReq}</p>
                <p>{(canvasUi.understanding.schema_analysis?.seed_fields as string[] | undefined)?.join(', ') ?? '-'}</p>
              </div>
              <div>
                <p className="text-[var(--text-muted)]">{local.formatReq}</p>
                <p>{String(canvasUi.understanding.basic_information?.file_format_analysis?.seed ?? 'JSONL')}</p>
              </div>
              <div>
                <p className="text-[var(--text-muted)]">{local.qualityReq}</p>
                <p>{(canvasUi.understanding.basic_information?.processing_targets ?? []).slice(0, 2).join(' / ')}</p>
              </div>
            </div>
          </div>

          <div
            className="rounded-xl p-3 border"
            style={{ borderColor: 'color-mix(in srgb, var(--de-orange) 30%, var(--border))', background: 'color-mix(in srgb, var(--bg-card) 92%, transparent)' }}
          >
            <p className="section-label mb-1">{local.memory}</p>
            <p className="text-[9px] text-[var(--text-muted)] mb-2">
              {local.expForRound} · I{displayedRound?.id ?? '—'}
            </p>
            {displayedRound?.experience ? (
              <div
                className="rounded-lg px-2 py-2 mb-3 text-xs border"
                style={{ borderColor: 'var(--de-orange-dim)', background: 'color-mix(in srgb, var(--de-orange) 8%, var(--bg-panel))' }}
              >
                <p className="text-[var(--text-dim)] leading-relaxed">{displayedRound.experience}</p>
              </div>
            ) : (
              <p className="text-[10px] text-[var(--text-muted)] mb-3">{local.noRoundData}</p>
            )}
            <p className="text-[9px] font-medium text-[var(--text-muted)] mb-1.5">{isZh ? '全局参考（Judge）' : 'Global reference (Judge)'}</p>
            <div className="text-xs space-y-1.5">
              {experienceItems.map((exp) => (
                <div
                  key={exp}
                  className="rounded-lg px-2 py-1.5 cursor-default"
                  style={{ background: 'color-mix(in srgb, var(--bg-panel) 92%, transparent)' }}
                >
                  <p className="text-[var(--text-dim)] text-[11px] leading-snug">{exp}</p>
                  <span
                    className="inline-block mt-1 text-[9px] px-1.5 py-0.5 rounded-md"
                    style={{ background: 'color-mix(in srgb, var(--de-green) 18%, transparent)', color: 'var(--de-green)' }}
                  >
                    {local.applied}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div
            className="rounded-xl p-3 border"
            style={{ borderColor: 'color-mix(in srgb, var(--de-green) 30%, var(--border))', background: 'color-mix(in srgb, var(--bg-card) 92%, transparent)' }}
          >
            <p className="section-label mb-1">{local.qualityPanel}</p>
            <p className="text-[9px] text-[var(--text-muted)] mb-2">
              {local.qualityForRound} · I{displayedRound?.id ?? '—'}
            </p>
            {typeof displayedRound?.sampleScore === 'number' ? (
              <div className="flex items-baseline gap-2 mb-3">
                <span className="text-2xl font-bold tabular-nums text-[var(--de-cyan)]">{displayedRound.sampleScore}</span>
                <span className="text-[11px] text-[var(--text-muted)]">{t.llmScore}</span>
              </div>
            ) : (
              <p className="text-[10px] text-[var(--text-muted)] mb-3">{local.noRoundData}</p>
            )}
            {qualityBarsSnapshot.length > 0 ? (
              <div className="space-y-1.5">
                {qualityBarsSnapshot.map((item) => (
                  <div key={item.key}>
                    <div className="flex items-center justify-between text-[11px] text-[var(--text-dim)]">
                      <span>{item.name}</span>
                      <span>{item.value}</span>
                    </div>
                    <div className="h-1.5 rounded-full" style={{ background: 'var(--border)' }}>
                      <div
                        className="h-1.5 rounded-full"
                        style={{ width: `${item.value}%`, background: 'linear-gradient(90deg, var(--de-cyan), var(--de-teal))' }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[10px] text-[var(--text-muted)] mb-1">{local.noRoundData}</p>
            )}
            <div className="text-[10px] text-[var(--text-muted)] pt-2 mt-2 border-t" style={{ borderColor: 'var(--border)' }}>
              {local.trend}: {allScores.length > 0 ? allScores.map((s, idx) => `I${idx + 1}:${s}`).join('  ') : '-'}
            </div>
          </div>
        </div>
      </div>

      <NodeDetailCenterModal
        nodeId={detailModalNodeId}
        onClose={() => setDetailModalNodeId(null)}
        rows={rows}
        t={t}
        local={local}
        isZh={isZh}
        onSelectDagTab={onSelectDagTab}
        scoreDelta={scoreDelta}
        operatorPool={operatorPool}
        canvasUi={canvasUi}
      />

      {openRunSummary && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
          role="dialog"
          aria-modal="true"
          onClick={() => setOpenRunSummary(false)}
        >
          <div
            className="w-full max-w-[520px] rounded-2xl border p-5 shadow-xl"
            style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <p className="section-label mb-2">{local.runSummary}</p>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-lg border p-2" style={{ borderColor: 'var(--border)' }}>Iteration: {rows.length}</div>
              <div className="rounded-lg border p-2" style={{ borderColor: 'var(--border)' }}>Operators: {operatorPool.length}</div>
              <div className="rounded-lg border p-2" style={{ borderColor: 'var(--border)' }}>
                {t.totalTokens}: {totalMetrics.tokens}
              </div>
              <div className="rounded-lg border p-2" style={{ borderColor: 'var(--border)' }}>
                {local.judgeGap}: {String(canvasUi.judge.has_differences)}
              </div>
              <div className="rounded-lg border p-2" style={{ borderColor: 'var(--border)' }}>
                {local.insightCount}: {(canvasUi.judge.critical_insights ?? []).length}
              </div>
              <div className="rounded-lg border p-2" style={{ borderColor: 'var(--border)' }}>
                {local.expCount}: {experienceItems.length}
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="h-8 px-3 rounded-lg border text-xs" style={{ borderColor: 'var(--border)', color: 'var(--text-dim)' }} onClick={() => setOpenRunSummary(false)}>
                {local.cancel}
              </button>
              <button
                type="button"
                disabled={workflowBusy || !(canRunFull || finished)}
                className="h-8 px-3 rounded-lg text-xs font-medium"
                style={{
                  background:
                    canRunFull || finished
                      ? 'linear-gradient(135deg, var(--de-cyan), var(--de-teal))'
                      : 'color-mix(in srgb, var(--bg-card) 90%, var(--border))',
                  color: canRunFull || finished ? '#0f172a' : 'var(--text-muted)',
                  border: canRunFull || finished ? 'none' : '1px solid var(--border)',
                }}
                onClick={() => {
                  setOpenRunSummary(false)
                  void onRunFullData()
                }}
              >
                {local.runNow}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="sticky bottom-0 z-30 mt-3">
        <div
          className="rounded-2xl border px-3 py-2.5 shadow-lg backdrop-blur"
          style={{
            borderColor: 'color-mix(in srgb, var(--de-cyan) 24%, var(--border))',
            background:
              'linear-gradient(90deg, color-mix(in srgb, var(--de-cyan) 16%, var(--bg-card)) 0%, color-mix(in srgb, var(--de-teal) 12%, var(--bg-card)) 45%, color-mix(in srgb, var(--de-orange) 10%, var(--bg-card)) 100%)',
            boxShadow:
              '0 -1px 0 color-mix(in srgb, var(--de-cyan) 22%, transparent), 0 8px 22px color-mix(in srgb, #0b1220 26%, transparent)',
          }}
        >
          <div className="flex flex-wrap items-center justify-between gap-2.5">
            <div className="flex flex-wrap items-center gap-1.5">
              <span
                className="inline-flex items-center gap-1 h-8 px-2.5 rounded-lg text-[11px] border"
                style={{
                  borderColor: 'color-mix(in srgb, var(--de-cyan) 42%, var(--border))',
                  background: 'color-mix(in srgb, var(--de-cyan) 8%, var(--bg-card))',
                  boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--de-cyan) 16%, transparent)',
                  color: 'var(--text-dim)',
                }}
              >
                {local.phase}: {phase}
              </span>
              <span
                className="inline-flex items-center gap-1 h-8 px-2.5 rounded-lg text-[11px] border"
                style={{
                  borderColor: 'color-mix(in srgb, var(--de-cyan) 38%, var(--border))',
                  background: 'color-mix(in srgb, var(--de-cyan) 6%, var(--bg-card))',
                  boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--de-cyan) 14%, transparent)',
                  color: 'var(--text-dim)',
                }}
              >
                {local.iteration}: I{currentIteration}
              </span>
              <span
                className="inline-flex items-center gap-1 h-8 px-2.5 rounded-lg text-[11px] border"
                style={{
                  borderColor: 'color-mix(in srgb, var(--de-cyan) 38%, var(--border))',
                  background: 'color-mix(in srgb, var(--de-cyan) 6%, var(--bg-card))',
                  boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--de-cyan) 14%, transparent)',
                  color: 'var(--text-dim)',
                }}
              >
                {local.quality}: {currentScore || '-'} ({scoreDelta >= 0 ? '+' : ''}
                {scoreDelta})
              </span>
              {workflowBusy && runningStepLabel ? (
                <span
                  className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-lg text-[11px] border font-medium"
                  style={{
                    borderColor: 'color-mix(in srgb, var(--de-cyan) 62%, var(--border))',
                    color: 'var(--text)',
                    background: 'color-mix(in srgb, var(--de-cyan) 12%, transparent)',
                  }}
                >
                  <Cpu className="w-3 h-3 animate-spin" />
                  {local.runningStep}: {runningStepLabel}
                </span>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center justify-end gap-1.5">
              <button
                type="button"
                disabled={workflowBusy}
                onClick={() => void onStepForward()}
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs whitespace-nowrap text-[var(--text-dim)] hover:opacity-80 disabled:opacity-50"
              >
                <Play className="w-3.5 h-3.5" />
                {t.stepForward}
              </button>
              <button
                type="button"
                disabled={workflowBusy}
                onClick={() => void onAutoCompleteRound()}
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs whitespace-nowrap border border-dashed disabled:opacity-50"
                style={{ borderColor: 'var(--de-cyan-dim)', color: 'var(--text)' }}
              >
                <FastForward className="w-3.5 h-3.5 text-[var(--de-cyan)]" />
                {t.autoBuildRound}
              </button>
              <button
                type="button"
                disabled={workflowBusy || !onRerunFromCurrentStep}
                onClick={() => {
                  if (onRerunFromCurrentStep) void onRerunFromCurrentStep()
                }}
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs whitespace-nowrap border disabled:opacity-50"
                style={{ borderColor: 'var(--border)', color: 'var(--text-dim)' }}
              >
                {local.rerunFromCurrentStep}
              </button>
              <button
                type="button"
                disabled={workflowBusy || !(canRunFull || finished)}
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs whitespace-nowrap font-semibold shadow-sm disabled:opacity-50"
                style={{
                  background:
                    canRunFull || finished || recommendation === local.readyToRun
                      ? 'linear-gradient(135deg, var(--de-cyan), var(--de-teal))'
                      : 'color-mix(in srgb, var(--bg-card) 90%, var(--border))',
                  color: canRunFull || finished || recommendation === local.readyToRun ? '#0f172a' : 'var(--text-muted)',
                  border:
                    canRunFull || finished || recommendation === local.readyToRun ? 'none' : '1px solid var(--border)',
                }}
                onClick={() => setOpenRunSummary(true)}
              >
                <Rocket className="w-3.5 h-3.5" />
                {local.applyPipeline}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="fixed right-6 bottom-32 z-40">
        {metricsOpen ? (
          <div
            className="flex w-[min(440px,calc(100vw-3rem))] max-h-[min(560px,72vh)] flex-col rounded-2xl border p-4 shadow-2xl"
            style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}
            role="dialog"
            aria-modal="true"
            aria-label={local.metricWindow}
          >
            <div className="flex shrink-0 items-start justify-between gap-2 border-b pb-3" style={{ borderColor: 'var(--border)' }}>
              <div>
                <p className="text-sm font-bold text-[var(--text)]">{local.metricWindow}</p>
                <p className="mt-0.5 text-[10px] leading-snug text-[var(--text-muted)]">{local.basedOn}</p>
              </div>
              <button
                type="button"
                className="shrink-0 rounded-lg border px-2.5 py-1 text-[11px]"
                style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}
                onClick={() => setMetricsOpen(false)}
              >
                {local.hide}
              </button>
            </div>

            <div className="mt-3 shrink-0 rounded-xl border px-3 py-3" style={{ borderColor: 'color-mix(in srgb, var(--de-cyan) 28%, var(--border))', background: 'color-mix(in srgb, var(--de-cyan) 6%, transparent)' }}>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                {isZh ? '管线合计' : 'Pipeline total'}
              </p>
              <div className="mt-2 flex flex-wrap items-baseline gap-6">
                <div>
                  <span className="text-2xl font-bold tabular-nums text-[var(--text)]">{totalMetrics.sec}</span>
                  <span className="ml-1 text-xs text-[var(--text-muted)]">s</span>
                  <p className="text-[10px] text-[var(--text-muted)]">{t.totalTime}</p>
                </div>
                <div>
                  <span className="text-2xl font-bold tabular-nums text-[var(--de-cyan)]">{totalMetrics.tokens}</span>
                  <span className="ml-1 text-xs text-[var(--text-muted)]">tok</span>
                  <p className="text-[10px] text-[var(--text-muted)]">{t.totalTokens}</p>
                </div>
              </div>
            </div>

            <div className="mt-3 max-h-[min(360px,46vh)] space-y-3 overflow-y-auto pr-1">
              <p className="text-[10px] font-semibold text-[var(--text-muted)]">{local.perRound}</p>
              {pipelineMetricsBreakdown.map((round) => (
                <div key={round.rowId} className="overflow-hidden rounded-xl border" style={{ borderColor: 'var(--border)' }}>
                  <div
                    className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-xs font-semibold"
                    style={{ background: 'color-mix(in srgb, var(--bg-panel) 96%, transparent)', borderBottom: '1px solid var(--border)' }}
                  >
                    <span className="text-[var(--text)]">
                      {isZh ? `迭代 I${round.rowId}` : `Iteration I${round.rowId}`}
                    </span>
                    <span className="font-mono text-[10px] font-normal tabular-nums text-[var(--text-muted)]">
                      {round.subtotalSec}s · {round.subtotalTokens} tok
                    </span>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[280px] border-collapse text-left text-[11px]">
                      <thead>
                        <tr style={{ background: 'color-mix(in srgb, var(--bg-panel) 88%, transparent)' }}>
                          <th className="px-2.5 py-2 font-semibold text-[var(--text-muted)]" style={{ width: '52%' }}>
                            {isZh ? '步骤' : 'Step'}
                          </th>
                          <th className="px-2 py-2 font-semibold text-[var(--text-muted)] tabular-nums">{isZh ? '用时' : 'Time'}</th>
                          <th className="px-2 py-2 font-semibold text-[var(--text-muted)] tabular-nums">Token</th>
                        </tr>
                      </thead>
                      <tbody>
                        {round.steps.map((step) => (
                          <tr key={step.id} style={{ borderTop: '1px solid var(--border)' }}>
                            <td className="max-w-[200px] px-2.5 py-2 leading-snug text-[var(--text-dim)]">{step.label}</td>
                            <td className="whitespace-nowrap px-2 py-2 tabular-nums text-[var(--text)]">
                              {step.sec === null ? '—' : `${step.sec}s`}
                            </td>
                            <td className="whitespace-nowrap px-2 py-2 tabular-nums text-[var(--text)]">
                              {step.tokens === null ? '—' : step.tokens}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <button
            type="button"
            className="h-10 rounded-full border px-4 text-xs font-medium shadow-md"
            style={{ borderColor: 'var(--border)', background: 'var(--bg-card)', color: 'var(--text-dim)' }}
            onClick={() => setMetricsOpen(true)}
          >
            {local.metricWindow} · {local.show}
          </button>
        )}
      </div>
    </section>
  )
}
