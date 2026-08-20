/**
 * The language-neutral model every view renders from.
 *
 * Nothing here imports `vscode`. The semantic layer fills these in from the
 * language server; the text parsers fill the same shapes in as a fallback. Views
 * (folding, hover, and the diagram panel) only ever see this model, so they do
 * not care which source produced it.
 */

import { MethodShape } from "./shape";

/** Inclusive, 0-based line span. */
export interface LineRange {
  start: number;
  end: number;
}

/** Where a method's facts came from — surfaced in the UI so a degraded view is
 * never silently presented as an exact one. */
export type Provenance = "semantic" | "textual";

/** A function, method, or constructor. */
export interface MethodNode {
  /** Stable id: `container.name@startLine`, unique within a document. */
  id: string;
  name: string;
  /** Enclosing class/interface name, when the symbol is nested in one. */
  container?: string;
  /** Signature detail from the language server, e.g. `(self, cart) -> Decimal`. */
  detail?: string;
  /** Whole symbol: signature through last body line. */
  range: LineRange;
  /** Line holding the symbol's name. */
  selectionLine: number;
  /** Last line that stays visible when folded — the docstring's end, or the
   * signature's end when undocumented. */
  foldStart: number;
  /** Raw docstring / doc comment text, when one was found. */
  doc?: string;
  origin: Provenance;
  /** Structural summary of the body — see `src/shape.ts`. */
  shape?: MethodShape;
}

/** A resolved call from one symbol to another. */
export interface CallEdge {
  /** MethodNode id of the caller. */
  from: string;
  /** MethodNode id of the callee, when it lives in this document. */
  to?: string;
  /** Callee name, always present — external callees have no local node. */
  toName: string;
  /** Set when the callee is defined outside the current document. */
  externalUri?: string;
  /** Lines within the caller where the call appears. */
  atLines: number[];
}

/** An inheritance relationship between types in the document. */
export interface TypeEdge {
  /** Subtype name. */
  from: string;
  /** Supertype name. */
  to: string;
  externalUri?: string;
}

/** Everything known about one document. */
export interface GlanceModel {
  uri: string;
  languageId: string;
  /** Document version this model was built from; used to invalidate caches. */
  version: number;
  methods: MethodNode[];
  /** Populated lazily — call hierarchy is one request per method. */
  calls: CallEdge[];
  types: TypeEdge[];
  /** True when methods came from the language server rather than the parsers. */
  semantic: boolean;
}

export function methodId(
  name: string,
  container: string | undefined,
  startLine: number
): string {
  return `${container ? container + "." : ""}${name}@${startLine}`;
}

/** Find the method whose range encloses a line. Innermost wins, so a nested
 * function is preferred over the function containing it. */
export function methodAtLine(
  methods: MethodNode[],
  line: number
): MethodNode | undefined {
  let best: MethodNode | undefined;
  for (const m of methods) {
    if (line >= m.range.start && line <= m.range.end) {
      if (!best || m.range.start > best.range.start) {
        best = m;
      }
    }
  }
  return best;
}
