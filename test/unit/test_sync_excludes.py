"""T1: `airlab sync`'s rsync filter rules.

The launch tree's per-block arch env files (Axis B: `<block>/x86.env`,
`<block>/jetpack.env`) are TRACKED and REQUIRED — `launch/` cannot render a single
compose file without them. A blanket `--exclude='*.env'` (added for the per-machine
root `airlab.env`) also swallowed those, so `airlab sync` delivered a launch tree with
zero .env files and every `docker compose` on the robot died with
`stat launch/<block>/x86.env: no such file or directory`.

These tests read the filter list out of `robot-sync` itself and run a real
`rsync --dry-run` against a fixture tree, so they pin behaviour rather than text.
"""
import re
import shutil
import subprocess

import pytest

from airlab_testlib import CMDS

pytestmark = pytest.mark.unit

# Files that MUST reach a robot: tracked, required, shared.
MUST_SYNC = [
    "launch/basestation-drivers/x86.env",
    "launch/phys-drivers/jetpack.env",
    "launch/vlm/x86.env",
    "launch/vlm/jetpack.env",
]
# Files that must NEVER reach a robot: per-machine, secret, or build noise.
MUST_NOT_SYNC = [
    "airlab.env",                                        # per-machine root env
    "storage_tools_ws/storage_tools_server/config.prod.env",   # deployment secrets
    "storage_tools_ws/storage_tools_device/config.env",
]


def rsync_filters():
    """The --include/--exclude tokens as robot-sync actually declares them, in order."""
    body = (CMDS / "robot-sync").read_text()
    block = body[body.index("RSYNC_OPTS=("):]
    block = block[:block.index("\n    )")]
    toks = re.findall(r"--(?:include|exclude)='[^']*'", block)
    assert toks, "could not find any filter rules in robot-sync"
    return [t.replace("'", "", 2) for t in toks]


@pytest.fixture
def tree(tmp_path):
    src = tmp_path / "airlab_ws"
    for rel in MUST_SYNC + MUST_NOT_SYNC + ["build/colcon_prefix.sh.env",
                                            "launch/phys/docker-compose.yaml"]:
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("X=1\n")
    return src


def transferred(tree, dest, extra_root=""):
    if shutil.which("rsync") is None:
        pytest.skip("rsync not available")
    root = tree / extra_root if extra_root else tree
    cp = subprocess.run(["rsync", "-a", "--dry-run", "--out-format=%n",
                         *rsync_filters(), f"{root}/", str(dest)],
                        capture_output=True, text=True, timeout=60)
    assert cp.returncode == 0, cp.stderr
    return {line.rstrip("/") for line in cp.stdout.splitlines() if line.strip()}


# --- the bug ---------------------------------------------------------------- #

@pytest.mark.parametrize("rel", MUST_SYNC)
def test_launch_arch_env_files_are_synced(tree, tmp_path, rel):
    assert rel in transferred(tree, tmp_path / "dst"), \
        f"{rel} must reach the robot — launch/ cannot render compose without it"


@pytest.mark.parametrize("rel", MUST_NOT_SYNC)
def test_per_machine_and_secret_env_files_are_not_synced(tree, tmp_path, rel):
    assert rel not in transferred(tree, tmp_path / "dst"), \
        f"{rel} is per-machine or secret and must stay local"


def test_arch_envs_are_synced_when_the_root_moves(tree, tmp_path):
    """`airlab sync --path=launch` moves the transfer root, so a 'launch/**' pattern
    would silently stop matching. The rules are anchored at any depth for this reason."""
    got = transferred(tree, tmp_path / "dst", extra_root="launch")
    assert "basestation-drivers/x86.env" in got
    assert "phys-drivers/jetpack.env" in got


# --- the ordering the fix depends on ---------------------------------------- #

def test_includes_precede_the_env_exclude(tree):
    """rsync takes the FIRST matching rule, so the includes are only effective above
    `--exclude=*.env`. Reordering them would reintroduce the bug silently."""
    rules = rsync_filters()
    env_exclude = next(i for i, r in enumerate(rules) if r == "--exclude=*.env")
    for pattern in ("--include=**/x86.env", "--include=**/jetpack.env"):
        assert pattern in rules, f"{pattern} missing from robot-sync"
        assert rules.index(pattern) < env_exclude, f"{pattern} must come before *.env"


def test_the_blanket_env_exclude_is_still_there(tree):
    """Narrowing it away entirely would start shipping storage-tools credentials."""
    assert "--exclude=*.env" in rsync_filters()


def test_build_artifacts_stay_excluded(tree, tmp_path):
    got = transferred(tree, tmp_path / "dst")
    assert not any(g.startswith("build/") for g in got)
