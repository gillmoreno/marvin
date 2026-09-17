import { useEffect, useState, type ReactNode } from "react";
import { GearIcon, GridIcon } from "../icons";
import { Brand, type EnterpriseMark } from "./Brand";
import { Profile, type ProfileInfo } from "./Profile";

const RAIL_KEY = "marvin.rail";

function useRailCollapsed() {
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(RAIL_KEY) === "1"; } catch { return false; }
  });
  useEffect(() => {
    try { localStorage.setItem(RAIL_KEY, collapsed ? "1" : "0"); } catch { /* private mode */ }
  }, [collapsed]);
  return [collapsed, setCollapsed] as const;
}

function RailLink({ href, on, onClick, label, children }: { href: string; on: boolean; onClick: () => void; label: string; children: ReactNode }) {
  return (
    <a
      href={href}
      className={on ? "on" : ""}
      title={label}
      onClick={(event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
        event.preventDefault();
        onClick();
      }}
    >
      {children}
      <span className="rail-label">{label}</span>
    </a>
  );
}

export function Sidebar({
  ee,
  section,
  profile,
  lead,
  onProjects,
  onSettings,
}: {
  ee?: EnterpriseMark;
  section: "projects" | "settings";
  profile: ProfileInfo;
  lead?: ReactNode;
  onProjects: () => void;
  onSettings: () => void;
}) {
  const [collapsed, setCollapsed] = useRailCollapsed();
  return (
    <aside id="marvin-rail" className={`join-rail${collapsed ? " collapsed" : ""}`}>
      <Brand ee={ee} collapsed={collapsed} onToggle={() => setCollapsed((on) => !on)} />
      {lead}
      <nav aria-label="Workspace">
        <RailLink href="/projects" on={section === "projects"} onClick={onProjects} label="Projects"><GridIcon /></RailLink>
        <RailLink href="/settings" on={section === "settings"} onClick={onSettings} label="Settings"><GearIcon /></RailLink>
      </nav>
      <Profile {...profile} />
    </aside>
  );
}
