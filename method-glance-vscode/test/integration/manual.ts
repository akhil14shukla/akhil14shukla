import * as path from "path";
import * as vscode from "vscode";

/**
 * Not an assertion suite — this drives the extension through a realistic
 * session and then holds the window open so the screen can be captured.
 * Used to look at the thing running, which is how the entry-point bug and the
 * blank-canvas bug were both found.
 */
export async function run(): Promise<void> {
  const dir = path.join(__dirname, "..", "..", "..", "test", "integration", "fixtures");
  // Read the plan from a file rather than the environment: VS Code does not
  // reliably pass custom env through to the extension host.
  let plan: { step: number; view: string; hold: number } = {
    step: 1,
    view: "graph",
    hold: 18000,
  };
  try {
    const raw = require("fs").readFileSync("/tmp/glance-manual.json", "utf8");
    plan = { ...plan, ...JSON.parse(raw) };
  } catch {
    /* defaults */
  }
  const step = plan.step;
  const hold = plan.hold;

  const ext = vscode.extensions.getExtension("akhil14shukla.method-glance");
  await ext!.activate();

  const file = step === 1 ? "orders.py" : "cache.ts";
  const doc = await vscode.workspace.openTextDocument(path.join(dir, file));
  const editor = await vscode.window.showTextDocument(doc, { preview: false });

  // Let the language server settle so the semantic path is exercised.
  await new Promise((r) => setTimeout(r, 6000));

  if (step === 1) {
    await vscode.commands.executeCommand("methodGlance.fold");
  } else {
    const line = doc
      .getText()
      .split("\n")
      .findIndex((l) => l.includes("set(key: string, value: T): void {"));
    editor.selection = new vscode.Selection(line, 4, line, 4);
    await vscode.commands.executeCommand("methodGlance.fold");
    await vscode.commands.executeCommand("methodGlance.showMap", plan.view);
  }

  await new Promise((r) => setTimeout(r, hold));
}
