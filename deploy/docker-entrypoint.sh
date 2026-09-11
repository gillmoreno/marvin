#!/bin/sh
# /work is a persistent volume shared with the dind sidecar; make the directories Marvin writes to.
set -e
mkdir -p "${HOME:-/work/home}" "${HF_HOME:-/work/cache/hf}" "${MARVIN_STATE_DIR:-/work/state}" "${MARVIN_REPOS_DIR:-/work/repos}"

# Git identity for commits Marvin makes (the Requested-by trailer names the human).
git config --global user.name  "${MARVIN_GIT_NAME:-Marvin}"
git config --global user.email "${MARVIN_GIT_EMAIL:-marvin@example.com}"
git config --global init.defaultBranch main
git config --global --add safe.directory '*'

# GitHub over HTTPS with a token from the Secret: git pushes and `gh` both use it. The token never touches disk.
if [ -n "$GITHUB_TOKEN" ]; then
  export GH_TOKEN="${GH_TOKEN:-$GITHUB_TOKEN}"
  git config --global credential.helper '!f() { echo "username=x-access-token"; echo "password=$GITHUB_TOKEN"; }; f'
  git config --global url."https://github.com/".insteadOf "git@github.com:"
fi
# Optional git deploy key mounted as a Secret (ssh). Used when there is no token.
if [ -f /etc/marvin/ssh/id_ed25519 ] && [ -z "$GIT_SSH_COMMAND" ]; then
  export GIT_SSH_COMMAND="ssh -i /etc/marvin/ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
fi
exec "$@"
