"""Encrypted backup transport and safe, quarantined archive restoration."""
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tarfile

from lib.config import ConfigError, load_env

CREDENTIAL_KEYS = {
    'RESTIC_REPOSITORY', 'RESTIC_PASSWORD_FILE', 'RESTIC_CACERT',
    'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN',
    'AWS_DEFAULT_REGION', 'AWS_REGION', 'AWS_ENDPOINT',
    'B2_ACCOUNT_ID', 'B2_ACCOUNT_KEY', 'AZURE_ACCOUNT_NAME', 'AZURE_ACCOUNT_KEY',
    'AZURE_ACCOUNT_SAS', 'GOOGLE_APPLICATION_CREDENTIALS', 'RCLONE_CONFIG',
}
REMOTE_PREFIXES = ('sftp:', 's3:', 'rest:', 'azure:', 'gs:', 'rclone:', 'b2:')
SERVICE_RE = re.compile(r'^[a-z0-9][a-z0-9_-]*$')
SNAPSHOT_RE = re.compile(r'^[0-9a-f]{64}$')


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def private_file(path, description):
    path = Path(path)
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise ConfigError(description + ' is unavailable.') from exc
    if not stat.S_ISREG(mode) or stat.S_IMODE(mode) != 0o600:
        raise ConfigError(description + ' must be a regular file with mode 0600, not a symlink.')


def repository_environment(root, allow_local=False):
    config_path = Path(root) / 'local/backup.env'
    private_file(config_path, 'local/backup.env')
    config = load_env(config_path)
    if set(config) - CREDENTIAL_KEYS:
        raise ConfigError('Unsupported backup configuration key; use the documented credential allowlist.')
    repository = config.get('RESTIC_REPOSITORY', '')
    password_path = Path(config.get('RESTIC_PASSWORD_FILE', ''))
    if not repository or not password_path.is_absolute():
        raise ConfigError('Set RESTIC_REPOSITORY and an absolute RESTIC_PASSWORD_FILE in local/backup.env.')
    private_file(password_path, 'Restic password file')
    remote = repository.startswith(REMOTE_PREFIXES)
    if not remote and not allow_local:
        raise ConfigError('Use an off-device network restic repository. Local fixtures require --allow-local-repository and do not meet the recovery requirement.')
    if not remote and (':' in repository or not Path(repository).is_absolute()):
        raise ConfigError('Local test repository must be an absolute filesystem path.')
    # Do not inherit arbitrary RESTIC_PASSWORD_COMMAND or provider credentials.
    env = {key: value for key, value in os.environ.items()
           if key in {'PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TMPDIR', 'SSH_AUTH_SOCK'}}
    env.update(config)
    return env, remote


def restic(arguments, env, cwd=None):
    try:
        result = subprocess.run(['restic', *arguments], env=env, cwd=cwd,
                                capture_output=True, text=True, timeout=3600)
    except FileNotFoundError as exc:
        raise ConfigError('Install restic before backup/restore; see docs/recovery.md.') from exc
    except subprocess.TimeoutExpired as exc:
        raise ConfigError('Restic timed out; private diagnostics were suppressed. Check repository connectivity.') from exc
    if result.returncode:
        raise ConfigError('Restic failed or produced an incomplete backup. No successful backup was recorded; check private repository access and source readability.')
    return result


def checked_relative(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name:
        raise ConfigError('Archive contains an unsafe path; restore remains quarantined.')
    return path


def archive_members(path):
    """Validate everything before extraction, including forward link references."""
    try:
        with tarfile.open(path, 'r:*') as archive:
            members = archive.getmembers()
    except (tarfile.TarError, OSError) as exc:
        raise ConfigError('State archive cannot be read; restore remains quarantined.') from exc
    seen = set()
    links = set()
    normalized = {}
    for member in members:
        name = str(checked_relative(member.name))
        if name == '.':
            if not member.isdir():
                raise ConfigError('Archive root must be a directory.')
            continue
        if name in seen:
            raise ConfigError('Archive contains duplicate paths; restore remains quarantined.')
        seen.add(name)
        normalized[name] = member
        if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
            raise ConfigError('Archive contains a device, FIFO, or unsupported entry; restore remains quarantined.')
        if member.issym() or member.islnk():
            links.add(name)
    for name, member in normalized.items():
        parents = {str(p) for p in PurePosixPath(name).parents}
        if parents & links:
            raise ConfigError('Archive writes through a link; restore remains quarantined.')
        if member.issym() or member.islnk():
            raw = PurePosixPath(member.linkname)
            if raw.is_absolute() or '\\' in member.linkname:
                raise ConfigError('Archive contains an absolute or unsafe link; restore remains quarantined.')
            parts = list(PurePosixPath(name).parent.parts) if member.issym() else []
            for part in raw.parts:
                if part == '..':
                    if not parts:
                        raise ConfigError('Archive link escapes its root; restore remains quarantined.')
                    parts.pop()
                elif part != '.':
                    parts.append(part)
            target = PurePosixPath(*parts)
            targets = {str(target), *(str(p) for p in target.parents)}
            if targets & links:
                raise ConfigError('Archive link chains are refused; restore remains quarantined.')
            if member.islnk() and (str(target) not in normalized or not normalized[str(target)].isfile()):
                raise ConfigError('Archive hardlink must target a regular archived file.')
    return members


def extract_archive(path, destination, members):
    """Keep numeric ownership in the tar, never chown or overwrite live files."""
    destination = Path(destination)
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    directories = []
    with tarfile.open(path, 'r:*') as archive:
        for member in members:
            name = str(checked_relative(member.name))
            if name == '.':
                continue
            target = destination / name
            target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            if member.isdir():
                target.mkdir(mode=0o700, exist_ok=True)
                directories.append((target, member))
            elif member.isfile():
                source = archive.extractfile(member)
                if source is None:
                    raise ConfigError('Archive regular-file content is unavailable.')
                with source, target.open('xb') as output:
                    os.fchmod(output.fileno(), 0o600)
                    shutil.copyfileobj(source, output)
                target.chmod(member.mode & 0o777)
                os.utime(target, (member.mtime, member.mtime))
        # Links go last so no archived file can traverse them while writing.
        for member in members:
            target = destination / str(checked_relative(member.name))
            if member.issym():
                os.symlink(member.linkname, target)
            elif member.islnk():
                os.link(destination / member.linkname, target)
        for target, member in reversed(directories):
            target.chmod(member.mode & 0o777)
            os.utime(target, (member.mtime, member.mtime))
