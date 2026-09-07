"""T1: `airlab compose` — prefill unchanged, and the new run path.

Bare, the command still just hands over the `docker compose` line for this machine
(elected file + profiles from airlab.env). With arguments it runs Compose itself, so
one invocation means the same thing on every configured machine — including
non-interactively, over `airlab exec`/ssh/ansible, where nothing has exported
airlab.env into the environment. That last case is why the run path passes
`--env-file` and the prefilled form does not.

`docker` is stubbed on PATH, so nothing is actually started.
"""
import os
import subprocess

import pytest

from airlab_testlib import CMDS

pytestmark = pytest.mark.unit

COMPOSE = CMDS / "compose"

ENV_BODY = (
    "ARCH=x86\n"
    'AIRLAB_COMPOSE_FILE="docker-compose-basestation.yaml"\n'
    'AIRLAB_COMPOSE_PROFILES="fleet storage-tools"\n'
)

# Stub docker: record argv, print nothing, succeed.
DOCKER_STUB = '#!/bin/bash\nprintf \'%s\\n\' "$*" >> "$DOCKER_LOG"\nexit 0\n'


@pytest.fixture
def ws(tmp_path):
    """A workspace with airlab.env and the elected compose file present."""
    (tmp_path / "launch").mkdir()
    (tmp_path / "launch" / "docker-compose-basestation.yaml").write_text("services: {}\n")
    (tmp_path / "airlab.env").write_text(ENV_BODY)
    return tmp_path


@pytest.fixture
def run_compose(tmp_path, ws):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "docker").write_text(DOCKER_STUB)
    (bindir / "docker").chmod(0o755)
    log = tmp_path / "docker.log"

    def _run(*args, env=None):
        base = {
            **os.environ,
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "AIRLAB_PATH": str(ws),
            "DOCKER_LOG": str(log),
            "NO_COLOR": "1",
        }
        base.update(env or {})
        cp = subprocess.run(["bash", str(COMPOSE), *args], capture_output=True,
                            text=True, env=base, timeout=30)
        cp.docker_argv = log.read_text().splitlines() if log.exists() else []
        return cp
    return _run


# --- the prefill path is unchanged ----------------------------------------- #

def test_bare_prints_the_command_and_runs_nothing(run_compose):
    cp = run_compose()
    assert cp.returncode == 0
    assert "docker compose -f docker-compose-basestation.yaml" in cp.stdout
    assert "--profile fleet" in cp.stdout and "--profile storage-tools" in cp.stdout
    assert cp.docker_argv == [], "bare `airlab compose` must not run anything"


def test_prefilled_form_has_no_env_file(run_compose):
    """Deliberate: the prefill is typed into a shell that already exported airlab.env."""
    assert "--env-file" not in run_compose("--emit").stdout


def test_emit_is_bare_and_trailing_space(run_compose):
    out = run_compose("--emit").stdout
    assert not out.endswith("\n") and out.endswith(" ")


# --- the run path ----------------------------------------------------------- #

def test_arguments_run_compose_with_them_appended(run_compose):
    cp = run_compose("up", "-d")
    assert cp.returncode == 0
    assert len(cp.docker_argv) == 1
    argv = cp.docker_argv[0]
    assert argv.startswith("compose ")
    assert argv.endswith(" up -d"), argv
    assert "-f docker-compose-basestation.yaml" in argv
    assert "--profile fleet" in argv and "--profile storage-tools" in argv


def test_run_path_passes_env_file(run_compose, ws):
    """Without it, a non-interactive run has no ARCH and renders the wrong stack."""
    argv = run_compose("down").docker_argv[0]
    assert f"--env-file {ws}/airlab.env" in argv


def test_profiles_precede_the_subcommand(run_compose):
    """Compose only accepts --profile before the subcommand."""
    argv = run_compose("up").docker_argv[0]
    assert argv.index("--profile") < argv.index(" up")


@pytest.mark.parametrize("args", [["down"], ["config"], ["ps"], ["logs", "-f"],
                                  ["build", "--no-cache"], ["restart"]])
def test_any_compose_subcommand_is_passed_through(run_compose, args):
    argv = run_compose(*args).docker_argv[0]
    assert argv.endswith(" " + " ".join(args)), argv


def test_dry_run_shows_the_command_but_runs_nothing(run_compose):
    cp = run_compose("--dry-run", "up", "-d")
    assert cp.returncode == 0
    assert "up -d" in cp.stderr
    assert cp.docker_argv == [], "--dry-run must not invoke docker"


def test_the_command_is_echoed_so_the_operator_sees_the_stack(run_compose):
    """A bare `airlab compose down` should never leave you guessing what it took down."""
    cp = run_compose("down")
    assert "docker-compose-basestation.yaml" in cp.stderr


def test_exit_code_is_propagated(tmp_path, ws):
    bindir = tmp_path / "bin"; bindir.mkdir()
    (bindir / "docker").write_text("#!/bin/bash\nexit 42\n")
    (bindir / "docker").chmod(0o755)
    cp = subprocess.run(["bash", str(COMPOSE), "up"], capture_output=True, text=True,
                        env={**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}",
                             "AIRLAB_PATH": str(ws), "NO_COLOR": "1"}, timeout=30)
    assert cp.returncode == 42, "compose's exit code must reach the caller"


def test_runs_from_the_launch_directory(run_compose, ws):
    """`-f` is a bare filename and include: paths are relative to launch/."""
    cp = run_compose("config")
    assert cp.returncode == 0
    assert "-f docker-compose-basestation.yaml" in cp.docker_argv[0]


# --- configuration errors still fail loudly, in both modes ------------------ #

@pytest.mark.parametrize("args", [[], ["up", "-d"]])
def test_missing_compose_file_is_refused(run_compose, ws, args):
    (ws / "launch" / "docker-compose-basestation.yaml").unlink()
    cp = run_compose(*args)
    assert cp.returncode != 0
    assert "not found" in cp.stderr
    assert cp.docker_argv == []


@pytest.mark.parametrize("args", [[], ["up", "-d"]])
def test_unset_profiles_is_refused(run_compose, ws, args):
    (ws / "airlab.env").write_text('AIRLAB_COMPOSE_FILE="docker-compose-basestation.yaml"\n')
    cp = run_compose(*args)
    assert cp.returncode != 0
    assert "AIRLAB_COMPOSE_PROFILES" in cp.stderr


def test_help_documents_both_modes(run_compose):
    out = run_compose("--help").stdout
    assert "airlab compose up -d" in out
    assert "Prefill" in out or "prefill" in out
