import { create } from 'zustand'
import type {
  StageId,
  UploadState,
  UnderstandingResult,
  DagResult,
  PipelineStep,
  InstantiationStep,
  JudgeResult,
  ExecutionProgress,
  ExecutionResult,
} from '../types'

type RunMode = 'auto' | 'manual'
type ThemeMode = 'dark' | 'light'
type Language = 'zh' | 'en'

interface AppState {
  runMode: RunMode
  currentStage: StageId
  pipelineId: string | null

  themeMode: ThemeMode
  language: Language

  upload: UploadState
  setUpload: (u: Partial<UploadState> | ((prev: UploadState) => Partial<UploadState>)) => void

  understandingLoading: boolean
  understandingResult: UnderstandingResult | null
  experienceText: string
  setUnderstanding: (loading: boolean, result?: UnderstandingResult | null) => void
  setExperienceText: (s: string) => void

  operators: { name: string; description: string; input_keys: string[]; output_keys: string[]; requires_llm?: boolean; category?: string }[]
  dag: DagResult | null
  pipelinePlan: PipelineStep[]
  checkFailed: boolean
  setOrchestration: (dag: DagResult | null, plan: PipelineStep[], checkFailed?: boolean) => void
  setOperators: (ops: AppState['operators']) => void

  instantiationSteps: InstantiationStep[]
  instantiationLoading: boolean
  currentInstantiationStep: number
  setInstantiation: (steps: InstantiationStep[], loading?: boolean, currentStep?: number) => void

  sampleProcessed: Record<string, unknown>[]
  sampleSeed: Record<string, unknown>[]
  judgeResult: JudgeResult | null
  experiences: string[]
  qualityCheckLoading: boolean
  setQualityCheck: (opts: {
    sampleProcessed?: Record<string, unknown>[]
    sampleSeed?: Record<string, unknown>[]
    judgeResult?: JudgeResult | null
    experiences?: string[]
    loading?: boolean
  }) => void

  executionProgress: ExecutionProgress | null
  executionResult: ExecutionResult | null
  executionLoading: boolean
  setExecution: (progress: ExecutionProgress | null, result?: ExecutionResult | null, loading?: boolean) => void

  tokenStats: {
    promptTokens: number
    completionTokens: number
    totalTokens: number
    estimatedCost: number
    elapsedSec: number
  }
  setTokenStats: (stats: Partial<AppState['tokenStats']>) => void

  llmConfig: {
    provider: string
    model: string
    temperature: number
    maxTokens: number
  }
  setLlmConfig: (partial: Partial<AppState['llmConfig']>) => void

  toast: { message: string; type: 'success' | 'error' | 'info' } | null
  setToast: (t: AppState['toast']) => void

  setRunMode: (m: RunMode) => void
  setThemeMode: (m: ThemeMode) => void
  setLanguage: (l: Language) => void
  setCurrentStage: (s: StageId) => void
  setPipelineId: (id: string | null) => void
}

export const useAppStore = create<AppState>((set) => ({
  runMode: 'manual',
  currentStage: 'upload',
  pipelineId: null,

  themeMode: 'light',
  language: 'zh',

  upload: {},
  setUpload: (u) =>
    set((s) => ({
      upload: typeof u === 'function' ? { ...s.upload, ...u(s.upload) } : { ...s.upload, ...u },
    })),

  understandingLoading: false,
  understandingResult: null,
  experienceText: '',
  setUnderstanding: (loading, result) =>
    set({ understandingLoading: loading, understandingResult: result ?? null }),
  setExperienceText: (experienceText) => set({ experienceText }),

  operators: [],
  dag: null,
  pipelinePlan: [],
  checkFailed: false,
  setOrchestration: (dag, pipelinePlan, checkFailed = false) =>
    set({ dag, pipelinePlan, checkFailed }),
  setOperators: (operators) => set({ operators }),

  instantiationSteps: [],
  instantiationLoading: false,
  currentInstantiationStep: 0,
  setInstantiation: (instantiationSteps, loading = false, currentInstantiationStep = 0) =>
    set({ instantiationSteps, instantiationLoading: loading, currentInstantiationStep }),

  sampleProcessed: [],
  sampleSeed: [],
  judgeResult: null,
  experiences: [],
  qualityCheckLoading: false,
  setQualityCheck: (opts) =>
    set((s) => ({
      sampleProcessed: opts.sampleProcessed ?? s.sampleProcessed,
      sampleSeed: opts.sampleSeed ?? s.sampleSeed,
      judgeResult: opts.judgeResult !== undefined ? opts.judgeResult : s.judgeResult,
      experiences: opts.experiences ?? s.experiences,
      qualityCheckLoading: opts.loading ?? s.qualityCheckLoading,
    })),

  executionProgress: null,
  executionResult: null,
  executionLoading: false,
  setExecution: (executionProgress, executionResult, executionLoading = false) =>
    set({
      executionProgress,
      executionResult: executionResult ?? null,
      executionLoading,
    }),

  tokenStats: {
    promptTokens: 0,
    completionTokens: 0,
    totalTokens: 0,
    estimatedCost: 0,
    elapsedSec: 0,
  },
  setTokenStats: (partial) =>
    set((s) => ({ tokenStats: { ...s.tokenStats, ...partial } })),

  llmConfig: {
    provider: 'openai',
    model: 'gpt-4o-mini',
    temperature: 0.1,
    maxTokens: 8000,
  },
  setLlmConfig: (partial) =>
    set((s) => ({ llmConfig: { ...s.llmConfig, ...partial } })),

  toast: null,
  setToast: (toast) => set({ toast }),

  setRunMode: (runMode) => set({ runMode }),
  setThemeMode: (themeMode) => set({ themeMode }),
  setLanguage: (language) => set({ language }),
  setCurrentStage: (currentStage) => set({ currentStage }),
  setPipelineId: (pipelineId) => set({ pipelineId }),
}))
