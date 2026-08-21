import * as path from "path";
import { runTests } from "@vscode/test-electron";

/** Download a real VS Code and run the functional suite inside it. */
async function main(): Promise<void> {
  const extensionDevelopmentPath = path.resolve(__dirname, "../../..");
  const extensionTestsPath = path.resolve(__dirname, "./suite");
  try {
    await runTests({
      extensionDevelopmentPath,
      extensionTestsPath,
      launchArgs: [
        "--disable-workspace-trust",
        "--no-sandbox",
        "--disable-gpu",
        path.resolve(__dirname, "../../../test/integration/fixtures"),
      ],
    });
  } catch (err) {
    console.error("Functional tests failed:", err);
    process.exit(1);
  }
}

void main();
