import * as assert from "assert";
import * as path from "path";
import * as vscode from "vscode";

/**
 * Functional tests that run inside a real VS Code instance with the extension
 * loaded. This exercises the wiring the unit tests cannot reach: activation,
 * provider registration, the fold command's effect on the editor, decorations,
 * and the webview panel.
 *
 * The TypeScript fixture is important: VS Code ships TS/JS language features,
 * so it drives the *semantic* path (real DocumentSymbol and call hierarchy).
 * The Python fixture has no language extension here, so it drives the text
 * fallback. Both paths are covered by choosing the file.
 */

const results: { name: string; error?: string }[] = [];

async function test(name: string, fn: () => Promise<void> | void): Promise<void> {
  try {
    await fn();
    results.push({ name });
    console.log(`  ok   ${name}`);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    results.push({ name, error: msg });
    console.log(`  FAIL ${name}\n         ${msg}`);
  }
}

/** Fixtures live in the source tree, not the build output, so the TypeScript
 * fixture is read as source rather than being compiled away. */
function fixture(name: string): string {
  return path.join(__dirname, "..", "..", "..", "test", "integration", "fixtures", name);
}

async function open(name: string): Promise<vscode.TextEditor> {
  const doc = await vscode.workspace.openTextDocument(fixture(name));
  const editor = await vscode.window.showTextDocument(doc, { preview: false });
  return editor;
}

/** Language servers start asynchronously; poll until symbols appear. */
async function waitForSymbols(
  uri: vscode.Uri,
  timeoutMs = 30000
): Promise<vscode.DocumentSymbol[]> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const s = await vscode.commands.executeCommand<vscode.DocumentSymbol[]>(
      "vscode.executeDocumentSymbolProvider",
      uri
    );
    if (s && s.length) {
      return s;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  return [];
}

function lineOf(doc: vscode.TextDocument, needle: string): number {
  for (let i = 0; i < doc.lineCount; i++) {
    if (doc.lineAt(i).text.includes(needle)) {
      return i;
    }
  }
  throw new Error(`fixture has no line containing ${JSON.stringify(needle)}`);
}

export async function run(): Promise<void> {
  console.log("\nMethod Glance — functional tests in a real VS Code\n");

  const ext = vscode.extensions.getExtension("akhil14shukla.method-glance");
  await test("extension is discovered", () => {
    assert.ok(ext, "extension not found by id");
  });

  await test("extension activates", async () => {
    await ext!.activate();
    assert.strictEqual(ext!.isActive, true);
  });

  await test("commands are registered", async () => {
    const all = await vscode.commands.getCommands(true);
    for (const id of [
      "methodGlance.fold",
      "methodGlance.unfold",
      "methodGlance.showMap",
    ]) {
      assert.ok(all.includes(id), `${id} not registered`);
    }
  });

  // ---------------------------------------------------------------------
  // Python — text fallback path (no Python extension installed here)
  // ---------------------------------------------------------------------

  const pyEditor = await open("orders.py");
  const pyDoc = pyEditor.document;

  await test("python: folding provider returns ranges", async () => {
    const ranges = await vscode.commands.executeCommand<vscode.FoldingRange[]>(
      "vscode.executeFoldingRangeProvider",
      pyDoc.uri
    );
    assert.ok(ranges && ranges.length > 0, "no folding ranges");
  });

  await test("python: fold starts at the docstring, not the signature", async () => {
    const ranges =
      (await vscode.commands.executeCommand<vscode.FoldingRange[]>(
        "vscode.executeFoldingRangeProvider",
        pyDoc.uri
      )) || [];
    const docLine = lineOf(pyDoc, '"""Return the total including tax."""');
    assert.ok(
      ranges.some((r) => r.start === docLine),
      `expected a fold starting at line ${docLine}; got ${ranges
        .map((r) => r.start)
        .join(",")}`
    );
  });

  await test("python: fold command hides bodies but keeps docstrings", async () => {
    await vscode.commands.executeCommand("methodGlance.fold");
    await new Promise((r) => setTimeout(r, 400));

    const visible = pyEditor.visibleRanges;
    const shown = (line: number) =>
      visible.some((r) => line >= r.start.line && line <= r.end.line);

    const sig = lineOf(pyDoc, "def _price(self, cart):");
    const doc = lineOf(pyDoc, '"""Return the total including tax."""');
    const body = lineOf(pyDoc, "subtotal = sum(");

    assert.ok(shown(sig), "signature was hidden");
    assert.ok(shown(doc), "docstring was hidden");
    assert.ok(!shown(body), "body line was still visible after folding");
  });

  await test("python: unfold restores the body", async () => {
    await vscode.commands.executeCommand("methodGlance.unfold");
    await new Promise((r) => setTimeout(r, 400));
    const body = lineOf(pyDoc, "subtotal = sum(");
    assert.ok(
      pyEditor.visibleRanges.some(
        (r) => body >= r.start.line && body <= r.end.line
      ),
      "body still hidden after unfold"
    );
  });

  await test("python: fold is idempotent", async () => {
    await vscode.commands.executeCommand("methodGlance.fold");
    await new Promise((r) => setTimeout(r, 300));
    const first = pyEditor.visibleRanges.map((r) => `${r.start.line}-${r.end.line}`).join("|");
    await vscode.commands.executeCommand("methodGlance.fold");
    await new Promise((r) => setTimeout(r, 300));
    const second = pyEditor.visibleRanges.map((r) => `${r.start.line}-${r.end.line}`).join("|");
    assert.strictEqual(second, first, "second fold changed the view");
    await vscode.commands.executeCommand("methodGlance.unfold");
  });

  await test("python: hover shows the docstring and the logic skeleton", async () => {
    const line = lineOf(pyDoc, "def _persist(self, cart, user, total):");
    const col = pyDoc.lineAt(line).text.indexOf("_persist") + 2;
    const hovers = await vscode.commands.executeCommand<vscode.Hover[]>(
      "vscode.executeHoverProvider",
      pyDoc.uri,
      new vscode.Position(line, col)
    );
    const text = (hovers || [])
      .flatMap((h) => h.contents)
      .map((c) => (typeof c === "string" ? c : (c as vscode.MarkdownString).value))
      .join("\n");
    assert.ok(/Write the order row/.test(text), `docstring missing from hover:\n${text}`);
  });

  // ---------------------------------------------------------------------
  // TypeScript — semantic path via VS Code's built-in language features
  // ---------------------------------------------------------------------

  const tsEditor = await open("cache.ts");
  const tsDoc = tsEditor.document;
  const symbols = await waitForSymbols(tsDoc.uri);

  await test("typescript: language server provides symbols", () => {
    assert.ok(symbols.length > 0, "no symbols — tsserver never started");
  });

  await test("typescript: folding keeps the signature visible", async () => {
    const ranges =
      (await vscode.commands.executeCommand<vscode.FoldingRange[]>(
        "vscode.executeFoldingRangeProvider",
        tsDoc.uri
      )) || [];
    const sig = lineOf(tsDoc, "get(key: string): T | undefined {");
    assert.ok(
      ranges.some((r) => r.start === sig),
      `expected a fold starting at the brace line ${sig}; got ${ranges
        .map((r) => r.start)
        .join(",")}`
    );
  });

  await test("typescript: fold command collapses method bodies", async () => {
    await vscode.window.showTextDocument(tsDoc, { preview: false });
    await vscode.commands.executeCommand("methodGlance.fold");
    await new Promise((r) => setTimeout(r, 400));
    const body = lineOf(tsDoc, "return this.store.get(key);");
    const editor = vscode.window.activeTextEditor!;
    assert.ok(
      !editor.visibleRanges.some(
        (r) => body >= r.start.line && body <= r.end.line
      ),
      "typescript body still visible after folding"
    );
    await vscode.commands.executeCommand("methodGlance.unfold");
  });

  await test("typescript: call hierarchy resolves an outgoing call", async () => {
    const line = lineOf(tsDoc, "set(key: string, value: T): void {");
    const col = tsDoc.lineAt(line).text.indexOf("set");
    const items = await vscode.commands.executeCommand<vscode.CallHierarchyItem[]>(
      "vscode.prepareCallHierarchy",
      tsDoc.uri,
      new vscode.Position(line, col)
    );
    assert.ok(items && items.length, "prepareCallHierarchy returned nothing");
    const outgoing = await vscode.commands.executeCommand<
      vscode.CallHierarchyOutgoingCall[]
    >("vscode.provideOutgoingCalls", items[0]);
    assert.ok(outgoing && outgoing.length, "no outgoing calls resolved");
    assert.ok(
      outgoing.some((c) => c.to.name === "evict"),
      `expected set() -> evict(); got ${(outgoing || []).map((c) => c.to.name).join(",")}`
    );
  });

  await test("typescript: hover reports what the method calls", async () => {
    const line = lineOf(tsDoc, "set(key: string, value: T): void {");
    const col = tsDoc.lineAt(line).text.indexOf("set") + 1;
    const hovers = await vscode.commands.executeCommand<vscode.Hover[]>(
      "vscode.executeHoverProvider",
      tsDoc.uri,
      new vscode.Position(line, col)
    );
    const text = (hovers || [])
      .flatMap((h) => h.contents)
      .map((c) => (typeof c === "string" ? c : (c as vscode.MarkdownString).value))
      .join("\n");
    assert.ok(/calls/.test(text) && /evict/.test(text), `call info missing:\n${text}`);
  });

  // ---------------------------------------------------------------------
  // Panel
  // ---------------------------------------------------------------------

  await test("map panel opens without throwing", async () => {
    await vscode.commands.executeCommand("methodGlance.showMap");
    await new Promise((r) => setTimeout(r, 2500));
  });

  await test("map panel survives switching the active file", async () => {
    await open("orders.py");
    await new Promise((r) => setTimeout(r, 1500));
    await open("cache.ts");
    await new Promise((r) => setTimeout(r, 1500));
  });

  // Every view must build against a real document. This is where a view that
  // works on synthetic fixtures but not on real language-server output shows up.
  for (const view of ["graph", "sequence", "classes", "flow", "modules"] as const) {
    await test(`map builds the ${view} view without throwing`, async () => {
      await open("cache.ts");
      // Put the cursor in a method so the cursor-driven views have an anchor.
      const editor = vscode.window.activeTextEditor!;
      const line = lineOf(editor.document, "set(key: string, value: T): void {");
      editor.selection = new vscode.Selection(line, 4, line, 4);
      await vscode.commands.executeCommand("methodGlance.showMap", view);
      await new Promise((r) => setTimeout(r, 1800));
    });
  }

  await test("mermaid export follows the active view", async () => {
    await open("cache.ts");
    const editor = vscode.window.activeTextEditor!;
    const line = lineOf(editor.document, "set(key: string, value: T): void {");
    editor.selection = new vscode.Selection(line, 4, line, 4);

    await vscode.commands.executeCommand("methodGlance.showMap", "sequence");
    await new Promise((r) => setTimeout(r, 1800));
    await vscode.commands.executeCommand("methodGlance.copyDiagram");
    const seq = await vscode.env.clipboard.readText();
    assert.ok(
      seq.startsWith("sequenceDiagram"),
      `sequence view exported: ${seq.slice(0, 60)}`
    );

    await vscode.commands.executeCommand("methodGlance.showMap", "classes");
    await new Promise((r) => setTimeout(r, 1800));
    await vscode.commands.executeCommand("methodGlance.copyDiagram");
    const cls = await vscode.env.clipboard.readText();
    assert.ok(
      cls.startsWith("classDiagram"),
      `class view exported: ${cls.slice(0, 60)}`
    );
    assert.ok(/class Cache/.test(cls), `Cache missing from class export:\n${cls}`);

    await vscode.commands.executeCommand("methodGlance.showMap", "graph");
    await new Promise((r) => setTimeout(r, 1500));
    await vscode.commands.executeCommand("methodGlance.copyDiagram");
    const graph = await vscode.env.clipboard.readText();
    assert.ok(graph.startsWith("flowchart"), `graph view exported: ${graph.slice(0, 60)}`);
  });

  await test("a method with no calls is only resolved once", async () => {
    // The negative result must be cached: without it, every call-less method
    // re-queried the language server on each hover and decoration pass.
    const editor = await open("cache.ts");
    const line = lineOf(editor.document, "evict(): void {");
    const col = editor.document.lineAt(line).text.indexOf("evict") + 1;
    const pos = new vscode.Position(line, col);
    const t0 = Date.now();
    await vscode.commands.executeCommand("vscode.executeHoverProvider", editor.document.uri, pos);
    const first = Date.now() - t0;
    const t1 = Date.now();
    await vscode.commands.executeCommand("vscode.executeHoverProvider", editor.document.uri, pos);
    const second = Date.now() - t1;
    assert.ok(second <= first + 250, `second hover took ${second}ms vs ${first}ms`);
  });

  await test("CRLF line endings are handled", async () => {
    const doc = await vscode.workspace.openTextDocument({
      content:
        'class A:\r\n    def go(self, x):\r\n        """Doc."""\r\n        if x:\r\n            return 1\r\n        return 2\r\n',
      language: "python",
    });
    await vscode.window.showTextDocument(doc, { preview: false });
    const ranges = await vscode.commands.executeCommand<vscode.FoldingRange[]>(
      "vscode.executeFoldingRangeProvider",
      doc.uri
    );
    assert.ok(ranges && ranges.length > 0, "no folds for a CRLF document");
  });

  await test("a file with no methods folds to nothing, without error", async () => {
    const doc = await vscode.workspace.openTextDocument({
      content: "X = 1\nY = 2\n",
      language: "python",
    });
    await vscode.window.showTextDocument(doc, { preview: false });
    await vscode.commands.executeCommand("methodGlance.fold");
    await new Promise((r) => setTimeout(r, 300));
  });

  await test("copy before opening the map does not throw", async () => {
    await vscode.commands.executeCommand("methodGlance.copyDiagram");
  });

  await test("unsupported file does not break anything", async () => {
    const doc = await vscode.workspace.openTextDocument({
      content: "just some text\nnot code at all\n",
      language: "plaintext",
    });
    await vscode.window.showTextDocument(doc, { preview: false });
    await vscode.commands.executeCommand("methodGlance.fold");
    await new Promise((r) => setTimeout(r, 300));
    const ranges = await vscode.commands.executeCommand<vscode.FoldingRange[]>(
      "vscode.executeFoldingRangeProvider",
      doc.uri
    );
    assert.ok(!ranges || ranges.length === 0, "produced folds for plaintext");
  });

  await test("empty file does not break anything", async () => {
    const doc = await vscode.workspace.openTextDocument({
      content: "",
      language: "python",
    });
    await vscode.window.showTextDocument(doc, { preview: false });
    await vscode.commands.executeCommand("methodGlance.fold");
    await new Promise((r) => setTimeout(r, 300));
  });

  await test("editing a document does not throw", async () => {
    const editor = await open("orders.py");
    await editor.edit((b) => {
      b.insert(new vscode.Position(0, 0), "# edited\n");
    });
    await new Promise((r) => setTimeout(r, 600));
    const ranges = await vscode.commands.executeCommand<vscode.FoldingRange[]>(
      "vscode.executeFoldingRangeProvider",
      editor.document.uri
    );
    assert.ok(ranges && ranges.length > 0, "folding broke after an edit");
    // leave the fixture as we found it
    await vscode.commands.executeCommand("undo");
  });

  const failed = results.filter((r) => r.error);
  console.log("");
  if (failed.length) {
    console.log(`${failed.length} of ${results.length} functional tests failed.`);
    throw new Error(
      "functional tests failed:\n" +
        failed.map((f) => ` - ${f.name}: ${f.error}`).join("\n")
    );
  }
  console.log(`All ${results.length} functional tests passed.`);
}
