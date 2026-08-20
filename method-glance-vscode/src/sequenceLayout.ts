import { LegendItem, Scene, SceneEdge, SceneNode } from "./scene";

const SEQ_LEGEND: LegendItem[] = [
  { swatch: "sw-entry", label: "trace root" },
  { swatch: "sw-line", label: "always runs" },
  { swatch: "sw-dash", label: "? may not run · ✻ may repeat" },
  { swatch: "sw-self", label: "↻ recursion" },
];

/** One call site, already resolved to a callee. */
export interface SeqCall {
  from: string;
  to: string;
  /** Line the call appears on, in the caller. */
  line: number;
  /** Inside an `if`/`try` — may not run. */
  conditional?: boolean;
  /** Inside a loop — may run many times. */
  repeated?: boolean;
}

export interface SeqParticipant {
  id: string;
  label: string;
  group?: string;
  clickLine?: number;
}

const HEAD_H = 40;
const HEAD_GAP = 26;
const ROW_H = 34;
const TOP = 24;
const PAD = 28;
const MIN_W = 132;

function headWidth(label: string): number {
  return Math.max(MIN_W, Math.min(240, Math.round(label.length * 7.7) + 40));
}

/**
 * Walk the call graph depth-first from an entry point, in source order, to a
 * depth limit. Depth-first in call-site order is what makes the result read
 * like an execution: a callee's own calls appear before the caller's next one.
 *
 * A method already on the current stack is not re-entered — that is recursion,
 * and it is reported once rather than unrolled forever.
 */
export function traceCalls(
  root: string,
  callsByCaller: Map<string, SeqCall[]>,
  maxDepth: number
): { call: SeqCall; depth: number; recursive: boolean }[] {
  const out: { call: SeqCall; depth: number; recursive: boolean }[] = [];
  const stack = new Set<string>();

  function walk(id: string, depth: number): void {
    if (depth > maxDepth) {
      return;
    }
    stack.add(id);
    const calls = (callsByCaller.get(id) || [])
      .slice()
      .sort((a, b) => a.line - b.line);
    for (const call of calls) {
      const recursive = stack.has(call.to);
      out.push({ call, depth, recursive });
      if (!recursive) {
        walk(call.to, depth + 1);
      }
    }
    stack.delete(id);
  }

  walk(root, 0);
  return out;
}

/**
 * Lifelines across the top, messages down the page in call order.
 *
 * This is *static* call order — the order call sites appear in the source,
 * followed depth-first. It is not a runtime trace: a call inside a branch may
 * never happen, and one inside a loop may happen many times. Both are marked,
 * and the caption says so, because a sequence diagram that silently implies
 * "this is what runs" is worse than none.
 */
export function sequenceScene(
  root: SeqParticipant,
  participants: Map<string, SeqParticipant>,
  callsByCaller: Map<string, SeqCall[]>,
  maxDepth = 4,
  viewWidth = 900
): Scene {
  const caption =
    "Static call order, followed depth-first — not a runtime trace. " +
    "? may not run (inside a branch) · ✻ may repeat (inside a loop).";

  const traced = traceCalls(root.id, callsByCaller, maxDepth);

  if (!traced.length) {
    return {
      kind: "sequence",
      nodes: [],
      edges: [],
      width: viewWidth,
      height: 200,
      caption,
      legend: SEQ_LEGEND,
      empty: `${root.label} makes no resolved calls.\nPut the cursor in a method that calls others, or check that a language server is running.`,
    };
  }

  // Lifeline order is first appearance, so the diagram reads left-to-right in
  // the order the reader meets each participant.
  const order: string[] = [root.id];
  for (const t of traced) {
    if (!order.includes(t.call.to)) {
      order.push(t.call.to);
    }
  }

  const nodes: SceneNode[] = [];
  const lanes = [];
  const centre = new Map<string, number>();

  let x = PAD;
  for (const id of order) {
    const p = participants.get(id) || { id, label: id };
    const w = headWidth(p.label);
    nodes.push({
      id,
      label: p.label,
      sub: p.group,
      x,
      y: TOP,
      w,
      h: HEAD_H,
      role: "participant",
      group: p.group,
      tip: p.group ? `${p.group}.${p.label}` : p.label,
      clickLine: p.clickLine,
      entry: id === root.id,
    });
    centre.set(id, x + w / 2);
    x += w + HEAD_GAP;
  }

  const bodyTop = TOP + HEAD_H + HEAD_GAP;
  const edges: SceneEdge[] = [];

  traced.forEach((t, i) => {
    const y = bodyTop + i * ROW_H;
    const fromX = centre.get(t.call.from) ?? PAD;
    const toX = centre.get(t.call.to) ?? PAD;

    const marks =
      (t.call.conditional ? " ?" : "") +
      (t.call.repeated ? " ✻" : "") +
      (t.recursive ? " ↻" : "");
    const label =
      (participants.get(t.call.to)?.label ?? t.call.to) + marks;

    if (t.call.from === t.call.to) {
      // Self-call: a small loop to the right of the lifeline.
      edges.push({
        from: t.call.from,
        to: t.call.to,
        points: [
          { x: fromX, y },
          { x: fromX + 34, y },
          { x: fromX + 34, y: y + 14 },
          { x: fromX + 2, y: y + 14 },
        ],
        label,
        style: "solid",
        order: i + 1,
      });
      return;
    }

    edges.push({
      from: t.call.from,
      to: t.call.to,
      points: [
        { x: fromX, y },
        { x: toX, y },
      ],
      label,
      // Depth is carried by the dash pattern so a nested call is visibly nested
      // even when the lifelines are far apart.
      style: t.call.conditional || t.call.repeated ? "dashed" : "solid",
      order: i + 1,
    });
  });

  const bottom = bodyTop + traced.length * ROW_H + 20;
  for (const id of order) {
    lanes.push({ id, x: centre.get(id)!, top: TOP + HEAD_H, bottom });
  }

  const width = Math.max(viewWidth, x - HEAD_GAP + PAD);

  return {
    kind: "sequence",
    nodes,
    edges,
    lanes,
    width,
    height: bottom + PAD,
    caption,
    legend: SEQ_LEGEND,
    hint: "numbers are call order · click a lifeline to open it",
  };
}
