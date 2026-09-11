import { useEffect, useState } from "react";
import { agent } from "./agent";
import { BotIcon, ChevronIcon, CpuIcon } from "./icons";

type Model = { id: string; label: string; note: string };
type Harness = { id: string; label: string; kind: string; auth: string; note: string };
type RoomInfo = { name: string; repo: string; model: string | null; model_pinned: string | null; harness: string; harness_pinned: string | null; linked: string[] };
type RepoInfo = { name: string; path: string };

/** Models one harness offers (empty for agents that pick their own). Re-fetched when the harness changes. */
export function useModels(harness: string | null | undefined) {
  const [models, setModels] = useState<Model[]>([]);
  const [def, setDef] = useState<string>("");
  useEffect(() => {
    const q = harness ? `?harness=${encodeURIComponent(harness)}` : "";
    fetch(`/api/models${q}`).then((r) => r.json()).then((j) => { setModels(j.models ?? []); setDef(j.default ?? ""); }).catch(() => {});
  }, [harness]);
  return { models, default: def };
}

export function useHarnesses() {
  const [harnesses, setHarnesses] = useState<Harness[]>([]);
  const [def, setDef] = useState<string>("");
  useEffect(() => {
    fetch("/api/harnesses").then((r) => r.json()).then((j) => { setHarnesses(j.harnesses ?? []); setDef(j.default ?? ""); }).catch(() => {});
  }, []);
  return { harnesses, default: def };
}

async function patchRoom(room: string, body: Record<string, unknown>) {
  const r = await fetch(`/api/rooms/${encodeURIComponent(room)}`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error((await r.json()).error ?? r.statusText);
}

/** Which coding agent runs this room (Claude Code, Codex, OpenCode, ...). Switching starts a fresh conversation. */
export function HarnessPicker({ room, info, reload }: { room: string; info: RoomInfo | null; reload: () => void }) {
  const { harnesses, default: def } = useHarnesses();
  const [busy, setBusy] = useState(false);
  const current = info?.harness ?? def;
  const label = harnesses.find((h) => h.id === current)?.label ?? current ?? "…";
  async function change(id: string) {
    setBusy(true);
    try {
      await patchRoom(room, { harness: id });
      reload();
    } catch (e) {
      alert(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }
  const pinned = Boolean(info?.harness_pinned);
  return (
    <span className={`modelpick harnesspick${pinned ? " pinned" : ""}`} title={`${pinned ? "Harness pinned for this room" : "Worker default harness"}: ${label}. Click to change; a new harness starts a new conversation.`}>
      <BotIcon />
      <span className="modelname">{label}</span>
      <ChevronIcon />
      <select aria-label="coding agent for this room" value={info?.harness_pinned ?? ""} disabled={busy} onChange={(e) => void change(e.target.value)}>
        <option value="">default ({harnesses.find((h) => h.id === def)?.label ?? def})</option>
        {harnesses.map((h) => <option key={h.id} value={h.id}>{h.label}</option>)}
      </select>
    </span>
  );
}

export function useRoomInfo(room: string, refreshKey: number) {
  const [info, setInfo] = useState<RoomInfo | null>(null);
  const load = () => fetch("/api/rooms").then((r) => r.json()).then((j) => setInfo((j.rooms ?? []).find((r: RoomInfo) => r.name === room) ?? null)).catch(() => {});
  useEffect(() => { void load(); }, [room, refreshKey]);
  return { info, reload: load };
}

/** Compact model picker for the conversation header: what the room runs on, changeable on the spot. */
export function ModelPicker({ room, info, reload }: { room: string; info: RoomInfo | null; reload: () => void }) {
  const { models, default: def } = useModels(info?.harness);
  const [busy, setBusy] = useState(false);
  const current = info?.model ?? def;
  const label = models.find((m) => m.id === current)?.label ?? (current || "harness default");
  async function change(id: string) {
    setBusy(true);
    try {
      await patchRoom(room, { model: id });
      reload();
    } catch (e) {
      alert(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }
  const pinned = Boolean(info?.model_pinned);
  const defaultLabel = models.find((m) => m.id === def)?.label ?? (def || "harness default");
  return (
    <span className={`modelpick${pinned ? " pinned" : ""}`} title={pinned ? `Model pinned for this room: ${label}. Click to change.` : `Harness default: ${label}. Click to pin a model for this room.`}>
      <CpuIcon />
      <span className="modelname">{label}</span>
      <ChevronIcon />
      <select aria-label="model for this room" value={info?.model_pinned ?? ""} disabled={busy} onChange={(e) => void change(e.target.value)}>
        <option value="">{models.length ? `default (${defaultLabel})` : "harness default"}</option>
        {models.map((m) => <option key={m.id} value={m.id}>{m.label} · {m.note}</option>)}
      </select>
    </span>
  );
}

/** The room's linked repos (extra folders the agent may read and edit) and the machine notes. */
export function RoomAndMachine({ room, info, reload }: { room: string; info: RoomInfo | null; reload: () => void }) {
  const [repos, setRepos] = useState<RepoInfo[]>([]);
  const [notes, setNotes] = useState<{ path: string; text: string } | null>(null);
  const [draft, setDraft] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    fetch("/api/repos").then((r) => r.json()).then((j) => setRepos(j.repos ?? [])).catch(() => {});
    fetch("/api/notes").then((r) => r.json()).then((j) => { setNotes(j); setDraft(j.text); }).catch(() => {});
  }, []);
  const linked = new Set(info?.linked ?? []);
  async function toggle(path: string) {
    const next = linked.has(path) ? [...linked].filter((p) => p !== path) : [...linked, path];
    const r = await fetch(`/api/rooms/${encodeURIComponent(room)}`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ linked: next }) });
    if (!r.ok) setMsg((await r.json()).error ?? r.statusText);
    reload();
  }
  async function saveNotes() {
    const r = await fetch("/api/notes", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ text: draft }) });
    setMsg(r.ok ? "Machine notes saved. Every room loads them at its next turn." : (await r.json()).error ?? r.statusText);
  }
  return (
    <>
      <section>
        <h3>This room · {room}</h3>
        <p className="dim small">Works in <code>{info?.repo ?? "…"}</code>. Linked repos are readable and editable too, e.g. a backend next to a frontend.</p>
        <div className="linklist">
          {repos.filter((r) => r.path !== info?.repo).map((r) => (
            <label key={r.path}><input type="checkbox" checked={linked.has(r.path)} onChange={() => void toggle(r.path)} /> {r.name}</label>
          ))}
          {repos.length <= 1 && <span className="dim small">no other repos on this machine yet</span>}
        </div>
      </section>
      <section>
        <h3>Machine notes</h3>
        <p className="dim small">Loaded into every room on this machine ({notes?.path ?? "~/.claude/CLAUDE.md"}). How repos connect, fake accounts, ports, recipes. {agent.name} appends here when asked to remember something machine-wide.</p>
        <textarea rows={12} value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false} />
        <div className="btns"><button onClick={() => void saveNotes()} disabled={notes === null || draft === notes.text}>save notes</button></div>
        {msg && <p className="status ok">{msg}</p>}
      </section>
    </>
  );
}
