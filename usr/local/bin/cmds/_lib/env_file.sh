#!/usr/bin/env bash
# Shared editing of KEY=VALUE environment files (airlab.env).
#
# Source this from a command:  source "$(dirname "$0")/_lib/env_file.sh"
#
#   env_file_set <file> <key> <value>
#
# Sets one key, replacing an existing line or appending a new one, and creating the
# file if it is missing. The value is carried through the environment and compared by
# prefix rather than by regex, so it is never interpreted: the previous
# `sed -i "s|^$KEY=.*|$KEY=$VALUE|"` broke on any value containing the `|` delimiter
# (`airlab set_env local 'FOO=a|b'` failed outright with "unknown option to `s'"),
# and `&` or a backslash in a value would have been rewritten silently.
#
# Where the old sed rewrote every duplicate line for a key, this keeps the first and
# drops the rest, so repeated keys collapse to one.

# Strip surrounding double quotes, but only when they are PAIRED.
#
# `airlab set_env local 'FOO="hello"'` is the documented form and yields `hello`. The
# strip used to be unconditional (`${v%\"}` then `${v#\"}`), so `FOO=say "hi"` lost
# its closing quote and `hi` was stored as `say "hi` — corrupted before the value ever
# reached the file.
strip_paired_quotes() {
    local value="$1"
    if [ "${#value}" -ge 2 ] && [ "${value#\"}" != "$value" ] && [ "${value%\"}" != "$value" ]; then
        value="${value#\"}"
        value="${value%\"}"
    fi
    printf '%s' "$value"
}

# Returns 1 on a value that cannot be represented on a single line.
env_file_set() {
    local file="$1" key="$2" value="$3"

    case "$value" in
        *$'\n'*)
            echo "[ERROR] refusing to write a multi-line value for $key" >&2
            return 1
            ;;
    esac

    local tmp
    tmp="$(mktemp "${file}.XXXXXX")" || return 1
    [ -f "$file" ] || : > "$file"

    if ! AIRLAB_ENV_KEY="$key" AIRLAB_ENV_VALUE="$value" awk '
        BEGIN { key = ENVIRON["AIRLAB_ENV_KEY"]; value = ENVIRON["AIRLAB_ENV_VALUE"];
                prefix = key "="; n = length(prefix) }
        substr($0, 1, n) == prefix { if (!done) { print prefix value; done = 1 } next }
        { print }
        END { if (!done) print prefix value }
    ' "$file" > "$tmp"; then
        rm -f "$tmp"
        return 1
    fi

    chmod --reference="$file" "$tmp" 2>/dev/null || true
    mv -f "$tmp" "$file"
}
