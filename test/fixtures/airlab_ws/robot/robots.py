#!/usr/bin/env python3
"""Stub resolver for tests — a faithful, self-contained stand-in for the real
robots.py that ships in airlab_ws.

It honors the CLI contract that the airlab tool's _lib/resolve.sh depends on:

  robots.py resolve <system> [--address NAME]   # prints ssh target, or nothing
  robots.py list                                # one system name per line
  robots.py addresses <system>                  # one address_name per line

Resolve output format (matches what resolve.sh parses):
  no port -> os_user@host        with port -> ssh://os_user@host:port
where host = the address's hostname, else its ip.

Reads robots.yaml sitting next to this file. Kept intentionally small; the
tool's tests exercise the *tool's* consumption of this contract, not the real
resolver's internals.
"""
import os
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("stub robots.py: PyYAML required")


def _load():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "robots.yaml")
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _systems(doc):
    return {s["system"]: s for s in doc.get("systems", []) if "system" in s}


def _pick(system, address_name=None):
    addrs = system.get("network_addresses") or []
    if address_name:
        for a in addrs:
            if a.get("address_name") == address_name:
                return a
        return None
    for a in addrs:
        if a.get("default") is True:
            return a
    return addrs[0] if addrs else None


def main(argv):
    if not argv:
        return 1
    cmd, rest = argv[0], argv[1:]
    doc = _load()
    systems = _systems(doc)

    if cmd == "list":
        for name in systems:
            print(name)
        return 0

    if cmd == "addresses":
        if not rest:
            return 1
        s = systems.get(rest[0])
        for a in (s or {}).get("network_addresses", []):
            if a.get("address_name"):
                print(a["address_name"])
        return 0

    if cmd == "resolve":
        args = list(rest)
        address = None
        if "--address" in args:
            i = args.index("--address")
            address = args[i + 1]
            del args[i:i + 2]
        if not args:
            return 1
        s = systems.get(args[0])
        if not s:
            return 0  # unknown system -> empty (the tool prints "not found")
        a = _pick(s, address)
        if not a:
            return 0
        host = a.get("hostname") or a.get("ip")
        if not host:
            return 0
        target = "%s@%s" % (s.get("os_user", "root"), host)
        if a.get("port"):
            target = "ssh://%s:%s" % (target, a["port"])
        print(target)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
