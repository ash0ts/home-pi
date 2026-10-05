"""Shared paths, literal dotenv parsing, private writes, and argv-only Docker calls."""

import os
from contextlib import contextmanager
import fcntl
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class ConfigError(RuntimeError):
    """An actionable error safe to display without configuration values."""


def reject_root():
    if os.geteuid() == 0:
        raise ConfigError("Run as the account that owns this checkout, not root. Use PI_DOCKER_SUDO=1 only for Docker access.")


def load_env(path=None, required=True):
    """Read single-line Compose dotenv values as data; never execute contents.

    Quoted values and comments work. Multiline values and duplicate keys are
    rejected with redacted line numbers. This parser never rewrites the file.
    """
    path = Path(path) if path is not None else ROOT / ".env"
    if not path.exists():
        if required:
            raise ConfigError("Missing .env. Run ./setup.sh configure --project-name NAME; use the installed project's exact name when migrating.")
        return {}
    result = {}
    for number, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if not match:
            raise ConfigError(f"Unsupported .env syntax at line {number}; use one KEY=value per line.")
        key, value = match.groups()
        if key in result:
            raise ConfigError(f"Duplicate .env key at line {number}; resolve duplicates before proceeding.")
        if "$" in value and not value.startswith("'"):
            raise ConfigError(f"Interpolation is unsupported at .env line {number}; single quote literal dollar signs before retrying.")
        if value.startswith(("'", '"')):
            quote = value[0]
            close = 1
            while close < len(value):
                if value[close] == quote and (quote == "'" or value[close - 1] != "\\"):
                    break
                close += 1
            if close == len(value) or (value[close + 1:].strip() and not value[close + 1:].lstrip().startswith("#")):
                raise ConfigError(f"Unsupported quoted .env value at line {number}; use a single line.")
            value = value[1:close]
            if quote == '"':
                value = re.sub(r'\\([nrt"\\])', lambda m: {"n": "\n", "r": "\r", "t": "\t"}.get(m[1], m[1]), value)
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        result[key] = value
    return result


def atomic_write(path, content, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content.encode() if isinstance(content, str) else content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def docker(*args, capture=True, check=True, timeout=60):
    if not capture:
        raise ConfigError("Managed Docker calls must capture output to protect private diagnostics.")
    prefix = ["sudo", "-n", "docker"] if os.environ.get("PI_DOCKER_SUDO") == "1" else ["docker"]
    child_env = os.environ.copy()
    for key in ("COMPOSE_FILE", "COMPOSE_PROFILES", "COMPOSE_PROJECT_NAME", "COMPOSE_ENV_FILES"):
        child_env.pop(key, None)
    # Compose normally gives the shell precedence over --env-file. The private
    # checkout configuration is authoritative for this command layer.
    for key in load_env(required=False):
        child_env.pop(key, None)
    try:
        completed = subprocess.run(prefix + [str(arg) for arg in args], cwd=ROOT,
                                   capture_output=True, text=True, check=False, env=child_env, timeout=timeout)
    except FileNotFoundError as exc:
        raise ConfigError("Docker (or selected sudo runner) is unavailable. See ./setup.sh install-deps.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ConfigError("Docker command timed out; inspect daemon readiness and retry. Private output was suppressed.") from exc
    if check and completed.returncode:
        # Docker errors can include interpolated credentials. Do not echo them.
        raise ConfigError("Docker command failed. Check daemon access, Compose configuration, and private local logs.")
    return completed


def compose_args(env_file=None, project_name=None, files=None):
    env_file = Path(env_file) if env_file else ROOT / ".env"
    if project_name is None:
        project_name = load_env(env_file).get("COMPOSE_PROJECT_NAME", "")
    if not PROJECT_RE.fullmatch(project_name):
        raise ConfigError("COMPOSE_PROJECT_NAME is missing or invalid. Inventory the installed name before configuring; never guess during migration.")
    result = ["compose", "--project-directory", str(ROOT), "--env-file", str(env_file),
              "--project-name", project_name]
    for path in files or [ROOT / "docker-compose.yaml"]:
        result.extend(["-f", str(path)])
    return result


def run_compose(*args, capture=True, check=True, files=None, timeout=60):
    return docker(*compose_args(files=files), *args, capture=capture, check=check, timeout=timeout)


@contextmanager
def command_lock():
    """Serialize mutating commands without executing a shell; no stale PID lock."""
    directory = ROOT / ".context"
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / "setup.lock"
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ConfigError("Another home-pi configuration operation is running. Retry when it finishes.") from exc
        yield
    finally:
        os.close(descriptor)
