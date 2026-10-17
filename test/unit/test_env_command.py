"""T1: `airlab env` — argument handling, local paths, and the env<->registry logic.

The remote paths (show/compare/sync-* against a machine) need SSH and belong to the
e2e tier; what is unit-testable is the local half: `show local`, `set local`, the
registry-side import/diff that sync-from and sync-to are built on, and the guard
rails on targets and flags.

Shell literals are the thing to protect. A machine's airlab.env legitimately holds
`USER_NAME=${SUDO_USER:-$USER}`; nothing here may evaluate it, or a sync would
silently freeze one machine's expansion into the shared record.
"""
import os
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
    """Quoted on the way out — airlab.env is sourced, so `FOO=a|b & "c"` bare is a
    pipeline and a background job, not an assignment."""
    ws = tmp_path / "ws"
    (ws / "robot").mkdir(parents=True)
    (ws / "airlab.env").write_text("FOO=old\n")
    r = run("env", "set", "local", 'FOO=a|b & "c"', ws=ws, stdin="", timeout=30)
    assert r.rc == 0, r.out
    back = subprocess.run(
        ["bash", "-c", 'set -o allexport; source "$1" || exit 9; printf "%s" "$FOO"',
         "_", str(ws / "airlab.env")], capture_output=True, text=True, timeout=30)
    assert back.returncode == 0, back.stderr
    assert back.stdout == 'a|b & "c"'


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


def test_full_round_trip_preserves_every_value(tmp_path, env_file):
    """env file -> registry (sync-from) -> env file (sync-to).

    The emitted file is NORMALISED, not byte-identical to the input: values are quoted
    where the shell needs it. That is the point — the input fixture here is deliberately
    an unsourceable file (`PIPE=/a|b` is a pipeline, not an assignment), which is exactly
    the shape that used to be written back out verbatim and break `source ~/.bashrc`.

    So the invariant is: the regenerated file SOURCES, and yields exactly the values the
    registry holds.
    """
    reg = tmp_path / "robot_info.yaml"
    reg.write_text("")
    py("import", reg, "botA", env_file)
    regenerated = tmp_path / "regenerated.env"
    regenerated.write_text(py("env", reg, "botA").stdout)

    stored = {k: v for k, v in yaml.safe_load(reg.read_text())["botA"].items()
              if k not in ("ws_path", "robot_ssh", "last_updated")}

    dump = "; ".join('printf "%s\\037%s\\036" ' + f'"{k}" "${{{k}}}"' for k in stored)
    r = subprocess.run(["bash", "-c", f'set -o allexport; source "$1" || exit 9; {dump}',
                        "_", str(regenerated)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"regenerated env is not sourceable: {r.stderr}"

    got = {}
    for rec in r.stdout.split("\036"):
        if "\037" in rec:
            k, _, v = rec.partition("\037")
            got[k] = v

    # Shell expressions expand on source by design; compare those separately.
    for key, value in stored.items():
        if "$" in value or "`" in value:
            assert got[key] != "", f"{key} expanded to nothing"
        else:
            assert got[key] == value, f"{key}: {got[key]!r} != {value!r}"


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


# --- sync-to end to end, against a stub ssh -------------------------------- #
#
# The round trip above writes `robot_info.py env` straight to a file, but sync-to
# does not: it stages each key through env_file_set, which quotes the value itself.
# Feeding it the already-quoted `env` output quoted every non-token value twice
# (`KEY="\"a b\""`), and the escapes grew on each sync-from/sync-to cycle. These run
# the real command, with an `ssh` that executes the remote command locally.

SYNC_VALUES = {
    "PROFILES": "db db-build fleet",            # multi-word: needs quotes
    "QOS": "/home/$USER/airlab_ws/x.xml",       # live expansion: quoted, $ left live
    "QUOTED": 'say "hi"',                       # embedded double quotes
    "PLAIN": "plain-token",                     # needs no quotes at all
}


@pytest.fixture
def remote(airlab_ws, tmp_path):
    """robotA's airlab.env lives in a local dir; returns (env_path, PATH with stub ssh)."""
    home = tmp_path / "robotA_ws"
    home.mkdir()
    env_path = home / "airlab.env"
    env_path.write_text("ROS_DOMAIN_ID=1\nLOCAL_ONLY=keep-me\n")

    info = airlab_ws / "robot" / "robot_info.yaml"
    for key, value in {"ws_path": str(home), **SYNC_VALUES}.items():
        assert py("set", info, "robotA", key, value).returncode == 0

    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "ssh"
    stub.write_text(
        "#!/bin/bash\n"
        "# Drop options and the target, run the remote command here.\n"
        'while [ $# -gt 0 ]; do case "$1" in -o|-p) shift 2;; -*) shift;; *) break;; esac; done\n'
        "shift\n"
        '[ $# -eq 0 ] && exit 0\n'
        'exec bash -c "$*"\n')
    stub.chmod(0o755)
    return env_path, f"{bindir}:{os.environ['PATH']}"


def test_sync_to_quotes_each_value_once(run, remote):
    env_path, path = remote
    r = run("env", "sync-to", "robotA", "--yes", env={"PATH": path})
    assert r.rc == 0, r.out
    lines = env_path.read_text().splitlines()
    assert 'PROFILES="db db-build fleet"' in lines
    assert 'QOS="/home/$USER/airlab_ws/x.xml"' in lines
    assert 'QUOTED="say \\"hi\\""' in lines
    assert "PLAIN=plain-token" in lines
    assert "LOCAL_ONLY=keep-me" in lines            # keys the record lacks survive
    assert not any('="\\"' in line for line in lines), lines


def test_sync_to_output_sources_to_the_recorded_values(run, remote):
    env_path, path = remote
    assert run("env", "sync-to", "robotA", "--yes", env={"PATH": path}).rc == 0
    r = subprocess.run(
        ["bash", "-c", 'source "$1"; printf "%s\\n" "$PROFILES" "$QUOTED" "$QOS"',
         "_", str(env_path)], capture_output=True, text=True, timeout=30)
    # QOS expands on source; the fixture record itself sets USER=dtc.
    assert r.stdout.splitlines() == ["db db-build fleet", 'say "hi"', "/home/dtc/airlab_ws/x.xml"]


def test_sync_to_is_idempotent_and_compare_agrees(run, remote):
    env_path, path = remote
    assert run("env", "sync-to", "robotA", "--yes", env={"PATH": path}).rc == 0
    first = env_path.read_text()
    again = run("env", "sync-to", "robotA", "--yes", env={"PATH": path})
    assert again.rc == 0 and "already matches" in again.out, again.out
    assert env_path.read_text() == first
    # Every recorded value matches; the env file's own extra keys (ROS_DOMAIN_ID,
    # LOCAL_ONLY) are reported as env-only, which is compare's exit 2 by design.
    cmp = run("env", "compare", "robotA", env={"PATH": path})
    assert ", 0 differ, 0 only in the record," in cmp.out, cmp.out


def test_envdiff_decodes_escaped_double_quotes(tmp_path):
    """`KEY="say \\"hi\\""` is the value `say "hi"`, not `say \\"hi\\"`."""
    reg = tmp_path / "robot_info.yaml"
    reg.write_text('  botA:\n    Q: "say \\"hi\\""\n    B: "a\\\\b"\n')
    env = tmp_path / "airlab.env"
    env.write_text('Q="say \\"hi\\""\nB="a\\\\b"\n')
    assert py("envdiff", reg, "botA", env).returncode == 0
