#!/bin/bash

# Parse command line arguments.
SKIP_APT=false
SKIP_PIP=false
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
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--skip-apt] [--skip-pip]"
            exit 1
            ;;
    esac
done

# Check if running under a Python virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Error: This script must be run from within a Python virtual environment."
    echo "Please activate a virtual environment first:"
    echo "  python3 -m venv /path/to/venv"
    echo "  source /path/to/venv/bin/activate"
    exit 1
fi

# Print virtual environment information
echo "Virtual environment detected:"
echo "  Name: $(basename "$VIRTUAL_ENV")"
echo "  Location: $VIRTUAL_ENV"
echo ""

# Install Ubuntu dependencies.
if [ "$SKIP_APT" = true ]; then
    echo "Skipping apt-get install (--skip-apt)."
else
    sudo apt-get install -y \
        curl unzip dpkg-dev git lsb-release openssh-server rsync sshpass tmux tmuxp
fi

# With the Python venv.
if [ "$SKIP_PIP" = true ]; then
    echo "Skipping pip install (--skip-pip)."
else
    pip install pyyaml vcstool "setuptools<=81.0.0"
fi

echo "Done."
