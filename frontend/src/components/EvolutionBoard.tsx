import { useMemo } from 'react'
import { useAppStore } from '../stores/appStore'

const STAGE_ORDER: { id: 'upload' | 'orchestration' | 'instantiation' | 'quality-check' | 'execution'; label: string }[] = [
  { id: 'upload', label: 'Stage 1 · 数据理解' },
  { id: 'orchestration', label: 'Stage 2 · 编排与 DAG' },
  { id: 'instantiation', label: 'Stage 3 · 算子实例化' },
  { id: 'quality-check', label: 'Stage 4 · 质量检查' },
  { id: 'execution', label: 'Run Full · 全量执行' },
]

/**
 * 双层自进化总览看板（大看板）：
 * - 顶部：一步一步的流程「1 数据理解 → 2 编排与 DAG → 3 算子实例化 → 4 质量检查 → Run Full」
 *   用大号数字 + 标题卡片展示，当前所处步骤高亮，已完成步骤标记为完成。
 * - 中间：关键指标（质量分、算子数、当前代数、经验条数）。
 * - 底部：简单易懂的进化历程摘要（按「初始 → 增强 → 重构 → 微调 → 收敛」叙事），而不是纯 G1~G5 代码。
 * 自动模式：仅展示整体进度；手动模式：在看板右上角提供「下一步」按钮，引导用户逐步执行。
 */
export function EvolutionBoard() {
  const runMode = useAppStore((s) => s.runMode)
  const currentStage = useAppStore((s) => s.currentStage)
  const operators = useAppStore((s) => s.operators)
  const experiences = useAppStore((s) => s.experiences)
  const judgeResult = useAppStore((s) => s.judgeResult)
  const setCurrentStage = useAppStore((s) => s.setCurrentStage)

  const stageIndex = useMemo(
    () => STAGE_ORDER.findIndex((s) => s.id === currentStage),
    [currentStage],
  )

  const qualityScore = useMemo(() => {
    // 简单示意：有 Judge 结果时给一个较高分，否则给一个基线分
    return judgeResult ? 94.7 : 80.0
  }, [judgeResult])

  const activeOperators = useMemo(
    () => (operators.length > 0 ? operators.length : 24),
    [operators.length],
  )

  const generation = useMemo(
    () => (experiences.length > 0 ? '收敛优化中' : '初始'),
    [experiences.length],
  )

  const nextStage = () => {
    const idx = stageIndex < 0 ? 0 : stageIndex
    const next = STAGE_ORDER[Math.min(idx + 1, STAGE_ORDER.length - 1)].id
    setCurrentStage(next)
    const elId =
      next === 'upload'
        ? 'section-upload'
        : next === 'orchestration'
        ? 'section-orchestration'
        : next === 'instantiation'
        ? 'section-instantiation'
        : next === 'quality-check'
        ? 'section-quality-check'
        : 'section-execution'
    const el = document.getElementById(elId)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div
      className="rounded-2xl border p-5 mb-8 animate-fade-slide"
      style={{ background: 'var(--bg-panel)', borderColor: 'var(--border)' }}
    >
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="section-label mb-2">双层自进化总览</p>
          <p className="text-sm text-[var(--text-dim)]">
            一图总览「理解 → 编排 → 实例化 → 质量检查 → 全量执行」的完整流程。上方是主流程，右下角可以逐步推进或一键自动。
          </p>
        </div>
        {runMode === 'manual' ? (
          <button
            type="button"
            onClick={nextStage}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-[var(--bg-deep)]"
            style={{ background: 'linear-gradient(135deg, #00e5c8, #00b4d8)' }}
          >
            下一步
          </button>
        ) : (
          <span className="text-xs text-[var(--text-muted)]">
            自动模式：运行时将自动推进各阶段
          </span>
        )}
      </div>

      <div className="space-y-5 mt-2">
        {/* 顶部：双层泳道图 */}
        <div className="space-y-3">
          {/* 上层：算子级（Operator-Level）主流程 */}
          <div className="flex items-center gap-3">
            <div className="w-28 text-right pr-2">
              <p className="text-[0.7rem] font-mono text-[var(--text-muted)] tracking-widest uppercase">
                Operator-Level
              </p>
              <p className="text-xs text-[var(--text-dim)]">算子自进化</p>
            </div>
            <div className="flex flex-wrap gap-3 flex-1">
              {STAGE_ORDER.filter((s) => s.id !== 'quality-check').map((s, idx) => {
                const status =
                  stageIndex < 0
                    ? 'pending'
                    : idx < stageIndex
                    ? 'done'
                    : (s.id === 'execution' && stageIndex >= STAGE_ORDER.length - 1) ||
                      idx === stageIndex
                    ? 'active'
                    : 'pending'
                const ringColor =
                  status === 'done'
                    ? 'border-[var(--de-green)] bg-[var(--de-green)]/10 text-[var(--de-green)]'
                    : status === 'active'
                    ? 'border-[var(--de-cyan-dim)] bg-[var(--de-cyan-glow)] text-[var(--de-cyan)]'
                    : 'border-[var(--border)] bg-[var(--bg-card)] text-[var(--text-muted)]'
                return (
                  <div
                    key={s.id}
                    className="flex items-center gap-3 px-4 py-3 rounded-xl border min-w-[180px]"
                    style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}
                  >
                    <div
                      className={`w-8 h-8 rounded-full border flex items-center justify-center text-xs font-mono font-bold ${ringColor}`}
                    >
                      {idx + 1}
                    </div>
                    <div className="flex flex-col">
                      <span className="text-xs text-[var(--text-muted)]">
                        {idx < 3 ? `Step ${idx + 1}` : 'Run Full'}
                      </span>
                      <span className="text-sm text-[var(--text)] font-semibold">
                        {s.label.replace(/Stage \\d+ · /, '')}
                      </span>
                    </div>
                    {idx < 3 && (
                      <span className="text-lg text-[var(--text-muted)]">→</span>
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {/* 下层：流水线级（Pipeline-Level）循环：质量检查 → 经验挖掘 → 反馈到 Stage1 */}
          <div className="flex items-center gap-3">
            <div className="w-28 text-right pr-2">
              <p className="text-[0.7rem] font-mono text-[var(--text-muted)] tracking-widest uppercase">
                Pipeline-Level
              </p>
              <p className="text-xs text-[var(--text-dim)]">Pipeline 自进化</p>
            </div>
            <div className="flex items-center gap-3 flex-1">
              <div
                className="px-4 py-3 rounded-xl border min-w-[160px]"
                style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}
              >
                <p className="text-xs text-[var(--text-muted)] mb-0.5">Step 4</p>
                <p className="text-sm text-[var(--text)] font-semibold">质量检查</p>
              </div>
              <span className="text-lg text-[var(--text-muted)]">→</span>
              <div
                className="px-4 py-3 rounded-xl border min-w-[160px]"
                style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}
              >
                <p className="text-xs text-[var(--text-muted)] mb-0.5">经验挖掘</p>
                <p className="text-sm text-[var(--text)] font-semibold">生成经验条目</p>
              </div>
              <span className="text-lg text-[var(--text-muted)]">→</span>
              <div
                className="px-4 py-3 rounded-xl border min-w-[160px]"
                style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}
              >
                <p className="text-xs text-[var(--text-muted)] mb-0.5">反馈到 Stage 1</p>
                <p className="text-sm text-[var(--text)] font-semibold">重新理解与编排</p>
              </div>
              {/* 简单回环箭头指向上层第一个卡片（仅大屏显示） */}
              <svg width="80" height="40" className="hidden lg:block">
                <defs>
                  <marker
                    id="arrowHead"
                    markerWidth="6"
                    markerHeight="6"
                    refX="5"
                    refY="3"
                    orient="auto"
                  >
                    <path d="M0,0 L6,3 L0,6 z" fill="var(--de-cyan-dim)" />
                  </marker>
                </defs>
                <path
                  d="M10,30 C30,10 50,10 70,10"
                  fill="none"
                  stroke="var(--de-cyan-dim)"
                  strokeWidth="1.5"
                  strokeDasharray="4 3"
                  markerEnd="url(#arrowHead)"
                />
              </svg>
            </div>
          </div>
        </div>

        {/* 中间：关键指标 + 进化历程说明 */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 text-xs">
          {/* 指标卡片 */}
          <div className="grid grid-cols-2 gap-3 lg:col-span-2">
            <div className="rounded-lg px-4 py-3" style={{ background: 'var(--bg-card)' }}>
              <p className="text-[var(--text-muted)] mb-1">质量评分（采样）</p>
              <p className="text-2xl font-extrabold text-[var(--de-cyan)]">
                {qualityScore.toFixed(1)}
              </p>
            </div>
            <div className="rounded-lg px-4 py-3" style={{ background: 'var(--bg-card)' }}>
              <p className="text-[var(--text-muted)] mb-1">活跃算子数</p>
              <p className="text-2xl font-extrabold text-[var(--de-orange)]">
                {activeOperators}
              </p>
            </div>
            <div className="rounded-lg px-4 py-3" style={{ background: 'var(--bg-card)' }}>
              <p className="text-[var(--text-muted)] mb-1">进化状态</p>
              <p className="text-base font-semibold text-[var(--de-green)]">
                {generation}
              </p>
            </div>
            <div className="rounded-lg px-4 py-3" style={{ background: 'var(--bg-card)' }}>
              <p className="text-[var(--text-muted)] mb-1">经验条数</p>
              <p className="text-xl font-extrabold text-[var(--de-cyan)]">
                {experiences.length}
              </p>
            </div>
          </div>

          {/* 进化历程文字版（更易懂） */}
          <div className="space-y-2">
            <p className="text-[var(--text-muted)] mb-1">进化历程</p>
            <p className="text-[0.8rem] text-[var(--text-dim)] leading-relaxed">
              起点是「初始 Pipeline」：只做基础清洗与格式统一；随后进入「语义增强」和「经验重构」阶段，引入 LLM
              对齐与经验反馈；当前状态显示为「{generation}」，说明系统已经在不断用 Judge
              结果与经验条目优化算子组合与整体流水线。
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

