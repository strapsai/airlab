#!/usr/bin/env bash
# Shared SSH-address resolution for airlab commands.
#
# Source this from a command:  source "$(dirname "$0")/_lib/resolve.sh"
# Requires AIRLAB_PATH to be set.
#
# resolve_ssh_address <system> [address_name]
#   Resolves against the target registry (robots.yaml via robots.py, which supports
#   named addresses like internet/vpn). Prints the ssh target, or nothing if the
#   system/address is unknown (or the registry is absent):
#     no port -> user@host        w/ port -> ssh://user@host:port
resolve_ssh_address() {
    local name="$1" address="${2:-}"
    local robots_py="$AIRLAB_PATH/robot/robots.py"
    [[ -f "$robots_py" ]] || return 0
    if [[ -n "$address" ]]; then
        python3 "$robots_py" resolve "$name" --address "$address" 2>/dev/null
    else
        python3 "$robots_py" resolve "$name" 2>/dev/null
    fi
}
