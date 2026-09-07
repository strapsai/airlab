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
    # Probe in a subshell: a failed redirect there costs us nothing, whereas `exec`-ing
    # the redirect in this shell would kill a non-interactive caller outright.
    ( : < /dev/tty ) 2>/dev/null || return 1
    # The prompt goes to /dev/tty, NOT to stderr. Callers capture this function with
    # $(...) and may redirect stderr; a `read -p` prompt (which bash writes to stderr)
    # then vanishes and the operator is left staring at a silent hang, waiting on a
    # question they were never shown. /dev/tty cannot be redirected away by a caller.
    printf '[sudo] password for the remote host: ' > /dev/tty
    if IFS= read -rs _AIRLAB_SUDO_PW < /dev/tty; then
        printf '\n' > /dev/tty
        _AIRLAB_SUDO_PW_CACHED=1
        printf '%s' "$_AIRLAB_SUDO_PW"
        return 0
    fi
    printf '\n' > /dev/tty
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

# Prime sudo's timestamp inside a pty session the CALLER owns.
#
#   remote_sudo_prime <ssh_target> || die
#   ssh -tt <target> "$REMOTE_SUDO_PRIME_CMD && <the real work>"
#   remote_sudo_prime_cleanup <ssh_target>
#
# Some remote work (e.g. install.sh, which runs `sudo apt`/`sudo dpkg` internally)
# has to run under one `ssh -tt` pty so sudo's tty-keyed timestamp cache carries
# from the priming command into those inner sudo calls. remote_sudo can't do that
# — it owns its own connection — so this hands back a fragment to prepend instead,
# and stages anything that fragment needs on the remote host.
#
# Results come back in globals, NOT on stdout: the caller would have to capture
# stdout with $(...), and the cleanup path it needs to know about would then be set
# in a subshell and lost — leaking the staged askpass dir on the robot.
#   $REMOTE_SUDO_PRIME_CMD     — the fragment to prepend to the remote command
#   $REMOTE_SUDO_PRIME_CLEANUP — remote path to remove afterwards ("" if none)
REMOTE_SUDO_PRIME_CMD=""
REMOTE_SUDO_PRIME_CLEANUP=""

remote_sudo_prime() {
    local target="$1"
    REMOTE_SUDO_PRIME_CMD=""
    REMOTE_SUDO_PRIME_CLEANUP=""
    _airlab_remote_ssh_cmd

    # NOPASSWD sudo (every robot prepared by setup-robot-access.sh) needs no password
    # at all. Probe FIRST and never ask: an unconditional prompt here is a hang on a
    # question the operator has no reason to expect.
    if "${_AIRLAB_SSH[@]}" "$target" "sudo -n true" >/dev/null 2>&1; then
        REMOTE_SUDO_PRIME_CMD="sudo -n true"
        return 0
    fi

    local pw
    if ! pw="$(_airlab_sudo_pw)"; then
        echo "[ERROR] sudo on $target needs a password; set AIRLAB_SUDO_PASSWORD" \
             "or run interactively." >&2
        return 1
    fi

    # Password sudo: hand the secret over on the stdin of a NON-pty ssh session and
    # let the robot write it to a 0600 askpass helper, which the caller's pty session
    # then reads via `sudo -A`. The two obvious shortcuts are both wrong:
    #   - interpolating the password into a remote command string breaks on quote
    #     characters and exposes it in `ps` to every user on the robot;
    #   - piping it into the `ssh -tt` session echoes it straight back onto the
    #     operator's screen, because the remote pty has ECHO on before the remote
    #     shell ever reaches its `read`.
    local staged
    staged="$(printf '%s' "$pw" | "${_AIRLAB_SSH[@]}" "$target" \
        'umask 077; d=$(mktemp -d -t airlab-askpass.XXXXXX) || exit 1;
         cat > "$d/pw" || exit 1;
         printf "#!/bin/sh\ncat -- \"%s\"\n" "$d/pw" > "$d/askpass" || exit 1;
         chmod 700 "$d/askpass" || exit 1;
         printf "%s" "$d"')" || return 1
    [[ -n "$staged" ]] || return 1

    REMOTE_SUDO_PRIME_CLEANUP="$staged"
    REMOTE_SUDO_PRIME_CMD="SUDO_ASKPASS=$staged/askpass sudo -A true"
}

# Remove whatever remote_sudo_prime staged on the remote host. No-op when the
# NOPASSWD path was taken. Safe to call unconditionally, including on failure.
remote_sudo_prime_cleanup() {
    local target="$1"
    [[ -n "$REMOTE_SUDO_PRIME_CLEANUP" ]] || return 0
    local staged="$REMOTE_SUDO_PRIME_CLEANUP"
    REMOTE_SUDO_PRIME_CLEANUP=""
    _airlab_remote_ssh_cmd
    "${_AIRLAB_SSH[@]}" "$target" "rm -rf -- '$staged'" >/dev/null 2>&1
}
