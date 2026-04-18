/**
 * DAG 可视化：科技感、流光边、粒子流动效果（参考 example/dataevolver.html）
 * 接收 nodes + edges，渲染为 SVG：虚线边 + dataflow 动画 + 沿路径运动的粒子
 */

import { useMemo } from 'react'
import type { DagNode, DagEdge } from '../types'

interface DagCanvasProps {
  nodes: DagNode[]
  edges: DagEdge[]
  executionOrder?: string[]
  activeNodeId?: string
  className?: string
  width?: number
  height?: number
}

export function DagCanvas({
  nodes,
  edges,
  executionOrder = [],
  activeNodeId,
  className = '',
  width = 700,
  height = 320,
}: DagCanvasProps) {
  const nodePositions = useMemo(() => {
    const order = executionOrder.length ? executionOrder : nodes.map((n) => n.node_id)
    const pos: Record<string, { x: number; y: number }> = {}
    order.forEach((id, i) => {
      const t = order.length <= 1 ? 0.5 : i / (order.length - 1)
      pos[id] = { x: 80 + t * (width - 160), y: height / 2 }
    })
    return pos
  }, [nodes, executionOrder, width, height])

  const pathD = useMemo(() => {
    const out: Record<string, string> = {}
    edges.forEach((e) => {
      const a = nodePositions[e.from_node]
      const b = nodePositions[e.to_node]
      if (!a || !b) return
      const mx = (a.x + b.x) / 2
      const key = `${e.from_node}-${e.to_node}`
      out[key] = `M${a.x},${a.y} C${mx},${a.y} ${mx},${b.y} ${b.x},${b.y}`
    })
    return out
  }, [edges, nodePositions])

  if (nodes.length === 0) {
    return (
      <div
        className={`flex items-center justify-center text-[var(--text-muted)] text-sm ${className}`}
        style={{ width, height, background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: 16 }}
      >
        暂无 DAG 数据
      </div>
    )
  }

  return (
    <div
      className={className}
      style={{
        background: 'var(--bg-panel)',
        border: '1px solid var(--border)',
        borderRadius: 16,
        overflow: 'hidden',
      }}
    >
      <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center gap-2.5 font-semibold text-sm">
          <span
            className="w-2 h-2 rounded-sm bg-[var(--de-cyan)]"
            style={{ boxShadow: '0 0 6px var(--de-cyan-dim)' }}
          />
          Operator DAG — 实时拓扑
        </div>
        <div className="flex gap-1.5">
          {['+', '−', '⟲'].map((sym, i) => (
            <button
              key={i}
              type="button"
              className="w-7 h-7 rounded-md border flex items-center justify-center text-xs text-[var(--text-muted)] hover:border-[var(--de-cyan-dim)] hover:text-[var(--de-cyan)] transition-colors"
              style={{ borderColor: 'var(--border)' }}
            >
              {sym}
            </button>
          ))}
        </div>
      </div>
      <svg width="100%" height={height} className="block">
        <defs>
          <linearGradient id="dagEdgeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="var(--de-cyan)" stopOpacity="0.6" />
            <stop offset="100%" stopColor="var(--de-cyan)" stopOpacity="0.1" />
          </linearGradient>
          <filter id="dagGlow">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
          <linearGradient id="dagNodeGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--dag-node-bg-start)" />
            <stop offset="100%" stopColor="var(--dag-node-bg-end)" />
          </linearGradient>
          <linearGradient id="dagActiveGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--dag-node-active-start)" />
            <stop offset="100%" stopColor="var(--dag-node-active-end)" />
          </linearGradient>
        </defs>
        {/* 边：虚线 + 流光动画 */}
        {edges.map((e, i) => {
          const d = pathD[`${e.from_node}-${e.to_node}`]
          if (!d) return null
          return (
            <g key={`edge-${i}`}>
              <path
                d={d}
                fill="none"
                stroke="var(--dag-edge-soft)"
                strokeWidth="1.5"
                strokeDasharray="5 3"
                style={{
                  animation: 'dataflow 1s linear infinite',
                  animationDelay: `${i * 0.15}s`,
                }}
              />
              {/* 沿路径运动的粒子 */}
              <circle r="2.5" fill="var(--de-cyan)" opacity="0.8">
                <animateMotion
                  dur={`${2 + i * 0.3}s`}
                  repeatCount="indefinite"
                  path={d}
                />
              </circle>
            </g>
          )
        })}
        {/* 节点 */}
        {nodes.map((n) => {
          const pos = nodePositions[n.node_id]
          if (!pos) return null
          const isActive = activeNodeId === n.node_id
          const isFirst = n.node_name === 'read_data'
          const isLast = n.node_name === 'write_data'
          const fill = isFirst
            ? '#00b4d820'
            : isLast
              ? '#4ceb9a20'
              : isActive
                ? 'url(#dagActiveGrad)'
                : 'url(#dagNodeGrad)'
          const stroke = isFirst
            ? '#00b4d860'
            : isLast
              ? '#4ceb9a60'
              : isActive
                ? '#00e5c850'
                : 'var(--dag-default-stroke)'
          const textColor = isFirst ? '#00b4d8' : isLast ? '#4ceb9a' : isActive ? '#00e5c8' : 'var(--dag-default-text)'
          const rw = 56
          const rh = 24

          return (
            <g key={n.node_id}>
              {isActive && (
                <rect
                  x={pos.x - rw - 4}
                  y={pos.y - rh - 4}
                  width={(rw + 4) * 2}
                  height={(rh + 4) * 2}
                  rx="12"
                  fill="none"
                  stroke="var(--de-cyan-dim)"
                  strokeWidth="1"
                  filter="url(#dagGlow)"
                  className="dag-node-glow"
                />
              )}
              <rect
                x={pos.x - rw}
                y={pos.y - rh}
                width={rw * 2}
                height={rh * 2}
                rx="10"
                fill={fill}
                stroke={stroke}
                strokeWidth="1"
              />
              <text
                x={pos.x}
                y={pos.y + 4}
                textAnchor="middle"
                fontFamily="Outfit, sans-serif"
                fontSize="10"
                fontWeight="600"
                fill={textColor}
              >
                {n.node_name}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
