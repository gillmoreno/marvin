import { useCallback, useEffect, useState } from "react";
import { useDataChannel, useLocalParticipant } from "@livekit/components-react";
import { AGENT_IDENTITY, IMAGE_CHUNK, MAX_IMAGE_BYTES, TOPIC_CONTROL, TOPIC_EVENTS, type MarvinEvent, type ControlMessage } from "./protocol";

export type ToolCall = { id: string; tool: string; input: Record<string, unknown>; output?: string; is_error?: boolean };
export type Turn = {
  id: number;
  asked_by: string;
  question: string;
  text: string; // streamed assistant text
  tools: ToolCall[];
  result?: Extract<MarvinEvent, { kind: "result" }>;
  needsSep?: boolean; // a text block just closed; the next delta starts a new paragraph
};
export type Permission = Extract<MarvinEvent, { kind: "permission_request" }> & { resolved?: { allow: boolean; by: string } };
export type Attachment = Extract<MarvinEvent, { kind: "attachment" }>;
export type TranscriptLine = Extract<MarvinEvent, { kind: "transcript" }>;

const dec = new TextDecoder();
const enc = new TextEncoder();

export function useMarvin() {
  const [state, setState] = useState<"offline" | "idle" | "thinking" | "waiting_approval">("offline");
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]); // waiting for the next turn
  const [appLinks, setAppLinks] = useState<{ label: string; url: string }[]>([]);
  const [autoApprove, setAutoApprove] = useState(false); // mirrors the worker; the worker is the source of truth
  const [notice, setNotice] = useState<string | null>(null); // last refusal from the worker, shown briefly in the pane
  const { localParticipant } = useLocalParticipant();

  const onMessage = useCallback((msg: { payload: Uint8Array }) => {
    const ev = JSON.parse(dec.decode(msg.payload)) as MarvinEvent;
    switch (ev.kind) {
      case "status":
        setState(ev.state);
        break;
      case "transcript": {
        // streaming STT sends interim lines (final=false) while someone speaks; each one replaces the previous interim of that speaker
        setTranscript((t) => {
          let i = t.length - 1;
          while (i >= 0 && !(t[i].speaker === ev.speaker && t[i].final === false)) i--;
          const base = i >= 0 ? [...t.slice(0, i), ...t.slice(i + 1)] : t;
          return [...base.slice(-500), ev];
        });
        break;
      }
      case "turn_start":
        setTurns((ts) => [...ts, { id: ts.length + 1, asked_by: ev.asked_by, question: ev.question, text: "", tools: [] }]);
        setAttachments([]); // the worker just handed them to this turn
        break;
      case "attachment":
        setAttachments((as) => (as.some((a) => a.path === ev.path) ? as : [...as, ev]));
        break;
      case "text_delta":
        setTurns((ts) => patchLast(ts, (t) => ({ ...t, text: t.text + (t.needsSep && t.text ? "\n\n" : "") + ev.text, needsSep: false })));
        break;
      case "text":
        // A complete block arrives after its deltas; keep the streamed text if it already ends with it, else append.
        setTurns((ts) =>
          patchLast(ts, (t) => ({ ...t, text: t.text.endsWith(ev.text) ? t.text : t.text + (t.text ? "\n\n" : "") + ev.text, needsSep: true })),
        );
        break;
      case "tool_use":
        setTurns((ts) => patchLast(ts, (t) => ({ ...t, tools: [...t.tools, { id: ev.id, tool: ev.tool, input: ev.input }] })));
        break;
      case "tool_result":
        setTurns((ts) => patchLast(ts, (t) => ({ ...t, tools: t.tools.map((c) => (c.id === ev.id ? { ...c, output: ev.output, is_error: ev.is_error } : c)) })));
        break;
      case "permission_request":
        setPermissions((ps) => [...ps, ev]);
        break;
      case "permission_resolved":
        setPermissions((ps) => ps.map((p) => (p.id === ev.id ? { ...p, resolved: { allow: ev.allow, by: ev.by } } : p)));
        break;
      case "app_links":
        setAppLinks(ev.links);
        break;
      case "auto_approve":
        setAutoApprove(ev.on);
        break;
      case "denied":
        setNotice(`${ev.by}: ${ev.action.replace("_", " ")} refused (${ev.reason})`);
        break;
      case "result":
        setTurns((ts) => patchLast(ts, (t) => ({ ...t, result: ev })));
        break;
      case "error":
        setTurns((ts) => patchLast(ts, (t) => ({ ...t, text: t.text + `\n\n⚠ ${ev.message}` })));
        break;
    }
  }, []);
  useDataChannel(TOPIC_EVENTS, onMessage);
  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(null), 6000);
    return () => clearTimeout(t);
  }, [notice]);

  const send = useCallback(
    (m: ControlMessage) => localParticipant.publishData(enc.encode(JSON.stringify(m)), { reliable: true, topic: TOPIC_CONTROL, destinationIdentities: [AGENT_IDENTITY] }),
    [localParticipant],
  );

  const sendImage = useCallback(
    async (file: File) => {
      if (!file.type.startsWith("image/")) throw new Error(`${file.name} is not an image`);
      if (file.size > MAX_IMAGE_BYTES) throw new Error(`${file.name} is too big (max ${MAX_IMAGE_BYTES / 1e6} MB)`);
      const data = toBase64(await file.arrayBuffer());
      const id = crypto.randomUUID();
      const total = Math.max(1, Math.ceil(data.length / IMAGE_CHUNK));
      for (let seq = 0; seq < total; seq++) {
        await send({ action: "image", id, seq, total, mime: file.type, name: file.name, data: data.slice(seq * IMAGE_CHUNK, (seq + 1) * IMAGE_CHUNK) });
      }
    },
    [send],
  );

  return { state, transcript, turns, permissions, attachments, autoApprove, appLinks, notice, send, sendImage };
}

function toBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000)); // chunked: apply() blows the stack on big files
  return btoa(s);
}

function patchLast(ts: Turn[], f: (t: Turn) => Turn): Turn[] {
  if (ts.length === 0) return ts;
  return [...ts.slice(0, -1), f(ts[ts.length - 1])];
}
