"""T3: connectivity to a real robot (Machine A -> Machine B) — non-destructive.

Proves the whole operator->robot path: registry resolution + key-based SSH.
Runs on the self-hosted runner (nightly / on-demand); skips when no robot is
configured. These tests do NOT mutate the robot.
"""
import pytest


@pytest.mark.e2e
def test_exec_runs_remote_command(run, robot, e2e_ws):
    r = run("exec", robot["name"], "-c", "echo AIRLAB_E2E_OK", ws=e2e_ws, timeout=45)
    assert r.rc == 0, r.out
    assert "AIRLAB_E2E_OK" in r.out


@pytest.mark.e2e
def test_exec_reports_remote_hostname(run, robot, e2e_ws):
    r = run("exec", robot["name"], "-c", "hostname", ws=e2e_ws, timeout=45)
    assert r.rc == 0, r.out
    assert r.stdout.strip(), "expected the remote hostname on stdout"


@pytest.mark.e2e
def test_exec_propagates_remote_exit_code(run, robot, e2e_ws):
    # exec must return the REMOTE command's exit status
    r = run("exec", robot["name"], "-c", "exit 7", ws=e2e_ws, timeout=45)
    assert r.rc == 7, r.out


@pytest.mark.e2e
def test_exec_unknown_target_fails(run, robot, e2e_ws):
    r = run("exec", "no-such-robot", "-c", "true", ws=e2e_ws, timeout=45)
    assert r.rc == 1
    assert "not found in robots.yaml" in r.out
