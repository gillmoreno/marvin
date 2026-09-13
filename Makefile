# Four processes, four terminals (or `make up` for livekit, then the other three).
include .env
export

up:            ## start livekit-server in docker
	docker compose up -d

down:
	docker compose down

token:         ## dev token endpoint on :8080
	cd worker && uv run python -m marvin.token_server

worker:        ## Marvin joins $(MARVIN_ROOM) and works in $(MARVIN_REPO)
	cd worker && uv run python -m marvin.main --room $(MARVIN_ROOM) --repo $(MARVIN_REPO) --whisper-model $(MARVIN_WHISPER)

web:           ## the room UI on http://localhost:5173
	cd web && pnpm dev

test:
	cd worker && uv run pytest -q

install:
	cd worker && uv sync && cd ../web && pnpm install

# ---------- Sandbox: the image each room's agent runs in when MARVIN_SANDBOX=docker (docs_and_changelog/sandbox.md).
SANDBOX_IMAGE ?= marvin-sandbox:local
SANDBOX_HARNESSES ?= claude-code claude-acp codex gemini opencode grok copilot cursor

sandbox-image: ## build $(SANDBOX_IMAGE); SANDBOX_HARNESSES="claude-code grok" for a smaller one
	docker build --build-arg HARNESSES="$(SANDBOX_HARNESSES)" -t $(SANDBOX_IMAGE) deploy/sandbox

sandbox-ps:    ## the room containers
	docker ps -a --filter label=marvin.room --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'

sandbox-clean: ## remove every room container (they are recreated on the next worker start)
	docker ps -aq --filter label=marvin.room | xargs -r docker rm -f

# ---------- Edge stack: everything in containers behind Caddy (TLS + auth), for a machine other people reach.
EDGE := docker compose -f docker-compose.edge.yml
export MARVIN_INSTALL_DIR ?= $(abspath .)
export MARVIN_GIT_SHA ?= $(shell git rev-parse HEAD 2>/dev/null)
export MARVIN_GIT_REF ?= main

edge-up: sandbox-image ## build + start livekit, worker, web and Caddy; password login (MARVIN_ROOM_PASSWORD)
	$(EDGE) up -d --build

update: ## pull origin/$(MARVIN_GIT_REF) and rebuild the edge stack (same as Settings → Update)
	@deploy/edge/update.sh

edge-oidc-up: sandbox-image ## same, with single sign-on through oauth2-proxy (MARVIN_AUTH=header, OAUTH2_PROXY_* in .env)
	MARVIN_AUTH=header MARVIN_CADDYFILE=./deploy/edge/Caddyfile.oidc $(EDGE) --profile oidc up -d --build

edge-down:
	$(EDGE) --profile oidc down

edge-logs:     ## follow all edge containers
	$(EDGE) --profile oidc logs -f --tail=100

edge-ps:
	$(EDGE) --profile oidc ps

# ---------- Images (see deploy/k8s/README.md)
# Override REGISTRY with your own: `make image REGISTRY=ghcr.io/<owner>`. CI pushes the same names with GITHUB_TOKEN.
REGISTRY ?= ghcr.io/$(shell git config --get remote.origin.url 2>/dev/null | sed -E 's#.*[:/]([^/]+)/[^/]+$$#\1#' | tr 'A-Z' 'a-z' | grep . || echo owner)
IMAGE ?= $(REGISTRY)/marvin
STT_IMAGE ?= $(REGISTRY)/marvin-stt
TAG ?= $(shell date +%Y%m%d-%H%M%S)

image-local:   ## build the amd64 image locally (no push)
	docker buildx build --platform linux/amd64 -t marvin:dev --load .

image:         ## build for amd64 and push $(IMAGE):TAG and :latest
	docker buildx build --platform linux/amd64 -t $(IMAGE):$(TAG) -t $(IMAGE):latest --push .

stt-image-local: ## build the streaming STT image (amd64, no push)
	docker buildx build --platform linux/amd64 -t marvin-stt:dev --load stt/

stt-image:     ## build + push the streaming STT image as $(STT_IMAGE):TAG and :latest
	docker buildx build --platform linux/amd64 -t $(STT_IMAGE):$(TAG) -t $(STT_IMAGE):latest --push stt/

# ---------- Kubernetes (see deploy/k8s/README.md)
k8s-apps:      ## regenerate the apps Ingress/ConfigMap from the `ports` list in rooms.yaml
	cd worker && uv run python ../deploy/gen_apps.py ../deploy/k8s/rooms.yaml > ../deploy/k8s/apps.yaml

k8s-dry-run:   ## validate manifests against the cluster without creating anything
	kubectl apply -k deploy/k8s --dry-run=server

k8s-deploy:
	kubectl apply -k deploy/k8s

k8s-restart:   ## roll the pod (picks up a new :latest image)
	kubectl rollout restart -n marvin statefulset/marvin

k8s-logs:
	kubectl logs -n marvin statefulset/marvin -c worker -f --tail=200

stt-local:     ## run the STT service locally (CPU/MPS; slow but functional)
	cd stt && uv run --no-sync python -m marvin_stt --port 8765

stt-bench:     ## stream a sentence to a running service and print latencies (URL=ws://host:8765/v1/stream)
	cd stt && uv run --no-sync python -m marvin_stt.client $(or $(URL),ws://127.0.0.1:8765/v1/stream) --say "Marvin, is the retry logic exponential with a cap?" --lang en-US

stt-restart:   ## roll the STT pod
	kubectl -n marvin rollout restart deploy/marvin-stt

stt-off:       ## scale STT to 0 (a cluster autoscaler can then remove the GPU node)
	kubectl -n marvin scale deploy/marvin-stt --replicas=0

stt-on:
	kubectl -n marvin scale deploy/marvin-stt --replicas=1

# ---------- power (cost control on the cluster)
marvin-up:     ## wake the cluster deployment (room + GPU transcription)
	@deploy/marvin-onoff.sh on
marvin-down:   ## scale it to zero (volumes persist)
	@deploy/marvin-onoff.sh off
marvin-status:
	@deploy/marvin-onoff.sh status
