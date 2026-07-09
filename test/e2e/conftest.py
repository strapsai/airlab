"""T3 (real-hardware e2e) fixtures.

These tests drive the airlab commands from the operator (Machine A / self-hosted
runner) against a real, sacrificial robot (Machine B) over the LAN. The robot is
FULLY CONFIGURABLE via env (so physical<->VM is a config swap) and tests SKIP
cleanly when it isn't configured — so the suite stays green on hosted runners and
locally.

Configure via env (in CI these come from repo vars + secret):
  AIRLAB_TEST_ROBOT_AVAILABLE=1
  AIRLAB_TEST_ROBOT_ADDR=<ip-or-host>
  AIRLAB_TEST_ROBOT_USER=<ssh user>          (default: dtc)
  AIRLAB_TEST_ROBOT_PORT=<ssh port>          (default: 22)
  AIRLAB_TEST_ROBOT_PASSWORD=<password>      (only for auth/password-fallback tests)
  AIRLAB_TEST_ROBOT_NAME=<registry name>     (default: e2ebot)

Prereq for key-based commands (ssh/exec/sync): the operator's SSH key is already
authorized on the robot (part of Machine A/B setup).
"""
import os
import shutil

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
    }


@pytest.fixture
def robot():
    cfg = _robot_cfg()
    if not cfg:
        pytest.skip("real robot not configured (set AIRLAB_TEST_ROBOT_AVAILABLE=1 + _ADDR/_USER/…)")
    return cfg


@pytest.fixture
def e2e_ws(tmp_path, robot):
    """A minimal airlab_ws whose registry resolves the robot NAME -> the real
    robot address, using the same stub robots.py the unit tests use."""
    ws = tmp_path / "airlab_ws"
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
    return ws
