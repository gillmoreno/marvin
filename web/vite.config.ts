import fs from "node:fs";
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Browsers only allow the microphone on HTTPS (or localhost), so the dev server serves TLS with a
// self-signed cert (web/certs, see README) and proxies both the token endpoint and LiveKit's signaling
// websocket, so a laptop on the LAN needs exactly one address: https://<this machine's IP>:5173
const certDir = path.resolve(__dirname, "certs");
const haveCert = fs.existsSync(path.join(certDir, "dev.crt"));
// The token endpoint (`marvin-web`) listens on MARVIN_TOKEN_PORT (default 8080); keep the proxy in step with it.
const apiPort = process.env.MARVIN_TOKEN_PORT || "8080";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    https: haveCert ? { key: fs.readFileSync(path.join(certDir, "dev.key")), cert: fs.readFileSync(path.join(certDir, "dev.crt")) } : undefined,
    proxy: {
      "/api": `http://127.0.0.1:${apiPort}`,
      "/rtc": { target: "ws://127.0.0.1:7880", ws: true, changeOrigin: true },
    },
  },
});
