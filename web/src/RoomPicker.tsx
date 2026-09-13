import { useEffect, useState } from "react";
import { useIsAdmin } from "./auth";
import { RepoAdder, RepoList, toApi, type ProjectRepoInfo, type RepoEntry } from "./ProjectRepos";
import { SettingsPanel } from "./Settings";

export type RoomInfo = { name: string; repo: string; git_url: string | null; branch: string | null; static: boolean; live: boolean; repos: ProjectRepoInfo[] };

/** Projects on this machine, plus a form to create one from one or more repos (your GitHub, a folder here, or a URL). */
export function RoomPicker({ value, onPick, locked }: { value: string; onPick: (room: string) => void; locked?: boolean }) {
  const admin = useIsAdmin(); // creating projects (and cloning repos) is admin-only; the token server enforces it
  const [rooms, setRooms] = useState<RoomInfo[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [entries, setEntries] = useState<RepoEntry[]>([]);
  const [showSettings, setShowSettings] = useState(false);

  const refresh = () => {
    fetch("/api/rooms").then((r) => r.json()).then((j) => setRooms(j.rooms ?? [])).catch(() => setRooms([]));
  };
  useEffect(refresh, []);

  async function create() {
    if (!name) { setError("project name is required"); return; }
    setBusy(true);
    setError(null);
    // No repo at all: an empty folder named after the project (the agent can `git clone` or `git init` on request).
    const body = { name, repos: entries.length ? toApi(entries) : undefined };
    try {
      const r = await fetch("/api/rooms", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error ?? r.statusText);
      setCreating(false);
      setEntries([]);
      setName("");
      refresh();
      onPick(j.name);
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
    } finally {
      setBusy(false);
    }
  }

  const roles = (r: RoomInfo) => {
    const reps = r.repos ?? [];
    if (reps.length <= 1) return `${reps[0]?.name ?? r.repo.replace(/^.*\//, "")}${r.branch ? ` · ${r.branch}` : ""}`;
    return `${reps.length} repos · ${reps.map((x) => x.role || x.name).join(" + ")}`;
  };

  return (
    <div className="rooms">
      <div className="rooms-head">
        <span>Project</span>
        {admin && !locked && <button type="button" className="ghost" onClick={() => setCreating((c) => !c)}>{creating ? "cancel" : "new project"}</button>}
      </div>
      {rooms === null && <p className="hint">loading projects…</p>}
      {rooms && rooms.length === 0 && !creating && <p className="hint">{admin ? "No projects yet. Create one from your GitHub repos, a folder here, or a URL." : "No projects yet. Ask an admin to create one."}</p>}
      {rooms && rooms.length > 0 && (
        <ul className="room-list">
          {rooms.map((r) => (
            <li key={r.name} className={r.name === value ? "sel" : ""} onClick={() => { if (!locked) onPick(r.name); }}>
              <span className={`dot ${r.live ? "idle" : "offline"}`} />
              <b>{r.name}</b>
              <span className="repo" title={(r.repos ?? []).map((x) => x.path).join("\n")}>{roles(r)}</span>
            </li>
          ))}
        </ul>
      )}
      {creating && admin && (
        <div className="newroom">
          <label>Project name <input value={name} onChange={(e) => setName(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"))} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void create(); } }} pattern="[a-z0-9][a-z0-9-]{0,39}" required autoFocus /></label>
          <div className="dim small">Repos in this project. The first is where the agent starts; all are readable and editable. A frontend and its API, a service and its shared library, one repo, or none yet.</div>
          <RepoList entries={entries} onChange={setEntries} />
          <RepoAdder exclude={entries} onAdd={(e) => setEntries((cur) => [...cur, e])} onConnectGitHub={() => setShowSettings(true)} />
          <button type="button" onClick={() => void create()} disabled={busy}>{busy ? (entries.some((e) => e.git_url) ? "cloning…" : "creating…") : "create and join"}</button>
          {error && <p className="error">{error}</p>}
        </div>
      )}
      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} />}
    </div>
  );
}
