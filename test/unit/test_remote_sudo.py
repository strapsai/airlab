"""T1: _lib/remote_sudo.sh password-source selection.

Unit-tests the pure password-source logic (`_airlab_sudo_pw`) by sourcing the
helper in a subshell with no controlling terminal. The ssh/`sudo -n` transport
is exercised by the e2e tier against a real robot.
"""
import subprocess

import pytest

from airlab_testlib import CMDS

LIB = CMDS / "_lib" / "remote_sudo.sh"


def _pw(setup):
    # stdin=DEVNULL => the /dev/tty prompt path fails cleanly (as in CI)
    cp = subprocess.run(
        ["bash", "-c", f'source "{LIB}"; {setup}; _airlab_sudo_pw'],
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    return cp.returncode, cp.stdout


@pytest.mark.unit
def test_reuses_ssh_password_first(self=None):
    rc, out = _pw('robot_password="sshpw"; AIRLAB_SUDO_PASSWORD="envpw"')
    assert rc == 0 and out == "sshpw"


@pytest.mark.unit
def test_env_password_when_no_ssh_password():
    rc, out = _pw('robot_password=""; export AIRLAB_SUDO_PASSWORD="envpw"')
    assert rc == 0 and out == "envpw"


@pytest.mark.unit
def test_fails_when_no_source_and_no_tty():
    rc, out = _pw('robot_password=""; unset AIRLAB_SUDO_PASSWORD')
    assert rc != 0 and out == ""
