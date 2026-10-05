#!/usr/bin/env python3
"""Static repository validation, using only dummy Compose configuration."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from lib.config import ConfigError, ROOT, compose_args, load_env


DUMMY = {
    "COMPOSE_PROJECT_NAME": "home-pi-validation", "PUID": "1000", "PGID": "1000", "TZ": "Etc/UTC",
    "PIHOLE_PASSWORD": "dummy-pihole-password", "WEBTOP_PASSWORD": "dummy-webtop-password",
    "SPEEDTEST_APP_KEY": "base64:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "SPEEDTEST_APP_URL": "http://localhost:8765", "TS_AUTHKEY": "",
}


def validate_models():
    """Render every real fragment with dummy inputs, then check its semantics."""
    from modules import catalog, compose_files, resolve, validate as validate_modules
    entries = catalog()
    files = compose_files(resolve(list(entries)))
    # Only the tracked example is read. Runtime .env, selection, storage markers,
    # and actual private secret-file contents are never inputs to static checks.
    values = load_env(ROOT / ".env.example")
    values.update(DUMMY)
    with tempfile.TemporaryDirectory(prefix="home-pi-validate-") as directory:
        env_file = Path(directory) / "dummy.env"
        for entry in entries.values():
            for key in entry["secrets"]:
                if key.endswith("_FILE"):
                    source = Path(directory) / (key.lower() + ".txt")
                    source.write_text("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\n")
                    source.chmod(0o600)
                    values[key] = str(source)
                elif key not in DUMMY:
                    values[key] = "dummy-" + key.lower()
        dummy_text = "\n".join(f"{key}={json.dumps(str(value))}" for key, value in values.items()) + "\n"
        env_file.write_text(dummy_text)
        env_file.chmod(0o600)
        child_env = os.environ.copy()
        variables = set(re.findall(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)", "\n".join(path.read_text() for path in files)))
        variables.update(re.findall(r"^([A-Za-z_][A-Za-z0-9_]*)=", dummy_text, re.MULTILINE))
        for key in variables | {"COMPOSE_FILE", "COMPOSE_PROFILES", "COMPOSE_PROJECT_NAME", "COMPOSE_ENV_FILES"}:
            child_env.pop(key, None)
        def render(selected_files, consistency=True):
            command = ["docker", *compose_args(env_file=env_file, project_name="home-pi-validation", files=selected_files),
                       "--profile", "*", "config", "--format", "json"]
            if not consistency:
                command.extend(["--no-consistency", "--no-env-resolution"])
            result = subprocess.run(command, cwd=ROOT, env=child_env, capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise ConfigError("Compose model validation failed with dummy settings; production configuration and command output were not used.")
            try:
                model = json.loads(result.stdout)
            except ValueError:
                raise ConfigError("Compose returned an invalid dummy model; output was suppressed.") from None
            if not isinstance(model, dict) or not isinstance(model.get("services"), dict):
                raise ConfigError("Compose returned an invalid dummy model shape.")
            return model
        return validate_modules(list(entries), env_override=values, model_loader=render, runtime_checks=False)


def validate():
    for name in ("bash", "shellcheck", "docker"):
        if not shutil.which(name):
            raise ConfigError(f"Static validation requires {name}. Install it before retrying.")
    shells = [ROOT / "pi", ROOT / "setup.sh", *sorted((ROOT / "scripts").rglob("*.sh")), *sorted((ROOT / "tests").rglob("*.sh"))]
    for path in shells:
        subprocess.run(["bash", "-n", str(path)], cwd=ROOT, check=True)
    subprocess.run(["shellcheck", "-x", *map(str, shells)], cwd=ROOT, check=True)
    validate_models()
    subprocess.run([sys.executable, "-B", str(ROOT / "scripts/check_images.py")], cwd=ROOT, check=True)
    print("PASS: shell syntax, ShellCheck, module ownership/state/access policy, and Compose models with dummy configuration.")
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
