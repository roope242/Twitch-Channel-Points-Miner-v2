#!/usr/bin/env bash
# Run the Python suite inside the image the miner actually ships in.
#
# The host venv is whatever Python happens to be installed here, and CI tests
# 3.9/3.10/3.13 on a bare runner. Neither is the published image. This builds
# the Dockerfile's `test` stage -- the runtime image's exact base and resolved
# requirements.txt, plus pytest -- and runs the suite in it.
#
# Usage: scripts/test-container.sh [extra pytest args...]
#   scripts/test-container.sh                     # python -m pytest tests/ -v
#   scripts/test-container.sh tests/test_utils.py # narrowed to one module
#
# Exit code is pytest's.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if command -v podman >/dev/null 2>&1; then
    engine=podman
elif command -v docker >/dev/null 2>&1; then
    engine=docker
else
    echo "Neither podman nor docker is on PATH." >&2
    exit 127
fi

# --platform is not optional with podman: it will happily reuse a locally
# stored base image of the wrong architecture if one is tagged
# python:3.10-slim-bookworm, and the resulting qemu-emulated run is ~2.5x
# slower. Harmless on an amd64 docker host, so it is passed unconditionally.
echo "==> building the test stage with $engine"
"$engine" build --platform linux/amd64 --target test -t tcpm:test .

echo "==> running the suite in the container"
if [ "$#" -eq 0 ]; then
    exec "$engine" run --rm tcpm:test
fi

# Any argument list replaces the image's CMD, so the `python -m pytest` form
# has to be repeated here -- the `pytest` console script would not put
# /usr/src/app on sys.path and would collect nothing.
exec "$engine" run --rm tcpm:test python -m pytest "$@"
