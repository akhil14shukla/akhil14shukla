import { LegendItem, Scene, SceneEdge, SceneNode } from "./scene";

export interface ClassMember {
  name: string;
  /** Rendered marker: `+` public, `-` private, `#` protected. */
  visibility: "+" | "-" | "#";
  kind: "method" | "attribute";
  clickLine?: number;
  /** Method touches io/net/db etc. */
  effects?: string[];
}

export interface ClassBox {
  name: string;
  clickLine?: number;
  members: ClassMember[];
  /** Defined outside the current file. */
  external?: boolean;
}

export interface InheritEdge {
  /** Subtype name. */
  from: string;
  /** Supertype name. */
  to: string;
}

const CLASS_LEGEND: LegendItem[] = [
  { swatch: "sw-node", label: "class in this file" },
  { swatch: "sw-ext", label: "external supertype" },
  { swatch: "sw-line", label: "inherits ▷" },
];

const HEAD_H = 26;
const ROW_H = 16;
const ROW_PAD = 12;
const LAYER_GAP = 64;
const BOX_GAP = 30;
const PAD = 28;
/** Beyond this a box becomes a wall of text; the rest is summarised. */
const MAX_ROWS = 12;

function boxWidth(box: ClassBox): number {
  const longest = Math.max(
    box.name.length + 2,
    ...box.members.map((m) => m.name.length + 4),
    12
  );
  return Math.max(150, Math.min(280, longest * 7.2 + 28));
}

function boxHeight(rowCount: number): number {
  return HEAD_H + ROW_PAD + rowCount * ROW_H + 10;
}

/** Python convention: `__x` private, `_x` protected, otherwise public. */
export function visibilityOf(name: string): "+" | "-" | "#" {
  if (name.startsWith("__") && !name.endsWith("__")) {
    return "-";
  }
  if (name.startsWith("_") && !name.startsWith("__")) {
    return "#";
  }
  return "+";
}

/**
 * Inheritance depth: a class sits one level below its deepest supertype, so
 * bases appear above the types that extend them.
 */
function depthOf(
  name: string,
  parents: Map<string, string[]>,
  seen = new Set<string>()
): number {
  if (seen.has(name)) {
    return 0; // cyclic hierarchies cannot happen in valid code, but never hang
  }
  seen.add(name);
  const ps = parents.get(name) || [];
  let best = 0;
  for (const p of ps) {
    best = Math.max(best, depthOf(p, parents, seen) + 1);
  }
  seen.delete(name);
  return best;
}

/**
 * Class boxes with their members, laid out by inheritance depth.
 *
 * Attributes come before methods inside a box because "what does this hold"
 * reads before "what does this do".
 */
export function classScene(
  boxes: ClassBox[],
  inherits: InheritEdge[],
  viewWidth = 900
): Scene {
  if (!boxes.length) {
    return {
      kind: "classes",
      nodes: [],
      edges: [],
      width: viewWidth,
      height: 200,
      legend: CLASS_LEGEND,
      empty:
        "No classes in this file.\nThe class diagram shows types, their members, and what they inherit from.",
    };
  }

  const byName = new Map(boxes.map((b) => [b.name, b]));
  const parents = new Map<string, string[]>();
  for (const e of inherits) {
    if (!parents.has(e.from)) {
      parents.set(e.from, []);
    }
    parents.get(e.from)!.push(e.to);
  }

  // Group by depth, stable-sorted so the picture never reshuffles.
  const layers = new Map<number, ClassBox[]>();
  for (const b of boxes) {
    const d = depthOf(b.name, parents);
    if (!layers.has(d)) {
      layers.set(d, []);
    }
    layers.get(d)!.push(b);
  }

  // Order each layer under its supertypes rather than alphabetically, so
  // inheritance edges run straight down instead of crossing each other.
  const placed = new Map<string, number>();
  const orderedDepths = [...layers.keys()].sort((a, b) => a - b);
  for (const d of orderedDepths) {
    const list = layers.get(d)!;
    list.sort((a, b) => {
      const key = (box: ClassBox): number => {
        const ps = (parents.get(box.name) || [])
          .map((p) => placed.get(p))
          .filter((v): v is number => v !== undefined);
        return ps.length ? ps.reduce((x, y) => x + y, 0) / ps.length : Infinity;
      };
      const ka = key(a);
      const kb = key(b);
      return ka === kb ? a.name.localeCompare(b.name) : ka - kb;
    });
    list.forEach((b, i) => placed.set(b.name, i));
  }

  const nodes: SceneNode[] = [];
  const geom = new Map<string, { x: number; y: number; w: number; h: number }>();
  const depths = [...layers.keys()].sort((a, b) => a - b);

  let y = PAD;
  let widest = viewWidth;

  for (const d of depths) {
    const list = layers.get(d)!;
    const widths = list.map(boxWidth);
    const total =
      widths.reduce((a, b) => a + b, 0) + BOX_GAP * (list.length - 1);
    let x = Math.max(PAD, (viewWidth - total) / 2);
    let tallest = 0;

    list.forEach((b, i) => {
      const attrs = b.members.filter((m) => m.kind === "attribute");
      const methods = b.members.filter((m) => m.kind === "method");
      const ordered = [...attrs, ...methods];

      const shown = ordered.slice(0, MAX_ROWS);
      const rows = shown.map(
        (m) =>
          `${m.visibility} ${m.name}${m.kind === "method" ? "()" : ""}` +
          (m.effects && m.effects.length ? `  ${m.effects.join(" ")}` : "")
      );
      if (ordered.length > MAX_ROWS) {
        rows.push(`… ${ordered.length - MAX_ROWS} more`);
      }

      const w = widths[i];
      const h = boxHeight(rows.length);
      tallest = Math.max(tallest, h);

      nodes.push({
        id: b.name,
        label: b.name,
        x,
        y,
        w,
        h,
        rows,
        role: "class",
        group: b.name,
        external: b.external,
        clickLine: b.clickLine,
        tip:
          `${b.name} — ${attrs.length} attribute${attrs.length === 1 ? "" : "s"}, ` +
          `${methods.length} method${methods.length === 1 ? "" : "s"}` +
          (b.external ? " (defined outside this file)" : ""),
      });
      geom.set(b.name, { x, y, w, h });
      x += w + BOX_GAP;
      widest = Math.max(widest, x - BOX_GAP + PAD);
    });

    y += tallest + LAYER_GAP;
  }

  // Edges run from the subtype's top edge to the supertype's bottom edge.
  const edges: SceneEdge[] = [];
  for (const e of inherits) {
    const child = geom.get(e.from);
    const parent = geom.get(e.to);
    if (!child || !parent) {
      continue;
    }
    edges.push({
      from: e.from,
      to: e.to,
      points: [
        { x: child.x + child.w / 2, y: child.y },
        { x: parent.x + parent.w / 2, y: parent.y + parent.h },
      ],
      style: byName.get(e.to)?.external ? "dashed" : "inherit",
      label: undefined,
    });
  }

  return {
    kind: "classes",
    nodes,
    edges,
    width: widest,
    height: y - LAYER_GAP + PAD,
    legend: CLASS_LEGEND,
    caption:
      "Types in this file with their members. Supertypes sit above; dashed boxes are defined elsewhere.",
    hint: "+ public · # protected · - private · click to open",
  };
}
