import * as vscode from "vscode";
import { familyFor } from "./languages";
import {
  CallEdge,
  GlanceModel,
  MethodNode,
  TypeEdge,
  methodAtLine,
} from "./model";
import { methodsFromSymbols, SymbolLike } from "./symbols";
import { annotateShapes } from "./shape";
import { methodsFromText } from "./textSource";

/**
 * Command ids for VS Code's built-in provider bridges. These are documented
 * commands rather than typed API, so each call is defensive: a language
 * extension that does not implement the underlying provider makes the command
 * reject or return undefined, and we degrade instead of failing.
 */
const CMD = {
  symbols: "vscode.executeDocumentSymbolProvider",
  prepareCall: "vscode.prepareCallHierarchy",
  outgoing: "vscode.provideOutgoingCalls",
  incoming: "vscode.provideIncomingCalls",
  prepareType: "vscode.prepareTypeHierarchy",
  supertypes: "vscode.provideSupertypes",
} as const;

async function safe<T>(
  command: string,
  ...args: unknown[]
): Promise<T | undefined> {
  try {
    return await vscode.commands.executeCommand<T>(command, ...args);
  } catch {
    // Provider missing or the server is still starting.
    return undefined;
  }
}

/** Race a provider call against a deadline so a cold language server never
 * blocks folding indefinitely. */
function withTimeout<T>(p: Thenable<T>, ms: number): Promise<T | undefined> {
  return Promise.race([
    Promise.resolve(p),
    new Promise<undefined>((res) => setTimeout(() => res(undefined), ms)),
  ]);
}

const SYMBOL_TIMEOUT_MS = 1500;

/** Cache keyed by document uri, invalidated on version change. */
const cache = new Map<string, GlanceModel>();

/**
 * Build the structural model for a document: methods, their fold points and
 * docs. Prefers the language server's symbol tree and falls back to the text
 * parsers when it is unavailable.
 *
 * Call edges are *not* filled in here — they cost one request per method, so
 * they are resolved lazily by `resolveCalls`.
 */
export async function getModel(
  doc: vscode.TextDocument
): Promise<GlanceModel> {
  const key = doc.uri.toString();
  const hit = cache.get(key);
  if (hit && hit.version === doc.version) {
    return hit;
  }

  const family = familyFor(doc.languageId);
  const text = doc.getText();
  const lines = text.split(/\r\n|\r|\n/);

  let methods: MethodNode[] = [];
  let semantic = false;

  const symbols = await withTimeout(
    safe<SymbolLike[]>(CMD.symbols, doc.uri),
    SYMBOL_TIMEOUT_MS
  );

  if (symbols && symbols.length) {
    methods = methodsFromSymbols(symbols, lines, family);
    semantic = methods.length > 0;
  }
  if (!methods.length) {
    methods = methodsFromText(family, text);
  }

  // Cheap, text-level, and independent of the language server — so the logic
  // skeleton is available even when nothing else is.
  annotateShapes(methods, lines, family);

  const model: GlanceModel = {
    uri: key,
    languageId: doc.languageId,
    version: doc.version,
    methods,
    calls: [],
    types: [],
    semantic,
  };
  cache.set(key, model);
  return model;
}

interface HierarchyItem {
  name: string;
  uri: vscode.Uri;
  selectionRange: vscode.Range;
  range: vscode.Range;
}

interface OutgoingCall {
  to: HierarchyItem;
  fromRanges: vscode.Range[];
}

/**
 * Resolve outgoing calls for one method through the call hierarchy provider —
 * the type-resolved answer to "what does this call", covering inheritance,
 * aliases and imports that text matching cannot see.
 *
 * Results are merged into the cached model so repeat hovers are free.
 */
export async function resolveCalls(
  doc: vscode.TextDocument,
  method: MethodNode
): Promise<CallEdge[]> {
  const model = await getModel(doc);
  const existing = model.calls.filter((c) => c.from === method.id);
  if (existing.length) {
    return existing;
  }

  const pos = new vscode.Position(
    method.selectionLine,
    Math.max(0, doc.lineAt(method.selectionLine).text.indexOf(method.name))
  );

  const items = await safe<HierarchyItem[]>(CMD.prepareCall, doc.uri, pos);
  if (!items || !items.length) {
    return [];
  }

  const outgoing = await safe<OutgoingCall[]>(CMD.outgoing, items[0]);
  if (!outgoing) {
    return [];
  }

  const edges: CallEdge[] = [];
  for (const call of outgoing) {
    const sameFile = call.to.uri.toString() === model.uri;
    const target = sameFile
      ? methodAtLine(model.methods, call.to.selectionRange.start.line)
      : undefined;

    edges.push({
      from: method.id,
      to: target?.id,
      toName: call.to.name,
      externalUri: sameFile ? undefined : call.to.uri.toString(),
      atLines: call.fromRanges.map((r) => r.start.line),
    });
  }

  model.calls.push(...edges);
  return edges;
}

/** Resolve callers of a method — the reverse edge, for "who depends on this". */
export async function resolveCallers(
  doc: vscode.TextDocument,
  method: MethodNode
): Promise<{ name: string; uri: string; line: number }[]> {
  const pos = new vscode.Position(
    method.selectionLine,
    Math.max(0, doc.lineAt(method.selectionLine).text.indexOf(method.name))
  );
  const items = await safe<HierarchyItem[]>(CMD.prepareCall, doc.uri, pos);
  if (!items || !items.length) {
    return [];
  }
  const incoming = await safe<{ from: HierarchyItem }[]>(
    CMD.incoming,
    items[0]
  );
  if (!incoming) {
    return [];
  }
  return incoming.map((c) => ({
    name: c.from.name,
    uri: c.from.uri.toString(),
    line: c.from.selectionRange.start.line,
  }));
}

/** Resolve supertypes for the classes in a document, for inheritance diagrams. */
export async function resolveTypes(
  doc: vscode.TextDocument,
  typeLines: { name: string; line: number }[]
): Promise<TypeEdge[]> {
  const edges: TypeEdge[] = [];
  for (const t of typeLines) {
    const pos = new vscode.Position(
      t.line,
      Math.max(0, doc.lineAt(t.line).text.indexOf(t.name))
    );
    const items = await safe<HierarchyItem[]>(CMD.prepareType, doc.uri, pos);
    if (!items || !items.length) {
      continue;
    }
    const supers = await safe<HierarchyItem[]>(CMD.supertypes, items[0]);
    if (!supers) {
      continue;
    }
    for (const s of supers) {
      edges.push({
        from: t.name,
        to: s.name,
        externalUri:
          s.uri.toString() === doc.uri.toString()
            ? undefined
            : s.uri.toString(),
      });
    }
  }
  return edges;
}

export function invalidate(uri: vscode.Uri): void {
  cache.delete(uri.toString());
}
