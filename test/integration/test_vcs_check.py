"""T2: `vcs check` against local git sandboxes (offline; no vcstool).

Filesystem mode groups on-disk clones by normalized origin URL and flags clones
of the same URL sitting on different commits ([DRIFT]). --version-control mode
inspects the manifest YAMLs only. Both are read-only and do no network.
"""
import pytest

from airlab_testlib import make_bare, make_clone, commit, git

CHECK = "version-control/check"


def _manifest(*repos, dir_="src"):
    """Build a manifest. Each repo is (key, url, version). Explicit indentation
    (no dedent) so nested keys land correctly under `repositories:`."""
    if not repos:
        repos = (("strapsai/foo", "git@github.com:strapsai/foo.git", "main"),)
    lines = [f"dir: {dir_}", "repositories:"]
    for key, url, version in repos:
        lines += [f"  {key}:", "    type: git", f"    url: {url}", f"    version: {version}"]
    return "\n".join(lines) + "\n"


# ---- filesystem mode ---- #

@pytest.mark.integration
def test_fs_shared_same_commit_is_clean(run, tmp_path):
    # two clones of one remote at the SAME commit but with DIFFERENT url forms;
    # normalize_url must treat them as one repo -> "same commit" -> exit 0.
    bare = make_bare(tmp_path / "r.git")
    seed = make_clone(bare, tmp_path / "seed"); commit(seed, push=True)
    ws = tmp_path / "ws"; ws.mkdir()
    make_clone(bare, ws / "a", origin_url="git@github.com:o/r.git")
    make_clone(bare, ws / "b", origin_url="https://github.com/o/r")
    r = run(CHECK, cwd=ws)
    assert r.rc == 0, r.out
    assert "same commit" in r.out.lower()


@pytest.mark.integration
def test_fs_drift_across_url_forms(run, tmp_path):
    # same two url forms, but the clones are on DIFFERENT commits -> [DRIFT], exit 1.
    # Proves both URL normalization (grouped) and drift detection.
    bare = make_bare(tmp_path / "r.git")
    seed = make_clone(bare, tmp_path / "seed"); commit(seed, push=True)
    ws = tmp_path / "ws"; ws.mkdir()
    a = make_clone(bare, ws / "a", origin_url="git@github.com:o/r.git")
    make_clone(bare, ws / "b", origin_url="https://github.com/o/r")
    commit(a, name="extra.txt", msg="diverge")  # a moves ahead
    r = run(CHECK, cwd=ws)
    assert r.rc == 1, r.out
    assert "DRIFT" in r.out


# ---- --version-control mode ---- #

@pytest.mark.integration
def test_vc_clean(run, tmp_path):
    vc = tmp_path / "ws" / "version_control"; vc.mkdir(parents=True)
    (vc / "a.yaml").write_text(_manifest())
    r = run(CHECK, "--version-control", ws=tmp_path / "ws")
    assert r.rc == 0, r.out


@pytest.mark.integration
def test_vc_version_drift(run, tmp_path):
    url = "git@github.com:strapsai/foo.git"
    vc = tmp_path / "ws" / "version_control"; vc.mkdir(parents=True)
    (vc / "a.yaml").write_text(_manifest(("strapsai/foo", url, "main")))
    (vc / "b.yaml").write_text(_manifest(("strapsai/foo", url, "dev")))
    r = run(CHECK, "--version-control", ws=tmp_path / "ws")
    assert r.rc == 1, r.out
    assert "VERSION DRIFT" in r.out


@pytest.mark.integration
def test_vc_duplicate_url_within_one_yaml(run, tmp_path):
    url = "git@github.com:strapsai/foo.git"
    vc = tmp_path / "ws" / "version_control"; vc.mkdir(parents=True)
    (vc / "a.yaml").write_text(_manifest(
        ("strapsai/foo", url, "main"),
        ("strapsai/foo_alias", url, "main"),
    ))
    r = run(CHECK, "--version-control", ws=tmp_path / "ws")
    assert r.rc == 1, r.out
    assert "DUPLICATE URL" in r.out
