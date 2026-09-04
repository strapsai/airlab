#!/bin/bash

# Parse command line arguments.
SKIP_APT=false
SKIP_PIP=false
NO_VENV=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-apt)
            SKIP_APT=true
            shift
            ;;
        --skip-pip)
            # Skip the pip installs below. Used by offline installs, where the
            # venv (and its packages) already exist from a prior online setup.
            SKIP_PIP=true
            shift
            ;;
        --no-venv)
            # Venv-free install (install.sh --no-venv): drop the active-venv
            # requirement and install the Python dependencies to the user site.
            NO_VENV=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--skip-apt] [--skip-pip] [--no-venv]"
            exit 1
            ;;
    esac
done

# Check if running under a Python virtual environment.
#
# --no-venv waives this deliberately. The airlab CLI is a bash dispatcher installed
# as a system .deb; the venv only ever held its Python dependencies, so a venv-free
# install is a supported shape rather than a broken one. See install.sh --no-venv.
if [ "$NO_VENV" = true ]; then
    echo "No virtual environment (--no-venv); Python dependencies go to the user site."
    echo ""
elif [ -z "$VIRTUAL_ENV" ]; then
    echo "Error: This script must be run from within a Python virtual environment."
    echo "Please activate a virtual environment first:"
    echo "  python3 -m venv /path/to/venv"
    echo "  source /path/to/venv/bin/activate"
    echo ""
    echo "Or install without one:  ./install.sh --no-venv"
    exit 1
else
    # Print virtual environment information
    echo "Virtual environment detected:"
    echo "  Name: $(basename "$VIRTUAL_ENV")"
    echo "  Location: $VIRTUAL_ENV"
    echo ""
fi

# Install Ubuntu dependencies.
if [ "$SKIP_APT" = true ]; then
    echo "Skipping apt-get install (--skip-apt)."
else
    sudo apt-get install -y \
        curl unzip dpkg-dev git lsb-release openssh-server rsync sshpass tmux tmuxp
fi

# Python dependencies. Into the venv when there is one, into the user site when
# there is not (--user is a no-op inside a venv, so it is only used for --no-venv).
if [ "$SKIP_PIP" = true ]; then
    echo "Skipping pip install (--skip-pip)."
elif [ "$NO_VENV" = true ]; then
    # Without a venv the two package managers have to share the work, because modern
    # Ubuntu marks the system Python "externally managed" (PEP 668) and refuses
    # `pip install --user` outright. Bionic-era targets — the VOXL case this mode
    # exists for — have no such restriction, so pip still does the rest there.
    #
    # PyYAML is the load-bearing dependency, so prefer the distro package for it.
    # python3-setuptools comes along because an old pip (bionic ships 9.0.1) builds
    # sdists with setup.py and fails outright without it.
    if [ "$SKIP_APT" = true ]; then
        python3 -c "import yaml" 2>/dev/null || echo "PyYAML missing and --skip-apt given; not installing it."
    else
        echo "Installing PyYAML and setuptools from apt (python3-yaml, python3-setuptools)."
        sudo apt-get install -y python3-yaml python3-setuptools || true
    fi
    # vcstool has no distro package, so it is pip-only and best-effort. Both common
    # failures are environmental rather than fixable here — Ubuntu 23.04+ marks the
    # system Python externally managed (PEP 668) and refuses --user outright, while
    # bionic's pip 9 tries to build a modern PyYAML sdist and gives up. Neither is
    # worth failing the install over: `airlab vcs` is the only affected subcommand,
    # and a robot never runs it (source arrives by `airlab sync` from the operator).
    if ! python3 -m pip install --user vcstool "setuptools<=81.0.0"; then
        echo ""
        echo "Note: 'pip install --user vcstool' did not succeed (see the pip output above)."
        echo "      Only 'airlab vcs' needs it — every other airlab command works without."
        echo "      If you do need it, install it with pipx or into a venv of your own."
    fi
else
    pip install pyyaml vcstool "setuptools<=81.0.0"
fi

# Verify what the tool actually needs at runtime, rather than assuming the install
# above covered it — with --skip-pip nothing was installed at all, and on a venv-free
# target the dependency may already be satisfied by a distro package.
#
# PyYAML is load-bearing: `robot-launch`, `robot-sync`, `docker-build`, `docker-list`
# and _lib/robot_info.py all use it, and several probe for it with
# `python3 -c "import yaml"` before doing anything. vcstool is needed only by
# `airlab vcs`, so its absence is a warning, not an error.
if python3 -c "import yaml" 2>/dev/null; then
    echo "PyYAML: OK"
else
    echo "WARNING: python3 cannot import yaml. Commands that read YAML (robot-launch," >&2
    echo "         robot-sync, docker-build, docker-list) will refuse to run. Install it" >&2
    echo "         with 'sudo apt install python3-yaml' or 'python3 -m pip install --user pyyaml'." >&2
fi
if ! python3 -c "import vcstool" 2>/dev/null; then
    echo "Note: vcstool is not importable — 'airlab vcs' will not work. Everything else will."
fi

echo "Done."
