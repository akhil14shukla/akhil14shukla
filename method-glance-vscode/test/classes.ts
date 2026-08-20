import { classScene, visibilityOf, ClassBox, InheritEdge } from "../src/classLayout";
import { attributesIn } from "../src/shape";

let failures = 0;
function ok(name: string, cond: boolean, detail?: string): void {
  if (cond) console.log(`  ok   ${name}`);
  else { failures++; console.log(`  FAIL ${name}${detail ? "\n         " + detail : ""}`); }
}

// ---------------------------------------------------------------------------
// Attribute extraction
// ---------------------------------------------------------------------------

const py = [
  "    def __init__(self, db):",
  "        self._db = db",
  "        self.count = 0",
  "        self.count += 1",
  "        note = 'self.fake = 1'",
  "        if self.count == 0:",
  "            self.ready = True",
];
const attrs = attributesIn(py, "python");
ok("attributes found in assignment order", attrs.join(",") === "_db,count,ready", attrs.join(","));
ok("augmented assignment does not duplicate", attrs.filter((a) => a === "count").length === 1);
ok("comparison is not an assignment", !attrs.includes("fake") && attrs.length === 3);
ok("assignment inside a string ignored", !attrs.includes("fake"));

const ts = attributesIn(["  this.store = new Map();", '  const s = "this.x = 1";'], "brace");
ok("brace attributes found", ts.join(",") === "store", ts.join(","));

// ---------------------------------------------------------------------------
// Visibility
// ---------------------------------------------------------------------------

ok("public", visibilityOf("save") === "+");
ok("protected", visibilityOf("_price") === "#");
ok("private", visibilityOf("__secret") === "-");
ok("dunder is public, not private", visibilityOf("__init__") === "+");

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

const boxes: ClassBox[] = [
  { name: "Base", clickLine: 1, members: [
    { name: "run", visibility: "+", kind: "method", clickLine: 2 },
  ]},
  { name: "OrderService", clickLine: 10, members: [
    { name: "_db", visibility: "#", kind: "attribute" },
    { name: "place_order", visibility: "+", kind: "method", clickLine: 12, effects: ["db"] },
    { name: "_tax", visibility: "#", kind: "method", clickLine: 20 },
  ]},
  { name: "Mixin", clickLine: 40, members: [], external: true },
];
const inherits: InheritEdge[] = [{ from: "OrderService", to: "Base" }];

const scene = classScene(boxes, inherits, 900);
ok("scene kind", scene.kind === "classes");
ok("a node per class", scene.nodes.length === 3);

const y = new Map(scene.nodes.map((n) => [n.id, n.y]));
ok("supertype sits above its subtype", y.get("Base")! < y.get("OrderService")!,
   `Base=${y.get("Base")} OrderService=${y.get("OrderService")}`);

const svc = scene.nodes.find((n) => n.id === "OrderService")!;
ok("attributes listed before methods", svc.rows![0].includes("_db"), svc.rows!.join(" | "));
ok("methods get parentheses", svc.rows!.some((r) => r.includes("place_order()")));
ok("attributes get no parentheses", !svc.rows![0].includes("()"));
ok("visibility markers rendered", svc.rows!.some((r) => r.startsWith("# _tax")));
ok("effects shown on members", svc.rows!.some((r) => r.includes("db")));
ok("box is tall enough for its rows", svc.h >= 26 + svc.rows!.length * 16);

ok("external class marked", scene.nodes.find((n) => n.id === "Mixin")!.external === true);
ok("inheritance edge drawn", scene.edges.length === 1);
ok("edge runs subtype -> supertype", scene.edges[0].from === "OrderService" && scene.edges[0].to === "Base");
ok("inheritance uses the hollow arrow style", scene.edges[0].style === "inherit");
ok("classes are navigable", scene.nodes.every((n) => n.clickLine !== undefined));
ok("every box fits the canvas",
   scene.nodes.every((n) => n.x + n.w <= scene.width && n.y + n.h <= scene.height));

// No overlap between boxes on the same row.
let overlap = false;
for (const a of scene.nodes) for (const b of scene.nodes) {
  if (a === b || a.y !== b.y) continue;
  if (a.x < b.x + b.w && b.x < a.x + a.w) overlap = true;
}
ok("no overlapping boxes", !overlap);

// Determinism.
const again = classScene(boxes, inherits, 900);
ok("layout is deterministic", JSON.stringify(again.nodes) === JSON.stringify(scene.nodes));
const shuffled = classScene([...boxes].reverse(), inherits, 900);
ok("input order does not change placement",
   JSON.stringify(shuffled.nodes.map(n=>[n.id,n.x,n.y]).sort()) ===
   JSON.stringify(scene.nodes.map(n=>[n.id,n.x,n.y]).sort()));

// A long member list is summarised rather than becoming a wall of text.
const many: ClassBox[] = [{ name: "Big", members: Array.from({length: 20}, (_, i) =>
  ({ name: `m${i}`, visibility: "+" as const, kind: "method" as const })) }];
const bigScene = classScene(many, [], 900);
ok("long member list truncated", bigScene.nodes[0].rows!.length === 13, `${bigScene.nodes[0].rows!.length}`);
ok("truncation states the remainder", bigScene.nodes[0].rows!.slice(-1)[0].includes("8 more"));

// Cyclic inheritance must not hang.
const cyc = classScene(
  [{ name: "A", members: [] }, { name: "B", members: [] }],
  [{ from: "A", to: "B" }, { from: "B", to: "A" }],
  900
);
ok("cyclic inheritance terminates", cyc.nodes.length === 2);

// Inheritance edges must not cross when a straight arrangement exists — the
// commonest way a small class diagram looks sloppy.
function segmentsCross(a: {x:number;y:number}[], b: {x:number;y:number}[]): boolean {
  const side = (p: any, q: any, r: any) =>
    (q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x);
  return (
    side(a[0], a[1], b[0]) * side(a[0], a[1], b[1]) < 0 &&
    side(b[0], b[1], a[0]) * side(b[0], b[1], a[1]) < 0
  );
}
const crossing = classScene(
  [
    { name: "Serializable", members: [], external: true },
    { name: "BaseService", members: [] },
    { name: "OrderService", members: [] },
    { name: "Order", members: [] },
  ],
  [
    { from: "OrderService", to: "BaseService" },
    { from: "Order", to: "Serializable" },
  ],
  900
);
ok(
  "subtypes ordered under their supertypes, so edges do not cross",
  !segmentsCross(crossing.edges[0].points, crossing.edges[1].points)
);

// Empty state.
const none = classScene([], [], 900);
ok("empty state explains the view", /no classes/i.test(none.empty || ""));

console.log("");
if (failures === 0) { console.log("All class tests passed."); process.exit(0); }
console.log(`${failures} test(s) failed.`); process.exit(1);
