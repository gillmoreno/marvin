// Wire protocol between the Marvin worker and the room. Mirrors worker/marvin/room/protocol.py.
export const TOPIC_EVENTS = "marvin"; // worker -> everyone
export const TOPIC_CONTROL = "marvin-control"; // clients -> worker
export const AGENT_IDENTITY = "marvin";

export type MarvinEvent =
  | { kind: "app_links"; links: { label: string; url: string }[] } // where the room's app is served (from rooms.yaml)
  | { kind: "status"; state: "idle" | "thinking" | "waiting_approval" }
  | { kind: "transcript"; speaker: string; text: string; start: number; end: number; at?: number; final?: boolean }
  | { kind: "turn_start"; asked_by: string; question: string }
  | { kind: "text_delta"; text: string }
  | { kind: "text"; text: string }
  | { kind: "tool_use"; id: string; tool: string; input: Record<string, unknown> }
  | { kind: "tool_result"; id: string; output: string; is_error: boolean }
  | { kind: "permission_request"; id: string; tool: string; input: Record<string, unknown> }
  | { kind: "permission_resolved"; id: string; allow: boolean; by: string }
  | { kind: "auto_approve"; on: boolean; by: string } // "always allow" was toggled by someone in the room
  | { kind: "result"; subtype: string; is_error: boolean; cost_usd: number | null; duration_ms: number | null; session_id: string | null }
  | { kind: "attachment"; name: string; path: string; by: string } // an image landed on disk, waiting for the next turn
  | { kind: "denied"; action: string; by: string; reason: string } // a control message was refused (e.g. auto_approve without the admin role)
  | { kind: "error"; message: string };

export type ControlMessage =
  | { action: "approve" | "deny"; id: string }
  | { action: "auto_approve"; on: boolean } // stop asking for every tool until turned back off
  | { action: "ask"; text: string } // typed fallback: same path as a spoken "Marvin, ..."
  | { action: "image"; id: string; seq: number; total: number; mime: string; name: string; data: string } // base64, split across packets
  | { action: "interrupt" };

export const IMAGE_CHUNK = 8_000; // base64 chars per packet, well under LiveKit's 15 KiB cap
export const MAX_IMAGE_BYTES = 8_000_000;
