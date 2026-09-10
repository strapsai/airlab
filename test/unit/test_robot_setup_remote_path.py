"""T1: `airlab setup <robot> --path=` must reach the ROBOT.

`--path` is documented in the usage text and shown in an example
(`airlab setup robot1 --path=~/custom/path --force`), and `setup local` honors it.
The remote dispatch used to hardcode "~/airlab_ws" and never pass PARSED_PATH, so
every `airlab setup <robot> --path=...` silently installed to the robot's default
location instead. That is hard to notice: the run reports success, and the split
only shows up later as an airlab.env in a place nothing looks for.

The default must NOT simply become PARSED_PATH, because that defaults to the
OPERATOR's $HOME/airlab_ws — sending it to a robot would install under a path that
exists only on the workstation. So the remote path stays "~/airlab_ws" (expanded
against the ROBOT's home) unless --path was explicitly given.

setup_remote reaches the observable line ("Checking for workspace setup at ...")
only after SSH, so these tests shim ssh/scp/rsync/sshpass/curl onto PATH. The
fixture registry's addresses are private-range and never contacted anyway.
"""
import os
import stat

import pytest

pytestmark = pytest.mark.unit

_ROBOT_HOME = "/home/robotuser"

_SSH_STUB = f"""#!/bin/bash
for a in "$@"; do
  case "$a" in
    'echo $HOME') echo {_ROBOT_HOME}; exit 0 ;;
    '[ -d '*)     exit 1 ;;
  esac
done
exit 0
"""
_NOOP_STUB = "#!/bin/bash\nexit 0\n"


@pytest.fixture
def shimmed_path(tmp_path):
    """A PATH with ssh and friends stubbed, so setup_remote gets past connecting."""
    bin_dir = tmp_path / "shim"
    bin_dir.mkdir()
    for name, body in [("ssh", _SSH_STUB), ("scp", _NOOP_STUB), ("rsync", _NOOP_STUB),
                       ("sshpass", _NOOP_STUB), ("curl", _NOOP_STUB)]:
        p = bin_dir / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return f"{bin_dir}{os.pathsep}{os.environ['PATH']}"


def _target_path(out):
    for line in out.splitlines():
        if "workspace setup at" in line:
            return line.rsplit(" ", 1)[-1].strip()
    raise AssertionError(f"setup_remote never reported a target path:\n{out}")


def test_explicit_path_is_used(run, shimmed_path):
    r = run("robot-setup", "robotA", "--path=/data/airlab/airlab_ws", "-y",
            env={"PATH": shimmed_path}, stdin="", timeout=30)
    assert _target_path(r.out) == "/data/airlab/airlab_ws", r.out


def test_default_is_the_robots_home_not_the_operators(run, shimmed_path):
    r = run("robot-setup", "robotA", "-y",
            env={"PATH": shimmed_path}, stdin="", timeout=30)
    target = _target_path(r.out)
    assert target == f"{_ROBOT_HOME}/airlab_ws", r.out
    # The operator's own home must never leak into a remote install path.
    assert os.path.expanduser("~") not in target, r.out
