import type { Graph } from "./types";

export function clusteredGraph(
  graph: Graph,
  selected: string | null = null,
): Graph {
  if (graph.nodes.length <= 64) return graph;
  const pinned = new Set<string>(selected ? [selected] : []);
  for (const kind of ["finding", "decision", "claim"])
    for (const node of graph.nodes
      .filter((n) => n.type === kind)
      .slice(0, kind === "decision" ? 4 : 8))
      pinned.add(node.id);
  if (selected)
    for (const edge of graph.edges
      .filter((e) => e.source === selected || e.target === selected)
      .slice(0, 8)) {
      pinned.add(edge.source);
      pinned.add(edge.target);
    }
  const groups = new Map<string, Graph["nodes"]>();
  const remaining = graph.nodes.filter((n) => !pinned.has(n.id));
  const keys = remaining.map(
    (n) =>
      n.type + " / " + (n.path?.split("/").slice(0, -1).join("/") || "project"),
  );
  const broad = new Set(keys).size > 24;
  remaining.forEach((node, index) => {
    const key = broad ? node.type : keys[index];
    groups.set(key, [...(groups.get(key) || []), node]);
  });
  const mapping = new Map<string, string>();
  const nodes = graph.nodes.filter((n) => pinned.has(n.id));
  for (const node of nodes) mapping.set(node.id, node.id);
  for (const [key, members] of groups) {
    if (members.length === 1) {
      nodes.push(members[0]);
      mapping.set(members[0].id, members[0].id);
      continue;
    }
    const id = "cluster:" + encodeURIComponent(key);
    nodes.push({
      id,
      type: "cluster",
      label: `${key} · ${members.length}`,
      members: members.map((n) => n.id),
      count: members.length,
    });
    for (const member of members) mapping.set(member.id, id);
  }
  const merged = new Map<string, Graph["edges"][number]>();
  for (const edge of graph.edges) {
    const source = mapping.get(edge.source),
      target = mapping.get(edge.target);
    if (!source || !target || source === target) continue;
    const key = JSON.stringify([source, target, edge.type]);
    const record = merged.get(key);
    if (record) record.count = (record.count || 1) + 1;
    else merged.set(key, { source, target, type: edge.type, count: 1 });
  }
  return { nodes, edges: [...merged.values()] };
}

export function visibleGraph(
  graph: Graph,
  selected: string | null = null,
  limit = 50,
): Graph {
  const focus = new Set<string>(selected ? [selected] : []);
  for (const edge of graph.edges)
    if (edge.source === selected || edge.target === selected) {
      focus.add(edge.source);
      focus.add(edge.target);
    }
  const priority: Record<string, number> = {
    finding: 0,
    decision: 1,
    claim: 2,
    execution: 3,
    paper: 4,
    results: 5,
    code: 6,
    configuration: 7,
    data: 8,
    documentation: 9,
  };
  const ordered = [...graph.nodes].sort(
    (a, b) =>
      Number(focus.has(b.id)) -
      Number(focus.has(a.id)) +
      (focus.has(a.id) === focus.has(b.id)
        ? (priority[a.type] ?? 10) - (priority[b.type] ?? 10)
        : 0),
  );
  const byId = new Map(ordered.map((n) => [n.id, n]));
  const chosen = new Map<string, Graph["nodes"][number]>();
  const add = (id: string) => {
    const node = byId.get(id);
    if (node && chosen.size < limit) chosen.set(id, node);
  };
  for (const node of ordered) if (focus.has(node.id)) add(node.id);
  for (const node of ordered.filter((n) =>
    ["finding", "decision", "claim", "execution"].includes(n.type),
  )) {
    add(node.id);
    for (const edge of graph.edges) {
      if (edge.target === node.id) add(edge.source);
      else if (edge.source === node.id) add(edge.target);
    }
    if (chosen.size >= limit) break;
  }
  for (const node of ordered) add(node.id);
  const nodes = [...chosen.values()];
  const ids = new Set(nodes.map((n) => n.id));
  return {
    nodes,
    edges: graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target)),
  };
}
