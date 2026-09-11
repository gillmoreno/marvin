"""What changed in a room's repo: files and diffs of the working tree against the branch base.

"Base" is the merge-base with main (or master) when the room works on a branch, otherwise HEAD. So on a feature
branch the view is everything the room did (committed or not); on main it is the uncommitted work.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, dataclass

MAX_DIFF_BYTES = 400_000


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str  # M A D R ? (untracked)
    additions: int
    deletions: int


@dataclass(frozen=True)
class Changes:
    repo: str
    git: bool
    branch: str | None
    base: str | None  # short ref the diff is against
    files: list[ChangedFile]

    def to_wire(self) -> dict:
        d = asdict(self)
        return d


async def _git(repo: str, *args: str, ok_codes=(0,)) -> str:
    proc = await asyncio.create_subprocess_exec("git", "-C", repo, *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    if proc.returncode not in ok_codes:
        raise RuntimeError(err.decode(errors="replace").strip() or f"git {' '.join(args)} failed")
    return out.decode(errors="replace")


async def base_ref(repo: str, branch: str | None) -> str | None:
    if branch in (None, "HEAD", "main", "master"):
        return "HEAD"
    for cand in ("origin/main", "main", "origin/master", "master"):
        try:
            mb = (await _git(repo, "merge-base", cand, "HEAD")).strip()
            if mb:
                return mb
        except RuntimeError:
            continue
    return "HEAD"


async def changes(repo: str) -> Changes:
    if not os.path.isdir(os.path.join(repo, ".git")):
        return Changes(repo=repo, git=False, branch=None, base=None, files=[])
    branch = (await _git(repo, "rev-parse", "--abbrev-ref", "HEAD")).strip() or None
    has_commits = (await _git(repo, "rev-parse", "--verify", "-q", "HEAD", ok_codes=(0, 1))).strip() != ""
    base = await base_ref(repo, branch) if has_commits else None
    files: dict[str, ChangedFile] = {}
    if base:
        # tracked changes vs base (committed on the branch + uncommitted), with rename detection
        stat = await _git(repo, "diff", "--numstat", "-M", base, "--")
        names = await _git(repo, "diff", "--name-status", "-M", base, "--")
        status = {}
        for line in names.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                status[parts[-1]] = parts[0][0]
        for line in stat.splitlines():
            a, d, path = line.split("\t", 2)
            if "\t" in path:  # rename: old\tnew
                path = path.split("\t")[-1]
            files[path] = ChangedFile(path=path, status=status.get(path, "M"), additions=int(a) if a.isdigit() else 0, deletions=int(d) if d.isdigit() else 0)
    for path in (await _git(repo, "ls-files", "--others", "--exclude-standard")).splitlines():
        if path and path not in files:
            try:
                n = (await _git(repo, "diff", "--no-index", "--numstat", "/dev/null", path, ok_codes=(0, 1))).split("\t")
                adds = int(n[0]) if n and n[0].isdigit() else 0
            except Exception:
                adds = 0
            files[path] = ChangedFile(path=path, status="?", additions=adds, deletions=0)
    short = None
    if base:
        short = "HEAD" if base == "HEAD" else (await _git(repo, "rev-parse", "--short", base)).strip()
        if base != "HEAD":
            short = f"main@{short}"
    return Changes(repo=repo, git=True, branch=branch, base=short, files=sorted(files.values(), key=lambda f: f.path))


async def file_diff(repo: str, path: str) -> str:
    """Unified diff for one file against the base (or the whole file for an untracked one)."""
    if os.path.isabs(path) or ".." in path.split("/"):
        raise ValueError("bad path")
    branch = (await _git(repo, "rev-parse", "--abbrev-ref", "HEAD")).strip() or None
    base = await base_ref(repo, branch)
    tracked = (await _git(repo, "ls-files", "--error-unmatch", path, ok_codes=(0, 1))).strip() != ""
    if tracked:
        out = await _git(repo, "diff", "-M", base, "--", path)
    else:
        out = await _git(repo, "diff", "--no-index", "/dev/null", path, ok_codes=(0, 1))
    if len(out) > MAX_DIFF_BYTES:
        out = out[:MAX_DIFF_BYTES] + "\n… diff truncated …\n"
    return out
