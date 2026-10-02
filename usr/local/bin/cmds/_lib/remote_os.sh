#!/bin/bash
# What operating system is on the other end of an SSH connection?
#
# Source this from a command:  source "$(dirname "$0")/_lib/remote_os.sh"
#
# The fleet is mixed: Linux robots and basestations run this tool, `airlab`; Macs
# run its macOS edition, `airlab-mac` (strapsai/airlab-mac). Anything that installs
# the tool, or runs an OS-specific command on the far side, has to ask first rather
# than assume the far side looks like the operator's machine.
#
#   remote_os <ssh_target>        prints "linux" or "macos" (or "unknown:<uname>")
#   airlab_tool_for_os <os>       prints the tool that belongs on that OS
#   remote_cmd_for_os <os> <cmd>  wraps <cmd> so it finds Homebrew tools on a Mac
#
# SSH transport follows the other helpers: the caller's SSHPASS_PREFIX array (empty
# or unset for key-based SSH) and an optional $SSH_PORT.

# Map `uname -s` output to the names airlab uses.
airlab_normalize_os() {
    case "$1" in
        Linux)  printf 'linux' ;;
        Darwin) printf 'macos' ;;
        "")     return 1 ;;
        *)      printf 'unknown:%s' "$1" ;;
    esac
}

remote_os() {
    local target="$1" uname_s
    local ssh_cmd=()
    [ -n "${SSHPASS_PREFIX+x}" ] && ssh_cmd=(${SSHPASS_PREFIX[@]+"${SSHPASS_PREFIX[@]}"})
    ssh_cmd+=(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15)
    [ -n "${SSH_PORT:-}" ] && ssh_cmd+=(-p "$SSH_PORT")
    uname_s="$("${ssh_cmd[@]}" "$target" "uname -s" 2>/dev/null | tr -d '\r' | head -n 1)"
    airlab_normalize_os "$uname_s"
}

# The airlab tool that runs on a given OS. The name doubles as the GitHub repo name.
airlab_tool_for_os() {
    case "$1" in
        linux) printf 'airlab' ;;
        macos) printf 'airlab-mac' ;;
        *)     return 1 ;;
    esac
}

# Non-interactive SSH sessions on a Mac start with PATH=/usr/bin:/bin:/usr/sbin:/sbin,
# so Homebrew's tools (tmuxp, a real rsync) and the airlab launcher are invisible to a
# one-shot command. Prefix the command so it sees them. Linux targets are left as-is.
remote_cmd_for_os() {
    local os="$1" cmd="$2"
    if [ "$os" = "macos" ]; then
        printf '%s' 'PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/VENVs/airlab/bin:$PATH"; export PATH; '"$cmd"
    else
        printf '%s' "$cmd"
    fi
}

# rsync arguments that select the right rsync on the far side. A Mac's
# /usr/bin/rsync is openrsync, so point it at Homebrew's rsync when one is there
# (`env` rather than `VAR=value cmd`, so it works whatever the login shell is).
# Linux targets get nothing extra: their rsync is used exactly as before.
# Prints one argument per line; read it into an array.
remote_rsync_args_for_os() {
    if [ "$1" = "macos" ]; then
        printf '%s\n' '--rsync-path=env PATH="/opt/homebrew/bin:/usr/local/bin:$PATH" rsync'
    fi
}
