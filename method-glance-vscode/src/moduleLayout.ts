import { ImportedModule, ModuleKind } from "./modules";
import { LegendItem, Scene, SceneEdge, SceneNode } from "./scene";

const MODULE_LEGEND: LegendItem[] = [
  { swatch: "sw-entry", label: "this file" },
  { swatch: "sw-local", label: "local" },
  { swatch: "sw-third", label: "third-party" },
  { swatch: "sw-std", label: "stdlib" },
  { swatch: "sw-dash", label: "imported, no resolved call" },
];

/** Pinned so the rails always agree with the legend swatches. */
const KIND_COLORS: Record<ModuleKind, string> = {
  local: "--vscode-charts-blue",
  "third-party": "--vscode-charts-orange",
  stdlib: "--vscode-charts-green",
};

const NODE_H = 40;
const V_GAP = 14;
const COL_GAP = 96;
const PAD = 28;
/** Groups are ordered by how much of the file's behaviour they own. */
const KIND_ORDER: ModuleKind[] = ["local", "third-party", "stdlib"];

function width(label: string): number {
  return Math.max(130, Math.min(250, label.length * 7.4 + 36));
}

/**
 * What this file reaches outside itself: the modules it imports, weighted by
 * how many resolved calls actually land in each.
 *
 * Imports with no resolved call are kept and drawn dashed rather than dropped —
 * an unused import is one of the more useful things the view can tell you.
 */
export function moduleScene(
  file: string,
  modules: ImportedModule[],
  viewWidth = 900
): Scene {
  const caption =
    "Modules this file imports, weighted by resolved calls. Dashed means imported but never called here — " +
    "which may mean it is unused, or used in a way the language server could not resolve.";

  if (!modules.length) {
    return {
      kind: "modules",
      nodes: [],
      edges: [],
      width: viewWidth,
      height: 200,
      legend: MODULE_LEGEND,
      groupColors: KIND_COLORS,
      caption,
      empty: `${file} imports nothing.\nThe module map shows what a file reaches outside itself.`,
    };
  }

  // Sort within a kind by call weight, then name, so the heaviest dependency
  // reads first and the order never wobbles between openings.
  const sorted = [...modules].sort((a, b) => {
    const ka = KIND_ORDER.indexOf(a.kind);
    const kb = KIND_ORDER.indexOf(b.kind);
    if (ka !== kb) return ka - kb;
    if (b.calls !== a.calls) return b.calls - a.calls;
    return a.name.localeCompare(b.name);
  });

  const nodes: SceneNode[] = [];
  const edges: SceneEdge[] = [];

  const rightW = Math.max(...sorted.map((m) => width(m.name)));
  const totalH = sorted.length * (NODE_H + V_GAP) - V_GAP;

  const leftW = width(file);
  const leftX = PAD;
  const rightX = leftX + leftW + COL_GAP;
  const centreY = PAD + totalH / 2;

  nodes.push({
    id: "__self__",
    label: file,
    sub: `${modules.length} import${modules.length === 1 ? "" : "s"}`,
    x: leftX,
    y: centreY - NODE_H / 2,
    w: leftW,
    h: NODE_H,
    role: "module",
    entry: true,
    tip: `${file} — the file being mapped`,
  });

  let y = PAD;
  for (const m of sorted) {
    nodes.push({
      id: m.name,
      label: m.name,
      sub:
        (m.calls ? `${m.calls} call${m.calls === 1 ? "" : "s"}` : "no calls") +
        (m.members.length ? ` · ${m.members.slice(0, 3).join(", ")}` : ""),
      x: rightX,
      y,
      w: rightW,
      h: NODE_H,
      role: "module",
      group: m.kind,
      clickLine: m.line,
      tip:
        `${m.name} — ${m.kind}, ${m.calls} resolved call${m.calls === 1 ? "" : "s"}` +
        (m.members.length ? `\nimports: ${m.members.join(", ")}` : ""),
    });

    edges.push({
      from: "__self__",
      to: m.name,
      points: [
        { x: leftX + leftW, y: centreY },
        { x: rightX, y: y + NODE_H / 2 },
      ],
      // Weight is call count, so the heavy dependencies are visible as such.
      count: m.calls,
      style: m.calls ? "solid" : "dashed",
    });

    y += NODE_H + V_GAP;
  }

  return {
    kind: "modules",
    nodes,
    edges,
    width: Math.max(viewWidth, rightX + rightW + PAD),
    height: Math.max(PAD * 2 + totalH, centreY + NODE_H),
    legend: MODULE_LEGEND,
    groupColors: KIND_COLORS,
    caption,
    hint: "line weight = resolved calls · click to jump to the import",
  };
}
