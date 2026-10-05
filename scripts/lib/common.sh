#!/usr/bin/env bash
# This file is sourced. Paths are always relative to the checkout, never $PWD.
PI_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
export PI_ROOT

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'Missing dependency: %s. See ReadMe.md.\n' "$1" >&2
    return 1
  }
}

run_docker() {
  if [[ "${PI_DOCKER_SUDO:-0}" == 1 ]]; then
    sudo -n docker "$@"
  else
    docker "$@"
  fi
}
