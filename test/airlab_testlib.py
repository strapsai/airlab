"""Shared helpers for the airlab test suite.

Kept in a normal importable module (NOT conftest.py) so both the top-level and
the e2e conftest — and the test files — can import from it. Two conftest.py
files can't both be imported under the name `conftest`, so `from conftest import`
is unreliable; import from here instead.
"""
import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CMDS = REPO_ROOT / "usr" / "local" / "bin" / "cmds"
FIXTURE_WS = Path(__file__).resolve().parent / "fixtures" / "airlab_ws"

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(s: str) -> str:
    return _ANSI.sub("", s)


class Result:
    def __init__(self, cp: subprocess.CompletedProcess):
        self.rc = cp.returncode
        self.stdout = strip_ansi(cp.stdout)
        self.stderr = strip_ansi(cp.stderr)
        self.out = self.stdout + self.stderr

    def __repr__(self):
        return f"Result(rc={self.rc}, stdout={self.stdout!r}, stderr={self.stderr!r})"


def all_command_scripts():
    """Every executable command script (cmds/* and version-control/*), minus _lib."""
    names = []
    for p in sorted(CMDS.iterdir()):
        if p.is_file() and os.access(p, os.X_OK):
            names.append(p.name)
    vc = CMDS / "version-control"
    if vc.is_dir():
        for p in sorted(vc.iterdir()):
            if p.is_file() and os.access(p, os.X_OK):
                names.append(f"version-control/{p.name}")
    return names


# --- deterministic git for sandbox fixtures (T2) ------------------------- #
GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
}


def git(*args, cwd=None, check=True):
    env = {**os.environ, **GIT_ENV}
    cp = subprocess.run(["git", *args], cwd=str(cwd) if cwd else None,
                        capture_output=True, text=True, env=env)
    if check and cp.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed ({cp.returncode}): {cp.stderr}")
    return cp.stdout.strip()


def make_bare(path):
    git("init", "--bare", "-b", "main", str(path))
    return Path(path)


def make_clone(remote, dest, origin_url=None):
    git("clone", str(remote), str(dest))
    if origin_url:
        git("remote", "set-url", "origin", origin_url, cwd=dest)
    return Path(dest)


def commit(repo, name="f.txt", content="x", msg="c", push=False):
    (Path(repo) / name).write_text(content)
    git("add", name, cwd=repo)
    git("commit", "-m", msg, cwd=repo)
    if push:
        git("push", "-q", "origin", "HEAD", cwd=repo)
    return head(repo)


def head(repo):
    return git("rev-parse", "HEAD", cwd=repo)


def current_branch(repo):
    return git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo)


def tags(repo):
    out = git("tag", cwd=repo)
    return out.split() if out else []
