"""T4: install-script flag handling that needs no Docker.

The rest of this tier exercises the *installed* .deb inside a container. These
tests cover the installer's own argument handling, which is pure shell and can
run here directly.

Focus: `--no-venv`. The tool is a bash dispatcher in a system .deb, so a
venv-free install is a supported shape — but `install_dependencies_ubuntu24.sh`
historically refused outright unless $VIRTUAL_ENV was set, which made that shape
unreachable.
"""
import os
import subprocess

from airlab_testlib import REPO_ROOT

DEPS = REPO_ROOT / "install_dependencies_ubuntu24.sh"
INSTALL = REPO_ROOT / "install.sh"


def _run(script, *args):
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    return subprocess.run(["bash", str(script), *args],
                          capture_output=True, text=True, env=env)


def test_deps_refuses_without_venv_and_names_the_alternative():
    """The guard still fires, and now points at the supported way out."""
    r = _run(DEPS, "--skip-apt", "--skip-pip")
    assert r.returncode == 1
    assert "must be run from within a Python virtual environment" in r.stdout
    assert "--no-venv" in r.stdout


def test_deps_accepts_no_venv_without_an_active_venv():
    r = _run(DEPS, "--no-venv", "--skip-apt", "--skip-pip")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "No virtual environment (--no-venv)" in r.stdout


def test_deps_reports_pyyaml_either_way():
    """PyYAML is load-bearing, so the installer states its status rather than
    assuming the pip step covered it (it is skipped here)."""
    r = _run(DEPS, "--no-venv", "--skip-apt", "--skip-pip")
    assert ("PyYAML: OK" in r.stdout) or ("cannot import yaml" in r.stderr)


def test_no_venv_is_in_both_usage_strings():
    for script in (INSTALL, DEPS):
        r = _run(script, "--definitely-not-a-flag")
        assert r.returncode == 1
        assert "--no-venv" in r.stdout, f"{script.name} usage omits --no-venv"
