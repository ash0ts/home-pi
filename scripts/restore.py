#!/usr/bin/env python3
"""Restore an exact encrypted snapshot into a fresh quarantined directory."""
import argparse
import json
import os
from pathlib import Path
import stat
import sys

from lib.config import ROOT, ConfigError, command_lock, reject_root
from lib.recovery import (SERVICE_RE, SNAPSHOT_RE, archive_members, checked_relative,
                          digest, extract_archive, now, repository_environment, restic)


def validate_restore(target):
    target = Path(target)
    for directory, dirs, files in os.walk(target, followlinks=False):
        for name in dirs + files:
            entry = Path(directory) / name
            mode = entry.lstat().st_mode
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise ConfigError('Restored snapshot contains a filesystem link or special file outside the state archives.')
    if {entry.name for entry in target.iterdir()} - {'manifest.json', 'archives', 'config'}:
        raise ConfigError('Restored snapshot contains unexpected top-level files.')
    manifest_path = target / 'manifest.json'
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ConfigError('Restored snapshot has no regular recovery manifest.')
    try:
        manifest = json.loads(manifest_path.read_text())
    except (ValueError, OSError) as exc:
        raise ConfigError('Restored recovery manifest is unreadable.') from exc
    if manifest.get('schema_version') != 1 or not isinstance(manifest.get('services'), list):
        raise ConfigError('Unsupported restored recovery manifest.')
    validated = []
    names = set()
    destinations = set()
    for service in manifest['services']:
        name = service.get('service', '')
        if not SERVICE_RE.fullmatch(name) or name in names:
            raise ConfigError('Restored manifest contains invalid or duplicate service identity.')
        names.add(name)
        for index, mount in enumerate(service.get('mounts', [])):
            if mount.get('exclude'):
                if mount.get('kind') != 'cache' or not mount.get('reason'):
                    raise ConfigError('Invalid excluded state in restored manifest.')
                continue
            expected_archive = 'archives/' + name + '-' + str(index) + '.tar'
            expected_state = 'state/' + name + '/' + str(index)
            if mount.get('archive') != expected_archive or mount.get('restore_path') != expected_state:
                raise ConfigError('Restored manifest archive paths are inconsistent.')
            archive = target / expected_archive
            if (not archive.is_file() or archive.is_symlink() or
                    not stat.S_ISREG(archive.lstat().st_mode) or digest(archive) != mount.get('sha256')):
                raise ConfigError('Restored archive checksum or regular-file validation failed.')
            destination = target / expected_state
            if destination in destinations or destination.exists() or destination.is_symlink():
                raise ConfigError('Restore extraction target already exists.')
            destinations.add(destination)
            validated.append((archive, destination, archive_members(archive)))
    for item in manifest.get('configuration', []):
        relative = str(checked_relative(item.get('path', '')))
        if not relative.startswith('config/'):
            raise ConfigError('Restored configuration path is outside its quarantine directory.')
        path = target / relative
        if not path.is_file() or path.is_symlink() or digest(path) != item.get('sha256'):
            raise ConfigError('Restored private configuration checksum failed.')
    return manifest, validated


def restore_snapshot(snapshot_id, target, allow_local_repository=False):
    if not SNAPSHOT_RE.fullmatch(snapshot_id):
        raise ConfigError('Use an exact 64-character lowercase snapshot ID, never latest or a prefix.')
    target = Path(target).expanduser().absolute()
    if '..' in target.parts:
        raise ConfigError('Restore target must not contain parent traversal; use an explicit canonical quarantine path.')
    if target.exists() or target.is_symlink():
        raise ConfigError('Restore target must not exist; choose a fresh quarantine directory.')
    # Existing symlink ancestors may redirect extraction into a live data tree.
    if any(parent.is_symlink() for parent in target.parents):
        raise ConfigError('Restore target ancestors must not be symlinks.')
    if target == ROOT or ROOT in target.parents and target.parts[len(ROOT.parts)] != '.context':
        raise ConfigError('Keep restoration outside the checkout or inside its .context directory.')
    env, remote = repository_environment(ROOT, allow_local_repository)
    target.mkdir(mode=0o700, parents=True)
    previous_umask = os.umask(0o077)
    try:
        restic(['restore', snapshot_id, '--target', str(target), '--verify'], env)
        manifest, archives = validate_restore(target)
        # Validate every archive before extracting any of them.
        for archive, destination, members in archives:
            extract_archive(archive, destination, members)
    finally:
        os.umask(previous_umask)
    return {'schema_version': 1, 'observed_at': now(), 'snapshot_id': snapshot_id,
            'services': [item['service'] for item in manifest['services']],
            'source_commit': manifest.get('source_commit'), 'local_test_only': not remote,
            'status': 'RESTORED_QUARANTINED', 'production_started': False,
            'next_action': 'Verify application state using docs/recovery.md; numeric owners remain in the preserved tar archives.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot_id')
    parser.add_argument('target')
    parser.add_argument('--allow-local-repository', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        reject_root()
        with command_lock():
            result = restore_snapshot(args.snapshot_id, args.target, args.allow_local_repository)
        print(json.dumps(result) if args.json else 'Restored and verified in quarantine. No production services were started; follow docs/recovery.md.')
        return 0
    except (ConfigError, OSError, ValueError) as exc:
        print(str(exc) if isinstance(exc, ConfigError) else 'Restore failed; inspect quarantined files and storage permissions.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
