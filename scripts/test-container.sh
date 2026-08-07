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

# Pin the platform explicitly: podman will otherwise reuse a locally stored
# base image of the *wrong* architecture if one happens to be tagged
# python:3.10-slim-bookworm, and the resulting qemu-emulated run is ~2.5x
# slower. Pin to the host's own architecture rather than to amd64, though --
# hardcoding amd64 makes this script unrunnable on a native arm64 host
# without binfmt registered, and README.md now points contributors at it.
# The published image is amd64; testing on arm64 tests the code, not the
# artifact, which is the honest limit of running it there.
host_arch="$(uname -m)"
case "$host_arch" in
    x86_64 | amd64) platform="linux/amd64" ;;
    aarch64 | arm64) platform="linux/arm64" ;;
    *) platform="" ;;  # unknown: let the engine decide rather than guess wrong
esac
platform="${TCPM_TEST_PLATFORM-$platform}"

echo "==> building the test stage with $engine${platform:+ for $platform}"
if [ -n "$platform" ]; then
    "$engine" build --platform "$platform" --target test -t tcpm:test .
else
    "$engine" build --target test -t tcpm:test .
fi

echo "==> running the suite in the container"
if [ "$#" -eq 0 ]; then
    exec "$engine" run --rm tcpm:test
fi

# Any argument list replaces the image's CMD, so the `python -m pytest` form
# has to be repeated here -- the `pytest` console script would not put
# /usr/src/app on sys.path and would collect nothing.
exec "$engine" run --rm tcpm:test python -m pytest "$@"
