import { useEffect, useState } from "react";

export type RoomInfo = { name: string; repo: string; git_url: string | null; branch: string | null; static: boolean; live: boolean };
type RepoInfo = { name: string; path: string; git: boolean; remote: string | null; branch: string | null; dirty: boolean; rooms: string[] };

/** Rooms on this machine, plus a form to create one from an existing folder or a GitHub URL. */
export function RoomPicker({ value, onPick }: { value: string; onPick: (room: string) => void }) {
  const [rooms, setRooms] = useState<RoomInfo[] | null>(null);
  const [repos, setRepos] = useState<RepoInfo[]>([]);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", source: "folder" as "folder" | "github", folder: "", git_url: "", branch: "" });

  const refresh = () => {
    fetch("/api/rooms").then((r) => r.json()).then((j) => setRooms(j.rooms ?? [])).catch(() => setRooms([]));
    fetch("/api/repos").then((r) => r.json()).then((j) => setRepos(j.repos ?? [])).catch(() => {});
  };
  useEffect(refresh, []);

  async function create() {
    if (!form.name || (form.source === "github" && !form.git_url)) {
      setError(form.name ? "repository URL is required" : "room name is required");
      return;
    }
    setBusy(true);
    setError(null);
    const body = form.source === "folder" ? { name: form.name, repo: form.folder || undefined } : { name: form.name, git_url: form.git_url, branch: form.branch || undefined };
    try {
      const r = await fetch("/api/rooms", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error ?? r.statusText);
      setCreating(false);
      refresh();
      onPick(j.name);
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rooms">
      <div className="rooms-head">
        <span>Room</span>
        <button type="button" className="ghost" onClick={() => setCreating((c) => !c)}>{creating ? "cancel" : "new room"}</button>
      </div>
      {rooms === null && <p className="hint">loading rooms…</p>}
      {rooms && rooms.length === 0 && !creating && <p className="hint">No rooms yet. Create one from a folder or a GitHub URL.</p>}
      {rooms && rooms.length > 0 && (
        <ul className="room-list">
          {rooms.map((r) => (
            <li key={r.name} className={r.name === value ? "sel" : ""} onClick={() => onPick(r.name)}>
              <span className={`dot ${r.live ? "idle" : "offline"}`} />
              <b>{r.name}</b>
              <span className="repo">{r.repo.replace(/^.*\//, "")}{r.branch ? ` · ${r.branch}` : ""}</span>
            </li>
          ))}
        </ul>
      )}
      {creating && (
        <div className="newroom" onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void create(); } }}>
          <label>Room name <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value.toLowerCase() })} pattern="[a-z0-9][a-z0-9-]{0,39}" required autoFocus /></label>
          <div className="src">
            <label><input type="radio" checked={form.source === "folder"} onChange={() => setForm({ ...form, source: "folder" })} /> folder on this machine</label>
            <label><input type="radio" checked={form.source === "github"} onChange={() => setForm({ ...form, source: "github" })} /> clone from GitHub</label>
          </div>
          {form.source === "folder" ? (
            <label>
              Folder
              <select value={form.folder} onChange={(e) => setForm({ ...form, folder: e.target.value })}>
                <option value="">new empty folder named after the room</option>
                {repos.map((r) => (
                  <option key={r.path} value={r.path}>{r.name}{r.branch ? ` (${r.branch}${r.dirty ? ", uncommitted changes" : ""})` : ""}</option>
                ))}
              </select>
            </label>
          ) : (
            <>
              <label>Repository URL <input value={form.git_url} onChange={(e) => setForm({ ...form, git_url: e.target.value })} placeholder="https://github.com/your-org/your-repo" required /></label>
              <label>Branch <input value={form.branch} onChange={(e) => setForm({ ...form, branch: e.target.value })} placeholder="default" /></label>
            </>
          )}
          <button type="button" onClick={() => void create()} disabled={busy}>{busy ? "creating…" : "create and join"}</button>
          {error && <p className="error">{error}</p>}
        </div>
      )}
    </div>
  );
}
