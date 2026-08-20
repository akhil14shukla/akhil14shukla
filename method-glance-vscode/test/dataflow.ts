import { analyzeFlow, parseParams } from "../src/dataflow";
import { flowScene } from "../src/flowLayout";

let failures = 0;
function ok(name: string, cond: boolean, detail?: string): void {
  if (cond) console.log(`  ok   ${name}`);
  else { failures++; console.log(`  FAIL ${name}${detail ? "\n         " + detail : ""}`); }
}

// ---------------------------------------------------------------------------
// Signatures
// ---------------------------------------------------------------------------

ok("plain params", parseParams("def f(self, cart, user):", "python").join(",") === "cart,user");
ok("self dropped", !parseParams("def f(self):", "python").length);
ok("defaults stripped", parseParams("def f(a, b=3, c='x'):", "python").join(",") === "a,b,c");
ok("annotations stripped", parseParams("def f(a: int, b: List[str]) -> None:", "python").join(",") === "a,b");
ok("annotation commas not split", parseParams("def f(a: Dict[str, int], b) -> None:", "python").join(",") === "a,b");
ok("star args normalised", parseParams("def f(*args, **kw):", "python").join(",") === "args,kw");
ok("multi-line signature", parseParams("def f(\n  a,\n  b,\n):", "python").join(",") === "a,b");
ok("brace params", parseParams("function f(a, b = 2) {", "brace").join(",") === "a,b");
ok("this dropped", parseParams("run(this, x) {", "brace").join(",") === "x");
ok("no parens is safe", parseParams("weird", "python").length === 0);

// ---------------------------------------------------------------------------
// Flow
// ---------------------------------------------------------------------------

const body = [
  "    if not cart:",                        // condition
  "        raise CartError(cart)",
  "    subtotal = price_of(cart)",           // step: subtotal from cart
  "    total = subtotal + tax(subtotal)",    // step: total from subtotal
  "    self.last_total = total",             // state sink
  "    log_it(user)",                        // call sink
  "    return total",                        // return sink
];
const flow = analyzeFlow("def place(self, cart, user):", body, 10, "python");

ok("params found", flow.params.join(",") === "cart,user");
ok("local assigned from a param is tracked",
   flow.steps.some((s) => s.name === "subtotal" && s.from.includes("cart")));
ok("transitive local tracked",
   flow.steps.some((s) => s.name === "total" && s.from.includes("subtotal")),
   JSON.stringify(flow.steps));

const sinkIds = flow.sinks.map((s) => s.id);
ok("state sink found", sinkIds.includes("state:last_total"), sinkIds.join(","));
ok("return sink found", sinkIds.includes("return"));
ok("call sink found", sinkIds.some((s) => s.startsWith("call:")), sinkIds.join(","));
ok("condition sink found", sinkIds.includes("condition"));
ok("raise carrying a tracked value creates a sink", sinkIds.includes("raise"), sinkIds.join(","));

// A raise that carries none of the tracked values is not a sink for them —
// the view must not imply a parameter reaches somewhere it does not.
const bareRaise = analyzeFlow(
  "def f(self, cart):",
  ["    if not cart:", "        raise CartError('empty')", "    return 1"],
  0,
  "python"
);
ok(
  "raise carrying no tracked value is not a sink",
  !bareRaise.sinks.some((s) => s.id === "raise"),
  bareRaise.sinks.map((s) => s.id).join(",")
);

const reaches = (from: string, to: string) => flow.edges.some((e) => e.from === from && e.to === to);
ok("cart steers the branch", reaches("cart", "condition"));
ok("cart reaches the raise it is passed to", reaches("cart", "raise"));
ok("user reaches the call it is passed to", flow.edges.some((e) => e.from === "user" && e.to.startsWith("call:")));
ok("total reaches return", reaches("total", "return"));
ok("total reaches instance state", reaches("total", "state:last_total"));
ok("line numbers are absolute", flow.sinks.every((s) => s.line >= 10));

// An untouched parameter produces no edges rather than a fake one.
const unused = analyzeFlow("def f(self, ghost):", ["    return 1"], 0, "python");
ok("unused parameter has no edges", !unused.edges.some((e) => e.from === "ghost"));

// Keywords and attribute access must not be mistaken for locals.
const attrs = analyzeFlow("def f(self, cart):", ["    return cart.total"], 0, "python");
ok("attribute name is not a tracked local", !attrs.steps.some((s) => s.name === "total"));
ok("param through attribute still reaches return", attrs.edges.some((e) => e.from === "cart" && e.to === "return"));

// A parameter mentioned only inside a string must not register.
const stringy = analyzeFlow("def f(self, token):", ["    return 'token is secret'"], 0, "python");
ok("parameter named in a string is not traced", !stringy.edges.some((e) => e.from === "token"));

// Brace language.
const bflow = analyzeFlow(
  "run(this, items) {",
  ["  const first = items[0];", "  return send(first);"],
  0,
  "brace"
);
ok("brace: local tracked", bflow.steps.some((s) => s.name === "first"));
ok("brace: reaches a call", bflow.edges.some((e) => e.to.startsWith("call:")));

// ---------------------------------------------------------------------------
// Scene
// ---------------------------------------------------------------------------

const scene = flowScene("place", flow, 900);
ok("scene kind", scene.kind === "flow");
ok("caption admits the heuristic", /heuristic/i.test(scene.caption || ""));
ok("params in the first column",
   scene.nodes.filter((n) => n.role === "param").every((n) => n.x === scene.nodes[0].x));
ok("value travels left to right",
   scene.edges.every((e) => e.points[1].x >= e.points[0].x));
ok("nodes fit the canvas",
   scene.nodes.every((n) => n.x + n.w <= scene.width && n.y + n.h <= scene.height));
ok("flow nodes are not clickable", scene.nodes.every((n) => n.clickLine === undefined));
ok("deterministic", JSON.stringify(flowScene("place", flow, 900)) === JSON.stringify(scene));

// No vertical overlap within a column.
let overlap = false;
for (const a of scene.nodes) for (const b of scene.nodes) {
  if (a === b || a.x !== b.x) continue;
  if (a.y < b.y + b.h && b.y < a.y + a.h) overlap = true;
}
ok("no overlapping nodes in a column", !overlap);

// Empty states.
ok("no-params state explains itself",
   /takes no parameters/i.test(flowScene("f", analyzeFlow("def f(self):", ["    pass"], 0, "python"), 900).empty || ""));
ok("untraceable state explains itself",
   /cannot follow/i.test(flowScene("f", unused, 900).empty || ""));

// A missing middle column must not leave a gap.
const direct = analyzeFlow("def f(self, x):", ["    return x"], 0, "python");
const directScene = flowScene("f", direct, 900);
const xs = [...new Set(directScene.nodes.map((n) => n.x))].sort((a, b) => a - b);
ok("empty local column is skipped, not left blank", xs.length === 2, `columns at ${xs.join(",")}`);

console.log("");
if (failures === 0) { console.log("All dataflow tests passed."); process.exit(0); }
console.log(`${failures} test(s) failed.`); process.exit(1);
