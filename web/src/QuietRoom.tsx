import { useEffect, useMemo, useRef, useState } from "react";
import { ControlBar, StartAudio } from "@livekit/components-react";
import { agent } from "./agent";
import { useChanges, type ChangedFile } from "./ChangesPane";
import { MarvinPane } from "./MarvinPane";
import { People } from "./People";
import type { ProjectRepoInfo } from "./ProjectRepos";
import { ScreenShareView, screenShareKey, screenShareLabel, useScreenShares } from "./ScreenShare";
import { Transcript } from "./Transcript";
import type { useMarvin } from "./useMarvin";
import { DiffView } from "./DiffView";
import { BrandLogo } from "./shell";

type Node = { name: string; path: string; dir: boolean; children: Node[]; file?: ChangedFile };

function buildTree(files: ChangedFile[]): Node[] {
  const root: Node[] = [];
  for (const file of files) {
    const parts = file.path.split("/");
    let level = root;
    let acc = "";
    parts.forEach((part, i) => {
      acc = acc ? `${acc}/${part}` : part;
      const dir = i < parts.length - 1;
      let node = level.find((item) => item.name === part && item.dir === dir);
      if (!node) {
        node = { name: part, path: acc, dir, children: [] };
        level.push(node);
      }
      if (!dir) node.file = file;
      level = node.children;
    });
  }
  const sort = (nodes: Node[]) => {
    nodes.sort((a, b) => Number(b.dir) - Number(a.dir) || a.name.localeCompare(b.name));
    nodes.forEach((node) => sort(node.children));
  };
  sort(root);
  return root;
}

function Tree({ nodes, depth, query, expanded, toggle, selected, onPick }: {
  nodes: Node[];
  depth: number;
  query: string;
  expanded: Set<string>;
  toggle: (path: string) => void;
  selected: string | null;
  onPick: (path: string) => void;
}) {
  const q = query.trim().toLowerCase();
  const hit = (item: Node): boolean => !q || item.path.toLowerCase().includes(q) || item.children.some(hit);
  return (
    <>
      {nodes.map((node) => {
        if (!hit(node)) return null;
        if (node.dir) {
          const open = q ? true : expanded.has(node.path);
          return (
            <div key={node.path}>
              <button type="button" className="quiet-row" style={{ paddingLeft: 8 + depth * 14 }} onClick={() => toggle(node.path)}>
                <span className="quiet-chev">{open ? "▾" : "▸"}</span>
                <span className="quiet-name">{node.name}</span>
                <span className="quiet-dot" title="Has changes" />
              </button>
              {open && (
                <Tree nodes={node.children} depth={depth + 1} query={query} expanded={expanded} toggle={toggle} selected={selected} onPick={onPick} />
              )}
            </div>
          );
        }
        if (q && !node.path.toLowerCase().includes(q)) return null;
        const file = node.file;
        return (
          <button type="button" key={node.path} className={`quiet-row${selected === node.path ? " on" : ""}${file?.status === "D" ? " gone" : ""}`} style={{ paddingLeft: 8 + depth * 14 }} onClick={() => onPick(node.path)}>
            <span className="quiet-chev" />
            <span className="quiet-kind">{file?.status === "?" ? "A" : file?.status ?? "·"}</span>
            <span className="quiet-name">{node.name}</span>
            {file && file.additions > 0 && <span className="quiet-add">+{file.additions}</span>}
            {file && file.deletions > 0 && <span className="quiet-del">−{file.deletions}</span>}
          </button>
        );
      })}
    </>
  );
}

export function QuietRoom({
  roomName, marvin, repos, refreshKey, deviceError, onProjects, onRoomSettings, setDeviceError,
}: {
  roomName: string;
  marvin: ReturnType<typeof useMarvin>;
  repos: ProjectRepoInfo[];
  refreshKey: number;
  deviceError: string | null;
  onProjects: () => void;
  onRoomSettings: () => void;
  setDeviceError: (s: string | null) => void;
}) {
  const [which, setWhich] = useState("");
  const repo = repos.find((item) => item.path === which) ?? repos[0];
  const { data, error, repoQ } = useChanges(roomName, repo?.path, repos.length > 1, refreshKey);
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const seeded = useRef("");
  const [selected, setSelected] = useState<string | null>(null);
  const [diff, setDiff] = useState("");
  const [mode, setMode] = useState("transcript");
  const [ask, setAsk] = useState("");
  const screens = useScreenShares();
  const seenScreens = useRef(new Set<string>());
  const apps = marvin.appLinks.filter((link) => link.url);
  const tree = useMemo(() => buildTree(data?.files ?? []), [data]);
  useEffect(() => {
    const key = repo?.path ?? "";
    if (!tree.length || seeded.current === key) return;
    seeded.current = key;
    setExpanded(new Set(tree.filter((node) => node.dir).map((node) => node.path)));
  }, [tree, repo?.path]);

  useEffect(() => {
    const keys = screens.map(screenShareKey);
    const fresh = keys.find((key) => !seenScreens.current.has(key));
    seenScreens.current = new Set(keys);
    if (fresh) setMode(`screen:${fresh}`);
    else setMode((current) => current.startsWith("screen:") && !keys.includes(current.slice("screen:".length)) ? "transcript" : current);
  }, [screens]);

  useEffect(() => {
    if (!selected) return;
    let alive = true;
    fetch(`/api/changes/file?room=${encodeURIComponent(roomName)}${repoQ}&path=${encodeURIComponent(selected)}`)
      .then((r) => r.text())
      .then((text) => { if (alive) setDiff(text); })
      .catch(() => { if (alive) setDiff(""); });
    return () => { alive = false; };
  }, [roomName, repoQ, selected, data]);

  function pick(path: string) {
    setSelected(path);
    setMode("file");
  }
  function toggle(path: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  const screen = screens.find((track) => mode === `screen:${screenShareKey(track)}`);
  const app = apps.find((link) => mode === `app:${link.url}`);
  const fileCount = data?.files.length ?? 0;

  return (
    <div className="quiet-room">
      <aside className="quiet-side">
        <div className="quiet-head">
          <button type="button" className="room-mark" onClick={onProjects} title="Projects" aria-label="Projects"><BrandLogo /></button>
          <button type="button" className="room-back" onClick={onProjects}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="m15 18-6-6 6-6" /></svg>
            Projects
          </button>
          <b className="room">#{roomName}</b>
        </div>
        <button type="button" className="room-settings quiet-settings" onClick={onRoomSettings}>Room settings</button>
        {repos.length > 1 && (
          <div className="quiet-repos">
            {repos.map((item, i) => (
              <button key={item.path} type="button" className={repo?.path === item.path ? "on" : ""} onClick={() => { setWhich(i === 0 ? "" : item.path); setSelected(null); }} title={item.path}>
                {item.name}{item.role ? <small> {item.role}</small> : null}
              </button>
            ))}
          </div>
        )}
        <label className="quiet-find">
          <span aria-hidden>⌕</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search changed files" />
        </label>
        <div className="quiet-tree">
          {error && <p className="quiet-empty">{error}</p>}
          {!error && !data && <p className="quiet-empty">Reading git…</p>}
          {data && !data.git && <p className="quiet-empty">This folder is not a git repository yet.</p>}
          {data?.git && fileCount === 0 && <p className="quiet-empty">Nothing changed on {data.branch ?? "this branch"}.</p>}
          {data?.git && fileCount > 0 && (
            <Tree nodes={tree} depth={0} query={query} expanded={expanded} toggle={toggle} selected={selected} onPick={pick} />
          )}
        </div>
        <div className="quiet-people"><People agentState={marvin.state} /></div>
      </aside>
      <section className="quiet-main">
        <header className="quiet-title">
          <div>
            <div className="quiet-kicker">In the room{data?.branch ? ` · ${data.branch}` : ""}{data?.base === "HEAD" ? " · uncommitted" : ""}</div>
            <h1>#{roomName}</h1>
          </div>
          <div className="room-controls">
            {deviceError && <p className="error devhint">{deviceError}</p>}
            <StartAudio label="Click to hear the room" />
            <ControlBar
              variation="minimal"
              controls={{ microphone: true, camera: false, screenShare: true, leave: true, chat: false }}
              onDeviceError={({ source, error: err }) => {
                const reason = `${err.name} ${err.message}`;
                const noun = source === "microphone" ? "Microphone" : "Screen";
                setDeviceError(/NotAllowed|PermissionDenied/i.test(reason)
                  ? `Chrome blocked the ${source}. Click the icon left of the address bar, set ${noun} to Allow, then reload.`
                  : /NotFound/i.test(reason) ? `No ${source} found on this computer.` : `${source}: ${reason}`);
              }}
            />
          </div>
        </header>
        <div className="page-modes">
          <button type="button" className={mode === "transcript" ? "on" : ""} onClick={() => setMode("transcript")}>Transcript</button>
          <button type="button" className={mode === "marvin" ? "on" : ""} onClick={() => setMode("marvin")}>
            <span className={`dot ${marvin.state}`} /> {agent.name}
          </button>
          {selected && <button type="button" className={mode === "file" ? "on" : ""} onClick={() => setMode("file")}>{selected.split("/").pop()}</button>}
          {screens.map((track) => {
            const key = `screen:${screenShareKey(track)}`;
            return <button key={key} type="button" className={mode === key ? "on" : ""} onClick={() => setMode(key)}>{screenShareLabel(track)}</button>;
          })}
          {apps.map((link) => (
            <button key={link.url} type="button" className={mode === `app:${link.url}` ? "on" : ""} onClick={() => setMode(`app:${link.url}`)}>{link.label}</button>
          ))}
        </div>
        {mode === "transcript" && (
          <>
            <form className="quiet-ask" onSubmit={(event) => { event.preventDefault(); if (!ask.trim()) return; marvin.send({ action: "ask", text: ask.trim() }); setAsk(""); setMode("marvin"); }}>
              <input value={ask} onChange={(event) => setAsk(event.target.value)} placeholder={`Ask ${agent.name} about #${roomName}…`} />
              <div className="quiet-ask-row"><span>Said here, heard in the room.</span><button type="submit">Send</button></div>
            </form>
            <div className="quiet-transcript"><Transcript lines={marvin.transcript} /></div>
          </>
        )}
        {mode === "marvin" && <div className="quiet-marvin"><MarvinPane marvin={marvin} room={roomName} /></div>}
        {mode === "file" && selected && (
          <div className="quiet-file">
            <p className="quiet-crumb">{repo?.name ?? roomName} / {selected.split("/").map((part, i, all) => i === all.length - 1 ? <b key={part}>{part}</b> : <span key={part}>{part} / </span>)}</p>
            <div className="quiet-file-actions">
              <button type="button" className="ghost" disabled={fileCount === 0} onClick={() => marvin.send({ action: "ask", text: `commit the current changes${repo && repos.length > 1 ? ` in ${repo.name}` : ""} with a clear message` })}>commit</button>
              <button type="button" disabled={!data?.branch || data.branch === "main" || data.branch === "master"} onClick={() => marvin.send({ action: "ask", text: `push the branch${repo && repos.length > 1 ? ` in ${repo.name}` : ""} and open a pull request` })}>open PR</button>
            </div>
            <DiffView text={diff} path={selected} />
          </div>
        )}
        {screen && <ScreenShareView track={screen} />}
        {app && <iframe className="preview quiet-preview" src={app.url} title={app.label} sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals" />}
      </section>
    </div>
  );
}
