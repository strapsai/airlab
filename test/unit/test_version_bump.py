"""T1: the automatic patch-bump logic used by the version-bump workflow.

The workflow at .github/workflows/version-bump.yml commits to contributors'
branches, so a wrong decision here silently corrupts the version on every PR.
The pure logic lives in .github/scripts/bump_version.py precisely so it can be
tested; this pins the ownership contract:

    MAJOR.MINOR -> the maintainer's, CI never touches them
    PATCH       -> CI's, always base-patch + 1
"""
import importlib.util

import pytest

from airlab_testlib import REPO_ROOT, package_version

pytestmark = pytest.mark.unit

_spec = importlib.util.spec_from_file_location(
    "bump_version", REPO_ROOT / ".github" / "scripts" / "bump_version.py"
)
bump = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bump)


def V(s):
    """'2.2.0-Stable-Release' -> the tuple the script works in."""
    return bump.parse_version(f"Version: {s}\n", "<test>")


def test_parses_the_real_control_file():
    major, minor, patch, suffix = bump.parse_version(
        (REPO_ROOT / "DEBIAN" / "control").read_text(), "DEBIAN/control"
    )
    assert (major, minor) >= (2, 2)
    assert isinstance(patch, int)
    assert bump.format_version((major, minor, patch, suffix)) == package_version()


def test_malformed_version_is_rejected():
    with pytest.raises(bump.MalformedVersion):
        bump.parse_version("Package: airlab\nVersion: two point two\n", "<test>")
    with pytest.raises(bump.MalformedVersion):
        bump.parse_version("Package: airlab\n", "<test>")


def test_unchanged_pr_gets_the_next_patch():
    target, _ = bump.compute_next_version(V("2.2.0-Stable-Release"), V("2.2.0-Stable-Release"))
    assert bump.format_version(target) == "2.2.1-Stable-Release"


def test_bump_is_relative_to_base_not_head():
    # A stale branch that still says 2.2.0 while dev has moved to 2.2.7
    # must land on 2.2.8, never 2.2.1.
    target, _ = bump.compute_next_version(V("2.2.7-Stable-Release"), V("2.2.0-Stable-Release"))
    assert bump.format_version(target) == "2.2.8-Stable-Release"


def test_already_bumped_is_a_noop():
    head = V("2.2.1-Stable-Release")
    target, reason = bump.compute_next_version(V("2.2.0-Stable-Release"), head)
    assert target == head
    assert "already" in reason


def test_idempotent_across_repeated_runs():
    base, head = V("2.2.0-Stable-Release"), V("2.2.0-Stable-Release")
    first, _ = bump.compute_next_version(base, head)
    second, _ = bump.compute_next_version(base, first)
    assert first == second


@pytest.mark.parametrize("authored", ["2.3.0-Stable-Release", "3.0.0-Stable-Release",
                                      "2.3.4-Stable-Release"])
def test_major_minor_change_is_left_to_the_maintainer(authored):
    # The reserved half changed, so CI takes the version verbatim — patch included.
    target, reason = bump.compute_next_version(V("2.2.9-Stable-Release"), V(authored))
    assert bump.format_version(target) == authored
    assert "maintainer-owned" in reason


def test_suffix_is_preserved_from_head():
    target, _ = bump.compute_next_version(V("2.2.0-Stable-Release"), V("2.2.0-rc1"))
    assert bump.format_version(target) == "2.2.1-rc1"


def test_apply_rewrites_only_the_version_line():
    control = (REPO_ROOT / "DEBIAN" / "control").read_text()
    out = bump.apply_version(control, V("9.9.9-Stable-Release"))
    assert "Version: 9.9.9-Stable-Release" in out
    assert out.count("Version:") == control.count("Version:")
    for line in control.splitlines():
        if not line.startswith("Version:"):
            assert line in out
