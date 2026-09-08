#!/usr/bin/env python3
"""Compute (and optionally apply) the automatic patch bump for a PR.

Versioning contract
-------------------
`DEBIAN/control`'s `Version:` field is the single source of truth for the tool's
version — `airlab --version` reads it back out of dpkg, so nothing else in the
tree should hard-code it.

The version is `MAJOR.MINOR.PATCH[-SUFFIX]`, and ownership is split:

  * MAJOR and MINOR are **reserved for the maintainer**. CI never touches them.
  * PATCH is **owned by CI**: every PR into `dev` gets base-patch + 1.

So a PR that leaves MAJOR.MINOR alone is patch-bumped automatically, and a PR
that deliberately changes MAJOR.MINOR (a release bump) is left exactly as the
author wrote it — that is how the maintainer takes manual control.

Usage:
    bump_version.py --base-file <control> --head-file <control> [--write]

Prints the decision to stdout and, with --write, edits the head control file in
place. Exits non-zero only on a malformed version it cannot reason about.
"""
import argparse
import re
import sys

VERSION_RE = re.compile(
    r"^(?P<prefix>Version:[ \t]*)"
    r"(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?P<suffix>\S*)[ \t]*$",
    re.MULTILINE,
)


class MalformedVersion(ValueError):
    pass


def parse_version(control_text, origin):
    """Return (major, minor, patch, suffix) from a DEBIAN/control body."""
    m = VERSION_RE.search(control_text)
    if not m:
        raise MalformedVersion(
            f"{origin}: no parseable 'Version: MAJOR.MINOR.PATCH' line found. "
            "DEBIAN/control must carry a three-part numeric version."
        )
    return (
        int(m.group("major")),
        int(m.group("minor")),
        int(m.group("patch")),
        m.group("suffix"),
    )


def compute_next_version(base, head):
    """Decide what the head version should be.

    `base` and `head` are (major, minor, patch, suffix) tuples.

    Returns (target_tuple, reason). `target_tuple == head` means "leave it
    alone" and the reason explains why.
    """
    b_major, b_minor, b_patch, _ = base
    h_major, h_minor, h_patch, h_suffix = head

    # MAJOR/MINOR are the maintainer's. If the PR changed either, it is a
    # deliberate release bump — take it verbatim, patch included.
    if (h_major, h_minor) != (b_major, b_minor):
        return head, (
            f"PR sets {h_major}.{h_minor}, base is {b_major}.{b_minor} — a "
            "MAJOR/MINOR change is maintainer-owned, leaving the version as authored"
        )

    target = (h_major, h_minor, b_patch + 1, h_suffix)
    if head == target:
        return head, f"already at the expected patch {format_version(target)}"
    return target, (
        f"base is {format_version(base)}, so this PR takes "
        f"{format_version(target)}"
    )


def format_version(v):
    major, minor, patch, suffix = v
    return f"{major}.{minor}.{patch}{suffix}"


def apply_version(control_text, version):
    """Return `control_text` with its Version: line set to `version`."""
    new_line = r"\g<prefix>" + format_version(version).replace("\\", r"\\")
    text, n = VERSION_RE.subn(new_line, control_text, count=1)
    if n != 1:
        raise MalformedVersion("failed to rewrite the Version: line")
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-file", required=True, help="DEBIAN/control as it is on the base branch")
    ap.add_argument("--head-file", required=True, help="DEBIAN/control on the PR branch")
    ap.add_argument("--write", action="store_true", help="edit --head-file in place")
    args = ap.parse_args(argv)

    with open(args.base_file, encoding="utf-8") as fh:
        base_text = fh.read()
    with open(args.head_file, encoding="utf-8") as fh:
        head_text = fh.read()

    try:
        base = parse_version(base_text, args.base_file)
        head = parse_version(head_text, args.head_file)
    except MalformedVersion as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    target, reason = compute_next_version(base, head)
    print(f"base    : {format_version(base)}")
    print(f"head    : {format_version(head)}")
    print(f"target  : {format_version(target)}")
    print(f"reason  : {reason}")

    changed = target != head
    if changed and args.write:
        with open(args.head_file, "w", encoding="utf-8") as fh:
            fh.write(apply_version(head_text, target))
        print(f"wrote {args.head_file}")

    # Machine-readable for the workflow step.
    print(f"::CHANGED::{'yes' if changed else 'no'}")
    print(f"::VERSION::{format_version(target)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
