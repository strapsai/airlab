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

Values are stored VERBATIM. A machine's airlab.env legitimately holds shell literals
(`USER_NAME=${SUDO_USER:-$USER}`, `GROUP_NAME=$(id -gn)`), and nothing here ever
evaluates them — the env file is read as text, never sourced — so a literal survives
a round trip through the registry unchanged.

Usage:
  robot_info.py get     <file> <system> <field>
  robot_info.py set     <file> <system> <field> <value> [--no-overwrite]
  robot_info.py env     <file> <system>
  robot_info.py systems <file>
  robot_info.py envdiff <file> <system> <env_file>
  robot_info.py import  <file> <system> <env_file> [--prune] [--dry-run]
"""
import json
import os
import re
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


ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def parse_env_file(path):
    """Parse a KEY=VALUE env file into an ordered dict, values VERBATIM.

    Read as text and never sourced, so `${SUDO_USER:-$USER}` is preserved as written
    instead of collapsing to whatever it happens to expand to here. Later duplicates
    win, matching what sourcing the file would leave in the environment.
    """
    if not os.path.exists(path):
        die("env file not found: %s" % path)
    out = {}
    with open(path, "r") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            m = ENV_LINE.match(line)
            if m:
                out[m.group(1)] = m.group(2)
    return out


def looks_like_shell(value):
    """A value carrying `$` or backticks is a shell literal, not a settled string.

    Worth flagging in a diff: the registry usually records what such a literal
    RESOLVED to on the machine, so `dtc` vs `${SUDO_USER:-$USER}` is a difference in
    representation rather than real drift.
    """
    return "$" in value or "`" in value


def envdiff(path, system, env_path):
    """Compare the registry's record for <system> against an env file.

    Returns (only_record, only_env, differing, agreeing) — differing entries are
    (key, record_value, env_value).
    """
    entry = load(path).get(system)
    if not isinstance(entry, dict):
        die("no entry for system %r in %s" % (system, path))
    record = {k: str(v) for k, v in entry.items() if k not in BOOKKEEPING}
    env = parse_env_file(env_path)

    only_record = [k for k in record if k not in env]
    only_env = [k for k in env if k not in record]
    differing, agreeing = [], []
    for key, value in record.items():
        if key not in env:
            continue
        if env[key] == value:
            agreeing.append(key)
        else:
            differing.append((key, value, env[key]))
    return only_record, only_env, differing, agreeing


def render_envdiff(system, record_label, env_label, result):
    """Print the comparison. Returns True when the two sides agree."""
    only_record, only_env, differing, agreeing = result
    print("system: %s" % system)
    print("  %-14s %s" % ("record:", record_label))
    print("  %-14s %s" % ("live env:", env_label))
    print("")

    if differing:
        print("DIFFERENT (%d):" % len(differing))
        for key, rec, env in differing:
            note = "   # shell literal — the record holds a resolved value" \
                if looks_like_shell(env) and not looks_like_shell(rec) else ""
            print("  %s%s" % (key, note))
            print("      record: %s" % rec)
            print("      env:    %s" % env)
        print("")
    if only_record:
        print("ONLY IN THE RECORD (%d) — missing from the env file:" % len(only_record))
        for key in only_record:
            print("  %s" % key)
        print("")
    if only_env:
        print("ONLY IN THE ENV FILE (%d) — not recorded:" % len(only_env))
        for key in only_env:
            # These three are bookkeeping. Finding them as live environment variables
            # means the machine was provisioned by a version whose env extraction
            # trimmed the entry positionally and let them through; they do nothing on
            # the machine. `sync-to --prune` clears them.
            note = "   # bookkeeping leaked by an older provision — harmless, " \
                   "clear with sync-to --prune" if key in BOOKKEEPING else ""
            print("  %s%s" % (key, note))
        print("")

    in_sync = not (differing or only_record or only_env)
    if in_sync:
        print("in sync — %d variables match" % len(agreeing))
    else:
        print("%d match, %d differ, %d only in the record, %d only in the env file"
              % (len(agreeing), len(differing), len(only_record), len(only_env)))
    return in_sync


def import_env(path, system, env_path, prune=False, dry_run=False):
    """Update <system>'s record from an env file. Returns (added, changed, removed).

    Merges by default: keys the env file doesn't mention are left alone, so a record
    never loses fields just because the machine's airlab.env is thinner. --prune
    drops those instead. Bookkeeping is never touched either way.
    """
    data = load(path)
    entry = data.setdefault(system, {})
    # Bookkeeping is operator-side truth (`robot_ssh` comes from address resolution,
    # `ws_path` from setup). A machine provisioned before the extraction fix has those
    # names sitting in its airlab.env as stray variables; importing them back would let
    # a leak overwrite the record that produced it.
    env = {k: v for k, v in parse_env_file(env_path).items() if k not in BOOKKEEPING}

    added = [k for k in env if k not in entry]
    changed = [k for k in env if k in entry and str(entry[k]) != env[k]]
    removed = [k for k in entry
               if k not in env and k not in BOOKKEEPING] if prune else []

    if not dry_run:
        for key in removed:
            entry.pop(key, None)
        for key, value in env.items():
            set_field(data, system, key, value)
        entry.pop("last_updated", None)               # keep it trailing even if env was empty
        entry["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save(path, data)
    return added, changed, removed


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

    if cmd == "envdiff":
        # 0 = the two sides agree, 2 = drift, 1 = error. The distinct code lets a
        # caller gate on drift without treating it as a failure to run.
        if len(argv) < 5:
            sys.stderr.write(__doc__)
            return 2
        env_path = argv[4]
        labels = argv[5:] + ["", ""]
        result = envdiff(path, system, env_path)
        ok = render_envdiff(system, labels[0] or path, labels[1] or env_path, result)
        return 0 if ok else 2

    if cmd == "import":
        if len(argv) < 5:
            sys.stderr.write(__doc__)
            return 2
        env_path = argv[4]
        flags = argv[5:]
        added, changed, removed = import_env(
            path, system, env_path,
            prune="--prune" in flags, dry_run="--dry-run" in flags)
        for key in added:
            print("add     %s" % key)
        for key in changed:
            print("update  %s" % key)
        for key in removed:
            print("remove  %s" % key)
        if not (added or changed or removed):
            print("no changes")
        return 0

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
