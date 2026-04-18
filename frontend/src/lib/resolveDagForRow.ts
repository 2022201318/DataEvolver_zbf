import type { DagResult } from '../types'

/** 由算子名列表生成线性 DAG（仅有节点列表时的回退） */
export function buildLinearDagFromOperatorNames(names: string[]): DagResult {
  if (names.length === 0) {
    return { nodes: [], edges: [], execution_order: [], total_nodes: 0, total_edges: 0 }
  }
  const nodes = names.map((name, i) => ({
    node_id: `oc_${i + 1}`,
    node_name: name,
    description: undefined as string | undefined,
    input_keys: ['records'],
    output_keys: ['records'],
  }))
  const edges = []
  for (let i = 0; i < nodes.length - 1; i++) {
    edges.push({
      from_node: nodes[i].node_id,
      to_node: nodes[i + 1].node_id,
      data_flow: { from_outputs: ['records'], to_inputs: ['records'] },
    })
  }
  return {
    nodes,
    edges,
    execution_order: nodes.map((n) => n.node_id),
    total_nodes: nodes.length,
    total_edges: edges.length,
  }
}

export type DagTabLike = {
  id: number
  nodes?: string[]
  dag?: DagResult
}

export type EvolutionRowLike = {
  dagTabs: DagTabLike[]
  activeDagTabId?: number
}

/** 当前选中编排 tab 对应的 DAG：优先 tab.dag，其次由 tab.nodes 线性展开，否则用管线级 fallback */
export function resolveDagForRow(row: EvolutionRowLike, fallback: DagResult): DagResult {
  const tab =
    row.dagTabs.find((t) => t.id === row.activeDagTabId) ?? row.dagTabs[row.dagTabs.length - 1]
  if (!tab) return fallback
  if (tab.dag) return tab.dag
  if (tab.nodes?.length) return buildLinearDagFromOperatorNames(tab.nodes)
  return fallback
}
