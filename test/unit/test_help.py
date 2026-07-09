"""T1: every command must handle --help gracefully (usage + exit 0).

Auto-discovers all command scripts, so new commands are covered automatically.
This is both a smoke test (the script parses/loads without error) and a
contract check (--help is the one universally-safe invocation).

KNOWN_HELP_ISSUES documents commands that currently violate this (xfail), so the
suite stays green while recording the defect. Remove the entry when fixed.
"""
import pytest

from airlab_testlib import all_command_scripts

# command -> reason it currently fails `--help` (bug to fix; see worklog)
KNOWN_HELP_ISSUES = {
    "robot-setup": "enforces root before handling --help; --help should not require sudo",
}


def _params():
    out = []
    for cmd in all_command_scripts():
        marks = []
        if cmd in KNOWN_HELP_ISSUES:
            marks.append(pytest.mark.xfail(reason=KNOWN_HELP_ISSUES[cmd], strict=False))
        out.append(pytest.param(cmd, marks=marks))
    return out


COMMANDS = _params()


@pytest.mark.unit
@pytest.mark.parametrize("cmd", COMMANDS)
def test_help_exits_zero(run, cmd):
    r = run(cmd, "--help")
    assert r.rc == 0, f"{cmd} --help exited {r.rc}\n{r.out}"


@pytest.mark.unit
@pytest.mark.parametrize("cmd", COMMANDS)
def test_help_prints_usage(run, cmd):
    r = run(cmd, "--help")
    assert "usage" in r.out.lower(), f"{cmd} --help printed no usage:\n{r.out}"


@pytest.mark.unit
def test_discovered_commands_nonempty():
    # guard against a broken discovery / path change silently emptying the suite
    assert len(COMMANDS) >= 10
