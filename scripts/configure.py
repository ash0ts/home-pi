#!/usr/bin/env python3
"""Generate private configuration without running Docker or installing packages."""

import argparse
import base64
import binascii
import os
import secrets
import sys

from lib.config import ConfigError, PROJECT_RE, ROOT, atomic_write, command_lock, load_env, reject_root


def valid_app_key(value):
    try:
        return value.startswith("base64:") and len(base64.b64decode(value[7:], validate=True)) == 32
    except (ValueError, binascii.Error):
        return False


def _configure(project_name=None, dry_run=False):
    reject_root()
    path = ROOT / ".env"
    if path.is_symlink():
        raise ConfigError(".env must be a regular private file, not a symbolic link.")
    is_new = not path.exists()
    existing = load_env(required=False)
    recorded = existing.get("COMPOSE_PROJECT_NAME")
    if recorded and project_name and recorded != project_name:
        raise ConfigError("Refusing to change the installed Compose project name. A project/volume migration requires a separate reviewed procedure.")
    project_name = recorded or project_name
    if not project_name or not PROJECT_RE.fullmatch(project_name):
        raise ConfigError("Supply --project-name NAME. For an existing installation, inspect its Compose project label first; do not infer it from this checkout.")
    app_key = existing.get("SPEEDTEST_APP_KEY")
    if app_key is not None and not valid_app_key(app_key):
        raise ConfigError("Existing SPEEDTEST_APP_KEY is invalid; it was preserved. Stop Speedtest, back up its config/database, and follow its documented encryption-key migration before retrying.")
    for key in ("PIHOLE_PASSWORD", "WEBTOP_PASSWORD"):
        if key in existing and not existing[key]:
            raise ConfigError(f"Existing {key} is empty; set it privately before retrying. No values were changed.")
    defaults = {
        "COMPOSE_PROJECT_NAME": project_name,
        "TZ": "America/New_York", "PUID": str(os.getuid()), "PGID": str(os.getgid()),
        "PIHOLE_PASSWORD": secrets.token_hex(24), "PIHOLE_HOSTNAME": "pi-hole",
        "PIHOLE_DOMAIN": "home.arpa", "PIHOLE_DNS": "1.1.1.1;1.0.0.1", "TS_AUTHKEY": "",
        "PIHOLE_LISTENING_MODE": "local", "ACK_REMOTE_DNS": "no",
        "SPEEDTEST_APP_KEY": "base64:" + base64.b64encode(secrets.token_bytes(32)).decode(),
        "SPEEDTEST_APP_URL": "http://localhost:8765", "NETDATA_HOSTNAME": "pi-netdata",
        "WEBTOP_USER": "user", "WEBTOP_PASSWORD": secrets.token_hex(24),
    }
    missing = {key: value for key, value in defaults.items() if key not in existing}
    if dry_run:
        print(f"Dry run: would {'update' if path.exists() else 'create'} private .env; {len(missing)} missing settings. No writes or external commands.")
        return
    original = path.read_bytes() if path.exists() else b"# Private home-pi configuration. Never commit or print this file.\n"
    if missing:
        separator = b"" if not original or original.endswith(b"\n") else b"\n"
        additions = "".join(f"{key}={value}\n" for key, value in missing.items()).encode()
        atomic_write(path, original + separator + additions)
    else:
        path.chmod(0o600)
    if is_new:
        from lib.selection import initialize
        initialize(preset="standard")
    print("Private configuration ready (mode 0600); existing values preserved. No services started.")


def configure(project_name=None, dry_run=False):
    reject_root()
    if dry_run:
        return _configure(project_name, dry_run=True)
    with command_lock():
        return _configure(project_name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        configure(args.project_name, args.dry_run)
    except (ConfigError, OSError) as exc:
        print(f"Configure failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
