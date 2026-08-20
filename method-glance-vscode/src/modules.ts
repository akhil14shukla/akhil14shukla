import { codePortion } from "./pythonParser";
import { LanguageFamily } from "./types";

export type ModuleKind = "local" | "third-party" | "stdlib";

export interface ImportedModule {
  /** Module path as written, e.g. `os.path` or `./utils`. */
  name: string;
  kind: ModuleKind;
  line: number;
  /** Names pulled from it, when the import form lists them. */
  members: string[];
  /** Resolved calls landing in this module. */
  calls: number;
}

/**
 * A deliberately small stdlib list. Getting this wrong in the safe direction —
 * calling something third-party when it is stdlib — costs only a colour, while
 * shipping a huge table would rot. Anything unrecognised and non-relative is
 * third-party.
 */
const PY_STDLIB = new Set([
  "abc","argparse","ast","asyncio","base64","collections","contextlib","copy",
  "csv","dataclasses","datetime","decimal","enum","functools","glob","hashlib",
  "heapq","hmac","html","http","importlib","inspect","io","itertools","json",
  "logging","math","os","pathlib","pickle","queue","random","re","secrets",
  "shutil","signal","socket","sqlite3","statistics","string","struct","subprocess",
  "sys","tempfile","textwrap","threading","time","traceback","types","typing",
  "unittest","urllib","uuid","warnings","weakref","xml","zipfile",
]);

const NODE_BUILTIN = new Set([
  "assert","buffer","child_process","cluster","crypto","dns","events","fs",
  "http","https","net","os","path","process","querystring","readline","stream",
  "string_decoder","timers","tls","url","util","v8","vm","worker_threads","zlib",
]);

export function classify(name: string, family: LanguageFamily): ModuleKind {
  if (name.startsWith(".") || name.startsWith("/") || name.startsWith("~")) {
    return "local";
  }
  const head = name.split(/[./]/)[0];
  if (family === "python") {
    return PY_STDLIB.has(head) ? "stdlib" : "third-party";
  }
  if (name.startsWith("node:") || NODE_BUILTIN.has(head)) {
    return "stdlib";
  }
  return "third-party";
}

const PY_FROM = /^\s*from\s+([.\w]+)\s+import\s+(.+)$/;
const PY_IMPORT = /^\s*import\s+([.\w]+)(?:\s+as\s+\w+)?/;
const JS_FROM = /^\s*import\s+(?:.+?\s+from\s+)?["']([^"']+)["']/;
const JS_REQUIRE = /\brequire\(\s*["']([^"']+)["']\s*\)/;

/**
 * Strip comments while keeping string literals intact.
 *
 * The usual literal-stripping pass cannot be reused here: in JavaScript the
 * module name *is* the string literal, so blanking it would erase the very
 * thing being parsed. Comments still have to go, because a commented-out
 * import must not be reported as a dependency.
 */
function stripComments(lines: string[], family: LanguageFamily): string[] {
  if (family === "python") {
    return lines.map((l) => codePortion(l));
  }

  const out: string[] = [];
  let block = false;
  for (const raw of lines) {
    let line = raw;
    if (block) {
      const close = line.indexOf("*/");
      if (close === -1) {
        out.push("");
        continue;
      }
      line = line.slice(close + 2);
      block = false;
    }

    let result = "";
    let quote: string | null = null;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      const next = line[i + 1];
      if (quote) {
        result += ch;
        if (ch === "\\") {
          result += next ?? "";
          i++;
        } else if (ch === quote) {
          quote = null;
        }
        continue;
      }
      if (ch === '"' || ch === "'" || ch === "`") {
        quote = ch;
        result += ch;
        continue;
      }
      if (ch === "/" && next === "/") {
        break;
      }
      if (ch === "/" && next === "*") {
        const close = line.indexOf("*/", i + 2);
        if (close === -1) {
          block = true;
          break;
        }
        i = close + 1;
        continue;
      }
      result += ch;
    }
    out.push(result);
  }
  return out;
}

/**
 * Imports as written in the file. Comments are removed but string literals are
 * kept, because an accurate list matters here — an unused import is one of the
 * things the view exists to show.
 */
export function parseImports(
  text: string,
  family: LanguageFamily
): ImportedModule[] {
  const raw = text.split(/\r\n|\r|\n/);
  const code = stripComments(raw, family);
  const found = new Map<string, ImportedModule>();

  const add = (name: string, line: number, members: string[]): void => {
    const existing = found.get(name);
    if (existing) {
      for (const m of members) {
        if (!existing.members.includes(m)) {
          existing.members.push(m);
        }
      }
      return;
    }
    found.set(name, {
      name,
      kind: classify(name, family),
      line,
      members,
      calls: 0,
    });
  };

  code.forEach((line, i) => {
    if (family === "python") {
      const f = line.match(PY_FROM);
      if (f) {
        const members = f[2]
          .replace(/[()]/g, "")
          .split(",")
          .map((m) => m.split(/\s+as\s+/)[0].trim())
          .filter((m) => m && m !== "*");
        add(f[1], i, members);
        return;
      }
      const im = line.match(PY_IMPORT);
      if (im) {
        // `import a, b` — the regex catches the first; split the rest by comma.
        const all = line.replace(/^\s*import\s+/, "").split(",");
        for (const part of all) {
          const nm = part.trim().split(/\s+as\s+/)[0].trim();
          if (/^[.\w]+$/.test(nm)) {
            add(nm, i, []);
          }
        }
      }
      return;
    }

    const jf = line.match(JS_FROM);
    if (jf) {
      add(jf[1], i, []);
      return;
    }
    const jr = line.match(JS_REQUIRE);
    if (jr) {
      add(jr[1], i, []);
    }
  });

  return [...found.values()];
}

/**
 * Turn a cross-file callee URI into a module name to group by. Prefers a name
 * matching an import, so the graph and the import list agree.
 */
export function moduleForUri(uri: string, imports: ImportedModule[]): string {
  const file = uri.split("/").pop() || uri;
  const stem = file.replace(/\.[^.]+$/, "");
  // Prefer an exact match; fall back to matching the final path segment, so
  // `models` beats `.models` when both are imported.
  const exact = imports.find((m) => m.name === stem);
  if (exact) {
    return exact.name;
  }
  const suffix = imports.find((m) => m.name.split(/[./]/).pop() === stem);
  return suffix ? suffix.name : stem;
}
