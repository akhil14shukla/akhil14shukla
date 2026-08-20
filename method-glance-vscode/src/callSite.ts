import { cleanCodeLines } from "./shape";
import { LanguageFamily } from "./types";

export interface SiteContext {
  /** Inside an if/elif/else/try/except — may not run. */
  conditional: boolean;
  /** Inside a for/while — may run more than once. */
  repeated: boolean;
}

const PY_COND = /^\s*(if|elif|else|try|except|finally|with|match|case)\b/;
const PY_LOOP = /^\s*(for|while)\b/;
const BR_COND = /^\s*\}?\s*(if|else|try|catch|finally|switch|case)\b/;
const BR_LOOP = /^\s*\}?\s*(for|while|do)\b/;

/**
 * Decide whether a call site runs unconditionally.
 *
 * Python is answered by indentation: walk upwards to find the enclosing blocks
 * and read the keyword that opened each one. Brace languages have no such
 * signal at the line level, so brace depth relative to the method body is used
 * instead — coarser, and it can miss a block opened on the same line.
 *
 * Both are read from literal-stripped code, so a keyword inside a string cannot
 * invent a branch.
 */
export function siteContext(
  lines: string[],
  bodyStart: number,
  bodyEnd: number,
  siteLine: number,
  family: LanguageFamily
): SiteContext {
  const out: SiteContext = { conditional: false, repeated: false };
  if (siteLine < 0 || siteLine >= lines.length) {
    return out;
  }

  const slice = lines.slice(bodyStart, bodyEnd + 1);
  const clean = cleanCodeLines(slice, family);
  const rel = siteLine - bodyStart;
  if (rel < 0 || rel >= clean.length) {
    return out;
  }

  if (family === "python") {
    const indentOf = (l: string) => l.length - l.replace(/^[ \t]+/, "").length;
    let indent = indentOf(clean[rel]);
    if (!clean[rel].trim()) {
      return out;
    }
    // Walk up through each enclosing block header.
    for (let i = rel - 1; i >= 0 && indent > 0; i--) {
      const line = clean[i];
      if (!line.trim()) {
        continue;
      }
      const ind = indentOf(line);
      if (ind < indent) {
        if (PY_LOOP.test(line)) {
          out.repeated = true;
        } else if (PY_COND.test(line)) {
          out.conditional = true;
        }
        indent = ind;
      }
    }
    return out;
  }

  // Brace languages: any block keyword still open above the site.
  let depth = 0;
  for (let i = rel; i >= 0; i--) {
    const line = clean[i];
    for (let c = line.length - 1; c >= 0; c--) {
      if (line[c] === "}") depth++;
      else if (line[c] === "{") depth--;
    }
    if (depth < 0) {
      if (BR_LOOP.test(line)) {
        out.repeated = true;
      } else if (BR_COND.test(line)) {
        out.conditional = true;
      }
      depth = 0;
    }
  }
  return out;
}
