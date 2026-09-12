// Voice presence: who is speaking and what Marvin is doing, drawn the way the theme asks (dot, oscilloscope, VU bars,
// ink underline, radial orb, ring). The app owns the drawing and the audio level; the theme picks the variant and
// colours it through `--presence` and `--glow`. `--level` (0..1) is kept live on the element for theme CSS to use.
import { useEffect, useRef } from "react";
import { useIsSpeaking } from "@livekit/components-react";
import type { Participant } from "livekit-client";
import { useTheme } from "./ThemeContext";
import type { AgentVariant, SpeakerVariant } from "./themes";

export type AgentState = "offline" | "idle" | "thinking" | "waiting_approval";
type Variant = AgentVariant | SpeakerVariant;

const reduced = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/** One requestAnimationFrame loop per element while `active`; `level()` is sampled each frame, smoothed, written to
 *  `--level` and handed to `draw`. Idle elements cost nothing. */
function useLoop(ref: React.RefObject<HTMLElement | null>, active: boolean, level: (t: number) => number, draw?: (l: number, t: number) => void) {
  useEffect(() => {
    const e = ref.current;
    if (!e) return;
    let raf = 0;
    let cur = 0;
    let last = performance.now();
    const still = reduced();
    const tick = () => {
      const now = performance.now();
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      const target = active ? Math.max(0, Math.min(1, level(now / 1000))) : 0;
      cur += (target - cur) * Math.min(1, dt * (target > cur ? 18 : 6)); // fast attack, slow release
      e.style.setProperty("--level", cur.toFixed(3));
      draw?.(cur, now / 1000);
      if (active || cur > 0.005) raf = requestAnimationFrame(tick);
      else { e.style.setProperty("--level", "0"); draw?.(0, now / 1000); }
    };
    if (still) { const l = active ? 0.5 : 0; e.style.setProperty("--level", String(l)); draw?.(l, 0); return; }
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [ref, active, level, draw]);
}

// -- drawings --------------------------------------------------------------------------------------------------------

function Scope({ level, active, state }: { level: (t: number) => number; active: boolean; state?: AgentState }) {
  const ref = useRef<HTMLSpanElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  useLoop(ref, active, level, (l, t) => {
    const c = canvas.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth, h = c.clientHeight;
    if (!w || !h) return;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
    const g = c.getContext("2d");
    if (!g) return;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const color = getComputedStyle(c).color;
    g.strokeStyle = color;
    g.lineWidth = 1.25;
    g.lineJoin = "round";
    const mid = h / 2;
    if (l < 0.02) {
      // quiet: a hairline with ticks
      g.globalAlpha = 0.55;
      g.beginPath(); g.moveTo(0, mid); g.lineTo(w, mid); g.stroke();
      g.globalAlpha = 0.35;
      for (let x = 8; x < w; x += 16) { g.beginPath(); g.moveTo(x, mid - 2); g.lineTo(x, mid + 2); g.stroke(); }
      g.globalAlpha = 1;
      return;
    }
    const structured = state === "thinking";
    g.beginPath();
    const amp = (h / 2 - 2) * l;
    for (let x = 0; x <= w; x += 2) {
      const p = x / w;
      const env = Math.sin(p * Math.PI); // fades at both ends
      const y = structured
        ? Math.sign(Math.sin(p * 40 + t * 8)) * amp * env * (0.6 + 0.4 * Math.sin(t * 3 + p * 6)) // square-ish: "computing"
        : (Math.sin(p * 22 + t * 9) * 0.6 + Math.sin(p * 47 - t * 13) * 0.3 + Math.sin(p * 9 + t * 4) * 0.4) * amp * env;
      x === 0 ? g.moveTo(x, mid + y) : g.lineTo(x, mid + y);
    }
    g.shadowColor = color; g.shadowBlur = 6 * l;
    g.stroke();
    g.shadowBlur = 0;
  });
  return <span ref={ref} className="presence-draw"><canvas ref={canvas} /></span>;
}

function Bars({ level, active }: { level: (t: number) => number; active: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  const bars = useRef<(HTMLElement | null)[]>([]);
  const K = [0.55, 0.85, 1, 0.8, 0.6];
  useLoop(ref, active, level, (l, t) => {
    bars.current.forEach((b, i) => {
      if (!b) return;
      const jitter = 0.75 + 0.25 * Math.sin(t * (7 + i * 1.7) + i);
      b.style.transform = `scaleY(${Math.max(0.12, l * K[i] * jitter)})`;
    });
  });
  return <span ref={ref} className="presence-draw">{K.map((_, i) => <i key={i} ref={(e) => { bars.current[i] = e; }} />)}</span>;
}

function Ink({ level, active, state }: { level: (t: number) => number; active: boolean; state?: AgentState }) {
  const ref = useRef<HTMLSpanElement>(null);
  const path = useRef<SVGPathElement>(null);
  useLoop(ref, active, level, (l, t) => {
    const p = path.current;
    if (!p) return;
    const pts: string[] = [];
    const writing = state === "thinking";
    const n = 12;
    for (let i = 0; i <= n; i++) {
      const x = (i / n) * 100;
      const wob = (Math.sin(i * 1.7 + t * 5) * 0.8 + Math.sin(i * 0.9 - t * 3) * 0.5) * (0.6 + 2.2 * l);
      pts.push(`${i ? "L" : "M"}${x.toFixed(1)} ${(5 + wob).toFixed(2)}`);
    }
    p.setAttribute("d", pts.join(" "));
    p.style.strokeWidth = String(1 + l * 2.6);
    if (writing) {
      const dash = 100;
      p.style.strokeDasharray = `${dash}`;
      p.style.strokeDashoffset = String(dash - ((t * 45) % (dash * 1.4)));
    } else { p.style.strokeDasharray = ""; p.style.strokeDashoffset = ""; }
  });
  return <span ref={ref} className="presence-draw"><svg viewBox="0 0 100 10" preserveAspectRatio="none"><path ref={path} d="M0 5 L100 5" /></svg></span>;
}

function Orb({ level, active, state }: { level: (t: number) => number; active: boolean; state?: AgentState }) {
  const ref = useRef<HTMLSpanElement>(null);
  const g = useRef<SVGGElement>(null);
  const N = 36;
  useLoop(ref, active, level, (l, t) => {
    const grp = g.current;
    if (!grp) return;
    const working = state === "thinking", waiting = state === "waiting_approval";
    const rot = working ? t * 40 : t * 4;
    grp.setAttribute("transform", `rotate(${waiting ? 0 : rot % 360} 50 50)`);
    const ticks = grp.children;
    for (let i = 0; i < ticks.length; i++) {
      const a = (i / N) * Math.PI * 2;
      const wave = working ? (i % 3 === 0 ? 1 : 0.35) * (0.6 + 0.4 * Math.sin(t * 6 + i)) : waiting ? 0.55 : 0.35 + 0.65 * Math.abs(Math.sin(i * 0.9 + t * 3.5));
      const len = 4 + (working ? 10 : 12) * l * wave + (waiting ? 4 : 0);
      const r0 = 30, r1 = r0 + len;
      const e = ticks[i] as SVGLineElement;
      e.setAttribute("x1", (50 + Math.cos(a) * r0).toFixed(2)); e.setAttribute("y1", (50 + Math.sin(a) * r0).toFixed(2));
      e.setAttribute("x2", (50 + Math.cos(a) * r1).toFixed(2)); e.setAttribute("y2", (50 + Math.sin(a) * r1).toFixed(2));
    }
  });
  return (
    <span ref={ref} className="presence-draw">
      <svg viewBox="0 0 100 100">
        <circle className="orb-halo" cx="50" cy="50" r="46" />
        <g ref={g}>{Array.from({ length: N }, (_, i) => <line key={i} x1="50" y1="20" x2="50" y2="16" />)}</g>
        <circle className="orb-ring" cx="50" cy="50" r="24" />
        <circle className="orb-core" cx="50" cy="50" r="7" />
      </svg>
    </span>
  );
}

function Simple({ level, active }: { level: (t: number) => number; active: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  useLoop(ref, active, level);
  return <span ref={ref} className="presence-draw"><i /></span>;
}

function Drawing({ variant, ...rest }: { variant: Variant; level: (t: number) => number; active: boolean; state?: AgentState }) {
  switch (variant) {
    case "scope": return <Scope {...rest} />;
    case "bars": return <Bars {...rest} />;
    case "ink": return <Ink {...rest} />;
    case "orb": return <Orb {...rest} />;
    default: return <Simple {...rest} />; // dot, ring: CSS does the work from --level
  }
}

// -- the two public elements -------------------------------------------------------------------------------------------

const agentLevel: Record<AgentState, (t: number) => number> = {
  offline: () => 0,
  idle: (t) => 0.06 + 0.05 * Math.sin(t * 1.2), // breathing
  thinking: (t) => 0.55 + 0.35 * Math.abs(Math.sin(t * 2.6)) * (0.7 + 0.3 * Math.sin(t * 11)),
  waiting_approval: () => 0.5,
};

/** Marvin's state. `variant` defaults to what the theme asks for. */
export function AgentPresence({ state, className = "", variant, label }: { state: AgentState; className?: string; variant?: AgentVariant; label?: string }) {
  const theme = useTheme();
  const v: AgentVariant = variant ?? theme.active.presence?.agent ?? "dot";
  return (
    <span className={`presence ${className}`.trim()} data-kind="agent" data-variant={v} data-state={state} data-active={state !== "offline" || undefined} title={label} aria-label={label}>
      <Drawing variant={v} level={agentLevel[state]} active={state !== "offline"} state={state} />
    </span>
  );
}

/** A person: lit while they speak, with their real audio level (plus a little life when LiveKit reports a flat level). */
export function SpeakerPresence({ participant, className = "", variant }: { participant: Participant; className?: string; variant?: SpeakerVariant }) {
  const theme = useTheme();
  const speaking = useIsSpeaking(participant);
  const v: SpeakerVariant = variant ?? theme.active.presence?.speaker ?? "dot";
  const ref = useRef(participant);
  ref.current = participant;
  const level = useRef((t: number) => {
    const real = ref.current.audioLevel || 0; // 0..1, updated by the server's active-speaker events
    const synth = 0.45 + 0.3 * Math.sin(t * 9) * Math.sin(t * 2.3);
    return Math.max(real * 1.6, synth * 0.9);
  }).current;
  return (
    <span className={`presence ${className}`.trim()} data-kind="speaker" data-variant={v} data-active={speaking || undefined}>
      <Drawing variant={v} level={level} active={speaking} />
    </span>
  );
}
