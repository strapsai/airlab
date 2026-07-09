"""T2: `vcs tag` (+ `push --tags` dry-run) against local git sandboxes (offline)."""
import pytest

from airlab_testlib import make_bare, make_clone, commit, tags, git

TAG = "version-control/tag"
PUSH = "version-control/push"


def _ws_with_repo(tmp_path):
    bare = make_bare(tmp_path / "r.git")
    seed = make_clone(bare, tmp_path / "seed"); commit(seed, push=True)
    ws = tmp_path / "ws"; ws.mkdir()
    a = make_clone(bare, ws / "a")
    return ws, a, bare


@pytest.mark.integration
def test_dry_run_creates_no_tag(run, tmp_path):
    ws, a, _ = _ws_with_repo(tmp_path)
    r = run(TAG, "v1", "-m", "msg", "--dry-run", cwd=ws)
    assert r.rc == 0, r.out
    assert "would tag" in r.out.lower()
    assert tags(a) == []


@pytest.mark.integration
def test_creates_annotated_tag(run, tmp_path):
    ws, a, _ = _ws_with_repo(tmp_path)
    r = run(TAG, "v1", "-m", "msg", cwd=ws)
    assert r.rc == 0, r.out
    assert "v1" in tags(a)
    # annotated -> has a tag object
    assert git("cat-file", "-t", "v1", cwd=a) == "tag"


@pytest.mark.integration
def test_lightweight_tag(run, tmp_path):
    ws, a, _ = _ws_with_repo(tmp_path)
    r = run(TAG, "v2", "--lightweight", cwd=ws)
    assert r.rc == 0, r.out
    assert "v2" in tags(a)
    assert git("cat-file", "-t", "v2", cwd=a) == "commit"  # lightweight -> points at commit


@pytest.mark.integration
def test_missing_name_fails(run, tmp_path):
    ws, a, _ = _ws_with_repo(tmp_path)
    r = run(TAG, cwd=ws)
    assert r.rc == 1


@pytest.mark.integration
def test_lightweight_conflicts_with_message(run, tmp_path):
    ws, a, _ = _ws_with_repo(tmp_path)
    r = run(TAG, "v1", "-m", "msg", "--lightweight", cwd=ws)
    assert r.rc == 1


@pytest.mark.integration
def test_push_tags_dry_run_does_not_push(run, tmp_path):
    ws, a, bare = _ws_with_repo(tmp_path)
    run(TAG, "v1", "-m", "msg", cwd=ws)          # create local tag
    r = run(PUSH, "--tags=v1", "--dry-run", cwd=ws)
    assert r.rc == 0, r.out
    assert ("[DRY]" in r.out) or ("would push" in r.out.lower())
    assert "v1" not in (git("tag", cwd=bare).split())  # nothing pushed to the remote
