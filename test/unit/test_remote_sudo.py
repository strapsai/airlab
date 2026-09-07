"""T1: _lib/remote_sudo.sh password-source selection.

Unit-tests the pure password-source logic (`_airlab_sudo_pw`) by sourcing the
helper in a subshell with no controlling terminal. The ssh/`sudo -n` transport
is exercised by the e2e tier against a real robot.
"""
import os
import pty
import subprocess

import pytest

from airlab_testlib import CMDS

LIB = CMDS / "_lib" / "remote_sudo.sh"


def _pw(setup):
    # setsid => no controlling terminal, so the /dev/tty prompt path fails cleanly
    # (as in CI) instead of blocking when the suite is run from a real terminal.
    cp = subprocess.run(
        ["setsid", "bash", "-c", f'source "{LIB}"; {setup}; _airlab_sudo_pw'],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30,
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


@pytest.mark.unit
def test_prompt_is_visible_even_when_caller_discards_stderr():
    """Regression: the prompt must reach the terminal, not stderr.

    `airlab setup <robot>` captured this helper as `$(_airlab_sudo_pw 2>/dev/null)`.
    bash writes `read -p` prompts to stderr, so the question was thrown away while
    the read kept blocking on /dev/tty — the operator saw setup freeze silently
    right after the airlab zip finished extracting. The prompt goes to /dev/tty now,
    which a caller cannot redirect away.
    """
    script = (
        f'source "{LIB}"; '
        'robot_password=""; unset AIRLAB_SUDO_PASSWORD; '
        'v="$(_airlab_sudo_pw 2>/dev/null)"; '
        'printf "CAPTURED:[%s]\\n" "$v"'
    )
    pid, fd = pty.fork()
    if pid == 0:                                    # child: runs on a real pty
        os.execvp("bash", ["bash", "-c", script])   # pragma: no cover
    os.write(fd, b"typed-pw\n")
    out = b""
    try:
        while True:
            chunk = os.read(fd, 1024)
            if not chunk:
                break
            out += chunk
    except OSError:                                 # pty closed on child exit
        pass
    os.waitpid(pid, 0)
    text = out.decode(errors="replace")

    assert "password for the remote host" in text, \
        f"prompt was swallowed instead of reaching the tty: {text!r}"
    assert "CAPTURED:[typed-pw]" in text
    # -s must still hold: the typed password is never echoed back by the prompt.
    assert "typed-pw\r\ntyped-pw" not in text
