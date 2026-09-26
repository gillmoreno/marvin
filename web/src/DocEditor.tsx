import { useEffect, useRef } from "react";
import { useLocalParticipant, useRoomContext } from "@livekit/components-react";
import { EditorState } from "@codemirror/state";
import { EditorView, basicSetup } from "codemirror";
import { oneDark } from "@codemirror/theme-one-dark";
import { javascript } from "@codemirror/lang-javascript";
import { python } from "@codemirror/lang-python";
import { cpp } from "@codemirror/lang-cpp";
import { html } from "@codemirror/lang-html";
import { markdown } from "@codemirror/lang-markdown";
import { css } from "@codemirror/lang-css";
import { json } from "@codemirror/lang-json";
import { sql } from "@codemirror/lang-sql";
import { yaml } from "@codemirror/lang-yaml";
import { rust } from "@codemirror/lang-rust";
import { go } from "@codemirror/lang-go";
import * as Y from "yjs";
import { Awareness } from "y-protocols/awareness";
import { yCollab } from "y-codemirror.next";

const TOPIC = "marvin-doc";
const CHUNK = 8000;
const COLORS = ["#2dd4bf", "#79c0ff", "#d2a8ff", "#ffa657", "#ff7b72", "#a5d6ff"];

function langOf(path: string) {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "ts" || ext === "tsx") return javascript({ typescript: true, jsx: ext === "tsx" });
  if (ext === "js" || ext === "jsx" || ext === "mjs") return javascript({ jsx: ext === "jsx" });
  if (ext === "py") return python();
  if (ext === "go") return go();
  if (ext === "rs") return rust();
  if (ext === "c" || ext === "h" || ext === "cpp" || ext === "cc" || ext === "hpp") return cpp();
  if (ext === "html" || ext === "htm" || ext === "xml" || ext === "svg") return html();
  if (ext === "css") return css();
  if (ext === "md") return markdown();
  if (ext === "json") return json();
  if (ext === "sql") return sql();
  if (ext === "yml" || ext === "yaml") return yaml();
  return [];
}

function b64(bytes: Uint8Array) {
  let s = "";
  bytes.forEach((b) => { s += String.fromCharCode(b); });
  return btoa(s);
}
function unb64(s: string) {
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

type Packet = { t: string; room: string; repo: string; path: string; id?: string; seq?: number; total?: number; b64?: string; sv?: string };

function firstChange(before: string, after: string): string {
  const a = before.split("\n");
  const b = after.split("\n");
  const n = Math.max(a.length, b.length);
  for (let i = 0; i < n; i++) {
    if (a[i] === b[i]) continue;
    const gone = (a[i] ?? "").trim();
    const added = (b[i] ?? "").trim();
    if (gone && added) return `− ${gone.slice(0, 42)}   + ${added.slice(0, 42)}`;
    if (added) return `+ ${added.slice(0, 80)}`;
    return `− ${gone.slice(0, 80)}`;
  }
  return "";
}

export function DocEditor({ room, repo, path, onActivity }: { room: string; repo: string; path: string; onActivity?: (summary: string) => void }) {
  const host = useRef<HTMLDivElement>(null);
  const notify = useRef(onActivity);
  notify.current = onActivity;
  const { localParticipant } = useLocalParticipant();
  const livekit = useRoomContext();
  const repoQ = repo ? `&repo=${encodeURIComponent(repo)}` : "";

  useEffect(() => {
    const parent = host.current;
    if (!parent) return;
    let dead = false;
    let view: EditorView | null = null;
    const doc = new Y.Doc();
    const ytext = doc.getText("t");
    const awareness = new Awareness(doc);
    const name = localParticipant.name || localParticipant.identity || "you";
    const color = COLORS[(name.charCodeAt(0) || 0) % COLORS.length];
    awareness.setLocalStateField("user", { name, color, colorLight: color + "33" });
    let typedAt = 0;
    let saveTimer = 0;
    let noteTimer = 0;
    let baseline = "";
    const chunks = new Map<string, string[]>();

    const publish = (packet: Packet) => {
      const raw = JSON.stringify(packet);
      if (raw.length <= 12000) {
        void localParticipant.publishData(new TextEncoder().encode(raw), { reliable: true, topic: TOPIC });
        return;
      }
    };
    const publishUpdate = (update: Uint8Array, tag: string) => {
      const data = b64(update);
      const id = crypto.randomUUID();
      const total = Math.max(1, Math.ceil(data.length / CHUNK));
      for (let seq = 0; seq < total; seq++) {
        publish({ t: tag, room, repo, path, id, seq, total, b64: data.slice(seq * CHUNK, (seq + 1) * CHUNK) });
      }
    };
    const save = () => {
      const update = b64(Y.encodeStateAsUpdate(doc));
      void fetch(`/api/files/text?room=${encodeURIComponent(room)}${repoQ}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ path, text: ytext.toString(), update }),
      });
    };

    const onUpdate = (update: Uint8Array, origin: unknown) => {
      if (origin === "remote" || origin === "seed" || origin === "disk") return;
      typedAt = Date.now();
      publishUpdate(update, "u");
      window.clearTimeout(saveTimer);
      saveTimer = window.setTimeout(save, 400);
      window.clearTimeout(noteTimer);
      noteTimer = window.setTimeout(() => {
        const summary = firstChange(baseline, ytext.toString());
        if (!summary) return;
        notify.current?.(summary);
        publish({ t: "note", room, repo, path, b64: summary });
      }, 150);
    };
    doc.on("update", onUpdate);

    const applyRemote = (update: Uint8Array) => Y.applyUpdate(doc, update, "remote");
    const take = (pkt: Packet) => {
      if (pkt.room !== room || pkt.path !== path || (pkt.repo || "") !== (repo || "")) return;
      if (pkt.t === "s1" && pkt.sv) {
        publishUpdate(Y.encodeStateAsUpdate(doc, unb64(pkt.sv)), "s2");
        return;
      }
      if (!pkt.id || pkt.seq == null || pkt.total == null || pkt.b64 == null) return;
      const parts = chunks.get(pkt.id) ?? [];
      parts[pkt.seq] = pkt.b64;
      chunks.set(pkt.id, parts);
      if (parts.filter(Boolean).length < pkt.total) return;
      chunks.delete(pkt.id);
      const update = unb64(parts.join(""));
      if (pkt.t === "u" || pkt.t === "s2") applyRemote(update);
    };
    const onData = (payload: Uint8Array) => {
      try { take(JSON.parse(new TextDecoder().decode(payload))); } catch { /* ignore a bad packet */ }
    };
    livekit.on("dataReceived", onData);

    const query = `/api/files/text?room=${encodeURIComponent(room)}${repoQ}&path=${encodeURIComponent(path)}`;
    void fetch(query).then((r) => r.json()).then((body) => {
      if (dead) return;
      if (body.error) return;
      if (typeof body.update === "string" && body.update) Y.applyUpdate(doc, unb64(body.update), "seed");
      else if (typeof body.text === "string" && ytext.length === 0) doc.transact(() => ytext.insert(0, body.text), "seed");
      baseline = ytext.toString();
      publish({ t: "s1", room, repo, path, sv: b64(Y.encodeStateVector(doc)) });
      view = new EditorView({
        state: EditorState.create({
          doc: ytext.toString(),
          extensions: [basicSetup, oneDark, langOf(path), yCollab(ytext, awareness), EditorView.lineWrapping],
        }),
        parent,
      });
    });

    const poll = window.setInterval(() => {
      if (Date.now() - typedAt < 1500) return;
      void fetch(query).then((r) => r.json()).then((body) => {
        if (dead || typeof body.text !== "string" || body.text === ytext.toString()) return;
        doc.transact(() => { ytext.delete(0, ytext.length); ytext.insert(0, body.text); }, "disk");
      });
    }, 1500);

    return () => {
      dead = true;
      window.clearTimeout(saveTimer);
      window.clearTimeout(noteTimer);
      window.clearInterval(poll);
      doc.off("update", onUpdate);
      livekit.off("dataReceived", onData);
      awareness.destroy();
      view?.destroy();
      doc.destroy();
    };
  }, [room, repo, path, localParticipant, livekit, repoQ]);

  return <div className="doc-editor" ref={host} />;
}
