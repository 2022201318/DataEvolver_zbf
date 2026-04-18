import { useState } from 'react'
import { useAppStore } from '../stores/appStore'
import { DagCanvas } from '../components/DagCanvas'
import { Collapse } from '../components/Collapse'
import { Link } from 'react-router-dom'

export function OrchestrationPage({ showOperatorLibrary = true }: { showOperatorLibrary?: boolean }) {
  const dag = useAppStore((s) => s.dag)
  const pipelinePlan = useAppStore((s) => s.pipelinePlan)
  const operators = useAppStore((s) => s.operators)
  const [activeNodeId, setActiveNodeId] = useState<string | undefined>(undefined)

  const currentDag = dag
  const currentPlan = pipelinePlan

  return (
    <div className={showOperatorLibrary ? 'grid grid-cols-1 lg:grid-cols-3 gap-8' : 'space-y-5'}>
      <div className={showOperatorLibrary ? 'lg:col-span-2 space-y-5' : 'space-y-5'}>
        <p className="section-label">DAG 与 Pipeline 计划</p>
        <p className="text-sm text-[var(--text-dim)] mb-1">
          第二步：查看自动编排出的算子 DAG 和 Pipeline 计划。每个节点代表一个算子，边上的粒子表示数据流动。
        </p>
        <DagCanvas
          nodes={currentDag?.nodes ?? []}
          edges={currentDag?.edges ?? []}
          executionOrder={currentDag?.execution_order ?? []}
          activeNodeId={activeNodeId}
          height={340}
        />
        <p className="text-xs text-[var(--text-muted)]">
          接口预留：GET /api/pipeline/{'{id}'}/orchestration/dag（FastAPI）；orchestration_dag 推送；重编排后刷新
        </p>

        <h2 className="text-base font-semibold text-[var(--text)] mt-6">Pipeline 计划</h2>
        <div
          className="rounded-xl border overflow-hidden"
          style={{ background: 'var(--bg-panel)', borderColor: 'var(--border)' }}
        >
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left" style={{ background: 'var(--bg-card)' }}>
                <th className="px-4 py-2.5 font-medium text-[var(--text-dim)]">Step</th>
                <th className="px-4 py-2.5 font-medium text-[var(--text-dim)]">算子</th>
                <th className="px-4 py-2.5 font-medium text-[var(--text-dim)]">描述</th>
              </tr>
            </thead>
            <tbody>
              {currentPlan.map((row) => (
                <tr
                  key={row.step}
                  className="border-t hover:bg-white/5 transition-colors cursor-pointer"
                  style={{ borderColor: 'var(--border)' }}
                  onClick={() => setActiveNodeId(currentDag?.nodes?.[row.step - 1]?.node_id)}
                >
                  <td className="px-4 py-2 text-[var(--text-muted)] font-mono">{row.step}</td>
                  <td className="px-4 py-2 font-mono text-[var(--de-cyan)]">{row.operator}</td>
                  <td className="px-4 py-2 text-[var(--text-dim)]">{row.description ?? '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!showOperatorLibrary && (
          <div
            className="rounded-xl border p-4 flex items-center justify-between gap-4"
            style={{ borderColor: 'var(--border)', background: 'var(--bg-card)' }}
          >
            <div>
              <p className="text-sm font-medium text-[var(--text)]">更多编排细节已收纳到深度详情页</p>
              <p className="text-xs text-[var(--text-muted)] mt-1">
                包括完整算子库、Step 级实例化代码与调试视图，主页仅保留关键流程信息。
              </p>
            </div>
            <Link
              to="/details#detail-orchestration"
              className="shrink-0 px-3 py-2 rounded-lg text-sm border text-[var(--de-cyan)] hover:bg-[var(--de-cyan-glow)] transition-colors"
              style={{ borderColor: 'var(--border-glow)' }}
            >
              进入深度详情
            </Link>
          </div>
        )}
      </div>

      {showOperatorLibrary && (
        <div className="space-y-4" id="detail-orchestration">
          <p className="section-label">算子库</p>
          <div
            className="rounded-xl border p-4 max-h-[500px] overflow-auto space-y-3"
            style={{ background: 'var(--bg-panel)', borderColor: 'var(--border)' }}
          >
            {operators.map((op) => (
              <Collapse key={op.name} title={op.name}>
                <p className="text-xs text-[var(--text-dim)] mb-2">{op.description}</p>
                <p className="text-xs text-[var(--text-muted)]">
                  in: [{op.input_keys.join(', ')}] → out: [{op.output_keys.join(', ')}]
                  {op.requires_llm && <span className="ml-2 text-[var(--de-orange)]">LLM</span>}
                </p>
              </Collapse>
            ))}
            {operators.length === 0 && (
              <p className="text-xs text-[var(--text-muted)]">暂无算子数据，请先执行编排步骤。</p>
            )}
          </div>
          <p className="text-xs text-[var(--text-muted)]">
            接口预留：GET /api/operators（FastAPI 模块化）；operators_updated 推送刷新
          </p>
        </div>
      )}
    </div>
  )
}
