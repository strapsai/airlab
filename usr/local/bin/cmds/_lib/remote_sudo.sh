#!/usr/bin/env bash
# Shared helper: run a command under sudo on a remote host over SSH — correctly,
# whether SSH authenticated with a key or a password, and whether the robot's
# sudo is passwordless (NOPASSWD) or password-protected.
#
#   remote_sudo <ssh_target> "<remote command string>"
#
# It first probes `sudo -n true`: if the robot has NOPASSWD sudo, the command
# runs with no password (works for key-based SSH too). Otherwise it feeds a sudo
# password to `sudo -S` on stdin (never on the command line). The sudo password
# is taken from, in order:
#   1. $robot_password    — the SSH password, when password auth / --password was used
#   2. $AIRLAB_SUDO_PASSWORD (env) — for automation / CI
#   3. an interactive prompt (asked once per run, then cached)
#
# SSH transport uses the caller's SSHPASS_PREFIX array (empty for key-based SSH)
# and optional $SSH_PORT — matching how the airlab commands already invoke ssh.

_AIRLAB_SUDO_PW=""
_AIRLAB_SUDO_PW_CACHED=0

# Echo the sudo password to use; return 1 if none can be obtained.
_airlab_sudo_pw() {
    if [[ -n "${robot_password:-}" ]]; then printf '%s' "$robot_password"; return 0; fi
    if [[ -n "${AIRLAB_SUDO_PASSWORD:-}" ]]; then printf '%s' "$AIRLAB_SUDO_PASSWORD"; return 0; fi
    if [[ "$_AIRLAB_SUDO_PW_CACHED" == "1" ]]; then printf '%s' "$_AIRLAB_SUDO_PW"; return 0; fi
    # Prompt only if a controlling terminal is actually usable (fails cleanly in CI).
    if read -rs -p "[sudo] password for the remote host: " _AIRLAB_SUDO_PW < /dev/tty 2>/dev/null; then
        echo >&2
        _AIRLAB_SUDO_PW_CACHED=1
        printf '%s' "$_AIRLAB_SUDO_PW"
        return 0
    fi
    return 1
}

# Build the ssh command array the airlab commands use (SSHPASS_PREFIX may be unset).
_airlab_remote_ssh_cmd() {
    _AIRLAB_SSH=()
    [[ -n "${SSHPASS_PREFIX+x}" ]] && _AIRLAB_SSH+=("${SSHPASS_PREFIX[@]}")
    _AIRLAB_SSH+=(ssh -o StrictHostKeyChecking=no)
    [[ -n "${SSH_PORT:-}" ]] && _AIRLAB_SSH+=(-p "$SSH_PORT")
}

remote_sudo() {
    local target="$1"
    local cmd="$2"
    _airlab_remote_ssh_cmd

    # NOPASSWD? harmless probe (does not run the real command).
    if "${_AIRLAB_SSH[@]}" "$target" "sudo -n true" >/dev/null 2>&1; then
        "${_AIRLAB_SSH[@]}" "$target" "sudo -n $cmd"
        return $?
    fi

    # sudo needs a password.
    local pw
    if ! pw="$(_airlab_sudo_pw)"; then
        echo "[ERROR] remote sudo on $target needs a password; set AIRLAB_SUDO_PASSWORD" \
             "or run interactively." >&2
        return 1
    fi
    printf '%s\n' "$pw" | "${_AIRLAB_SSH[@]}" "$target" "sudo -S -p '' $cmd"
}
