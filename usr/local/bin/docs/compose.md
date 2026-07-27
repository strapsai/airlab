# compose

## Overview
`airlab compose` **prefills** the `docker compose` command for this machine's elected compose file and profiles onto your prompt — editable, with tab-completion — then gets out of the way. It deliberately does **not** wrap Docker Compose: you drive Compose directly (`up -d`, `down`, `config`, `logs`, …) with all of its power.

## Syntax
```bash
airlab compose
```

## Configuration (in `airlab.env`)
Set these per machine in `$AIRLAB_PATH/airlab.env`:
- `AIRLAB_COMPOSE_FILE` — the elected top-level compose file, a filename under `$AIRLAB_PATH/launch/` (e.g. `docker-compose-basestation.yaml`).
- `AIRLAB_COMPOSE_PROFILES` — the profiles this machine runs, space- or comma-separated (e.g. `"fleet storage-tools"`).

## How It Works
The airlab shell function (zsh/bash) intercepts `airlab compose`, `cd`s to `$AIRLAB_PATH/launch`, and prefills:
```bash
docker compose --env-file ../airlab.env -f <AIRLAB_COMPOSE_FILE> --profile <p1> --profile <p2> …
```
onto the next prompt so you can edit it and run it:
- **zsh:** `print -z` pushes the line onto the editing buffer.
- **bash:** the command is injected into the readline buffer via the terminal Device-Status-Report trick (`bind '"\e[0n": …"'; printf '\e[5n'`).

A subprocess can't type into its parent shell's input buffer, which is why this lives in the shell function (like `airlab cd`). If the shell integration isn't sourced — or you run `command airlab compose` — it simply prints the command for you to copy.

## Notes
- Requires `AIRLAB_PATH` set and `$AIRLAB_PATH/airlab.env` present (populate it with `launch/deployer/deployer`).
- Errors clearly if `AIRLAB_COMPOSE_FILE` / `AIRLAB_COMPOSE_PROFILES` are unset, or the compose file is missing under `launch/`.
- **Local only** — it prepares a command for the machine you're on; there is no remote path.

## Examples
```bash
airlab compose            # cd to launch/ and prefill the command; type `up -d` and run
airlab compose --help
```
