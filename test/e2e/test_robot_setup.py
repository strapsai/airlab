"""T3 (sudo, OPT-IN): `airlab setup <robot>` provisions the robot.

This reinstalls the airlab tool ON the robot (system-wide) and — unless
--no-reboot — reboots it. It mutates B well beyond a test workspace, so it is
GATED: set AIRLAB_TEST_ALLOW_ROBOT_SETUP=1 to run, and RE-SNAPSHOT B afterward.

Notes (findings the suite surfaced):
- robot-setup captures the sudo password only when key-auth FAILS. With A's key
  authorized on B and no NOPASSWD sudo, its `sudo -S` would get an empty password,
  so `--password` is REQUIRED here (we feed AIRLAB_TEST_ROBOT_PASSWORD on stdin).
- Installs the tool from the local checkout via --airlab-src (no GitHub needed on B).

Status: written from source analysis; needs on-A validation when first opted in
(flag/stdin/reboot-wait behavior may need iteration). Reboot variant TODO
(drop --no-reboot + wait-for-ssh).
"""
import os
import pytest

from airlab_testlib import REPO_ROOT

_ALLOW = os.environ.get("AIRLAB_TEST_ALLOW_ROBOT_SETUP", "").lower() in ("1", "true", "yes")

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not _ALLOW,
        reason="opt-in: reinstalls airlab on the robot; set AIRLAB_TEST_ALLOW_ROBOT_SETUP=1 "
               "(and re-snapshot B afterward)",
    ),
]


def test_robot_setup_reinstalls_tool(run, robot, e2e_ws, robot_ssh):
    r = run(
        "robot-setup", robot["name"],
        "--password", "-y", "--no-reboot", "--force",
        f"--airlab-src={REPO_ROOT}",
        f"--path={robot['ws']}",
        ws=e2e_ws,
        stdin=(robot["password"] or "") + "\n",
        timeout=1800,
    )
    assert r.rc == 0, r.out
    # the tool should now be installed on the robot
    cp = robot_ssh("airlab --version")
    assert cp.returncode == 0, cp.stderr
