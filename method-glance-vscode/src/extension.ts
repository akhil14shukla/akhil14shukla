import * as vscode from "vscode";
import { familyFor, supportedLanguageIds } from "./languages";
import { GlanceHoverProvider } from "./hover";
import { MethodNode } from "./model";
import { GlanceMapPanel } from "./panel";
import { SceneKind } from "./scene";
import { getModel, invalidate, resolveCalls } from "./semantics";
import { MethodShape, shapeSummary } from "./shape";

/**
 * Contributes one folding range per method, ending at the last body line and
 * starting at the docstring's end so the signature and docs stay visible.
 * Additive to the built-in folding — normal fold controls keep working.
 */
class GlanceFoldingProvider implements vscode.FoldingRangeProvider {
  async provideFoldingRanges(
    document: vscode.TextDocument
  ): Promise<vscode.FoldingRange[]> {
    if (familyFor(document.languageId) === "unsupported") {
      return [];
    }
    const model = await getModel(document);
    return model.methods
      .filter((m) => m.range.end > m.foldStart)
      .map((m) => new vscode.FoldingRange(m.foldStart, m.range.end));
  }
}

/** Gutter caret marking methods that call something, so the editor hints at
 * structure even with no panel open. */
const callDecoration = vscode.window.createTextEditorDecorationType({
  before: {
    contentText: "↳",
    margin: "0 4px 0 0",
    color: new vscode.ThemeColor("editorCodeLens.foreground"),
  },
});

/**
 * The inline logic skeleton. Rendered after the docstring — the line that stays
 * on screen when folded — so a collapsed method still says what its body does,
 * not just what it is called.
 */
const shapeDecoration = vscode.window.createTextEditorDecorationType({});

/** Above this, a method is worth breaking up; flagged in the warning colour. */
const COMPLEXITY_WARN = 10;

function shapeHover(name: string, s: MethodShape): vscode.MarkdownString {
  const md = new vscode.MarkdownString();
  md.appendMarkdown(`**${name}** \u2014 complexity ${s.complexity}, nesting depth ${s.depth}\n\n`);
  const rows: string[] = [];
  if (s.branches) rows.push(`- ${s.branches} decision point${s.branches > 1 ? "s" : ""}`);
  if (s.loops) rows.push(`- ${s.loops} loop${s.loops > 1 ? "s" : ""}`);
  if (s.handlers) rows.push(`- ${s.handlers} error handler${s.handlers > 1 ? "s" : ""}`);
  if (s.guards) rows.push(`- ${s.guards} early exit${s.guards > 1 ? "s" : ""}`);
  if (s.returns) rows.push(`- ${s.returns} return${s.returns > 1 ? "s" : ""}`);
  if (s.raises) rows.push(`- ${s.raises} raise${s.raises > 1 ? "s" : ""}`);
  if (s.yields) rows.push("- generator");
  if (s.awaits) rows.push(`- ${s.awaits} await${s.awaits > 1 ? "s" : ""}`);
  if (s.mutates) rows.push("- mutates instance state");
  if (s.effects.length) rows.push(`- touches: ${s.effects.join(", ")}`);
  md.appendMarkdown(rows.join("\n"));
  if (s.complexity >= COMPLEXITY_WARN) {
    md.appendMarkdown("\n\n_High complexity \u2014 consider splitting._");
  }
  return md;
}

/**
 * Rebuilding the model means a symbol-provider round trip, so annotations are
 * debounced. Without this every keystroke re-parsed the file and re-queried the
 * language server.
 */
const SHAPE_DEBOUNCE_MS = 250;
let shapeTimer: ReturnType<typeof setTimeout> | undefined;

function scheduleShapes(editor: vscode.TextEditor): void {
  if (shapeTimer) {
    clearTimeout(shapeTimer);
  }
  shapeTimer = setTimeout(() => {
    shapeTimer = undefined;
    void decorateShapes(editor);
  }, SHAPE_DEBOUNCE_MS);
}

async function decorateShapes(editor: vscode.TextEditor): Promise<void> {
  const cfg = vscode.workspace.getConfiguration("methodGlance");
  if (!cfg.get<boolean>("showShapeAnnotations", true)) {
    editor.setDecorations(shapeDecoration, []);
    return;
  }
  const model = await getModel(editor.document);
  const opts: vscode.DecorationOptions[] = [];

  for (const m of model.methods) {
    const s = m.shape;
    if (!s || m.foldStart >= editor.document.lineCount) {
      continue;
    }
    const summary = shapeSummary(s);
    const hot = s.complexity >= COMPLEXITY_WARN;
    if (!summary && !hot) {
      continue;
    }
    const text = hot ? `${summary ? summary + " \u00b7 " : ""}complexity ${s.complexity}` : summary;
    opts.push({
      range: editor.document.lineAt(m.foldStart).range,
      hoverMessage: shapeHover(m.name, s),
      renderOptions: {
        after: {
          contentText: `    ${text}`,
          color: new vscode.ThemeColor(
            hot ? "editorWarning.foreground" : "editorCodeLens.foreground"
          ),
          fontStyle: "italic",
        },
      },
    });
  }
  editor.setDecorations(shapeDecoration, opts);
}

async function glanceFold(editor: vscode.TextEditor): Promise<void> {
  const model = await getModel(editor.document);
  const foldable = model.methods.filter((m) => m.range.end > m.foldStart);
  if (!foldable.length) {
    vscode.window.setStatusBarMessage(
      "Method Glance: no methods found to fold",
      3000
    );
    return;
  }
  await vscode.commands.executeCommand("editor.unfoldAll");
  await vscode.commands.executeCommand("editor.fold", {
    selectionLines: foldable.map((m) => m.foldStart),
  });

  const source = model.semantic ? "language server" : "text parser";
  vscode.window.setStatusBarMessage(
    `Method Glance: folded ${foldable.length} methods (${source})`,
    3000
  );
}

/**
 * Mark methods that call a sibling. Resolved lazily and capped, because each
 * method costs one call-hierarchy round trip.
 */
const DECORATION_BUDGET = 40;

async function decorateCallers(editor: vscode.TextEditor): Promise<void> {
  const cfg = vscode.workspace.getConfiguration("methodGlance");
  if (!cfg.get<boolean>("showCallCarets", true)) {
    editor.setDecorations(callDecoration, []);
    return;
  }
  const model = await getModel(editor.document);
  if (!model.semantic) {
    editor.setDecorations(callDecoration, []);
    return;
  }

  const marked: vscode.Range[] = [];
  const budget: MethodNode[] = model.methods.slice(0, DECORATION_BUDGET);
  for (const m of budget) {
    const edges = await resolveCalls(editor.document, m);
    if (edges.some((e) => e.to)) {
      marked.push(new vscode.Range(m.selectionLine, 0, m.selectionLine, 0));
    }
  }
  editor.setDecorations(callDecoration, marked);
}

export function activate(context: vscode.ExtensionContext): void {
  const selector = supportedLanguageIds().map((language) => ({
    language,
    scheme: "file",
  }));

  context.subscriptions.push(
    vscode.languages.registerFoldingRangeProvider(
      selector,
      new GlanceFoldingProvider()
    ),
    vscode.languages.registerHoverProvider(
      selector,
      new GlanceHoverProvider()
    ),
    callDecoration,
    shapeDecoration
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("methodGlance.fold", () => {
      const editor = vscode.window.activeTextEditor;
      if (editor) {
        void glanceFold(editor);
      }
    }),
    vscode.commands.registerCommand("methodGlance.unfold", () => {
      void vscode.commands.executeCommand("editor.unfoldAll");
    }),
    vscode.commands.registerCommand(
      "methodGlance.showMap",
      (view?: SceneKind) => {
        GlanceMapPanel.show(context, view);
      }
    ),
    vscode.commands.registerCommand("methodGlance.copyDiagram", async () => {
      const copied = await GlanceMapPanel.copyCurrent();
      vscode.window.setStatusBarMessage(
        copied
          ? "Method Glance: diagram copied as Mermaid"
          : "Method Glance: open the Glance Map first",
        3000
      );
    })
  );

  // Drop cached models when the document changes.
  context.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument((e) => {
      invalidate(e.document.uri);
      const editor = vscode.window.activeTextEditor;
      if (editor && editor.document === e.document) {
        scheduleShapes(editor);
      }
    })
  );

  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor((editor) => {
      if (!editor || familyFor(editor.document.languageId) === "unsupported") {
        return;
      }
      void decorateCallers(editor);
      void decorateShapes(editor);
      const cfg = vscode.workspace.getConfiguration("methodGlance");
      if (cfg.get<boolean>("foldOnOpen", false)) {
        void glanceFold(editor);
      }
    })
  );

  if (vscode.window.activeTextEditor) {
    void decorateCallers(vscode.window.activeTextEditor);
    void decorateShapes(vscode.window.activeTextEditor);
  }
}

export function deactivate(): void {
  if (shapeTimer) {
    clearTimeout(shapeTimer);
    shapeTimer = undefined;
  }
}
