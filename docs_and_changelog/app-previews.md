# App previews

The room embeds whatever the agent has started (Vite, Rails, nginx, …) in the middle column. This page is how
those URLs are built and why they are children of **this install's** hostname, not a Marvin-wide domain.

## One install, one hostname

`MARVIN_DOMAIN` is the name people type to reach the room (`marvin.aigil.dev` on the pilot, `marvin.acme.com` at a
customer). Preview hosts are one label under that name:

```
https://p3000.marvin.aigil.dev   →  the process listening on port 3000 in the worker's network
https://p5173.marvin.acme.com    →  the same idea on another machine
```

A wildcard DNS record can point at **one** IP. `*.marvin.aigil.dev` is therefore this VM, not every Marvin in the
world. Putting every customer's running app on `aigil.dev` would mean their traffic lands on our box — a hosted
edge, with our name on their product, our abuse and GDPR surface. That is the hosted tier, and it is deferred
(`roadmap.md`, `decisions-log.md`).

Each customer who installs Marvin sets their own `MARVIN_DOMAIN` and two DNS records (below). The formula does not
change.

## DNS

On the zone that owns `MARVIN_DOMAIN`:

1. `A MARVIN_DOMAIN` → this VM (already required for the room).
2. `A *.MARVIN_DOMAIN` → the same IP.

Both must be **DNS only** (grey-cloud on Cloudflare). If the wildcard is proxied, WebRTC is fine on the apex but
preview TLS and websockets go through the proxy and break. Let's Encrypt talks to the VM (tls-alpn-01 / HTTP-01),
not to Cloudflare.

No `*.parent-zone` record is required. The pilot could not have `*.aigil.dev`; `*.marvin.aigil.dev` is enough.

## TLS

Caddy does **not** get a wildcard certificate. Each preview name (`p3000.…`) gets its own cert on first visit
(on-demand TLS). Before issuing, Caddy asks `GET /tls-ask?domain=…` on the token server; only
`{prefix}{port}.{MARVIN_DOMAIN}` (default prefix `p`) is allowed. A random name pointed at the IP cannot burn
the Let's Encrypt quota.

`MARVIN_DOMAIN` has to exist before the UI (Caddy boots on it). Settings → **App previews** shows the pattern
and where it comes from; it is not edited there.

## Local and Kubernetes

- No `MARVIN_DOMAIN` / `MARVIN_APPS_HOST`: links stay `http://localhost:{port}` (the four-terminal loop).
- `MARVIN_APPS_DOMAIN` (the older k8s ConfigMap, a parent zone) still builds `https://marvin-{port}.{that-zone}`
  so existing ingress rules keep working. New edge installs should not set it; they use `MARVIN_DOMAIN`.
- `MARVIN_APPS_HOST` / `MARVIN_APPS_PREFIX` override the host and the label if a site must differ from the UI name.

## What the browser hits

```
iframe  →  https://p3000.<MARVIN_DOMAIN>
        →  Caddy (TLS)  →  apps (nginx)  →  worker:<port>
```

Room sandboxes join the worker's network namespace, so the agent's port is on `worker`. The Marvin login cookie
is host-only on `MARVIN_DOMAIN` and is not sent to `p3000.…`. Preview responses allow framing only from
`https://<MARVIN_DOMAIN>`.
