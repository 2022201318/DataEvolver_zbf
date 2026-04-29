import { useState } from 'react'
import { useAppStore } from '../stores/appStore'
import { BarChart3, X } from 'lucide-react'

/**
 * Token & 时间消耗浮窗：
 * - 默认折叠在右下角一个小图标，点击展开查看详细统计
 * - 不占据主布局空间，用户想看时再打开
 * - 当前数据由 store 提供，后续可由后端实时更新
 */
export function TokenStatsPanel() {
  const [open, setOpen] = useState(false)
  const stats = useAppStore((s) => s.tokenStats)

  const safeTotal = stats.totalTokens || stats.promptTokens + stats.completionTokens || 1
  const promptRatio = Math.min(1, stats.promptTokens / safeTotal)
  const completionRatio = Math.min(1, stats.completionTokens / safeTotal)
  const timeRatio = Math.min(1, stats.elapsedSec / 120 || 0) // 以 120s 作为简单参考上限

  return (
    <div className="fixed bottom-4 right-4 z-40">
      {open ? (
        <div
          className="rounded-2xl border shadow-lg backdrop-blur-sm w-80 p-4 space-y-3 animate-in"
          style={{ background: 'var(--bg-panel)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-base font-semibold text-[var(--text)]">
              <BarChart3 className="w-5 h-5 text-[var(--de-cyan)]" />
              Token & 时间消耗
            </div>
            <button
              type="button"
              className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text)]"
              onClick={() => setOpen(false)}
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          <p className="text-xs text-[var(--text-dim)]">
            统计 多模态数据准备 四阶段中调用 LLM 的 Token 与时间开销。后端使用 FastAPI 统一汇总并实时推送。
          </p>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-lg bg-[var(--bg-card)] px-3 py-2.5">
              <p className="text-[var(--text-muted)] mb-1 text-xs uppercase tracking-wide">Prompt Tokens</p>
              <p className="font-mono text-[var(--text)] text-lg">{stats.promptTokens}</p>
            </div>
            <div className="rounded-lg bg-[var(--bg-card)] px-3 py-2.5">
              <p className="text-[var(--text-muted)] mb-1 text-xs uppercase tracking-wide">Completion</p>
              <p className="font-mono text-[var(--text)] text-lg">{stats.completionTokens}</p>
            </div>
            <div className="rounded-lg bg-[var(--bg-card)] px-3 py-2.5">
              <p className="text-[var(--text-muted)] mb-1 text-xs uppercase tracking-wide">Total Tokens</p>
              <p className="font-mono text-[var(--text)] text-lg">{stats.totalTokens}</p>
            </div>
            <div className="rounded-lg bg-[var(--bg-card)] px-3 py-2.5">
              <p className="text-[var(--text-muted)] mb-1 text-xs uppercase tracking-wide">估算费用</p>
              <p className="font-mono text-[var(--text)] text-lg">${stats.estimatedCost.toFixed(4)}</p>
            </div>
          </div>
          <div className="rounded-lg bg-[var(--bg-card)] px-3 py-2.5 text-xs space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-[var(--text-muted)]">Prompt vs Completion 占比</p>
              <p className="font-mono text-[var(--text-dim)]">
                {Math.round(promptRatio * 100)}% / {Math.round(completionRatio * 100)}%
              </p>
            </div>
            <div className="h-2 rounded-full overflow-hidden flex" style={{ background: 'var(--bg-panel)' }}>
              <div
                style={{ width: `${promptRatio * 100}%`, background: 'linear-gradient(90deg, #22d3ee, #0ea5e9)' }}
              />
              <div
                style={{ width: `${completionRatio * 100}%`, background: 'linear-gradient(90deg, #f97316, #ea580c)' }}
              />
            </div>
          </div>
          <div className="rounded-lg bg-[var(--bg-card)] px-3 py-2.5 text-xs space-y-1">
            <div className="flex items-center justify-between">
              <p className="text-[var(--text-muted)]">累计耗时</p>
              <p className="font-mono text-[var(--text)] text-sm">
                {stats.elapsedSec.toFixed(1)}s
              </p>
            </div>
            <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--bg-panel)' }}>
              <div
                className="h-full rounded-full"
                style={{
                  width: `${timeRatio * 100}%`,
                  background: 'linear-gradient(90deg, #22c55e, #84cc16)',
                }}
              />
            </div>
          </div>
        </div>
      ) : null}
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="rounded-full w-9 h-9 flex items-center justify-center shadow-md border bg-[var(--bg-card)] border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--de-cyan)] hover:border-[var(--de-cyan-dim)]"
        >
          <BarChart3 className="w-4 h-4" />
        </button>
      )}
    </div>
  )
}

