import { docInfoFor } from "./docs";
import { MethodNode, methodId } from "./model";
import { LanguageFamily } from "./types";

/**
 * Structural stand-in for `vscode.DocumentSymbol`. Declaring the shape rather
 * than importing it keeps this module testable under plain Node — the real
 * DocumentSymbol satisfies it.
 */
export interface SymbolLike {
  name: string;
  kind: number;
  detail?: string;
  range: { start: { line: number }; end: { line: number } };
  selectionRange: { start: { line: number } };
  children?: SymbolLike[];
}

/** `vscode.SymbolKind` members we care about (values are stable across the API). */
export const KIND = {
  Class: 4,
  Method: 5,
  Constructor: 8,
  Interface: 10,
  Function: 11,
  Struct: 22,
} as const;

const CALLABLE = new Set<number>([
  KIND.Method,
  KIND.Constructor,
  KIND.Function,
]);
const CONTAINER = new Set<number>([
  KIND.Class,
  KIND.Interface,
  KIND.Struct,
]);

/**
 * Flatten a document's symbol tree into the methods we render, resolving each
 * one's fold point and doc text against the source lines.
 *
 * Nested callables are kept — an inner helper function is foldable in its own
 * right — and the enclosing class name is carried down as `container`.
 */
export function methodsFromSymbols(
  symbols: SymbolLike[],
  lines: string[],
  family: LanguageFamily
): MethodNode[] {
  const out: MethodNode[] = [];

  function walk(nodes: SymbolLike[], container?: string): void {
    for (const s of nodes) {
      const range = { start: s.range.start.line, end: s.range.end.line };
      const nameLine = s.selectionRange.start.line;

      if (CALLABLE.has(s.kind)) {
        const info = docInfoFor(family, lines, range, nameLine);
        out.push({
          id: methodId(s.name, container, range.start),
          name: s.name,
          container,
          detail: s.detail || undefined,
          range,
          selectionLine: nameLine,
          foldStart: info.foldStart,
          doc: info.doc,
          origin: "semantic",
        });
      }

      if (s.children && s.children.length) {
        // A callable's children are nested helpers, still scoped to the class.
        walk(s.children, CONTAINER.has(s.kind) ? s.name : container);
      }
    }
  }

  walk(symbols);
  out.sort((a, b) => a.range.start - b.range.start);
  return out;
}

/** Collect class/interface/struct names with their ranges, for type diagrams. */
export function typesFromSymbols(
  symbols: SymbolLike[]
): { name: string; line: number }[] {
  const out: { name: string; line: number }[] = [];
  function walk(nodes: SymbolLike[]): void {
    for (const s of nodes) {
      if (CONTAINER.has(s.kind)) {
        out.push({ name: s.name, line: s.selectionRange.start.line });
      }
      if (s.children && s.children.length) {
        walk(s.children);
      }
    }
  }
  walk(symbols);
  return out;
}
