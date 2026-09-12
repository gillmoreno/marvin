import { useCallback, useEffect, useState } from "react";
import type { ControlMessage } from "./protocol";
import { agent } from "./agent";
import type { ProjectRepoInfo } from "./ProjectRepos";

type ChangedFile = { path: string; status: string; additions: number; deletions: number };
type Changes = { repo: string; git: boolean; branch: string | null; base: string | null; files: ChangedFile[] };

const STATUS: Record<string, string> = { M: "modified", A: "added", D: "deleted", R: "renamed", "?": "new" };

/** What git knows about the project's repos: files changed vs the branch base, and the diff of any of them. A project
 *  with several repos gets a tab per repo. */
export function ChangesPane({ room, repos, refreshKey, send }: { room: string; repos: ProjectRepoInfo[]; refreshKey: number; send: (m: ControlMessage) => void }) {
  const [which, setWhich] = useState<string>("");  // repo path; "" = primary
  const repo = repos.find((r) => r.path === which) ?? repos[0];
  const repoQ = repo && repos.length > 1 ? `&repo=${encodeURIComponent(repo.path)}` : "";
  const [data, setData] = useState<Changes | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [diff, setDiff] = useState<string>("");

  const load = useCallback(async () => {
    try {
      const r = await fetch(`/api/changes?room=${encodeURIComponent(room)}${repoQ}`);
      const j = await r.json();
      if (!r.ok) throw new Error(j.error ?? r.statusText);
      setData(j);
      setError(null);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    }
  }, [room, repoQ]);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 8000);
    return () => clearInterval(t);
  }, [load, refreshKey]);

  useEffect(() => {
    if (!selected) return;
    let alive = true;
    fetch(`/api/changes/file?room=${encodeURIComponent(room)}${repoQ}&path=${encodeURIComponent(selected)}`)
      .then((r) => r.text())
      .then((t) => alive && setDiff(t))
      .catch(() => alive && setDiff(""));
    return () => { alive = false; };
  }, [room, repoQ, selected, data]);

  useEffect(() => {
    if (data && selected && !data.files.some((f) => f.path === selected)) setSelected(null);
    if (data && !selected && data.files.length > 0) setSelected(data.files[0].path);
  }, [data, selected]);

  const tabs = repos.length > 1 ? (
    <div className="repo-tabs">
      {repos.map((r, i) => (
        <button key={r.path} className={(repo?.path === r.path) ? "on" : ""} onClick={() => { setWhich(i === 0 ? "" : r.path); setSelected(null); setData(null); }} title={r.path}>
          {r.name}{r.role ? <span className="dim"> · {r.role}</span> : null}
        </button>
      ))}
    </div>
  ) : null;
  if (error) return <div className="changes">{tabs}<p className="error">{error}</p></div>;
  if (!data) return <div className="changes">{tabs}<p className="hint">reading git…</p></div>;
  if (!data.git) return <div className="changes">{tabs}<p className="hint">{data.repo} is not a git repository yet. Ask {agent.name} to <code>git init</code> it, or add the repo from GitHub.</p></div>;

  const adds = data.files.reduce((n, f) => n + f.additions, 0);
  const dels = data.files.reduce((n, f) => n + f.deletions, 0);
  const inRepo = repos.length > 1 && repo ? ` in ${repo.name}` : "";
  return (
    <div className="changes">
      {tabs}
      <header>
        <span className="branch">{data.branch}</span>
        {data.base && data.base !== "HEAD" && <span className="dim"> vs {data.base}</span>}
        {data.base === "HEAD" && <span className="dim"> uncommitted</span>}
        <span className="stat"><b className="ins">+{adds}</b> <b className="del">−{dels}</b> · {data.files.length} file{data.files.length === 1 ? "" : "s"}</span>
        <span className="btns">
          <button className="ghost" disabled={data.files.length === 0} onClick={() => send({ action: "ask", text: `commit the current changes${inRepo} with a clear message` })}>commit</button>
          <button disabled={!data.branch || data.branch === "main" || data.branch === "master"} onClick={() => send({ action: "ask", text: `push the branch${inRepo} and open a pull request` })}>open PR</button>
        </span>
      </header>
      {data.files.length === 0 ? (
        <p className="hint">Nothing changed since the branch base. Ask {agent.name} for something.</p>
      ) : (
        <div className="changes-body">
          <ul className="files">
            {data.files.map((f) => (
              <li key={f.path} className={f.path === selected ? "sel" : ""} onClick={() => setSelected(f.path)} title={STATUS[f.status] ?? f.status}>
                <span className={`st st-${f.status === "?" ? "U" : f.status}`}>{f.status === "?" ? "A" : f.status}</span>
                <span className="path">{f.path}</span>
                <span className="nums"><span className="ins">+{f.additions}</span> <span className="del">−{f.deletions}</span></span>
              </li>
            ))}
          </ul>
          <pre className="diff">{renderDiff(diff)}</pre>
        </div>
      )}
    </div>
  );
}

function renderDiff(text: string) {
  if (!text) return <span className="dim">select a file</span>;
  return text.split("\n").map((line, i) => {
    const cls = line.startsWith("+++") || line.startsWith("---") ? "meta" : line.startsWith("@@") ? "hunk" : line.startsWith("+") ? "ins" : line.startsWith("-") ? "del" : line.startsWith("diff ") || line.startsWith("index ") ? "meta" : "";
    return <span key={i} className={`dl ${cls}`}>{line}{"\n"}</span>;
  });
}
