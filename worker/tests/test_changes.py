import subprocess

import pytest

from marvin.changes import changes, file_diff

ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/opt/homebrew/bin"}


def git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, env=ENV, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    (r / "a.py").write_text("print(1)\n")
    (r / "keep.txt").write_text("x\n")
    git(r, "add", "."); git(r, "commit", "-q", "-m", "init")
    return r


async def test_no_git(tmp_path):
    c = await changes(str(tmp_path))
    assert not c.git and c.files == []


async def test_clean_on_main(repo):
    c = await changes(str(repo))
    assert c.git and c.branch == "main" and c.base == "HEAD" and c.files == []


async def test_branch_committed_uncommitted_and_untracked(repo):
    git(repo, "checkout", "-q", "-b", "marvin/room/topic")
    (repo / "a.py").write_text("print(1)\nprint(2)\n")
    git(repo, "commit", "-q", "-am", "committed on branch")
    (repo / "a.py").write_text("print(1)\nprint(2)\nprint(3)\n")   # uncommitted on top
    (repo / "new.py").write_text("new = True\n")                      # untracked
    (repo / "keep.txt").unlink()                                      # deleted, uncommitted
    c = await changes(str(repo))
    assert c.branch == "marvin/room/topic" and c.base.startswith("main@")
    by = {f.path: f for f in c.files}
    assert by["a.py"].status == "M" and by["a.py"].additions == 2   # both commits vs base
    assert by["new.py"].status == "?" and by["new.py"].additions == 1
    assert by["keep.txt"].status == "D" and by["keep.txt"].deletions == 1
    d = await file_diff(str(repo), "a.py")
    assert "+print(2)" in d and "+print(3)" in d
    d2 = await file_diff(str(repo), "new.py")
    assert "+new = True" in d2
    with pytest.raises(ValueError):
        await file_diff(str(repo), "../etc/passwd")
