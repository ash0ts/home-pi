#!/usr/bin/env python3
"""Static repository validation, using only dummy Compose configuration."""

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from lib.config import ConfigError, ROOT, compose_args


DUMMY = {
    "COMPOSE_PROJECT_NAME": "home-pi-validation", "PUID": "1000", "PGID": "1000", "TZ": "Etc/UTC",
    "PIHOLE_PASSWORD": "dummy-pihole-password", "WEBTOP_PASSWORD": "dummy-webtop-password",
    "SPEEDTEST_APP_KEY": "base64:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "SPEEDTEST_APP_URL": "http://localhost:8765", "TS_AUTHKEY": "",
}


def validate():
    for name in ("bash", "shellcheck", "docker"):
        if not shutil.which(name):
            raise ConfigError(f"Static validation requires {name}. Install it before retrying.")
    shells = [ROOT / "setup.sh", *sorted((ROOT / "scripts").rglob("*.sh")), *sorted((ROOT / "tests").rglob("*.sh"))]
    for path in shells:
        subprocess.run(["bash", "-n", str(path)], cwd=ROOT, check=True)
    subprocess.run(["shellcheck", "-x", *map(str, shells)], cwd=ROOT, check=True)
    # Read .env.example, not the real .env. All expanded values stay in memory
    # inside Compose; neither model nor logs become artifacts.
    dummy_text = (ROOT / ".env.example").read_text()
    dummy_text += "\n" + "\n".join(f"{key}={value}" for key, value in DUMMY.items()) + "\n"
    with tempfile.TemporaryDirectory(prefix="home-pi-validate-") as directory:
        env_file = Path(directory) / "dummy.env"
        env_file.write_text(dummy_text)
        env_file.chmod(0o600)
        child_env = os.environ.copy()
        variables = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", (ROOT / "docker-compose.yaml").read_text()))
        variables.update(re.findall(r"^([A-Za-z_][A-Za-z0-9_]*)=", dummy_text, re.MULTILINE))
        for key in variables | {"COMPOSE_FILE", "COMPOSE_PROFILES", "COMPOSE_PROJECT_NAME", "COMPOSE_ENV_FILES"}:
            child_env.pop(key, None)
        result = subprocess.run(["docker", *compose_args(env_file=env_file, project_name="home-pi-validation"), "--profile", "*", "config", "--quiet"],
                                cwd=ROOT, env=child_env, capture_output=True, text=True)
        if result.returncode:
            raise ConfigError("Compose model validation failed with dummy settings; run a local dummy configuration check to diagnose. Production values were not used.")
    print("PASS: shell syntax, ShellCheck, and Compose model with dummy configuration.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        return validate()
    except (ConfigError, OSError, subprocess.SubprocessError) as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
