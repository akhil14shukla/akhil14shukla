import { GraphEdge, GraphNode } from "./layout";
import { ClassBox, InheritEdge } from "./classLayout";
import { SeqCall, SeqParticipant } from "./sequenceLayout";
import { traceCalls } from "./sequenceLayout";

/** Mermaid labels break on quotes and brackets; keep them plain. */
function safeLabel(s: string): string {
  return s.replace(/["[\]{}<>|]/g, "").trim() || "unnamed";
}

/** Mermaid node ids must be identifier-safe and stable. */
function safeId(id: string, seq: number): string {
  const base = id.replace(/[^A-Za-z0-9_]/g, "_").slice(0, 40);
  return `n${seq}_${base}`;
}

/**
 * Render the call graph as a Mermaid flowchart so it can be pasted into a PR,
 * an issue, or a Markdown doc as text — the one form of the diagram that
 * survives outside the editor.
 *
 * Methods are grouped into subgraphs by their class, which is how people
 * actually read a file.
 */
export function toMermaid(nodes: GraphNode[], edges: GraphEdge[]): string {
  const ids = new Map<string, string>();
  nodes.forEach((n, i) => ids.set(n.id, safeId(n.id, i)));

  const lines: string[] = ["flowchart TD"];

  const groups = new Map<string, GraphNode[]>();
  for (const n of nodes) {
    const key = n.group || "";
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key)!.push(n);
  }

  let sub = 0;
  for (const [group, members] of groups) {
    const indent = group ? "    " : "  ";
    if (group) {
      lines.push(`  subgraph g${sub++}["${safeLabel(group)}"]`);
    }
    for (const n of members) {
      const label = safeLabel(n.label);
      // Rounded for local methods, stadium for anything outside the file.
      lines.push(
        n.external
          ? `${indent}${ids.get(n.id)}(["${label}"])`
          : `${indent}${ids.get(n.id)}("${label}")`
      );
    }
    if (group) {
      lines.push("  end");
    }
  }

  for (const e of edges) {
    const a = ids.get(e.from);
    const b = ids.get(e.to);
    if (!a || !b) {
      continue;
    }
    const arrow = e.cross ? "-.->" : "-->";
    const label = e.count && e.count > 1 ? `|${e.count}x| ` : "";
    lines.push(`  ${a} ${arrow} ${label}${b}`);
  }

  return lines.join("\n");
}


/**
 * Mermaid's own sequence syntax, so a copied sequence diagram is still a
 * sequence diagram. Exporting the call graph from every view — which is what
 * this used to do — hands over a picture of something the reader did not ask
 * for.
 */
export function toMermaidSequence(
  rootId: string,
  participants: Map<string, SeqParticipant>,
  callsByCaller: Map<string, SeqCall[]>,
  maxDepth: number
): string {
  const traced = traceCalls(rootId, callsByCaller, maxDepth);
  const lines: string[] = ["sequenceDiagram"];

  const order: string[] = [rootId];
  for (const t of traced) {
    if (!order.includes(t.call.to)) {
      order.push(t.call.to);
    }
  }
  const alias = new Map<string, string>();
  order.forEach((id, i) => alias.set(id, `p${i}`));

  for (const id of order) {
    const p = participants.get(id);
    lines.push(`  participant ${alias.get(id)} as ${safeLabel(p?.label ?? id)}`);
  }

  for (const t of traced) {
    const from = alias.get(t.call.from);
    const to = alias.get(t.call.to);
    if (!from || !to) {
      continue;
    }
    const label = safeLabel(participants.get(t.call.to)?.label ?? t.call.to);
    const note =
      (t.call.conditional ? " [opt]" : "") +
      (t.call.repeated ? " [loop]" : "") +
      (t.recursive ? " [recursive]" : "");
    lines.push(`  ${from}->>${to}: ${label}${note}`);
  }

  return lines.join("\n");
}

/** Mermaid's class syntax, including members and inheritance. */
export function toMermaidClasses(
  boxes: ClassBox[],
  inherits: InheritEdge[]
): string {
  const lines: string[] = ["classDiagram"];
  for (const b of boxes) {
    const name = safeId(b.name, 0).replace(/^n0_/, "") || "Unnamed";
    lines.push(`  class ${name} {`);
    for (const m of b.members) {
      lines.push(
        `    ${m.visibility}${safeLabel(m.name)}${m.kind === "method" ? "()" : ""}`
      );
    }
    lines.push("  }");
    if (b.external) {
      lines.push(`  <<external>> ${name}`);
    }
  }
  for (const e of inherits) {
    const a = safeId(e.to, 0).replace(/^n0_/, "");
    const b = safeId(e.from, 0).replace(/^n0_/, "");
    lines.push(`  ${a} <|-- ${b}`);
  }
  return lines.join("\n");
}
