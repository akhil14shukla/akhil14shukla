import * as vscode from "vscode";
import { familyFor, supportedLanguageIds } from "./languages";
import { GlanceHoverProvider } from "./hover";
import { MethodNode } from "./model";
import { getModel, invalidate, resolveCalls } from "./semantics";

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
    callDecoration
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
    })
  );

  // Drop cached models when the document changes.
  context.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument((e) => invalidate(e.document.uri))
  );

  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor((editor) => {
      if (!editor || familyFor(editor.document.languageId) === "unsupported") {
        return;
      }
      void decorateCallers(editor);
      const cfg = vscode.workspace.getConfiguration("methodGlance");
      if (cfg.get<boolean>("foldOnOpen", false)) {
        void glanceFold(editor);
      }
    })
  );

  if (vscode.window.activeTextEditor) {
    void decorateCallers(vscode.window.activeTextEditor);
  }
}

export function deactivate(): void {
  /* nothing to clean up */
}
