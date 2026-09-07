#!/usr/bin/env bash
# Shared access to $AIRLAB_PATH/robot/robot_info.yaml.
#
# Source this from a command:  source "$(dirname "$0")/_lib/robot_info.sh"
#
# The file format is owned by _lib/robot_info.py — see its docstring. These are thin
# bash wrappers so the commands keep the call shape they already used. There is one
# implementation now: `robot-setup` and `set_env` each carried their own copy of
# update_robot_info, built out of line-anchored `sed`, and the two had already
# drifted apart.
#
#   update_robot_info  <ws_root> <system> <field> <value> [--no-overwrite] [return_var]
#   read_env_from_yaml <yaml_file> <system> <output_file>
#   robot_info_get     <yaml_file> <system> <field>
#
# `log_info` / `log_warn` / `log_error` are expected from the sourcing command.

_ROBOT_INFO_PY="$(dirname "${BASH_SOURCE[0]}")/robot_info.py"

# Path of the registry inside a workspace root.
robot_info_path() { printf '%s/robot/robot_info.yaml' "${1%/}"; }

# Read one field. Prints the value; returns non-zero (silently) when absent.
robot_info_get() {
    python3 "$_ROBOT_INFO_PY" get "$1" "$2" "$3"
}

# True when <yaml_file> has an entry for <system>. Absent or empty file -> false.
robot_info_has() {
    local file="$1" system="$2"
    [ -f "$file" ] || return 1
    python3 "$_ROBOT_INFO_PY" systems "$file" 2>/dev/null \
        | grep -Fxq -- "$system"
}

# Set one field on a system, creating the file or the entry as needed.
#
# <ws_root> is the WORKSPACE root — the registry beneath it is resolved here, which
# is the shape both callers already used. With --no-overwrite an existing non-empty
# value is kept; `return_var`, when given, receives the value now in effect (so the
# caller sees the kept value, not the one it proposed).
update_robot_info() {
    local ws_root="$1" system="$2" field="$3" value="$4"
    local no_overwrite="${5:-}" return_var="${6:-}"

    local file; file="$(robot_info_path "$ws_root")"
    local args=(set "$file" "$system" "$field" "$value")
    [ "$no_overwrite" = "--no-overwrite" ] && args+=(--no-overwrite)

    local effective
    if ! effective="$(python3 "$_ROBOT_INFO_PY" "${args[@]}")"; then
        log_error "Failed to update $system $field in $file"
        return 1
    fi

    if [ "$no_overwrite" = "--no-overwrite" ] && [ "$effective" != "$value" ]; then
        log_warn "Kept existing $system $field (--no-overwrite): $effective"
    fi
    # printf, not eval: the value is arbitrary text and must not be re-parsed.
    [ -n "$return_var" ] && printf -v "$return_var" '%s' "$effective"
    log_info "Updated robot $system $field in $file"
    return 0
}

# Write a system's ENVIRONMENT variables to <output_file> as KEY=VALUE lines.
#
# Only environment variables: `ws_path`, `robot_ssh` and `last_updated` are
# bookkeeping and are excluded by name. The previous implementation trimmed the tail
# of the entry positionally (two blind `sed '$d'`), so what it emitted depended on
# where the system sat in the file — `robot_ssh` leaked into airlab.env for every
# entry except the last one, and a field added after `last_updated` would have been
# swallowed instead.
read_env_from_yaml() {
    local yaml_file="$1" system="$2" output_file="$3"

    if [ ! -f "$yaml_file" ]; then
        log_error "YAML file not found at $yaml_file"
        return 1
    fi
    if ! python3 "$_ROBOT_INFO_PY" env "$yaml_file" "$system" > "$output_file"; then
        log_error "No environment variables found for $system in $yaml_file"
        return 1
    fi
    log_info "Environment variables for $system have been extracted to $output_file:"
    cat "$output_file"
}
