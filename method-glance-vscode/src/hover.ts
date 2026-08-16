import * as vscode from "vscode";
import { familyFor } from "./languages";
import { methodAtLine } from "./model";
import { getModel, resolveCallers, resolveCalls } from "./semantics";

/**
 * Shows a method's documentation plus its resolved call relationships. This is
 * the piece that pays off most when the body is folded: the docstring is on
 * screen, and the hover adds what the body would have told you — what it calls,
 * and who calls it.
 */
export class GlanceHoverProvider implements vscode.HoverProvider {
  async provideHover(
    document: vscode.TextDocument,
    position: vscode.Position
  ): Promise<vscode.Hover | undefined> {
    if (familyFor(document.languageId) === "unsupported") {
      return undefined;
    }

    const model = await getModel(document);
    const method = methodAtLine(model.methods, position.line);
    // Only answer on the signature line, so we never fight the language
    // server's own hovers inside the body.
    if (!method || position.line !== method.selectionLine) {
      return undefined;
    }

    const md = new vscode.MarkdownString();
    md.isTrusted = true;

    const title = method.container
      ? `${method.container}.${method.name}`
      : method.name;
    md.appendMarkdown(`**${title}**${method.detail ? ` \`${method.detail}\`` : ""}\n\n`);

    if (method.doc) {
      md.appendMarkdown(`${method.doc}\n\n`);
    }

    const [calls, callers] = await Promise.all([
      resolveCalls(document, method),
      resolveCallers(document, method),
    ]);

    if (calls.length || callers.length) {
      md.appendMarkdown("---\n\n");
    }
    if (calls.length) {
      const names = calls.map((c) =>
        c.externalUri ? `${c.toName} _(external)_` : c.toName
      );
      md.appendMarkdown(`**calls →** ${names.join(", ")}\n\n`);
    }
    if (callers.length) {
      md.appendMarkdown(
        `**called by ←** ${callers.map((c) => c.name).join(", ")}\n\n`
      );
    }

    if (!model.semantic) {
      md.appendMarkdown(
        "\n_Structure read from text — no language server answered for this file._"
      );
    }

    return new vscode.Hover(
      md,
      new vscode.Range(method.selectionLine, 0, method.selectionLine, 200)
    );
  }
}
