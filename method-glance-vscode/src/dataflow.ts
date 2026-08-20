import { cleanCodeLines } from "./shape";
import { LanguageFamily } from "./types";

/**
 * Where a value ends up. These are the questions worth asking of a parameter:
 * does it leave the function, does it change the object, or does it just steer
 * a branch?
 */
export type SinkKind = "call" | "return" | "state" | "raise" | "condition";

export interface FlowSink {
  id: string;
  kind: SinkKind;
  label: string;
  line: number;
}

export interface FlowStep {
  /** Local name assigned from one or more tracked values. */
  name: string;
  line: number;
  /** Tracked names this assignment reads. */
  from: string[];
}

export interface FlowResult {
  params: string[];
  steps: FlowStep[];
  sinks: FlowSink[];
  /** name -> sink ids it reaches. */
  edges: { from: string; to: string }[];
}

const PY_KEYWORDS = new Set([
  "if","elif","else","for","while","return","raise","try","except","finally",
  "with","and","or","not","in","is","None","True","False","def","class","import",
  "from","as","pass","break","continue","lambda","yield","await","assert","del",
  "global","nonlocal","self",
]);

const BRACE_KEYWORDS = new Set([
  "if","else","for","while","return","throw","try","catch","finally","switch",
  "case","const","let","var","new","this","function","await","yield","typeof",
  "instanceof","true","false","null","undefined","break","continue",
]);

/** Identifiers appearing in a line, minus language keywords. */
function identifiers(line: string, family: LanguageFamily): string[] {
  const kw = family === "python" ? PY_KEYWORDS : BRACE_KEYWORDS;
  const out: string[] = [];
  const re = /[A-Za-z_$][\w$]*/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(line)) !== null) {
    // Skip attribute access: the `y` in `x.y` is a member, not a local.
    if (m.index > 0 && line[m.index - 1] === ".") {
      continue;
    }
    if (!kw.has(m[0])) {
      out.push(m[0]);
    }
  }
  return out;
}

/** Parameter names from a signature, minus `self`/`cls` and defaults. */
export function parseParams(
  signature: string,
  family: LanguageFamily
): string[] {
  const open = signature.indexOf("(");
  if (open === -1) {
    return [];
  }
  let depth = 0;
  let end = -1;
  for (let i = open; i < signature.length; i++) {
    if ("([{".includes(signature[i])) depth++;
    else if (")]}".includes(signature[i])) {
      depth--;
      if (depth === 0) {
        end = i;
        break;
      }
    }
  }
  if (end === -1) {
    return [];
  }
  const inner = signature.slice(open + 1, end);

  const parts: string[] = [];
  let buf = "";
  let d = 0;
  for (const ch of inner) {
    if ("([{".includes(ch)) d++;
    if (")]}".includes(ch)) d--;
    if (ch === "," && d === 0) {
      parts.push(buf);
      buf = "";
    } else {
      buf += ch;
    }
  }
  if (buf.trim()) {
    parts.push(buf);
  }

  const out: string[] = [];
  for (const raw of parts) {
    let p = raw.split("=")[0].split(":")[0].trim();
    p = p.replace(/^[*&.]+/, "").trim();
    if (!p || p === "self" || p === "cls" || p === "this") {
      continue;
    }
    if (/^[A-Za-z_$][\w$]*$/.test(p)) {
      out.push(p);
    }
  }
  return out;
}

/**
 * Follow each parameter through a method body to the places its value ends up.
 *
 * This is a **heuristic**, not real dataflow analysis. It tracks assignment by
 * name, propagating through locals for as many passes as it takes to settle. It
 * cannot see a value put into a container and taken out again, reassignment
 * that happens only on one branch, or aliasing through a closure. It is useful
 * for the common shape — parameter, a couple of locals, a call — and the view
 * says so rather than implying precision it does not have.
 */
export function analyzeFlow(
  signature: string,
  bodyLines: string[],
  bodyStartLine: number,
  family: LanguageFamily
): FlowResult {
  const params = parseParams(signature, family);
  const code = cleanCodeLines(bodyLines, family);

  const tracked = new Set(params);
  const steps: FlowStep[] = [];
  const sinks: FlowSink[] = [];
  const edges: { from: string; to: string }[] = [];
  const seenEdge = new Set<string>();

  const addEdge = (from: string, to: string): void => {
    const k = `${from}->${to}`;
    if (!seenEdge.has(k)) {
      seenEdge.add(k);
      edges.push({ from, to });
    }
  };

  const assignRe =
    family === "python"
      ? /^\s*([A-Za-z_]\w*)\s*(?::[^=]+)?=(?!=)(.*)$/
      : /^\s*(?:const|let|var)?\s*([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=(?!=)(.*)$/;
  const stateRe =
    family === "python"
      ? /^\s*self\.([A-Za-z_]\w*)\s*(?:[-+*/|&]?=)(?!=)(.*)$/
      : /^\s*this\.([A-Za-z_$][\w$]*)\s*(?:[-+*/|&]?=)(?!=)(.*)$/;

  // Repeat until no new local becomes tracked: a value can reach a local via
  // another local assigned further down.
  for (let pass = 0; pass < 4; pass++) {
    let grew = false;
    code.forEach((line, i) => {
      const state = line.match(stateRe);
      const asg = state ? null : line.match(assignRe);
      if (!asg) {
        return;
      }
      const target = asg[1];
      const sources = identifiers(asg[2], family).filter((id) =>
        tracked.has(id)
      );
      if (!sources.length || tracked.has(target)) {
        return;
      }
      tracked.add(target);
      grew = true;
      steps.push({ name: target, line: bodyStartLine + i, from: [...new Set(sources)] });
    });
    if (!grew) {
      break;
    }
  }

  code.forEach((line, i) => {
    const absolute = bodyStartLine + i;
    if (!line.trim()) {
      return;
    }
    const used = identifiers(line, family).filter((id) => tracked.has(id));
    if (!used.length) {
      return;
    }

    const state = line.match(stateRe);
    if (state) {
      const id = `state:${state[1]}`;
      if (!sinks.some((s) => s.id === id)) {
        sinks.push({
          id,
          kind: "state",
          label: (family === "python" ? "self." : "this.") + state[1],
          line: absolute,
        });
      }
      for (const u of identifiers(state[2], family).filter((x) => tracked.has(x))) {
        addEdge(u, id);
      }
      return;
    }

    const isReturn = /^\s*return\b/.test(line);
    const isRaise = family === "python" ? /^\s*raise\b/.test(line) : /^\s*throw\b/.test(line);
    const isCond = /^\s*(if|elif|while|assert)\b/.test(line);

    // A call anywhere on the line, taking the outermost callee name.
    const callMatch = line.match(/([A-Za-z_$][\w$.]*)\s*\(/);

    if (isReturn) {
      const id = "return";
      if (!sinks.some((s) => s.id === id)) {
        sinks.push({ id, kind: "return", label: "return", line: absolute });
      }
      used.forEach((u) => addEdge(u, id));
      // A return may also be a call; record both.
    }
    if (isRaise) {
      const id = "raise";
      if (!sinks.some((s) => s.id === id)) {
        sinks.push({ id, kind: "raise", label: "raise", line: absolute });
      }
      used.forEach((u) => addEdge(u, id));
      return;
    }

    if (callMatch) {
      const callee = callMatch[1];
      // The assignment target itself is a step, not a sink.
      const asg = line.match(assignRe);
      const args = asg ? asg[2] : line;
      const inArgs = identifiers(args, family).filter((id) => tracked.has(id));
      if (inArgs.length) {
        const id = `call:${callee}`;
        if (!sinks.some((s) => s.id === id)) {
          sinks.push({
            id,
            kind: "call",
            label: `${callee}()`,
            line: absolute,
          });
        }
        inArgs.forEach((u) => addEdge(u, id));
      }
      return;
    }

    if (isCond && !isReturn) {
      const id = "condition";
      if (!sinks.some((s) => s.id === id)) {
        sinks.push({ id, kind: "condition", label: "steers a branch", line: absolute });
      }
      used.forEach((u) => addEdge(u, id));
    }
  });

  return { params, steps, sinks, edges };
}
