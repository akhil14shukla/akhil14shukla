import { LanguageFamily } from "./types";

/**
 * Map a VS Code languageId to the parser family that handles it.
 *
 * Python is the primary, most precise target. Brace-delimited C-family
 * languages are handled on a best-effort basis: their doc comments live
 * above the signature (outside the body), so folding the `{ … }` body is
 * enough to keep the signature and its doc comment on screen.
 */
const BRACE_LANGUAGES = new Set<string>([
  "javascript",
  "javascriptreact",
  "typescript",
  "typescriptreact",
  "java",
  "c",
  "cpp",
  "csharp",
  "go",
  "rust",
  "php",
  "kotlin",
  "scala",
  "swift",
  "dart",
  "groovy",
]);

export function familyFor(languageId: string): LanguageFamily {
  if (languageId === "python") {
    return "python";
  }
  if (BRACE_LANGUAGES.has(languageId)) {
    return "brace";
  }
  return "unsupported";
}

/** Every languageId the extension activates for. */
export function supportedLanguageIds(): string[] {
  return ["python", ...BRACE_LANGUAGES];
}
