import { GraphEdge, GraphNode } from "./layout";

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
