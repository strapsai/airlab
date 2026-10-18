# upgrade

## Overview
The `airlab upgrade` command self-upgrades the airlab tool to the latest version: it downloads the current source from GitHub, removes the installed package, and reinstalls by running the freshly downloaded `install.sh`. `install.sh` runs **interactively**, so you answer its venv and `sudo` prompts at the keyboard.

## Syntax
```bash
airlab upgrade [--branch <branch>] [--yes] [-- <install.sh flags>...]
```

## Options
- `--branch <branch>`: Branch to install from (default: `main`).
- `-y`, `--yes`: Skip the confirmation prompt. Required for a non-interactive run.
- `-- <flags>...`: Pass everything after `--` through to `install.sh` (e.g. `-- --keep-venv`, `-- --offline`). `airlab upgrade`'s own options go **before** the `--`.
- `-h`, `--help`: Display usage information.

## Passing flags to install.sh
Everything after a literal `--` is handed to the downloaded `install.sh` unchanged (each argument quoted as one word):

```bash
airlab upgrade -- --keep-venv                  # keep ~/VENVs/airlab, no venv prompt; still pip install/upgrade into it
airlab upgrade --yes -- --keep-venv            # same, and no confirmation prompt either
airlab upgrade --branch dev --yes -- --keep-venv
airlab upgrade -- --offline                    # no network: skip apt + pip, reuse the venv as-is
airlab upgrade -- --override-venv              # re-create the venv without asking
```

`--keep-venv` is the non-interactive form of answering **N** to install.sh's "Remove and re-create it?" prompt. Run `bash install.sh --help` in a checkout for the full flag list.

## Exit status
- `0` — upgraded.
- `1` — aborted (prompt declined, or no answer because stdin is not a terminal and `--yes` was not given), or any failure. A declined upgrade is **not** reported as success.
- Otherwise `install.sh`'s own exit code when it fails during the reinstall.

## How It Works

### Source
The upgrade source repo is read from `/usr/share/airlab/install_source` (recorded at package-build time, default `strapsai/airlab`), so a fork upgrades from its own repo. The source is fetched as `https://github.com/<repo>/archive/refs/heads/<branch>.zip` — the same mechanism `airlab setup <robot>` uses to provision a robot.

### Self-deletion safety
`airlab upgrade` is itself a file inside the airlab package, so it cannot run `dpkg -r airlab` from its own script without risking bash reading a file that no longer exists. Instead it:

1. Downloads the fresh source to `/tmp/airlab-upgrade/` (this does **not** touch the installed package).
2. Writes a small remove+reinstall runner into `/tmp` and hands off to it with `exec`.
3. Before handing off — while the installed package is still untouched — it checks the downloaded `install.sh`: it must exist, pass `bash -n`, and pass `install.sh --check <your flags>` (argument parsing plus venv preconditions such as "`--offline` needs an existing venv"). Any failure aborts with exit 1 and **nothing removed**.
4. After the `exec`, the running process lives entirely in `/tmp` — independent of the package being removed — so `sudo dpkg -r airlab` followed by `bash install.sh` is safe. `exec` preserves the controlling terminal, so `install.sh` stays fully interactive.

## Examples
```bash
airlab upgrade                     # confirm, then upgrade from main (interactive install.sh)
airlab upgrade --yes               # no confirmation prompt
airlab upgrade --branch dev        # upgrade from the dev branch
airlab upgrade -- --offline        # reuse the existing venv / skip apt+pip during install
airlab upgrade -- --keep-venv      # keep the venv without being asked; deps still upgraded
```

## Notes
- Requires `curl` and `unzip`.
- Run it as your normal user (not `sudo`) — `install.sh` uses `sudo` internally so its `~/VENVs` and `~/.bashrc` edits land in the right `$HOME`.
- If `install.sh` fails after the package was removed, the runner prints a loud banner saying airlab is **currently uninstalled**, with the exact command to reinstall from the unpacked source, e.g. `cd /tmp/airlab-upgrade/airlab-main && bash /tmp/airlab-upgrade/airlab-main/install.sh --keep-venv`. It lives in `/tmp`, so run it before a reboot.
- `install.sh`'s venv prompt treats a closed stdin as the default answer (keep), so it no longer aborts the reinstall when there is no terminal to answer it.
