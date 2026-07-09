"""T3 (destructive): `airlab sync` (robot-sync) to a real robot.

Operates only inside the dedicated remote workspace (AIRLAB_TEST_ROBOT_WS), which
`reset_robot` removes before and after each test.
"""
import pytest


@pytest.mark.e2e
def test_sync_pushes_file(run, robot, e2e_ws, robot_ssh, reset_robot):
    sub = "payload"
    (e2e_ws / sub).mkdir()
    (e2e_ws / sub / "marker.txt").write_text("E2E_SYNC_OK\n")

    r = run("robot-sync", robot["name"], f"--path={sub}", ws=e2e_ws, timeout=120)
    assert r.rc == 0, r.out

    cp = robot_ssh(f"cat {robot['ws']}/{sub}/marker.txt")
    assert cp.returncode == 0, cp.stderr
    assert "E2E_SYNC_OK" in cp.stdout


@pytest.mark.e2e
def test_sync_dry_run_pushes_nothing(run, robot, e2e_ws, robot_ssh, reset_robot):
    sub = "payload"
    (e2e_ws / sub).mkdir()
    (e2e_ws / sub / "marker.txt").write_text("x\n")

    r = run("robot-sync", robot["name"], f"--path={sub}", "--dry-run", ws=e2e_ws, timeout=120)
    assert r.rc == 0, r.out

    cp = robot_ssh(f"test -e {robot['ws']}/{sub}/marker.txt && echo EXISTS || echo ABSENT")
    assert "ABSENT" in cp.stdout, "dry-run must not create anything on the robot"
