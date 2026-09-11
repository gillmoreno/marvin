# Spin-out notes (Albi -> Marvin, 2026-09-11)

Decisions made while turning the internal repo into the public Marvin project, and things worth a second look.

## Decisions that were not spelled out in the brief

1. **`settings.py` deleted outright.** It contained only the CodeArtifact token logic, so the module, its tests, and
   the `/api/settings*` routes (admin API and token-server proxy) are gone. The web `SettingsPanel` now only hosts
   the per-room section (`RoomAndMachine`) and the power section. `useSettings` / `registryWarning` / the orange
   warning box in the left column were removed along with their CSS (`.warnbox`).
2. **Console scripts added.** `worker/pyproject.toml` now declares `marvin`, `marvin-web`, `marvin-gate`;
   `stt/pyproject.toml` declares `marvin-stt`. `python -m marvin.main` etc. still work and are what the Dockerfile,
   Makefile and manifests use.
3. **Gate timezone default: UTC.** `Schedule.tz` defaulted to `Europe/Rome`; it is now `UTC` in code and in
   `gate.yaml` (still set by `TZ`). `test_gate.py` passes `tz="Europe/Rome"` explicitly because its fixtures are
   written in Rome time.
4. **`CLAUDE_CODE_OAUTH_TOKEN` removed from `secrets.env.example`.** The brief asked for an authentication note that
   personal Pro/Max OAuth tokens must not be used on a shared server, so the example no longer offers that path. The
   Claude Agent SDK would still honour the variable if someone sets it; nothing in Marvin's code references it.
5. **`gen_apps.py` made configurable.** `domain`, `ui_host` and `ingress_class` are read from `deploy/k8s/rooms.yaml`
   (defaults `example.com`, `marvin.<domain>`, `nginx`). The external-dns `alias`/`target` annotations were dropped
   (they encoded the internal ALB); the README tells people to create DNS records or run external-dns themselves.
   `apps.yaml` was regenerated from the new inputs.
6. **Pinned ClusterIP removed, mechanism kept.** `services.yaml` no longer pins `172.20.250.10`; a commented
   `clusterIP` line and the k8s README explain when to pin it and create a TURN A record. `MARVIN_ICE_RELAY_ONLY` is
   `"false"` in `statefulset.yaml` by default (was `"true"`, which only makes sense with the TURN hostname set up).
7. **GPU scheduling made generic.** `stt.yaml` keeps the `nvidia.com/gpu` toleration and the GPU resource request;
   the company node-pool tolerations and Karpenter label affinity were replaced by a commented generic
   `nvidia.com/gpu.product` example.
8. **Ingress class `nginx`.** `nginx-private-controller` -> `nginx` in `ingress.yaml` and the generator. The
   controller-specific annotations (`configuration-snippet`, `default-backend`) are kept because the mic
   Permissions-Policy header and the sleep page depend on them.
9. **`storageClassName: gp3` kept** in `statefulset.yaml` and `stt.yaml` (AWS default name, but harmless as an
   example); the comment says to adjust it.
10. **CI rewritten from scratch.** The old workflows used company composite actions and self-hosted runners. The
    new ones use `ubuntu-latest`, `astral-sh/setup-uv`, `pnpm/action-setup`, `docker/build-push-action` with GHA
    cache, and push to GHCR with `GITHUB_TOKEN` (`permissions: packages: write`). A `test` job (worker pytest, web
    tsc + build; STT protocol tests) gates the image job. PRs build without pushing. Markdown-only and
    `docs_and_changelog/` changes do not trigger the worker image.
11. **Makefile `REGISTRY` default** is derived from the git remote owner (lower-cased) and falls back to
    `ghcr.io/owner` when there is no remote; override with `make image REGISTRY=ghcr.io/<owner>`.
12. **STT image tags** changed from `<repo>:stt-<tag>` (same ECR repo) to a separate image `marvin-stt:<tag>` /
    `:latest`, matching the GHCR layout. `kustomization.yaml` `images:` uses `ghcr.io/OWNER/marvin` and
    `ghcr.io/OWNER/marvin-stt` with `OWNER` to be replaced.
13. **Internal project names in tests.** `oxygen` (an internal repo name) became `backend` in `test_config.py` and
    `test_manager.py`; the RoomPicker placeholder URL is `https://github.com/your-org/your-repo`.
14. **`rooms.local.yaml`** had a personal absolute path; it is now `/path/to/a/repo`.
15. **`.env.example` `MARVIN_REPO`** placeholder kept as a path the user must edit.
16. **Wake-word fuzzy comment** in `bridge/wake.py` updated to a Marvin example (`"marvin" vs "marvyn"`); the logic
    is unchanged and name-agnostic.
17. **`stt/uv.lock` not committed.** The original repo had no lockfile for `stt/` (the Docker image installs CUDA
    wheels from the PyTorch index, which a local lock would not describe). `uv sync` creates one locally; it was
    deleted before the commit. Add it to `.gitignore` or commit it deliberately if you want it.
18. **Web `pnpm-lock.yaml`** did not contain the old name, so it was left untouched.

## Things to double-check

- **GHCR visibility.** New GHCR packages are private by default. Either make `marvin` and `marvin-stt` public in the
  package settings or add an `imagePullSecrets` entry to `deploy/k8s/service-account.yaml`.
- **`.github/workflows` first run.** The worker test job runs `uv sync --frozen`; the lock was regenerated today so
  it matches. If you bump dependencies, re-run `uv lock`.
- **`Schedule` default timezone change** (UTC) is a behaviour change for anyone reusing the old `gate.yaml` values
  without `TZ`.
- **Relay-only ICE default flipped to `false`** in `statefulset.yaml`. Set it back to `true` where clients cannot
  reach Pod/Service IPs (see the k8s README section).
- **Local storage keys** in the UI changed (`albi.*` -> `marvin.*`): returning users re-enter name/room once.
- **Model list in `worker/marvin/admin.py`** (`MODELS`) is unchanged; review whether those model ids should be the
  public defaults.
- **System prompt** still says `~/.claude/CLAUDE.md` lives under `/work/repos`-style paths; fine for the image,
  slightly off for local runs (it was already so).
- **`README.md` "Model" section** lists the same model names the UI shows; update together with `MODELS`.
- **License** is still "to be decided". Add a `LICENSE` file before publishing.
- **Old history.** The public repo starts fresh; the original history (with internal hostnames and account IDs) is
  only in the original internal repository. Do not `git fetch` it into this one.
- **Secrets.** Nothing in the tree contains keys; `.env`, `deploy/k8s/secrets.env`, `web/certs/` are gitignored.
  `deploy/k8s/secrets.env.example` has `LIVEKIT_API_KEY=marvin` and an empty secret placeholder only.

## Verification performed

- `cd worker && uv sync && uv run pytest -q`: 44 passed (2 aiohttp deprecation warnings, pre-existing).
- `cd stt && uv sync && uv run pytest -q tests/test_server_protocol.py`: 4 passed. `test_engine_real.py` is opt-in
  via `MARVIN_STT_REAL=1` and was not run (downloads the 2.4 GB model).
- `cd web && pnpm install && pnpm exec tsc --noEmit && pnpm build`: clean (one pre-existing Vite chunk-size warning).
- Case-insensitive `rg --hidden` for the old name, the company name, the AWS account id, the VPN product, the
  GitOps repo, the private registry and the internal domain (excluding `.git`, `node_modules`, `.venv`, `dist`):
  no matches outside `docs_and_changelog/`, where the old name appears only in this file and the changelog entry
  that documents the rename.
- `deploy/k8s/apps.yaml` regenerated with `make k8s-apps` (via `uv run`).
