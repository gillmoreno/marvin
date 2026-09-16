import { useContext, useEffect, useState, type ReactNode } from "react";
import { MeContext, isAdmin, logout } from "./auth";
import { ClientIdSetup, GitHubAuth, type Status as GitHubStatus } from "./GitHubConnect";
import { MachineSetup, type Setup } from "./MachineSetup";
import { MachineUpdate } from "./MachineUpdate";
import { RoomPicker } from "./RoomPicker";
import { SettingsPanel } from "./Settings";

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
  const [setupError, setSetupError] = useState(false);
  const [github, setGitHub] = useState<GitHubStatus | null>(null);
  const [personalOpen, setPersonalOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsFocus, setSettingsFocus] = useState<string | undefined>();

  const reload = () => {
    fetch("/api/setup")
      .then((response) => response.json())
      .then((body) => {
        if (body.error) { setSetupError(true); return; }
        setSetupError(false);
        setSetup(body);
      })
      .catch(() => setSetupError(true));
    fetch("/api/github/me")
      .then((response) => response.json())
      .then((body) => { if (!body.error) setGitHub(body); })
      .catch(() => {});
  };
  useEffect(() => {
    reload();
    const tick = window.setInterval(reload, 4000);
    return () => window.clearInterval(tick);
  }, [admin]);

  const who = me.identity?.email || me.identity?.name || name || "you";
  const display = me.identity?.name || who;
  const initials = who.split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "M";
  const canLogout = me.auth === "password";
  const onLogout = () => void logout().then(() => setMe({ ...me, identity: null }));

  if (!setup?.ready) {
    return (
      <MachineSetup
        admin={admin}
        who={display}
        role={admin ? "Administrator" : "Participant"}
        initials={initials}
        canLogout={canLogout}
        onLogout={onLogout}
        setup={setup}
        setupError={setupError}
        github={github}
        onGitHub={(status) => { setGitHub(status); reload(); }}
        reload={reload}
      />
    );
  }

  const canJoin = Boolean(room) && !(needsName && !name);

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
          <div><b>{display}</b><small>{admin ? "Administrator" : "Participant"}</small></div>
          {canLogout && <button type="button" onClick={onLogout}>Log out</button>}
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
            <span>{agentName} is ready</span>
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
            <RoomPicker value={room} onPick={setRoom} locked={false} />
            {canJoin && (
              <button type="submit" className="join-project-cta">
                <span><i /> Join <b>{room}</b></span><ArrowIcon />
              </button>
            )}
            {error && <p className="error">{error}</p>}
          </section>

          <aside className="join-machine">
            <h2>This machine</h2>
            <SetupStatus ready title="GitHub" value={setup.machine_github?.login ? `@${setup.machine_github.login}` : setup.machine_github?.name} />
            <SetupStatus ready title="Coding agent" value={setup.agent.label} />

            <div className="join-personal">
              <span className={setup.personal ? "ready" : ""}>{setup.personal ? <CheckIcon /> : <UserIcon />}</span>
              <div>
                <b>Your GitHub</b>
                <small>{setup.personal ? `@${setup.personal.login}` : "Optional"}</small>
              </div>
              {setup.personal ? (
                <button type="button" className="join-link" onClick={() => void fetch("/api/github/me", { method: "DELETE" }).then(reload)}>Disconnect</button>
              ) : (
                <button type="button" className="join-link" onClick={() => setPersonalOpen((open) => !open)}>{personalOpen ? "Close" : "Connect"}</button>
              )}
            </div>
            {personalOpen && !setup.personal && (
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

function SetupStatus({ ready, title, value }: { ready: boolean; title: string; value?: string | null }) {
  return (
    <section className={`join-status${ready ? " ready" : ""}`}>
      <span>{ready ? <CheckIcon /> : <AlertIcon />}</span>
      <div><b>{title}</b><small>{ready ? value : "Required"}</small></div>
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
