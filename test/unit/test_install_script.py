"""T1: install.sh argument handling and venv decisions, run hermetically.

install.sh is copied into a fake source tree whose install_dependencies_ubuntu24.sh
is a stub, with `sudo` and `dpkg-deb` stubbed on PATH and $HOME pointed at a temp
dir — so nothing is apt-installed, pip-installed or dpkg-installed. The real
build/install path is covered by the install tier and test/test_install.sh.
"""
import os
import shutil
import subprocess

import pytest

from airlab_testlib import REPO_ROOT

pytestmark = pytest.mark.unit

LOGGER = '#!/bin/bash\nprintf "%s %s\\n" "$(basename "$0")" "$*" >> "$STUB_LOG"\nexit 0\n'
DEPS_STUB = ('#!/bin/bash\nprintf "deps %s VIRTUAL_ENV=%s\\n" "$*" "${VIRTUAL_ENV:-}" '
             '>> "$STUB_LOG"\nexit 0\n')


@pytest.fixture
def tree(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    shutil.copy(REPO_ROOT / "install.sh", src / "install.sh")
    for d in ("DEBIAN", "etc", "usr"):
        (src / d).mkdir()
    (src / "install_dependencies_ubuntu24.sh").write_text(DEPS_STUB)
    home = tmp_path / "home"
    home.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("sudo", "dpkg-deb", "apt"):
        (bindir / tool).write_text(LOGGER)
        (bindir / tool).chmod(0o755)
    return src, home, bindir, tmp_path / "stub.log"


def make_venv(home):
    venv = home / "VENVs" / "airlab"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "activate").write_text(f'export VIRTUAL_ENV="{venv}"\n')
    (venv / "KEEP_ME").write_text("marker\n")
    return venv


@pytest.fixture
def run_install(tree):
    src, home, bindir, log = tree

    def _run(*args, stdin=""):
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        env.update({"HOME": str(home), "PATH": f"{bindir}:{os.environ['PATH']}",
                    "STUB_LOG": str(log), "SHELL": "/bin/bash"})
        cp = subprocess.run(["bash", str(src / "install.sh"), *args], input=stdin,
                            capture_output=True, text=True, env=env, timeout=60)
        cp.log = log.read_text().splitlines() if log.exists() else []
        return cp
    return _run


def test_help_documents_keep_venv(run_install):
    cp = run_install("--help")
    assert cp.returncode == 0
    assert "--keep-venv" in cp.stdout and "--check" in cp.stdout
    assert cp.log == []


def test_unknown_option_is_refused(run_install):
    cp = run_install("--bogus")
    assert cp.returncode != 0
    assert "Unknown option: --bogus" in cp.stderr
    assert cp.log == []


@pytest.mark.parametrize("args", [["--keep-venv", "--override-venv"],
                                  ["--override-venv", "--no-venv"]])
def test_conflicting_venv_modes_are_refused(run_install, args):
    cp = run_install("--skip-apt", *args)
    assert cp.returncode != 0
    assert "mutually exclusive" in cp.stderr
    assert cp.log == []


def test_keep_venv_reuses_without_prompt_and_still_installs_deps(run_install, tree):
    venv = make_venv(tree[1])
    cp = run_install("--skip-apt", "--keep-venv", stdin="y\n")  # a stray "y" is ignored
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "Remove and re-create" not in cp.stdout
    assert (venv / "KEEP_ME").exists(), "--keep-venv must not touch the venv"
    deps = [line for line in cp.log if line.startswith("deps")]
    assert len(deps) == 1
    assert "--skip-pip" not in deps[0], "--keep-venv still runs the pip installs"
    assert f"VIRTUAL_ENV={venv}" in deps[0], "deps must install INTO the kept venv"


def test_keep_venv_check_validates_without_side_effects(run_install, tree):
    make_venv(tree[1])
    cp = run_install("--check", "--keep-venv")
    assert cp.returncode == 0, cp.stderr
    assert cp.log == [], "--check must not run apt, sudo, deps or dpkg"


def test_prompt_on_closed_stdin_keeps_the_venv(run_install, tree):
    """No terminal to answer: `read` hits EOF. Under `set -e` that used to kill the
    install (after `airlab upgrade` had already removed the package)."""
    venv = make_venv(tree[1])
    cp = run_install("--skip-apt", stdin="")
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert (venv / "KEEP_ME").exists()
    assert "keep" in cp.stdout.lower()
    assert any(line.startswith("deps") for line in cp.log)
    assert any(line.startswith("sudo dpkg -i") for line in cp.log)


def test_prompt_answered_no_keeps_the_venv(run_install, tree):
    venv = make_venv(tree[1])
    cp = run_install("--skip-apt", stdin="n\n")
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert (venv / "KEEP_ME").exists()


def test_check_catches_missing_offline_venv_before_anything_runs(run_install):
    cp = run_install("--check", "--offline")
    assert cp.returncode != 0
    assert "needs an existing venv" in cp.stderr
    assert cp.log == []


def test_check_catches_no_override_with_existing_venv(run_install, tree):
    make_venv(tree[1])
    cp = run_install("--check", "--no-override-venv")
    assert cp.returncode != 0
    assert cp.log == []


def test_check_catches_skip_venv_without_active_venv(run_install):
    cp = run_install("--check", "--skip-venv")
    assert cp.returncode != 0
    assert "--skip-venv" in cp.stderr


def test_precondition_errors_come_before_apt(run_install):
    """A real (non --check) run must fail on a known-bad precondition before it
    runs `sudo apt`, not after."""
    cp = run_install("--skip-venv")   # apt NOT skipped; no active venv
    assert cp.returncode != 0
    assert "--skip-venv" in cp.stderr
    assert not any(line.startswith("sudo apt") for line in cp.log), cp.log
