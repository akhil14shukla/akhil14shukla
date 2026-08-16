import { FoldSpec } from "./types";

/**
 * Keywords that introduce a `(...) { }` block which is NOT a function/method.
 * When the identifier directly before the parameter list is one of these, the
 * block is control flow and we leave it expanded.
 */
const CONTROL_KEYWORDS = new Set<string>([
  "if",
  "else",
  "for",
  "while",
  "switch",
  "do",
  "try",
  "catch",
  "finally",
  "with",
  "using",
  "lock",
  "synchronized",
  "fixed",
  "return",
  "await",
  "yield",
  "in",
  "of",
  "new",
]);

interface OpenBrace {
  line: number;
  isFunc: boolean;
}

/**
 * Decide whether the text preceding an opening `{` reads as a function or
 * method signature (as opposed to a class body, control-flow block, or object
 * literal). Best-effort and language-agnostic across the C family.
 */
function looksLikeFunctionHeader(header: string): boolean {
  const h = header.replace(/\s+/g, " ").trim();
  if (h.length === 0) {
    return false;
  }
  // Arrow function: `... => {`
  if (/=>\s*$/.test(h)) {
    return true;
  }
  // A parameter list at the end, optionally followed by a return-type
  // annotation (`: Type`), a `throws`/`where` clause, or `const`/`noexcept`.
  const m = h.match(
    /([A-Za-z_$][\w$]*)\s*(?:<[^;{}()]*>)?\s*\([^;{}]*\)\s*(?::[^;{}]*|throws[^;{}]*|where[^;{}]*|const|noexcept|override|final|mutable|\s)*$/
  );
  if (!m) {
    return false;
  }
  const callee = m[1];
  return !CONTROL_KEYWORDS.has(callee);
}

/**
 * Compute glance fold ranges for a brace-delimited language. Every function or
 * method body `{ … }` is folded; leading doc comments and the signature sit
 * above the `{` and remain visible.
 */
export function parseBrace(text: string): FoldSpec[] {
  const specs: FoldSpec[] = [];
  const stack: OpenBrace[] = [];
  // Text of the current statement/header since the last `;`, `{`, or `}`.
  let segment = "";

  let line = 0;
  // Scanner modes for the parts of the text where braces must be ignored.
  type Mode = "code" | "line" | "block" | "sq" | "dq" | "tpl";
  let mode: Mode = "code";
  // `${ }` nesting depth while inside a template literal.
  let exprDepth = 0;

  const n = text.length;
  for (let i = 0; i < n; i++) {
    const ch = text[i];
    const next = i + 1 < n ? text[i + 1] : "";

    if (ch === "\n") {
      line++;
      if (mode === "line") {
        mode = "code";
      }
      if (mode === "code") {
        segment += " ";
      }
      continue;
    }

    switch (mode) {
      case "line":
        break;
      case "block":
        if (ch === "*" && next === "/") {
          mode = "code";
          i++;
        }
        break;
      case "sq":
        if (ch === "\\") {
          i++;
        } else if (ch === "'") {
          mode = "code";
        }
        break;
      case "dq":
        if (ch === "\\") {
          i++;
        } else if (ch === '"') {
          mode = "code";
        }
        break;
      case "tpl":
        if (ch === "\\") {
          i++;
        } else if (exprDepth === 0 && ch === "`") {
          mode = "code";
        } else if (ch === "$" && next === "{") {
          exprDepth++;
          i++;
        } else if (exprDepth > 0 && ch === "{") {
          exprDepth++;
        } else if (exprDepth > 0 && ch === "}") {
          exprDepth--;
        }
        break;
      case "code": {
        if (ch === "/" && next === "/") {
          mode = "line";
          i++;
        } else if (ch === "/" && next === "*") {
          mode = "block";
          i++;
        } else if (ch === '"') {
          mode = "dq";
        } else if (ch === "'") {
          mode = "sq";
        } else if (ch === "`") {
          mode = "tpl";
        } else if (ch === "{") {
          const isFunc = looksLikeFunctionHeader(segment);
          stack.push({ line, isFunc });
          segment = "";
        } else if (ch === "}") {
          const open = stack.pop();
          segment = "";
          if (open && open.isFunc && line > open.line) {
            specs.push({ start: open.line, end: line });
          }
        } else if (ch === ";") {
          segment = "";
        } else {
          segment += ch;
        }
        break;
      }
    }
  }

  specs.sort((a, b) => a.start - b.start);
  return specs;
}
