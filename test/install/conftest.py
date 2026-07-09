"""T4 (install tier) fixtures.

Builds the airlab .deb from a clean staging tree (usr/ + etc/ + DEBIAN/), installs
it into a fresh Ubuntu container, and exposes `in_image` to run commands inside
that installed image. Skips if Docker isn't available. This is the ONE tier that
exercises the installed `/usr/local/bin/airlab` dispatcher (and its hardcoded
paths, e.g. `vcs update`).
"""
import shutil
import subprocess
from pathlib import Path

import pytest

from airlab_testlib import REPO_ROOT

INSTALL_DIR = Path(__file__).resolve().parent
IMAGE_TAG = "airlab-test-install:ci"


def _docker_available():
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@pytest.fixture(scope="session")
def airlab_image(tmp_path_factory):
    if not _docker_available():
        pytest.skip("docker not available")
    ctx = tmp_path_factory.mktemp("airlab_install_ctx")

    # Build a clean .deb: stage only the package contents (not test/, .git/, …).
    stage = ctx / "pkg"
    for d in ("usr", "etc", "DEBIAN"):
        shutil.copytree(REPO_ROOT / d, stage / d)
    deb = ctx / "airlab.deb"
    r = subprocess.run(["dpkg-deb", "--build", str(stage), str(deb)],
                       capture_output=True, text=True)
    assert r.returncode == 0, f"dpkg-deb failed:\n{r.stderr}"

    shutil.copy(INSTALL_DIR / "Dockerfile", ctx / "Dockerfile")
    b = subprocess.run(["docker", "build", "-t", IMAGE_TAG, str(ctx)],
                       capture_output=True, text=True)
    if b.returncode != 0:
        pytest.fail(f"docker build failed:\n{b.stdout[-3000:]}\n{b.stderr[-3000:]}")
    yield IMAGE_TAG


@pytest.fixture
def in_image(airlab_image):
    """Run a shell command inside a throwaway container of the installed image."""
    def _run(cmd, timeout=120):
        return subprocess.run(
            ["docker", "run", "--rm", airlab_image, "bash", "-lc", cmd],
            capture_output=True, text=True, timeout=timeout,
        )
    return _run
