/**
 * 合并画布行：已完成轮次优先保留更完整的快照数据，避免刷新后被空壳覆盖。
 */
import type { CanvasEvolutionRow } from './canvasRowTypes'

function instCardsRichness(cards: CanvasEvolutionRow['instantiationCards']): number {
  if (!cards.length) return 0
  const withCode = cards.filter((c) => c.code.trim().length > 0).length
  return withCode * 1000 + cards.length
}

function dagTabsRichness(tabs: CanvasEvolutionRow['dagTabs']): number {
  if (!tabs.length) return 0
  const passed = tabs.filter((t) => t.status === 'passed').length
  const withDag = tabs.filter((t) => t.dag && (t.dag.nodes?.length ?? 0) > 0).length
  return withDag * 500 + passed * 100 + tabs.length
}

function pickRicherRow(prev: CanvasEvolutionRow, inc: CanvasEvolutionRow): CanvasEvolutionRow {
  const inst =
    instCardsRichness(inc.instantiationCards) >= instCardsRichness(prev.instantiationCards)
      ? inc.instantiationCards
      : prev.instantiationCards
  const dagTabs =
    dagTabsRichness(inc.dagTabs) >= dagTabsRichness(prev.dagTabs) ? inc.dagTabs : prev.dagTabs
  const activeDagTabId =
    dagTabs.find((t) => t.id === inc.activeDagTabId)?.id ??
    dagTabs.find((t) => t.id === prev.activeDagTabId)?.id ??
    dagTabs.find((t) => t.status === 'passed')?.id ??
    dagTabs[dagTabs.length - 1]?.id
  const rowUi = inc.rowUi?.understanding ? inc.rowUi : prev.rowUi ?? inc.rowUi
  return {
    ...inc,
    dagTabs,
    activeDagTabId,
    instantiationCards: inst,
    rowUi,
    sampleScore: inc.sampleScore ?? prev.sampleScore,
    experience: inc.experience?.trim() ? inc.experience : prev.experience,
    completed: true,
    needNext: inc.needNext ?? prev.needNext,
  }
}

/** 将服务端重建结果与本地已有行合并；currentRoundId 之前的轮次视为已冻结。 */
export function mergeEvolutionRows(
  prev: CanvasEvolutionRow[],
  incoming: CanvasEvolutionRow[],
  currentRoundId: number
): CanvasEvolutionRow[] {
  const curRound = Math.max(1, Math.round(currentRoundId))
  const byId = new Map<number, CanvasEvolutionRow>()
  for (const r of incoming) {
    byId.set(r.id, r)
  }
  for (const p of prev) {
    if (p.id >= curRound) continue
    const inc = byId.get(p.id)
    if (!inc) {
      byId.set(p.id, { ...p, completed: true })
      continue
    }
    byId.set(p.id, pickRicherRow(p, { ...inc, completed: true }))
  }
  return [...byId.values()].sort((a, b) => a.id - b.id)
}
