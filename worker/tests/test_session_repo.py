import subprocess

from marvin.config import RoomConfig
from marvin.room.session import ensure_repo


def test_missing_repo_without_git_url_becomes_sandbox(tmp_path):
    cfg = RoomConfig(name="sandbox", repo=str(tmp_path / "new"))
    ensure_repo(cfg)
    assert (tmp_path / "new").is_dir()


def test_existing_repo_untouched(tmp_path):
    (tmp_path / "x").mkdir()
    ensure_repo(RoomConfig(name="x", repo=str(tmp_path / "x"), git_url="git@nowhere:never.git"))  # no clone attempted


def test_clone_when_git_url_and_missing(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    subprocess.run(["git", "init", "-q", str(src)], check=True)
    subprocess.run(["git", "-C", str(src), "commit", "-q", "--allow-empty", "-m", "init"], check=True, env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/opt/homebrew/bin"})
    dst = tmp_path / "dst"
    ensure_repo(RoomConfig(name="c", repo=str(dst), git_url=str(src)))
    assert (dst / ".git").is_dir()
