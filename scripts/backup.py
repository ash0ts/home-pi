#!/usr/bin/env python3
"""Stop selected writers briefly, archive exact mounts, and encrypt with restic."""
import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

from lib.config import (ROOT, ConfigError, atomic_write, command_lock, docker,
                        load_env, reject_root, run_compose)
from lib.recovery import (SERVICE_RE, SNAPSHOT_RE, archive_members, digest, now,
                          repository_environment, restic)
from service_config import active_file_secrets

SYSTEM_BINDS = {('/var/run/docker.sock', '/var/run/docker.sock'),
                ('/dev/net/tun', '/dev/net/tun')}
PRIVATE_CONFIG = ('.env', 'local/selection.json', 'local/routes-owned.json',
                  'local/backup.env', 'local/notify.env', 'local/home-network.md',
                  'local/access-enrollment.json', 'local/storage.json',
                  'local/current-deployment.json')
INSPECT = ('{"id":{{json .Id}},"running":{{json .State.Running}},'
           '"image_id":{{json .Image}},"image_reference":{{json .Config.Image}},'
           '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
           '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
           '"mounts":{{json .Mounts}}}')


def compose_model():
    # E1 can supply the selected ordered module file list through run_compose.
    return json.loads(run_compose('config', '--format', 'json').stdout)


def state_policy():
    try:
        value = json.loads((ROOT / 'config/state-policy.json').read_text())
    except (OSError, ValueError) as exc:
        raise ConfigError('Backup state policy is missing or invalid.') from exc
    if value.get('schema_version') != 1 or not isinstance(value.get('services'), dict):
        raise ConfigError('Unsupported backup state-policy schema.')
    from modules import metadata_for_services
    for service, metadata in metadata_for_services().items():
        if service in value['services']:
            raise ConfigError('Duplicate state policy between core and selected module.')
        value['services'][service] = [{**{key: val for key, val in row.items() if key != 'service'},
                                     **({'exclude': True} if row['kind'] == 'cache' and row.get('reason') else {})}
                                    for row in metadata['state']]
    return value['services']


def inventory(model, services, project, policies):
    result = []
    for service in services:
        if not SERVICE_RE.fullmatch(service) or service not in model['services']:
            raise ConfigError('Selected backup service is not in the managed Compose model.')
        if service not in policies:
            raise ConfigError('Selected service lacks an explicit backup state policy.')
        ids = docker('ps', '--all', '--filter', 'label=com.docker.compose.project=' + project,
                     '--filter', 'label=com.docker.compose.service=' + service,
                     '--format', '{{.ID}}').stdout.split()
        if len(ids) != 1:
            raise ConfigError('Backup requires exactly one existing container for each selected service; inventory and resolve missing/duplicate containers first.')
        details = json.loads(docker('inspect', '--format', INSPECT, ids[0]).stdout)
        if details.get('project') != project or details.get('service') != service:
            raise ConfigError('Container ownership changed during backup inventory.')
        policy_by_target = {}
        for policy in policies[service]:
            target = policy.get('target', '')
            if (not target.startswith('/') or '..' in Path(target).parts or
                    target in policy_by_target or policy.get('consistency') != 'stop' or
                    policy.get('kind') not in {'essential', 'history', 'cache'}):
                raise ConfigError('Invalid backup state policy; use unique absolute mount targets and stop consistency.')
            if policy.get('exclude') and (policy['kind'] != 'cache' or not policy.get('reason')):
                raise ConfigError('Only explicitly documented regenerable cache can be excluded.')
            policy_by_target[target] = policy
        declared = {mount['target']: mount for mount in model['services'][service].get('volumes', [])}
        mounts = []
        actual_targets = set()
        for actual in details['mounts']:
            target = actual.get('Destination', '')
            if not actual.get('RW'):
                continue
            if (actual.get('Source'), target) in SYSTEM_BINDS:
                continue
            if actual.get('Type') not in {'bind', 'volume'}:
                raise ConfigError('A writable container mount has no supported backup adapter.')
            if target not in declared or target not in policy_by_target:
                raise ConfigError('Unclassified writable persistent mount found; add its state policy before backup.')
            expected = declared[target]
            if expected.get('read_only') or expected.get('type') != actual['Type']:
                raise ConfigError('Running mounts differ from the Compose model; reconcile without replacing data.')
            if actual['Type'] == 'bind':
                if Path(expected['source']).resolve() != Path(actual['Source']).resolve():
                    raise ConfigError('Running bind source differs from the configured path; inventory the installed state first.')
            else:
                volume_key = expected.get('source')
                volume = model.get('volumes', {}).get(volume_key, {})
                expected_name = volume.get('name') or project + '_' + str(volume_key)
                if actual.get('Name') != expected_name:
                    raise ConfigError('Running named-volume identity differs from the configured project; migration is required.')
            actual_targets.add(target)
            mounts.append({**policy_by_target[target], 'type': actual['Type'],
                           'source': actual['Source'], 'volume_name': actual.get('Name')})
        if set(policy_by_target) - actual_targets:
            raise ConfigError('A declared state mount is missing or read-only in the installed container; resolve inventory before backup.')
        digests = json.loads(docker('image', 'inspect', '--format', '{{json .RepoDigests}}', details['image_id']).stdout or '[]')
        result.append({'service': service, 'container_id': details['id'],
                       'was_running': details['running'], 'image_id': details['image_id'],
                       'image_reference': details['image_reference'], 'repo_digests': digests or [],
                       'mounts': mounts})
    return result


def copy_archive(container, target, archive):
    prefix = ['sudo', '-n', 'docker'] if os.environ.get('PI_DOCKER_SUDO') == '1' else ['docker']
    child = os.environ.copy()
    for key in ('COMPOSE_FILE', 'COMPOSE_PROFILES', 'COMPOSE_PROJECT_NAME', 'COMPOSE_ENV_FILES'):
        child.pop(key, None)
    for key in load_env(required=False):
        child.pop(key, None)
    try:
        with archive.open('xb') as output:
            os.fchmod(output.fileno(), 0o600)
            copied = subprocess.run(prefix + ['cp', '-a', container + ':' + target.rstrip('/') + '/.', '-'],
                                    stdout=output, stderr=subprocess.PIPE, cwd=ROOT, env=child, timeout=1800)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ConfigError('State archive copy failed; selected writers will be restarted.') from exc
    if copied.returncode:
        raise ConfigError('Docker could not archive a state mount; selected writers will be restarted.')
    if archive.stat().st_size < 512:
        raise ConfigError('Docker returned an invalid empty archive.')


def copy_private_config(stage, model=None, services=None):
    files = []
    for relative in PRIVATE_CONFIG:
        source = ROOT / relative
        if not source.exists() and not source.is_symlink():
            if relative == '.env':
                raise ConfigError('The private .env configuration is required for recovery.')
            continue
        if not stat.S_ISREG(source.lstat().st_mode):
            raise ConfigError('Recovery configuration must use regular files, not symlinks.')
        target = stage / 'config' / relative
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        atomic_write(target, source.read_bytes(), 0o600)
        files.append({'path': str(target.relative_to(stage)), 'sha256': digest(target)})
    for index, (name, source) in enumerate(active_file_secrets(model or {}, services).items()):
        # Numeric quarantine paths never reuse an external source path. The
        # encrypted manifest records that path only for deliberate later recovery.
        target = stage / 'config' / 'compose-secrets' / str(index)
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        atomic_write(target, source.read_bytes(), 0o600)
        files.append({'path': str(target.relative_to(stage)), 'sha256': digest(target),
                      'compose_secret': name, 'source_path': str(source)})
    return files


def source_commit():
    result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def create_backup(services=None, allow_dns_interruption=False, allow_local_repository=False):
    env, remote = repository_environment(ROOT, allow_local_repository)
    # Verify credentials/repository before interrupting any service; init is explicit.
    restic(['snapshots', '--json'], env)
    model = compose_model()
    project = load_env()['COMPOSE_PROJECT_NAME']
    if services is None:
        services = sorted(set(run_compose('ps', '--all', '--orphans=false', '--services').stdout.split()))
    services = sorted(set(services))
    if not services:
        raise ConfigError('No managed installed services were selected for backup.')
    records = inventory(model, services, project, state_policy())
    writers = [record for record in records if record['was_running'] and
               any(not mount.get('exclude') for mount in record['mounts'])]
    if any(record['service'] == 'pihole' for record in writers) and not allow_dns_interruption:
        raise ConfigError('Pi-hole needs a brief consistent-backup stop. Arrange DNS continuity, then use --allow-dns-interruption.')
    stage = ROOT / 'local/backup-stage'
    if stage.exists() or stage.is_symlink():
        raise ConfigError('Backup staging already exists; inspect and remove stale private staging before retrying.')
    stage.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage.mkdir(mode=0o700)
    (stage / 'archives').mkdir(mode=0o700)
    previous_umask = os.umask(0o077)
    operation_error = None
    restart_failures = []
    result = None
    try:
        files = copy_private_config(stage, model, services)
        commit = source_commit()
        writer_services = {record['service'] for record in writers}
        for record in records:
            # Each application has independent state. Pause only its writer for
            # its own archives, so large optional data never extends DNS downtime.
            restart_required = record['service'] in writer_services
            record['capture_started_at'] = now()
            try:
                if restart_required:
                    docker('stop', '--time', '30', record['container_id'], timeout=90)
                for index, mount in enumerate(record['mounts']):
                    if mount.get('exclude'):
                        continue
                    name = record['service'] + '-' + str(index) + '.tar'
                    path = stage / 'archives' / name
                    copy_archive(record['container_id'], mount['target'], path)
                    archive_members(path)  # A success marker must describe archives this restore adapter can read.
                    mount.update(archive='archives/' + name, sha256=digest(path),
                                 restore_path='state/' + record['service'] + '/' + str(index))
                record['captured_at'] = now()
            finally:
                # A stop may time out after taking effect. Restore this originally
                # running writer even on stop/copy failure; untouched writers stay up.
                if restart_required:
                    try:
                        docker('start', record['container_id'], timeout=90)
                    except Exception:
                        restart_failures.append(record['service'])
            if restart_failures:
                raise ConfigError('State was archived but service restart failed; run doctor before retrying backup.')
        manifest = {'schema_version': 1, 'created_at': now(), 'project': project,
                    'source_commit': commit, 'services': records, 'configuration': files,
                    'ownership': 'Numeric UID/GID and modes remain authoritative in each tar archive.'}
        atomic_write(stage / 'manifest.json', json.dumps(manifest, indent=2) + '\n')
        # Relative inputs give stable snapshot paths independent of checkout location.
        response = restic(['backup', '--json', '--tag', 'home-pi', '--host', project,
                           'manifest.json', 'archives', 'config'], env, cwd=stage)
        summaries = []
        for line in response.stdout.splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if item.get('message_type') == 'summary':
                summaries.append(item)
        snapshot = summaries[-1].get('snapshot_id', '') if summaries else ''
        if not SNAPSHOT_RE.fullmatch(snapshot):
            raise ConfigError('Restic did not return an exact successful snapshot ID; no backup success was recorded.')
        verified = json.loads(restic(['snapshots', '--json', snapshot], env).stdout)
        if len(verified) != 1 or verified[0].get('id') != snapshot:
            raise ConfigError('The completed snapshot could not be verified in the repository.')
        result = {'schema_version': 1, 'observed_at': now(), 'snapshot_id': snapshot,
                  'services': services, 'source_commit': commit,
                  'off_device_required': remote, 'local_test_only': not remote}
    except Exception as exc:
        operation_error = exc
    finally:
        try:
            shutil.rmtree(stage)
        finally:
            os.umask(previous_umask)
    if restart_failures:
        raise ConfigError('Backup did not finish safely: service restart failed. Run doctor and restore service availability before retrying; no successful backup marker was written.')
    if operation_error is not None:
        if isinstance(operation_error, ConfigError):
            raise operation_error
        raise ConfigError('Backup failed; private error details were suppressed. Previously running writers were restarted.') from operation_error
    result['completed_at'] = now()
    result['observed_at'] = result['completed_at']
    atomic_write(ROOT / 'local/last-backup.json', json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--services', nargs='+')
    parser.add_argument('--allow-dns-interruption', action='store_true')
    parser.add_argument('--allow-local-repository', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        reject_root()
        with command_lock():
            result = create_backup(args.services, args.allow_dns_interruption, args.allow_local_repository)
        if args.json:
            print(json.dumps(result))
        else:
            print('Encrypted backup verified: ' + result['snapshot_id'])
            if result['local_test_only']:
                print('LOCAL TEST ONLY: this does not satisfy off-device recovery.')
        return 0
    except (ConfigError, OSError, ValueError) as exc:
        print(str(exc) if isinstance(exc, ConfigError) else 'Backup failed; check private configuration and storage permissions.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
