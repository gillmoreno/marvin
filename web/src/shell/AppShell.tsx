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
  inProject,
  children,
}: {
  ee?: EnterpriseMark;
  section: "projects" | "settings";
  profile: ProfileInfo;
  lead?: ReactNode;
  onProjects: () => void;
  onSettings: () => void;
  room?: boolean;
  inProject?: boolean;
  children: ReactNode;
}) {
  const project = Boolean(room || inProject);
  return (
    <div className={`join-workspace app-shell${room ? " room-open" : ""}${project ? " in-project" : ""}`}>
      <Sidebar
        ee={ee}
        section={section}
        profile={profile}
        lead={lead}
        onProjects={onProjects}
        onSettings={onSettings}
        hidden={project}
      />
      <div className={`app-main${room ? " room-main" : ""}`}>{children}</div>
    </div>
  );
}
