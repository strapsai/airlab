"""T1: the `alias` command (airlab a) — listing, linting, and running.

Uses the dummy workspace's alias/ dir (hello.sh) via AIRLAB_ALIAS_PATH, which
the `run` fixture points at the copied workspace. Pure filesystem behavior — no
network/container.
"""
import pytest


@pytest.mark.unit
def test_list_shows_alias(run):
    r = run("alias")
    assert r.rc == 0, r.out
    assert "hello" in r.out


@pytest.mark.unit
def test_lint_passes_on_compliant_alias(run):
    r = run("alias", "--lint")
    assert r.rc == 0, f"lint should pass on the compliant fixture alias:\n{r.out}"


@pytest.mark.unit
def test_run_alias_executes(run):
    r = run("alias", "hello")
    assert r.rc == 0, r.out
    assert "HELLO_FROM_ALIAS" in r.out


@pytest.mark.unit
def test_lint_fails_on_noncompliant_alias(run, airlab_ws):
    # an alias missing the required @desc/@author headers must fail lint
    bad = airlab_ws / "alias" / "bad.sh"
    bad.write_text("#!/bin/bash\necho nope\n")
    bad.chmod(0o755)
    r = run("alias", "--lint")
    assert r.rc != 0, f"lint should fail when an alias violates the contract:\n{r.out}"
    assert "bad" in r.out.lower()
