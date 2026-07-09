"""T2 (vcstool slice): `vcs init` / `status` / `pull` against local bare remotes.

These subcommands shell out to the external vcstool `vcs` binary (unlike
check/tag/checkout which are plain git). Offline — the manifest `url:` points at
a local bare repo. Skips if vcstool isn't installed.

`update` is intentionally omitted: it shells to a hardcoded
/usr/local/bin/cmds/version-control/init path, so it only works when the .deb is
installed (covered by the install tier, later), not run-in-place.
"""
import shutil

import pytest

from airlab_testlib import make_bare, make_clone, commit, current_branch

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("vcs") is None, reason="vcstool 'vcs' binary not installed"),
]

VC = "version-control"


def _build_ws(tmp_path):
    """A workspace with a manifest whose one repo points at a local bare remote."""
    bare = make_bare(tmp_path / "foo.git")
    seed = make_clone(bare, tmp_path / "seed"); commit(seed, push=True)
    ws = tmp_path / "ws"
    (ws / "version_control").mkdir(parents=True)
    (ws / "version_control" / "repos.yaml").write_text(
        "dir: src\n"
        "repositories:\n"
        "  strapsai/foo:\n"
        "    type: git\n"
        f"    url: {bare}\n"
        "    version: main\n"
    )
    return ws, bare


def _init(run, ws):
    r = run(f"{VC}/init", "--repo_file=repos.yaml", ws=ws, timeout=120)
    assert r.rc == 0, r.out
    return r


def test_init_clones_repo(run, tmp_path):
    ws, _ = _build_ws(tmp_path)
    _init(run, ws)
    clone = ws / "src" / "strapsai" / "foo"
    assert (clone / ".git").exists(), "repo was not cloned"
    assert current_branch(clone) == "main"
    assert (ws / "src" / "AIRLAB_REPO_FILE").read_text().strip() == "repos.yaml"


def test_init_here_check_reports_present(run, tmp_path):
    ws, _ = _build_ws(tmp_path)
    _init(run, ws)
    r = run(f"{VC}/init", "--here", "--check", ws=ws, cwd=ws / "src", timeout=60)
    assert "All repositories from YAML exist on disk" in r.out, r.out


def test_status_clean_after_init(run, tmp_path):
    ws, _ = _build_ws(tmp_path)
    _init(run, ws)
    r = run(f"{VC}/status", ws=ws, cwd=ws / "src", timeout=120)
    assert r.rc == 0, r.out
    assert "All repositories from YAML exist on disk" in r.out


def test_pull_no_rebase(run, tmp_path):
    ws, _ = _build_ws(tmp_path)
    _init(run, ws)
    r = run(f"{VC}/pull", "--no-rebase", ws=ws, cwd=ws / "src", timeout=120)
    assert r.rc == 0, r.out


@pytest.mark.xfail(
    reason="airlab `vcs pull` default runs `vcs pull --rebase`, but vcstool 0.3.0 "
           "`vcs pull` rejects --rebase (bug: default pull is broken; use --no-rebase)",
    strict=False,
)
def test_pull_default_rebase(run, tmp_path):
    ws, _ = _build_ws(tmp_path)
    _init(run, ws)
    r = run(f"{VC}/pull", ws=ws, cwd=ws / "src", timeout=120)
    assert r.rc == 0, r.out
