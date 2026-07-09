#!/bin/bash
# @desc: dummy alias for tests — prints a marker
# @author: Test <tester>
set -euo pipefail
[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { echo "Usage: airlab a hello — print a marker"; exit 0; }
echo "HELLO_FROM_ALIAS"
