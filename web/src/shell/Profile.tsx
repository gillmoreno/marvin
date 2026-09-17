import { useContext } from "react";
import { MeContext, isAdmin, logout } from "../auth";

export type ProfileInfo = {
  display: string;
  initials: string;
  role: string;
  admin: boolean;
  canLogout: boolean;
  onLogout: () => void;
};

export function useProfile(fallbackName = ""): ProfileInfo {
  const { me, setMe } = useContext(MeContext);
  const admin = isAdmin(me);
  const who = me.identity?.email || me.identity?.name || fallbackName || "you";
  const display = me.identity?.name || who;
  const initials = who.split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "M";
  const canLogout = (me.auth === "password" || me.auth === "header") && Boolean(me.identity);
  return {
    display,
    initials,
    role: admin ? "Administrator" : "Participant",
    admin,
    canLogout,
    onLogout: () => {
      if (me.auth === "header") { location.href = "/oauth2/sign_out"; return; }
      void logout().then(() => setMe({ ...me, identity: null }));
    },
  };
}

export function Profile({ display, initials, role, canLogout, onLogout }: ProfileInfo) {
  return (
    <div className="join-profile">
      <span>{initials}</span>
      <div><b>{display}</b><small>{role}</small></div>
      {canLogout && <button type="button" onClick={onLogout}>Log out</button>}
    </div>
  );
}
