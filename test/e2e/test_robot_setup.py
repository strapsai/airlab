"""T3 (OPT-IN): `airlab setup <robot>` provisions the robot.

This reinstalls the airlab tool ON the robot (system-wide) and — unless
--no-reboot — reboots it. It mutates B well beyond a test workspace, so it is
GATED: set AIRLAB_TEST_ALLOW_ROBOT_SETUP=1 to run, and RE-SNAPSHOT B afterward.

Notes (findings the suite surfaced):
- Remote setup runs as the INVOKING USER (no local root): its git/rsync steps use
  that user's repo + SSH keys, and it elevates only ON THE ROBOT via the shared
  remote_sudo helper. So `run(...)` here is NOT wrapped in sudo.
- B has key-auth (A's key) + no NOPASSWD sudo, so remote_sudo needs the robot's sudo
  password; we supply it via the AIRLAB_SUDO_PASSWORD env var (see env= below).
- Installs the tool from the local checkout via --airlab-src (no GitHub needed on B).

Status: written from source analysis; needs on-A validation when first opted in
(env/reboot-wait behavior may need iteration). Reboot variant TODO
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
    # Key-based SSH (A's key on B); robot-setup's remote sudo now goes through the
    # shared remote_sudo helper, which takes the sudo password from AIRLAB_SUDO_PASSWORD.
    r = run(
        "robot-setup", robot["name"],
        "-y", "--no-reboot", "--force",
        f"--airlab-src={REPO_ROOT}",
        f"--path={robot['ws']}",
        ws=e2e_ws,
        env={"AIRLAB_SUDO_PASSWORD": robot["password"]},
        timeout=1800,
    )
    assert r.rc == 0, r.out
    # the tool should now be installed on the robot
    cp = robot_ssh("airlab --version")
    assert cp.returncode == 0, cp.stderr
