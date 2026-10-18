"""T1: `airlab upgrade` — abort exit codes, pre-removal validation, failure message.

Everything with side effects is stubbed on PATH: `curl` copies a locally built
source zip, `sudo` / `dpkg-deb` only log, `dpkg-query` reports a version. The
zip holds the REAL install.sh (so `install.sh --check` is exercised for real) in
a fake tree whose install_dependencies_ubuntu24.sh is a stub. The download dir
is relocated under tmp via AIRLAB_UPGRADE_TMPDIR, and $HOME is a temp dir.
"""
import os
import shutil
import subprocess
import zipfile

import pytest

from airlab_testlib import CMDS, REPO_ROOT

pytestmark = pytest.mark.unit

UPGRADE = CMDS / "upgrade"

LOGGER = '#!/bin/bash\nprintf "%s %s\\n" "$(basename "$0")" "$*" >> "$STUB_LOG"\nexit 0\n'
CURL_STUB = ('#!/bin/bash\nprintf "curl %s\\n" "$*" >> "$STUB_LOG"\n'
             'while [ $# -gt 0 ]; do [ "$1" = -o ] && { cp "$SRC_ZIP" "$2"; exit 0; }; shift; done\n'
             'exit 1\n')
DPKG_QUERY_STUB = ('#!/bin/bash\n[ "$1" = --show ] && { echo 2.2.5-Stable-Release; exit 0; }\n'
                   'exit 1\n')
DEPS_STUB = ('#!/bin/bash\nprintf "deps %s\\n" "$*" >> "$STUB_LOG"\n'
             '[ -n "${DEPS_FAIL:-}" ] && exit 3\nexit 0\n')


@pytest.fixture
def env(tmp_path):
    # The source zip, laid out like GitHub's archive: one top-level dir.
    zpath = tmp_path / "src.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.write(REPO_ROOT / "install.sh", "airlab-main/install.sh")
        z.writestr("airlab-main/install_dependencies_ubuntu24.sh", DEPS_STUB)
        for d in ("DEBIAN", "etc", "usr"):
            z.writestr(f"airlab-main/{d}/.keep", "")
    home = tmp_path / "home"
    venv = home / "VENVs" / "airlab"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "activate").write_text(f'export VIRTUAL_ENV="{venv}"\n')
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in {"sudo": LOGGER, "dpkg-deb": LOGGER, "airlab": LOGGER,
                       "curl": CURL_STUB, "dpkg-query": DPKG_QUERY_STUB}.items():
        (bindir / name).write_text(body)
        (bindir / name).chmod(0o755)
    (tmp_path / "upg").mkdir()
    return {"tmp": tmp_path, "home": home, "bin": bindir, "zip": zpath,
            "log": tmp_path / "stub.log"}


@pytest.fixture
def run_upgrade(env):
    def _run(*args, stdin="", extra=None):
        e = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        e.update({"HOME": str(env["home"]), "PATH": f"{env['bin']}:{os.environ['PATH']}",
                  "STUB_LOG": str(env["log"]), "SRC_ZIP": str(env["zip"]),
                  "AIRLAB_UPGRADE_TMPDIR": str(env["tmp"] / "upg"), "SHELL": "/bin/bash",
                  "NO_COLOR": "1"})
        e.update(extra or {})
        cp = subprocess.run(["bash", str(UPGRADE), *args], input=stdin,
                            capture_output=True, text=True, env=e, timeout=60)
        cp.log = env["log"].read_text().splitlines() if env["log"].exists() else []
        return cp
    return _run


def removed(cp):
    return any(line.startswith("sudo dpkg -r") for line in cp.log)


# --- aborting is not success ------------------------------------------------ #

@pytest.mark.parametrize("answer", ["n\n", "\n", "nope\n"])
def test_declined_prompt_exits_nonzero(run_upgrade, answer):
    cp = run_upgrade(stdin=answer)
    assert cp.returncode == 1
    assert "Aborted" in cp.stdout + cp.stderr
    assert cp.log == [], "an aborted upgrade must not download or remove anything"


def test_no_tty_without_yes_exits_nonzero(run_upgrade):
    cp = run_upgrade(stdin="")      # EOF: nothing to answer the prompt
    assert cp.returncode == 1
    assert "--yes" in cp.stderr
    assert cp.log == []


def test_yes_skips_the_prompt(run_upgrade):
    cp = run_upgrade("--yes", "--", "--keep-venv", stdin="")
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "Proceed?" not in cp.stdout


# --- validate before removing ----------------------------------------------- #

def test_bad_install_flag_is_caught_before_dpkg_remove(run_upgrade):
    cp = run_upgrade("--yes", "--", "--bogus")
    assert cp.returncode == 1
    assert "nothing was removed" in cp.stderr
    assert not removed(cp), cp.log


def test_failed_precondition_is_caught_before_dpkg_remove(run_upgrade, env):
    shutil.rmtree(env["home"] / "VENVs")
    cp = run_upgrade("--yes", "--", "--offline")    # --offline needs the venv
    assert cp.returncode == 1
    assert not removed(cp), cp.log


def test_keep_venv_passthrough_reaches_install_sh(run_upgrade, env):
    cp = run_upgrade("--yes", "--", "--keep-venv")
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert removed(cp)
    assert "Remove and re-create" not in cp.stdout
    assert "--keep-venv" in cp.stdout
    deps = [line for line in cp.log if line.startswith("deps")]
    assert deps and "--skip-pip" not in deps[0], "--keep-venv still installs deps"
    assert any(line.startswith("sudo dpkg -i") for line in cp.log)
    dpkg = [line.split()[2] for line in cp.log if line.startswith("sudo dpkg ")]
    assert dpkg == ["-r", "-i"], "remove first, then reinstall"


def test_install_failure_after_removal_is_loud(run_upgrade):
    cp = run_upgrade("--yes", "--", "--keep-venv", extra={"DEPS_FAIL": "1"})
    assert cp.returncode != 0
    assert removed(cp)
    assert "UNINSTALLED" in cp.stderr
    reinstall = [line for line in cp.stderr.splitlines() if "install.sh --keep-venv" in line]
    assert reinstall, cp.stderr
    assert "cd " in reinstall[0] and "airlab-upgrade" in reinstall[0]


def test_help_documents_keep_venv_passthrough(run_upgrade):
    out = run_upgrade("--help").stdout
    assert "airlab upgrade -- --keep-venv" in out
