import { useContext, useEffect, useState, type ReactNode } from "react";
import { MeContext, isAdmin, logout } from "./auth";
import { ClientIdSetup, GitHubAuth, startGitHubApp, type Status as GitHubStatus } from "./GitHubConnect";
import { GrokLogin } from "./HarnessConnect";
import { MachineUpdate } from "./MachineUpdate";
import { RoomPicker } from "./RoomPicker";
import { SettingsPanel } from "./Settings";

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
  setName: (name: string) => void;
  agentName: string;
}) {
  const { me, setMe } = useContext(MeContext);
  const admin = isAdmin(me);
  const [room, setRoom] = useState(localStorage.getItem("marvin.room") ?? "");
  const [setup, setSetup] = useState<Setup | null>(null);
  const [github, setGitHub] = useState<GitHubStatus | null>(null);
  const [agentKey, setAgentKey] = useState("");
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [appError, setAppError] = useState<string | null>(null);
  const [personalOpen, setPersonalOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsFocus, setSettingsFocus] = useState<string | undefined>();

  const reload = () => {
    fetch("/api/setup").then((response) => response.json()).then((body) => { if (!body.error) setSetup(body); }).catch(() => {});
    fetch("/api/github/me").then((response) => response.json()).then((body) => { if (!body.error) setGitHub(body); }).catch(() => {});
  };
  useEffect(reload, [admin]);

  const saveClaude = async () => {
    setAgentBusy(true);
    setAgentError(null);
    try {
      const response = await fetch("/api/harness-creds/anthropic", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ key: agentKey }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error ?? `HTTP ${response.status}`);
      setAgentKey("");
      reload();
    } catch (cause) {
      setAgentError((cause as Error).message);
    } finally {
      setAgentBusy(false);
    }
  };

  const who = me.identity?.email || me.identity?.name || (needsName ? name : "you");
  const initials = who.split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "M";
  const machine = setup?.machine_github ?? null;
  const machineReady = Boolean(machine);
  const agentReady = Boolean(setup?.agent.ready);
  const locked = !machineReady || !agentReady || (needsName && !name);
  const canJoin = Boolean(room) && !locked;

  return (
    <main className="join-workspace">
      <aside className="join-rail">
        <Brand />
        <nav aria-label="Workspace">
          <button type="button" className="on"><GridIcon /> Projects</button>
          <button type="button" onClick={() => { setSettingsFocus("settings-sessions"); setSettingsOpen(true); }}><ClockIcon /> Sessions</button>
          <button type="button" onClick={() => { setSettingsFocus(undefined); setSettingsOpen(true); }}><GearIcon /> Machine settings</button>
        </nav>
        <div className="join-profile">
          <span>{initials}</span>
          <div><b>{me.identity?.name || who}</b><small>{admin ? "Administrator" : "Participant"}</small></div>
          {me.auth === "password" && (
            <button type="button" onClick={() => void logout().then(() => setMe({ ...me, identity: null }))}>Log out</button>
          )}
        </div>
      </aside>

      <form
        className="join-main"
        onSubmit={(event) => {
          event.preventDefault();
          if (!canJoin) return;
          localStorage.setItem("marvin.room", room);
          if (needsName) localStorage.setItem("marvin.name", name);
          onJoin(room, needsName ? name : null);
        }}
      >
        <header className="join-main-head">
          <div>
            <span>{setup?.ready ? `${agentName} is ready` : "Finish setting up this machine"}</span>
            <h1>Projects</h1>
          </div>
          {canJoin && <button type="submit" className="join-primary">Join {room}</button>}
        </header>

        {me.notice && <p className="join-notice"><LockIcon /> {me.notice}</p>}

        {needsName && (
          <label className="join-name">Your name <input value={name} onChange={(event) => setName(event.target.value)} required autoFocus /></label>
        )}

        <div className="join-content">
          <section className="join-projects">
            <h2>{room ? "Ready to continue" : "Choose a project"}</h2>
            <div className={locked ? "join-locked" : undefined} aria-disabled={locked || undefined}>
              <RoomPicker value={room} onPick={setRoom} locked={locked} />
            </div>
            {canJoin && (
              <button type="submit" className="join-project-cta">
                <span><i /> Join <b>{room}</b></span><ArrowIcon />
              </button>
            )}
            {locked && <p className="join-lock-reason">Projects unlock when this machine has GitHub and a coding agent.</p>}
            {error && <p className="error">{error}</p>}
          </section>

          <aside className="join-machine">
            <h2>This machine</h2>

            <SetupStatus ready={machineReady} title="GitHub" value={machine?.login ? `@${machine.login}` : machine?.name}>
              {!machineReady && admin && github && (
                <div className="join-setup">
                  {!github.configured && <ClientIdSetup status={github} onSaved={(status) => { setGitHub(status); reload(); }} />}
                  <button type="button" className="join-link" onClick={() => void startGitHubApp().then(setAppError)}>Create a GitHub App</button>
                  {appError && <p className="error small">{appError}</p>}
                  <GitHubAuth dest="machine" configured={github.configured} onDone={reload} />
                </div>
              )}
              {!machineReady && !admin && <small>Waiting on an administrator</small>}
            </SetupStatus>

            <SetupStatus ready={agentReady} title="Coding agent" value={setup?.agent.label}>
              {!agentReady && admin && (
                <div className="join-setup">
                  <GrokLogin onSaved={reload} />
                  <p className="dim small">Or use an Anthropic API key.</p>
                  <div className="join-key">
                    <input type="password" placeholder="sk-ant-…" value={agentKey} onChange={(event) => setAgentKey(event.target.value)} autoComplete="off" spellCheck={false} />
                    <button type="button" disabled={agentBusy || agentKey.trim().length < 12} onClick={() => void saveClaude()}>{agentBusy ? "Saving…" : "Save"}</button>
                  </div>
                  {agentError && <p className="error small">{agentError}</p>}
                </div>
              )}
              {!agentReady && !admin && <small>Waiting on an administrator</small>}
            </SetupStatus>

            <div className="join-personal">
              <span className={setup?.personal ? "ready" : ""}>{setup?.personal ? <CheckIcon /> : <UserIcon />}</span>
              <div>
                <b>Your GitHub</b>
                <small>{setup?.personal ? `@${setup.personal.login}` : "Optional"}</small>
              </div>
              {setup?.personal ? (
                <button type="button" className="join-link" onClick={() => void fetch("/api/github/me", { method: "DELETE" }).then(reload)}>Disconnect</button>
              ) : (
                <button type="button" className="join-link" onClick={() => setPersonalOpen((open) => !open)}>{personalOpen ? "Close" : "Connect"}</button>
              )}
            </div>
            {personalOpen && !setup?.personal && (
              <div className="join-setup personal">
                {admin && github && !github.configured && <ClientIdSetup status={github} onSaved={(status) => { setGitHub(status); reload(); }} />}
                <GitHubAuth dest="user" configured={Boolean(github?.configured)} onDone={() => { setPersonalOpen(false); reload(); }} />
              </div>
            )}

            {admin && <MachineUpdate compact />}
          </aside>
        </div>
      </form>
      {settingsOpen && <SettingsPanel focus={settingsFocus} onClose={() => setSettingsOpen(false)} />}
    </main>
  );
}

function Brand() {
  return <div className="join-brand"><span><i /></span><b>Marvin</b></div>;
}

function SetupStatus({ ready, title, value, children }: { ready: boolean; title: string; value?: string | null; children?: ReactNode }) {
  return (
    <section className={`join-status${ready ? " ready" : ""}`}>
      <span>{ready ? <CheckIcon /> : <AlertIcon />}</span>
      <div><b>{title}</b><small>{ready ? value : "Required"}</small></div>
      {children}
    </section>
  );
}

function Icon({ children }: { children: ReactNode }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>;
}
function CheckIcon() { return <Icon><path d="m5 12 4 4L19 6" /></Icon>; }
function AlertIcon() { return <Icon><circle cx="12" cy="12" r="9" /><path d="M12 8v5m0 3h.01" /></Icon>; }
function UserIcon() { return <Icon><circle cx="12" cy="8" r="3.5" /><path d="M5 20a7 7 0 0 1 14 0" /></Icon>; }
function LockIcon() { return <Icon><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></Icon>; }
function ArrowIcon() { return <Icon><path d="M5 12h14m-5-5 5 5-5 5" /></Icon>; }
function GridIcon() { return <Icon><rect x="4" y="4" width="6" height="6" rx="1" /><rect x="14" y="4" width="6" height="6" rx="1" /><rect x="4" y="14" width="6" height="6" rx="1" /><rect x="14" y="14" width="6" height="6" rx="1" /></Icon>; }
function ClockIcon() { return <Icon><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Icon>; }
function GearIcon() { return <Icon><circle cx="12" cy="12" r="3" /><path d="M19 12a7 7 0 0 0-.1-1l2-1.6-2-3.4-2.5 1A8 8 0 0 0 15 6l-.4-2.6h-4L10 6a8 8 0 0 0-1.5 1L6 6 4 9.4 6 11a7 7 0 0 0 0 2l-2 1.6L6 18l2.5-1A8 8 0 0 0 10 18l.5 2.6h4L15 18a8 8 0 0 0 1.5-1l2.5 1 2-3.4-2-1.6a7 7 0 0 0 0-1Z" /></Icon>; }
