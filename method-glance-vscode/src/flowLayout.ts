import { FlowResult } from "./dataflow";
import { LegendItem, Scene, SceneEdge, SceneNode } from "./scene";

const FLOW_LEGEND: LegendItem[] = [
  { swatch: "sw-param", label: "parameter" },
  { swatch: "sw-node", label: "local" },
  { swatch: "sw-sink", label: "where it ends up" },
];

const NODE_H = 34;
const V_GAP = 18;
const COL_GAP = 76;
const PAD = 28;

function width(label: string): number {
  return Math.max(120, Math.min(230, label.length * 7.4 + 34));
}

/**
 * Three columns — parameters, locals they flow through, and the places the
 * value ends up. Left to right is the direction the value travels.
 */
export function flowScene(
  methodLabel: string,
  flow: FlowResult,
  viewWidth = 900
): Scene {
  const caption =
    `Where ${methodLabel}'s parameters end up. Heuristic: values are followed by name ` +
    `through assignments — it cannot see a value stored in a container, or reassigned on only one branch.`;

  if (!flow.params.length) {
    return {
      kind: "flow",
      nodes: [],
      edges: [],
      width: viewWidth,
      height: 200,
      legend: FLOW_LEGEND,
      caption,
      empty: `${methodLabel} takes no parameters.\nPut the cursor in a method that takes arguments.`,
    };
  }
  if (!flow.edges.length) {
    return {
      kind: "flow",
      nodes: [],
      edges: [],
      width: viewWidth,
      height: 200,
      legend: FLOW_LEGEND,
      caption,
      empty: `No use of ${methodLabel}'s parameters was traced.\nThey may be unused, or used in a way this heuristic cannot follow.`,
    };
  }

  const columns: { id: string; label: string; sub?: string; role: SceneNode["role"] }[][] = [
    flow.params.map((p) => ({ id: p, label: p, role: "param" as const })),
    flow.steps.map((s) => ({
      id: s.name,
      label: s.name,
      sub: `from ${s.from.join(", ")}`,
      role: "local" as const,
    })),
    flow.sinks.map((s) => ({
      id: s.id,
      label: s.label,
      sub: s.kind,
      role: "sink" as const,
    })),
  ];

  const nodes: SceneNode[] = [];
  const geom = new Map<string, { x: number; y: number; w: number; h: number }>();
  const colWidths = columns.map((col) =>
    col.length ? Math.max(...col.map((c) => width(c.label))) : 0
  );

  // Skip an empty middle column rather than leaving a gap where locals would be.
  const present = columns
    .map((col, i) => ({ col, i }))
    .filter((c) => c.col.length);

  let x = PAD;
  const tallest = Math.max(...present.map((p) => p.col.length));
  const columnHeight = tallest * (NODE_H + V_GAP) - V_GAP;

  for (const { col, i } of present) {
    const w = colWidths[i];
    const colH = col.length * (NODE_H + V_GAP) - V_GAP;
    let y = PAD + (columnHeight - colH) / 2;
    for (const c of col) {
      nodes.push({
        id: c.id,
        label: c.label,
        sub: c.sub,
        x,
        y,
        w,
        h: NODE_H,
        role: c.role,
        tip: c.sub ? `${c.label} — ${c.sub}` : c.label,
      });
      geom.set(c.id, { x, y, w, h: NODE_H });
      y += NODE_H + V_GAP;
    }
    x += w + COL_GAP;
  }

  const edges: SceneEdge[] = [];
  for (const e of flow.edges) {
    const a = geom.get(e.from);
    const b = geom.get(e.to);
    if (!a || !b) {
      continue;
    }
    edges.push({
      from: e.from,
      to: e.to,
      points: [
        { x: a.x + a.w, y: a.y + a.h / 2 },
        { x: b.x, y: b.y + b.h / 2 },
      ],
      style: "flow",
    });
  }

  return {
    kind: "flow",
    nodes,
    edges,
    width: Math.max(viewWidth, x - COL_GAP + PAD),
    height: PAD * 2 + columnHeight,
    legend: FLOW_LEGEND,
    caption,
    hint: "left to right is the direction the value travels",
  };
}
