#!/bin/sh
# Run Dex + oauth2-proxy + Caddy on the host when Docker is not available.
# Usage: sso-dev-host.sh [start|stop]
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
DIR="$ROOT/.sso-dev"
BIN="$DIR/bin"
LOG="$DIR/log"
mkdir -p "$BIN" "$LOG"

stop() {
  for name in caddy oauth2-proxy dex; do
    if [ -f "$DIR/$name.pid" ]; then
      pid=$(cat "$DIR/$name.pid")
      kill "$pid" 2>/dev/null || true
      rm -f "$DIR/$name.pid"
    fi
  done
}

if [ "${1:-start}" = "stop" ]; then
  stop
  exit 0
fi

if [ ! -x "$BIN/caddy" ]; then
  echo "downloading caddy…"
  curl -fsSL "https://github.com/caddyserver/caddy/releases/download/v2.10.2/caddy_2.10.2_mac_arm64.tar.gz" | tar -xz -C "$BIN" caddy
fi
if [ ! -x "$BIN/oauth2-proxy" ]; then
  echo "downloading oauth2-proxy…"
  tmp=$(mktemp -d)
  curl -fsSL "https://github.com/oauth2-proxy/oauth2-proxy/releases/download/v7.8.1/oauth2-proxy-v7.8.1.darwin-arm64.tar.gz" | tar -xz -C "$tmp"
  mv "$tmp"/oauth2-proxy-*/oauth2-proxy "$BIN/oauth2-proxy"
  rm -rf "$tmp"
fi
if [ ! -x "$BIN/dex" ]; then
  echo "building dex (once)…"
  src=$(mktemp -d)
  git clone --depth 1 --branch v2.42.1 https://github.com/dexidp/dex.git "$src/dex"
  (cd "$src/dex" && go build -o "$BIN/dex" ./cmd/dex)
  rm -rf "$src"
fi

stop
nohup "$BIN/dex" serve "$ROOT/deploy/edge/dex-local.yaml" >"$LOG/dex.log" 2>&1 &
echo $! >"$DIR/dex.pid"
nohup "$BIN/oauth2-proxy" \
  --provider=oidc \
  --oidc-issuer-url=http://127.0.0.1:8088/dex \
  --skip-oidc-discovery \
  --login-url=http://127.0.0.1:8088/dex/auth \
  --redeem-url=http://127.0.0.1:5556/dex/token \
  --oidc-jwks-url=http://127.0.0.1:5556/dex/keys \
  --profile-url=http://127.0.0.1:5556/dex/userinfo \
  --validate-url=http://127.0.0.1:5556/dex/userinfo \
  --client-id=marvin \
  --client-secret=marvin-local \
  --redirect-url=http://127.0.0.1:8088/oauth2/callback \
  --http-address=127.0.0.1:4180 \
  --reverse-proxy=true \
  --set-xauthrequest=true \
  --upstream=static://202 \
  --cookie-secure=false \
  --cookie-secret=0123456789abcdef0123456789abcdef \
  --whitelist-domain=127.0.0.1:8088 \
  --email-domain='*' \
  --user-id-claim=email \
  --insecure-oidc-allow-unverified-email=true \
  --scope='openid email profile' \
  --skip-provider-button=true \
  --approval-prompt=auto \
  --prefer-email-to-user=true \
  >"$LOG/oauth2-proxy.log" 2>&1 &
echo $! >"$DIR/oauth2-proxy.pid"
nohup "$BIN/caddy" run --config "$ROOT/deploy/edge/Caddyfile.sso-dev-host" --adapter caddyfile >"$LOG/caddy.log" 2>&1 &
echo $! >"$DIR/caddy.pid"
echo "local SSO on http://127.0.0.1:8088 (maria@acme.com / maria, alex@acme.com / alex)"
