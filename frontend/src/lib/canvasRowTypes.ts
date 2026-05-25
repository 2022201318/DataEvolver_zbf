import type { DagResult, JudgeResult, UnderstandingResult } from '../types'

export type CanvasMetric = { sec: number; tokens: number }

export type CanvasDagTab = {
  id: number
  title: string
  status: 'passed' | 'failed'
  summary: string
  metrics: CanvasMetric
  nodes: string[]
  dag?: DagResult | null
}

export type CanvasInstantiationCard = {
  id: string
  name: string
  summary: string
  code: string
  metrics: CanvasMetric
  /** 该步是否由 LLM 生成 prompt/参数 */
  llmGenerated?: boolean
}

export type InstantiationMeta = {
  reused?: boolean
  llm_codegen?: boolean
  llm_steps?: string[]
  note?: string
  source?: string
}

export type ExperienceMeta = {
  llm_used?: boolean
  source_kind?: string
  detail?: string
}

export interface LiveArtifactsForCanvas {
  understanding: UnderstandingResult | null
  dag: DagResult | null
  orchestrationValidation: { is_valid: boolean; validation_issues: string[] } | null
  judge: JudgeResult | null
  experienceBullets: string[]
}

export type CanvasEvolutionRow = {
  id: number
  understandingDone: boolean
  understandingMetrics?: CanvasMetric
  dagTabs: CanvasDagTab[]
  activeDagTabId?: number
  instantiationCards: CanvasInstantiationCard[]
  /** 实例化阶段 LLM/复用说明 */
  instantiationMeta?: InstantiationMeta
  sampleScore?: number
  sampleMetrics?: CanvasMetric
  experience?: string
  experienceMetrics?: CanvasMetric
  /** 经验总结来源说明（规则聚合 vs LLM） */
  experienceMeta?: ExperienceMeta
  needNext: boolean
  completed: boolean
  rowUi?: LiveArtifactsForCanvas
}

export interface RoundHistoryArtifact {
  round: number
  quality_passed?: boolean
  understanding?: Record<string, unknown> | null
  orchestration?: Record<string, unknown> | null
  instantiation?: Record<string, unknown> | null
  quality_check?: Record<string, unknown> | null
  trial?: Record<string, unknown> | null
  experience?: Record<string, unknown> | null
}

export interface IterationHistoryArtifact {
  round: number
  iteration: number
  reason?: string
  orchestration?: Record<string, unknown> | null
}

export interface OrchestrationArchiveArtifact {
  round: number
  understanding_revision?: number
  orchestration_revision?: number
  orchestration?: Record<string, unknown> | null
}
