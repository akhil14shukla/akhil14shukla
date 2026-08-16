import { GraphEdge, GraphNode, layout } from "../src/layout";
import { toMermaid } from "../src/mermaid";

let failures = 0;

function ok(name: string, cond: boolean, detail?: string): void {
  if (cond) {
    console.log(`  ok   ${name}`);
  } else {
    failures++;
    console.log(`  FAIL ${name}${detail ? "\n         " + detail : ""}`);
  }
}

function n(id: string, group?: string): GraphNode {
  return { id, label: id, group };
}
function e(from: string, to: string): GraphEdge {
  return { from, to };
}

// ---------------------------------------------------------------------------
// Layering
// ---------------------------------------------------------------------------

const nodes = [n("place_order"), n("_validate"), n("_price"), n("_charge"), n("_tax")];
const edges = [
  e("place_order", "_validate"),
  e("place_order", "_price"),
  e("place_order", "_charge"),
  e("_price", "_tax"),
];
const r = layout(nodes, edges, 900);

const layerOf = new Map(r.nodes.map((x) => [x.id, x.layer]));
ok("caller sits above its callees", layerOf.get("place_order") === 0);
ok("direct callees share a layer", layerOf.get("_validate") === 1 && layerOf.get("_charge") === 1);
ok(
  "transitive callee pushed a layer deeper",
  layerOf.get("_tax") === 2,
  `_tax layer=${layerOf.get("_tax")}`
);

// No two nodes in a layer may overlap horizontally.
let overlap = false;
for (const a of r.nodes) {
  for (const b of r.nodes) {
    if (a === b || a.layer !== b.layer || a.layer < 0) {
      continue;
    }
    if (a.x < b.x + b.w && b.x < a.x + a.w) {
      overlap = true;
    }
  }
}
ok("no overlapping nodes within a layer", !overlap);

ok("every edge routed with a start and end point",
  r.edges.every((x) => x.points.length >= 2));
ok("canvas is large enough for every node",
  r.nodes.every((x) => x.x + x.w <= r.width && x.y + x.h <= r.height));

// ---------------------------------------------------------------------------
// Determinism — the same input must draw the same picture every time
// ---------------------------------------------------------------------------

const again = layout(nodes, edges, 900);
ok(
  "layout is deterministic",
  JSON.stringify(again.nodes) === JSON.stringify(r.nodes)
);

// Input order must not change the result either.
const shuffled = layout([...nodes].reverse(), [...edges].reverse(), 900);
const posOf = (res: typeof r) =>
  JSON.stringify(
    res.nodes.slice().sort((a, b) => a.id.localeCompare(b.id)).map((x) => [x.id, x.layer])
  );
ok("layout is independent of input order", posOf(shuffled) === posOf(r));

// ---------------------------------------------------------------------------
// Cycles
// ---------------------------------------------------------------------------

const cyc = layout(
  [n("a"), n("b"), n("c")],
  [e("a", "b"), e("b", "c"), e("c", "a")],
  600
);
ok("cyclic graph still lays out", cyc.nodes.length === 3);
ok("cycle is preserved, not dropped", cyc.edges.length === 3);
ok("back edge is marked reversed", cyc.edges.some((x) => x.reversed));
// The reversed edge must still report its true direction.
const back = cyc.edges.find((x) => x.reversed)!;
ok(
  "reversed edge keeps caller→callee direction",
  back.from === "c" && back.to === "a",
  `got ${back.from}->${back.to}`
);

// Recursion becomes a self-edge with no geometry, not a crash.
const rec = layout([n("f")], [e("f", "f")], 400);
ok("self-call kept as a badge edge", rec.edges.length === 1 && rec.edges[0].points.length === 0);

// ---------------------------------------------------------------------------
// Detached nodes
// ---------------------------------------------------------------------------

const many = Array.from({ length: 12 }, (_, i) => n(`solo${i}`));
const det = layout([...nodes, ...many], edges, 900);
ok("unconnected nodes are pulled out of the layered section",
  det.nodes.filter((x) => x.layer === -1).length === 12);
ok("detached divider position reported", det.detachedFrom !== undefined);
// They must wrap into a grid rather than forming one enormous row.
const rows = new Set(det.nodes.filter((x) => x.layer === -1).map((x) => x.y));
ok("detached nodes wrap onto multiple rows", rows.size > 1, `rows=${rows.size}`);
ok("detached grid stays inside the canvas",
  det.nodes.every((x) => x.x + x.w <= det.width));

// ---------------------------------------------------------------------------
// Edge cases
// ---------------------------------------------------------------------------

const empty = layout([], [], 800);
ok("empty graph is safe", empty.nodes.length === 0 && empty.width >= 320);

const dangling = layout([n("a")], [e("a", "ghost")], 800);
ok("edge to a missing node is dropped", dangling.edges.length === 0);

// ---------------------------------------------------------------------------
// Mermaid export
// ---------------------------------------------------------------------------

const mmd = toMermaid(
  [n("place_order", "OrderService"), n("_tax", "OrderService"), { id: "gateway.capture", label: "capture", external: true }],
  [{ from: "place_order", to: "_tax" }, { from: "place_order", to: "gateway.capture", cross: true }]
);
ok("mermaid starts with a flowchart header", mmd.startsWith("flowchart TD"));
ok("mermaid groups by class", mmd.includes('subgraph g0["OrderService"]'));
ok("mermaid marks external nodes as stadium", /\(\["capture"\]\)/.test(mmd));
ok("mermaid dashes cross-file edges", mmd.includes("-.->"));

// Delimiter-breaking characters must be stripped from the label itself; the
// quotes wrapping it are Mermaid's own syntax and must survive.
const risky = toMermaid([{ id: "x", label: 'we"ird[label]' }], []);
ok(
  "mermaid label is sanitised",
  risky.split("\n")[1] === '  n0_x("weirdlabel")',
  `got ${JSON.stringify(risky.split("\n")[1])}`
);

console.log("");
if (failures === 0) {
  console.log("All layout tests passed.");
  process.exit(0);
} else {
  console.log(`${failures} test(s) failed.`);
  process.exit(1);
}
