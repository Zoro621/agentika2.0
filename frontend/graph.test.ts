import { expect, it } from "vitest";
import { visibleGraph, clusteredGraph } from "./graph";
it("keeps the selected finding and real linked source visible in a large project", () => {
  const graph = {
    nodes: [
      ...Array.from({ length: 100 }, (_, i) => ({
        id: `file-${i}`,
        type: "documentation",
        label: `File ${i}`,
      })),
      { id: "finding", type: "finding", label: "Concern" },
    ],
    edges: [{ source: "file-99", target: "finding", type: "conflicts_with" }],
  };
  const projected = visibleGraph(graph, "finding", 20);
  expect(projected.nodes.some((n) => n.id === "finding")).toBe(true);
  expect(projected.nodes.some((n) => n.id === "file-99")).toBe(true);
  expect(projected.nodes).toHaveLength(20);
  expect(projected.edges).toEqual(graph.edges);
  expect(graph.nodes).toHaveLength(101);
});
it("retains actual source connections when many claims exceed the display budget", () => {
  const graph = {
    nodes: [
      { id: "paper", type: "paper", label: "Paper" },
      ...Array.from({ length: 100 }, (_, i) => ({
        id: `claim-${i}`,
        type: "claim",
        label: `Claim ${i}`,
      })),
    ],
    edges: Array.from({ length: 100 }, (_, i) => ({
      source: "paper",
      target: `claim-${i}`,
      type: "derived_from",
    })),
  };
  const visible = visibleGraph(graph, null, 20);
  expect(visible.nodes.some((n) => n.id === "paper")).toBe(true);
  expect(visible.edges.length).toBeGreaterThan(0);
});

it("clusters every stored node exactly once and only aggregates real edges", () => {
  const graph = {
    nodes: Array.from({ length: 2000 }, (_, i) => ({
      id: `n${i}`,
      type: i === 1999 ? "finding" : "code",
      label: `Node ${i}`,
      path: `src/module${i % 40}/file${i}.py`,
    })),
    edges: Array.from({ length: 1999 }, (_, i) => ({
      source: `n${i}`,
      target: "n1999",
      type: "supports",
    })),
  };
  const view = clusteredGraph(graph, "n1999");
  expect(view.nodes.length).toBeLessThanOrEqual(64);
  const members = view.nodes.flatMap((n) => n.members || [n.id]);
  expect(new Set(members).size).toBe(2000);
  expect(members.length).toBe(2000);
  expect(view.edges.reduce((sum, e) => sum + (e.count || 1), 0)).toBe(1999);
  expect(view.nodes.some((n) => n.id === "n1999")).toBe(true);
});
