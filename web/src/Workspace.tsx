import { useEffect, useState } from "react";
import { ChangesPane } from "./ChangesPane";
import type { ControlMessage } from "./protocol";

type Link = { label: string; url: string };

/** The centre of the room: the running app(s) and what changed, in tabs. Files come next. */
export function Workspace({ room, appLinks, refreshKey, send, wanted, onShown }: { room: string; appLinks: Link[]; refreshKey: number; send: (m: ControlMessage) => void; wanted: string | null; onShown: () => void }) {
  const apps = appLinks.filter((l) => l.url);
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

  const current = apps.find((a) => `app:${a.url}` === active);
  return (
    <div className="workspace">
      <div className="ws-tabs">
        <button className={active === "changes" ? "on" : ""} onClick={() => setActive("changes")}>Changes</button>
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
        {active === "changes" && <ChangesPane room={room} refreshKey={refreshKey} send={send} />}
        {current && (
          <iframe key={`${current.url}#${reload}`} className="preview" src={current.url} title={current.label} sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals" />
        )}
      </div>
      {current && <p className="ws-foot dim">If the preview stays blank, the app refuses to be framed or is still starting. "Open in new tab" always works.</p>}
    </div>
  );
}
