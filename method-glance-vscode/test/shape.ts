import { analyzeShape, annotateShapes, cleanCodeLines, shapeSummary } from "../src/shape";
import { methodsFromText } from "../src/textSource";

let failures = 0;
function ok(name: string, cond: boolean, detail?: string): void {
  if (cond) {
    console.log(`  ok   ${name}`);
  } else {
    failures++;
    console.log(`  FAIL ${name}${detail ? "\n         " + detail : ""}`);
  }
}

const py = (s: string[]) => s;

// ---------------------------------------------------------------------------
// Literals and comments must not be counted as code
// ---------------------------------------------------------------------------

const cleaned = cleanCodeLines(
  py([
    '    """This docstring mentions if and for and while."""',
    "    x = 'a string with return in it'",
    "    # a comment with try except",
    "    if x:",
    "        return 1",
  ]),
  "python"
);
const cleanText = cleaned.join("\n");
ok("docstring keywords stripped", !/\bfor\b/.test(cleanText));
ok("string literal contents stripped", !/a string with/.test(cleanText));
ok("comment contents stripped", !/except/.test(cleanText));
ok("real code survives", /\bif\b/.test(cleanText) && /\breturn\b/.test(cleanText));

const braceClean = cleanCodeLines(
  ["  /* block if for */", '  const s = "while true";', "  if (x) { return 1; }"],
  "brace"
).join("\n");
ok("brace block comment stripped", !/block if/.test(braceClean));
ok("brace string stripped", !/while true/.test(braceClean));
ok("brace code survives", /\bif\b/.test(braceClean));

// A multi-line docstring must not leak its keywords either.
const fenced = cleanCodeLines(
  py(['    """', "    Loop over items and return.", '    """', "    return 1"]),
  "python"
).join("\n");
ok("multi-line docstring fully stripped", !/Loop over/.test(fenced));
ok("code after docstring survives", /\breturn\b/.test(fenced));

// ---------------------------------------------------------------------------
// Counting
// ---------------------------------------------------------------------------

const s1 = analyzeShape(
  py([
    "    if not cart:",
    "        raise CartError('empty')",
    "    total = 0",
    "    for item in cart.items:",
    "        if item.taxable and item.price > 0:",
    "            total += item.price",
    "    try:",
    "        db.execute('INSERT ...')",
    "    except DBError:",
    "        logger.warning('failed')",
    "    return total",
  ]),
  "python"
);
ok("branches counted", s1.branches === 2, `got ${s1.branches}`);
ok("loops counted", s1.loops === 1, `got ${s1.loops}`);
ok("handlers counted", s1.handlers === 1, `got ${s1.handlers}`);
ok("guard clause detected", s1.guards === 1, `got ${s1.guards}`);
ok(
  "complexity = 1 + branches + loops + handlers + boolean ops",
  s1.complexity === 1 + 2 + 1 + 1 + 1,
  `got ${s1.complexity}`
);
ok("db effect detected", s1.effects.includes("db"), s1.effects.join(","));
ok("log effect detected", s1.effects.includes("log"), s1.effects.join(","));
ok("no bogus net effect", !s1.effects.includes("net"), s1.effects.join(","));

// A URL inside a string must not register as a network call.
const s2 = analyzeShape(py(['    url = "https://example.com/api/post"', "    return url"]), "python");
ok("url in a string is not a net effect", !s2.effects.includes("net"), s2.effects.join(","));

const s3 = analyzeShape(py(["    resp = requests.get(url)", "    return resp"]), "python");
ok("real network call detected", s3.effects.includes("net"));

// Mutation marks a command rather than a query.
ok("self assignment counts as mutation", analyzeShape(py(["    self.total = 1"]), "python").mutates);
ok("self comparison is not mutation", !analyzeShape(py(["    return self.total == 1"]), "python").mutates);
ok("this assignment counts in brace langs", analyzeShape(["  this.x = 1;"], "brace").mutates);

// Generators and async.
ok("generator detected", analyzeShape(py(["    yield 1"]), "python").yields === 1);
ok("await detected", analyzeShape(py(["    await go()"]), "python").awaits === 1);

// Nesting depth, with 4-space and 2-space files measuring the same.
const deep4 = analyzeShape(py(["    if a:", "        for b in c:", "            return b"]), "python");
const deep2 = analyzeShape(py(["  if a:", "    for b in c:", "      return b"]), "python");
ok("nesting depth measured", deep4.depth === 2, `got ${deep4.depth}`);
ok("indent width does not change depth", deep2.depth === deep4.depth, `2sp=${deep2.depth} 4sp=${deep4.depth}`);

// Brace ternary counts as a branch, optional chaining does not.
const tern = analyzeShape(["  const v = a ? b : c;", "  const w = x?.y ?? z;"], "brace");
ok("ternary counts as a branch", tern.branches === 1, `got ${tern.branches}`);

// ---------------------------------------------------------------------------
// Effect precision — collection calls must not read as I/O
//
// Found by looking at the map for a real TypeScript file: `Map.get` was
// labelled a network call and `Map.delete` a database write, because the
// patterns matched bare method names. A false effect is worse than no effect.
// ---------------------------------------------------------------------------

const eff = (body: string[], family: "python" | "brace" = "python") =>
  analyzeShape(body, family).effects;

ok("Map.get is not a network call", eff(["  return this.store.get(key);"], "brace").length === 0,
   JSON.stringify(eff(["  return this.store.get(key);"], "brace")));
ok("Map.delete is not a database write", eff(["  this.store.delete(k);"], "brace").length === 0,
   JSON.stringify(eff(["  this.store.delete(k);"], "brace")));
ok("Map.set is not an effect", eff(["  this.store.set(k, v);"], "brace").length === 0);
ok("Array.find is not a query", eff(["  return items.find(x => x.id);"], "brace").length === 0);
ok("dict.update is not a database write", eff(["    self.opts.update(other)"]).length === 0);
ok("list.insert is not a database write", eff(["    items.insert(0, x)"]).length === 0);

// True positives must survive the tightening.
ok("requests.get is still net", eff(["    return requests.get(url)"]).includes("net"));
ok("axios.post is still net", eff(["  return axios.post(u, b);"], "brace").includes("net"));
ok("fetch is still net", eff(["  return fetch(u);"], "brace").includes("net"));
ok("cursor.execute is still db", eff(['    cur.execute("SELECT 1")']).includes("db"));
ok("db.commit is still db", eff(["    self._db.commit()"]).includes("db"));
ok("orm queryset is still db", eff(["    return Order.objects.filter(id=1)"]).includes("db"));
ok("open() is still io", eff(["    with open(p) as f:"]).includes("io"));
ok("logger is still log", eff(['    logger.info("x")']).includes("log"));
ok("subprocess is still proc", eff(["    subprocess.run(cmd)"]).includes("proc"));

// ---------------------------------------------------------------------------
// Entry points
// ---------------------------------------------------------------------------

ok("route decorator marks an entry", analyzeShape(py(["    return 1"]), "python", ["app.route"], "index").entry);
ok("click command marks an entry", analyzeShape(py(["    return 1"]), "python", ["click.command"], "go").entry);
ok("main marks an entry", analyzeShape(py(["    return 1"]), "python", [], "main").entry);
ok("test_ prefix marks an entry", analyzeShape(py(["    return 1"]), "python", [], "test_orders").entry);
ok("a plain helper is not an entry", !analyzeShape(py(["    return 1"]), "python", [], "_price").entry);

// ---------------------------------------------------------------------------
// annotateShapes: a nested helper's body belongs to the helper
// ---------------------------------------------------------------------------

const src = [
  "def outer(items):",
  '    """Outer."""',
  "    def inner(x):",
  '        """Inner."""',
  "        for i in x:",
  "            if i:",
  "                return i",
  "    return inner(items)",
].join("\n");
const methods = methodsFromText("python", src);
annotateShapes(methods, src.split("\n"), "python");
const outer = methods.find((m) => m.name === "outer")!;
const inner = methods.find((m) => m.name === "inner")!;
ok("nested helper analysed separately", inner.shape!.loops === 1 && inner.shape!.branches === 1);
ok(
  "outer is not blamed for its helper's control flow",
  outer.shape!.loops === 0 && outer.shape!.branches === 0,
  `outer loops=${outer.shape!.loops} branches=${outer.shape!.branches}`
);
ok("decorator list captured", Array.isArray(outer.shape!.decorators));

// ---------------------------------------------------------------------------
// Summary line
// ---------------------------------------------------------------------------

const sum = shapeSummary(s1);
ok("summary mentions branches", sum.includes("2 branches"), sum);
ok("summary mentions effects", sum.includes("db"), sum);
ok("empty body summarises to nothing", shapeSummary(analyzeShape(py(["    pass"]), "python")) === "");

console.log("");
if (failures === 0) {
  console.log("All shape tests passed.");
  process.exit(0);
} else {
  console.log(`${failures} test(s) failed.`);
  process.exit(1);
}
