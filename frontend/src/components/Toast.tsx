import { useEffect } from 'react'
import { CheckCircle2, XCircle, Info } from 'lucide-react'
import clsx from 'clsx'

interface ToastProps {
  message: string
  type: 'success' | 'error' | 'info'
  onClose: () => void
}

export function Toast({ message, type, onClose }: ToastProps) {
  useEffect(() => {
    const t = setTimeout(onClose, 4000)
    return () => clearTimeout(t)
  }, [onClose])

  const icon =
    type === 'success' ? (
      <CheckCircle2 className="w-5 h-5 text-green-400" />
    ) : type === 'error' ? (
      <XCircle className="w-5 h-5 text-red-400" />
    ) : (
      <Info className="w-5 h-5 text-brand-400" />
    )

  return (
    <div
      className={clsx(
        'fixed bottom-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg border backdrop-blur-sm animate-in',
        type === 'success' && 'border-green-500/40',
        type === 'error' && 'border-red-500/40',
        type === 'info' && 'border-brand-500/40'
      )}
      style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
    >
      {icon}
      <span className="text-sm" style={{ color: 'var(--text)' }}>
        {message}
      </span>
    </div>
  )
}
