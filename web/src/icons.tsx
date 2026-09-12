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
export const MicIcon = () => (
  <svg {...base}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6" /></svg>
);
export const MicOffIcon = () => (
  <svg {...base}><path d="M3 3l18 18M15 9.5V6a3 3 0 0 0-6 0v1M9 9v2a3 3 0 0 0 5.1 2.1M5 11a7 7 0 0 0 11.2 5.6M19 11a7 7 0 0 1-.6 2.8M12 18v3M9 21h6" /></svg>
);
export const LeaveIcon = () => (
  <svg {...base}><path d="M10 17l5-5-5-5M15 12H3M13 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6" /></svg>
);
export const GearIcon = () => (
  <svg {...base}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></svg>
);
/** Two sliders: the Control Room settings control (matches the prototype). */
export const SlidersIcon = () => (
  <svg {...base} strokeWidth={1.6}><path d="M4 7h9M18 7h2M4 17h4M13 17h7" /><circle cx="15.5" cy="7" r="2.5" /><circle cx="10.5" cy="17" r="2.5" /></svg>
);
