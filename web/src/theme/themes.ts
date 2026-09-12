// UI themes: three built in, any number added under the worker's state dir (by people or by the agent in a room).
// A theme is data + CSS, never code. This file loads one, sanitises it again (the worker already validated custom
// ones), scopes its CSS to `html[data-theme="<id>"]` through the CSSOM and applies tokens, fonts and colour scheme.
// The contract (tokens, presence variants, stable class names) is worker/marvin/theme_docs/README.md.
import controlRoomMeta from "./builtin/control-room.json";
import controlRoomCss from "./builtin/control-room.css?inline";
import editorialMeta from "./builtin/editorial.json";
import editorialCss from "./builtin/editorial.css?inline";
import signalMeta from "./builtin/signal.json";
import signalCss from "./builtin/signal.css?inline";

export type AgentVariant = "dot" | "scope" | "ink" | "orb" | "bars";
export type SpeakerVariant = "dot" | "bars" | "ink" | "ring";
export type Theme = {
  id: string;
  name: string;
  description: string;
  author?: string;
  scheme: "dark" | "light";
  fonts: { ui?: string; display?: string; mono?: string; google?: string };
  presence: { agent?: AgentVariant; speaker?: SpeakerVariant };
  tokens: Record<string, string>;
  css: string | null; // built-in: the stylesheet text; custom: its URL (/api/themes/<id>/theme.css)
  builtin: boolean;
  valid: boolean;
  errors: string[];
  warnings: string[];
  mtime?: number;
};

export const FALLBACK_ID = "control-room";
export const CHOICE_KEY = "marvin.theme"; // this browser's pick; absent = follow the machine default
const CACHE_KEY = "marvin.theme.cache"; // last applied custom theme, so it shows before /api/themes is reachable (login screen)

const TOKENS = new Set([
  "--bg", "--panel", "--panel-2", "--line", "--fg", "--fg-2", "--dim", "--accent", "--accent-fg", "--sel", "--ok", "--warn", "--warn-bg", "--bad",
  "--exec", "--read", "--write", "--ins-bg", "--del-bg", "--glow", "--font-ui", "--font-display", "--font-mono", "--text", "--radius", "--radius-lg",
  "--shadow", "--left-w", "--right-w",
]);
const BAD_VALUE = /url\(|[;{}<]/i;
const GOOGLE_OK = /^[A-Za-z0-9+:;@,&=.\- ]{1,600}$/;
const FONT_OK = /^[A-Za-z0-9 ,'"\-]{1,120}$/;

function builtin(meta: Record<string, unknown>, css: string): Theme {
  return { ...(meta as Omit<Theme, "css" | "builtin" | "valid" | "errors" | "warnings">), css, builtin: true, valid: true, errors: [], warnings: [] };
}

export const BUILTIN: Theme[] = [builtin(controlRoomMeta, controlRoomCss), builtin(editorialMeta, editorialCss), builtin(signalMeta, signalCss)];

/** The worker's list of custom themes plus the machine default. 401 (not signed in yet) and a missing worker both
 *  return null: the caller keeps what it has. */
export async function fetchThemes(): Promise<{ themes: Theme[]; default: string; default_source: "env" | "settings" | "builtin"; dir: string | null } | null> {
  try {
    const r = await fetch("/api/themes");
    if (!r.ok) return null;
    const j = await r.json();
    if (!Array.isArray(j.themes)) return null;
    return { themes: j.themes as Theme[], default: String(j.default || FALLBACK_ID), default_source: j.default_source ?? "builtin", dir: j.dir ?? null };
  } catch {
    return null;
  }
}

export function readChoice(): string | null {
  try { return localStorage.getItem(CHOICE_KEY); } catch { return null; }
}
export function writeChoice(id: string | null): void {
  try { id ? localStorage.setItem(CHOICE_KEY, id) : localStorage.removeItem(CHOICE_KEY); } catch { /* private mode */ }
}
export function readCache(): (Theme & { cssText?: string }) | null {
  try { const s = localStorage.getItem(CACHE_KEY); return s ? JSON.parse(s) : null; } catch { return null; }
}
function writeCache(t: Theme, cssText: string): void {
  try { localStorage.setItem(CACHE_KEY, JSON.stringify({ ...t, cssText })); } catch { /* quota or private mode */ }
}

// -- applying ----------------------------------------------------------------------------------------------------

function el<T extends HTMLElement>(id: string, tag: string, attrs: Record<string, string> = {}): T {
  let e = document.getElementById(id) as T | null;
  if (!e) {
    e = document.createElement(tag) as T;
    e.id = id;
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    document.head.appendChild(e);
  }
  return e;
}

/** Prefix every selector with `html[data-theme="<id>"]`, descending into @media/@supports/@container/@layer. Themes
 *  write plain CSS (`.left {}`, `:root {}`); this keeps them from leaking when one is swapped for another. */
export function scopeSheet(sheet: CSSStyleSheet, prefix: string): void {
  const rewrite = (sel: string) =>
    sel.split(",").map((s) => {
      s = s.trim();
      if (!s) return s;
      if (s.startsWith(prefix)) return s;
      if (/^(:root|html)(?![\w-])/.test(s)) return s.replace(/^(:root|html)/, prefix); // `body...` stays a descendant: `html[data-theme] body.resizing`
      return `${prefix} ${s}`;
    }).join(", ");
  const walk = (rules: CSSRuleList) => {
    for (const r of Array.from(rules)) {
      if (r instanceof CSSStyleRule) {
        try { r.selectorText = rewrite(r.selectorText); } catch { /* unsupported selector: leave it */ }
      } else if ("cssRules" in r && !(r instanceof CSSKeyframesRule)) {
        walk((r as CSSGroupingRule).cssRules);
      }
    }
  };
  walk(sheet.cssRules);
}

function tokenBlock(t: Theme): string {
  const out: string[] = [`color-scheme: ${t.scheme === "light" ? "light" : "dark"};`];
  for (const [k, v] of Object.entries(t.tokens ?? {})) {
    if (TOKENS.has(k) && typeof v === "string" && v.length <= 200 && !BAD_VALUE.test(v)) out.push(`${k}: ${v};`);
  }
  const f = t.fonts ?? {};
  const fam = (name: string | undefined, fallback: string) => (name && FONT_OK.test(name) ? `"${name.replace(/"/g, "")}", ${fallback}` : null);
  const ui = fam(f.ui, "system-ui, sans-serif");
  const display = fam(f.display, "system-ui, sans-serif");
  const mono = fam(f.mono, "ui-monospace, Menlo, monospace");
  if (ui && !t.tokens?.["--font-ui"]) out.push(`--font-ui: ${ui};`);
  if (display && !t.tokens?.["--font-display"]) out.push(`--font-display: ${display};`);
  if (mono && !t.tokens?.["--font-mono"]) out.push(`--font-mono: ${mono};`);
  return `html[data-theme="${t.id}"] { ${out.join(" ")} }`;
}

let applying = 0;

/** Make `t` the page's theme. Resolves once tokens, fonts and CSS are in place; rejects (after restoring nothing) if
 *  the CSS could not be fetched, so the caller can fall back. */
export async function applyTheme(t: Theme, cssText?: string): Promise<void> {
  const seq = ++applying;
  let css = cssText ?? "";
  if (!cssText && t.css) {
    if (t.builtin) css = t.css;
    else {
      const r = await fetch(`${t.css}${t.css.includes("?") ? "&" : "?"}v=${encodeURIComponent(String(t.mtime ?? ""))}`);
      if (!r.ok) throw new Error(`theme ${t.id}: its CSS is not available (${r.status})`);
      css = await r.text();
    }
  }
  if (seq !== applying) return; // a later apply won
  const html = document.documentElement;
  // fonts
  const google = t.fonts?.google && GOOGLE_OK.test(t.fonts.google) && t.fonts.google.includes("family=") ? t.fonts.google.replace(/^[?&]+/, "") : null;
  const existing = document.getElementById("mv-theme-fonts");
  if (google) {
    const link = el<HTMLLinkElement>("mv-theme-fonts", "link", { rel: "stylesheet" });
    const href = `https://fonts.googleapis.com/css2?${google}&display=swap`;
    if (link.href !== href) link.href = href;
  } else if (existing) existing.remove();
  // tokens + colour scheme
  el<HTMLStyleElement>("mv-theme-tokens", "style").textContent = tokenBlock(t);
  // the stylesheet, scoped
  const style = el<HTMLStyleElement>("mv-theme-css", "style");
  style.textContent = css;
  if (style.sheet) {
    try { scopeSheet(style.sheet, `html[data-theme="${t.id}"]`); } catch (e) { console.warn("theme css could not be scoped", e); }
  }
  html.dataset.theme = t.id;
  html.dataset.scheme = t.scheme === "light" ? "light" : "dark";
  if (!t.builtin) writeCache(t, css);
}

/** Before anything is fetched: the cached custom theme if that is what this browser chose, else a built-in. */
export function applyInitial(): void {
  const choice = readChoice();
  const b = BUILTIN.find((t) => t.id === choice);
  if (b) { void applyTheme(b); return; }
  const cached = readCache();
  if (choice && cached && cached.id === choice) { void applyTheme(cached, cached.cssText ?? ""); return; }
  void applyTheme(BUILTIN[0]);
}

export function swatches(t: Theme): string[] {
  const tk = t.tokens ?? {};
  return [tk["--bg"], tk["--panel"], tk["--fg"], tk["--accent"], tk["--warn"]].filter((x): x is string => Boolean(x));
}
