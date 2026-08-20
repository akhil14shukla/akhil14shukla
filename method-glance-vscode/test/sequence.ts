import { sequenceScene, traceCalls, SeqCall, SeqParticipant } from "../src/sequenceLayout";
import { siteContext } from "../src/callSite";

let failures = 0;
function ok(name: string, cond: boolean, detail?: string): void {
  if (cond) console.log(`  ok   ${name}`);
  else { failures++; console.log(`  FAIL ${name}${detail ? "\n         " + detail : ""}`); }
}

const call = (from: string, to: string, line: number, extra: Partial<SeqCall> = {}): SeqCall =>
  ({ from, to, line, ...extra });

function byCaller(calls: SeqCall[]): Map<string, SeqCall[]> {
  const m = new Map<string, SeqCall[]>();
  for (const c of calls) {
    if (!m.has(c.from)) m.set(c.from, []);
    m.get(c.from)!.push(c);
  }
  return m;
}

// ---------------------------------------------------------------------------
// Trace order
// ---------------------------------------------------------------------------

const calls = byCaller([
  call("place_order", "_validate", 12),
  call("place_order", "_price", 13),
  call("place_order", "_charge", 14),
  call("_price", "_tax", 30),
  call("_charge", "_retry", 40),
]);

const traced = traceCalls("place_order", calls, 4);
ok(
  "depth-first in call-site order, so a callee's calls precede the next sibling",
  traced.map((t) => `${t.call.from}>${t.call.to}`).join(" ") ===
    "place_order>_validate place_order>_price _price>_tax place_order>_charge _charge>_retry",
  traced.map((t) => `${t.call.from}>${t.call.to}`).join(" ")
);
ok("depth recorded", traced.find((t) => t.call.to === "_tax")!.depth === 1);

// Source order wins over insertion order.
const unordered = byCaller([call("a", "z", 30), call("a", "b", 10), call("a", "m", 20)]);
ok(
  "calls sorted by source line",
  traceCalls("a", unordered, 3).map((t) => t.call.to).join(" ") === "b m z"
);

// Depth limit.
const deep = byCaller([call("a","b",1), call("b","c",2), call("c","d",3), call("d","e",4)]);
ok("depth limit respected", traceCalls("a", deep, 1).length === 2,
   `got ${traceCalls("a", deep, 1).length}`);

// Recursion must terminate and be reported once.
const rec = byCaller([call("a","a",5)]);
const recTraced = traceCalls("a", rec, 5);
ok("direct recursion terminates", recTraced.length === 1);
ok("direct recursion flagged", recTraced[0].recursive === true);

const mutual = byCaller([call("a","b",1), call("b","a",2)]);
const mutualTraced = traceCalls("a", mutual, 6);
ok("mutual recursion terminates", mutualTraced.length === 2, `got ${mutualTraced.length}`);
ok("mutual recursion flagged", mutualTraced[1].recursive === true);

// ---------------------------------------------------------------------------
// Scene geometry
// ---------------------------------------------------------------------------

const parts = new Map<string, SeqParticipant>([
  ["place_order", { id: "place_order", label: "place_order", group: "OrderService", clickLine: 8 }],
  ["_validate", { id: "_validate", label: "_validate", group: "OrderService", clickLine: 17 }],
  ["_price", { id: "_price", label: "_price", group: "OrderService", clickLine: 24 }],
  ["_charge", { id: "_charge", label: "_charge", group: "OrderService", clickLine: 30 }],
  ["_tax", { id: "_tax", label: "_tax", group: "OrderService", clickLine: 44 }],
  ["_retry", { id: "_retry", label: "_retry", group: "Retry", clickLine: 50 }],
]);

const scene = sequenceScene(parts.get("place_order")!, parts, calls, 4, 900);
ok("scene kind", scene.kind === "sequence");
ok("one lifeline per participant", scene.lanes!.length === scene.nodes.length);
ok("root is the first lifeline", scene.nodes[0].id === "place_order");
ok("root marked as entry", scene.nodes[0].entry === true);
ok("messages numbered from 1", scene.edges[0].order === 1);
ok("messages in trace order", scene.edges.map((e) => e.to).join(" ") === "_validate _price _tax _charge _retry");
ok("participants are navigable", scene.nodes.every((n) => n.clickLine !== undefined));
ok("caption states it is not a runtime trace", /not a runtime trace/i.test(scene.caption || ""));

// Messages must descend the page, never overlap vertically.
const ys = scene.edges.map((e) => e.points[0].y);
ok("messages descend the page", ys.every((y, i) => i === 0 || y > ys[i - 1]));
ok("canvas contains every message", scene.edges.every((e) => e.points.every((p) => p.y <= scene.height)));
ok("lifelines span the messages", scene.lanes!.every((l) => l.bottom >= Math.max(...ys)));

// Conditional and repeated calls are marked, not silently drawn as certain.
const marked = sequenceScene(
  parts.get("place_order")!,
  parts,
  byCaller([
    call("place_order", "_validate", 12, { conditional: true }),
    call("place_order", "_price", 13, { repeated: true }),
  ]),
  3,
  900
);
ok("conditional call marked", /\?/.test(marked.edges[0].label || ""), marked.edges[0].label);
ok("repeated call marked", /✻/.test(marked.edges[1].label || ""), marked.edges[1].label);
ok("uncertain calls drawn dashed", marked.edges.every((e) => e.style === "dashed"));

// A method with no calls gets a useful empty state, not a blank panel.
const none = sequenceScene(parts.get("_tax")!, parts, new Map(), 4, 900);
ok("empty state explains itself", /no resolved calls/i.test(none.empty || ""));
ok("empty scene draws nothing", none.nodes.length === 0);

// Self-call routes as a loop with four points rather than a zero-length line.
const selfScene = sequenceScene(
  parts.get("_retry")!, parts, byCaller([call("_retry", "_retry", 51)]), 3, 900
);
ok("self-call routed as a loop", selfScene.edges[0].points.length === 4);

// ---------------------------------------------------------------------------
// Call-site context
// ---------------------------------------------------------------------------

const pyLines = [
  "def run(self, items):",          // 0
  "    self.setup()",                // 1  unconditional
  "    if items:",                   // 2
  "        self.handle(items)",      // 3  conditional
  "    for i in items:",             // 4
  "        self.each(i)",            // 5  repeated
  "        if i.bad:",               // 6
  "            self.warn(i)",        // 7  conditional AND repeated
  "    try:",                        // 8
  "        self.finish()",           // 9  conditional
  "    except Exception:",           // 10
  "        pass",                    // 11
];
const ctx = (line: number) => siteContext(pyLines, 0, 11, line, "python");
ok("unconditional call not marked", !ctx(1).conditional && !ctx(1).repeated);
ok("call inside if marked conditional", ctx(3).conditional && !ctx(3).repeated);
ok("call inside for marked repeated", ctx(5).repeated && !ctx(5).conditional);
ok("call inside if inside for marked both", ctx(7).conditional && ctx(7).repeated);
ok("call inside try marked conditional", ctx(9).conditional);

// A keyword inside a string must not invent a branch.
const stringy = [
  "def go(self):",
  "    msg = 'if you see this it is not a branch'",
  "    self.send(msg)",
];
ok("keyword in a string does not create a branch",
   !siteContext(stringy, 0, 2, 2, "python").conditional);

const braceLines = [
  "function run(items) {",     // 0
  "  setup();",                 // 1
  "  if (items.length) {",      // 2
  "    handle(items);",         // 3
  "  }",                        // 4
  "  for (const i of items) {", // 5
  "    each(i);",               // 6
  "  }",                        // 7
  "}",                          // 8
];
const bctx = (line: number) => siteContext(braceLines, 0, 8, line, "brace");
ok("brace: call inside if marked conditional", bctx(3).conditional);
ok("brace: call inside for marked repeated", bctx(6).repeated);

console.log("");
if (failures === 0) { console.log("All sequence tests passed."); process.exit(0); }
console.log(`${failures} test(s) failed.`); process.exit(1);
