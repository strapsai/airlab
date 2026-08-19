# Zsh shell function wrapper for airlab.
# Sourced from ~/.zshrc to enable "airlab cd" (which must run in the current shell).
#
# Installed to /etc/airlab/airlab.zsh

airlab() {
    if [[ "${1:-}" == "cd" ]]; then
        shift
        local target="${AIRLAB_PATH:-}"
        if [[ -z "$target" ]]; then
            echo "Error: AIRLAB_PATH is not set. Run 'airlab setup local' first." >&2
            return 1
        fi
        if [[ "$1" == "--help" || "$1" == "-h" ]]; then
            echo "Usage: airlab cd [path]"
            echo ""
            echo "Change directory to a path relative to \$AIRLAB_PATH ($AIRLAB_PATH)."
            echo ""
            echo "  airlab cd              # cd to \$AIRLAB_PATH"
            echo "  airlab cd docker       # cd to \$AIRLAB_PATH/docker"
            echo "  airlab cd robot        # cd to \$AIRLAB_PATH/robot"
            return 0
        fi
        if [[ -n "$1" ]]; then
            target="$target/$1"
        fi
        builtin cd "$target"
    elif [[ "${1:-}" == "compose" ]]; then
        # Bare `airlab compose` prefills the command onto the prompt (must run in the
        # current shell — a subprocess can't inject into the parent's input buffer).
        # With arguments it is a normal command that RUNS Compose, so hand it straight
        # over: prefilling `airlab compose up -d` would be the wrong thing entirely.
        shift
        if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
            command airlab compose --help
            return 0
        fi
        if [[ $# -gt 0 ]]; then
            command airlab compose "$@"
            return $?
        fi
        local _cmd
        _cmd="$(command airlab compose --emit)" || return $?
        [[ -n "${AIRLAB_PATH:-}" ]] && builtin cd "${AIRLAB_PATH}/launch" 2>/dev/null
        if [[ -o interactive ]]; then
            print -z "$_cmd"     # push onto the editing buffer: appears editable at the next prompt
        else
            print -r -- "$_cmd"
        fi
    else
        command airlab "$@"
    fi
}
