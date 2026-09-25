import { useMemo } from "react";
import hljs from "highlight.js/lib/core";
import bash from "highlight.js/lib/languages/bash";
import c from "highlight.js/lib/languages/c";
import cpp from "highlight.js/lib/languages/cpp";
import css from "highlight.js/lib/languages/css";
import go from "highlight.js/lib/languages/go";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import markdown from "highlight.js/lib/languages/markdown";
import python from "highlight.js/lib/languages/python";
import rust from "highlight.js/lib/languages/rust";
import sql from "highlight.js/lib/languages/sql";
import typescript from "highlight.js/lib/languages/typescript";
import xml from "highlight.js/lib/languages/xml";
import yaml from "highlight.js/lib/languages/yaml";

hljs.registerLanguage("bash", bash);
hljs.registerLanguage("c", c);
hljs.registerLanguage("cpp", cpp);
hljs.registerLanguage("css", css);
hljs.registerLanguage("go", go);
hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("json", json);
hljs.registerLanguage("markdown", markdown);
hljs.registerLanguage("python", python);
hljs.registerLanguage("rust", rust);
hljs.registerLanguage("sql", sql);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("xml", xml);
hljs.registerLanguage("yaml", yaml);

const LANG: Record<string, string> = {
  ts: "typescript", tsx: "typescript", mts: "typescript", cts: "typescript",
  js: "javascript", jsx: "javascript", mjs: "javascript", cjs: "javascript",
  py: "python", go: "go", rs: "rust",
  c: "c", h: "c",
  cpp: "cpp", cc: "cpp", cxx: "cpp", hpp: "cpp", hh: "cpp", hxx: "cpp",
  html: "xml", htm: "xml", xml: "xml", svg: "xml",
  css: "css", md: "markdown", markdown: "markdown",
  json: "json", sh: "bash", bash: "bash", zsh: "bash",
  yml: "yaml", yaml: "yaml", sql: "sql",
};

function languageFor(path: string | null): string | null {
  const ext = path?.split(".").pop()?.toLowerCase() ?? "";
  return LANG[ext] ?? null;
}

function kind(line: string): "meta" | "hunk" | "ins" | "del" | "ctx" {
  if (line.startsWith("diff ") || line.startsWith("index ") || line.startsWith("+++") || line.startsWith("---") || line.startsWith("new file") || line.startsWith("deleted file") || line.startsWith("similarity ") || line.startsWith("rename ") || line.startsWith("old mode") || line.startsWith("new mode")) return "meta";
  if (line.startsWith("@@")) return "hunk";
  if (line.startsWith("+")) return "ins";
  if (line.startsWith("-")) return "del";
  return "ctx";
}

function highlight(code: string, language: string | null): string {
  if (!language || !code) return escapeHtml(code);
  try {
    return hljs.highlight(code, { language, ignoreIllegals: true }).value;
  } catch {
    return escapeHtml(code);
  }
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** A git diff with green additions, red deletions, and language coloring on the code. */
export function DiffView({ text, path }: { text: string; path?: string | null }) {
  const language = languageFor(path ?? null);
  const lines = useMemo(() => text.split("\n"), [text]);
  if (!text) return <p className="quiet-empty">Reading the diff…</p>;
  return (
    <pre className="diff">
      {lines.map((line, i) => {
        const cls = kind(line);
        const code = cls === "ins" || cls === "del" || cls === "ctx" ? line.slice(1) : line;
        const marker = cls === "ins" || cls === "del" || cls === "ctx" ? line.slice(0, 1) : "";
        const html = cls === "meta" || cls === "hunk" ? escapeHtml(line) : highlight(code, language);
        return (
          <span key={i} className={`dl ${cls}`}>
            {marker}
            <span dangerouslySetInnerHTML={{ __html: html }} />
            {"\n"}
          </span>
        );
      })}
    </pre>
  );
}
