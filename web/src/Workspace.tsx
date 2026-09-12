import { useEffect, useRef, useState } from "react";
import { ChangesPane } from "./ChangesPane";
import { ScreenShareView, screenShareKey, screenShareLabel, useScreenShares } from "./ScreenShare";
import type { ControlMessage } from "./protocol";
import type { ProjectRepoInfo } from "./ProjectRepos";

type Link = { label: string; url: string };

/** The centre of the room: the running app(s), shared screens and what changed, in tabs. Files come next. */
export function Workspace({ room, repos, appLinks, refreshKey, send, wanted, onShown }: { room: string; repos: ProjectRepoInfo[]; appLinks: Link[]; refreshKey: number; send: (m: ControlMessage) => void; wanted: string | null; onShown: () => void }) {
  const apps = appLinks.filter((l) => l.url);
  const screens = useScreenShares();
  const [active, setActive] = useState<string>("changes");
  const [reload, setReload] = useState(0);

  // A click on an App link in the left column opens it here.
  useEffect(() => {
    if (wanted) { setActive(`app:${wanted}`); onShown(); }
  }, [wanted, onShown]);
  // If the active app disappears (port closed), fall back to Changes.
  useEffect(() => {
    if (active.startsWith("app:") && !apps.some((a) => `app:${a.url}` === active)) setActive("changes");
  }, [apps, active]);
  // A screen that starts being shared takes the middle; when it stops, go back to Changes.
  const seenScreens = useRef<Set<string>>(new Set());
  useEffect(() => {
    const keys = screens.map(screenShareKey);
    const fresh = keys.find((k) => !seenScreens.current.has(k));
    seenScreens.current = new Set(keys);
    if (fresh) setActive(`screen:${fresh}`);
    else if (active.startsWith("screen:") && !keys.includes(active.slice("screen:".length))) setActive("changes");
  }, [screens, active]);

  const current = apps.find((a) => `app:${a.url}` === active);
  const screen = screens.find((t) => `screen:${screenShareKey(t)}` === active);
  return (
    <div className="workspace">
      <div className="ws-tabs">
        <button className={active === "changes" ? "on" : ""} onClick={() => setActive("changes")}>Changes</button>
        {screens.map((t) => {
          const key = `screen:${screenShareKey(t)}`;
          return (
            <button key={key} className={`${active === key ? "on" : ""} live`.trim()} onClick={() => setActive(key)}>
              <span className="dot rec" /> {screenShareLabel(t)}
            </button>
          );
        })}
        {apps.map((a) => (
          <button key={a.url} className={active === `app:${a.url}` ? "on" : ""} onClick={() => setActive(`app:${a.url}`)} title={a.url}>▶ {a.label}</button>
        ))}
        {current && (
          <span className="ws-actions">
            <span className="dim url">{current.url.replace(/^https?:\/\//, "")}</span>
            <button className="ghost" onClick={() => setReload((n) => n + 1)}>reload</button>
            <a className="ghost btn" href={current.url} target="_blank" rel="noreferrer">open in new tab</a>
          </span>
        )}
      </div>
      <div className="ws-body">
        {active === "changes" && <ChangesPane room={room} repos={repos} refreshKey={refreshKey} send={send} />}
        {screen && <ScreenShareView track={screen} />}
        {current && (
          <iframe key={`${current.url}#${reload}`} className="preview" src={current.url} title={current.label} sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals" />
        )}
      </div>
      {current && <p className="ws-foot dim">If the preview stays blank, the app refuses to be framed or is still starting. "Open in new tab" always works.</p>}
    </div>
  );
}
