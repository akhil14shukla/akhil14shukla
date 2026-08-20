import * as fs from "fs";
import * as path from "path";

/**
 * Static guards on the webview assets. They cannot be unit-tested through a
 * DOM here, so the rules that already cost a real bug are asserted directly
 * against the source.
 */
let failures = 0;
function ok(name: string, cond: boolean, detail?: string): void {
  if (cond) console.log(`  ok   ${name}`);
  else { failures++; console.log(`  FAIL ${name}${detail ? "\n         " + detail : ""}`); }
}

const root = path.join(__dirname, "..", "..");
const js = fs.readFileSync(path.join(root, "media", "glance.js"), "utf8");
const css = fs.readFileSync(path.join(root, "media", "glance.css"), "utf8");
const panel = fs.readFileSync(path.join(root, "src", "panel.ts"), "utf8");

// `hidden` is an HTMLElement property. SVGElement does not implement it, so
// `svg.hidden = false` sets a JS expando and leaves the attribute in place —
// which, combined with the `[hidden]` rule, hid the diagram in every view.
ok(
  "svg visibility is toggled by attribute, not the hidden property",
  !/\bsvg\.hidden\s*=/.test(js),
  "use svg.setAttribute/removeAttribute('hidden') instead"
);
ok(
  "svg is shown by removing the attribute",
  js.includes('svg.removeAttribute("hidden")')
);

// The `[hidden]` rule is what makes the attribute authoritative over the
// toolbar's display:inline-flex. Without it, per-view controls never hide.
ok("hidden attribute overrides display rules", /\[hidden\]\s*\{[^}]*display:\s*none\s*!important/.test(css));

// Every element the script reaches for must exist in the panel's markup.
const ids = [...js.matchAll(/getElementById\("([^"]+)"\)/g)].map((m) => m[1]);
const missing = ids.filter((id) => !panel.includes(`id="${id}"`));
ok("every element the webview looks up exists in the markup", missing.length === 0,
   `missing: ${missing.join(", ")}`);

// The webview must never receive a raw layout: everything goes through Scene.
ok("webview renders scenes", js.includes("render(msg.scene"), "expected msg.scene");
ok("panel posts scenes", panel.includes("scene,"));

// CSP: no inline handlers or remote references may creep into the markup.
ok("no inline event handlers in the panel markup", !/\son\w+=/.test(panel.split("<body>")[1] || ""));
ok("no external resource URLs", !/https?:\/\//.test(css));

console.log("");
if (failures === 0) { console.log("All webview contract tests passed."); process.exit(0); }
console.log(`${failures} test(s) failed.`); process.exit(1);
