import { FoldSpec } from "./types";

const DEF_RE = /^(\s*)(async\s+)?def\s/;

/** Leading-whitespace width, treating a tab as one column (indent only needs
 * to be compared for relative depth, and Python forbids mixing anyway). */
export function indentWidth(line: string): number {
  const m = line.match(/^[ \t]*/);
  return m ? m[0].length : 0;
}

export function isBlank(line: string): boolean {
  return line.trim().length === 0;
}

/**
 * Strip a trailing `# comment` that sits outside any string, so we can find the
 * `:` that ends a `def` signature. This is a light scanner — good enough for
 * signatures, which rarely contain `#` inside strings, but it does respect
 * quotes it can see on the line.
 */
export function codePortion(line: string): string {
  let inStr: string | null = null;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inStr) {
      if (ch === "\\") {
        i++;
        continue;
      }
      if (ch === inStr) {
        inStr = null;
      }
    } else if (ch === '"' || ch === "'") {
      inStr = ch;
    } else if (ch === "#") {
      return line.slice(0, i);
    }
  }
  return line;
}

/** Net bracket depth contributed by a line's code, ignoring brackets in strings. */
function bracketDelta(line: string): number {
  let inStr: string | null = null;
  let depth = 0;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inStr) {
      if (ch === "\\") {
        i++;
        continue;
      }
      if (ch === inStr) {
        inStr = null;
      }
      continue;
    }
    if (ch === '"' || ch === "'") {
      inStr = ch;
    } else if (ch === "#") {
      break;
    } else if (ch === "(" || ch === "[" || ch === "{") {
      depth++;
    } else if (ch === ")" || ch === "]" || ch === "}") {
      depth--;
    }
  }
  return depth;
}

/**
 * Find the line index where a `def` signature ends (the line whose code ends
 * with `:` at bracket depth 0). Returns the signature's last line index, or -1
 * if the signature never closes within the document.
 */
export function signatureEnd(lines: string[], defLine: number): number {
  let depth = 0;
  for (let i = defLine; i < lines.length; i++) {
    depth += bracketDelta(lines[i]);
    if (depth <= 0) {
      const code = codePortion(lines[i]).replace(/\s+$/, "");
      if (code.endsWith(":")) {
        return i;
      }
    }
  }
  return -1;
}

/**
 * Given the first non-blank body line, if it opens a docstring return the index
 * of the line on which that docstring closes. Otherwise return -1.
 */
export function docstringEnd(lines: string[], firstBodyLine: number): number {
  const stripped = lines[firstBodyLine].trim();
  // Optional string prefixes: r, b, u, f and combinations, then a triple quote.
  const m = stripped.match(/^[rRbBuUfF]{0,2}("""|''')/);
  if (!m) {
    return -1;
  }
  const quote = m[1];
  const afterOpen = stripped.slice(stripped.indexOf(quote) + 3);
  // Single-line docstring: closing quote on the same line.
  if (afterOpen.includes(quote)) {
    return firstBodyLine;
  }
  for (let i = firstBodyLine + 1; i < lines.length; i++) {
    if (lines[i].includes(quote)) {
      return i;
    }
  }
  // Unterminated docstring — treat as ending at EOF.
  return lines.length - 1;
}

/** Last non-blank line of a block whose lines are indented deeper than `defIndent`. */
function bodyEnd(lines: string[], bodyStart: number, defIndent: number): number {
  let last = -1;
  for (let i = bodyStart; i < lines.length; i++) {
    if (isBlank(lines[i])) {
      continue;
    }
    if (indentWidth(lines[i]) > defIndent) {
      last = i;
    } else {
      break;
    }
  }
  return last;
}

/**
 * Compute glance fold ranges for a Python source. For every `def`/`async def`
 * we hide the body but keep the signature and (if present) the docstring
 * visible.
 */
export function parsePython(text: string): FoldSpec[] {
  const lines = text.split(/\r\n|\r|\n/);
  const specs: FoldSpec[] = [];

  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(DEF_RE);
    if (!m) {
      continue;
    }
    const defIndent = indentWidth(lines[i]);
    const sigEnd = signatureEnd(lines, i);
    if (sigEnd === -1) {
      continue;
    }

    // First non-blank line after the signature.
    let firstBody = sigEnd + 1;
    while (firstBody < lines.length && isBlank(lines[firstBody])) {
      firstBody++;
    }
    if (firstBody >= lines.length) {
      continue;
    }
    // A body must be indented deeper than the def (guards against one-line
    // `def f(): return 1`, which has no separate body to fold).
    if (indentWidth(lines[firstBody]) <= defIndent) {
      continue;
    }

    const end = bodyEnd(lines, firstBody, defIndent);
    if (end === -1) {
      continue;
    }

    const docEnd = docstringEnd(lines, firstBody);
    // Fold starts at the last docstring line (kept visible) when documented,
    // otherwise at the signature's last line.
    const start = docEnd !== -1 ? docEnd : sigEnd;

    if (end > start) {
      specs.push({ start, end });
    }
    // Continue scanning; nested defs are picked up by the outer loop.
  }

  return specs;
}
