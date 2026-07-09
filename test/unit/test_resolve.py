"""T1: _lib/resolve.sh::resolve_ssh_address against the stub registry.

resolve.sh is a sourceable library (no main), so we source it in a subshell
with AIRLAB_PATH pointed at the dummy workspace and assert the printed target.
"""
import subprocess

import pytest

from airlab_testlib import CMDS


def _resolve(ws, name, address=None):
    lib = CMDS / "_lib" / "resolve.sh"
    addr = f'"{address}"' if address else ""
    script = f'source "{lib}"; resolve_ssh_address "{name}" {addr}'
    cp = subprocess.run(
        ["bash", "-c", script],
        capture_output=True, text=True,
        env={**_env(ws)},
    )
    return cp.returncode, cp.stdout.strip(), cp.stderr.strip()


def _env(ws):
    import os
    e = dict(os.environ)
    e["AIRLAB_PATH"] = str(ws)
    return e


@pytest.mark.unit
def test_default_address(airlab_ws):
    rc, out, _ = _resolve(airlab_ws, "robotA")
    assert rc == 0 and out == "dtc@10.0.0.10"


@pytest.mark.unit
def test_named_address_hostname(airlab_ws):
    rc, out, _ = _resolve(airlab_ws, "robotA", "vpn")
    assert out == "dtc@robotA-vpn"


@pytest.mark.unit
def test_port_address_uses_ssh_uri(airlab_ws):
    rc, out, _ = _resolve(airlab_ws, "robotA", "fwd")
    assert out == "ssh://dtc@10.0.0.10:2222"


@pytest.mark.unit
def test_basestation_default(airlab_ws):
    _, out, _ = _resolve(airlab_ws, "baseA")
    assert out == "airlab@10.0.0.20"


@pytest.mark.unit
def test_no_default_falls_back_to_first(airlab_ws):
    _, out, _ = _resolve(airlab_ws, "no-default-bot")
    assert out == "dtc@10.0.0.30"


@pytest.mark.unit
def test_unknown_system_is_empty(airlab_ws):
    _, out, _ = _resolve(airlab_ws, "does-not-exist")
    assert out == ""


@pytest.mark.unit
def test_missing_registry_is_empty(tmp_path):
    # no robots.py present -> resolver returns nothing (not an error)
    rc, out, _ = _resolve(tmp_path, "robotA")
    assert out == ""
