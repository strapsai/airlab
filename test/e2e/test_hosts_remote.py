"""T3 (sudo): `airlab hosts` set / compare / remove against a real robot.

Exercises the remote half that the unit tier cannot: reading /etc/hosts over SSH,
elevating through _lib/remote_sudo.sh to write it, and the remote backup.

Robot B has no passwordless sudo, so remote_sudo takes the sudo password from
AIRLAB_SUDO_PASSWORD; SSH itself is key-based. (An earlier note here claimed
set_hosts used plain `sudo cp`/`sudo tee` and could not work on B at all — that was
fixed when the shared remote_sudo helper landed, and the note was left behind.)

reset_hosts strips any airlab block afterward.
"""
import pytest

pytestmark = pytest.mark.e2e


def _env(robot):
    return {"AIRLAB_SUDO_PASSWORD": robot["password"]}


def test_hosts_set_writes_markers(run, robot, e2e_ws, robot_ssh, reset_hosts):
    r = run("hosts", "set", robot["name"], ws=e2e_ws, env=_env(robot), timeout=90)
    assert r.rc == 0, r.out
    cp = robot_ssh("grep -c 'Airlab Hosts Start' /etc/hosts")
    assert cp.stdout.strip() not in ("", "0"), "airlab block not written to /etc/hosts"


def test_hosts_compare_is_in_sync_after_set(run, robot, e2e_ws, reset_hosts):
    assert run("hosts", "set", robot["name"], ws=e2e_ws,
               env=_env(robot), timeout=90).rc == 0
    r = run("hosts", "compare", robot["name"], ws=e2e_ws, env=_env(robot), timeout=90)
    assert r.rc == 0, r.out
    assert "in sync" in r.out


def test_hosts_compare_reports_drift_before_any_set(run, robot, e2e_ws, reset_hosts):
    """reset_hosts leaves the robot with no airlab block, so compare must say so."""
    r = run("hosts", "compare", robot["name"], ws=e2e_ws, env=_env(robot), timeout=90)
    assert r.rc == 2, r.out


def test_hosts_remove_strips_the_block_and_leaves_the_rest(run, robot, e2e_ws,
                                                           robot_ssh, reset_hosts):
    assert run("hosts", "set", robot["name"], ws=e2e_ws,
               env=_env(robot), timeout=90).rc == 0
    r = run("hosts", "remove", robot["name"], ws=e2e_ws, env=_env(robot), timeout=90)
    assert r.rc == 0, r.out
    assert robot_ssh("grep -c 'Airlab Hosts Start' /etc/hosts").stdout.strip() in ("", "0")
    # localhost must still be there — remove touches only the marker block.
    assert robot_ssh("grep -c '127.0.0.1' /etc/hosts").stdout.strip() not in ("", "0")


def test_hosts_dry_run_does_not_touch_the_robot(run, robot, e2e_ws, robot_ssh, reset_hosts):
    r = run("hosts", "set", robot["name"], "--dry-run", ws=e2e_ws,
            env=_env(robot), timeout=90)
    assert r.rc == 0, r.out
    assert robot_ssh("grep -c 'Airlab Hosts Start' /etc/hosts").stdout.strip() in ("", "0")
