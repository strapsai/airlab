# airlab test suite

Automated tests for the airlab tool. **pytest** drives the (bash) commands via
subprocess against a dummy `airlab_ws` workspace.

## Tiers
| Tier | Marker | Needs | Status |
|------|--------|-------|--------|
| T1 pure-logic | `unit` | nothing (hosted) | **active** |
| T2 git-integration | `integration` | local git (hosted) | **active** |
| T3 real-hardware e2e | `e2e` | self-hosted runner (Machine A) + sacrificial robot (Machine B) | **wired** (nightly + on-demand; connectivity slice) |
| T4 install | `install` | Docker (Ubuntu container) | **active** |

## Run locally
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r test/requirements-test.txt
cd test && python -m pytest unit        # T1
```

## How it works
- Commands are **standalone bash scripts run in-place by path** with `$AIRLAB_PATH`
  set — no install needed (matches the tool's CLAUDE.md "Testing" note). Tests do
  not go through the installed `/usr/local/bin/airlab` dispatcher (that gets a
  single smoke test in the install tier).
- `conftest.py` provides: `airlab_ws` (a fresh, mutable **copy** of
  `fixtures/airlab_ws` per test), and `run(cmd, *args)` → `Result(rc, stdout,
  stderr)` with ANSI stripped. Command list is **auto-discovered** so new commands
  are covered by the `--help` contract automatically.
- The address resolver (`_lib/resolve.sh`) shells to `$AIRLAB_PATH/robot/robots.py`.
  That resolver lives in **airlab_ws, not this repo**, so `fixtures/airlab_ws/robot/`
  ships a faithful **stub** honoring the CLI contract (`resolve`/`list`/`addresses`).

## Fixtures (`fixtures/airlab_ws/`)
A dummy workspace with the tricky cases baked in: a hostname-only (no-`ip`) address
and a port-bearing address in `robots.yaml`; `robot_info.yaml` with `ws_path`;
a `version_control` manifest; a compliant `alias/`. Copy-per-test keeps mutations
isolated.

## Install tier (T4)
Builds the `.deb` (staging `usr/`+`etc/`+`DEBIAN/`), installs it in a fresh
Ubuntu container, and smokes the installed dispatcher (`--version`, `greet`,
`vcs`/`vcs update` routing), both shell completions, and the postinst signal
seed. Covers the **installed** layout (incl. `vcs update`'s hardcoded path) that
run-in-place tests can't. It does NOT run the full `install.sh` (venv/pip/apt/
nvidia) — the manual `test/test_install.sh` remains the full-stack install smoke.

## Real-hardware config (T3, later)
The e2e tier targets a real sacrificial robot. It will be **fully configurable** so
physical machines and VMs are interchangeable — via env / Actions vars:
`AIRLAB_TEST_ROBOT_ADDR`, `AIRLAB_TEST_ROBOT_USER`, `AIRLAB_TEST_ROBOT_PORT`,
`AIRLAB_TEST_ROBOT_AVAILABLE` (tests skip cleanly when unset).

## vcs family coverage
`check` / `tag` / `checkout` are plain-git (offline). `init` / `status` / `pull`
shell out to the vcstool `vcs` binary (installed via requirements-test.txt;
`setuptools<81` is pinned because vcstool still imports `pkg_resources`).
`update` is not covered run-in-place — it shells to a hardcoded
`/usr/local/bin/...` path, so it belongs to the install tier.

## Known-issue xfails
Tests can be `xfail`ed to record a real defect without blocking CI (see
`KNOWN_HELP_ISSUES` in `unit/test_help.py`). No hard xfails currently.

Fixed (previously xfail): `robot-setup --help` (required root); `vcs pull --rebase`
(rejected by vcstool 0.3.0); and `hosts set <robot>` remote sudo — now via the shared
`_lib/remote_sudo.sh` helper (handles key/password SSH × NOPASSWD/password sudo; sudo
password from `$robot_password` → `$AIRLAB_SUDO_PASSWORD` → prompt).

Both `hosts` and `robot-setup` now route remote sudo through `_lib/remote_sudo.sh`,
so they work on a key-authorized + no-NOPASSWD robot (sudo password from
`$AIRLAB_SUDO_PASSWORD` etc.). The `robot-setup` path is validated via the opt-in
`e2e/test_robot_setup.py` (gated behind `AIRLAB_TEST_ALLOW_ROBOT_SETUP=1`; reinstalls
airlab on the robot — re-snapshot B afterward).
