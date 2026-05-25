import { useState } from 'react'
import { useAppStore } from '../stores/appStore'
import { CodeBlock } from '../components/CodeBlock'
import { ChevronDown, ChevronRight } from 'lucide-react'
import clsx from 'clsx'
import { Link } from 'react-router-dom'

export function InstantiationPage({ mode = 'full' }: { mode?: 'full' | 'summary' }) {
  const instantiationSteps = useAppStore((s) => s.instantiationSteps)
  const currentInstantiationStep = useAppStore((s) => s.currentInstantiationStep)
  const [expanded, setExpanded] = useState<Record<number, boolean>>({ 1: true })

  const steps = instantiationSteps
  const currentStep = steps.find((s) => s.step_index === currentInstantiationStep) ?? steps[0]

  const toggle = (k: number) =>
    setExpanded((e) => ({ ...e, [k]: !e[k] }))
  const expandAll = () => setExpanded(Object.fromEntries(steps.map((s) => [s.step_index, true])))
  const collapseAll = () => setExpanded({})

  if (mode === 'summary') {
    return (
      <div className="space-y-5">
        <div>
          <p className="section-label">实例化摘要 (Stage 3)</p>
          <p className="text-sm text-[var(--text-dim)]">
            保留主页可理解的关键信息：当前实例化进度、步骤概览和最新代码片段。完整逐步代码阅读放在深度详情页。
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="rounded-xl border p-4" style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}>
            <p className="text-xs text-[var(--text-muted)] mb-1">总步骤</p>
            <p className="text-2xl font-semibold text-[var(--text)]">{steps.length}</p>
          </div>
          <div className="rounded-xl border p-4" style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}>
            <p className="text-xs text-[var(--text-muted)] mb-1">当前步骤</p>
            <p className="text-sm font-semibold text-[var(--de-cyan)]">
              Step {currentStep?.step_index ?? '-'} · {currentStep?.operator_name ?? '待开始'}
            </p>
          </div>
          <div className="rounded-xl border p-4" style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}>
            <p className="text-xs text-[var(--text-muted)] mb-1">查看方式</p>
            <p className="text-sm text-[var(--text-dim)]">主页看摘要，详情页看全量代码与调试信息</p>
          </div>
        </div>
        <div
          className="rounded-xl border p-4 space-y-3"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
        >
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-[var(--text)]">步骤概览</h3>
            <Link
              to="/details#detail-instantiation"
              className="px-3 py-1.5 rounded-lg text-xs border text-[var(--de-cyan)] hover:bg-[var(--de-cyan-glow)] transition-colors"
              style={{ borderColor: 'var(--border-glow)' }}
            >
              查看全量实例化代码
            </Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {steps.map((s) => (
              <div
                key={s.step_index}
                className="rounded-lg border px-3 py-2 text-sm"
                style={{
                  borderColor: s.step_index === currentStep?.step_index ? 'var(--de-cyan-dim)' : 'var(--border)',
                  background: s.step_index === currentStep?.step_index ? 'var(--de-cyan-glow)' : 'var(--bg-card)',
                }}
              >
                <span className="font-mono text-[var(--text-muted)] mr-1">#{s.step_index}</span>
                <span className="text-[var(--text-dim)]">{s.operator_name}</span>
              </div>
            ))}
          </div>
          {currentStep?.code && (
            <div>
              <p className="text-xs text-[var(--text-muted)] mb-2">当前步骤代码片段（预览）</p>
              <CodeBlock code={currentStep.code.split('\n').slice(0, 16).join('\n')} />
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <p className="section-label">实例化代码 (Stage 3)</p>
          <h2 className="text-base font-semibold text-[var(--text)]">按 Step 展开代码</h2>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={expandAll}
            className="text-sm px-2 py-1 rounded"
            style={{ color: 'var(--text-muted)' }}
          >
            展开全部
          </button>
          <button
            type="button"
            onClick={collapseAll}
            className="text-sm px-2 py-1 rounded"
            style={{ color: 'var(--text-muted)' }}
          >
            折叠全部
          </button>
        </div>
      </div>
      <p className="text-sm text-[var(--text-muted)]">
        第三步：DataEvolver 将 DAG 中的每个算子实例化为具体 Python 代码。你可以逐步展开阅读，也可以结合日志 Debug。
        接口预留：GET /api/pipeline/{'{id}'}/instantiation/steps 或 instantiation_step_done 推送；新 step 完成时追加并高亮。
      </p>
      <div className="space-y-3">
        {steps.length === 0 && (
          <p className="text-sm text-[var(--text-muted)]">暂无实例化结果，请先完成编排并推进到实例化步骤。</p>
        )}
        {steps.map((s) => {
          const isOpen = expanded[s.step_index] ?? false
          const isCurrent = currentInstantiationStep === s.step_index
          return (
            <div
              key={s.step_index}
              className={clsx(
                'rounded-xl border overflow-hidden transition-stage',
                isCurrent ? 'border-[var(--border-glow)] bg-[var(--de-cyan-glow)]' : 'border-[var(--border)] bg-[var(--bg-panel)]'
              )}
            >
              <button
                type="button"
                onClick={() => toggle(s.step_index)}
                className="w-full flex items-center gap-2 px-4 py-3 text-left"
                style={{ cursor: 'pointer' }}
              >
                {isOpen ? (
                  <ChevronDown className="w-4 h-4 text-[var(--text-muted)]" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-[var(--text-muted)]" />
                )}
                <span className="font-medium text-[var(--text)]">
                  Step {s.step_index}: {s.operator_name}
                </span>
                {isCurrent && (
                  <span className="text-xs px-2 py-0.5 rounded text-[var(--de-cyan)]" style={{ background: 'var(--de-cyan-glow)' }}>
                    当前
                  </span>
                )}
              </button>
              {isOpen && (
                <div
                  className="border-t px-4 py-3 space-y-2"
                  style={{ borderColor: 'var(--border)' }}
                >
                  {s.intermediate_summary && (
                    <p className="text-xs text-[var(--text-muted)]">{s.intermediate_summary}</p>
                  )}
                  <CodeBlock code={s.code} />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
