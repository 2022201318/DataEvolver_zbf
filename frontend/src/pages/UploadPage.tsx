import { useEffect, useState } from 'react'
import { useAppStore } from '../stores/appStore'
import { FileUpload } from '../components/FileUpload'
import { Collapse } from '../components/Collapse'
import { ApiError, fetchPipelinePreview, runPipelineUnderstand } from '../api'
import { Loader2, Play } from 'lucide-react'

export function UploadPage() {
  const upload = useAppStore((s) => s.upload)
  const setUpload = useAppStore((s) => s.setUpload)
  const understandingLoading = useAppStore((s) => s.understandingLoading)
  const understandingResult = useAppStore((s) => s.understandingResult)
  const setUnderstanding = useAppStore((s) => s.setUnderstanding)
  const experienceText = useAppStore((s) => s.experienceText)
  const setExperienceText = useAppStore((s) => s.setExperienceText)
  const setToast = useAppStore((s) => s.setToast)
  const pipelineId = useAppStore((s) => s.pipelineId)

  const llmConfig = useAppStore((s) => s.llmConfig)
  const setLlmConfig = useAppStore((s) => s.setLlmConfig)

  const [previewTab, setPreviewTab] = useState<'raw' | 'seed' | 'desc'>('raw')
  const [previewLines, setPreviewLines] = useState<string[]>([])
  const [previewHint, setPreviewHint] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)

  const sessionPipelineId = pipelineId ?? upload.pipelineId ?? null
  const canRunUnderstanding = Boolean(
    sessionPipelineId && upload.raw?.name && !upload.raw?.error && upload.seed?.name && !upload.seed?.error
  )

  useEffect(() => {
    if (!sessionPipelineId) {
      setPreviewLines([])
      setPreviewHint('')
      return
    }
    const kind = previewTab === 'desc' ? 'description' : previewTab
    let cancelled = false
    setPreviewLoading(true)
    void fetchPipelinePreview(sessionPipelineId, kind)
      .then((r) => {
        if (cancelled) return
        if (!r.ok) {
          setPreviewLines([])
          setPreviewHint(r.error || '预览不可用（文件缺失或路径无效）')
          return
        }
        setPreviewLines(r.lines ?? [])
        const parts: string[] = [r.relative_path]
        if (r.truncated_lines) parts.push('行已截断')
        if (r.truncated_chars) parts.push('字符已截断')
        setPreviewHint(parts.join(' · '))
      })
      .catch((e) => {
        if (cancelled) return
        setPreviewLines([])
        const msg =
          e instanceof ApiError
            ? `预览加载失败（HTTP ${e.status}）`
            : '预览请求失败，请确认已「启动」会话且后端可访问'
        setPreviewHint(msg)
      })
      .finally(() => {
        if (!cancelled) setPreviewLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [sessionPipelineId, previewTab])

  const runUnderstanding = async () => {
    if (!canRunUnderstanding || !sessionPipelineId) return
    setUnderstanding(true)
    try {
      const res = await runPipelineUnderstand(sessionPipelineId, { mode: 'auto' })
      setUnderstanding(false, res.result)
      const lang = res.result.language ?? 'unknown'
      setToast({ message: `数据理解完成（内容语言: ${lang}）`, type: 'success' })
    } catch (e) {
      setUnderstanding(false)
      let msg = '数据理解失败'
      if (e instanceof ApiError && e.detail) {
        try {
          const j = JSON.parse(e.detail) as { detail?: unknown }
          if (typeof j.detail === 'string') msg = j.detail
          else msg = `${msg}: ${e.detail.slice(0, 200)}`
        } catch {
          msg = `${msg}: ${e.detail.slice(0, 200)}`
        }
      }
      setToast({ message: msg, type: 'error' })
    }
  }

  return (
    <div className="space-y-10">
      <section>
        <p className="section-label">数据上传 &amp; 模型参数</p>
        <p className="text-sm text-[var(--text-dim)] mb-3">
          第一步：选择 Raw / Seed / 描述文件，并配置默认大模型与解码参数。后续所有 Stage 的调用都会以这里为基准。
        </p>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <FileUpload
                label="Raw Data"
                accept=".jsonl"
                required
                value={upload.raw}
                onChange={(info) =>
                  setUpload({
                    raw:
                      info.name && info.size != null
                        ? { name: info.name, size: info.size, rows: info.rows, error: info.error }
                        : undefined,
                  })
                }
                onFileSelect={async () => ({})}
              />
              <FileUpload
                label="Seed Data"
                accept=".jsonl"
                required
                value={upload.seed}
                onChange={(info) =>
                  setUpload({
                    seed:
                      info.name && info.size != null
                        ? { name: info.name, size: info.size, rows: info.rows, error: info.error }
                        : undefined,
                  })
                }
                onFileSelect={async () => ({})}
              />
              <FileUpload
                label="Description (可选)"
                accept=".txt,.md"
                value={upload.description}
                onChange={(info) =>
                  setUpload({
                    description:
                      info.name && info.size != null
                        ? { name: info.name, size: info.size, error: info.error }
                        : undefined,
                  })
                }
                onFileSelect={async () => ({})}
              />
            </div>
          </div>
          <div className="space-y-3">
            <div className="rounded-xl border" style={{ background: 'var(--bg-panel)', borderColor: 'var(--border)' }}>
              <div className="px-4 py-3 border-b" style={{ borderColor: 'var(--border)' }}>
                <p className="text-xs font-mono text-[var(--text-muted)] tracking-[0.16em] uppercase">Provider &amp; Model</p>
              </div>
              <div className="p-4 space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="text-xs text-[var(--text-dim)]">服务商</label>
                    <select
                      className="mt-1 w-full rounded-md border bg-transparent px-3 py-1.5 text-sm"
                      style={{ borderColor: 'var(--border)' }}
                      value={llmConfig.provider}
                      onChange={(e) => setLlmConfig({ provider: e.target.value })}
                    >
                      <option value="openai">OpenAI / Azure OpenAI</option>
                      <option value="local">本地/自建模型</option>
                      <option value="other">其他云服务商</option>
                    </select>
                  </div>
                  <div className="space-y-2">
                    <label className="text-xs text-[var(--text-dim)]">模型</label>
                    <select
                      className="mt-1 w-full rounded-md border bg-transparent px-3 py-1.5 text-sm"
                      style={{ borderColor: 'var(--border)' }}
                      value={llmConfig.model}
                      onChange={(e) => setLlmConfig({ model: e.target.value })}
                    >
                      <option value="gpt-4.1">gpt-4.1</option>
                      <option value="gpt-4o">gpt-4o</option>
                      <option value="gpt-4.1-mini">gpt-4.1-mini</option>
                      <option value="custom">自定义（后端配置）</option>
                    </select>
                  </div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <div className="flex items-center justify-between text-xs text-[var(--text-dim)] mb-1">
                      <span>Temperature</span>
                      <span className="font-mono">{llmConfig.temperature.toFixed(2)}</span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.01}
                      value={llmConfig.temperature}
                      onChange={(e) => setLlmConfig({ temperature: Number(e.target.value) })}
                      className="w-full"
                    />
                  </div>
                  <div>
                    <div className="flex items-center justify-between text-xs text-[var(--text-dim)] mb-1">
                      <span>Max Tokens</span>
                      <span className="font-mono">{llmConfig.maxTokens}</span>
                    </div>
                    <input
                      type="range"
                      min={512}
                      max={8192}
                      step={256}
                      value={llmConfig.maxTokens}
                      onChange={(e) => setLlmConfig({ maxTokens: Number(e.target.value) })}
                      className="w-full"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section>
        <p className="section-label">数据预览</p>
        <p className="text-sm text-[var(--text-dim)] mb-3">
          在继续之前，先快速对比 Raw 与 Seed 的结构与内容，确认输入是否符合预期。
        </p>
        <div
          className="rounded-xl border overflow-hidden"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
        >
          <div className="flex border-b" style={{ borderColor: 'var(--border)' }}>
            {(['raw', 'seed', 'desc'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setPreviewTab(tab)}
                className={`px-4 py-2.5 text-sm font-medium transition-colors ${
                  previewTab === tab
                    ? 'text-[var(--de-teal)] border-b-2 border-[var(--de-teal)] bg-[var(--bg-card)]'
                    : 'text-[var(--text-muted)] hover:text-[var(--text)]'
                }`}
              >
                {tab === 'raw' && 'Raw'}
                {tab === 'seed' && 'Seed'}
                {tab === 'desc' && 'Description'}
              </button>
            ))}
          </div>
          <div className="p-4 min-h-[200px] max-h-[320px] overflow-auto">
            {!sessionPipelineId && (
              <p className="text-sm text-[var(--text-dim)]">
                请先在侧栏点击「启动」并填写 Pipeline ID，将文件写入服务端后，此处会请求{' '}
                <code className="text-xs">GET /api/pipeline/&lt;id&gt;/preview/…</code> 展示前几行。
              </p>
            )}
            {sessionPipelineId && previewLoading && (
              <p className="text-sm text-[var(--text-muted)] flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                正在加载预览…
              </p>
            )}
            {sessionPipelineId && !previewLoading && (
              <>
                {previewHint ? (
                  <p className="text-[11px] text-[var(--text-muted)] mb-2 font-mono break-all">{previewHint}</p>
                ) : null}
                {previewLines.length > 0 ? (
                  <pre className="text-[11px] leading-relaxed text-[var(--text-dim)] whitespace-pre-wrap font-mono">
                    {previewLines.join('\n')}
                  </pre>
                ) : previewHint ? (
                  <p className="text-sm text-[var(--text-dim)]">无预览行（文件可能为空或该类型未上传）。</p>
                ) : null}
              </>
            )}
          </div>
        </div>
      </section>

      <section>
        <p className="section-label">数据理解 (Stage 1)</p>
        <p className="text-sm text-[var(--text-dim)] mb-3">
          多模态数据准备 会分析 Raw 与 Seed 的差异，提取数据画像与质量指标，为后续 DAG 编排提供依据。
        </p>
        <div className="flex items-center gap-4 mb-4">
          <button
            onClick={runUnderstanding}
            disabled={!canRunUnderstanding || understandingLoading}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background: 'linear-gradient(135deg, #00e5c8, #00b4d8)',
              color: '#06090f',
            }}
          >
            {understandingLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            执行数据理解
          </button>
          <span className="text-sm text-[var(--text-muted)]">
            {sessionPipelineId
              ? `已绑定会话 ${sessionPipelineId}；POST /api/pipeline/{id}/understand（auto：有 Key 时极简 LLM 判语言，否则启发式）`
              : '需先启动会话后再执行理解'}
          </span>
        </div>
        {understandingResult?.language && (
          <p className="text-sm text-[var(--text-dim)] mb-2">
            检测结果 · 内容语言码 <span className="font-mono text-[var(--text)]">{understandingResult.language}</span>
            {understandingResult.language_label ? (
              <>
                {' '}
               （{understandingResult.language_label}）
              </>
            ) : null}
            {understandingResult.user_declared_language ? (
              <span className="text-[var(--text-muted)]">
                {' '}
                · 上传表单声明: {understandingResult.user_declared_language}
              </span>
            ) : null}
          </p>
        )}
        {experienceText && (
          <div className="mb-4 rounded-lg border p-4" style={{ borderColor: 'var(--de-orange-dim)', background: 'rgba(255,140,66,0.06)' }}>
            <p className="text-sm font-medium text-[var(--text)] mb-2">上一轮经验（流水线级自进化）</p>
            <textarea
              value={experienceText}
              onChange={(e) => setExperienceText(e.target.value)}
              className="w-full h-20 rounded border text-sm p-2 resize-none"
              style={{ background: 'var(--bg-panel)', borderColor: 'var(--border)', color: 'var(--text)' }}
              placeholder="经验文本..."
            />
          </div>
        )}
        {understandingResult && (
          <div className="space-y-3 transition-stage">
            <Collapse title="basic_information" defaultOpen>
              <pre className="text-xs text-[var(--text-dim)] whitespace-pre-wrap">
                {JSON.stringify(understandingResult.basic_information, null, 2)}
              </pre>
            </Collapse>
            <Collapse title="schema_analysis">
              <pre className="text-xs text-[var(--text-dim)] whitespace-pre-wrap">
                {JSON.stringify(understandingResult.schema_analysis, null, 2)}
              </pre>
            </Collapse>
            <Collapse title="dataset_level_delta">
              <pre className="text-xs text-[var(--text-dim)] whitespace-pre-wrap">
                {JSON.stringify(understandingResult.dataset_level_delta, null, 2)}
              </pre>
            </Collapse>
          </div>
        )}
      </section>
    </div>
  )
}
