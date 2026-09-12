import { useEffect, useMemo, useState } from "react";

/** A room is a project: one or more repos with roles. This file is the shared editor for that list, used by the
 *  "new project" form on the join screen and by Settings → This project. Repos come from the person's GitHub
 *  account (via the connected token), from a folder already on the machine, or from a pasted URL. */

export const ROLES = ["frontend", "api", "worker", "lib", "infra", "docs", "other"] as const;

export type RepoEntry = {
  key: string;
  source: "github" | "folder" | "url";
  label: string;  // what we show: acme/web, ./web, or the URL
  path?: string;  // folder on the machine (absolute or relative to the repos dir)
  git_url?: string;
  role: string;
  branch: string;
};
export type ProjectRepoInfo = { path: string; name: string; role: string; git_url: string | null; branch: string | null; exists?: boolean; git?: boolean };
export type LocalRepo = { name: string; path: string; git: boolean; remote: string | null; branch: string | null; dirty: boolean; rooms: string[] };
type GhRepo = { full_name: string; html_url: string; clone_url: string; default_branch: string; private: boolean; pushed_at: string | null; description: string; language: string };

let seq = 0;
export const newKey = () => `r${++seq}-${Date.now().toString(36)}`;

export function fromInfo(r: ProjectRepoInfo): RepoEntry {
  return { key: newKey(), source: r.git_url ? "url" : "folder", label: r.name, path: r.path, git_url: r.git_url ?? undefined, role: r.role, branch: r.branch ?? "" };
}

/** What the worker's create/patch endpoints take. */
export function toApi(entries: RepoEntry[]) {
  return entries.map((e) => ({ path: e.path || undefined, git_url: e.git_url || undefined, role: e.role || undefined, branch: e.branch || undefined }));
}

/** Guess a role from the repo's name/language so most rows need no click. */
export function guessRole(name: string, language = ""): string {
  const n = name.toLowerCase();
  if (/(front|web|ui|app|site|client|dashboard|admin|portal)/.test(n) || /typescript|javascript|vue|svelte/i.test(language) && !/api|server|backend/.test(n)) return "frontend";
  if (/(api|backend|server|service|core)/.test(n)) return "api";
  if (/(worker|jobs|queue|cron|pipeline|etl)/.test(n)) return "worker";
  if (/(lib|sdk|shared|common|schema|proto|types)/.test(n)) return "lib";
  if (/(infra|terraform|deploy|k8s|helm|ops|docker)/.test(n)) return "infra";
  if (/(docs?|wiki|handbook)/.test(n)) return "docs";
  return "";
}

/** The person's GitHub repositories, searchable. Needs a connected account (or the machine token). */
export function useGitHubRepos(enabled: boolean) {
  const [repos, setRepos] = useState<GhRepo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needsConnect, setNeedsConnect] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    fetch("/api/github/repos").then(async (r) => {
      const j = await r.json();
      if (!alive) return;
      if (r.status === 409) { setNeedsConnect(true); setRepos([]); return; }
      if (!r.ok) throw new Error(j.error ?? r.statusText);
      setRepos(j.repos ?? []);
    }).catch((e) => alive && setError(String(e instanceof Error ? e.message : e)));
    return () => { alive = false; };
  }, [enabled]);
  return { repos, error, needsConnect };
}

/** Add one repo: pick from GitHub, from a folder on the machine, or paste a URL. Calls onAdd with the entry. */
export function RepoAdder({ onAdd, exclude, onConnectGitHub }: { onAdd: (e: RepoEntry) => void; exclude: RepoEntry[]; onConnectGitHub?: () => void }) {
  const [mode, setMode] = useState<"github" | "folder" | "url">("github");
  const [q, setQ] = useState("");
  const [url, setUrl] = useState("");
  const [local, setLocal] = useState<LocalRepo[]>([]);
  const gh = useGitHubRepos(mode === "github");
  useEffect(() => {
    if (mode === "folder") fetch("/api/repos").then((r) => r.json()).then((j) => setLocal(j.repos ?? [])).catch(() => {});
  }, [mode]);
  const taken = useMemo(() => new Set(exclude.flatMap((e) => [e.git_url ?? "", e.path ?? "", e.label].filter(Boolean))), [exclude]);
  const list = useMemo(() => {
    const ql = q.trim().toLowerCase();
    return (gh.repos ?? []).filter((r) => !ql || r.full_name.toLowerCase().includes(ql) || r.description.toLowerCase().includes(ql)).slice(0, 40);
  }, [gh.repos, q]);

  return (
    <div className="repo-adder">
      <div className="src">
        <label><input type="radio" checked={mode === "github"} onChange={() => setMode("github")} /> from your GitHub</label>
        <label><input type="radio" checked={mode === "folder"} onChange={() => setMode("folder")} /> folder on this machine</label>
        <label><input type="radio" checked={mode === "url"} onChange={() => setMode("url")} /> git URL</label>
      </div>
      {mode === "github" && (
        <>
          {gh.needsConnect && (
            <p className="hint">
              Connect your GitHub account to pick from your repositories.{" "}
              {onConnectGitHub ? <a href="#" onClick={(e) => { e.preventDefault(); onConnectGitHub(); }}>Connect GitHub</a> : <>Settings → GitHub → Connect GitHub.</>}
              {" "}Or paste a URL.
            </p>
          )}
          {gh.error && <p className="error">{gh.error}</p>}
          {!gh.needsConnect && !gh.error && (
            <>
              <input placeholder="search your repositories…" value={q} onChange={(e) => setQ(e.target.value)} />
              {gh.repos === null ? <p className="hint">loading your repositories…</p> : (
                <ul className="repo-pick">
                  {list.map((r) => {
                    const dup = taken.has(r.clone_url) || taken.has(r.full_name);
                    return (
                      <li key={r.full_name} className={dup ? "taken" : ""} onClick={() => !dup && onAdd({ key: newKey(), source: "github", label: r.full_name, git_url: r.clone_url, role: guessRole(r.full_name.split("/")[1] ?? r.full_name, r.language), branch: "" })} title={r.description}>
                        <b>{r.full_name}</b>{r.private && <span className="tag">private</span>}{r.language && <span className="dim"> · {r.language}</span>}
                        <span className="dim desc">{r.description}</span>
                      </li>
                    );
                  })}
                  {list.length === 0 && <li className="hint">no match</li>}
                </ul>
              )}
            </>
          )}
        </>
      )}
      {mode === "folder" && (
        <ul className="repo-pick">
          {local.map((r) => {
            const dup = taken.has(r.path);
            return (
              <li key={r.path} className={dup ? "taken" : ""} onClick={() => !dup && onAdd({ key: newKey(), source: "folder", label: r.name, path: r.path, role: guessRole(r.name), branch: "" })}>
                <b>{r.name}</b><span className="dim"> {r.branch ? `· ${r.branch}` : ""}{r.dirty ? " · uncommitted changes" : ""}{r.rooms.length ? ` · in ${r.rooms.join(", ")}` : ""}</span>
              </li>
            );
          })}
          {local.length === 0 && <li className="hint">no repos on this machine yet</li>}
        </ul>
      )}
      {mode === "url" && (
        <div className="row">
          <input placeholder="https://github.com/your-org/your-repo or git@github.com:org/repo.git" value={url} onChange={(e) => setUrl(e.target.value)} />
          <button type="button" disabled={!url.trim()} onClick={() => { const u = url.trim(); const name = u.replace(/\/+$/, "").split(/[/:]/).pop()?.replace(/\.git$/, "") ?? u; onAdd({ key: newKey(), source: "url", label: name, git_url: u, role: guessRole(name), branch: "" }); setUrl(""); }}>add</button>
        </div>
      )}
    </div>
  );
}

/** The project's repo list: role and branch per repo, first one is the agent's working directory. */
export function RepoList({ entries, onChange, readOnly }: { entries: RepoEntry[]; onChange: (e: RepoEntry[]) => void; readOnly?: boolean }) {
  const set = (k: string, patch: Partial<RepoEntry>) => onChange(entries.map((e) => (e.key === k ? { ...e, ...patch } : e)));
  const move = (i: number, j: number) => { const a = entries.slice(); const [x] = a.splice(i, 1); a.splice(j, 0, x); onChange(a); };
  if (entries.length === 0) return <p className="hint">No repos yet. Add the first one below; it becomes the agent's working directory.</p>;
  return (
    <ul className="repo-rows">
      {entries.map((e, i) => (
        <li key={e.key}>
          <span className="who" title={e.git_url ?? e.path}>
            <b>{e.label}</b>
            {i === 0 && <span className="tag">working dir</span>}
            {e.source === "github" && <span className="dim small"> github</span>}
          </span>
          <select value={ROLES.includes(e.role as typeof ROLES[number]) || e.role === "" ? e.role : "other"} disabled={readOnly} onChange={(ev) => set(e.key, { role: ev.target.value })} aria-label="role">
            <option value="">role…</option>
            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <input value={e.branch} disabled={readOnly} onChange={(ev) => set(e.key, { branch: ev.target.value })} placeholder="branch (default)" aria-label="branch" />
          {!readOnly && (
            <span className="btns">
              {i > 0 && <button type="button" className="ghost" title="make this the working directory" onClick={() => move(i, 0)}>↑ first</button>}
              <button type="button" className="ghost" onClick={() => onChange(entries.filter((x) => x.key !== e.key))}>remove</button>
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
