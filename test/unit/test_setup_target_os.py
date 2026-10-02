"""T1: `airlab setup <target>` installs the tool that matches the TARGET's OS.

The fleet is mixed. A Linux robot or basestation gets this tool (the .deb, with
Docker support); a Mac gets its macOS edition, `airlab-mac` (strapsai/airlab-mac).
setup asks the far side for `uname -s` before sending anything. The Linux path must
stay exactly what it was.

Everything remote is a shim below: the target's OS is the STUB_UNAME knob, and the
tests assert on what setup WOULD have run there.
"""
import os
import subprocess
from pathlib import Path

import pytest

from airlab_testlib import GIT_ENV, REPO_ROOT

pytestmark = pytest.mark.unit

# --- a fake remote machine (ssh/scp/rsync/curl/sshpass shims) ------------------ #
#
# Commands that talk to a robot are exercised against these shims, never a real
# host. `ssh` answers the handful of probes the tool makes (uname -s, echo $HOME,
# sudo -n true, "is the tool installed?") from environment knobs, and every shim
# appends its argv to a log so a test can assert what WOULD have run remotely.

FAKE_SSH = r'''#!/usr/bin/env bash
log="${STUB_DIR:?}/ssh.log"
printf '%s\n' "$*" >> "$log"
cmd="${@: -1}"
case "$cmd" in
    "uname -s")                   echo "${STUB_UNAME-Linux}"; exit 0 ;;
    'echo $HOME')                 echo "${STUB_HOME:-/home/robotuser}"; exit 0 ;;
    "sudo -n true")               exit "${STUB_SUDO_NOPASSWD_RC:-0}" ;;
    "[ -d "*)                     exit 1 ;;
    "test -e "*)                  exit 1 ;;   # no such path (e.g. a free backup name)
    *"dpkg -l"*)                  exit "${STUB_DPKG_RC:-1}" ;;
    *"airlab --version"*)         [ -n "${STUB_MAC_VERSION:-}" ] && echo "$STUB_MAC_VERSION"; exit 0 ;;
    "test -x /opt/homebrew/bin/brew"*) exit "${STUB_BREW_RC:-0}" ;;
    "/bin/bash -s -- "*)          cat > "$STUB_DIR/remote_script.sh"; exit 0 ;;
    "date +%s")                   date +%s; exit 0 ;;
    "cat > "*|*"cat > "*)         cat > /dev/null; exit 0 ;;
    "cat "*)                      f="${cmd#cat }"; if [ -f "$f" ]; then cat "$f"; else echo "127.0.0.1 localhost"; fi; exit 0 ;;
    exit)                         exit 0 ;;
esac
# Anything piped in (sudo passwords, staged content) is drained, not echoed. Only a
# pipe: an inherited terminal or never-closing stdin would hang the suite.
[ -p /dev/stdin ] && cat > /dev/null
exit 0
'''

FAKE_SCP = r'''#!/usr/bin/env bash
printf '%s\n' "$*" >> "${STUB_DIR:?}/scp.log"
src="${@: -2:1}"; dest="${@: -1}"
mkdir -p "$STUB_DIR/scp"
cp "$src" "$STUB_DIR/scp/$(basename "${dest#*:}")"
'''

FAKE_RSYNC = r'''#!/usr/bin/env bash
printf '%s\n' "$*" >> "${STUB_DIR:?}/rsync.log"
exit 0
'''

FAKE_CURL = r'''#!/usr/bin/env bash
printf '%s\n' "$*" >> "${STUB_DIR:?}/curl.log"
out=""
while [ $# -gt 0 ]; do
    case "$1" in -o) out="$2"; shift ;; esac
    shift
done
[ -n "$out" ] && : > "$out"
exit 0
'''

FAKE_SSHPASS = r'''#!/usr/bin/env bash
[ "$1" = "-p" ] && shift 2
exec "$@"
'''


def make_fake_remote(tmp_path):
    """Write the shims to <tmp>/fakebin; return (bin_dir, stub_dir)."""
    bin_dir = tmp_path / "fakebin"
    stub_dir = tmp_path / "stub"
    bin_dir.mkdir()
    stub_dir.mkdir()
    for name, body in [("ssh", FAKE_SSH), ("scp", FAKE_SCP), ("rsync", FAKE_RSYNC),
                       ("curl", FAKE_CURL), ("sshpass", FAKE_SSHPASS)]:
        p = bin_dir / name
        p.write_text(body)
        p.chmod(0o755)
    return bin_dir, stub_dir


def read_log(stub_dir, name):
    p = Path(stub_dir) / f"{name}.log"
    return p.read_text() if p.exists() else ""


@pytest.fixture
def remote(tmp_path, airlab_ws):
    bin_dir, stub_dir = make_fake_remote(tmp_path)
    # The workspace must be a git repo for the --offline path (`git ls-files`).
    env_git = {**os.environ, **GIT_ENV}
    subprocess.run(["git", "init", "-q", str(airlab_ws)], check=True, env=env_git)
    # Homebrew's bin sits right after the shims (and before /usr/bin), so the tool's
    # PATH setup leaves the order alone and no real ssh/rsync can get ahead of them.
    path = os.pathsep.join([str(bin_dir), "/opt/homebrew/bin", "/usr/local/bin", os.environ["PATH"]])
    return {"bin": bin_dir, "stub": stub_dir, "path": path}


@pytest.fixture
def linux_src():
    """This repository is a Linux `airlab` source tree."""
    return REPO_ROOT


@pytest.fixture
def mac_src(tmp_path):
    """A minimal tree that looks like an `airlab-mac` checkout."""
    d = tmp_path / "airlab-mac-src"
    (d / "share" / "airlab").mkdir(parents=True)
    (d / "share" / "airlab" / "VERSION").write_text("1.0.0\n")
    (d / "bin").mkdir()
    (d / "bin" / "airlab").write_text("#!/bin/bash\n")
    (d / "install.sh").write_text("#!/bin/bash\n")
    return d


@pytest.fixture
def online_ws(airlab_ws, remote):
    """Give the workspace a clonable origin (a local bare repo), as online setup needs."""
    bare = airlab_ws.parent / "ws.git"
    env_git = {**os.environ, **GIT_ENV}
    for cmd in (["add", "-A"], ["commit", "-qm", "ws"], ["branch", "-M", "main"]):
        subprocess.run(["git", "-C", str(airlab_ws), *cmd], check=True, env=env_git)
    subprocess.run(["git", "clone", "-q", "--bare", str(airlab_ws), str(bare)], check=True, env=env_git)
    subprocess.run(["git", "-C", str(airlab_ws), "remote", "add", "origin", str(bare)],
                   check=True, env=env_git)
    return airlab_ws


def _setup(run, remote, *args, uname="Linux", extra_env=None, system="robotA"):
    env = {"PATH": remote["path"], "STUB_DIR": str(remote["stub"]),
           "STUB_UNAME": uname, "STUB_HOME": "/Users/robot" if uname == "Darwin" else "/home/robotuser"}
    env.update(extra_env or {})
    return run("robot-setup", system, *args, env=env, stdin="", timeout=60)


def _offline(src):
    return ["--offline", f"--airlab-src={src}", "-y", "--no-reboot"]


# --- which tool ------------------------------------------------------------- #

def test_linux_target_gets_the_linux_tool(run, remote, linux_src):
    r = _setup(run, remote, *_offline(linux_src), uname="Linux")
    assert r.rc == 0, r.out
    assert "Target OS: linux -> installing 'airlab'" in r.out
    ssh = read_log(remote["stub"], "ssh")
    assert "bash /tmp/airlab-main/install.sh --offline" in ssh
    assert "airlab-mac" not in ssh


def test_mac_target_gets_airlab_mac(run, remote, mac_src):
    r = _setup(run, remote, *_offline(mac_src), uname="Darwin")
    assert r.rc == 0, r.out
    assert "Target OS: macos -> installing 'airlab-mac'" in r.out
    ssh = read_log(remote["stub"], "ssh")
    assert "/bin/bash /tmp/airlab-mac-main/install.sh --offline -y" in ssh
    assert "/tmp/airlab-main/" not in ssh
    # No Linux package machinery against a Mac.
    assert "dpkg" not in ssh and "apt-get" not in ssh


def test_online_linux_install_downloads_strapsai_airlab(run, remote, online_ws):

    r = _setup(run, remote, "-y", "--no-reboot", uname="Linux")
    assert r.rc == 0, r.out
    assert "github.com/strapsai/airlab/archive/refs/heads/main.zip" in read_log(remote["stub"], "curl")
    assert "bash /tmp/airlab-main/install.sh --override-venv" in read_log(remote["stub"], "ssh")


def test_online_mac_install_downloads_strapsai_airlab_mac(run, remote, online_ws):

    r = _setup(run, remote, "-y", uname="Darwin")
    assert r.rc == 0, r.out
    assert "github.com/strapsai/airlab-mac/archive/refs/heads/main.zip" in read_log(remote["stub"], "curl")
    ssh = read_log(remote["stub"], "ssh")
    assert "/bin/bash /tmp/airlab-mac-main/install.sh --override-venv -y" in ssh


def test_unknown_os_is_refused_before_anything_is_sent(run, remote, linux_src):
    r = _setup(run, remote, *_offline(linux_src), uname="FreeBSD")
    assert r.rc != 0
    assert "Unsupported target OS" in r.out and "unknown:FreeBSD" in r.out
    assert read_log(remote["stub"], "rsync") == ""
    assert read_log(remote["stub"], "scp") == ""


def test_no_uname_answer_is_refused(run, remote, linux_src):
    r = _setup(run, remote, *_offline(linux_src), uname="")
    assert r.rc != 0
    assert "Unsupported target OS" in r.out


# --- the wrong tool is never sent -------------------------------------------- #

def test_mac_source_tree_refused_for_a_linux_target(run, remote, mac_src):
    r = _setup(run, remote, *_offline(mac_src), uname="Linux")
    assert r.rc != 0
    assert "is an 'airlab-mac' tree" in r.out and "needs 'airlab'" in r.out
    assert read_log(remote["stub"], "rsync") == ""


def test_linux_source_tree_refused_for_a_mac_target(run, remote, linux_src):
    r = _setup(run, remote, *_offline(linux_src), uname="Darwin")
    assert r.rc != 0
    assert "is an 'airlab' tree" in r.out and "needs 'airlab-mac'" in r.out


def test_unrecognised_source_tree_refused(run, remote, tmp_path):
    junk = tmp_path / "junk"
    junk.mkdir()
    r = _setup(run, remote, *_offline(junk), uname="Linux")
    assert r.rc != 0
    assert "neither an 'airlab' nor an 'airlab-mac' source tree" in r.out


# --- per-OS details ----------------------------------------------------------- #

def _env_sent(remote):
    p = Path(remote["stub"]) / "scp" / "airlab.env"
    assert p.exists(), "no airlab.env was copied to the target"
    return p.read_text()


# "no-default-bot" is in robots.yaml but has no robot_info record, so setup takes
# the fresh path: it records the machine and writes it a new airlab.env.
def test_linux_target_env_keeps_docker_keys(run, remote, online_ws):
    r = _setup(run, remote, "-y", "--no-reboot", uname="Linux", system="no-default-bot")
    assert r.rc == 0, r.out
    env = _env_sent(remote)
    assert "AIRLAB_PATH=/home/robotuser/airlab_ws\n" in env
    assert "DOCKER_BUILD_PATH=/home/robotuser/airlab_ws/docker/docker-compose.yml\n" in env
    assert "AIRLAB_DEFAULT_IMAGE=" in env
    record = (online_ws / "robot" / "robot_info.yaml").read_text()
    assert "no-default-bot:" in record and "DOCKER_BUILD_PATH" in record


def test_mac_target_env_has_no_docker_keys(run, remote, online_ws):
    r = _setup(run, remote, "-y", uname="Darwin", system="no-default-bot")
    assert r.rc == 0, r.out
    env = _env_sent(remote)
    assert "AIRLAB_PATH=/Users/robot/airlab_ws\n" in env
    assert "LAUNCH_FILE_PATH=/Users/robot/airlab_ws/launch/sample.yaml\n" in env
    assert "DOCKER" not in env
    record = (online_ws / "robot" / "robot_info.yaml").read_text()
    section = record.split("no-default-bot:")[1]
    assert "DOCKER" not in section


def test_mac_target_gets_mac_rc_edits_not_gnu_sed(run, remote, mac_src):
    r = _setup(run, remote, *_offline(mac_src), uname="Darwin")
    assert r.rc == 0, r.out
    ssh = read_log(remote["stub"], "ssh")
    assert "sed -i" not in ssh               # BSD sed has no GNU -i
    script = (Path(remote["stub"]) / "remote_script.sh").read_text()
    assert 'grep -v "source .*airlab\\.env"' in script
    assert ".bash_profile" in script         # login bash must reach ~/.bashrc


def test_linux_target_rc_edits_are_unchanged(run, remote, linux_src):
    r = _setup(run, remote, *_offline(linux_src), uname="Linux")
    assert r.rc == 0, r.out
    assert "sed -i '/source .*airlab.env/d' ~/.bashrc" in read_log(remote["stub"], "ssh")


def test_mac_target_is_not_rebooted(run, remote, mac_src):
    r = _setup(run, remote, "--offline", f"--airlab-src={mac_src}", "-y", uname="Darwin")
    assert r.rc == 0, r.out
    assert "No reboot needed on a Mac" in r.out
    assert "reboot" not in read_log(remote["stub"], "ssh")


def test_mac_target_workspace_rsync_uses_homebrew_rsync(run, remote, mac_src):
    r = _setup(run, remote, *_offline(mac_src), uname="Darwin")
    assert r.rc == 0, r.out
    rsync = read_log(remote["stub"], "rsync")
    assert '--rsync-path=env PATH="/opt/homebrew/bin:/usr/local/bin:$PATH" rsync' in rsync


def test_linux_target_rsync_has_no_rsync_path(run, remote, linux_src):
    r = _setup(run, remote, *_offline(linux_src), uname="Linux")
    assert r.rc == 0, r.out
    assert "--rsync-path" not in read_log(remote["stub"], "rsync")


def test_mac_target_without_homebrew_is_refused(run, remote, online_ws):
    # Online (not --offline): Homebrew is required on the Mac to install dependencies.
    r = _setup(run, remote, "-y", uname="Darwin", extra_env={"STUB_BREW_RC": "1"})
    assert r.rc != 0
    assert "Homebrew is not installed" in r.out
