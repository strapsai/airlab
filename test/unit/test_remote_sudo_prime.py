"""T1: _lib/remote_sudo.sh sudo priming for caller-owned `ssh -tt` sessions.

`remote_sudo_prime` builds the fragment that primes sudo inside the single pty
session `airlab setup <robot>` uses to run install.sh. Two behaviours matter and
both used to be wrong:

  1. A NOPASSWD robot must never be asked for a password. The old call site asked
     unconditionally with stderr discarded, so setup hung on an invisible prompt.
  2. When a password IS needed it must never land on a remote command line, where
     quote characters break the command and `ps` exposes it to the whole robot.

`ssh` is stubbed on PATH, so these run with no robot and no network.
"""
import os
import shlex
import subprocess

import pytest

from airlab_testlib import CMDS

pytestmark = pytest.mark.unit

LIB = CMDS / "_lib" / "remote_sudo.sh"

# Stub ssh: logs argv and stdin, then behaves per $STUB_NOPASSWD / $STUB_STAGE_DIR.
STUB = r"""#!/bin/bash
# The remote command is the last argument; everything before it is ssh transport.
remote_cmd="${!#}"
printf '%s\n' "$*" >> "$STUB_ARGV_LOG"
case "$remote_cmd" in
    *"sudo -n true"*)
        [ "${STUB_NOPASSWD:-0}" = "1" ] && exit 0
        exit 1
        ;;
    *mktemp*askpass*)
        cat >> "$STUB_STDIN_LOG"          # consume the piped password
        printf '%s' "$STUB_STAGE_DIR"     # what the robot echoes back
        exit 0
        ;;
    *rm\ -rf*)
        printf '%s\n' "$remote_cmd" >> "$STUB_RM_LOG"
        exit 0
        ;;
esac
exit 0
"""


@pytest.fixture
def prime(tmp_path):
    """prime(setup, nopasswd=..., stage_dir=...) -> (rc, fragment, logs dict)."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "ssh"
    stub.write_text(STUB)
    stub.chmod(0o755)
    logs = {k: tmp_path / f"{k}.log" for k in ("argv", "stdin", "rm")}
    for p in logs.values():
        p.write_text("")

    def _prime(setup, nopasswd=False, stage_dir="/tmp/airlab-askpass.AbC123", cleanup=False):
        script = (
            f'source "{LIB}"; {setup}; '
            'remote_sudo_prime robot@host; rc=$?; '
            'printf "FRAG:[%s]\\n" "$REMOTE_SUDO_PRIME_CMD"; '
            'printf "CLEANUP:[%s]\\n" "$REMOTE_SUDO_PRIME_CLEANUP"; '
            + ('remote_sudo_prime_cleanup robot@host; ' if cleanup else '')
            + 'exit $rc'
        )
        env = {
            **os.environ,
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "STUB_NOPASSWD": "1" if nopasswd else "0",
            "STUB_STAGE_DIR": stage_dir,
            "STUB_ARGV_LOG": str(logs["argv"]),
            "STUB_STDIN_LOG": str(logs["stdin"]),
            "STUB_RM_LOG": str(logs["rm"]),
        }
        # setsid: no controlling terminal, so any attempt to prompt fails fast
        # rather than hanging the suite.
        cp = subprocess.run(["setsid", "bash", "-c", script], capture_output=True,
                            text=True, env=env, stdin=subprocess.DEVNULL, timeout=30)
        return cp, {k: v.read_text() for k, v in logs.items()}
    return _prime


def _frag(cp):
    for line in cp.stdout.splitlines():
        if line.startswith("FRAG:["):
            return line[len("FRAG:["):-1]
    raise AssertionError(f"no FRAG line in {cp.stdout!r} / {cp.stderr!r}")


def _cleanup_var(cp):
    for line in cp.stdout.splitlines():
        if line.startswith("CLEANUP:["):
            return line[len("CLEANUP:["):-1]
    raise AssertionError(f"no CLEANUP line in {cp.stdout!r}")


def test_nopasswd_robot_is_never_asked_for_a_password(prime):
    # No password source at all: on a NOPASSWD robot this must still succeed.
    # (It used to reach the prompt and block — the g-uav-2 hang.)
    cp, logs = prime('robot_password=""; unset AIRLAB_SUDO_PASSWORD', nopasswd=True)
    assert cp.returncode == 0
    assert _frag(cp) == "sudo -n true"
    assert _cleanup_var(cp) == "", "nothing should need cleaning up on the NOPASSWD path"
    assert logs["stdin"] == "", "no password should have been sent anywhere"
    assert "mktemp" not in logs["argv"], "no askpass helper should be staged"


def test_password_robot_stages_an_askpass_helper(prime):
    cp, logs = prime('robot_password=""; export AIRLAB_SUDO_PASSWORD="envpw"')
    assert cp.returncode == 0
    assert _frag(cp) == "SUDO_ASKPASS=/tmp/airlab-askpass.AbC123/askpass sudo -A true"
    assert _cleanup_var(cp) == "/tmp/airlab-askpass.AbC123"
    # The password went over stdin, and ONLY over stdin.
    assert logs["stdin"] == "envpw"
    assert "envpw" not in logs["argv"], "password must never reach a remote command line"


@pytest.mark.parametrize("pw", ["pa'ss", 'pa"ss', "pa ss", "pa$ss", "pa\\ss"])
def test_password_with_shell_metacharacters_survives(prime, pw):
    """Regression: the password used to be interpolated as `echo '$pw' | sudo -S`,
    so a single quote broke the remote command outright."""
    # shlex.quote, not repr: bash single-quotes don't honour Python's backslash escapes.
    cp, logs = prime(f'robot_password=""; export AIRLAB_SUDO_PASSWORD={shlex.quote(pw)}')
    assert cp.returncode == 0
    assert _frag(cp) == "SUDO_ASKPASS=/tmp/airlab-askpass.AbC123/askpass sudo -A true"
    assert logs["stdin"] == pw
    assert pw not in logs["argv"]


def test_prime_fails_cleanly_when_a_password_is_needed_but_unavailable(prime):
    cp, _ = prime('robot_password=""; unset AIRLAB_SUDO_PASSWORD')
    assert cp.returncode != 0
    assert _frag(cp) == ""
    assert "AIRLAB_SUDO_PASSWORD" in cp.stderr


def test_cleanup_removes_the_staged_dir_and_clears_the_marker(prime):
    cp, logs = prime('robot_password=""; export AIRLAB_SUDO_PASSWORD="envpw"',
                     cleanup=True)
    assert cp.returncode == 0
    assert "/tmp/airlab-askpass.AbC123" in logs["rm"]


def test_cleanup_is_a_noop_when_nothing_was_staged(prime):
    cp, logs = prime('robot_password=""; unset AIRLAB_SUDO_PASSWORD',
                     nopasswd=True, cleanup=True)
    assert cp.returncode == 0
    assert logs["rm"] == "", "cleanup must not touch the robot when nothing was staged"
