import { docInfoFor } from "./docs";
import { MethodNode, methodId } from "./model";
import { parseBrace } from "./braceParser";
import { indentWidth, isBlank, signatureEnd } from "./pythonParser";
import { LanguageFamily } from "./types";

const PY_DEF = /^(\s*)(?:async\s+)?def\s+([A-Za-z_]\w*)/;
const PY_CLASS = /^(\s*)class\s+([A-Za-z_]\w*)/;
const BRACE_NAME = /([A-Za-z_$][\w$]*)\s*(?:<[^;{}()]*>)?\s*\([^;{}]*\)\s*[^;{}(]*$/;

/** Last line of a block indented deeper than `indent`. */
function blockEnd(lines: string[], from: number, indent: number): number {
  let last = from - 1;
  for (let i = from; i < lines.length; i++) {
    if (isBlank(lines[i])) {
      continue;
    }
    if (indentWidth(lines[i]) > indent) {
      last = i;
    } else {
      break;
    }
  }
  return last;
}

function pythonMethods(lines: string[]): MethodNode[] {
  const out: MethodNode[] = [];
  // Track open class blocks so `container` is filled in like the semantic path.
  const classes: { name: string; indent: number }[] = [];

  for (let i = 0; i < lines.length; i++) {
    if (isBlank(lines[i])) {
      continue;
    }
    const here = indentWidth(lines[i]);
    while (classes.length && here <= classes[classes.length - 1].indent) {
      classes.pop();
    }

    const cm = lines[i].match(PY_CLASS);
    if (cm) {
      classes.push({ name: cm[2], indent: here });
      continue;
    }

    const dm = lines[i].match(PY_DEF);
    if (!dm) {
      continue;
    }

    const sigEnd = signatureEnd(lines, i);
    if (sigEnd === -1) {
      continue;
    }
    const end = blockEnd(lines, sigEnd + 1, here);
    if (end <= sigEnd) {
      continue; // one-line def: nothing to fold
    }

    const container = classes.length
      ? classes[classes.length - 1].name
      : undefined;
    const info = docInfoFor("python", lines, { start: i, end }, i);
    out.push({
      id: methodId(dm[2], container, i),
      name: dm[2],
      container,
      range: { start: i, end },
      selectionLine: i,
      foldStart: info.foldStart,
      doc: info.doc,
      origin: "textual",
    });
  }
  return out;
}

function braceMethods(text: string, lines: string[]): MethodNode[] {
  return parseBrace(text).map((spec) => {
    // The name sits on the brace line, or just above it for wrapped signatures.
    let name = "anonymous";
    for (let i = spec.start; i >= Math.max(0, spec.start - 3); i--) {
      const head = lines[i].split("{")[0];
      const m = head.match(BRACE_NAME);
      if (m) {
        name = m[1];
        break;
      }
    }
    const info = docInfoFor("brace", lines, spec, spec.start);
    return {
      id: methodId(name, undefined, spec.start),
      name,
      range: { start: spec.start, end: spec.end },
      selectionLine: spec.start,
      foldStart: info.foldStart,
      doc: info.doc,
      origin: "textual" as const,
    };
  });
}

/**
 * Build methods without any language-server help. Used when no symbol provider
 * answers for the document — a file opened with no language extension
 * installed, or a server that has not finished starting.
 */
export function methodsFromText(
  family: LanguageFamily,
  text: string
): MethodNode[] {
  const lines = text.split(/\r\n|\r|\n/);
  if (family === "python") {
    return pythonMethods(lines);
  }
  if (family === "brace") {
    return braceMethods(text, lines);
  }
  return [];
}
