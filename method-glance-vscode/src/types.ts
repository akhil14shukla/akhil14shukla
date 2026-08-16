/**
 * A region of the document that should be collapsed when "glancing" over a
 * file. `start` stays visible (it carries the collapsed `…` marker); the lines
 * from `start + 1` through `end` are hidden.
 *
 * For a documented Python method this is [last-line-of-docstring, last-line-of-body]
 * so the signature and docstring remain on screen. For a brace-language function
 * it is [line-with-`{`, line-with-matching-`}`] so the leading doc comment and
 * signature stay visible.
 *
 * All line numbers are 0-based to match the VS Code editor API.
 */
export interface FoldSpec {
  /** 0-based line that remains visible and shows the collapse marker. */
  start: number;
  /** 0-based last hidden line. */
  end: number;
}

/** Broad language families we know how to parse. */
export type LanguageFamily = "python" | "brace" | "unsupported";
