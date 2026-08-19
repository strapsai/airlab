"""T1: the .deb payload contains only packaged files, and setup never repackages the
delivered source tree.

`airlab setup <robot>` (online) delivers the repository to /tmp/airlab-main on the
target and runs install.sh, which builds a CLEAN .deb from a staging dir holding only
DEBIAN/, etc/ and usr/. The online path then ALSO ran `dpkg-deb --build
/tmp/airlab-main` and installed that — and since /tmp/airlab-main is the whole
repository, everything outside DEBIAN/ became payload rooted at "/". README.md,
install.sh, LICENSE, TODO, CLAUDE.md and test/ were installed into the target's
filesystem root; g-uav-2 and g-phys carry them to this day, owned by the package.

These tests pin both halves: what may appear in a package, and that setup does not
build one from the tree it delivered.
"""
import shutil
import subprocess

import pytest

from airlab_testlib import CMDS, REPO_ROOT

pytestmark = pytest.mark.unit

# Only these may ever appear at the payload root.
ALLOWED_TOP_LEVEL = {"usr", "etc"}

# Repository files that must never be packaged — the ones that actually leaked.
NEVER_PACKAGED = ["README.md", "install.sh", "LICENSE", "TODO", "CLAUDE.md",
                  "test", "requirements.txt", "install_dependencies_ubuntu24.sh"]


def _payload_paths(deb):
    cp = subprocess.run(["dpkg-deb", "-c", str(deb)], capture_output=True, text=True)
    assert cp.returncode == 0, cp.stderr
    out = []
    for line in cp.stdout.splitlines():
        path = line.split(None, 5)[-1]
        out.append(path.lstrip(".").lstrip("/").rstrip("/"))
    return [p for p in out if p]


@pytest.fixture(scope="module")
def built_deb(tmp_path_factory):
    """Stage exactly what install.sh stages, and build it."""
    if shutil.which("dpkg-deb") is None:
        pytest.skip("dpkg-deb not available")
    ctx = tmp_path_factory.mktemp("payload")
    stage = ctx / "pkg"
    for d in ("usr", "etc", "DEBIAN"):
        shutil.copytree(REPO_ROOT / d, stage / d)
    deb = ctx / "airlab.deb"
    cp = subprocess.run(["dpkg-deb", "--build", str(stage), str(deb)],
                        capture_output=True, text=True)
    assert cp.returncode == 0, cp.stderr
    return deb


def test_payload_has_only_usr_and_etc_at_the_root(built_deb):
    tops = {p.split("/")[0] for p in _payload_paths(built_deb)}
    assert tops <= ALLOWED_TOP_LEVEL, f"unexpected top-level payload entries: {tops - ALLOWED_TOP_LEVEL}"


@pytest.mark.parametrize("name", NEVER_PACKAGED)
def test_repository_files_are_not_packaged(built_deb, name):
    paths = _payload_paths(built_deb)
    assert name not in paths, f"{name} would be installed to the filesystem root"


def test_the_new_commands_are_actually_in_the_payload(built_deb):
    """Guard the opposite mistake: staging so narrowly that commands go missing."""
    paths = set(_payload_paths(built_deb))
    for expected in ("usr/local/bin/airlab",
                     "usr/local/bin/cmds/env",
                     "usr/local/bin/cmds/hosts",
                     "usr/local/bin/cmds/_lib/robot_info.py",
                     "etc/bash_completion.d/airlab",
                     "usr/share/zsh/vendor-completions/_airlab"):
        assert expected in paths, f"{expected} missing from the package"


def test_setup_does_not_build_a_package_from_the_delivered_tree():
    """A source-level assertion, deliberately: the failure mode is silent — the robot
    ends up correctly installed AND polluted, so nothing downstream notices."""
    body = (CMDS / "robot-setup").read_text()
    offending = [line.strip() for line in body.splitlines()
                 if "dpkg-deb --build" in line and not line.strip().startswith("#")]
    assert not offending, \
        f"robot-setup must not package the delivered source tree: {offending}"
