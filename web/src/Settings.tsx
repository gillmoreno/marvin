import { useEffect, useState, type ReactNode } from "react";
import { agent } from "./agent";
import { useIsAdmin } from "./auth";
import { AccountSection } from "./RoomSettings";
import { GitHubSection } from "./GitHubConnect";
import { HarnessSection } from "./HarnessConnect";
import { AccessSection } from "./AccessSection";
import { ExportSection, SessionsSection } from "./Sessions";
import { LicenseSection, useEnterprise } from "./License";
import { MachineUpdate } from "./MachineUpdate";
import type { SettingsPane } from "./nav";
import { Actions, Button, Card, Text } from "./ui";

const MACHINE_PANES: { id: SettingsPane; label: string }[] = [
  { id: "signin", label: "Sign-in" },
  { id: "github", label: "GitHub" },
  { id: "agents", label: "Coding agents" },
  { id: "sessions", label: "Sessions" },
  { id: "audit", label: "Audit export" },
  { id: "license", label: "Enterprise" },
  { id: "machine", label: "This machine" },
];

/** Sleep the whole machine (scale to zero). Only meaningful on the cluster, where /power is served by the gate. */
export function PowerSection() {
  const [state, setState] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    fetch("/power/status").then((r) => (r.ok ? r.json() : null)).then((j) => setState(j?.state ?? null)).catch(() => setState(null));
  }, []);
  if (state === null) return null;
  async function sleep() {
    if (!confirm(`Put ${agent.name} to sleep? Everyone in every room gets disconnected. The machine wakes from the same URL, or on the morning schedule.`)) return;
    const r = await fetch("/power/sleep", { method: "POST" });
    setMsg(r.ok ? "Going to sleep. This page will stop responding in a moment." : "Could not sleep: " + r.statusText);
  }
  return (
    <Card>
      <h3>Machine power</h3>
      <Text>State: <b>{state}</b>. Sleeping scales everything to zero (volumes stay), which drops the GPU node and its cost. The URL then shows a Wake button.</Text>
      <Actions><Button variant="danger" onClick={() => void sleep()}>Put {agent.name} to sleep</Button></Actions>
      {msg && <Text tone="ok">{msg}</Text>}
    </Card>
  );
}

function AppPreviewsSection() {
  const admin = useIsAdmin();
  const [pattern, setPattern] = useState<string | null>(null);
  const [host, setHost] = useState<string | null>(null);
  useEffect(() => {
    fetch("/api/agent").then((r) => r.json()).then((j) => {
      setHost(typeof j.public_host === "string" ? j.public_host : null);
      setPattern(typeof j.preview_pattern === "string" ? j.preview_pattern : null);
    }).catch(() => {});
  }, []);
  if (!admin) return null;
  return (
    <Card>
      <h3>App previews</h3>
      {pattern && host ? (
        <>
          <Text>This machine is <code>{host}</code>. A port the agent opens is <code>{pattern}</code> — so port 3000 is <code>{pattern.replace("{port}", "3000")}</code>.</Text>
          <Text>
            DNS: an A record for <code>{host}</code> and for <code>*.{host}</code>, both pointing at this VM, DNS-only (not proxied).
            The name is this install&apos;s hostname (<code>MARVIN_DOMAIN</code>), not a Marvin-wide domain.
          </Text>
        </>
      ) : (
        <Text>No public hostname on this machine, so previews are <code>http://localhost:&lt;port&gt;</code>. Set <code>MARVIN_DOMAIN</code> (and a <code>*.that-name</code> DNS record) for HTTPS links other people can open.</Text>
      )}
    </Card>
  );
}

export function SettingsPage({ extra, room, pane, onPane }: {
  extra?: ReactNode;
  room?: string;
  pane: SettingsPane;
  onPane: (pane: SettingsPane) => void;
}) {
  const admin = useIsAdmin();
  const ent = useEnterprise();
  const hasRoom = Boolean(extra);
  const panes = hasRoom ? [{ id: "room" as SettingsPane, label: "This room" }, ...MACHINE_PANES] : MACHINE_PANES;

  return (
    <div className="settings-page">
      <header className="join-main-head">
        <div>
          <span>{room ? `#${room}` : "This machine"}</span>
          <h1>Settings</h1>
        </div>
      </header>
      <div className="settings-body">
        <nav className="settings-nav" aria-label="Settings">
          {panes.map((item) => (
            <a
              key={item.id}
              href={`/settings/${item.id}`}
              className={pane === item.id ? "on" : ""}
              onClick={(event) => {
                if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
                event.preventDefault();
                onPane(item.id);
              }}
            >
              {item.label}{(item.id === "audit" || item.id === "signin") && !ent.ee ? " 🔒" : ""}
            </a>
          ))}
        </nav>
        <div className="settings-pane">
          {pane === "room" && extra}
          {pane === "signin" && <><AccountSection /><AccessSection /></>}
          {pane === "github" && <GitHubSection />}
          {pane === "agents" && <HarnessSection />}
          {pane === "sessions" && <div id="settings-sessions"><SessionsSection /></div>}
          {pane === "audit" && <ExportSection />}
          {pane === "license" && <LicenseSection />}
          {pane === "machine" && (
            <>
              <AppPreviewsSection />
              {admin && <Card><h3>This machine</h3><MachineUpdate /></Card>}
              <PowerSection />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
