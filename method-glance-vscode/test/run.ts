import { computeFoldSpecs } from "../src/parse";
import { FoldSpec } from "../src/types";

let failures = 0;

function eq(name: string, actual: FoldSpec[], expected: FoldSpec[]): void {
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

// ---------------------------------------------------------------------------
// Python
// ---------------------------------------------------------------------------

const pyDocstring = [
  "def greet(name):", //                       0
  '    """Return a greeting for name."""', //  1
  "    prefix = 'Hello'", //                   2
  "    return f'{prefix}, {name}!'", //        3
].join("\n");
// Keep signature (0) and docstring (1) visible; hide 2-3.
eq("py: single-line docstring", computeFoldSpecs("python", pyDocstring), [
  { start: 1, end: 3 },
]);

const pyMultiline = [
  "def area(r):", //                    0
  '    """', //                         1
  "    Compute a circle's area.", //    2
  '    """', //                         3
  "    import math", //                 4
  "    return math.pi * r * r", //      5
].join("\n");
// Docstring closes on line 3; hide 4-5.
eq("py: multi-line docstring", computeFoldSpecs("python", pyMultiline), [
  { start: 3, end: 5 },
]);

const pyNoDoc = [
  "def add(a, b):", //     0
  "    total = a + b", //  1
  "    return total", //   2
].join("\n");
// No docstring: fold from signature (0), hide 1-2.
eq("py: no docstring", computeFoldSpecs("python", pyNoDoc), [
  { start: 0, end: 2 },
]);

const pyMethods = [
  "class Shape:", //                          0
  "    def __init__(self, sides):", //        1
  '        """Store the side count."""', //   2
  "        self.sides = sides", //            3
  "", //                                      4
  "    def describe(self):", //               5
  '        """Human-readable summary."""', // 6
  "        return f'{self.sides}-sided'", //  7
].join("\n");
// Each method folds independently; the class line and signatures stay visible.
eq("py: methods in a class", computeFoldSpecs("python", pyMethods), [
  { start: 2, end: 3 },
  { start: 6, end: 7 },
]);

const pyMultilineSig = [
  "def connect(", //          0
  "    host,", //             1
  "    port=5432,", //        2
  "):", //                    3
  '    """Open a socket."""', // 4
  "    return (host, port)", //  5
].join("\n");
eq("py: multi-line signature", computeFoldSpecs("python", pyMultilineSig), [
  { start: 4, end: 5 },
]);

const pyOneLiner = "def noop(): return None";
eq("py: one-line def has nothing to fold", computeFoldSpecs("python", pyOneLiner), []);

// ---------------------------------------------------------------------------
// Brace languages
// ---------------------------------------------------------------------------

const ts = [
  "/** Add two numbers. */", //      0
  "function add(a: number, b: number): number {", // 1
  "  const total = a + b;", //       2
  "  return total;", //              3
  "}", //                            4
].join("\n");
// Fold the body brace-to-brace; the JSDoc and signature stay visible.
eq("ts: documented function", computeFoldSpecs("typescript", ts), [
  { start: 1, end: 4 },
]);

const tsClass = [
  "class Calc {", //          0
  "  add(a, b) {", //         1
  "    return a + b;", //     2
  "  }", //                   3
  "  sub(a, b) {", //         4
  "    return a - b;", //     5
  "  }", //                   6
  "}", //                     7
].join("\n");
// Methods fold; the class body itself is not folded so methods stay visible.
eq("ts: class methods only", computeFoldSpecs("typescript", tsClass), [
  { start: 1, end: 3 },
  { start: 4, end: 6 },
]);

const tsControl = [
  "function run(items) {", //   0
  "  for (const x of items) {", // 1
  "    if (x > 0) {", //        2
  "      handle(x);", //        3
  "    }", //                   4
  "  }", //                     5
  "}", //                       6
].join("\n");
// Only the function body folds; for/if control blocks are left expanded.
eq("ts: control flow not folded", computeFoldSpecs("typescript", tsControl), [
  { start: 0, end: 6 },
]);

const tsArrow = [
  "const double = (x) => {", //  0
  "  return x * 2;", //          1
  "};", //                       2
].join("\n");
eq("ts: arrow function", computeFoldSpecs("typescript", tsArrow), [
  { start: 0, end: 2 },
]);

const tsTemplate = [
  "function label(x) {", //             0
  "  return `val: ${ {a: x}.a }`;", //  1  (braces inside template expr)
  "}", //                               2
].join("\n");
// The template's `${ { } }` braces must not confuse body matching.
eq("ts: template literal braces", computeFoldSpecs("typescript", tsTemplate), [
  { start: 0, end: 2 },
]);

const java = [
  "public class Greeter {", //                     0
  "    /** Greet someone. */", //                  1
  "    public String greet(String name) {", //     2
  '        return "Hi " + name;', //               3
  "    }", //                                      4
  "}", //                                          5
].join("\n");
eq("java: method", computeFoldSpecs("java", java), [{ start: 2, end: 4 }]);

// ---------------------------------------------------------------------------
// Unsupported
// ---------------------------------------------------------------------------

eq("unsupported language yields nothing", computeFoldSpecs("plaintext", "hello"), []);

console.log("");
if (failures === 0) {
  console.log("All tests passed.");
  process.exit(0);
} else {
  console.log(`${failures} test(s) failed.`);
  process.exit(1);
}
