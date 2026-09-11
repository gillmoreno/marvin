# Marvin on Kubernetes

One Pod in namespace `marvin`, five containers, two volumes, applied with `kubectl apply -k`. This is a plain example
for any cluster with an nginx ingress controller; swap the storage class, ingress class and hostnames for yours.

```
browser ──https──▶ ingress (marvin.example.com) ──▶ marvin-web :8080      (UI + /api/token + /api proxy)
                                                 └─▶ marvin-livekit :7880 (/rtc signaling ws)
                                                 └─▶ marvin-gate :8091    (/power, and the whole host while asleep)
browser ──udp/tcp──▶ marvin-livekit :7881/:7882 (direct media)  or  :3478 (coturn, by hostname, when IPs are not reachable)
Pod: [livekit] [coturn] [worker: whisper + bridge + Claude Code, DOCKER_HOST=localhost:2375] [web] [apps-proxy] [dind: privileged]
     /work (100Gi): repos, Claude home, whisper cache, per-room state    /var/lib/docker (100Gi): dind layer cache
```

## First deploy

1. **Images**: CI pushes `ghcr.io/<owner>/marvin` and `ghcr.io/<owner>/marvin-stt` on every push to `main`
   (`.github/workflows/`). Or build yourself: `make image REGISTRY=ghcr.io/<owner>` (and `make stt-image` if you
   want GPU streaming STT). Put the names in `kustomization.yaml` under `images:` (replace `OWNER`). If the GHCR
   package is private, add an `imagePullSecrets` entry to `service-account.yaml`.
2. **Secrets**: `cp secrets.env.example secrets.env` and fill in. `LIVEKIT_API_SECRET` must be 32+ chars.
   Claude auth is `ANTHROPIC_API_KEY` (or Bedrock/Vertex credentials, see the Claude Agent SDK docs). Do not use a
   personal Claude Pro/Max OAuth token here: Anthropic's terms forbid using those outside Claude Code / claude.ai.
   `GITHUB_TOKEN` is optional and makes `git` over HTTPS and `gh pr create` work.
3. **Hostnames**: replace `marvin.example.com` in `ingress.yaml`, and `domain:` in `rooms.yaml`. Every app port in
   `rooms.yaml` becomes `marvin-<port>.<domain>`; create those DNS records (a wildcard `*.<domain>` is easiest) or run
   external-dns. TLS is your ingress controller's business (cert-manager, a wildcard cert, ...). The mic only works
   over HTTPS.
4. **Git access** for cloning repos on the /work volume (optional, only for `git_url` rooms without a `GITHUB_TOKEN`):
   ```sh
   kubectl create ns marvin
   kubectl -n marvin create secret generic marvin-git-ssh --from-file=id_ed25519=/path/to/deploy_key
   ```
5. **Rooms**: edit `rooms.yaml`, then `make k8s-apps` to regenerate `apps.yaml` (the apps Ingress + ConfigMap).
6. **Deploy**: `make k8s-dry-run` then `make k8s-deploy`.

## When clients can only reach hostnames (VPN / strict firewall)

Some VPNs and firewalls let browsers resolve and reach DNS names under your domain, but never raw Pod or Service IPs.
WebRTC candidates are raw IPs, so direct media fails; TURN is addressed by hostname, so it works. The manifests
already run a coturn sidecar and `livekit.yaml` advertises it as `marvin-turn.example.com`. To use it:

1. Pin `clusterIP` on the `marvin-livekit` Service (`services.yaml`) and create an A record
   `marvin-turn.<domain> -> <that IP>` in the zone your clients resolve (a private zone, typically). A TURN hostname
   plus its DNS record is required in this setup; ClusterIP Services are not published by external-dns.
2. Set `MARVIN_ICE_RELAY_ONLY=true` on the `web` container (`statefulset.yaml`): the token endpoint then tells
   browsers to use relay-only ICE, so they skip the unroutable direct candidates.
3. Check: `echo | nc -u -w 2 marvin-turn.<domain> 3478` from a client; any reply means UDP arrives. In Chrome,
   chrome://webrtc-internals should show the selected candidate pair as `relay`.

If your clients can reach the Service/Pod IPs directly (plain LAN, or a VPN that routes the cluster CIDR), skip all
this and leave `MARVIN_ICE_RELAY_ONLY` at `false`.

## Verify

```sh
kubectl -n marvin get pod,svc,ingress,pvc
make k8s-logs                                  # worker: "serving N room(s)"
curl https://marvin.example.com/api/rooms
```
Then open the UI, join a room, allow the mic, say "Marvin, what does this repo do".

## Day to day

- New app to expose: add the port to `ports` in `rooms.yaml` (and an `app_links` entry with that `port`),
  `make k8s-apps`, `make k8s-deploy`. The compose file in that repo publishes the port (`-p 3000:3000`); dind shares
  the Pod network, so the proxy reaches it on 127.0.0.1.
- New image: `make image && make k8s-restart` (or let CI push `:latest` and roll the pod).
- Claude Code sessions resume across restarts per room (`/work/state/<room>.json`).
- "Always allow" in the UI lets Marvin run anything in the Pod without asking. The blast radius is this Pod and its volumes.

## Power (cost control)

`make marvin-down` / `make marvin-up` / `make marvin-status` scale the StatefulSet and the STT Deployment to zero and
back (volumes persist). While asleep the URL shows "Marvin is asleep" with a Wake button, served by the `marvin-gate`
Deployment (`worker/marvin/gate.py`, the ingress default backend + `/power`). The gate also runs a schedule:
`MARVIN_SLEEP_AT` (every day, unless someone is in a room) and `MARVIN_WAKE_AT` (weekdays), read in the `TZ` timezone
(`gate.yaml`). Settings in the room UI has "put Marvin to sleep". If a GitOps tool manages this app, make it ignore
replica counts or it will undo the scaling.

## Streaming STT (GPU)

`stt.yaml` runs the `marvin-stt` service (NVIDIA Nemotron 3.5 ASR streaming through NeMo, see `../../stt/README.md`)
as a one-replica Deployment requesting one GPU (a T4 or L4 is enough; fp16 on a T4). Add the tolerations /
nodeAffinity your GPU node pool needs. The worker reads `MARVIN_STT_URL` (`ws://marvin-stt:8765/v1/stream`); remove
that env var, or drop `stt.yaml` from the kustomization, to run on local Whisper only. No GPU is required for Marvin.

- Image: `make stt-image` pushes `ghcr.io/<owner>/marvin-stt`.
- First start downloads the 2.4 GB checkpoint into the `marvin-stt-cache` PVC (startup probe allows 15 min).
- `make stt-off` / `make stt-on` scale it to 0 and back; with a cluster autoscaler the GPU node goes with it.
- Smoke test from a laptop: `kubectl -n marvin port-forward deploy/marvin-stt 8765:8765` then `make stt-bench`.
- Logs print one line per utterance with latency, detected language and text: `kubectl -n marvin logs deploy/marvin-stt -f`.

## Not done yet

- SSO on the ingress (a commented `auth-url` example is in `ingress.yaml`). Without it, anyone who can reach the
  hostname can join a room and approve tool calls: keep it on a private network until then.
- Resource requests are a guess: worker 3 CPU / 6Gi, dind 2 CPU / 4Gi. Watch `kubectl top pod -n marvin` during a real meeting.
- Whisper runs on CPU (`small`, int8). A GPU node is not required.
