/** 突出 多模态数据准备 特点的 Hero 区：双轨自进化、原始→智能进化→高质量输出 */

export function HeroBanner() {
  return (
    <div
      className="rounded-2xl border p-7 mb-6 overflow-hidden relative animate-fade-slide"
      style={{
        background: 'var(--bg-panel)',
        borderColor: 'var(--border)',
      }}
    >
      <div
        className="absolute top-0 left-0 right-0 h-0.5"
        style={{
          background: 'linear-gradient(90deg, transparent, #00e5c8, #ff8c42, transparent)',
        }}
      />
      <p
        className="font-mono text-[0.65rem] tracking-widest uppercase mb-3"
        style={{ color: 'var(--de-cyan)' }}
      >
        Dual-Layer Self-Evolution Engine
      </p>
      <h1 className="text-2xl font-extrabold tracking-tight leading-tight mb-2">
        原始数据 →{' '}
        <span
          style={{
            background: 'linear-gradient(135deg, #00e5c8, #ff8c42)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}
        >
          智能进化
        </span>
        {' '}→ 高质量输出
      </h1>
      <p className="text-sm text-[var(--text-dim)] leading-relaxed max-w-2xl">
        输入原始数据与少量高质量 Seed 数据，通过算子自进化构建逻辑 DAG，实例化为可执行代码，
        再经 Pipeline 自进化迭代优化，最终使增强数据达到 Seed 品质。
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-5">
        <div
          className="rounded-xl border p-5 transition-all hover:border-[var(--border-glow)] hover:-translate-y-0.5 hover:shadow-lg"
          style={{
            background: 'var(--bg-card)',
            borderColor: 'var(--border)',
          }}
        >
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center text-lg mb-3"
            style={{
              background: 'linear-gradient(135deg, rgba(0,229,200,0.2), rgba(0,180,216,0.1))',
              color: 'var(--de-cyan)',
            }}
          >
            ⬡
          </div>
          <p className="font-mono text-[0.6rem] text-[var(--text-muted)] tracking-wider uppercase mb-1">
            Layer 1
          </p>
          <p className="font-semibold text-[var(--text)] mb-1">算子自进化</p>
          <p className="text-xs text-[var(--text-dim)] leading-relaxed">
            自动发现、组合逻辑算子，构建 DAG 拓扑，每个节点实例化为可执行代码
          </p>
        </div>
        <div
          className="rounded-xl border p-5 transition-all hover:border-[var(--border-glow)] hover:-translate-y-0.5 hover:shadow-lg"
          style={{
            background: 'var(--bg-card)',
            borderColor: 'var(--border)',
          }}
        >
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center text-lg mb-3"
            style={{
              background: 'linear-gradient(135deg, rgba(255,140,66,0.2), rgba(224,64,251,0.1))',
              color: 'var(--de-orange)',
            }}
          >
            ⟳
          </div>
          <p className="font-mono text-[0.6rem] text-[var(--text-muted)] tracking-wider uppercase mb-1">
            Layer 2
          </p>
          <p className="font-semibold text-[var(--text)] mb-1">Pipeline 自进化</p>
          <p className="text-xs text-[var(--text-dim)] leading-relaxed">
            执行数据准备 Pipeline，与 Seed 比对质量，总结经验并迭代优化
          </p>
        </div>
      </div>
    </div>
  )
}
