"""T1: `airlab env` — argument handling, local paths, and the env<->registry logic.

The remote paths (show/compare/sync-* against a machine) need SSH and belong to the
e2e tier; what is unit-testable is the local half: `show local`, `set local`, the
registry-side import/diff that sync-from and sync-to are built on, and the guard
rails on targets and flags.

Shell literals are the thing to protect. A machine's airlab.env legitimately holds
`USER_NAME=${SUDO_USER:-$USER}`; nothing here may evaluate it, or a sync would
silently freeze one machine's expansion into the shared record.
"""
import subprocess

import pytest
import yaml

from airlab_testlib import CMDS

pytestmark = pytest.mark.unit

PY = CMDS / "_lib" / "robot_info.py"

LITERALS = {
    "USER_NAME": "${SUDO_USER:-$USER}",
    "GROUP_NAME": "$(id -gn)",
    "BACKTICK": "`hostname`",
    "PIPE": "/a|b",
    "QUOTED": 'say "hi"',
}


def py(*args):
    return subprocess.run(["python3", str(PY), *map(str, args)],
                          capture_output=True, text=True, timeout=30)


@pytest.fixture
def env_file(tmp_path):
    p = tmp_path / "airlab.env"
    p.write_text("".join(f"{k}={v}\n" for k, v in LITERALS.items()) + "ROS_DOMAIN_ID=10\n")
    return p


# --- the command's own argument handling ---------------------------------- #

def test_help_lists_every_subcommand(run, airlab_ws):
    r = run("env", "--help", ws=airlab_ws, stdin="", timeout=30)
    assert r.rc == 0
    for sub in ("show", "compare", "sync-from", "sync-to", "set"):
        assert sub in r.out


def test_unknown_subcommand_is_refused(run, airlab_ws):
    r = run("env", "frobnicate", "robotA", ws=airlab_ws, stdin="", timeout=30)
    assert r.rc != 0
    assert "Unknown subcommand" in r.out


def test_unknown_option_is_refused(run, airlab_ws):
    r = run("env", "show", "local", "--nope", ws=airlab_ws, stdin="", timeout=30)
    assert r.rc != 0
    assert "Unknown option" in r.out


@pytest.mark.parametrize("sub", ["compare", "sync-from", "sync-to"])
def test_local_is_refused_where_it_has_no_meaning(run, airlab_ws, sub):
    """These three diff or move data between HERE and a machine; `local` is not a machine."""
    r = run("env", sub, "local", ws=airlab_ws, stdin="", timeout=30)
    assert r.rc != 0
    assert "system name" in r.out


def test_missing_target_is_refused(run, airlab_ws):
    r = run("env", "show", ws=airlab_ws, stdin="", timeout=30)
    assert r.rc != 0
    assert "needs a target" in r.out


# --- show local ------------------------------------------------------------ #

def test_show_local_prints_the_env_file_verbatim(tmp_path, run):
    ws = tmp_path / "ws"
    (ws / "robot").mkdir(parents=True)
    body = "A=1\nUSER_NAME=${SUDO_USER:-$USER}\n"
    (ws / "airlab.env").write_text(body)
    r = run("env", "show", "local", ws=ws, stdin="", timeout=30)
    assert r.rc == 0
    assert "USER_NAME=${SUDO_USER:-$USER}" in r.stdout, "the literal must not be expanded"
    assert "A=1" in r.stdout


def test_show_local_without_an_env_file_fails_clearly(tmp_path, run):
    ws = tmp_path / "ws"
    (ws / "robot").mkdir(parents=True)
    r = run("env", "show", "local", ws=ws, stdin="", timeout=30)
    assert r.rc != 0
    assert "No airlab.env" in r.out


# --- set local (the airlab set_env replacement) ---------------------------- #

def test_set_local_replaces_a_value(tmp_path, run):
    ws = tmp_path / "ws"
    (ws / "robot").mkdir(parents=True)
    (ws / "airlab.env").write_text("ROS_DOMAIN_ID=1\nKEEP=me\n")
    r = run("env", "set", "local", "ROS_DOMAIN_ID=10", ws=ws, stdin="", timeout=30)
    assert r.rc == 0, r.out
    assert (ws / "airlab.env").read_text() == "ROS_DOMAIN_ID=10\nKEEP=me\n"


def test_set_local_carries_metacharacters(tmp_path, run):
    ws = tmp_path / "ws"
    (ws / "robot").mkdir(parents=True)
    (ws / "airlab.env").write_text("FOO=old\n")
    r = run("env", "set", "local", 'FOO=a|b & "c"', ws=ws, stdin="", timeout=30)
    assert r.rc == 0, r.out
    assert (ws / "airlab.env").read_text() == 'FOO=a|b & "c"\n'


def test_set_local_rejects_a_bare_name(tmp_path, run):
    ws = tmp_path / "ws"
    (ws / "robot").mkdir(parents=True)
    (ws / "airlab.env").write_text("")
    r = run("env", "set", "local", "NOEQUALS", ws=ws, stdin="", timeout=30)
    assert r.rc != 0
    assert "VAR=value" in r.out


# --- the registry side of sync-from / sync-to ------------------------------ #

def test_env_file_parsing_preserves_literals(tmp_path, env_file):
    reg = tmp_path / "robot_info.yaml"
    reg.write_text("")
    assert py("import", reg, "botA", env_file).returncode == 0
    stored = yaml.safe_load(reg.read_text())["botA"]
    for key, value in LITERALS.items():
        assert stored[key] == value, f"{key} was altered on the way in"


def test_full_round_trip_is_byte_identical(tmp_path, env_file):
    """env file -> registry (sync-from) -> env file (sync-to)."""
    reg = tmp_path / "robot_info.yaml"
    reg.write_text("")
    py("import", reg, "botA", env_file)
    regenerated = py("env", reg, "botA").stdout
    assert regenerated == env_file.read_text()


def test_import_merges_by_default(tmp_path, env_file):
    reg = tmp_path / "robot_info.yaml"
    reg.write_text('  botA:\n    ONLY_IN_RECORD: "keep"\n    last_updated: "2026-01-01 00:00:00"\n')
    py("import", reg, "botA", env_file)
    stored = yaml.safe_load(reg.read_text())["botA"]
    assert stored["ONLY_IN_RECORD"] == "keep", "a merge must not drop unrelated fields"
    assert stored["ROS_DOMAIN_ID"] == "10"


def test_import_prune_removes_fields_the_env_file_lacks(tmp_path, env_file):
    reg = tmp_path / "robot_info.yaml"
    reg.write_text('  botA:\n    ONLY_IN_RECORD: "drop"\n    ws_path: "/ws"\n'
                   '    last_updated: "2026-01-01 00:00:00"\n')
    py("import", reg, "botA", env_file, "--prune")
    stored = yaml.safe_load(reg.read_text())["botA"]
    assert "ONLY_IN_RECORD" not in stored
    assert stored["ws_path"] == "/ws", "bookkeeping survives --prune"


def test_import_never_takes_bookkeeping_from_the_env_file(tmp_path):
    """A machine provisioned before the extraction fix has ws_path/robot_ssh sitting
    in its airlab.env. Importing those would let the leak overwrite the record."""
    reg = tmp_path / "robot_info.yaml"
    reg.write_text('  botA:\n    ws_path: "/real"\n    robot_ssh: "dtc@real"\n'
                   '    last_updated: "2026-01-01 00:00:00"\n')
    env = tmp_path / "airlab.env"
    env.write_text("ws_path=/leaked\nrobot_ssh=dtc@leaked\nA=1\n")
    py("import", reg, "botA", env)
    stored = yaml.safe_load(reg.read_text())["botA"]
    assert stored["ws_path"] == "/real"
    assert stored["robot_ssh"] == "dtc@real"
    assert stored["A"] == "1"


def test_import_dry_run_writes_nothing(tmp_path, env_file):
    reg = tmp_path / "robot_info.yaml"
    reg.write_text("")
    before = reg.read_text()
    r = py("import", reg, "botA", env_file, "--dry-run")
    assert r.returncode == 0
    assert "add     ROS_DOMAIN_ID" in r.stdout
    assert reg.read_text() == before


# --- compare --------------------------------------------------------------- #

def test_envdiff_reports_in_sync_with_exit_0(tmp_path, env_file):
    reg = tmp_path / "robot_info.yaml"
    reg.write_text("")
    py("import", reg, "botA", env_file)
    r = py("envdiff", reg, "botA", env_file)
    assert r.returncode == 0
    assert "in sync" in r.stdout


def test_envdiff_reports_drift_with_exit_2(tmp_path, env_file):
    reg = tmp_path / "robot_info.yaml"
    reg.write_text("")
    py("import", reg, "botA", env_file)
    py("set", reg, "botA", "ROS_DOMAIN_ID", "99")
    r = py("envdiff", reg, "botA", env_file)
    assert r.returncode == 2
    assert "DIFFERENT" in r.stdout
    assert "ROS_DOMAIN_ID" in r.stdout


def test_envdiff_flags_a_shell_literal_against_a_resolved_value(tmp_path):
    reg = tmp_path / "robot_info.yaml"
    reg.write_text('  botA:\n    USER_NAME: "dtc"\n    last_updated: "2026-01-01 00:00:00"\n')
    env = tmp_path / "airlab.env"
    env.write_text("USER_NAME=${SUDO_USER:-$USER}\n")
    r = py("envdiff", reg, "botA", env)
    assert r.returncode == 2
    assert "shell literal" in r.stdout, "a literal-vs-resolved difference should say so"


def test_envdiff_names_leaked_bookkeeping_for_what_it_is(tmp_path):
    reg = tmp_path / "robot_info.yaml"
    reg.write_text('  botA:\n    A: "1"\n    ws_path: "/ws"\n'
                   '    last_updated: "2026-01-01 00:00:00"\n')
    env = tmp_path / "airlab.env"
    env.write_text("A=1\nws_path=/ws\nrobot_ssh=dtc@x\n")
    r = py("envdiff", reg, "botA", env)
    assert r.returncode == 2
    assert "bookkeeping leaked" in r.stdout


def test_envdiff_ignores_comments_and_blank_lines(tmp_path):
    reg = tmp_path / "robot_info.yaml"
    reg.write_text('  botA:\n    A: "1"\n    last_updated: "2026-01-01 00:00:00"\n')
    env = tmp_path / "airlab.env"
    env.write_text("# a comment\n\n   \nA=1\n")
    assert py("envdiff", reg, "botA", env).returncode == 0
