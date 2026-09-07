# Airlab - Claude Code Context

## Project Overview

`airlab` is a Bash-based CLI tool for deploying and managing robotic systems. It is packaged as a `.deb` and installs to `/usr/local/bin/`. The tool wraps `rsync`, `ssh`, `docker`, `tmux`, and `vcs` (vcstool) under a unified interface.

## Repository Structure

```
usr/local/bin/
  airlab                          # Main entrypoint (case dispatcher)
  cmds/
    alias                         # Run user-defined alias scripts ("airlab a"); resolves
                                  #   $AIRLAB_ALIAS_PATH, lists/lints/scaffolds aliases
    ssh                           # SSH into a robot
    ping                          # Ping a robot
    auth                          # Install SSH public key on a robot
    robot-sync                    # Sync files via rsync
    robot-setup                   # Setup local/remote environment
    robot-launch                  # Launch tmux sessions
    docker-build                  # Build Docker images
    docker-up                     # Start Docker containers
    docker-join                   # Attach to running containers
    docker-list                   # List Docker containers/images
    env                           # Inspect/sync environment variables
    hosts                         # Manage the /etc/hosts section from robots.yaml
                                  #   (set/compare/remove; set_hosts is a deprecated shim)
                                  #   (show/compare/sync-from/sync-to/set)
    _lib/
      resolve.sh                  # Shared SSH-address resolution via robots.yaml
      remote_sudo.sh              # Remote sudo over SSH (key/password × NOPASSWD/password)
      robot_info.py               # Sole owner of robot_info.yaml's format (read/write/env)
      robot_info.sh               # bash wrappers: update_robot_info / read_env_from_yaml
      env_file.sh                 # Safe KEY=VALUE editing of airlab.env
    version-control/
      vcs                         # VCS sub-command dispatcher
      init                        # Clone repos from YAML (--here, --check, --from-scratch)
      pull                        # Pull repos
      push                        # Push repos
      status                      # Status with branch/remote/dirty/submodule checks
      update                      # Pull + init missing + pull again with summary
usr/share/zsh/vendor-completions/
  _airlab                         # Zsh completion function (auto-discovered via fpath)
usr/share/airlab/alias-templates/
  alias.sh, alias.py              # Templates for "airlab a --new" (with @desc/@author/--help)
etc/airlab/                       # Default config templates (copied to workspace on setup)
  airlab.zsh                      # Zsh shell function wrapper (sourced from ~/.zshrc)
  robot/robots.yaml               # Robot registry: systems + network addresses (SSH resolution)
  robot/robot_info.yaml           # Robot metadata (YAML)
  version_control/repos.yaml      # Repository definitions for vcstool
etc/bash_completion.d/
  airlab                          # Bash completion + shell function wrapper
```

## Key Conventions

- **Commands are mostly standalone Bash scripts**: each defines its own utility functions (`log_info`, `log_warn`, `log_error`, `parse_yaml`, `ssh_authenticate`, etc.). The few genuinely shared helpers live in `cmds/_lib/` and are `source`d by the commands that need them (`resolve.sh`, `remote_sudo.sh`, `robot_info.sh`, `env_file.sh`).
- **SSH authentication pattern**: Every SSH-using command has an `ssh_authenticate()` function that tries key-based SSH first (`BatchMode=yes`), falls back to password via `sshpass`. The result is stored in the global `robot_password` variable. Callers must NOT declare `local robot_password` before calling `ssh_authenticate` — use `robot_password=""` instead.
- **SSHPASS_PREFIX pattern**: After `ssh_authenticate`, commands set up `SSHPASS_PREFIX=()` (empty for key-based) or `SSHPASS_PREFIX=(sshpass -p "$robot_password")`. All SSH/rsync/scp calls use `"${SSHPASS_PREFIX[@]}"` as a prefix.
- **`--password` flag**: All SSH-using commands accept `--password` to skip key-based auth and prompt directly.
- **Remote sudo**: always elevate through `_lib/remote_sudo.sh` — `remote_sudo` for a one-off command, or `remote_sudo_prime` when the caller needs its own `ssh -tt` pty so sudo's tty-keyed timestamp carries into a script's internal sudo calls (that's what `airlab setup <robot>` does for `install.sh`). Both probe `sudo -n true` first, so a NOPASSWD robot is never asked for a password it doesn't need. **Never interpolate a sudo password into a remote command string** (`ssh host "echo $pw | sudo -S ..."`): quote characters break the command and `ps` exposes the password to every user on the robot. **Never pipe it into an `ssh -tt` session either** — the remote pty echoes it onto the operator's screen. Feed it on the stdin of a non-pty session (`remote_sudo`) or via a staged 0600 `SUDO_ASKPASS` helper (`remote_sudo_prime`).
- **Interactive prompts**: `_airlab_sudo_pw` writes its prompt to `/dev/tty`, not stderr, because callers capture it with `$(...)`. Any prompt a caller might redirect away has to do the same, or it becomes a silent hang on an invisible question.
- **YAML parsing**: Done via inline `python3 -c "import yaml; ..."` calls. PyYAML is a dependency.
- **`airlab env`**: the one place that moves environment variables between a machine's `airlab.env` and the operator-side `robot_info.yaml` record (`show` / `compare` / `sync-from` / `sync-to` / `set`). It reads `airlab.env` as **text and never sources it**, so shell literals like `${SUDO_USER:-$USER}` round-trip instead of freezing one host's expansion into the shared record. Replaced `airlab set_env`, whose dispatcher arm now just points at `airlab env set`.
- **`robot_info.yaml`**: system names sit at the **top level** — there is no `robots:` root key, and readers look fields up as `<system>.<field>`. `ws_path`, `robot_ssh` and `last_updated` are bookkeeping, not environment variables, and are excluded when regenerating a machine's `airlab.env`. All access goes through `_lib/robot_info.sh`; do not re-add a second writer.
- **Never edit config files with `sed -i "s|...|$value|"`**: the value lands in the replacement text, so `|` aborts the command and `&` or a backslash is silently rewritten. Use `env_file_set` for `airlab.env` and `update_robot_info` for `robot_info.yaml` — both compare by prefix/key and pass the value as data.
- **AIRLAB_REPO_FILE**: A marker file placed in repo directories by `vcs init`. Contains the YAML filename used for initialization. Used by `--here`, `--check`, `--from-scratch`, `vcs status`, and `vcs update`.
- **Config path**: `$AIRLAB_PATH` env var points to the workspace root (set in `~/.bashrc` or `~/.zshrc` during `sudo airlab setup local`).
- **Setup privileges**: `airlab setup local` provisions the machine system-wide and **must run as root** (`sudo airlab setup local`) — the root check lives in the `local)` arm of `robot-setup`'s `main()`. `airlab setup <robot>` runs as the **invoking user** (its local git/rsync use that user's repo + SSH keys) and elevates **only on the robot** via `_lib/remote_sudo.sh`, so it needs no local root. The robot-side sudo password comes from `--password` → `$AIRLAB_SUDO_PASSWORD` → prompt.
- **Shell support**: Both Bash and Zsh are supported. Bash completion uses the traditional `complete -F` API in `etc/bash_completion.d/airlab`. Zsh completion uses `_arguments` in `usr/share/zsh/vendor-completions/_airlab`. The `airlab cd` shell function is defined in both completion files (Bash) and `etc/airlab/airlab.zsh` (Zsh). The install script configures `~/.zshrc` when zsh is detected.

## Testing

To test without building a .deb, run scripts directly from the repo:
```bash
./usr/local/bin/cmds/ssh mt001
./usr/local/bin/cmds/robot-sync mt001 --dry-run
```
The scripts only depend on `$AIRLAB_PATH` being set (from an existing install).

## Known Issues

- `robot-launch` uses `error_exit()` which is not defined in that file (should be `log_error` + `exit 1`).
- `docker-join` default `CONTAINER_NAME` is `"docker-compose.yml"` which is a filename, not a container name.
- `robot-sync` port extraction logic (lines ~303-311) is fragile for addresses with ports.

## Build & Install

```bash
# Build .deb
sudo dpkg-deb --build /path/to/airlab
# Install
sudo dpkg -i airlab.deb
# Install dependencies
./install_dependencies_ubuntu24.sh
```
