import * as path from "path";
import { runTests } from "@vscode/test-electron";

/** Launch a real VS Code, drive it, and hold it open for a screen capture. */
async function main(): Promise<void> {
  await runTests({
    extensionDevelopmentPath: path.resolve(__dirname, "../../.."),
    extensionTestsPath: path.resolve(__dirname, "./manual"),
    launchArgs: [
      "--disable-workspace-trust",
      "--no-sandbox",
      "--disable-gpu",
      "--remote-debugging-port=9222",
      path.resolve(__dirname, "../../../test/integration/fixtures"),
    ],
  });
}
void main().catch((e) => {
  console.error(e);
  process.exit(1);
});
