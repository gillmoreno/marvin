import { useCallback, useEffect, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";

// The room is three columns; the outer two can be dragged (and reset with a double-click).
type Side = "left" | "right";
type Widths = Record<Side, number>;

const DEFAULTS: Widths = { left: 240, right: 360 };
const MIN: Widths = { left: 180, right: 280 };
const MAX: Widths = { left: 520, right: 820 };
const CENTER_MIN = 360; // the workspace never gets squeezed below this
const KEY = "marvin.columns";

function clamp(side: Side, px: number, other: number): number {
  const room = window.innerWidth - other - CENTER_MIN;
  return Math.round(Math.min(MAX[side], room, Math.max(MIN[side], px)));
}

function load(): Widths {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) ?? "");
    if (Number.isFinite(s.left) && Number.isFinite(s.right)) return { left: s.left, right: s.right };
  } catch { /* first visit or garbage */ }
  return DEFAULTS;
}

export function useColumns() {
  const [w, setW] = useState<Widths>(load);
  useEffect(() => { try { localStorage.setItem(KEY, JSON.stringify(w)); } catch { /* private mode */ } }, [w]);
  const resize = useCallback((side: Side, px: number) => setW((c) => ({ ...c, [side]: clamp(side, px, c[side === "left" ? "right" : "left"]) })), []);
  const reset = useCallback((side: Side) => setW((c) => ({ ...c, [side]: DEFAULTS[side] })), []);
  const style = { "--left-w": `${w.left}px`, "--right-w": `${w.right}px` } as CSSProperties;
  return { style, resize, reset };
}

/** The draggable line between two columns. Arrow keys nudge it when focused. */
export function Gutter({ side, resize, reset }: { side: Side; resize: (side: Side, px: number) => void; reset: (side: Side) => void }) {
  const fromPointer = (x: number) => (side === "left" ? x : window.innerWidth - x);
  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const el = e.currentTarget;
    el.setPointerCapture(e.pointerId);
    document.body.classList.add("resizing");
    const move = (ev: PointerEvent) => resize(side, fromPointer(ev.clientX));
    const up = () => {
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("pointercancel", up);
      document.body.classList.remove("resizing");
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
  };
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? 48 : 16;
    const rect = e.currentTarget.getBoundingClientRect();
    const here = fromPointer(rect.left);
    if (e.key === "ArrowLeft") resize(side, here + (side === "left" ? -step : step));
    else if (e.key === "ArrowRight") resize(side, here + (side === "left" ? step : -step));
    else if (e.key === "Home" || e.key === "Enter") reset(side);
    else return;
    e.preventDefault();
  };
  return (
    <div
      className="gutter"
      role="separator"
      aria-orientation="vertical"
      aria-label={`resize ${side} column`}
      tabIndex={0}
      title="drag to resize · double-click to reset"
      onPointerDown={onPointerDown}
      onDoubleClick={() => reset(side)}
      onKeyDown={onKeyDown}
    />
  );
}
