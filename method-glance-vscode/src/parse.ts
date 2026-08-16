import { FoldSpec } from "./types";
import { familyFor } from "./languages";
import { parsePython } from "./pythonParser";
import { parseBrace } from "./braceParser";

/** Compute glance fold ranges for a document, dispatching on its language. */
export function computeFoldSpecs(languageId: string, text: string): FoldSpec[] {
  switch (familyFor(languageId)) {
    case "python":
      return parsePython(text);
    case "brace":
      return parseBrace(text);
    default:
      return [];
  }
}
