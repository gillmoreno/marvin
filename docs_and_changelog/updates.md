# Updating an install

The appliance is a git checkout plus `make edge-up`. First boot clones `main` (or `git_ref`) and builds
images. After that the VM stays on that snapshot until someone updates it.

## In the app

Settings → **This machine** (admin) compares the running image (`MARVIN_GIT_SHA`) to GitHub
`MARVIN_GIT_REF` (default `main`). When it is behind, the panel lists the commit subjects and an
**Update now** button. After the machine is ready, the project workspace shows the same status before anyone joins a room.
**What changed** reads the human-friendly entries in `product-updates.json` from the target branch;
commit subjects are only the fallback when a release has no product note.

The button starts a sibling container (`marvin-update`), not a child of the worker. Compose rebuilds
the worker mid-update; if the script ran inside the worker it would die with the container and leave
the page on “worker unreachable”. The sibling writes `/work/state/update.log` and `update.json`.
Settings reads those files from the web container even while the worker is down. Stay on that page:
the step line and the log are what is actually happening.

`deploy/edge/update.sh` does `git fetch` + `reset --hard` to `origin/<ref>`, rebuilds the sandbox
image, then `docker compose … up -d --build`. `.env` is untracked and is left alone (passwords,
LiveKit keys, session secret). Rooms disconnect for the length of the build. That is expected.

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
