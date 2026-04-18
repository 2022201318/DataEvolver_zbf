import { useEffect, useRef } from 'react'
import Prism from 'prismjs'
import 'prismjs/components/prism-python'

interface CodeBlockProps {
  code: string
  language?: string
  className?: string
}

export function CodeBlock({ code, language = 'python', className }: CodeBlockProps) {
  const ref = useRef<HTMLPreElement>(null)

  useEffect(() => {
    if (ref.current) Prism.highlightElement(ref.current)
  }, [code, language])

  return (
    <pre className={className} ref={ref}>
      <code className={`language-${language}`}>{code}</code>
    </pre>
  )
}
