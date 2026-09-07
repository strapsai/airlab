# compose

## Overview
`airlab compose` is this machine's `docker compose` command — either **prefilled** onto your prompt to edit, or **run** for you.

- **Bare** (`airlab compose`) it prefills the command for this machine's elected compose file and profiles — editable, with tab-completion — then gets out of the way.
- **With arguments** (`airlab compose up -d`) it runs Compose with them, from `$AIRLAB_PATH/launch`.

The point of the second form: the elected file and profiles live in `airlab.env`, so **the same command brings the right stack up on any configured machine** — a basestation, a robot, a GPU box — without the operator knowing which compose file or profiles that machine uses. It also works non-interactively, so it is usable over `airlab exec`, ssh, or from a script.

Arguments are handed to Compose **verbatim**, so nothing is taken away: `up`, `down`, `config`, `ps`, `logs`, `build`, `restart` and the rest all behave normally, and Compose's exit code is propagated.

## Syntax
```bash
airlab compose                      # prefill the command
airlab compose up -d                # run it
airlab compose down                 # run it
airlab compose --dry-run up -d      # print exactly what would run; run nothing
```

## Configuration (in `airlab.env`)
Set these per machine in `$AIRLAB_PATH/airlab.env`:
- `AIRLAB_COMPOSE_FILE` — the elected top-level compose file, a filename under `$AIRLAB_PATH/launch/` (e.g. `docker-compose-basestation.yaml`).
- `AIRLAB_COMPOSE_PROFILES` — the profiles this machine runs, space- or comma-separated (e.g. `"fleet storage-tools"`).

## How It Works

**With arguments**, it is an ordinary command: it `cd`s to `$AIRLAB_PATH/launch`, prints the full command it is about to run (so a bare `airlab compose down` never leaves you guessing which stack it just stopped), and `exec`s it.

**Bare**, the airlab shell function (zsh/bash) intercepts `airlab compose`, `cd`s to `$AIRLAB_PATH/launch`, and prefills:
```bash
docker compose -f <AIRLAB_COMPOSE_FILE> --profile <p1> --profile <p2> …
```
onto the next prompt so you can edit it and run it.

### Why the two forms differ by `--env-file`

The **prefilled** form has no `--env-file`: it is typed into an interactive shell, where `~/.bashrc` has already sourced and exported `airlab.env`, so Compose interpolates `${VAR}` from the environment — the same assumption the launch Makefiles make.

The **run** form adds `--env-file $AIRLAB_PATH/airlab.env`, because it must also work where that assumption does not hold. Run over `airlab exec`, ssh or ansible, the stock `~/.bashrc` early-returns and nothing exports `airlab.env`; without the flag `${ARCH}` resolves to empty and Compose fails looking for `launch/<block>/.env`.

For `${VAR}` interpolation the real environment still **wins** over `--env-file`, so `GATE_LANE=gate3 airlab compose up -d` overrides the file — it is a floor, not an override. What a *container* sees is separate: that comes from each service's `env_file:` (`base-service` loads `airlab.env` directly) and is unaffected by either.

Then edit it and run it:
- **zsh:** `print -z` pushes the line onto the editing buffer.
- **bash:** the command is injected into the readline buffer via the terminal Device-Status-Report trick (`bind '"\e[0n": …"'; printf '\e[5n'`).

A subprocess can't type into its parent shell's input buffer, which is why this lives in the shell function (like `airlab cd`). If the shell integration isn't sourced — or you run `command airlab compose` — it simply prints the command for you to copy.

## Notes
- Requires `AIRLAB_PATH` set and `$AIRLAB_PATH/airlab.env` present (populate it with `launch/deployer/deployer`).
- Errors clearly if `AIRLAB_COMPOSE_FILE` / `AIRLAB_COMPOSE_PROFILES` are unset, or the compose file is missing under `launch/`.
- **Local only** — it acts on the machine you're on; there is no remote path. To drive another machine, run it there: `airlab exec <robot> "airlab compose up -d"`.

## Examples
```bash
airlab compose                  # cd to launch/ and prefill the command; type `up -d` and run
airlab compose up -d            # bring this machine's stack up
airlab compose down             # take it down
airlab compose ps               # what's running
airlab compose logs -f reid     # follow one service
airlab compose --dry-run down   # see the exact command first
airlab compose --help
```
