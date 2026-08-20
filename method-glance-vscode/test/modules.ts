import { classify, moduleForUri, parseImports } from "../src/modules";
import { moduleScene } from "../src/moduleLayout";

let failures = 0;
function ok(name: string, cond: boolean, detail?: string): void {
  if (cond) console.log(`  ok   ${name}`);
  else { failures++; console.log(`  FAIL ${name}${detail ? "\n         " + detail : ""}`); }
}

// ---------------------------------------------------------------------------
// Classification
// ---------------------------------------------------------------------------

ok("relative import is local", classify(".utils", "python") === "local");
ok("python stdlib recognised", classify("os.path", "python") === "stdlib");
ok("python third-party is the default", classify("requests", "python") === "third-party");
ok("node builtin recognised", classify("fs", "brace") === "stdlib");
ok("node: prefix recognised", classify("node:crypto", "brace") === "stdlib");
ok("relative js import is local", classify("./helpers", "brace") === "local");
ok("scoped package is third-party", classify("@scope/pkg", "brace") === "third-party");

// ---------------------------------------------------------------------------
// Parsing
// ---------------------------------------------------------------------------

const py = [
  "import os",
  "import json, re",
  "from pathlib import Path",
  "from .models import Order, Cart",
  "from collections import (defaultdict, deque)",
  "import numpy as np",
  "# import shutil",
  "TEXT = 'import antigravity'",
].join("\n");
const pyMods = parseImports(py, "python");
const names = pyMods.map((m) => m.name).sort();

ok("plain import", names.includes("os"));
ok("comma import splits", names.includes("json") && names.includes("re"), names.join(","));
ok("from-import", names.includes("pathlib"));
ok("relative from-import", names.includes(".models"));
ok("aliased import uses the real module name", names.includes("numpy") && !names.includes("np"));
ok("commented import ignored", !names.includes("shutil"), names.join(","));
ok("import inside a string ignored", !names.includes("antigravity"), names.join(","));

const models = pyMods.find((m) => m.name === ".models")!;
ok("imported members captured", models.members.join(",") === "Order,Cart", models.members.join(","));
ok("parenthesised members captured",
   pyMods.find((m) => m.name === "collections")!.members.join(",") === "defaultdict,deque");
ok("relative import classified local", models.kind === "local");

const js = [
  "import fs from 'fs';",
  "import { render } from './view';",
  "const lodash = require('lodash');",
  "// import ghost from 'ghost';",
].join("\n");
const jsNames = parseImports(js, "brace").map((m) => m.name).sort();
ok("js import form", jsNames.includes("fs"));
ok("js relative import", jsNames.includes("./view"));
ok("require form", jsNames.includes("lodash"));
ok("commented js import ignored", !jsNames.includes("ghost"), jsNames.join(","));

// Duplicate imports merge rather than producing two nodes.
const dup = parseImports("from a import x\nfrom a import y", "python");
ok("duplicate module merged", dup.length === 1 && dup[0].members.join(",") === "x,y");

// ---------------------------------------------------------------------------
// URI -> module
// ---------------------------------------------------------------------------

ok("uri matched to an import",
   moduleForUri("file:///proj/models.py", pyMods.concat([{name:"models",kind:"local",line:0,members:[],calls:0}])) === "models");
ok("unmatched uri falls back to the file stem",
   moduleForUri("file:///proj/helpers.py", []) === "helpers");

// ---------------------------------------------------------------------------
// Scene
// ---------------------------------------------------------------------------

const mods = [
  { name: "os", kind: "stdlib" as const, line: 0, members: [], calls: 1 },
  { name: ".models", kind: "local" as const, line: 3, members: ["Order"], calls: 5 },
  { name: "requests", kind: "third-party" as const, line: 2, members: [], calls: 2 },
  { name: "unused", kind: "third-party" as const, line: 4, members: [], calls: 0 },
];
const scene = moduleScene("orders.py", mods, 900);

ok("scene kind", scene.kind === "modules");
ok("one node per module plus the file", scene.nodes.length === mods.length + 1);
ok("the file itself is marked", scene.nodes[0].id === "__self__" && scene.nodes[0].entry === true);
ok("an edge per module", scene.edges.length === mods.length);

const order = scene.nodes.slice(1).map((n) => n.id);
ok("local modules listed before third-party and stdlib",
   order[0] === ".models", order.join(","));
ok("heavier dependency listed first within its kind",
   order.indexOf("requests") < order.indexOf("unused"), order.join(","));

const unusedEdge = scene.edges.find((e) => e.to === "unused")!;
ok("uncalled import drawn dashed", unusedEdge.style === "dashed");
ok("called import drawn solid", scene.edges.find((e) => e.to === "os")!.style === "solid");
ok("edge weight carries call count", scene.edges.find((e) => e.to === ".models")!.count === 5);
ok("uncalled import kept, not dropped", order.includes("unused"));
ok("modules are navigable", scene.nodes.slice(1).every((n) => n.clickLine !== undefined));
ok("nodes fit the canvas",
   scene.nodes.every((n) => n.x + n.w <= scene.width && n.y + n.h <= scene.height),
   JSON.stringify(scene.nodes.map(n=>[n.id,n.x+n.w,n.y+n.h])));
ok("caption explains the dashed edges", /dashed/i.test(scene.caption || ""));
ok("deterministic", JSON.stringify(moduleScene("orders.py", mods, 900)) === JSON.stringify(scene));
ok("input order does not change output",
   JSON.stringify(moduleScene("orders.py", [...mods].reverse(), 900)) === JSON.stringify(scene));

// No vertical overlap in the module column.
let overlap = false;
const col = scene.nodes.slice(1);
for (const a of col) for (const b of col) {
  if (a === b) continue;
  if (a.y < b.y + b.h && b.y < a.y + a.h) overlap = true;
}
ok("no overlapping module boxes", !overlap);

// Rails must agree with the legend: every kind rendered needs a pinned colour.
const kinds = [...new Set(mods.map((m) => m.kind))];
ok(
  "every module kind has a pinned colour",
  kinds.every((k) => !!scene.groupColors && !!scene.groupColors[k]),
  JSON.stringify(scene.groupColors)
);
ok(
  "pinned colours cover the legend entries",
  Object.keys(scene.groupColors || {}).length === 3
);

ok("empty state explains the view", /imports nothing/i.test(moduleScene("x.py", [], 900).empty || ""));

console.log("");
if (failures === 0) { console.log("All module tests passed."); process.exit(0); }
console.log(`${failures} test(s) failed.`); process.exit(1);
