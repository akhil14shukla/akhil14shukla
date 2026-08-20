import { LayoutResult, Point } from "./layout";

/**
 * The single shape every view renders to.
 *
 * Views differ in how they compute geometry, not in how they are drawn — the
 * webview understands these primitives and nothing else, so adding a diagram is
 * a layout function plus a test rather than a new renderer.
 */
export type SceneKind = "graph" | "sequence" | "classes" | "flow" | "modules";

/** Styling role, kept separate from geometry so the CSS owns appearance. */
export type NodeRole =
  | "method"
  | "entry"
  | "external"
  | "class"
  | "participant"
  | "param"
  | "local"
  | "sink"
  | "module"
  | "activation";

export interface SceneNode {
  id: string;
  label: string;
  /** Second line inside the box. */
  sub?: string;
  x: number;
  y: number;
  w: number;
  h: number;
  role?: NodeRole;
  /** Colour-grouping key (class name, module kind). */
  group?: string;
  /** Extra lines rendered inside the box — class members, flow details. */
  rows?: string[];
  /** 0 none, 1 warning, 2 error. */
  severity?: number;
  complexity?: number;
  effects?: string[];
  lines?: number;
  /** Full text for the native tooltip. */
  tip?: string;
  /** Line to reveal in the editor when clicked; omitted for non-navigable nodes. */
  clickLine?: number;
  /** Suppress the arrowhead-free plain box treatment. */
  external?: boolean;
  entry?: boolean;
}

export type EdgeStyle = "solid" | "dashed" | "inherit" | "flow";

export interface SceneEdge {
  from?: string;
  to?: string;
  points: Point[];
  label?: string;
  style?: EdgeStyle;
  /** Sequence message number. */
  order?: number;
  /** Call-site count; drives stroke weight. */
  count?: number;
  /** Drawn reversed to break a cycle; direction reported is still true. */
  reversed?: boolean;
  /** Renders as a self-loop badge rather than a line. */
  self?: boolean;
}

/** Vertical lifeline for the sequence view. */
export interface Lane {
  id: string;
  x: number;
  top: number;
  bottom: number;
}

export interface Divider {
  y: number;
  label: string;
}

/** One legend entry. `swatch` is a CSS class on `media/glance.css`. */
export interface LegendItem {
  swatch: string;
  label: string;
}

export interface Scene {
  kind: SceneKind;
  nodes: SceneNode[];
  edges: SceneEdge[];
  lanes?: Lane[];
  dividers?: Divider[];
  width: number;
  height: number;
  /** One line under the toolbar stating what the view does and does not show. */
  caption?: string;
  /** Shown as a centred message when there is nothing to draw. */
  empty?: string;
  /** Keyed to this view. A legend describing a different diagram is worse than
   * none, so every view supplies its own. */
  legend?: LegendItem[];
  /** Right-aligned note on how to read the view. */
  hint?: string;
  /**
   * Fixed colour per group, as a VS Code theme variable name.
   *
   * Grouping is arbitrary in some views (which class a method sits in) and
   * meaningful in others (whether a module is local or third-party). Where it
   * is meaningful the colour has to be pinned, or the rails stop agreeing with
   * the legend.
   */
  groupColors?: Record<string, string>;
}

export const GRAPH_LEGEND: LegendItem[] = [
  { swatch: "sw-node", label: "method" },
  { swatch: "sw-entry", label: "entry point" },
  { swatch: "sw-ext", label: "external" },
  { swatch: "sw-warn", label: "warning" },
  { swatch: "sw-err", label: "error" },
  { swatch: "sw-line", label: "calls" },
  { swatch: "sw-dash", label: "cross-file" },
];

/** Wrap the call-graph layout in the common Scene shape. */
export function graphScene(
  result: LayoutResult,
  clickLines: Record<string, number>
): Scene {
  return {
    kind: "graph",
    legend: GRAPH_LEGEND,
    hint: "width = method size · subtitle = side effects · click to open",
    width: result.width,
    height: result.height,
    dividers:
      result.detachedFrom !== undefined
        ? [{ y: result.detachedFrom, label: "no resolved calls" }]
        : undefined,
    nodes: result.nodes.map((n) => {
      const bits: string[] = [];
      if (n.effects && n.effects.length) {
        bits.push(n.effects.join(" "));
      }
      if (n.complexity && n.complexity >= 10) {
        bits.push(`C${n.complexity}`);
      }
      if (n.lines) {
        bits.push(`${n.lines}L`);
      }
      if (n.group) {
        bits.push(n.group);
      }
      // Ordered by what earns the space; trimmed from the end until it fits.
      // The class name goes first because the rail colour already carries it,
      // while what a body touches is not recoverable from anything else.
      const room = Math.floor((n.w - 24) / 5.4);
      while (bits.length > 1 && bits.join(" · ").length > room) {
        bits.pop();
      }

      const tip = [n.group ? `${n.group}.${n.label}` : n.label];
      if (n.lines) tip.push(`${n.lines} lines`);
      if (n.complexity) tip.push(`complexity ${n.complexity}`);
      if (n.shape) tip.push(n.shape);
      if (n.entry) tip.push("entry point");
      if (n.external) tip.push("defined outside this file");

      return {
        id: n.id,
        label: n.label,
        sub: bits.join(" · "),
        x: n.x,
        y: n.y,
        w: n.w,
        h: n.h,
        role: n.external ? "external" : n.entry ? "entry" : "method",
        group: n.group,
        severity: n.severity,
        complexity: n.complexity,
        effects: n.effects,
        lines: n.lines,
        entry: n.entry,
        external: n.external,
        tip: tip.join(" — "),
        clickLine: n.external ? undefined : clickLines[n.id],
      } as SceneNode;
    }),
    edges: result.edges.map((e) => ({
      from: e.from,
      to: e.to,
      points: e.points,
      style: e.cross ? "dashed" : "solid",
      count: e.count,
      reversed: e.reversed,
      self: e.points.length === 0,
    })),
  };
}
