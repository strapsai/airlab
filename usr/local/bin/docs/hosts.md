# `airlab hosts` — the /etc/hosts section, from robots.yaml

## Overview

`airlab hosts` manages a bounded section of `/etc/hosts` on this machine or a remote one, generated from `robots.yaml`, so machine names resolve directly — `ping g-uav-1`, `ssh g-uav-2-vpn` — without anyone memorising IPs.

```bash
airlab hosts set     <local|system> [options]   # write the section
airlab hosts compare <local|system> [options]   # report drift against robots.yaml
airlab hosts remove  <local|system> [options]   # delete the section
```

> Replaces `airlab set_hosts`, which now warns and forwards to `airlab hosts set`.

**The registry is always the local one.** `airlab hosts compare g-uav-1` reads *this* workstation's `robots.yaml` and *that robot's* `/etc/hosts`, so the check means the same thing wherever you run it from.

## Entry generation

For each system in `robots.yaml`, every `network_addresses` entry becomes a host entry:

| address | hostname produced |
| --- | --- |
| the one marked `default: true` | the bare system name — `g-uav-1` |
| any other | `<system>-<address_name>` — `g-uav-1-vpn` |

Two kinds of address are **skipped by design**, and both are reported in a summary at the end of every run:

* **no `ip` field** — the address resolves by hostname already (all the Tailscale `vpn` entries), so there is no static IP to write.
* **the composed name is not a valid hostname** — it would produce a line `/etc/hosts` could not use.

## What it will and will not touch

Everything happens between two markers:

```
# Airlab Hosts Start
10.3.1.50       g-uav-1
10.3.1.51       g-uav-2
# Airlab Hosts End
```

Anything outside them is preserved verbatim — your own entries, comments, `127.0.0.1 localhost`. `set` replaces the block's contents if the markers exist and appends the block if they don't. `remove` deletes the markers and everything between them, and nothing else.

Before writing, `set` checks for hostname or IP collisions with entries **outside** the markers and **aborts** rather than shadowing a hand-written line. `compare` reports the same condition as a warning, since it is what would stop a later `set`.

## Safety

* **Backups.** `set` and `remove` take a timestamped copy first — `/etc/hosts_20260429_160345` — local or remote. If two runs land in the same second the name gets a `_1`, `_2` suffix rather than overwriting the earlier backup.
* **`--dry-run`.** `set` and `remove` print exactly what they would do and write nothing — no file change, no backup. `compare` never writes, so `--dry-run` there is redundant and says so.
* **Elevation.** Remote writes go through `_lib/remote_sudo.sh`, which probes for NOPASSWD sudo first and otherwise feeds the password on stdin. Locally, `sudo` is used only when the file is not writable as your own user.

## Drift, and the exit status

`compare` classifies every difference:

```
IP MISMATCH (1) — the name resolves to the wrong host:
  dtc-gforce: /etc/hosts=192.168.50.106  registry=10.3.1.106

MISSING (5) — in robots.yaml, not in /etc/hosts:
  10.3.1.50       g-uav-1
  ...

STALE (3) — in the airlab section, no longer in robots.yaml:
  10.3.1.135      bench-02
```

**IP MISMATCH is the one to care about.** A stale entry is clutter; a mismatch means a name on that machine currently resolves to the wrong host, which is how you end up SSHing or publishing to a machine you did not mean to.

Exit status: **0** in sync, **2** drifted, **1** the comparison could not be made. So it gates a script:

```bash
airlab hosts compare local || echo "hosts file has drifted from robots.yaml"
```

## Typical use

```bash
# After adding a machine to robots.yaml
airlab hosts compare local          # see what changed
airlab hosts set local              # adopt it

# Give a robot the same view of the fleet
airlab hosts set g-uav-1
airlab hosts compare g-uav-1

# Back it out
airlab hosts remove g-uav-1 --dry-run
airlab hosts remove g-uav-1
```

## Testing note

`AIRLAB_HOSTS_FILE` redirects the target file. It exists so the unit tests can exercise the write paths against a scratch file — `set`/`compare`/`remove`, markers, conflicts, backups and `--dry-run` all run with no root and no network. Operationally you should never set it.
