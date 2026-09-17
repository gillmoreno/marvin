import { createContext, useContext, useEffect, useState } from "react";

export const SETTINGS_PANES = ["room", "signin", "github", "agents", "sessions", "audit", "license", "machine"] as const;
export type SettingsPane = (typeof SETTINGS_PANES)[number];
export type AppPage = "projects" | "room" | "settings";

export type AppLoc = {
  page: AppPage;
  room: string | null;
  settingsPane: SettingsPane | null;
};

const MARK = "marvin";

export function locFromPath(path = typeof location === "undefined" ? "/" : location.pathname): AppLoc {
  const clean = path.replace(/\/+$/, "") || "/";
  if (clean === "/settings") return { page: "settings", room: null, settingsPane: null };
  if (clean.startsWith("/settings/")) {
    const id = clean.slice("/settings/".length).split("/")[0];
    return { page: "settings", room: null, settingsPane: (SETTINGS_PANES as readonly string[]).includes(id) ? (id as SettingsPane) : null };
  }
  if (clean.startsWith("/projects/")) {
    const room = clean.slice("/projects/".length).split("/")[0];
    if (room) return { page: "room", room, settingsPane: null };
  }
  return { page: "projects", room: null, settingsPane: null };
}

export function pathFor(loc: AppLoc, hasRoom = false): string {
  if (loc.page === "settings") {
    const pane = loc.settingsPane ?? (hasRoom ? "room" : "signin");
    if (pane === "signin" && !hasRoom) return "/settings";
    return `/settings/${pane}`;
  }
  if (loc.page === "room" && loc.room) return `/projects/${loc.room}`;
  return "/projects";
}

export type AppNav = {
  page: AppPage;
  room: string | null;
  settingsPane: SettingsPane;
  openProject: (room: string) => void;
  goProjects: () => void;
  openSettings: (pane?: SettingsPane) => void;
  setSettingsPane: (pane: SettingsPane) => void;
};

export const AppNavContext = createContext<AppNav | null>(null);

export function useAppNav(): AppNav {
  const nav = useContext(AppNavContext);
  if (!nav) throw new Error("useAppNav needs AppNavProvider");
  return nav;
}

export function useAppNavState(hasRoom = false): AppNav {
  const [loc, setLoc] = useState(() => locFromPath());
  useEffect(() => {
    const onPop = () => setLoc(locFromPath());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    if (location.pathname === "/" || location.pathname === "") {
      history.replaceState({ [MARK]: "projects" }, "", "/projects");
    }
  }, []);

  const page = loc.page;
  const rawPane = loc.settingsPane ?? (hasRoom ? "room" : "signin");
  const settingsPane = rawPane === "room" && !hasRoom ? "signin" : rawPane;

  useEffect(() => {
    const previous = document.title;
    if (page === "settings") document.title = "Settings · Marvin";
    else if (page === "room" && loc.room) document.title = `#${loc.room} · Marvin`;
    else document.title = "Marvin";
    return () => { document.title = previous; };
  }, [page, loc.room]);

  const apply = (next: AppLoc, mode: "push" | "replace") => {
    const path = pathFor(next, hasRoom);
    const state = { [MARK]: next.page };
    if (mode === "replace") history.replaceState(state, "", path);
    else history.pushState(state, "", path);
    setLoc(next);
  };

  return {
    page,
    room: loc.room,
    settingsPane,
    openProject: (room: string) => apply({ page: "room", room, settingsPane: null }, page === "room" ? "replace" : "push"),
    goProjects: () => {
      if (page === "projects") {
        if (location.pathname !== "/projects") apply({ page: "projects", room: null, settingsPane: null }, "replace");
        return;
      }
      if (history.state?.[MARK] === "room" || (history.state?.[MARK] === "settings" && !hasRoom)) {
        history.back();
        return;
      }
      apply({ page: "projects", room: null, settingsPane: null }, "replace");
    },
    openSettings: (pane?: SettingsPane) => {
      const nextPane = pane ?? (hasRoom ? "room" : "signin");
      apply({ page: "settings", room: null, settingsPane: nextPane === "signin" && !hasRoom ? null : nextPane }, page === "settings" ? "replace" : "push");
    },
    setSettingsPane: (pane: SettingsPane) => apply({ page: "settings", room: null, settingsPane: pane === "signin" && !hasRoom ? null : pane }, "replace"),
  };
}
