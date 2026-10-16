"""T1: what `airlab sync` copies to a machine.

`robot-sync` builds its rsync filters from the built-in floor, the `--exclude=` flags and
`$AIRLAB_PATH/.airlabignore`, in that order (rsync takes the first matching rule). These tests
run the real `robot-sync` against stub `ssh`/`rsync` (the stub records rsync's arguments
instead of transferring) and replay the recorded filters with a real `rsync --dry-run`, so
they pin what reaches a machine, not the text of the rules.

History: a blanket `--exclude='*.env'` that re-admitted only x86.env and jetpack.env dropped
the Spark's launch/<block>/spark_gb10.env files (2026-10-15).
"""
import os
import shutil
import subprocess
import sys

import pytest

from airlab_testlib import CMDS, REPO_ROOT

pytestmark = pytest.mark.unit

HELPER = CMDS / "_lib" / "airlabignore.py"
TEMPLATE = REPO_ROOT / "etc" / "airlab" / ".airlabignore"

# Must reach a machine: tracked, shared, and compose cannot render without them.
MUST_SYNC = [
    "launch/basestation-drivers/x86.env",
    "launch/phys-drivers/jetpack.env",
    "launch/phys/spark_gb10.env",
    "launch/newblock/future_arch.env",
    "launch/phys/docker-compose.yaml",
]
# Must stay local: per-machine, secret, or build output.
MUST_NOT_SYNC = [
    "airlab.env",
    "storage_tools_ws/storage_tools_server/config.prod.env",
    "storage_tools_ws/storage_tools_device/config.env",
    "ras_ws/src/triage_database/database.env",
    "perception_ws/src/HumanFlow/docker/.env",
    "config/dev_env/g-force-2_20261012.env",
    "scripts/system-init-scripts/airlab.env",
    "build/colcon_prefix.sh.env",
    "physiology_ws/build/rrate/setup.py",
]


def template():
    assert TEMPLATE.is_file(), f"{TEMPLATE} (the default .airlabignore) is missing"
    return TEMPLATE.read_text()


def helper_lines(*args):
    cp = subprocess.run([sys.executable, str(HELPER), *args], capture_output=True, text=True)
    assert cp.returncode == 0, cp.stderr
    return cp.stdout.splitlines()


def transferred(src, rules, tmp_path):
    if shutil.which("rsync") is None:
        pytest.skip("rsync not available")
    cp = subprocess.run(["rsync", "-a", "--dry-run", "--out-format=%n", *rules,
                         src.rstrip("/") + "/", str(tmp_path / "dst")],
                        capture_output=True, text=True, timeout=60)
    assert cp.returncode == 0, cp.stderr
    return {line.rstrip("/") for line in cp.stdout.splitlines() if line.strip()}


@pytest.fixture
def sync(airlab_ws, tmp_path, run):
    """sync(*args, ignore=TEXT|None) -> (result, filters|None, src|None) for
    `airlab sync robotA --dry-run *args`. The workspace holds MUST_SYNC + MUST_NOT_SYNC;
    `ignore` becomes its .airlabignore (None: no file). filters is None if rsync never ran."""
    for rel in MUST_SYNC + MUST_NOT_SYNC:
        p = airlab_ws / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("X=1\n")
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    argv_log = tmp_path / "rsync.argv"
    (bindir / "ssh").write_text("#!/bin/sh\nexit 0\n")
    (bindir / "rsync").write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{argv_log}"\n')
    for stub in bindir.iterdir():
        stub.chmod(0o755)

    def _sync(*args, ignore=None):
        f = airlab_ws / ".airlabignore"
        if ignore is None:
            f.unlink(missing_ok=True)
        else:
            f.write_text(ignore)
        argv_log.unlink(missing_ok=True)
        res = run("robot-sync", "robotA", "--dry-run", *args,
                  env={"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"})
        if not argv_log.exists():
            return res, None, None
        argv = argv_log.read_text().splitlines()
        return res, [a for a in argv if a.startswith(("--include=", "--exclude="))], argv[-2]
    return _sync


# --- the default policy ------------------------------------------------------ #

@pytest.mark.parametrize("rel", MUST_SYNC)
def test_shared_files_reach_the_machine(sync, tmp_path, rel):
    res, rules, src = sync(ignore=template())
    assert res.rc == 0, res.out
    assert rel in transferred(src, rules, tmp_path)


@pytest.mark.parametrize("rel", MUST_NOT_SYNC)
def test_per_machine_secret_and_build_files_stay_local(sync, tmp_path, rel):
    res, rules, src = sync(ignore=template())
    assert res.rc == 0, res.out
    assert rel not in transferred(src, rules, tmp_path)


def test_arch_envs_reach_the_machine_under_path_launch(sync, tmp_path):
    res, rules, src = sync("--path=launch", ignore=template())
    assert res.rc == 0, res.out
    got = transferred(src, rules, tmp_path)
    assert {"phys/spark_gb10.env", "basestation-drivers/x86.env", "newblock/future_arch.env"} <= got


# --- precedence -------------------------------------------------------------- #

def test_the_file_cannot_override_the_floor(sync, tmp_path):
    res, rules, src = sync(ignore="!airlab.env\n!/airlab.env\n!build/\n!config*.env\n")
    got = transferred(src, rules, tmp_path)
    assert {"airlab.env", "storage_tools_ws/storage_tools_server/config.prod.env",
            "build/colcon_prefix.sh.env"}.isdisjoint(got)


def test_an_exclude_flag_beats_the_files_reinclude(sync, tmp_path):
    res, rules, src = sync("--exclude=spark_gb10.env", ignore=template())
    got = transferred(src, rules, tmp_path)
    assert "launch/phys/spark_gb10.env" not in got and "launch/basestation-drivers/x86.env" in got


def test_filters_are_floor_then_flags_then_file(sync):
    res, rules, _ = sync("--exclude=from-flag", ignore="from-file\n")
    assert rules == helper_lines("floor", "--path=") + ["--exclude=from-flag", "--exclude=from-file"]


# --- missing, empty and broken ----------------------------------------------- #

def test_without_a_file_the_floor_still_applies(sync, tmp_path):
    res, rules, src = sync(ignore=None)
    assert res.rc == 0, res.out
    assert "No .airlabignore" in res.out
    got = transferred(src, rules, tmp_path)
    assert {"airlab.env", "storage_tools_ws/storage_tools_device/config.env",
            "build/colcon_prefix.sh.env"}.isdisjoint(got)


def test_an_empty_file_leaves_only_the_floor(sync):
    res, rules, _ = sync(ignore="# nothing here\n")
    assert res.rc == 0, res.out
    assert rules == helper_lines("floor", "--path=")
    assert "(0 rules)" in res.out


def test_the_rules_source_is_logged(sync):
    res, _, _ = sync(ignore=template())
    assert "Ignore rules:" in res.out and ".airlabignore" in res.out


def test_a_converter_failure_stops_the_sync(sync):
    res, rules, _ = sync("--path=../outside", ignore=template())
    assert res.rc != 0 and rules is None
