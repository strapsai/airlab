"""T1: robot-setup local-root gating (option b).

`airlab setup local` provisions the machine system-wide, so it must run as root.
`airlab setup <robot>` runs as the invoking user and elevates ON THE ROBOT, so it
must NOT require local root. These tests run as a non-root user (the CI user), so
they can assert both halves of the gate directly.
"""
import pytest

pytestmark = pytest.mark.unit

_ROOT_MSG = "must be run as root"


def test_setup_local_requires_root(run, airlab_ws):
    # Non-root `setup local` must be refused with the root message.
    r = run("robot-setup", "local", ws=airlab_ws, stdin="", timeout=30)
    assert r.rc != 0
    assert _ROOT_MSG in r.out.lower()


def test_setup_remote_does_not_require_root(run, airlab_ws):
    # Non-root `setup <robot>` must get PAST the root gate (it fails later on
    # resolution/SSH for a bogus robot, but never with the local-root message).
    r = run("robot-setup", "definitely-not-a-real-robot",
            ws=airlab_ws, stdin="", timeout=30)
    assert _ROOT_MSG not in r.out.lower()
