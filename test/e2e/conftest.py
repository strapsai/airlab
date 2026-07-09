"""T3 (real-hardware e2e) fixtures.

These tests drive the airlab commands from the operator (Machine A / self-hosted
runner) against a real, sacrificial robot (Machine B) over the LAN. The robot is
FULLY CONFIGURABLE via env (physical<->VM is a config swap) and tests SKIP cleanly
when it isn't configured.

Env (in CI: repo vars + a secret):
  AIRLAB_TEST_ROBOT_AVAILABLE=1
  AIRLAB_TEST_ROBOT_ADDR=<ip-or-host>
  AIRLAB_TEST_ROBOT_USER=<ssh user>       (default: dtc)
  AIRLAB_TEST_ROBOT_PORT=<ssh port>       (default: 22)
  AIRLAB_TEST_ROBOT_PASSWORD=<password>   (only for auth/password-fallback/sudo tests)
  AIRLAB_TEST_ROBOT_NAME=<registry name>  (default: e2ebot)
  AIRLAB_TEST_ROBOT_WS=<remote test ws>   (default: ~/airlab_e2e_ws)

Mutating tests operate ONLY inside the dedicated remote workspace (AIRLAB_TEST_ROBOT_WS)
and a throwaway docker container, and are reset to a known state by `reset_robot`.
"""
import os
import shutil
import subprocess

import pytest

from airlab_testlib import FIXTURE_WS


def _robot_cfg():
    if os.environ.get("AIRLAB_TEST_ROBOT_AVAILABLE", "").lower() not in ("1", "true", "yes"):
        return None
    addr = os.environ.get("AIRLAB_TEST_ROBOT_ADDR")
    if not addr:
        return None
    return {
        "name": os.environ.get("AIRLAB_TEST_ROBOT_NAME", "e2ebot"),
        "addr": addr,
        "user": os.environ.get("AIRLAB_TEST_ROBOT_USER", "dtc"),
        "port": os.environ.get("AIRLAB_TEST_ROBOT_PORT", "22"),
        "password": os.environ.get("AIRLAB_TEST_ROBOT_PASSWORD", ""),
        "ws": os.environ.get("AIRLAB_TEST_ROBOT_WS", "~/airlab_e2e_ws"),
    }


@pytest.fixture
def robot():
    cfg = _robot_cfg()
    if not cfg:
        pytest.skip("real robot not configured (set AIRLAB_TEST_ROBOT_AVAILABLE=1 + _ADDR/_USER/…)")
    return cfg


@pytest.fixture
def e2e_ws(tmp_path, robot):
    """A minimal airlab_ws whose registry + robot_info resolve the robot NAME to
    the real robot address and the remote test workspace."""
    # Own directory — NOT "airlab_ws", which the top-level `airlab_ws` fixture
    # (pulled in via `run`) already creates in the same tmp_path.
    ws = tmp_path / "e2e_ws"
    (ws / "robot").mkdir(parents=True)
    shutil.copy(FIXTURE_WS / "robot" / "robots.py", ws / "robot" / "robots.py")
    (ws / "robot" / "robots.py").chmod(0o755)
    port_line = f"        port: {robot['port']}\n" if str(robot["port"]) != "22" else ""
    (ws / "robot" / "robots.yaml").write_text(
        "version: 1\n"
        "systems:\n"
        f"  - system: {robot['name']}\n"
        f"    os_user: {robot['user']}\n"
        "    type: robot\n"
        "    network_addresses:\n"
        "      - address_name: default\n"
        f"        ip: {robot['addr']}\n"
        "        default: true\n"
        f"{port_line}"
    )
    # robot_info.yaml: top-level <name> with ws_path (parse_yaml reads "<name>.ws_path")
    (ws / "robot" / "robot_info.yaml").write_text(
        f"{robot['name']}:\n"
        f"  ws_path: {robot['ws']}\n"
        f"  robot_ssh: {robot['user']}@{robot['addr']}\n"
    )
    return ws


@pytest.fixture
def robot_ssh(robot):
    """Run a command on the robot over key-based SSH; returns CompletedProcess."""
    def _ssh(remote_cmd, timeout=30, check=False):
        args = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
                "-o", "ConnectTimeout=15"]
        if str(robot["port"]) != "22":
            args += ["-p", str(robot["port"])]
        args += [f"{robot['user']}@{robot['addr']}", remote_cmd]
        cp = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if check and cp.returncode != 0:
            raise AssertionError(f"remote `{remote_cmd}` failed ({cp.returncode}): {cp.stderr}")
        return cp
    return _ssh


@pytest.fixture
def reset_robot(robot, robot_ssh):
    """Reset the robot to a known state around a mutating test: remove the remote
    test workspace before and after. (Docker/hosts cleanups are added per-test.)"""
    ws = robot["ws"]
    def _reset():
        robot_ssh(f"rm -rf {ws}", timeout=30)
    _reset()
    yield
    _reset()
