"""T1: robot_info.yaml — canonical format, the writer, and env extraction.

Covers `_lib/robot_info.py` (the format owner) and the `_lib/robot_info.sh` wrappers
that `robot-setup` and `set_env` call. Three defects are pinned here:

  1. The old writers seeded a fresh file with a `robots:` root, while every reader
     looks a field up as `<system>.<field>` at the TOP level — a file created by the
     tool was born unreadable by the tool.
  2. `read_env_from_yaml` trimmed the tail of an entry positionally (two blind
     `sed '$d'`), so its output depended on where the system sat in the file:
     `robot_ssh` leaked into airlab.env for every entry except the last one.
  3. The writer was line-anchored `sed -i "s|...|...|"`, so a value containing the
     `|` delimiter, a quote or a backslash corrupted the file — and the whole
     implementation was duplicated in `robot-setup` and `set_env`, already drifted.
"""
import subprocess

import pytest
import yaml

from airlab_testlib import CMDS

pytestmark = pytest.mark.unit

PY = CMDS / "_lib" / "robot_info.py"
SH = CMDS / "_lib" / "robot_info.sh"

# Two entries so "middle vs last" is expressible — that ordering is what defect 2 was
# sensitive to. `zz-last` is deliberately the final entry in the file.
SAMPLE = '''  botA:
    ROS_DOMAIN_ID: "10"
    DOCKER_UP_PATH: "/ws/docker/docker-compose.yml"
    robot_ssh: "dtc@10.0.0.10"
    ws_path: "/ws"
    last_updated: "2026-07-09 00:00:00"
  zz-last:
    ROS_DOMAIN_ID: "20"
    robot_ssh: "dtc@10.0.0.20"
    ws_path: "/ws"
    last_updated: "2026-07-09 00:00:00"
'''


@pytest.fixture
def reg(tmp_path):
    """A registry file in the canonical format; returns its Path."""
    p = tmp_path / "robot_info.yaml"
    p.write_text(SAMPLE)
    return p


def py(*args):
    return subprocess.run(["python3", str(PY), *map(str, args)],
                          capture_output=True, text=True, timeout=30)


def sh(script, **kw):
    """Run a snippet with the bash wrappers sourced and log_* stubbed."""
    body = (
        'log_info(){ :; }; log_warn(){ echo "[WARN] $1"; }; log_error(){ echo "[ERROR] $1" >&2; }; '
        f'source "{SH}"; {script}'
    )
    return subprocess.run(["bash", "-c", body], capture_output=True, text=True,
                          timeout=30, **kw)


# --- 1. canonical format: system names at the top level -------------------- #

def test_new_file_has_no_robots_root(tmp_path):
    """A file the tool creates must be readable by the tool."""
    p = tmp_path / "fresh.yaml"
    assert py("set", p, "botA", "ROS_DOMAIN_ID", "7").returncode == 0
    data = yaml.safe_load(p.read_text())
    assert "robots" not in data
    assert data["botA"]["ROS_DOMAIN_ID"] == "7"


def test_empty_file_is_seeded_correctly(tmp_path):
    """etc/airlab/robot/robot_info.yaml ships EMPTY, so this is the fresh-workspace path."""
    p = tmp_path / "empty.yaml"
    p.write_text("")
    assert py("set", p, "botA", "A", "b").returncode == 0
    data = yaml.safe_load(p.read_text())
    assert "robots" not in data
    assert data["botA"]["A"] == "b"
    assert "last_updated" in data["botA"]


def test_legacy_robots_root_is_reported_not_half_read(tmp_path):
    p = tmp_path / "legacy.yaml"
    p.write_text('robots:\n  botA:\n    ws_path: "/ws"\n')
    r = py("get", p, "botA", "ws_path")
    assert r.returncode != 0
    assert "legacy" in r.stderr.lower() and "robots" in r.stderr


def test_missing_system_is_quietly_absent(reg):
    r = py("get", reg, "nope", "ws_path")
    assert r.returncode == 1 and r.stdout == ""


# --- 2. env extraction: by name, not by position --------------------------- #

BOOKKEEPING = ("ws_path", "robot_ssh", "last_updated")


@pytest.mark.parametrize("system", ["botA", "zz-last"])
def test_env_excludes_bookkeeping_regardless_of_position(reg, system):
    """The old positional trim leaked robot_ssh for every entry but the last."""
    r = py("env", reg, system)
    assert r.returncode == 0
    keys = [line.split("=", 1)[0] for line in r.stdout.splitlines()]
    for field in BOOKKEEPING:
        assert field not in keys, f"{field} leaked into airlab.env for {system}"
    assert "ROS_DOMAIN_ID" in keys


def test_env_is_position_independent(reg):
    """Both entries carry the same shape, so both must yield the same key set."""
    a = {l.split("=", 1)[0] for l in py("env", reg, "botA").stdout.splitlines()}
    b = {l.split("=", 1)[0] for l in py("env", reg, "zz-last").stdout.splitlines()}
    assert b <= a and "ROS_DOMAIN_ID" in b


def test_env_survives_a_field_added_after_last_updated(reg):
    """A trailing field used to be swallowed by the blind tail trim."""
    py("set", reg, "botA", "ADDED_LATE", "yes")
    keys = [l.split("=", 1)[0] for l in py("env", reg, "botA").stdout.splitlines()]
    assert "ADDED_LATE" in keys


# --- 3. the writer --------------------------------------------------------- #

@pytest.mark.parametrize("value", [
    "a|b",                       # the old sed delimiter
    'say "hi"',
    "back\\slash",
    "$HOME and `cmd`",
    "amp & semi; colon",
    "/ws/docker/docker-compose.yml",
])
def test_writer_round_trips_shell_and_sed_metacharacters(reg, value):
    assert py("set", reg, "botA", "TRICKY", value).returncode == 0
    assert py("get", reg, "botA", "TRICKY").stdout.rstrip("\n") == value
    assert yaml.safe_load(reg.read_text())["botA"]["TRICKY"] == value


def test_writer_leaves_other_entries_byte_identical(reg):
    before = reg.read_text().splitlines()
    py("set", reg, "botA", "NEWKEY", "v")
    after = reg.read_text().splitlines()
    # zz-last's block is untouched (its last_updated included).
    i = before.index("  zz-last:")
    j = after.index("  zz-last:")
    assert before[i:] == after[j:]


def test_last_updated_stays_at_the_end_and_is_refreshed(reg):
    py("set", reg, "botA", "NEWKEY", "v")
    block = [l for l in reg.read_text().splitlines()]
    start = block.index("  botA:")
    end = block.index("  zz-last:")
    entry = block[start + 1:end]
    assert entry[-1].strip().startswith("last_updated:")
    assert '"2026-07-09 00:00:00"' not in entry[-1]


def test_no_overwrite_keeps_the_existing_value(reg):
    r = py("set", reg, "botA", "DOCKER_UP_PATH", "/should/not/win", "--no-overwrite")
    assert r.returncode == 0
    assert r.stdout.strip() == "/ws/docker/docker-compose.yml"
    assert yaml.safe_load(reg.read_text())["botA"]["DOCKER_UP_PATH"] \
        == "/ws/docker/docker-compose.yml"


def test_no_overwrite_still_writes_when_the_field_is_absent(reg):
    py("set", reg, "botA", "FRESH", "/v", "--no-overwrite")
    assert yaml.safe_load(reg.read_text())["botA"]["FRESH"] == "/v"


# --- the bash wrappers the commands actually call -------------------------- #

def test_update_robot_info_returns_the_effective_value(tmp_path, reg):
    """robot-setup relies on the return_var receiving the KEPT value, not its own."""
    ws = tmp_path / "ws"
    (ws / "robot").mkdir(parents=True)
    (ws / "robot" / "robot_info.yaml").write_text(SAMPLE)
    r = sh(f'update_robot_info "{ws}" botA DOCKER_UP_PATH /nope --no-overwrite kept; '
           f'echo "KEPT=$kept"')
    assert "KEPT=/ws/docker/docker-compose.yml" in r.stdout


def test_update_robot_info_return_var_is_not_evaluated(tmp_path):
    """The old implementation used `eval`, so a value with backticks or $() ran."""
    ws = tmp_path / "ws"
    (ws / "robot").mkdir(parents=True)
    marker = tmp_path / "pwned"
    r = sh(f'update_robot_info "{ws}" botA V \'$(touch {marker})`touch {marker}`\' "" got; '
           f'echo "GOT=$got"')
    assert r.returncode == 0
    assert not marker.exists(), "value was evaluated by the shell"
    assert "GOT=$(touch" in r.stdout


def test_robot_info_has(tmp_path):
    p = tmp_path / "robot_info.yaml"
    p.write_text(SAMPLE)
    assert sh(f'robot_info_has "{p}" botA').returncode == 0
    assert sh(f'robot_info_has "{p}" nope').returncode != 0
    assert sh(f'robot_info_has "{tmp_path}/missing.yaml" botA').returncode != 0


def test_read_env_from_yaml_writes_an_env_file(tmp_path, reg):
    out = tmp_path / "airlab.env"
    r = sh(f'read_env_from_yaml "{reg}" botA "{out}"')
    assert r.returncode == 0
    lines = out.read_text().splitlines()
    assert "ROS_DOMAIN_ID=10" in lines
    assert not [l for l in lines if l.split("=", 1)[0] in BOOKKEEPING]


def test_read_env_from_yaml_fails_on_a_missing_file(tmp_path):
    r = sh(f'read_env_from_yaml "{tmp_path}/nope.yaml" botA "{tmp_path}/out"')
    assert r.returncode != 0
