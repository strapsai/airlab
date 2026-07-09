"""T4: the airlab .deb installs cleanly and the installed dispatcher works.

Runs against a fresh Ubuntu container with the package installed (see conftest).
"""
import pytest

pytestmark = pytest.mark.install


def test_version(in_image):
    cp = in_image("airlab --version")
    assert cp.returncode == 0, cp.stderr
    assert "2.1.8" in cp.stdout


def test_greet(in_image):
    cp = in_image("airlab greet")
    assert "HELLO" in cp.stdout.upper(), cp.stdout + cp.stderr


def test_vcs_help_dispatches(in_image):
    cp = in_image("airlab vcs --help")
    assert cp.returncode == 0, cp.stderr
    assert "usage" in (cp.stdout + cp.stderr).lower()


def test_vcs_update_help_dispatches(in_image):
    # `vcs update` shells to a hardcoded /usr/local/bin path — only works installed,
    # so this specifically exercises the installed layout.
    cp = in_image("airlab vcs update --help")
    assert cp.returncode == 0, cp.stderr


def test_bash_completion_installed(in_image):
    cp = in_image("test -f /etc/bash_completion.d/airlab && echo OK")
    assert "OK" in cp.stdout, cp.stdout + cp.stderr


def test_zsh_completion_installed(in_image):
    cp = in_image("test -f /usr/share/zsh/vendor-completions/_airlab && echo OK")
    assert "OK" in cp.stdout, cp.stdout + cp.stderr


def test_postinst_seeds_motionless_signal(in_image):
    cp = in_image("test -f /etc/airlab/signals/MOTIONLESS && echo OK")
    assert "OK" in cp.stdout, cp.stdout + cp.stderr
