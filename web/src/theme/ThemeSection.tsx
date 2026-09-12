import { useState } from "react";
import { useIsAdmin } from "../auth";
import { agent } from "../agent";
import { useTheme } from "./ThemeContext";
import { swatches, type Theme } from "./themes";

/** Settings → Appearance: pick a theme for this browser; admins pick the machine default and remove custom themes.
 *  Custom themes are made by asking Marvin (or by dropping a folder into the worker's themes directory). */
export function ThemeSection() {
  const admin = useIsAdmin();
  const th = useTheme();
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (f: () => Promise<void>, ok: string) => {
    setBusy(true); setMsg(null);
    try { await f(); setMsg(ok); } catch (e) { setMsg(`error: ${e instanceof Error ? e.message : String(e)}`); } finally { setBusy(false); }
  };
  const following = th.choice === null;
  return (
    <section className="appearance">
      <h3>Appearance</h3>
      <p className="dim small">
        Your pick, for this browser. {following ? <>Following the machine default (<b>{name(th.themes, th.defaultId)}</b>).</> : <>Machine default is <b>{name(th.themes, th.defaultId)}</b>. <a href="#" onClick={(e) => { e.preventDefault(); th.choose(null); }}>follow it</a></>}
      </p>
      <div className="theme-cards">
        {th.themes.map((t) => {
          const on = th.active.id === t.id;
          const isDefault = th.defaultId === t.id;
          return (
            <div key={t.id} className={`theme-card${on ? " on" : ""}${t.valid ? "" : " invalid"}`} data-scheme={t.scheme} onClick={() => t.valid && th.choose(t.id)} role="button" tabIndex={0}
              onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && t.valid) { e.preventDefault(); th.choose(t.id); } }}>
              <div className="swatches">{swatches(t).map((c, i) => <span key={i} style={{ background: c }} />)}</div>
              <div className="theme-name">
                <b>{t.name}</b>
                {isDefault && <span className="tag">default</span>}
                {!t.builtin && <span className="tag">custom</span>}
                {t.scheme === "light" && <span className="tag">light</span>}
              </div>
              {t.description && <p className="dim small">{t.description}</p>}
              {!t.valid && <p className="error small">Not usable: {t.errors[0]}{t.errors.length > 1 ? ` (+${t.errors.length - 1} more)` : ""}</p>}
              {t.valid && t.warnings.length > 0 && <p className="dim small" title={t.warnings.join("\n")}>{t.warnings.length} warning{t.warnings.length > 1 ? "s" : ""}</p>}
              {admin && (
                <div className="btns" onClick={(e) => e.stopPropagation()}>
                  {t.valid && !isDefault && th.defaultSource !== "env" && (
                    <button type="button" className="ghost" disabled={busy} onClick={() => void run(() => th.setDefault(t.id), `${t.name} is now the default for everyone on this machine.`)}>make default</button>
                  )}
                  {!t.builtin && (
                    <button type="button" className="ghost" disabled={busy} onClick={() => { if (confirm(`Remove the theme "${t.name}" from this machine?`)) void run(() => th.remove(t.id), `${t.name} removed.`); }}>remove</button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
      {admin && th.defaultSource === "env" && <p className="dim small">The machine default comes from <code>MARVIN_THEME</code> in the environment; unset it to choose here.</p>}
      {admin && th.defaultSource === "settings" && <p className="dim small">Default set here · <a href="#" onClick={(e) => { e.preventDefault(); void run(() => th.setDefault(null), "Back to the app default."); }}>reset</a></p>}
      <p className="dim small">
        Want another look? Ask in the room: <i>"{agent.name}, make me a theme: light, warm, serif, with a green accent."</i> {agent.name} writes it{th.dir ? <> to <code>{th.dir}</code></> : null} and it shows up here when the turn ends. Themes are colours, fonts and CSS only; a broken one is listed with the reason and cannot be turned on.
      </p>
      {th.error && <p className="error small">{th.error}</p>}
      {msg && <p className={`status ${msg.startsWith("error") ? "bad" : "ok"}`}>{msg}</p>}
    </section>
  );
}

function name(themes: Theme[], id: string): string {
  return themes.find((t) => t.id === id)?.name ?? id;
}
