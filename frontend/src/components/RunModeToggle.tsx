import { useAppStore } from '../stores/appStore'

/**
 * 运行模式切换：自动 / 手动
 * - 自动：一键执行完整流程（后端对接后由 runMode 控制）
 * - 手动：按阶段逐步执行，每一步由用户确认
 * 放在流程顶部，强调是「Pipeline 控制方式」而不是全站设置。
 */
export function RunModeToggle() {
  const runMode = useAppStore((s) => s.runMode)
  const setRunMode = useAppStore((s) => s.setRunMode)

  return (
    <div className="flex items-center justify-between mb-4">
      <div>
        <p className="section-label mb-1">运行模式</p>
        <p className="text-sm text-[var(--text-dim)]">
          自动：一键完成四个阶段；手动：每一阶段由你确认后再执行，便于 Debug 和展示。
        </p>
      </div>
      <div className="flex items-center gap-1 rounded-lg p-1" style={{ background: 'var(--bg-card)' }}>
        <button
          type="button"
          onClick={() => setRunMode('manual')}
          className={
            runMode === 'manual'
              ? 'px-3 py-1.5 rounded-md text-sm font-semibold text-[var(--de-cyan)]'
              : 'px-3 py-1.5 rounded-md text-sm text-[var(--text-dim)] hover:text-[var(--text)]'
          }
        >
          手动
        </button>
        <button
          type="button"
          onClick={() => setRunMode('auto')}
          className={
            runMode === 'auto'
              ? 'px-3 py-1.5 rounded-md text-sm font-semibold text-[var(--de-cyan)]'
              : 'px-3 py-1.5 rounded-md text-sm text-[var(--text-dim)] hover:text-[var(--text)]'
          }
        >
          自动
        </button>
      </div>
    </div>
  )
}

