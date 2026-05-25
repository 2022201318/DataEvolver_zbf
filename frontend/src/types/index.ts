/** 与后端/实时同步接口对齐的类型预留 */

export type StageId = 'upload' | 'understanding' | 'orchestration' | 'instantiation' | 'quality-check' | 'execution'

export interface UploadState {
  raw?: { name: string; size: number; rows?: number; error?: string }
  seed?: { name: string; size: number; rows?: number; error?: string }
  description?: { name: string; size: number; error?: string }
  pipelineId?: string
}

/** 与 `data/manifest.jsonl` 单行结构对齐（开源版与旧版对齐用） */
export interface ManifestRecord {
  pipeline_id: string
  raw_data_files: string[]
  seed_data_files: string[]
  description_data_files?: string[]
  domain?: string
  task_type?: string
  language?: string
}

export interface StartSessionResponse {
  ok: boolean
  pipeline_id: string
  manifest_record: ManifestRecord
  saved_paths: {
    raw?: string | null
    seed?: string | null
    description?: string | null
  }
}

/** 与 `GET /api/operators/` 响应中 `operators[]` 项对齐 */
export interface ApiOperatorEntry {
  name: string
  source: 'base' | 'general' | 'domain' | 'task' | 'legacy_user' | 'user'
  /** Stable id: io | structure | control | semantic | quality | bridge */
  category_id: string
  category_label: string
  category_label_zh?: string
  /** Suggested token for card color mapping, e.g. slate | cyan | amber | violet | rose | emerald */
  card_variant?: string
  /** Same as category_label; kept for backward compatibility */
  category: string
  description: string
  input_keys: string[]
  output_keys: string[]
  requires_llm: boolean
}

/** `data/operator_categories.json` 中单类目的展示信息 */
export interface OperatorCategoryMeta {
  label: string
  label_zh?: string
  description?: string
  card_variant?: string
}

export interface OperatorsListResponse {
  operators: ApiOperatorEntry[]
  categories: Record<string, OperatorCategoryMeta>
  counts: {
    merged: number
    base: number
    general?: number
    domain?: number
    task?: number
    legacy_user?: number
    user?: number
  }
  task_operator_names?: string[]
  domain_operator_names?: string[]
  general_operator_names?: string[]
  legacy_user_operator_names?: string[]
  user_operator_names?: string[]
  paths: {
    base: string
    general?: string | null
    domain?: string | null
    user: string
    categories: string
  }
}

/**
 * 画布算子池卡片：来自 `GET /api/operators/` 映射；`source===evolved'` 含用户注册表算子（API 为 `user`）
 */
export interface OperatorItem {
  id: string
  name: string
  description: string
  source: 'base' | 'evolved'
  updatedAt?: string
  /** 展示用类别文案（随界面语言取中/英） */
  category?: string
  category_id?: string
  input_keys?: string[]
  output_keys?: string[]
  requires_llm?: boolean
  card_variant?: string
}

export interface UnderstandingResult {
  pipeline_id?: string
  /** 数据内容语言码（zh/en/mixed/unknown），用于后续阶段自然语言输出与 UI 展示语言对齐 */
  language?: string
  language_label?: string
  /** 上传表单中用户填写的数据语言（若有），与自动检测的 `language` 区分 */
  user_declared_language?: string | null
  domain?: string | null
  task_type?: string | null
  basic_information?: {
    language?: string
    content_language_code?: string
    user_declared_language?: string | null
    file_format_analysis?: Record<string, unknown>
    seed_vs_raw_quality?: Record<string, unknown>
    processing_targets?: string[]
    domain_characteristics?: string
    transformation_direction?: string
    quality_standards?: string
  }
  schema_analysis?: Record<string, unknown>
  dataset_level_delta?: Record<string, unknown>
  content_slot_library?: Record<string, unknown>
  quality_rubrics?: Record<string, unknown>
  meta?: Record<string, unknown>
  /** 服务端落盘相对路径 */
  saved_path?: string
}

export interface DagNode {
  node_id: string
  node_name: string
  node_type?: string
  description?: string
  input_keys?: string[]
  output_keys?: string[]
  parameters?: Record<string, unknown>
}

export interface DagEdge {
  from_node: string
  to_node: string
  edge_type?: string
  data_flow?: { from_outputs?: string[]; to_inputs?: string[] }
  description?: string
}

export interface DagResult {
  nodes: DagNode[]
  edges: DagEdge[]
  dag_type?: string
  execution_order?: string[]
  total_nodes?: number
  total_edges?: number
}

export interface PipelineStep {
  step: number
  operator: string
  description?: string
  parameters?: Record<string, unknown>
}

export interface InstantiationStep {
  step_index: number
  operator_name: string
  code: string
  intermediate_summary?: string
}

export interface JudgeResult {
  has_differences?: boolean
  overall_assessment?: string
  critical_insights?: string[]
  implicit_quality_requirements?: Record<string, unknown>
  style_consistency_analysis?: Record<string, unknown>
}

export interface ExecutionProgress {
  stage?: string
  step_index?: number
  percent?: number
  message?: string
  log_lines?: string[]
}

export interface ExecutionResult {
  total_rows?: number
  duration_sec?: number
  status?: string
  download_url?: string
  preview?: Record<string, unknown>[]
}
