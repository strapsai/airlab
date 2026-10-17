"""T1: a machine's workspace root is its recorded AIRLAB_PATH.

`ws_path` used to carry the same path as separate bookkeeping, and the two could
disagree. Commands now read AIRLAB_PATH from robot_info.yaml, and refuse a value that
is not an absolute, literal path — a shell literal such as `/home/$USER/airlab_ws`
would be expanded on the wrong machine, or not at all. Exercised through the real
`airlab sync` against stub ssh/rsync.
"""
import os
import subprocess

import pytest

from airlab_testlib import CMDS, Result

pytestmark = pytest.mark.unit

PY = CMDS / "_lib" / "robot_info.py"


@pytest.fixture
def sync(airlab_ws, tmp_path):
    """sync() -> (result, rsync argv or None) for `airlab sync robotA --dry-run`."""
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    argv_log = tmp_path / "rsync.argv"
    (bindir / "ssh").write_text("#!/bin/sh\nexit 0\n")
    (bindir / "rsync").write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{argv_log}"\n')
    for stub in bindir.iterdir():
        stub.chmod(0o755)

    def _sync():
        env = dict(os.environ, AIRLAB_PATH=str(airlab_ws), NO_COLOR="1",
                   PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}")
        res = Result(subprocess.run(["bash", str(CMDS / "robot-sync"), "robotA", "--dry-run"],
                                    capture_output=True, text=True, env=env, timeout=60))
        argv = argv_log.read_text().splitlines() if argv_log.exists() else None
        return res, argv
    return _sync


def set_field(airlab_ws, field, value):
    info = airlab_ws / "robot" / "robot_info.yaml"
    r = subprocess.run(["python3", str(PY), "set", str(info), "robotA", field, value],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr


def test_sync_pushes_to_the_recorded_airlab_path(airlab_ws, sync):
    set_field(airlab_ws, "AIRLAB_PATH", "/srv/robot_ws")
    res, argv = sync()
    assert res.rc == 0, res.out
    assert argv and argv[-1].endswith(":/srv/robot_ws/"), argv


@pytest.mark.parametrize("value", ["/home/$USER/airlab_ws", "airlab_ws", "~/airlab_ws"])
def test_sync_refuses_a_non_literal_airlab_path(airlab_ws, sync, value):
    set_field(airlab_ws, "AIRLAB_PATH", value)
    res, argv = sync()
    assert res.rc != 0
    assert "must be an absolute path" in res.out
    assert argv is None, "rsync ran against an unusable destination"
