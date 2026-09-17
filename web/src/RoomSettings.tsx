import { useEffect, useState } from "react";
import { agent } from "./agent";
import { BotIcon, ChevronIcon, CpuIcon } from "./icons";
import { useIsAdmin, useMe, logout } from "./auth";
import { RepoAdder, RepoList, fromInfo, toApi, type ProjectRepoInfo, type RepoEntry } from "./ProjectRepos";
import { Actions, Button, Card, Field, Text, Textarea } from "./ui";

type Model = { id: string; label: string; note: string };
type Harness = { id: string; label: string; kind: string; auth: string; note: string };
type RoomInfo = {
  name: string; repo: string; model: string | null; model_pinned: string | null; harness: string; harness_pinned: string | null; linked: string[];
  repos: ProjectRepoInfo[];
  sandbox: { image: string; container: string; network: string } | null;
};

/** Models this room can pick: what its running agent reports about itself (ACP harnesses), else the profile's static
 * list. Re-fetched when the harness or its effective model changes, i.e. right after a swap has finished starting. */
export function useModels(room: string, harness: string | null | undefined, effectiveModel: string | null | undefined) {
  const [models, setModels] = useState<Model[]>([]);
  const [def, setDef] = useState<string>("");
  const [live, setLive] = useState(false);
  useEffect(() => {
    const q = new URLSearchParams({ room });
    if (harness) q.set("harness", harness);
    fetch(`/api/models?${q}`).then((r) => r.json()).then((j) => { setModels(j.models ?? []); setDef(j.default ?? ""); setLive(Boolean(j.live)); }).catch(() => {});
  }, [room, harness, effectiveModel]);
  return { models, default: def, live };
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

function friendlyPatchError(e: unknown): string {
  const m = String(e instanceof Error ? e.message : e).replace(/^AcpError:\s*/, "");
  if (/rc=127|not installed/.test(m)) return "That agent is not in the room container. An admin needs to rebuild the sandbox image with this harness.";
  if (/TimeoutError|did not finish starting/i.test(m)) return "The agent did not start. Check Settings → Coding agents.";
  return m;
}

/** Which coding agent runs this room (Claude Code, Codex, OpenCode, ...). Switching starts a fresh conversation. */
export function HarnessPicker({ room, info, reload, onError }: { room: string; info: RoomInfo | null; reload: () => void; onError?: (m: string | null) => void }) {
  const admin = useIsAdmin(); // non-admins see the chip read-only (PATCH /api/rooms is admin-only)
  const { harnesses, default: def } = useHarnesses();
  const [busy, setBusy] = useState(false);
  const ready = harnesses.length > 0 && info !== null;  // no "default ( )" flash before the lists are in
  const current = info?.harness ?? def;
  const label = ready ? harnesses.find((h) => h.id === current)?.label ?? current : "…";
  const defaultLabel = harnesses.find((h) => h.id === def)?.label ?? def;
  async function change(id: string) {
    setBusy(true);
    onError?.(null);
    try {
      await patchRoom(room, { harness: id });
      reload();
    } catch (e) {
      onError?.(friendlyPatchError(e));
    } finally {
      setBusy(false);
    }
  }
  const pinned = Boolean(info?.harness_pinned);
  const what = `${pinned ? "Harness pinned for this room" : "Worker default harness"}: ${label}.`;
  return (
    <span className={`modelpick harnesspick${pinned ? " pinned" : ""}${admin ? "" : " readonly"}`} title={admin ? `${what} Click to change; a new harness starts a new conversation.` : `${what} Only admins can change it.`}>
      <BotIcon />
      <span className="pick-k">harness</span>
      <span className="modelname">{label}</span>
      {admin && <ChevronIcon />}
      {admin && (
        <select aria-label="coding agent for this room" value={info?.harness_pinned ?? ""} disabled={busy || !ready} onChange={(e) => void change(e.target.value)}>
          <option value="">{ready ? `default (${defaultLabel})` : "…"}</option>
          {harnesses.map((h) => <option key={h.id} value={h.id}>{h.label}</option>)}
        </select>
      )}
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
export function ModelPicker({ room, info, reload, onError }: { room: string; info: RoomInfo | null; reload: () => void; onError?: (m: string | null) => void }) {
  const admin = useIsAdmin();
  const { models, default: def, live } = useModels(room, info?.harness, info?.model);
  const [busy, setBusy] = useState(false);
  const current = info?.model ?? def;
  const label = models.find((m) => m.id === current)?.label ?? (current || "harness default");
  async function change(id: string) {
    setBusy(true);
    onError?.(null);
    try {
      await patchRoom(room, { model: id });
      reload();
    } catch (e) {
      onError?.(friendlyPatchError(e));
    } finally {
      setBusy(false);
    }
  }
  const pinned = Boolean(info?.model_pinned);
  const defaultLabel = models.find((m) => m.id === def)?.label ?? (def || "harness default");
  const source = live ? "reported by the agent" : "from the harness profile";
  const what = pinned ? `Model pinned for this room: ${label}.` : `Harness default: ${label}.`;
  return (
    <span className={`modelpick${pinned ? " pinned" : ""}${admin ? "" : " readonly"}`} title={admin ? `${what} ${pinned ? "Click to change." : `Click to pin a model for this room (list ${source}).`}` : `${what} Only admins can change it.`}>
      <CpuIcon />
      <span className="pick-k">model</span>
      <span className="modelname">{label}</span>
      {admin && <ChevronIcon />}
      {admin && (
        <select aria-label="model for this room" value={info?.model_pinned ?? ""} disabled={busy} onChange={(e) => void change(e.target.value)}>
          <option value="">{models.length ? `default (${defaultLabel})` : "harness default"}</option>
          {models.map((m) => <option key={m.id} value={m.id}>{m.label}{m.note ? ` · ${m.note}` : ""}</option>)}
        </select>
      )}
    </span>
  );
}

/** The project's repos (what the agent may read and edit, with roles) and the machine notes. Both change what the
 * agent can see and do, so only admins may edit them; the machine notes (a prompt-injection surface) are admin-only
 * even to read. */
export function RoomAndMachine({ room, info, reload }: { room: string; info: RoomInfo | null; reload: () => void }) {
  const admin = useIsAdmin();
  const [notes, setNotes] = useState<{ path: string; text: string } | null>(null);
  const [draft, setDraft] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [entries, setEntries] = useState<RepoEntry[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (admin) fetch("/api/notes").then((r) => r.json()).then((j) => { if (j.text !== undefined) { setNotes(j); setDraft(j.text); } }).catch(() => {});
  }, [admin]);
  // Start editing from what the room has; keep local edits until saved.
  useEffect(() => { if (info && entries === null) setEntries(info.repos.map(fromInfo)); }, [info, entries]);
  const saved = JSON.stringify(info?.repos.map((r) => [r.path, r.git_url, r.role, r.branch ?? ""]) ?? []);
  const current = JSON.stringify((entries ?? []).map((e) => [e.path ?? null, e.git_url ?? null, e.role, e.branch]));
  const dirty = entries !== null && saved !== current;
  async function saveRepos() {
    if (!entries) return;
    setBusy(true); setMsg(null);
    try {
      const r = await fetch(`/api/rooms/${encodeURIComponent(room)}`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ repos: toApi(entries) }) });
      if (!r.ok) throw new Error((await r.json()).error ?? r.statusText);
      setEntries(null); setAdding(false); reload();
      setMsg("Project updated. The agent restarts with the new repos; the conversation continues.");
    } catch (e) { setMsg(String(e instanceof Error ? e.message : e)); } finally { setBusy(false); }
  }
  async function saveNotes() {
    const r = await fetch("/api/notes", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ text: draft }) });
    setMsg(r.ok ? "Machine notes saved. Every room loads them at its next turn." : (await r.json()).error ?? r.statusText);
  }
  return (
    <>
      <Card>
        <h3>This project · {room}</h3>
        <Text>
          {info && info.repos.length > 1
            ? <>{info.repos.length} repos worked on together; the agent starts in <code>{info.repo}</code> and may read and edit all of them. Commits and PRs go to the repo each change belongs to.</>
            : <>Works in <code>{info?.repo ?? "…"}</code>. Add the other repos of this project (its API, a shared library) so the agent sees the whole thing.</>}
        </Text>
        <Text>
          {info?.sandbox
            ? <>The agent runs in its own container <code>{info.sandbox.container}</code> (image <code>{info.sandbox.image}</code>); only these repos are mounted into it.</>
            : <>The agent runs directly on this machine (no sandbox; set <code>MARVIN_SANDBOX=docker</code> to contain it).</>}
        </Text>
        {entries && <RepoList entries={entries} onChange={setEntries} readOnly={!admin} />}
        {admin && (
          <>
            {adding ? <RepoAdder exclude={entries ?? []} onAdd={(e) => { setEntries((cur) => [...(cur ?? []), e]); setAdding(false); }} /> : null}
            <Actions>
              <Button variant="ghost" onClick={() => setAdding((a) => !a)}>{adding ? "Close" : "Add repo"}</Button>
              <Button disabled={!dirty || busy || (entries?.length ?? 0) === 0} onClick={() => void saveRepos()}>{busy ? "Saving…" : "Save project"}</Button>
              {dirty && <Button variant="ghost" disabled={busy} onClick={() => { setEntries(null); setAdding(false); }}>Discard</Button>}
            </Actions>
          </>
        )}
        {!admin && <Text>Only admins can change the project's repos.</Text>}
      </Card>
      {admin && (
        <Card>
          <h3>Machine notes</h3>
          <Text>Loaded into every room on this machine ({notes?.path ?? "~/.claude/CLAUDE.md"}). How repos connect, fake accounts, ports, recipes. {agent.name} appends here when asked to remember something machine-wide.</Text>
          <Field label="Notes" wide>
            <Textarea rows={12} value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false} />
          </Field>
          <Actions>
            <Button onClick={() => void saveNotes()} disabled={notes === null || draft === notes.text}>Save notes</Button>
          </Actions>
        </Card>
      )}
      {msg && <Card><Text tone="ok">{msg}</Text></Card>}
    </>
  );
}

/** Who you are, how you were signed in, and (password mode) a way out. */
export function AccountSection() {
  const me = useMe();
  if (me.auth === "none") return null; // localhost dev: no account to speak of
  const how = me.auth === "header" ? "signed in by the identity proxy (SSO)" : "signed in with the room password";
  return (
    <Card>
      <h3>Account</h3>
      <Text>
        <b>{me.identity?.name ?? "?"}</b>{me.identity?.email ? ` · ${me.identity.email}` : ""} · {how} · roles: {me.identity?.roles.join(", ") || "none"}
      </Text>
      {me.auth === "password" && (
        <Actions><Button variant="ghost" onClick={() => void logout().then(() => location.reload())}>Log out</Button></Actions>
      )}
      {me.auth === "header" && <Text>To sign out, use your identity provider (for oauth2-proxy: <a href="/oauth2/sign_out">/oauth2/sign_out</a>).</Text>}
    </Card>
  );
}
