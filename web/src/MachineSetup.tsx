import { useEffect, useState } from "react";
import { ClientIdSetup, GitHubAuth, startGitHubApp, type Status as GitHubStatus } from "./GitHubConnect";
import { GrokLogin, KeyForm, type Status as HarnessStatus } from "./HarnessConnect";
import { LicensePaste } from "./License";

export type Setup = {
  ready: boolean;
  machine_github: { login: string | null; name: string; source: string } | null;
  agent: { ready: boolean; label: string | null; default_harness: string | null };
  personal: { login: string; name: string; email: string } | null;
  oauth_configured: boolean;
};

export function setupLead(admin: boolean, setup: Setup | null) {
  const done = (setup?.machine_github ? 1 : 0) + (setup?.agent.ready ? 1 : 0);
  return (
    <>
      <p className="setup-rail-copy">
        {admin
          ? "This machine cannot open a room until both required connections are in place."
          : "An administrator has to finish opening this machine."}
      </p>
      {admin && setup && <div className="setup-count">{done} of 2</div>}
    </>
  );
}

export function MachineSetup({
  admin, setup, setupError, github, onGitHub, reload,
}: {
  admin: boolean;
  setup: Setup | null;
  setupError: boolean;
  github: GitHubStatus | null;
  onGitHub: (status: GitHubStatus) => void;
  reload: () => void;
}) {
  const machine = setup?.machine_github ?? null;
  const machineReady = Boolean(machine);
  const agentReady = Boolean(setup?.agent.ready);

  return (
    <div className="join-main setup-main">
        {!admin ? (
          <Waiting />
        ) : setupError && !setup ? (
          <LoadError onRetry={reload} />
        ) : !setup ? (
          <>
            <p className="setup-eyebrow">Required</p>
            <h1>Checking this machine…</h1>
            <p className="setup-lead">Looking for a shared GitHub account and a coding agent.</p>
          </>
        ) : (
          <AdminSteps
            machine={machine}
            machineReady={machineReady}
            agentReady={agentReady}
            agentLabel={setup.agent.label}
            github={github}
            onGitHub={onGitHub}
            reload={reload}
          />
        )}
    </div>
  );
}

function AdminSteps({
  machine, machineReady, agentReady, agentLabel, github, onGitHub, reload,
}: {
  machine: Setup["machine_github"];
  machineReady: boolean;
  agentReady: boolean;
  agentLabel: string | null;
  github: GitHubStatus | null;
  onGitHub: (status: GitHubStatus) => void;
  reload: () => void;
}) {
  const [changeGithub, setChangeGithub] = useState(false);
  const [changeAgent, setChangeAgent] = useState(false);
  const [clientIdOpen, setClientIdOpen] = useState(false);
  const [appError, setAppError] = useState<string | null>(null);
  const agentLocked = !machineReady && !agentReady;
  const showGithubForm = !machineReady || changeGithub;
  const showAgentForm = (!agentReady || changeAgent) && !agentLocked;

  return (
    <>
      <p className="setup-eyebrow">Required</p>
      <h1>Open this machine.</h1>
      <p className="setup-lead">
        Connect the shared GitHub account first, then pick a coding agent. Projects stay hidden until both are done.
      </p>
      <div className="setup-steps">
        <section className={`setup-step${machineReady && !changeGithub ? " done" : ""}`}>
          <div className="setup-step-head">
            <span className="setup-num">{machineReady && !changeGithub ? "✓" : "1"}</span>
            <div>
              <h2>Machine GitHub</h2>
              <p>The shared account this machine uses to clone, branch, and open pull requests.</p>
            </div>
            <span className="setup-tag">{machineReady ? machineLabel(machine) : "Required"}</span>
          </div>
          <div className="setup-body">
            {machineReady && !changeGithub ? (
              <p>
                Connected as <b>{machineLabel(machine)}</b>
                {" · "}
                <button type="button" className="join-link" onClick={() => setChangeGithub(true)}>Change</button>
              </p>
            ) : github ? (
              <>
                <div className="setup-actions">
                  <GitHubAuth dest="machine" configured={github.configured} onDone={() => { setChangeGithub(false); reload(); }} />
                  <GithubAppButton onError={setAppError} />
                </div>
                {appError && <p className="error small">{appError}</p>}
                {!github.configured && (clientIdOpen ? (
                  <ClientIdSetup status={github} onSaved={onGitHub} />
                ) : (
                  <button type="button" className="join-link" onClick={() => setClientIdOpen(true)}>
                    Need device-code sign-in? Add an OAuth client id
                  </button>
                ))}
                {machineReady && (
                  <button type="button" className="join-link" onClick={() => setChangeGithub(false)}>Cancel</button>
                )}
              </>
            ) : (
              <p className="setup-note">Loading GitHub options…</p>
            )}
          </div>
        </section>

        <section className={`setup-step${agentReady && !changeAgent ? " done" : ""}${agentLocked ? " wait" : ""}`}>
          <div className="setup-step-head">
            <span className="setup-num">{agentReady && !changeAgent ? "✓" : "2"}</span>
            <div>
              <h2>Coding agent</h2>
              <p>At least one agent this machine can talk to. Rooms can pick another later.</p>
            </div>
            <span className="setup-tag">{agentReady ? (agentLabel ?? "Connected") : agentLocked ? "After GitHub" : "Required"}</span>
          </div>
          {agentLocked ? (
            <p className="setup-body setup-note">Connect GitHub first. Then choose an agent here.</p>
          ) : (
            <div className="setup-body">
              {agentReady && !changeAgent ? (
                <p>
                  Default agent is <b>{agentLabel ?? "connected"}</b>
                  {" · "}
                  <button type="button" className="join-link" onClick={() => setChangeAgent(true)}>Change</button>
                </p>
              ) : (
                <AgentConnect
                  onSaved={() => { setChangeAgent(false); reload(); }}
                  onCancel={agentReady ? () => setChangeAgent(false) : undefined}
                />
              )}
            </div>
          )}
        </section>
      </div>
    </>
  );
}

function GithubAppButton({ onError }: { onError: (message: string | null) => void }) {
  const [needLicense, setNeedLicense] = useState(false);
  const [busy, setBusy] = useState(false);

  const start = async () => {
    onError(null);
    setBusy(true);
    try {
      const status = await fetch("/api/license").then((response) => response.json());
      if (!status.valid) {
        setNeedLicense(true);
        return;
      }
      onError(await startGitHubApp());
    } catch (cause) {
      onError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button type="button" className="ghost" disabled={busy} onClick={() => void start()}>
        {busy ? "Starting…" : "Create a GitHub App"}
      </button>
      {needLicense && (
        <div className="setup-license">
          <p className="setup-note">A GitHub App needs an Enterprise license on this machine. Paste it here, then GitHub opens. No restart.</p>
          <LicensePaste onValid={() => { setNeedLicense(false); void startGitHubApp().then(onError); }} />
        </div>
      )}
    </>
  );
}

function AgentConnect({ onSaved, onCancel }: { onSaved: () => void; onCancel?: () => void }) {
  const [status, setStatus] = useState<HarnessStatus | null>(null);
  const [pick, setPick] = useState("grok");
  const [pasteKey, setPasteKey] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/harness-creds")
      .then((response) => response.json())
      .then((body) => {
        if (body.error) { setError(body.error); return; }
        const next = body as HarnessStatus;
        setStatus(next);
        const connectable = next.harnesses.filter((h) => next.providers.some((p) => p.harnesses.includes(h.id)));
        const preferred = connectable.some((h) => h.id === next.default_harness)
          ? next.default_harness
          : connectable.some((h) => h.id === "grok") ? "grok" : connectable[0]?.id;
        if (preferred) setPick(preferred);
      })
      .catch(() => setError("Could not load coding agents."));
  }, []);

  const connectable = status?.harnesses.filter((h) => status.providers.some((p) => p.harnesses.includes(h.id))) ?? [];
  const provider = status?.providers.find((p) => p.harnesses.includes(pick));
  const harness = connectable.find((h) => h.id === pick);
  const grok = provider?.subscription === "grok";

  const finish = async (next: HarnessStatus) => {
    setStatus(next);
    if (pick) {
      const response = await fetch("/api/harness-creds/default", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ harness: pick }),
      });
      if (response.ok) setStatus(await response.json());
    }
    onSaved();
  };

  if (error && !status) return <p className="error small">{error}</p>;
  if (!status) return <p className="setup-note">Loading agents…</p>;
  if (!provider) return <p className="setup-note">Pick an agent you can sign in to or paste a key for.</p>;

  return (
    <>
      <div className="setup-actions">
        <select value={pick} onChange={(event) => { setPick(event.target.value); setPasteKey(false); }}>
          {connectable.map((h) => <option key={h.id} value={h.id}>{h.label}</option>)}
        </select>
        {grok && !pasteKey && (
          <button type="button" className="ghost" onClick={() => setPasteKey(true)}>Paste API key</button>
        )}
        {onCancel && <button type="button" className="ghost" onClick={onCancel}>Cancel</button>}
      </div>
      {grok && !pasteKey ? (
        <>
          <GrokLogin onSaved={(next) => void finish(next)} />
          <p className="setup-note">Sign in with a grok.com subscription, or paste an xAI API key.</p>
        </>
      ) : (
        <>
          <KeyForm key={provider.id} p={provider} onSaved={(next) => void finish(next)} />
          <p className="setup-note">
            {harness ? `Paste a ${provider.label} key for ${harness.label}.` : provider.note || `Paste a ${provider.label} key.`}
          </p>
        </>
      )}
      {error && <p className="error small">{error}</p>}
    </>
  );
}

function Waiting() {
  return (
    <>
      <p className="setup-eyebrow">Waiting</p>
      <h1>This machine is not open yet.</h1>
      <div className="setup-waiting">
        <p>It still needs a shared GitHub account and a coding agent. Ask an administrator. There is nothing to join until both are connected.</p>
      </div>
    </>
  );
}

function LoadError({ onRetry }: { onRetry: () => void }) {
  return (
    <>
      <p className="setup-eyebrow">Waiting</p>
      <h1>Could not reach this machine.</h1>
      <div className="setup-waiting">
        <p>Setup status is not answering. Check that the worker is running, then try again.</p>
        <button type="button" onClick={onRetry}>Try again</button>
      </div>
    </>
  );
}

function machineLabel(machine: Setup["machine_github"]): string {
  if (!machine) return "Connected";
  return machine.login ? `@${machine.login}` : machine.name;
}
