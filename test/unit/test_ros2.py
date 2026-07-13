"""T1: `airlab ros2` pass-through wrapper (pure-logic paths).

The wrapper's real work is `docker run`, which is out of unit scope. These tests
cover everything up to (and the argv handed to) the container launch by putting a
fake `docker` on PATH:
- `--help` / no-command work without docker installed (the #47 lesson);
- image resolution from AIRLAB_DEFAULT_IMAGE / --image, and the error when neither;
- AIRLAB_DEFAULT_DOCKER_VOLUMES validation (missing / not-writable → stop);
- the pass-through boundary (`ros2 bag --help` forwards, not swallowed) and that
  the expected volume mounts reach `docker run`.
"""
import os
import shutil
import subprocess

import pytest

from airlab_testlib import CMDS

pytestmark = pytest.mark.unit


@pytest.fixture
def no_docker_path(tmp_path):
    """PATH with `bash` available but NO `docker` — to prove help paths don't
    need docker. (An empty PATH would also hide `bash` from the launcher.)"""
    bindir = tmp_path / "nodocker"
    bindir.mkdir()
    (bindir / "bash").symlink_to(shutil.which("bash"))
    return {"PATH": str(bindir)}


@pytest.fixture
def fake_docker(tmp_path):
    """A stub `docker` on PATH: `image inspect` → found (0); `run` → echo argv (0).

    Returns an env dict (PATH prepended) to pass to run(..., env=...).
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    docker = bindir / "docker"
    docker.write_text(
        "#!/bin/bash\n"
        'case "$1" in\n'
        '  image) [ "$2" = "inspect" ] && exit 0 ;;\n'
        '  run) echo "FAKEDOCKER_RUN $*"; exit 0 ;;\n'
        "esac\n"
        "exit 0\n"
    )
    docker.chmod(0o755)
    return {"PATH": f"{bindir}:{os.environ['PATH']}"}


def test_help_needs_no_docker(run, no_docker_path):
    # --help must work even with docker absent.
    r = run("ros2", "--help", env=no_docker_path)
    assert r.rc == 0, r.out
    assert "Usage:" in r.out and "airlab ros2" in r.out


def test_no_command_errors_without_docker(run, no_docker_path):
    r = run("ros2", env=no_docker_path)
    assert r.rc == 1
    assert "No ros2 command given" in r.out


def test_no_image_configured_errors(run, fake_docker):
    # AIRLAB_DEFAULT_IMAGE unset and no --image → clear error, no container.
    r = run("ros2", "topic", "list", env=fake_docker)
    assert r.rc == 1
    assert "No Docker image configured" in r.out
    assert "AIRLAB_DEFAULT_IMAGE" in r.out


def test_airlab_path_required(run, fake_docker):
    env = {**fake_docker, "AIRLAB_PATH": "", "AIRLAB_DEFAULT_IMAGE": "img:test"}
    r = run("ros2", "topic", "list", env=env)
    assert r.rc == 1
    assert "AIRLAB_PATH is not set" in r.out


def test_volume_missing_folder_stops(run, fake_docker):
    env = {**fake_docker,
           "AIRLAB_DEFAULT_IMAGE": "img:test",
           "AIRLAB_DEFAULT_DOCKER_VOLUMES": "/definitely/not/here_xyz"}
    r = run("ros2", "topic", "list", env=env)
    assert r.rc == 1
    assert "does not exist" in r.out
    assert "FAKEDOCKER_RUN" not in r.out  # never reached docker run


def test_volume_not_writable_stops(run, fake_docker):
    # /proc exists but is not user-writable.
    env = {**fake_docker,
           "AIRLAB_DEFAULT_IMAGE": "img:test",
           "AIRLAB_DEFAULT_DOCKER_VOLUMES": "/proc"}
    r = run("ros2", "topic", "list", env=env)
    assert r.rc == 1
    assert "not writable" in r.out
    assert "FAKEDOCKER_RUN" not in r.out


def test_passthrough_and_mounts(run, fake_docker, tmp_path, airlab_ws):
    # A writable extra volume; a valid image; a pass-through that must NOT be
    # swallowed by the wrapper (`bag --help` → forwarded to ros2).
    vol = tmp_path / "data"
    vol.mkdir()
    env = {**fake_docker,
           "AIRLAB_DEFAULT_IMAGE": "img:test",
           "AIRLAB_DEFAULT_DOCKER_VOLUMES": str(vol)}
    r = run("ros2", "bag", "--help", env=env)
    assert r.rc == 0, r.out
    # forwarded, wrapper help NOT shown
    assert "Running 'ros2 bag --help'" in r.out
    assert "Wrapper options" not in r.out
    # reached docker run with the expected mounts
    assert "FAKEDOCKER_RUN" in r.out
    assert f"-v {vol}:{vol}" in r.out
    assert f"-v {airlab_ws}:{airlab_ws}" in r.out
    assert "--network=host" in r.out


def test_in_container_script_is_valid_bash():
    # The `bash -lc '<script>'` block is a single-quoted string, so the outer
    # `bash -n` never parses it. Extract and syntax-check it on its own.
    text = (CMDS / "ros2").read_text()
    marker = "bash -lc '"
    start = text.index(marker) + len(marker)
    end = text.index("' _ \"$@\"", start)
    snippet = text[start:end]
    cp = subprocess.run(["bash", "-n"], input=snippet, text=True,
                        capture_output=True)
    assert cp.returncode == 0, cp.stderr
    # guards the RTI Connext overlay logic stays present + keyed on the RMW
    assert 'RMW_IMPLEMENTATION:-' in snippet
    assert "rmw_connextdds" in snippet
