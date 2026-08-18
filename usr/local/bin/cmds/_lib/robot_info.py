#!/usr/bin/env python3
"""Sole owner of `$AIRLAB_PATH/robot/robot_info.yaml`.

That file is the operator-side record of each machine's environment: one entry per
system, holding the variables that machine's `airlab.env` should contain plus the
bookkeeping needed to reach it.

CANONICAL FORMAT — a top-level mapping of system name -> mapping of field -> value:

      spot1-phys:
        ROS_DOMAIN_ID: "10"
        ws_path: "/home/dtc/airlab_ws"
        last_updated: "2026-04-02 10:29:04"

There is deliberately **no `robots:` root key**. Every reader in the tool looks a
field up as `<system>.<field>` at the top level, and the deployed file has always
been written this way; only the old file-creation path disagreed, seeding `robots:`
into a fresh file that every reader then failed on. A legacy `robots:`-rooted file
is detected and reported rather than silently half-read.

Three fields are BOOKKEEPING, not environment variables: `ws_path`, `robot_ssh` and
`last_updated`. They live in the same mapping for convenience but are never written
into a machine's `airlab.env` (`env` below excludes them).

Writes are read-modify-write through PyYAML and re-emitted in the file's existing
style, so a value containing quotes, backslashes or `|` round-trips intact — the
previous `sed -i "s|...|...|"` implementation corrupted the file on those. Writes
land atomically via a temp file + rename.

Usage:
  robot_info.py get     <file> <system> <field>
  robot_info.py set     <file> <system> <field> <value> [--no-overwrite]
  robot_info.py env     <file> <system>
  robot_info.py systems <file>
"""
import json
import os
import sys
import tempfile
from datetime import datetime

try:
    import yaml
except ImportError:
    sys.stderr.write("robot_info.py: PyYAML not found. Install: pip3 install PyYAML\n")
    sys.exit(2)

# Fields that live in robot_info.yaml but are NOT environment variables.
BOOKKEEPING = ("ws_path", "robot_ssh", "last_updated")

INDENT_SYSTEM = "  "
INDENT_FIELD = "    "


def die(msg):
    sys.stderr.write("robot_info.py: %s\n" % msg)
    sys.exit(1)


def load(path):
    """Parse the registry. Missing or empty file -> {}."""
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        die("%s: expected a mapping of system -> fields, got %s"
            % (path, type(data).__name__))
    # Legacy shape: everything nested under a single `robots:` key. Readers look at
    # the top level, so half-reading this would silently return empty values.
    if list(data) == ["robots"] and isinstance(data["robots"], dict):
        die("%s is in the legacy `robots:`-rooted format. The canonical format has "
            "system names at the top level; remove the `robots:` line and de-indent "
            "the entries by two spaces." % path)
    return data


def emit(data):
    """Render the registry in the file's established style: system keys indented by
    two, fields by four, every value a double-quoted scalar."""
    lines = []
    for system, fields in data.items():
        lines.append("%s%s:" % (INDENT_SYSTEM, system))
        if not isinstance(fields, dict):
            die("system %r: expected a mapping of field -> value" % system)
        for key, value in fields.items():
            # json.dumps produces a valid YAML double-quoted scalar: it escapes the
            # quote, the backslash and control characters, and leaves `|`, `$`, `#`
            # and friends alone (they are literal inside double quotes).
            lines.append("%s%s: %s" % (INDENT_FIELD, key, json.dumps(str(value))))
    return "\n".join(lines) + "\n"


def save(path, data):
    """Write atomically, so an interrupted run can't leave a truncated registry."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    if not os.path.isdir(directory):
        die("directory does not exist: %s" % directory)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".robot_info.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(emit(data))
        if os.path.exists(path):                      # keep the original mode
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def set_field(data, system, field, value, no_overwrite=False):
    """Set one field. Returns the value now in effect (which is the pre-existing one
    when --no-overwrite held a value in place)."""
    entry = data.setdefault(system, {})
    existing = entry.get(field)
    if no_overwrite and existing not in (None, ""):
        value = str(existing)                         # hold the existing value
    else:
        entry[field] = str(value)                     # existing key keeps its position
    # `last_updated` always trails the entry, however the field was added.
    entry.pop("last_updated", None)
    entry["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def main(argv):
    if len(argv) < 3:
        sys.stderr.write(__doc__)
        return 2
    cmd, path = argv[1], argv[2]

    if cmd == "systems":
        for system in load(path):
            print(system)
        return 0

    if len(argv) < 4:
        sys.stderr.write(__doc__)
        return 2
    system = argv[3]

    if cmd == "get":
        if len(argv) < 5:
            sys.stderr.write(__doc__)
            return 2
        entry = load(path).get(system)
        if not isinstance(entry, dict) or argv[4] not in entry:
            return 1                                  # absent: quiet, non-zero
        print(entry[argv[4]])
        return 0

    if cmd == "env":
        entry = load(path).get(system)
        if not isinstance(entry, dict):
            die("no entry for system %r in %s" % (system, path))
        wrote = False
        for key, value in entry.items():
            if key in BOOKKEEPING:
                continue
            print("%s=%s" % (key, value))
            wrote = True
        return 0 if wrote else 1

    if cmd == "set":
        if len(argv) < 6:
            sys.stderr.write(__doc__)
            return 2
        field, value = argv[4], argv[5]
        no_overwrite = "--no-overwrite" in argv[6:]
        data = load(path)
        effective = set_field(data, system, field, value, no_overwrite)
        save(path, data)
        print(effective)
        return 0

    die("unknown command %r" % cmd)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
