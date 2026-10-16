#!/usr/bin/env python3
"""Turn `.airlabignore` (gitignore syntax) into rsync filter arguments for `airlab sync`.

    airlabignore.py floor [--path P]        the built-in floor
    airlabignore.py rules FILE [--path P]   FILE's rules

Prints one `--include=PATTERN` / `--exclude=PATTERN` per line, in rsync order: rsync uses
the FIRST rule that matches a name, gitignore the LAST, so a file's lines come out reversed.

Syntax: blank lines and `#` comments are skipped (`\\#`, `\\!` start a literal name); `!`
re-includes; a leading `/`, or a `/` anywhere but the end, anchors the pattern at the
workspace root, otherwise it matches a name at any depth; a trailing `/` matches folders
only; `**` as a whole segment matches any number of folders, none included.

P is `airlab sync --path`. rsync's transfer root moves there, so anchored patterns are
rewritten relative to it and anchored patterns for the rest of the tree are dropped. A
pattern that matches P itself or a parent of P is dropped too: an explicit --path is
synced, and the rules apply below it.
"""
import argparse
import fnmatch
import re
import sys

# Excluded whatever .airlabignore says: build output, the machine's own airlab.env and the
# storage-tools secrets. rsync sees these first, so the file cannot re-include them.
FLOOR = """
.git
build/
devel/
log/
install/
*.pyc
__pycache__
/airlab.env
/storage_tools_ws/**/config*.env
"""


def parse_line(raw):
    """(include, anchored, segments, dir_only) for one line; None for blanks and comments."""
    line = raw.rstrip('\r\n').rstrip(' ')
    if not line or line.startswith('#'):
        return None
    include = False
    if line.startswith(('\\#', '\\!')):
        line = line[1:]
    elif line.startswith('!'):
        include, line = True, line[1:]
    dir_only = line.endswith('/')
    anchored = '/' in line.rstrip('/')
    segments = [s for s in line.strip('/').split('/') if s]
    if not segments:
        return None
    if len(segments) == 2 and segments[0] == '**':       # **/name: a name at any depth
        anchored, segments = False, segments[1:]
    # '**' is special only as a whole segment; inside a name it is '*' (rsync's would cross '/')
    segments = [s if s == '**' else re.sub(r'\*{2,}', '*', s) for s in segments]
    return include, anchored, segments, dir_only


def residuals(segments, path):
    """What is left of an anchored pattern below the transfer root `path` (folder names):
    one segment list per way the pattern can match its way down `path`."""
    out = []

    def walk(i, j):
        if j == len(path):
            if i < len(segments):           # i == len(segments): the pattern is the root itself
                out.append(segments[i:])
            return
        if i == len(segments):              # the pattern is a parent of the root
            return
        if segments[i] == '**':
            walk(i + 1, j)                  # '**' as zero folders
            walk(i, j + 1)                  # '**' swallowing one more folder
        elif fnmatch.fnmatchcase(path[j], segments[i]):
            walk(i + 1, j + 1)

    walk(0, 0)
    return out


def zero_folder_variants(segments):
    """gitignore's `a/**/b` also matches `a/b`; rsync's does not. Every variant with any of
    the non-final '**' segments left out."""
    variants = [[]]
    for k, seg in enumerate(segments):
        if seg == '**' and k < len(segments) - 1:
            variants = [v + [seg] for v in variants] + [list(v) for v in variants]
        else:
            variants = [v + [seg] for v in variants]
    return variants


def to_rsync(rule, path):
    """rsync filter args for one parsed line, below the transfer root `path`."""
    include, anchored, segments, dir_only = rule
    flag = '--include=' if include else '--exclude='
    tail = '/' if dir_only else ''
    if not anchored:                        # a single name: rsync matches it at any depth
        return [flag + segments[0] + tail]
    out = []
    for rest in residuals(segments, path):
        for variant in zero_folder_variants(rest):
            arg = flag + '/' + '/'.join(variant) + tail
            if arg not in out:
                out.append(arg)
    return out


def convert(lines, path):
    """rsync filter args for gitignore-style `lines`, in rsync (first match wins) order."""
    args = []
    for rule in reversed([r for r in map(parse_line, lines) if r]):
        for arg in to_rsync(rule, path):
            if arg not in args:
                args.append(arg)
    return args


def path_segments(path):
    """`airlab sync --path` as folder names ('launch/', './launch' -> ['launch'])."""
    segs = [s for s in path.split('/') if s not in ('', '.')]
    if '..' in segs:
        sys.exit(f"airlabignore: --path must stay inside the workspace: {path!r}")
    return segs


def main(argv=None):
    parser = argparse.ArgumentParser(description="`.airlabignore` -> rsync filters for `airlab sync`")
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('floor').add_argument('--path', default='')
    rules = sub.add_parser('rules')
    rules.add_argument('file')
    rules.add_argument('--path', default='')
    args = parser.parse_args(argv)
    path = path_segments(args.path)
    if args.command == 'floor':
        lines = FLOOR.splitlines()
    else:
        try:
            with open(args.file, encoding='utf-8') as fh:
                lines = fh.read().splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            print(f"airlabignore: cannot read {args.file}: {exc}", file=sys.stderr)
            return 1
    for arg in convert(lines, path):
        print(arg)
    return 0


if __name__ == '__main__':
    sys.exit(main())
