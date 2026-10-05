#!/usr/bin/env python3
"""Explicit configuration, validation, dependency, and startup stages."""

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

from configure import configure, valid_app_key
from lib.config import ConfigError, ROOT, command_lock, docker, load_env, reject_root, run_compose


def platform_check():
    if platform.system() != "Linux" or platform.machine() not in ("aarch64", "arm64"):
        raise ConfigError("Live setup requires a 64-bit ARM Linux host. Configuration and static validation may run on a workstation.")


def preflight():
    platform_check()
    for name in ("docker", "curl", "openssl", "ss"):
        if not shutil.which(name):
            raise ConfigError(f"Missing dependency: {name}. Run the explicit install-deps stage or install it for your OS.")
    env = load_env()
    if not valid_app_key(env.get("SPEEDTEST_APP_KEY", "")):
        raise ConfigError("Invalid SPEEDTEST_APP_KEY. Run configure and follow its migration instructions; startup stopped.")
    if (ROOT / ".env").stat().st_mode & 0o077:
        raise ConfigError(".env must be mode 0600. Run ./setup.sh configure to repair private file permissions.")
    docker("info", "--format", "{{.OSType}}/{{.Architecture}}")
    docker("compose", "version")
    run_compose("config", "--quiet")
    model = json.loads(run_compose("config", "--format", "json").stdout)
    if any(service.get("network_mode") == "host" and "tailscale" in name for name, service in model["services"].items()):
        if not Path("/dev/net/tun").exists():
            raise ConfigError("/dev/net/tun is missing. Configure the host TUN device before starting Tailscale.")
    disk = shutil.disk_usage(ROOT)
    if disk.free < max(2 * 1024**3, disk.total * 0.20):
        raise ConfigError("Data filesystem has less than 20% or 2 GiB free. Free space safely before startup.")
    running = run_compose("ps", "--status", "running", "--format", "json").stdout.strip()
    # An existing running stack owns some expected listeners. Its live migration
    # must use doctor and the service-by-service update workflow.
    if running and running != "[]":
        raise ConfigError("This project already has running services. Use the documented inventory, backup, and service-by-service maintenance workflow; initial startup will not recreate live DNS.")
    expected = {(int(port["published"]), port.get("protocol", "tcp"))
                for service in model["services"].values() for port in service.get("ports", []) if port.get("published")}
    if model["services"].get("pihole", {}).get("network_mode") == "host":
        expected.update({(53, "tcp"), (53, "udp"), (80, "tcp"), (443, "tcp")})
    observed = subprocess.run(["ss", "-H", "-lntu"], capture_output=True, text=True, check=True)
    conflicts = set()
    for line in observed.stdout.splitlines():
        fields = line.split()
        if len(fields) < 5:
            continue
        match = re.search(r":(\d+)$", fields[4])
        if match and (int(match[1]), fields[0]) in expected:
            conflicts.add(f"{fields[0]}/{match[1]}")
    if conflicts:
        raise ConfigError("Ports already listening: " + ", ".join(sorted(conflicts)) + ". Identify their owners before starting; no listeners were changed.")


def install_deps():
    platform_check()
    if not Path("/etc/debian_version").exists() or not shutil.which("apt-get"):
        raise ConfigError("Automatic dependency installation supports Debian-family ARM64 Linux only. Follow your OS and Docker installation documentation.")
    if not shutil.which("sudo"):
        raise ConfigError("sudo is required for the explicit dependency installation stage.")
    # Use configured OS repositories. Docker's repository must already be set up
    # by the owner if docker-ce-cli/docker-compose-plugin are not available.
    commands = [["sudo", "apt-get", "update"],
                ["sudo", "apt-get", "install", "-y", "curl", "openssl", "python3", "iproute2", "shellcheck"]]
    for command in commands:
        subprocess.run(command, check=True)
    if not shutil.which("docker"):
        raise ConfigError("Base dependencies installed. Install Docker Engine and Compose v2 using the official Debian guide linked in ReadMe.md, then retry validation.")
    docker("compose", "version")
    print("Base dependencies and Compose are available. No VPN installed or services started.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("configure", "validate", "start", "install-deps"))
    parser.add_argument("--project-name")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "configure":
            configure(args.project_name, args.dry_run)
            return 0
        if args.project_name:
            raise ConfigError("--project-name belongs to configure; startup always uses the persisted project identity.")
        if args.dry_run:
            print(f"Dry run: would run {args.command}. No installs, starts, writes, locks, or external commands.")
            return 0
        if args.command == "validate":
            from validate import validate
            return validate()
        reject_root()
        with command_lock():
            if args.command == "install-deps":
                install_deps()
            elif args.command == "start":
                preflight()
                run_compose("up", "-d", "--pull", "never")
                print("Selected services started using local images. Run doctor and complete the live network checks before relying on them.")
    except (ConfigError, OSError, subprocess.SubprocessError, ValueError) as exc:
        if isinstance(exc, ConfigError):
            print(f"Setup failed: {exc}", file=sys.stderr)
        else:
            print("Setup failed during a local preflight or dependency command; no diagnostic configuration was printed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
