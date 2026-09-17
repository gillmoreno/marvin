import { type ReactNode } from "react";
import { AppNavContext, useAppNavState } from "../nav";
import { type EnterpriseMark } from "./Brand";
import { type ProfileInfo } from "./Profile";
import { Sidebar } from "./Sidebar";

export function AppNavProvider({ hasRoom, children }: { hasRoom: boolean; children: ReactNode }) {
  const nav = useAppNavState(hasRoom);
  return <AppNavContext.Provider value={nav}>{children}</AppNavContext.Provider>;
}

export function AppShell({
  ee,
  section,
  profile,
  lead,
  onProjects,
  onSettings,
  room,
  children,
}: {
  ee?: EnterpriseMark;
  section: "projects" | "settings";
  profile: ProfileInfo;
  lead?: ReactNode;
  onProjects: () => void;
  onSettings: () => void;
  room?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={`join-workspace app-shell${room ? " room-open" : ""}`}>
      <Sidebar
        ee={ee}
        section={section}
        profile={profile}
        lead={lead}
        onProjects={onProjects}
        onSettings={onSettings}
      />
      <div className={`app-main${room ? " room-main" : ""}`}>{children}</div>
    </div>
  );
}
