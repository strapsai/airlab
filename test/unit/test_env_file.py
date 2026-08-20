"""T1: _lib/env_file.sh — safe KEY=VALUE editing of airlab.env.

The invariant these tests exist to protect: **airlab.env is SOURCED** (~/.bashrc runs
`set -o allexport; source airlab.env`), so every line must be a valid shell assignment
and every value must come back out of the shell unchanged. An earlier version of this
file asserted the value was written *verbatim*, which for `a|b` or `two words` produces
`KEY=two words` — read by the shell as `KEY=two` plus the command `words`, breaking every
later login on that machine. Values are now quoted when they need it; assertions below
go through a real `source` rather than comparing bytes.

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

# Values that must come back out of a `source` byte-for-byte. Live shell expressions
# (`${SUDO_USER:-$USER}`) deliberately do NOT belong here — airlab.env exists so those
# expand; see test_a_shell_expression_still_expands_when_sourced.
METACHARS = [
    "a|b",                       # the old sed delimiter — used to abort the command
    "tom & jerry",               # `&` is "the whole match" in a sed replacement
    "back\\slash",
    'quoted "value"',
    "/ws/launch/docker-compose-basestation.yaml",
    "two words",                 # unquoted, this is `KEY=two` plus a command
    "db-distributed fleet storage-device",
    "",                          # empty value
]


def env_set(path, key, value):
    return subprocess.run(
        ["bash", "-c", f'source "{LIB}"; env_file_set "$1" "$2" "$3"',
         "_", str(path), key, value],
        capture_output=True, text=True, timeout=30,
    )


def source_and_read(path, key):
    """Source the file the way ~/.bashrc does, and echo one variable back."""
    r = subprocess.run(
        ["bash", "-c", f'set -o allexport; source "$1" || exit 9; printf "%s" "${{{key}}}"',
         "_", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, f"file is not sourceable: {r.stderr}\n{path.read_text()}"
    return r.stdout


@pytest.mark.parametrize("value", METACHARS)
def test_value_survives_a_source_round_trip(tmp_path, value):
    p = tmp_path / "airlab.env"
    p.write_text("FOO=old\n")
    assert env_set(p, "FOO", value).returncode == 0
    assert source_and_read(p, "FOO") == value


@pytest.mark.parametrize("value", METACHARS)
def test_value_survives_a_source_round_trip_when_appending(tmp_path, value):
    p = tmp_path / "airlab.env"
    p.write_text("OTHER=x\n")
    assert env_set(p, "NEW", value).returncode == 0
    assert source_and_read(p, "NEW") == value
    assert source_and_read(p, "OTHER") == "x"


@pytest.mark.parametrize("value,expected_line", [
    ("plain", "FOO=plain"),                       # a plain token stays unquoted
    ("/a/b.yaml", "FOO=/a/b.yaml"),
    ("two words", 'FOO="two words"'),             # anything else gets quoted
    ("a|b", 'FOO="a|b"'),
    ("${SUDO_USER:-$USER}", 'FOO="${SUDO_USER:-$USER}"'),
])
def test_quoting_matches_the_conventions_already_in_airlab_env(tmp_path, value, expected_line):
    p = tmp_path / "airlab.env"
    assert env_set(p, "FOO", value).returncode == 0
    assert p.read_text().strip() == expected_line


def test_a_shell_expression_still_expands_when_sourced(tmp_path):
    """Double quotes, not single: airlab.env's own values rely on expansion."""
    p = tmp_path / "airlab.env"
    env_set(p, "WHO", "${SUDO_USER:-fallback}")
    assert source_and_read(p, "WHO") == "fallback"


def test_other_lines_and_their_order_are_untouched(tmp_path):
    p = tmp_path / "airlab.env"
    p.write_text("A=1\nFOO=old\nB=2\n# a comment\nC=3\n")
    env_set(p, "FOO", "new")
    assert p.read_text() == "A=1\nFOO=new\nB=2\n# a comment\nC=3\n"


def test_a_multi_word_value_does_not_break_the_rest_of_the_file(tmp_path):
    """The reported bug: the broken line made `source ~/.bashrc` fail on that machine."""
    p = tmp_path / "airlab.env"
    p.write_text("ARCH=x86\n")
    env_set(p, "AIRLAB_COMPOSE_PROFILES",
            "db-distributed db-distributed-build fleet fleet-build storage-device")
    assert source_and_read(p, "ARCH") == "x86"
    assert source_and_read(p, "AIRLAB_COMPOSE_PROFILES") == \
        "db-distributed db-distributed-build fleet fleet-build storage-device"


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
    # quoted on the way out, and the value survives a source
    assert (ws / "airlab.env").read_text() == 'FOO="a|b \\"c\\""\nKEEP=me\n'
    assert source_and_read(ws / "airlab.env", "FOO") == 'a|b "c"'


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
    assert source_and_read(ws / "airlab.env", "FOO") == 'say "hi"'


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
    assert (ws / "airlab.env").read_text() == 'EXISTING=1\nNEWVAR="a|b"\n'
    assert source_and_read(ws / "airlab.env", "NEWVAR") == "a|b"
