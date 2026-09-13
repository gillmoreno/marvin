import { useCallback, useEffect, useRef, useState } from "react";
import type { useMarvin } from "./useMarvin";
import { agent } from "./agent";
import { HarnessPicker, ModelPicker, useRoomInfo } from "./RoomSettings";
import { BoltIcon, StopIcon } from "./icons";
import { useIsAdmin } from "./auth";

export function MarvinPane({ marvin, room }: { marvin: ReturnType<typeof useMarvin>; room: string }) {
  const roomInfo = useRoomInfo(room, marvin.turns.length);
  const admin = useIsAdmin(); // "always allow" is admin-only (the worker enforces it; hiding it just avoids a refusal)
  const { state, turns, permissions, attachments, autoApprove, notice, send, sendImage } = marvin;
  const [typed, setTyped] = useState("");
  const [patchError, setPatchError] = useState<string | null>(null);
  const [dropping, setDropping] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [turns, permissions, attachments]);
  const open = permissions.filter((p) => !p.resolved);

  const upload = useCallback(
    (files: Iterable<File> | FileList | null | undefined) => {
      const images = Array.from(files ?? []).filter((f) => f.type.startsWith("image/"));
      if (images.length === 0) return;
      setUploadError("");
      for (const f of images) sendImage(f).catch((e) => setUploadError(String(e?.message ?? e)));
    },
    [sendImage],
  );

  // Window-level: a drop or a ⌘V lands wherever the cursor happens to be, not necessarily on this pane.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const items = Array.from(e.clipboardData?.items ?? []).filter((i) => i.kind === "file");
      const files = items.map((i) => i.getAsFile()).filter((f): f is File => f != null);
      if (files.length) e.preventDefault();
      upload(files);
    };
    const over = (e: DragEvent) => { e.preventDefault(); setDropping(true); };
    const leave = (e: DragEvent) => { if (!e.relatedTarget) setDropping(false); };
    const drop = (e: DragEvent) => { e.preventDefault(); setDropping(false); upload(e.dataTransfer?.files); };
    window.addEventListener("paste", onPaste);
    window.addEventListener("dragover", over);
    window.addEventListener("dragleave", leave);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("paste", onPaste);
      window.removeEventListener("dragover", over);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("drop", drop);
    };
  }, [upload]);

  return (
    <div className={`marvin${dropping ? " dropping" : ""}`}>
      <header className="marvin-head">
        <div className="marvin-r1">
          <span className={`status ${state}`} title={`${agent.name} is ${label(state)}`}>
            <span className={`dot ${state}`} />
            <span className="status-name">{agent.name}</span>
            <span className="status-text">{label(state)}</span>
          </span>
          <span className="spacer" />
          {state === "thinking" && (
            <button type="button" className="iconbtn stop" onClick={() => send({ action: "interrupt" })} title="Stop this turn" aria-label="stop">
              <StopIcon />
              <span className="btn-label">stop</span>
            </button>
          )}
        </div>
        <div className="marvin-r2">
          <HarnessPicker room={room} info={roomInfo.info} reload={roomInfo.reload} onError={setPatchError} />
          <ModelPicker room={room} info={roomInfo.info} reload={roomInfo.reload} onError={setPatchError} />
          {admin ? (
            <button
              type="button"
              className={`iconbtn always-btn${autoApprove ? " on" : ""}`}
              aria-pressed={autoApprove}
              onClick={() => send({ action: "auto_approve", on: !autoApprove })}
              title={autoApprove ? "Always allow is on: every tool runs without asking the room. Click to turn off." : "Always allow: run every tool without asking the room"}
            >
              <BoltIcon />
              <span className="btn-label">always allow</span>
            </button>
          ) : (
            autoApprove && <span className="iconbtn always-btn on" title="Always allow is on: every tool runs without asking the room. An admin can turn it off."><BoltIcon /><span className="btn-label">always allow</span></span>
          )}
        </div>
      </header>
      {(notice || patchError) && <p className="notice">{notice ?? patchError}</p>}
      <div className="turns">
        {turns.length === 0 && <p className="hint">Nobody has said "{agent.name}" yet. Try: "{agent.name}, what does this repo do?"</p>}
        {turns.map((t) => (
          <section key={t.id} className="turn">
            <div className="q"><b>{t.asked_by}</b>: {t.question}</div>
            {t.tools.length > 0 && (
              <ul className="tools">
                {t.tools.map((c) => (
                  <li key={c.id} className={c.is_error ? "err" : c.output === undefined ? "running" : ""}>
                    <code className={kind(c.tool)}>{c.tool}</code> <span className="arg">{summarize(c.input)}</span>
                    {c.output !== undefined && <pre>{c.output}</pre>}
                  </li>
                ))}
              </ul>
            )}
            <div className="a">
              {t.queued ? <span className="hint">waiting for the current turn to finish…</span> : t.text || (t.result ? "" : <WaitingHint />)}
            </div>
            {t.result && (
              <div className="meta">
                {t.result.is_error ? "failed" : "done"} · {t.result.duration_ms != null ? `${(t.result.duration_ms / 1000).toFixed(1)}s` : ""}
              </div>
            )}
          </section>
        ))}
        <div ref={endRef} />
      </div>
      {open.length > 0 && (
        <div className="approvals">
          {open.map((p) => (
            <div key={p.id} className="approval">
              <div>
                {agent.name} wants to run <code className={kind(p.tool)}>{p.tool}</code>
                <pre>{summarize(p.input, 600)}</pre>
              </div>
              <div className="btns">
                <button onClick={() => send({ action: "approve", id: p.id })}>Allow</button>
                {admin && <button className="ghost" onClick={() => send({ action: "auto_approve", on: true })}>Always</button>}
                <button className="danger" onClick={() => send({ action: "deny", id: p.id })}>Deny</button>
              </div>
            </div>
          ))}
        </div>
      )}
      {(attachments.length > 0 || uploadError) && (
        <div className="attachments">
          {attachments.map((a) => (
            <span key={a.path} className="chip">📎 {a.name} <span className="muted">from {a.by}</span></span>
          ))}
          {attachments.length > 0 && <span className="muted">goes to Marvin with the next question</span>}
          {uploadError && <span className="error">{uploadError}</span>}
        </div>
      )}
      <form
        className="typed"
        onSubmit={(e) => {
          e.preventDefault();
          if (!typed.trim()) return;
          send({ action: "ask", text: typed.trim() });
          setTyped("");
        }}
      >
        <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={`Ask ${agent.name}…`} title="Typed questions need no wake word. Drop or paste a screenshot to attach it." />
        <button type="submit">Send</button>
      </form>
    </div>
  );
}

function label(s: string) {
  return { offline: "not in the room", idle: "listening", thinking: "working", waiting_approval: "waiting for approval" }[s] ?? s;
}

function WaitingHint() {
  const [long, setLong] = useState(false);
  useEffect(() => {
    const t = window.setTimeout(() => setLong(true), 8000);
    return () => window.clearTimeout(t);
  }, []);
  return <>{long ? "Still waiting on the agent…" : "…"}</>;
}

// Colour tool names by what they do to the box: run, look, change.
function kind(tool: string): string {
  if (/^(Bash|BashOutput|KillShell)$/.test(tool)) return "exec";
  if (/^(Read|Glob|Grep|NotebookRead|WebFetch|WebSearch|Task|TodoWrite)$/.test(tool)) return "read";
  if (/^(Write|Edit|MultiEdit|NotebookEdit)$/.test(tool)) return "write";
  return "other";
}

function summarize(input: Record<string, unknown>, max = 160): string {
  const v = (input.command ?? input.file_path ?? input.pattern ?? input.query ?? input.url) as string | undefined;
  const s = v ?? JSON.stringify(input);
  return s.length > max ? s.slice(0, max) + "…" : s;
}
