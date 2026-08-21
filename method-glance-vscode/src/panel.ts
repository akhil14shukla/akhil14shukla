import * as vscode from "vscode";
import { familyFor } from "./languages";
import { GraphEdge, GraphNode, layout } from "./layout";
import { toMermaid, toMermaidClasses, toMermaidSequence } from "./mermaid";
import { siteContext } from "./callSite";
import { ClassBox, InheritEdge, classScene, visibilityOf } from "./classLayout";
import { analyzeFlow } from "./dataflow";
import { flowScene } from "./flowLayout";
import { ImportedModule, moduleForUri, parseImports } from "./modules";
import { moduleScene } from "./moduleLayout";
import { methodAtLine } from "./model";
import { graphScene, Scene, SceneKind } from "./scene";
import { SeqCall, SeqParticipant, sequenceScene } from "./sequenceLayout";
import { getModel, resolveCalls, resolveTypes } from "./semantics";
import { attributesIn, shapeSummary } from "./shape";
import { typesFromSymbols, SymbolLike } from "./symbols";

/** Cap on call-hierarchy requests for one map. Each method costs one round
 * trip, so a very large file is summarised rather than stalling the editor. */
const RESOLVE_BUDGET = 60;

interface RawGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** Node id -> line to reveal when clicked. */
  lines: Record<string, number>;
  truncated: boolean;
  semantic: boolean;
  file: string;
  /** Call sites annotated with whether they actually run unconditionally. */
  seqCalls: SeqCall[];
  participants: SeqParticipant[];
  /** Ids of methods that read as entry points. */
  entries: string[];
  classes: ClassBox[];
  inherits: InheritEdge[];
  modules: ImportedModule[];
}

/** Highest diagnostic severity overlapping a line range: 2 error, 1 warning. */
function severityFor(
  diags: vscode.Diagnostic[],
  start: number,
  end: number
): number {
  let worst = 0;
  for (const d of diags) {
    if (d.range.end.line < start || d.range.start.line > end) {
      continue;
    }
    if (d.severity === vscode.DiagnosticSeverity.Error) {
      return 2;
    }
    if (d.severity === vscode.DiagnosticSeverity.Warning) {
      worst = Math.max(worst, 1);
    }
  }
  return worst;
}

async function buildGraph(doc: vscode.TextDocument): Promise<RawGraph> {
  const model = await getModel(doc);
  const diags = vscode.languages.getDiagnostics(doc.uri);

  const nodes: GraphNode[] = [];
  const lines: Record<string, number> = {};
  for (const m of model.methods) {
    nodes.push({
      id: m.id,
      label: m.name,
      group: m.container,
      lines: m.range.end - m.range.start + 1,
      severity: severityFor(diags, m.range.start, m.range.end),
      entry: m.shape?.entry,
      complexity: m.shape?.complexity,
      effects: m.shape?.effects,
      shape: m.shape ? shapeSummary(m.shape) : undefined,
    });
    lines[m.id] = m.selectionLine;
  }

  const family = familyFor(doc.languageId);
  const docLines = doc.getText().split(/\r\n|\r|\n/);
  const seqCalls: SeqCall[] = [];
  const participants: SeqParticipant[] = model.methods.map((m) => ({
    id: m.id,
    label: m.name,
    group: m.container,
    clickLine: m.selectionLine,
  }));
  const entries = model.methods.filter((m) => m.shape?.entry).map((m) => m.id);

  const budget = model.methods.slice(0, RESOLVE_BUDGET);
  const edges: GraphEdge[] = [];
  const externals = new Map<string, GraphNode>();

  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Window, title: "Method Glance: mapping calls" },
    async () => {
      for (const m of budget) {
        const resolved = await resolveCalls(doc, m);
        for (const c of resolved) {
          if (c.to) {
            edges.push({ from: m.id, to: c.to, count: c.atLines.length });
            for (const line of c.atLines) {
              const ctx = siteContext(
                docLines,
                m.range.start,
                m.range.end,
                line,
                family
              );
              seqCalls.push({
                from: m.id,
                to: c.to,
                line,
                conditional: ctx.conditional || undefined,
                repeated: ctx.repeated || undefined,
              });
            }
          } else {
            // Keep external callees as their own nodes; the view hides them by
            // default so library noise does not drown the file's own shape.
            const id = `ext:${c.toName}`;
            if (!externals.has(id)) {
              externals.set(id, { id, label: c.toName, external: true });
            }
            edges.push({
              from: m.id,
              to: id,
              count: c.atLines.length,
              cross: true,
            });
          }
        }
      }
    }
  );

  const { classes, inherits } = await buildClasses(doc);

  // Imports as written, then weighted by the cross-file calls already resolved
  // during the graph build — no extra language-server requests.
  const modules = parseImports(doc.getText(), family);
  for (const m of model.methods) {
    for (const c of model.calls.filter((e) => e.from === m.id)) {
      if (!c.externalUri) {
        continue;
      }
      const name = moduleForUri(c.externalUri, modules);
      const hit = modules.find((x) => x.name === name);
      if (hit) {
        hit.calls += c.atLines.length;
      }
    }
  }

  nodes.push(...externals.values());

  return {
    nodes,
    edges,
    lines,
    truncated: model.methods.length > RESOLVE_BUDGET,
    semantic: model.semantic,
    file: doc.uri.path.split("/").pop() || "",
    seqCalls,
    participants,
    entries,
    classes,
    inherits,
    modules,
  };
}

/**
 * Classes with their members. Methods come from the model; attributes are
 * harvested from `self.`/`this.` assignments, which no symbol provider reports
 * reliably across languages.
 */
async function buildClasses(
  doc: vscode.TextDocument
): Promise<{ classes: ClassBox[]; inherits: InheritEdge[] }> {
  const model = await getModel(doc);
  const family = familyFor(doc.languageId);
  const lines = doc.getText().split(/\r\n|\r|\n/);

  const symbols = await vscode.commands
    .executeCommand<SymbolLike[]>(
      "vscode.executeDocumentSymbolProvider",
      doc.uri
    )
    .then(
      (s) => s || [],
      () => [] as SymbolLike[]
    );

  const declared = typesFromSymbols(symbols);
  const byName = new Map<string, ClassBox>();

  for (const t of declared) {
    byName.set(t.name, {
      name: t.name,
      clickLine: t.line,
      members: [],
    });
  }

  // Methods, grouped by the container the model already recorded.
  for (const m of model.methods) {
    if (!m.container) {
      continue;
    }
    let box = byName.get(m.container);
    if (!box) {
      box = { name: m.container, members: [] };
      byName.set(m.container, box);
    }
    box.members.push({
      name: m.name,
      visibility: visibilityOf(m.name),
      kind: "method",
      clickLine: m.selectionLine,
      effects: m.shape?.effects,
    });
  }

  // Attributes assigned anywhere inside the class body.
  for (const t of declared) {
    const box = byName.get(t.name);
    if (!box) {
      continue;
    }
    const own = model.methods.filter((m) => m.container === t.name);
    const from = own.length ? Math.min(...own.map((m) => m.range.start)) : t.line;
    const to = own.length ? Math.max(...own.map((m) => m.range.end)) : t.line;
    for (const name of attributesIn(lines.slice(from, to + 1), family)) {
      box.members.unshift({
        name,
        visibility: visibilityOf(name),
        kind: "attribute",
      });
    }
  }

  const inherits: InheritEdge[] = [];
  const typeEdges = await resolveTypes(doc, declared);
  for (const e of typeEdges) {
    inherits.push({ from: e.from, to: e.to });
    if (!byName.has(e.to)) {
      // Supertype defined elsewhere: shown as an empty dashed box so the
      // hierarchy is not silently cut off at the file boundary.
      byName.set(e.to, { name: e.to, members: [], external: true });
    }
  }

  return { classes: [...byName.values()], inherits };
}

function nonce(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

/**
 * The Glance Map: the folded file drawn as a call graph. Layout runs in the
 * extension host so there is a single tested implementation; the webview owns
 * only rendering and interaction.
 */
export class GlanceMapPanel {
  private static current: GlanceMapPanel | undefined;

  private readonly panel: vscode.WebviewPanel;
  private readonly disposables: vscode.Disposable[] = [];
  private graph: RawGraph | undefined;
  private docUri: vscode.Uri | undefined;
  private showExternal = false;
  private lastWidth = 900;
  private view: SceneKind = "graph";
  /** Line the cursor sat on when the view was last built — the anchor for the
   * views that describe one method rather than the whole file. */
  private anchorLine = 0;
  /** Id of the method enclosing the cursor, if any. */
  private enclosingId: string | undefined;
  /** How far the sequence trace follows calls. */
  private depth = 4;

  static show(context: vscode.ExtensionContext, view?: SceneKind): void {
    const column = vscode.ViewColumn.Beside;
    if (GlanceMapPanel.current) {
      if (view) {
        GlanceMapPanel.current.view = view;
      }
      GlanceMapPanel.current.panel.reveal(column, true);
      void GlanceMapPanel.current.refresh();
      return;
    }
    const panel = vscode.window.createWebviewPanel(
      "methodGlance.map",
      "Glance Map",
      { viewColumn: column, preserveFocus: true },
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(context.extensionUri, "media")],
      }
    );
    GlanceMapPanel.current = new GlanceMapPanel(panel, context);
    if (view) {
      GlanceMapPanel.current.view = view;
      void GlanceMapPanel.current.refresh();
    }
  }

  /** Copy the diagram currently on screen, in Mermaid syntax. */
  static async copyCurrent(): Promise<boolean> {
    const panel = GlanceMapPanel.current;
    if (!panel || !panel.graph) {
      return false;
    }
    await vscode.env.clipboard.writeText(panel.mermaidForView());
    return true;
  }

  private constructor(
    panel: vscode.WebviewPanel,
    private readonly context: vscode.ExtensionContext
  ) {
    this.panel = panel;
    this.panel.webview.html = this.html();

    this.panel.onDidDispose(() => this.dispose(), null, this.disposables);

    this.panel.webview.onDidReceiveMessage(
      (msg) => void this.onMessage(msg),
      null,
      this.disposables
    );

    // Follow the active editor, and refresh when its content settles.
    vscode.window.onDidChangeActiveTextEditor(
      () => void this.refresh(),
      null,
      this.disposables
    );
    vscode.workspace.onDidSaveTextDocument(
      (doc) => {
        if (doc.uri.toString() === this.docUri?.toString()) {
          void this.refresh();
        }
      },
      null,
      this.disposables
    );

    void this.refresh();
  }

  private async onMessage(msg: {
    type: string;
    id?: string;
    width?: number;
    showExternal?: boolean;
    view?: SceneKind;
    depth?: number;
  }): Promise<void> {
    if (msg.type === "relayout") {
      this.lastWidth = msg.width ?? this.lastWidth;
      this.showExternal = msg.showExternal ?? this.showExternal;
      if (msg.depth !== undefined) {
        this.depth = msg.depth;
      }
      const nextView = msg.view ?? this.view;
      const changed = nextView !== this.view;
      this.view = nextView;
      if (changed) {
        // Other views need data the graph build does not gather.
        await this.refresh();
      } else {
        await this.post();
      }
      return;
    }

    if (msg.type === "reveal" && msg.id && this.docUri && this.graph) {
      const line = this.graph.lines[msg.id];
      if (line === undefined) {
        return;
      }
      const doc = await vscode.workspace.openTextDocument(this.docUri);
      const editor = await vscode.window.showTextDocument(doc, {
        viewColumn: vscode.ViewColumn.One,
        preserveFocus: false,
      });
      const range = new vscode.Range(line, 0, line, 0);
      editor.revealRange(range, vscode.TextEditorRevealType.InCenter);
      editor.selection = new vscode.Selection(range.start, range.start);
      return;
    }

    if (msg.type === "copyMermaid" && this.graph) {
      const text = this.mermaidForView();
      await vscode.env.clipboard.writeText(text);
      void vscode.window.showInformationMessage(
        `Method Glance: ${this.view} diagram copied as Mermaid`
      );
      return;
    }

    if (msg.type === "refresh") {
      await this.refresh();
    }
  }

  /**
   * Export whatever the user is looking at. This previously always emitted the
   * call graph, so copying from the sequence or class view silently handed over
   * a diagram of something else.
   */
  private mermaidForView(): string {
    const g = this.graph!;

    if (this.view === "sequence") {
      const parts = new Map(g.participants.map((p) => [p.id, p]));
      const byCaller = this.callsByCaller();
      const root = this.sequenceRoot(g, byCaller);
      return root
        ? toMermaidSequence(root.id, parts, byCaller, this.depth)
        : "sequenceDiagram";
    }

    if (this.view === "classes") {
      return toMermaidClasses(g.classes, g.inherits);
    }

    if (this.view === "modules") {
      const nodes: GraphNode[] = [
        { id: "__self__", label: g.file },
        ...g.modules.map((m) => ({
          id: m.name,
          label: m.name,
          group: m.kind,
        })),
      ];
      const edges: GraphEdge[] = g.modules.map((m) => ({
        from: "__self__",
        to: m.name,
        count: m.calls,
        cross: m.calls === 0,
      }));
      return toMermaid(nodes, edges);
    }

    // Graph and flow both read well as a flowchart.
    const { nodes, edges } = this.filtered();
    return toMermaid(nodes, edges);
  }

  private callsByCaller(): Map<string, SeqCall[]> {
    const byCaller = new Map<string, SeqCall[]>();
    for (const c of this.graph!.seqCalls) {
      if (!byCaller.has(c.from)) {
        byCaller.set(c.from, []);
      }
      byCaller.get(c.from)!.push(c);
    }
    return byCaller;
  }

  private filtered(): { nodes: GraphNode[]; edges: GraphEdge[] } {
    const g = this.graph!;
    if (this.showExternal) {
      return { nodes: g.nodes, edges: g.edges };
    }
    const nodes = g.nodes.filter((n) => !n.external);
    const keep = new Set(nodes.map((n) => n.id));
    return {
      nodes,
      edges: g.edges.filter((e) => keep.has(e.from) && keep.has(e.to)),
    };
  }

  private async refresh(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor || familyFor(editor.document.languageId) === "unsupported") {
      return;
    }
    this.docUri = editor.document.uri;
    this.anchorLine = editor.selection.active.line;
    const cursorModel = await getModel(editor.document);
    this.enclosingId = methodAtLine(cursorModel.methods, this.anchorLine)?.id;
    this.panel.webview.postMessage({ type: "loading" });
    this.graph = await buildGraph(editor.document);
    this.panel.title = `Glance Map · ${this.graph.file}`;
    await this.post();
  }

  /** Build the Scene for the selected view and hand it to the webview. */
  private async buildScene(): Promise<Scene> {
    const g = this.graph!;

    if (this.view === "sequence") {
      const parts = new Map(g.participants.map((p) => [p.id, p]));
      const byCaller = this.callsByCaller();
      const root = this.sequenceRoot(g, byCaller);
      if (!root) {
        return {
          kind: "sequence",
          nodes: [],
          edges: [],
          width: this.lastWidth,
          height: 200,
          empty: "No methods found to trace.",
        };
      }
      return sequenceScene(root, parts, byCaller, this.depth, this.lastWidth);
    }

    if (this.view === "classes") {
      return classScene(g.classes, g.inherits, this.lastWidth);
    }

    if (this.view === "flow") {
      return this.flowSceneForCursor();
    }

    if (this.view === "modules") {
      return moduleScene(g.file, g.modules, this.lastWidth);
    }

    const { nodes, edges } = this.filtered();
    return graphScene(layout(nodes, edges, this.lastWidth), g.lines);
  }

  /**
   * Data flow describes one method, so it follows the cursor. Without a method
   * under the caret there is nothing meaningful to show — saying so beats
   * picking one arbitrarily.
   */
  private async flowSceneForCursor(): Promise<Scene> {
    const doc = this.docUri
      ? await vscode.workspace.openTextDocument(this.docUri)
      : undefined;
    const model = doc ? await getModel(doc) : undefined;
    const method =
      model && doc ? methodAtLine(model.methods, this.anchorLine) : undefined;

    if (!doc || !method) {
      return {
        kind: "flow",
        nodes: [],
        edges: [],
        width: this.lastWidth,
        height: 200,
        empty:
          "Put the cursor inside a method.\nThe data-flow view follows one method's parameters to where they end up.",
      };
    }

    const family = familyFor(doc.languageId);
    const lines = doc.getText().split(/\r\n|\r|\n/);
    const signature = lines
      .slice(method.selectionLine, method.foldStart + 1)
      .join(" ");
    const body = lines.slice(method.foldStart + 1, method.range.end + 1);
    const flow = analyzeFlow(signature, body, method.foldStart + 1, family);
    return flowScene(method.name, flow, this.lastWidth);
  }

  /**
   * Where the trace starts: the method under the cursor if it calls anything,
   * otherwise a detected entry point, otherwise whichever method calls the
   * most. Following the cursor is what makes the view feel like it is
   * answering a question you just asked.
   */
  private sequenceRoot(
    g: RawGraph,
    byCaller: Map<string, SeqCall[]>
  ): SeqParticipant | undefined {
    const byId = new Map(g.participants.map((p) => [p.id, p]));

    const atCursor = g.participants.find(
      (p) => p.clickLine !== undefined && p.clickLine === this.anchorLine
    );
    if (atCursor && byCaller.has(atCursor.id)) {
      return atCursor;
    }
    const cursorEnclosing = g.participants.find(
      (p) => p.id === this.enclosingId
    );
    if (cursorEnclosing && byCaller.has(cursorEnclosing.id)) {
      return cursorEnclosing;
    }
    for (const id of g.entries) {
      if (byCaller.has(id)) {
        return byId.get(id);
      }
    }
    let best: SeqParticipant | undefined;
    let bestCount = 0;
    for (const [id, calls] of byCaller) {
      if (calls.length > bestCount) {
        bestCount = calls.length;
        best = byId.get(id);
      }
    }
    return best || g.participants[0];
  }

  private async post(): Promise<void> {
    if (!this.graph) {
      return;
    }
    const scene = await this.buildScene();
    this.panel.webview.postMessage({
      type: "render",
      scene,
      meta: {
        file: this.graph.file,
        semantic: this.graph.semantic,
        truncated: this.graph.truncated,
        externalCount: this.graph.nodes.filter((n) => n.external).length,
        showExternal: this.showExternal,
        view: this.view,
      },
    });
  }

  private html(): string {
    const w = this.panel.webview;
    const css = w.asWebviewUri(
      vscode.Uri.joinPath(this.context.extensionUri, "media", "glance.css")
    );
    const js = w.asWebviewUri(
      vscode.Uri.joinPath(this.context.extensionUri, "media", "glance.js")
    );
    const n = nonce();
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${w.cspSource}; style-src ${w.cspSource}; script-src 'nonce-${n}';">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link href="${css}" rel="stylesheet">
<title>Glance Map</title>
</head>
<body>
  <header class="bar">
    <div class="bar-left">
      <strong id="file">Glance Map</strong>
      <span id="badge" class="badge" hidden></span>
    </div>
    <div class="bar-right">
      <select id="view" title="Diagram">
        <option value="graph">Call graph</option>
        <option value="sequence">Sequence</option>
        <option value="classes">Classes</option>
        <option value="flow">Data flow</option>
        <option value="modules">Modules</option>
      </select>
      <label class="toggle" id="depthWrap" hidden>depth
        <select id="depth">
          <option value="2">2</option>
          <option value="3">3</option>
          <option value="4" selected>4</option>
          <option value="6">6</option>
        </select>
      </label>
      <label class="toggle"><input type="checkbox" id="ext"> External calls</label>
      <button id="fit" title="Fit to window">Fit</button>
      <button id="copy" title="Copy as Mermaid">Copy Mermaid</button>
      <button id="reload" title="Recompute">Refresh</button>
    </div>
  </header>

  <div id="caption" class="caption" hidden></div>

  <div id="stage" class="stage" tabindex="0">
    <div id="state" class="state">Open a supported file to map it.</div>
    <svg id="svg" hidden></svg>
  </div>

  <footer class="legend" id="legend"></footer>

  <script nonce="${n}" src="${js}"></script>
</body>
</html>`;
  }

  private dispose(): void {
    GlanceMapPanel.current = undefined;
    this.panel.dispose();
    while (this.disposables.length) {
      this.disposables.pop()?.dispose();
    }
  }
}
