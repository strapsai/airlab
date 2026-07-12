"""T3 (sudo): `airlab set_hosts <robot>` writes /etc/hosts on the robot.

FINDING (documented as xfail): set_hosts runs plain `sudo cp`/`sudo tee` over SSH
without feeding a password (no `sudo -S`), so it only works on a robot with
passwordless sudo. The test robot (B) does not have NOPASSWD, so this currently
fails at the remote sudo step. reset_hosts strips any airlab block afterward.
"""
import pytest


@pytest.mark.e2e
def test_set_hosts_writes_markers(run, robot, e2e_ws, robot_ssh, reset_hosts):
    # B has no passwordless sudo; the remote_sudo helper takes the sudo password
    # from AIRLAB_SUDO_PASSWORD (env). Key-based SSH otherwise.
    r = run("set_hosts", robot["name"], ws=e2e_ws,
            env={"AIRLAB_SUDO_PASSWORD": robot["password"]}, timeout=90)
    assert r.rc == 0, r.out
    cp = robot_ssh("grep -c 'Airlab Hosts Start' /etc/hosts")
    assert cp.stdout.strip() not in ("", "0"), "airlab block not written to /etc/hosts"
