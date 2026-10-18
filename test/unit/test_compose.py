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
import shutil
import subprocess

import pytest

from airlab_testlib import CMDS, REPO_ROOT

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


# --- airlab.env parsing (read as text, never sourced) ----------------------- #

def _profiles_in(text):
    """The --profile values in a rendered command, in order."""
    words = text.split()
    return [words[i + 1] for i, w in enumerate(words) if w == "--profile"]


@pytest.mark.parametrize("line", [
    # closing quote followed by trailing whitespace — left a stray `"` before
    'AIRLAB_COMPOSE_PROFILES="db fleet vlm-zoo-orchestrator" ',
    'AIRLAB_COMPOSE_PROFILES="db fleet vlm-zoo-orchestrator"\t',
    # trailing comment, quoted and unquoted
    'AIRLAB_COMPOSE_PROFILES="db fleet vlm-zoo-orchestrator"  # basestation',
    'AIRLAB_COMPOSE_PROFILES=db,fleet,vlm-zoo-orchestrator # basestation',
    # single quotes
    "AIRLAB_COMPOSE_PROFILES='db fleet vlm-zoo-orchestrator'",
    "AIRLAB_COMPOSE_PROFILES='db fleet vlm-zoo-orchestrator'  # c",
    # export prefix (with and without quotes, with leading indentation)
    'export AIRLAB_COMPOSE_PROFILES="db fleet vlm-zoo-orchestrator"',
    '  export AIRLAB_COMPOSE_PROFILES=db,fleet,vlm-zoo-orchestrator',
    # unquoted with trailing whitespace, and a CRLF line ending
    'AIRLAB_COMPOSE_PROFILES=db,fleet,vlm-zoo-orchestrator   ',
    'AIRLAB_COMPOSE_PROFILES="db fleet vlm-zoo-orchestrator"\r',
])
def test_env_value_is_unquoted_robustly(run_compose, ws, line):
    (ws / "airlab.env").write_text(
        'AIRLAB_COMPOSE_FILE="docker-compose-basestation.yaml"\n' + line + "\n")
    cp = run_compose("--emit")
    assert cp.returncode == 0, cp.stderr
    assert _profiles_in(cp.stdout) == ["db", "fleet", "vlm-zoo-orchestrator"], cp.stdout
    assert '"' not in cp.stdout and "'" not in cp.stdout and "#" not in cp.stdout


@pytest.mark.parametrize("line", [
    'AIRLAB_COMPOSE_FILE="docker-compose-basestation.yaml" ',
    "AIRLAB_COMPOSE_FILE='docker-compose-basestation.yaml' # elected",
    "export AIRLAB_COMPOSE_FILE=docker-compose-basestation.yaml",
])
def test_compose_file_value_is_unquoted_robustly(run_compose, ws, line):
    (ws / "airlab.env").write_text(line + '\nAIRLAB_COMPOSE_PROFILES="fleet"\n')
    cp = run_compose("--emit")
    assert cp.returncode == 0, cp.stderr
    assert cp.stdout.startswith("docker compose -f docker-compose-basestation.yaml ")


def test_last_assignment_wins(run_compose, ws):
    (ws / "airlab.env").write_text(
        'AIRLAB_COMPOSE_FILE="docker-compose-basestation.yaml"\n'
        'AIRLAB_COMPOSE_PROFILES="old"\n'
        'export AIRLAB_COMPOSE_PROFILES="new other" # wins\n')
    assert _profiles_in(run_compose("--emit").stdout) == ["new", "other"]


def test_env_file_is_not_sourced(run_compose, ws, tmp_path):
    marker = tmp_path / "sourced"
    (ws / "airlab.env").write_text(
        f"touch {marker}\n" + ENV_BODY + 'AIRLAB_COMPOSE_PROFILES="$(touch ' + str(marker) + ')x"\n')
    run_compose("--emit")
    assert not marker.exists(), "airlab.env must be read as text, never executed"


def test_similar_key_prefix_is_not_matched(run_compose, ws):
    (ws / "airlab.env").write_text(ENV_BODY + 'AIRLAB_COMPOSE_PROFILES_EXTRA="nope"\n')
    assert _profiles_in(run_compose("--emit").stdout) == ["fleet", "storage-tools"]


# --- --build-only / --profiles ---------------------------------------------- #

BUILD_ENV = (
    'AIRLAB_COMPOSE_FILE="docker-compose-basestation.yaml"\n'
    'AIRLAB_COMPOSE_PROFILES="db fleet-build fleet reid-build"\n'
)


@pytest.fixture
def build_ws(ws):
    (ws / "airlab.env").write_text(BUILD_ENV)
    return ws


def test_build_only_emit_keeps_only_build_profiles(run_compose, build_ws):
    cp = run_compose("--emit", "--build-only")
    assert cp.returncode == 0, cp.stderr
    assert _profiles_in(cp.stdout) == ["fleet-build", "reid-build"]
    assert cp.stdout.endswith(" ") and not cp.stdout.endswith("\n")


def test_build_only_bare_prints_and_runs_nothing(run_compose, build_ws):
    """What the shell wrappers fall back to for `command airlab compose --build-only`."""
    cp = run_compose("--build-only")
    assert cp.returncode == 0
    assert _profiles_in(cp.stdout) == ["fleet-build", "reid-build"]
    assert cp.docker_argv == []


def test_build_only_dry_run(run_compose, build_ws):
    cp = run_compose("--dry-run", "--build-only", "build")
    assert cp.returncode == 0
    assert _profiles_in(cp.stderr) == ["fleet-build", "reid-build"]
    assert cp.docker_argv == []


def test_build_only_run_mode(run_compose, build_ws):
    cp = run_compose("--build-only", "up", "-d")
    assert cp.returncode == 0, cp.stderr
    argv = cp.docker_argv[0]
    assert _profiles_in(argv) == ["fleet-build", "reid-build"]
    assert argv.endswith(" up -d")


def test_build_only_with_no_build_profiles_errors(run_compose, ws):
    for args in (["--emit", "--build-only"], ["--build-only", "up", "-d"]):
        cp = run_compose(*args)
        assert cp.returncode != 0
        assert "-build" in cp.stderr
        assert cp.docker_argv == []


@pytest.mark.parametrize("args", [
    ["--profiles", "a,b-build"], ["--profiles=a,b-build"], ["--profiles", "a b-build"]])
def test_profiles_overrides_the_env_list(run_compose, build_ws, args):
    cp = run_compose("--emit", *args)
    assert cp.returncode == 0, cp.stderr
    assert _profiles_in(cp.stdout) == ["a", "b-build"]


def test_profiles_run_mode(run_compose, build_ws):
    argv = run_compose("--profiles", "db", "up", "-d").docker_argv[0]
    assert _profiles_in(argv) == ["db"] and argv.endswith(" up -d")


def test_profiles_works_when_env_has_none(run_compose, ws):
    (ws / "airlab.env").write_text('AIRLAB_COMPOSE_FILE="docker-compose-basestation.yaml"\n')
    cp = run_compose("--emit", "--profiles", "fleet")
    assert cp.returncode == 0, cp.stderr
    assert _profiles_in(cp.stdout) == ["fleet"]


def test_build_only_filters_the_profiles_override(run_compose, build_ws):
    """Precedence: --profiles replaces the list, then --build-only filters it."""
    cp = run_compose("--emit", "--profiles", "x,y-build", "--build-only")
    assert _profiles_in(cp.stdout) == ["y-build"]


@pytest.mark.parametrize("args", [["--profiles"], ["--profiles", ""], ["--profiles", " , "]])
def test_empty_profiles_override_errors(run_compose, build_ws, args):
    cp = run_compose("--emit", *args)
    assert cp.returncode != 0
    assert "--profiles" in cp.stderr


def test_compose_args_are_not_taken_as_airlab_options(run_compose, build_ws):
    """Only LEADING options are airlab's; later ones belong to Compose verbatim."""
    argv = run_compose("build", "--build-only").docker_argv[0]
    assert argv.endswith(" build --build-only")
    assert _profiles_in(argv) == ["db", "fleet-build", "fleet", "reid-build"]


def test_help_documents_profile_selection(run_compose):
    out = run_compose("--help").stdout
    assert "--build-only" in out and "--profiles" in out


# --- shell wrappers: `airlab compose --build-only` alone still prefills ----- #

WRAPPERS = {
    "bash": REPO_ROOT / "etc" / "bash_completion.d" / "airlab",
    "zsh": REPO_ROOT / "etc" / "airlab" / "airlab.zsh",
}


@pytest.fixture
def run_wrapper(tmp_path, build_ws):
    """Source a shell wrapper NON-interactively (it then prints the prefill line)
    with a stub `airlab` on PATH that dispatches to the in-repo command scripts."""
    bindir = tmp_path / "wbin"
    bindir.mkdir()
    (bindir / "airlab").write_text(f'#!/bin/bash\nc=$1; shift; exec bash "{CMDS}/$c" "$@"\n')
    (bindir / "airlab").chmod(0o755)
    (bindir / "docker").write_text(DOCKER_STUB)
    (bindir / "docker").chmod(0o755)
    log = tmp_path / "wdocker.log"

    def _run(shell, *args):
        if shutil.which(shell) is None:
            pytest.skip(f"{shell} not installed")
        script = f'source "{WRAPPERS[shell]}"; airlab compose "$@"'
        cmd = [shell, "-c", script, "_", *args] if shell == "bash" else \
              [shell, "-f", "-c", script, "_", *args]
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env={
            **os.environ, "PATH": f"{bindir}:{os.environ['PATH']}",
            "AIRLAB_PATH": str(build_ws), "DOCKER_LOG": str(log), "NO_COLOR": "1"})
        cp.docker_argv = log.read_text().splitlines() if log.exists() else []
        return cp
    return _run


@pytest.mark.parametrize("shell", ["bash", "zsh"])
@pytest.mark.parametrize("args,expected", [
    (["--build-only"], ["fleet-build", "reid-build"]),
    (["--profiles", "a,b"], ["a", "b"]),
    (["--profiles=a", "--build-only"], None),   # filtered to nothing -> error
])
def test_wrapper_prefills_for_selection_options_alone(run_wrapper, shell, args, expected):
    cp = run_wrapper(shell, *args)
    assert cp.docker_argv == [], "selection options alone must prefill, not run"
    if expected is None:
        assert cp.returncode != 0
        return
    assert cp.returncode == 0, cp.stderr
    assert cp.stdout.startswith("docker compose -f ")
    assert "--env-file" not in cp.stdout
    assert _profiles_in(cp.stdout) == expected


@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_wrapper_runs_when_compose_args_follow(run_wrapper, shell):
    cp = run_wrapper(shell, "--build-only", "up", "-d")
    assert cp.returncode == 0, cp.stderr
    assert len(cp.docker_argv) == 1
    assert _profiles_in(cp.docker_argv[0]) == ["fleet-build", "reid-build"]
    assert cp.docker_argv[0].endswith(" up -d")
