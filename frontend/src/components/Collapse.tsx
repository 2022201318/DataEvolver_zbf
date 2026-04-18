import { ReactNode, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import clsx from 'clsx'

interface CollapseProps {
  title: string
  children: ReactNode
  defaultOpen?: boolean
  className?: string
}

export function Collapse({ title, children, defaultOpen = false, className }: CollapseProps) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div
      className={clsx('rounded-lg border overflow-hidden', className)}
      style={{ borderColor: 'var(--border)' }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left text-sm font-medium transition-colors"
        style={{
          background: 'var(--bg-card)',
          color: 'var(--text)',
        }}
      >
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        {title}
      </button>
      {open && (
        <div
          className="px-4 py-3 border-t"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-panel)' }}
        >
          {children}
        </div>
      )}
    </div>
  )
}
