"""T2: `vcs checkout` against local git sandboxes (offline via --no-fetch)."""
import pytest

from conftest import make_bare, make_clone, commit, current_branch, git

CHECKOUT = "version-control/checkout"


def _ws_with_branches(tmp_path):
    bare = make_bare(tmp_path / "r.git")
    seed = make_clone(bare, tmp_path / "seed")
    commit(seed, push=True)                                  # main @ base
    git("checkout", "-q", "-b", "feature", cwd=seed)
    commit(seed, name="feat.txt", msg="feat")
    git("push", "-q", "origin", "feature", cwd=seed)         # publish feature
    git("tag", "rel1", cwd=seed)
    git("push", "-q", "origin", "rel1", cwd=seed)            # publish a tag
    ws = tmp_path / "ws"; ws.mkdir()
    a = make_clone(bare, ws / "a")                           # on main; knows origin/feature + rel1
    return ws, a


@pytest.mark.integration
def test_switch_to_published_branch(run, tmp_path):
    ws, a = _ws_with_branches(tmp_path)
    r = run(CHECKOUT, "feature", "--no-fetch", cwd=ws)
    assert current_branch(a) == "feature", r.out
    assert "switched" in r.out.lower()


@pytest.mark.integration
def test_missing_ref_fails(run, tmp_path):
    ws, a = _ws_with_branches(tmp_path)
    r = run(CHECKOUT, "no-such-ref", "--no-fetch", cwd=ws)
    assert r.rc == 1, r.out
    assert "MISSING" in r.out
    assert current_branch(a) == "main"  # unchanged
