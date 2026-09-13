# Updating an install

The appliance is a git checkout plus `make edge-up`. First boot clones `main` (or `git_ref`) and builds
images. After that the VM stays on that snapshot until someone updates it.

## In the app

Settings → **This machine** (admin) compares the running image (`MARVIN_GIT_SHA`) to GitHub
`MARVIN_GIT_REF` (default `main`). When it is behind, the panel lists the commit subjects and an
**Update this machine** button.

Update runs `deploy/edge/update.sh` on the checkout: `git fetch` + `reset --hard` to `origin/<ref>`,
rebuild the sandbox image, `docker compose … up -d --build`. `.env` is untracked and is left alone
(passwords, LiveKit keys, session secret). Rooms disconnect for the length of the build.

The worker can do this because the checkout is mounted at the same host path (`MARVIN_INSTALL_DIR`)
and it already has the host Docker socket.

A laptop `make up` / Vite loop has no checkout mount. The panel still shows the commits; the button
stays off. Use `git pull` there.

## From a shell

```
cd /home/ubuntu/marvin   # or this repo
make update              # same script as the button
```

`make edge-up` alone rebuilds whatever is already on disk. It does not pull.

## First update after a new box

Cloud-init clones whatever was on GitHub at boot. The Settings panel only exists after that code is
on the box. The first time you want this button, either wait until a later image includes it, or
`git pull && make edge-up` once over SSM. After that, updates stay in the browser.
