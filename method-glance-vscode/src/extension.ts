import * as vscode from "vscode";
import { computeFoldSpecs } from "./parse";
import { familyFor, supportedLanguageIds } from "./languages";
import { FoldSpec } from "./types";

/**
 * Provider that exposes the "glance" ranges to the editor so that
 * `editor.fold` has a foldable region beginning at each range's start line.
 * These ranges are additive to the built-in folding; they never remove the
 * user's normal fold controls.
 */
class GlanceFoldingProvider implements vscode.FoldingRangeProvider {
  provideFoldingRanges(document: vscode.TextDocument): vscode.FoldingRange[] {
    if (familyFor(document.languageId) === "unsupported") {
      return [];
    }
    return computeFoldSpecs(document.languageId, document.getText()).map(
      (s) => new vscode.FoldingRange(s.start, s.end)
    );
  }
}

function specsFor(document: vscode.TextDocument): FoldSpec[] {
  return computeFoldSpecs(document.languageId, document.getText());
}

/** Collapse everything but method signatures and their docstrings. */
async function glanceFold(editor: vscode.TextEditor): Promise<void> {
  const specs = specsFor(editor.document);
  if (specs.length === 0) {
    vscode.window.setStatusBarMessage(
      "Method Glance: no methods found to fold",
      3000
    );
    return;
  }
  const selectionLines = specs.map((s) => s.start);
  // Reset first so repeated runs are idempotent regardless of current state.
  await vscode.commands.executeCommand("editor.unfoldAll");
  await vscode.commands.executeCommand("editor.fold", { selectionLines });
}

async function glanceUnfold(): Promise<void> {
  await vscode.commands.executeCommand("editor.unfoldAll");
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
    )
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("methodGlance.fold", () => {
      const editor = vscode.window.activeTextEditor;
      if (editor) {
        void glanceFold(editor);
      }
    }),
    vscode.commands.registerCommand("methodGlance.unfold", () => {
      void glanceUnfold();
    })
  );

  // Optional: fold automatically when a supported file is opened.
  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor((editor) => {
      if (!editor) {
        return;
      }
      const cfg = vscode.workspace.getConfiguration("methodGlance");
      if (!cfg.get<boolean>("foldOnOpen", false)) {
        return;
      }
      if (familyFor(editor.document.languageId) === "unsupported") {
        return;
      }
      void glanceFold(editor);
    })
  );
}

export function deactivate(): void {
  /* nothing to clean up */
}
