import { useAppStore } from '../stores/appStore'
import { Loader2, Play, RefreshCw } from 'lucide-react'

export function QualityCheckPage() {
  const judgeResult = useAppStore((s) => s.judgeResult)
  const experiences = useAppStore((s) => s.experiences)
  const sampleProcessedStore = useAppStore((s) => s.sampleProcessed)
  const sampleSeedStore = useAppStore((s) => s.sampleSeed)
  const qualityCheckLoading = useAppStore((s) => s.qualityCheckLoading)
  const setQualityCheck = useAppStore((s) => s.setQualityCheck)
  const setCurrentStage = useAppStore((s) => s.setCurrentStage)
  const setToast = useAppStore((s) => s.setToast)

  const runSample = async () => {
    setQualityCheck({ loading: true })
    setQualityCheck({ loading: false })
    setToast({ message: '请在主流程中执行试运行与质检后查看真实结果。', type: 'info' })
  }

  const judge = judgeResult
  const exp = experiences
  const processed = sampleProcessedStore
  const seed = sampleSeedStore

  return (
    <div className="space-y-8">
      <div>
        <p className="section-label">质量检查 (Stage 4)</p>
        <p className="text-sm text-[var(--text-dim)]">
          第四步：用少量采样数据跑一遍 Pipeline，对比 Seed，查看 Judge 结果与进化经验，决定是否需要再自进化一轮。
        </p>
      </div>
      <div className="flex items-center gap-4">
        <button
          onClick={runSample}
          disabled={qualityCheckLoading}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm text-[var(--bg-deep)] disabled:opacity-50"
          style={{ background: 'linear-gradient(135deg, #00e5c8, #00b4d8)' }}
        >
          {qualityCheckLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          小规模采样执行
        </button>
        <span className="text-sm text-[var(--text-muted)]">
          接口预留：quality_check_sample_done / quality_check_judge_done 推送
        </span>
      </div>

      <h2 className="text-base font-semibold text-[var(--text)]">采样生成结果 vs Seed 对比</h2>
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-xl border overflow-hidden" style={{ background: 'var(--bg-panel)', borderColor: 'var(--border)' }}>
          <div className="px-4 py-2 text-sm font-medium text-[var(--text-dim)]" style={{ background: 'var(--bg-card)' }}>采样生成结果</div>
          <div className="p-4 max-h-64 overflow-auto space-y-2">
            {processed.map((row, i) => (
              <pre
                key={i}
                className="text-xs p-2 rounded"
                style={{ background: 'var(--bg-card)', color: 'var(--text-dim)' }}
              >
                {JSON.stringify(row, null, 2)}
              </pre>
            ))}
          </div>
        </div>
        <div className="rounded-xl border overflow-hidden" style={{ background: 'var(--bg-panel)', borderColor: 'var(--border)' }}>
          <div className="px-4 py-2 text-sm font-medium text-[var(--text-dim)]" style={{ background: 'var(--bg-card)' }}>Seed 数据</div>
          <div className="p-4 max-h-64 overflow-auto space-y-2">
            {seed.map((row, i) => (
              <pre
                key={i}
                className="text-xs p-2 rounded"
                style={{ background: 'var(--bg-card)', color: 'var(--text-dim)' }}
              >
                {JSON.stringify(row, null, 2)}
              </pre>
            ))}
          </div>
        </div>
      </div>

      <h2 className="text-base font-semibold text-[var(--text)]">Judge 结果 · Seed Benchmark</h2>
      <div
        className="rounded-2xl border p-4 space-y-4"
        style={{ background: 'var(--bg-panel)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center justify-between">
          <p className="text-sm text-[var(--text-dim)]">展示当前轮真实评估结果（无占位分数）。</p>
          <div className="text-xs text-[var(--text-muted)]">数据源：workflow 真实结果</div>
        </div>
        <div className="text-xs text-[var(--text-muted)]">如需多维评分条，请由后端返回对应指标字段后再渲染。</div>
        <div className="border-t pt-3 mt-1" style={{ borderColor: 'var(--border)' }}>
          <p className="text-sm text-[var(--text-dim)] mb-1">
            <span className="text-[var(--text-muted)]">整体评估：</span>
            {judge?.overall_assessment ?? '—'}
          </p>
          {judge?.critical_insights && judge.critical_insights.length > 0 && (
            <p className="text-xs text-[var(--text-muted)]">
              关键结论：{judge.critical_insights.join('；')}
            </p>
          )}
        </div>
      </div>

      {exp.length > 0 && (
        <>
          <h2 className="text-base font-semibold text-[var(--text)]">本轮经验（流水线级自进化）</h2>
          <ul className="space-y-2">
            {exp.map((e, i) => (
              <li key={i} className="rounded-lg border px-4 py-2 text-sm text-[var(--text-dim)]" style={{ borderColor: 'var(--de-orange-dim)', background: 'rgba(255,140,66,0.08)' }}>
                {e}
              </li>
            ))}
          </ul>
          <button
            onClick={() => setCurrentStage('upload')}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border text-[var(--de-cyan)] hover:bg-[var(--de-cyan-glow)] transition-colors"
            style={{ borderColor: 'var(--border-glow)' }}
          >
            <RefreshCw className="w-4 h-4" />
            将经验反馈到理解并重新运行 Stage 1
          </button>
        </>
      )}
    </div>
  )
}
