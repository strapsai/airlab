# upgrade

## Overview
The `airlab upgrade` command self-upgrades the airlab tool to the latest version: it downloads the current source from GitHub, removes the installed package, and reinstalls by running the freshly downloaded `install.sh`. `install.sh` runs **interactively**, so you answer its venv and `sudo` prompts at the keyboard.

## Syntax
```bash
airlab upgrade [--branch <branch>] [--yes] [-- <install.sh flags>...]
```

## Options
- `--branch <branch>`: Branch to install from (default: `main`).
- `-y`, `--yes`: Skip the confirmation prompt.
- `-- <flags>...`: Pass the remaining arguments through to `install.sh` (e.g. `-- --offline`).
- `-h`, `--help`: Display usage information.

## How It Works

### Source
The upgrade source repo is read from `/usr/share/airlab/install_source` (recorded at package-build time, default `strapsai/airlab`), so a fork upgrades from its own repo. The source is fetched as `https://github.com/<repo>/archive/refs/heads/<branch>.zip` — the same mechanism `airlab setup <robot>` uses to provision a robot.

### Self-deletion safety
`airlab upgrade` is itself a file inside the airlab package, so it cannot run `dpkg -r airlab` from its own script without risking bash reading a file that no longer exists. Instead it:

1. Downloads the fresh source to `/tmp/airlab-upgrade/` (this does **not** touch the installed package).
2. Writes a small remove+reinstall runner into `/tmp` and hands off to it with `exec`.
3. After the `exec`, the running process lives entirely in `/tmp` — independent of the package being removed — so `sudo dpkg -r airlab` followed by `bash install.sh` is safe. `exec` preserves the controlling terminal, so `install.sh` stays fully interactive.

## Examples
```bash
airlab upgrade                     # confirm, then upgrade from main (interactive install.sh)
airlab upgrade --yes               # no confirmation prompt
airlab upgrade --branch dev        # upgrade from the dev branch
airlab upgrade -- --offline        # reuse the existing venv / skip apt+pip during install
```

## Notes
- Requires `curl` and `unzip`.
- Run it as your normal user (not `sudo`) — `install.sh` uses `sudo` internally so its `~/VENVs` and `~/.bashrc` edits land in the right `$HOME`.
- If `install.sh` fails partway, airlab may be left uninstalled; the command prints the exact `install.sh` path in `/tmp` to re-run.
