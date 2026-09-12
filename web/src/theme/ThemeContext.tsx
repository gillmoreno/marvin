import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { BUILTIN, FALLBACK_ID, applyInitial, applyTheme, fetchThemes, readChoice, writeChoice, type Theme } from "./themes";

type Ctx = {
  themes: Theme[]; // built-in first, then this machine's custom ones
  active: Theme;
  choice: string | null; // this browser's pick, null = follow the machine default
  defaultId: string;
  defaultSource: "env" | "settings" | "builtin";
  dir: string | null; // where custom themes live on the worker (shown in Settings so people know what to ask Marvin)
  fresh: Theme | null; // a custom theme that appeared since the last refresh, for a one-line "try it" notice
  error: string | null;
  choose: (id: string | null) => void;
  setDefault: (id: string | null) => Promise<void>;
  remove: (id: string) => Promise<void>;
  refresh: () => Promise<void>;
  dismissFresh: () => void;
};

const ThemeCtx = createContext<Ctx | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [custom, setCustom] = useState<Theme[]>([]);
  const [defaultId, setDefaultId] = useState(FALLBACK_ID);
  const [defaultSource, setDefaultSource] = useState<Ctx["defaultSource"]>("builtin");
  const [dir, setDir] = useState<string | null>(null);
  const [choice, setChoice] = useState<string | null>(readChoice);
  const [fresh, setFresh] = useState<Theme | null>(null);
  const [error, setError] = useState<string | null>(null);
  const known = useRef<Set<string> | null>(null);
  const applied = useRef<string>("");

  useEffect(() => { applyInitial(); }, []);

  const refresh = useCallback(async () => {
    const r = await fetchThemes();
    if (!r) return;
    setCustom(r.themes);
    setDefaultId(r.default);
    setDefaultSource(r.default_source);
    setDir(r.dir);
    const ids = new Set(r.themes.filter((t) => t.valid).map((t) => t.id));
    if (known.current) {
      const added = r.themes.find((t) => t.valid && !known.current!.has(t.id));
      if (added) setFresh(added);
    }
    known.current = ids;
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  const themes = useMemo(() => [...BUILTIN, ...custom], [custom]);
  const active = useMemo(() => {
    const want = choice ?? defaultId;
    const t = themes.find((x) => x.id === want && x.valid);
    return t ?? themes.find((x) => x.id === defaultId && x.valid) ?? BUILTIN[0];
  }, [themes, choice, defaultId]);

  // Apply whenever the active theme (or a custom theme's files) changes; fall back to the default on failure.
  useEffect(() => {
    const key = `${active.id}@${active.mtime ?? ""}`;
    if (applied.current === key) return;
    applied.current = key;
    applyTheme(active).then(() => setError(null)).catch((e) => {
      setError(String(e instanceof Error ? e.message : e));
      const fb = themes.find((x) => x.id === defaultId && x.valid && x.builtin) ?? BUILTIN[0];
      applied.current = `${fb.id}@`;
      void applyTheme(fb);
    });
  }, [active, themes, defaultId]);

  const choose = useCallback((id: string | null) => { writeChoice(id); setChoice(id); setFresh(null); }, []);
  const setDefault = useCallback(async (id: string | null) => {
    const r = await fetch("/api/themes/default", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ id }) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error ?? r.statusText);
    await refresh();
  }, [refresh]);
  const remove = useCallback(async (id: string) => {
    const r = await fetch(`/api/themes/${encodeURIComponent(id)}`, { method: "DELETE" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error ?? r.statusText);
    if (choice === id) choose(null);
    await refresh();
  }, [refresh, choice, choose]);

  const value: Ctx = { themes, active, choice, defaultId, defaultSource, dir, fresh, error, choose, setDefault, remove, refresh, dismissFresh: () => setFresh(null) };
  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>;
}

export function useTheme(): Ctx {
  const c = useContext(ThemeCtx);
  if (!c) throw new Error("useTheme outside ThemeProvider");
  return c;
}
