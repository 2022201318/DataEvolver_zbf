"""
DAG 图结构分析：边合法性、环检测、从入口可达性、execution_order 与边方向一致性、单源/单汇启发式检查。
用于开源版闭环中「静态图」与线性 final_pipeline 互补校验。
"""

from __future__ import annotations

from collections import deque
from typing import Any


def validate_dag_graph_topology(dag: Any) -> list[dict[str, Any]]:
    """
    对 `orchestration_results` 中的 `dag` 做图论校验。
    若 `dag` 无效或为空节点列表，返回单条说明性 issue（type=dag_graph）。
    """
    issues: list[dict[str, Any]] = []
    if not isinstance(dag, dict):
        return [{"type": "dag_graph", "description": "dag 不是对象"}]
    nodes = dag.get("nodes")
    edges = dag.get("edges")
    if not isinstance(nodes, list) or not nodes:
        return issues
    if not isinstance(edges, list):
        edges = []

    node_ids: list[str] = []
    seen: set[str] = set()
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            continue
        nid = n.get("node_id")
        if not nid or not isinstance(nid, str):
            issues.append(
                {
                    "type": "dag_graph_bad_node",
                    "index": i,
                    "description": f"nodes[{i}] 缺少有效 node_id",
                }
            )
            continue
        if nid in seen:
            issues.append(
                {
                    "type": "dag_graph_duplicate_id",
                    "description": f"重复的 node_id: {nid!r}",
                }
            )
        seen.add(nid)
        node_ids.append(nid)

    ids = set(node_ids)
    if not ids:
        return issues

    for ei, e in enumerate(edges):
        if not isinstance(e, dict):
            continue
        a = e.get("from_node")
        b = e.get("to_node")
        if a not in ids:
            issues.append(
                {
                    "type": "dag_graph_unknown_node",
                    "edge_index": ei,
                    "description": f"边 from_node={a!r} 不在 nodes 中",
                }
            )
        if b not in ids:
            issues.append(
                {
                    "type": "dag_graph_unknown_node",
                    "edge_index": ei,
                    "description": f"边 to_node={b!r} 不在 nodes 中",
                }
            )

    adj: dict[str, list[str]] = {i: [] for i in ids}
    indeg: dict[str, int] = {i: 0 for i in ids}
    outdeg: dict[str, int] = {i: 0 for i in ids}
    for e in edges:
        if not isinstance(e, dict):
            continue
        a, b = e.get("from_node"), e.get("to_node")
        if a in ids and b in ids:
            adj[a].append(b)
            indeg[b] += 1
            outdeg[a] += 1

    sources = [n for n in ids if indeg[n] == 0]
    sinks = [n for n in ids if outdeg[n] == 0]
    if len(sources) > 1:
        issues.append(
            {
                "type": "dag_graph_multi_source",
                "description": f"多个零入度节点（{len(sources)} 个），数据流入口应唯一: {sources[:6]}",
                "sources": sources,
            }
        )
    if len(sinks) > 1:
        issues.append(
            {
                "type": "dag_graph_multi_sink",
                "description": f"多个零出度节点（{len(sinks)} 个），数据流出口应唯一: {sinks[:6]}",
                "sinks": sinks,
            }
        )

    q: deque[str] = deque([n for n in ids if indeg[n] == 0])
    rem = dict(indeg)
    topo_count = 0
    while q:
        u = q.popleft()
        topo_count += 1
        for v in adj[u]:
            rem[v] -= 1
            if rem[v] == 0:
                q.append(v)
    if topo_count != len(ids):
        issues.append(
            {
                "type": "dag_cycle_or_disconnected",
                "description": (
                    "无法完成拓扑排序：可能存在有向环，或存在与入口不连通的节点分量"
                ),
            }
        )

    order = dag.get("execution_order")
    if isinstance(order, list) and len(order) == len(ids):
        pos = {nid: i for i, nid in enumerate(order) if isinstance(nid, str)}
        if len(pos) != len(order):
            issues.append(
                {
                    "type": "dag_graph_order",
                    "description": "execution_order 中存在非字符串或重复 id",
                }
            )
        else:
            for e in edges:
                if not isinstance(e, dict):
                    continue
                a, b = e.get("from_node"), e.get("to_node")
                if a not in pos or b not in pos:
                    continue
                if pos[a] > pos[b]:
                    issues.append(
                        {
                            "type": "dag_topo_order_conflict",
                            "description": (
                                f"边 {a!r} -> {b!r} 要求 a 先于 b，但 execution_order 中顺序相反"
                            ),
                        }
                    )
            entry = order[0]
            if entry in ids:
                reachable: set[str] = set()
                stack = [entry]
                while stack:
                    u = stack.pop()
                    if u in reachable:
                        continue
                    reachable.add(u)
                    stack.extend(adj[u])
                missing = ids - reachable
                if missing:
                    issues.append(
                        {
                            "type": "dag_disconnected",
                            "description": (
                                f"从 execution_order 首节点 {entry!r} 沿边不可达: "
                                f"{sorted(missing)[:12]}{'…' if len(missing) > 12 else ''}"
                            ),
                            "unreachable": sorted(missing),
                        }
                    )
    elif isinstance(order, list) and order:
        issues.append(
            {
                "type": "dag_graph_order",
                "description": (
                    f"execution_order 长度 ({len(order)}) 与节点数 ({len(ids)}) 不一致，跳过可达性/边序校验"
                ),
            }
        )

    return issues
