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
    const [room, rest] = clean.slice("/projects/".length).split("/");
    if (room && rest === "settings") return { page: "settings", room, settingsPane: "room" };
    if (room) return { page: "room", room, settingsPane: null };
  }
  return { page: "projects", room: null, settingsPane: null };
}

export function pathFor(loc: AppLoc, _hasRoom = false): string {
  if (loc.page === "settings") {
    if (loc.room) return `/projects/${loc.room}/settings`;
    const pane = loc.settingsPane ?? "signin";
    if (pane === "signin" || pane === "room") return "/settings";
    return `/settings/${pane}`;
  }
  if (loc.page === "room" && loc.room) return `/projects/${loc.room}`;
  return "/projects";
}

const OPEN_ROOMS_KEY = "marvin.openRooms";

function loadOpenRooms(): string[] {
  try {
    const raw = JSON.parse(sessionStorage.getItem(OPEN_ROOMS_KEY) || "[]");
    if (!Array.isArray(raw)) return [];
    return raw.filter((item): item is string => typeof item === "string" && item.length > 0);
  } catch {
    return [];
  }
}

function saveOpenRooms(rooms: string[]) {
  try { sessionStorage.setItem(OPEN_ROOMS_KEY, JSON.stringify(rooms)); } catch { /* private mode */ }
}

export type AppNav = {
  page: AppPage;
  room: string | null;
  settingsPane: SettingsPane;
  openRooms: string[];
  openProject: (room: string) => void;
  goProjects: () => void;
  openSettings: (pane?: SettingsPane) => void;
  openRoomSettings: (room: string) => void;
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
  const [openRooms, setOpenRooms] = useState(loadOpenRooms);
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
  const rawPane = loc.settingsPane ?? (loc.room ? "room" : "signin");
  const settingsPane = rawPane === "room" && !loc.room ? "signin" : rawPane;

  useEffect(() => {
    if (!loc.room) return;
    setOpenRooms((prev) => {
      if (prev[0] === loc.room) return prev;
      const next = [loc.room!, ...prev.filter((name) => name !== loc.room)];
      saveOpenRooms(next);
      return next;
    });
  }, [loc.room]);

  useEffect(() => {
    const previous = document.title;
    if (page === "settings" && loc.room) document.title = `#${loc.room} settings · Marvin`;
    else if (page === "settings") document.title = "Settings · Marvin";
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
    openRooms,
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
      const nextPane = pane && pane !== "room" ? pane : "signin";
      apply(
        { page: "settings", room: null, settingsPane: nextPane === "signin" ? null : nextPane },
        page === "settings" && !loc.room ? "replace" : "push",
      );
    },
    openRoomSettings: (room: string) => apply(
      { page: "settings", room, settingsPane: "room" },
      page === "settings" && loc.room === room ? "replace" : "push",
    ),
    setSettingsPane: (pane: SettingsPane) => {
      const nextPane = pane === "room" ? "signin" : pane;
      apply({ page: "settings", room: null, settingsPane: nextPane === "signin" ? null : nextPane }, "replace");
    },
  };
}
