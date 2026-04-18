import { useState } from 'react'
import { useAppStore } from '../stores/appStore'
import { Play, Download } from 'lucide-react'

export function ExecutionPage() {
  const executionLoading = useAppStore((s) => s.executionLoading)
  const executionProgress = useAppStore((s) => s.executionProgress)
  const executionResult = useAppStore((s) => s.executionResult)
  const setExecution = useAppStore((s) => s.setExecution)
  const setToast = useAppStore((s) => s.setToast)

  const [confirmOpen, setConfirmOpen] = useState(false)

  const runFull = async () => {
    setConfirmOpen(false)
    setExecution(null, null, false)
    setToast({ message: '请在主流程页面点击“应用当前 pipeline 到全量数据”执行真实全量运行。', type: 'info' })
  }

  const result = executionResult ?? null
  const progress = executionProgress

  return (
    <div className="space-y-8">
      <div>
        <p className="section-label">全量执行与结果</p>
        <p className="text-sm text-[var(--text-dim)]">
          当你对采样质量满意后，可以在这里执行全量数据。支持查看执行进度、日志与最终统计结果。
          接口预留：POST /api/pipeline/{'{id}'}/run-full；SSE/WebSocket execution_progress / execution_done；或轮询 jobs/{'{job_id}'}/progress。
        </p>
      </div>

      {!result && !executionLoading && (
        <button
          onClick={() => setConfirmOpen(true)}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm text-[var(--bg-deep)]"
          style={{ background: 'linear-gradient(135deg, #00e5c8, #00b4d8)' }}
        >
          <Play className="w-4 h-4" />
          执行全量数据
        </button>
      )}

      {confirmOpen && (
        <div
          className="rounded-xl border p-4 max-w-md"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
        >
          <p className="mb-4 text-[var(--text-dim)]">将对当前 Pipeline 执行全量 Raw 数据，预计耗时视数据量而定。确认执行？</p>
          <div className="flex gap-2">
            <button onClick={runFull} className="px-3 py-2 rounded-lg bg-brand-500 text-white text-sm">
              确认
            </button>
            <button
              onClick={() => setConfirmOpen(false)}
              className="px-3 py-2 rounded-lg text-sm"
              style={{ background: 'var(--bg-card)', color: 'var(--text)' }}
            >
              取消
            </button>
          </div>
        </div>
      )}

      {executionLoading && progress && (
        <div
          className="rounded-xl border p-4 space-y-3"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
        >
          <div className="flex justify-between text-sm text-[var(--text-dim)]">
            <span>{progress.message}</span>
            <span>{progress.percent}%</span>
          </div>
          <div className="h-2 rounded-full overflow-hidden" style={{ background: 'var(--bg-card)' }}>
            <div
              className="h-full bg-brand-500 rounded-full transition-all duration-300"
              style={{ width: `${progress.percent ?? 0}%` }}
            />
          </div>
            {progress.log_lines?.length ? (
              <pre className="text-xs font-mono overflow-auto max-h-24 text-[var(--text-muted)]">
              {progress.log_lines.join('\n')}
            </pre>
          ) : null}
        </div>
      )}

      {result && !executionLoading && (
        <div
          className="rounded-xl border p-4 space-y-4"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
        >
          <div className="flex items-center justify-between">
            <h3 className="font-medium text-[var(--text)]">执行结果</h3>
            <a
              href={result.download_url}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-brand-500/20 text-brand-400 hover:bg-brand-500/30 text-sm"
            >
              <Download className="w-4 h-4" />
              下载 final_processed_data.jsonl
            </a>
          </div>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div className="rounded-lg px-3 py-2" style={{ background: 'var(--bg-card)' }}>
              <p className="text-[var(--text-muted)]">总行数</p>
              <p className="font-mono text-[var(--text)]">{result.total_rows ?? '-'}</p>
            </div>
            <div className="rounded-lg px-3 py-2" style={{ background: 'var(--bg-card)' }}>
              <p className="text-[var(--text-muted)]">耗时</p>
              <p className="font-mono text-[var(--text)]">
                {result.duration_sec != null ? `${result.duration_sec}s` : '-'}
              </p>
            </div>
            <div className="rounded-lg px-3 py-2" style={{ background: 'var(--bg-card)' }}>
              <p className="text-[var(--text-muted)]">状态</p>
              <p className="text-[var(--text)]">{result.status ?? '-'}</p>
            </div>
          </div>
          {result.preview && result.preview.length > 0 && (
            <div>
              <p className="text-sm text-[var(--text-muted)] mb-2">预览</p>
              <div
                className="rounded-lg p-3 max-h-48 overflow-auto space-y-2"
                style={{ background: 'var(--bg-card)' }}
              >
                {result.preview.map((row, i) => (
                  <pre key={i} className="text-xs text-[var(--text-dim)]">
                    {JSON.stringify(row, null, 2)}
                  </pre>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
