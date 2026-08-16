import { methodsFromSymbols, SymbolLike, KIND } from "../src/symbols";
import { methodsFromText } from "../src/textSource";
import { docInfoFor } from "../src/docs";

let failures = 0;

function check(name: string, actual: unknown, expected: unknown): void {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a === e) {
    console.log(`  ok   ${name}`);
  } else {
    failures++;
    console.log(`  FAIL ${name}`);
    console.log(`         expected ${e}`);
    console.log(`         actual   ${a}`);
  }
}

function sym(
  name: string,
  kind: number,
  start: number,
  end: number,
  nameLine: number,
  children: SymbolLike[] = []
): SymbolLike {
  return {
    name,
    kind,
    range: { start: { line: start }, end: { line: end } },
    selectionRange: { start: { line: nameLine } },
    children,
  };
}

// ---------------------------------------------------------------------------
// Symbol path — the primary source
// ---------------------------------------------------------------------------

const pySrc = [
  "class Repo:", //                             0
  '    """A store."""', //                      1
  "", //                                        2
  "    @cached", //                             3  decorator: in range, not nameLine
  "    def find(self, id):", //                 4
  '        """Return a record."""', //          5
  "        return self._db.get(id)", //         6
].join("\n");
const pyLines = pySrc.split("\n");

const pySymbols: SymbolLike[] = [
  sym("Repo", KIND.Class, 0, 6, 0, [sym("find", KIND.Method, 3, 6, 4)]),
];

const pyMethods = methodsFromSymbols(pySymbols, pyLines, "python");

check(
  "symbols: container carried from the class",
  pyMethods.map((m) => m.container),
  ["Repo"]
);
// The decorator is inside range.start (3) but the def is on line 4; the fold
// must still begin at the docstring's last line (5), not the decorator.
check(
  "symbols: fold starts at docstring end, decorator ignored",
  pyMethods.map((m) => m.foldStart),
  [5]
);
check(
  "symbols: docstring text extracted",
  pyMethods.map((m) => m.doc),
  ["Return a record."]
);
check(
  "symbols: origin marked semantic",
  pyMethods.map((m) => m.origin),
  ["semantic"]
);

// Multi-line docstrings get dedented, not returned with body indentation.
const multiSrc = [
  "def area(r):", //          0
  '    """', //               1
  "    Compute area.", //     2
  "", //                      3
  "    Uses pi.", //          4
  '    """', //               5
  "    return 3.14 * r * r", // 6
].join("\n");
const multiMethods = methodsFromSymbols(
  [sym("area", KIND.Function, 0, 6, 0)],
  multiSrc.split("\n"),
  "python"
);
check("symbols: multi-line docstring dedented", multiMethods[0].doc, [
  "Compute area.",
  "",
  "Uses pi.",
].join("\n"));
check("symbols: multi-line fold start", multiMethods[0].foldStart, 5);

// Brace language: doc comment sits above the signature.
const tsSrc = [
  "class Cache {", //          0
  "  /** Look up a key. */", // 1
  "  get(key) {", //           2
  "    return this.m.get(key);", // 3
  "  }", //                    4
  "}", //                      5
].join("\n");
const tsMethods = methodsFromSymbols(
  [sym("Cache", KIND.Class, 0, 5, 0, [sym("get", KIND.Method, 1, 4, 2)])],
  tsSrc.split("\n"),
  "brace"
);
check("symbols: brace fold starts at opening brace", tsMethods[0].foldStart, 2);
check("symbols: brace doc comment read", tsMethods[0].doc, "Look up a key.");
check("symbols: brace container", tsMethods[0].container, "Cache");

// Nested helper functions are kept as their own foldable methods.
const nestedMethods = methodsFromSymbols(
  [
    sym("outer", KIND.Function, 0, 5, 0, [
      sym("inner", KIND.Function, 2, 4, 2),
    ]),
  ],
  ["def outer():", "    x = 1", "    def inner():", '        """Doc."""', "        return 2", ""],
  "python"
);
check(
  "symbols: nested functions kept",
  nestedMethods.map((m) => m.name),
  ["outer", "inner"]
);

// ---------------------------------------------------------------------------
// Text fallback — must produce the same shape
// ---------------------------------------------------------------------------

const fallback = methodsFromText("python", pySrc);
check(
  "fallback: finds the method with its container",
  fallback.map((m) => `${m.container}.${m.name}`),
  ["Repo.find"]
);
check(
  "fallback: same fold point as the semantic path",
  fallback.map((m) => m.foldStart),
  [5]
);
check(
  "fallback: origin marked textual",
  fallback.map((m) => m.origin),
  ["textual"]
);

const fbTs = methodsFromText("brace", tsSrc);
check(
  "fallback: brace method name recovered",
  fbTs.map((m) => m.name),
  ["get"]
);

// A one-line def has nothing to fold and must not appear.
check("fallback: one-line def skipped", methodsFromText("python", "def f(): return 1"), []);

// ---------------------------------------------------------------------------
// docInfoFor directly
// ---------------------------------------------------------------------------

check(
  "docs: undocumented python folds from the signature",
  docInfoFor("python", ["def add(a, b):", "    return a + b"], { start: 0, end: 1 }, 0),
  { foldStart: 0 }
);
check(
  "docs: multi-line signature closes on the right line",
  docInfoFor(
    "python",
    ["def f(", "    a,", "):", '    """D."""', "    return a"],
    { start: 0, end: 4 },
    0
  ),
  { foldStart: 3, doc: "D." }
);

console.log("");
if (failures === 0) {
  console.log("All semantic-layer tests passed.");
  process.exit(0);
} else {
  console.log(`${failures} test(s) failed.`);
  process.exit(1);
}
