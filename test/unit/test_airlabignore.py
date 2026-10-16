"""T1: `_lib/airlabignore.py`, the .airlabignore -> rsync filter converter.

Every rule is checked by running a real `rsync --dry-run` with the converter's output over a
small tree, so the tests pin what gets synced rather than the text of the patterns.
"""
import shutil
import subprocess
import sys

import pytest

from airlab_testlib import CMDS

pytestmark = pytest.mark.unit

HELPER = CMDS / "_lib" / "airlabignore.py"


def helper(*args):
    return subprocess.run([sys.executable, str(HELPER), *map(str, args)],
                          capture_output=True, text=True, timeout=30)


def filters(tmp_path, text, path=""):
    """rsync args for an .airlabignore holding `text` (written as bytes so '\\r\\n' survives)."""
    f = tmp_path / ".airlabignore"
    f.write_bytes(text.encode())
    cp = helper("rules", f, f"--path={path}")
    assert cp.returncode == 0, cp.stderr
    return cp.stdout.splitlines()


def floor(path=""):
    cp = helper("floor", f"--path={path}")
    assert cp.returncode == 0, cp.stderr
    return cp.stdout.splitlines()


def synced(tmp_path, files, rules, root=""):
    """Names rsync would transfer from a tree holding `files`, with `rules`, rooted at `root`."""
    if shutil.which("rsync") is None:
        pytest.skip("rsync not available")
    src = tmp_path / "tree"
    for rel in files:
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n")
    base = src / root if root else src
    cp = subprocess.run(["rsync", "-a", "--dry-run", "--out-format=%n", *rules, f"{base}/",
                         str(tmp_path / "dst")], capture_output=True, text=True, timeout=60)
    assert cp.returncode == 0, cp.stderr
    return {line.rstrip("/") for line in cp.stdout.splitlines() if line.strip()}


# --- syntax ------------------------------------------------------------------ #

def test_comments_and_blank_lines_are_ignored(tmp_path):
    assert filters(tmp_path, "# a comment\n\n   \n*.log\n") == ["--exclude=*.log"]


def test_a_name_without_slash_matches_at_any_depth(tmp_path):
    got = synced(tmp_path, ["a.log", "d/e/b.log", "keep.txt"], filters(tmp_path, "*.log\n"))
    assert {"a.log", "d/e/b.log"}.isdisjoint(got) and "keep.txt" in got


def test_the_last_matching_line_wins(tmp_path):
    got = synced(tmp_path, ["keep.env", "drop.env"], filters(tmp_path, "*.env\n!keep.env\n"))
    assert "keep.env" in got and "drop.env" not in got


def test_an_earlier_reinclude_loses_to_a_later_exclude(tmp_path):
    assert "keep.env" not in synced(tmp_path, ["keep.env"], filters(tmp_path, "!keep.env\n*.env\n"))


def test_a_leading_slash_anchors_at_the_workspace_root(tmp_path):
    got = synced(tmp_path, ["top.txt", "sub/top.txt"], filters(tmp_path, "/top.txt\n"))
    assert "top.txt" not in got and "sub/top.txt" in got


def test_a_slash_in_the_middle_anchors_too(tmp_path):
    got = synced(tmp_path, ["a/b.txt", "x/a/b.txt"], filters(tmp_path, "a/b.txt\n"))
    assert "a/b.txt" not in got and "x/a/b.txt" in got


def test_a_trailing_slash_matches_folders_only(tmp_path):
    got = synced(tmp_path, ["cache/data.bin", "sub/cache"], filters(tmp_path, "cache/\n"))
    assert "cache/data.bin" not in got and "sub/cache" in got


def test_double_star_matches_zero_or_more_folders(tmp_path):
    got = synced(tmp_path, ["a/b.txt", "a/x/b.txt", "a/x/y/b.txt", "c/a/b.txt"],
                 filters(tmp_path, "a/**/b.txt\n"))
    assert {"a/b.txt", "a/x/b.txt", "a/x/y/b.txt"}.isdisjoint(got) and "c/a/b.txt" in got


def test_leading_double_star_matches_a_name_at_any_depth(tmp_path):
    got = synced(tmp_path, ["secret.txt", "d/e/secret.txt", "d/keep.txt"],
                 filters(tmp_path, "**/secret.txt\n"))
    assert {"secret.txt", "d/e/secret.txt"}.isdisjoint(got) and "d/keep.txt" in got


def test_leading_double_star_with_a_folder_part(tmp_path):
    got = synced(tmp_path, ["a/b.txt", "d/a/b.txt", "d/b.txt"], filters(tmp_path, "**/a/b.txt\n"))
    assert {"a/b.txt", "d/a/b.txt"}.isdisjoint(got) and "d/b.txt" in got


def test_double_star_inside_a_name_is_a_plain_star(tmp_path):
    """gitignore: '**' is special only as a whole segment; rsync's '**' would cross '/'."""
    got = synced(tmp_path, ["axyzb", "a/x/b"], filters(tmp_path, "a**b\n"))
    assert "axyzb" not in got and "a/x/b" in got


def test_escaped_hash_and_bang_are_literal_names(tmp_path):
    got = synced(tmp_path, ["#hash.txt", "!bang.txt", "keep.txt"],
                 filters(tmp_path, "\\#hash.txt\n\\!bang.txt\n"))
    assert {"#hash.txt", "!bang.txt"}.isdisjoint(got) and "keep.txt" in got


def test_windows_line_endings_still_match(tmp_path):
    got = synced(tmp_path, ["a.log", "keep.txt"], filters(tmp_path, "*.log\r\nfoo/\r\n"))
    assert "a.log" not in got and "keep.txt" in got


def test_lines_that_are_only_a_slash_or_a_bang_are_ignored(tmp_path):
    assert filters(tmp_path, "/\n!\n!/\n") == []


def test_an_empty_file_gives_no_rules(tmp_path):
    assert filters(tmp_path, "") == []


# --- --path ------------------------------------------------------------------ #

def test_anchored_rules_follow_the_transfer_root(tmp_path):
    """`airlab sync --path=launch`: the default file's re-include still finds the arch envs."""
    files = ["launch/phys/spark_gb10.env", "launch/phys/docker-compose.yaml", "launch/stray.env"]
    got = synced(tmp_path, files, filters(tmp_path, "*.env\n!/launch/*/*.env\n", path="launch"),
                 root="launch")
    assert {"phys/spark_gb10.env", "phys/docker-compose.yaml"} <= got and "stray.env" not in got


def test_anchored_rules_for_other_parts_of_the_tree_are_dropped(tmp_path):
    assert filters(tmp_path, "/airlab.env\n/other/x\n", path="launch") == []


def test_unanchored_rules_do_not_depend_on_the_path(tmp_path):
    assert filters(tmp_path, "*.env\n", path="launch") == filters(tmp_path, "*.env\n")


@pytest.mark.parametrize("root,secret", [
    ("storage_tools_ws", "storage_tools_server/config.prod.env"),
    ("storage_tools_ws/storage_tools_server", "config.prod.env"),
])
def test_the_floor_keeps_storage_secrets_out_under_any_path(tmp_path, root, secret):
    files = ["storage_tools_ws/storage_tools_server/config.prod.env",
             "storage_tools_ws/storage_tools_server/server.py"]
    got = synced(tmp_path, files, floor(root), root=root)
    assert secret not in got and any(n.endswith("server.py") for n in got)


def test_an_explicit_path_into_an_ignored_folder_is_still_synced(tmp_path):
    rules = filters(tmp_path, "/vlm_ws/\n", path="vlm_ws/src")
    assert "a.py" in synced(tmp_path, ["vlm_ws/src/a.py"], rules, root="vlm_ws/src")


def test_an_explicit_path_into_a_floor_folder_is_still_synced(tmp_path):
    assert "x.txt" in synced(tmp_path, ["build/x.txt"], floor("build"), root="build")


def test_path_spelling_does_not_matter(tmp_path):
    want = filters(tmp_path, "!/launch/*/*.env\n", path="launch")
    assert want == ["--include=/*/*.env"]
    assert filters(tmp_path, "!/launch/*/*.env\n", path="launch/") == want
    assert filters(tmp_path, "!/launch/*/*.env\n", path="./launch") == want


def test_a_path_leaving_the_workspace_is_refused():
    cp = helper("floor", "--path=../elsewhere")
    assert cp.returncode != 0 and "--path" in cp.stderr


def test_an_unreadable_file_is_an_error(tmp_path):
    cp = helper("rules", tmp_path / "missing", "--path=")
    assert cp.returncode != 0 and "cannot read" in cp.stderr


# --- the floor --------------------------------------------------------------- #

def test_the_floor_excludes_build_output_and_the_machine_env(tmp_path):
    files = [".git/HEAD", "build/a", "ws/devel/a", "ws/log/a", "ws/install/a", "m.pyc",
             "pkg/__pycache__/m.cpython-310.pyc", "airlab.env",
             "storage_tools_ws/storage_tools_device/config.env", "keep.py"]
    assert synced(tmp_path, files, floor()) & set(files) == {"keep.py"}
