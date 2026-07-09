"""Shared pytest fixtures/helpers for the airlab test suite.

Design (see test/README.md):
- Commands are standalone bash scripts run IN-PLACE by absolute path with
  $AIRLAB_PATH pointed at a dummy workspace — no install required.
- The dummy workspace is COPIED to a tmp dir per test so tests may mutate it.
- resolve_ssh_address() reaches $AIRLAB_PATH/robot/robots.py (a stub here).
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

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


@pytest.fixture
def airlab_ws(tmp_path):
    """A fresh, mutable copy of the dummy workspace; returns its Path."""
    dst = tmp_path / "airlab_ws"
    shutil.copytree(FIXTURE_WS, dst)
    # ensure the stub resolver is executable after copy
    (dst / "robot" / "robots.py").chmod(0o755)
    return dst


@pytest.fixture
def run(airlab_ws):
    """Return run(cmd, *args, ws=..., env=..., input=...) -> Result.

    `cmd` is a command name under cmds/ (e.g. "ssh") or a relative path
    (e.g. "version-control/vcs"). $AIRLAB_PATH defaults to the copied workspace.
    """
    def _run(cmd, *args, ws=None, cwd=None, env=None, stdin=None, timeout=60):
        script = CMDS / cmd
        base = dict(os.environ)
        base["AIRLAB_PATH"] = str(ws or airlab_ws)
        base["AIRLAB_ALIAS_PATH"] = str((ws or airlab_ws) / "alias")
        # keep tests hermetic / non-interactive
        base.setdefault("NO_COLOR", "1")
        if env:
            base.update(env)
        cp = subprocess.run(
            ["bash", str(script), *args],
            capture_output=True, text=True, env=base,
            cwd=str(cwd) if cwd else None,
            input=stdin, timeout=timeout,
        )
        return Result(cp)
    return _run


# --- git sandbox helpers (T2) -------------------------------------------- #
# Deterministic git that ignores host/user config so tests are hermetic.
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
    path = Path(path)
    git("init", "--bare", "-b", "main", str(path))
    return path


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


def all_command_scripts():
    """Discover every executable command script (cmds/* and version-control/*),
    excluding the _lib helpers. Returns repo-relative-ish names for parametrize."""
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
