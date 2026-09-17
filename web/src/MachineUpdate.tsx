import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "./ui";

export type ProductRelease = {
  id: string;
  date: string;
  title: string;
  summary: string;
  changes: { title: string; description: string }[];
};

type UpdateInfo = {
  short: string | null;
  latest_short: string | null;
  latest_message: string | null;
  ref: string;
  behind: boolean;
  commits: { sha: string; message: string }[];
  can_apply: boolean;
  applying: boolean;
  last_error: string | null;
  step?: string | null;
  log?: string;
  worker_up?: boolean;
  started_at?: number | null;
  product_updates?: ProductRelease[];
};

const stepLabels: Record<string, string> = {
  starting: "Starting the updater",
  "updater running": "Updater is running",
  fetching: "Pulling the latest changes",
  "building sandbox": "Building the sandbox",
  "rebuilding stack": "Restarting Marvin",
  ready: "Marvin is ready",
  failed: "Update failed",
};

export function MachineUpdate({ compact = false }: { compact?: boolean }) {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const logEl = useRef<HTMLPreElement>(null);
  const applying = Boolean(info?.applying);

  const load = () => {
    fetch("/api/update")
      .then(async (response) => {
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.error ?? response.statusText);
        setInfo(body);
        setError(null);
      })
      .catch((cause) => setError(String(cause instanceof Error ? cause.message : cause)));
  };

  useEffect(() => {
    void load();
    const timer = window.setInterval(load, applying ? 2000 : 30000);
    return () => window.clearInterval(timer);
  }, [applying]);

  useEffect(() => {
    const el = logEl.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [info?.log]);

  useEffect(() => {
    if (!notesOpen) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setNotesOpen(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [notesOpen]);

  const apply = async () => {
    if (!confirm("Update this machine? Rooms disconnect while Marvin rebuilds. Keep this page open to follow progress.")) return;
    setBusy(true);
    setError(null);
    const response = await fetch("/api/update", { method: "POST" });
    const body = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setError(body.error ?? response.statusText);
      return;
    }
    setInfo((current) => current ? { ...current, applying: true, can_apply: false, step: "starting" } : current);
    load();
  };

  const releases = info?.product_updates ?? [];
  const hasNotes = releases.length > 0 || Boolean(info?.commits.length);
  const stale = applying && typeof info?.started_at === "number" && Date.now() / 1000 - info.started_at > 30 * 60;
  const updateReady = Boolean(info?.behind && info.can_apply && !applying);

  if (!info && !error) {
    return <p className="machine-update-loading">Checking for updates…</p>;
  }

  if (compact && info && !updateReady && !applying && !info.last_error && !error) {
    return (
      <div className="machine-update-current">
        <CheckIcon />
        <span><b>Marvin is up to date</b><small>Running {info.short ?? info.ref}</small></span>
      </div>
    );
  }

  return (
    <>
      <section className={`machine-update${compact ? " compact" : ""}${applying ? " applying" : ""}${info?.last_error || error ? " failed" : ""}`}>
        <span className="machine-update-icon">{applying ? <SpinnerIcon /> : updateReady ? <DownloadIcon /> : info?.last_error || error ? <AlertIcon /> : <CheckIcon />}</span>
        <div className="machine-update-copy">
          <b>{applying ? stepLabels[info?.step ?? ""] ?? info?.step ?? "Updating Marvin" : updateReady ? "An update is ready" : info?.last_error || error ? "Update needs attention" : "Marvin is up to date"}</b>
          <small>
            {applying
              ? "The worker restarts during this process. Keep this page open."
              : updateReady
                ? `${info?.commits.length || releases[0]?.changes.length || 1} improvements · about 4 minutes`
                : info?.worker_up === false
                  ? "The worker is not responding."
                  : `Running ${info?.short ?? info?.ref ?? "current version"}`}
          </small>
          {applying && <span className="machine-update-progress"><i /></span>}
        </div>
        <div className="machine-update-actions">
          {hasNotes && <Button variant="ghost" onClick={() => setNotesOpen(true)}>What changed</Button>}
          {updateReady && <Button disabled={busy} onClick={() => void apply()}>{busy ? "Starting…" : "Update now"}</Button>}
        </div>
        {!compact && info?.latest_short && !applying && (
          <p className="machine-update-version">Running <code>{info.short ?? "unknown"}</code> · {info.ref} is <code>{info.latest_short}</code></p>
        )}
        {applying && (
          <pre ref={logEl} className="update-log" aria-live="polite">{info?.log || "Waiting for the first log line…"}</pre>
        )}
        {stale && <p className="machine-update-error">No progress for 30 minutes. The updater may have stopped.</p>}
        {(info?.last_error || error) && !applying && <p className="machine-update-error">{info?.last_error || error}</p>}
      </section>
      {notesOpen && (
        <ReleaseNotes
          releases={releases}
          commits={info?.commits ?? []}
          onClose={() => setNotesOpen(false)}
        />
      )}
    </>
  );
}

function ReleaseNotes({ releases, commits, onClose }: { releases: ProductRelease[]; commits: UpdateInfo["commits"]; onClose: () => void }) {
  return (
    <div className="release-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <aside className="release-sheet" role="dialog" aria-modal="true" aria-labelledby="release-title">
        <header>
          <div><small>Product updates</small><h2 id="release-title">What’s new in Marvin</h2></div>
          <button type="button" aria-label="Close release notes" onClick={onClose} autoFocus>×</button>
        </header>
        <div className="release-content">
          {releases.map((release) => (
            <section key={release.id}>
              <p className="release-date">{release.date}</p>
              <h3>{release.title}</h3>
              <p>{release.summary}</p>
              <ol>
                {release.changes.map((change) => (
                  <li key={change.title}><b>{change.title}</b><span>{change.description}</span></li>
                ))}
              </ol>
            </section>
          ))}
          {releases.length === 0 && commits.length > 0 && (
            <section>
              <h3>Changes in this update</h3>
              <ol>{commits.map((commit) => <li key={commit.sha}><b>{commit.message}</b><span>{commit.sha}</span></li>)}</ol>
            </section>
          )}
          {releases.length === 0 && commits.length === 0 && <p>No release notes were published for this version.</p>}
        </div>
        <footer><Button onClick={onClose}>Done</Button></footer>
      </aside>
    </div>
  );
}

function Icon({ children }: { children: ReactNode }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>;
}
function CheckIcon() { return <Icon><path d="m5 12 4 4L19 6" /></Icon>; }
function DownloadIcon() { return <Icon><path d="M12 3v12m-5-5 5 5 5-5M5 21h14" /></Icon>; }
function AlertIcon() { return <Icon><path d="M12 9v4m0 4h.01M10.3 4.4 2.8 18a2 2 0 0 0 1.8 3h14.8a2 2 0 0 0 1.8-3L13.7 4.4a2 2 0 0 0-3.4 0Z" /></Icon>; }
function SpinnerIcon() { return <Icon><path d="M21 12a9 9 0 1 1-6.2-8.6" /></Icon>; }
