"""Top-level pytest fixtures for the airlab test suite.

Shared helpers live in airlab_testlib.py (imported here and by tests). This file
holds only fixtures. Commands are standalone bash scripts run IN-PLACE by path
with $AIRLAB_PATH pointed at a dummy workspace — no install required.
"""
import os
import shutil
import subprocess

import pytest

from airlab_testlib import CMDS, FIXTURE_WS, Result


@pytest.fixture
def airlab_ws(tmp_path):
    """A fresh, mutable copy of the dummy workspace; returns its Path."""
    dst = tmp_path / "airlab_ws"
    shutil.copytree(FIXTURE_WS, dst)
    (dst / "robot" / "robots.py").chmod(0o755)
    return dst


@pytest.fixture
def run(airlab_ws):
    """run(cmd, *args, ws=..., cwd=..., env=..., stdin=...) -> Result.

    `cmd` is a command name under cmds/ (e.g. "ssh") or a relative path
    (e.g. "version-control/vcs"). $AIRLAB_PATH defaults to the copied workspace.
    """
    def _run(cmd, *args, ws=None, cwd=None, env=None, stdin=None, timeout=60):
        script = CMDS / cmd
        base = dict(os.environ)
        base["AIRLAB_PATH"] = str(ws or airlab_ws)
        base["AIRLAB_ALIAS_PATH"] = str((ws or airlab_ws) / "alias")
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
