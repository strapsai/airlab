"""T1: _lib/env_file.sh — safe KEY=VALUE editing of airlab.env.

`airlab set_env local FOO=...` and `airlab setup local` both rewrote airlab.env with
`sed -i "s|^KEY=.*|KEY=VALUE|"`. The value went straight into the replacement text,
so `|` (the delimiter) aborted the command outright and `&` or a backslash would have
been rewritten silently. That path runs ON the robot — `set_env <robot>` SSHes in and
invokes `set_env local` there — so a mangled value lands on the machine.
"""
import subprocess

import pytest

from airlab_testlib import CMDS

pytestmark = pytest.mark.unit

LIB = CMDS / "_lib" / "env_file.sh"

METACHARS = [
    "a|b",                       # the old sed delimiter — used to abort the command
    "tom & jerry",               # `&` is "the whole match" in a sed replacement
    "back\\slash",
    'quoted "value"',
    "$HOME and `cmd` and $(cmd)",
    "/ws/launch/docker-compose-basestation.yaml",
    "",                          # empty value
]


def env_set(path, key, value):
    return subprocess.run(
        ["bash", "-c", f'source "{LIB}"; env_file_set "$1" "$2" "$3"',
         "_", str(path), key, value],
        capture_output=True, text=True, timeout=30,
    )


@pytest.mark.parametrize("value", METACHARS)
def test_value_is_written_literally(tmp_path, value):
    p = tmp_path / "airlab.env"
    p.write_text("FOO=old\n")
    assert env_set(p, "FOO", value).returncode == 0
    assert p.read_text() == f"FOO={value}\n"


@pytest.mark.parametrize("value", METACHARS)
def test_value_is_written_literally_when_appending(tmp_path, value):
    p = tmp_path / "airlab.env"
    p.write_text("OTHER=x\n")
    assert env_set(p, "NEW", value).returncode == 0
    assert p.read_text() == f"OTHER=x\nNEW={value}\n"


def test_other_lines_and_their_order_are_untouched(tmp_path):
    p = tmp_path / "airlab.env"
    p.write_text("A=1\nFOO=old\nB=2\n# a comment\nC=3\n")
    env_set(p, "FOO", "new")
    assert p.read_text() == "A=1\nFOO=new\nB=2\n# a comment\nC=3\n"


def test_missing_file_is_created(tmp_path):
    p = tmp_path / "airlab.env"
    assert env_set(p, "FOO", "bar").returncode == 0
    assert p.read_text() == "FOO=bar\n"


def test_a_longer_key_is_not_matched_by_prefix(tmp_path):
    p = tmp_path / "airlab.env"
    p.write_text("FOOBAR=untouched\nFOO=old\n")
    env_set(p, "FOO", "new")
    assert p.read_text() == "FOOBAR=untouched\nFOO=new\n"


def test_duplicate_keys_collapse_to_one(tmp_path):
    p = tmp_path / "airlab.env"
    p.write_text("FOO=1\nBAR=x\nFOO=2\n")
    env_set(p, "FOO", "3")
    assert p.read_text() == "FOO=3\nBAR=x\n"


def test_multiline_value_is_refused_rather_than_corrupting_the_file(tmp_path):
    p = tmp_path / "airlab.env"
    p.write_text("FOO=old\n")
    r = env_set(p, "FOO", "line1\nline2")
    assert r.returncode != 0
    assert p.read_text() == "FOO=old\n", "the file must be left alone"


def test_no_temp_file_is_left_behind(tmp_path):
    p = tmp_path / "airlab.env"
    p.write_text("FOO=old\n")
    env_set(p, "FOO", "new")
    assert [f.name for f in tmp_path.iterdir()] == ["airlab.env"]


# --- through the real command --------------------------------------------- #
# `airlab set_env` is now `airlab env set` (cmds/env); these drive the real command.

def test_env_set_local_writes_a_pipe_bearing_value(tmp_path, run):
    """`set_env local 'FOO=a|b'` used to die with "unknown option to `s'"."""
    ws = tmp_path / "ws"
    (ws / "robot").mkdir(parents=True)
    (ws / "airlab.env").write_text("FOO=old\nKEEP=me\n")
    r = run("env", "set", "local", 'FOO=a|b "c"', ws=ws, stdin="", timeout=30)
    assert r.rc == 0, r.out
    assert (ws / "airlab.env").read_text() == 'FOO=a|b "c"\nKEEP=me\n'


# --- value parsing: quotes are stripped only when paired -------------------- #

@pytest.mark.parametrize("given,want", [
    ('"hello"', "hello"),          # the documented form
    ('say "hi"', 'say "hi"'),      # used to lose the closing quote
    ('"unbalanced', '"unbalanced'),
    ('unbalanced"', 'unbalanced"'),
    ('"', '"'),                    # a lone quote is not half a pair
    ("plain", "plain"),
    ("", ""),
])
def test_strip_paired_quotes(given, want):
    r = subprocess.run(
        ["bash", "-c", f'source "{LIB}"; strip_paired_quotes "$1"', "_", given],
        capture_output=True, text=True, timeout=30,
    )
    assert r.stdout == want


def test_env_set_local_keeps_an_inner_trailing_quote(tmp_path, run):
    ws = tmp_path / "ws"
    (ws / "robot").mkdir(parents=True)
    (ws / "airlab.env").write_text("FOO=old\n")
    r = run("env", "set", "local", 'FOO=say "hi"', ws=ws, stdin="", timeout=30)
    assert r.rc == 0, r.out
    assert (ws / "airlab.env").read_text() == 'FOO=say "hi"\n'


def test_env_set_local_strips_the_documented_wrapping_quotes(tmp_path, run):
    ws = tmp_path / "ws"
    (ws / "robot").mkdir(parents=True)
    (ws / "airlab.env").write_text("FOO=old\n")
    r = run("env", "set", "local", 'FOO="hello"', ws=ws, stdin="", timeout=30)
    assert r.rc == 0, r.out
    assert (ws / "airlab.env").read_text() == "FOO=hello\n"


def test_env_set_local_appends_a_new_variable(tmp_path, run):
    ws = tmp_path / "ws"
    (ws / "robot").mkdir(parents=True)
    (ws / "airlab.env").write_text("EXISTING=1\n")
    r = run("env", "set", "local", "NEWVAR=a|b", ws=ws, stdin="", timeout=30)
    assert r.rc == 0, r.out
    assert (ws / "airlab.env").read_text() == "EXISTING=1\nNEWVAR=a|b\n"
