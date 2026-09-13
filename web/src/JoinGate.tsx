import { useContext, useEffect, useState } from "react";
import { MeContext, isAdmin, logout } from "./auth";
import { ClientIdSetup, GitHubAuth, type Status as GitHubStatus } from "./GitHubConnect";
import { GrokLogin } from "./HarnessConnect";
import { RoomPicker } from "./RoomPicker";

type Setup = {
  ready: boolean;
  machine_github: { login: string | null; name: string; source: string } | null;
  agent: { ready: boolean; label: string | null; default_harness: string | null };
  personal: { login: string; name: string; email: string } | null;
  oauth_configured: boolean;
};

export function JoinGate({
  onJoin, error, needsName, name, setName, agentName,
}: {
  onJoin: (room: string, name: string | null) => void;
  error: string | null;
  needsName: boolean;
  name: string;
  setName: (n: string) => void;
  agentName: string;
}) {
  const { me, setMe } = useContext(MeContext);
  const admin = isAdmin(me);
  const [room, setRoom] = useState(localStorage.getItem("marvin.room") ?? "");
  const [setup, setSetup] = useState<Setup | null>(null);
  const [gh, setGh] = useState<GitHubStatus | null>(null);
  const [agentKey, setAgentKey] = useState("");
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentErr, setAgentErr] = useState<string | null>(null);

  const reload = () => {
    fetch("/api/setup").then((r) => r.json()).then((j) => { if (!j.error) setSetup(j); }).catch(() => {});
    fetch("/api/github/me").then((r) => r.json()).then((j) => { if (!j.error) setGh(j); }).catch(() => {});
  };
  useEffect(reload, [admin]);

  const saveClaude = async () => {
    setAgentBusy(true); setAgentErr(null);
    try {
      const r = await fetch("/api/harness-creds/anthropic", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ key: agentKey }) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error ?? `HTTP ${r.status}`);
      setAgentKey("");
      reload();
    } catch (e) { setAgentErr((e as Error).message); } finally { setAgentBusy(false); }
  };

  const who = me.identity?.email || me.identity?.name || (needsName ? name : "you");
  const machine = setup?.machine_github ?? null;
  const machineOk = Boolean(machine);
  const agentOk = Boolean(setup?.agent.ready);
  const locked = !machineOk || !agentOk || (needsName && !name);
  const canJoin = Boolean(room) && !locked;

  return (
    <form
      className="join gate"
      onSubmit={(e) => {
        e.preventDefault();
        if (!canJoin) return;
        localStorage.setItem("marvin.room", room);
        if (needsName) localStorage.setItem("marvin.name", name);
        onJoin(room, needsName ? name : null);
      }}
    >
      <h1>Marvin</h1>
      <p>A voice room with a coding agent in it. Say "{agentName}" to talk to it. This machine needs a GitHub account and an agent. Your own GitHub is optional.</p>

      {needsName ? (
        <label>Your name <input value={name} onChange={(e) => setName(e.target.value)} required autoFocus /></label>
      ) : (
        <p className="signedin">
          You’re logged in as <b>{who}</b>{isAdmin(me) && <span className="badge">admin</span>}
          {me.auth === "password" && (
            <button type="button" className="ghost" onClick={() => void logout().then(() => setMe({ ...me, identity: null }))}>log out</button>
          )}
        </p>
      )}

      <ol className="join-steps">
        <li className={machineOk ? "done" : ""}>
          <h3>This machine’s GitHub</h3>
          <p className="dim small">{machineOk
            ? <>Shared account{machine!.login ? <> <b>@{machine!.login}</b></> : null}{machine!.source === "env" ? " (from the environment)" : ""} · commits say Marvin unless you attach your own GitHub.</>
            : "Required. One account for the box. An admin sets this once."}</p>
          {!machineOk && admin && gh && (
            <>
              {!gh.configured && <ClientIdSetup status={gh} onSaved={(s) => { setGh(s); reload(); }} />}
              <GitHubAuth dest="machine" configured={gh.configured} onDone={reload} />
            </>
          )}
          {!machineOk && !admin && <p className="dim small">Waiting on an admin.</p>}
        </li>
        <li className={agentOk ? "done" : ""}>
          <h3>A coding agent</h3>
          <p className="dim small">{agentOk
            ? <>This machine talks to <b>{setup!.agent.label}</b>.</>
            : (admin ? "Required. One provider is enough to start. Without this, talking does nothing." : "Waiting on an admin.")}</p>
          {!agentOk && admin && (
            <>
              <GrokLogin onSaved={() => reload()} />
              <div className="github-setup">
                <p className="dim small">Or paste an Anthropic API key. Other providers stay in Settings.</p>
                <div className="row">
                  <input type="password" placeholder="sk-ant-…" value={agentKey} onChange={(e) => setAgentKey(e.target.value)} autoComplete="off" spellCheck={false} />
                  <button type="button" disabled={agentBusy || agentKey.trim().length < 12} onClick={() => void saveClaude()}>save</button>
                </div>
                {agentErr && <p className="error small">{agentErr}</p>}
              </div>
            </>
          )}
        </li>
        <li className={`opt${setup?.personal ? " done" : ""}`}>
          <h3>Your GitHub <span className="badge">optional</span></h3>
          <p className="dim small">{setup?.personal
            ? <>Your turns will push as <b>@{setup.personal.login}</b>.</>
            : <>Skip this. You’re logged in as <b>{who}</b>. Connect only if you want your name on the git author line.</>}</p>
          {setup?.personal
            ? <p className="dim small"><a href="#" onClick={(e) => { e.preventDefault(); void fetch("/api/github/me", { method: "DELETE" }).then(reload); }}>use the machine account instead</a></p>
            : (
              <>
                {admin && gh && !gh.configured && <ClientIdSetup status={gh} onSaved={(s) => { setGh(s); reload(); }} />}
                <GitHubAuth dest="user" configured={Boolean(gh?.configured)} onDone={reload} />
              </>
            )}
        </li>
      </ol>

      <div className={locked ? "join-locked" : undefined} aria-disabled={locked || undefined}>
        <RoomPicker value={room} onPick={setRoom} locked={locked} />
      </div>
      <button type="submit" disabled={!canJoin}>Join {room || "a room"}</button>
      {locked && <p className="lock-reason">Join waits on this machine’s GitHub and a coding agent — never on your GitHub.</p>}
      {error && <p className="error">{error}</p>}
    </form>
  );
}
