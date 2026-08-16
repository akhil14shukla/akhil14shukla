import * as vscode from "vscode";
import { familyFor } from "./languages";
import { GraphEdge, GraphNode, layout } from "./layout";
import { toMermaid } from "./mermaid";
import { getModel, resolveCalls } from "./semantics";

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
    });
    lines[m.id] = m.selectionLine;
  }

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

  nodes.push(...externals.values());

  return {
    nodes,
    edges,
    lines,
    truncated: model.methods.length > RESOLVE_BUDGET,
    semantic: model.semantic,
    file: doc.uri.path.split("/").pop() || "",
  };
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

  static show(context: vscode.ExtensionContext): void {
    const column = vscode.ViewColumn.Beside;
    if (GlanceMapPanel.current) {
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
  }): Promise<void> {
    if (msg.type === "relayout") {
      this.lastWidth = msg.width ?? this.lastWidth;
      this.showExternal = msg.showExternal ?? this.showExternal;
      this.post();
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
      const { nodes, edges } = this.filtered();
      await vscode.env.clipboard.writeText(toMermaid(nodes, edges));
      void vscode.window.showInformationMessage(
        "Method Glance: Mermaid diagram copied to clipboard"
      );
      return;
    }

    if (msg.type === "refresh") {
      await this.refresh();
    }
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
    this.panel.webview.postMessage({ type: "loading" });
    this.graph = await buildGraph(editor.document);
    this.panel.title = `Glance Map · ${this.graph.file}`;
    this.post();
  }

  private post(): void {
    if (!this.graph) {
      return;
    }
    const { nodes, edges } = this.filtered();
    const result = layout(nodes, edges, this.lastWidth);
    this.panel.webview.postMessage({
      type: "render",
      layout: result,
      meta: {
        file: this.graph.file,
        semantic: this.graph.semantic,
        truncated: this.graph.truncated,
        externalCount: this.graph.nodes.filter((n) => n.external).length,
        showExternal: this.showExternal,
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
      <label class="toggle"><input type="checkbox" id="ext"> External calls</label>
      <button id="fit" title="Fit to window">Fit</button>
      <button id="copy" title="Copy as Mermaid">Copy Mermaid</button>
      <button id="reload" title="Recompute">Refresh</button>
    </div>
  </header>

  <div id="stage" class="stage" tabindex="0">
    <div id="state" class="state">Open a supported file to map it.</div>
    <svg id="svg" hidden></svg>
  </div>

  <footer class="legend" id="legend">
    <span><i class="sw sw-node"></i>method</span>
    <span><i class="sw sw-ext"></i>external</span>
    <span><i class="sw sw-warn"></i>warning</span>
    <span><i class="sw sw-err"></i>error</span>
    <span><i class="sw sw-line"></i>calls</span>
    <span><i class="sw sw-dash"></i>cross-file</span>
    <span class="hint">width = method size · click to open · hover to trace</span>
  </footer>

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
