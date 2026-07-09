# airlab test suite

Automated tests for the airlab tool. **pytest** drives the (bash) commands via
subprocess against a dummy `airlab_ws` workspace.

## Tiers
| Tier | Marker | Needs | Status |
|------|--------|-------|--------|
| T1 pure-logic | `unit` | nothing (hosted) | **active** |
| T2 git-integration | `integration` | local git (hosted) | **active** |
| T3 real-hardware e2e | `e2e` | self-hosted runner (Machine A) + sacrificial robot (Machine B) | **wired** (nightly + on-demand; connectivity slice) |
| T4 install | `install` | Docker (Ubuntu container) | planned |

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

## Real-hardware config (T3, later)
The e2e tier targets a real sacrificial robot. It will be **fully configurable** so
physical machines and VMs are interchangeable — via env / Actions vars:
`AIRLAB_TEST_ROBOT_ADDR`, `AIRLAB_TEST_ROBOT_USER`, `AIRLAB_TEST_ROBOT_PORT`,
`AIRLAB_TEST_ROBOT_AVAILABLE` (tests skip cleanly when unset).

## Known-issue xfails
Some tests are `xfail` to record real defects without blocking CI (e.g.
`robot-setup --help` requires root). See `KNOWN_HELP_ISSUES` in `unit/test_help.py`.
Remove the entry when the bug is fixed.
