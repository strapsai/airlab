# `airlab env` — environment variables across the fleet

## The two stores

A machine's environment lives in two places, and they drift:

| | Where | What it is |
| --- | --- | --- |
| **airlab.env** | `<AIRLAB_PATH>/airlab.env` **on the machine** | What the machine actually uses. Sourced from `~/.bashrc` / `~/.zshrc`; read by `docker-up`, `launch`, `compose` and the containers. |
| **robot_info.yaml** | `<AIRLAB_PATH>/robot/robot_info.yaml` **on your workstation** | The git-tracked record of what each machine's environment *should* be. One entry per system. |

Anyone who edits `airlab.env` on a robot — during a field debug, say — moves that machine away from the record without anything noticing. `airlab env` is how you see that and decide which side wins.

**The record side is always local.** `airlab env compare g-uav-2` reads *this* workstation's `robot_info.yaml` and *the robot's* `airlab.env`. Run it from a dev machine, a basestation, or a laptop in the field: you are always comparing the machine in front of you against the record you have.

## The workflow

```bash
# 1. What has drifted?
airlab env compare g-uav-2

# 2a. The robot is right — adopt its environment into the record, then commit it.
airlab env sync-from g-uav-2

# 2b. The record is right — push it back to the robot.
airlab env sync-to g-uav-2 --dry-run     # preview as a unified diff
airlab env sync-to g-uav-2
```

`compare` exits `0` when the two sides agree and `2` when they have drifted, so it works as a gate:

```bash
airlab env compare g-uav-2 || echo "g-uav-2 has drifted from the record"
```

## Merge by default, `--prune` to subtract

`sync-from` and `sync-to` **merge**: they add and update, and leave keys the source does not mention alone. A record never loses fields because a machine's `airlab.env` is thinner, and a machine never loses a local key the record has never heard of.

`--prune` opts into the stricter reading — make the destination match the source exactly, removing anything the source lacks. Use it when you want a machine's environment to be exactly the record.

Both always show you what they will do and ask before writing. `-y` skips the prompt; `--dry-run` writes nothing.

## Shell literals survive

`airlab.env` is read as **text and never sourced**. A machine legitimately stores shell expressions:

```bash
USER_NAME=${SUDO_USER:-$USER}
GROUP_NAME=$(id -gn)
```

These round-trip through `robot_info.yaml` unchanged. That matters: if the file were sourced, `sync-from` would record whatever those happened to expand to *on the machine doing the sync*, freezing one host's identity into a record shared by the whole fleet.

When `compare` finds a resolved value on one side and a shell literal on the other, it says so rather than reporting a bare mismatch — that is usually a difference in representation, not real drift.

## Bookkeeping fields

`ws_path`, `robot_ssh` and `last_updated` sit in `robot_info.yaml` alongside the variables but are **not** environment variables — they are how the tool reaches the machine and dates the entry.

* `sync-to` never writes them to a machine.
* `sync-from` never imports them. They are operator-side truth: `robot_ssh` comes from address resolution and `ws_path` from setup, so taking them back off a machine would let a stale copy overwrite the record that produced it.

If `compare` reports them **in a machine's `airlab.env`**, that machine was provisioned by a version whose env extraction trimmed entries positionally and let them through. They do nothing there. `airlab env sync-to <system> --prune` clears them.

## `set`

```bash
airlab env set local ROS_DOMAIN_ID=10       # this machine's airlab.env
airlab env set g-uav-2 ROS_DOMAIN_ID=10     # the robot's airlab.env AND the local record
```

This replaces `airlab set_env`. For a remote target it writes both sides, so the two do not drift apart the moment you change something.

Values are written literally — `|`, `&`, quotes and backslashes are all safe. Surrounding double quotes are stripped only when **paired**, so `FOO="hello"` stores `hello` while `FOO=say "hi"` keeps its closing quote.

## Reaching the machine

`show`, `compare`, `sync-from`, `sync-to` and a remote `set` all resolve the target through `robots.yaml`, so `--address=<name>` selects a named route exactly as it does for `ssh` and `sync`:

```bash
airlab env show g-uav-2 --address=vpn
```

The machine's workspace root comes from the record's `ws_path`. A system that is in `robots.yaml` but not yet in `robot_info.yaml` — freshly registered, never provisioned — falls back to `$HOME/airlab_ws` with a warning, so `airlab env show` still works on a new machine.
