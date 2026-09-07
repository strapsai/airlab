"""T1: `airlab hosts` — set / compare / remove against a scratch hosts file.

The old `set_hosts` was hard-wired to /etc/hosts, so nothing could exercise its
write paths and it shipped with a single e2e test that only runs on real hardware.
`AIRLAB_HOSTS_FILE` now redirects the target file, which makes the whole local half
testable: marker handling, conflict detection, the drift report, backups, --dry-run,
and the set->remove round trip.

The registry is always the LOCAL robots.yaml, so these run with no network.
"""
import re

import pytest

pytestmark = pytest.mark.unit

START = "# Airlab Hosts Start"
END = "# Airlab Hosts End"

# The dummy workspace's robots.yaml (test/fixtures/airlab_ws/robot/robots.yaml).
BASE = "127.0.0.1\tlocalhost\n127.0.1.1\tmybox\n\n# hand-written\n10.9.9.9\tprivate-thing\n"


@pytest.fixture
def hosts(tmp_path):
    p = tmp_path / "hosts"
    p.write_text(BASE)
    return p


@pytest.fixture
def run_hosts(run, airlab_ws, hosts):
    def _run(*args, expect_rc=None, hosts_file=None, **kw):
        r = run("hosts", *args, ws=airlab_ws, stdin="", timeout=60,
                env={"AIRLAB_HOSTS_FILE": str(hosts_file or hosts)}, **kw)
        if expect_rc is not None:
            assert r.rc == expect_rc, f"rc={r.rc}\n{r.out}"
        return r
    return _run


def block_of(text):
    """The 'IP hostname' pairs inside the airlab markers."""
    m = re.search(re.escape(START) + r"\n(.*?)\n" + re.escape(END), text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        parts = line.split()
        if len(parts) >= 2:
            out[parts[1]] = parts[0]
    return out


# --- argument handling ------------------------------------------------------ #

def test_help_lists_the_subcommands(run_hosts):
    r = run_hosts("--help", expect_rc=0)
    for sub in ("set", "compare", "remove"):
        assert sub in r.out


def test_subcommand_help_is_not_taken_as_a_target(run_hosts):
    """`hosts set --help` must print help, not hunt for a system named '--help'."""
    r = run_hosts("set", "--help", expect_rc=0)
    assert "Usage: airlab hosts" in r.out
    assert "not found in robots.yaml" not in r.out


def test_unknown_subcommand_is_refused(run_hosts):
    r = run_hosts("frobnicate", "local")
    assert r.rc != 0 and "Unknown subcommand" in r.out


def test_missing_target_is_refused(run_hosts):
    r = run_hosts("set")
    assert r.rc != 0 and "needs a target" in r.out


def test_flag_before_target_is_refused(run_hosts):
    r = run_hosts("set", "--dry-run")
    assert r.rc != 0 and "needs a target" in r.out


# --- set -------------------------------------------------------------------- #

def test_set_writes_the_block_and_preserves_everything_else(run_hosts, hosts):
    run_hosts("set", "local", expect_rc=0)
    text = hosts.read_text()
    assert START in text and END in text
    for line in BASE.splitlines():
        assert line in text, f"pre-existing line lost: {line!r}"
    entries = block_of(text)
    assert entries, "no entries written"
    assert "robotA" in entries


def test_set_maps_default_address_to_the_bare_name_and_others_suffixed(run_hosts, hosts):
    run_hosts("set", "local", expect_rc=0)
    entries = block_of(hosts.read_text())
    assert "robotA" in entries                      # the default address
    assert not any(k.startswith("robotA-vpn") for k in entries), \
        "the vpn address has no ip in the fixture, so it must be skipped"


def test_set_is_idempotent(run_hosts, hosts):
    run_hosts("set", "local", expect_rc=0)
    once = hosts.read_text()
    run_hosts("set", "local", expect_rc=0)
    assert hosts.read_text() == once


def test_set_replaces_the_block_rather_than_appending_a_second_one(run_hosts, hosts):
    run_hosts("set", "local", expect_rc=0)
    run_hosts("set", "local", expect_rc=0)
    assert hosts.read_text().count(START) == 1


def test_set_takes_a_backup(run_hosts, hosts, tmp_path):
    run_hosts("set", "local", expect_rc=0)
    backups = list(tmp_path.glob("hosts_*"))
    assert len(backups) == 1
    assert backups[0].read_text() == BASE, "the backup must hold the PRE-write content"


def test_set_dry_run_writes_nothing(run_hosts, hosts, tmp_path):
    r = run_hosts("set", "local", "--dry-run", expect_rc=0)
    assert "dry-run" in r.out
    assert hosts.read_text() == BASE
    assert not list(tmp_path.glob("hosts_*")), "--dry-run must not leave a backup either"


def test_set_aborts_on_a_conflict_outside_the_markers(run_hosts, hosts):
    """A hand-written entry claiming a managed name must not be silently shadowed."""
    hosts.write_text(BASE + "10.1.2.3\trobotA\n")
    r = run_hosts("set", "local")
    assert r.rc != 0
    assert "CONFLICT" in r.out or "Conflicts detected" in r.out
    assert START not in hosts.read_text(), "nothing should have been written"


# --- compare ---------------------------------------------------------------- #

def test_compare_reports_no_section(run_hosts):
    r = run_hosts("compare", "local")
    assert r.rc == 2
    assert "No airlab section" in r.out


def test_compare_is_in_sync_right_after_set(run_hosts):
    run_hosts("set", "local", expect_rc=0)
    r = run_hosts("compare", "local", expect_rc=0)
    assert "in sync" in r.out


def test_compare_never_writes(run_hosts, hosts, tmp_path):
    run_hosts("set", "local", expect_rc=0)
    before = hosts.read_text()
    run_hosts("compare", "local", expect_rc=0)
    assert hosts.read_text() == before
    assert len(list(tmp_path.glob("hosts_*"))) == 1, "compare must not take a backup"


def test_compare_detects_a_stale_entry(run_hosts, hosts):
    run_hosts("set", "local", expect_rc=0)
    hosts.write_text(hosts.read_text().replace(END, "10.4.4.4         retired-bot\n" + END))
    r = run_hosts("compare", "local")
    assert r.rc == 2
    assert "STALE" in r.out and "retired-bot" in r.out


def test_compare_detects_an_ip_mismatch(run_hosts, hosts):
    run_hosts("set", "local", expect_rc=0)
    # Rewrite robotA's line whatever the column padding happens to be.
    text = re.sub(r"^\S+(\s+robotA)$", r"10.7.7.7\1", hosts.read_text(), flags=re.M)
    hosts.write_text(text)
    r = run_hosts("compare", "local")
    assert r.rc == 2
    assert "MISMATCH" in r.out and "robotA" in r.out


def test_compare_detects_a_missing_entry(run_hosts, hosts):
    run_hosts("set", "local", expect_rc=0)
    kept = [l for l in hosts.read_text().splitlines() if "robotA" not in l]
    hosts.write_text("\n".join(kept) + "\n")
    r = run_hosts("compare", "local")
    assert r.rc == 2
    assert "MISSING" in r.out and "robotA" in r.out


# --- remove ----------------------------------------------------------------- #

def test_remove_restores_the_file_byte_for_byte(run_hosts, hosts):
    run_hosts("set", "local", expect_rc=0)
    assert START in hosts.read_text()
    run_hosts("remove", "local", expect_rc=0)
    assert hosts.read_text() == BASE, "set -> remove must be a clean round trip"


def test_remove_keeps_entries_outside_the_markers(run_hosts, hosts):
    run_hosts("set", "local", expect_rc=0)
    run_hosts("remove", "local", expect_rc=0)
    text = hosts.read_text()
    assert "private-thing" in text and "localhost" in text
    assert START not in text and END not in text


def test_remove_takes_a_backup(run_hosts, hosts, tmp_path):
    run_hosts("set", "local", expect_rc=0)
    with_block = hosts.read_text()
    run_hosts("remove", "local", expect_rc=0)
    backups = sorted(tmp_path.glob("hosts_*"))
    assert len(backups) == 2
    assert any(b.read_text() == with_block for b in backups), \
        "a backup must hold the content as it was before the removal"


def test_remove_dry_run_writes_nothing(run_hosts, hosts):
    run_hosts("set", "local", expect_rc=0)
    before = hosts.read_text()
    r = run_hosts("remove", "local", "--dry-run", expect_rc=0)
    assert "REMOVED" in r.out and "dry-run" in r.out
    assert hosts.read_text() == before


def test_remove_is_a_noop_when_there_is_no_section(run_hosts, hosts, tmp_path):
    r = run_hosts("remove", "local", expect_rc=0)
    assert "nothing to remove" in r.out
    assert hosts.read_text() == BASE
    assert not list(tmp_path.glob("hosts_*"))


def test_remove_then_set_returns_to_the_same_content(run_hosts, hosts):
    run_hosts("set", "local", expect_rc=0)
    after_first = hosts.read_text()
    run_hosts("remove", "local", expect_rc=0)
    run_hosts("set", "local", expect_rc=0)
    assert hosts.read_text() == after_first
