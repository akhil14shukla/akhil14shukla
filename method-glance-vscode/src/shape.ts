import { MethodNode } from "./model";
import { codePortion } from "./pythonParser";
import { LanguageFamily } from "./types";

/**
 * Side effects worth knowing about before reading a body. These are what turn
 * "a function" into "a function that talks to the database", which is usually
 * the first thing you want to know and the last thing a name tells you.
 */
export type Effect = "io" | "net" | "db" | "proc" | "log" | "time" | "random";

export interface MethodShape {
  /** if / elif / else-if / ternary — decision points. */
  branches: number;
  loops: number;
  /** except / catch clauses. */
  handlers: number;
  returns: number;
  raises: number;
  yields: number;
  awaits: number;
  /** Returns or raises that are not the final statement — guard clauses. */
  guards: number;
  /** Cyclomatic complexity: 1 + every independent path. */
  complexity: number;
  /** Deepest nesting inside the body, in levels. */
  depth: number;
  effects: Effect[];
  /** Assigns to `self.` / `this.` — a command rather than a query. */
  mutates: boolean;
  /** Decorators applied to the definition. */
  decorators: string[];
  /** Reads as a way into the script: CLI entry, route handler, test. */
  entry: boolean;
}

/**
 * Matched against literal-stripped code.
 *
 * These require a *recognisable receiver or library*, never a bare method name.
 * An earlier version matched `.get(`, `.delete(`, `.find(` and `.update(`
 * anywhere, which labelled every `Map.get` as a network call and every
 * `Array.find` as a database query — noise that is worse than no label at all.
 * Precision is the right trade here: missing an exotic ORM costs less than
 * telling someone their cache lookup talks to the network.
 */
const EFFECT_PATTERNS: [Effect, RegExp][] = [
  [
    "io",
    /\b(open|Path|shutil|readFileSync|writeFileSync|appendFileSync|createReadStream|createWriteStream|read_text|write_text|readlines|writelines)\s*\(|\b(os\.path|pathlib)\b|\.\s*(write|writelines|readline)\s*\(/,
  ],
  [
    "net",
    /\b(requests|urllib|httpx|aiohttp|socket|axios|XMLHttpRequest|WebSocket|urlopen)\b|\bfetch\s*\(|\b(requests|httpx|axios|http|https|client|api)\s*\.\s*(get|post|put|patch|delete|head)\s*\(/,
  ],
  [
    "db",
    /\b(cursor|execute|executemany|commit|rollback|queryset|sessionmaker)\b|\b(db|database|conn|connection|session)\s*\.\s*\w+\s*\(|\.objects\.\w+\s*\(/,
  ],
  ["proc", /\b(subprocess|popen|spawn|execFile|os\.system|child_process)\b/i],
  ["log", /\b(print|logging|logger|console|warnings)\b/],
  [
    "time",
    /\b(sleep|perf_counter|monotonic|datetime|Date\.now|setTimeout|setInterval)\b|\btime\./,
  ],
  ["random", /\b(random|uuid|secrets|shuffle|Math\.random)\b/],
];

const ENTRY_DECORATORS =
  /^(app|router|bp|blueprint|celery|task|click|api|route|get|post|put|patch|delete|command|group|fixture|shared_task|cli)\b|\b(route|command|task|handler|endpoint)\b/i;

/**
 * Strip comments and string bodies so keyword counting cannot be fooled by a
 * docstring that says "if" or a URL that contains "post".
 */
export function cleanCodeLines(
  lines: string[],
  family: LanguageFamily
): string[] {
  const out: string[] = [];

  if (family === "python") {
    let fence: string | null = null;
    for (const raw of lines) {
      let line = raw;
      if (fence) {
        // Inside a triple-quoted block: emit nothing until it closes.
        const close = line.indexOf(fence);
        if (close === -1) {
          out.push("");
          continue;
        }
        line = line.slice(close + 3);
        fence = null;
      }
      let code = codePortion(line);
      // Consume any triple-quoted runs that open on this line.
      for (;;) {
        const m = code.match(/("""|''')/);
        if (!m) {
          break;
        }
        const q = m[1];
        const start = code.indexOf(q);
        const rest = code.slice(start + 3);
        const end = rest.indexOf(q);
        if (end === -1) {
          fence = q;
          code = code.slice(0, start);
          break;
        }
        code = code.slice(0, start) + " " + rest.slice(end + 3);
      }
      // Blank out ordinary string literals.
      code = code.replace(/(['"])(?:\\.|(?!\1).)*\1/g, '""');
      out.push(code);
    }
    return out;
  }

  let block = false;
  for (const raw of lines) {
    let code = raw;
    if (block) {
      const close = code.indexOf("*/");
      if (close === -1) {
        out.push("");
        continue;
      }
      code = code.slice(close + 2);
      block = false;
    }
    code = code.replace(/\/\*[\s\S]*?\*\//g, " ");
    const open = code.indexOf("/*");
    if (open !== -1) {
      block = true;
      code = code.slice(0, open);
    }
    code = code.replace(/\/\/.*$/, "");
    code = code.replace(/(['"`])(?:\\.|(?!\1).)*\1/g, '""');
    out.push(code);
  }
  return out;
}

function count(text: string, re: RegExp): number {
  const m = text.match(re);
  return m ? m.length : 0;
}

/** Indent unit inferred from the body, so 2- and 4-space files both measure right. */
function nestingDepth(codeLines: string[], family: LanguageFamily): number {
  if (family !== "python") {
    let depth = 0;
    let max = 0;
    for (const l of codeLines) {
      for (const ch of l) {
        if (ch === "{") {
          max = Math.max(max, ++depth);
        } else if (ch === "}") {
          depth = Math.max(0, depth - 1);
        }
      }
    }
    return Math.max(0, max - 1);
  }

  const indents = codeLines
    .filter((l) => l.trim().length)
    .map((l) => l.length - l.replace(/^[ \t]+/, "").length);
  if (!indents.length) {
    return 0;
  }
  const base = Math.min(...indents);
  const steps = indents
    .map((i) => i - base)
    .filter((d) => d > 0)
    .sort((a, b) => a - b);
  const unit = steps.length ? steps[0] : 4;
  return Math.round((Math.max(...indents) - base) / (unit || 4));
}

/**
 * Read a method body's structure. Text-level on purpose: this works with no
 * language server running, and control-flow keywords are unambiguous once
 * comments and string bodies are gone.
 */
export function analyzeShape(
  bodyLines: string[],
  family: LanguageFamily,
  decorators: string[] = [],
  name = ""
): MethodShape {
  const code = cleanCodeLines(bodyLines, family);
  const text = code.join("\n");
  const py = family === "python";

  const branches = py
    ? count(text, /\b(?:if|elif)\b/g) + count(text, /\bcase\b/g)
    : count(text, /\bif\b/g) + count(text, /\bcase\b/g) + count(text, /(?<![?.])\?(?![?.])/g);

  const loops = count(text, /\b(?:for|while)\b/g);
  const handlers = py ? count(text, /\bexcept\b/g) : count(text, /\bcatch\b/g);
  const returns = count(text, /\breturn\b/g);
  const raises = py ? count(text, /\braise\b/g) : count(text, /\bthrow\b/g);
  const yields = count(text, /\byield\b/g);
  const awaits = count(text, /\bawait\b/g);
  const bools = py
    ? count(text, /\b(?:and|or)\b/g)
    : count(text, /&&|\|\|/g);

  // An exit that is not the last statement is a guard clause.
  let guards = 0;
  const exitRe = py ? /\b(?:return|raise)\b/ : /\b(?:return|throw)\b/;
  const lastCode = (() => {
    for (let i = code.length - 1; i >= 0; i--) {
      if (code[i].trim().length) {
        return i;
      }
    }
    return -1;
  })();
  for (let i = 0; i < code.length; i++) {
    if (i !== lastCode && exitRe.test(code[i])) {
      guards++;
    }
  }

  const effects: Effect[] = [];
  for (const [effect, re] of EFFECT_PATTERNS) {
    if (re.test(text)) {
      effects.push(effect);
    }
  }

  const mutates = py
    ? /\bself\.\w+\s*(?:[-+*/|&]?=)(?!=)/.test(text)
    : /\bthis\.\w+\s*(?:[-+*/|&]?=)(?!=)/.test(text);

  const entry =
    decorators.some((d) => ENTRY_DECORATORS.test(d)) ||
    /^(main|run|handler|handle|cli|__main__)$/i.test(name) ||
    /^test_/.test(name);

  return {
    branches,
    loops,
    handlers,
    returns,
    raises,
    yields,
    awaits,
    guards,
    complexity: 1 + branches + loops + handlers + bools,
    depth: nestingDepth(code, family),
    effects,
    mutates,
    decorators,
    entry,
  };
}

/** Decorator names sitting directly above a definition. */
function decoratorsAbove(lines: string[], defLine: number): string[] {
  const out: string[] = [];
  for (let i = defLine - 1; i >= 0; i--) {
    const t = lines[i].trim();
    if (!t) {
      continue;
    }
    if (!t.startsWith("@")) {
      break;
    }
    out.unshift(t.slice(1).split("(")[0].trim());
  }
  return out;
}

/**
 * Attach a shape to every method, measuring only its own body — lines belonging
 * to a nested definition are left to that definition, so an outer function is
 * not blamed for its helper's complexity.
 */
export function annotateShapes(
  methods: MethodNode[],
  lines: string[],
  family: LanguageFamily
): void {
  for (const m of methods) {
    const nestedLines = new Set<number>();
    for (const other of methods) {
      if (
        other !== m &&
        other.range.start > m.range.start &&
        other.range.end <= m.range.end
      ) {
        for (let i = other.range.start; i <= other.range.end; i++) {
          nestedLines.add(i);
        }
      }
    }

    const body: string[] = [];
    for (let i = m.foldStart + 1; i <= m.range.end && i < lines.length; i++) {
      body.push(nestedLines.has(i) ? "" : lines[i]);
    }

    m.shape = analyzeShape(
      body,
      family,
      family === "python" ? decoratorsAbove(lines, m.selectionLine) : [],
      m.name
    );
  }
}

/**
 * Instance attributes assigned anywhere in a range — `self.x = …` in Python,
 * `this.x = …` in the C family. Reported in first-assignment order, which is
 * usually declaration order in `__init__`/the constructor.
 *
 * Read from literal-stripped code so an assignment inside a string is not
 * mistaken for a real one.
 */
export function attributesIn(
  lines: string[],
  family: LanguageFamily
): string[] {
  const code = cleanCodeLines(lines, family);
  const re =
    family === "python"
      ? /\bself\.([A-Za-z_]\w*)\s*(?:[-+*/|&]?=)(?!=)/g
      : /\bthis\.([A-Za-z_$][\w$]*)\s*(?:[-+*/|&]?=)(?!=)/g;
  const seen: string[] = [];
  for (const line of code) {
    re.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(line)) !== null) {
      if (!seen.includes(m[1])) {
        seen.push(m[1]);
      }
    }
  }
  return seen;
}

/** Compact one-line summary for an inline editor annotation. */
export function shapeSummary(s: MethodShape): string {
  const bits: string[] = [];
  if (s.branches) bits.push(`${s.branches} branch${s.branches > 1 ? "es" : ""}`);
  if (s.loops) bits.push(`${s.loops} loop${s.loops > 1 ? "s" : ""}`);
  if (s.handlers) bits.push(`${s.handlers} catch`);
  if (s.guards) bits.push(`${s.guards} guard${s.guards > 1 ? "s" : ""}`);
  if (s.yields) bits.push("generator");
  if (s.awaits) bits.push("async");
  if (s.mutates) bits.push("mutates");
  if (s.effects.length) bits.push(s.effects.join(" "));
  return bits.join(" · ");
}
