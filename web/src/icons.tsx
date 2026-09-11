// Small inline icons (stroke = currentColor) so the header stays crisp at any width and needs no icon font.
import type { SVGProps } from "react";

const base: SVGProps<SVGSVGElement> = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true };

export const StopIcon = () => (
  <svg {...base}><rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none" /></svg>
);
export const BoltIcon = () => (
  <svg {...base}><path d="M13 2 3 14h8l-1 8 10-12h-8l1-8z" /></svg>
);
export const CpuIcon = () => (
  <svg {...base}>
    <rect x="5" y="5" width="14" height="14" rx="2" /><rect x="9" y="9" width="6" height="6" />
    <path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" />
  </svg>
);
export const ChevronIcon = () => (
  <svg {...base}><path d="m6 9 6 6 6-6" /></svg>
);
export const BotIcon = () => (
  <svg {...base}>
    <rect x="4" y="8" width="16" height="12" rx="2" /><path d="M12 4v4M8 4h8" /><circle cx="9" cy="14" r="1" fill="currentColor" /><circle cx="15" cy="14" r="1" fill="currentColor" />
  </svg>
);
export const PinIcon = () => (
  <svg {...base}><path d="M12 17v5M8 3h8l-1 7 3 3H6l3-3-1-7z" /></svg>
);
