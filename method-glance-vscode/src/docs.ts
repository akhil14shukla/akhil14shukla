import { LineRange } from "./model";
import {
  codePortion,
  docstringEnd,
  isBlank,
  signatureEnd,
} from "./pythonParser";
import { LanguageFamily } from "./types";

export interface DocInfo {
  /** Last line that stays visible when the method is folded. */
  foldStart: number;
  /** Doc text, when one was found. */
  doc?: string;
}

/** Strip the surrounding triple quotes and common indentation from a Python
 * docstring so it can be rendered in a hover. */
function cleanPyDoc(lines: string[]): string {
  const joined = lines.join("\n").trim();
  const m = joined.match(/^[rRbBuUfF]{0,2}("""|''')/);
  if (!m) {
    return joined;
  }
  const q = m[1];
  let body = joined.slice(joined.indexOf(q) + 3);
  if (body.endsWith(q)) {
    body = body.slice(0, -3);
  }
  return dedent(body).trim();
}

/** Remove the smallest indentation shared by all non-blank lines. */
function dedent(text: string): string {
  const rows = text.split("\n");
  let min = Infinity;
  for (const r of rows.slice(1)) {
    if (r.trim().length === 0) {
      continue;
    }
    const w = r.length - r.replace(/^[ \t]+/, "").length;
    min = Math.min(min, w);
  }
  if (!isFinite(min) || min === 0) {
    return text;
  }
  return rows
    .map((r, i) => (i === 0 ? r : r.slice(min)))
    .join("\n");
}

/**
 * Python: the fold begins at the docstring's last line when documented, so both
 * the signature and the docstring survive folding.
 *
 * `defLine` is the line carrying the `def` keyword — pass the symbol's
 * selectionRange line rather than its range start, since the latter includes
 * decorators.
 */
function pythonDoc(lines: string[], defLine: number): DocInfo {
  const sigEnd = signatureEnd(lines, defLine);
  if (sigEnd === -1) {
    return { foldStart: defLine };
  }

  let firstBody = sigEnd + 1;
  while (firstBody < lines.length && isBlank(lines[firstBody])) {
    firstBody++;
  }
  if (firstBody >= lines.length) {
    return { foldStart: sigEnd };
  }

  const docEnd = docstringEnd(lines, firstBody);
  if (docEnd === -1) {
    return { foldStart: sigEnd };
  }
  return {
    foldStart: docEnd,
    doc: cleanPyDoc(lines.slice(firstBody, docEnd + 1)),
  };
}

/** Strip comment markers from a `/** ... *\/` or `///` run. */
function cleanBraceDoc(lines: string[]): string {
  const out = lines
    .map((l) =>
      l
        .replace(/^\s*\/\*\*?/, "")
        .replace(/\*\/\s*$/, "")
        .replace(/^\s*\*\s?/, "")
        .replace(/^\s*\/\/\/?\s?/, "")
    )
    .join("\n");
  return dedent(out).trim();
}

/**
 * Brace languages: doc comments sit *above* the signature, so folding the body
 * already keeps them visible. The fold begins on the line holding the opening
 * brace; the doc is read from the comment run immediately above the symbol.
 */
function braceDoc(lines: string[], range: LineRange, nameLine: number): DocInfo {
  let foldStart = nameLine;
  for (let i = nameLine; i <= Math.min(range.end, lines.length - 1); i++) {
    if (codePortion(lines[i]).includes("{")) {
      foldStart = i;
      break;
    }
  }

  // Walk up from the signature collecting a contiguous comment run. Anchoring
  // to the name line rather than `range.start` matters because some language
  // servers fold the doc comment into the symbol's range and others do not.
  const collected: string[] = [];
  let i = nameLine - 1;
  while (i >= 0 && isBlank(lines[i])) {
    i--;
  }
  if (i >= 0 && /\*\/\s*$/.test(lines[i])) {
    while (i >= 0) {
      collected.unshift(lines[i]);
      if (/^\s*\/\*/.test(lines[i])) {
        break;
      }
      i--;
    }
  } else {
    while (i >= 0 && /^\s*\/\//.test(lines[i])) {
      collected.unshift(lines[i]);
      i--;
    }
  }

  const doc = collected.length ? cleanBraceDoc(collected) : undefined;
  return { foldStart, doc: doc || undefined };
}

/**
 * Locate a method's fold point and doc text within its symbol range. This is
 * the piece no language-server API provides: `DocumentSymbol.range` covers
 * signature, docstring and body as one span, with no marker for where the
 * documentation ends.
 */
export function docInfoFor(
  family: LanguageFamily,
  lines: string[],
  range: LineRange,
  nameLine: number
): DocInfo {
  if (family === "python") {
    return pythonDoc(lines, nameLine);
  }
  if (family === "brace") {
    return braceDoc(lines, range, nameLine);
  }
  return { foldStart: nameLine };
}
