"""T3 (read-only): remote docker access via `airlab docker-list --system=<robot>`.

Proves the operator can reach and query Docker on the real robot (no DinD, real
daemon on B). Read-only — lists containers/images; changes nothing.
"""
import pytest


@pytest.mark.e2e
def test_docker_list_remote(run, robot, e2e_ws):
    r = run("docker-list", f"--system={robot['name']}", ws=e2e_ws, timeout=60)
    assert r.rc == 0, r.out


@pytest.mark.e2e
def test_docker_list_images_remote(run, robot, e2e_ws):
    r = run("docker-list", f"--system={robot['name']}", "--images", ws=e2e_ws, timeout=60)
    assert r.rc == 0, r.out
