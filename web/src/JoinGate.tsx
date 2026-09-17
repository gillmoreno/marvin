import { useContext, useEffect, useState, type ReactNode } from "react";
import { MeContext, isAdmin } from "./auth";
import { ClientIdSetup, GitHubAuth, type Status as GitHubStatus } from "./GitHubConnect";
import { MachineSetup, setupLead, type Setup } from "./MachineSetup";
import { MachineUpdate } from "./MachineUpdate";
import { RoomPicker } from "./RoomPicker";
import { SettingsPage } from "./Settings";
import { useEnterprise } from "./License";
import { useAppNav } from "./nav";
import { AppShell, useProfile } from "./shell";

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
  const { me } = useContext(MeContext);
  const admin = isAdmin(me);
  const [room, setRoom] = useState(localStorage.getItem("marvin.room") ?? "");
  const [setup, setSetup] = useState<Setup | null>(null);
  const [setupError, setSetupError] = useState(false);
  const [github, setGitHub] = useState<GitHubStatus | null>(null);
  const [personalOpen, setPersonalOpen] = useState(false);
  const nav = useAppNav();
  const ee = useEnterprise();
  const profile = useProfile(name);

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

  const shell = (children: ReactNode, lead?: ReactNode) => (
    <AppShell
      ee={ee}
      section={nav.page === "settings" ? "settings" : "projects"}
      profile={profile}
      lead={lead}
      onProjects={nav.goProjects}
      onSettings={() => nav.openSettings()}
    >
      {children}
    </AppShell>
  );

  if (nav.page === "settings") {
    return shell(<SettingsPage pane={nav.settingsPane} onPane={nav.setSettingsPane} />, setup?.ready ? undefined : setupLead(admin, setup));
  }

  if (!setup?.ready) {
    return shell(
      <MachineSetup
        admin={admin}
        setup={setup}
        setupError={setupError}
        github={github}
        onGitHub={(status) => { setGitHub(status); reload(); }}
        reload={reload}
      />,
      setupLead(admin, setup),
    );
  }

  if (nav.page === "room" && nav.room) {
    return shell(
      <div className="join-main">
        <p className="hint">Joining {nav.room}…</p>
        {error && <p className="error">{error}</p>}
      </div>,
    );
  }

  const join = (next: string) => {
    localStorage.setItem("marvin.room", next);
    if (needsName) localStorage.setItem("marvin.name", name);
    onJoin(next, needsName ? name : null);
  };
  const canJoin = Boolean(room) && !(needsName && !name);

  return shell(
    <form
      className="join-main"
      onSubmit={(event) => {
        event.preventDefault();
        if (!canJoin) return;
        join(room);
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
          <RoomPicker
            value={room}
            onPick={(next) => {
              setRoom(next);
              if (!(needsName && !name)) join(next);
            }}
            locked={false}
            onOpenSettings={() => nav.openSettings("github")}
          />
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
    </form>,
  );
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
