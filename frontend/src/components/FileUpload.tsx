import { useCallback, useRef } from 'react'
import { Upload, X, FileText } from 'lucide-react'
import clsx from 'clsx'

interface FileInfo {
  name?: string
  size?: number
  rows?: number
  error?: string
}

interface FileUploadProps {
  label: string
  accept: string
  value?: FileInfo
  onChange: (info: FileInfo) => void
  onFileSelect: (file: File) => Promise<{ rows?: number; error?: string }>
  required?: boolean
}

export function FileUpload({
  label,
  accept,
  value,
  onChange,
  onFileSelect,
  required,
}: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (!file) return
      const result = await onFileSelect(file)
      onChange({
        name: file.name,
        size: file.size,
        rows: result.rows,
        error: result.error,
      })
      e.target.value = ''
    },
    [onChange, onFileSelect]
  )

  const clear = useCallback(() => {
    onChange({})
    if (inputRef.current) inputRef.current.value = ''
  }, [onChange])

  const hasFile = value?.name && !value?.error
  const hasError = value?.error

  return (
    <div
      className="rounded-xl border p-4"
      style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-[var(--text)]">
          {label}
          {required && <span className="text-red-400 ml-0.5">*</span>}
        </span>
        {hasFile && (
          <button
            type="button"
            onClick={clear}
            className="text-[var(--text-muted)] hover:text-red-400 p-1 rounded transition-colors"
            title="清除"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={handleFile}
        className="hidden"
      />
      {!hasFile ? (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className={clsx(
            'w-full flex items-center justify-center gap-2 py-6 rounded-lg border-2 border-dashed transition-colors',
            hasError
              ? 'border-red-500/50 bg-red-500/5 text-red-400'
              : 'border-[var(--border)] hover:border-brand-500/50 hover:bg-brand-500/5 text-[var(--text-muted)] hover:text-brand-400'
          )}
        >
          <Upload className="w-5 h-5" />
          <span>点击或拖拽上传</span>
        </button>
      ) : (
        <div
          className="flex items-center gap-3 py-2 px-3 rounded-lg"
          style={{ background: 'var(--bg-card)' }}
        >
          <FileText className="w-5 h-5 text-brand-400 shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-medium text-[var(--text)] truncate">{value.name}</p>
            <p className="text-xs text-[var(--text-dim)]">
              {value.size != null && `${(value.size / 1024).toFixed(1)} KB`}
              {value.rows != null && ` · ${value.rows} 行`}
            </p>
          </div>
        </div>
      )}
      {hasError && <p className="mt-2 text-sm text-red-400">{value.error}</p>}
    </div>
  )
}
