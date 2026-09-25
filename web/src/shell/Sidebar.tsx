import { useEffect, useState, type ReactNode } from "react";
import { GearIcon, GridIcon } from "../icons";
import { useAppNav } from "../nav";
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

function RailLink({ href, on, onClick, label, className, children }: { href: string; on: boolean; onClick: () => void; label: string; className?: string; children: ReactNode }) {
  return (
    <a
      href={href}
      className={[className, on ? "on" : ""].filter(Boolean).join(" ")}
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
  section: _section,
  profile,
  lead,
  onProjects,
  onSettings,
  hidden,
}: {
  ee?: EnterpriseMark;
  section: "projects" | "settings";
  profile: ProfileInfo;
  lead?: ReactNode;
  onProjects: () => void;
  onSettings: () => void;
  hidden?: boolean;
}) {
  const nav = useAppNav();
  const [collapsed, setCollapsed] = useRailCollapsed();
  const generalSettings = nav.page === "settings" && !nav.room;
  return (
    <aside id="marvin-rail" className={`join-rail${collapsed ? " collapsed" : ""}`} aria-hidden={hidden || undefined} inert={hidden || undefined}>
      <Brand ee={ee} collapsed={collapsed} onToggle={() => setCollapsed((on) => !on)} />
      {lead}
      <nav aria-label="Workspace">
        <RailLink href="/projects" on={nav.page === "projects"} onClick={onProjects} label="Projects"><GridIcon /></RailLink>
        {nav.openRooms.length > 0 && (
          <div className="rail-rooms">
            {nav.openRooms.map((room) => {
              const here = nav.room === room && (nav.page === "room" || nav.page === "settings");
              return (
                <RailLink key={room} href={`/projects/${room}`} on={here} onClick={() => nav.openProject(room)} label={room} className="rail-room-link">
                  <span className="rail-hash" aria-hidden>#</span>
                </RailLink>
              );
            })}
          </div>
        )}
      </nav>
      <div className="rail-foot">
        <nav aria-label="Settings">
          <RailLink href="/settings" on={generalSettings} onClick={onSettings} label="Settings"><GearIcon /></RailLink>
        </nav>
        <Profile {...profile} />
      </div>
    </aside>
  );
}
