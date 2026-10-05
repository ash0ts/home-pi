#!/usr/bin/env python3
"""Apply an explicitly reviewed checkout to one scope with a verified backup."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
from lib.config import ConfigError, ROOT, atomic_write, command_lock, docker, load_env, reject_root, run_compose
from backup import create_backup, inventory, state_policy

REVISION = re.compile(r'^[0-9a-f]{40}$')
IMAGE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}$')
SERVICE = re.compile(r'^[a-z][a-z0-9-]*$')
CORE = {'pihole', 'tailscale', 'homer'}
WATCHTOWER_FIELDS = ('{"id":{{json .Id}},"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
                    '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
                    '"running":{{json .State.Running}},"restart":{{json .HostConfig.RestartPolicy.Name}},'
                    '"image_id":{{json .Image}}}')


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def git(*args):
    result = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ConfigError('Git revision verification failed; use a reviewed full commit already present in this checkout.')
    return result.stdout.strip()


def verify_revision(revision, previous=None):
    if not REVISION.fullmatch(revision or '') or (previous and not REVISION.fullmatch(previous)):
        raise ConfigError('Supply full lowercase 40-character commit IDs; mutable branches/tags are not update approval.')
    if git('rev-parse', '--verify', revision + '^{commit}') != revision or git('rev-parse', 'HEAD') != revision:
        raise ConfigError('The requested revision must exactly match the checked-out HEAD. Review and check out the candidate yourself before updating.')
    if git('status', '--porcelain', '--untracked-files=all'):
        raise ConfigError('The checkout has uncommitted code changes. Commit and review the exact candidate before updating; private ignored state is allowed.')
    if previous and git('rev-parse', '--verify', previous + '^{commit}') != previous:
        raise ConfigError('The previous deployment revision must be an existing full commit.')


def static_validation():
    result = subprocess.run([str(ROOT / 'scripts/validate.sh')], cwd=ROOT, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise ConfigError('Static candidate validation failed; fix its dummy configuration/lint checks before updating.')


def selected_model():
    from modules import selected, validate
    from service_config import check_compose_version, validate_services, check_ownership
    from access import validate_access
    check_compose_version(docker('compose', 'version', '--short').stdout)
    model = validate(selected())
    env = load_env()
    validate_services(env, model['services'])
    check_ownership(env, model['services'])
    validate_access(model, env)
    return model


def configuration_fingerprint(model):
    """Keep secret/configuration hashes in memory; never include them in reports."""
    paths = {ROOT / '.env', ROOT / 'local/selection.json'}
    active_secrets = set()
    for spec in model.get('services', {}).values():
        for secret in spec.get('secrets', []):
            name = secret if isinstance(secret, str) else secret.get('source')
            if not isinstance(name, str):
                raise ConfigError('Invalid active Compose secret reference.')
            active_secrets.add(name)
    for name in active_secrets:
        secret = model.get('secrets', {}).get(name, {})
        if not isinstance(secret, dict) or not isinstance(secret.get('file'), str):
            raise ConfigError('Updates require file-backed active Compose secrets with a stable private source.')
        path = Path(secret['file'])
        paths.add(path if path.is_absolute() else ROOT / path)
    result = {}
    for path in sorted(paths):
        try:
            before = path.lstat()
            if not stat.S_ISREG(before.st_mode):
                raise ConfigError('Update configuration and secret sources must be regular files, not symlinks.')
            checksum = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    checksum.update(block)
            after = path.lstat()
            if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                raise ConfigError('Private configuration changed while it was being checked; retry after completing edits.')
            result[str(path)] = checksum.digest()
        except OSError:
            raise ConfigError('An update configuration or active secret source is unavailable; no secret values were printed.') from None
    return result


def update_scope(model, services=None, module=None):
    if bool(services) == bool(module):
        raise ConfigError('Choose explicit --services IDs or one --module ID.')
    if module:
        from modules import selected, resolve, metadata_for_services
        if module not in selected():
            raise ConfigError('The update module must already be selected.')
        services = list(metadata_for_services(resolve([module])))
    if not isinstance(services, list) or not services or any(not isinstance(name, str) or not SERVICE.fullmatch(name) for name in services):
        raise ConfigError('An explicit nonempty list of valid services is required.')
    chosen = set(services)
    if chosen - set(model['services']):
        raise ConfigError('An update service is absent from the selected model; enable/reconcile its module first.')
    # Namespace owners and consumers must be recreated together. This handles
    # Gluetun/Webtop without hard-coding a browser-specific update branch.
    changed = True
    while changed:
        changed = False
        for name, spec in model['services'].items():
            mode = spec.get('network_mode', '')
            if not mode.startswith('service:'):
                continue
            owner = mode.split(':', 1)[1]
            if owner not in model['services']:
                raise ConfigError('A service network namespace owner is missing from the selected model.')
            if chosen & {name, owner} and not {name, owner} <= chosen:
                chosen.update((name, owner))
                changed = True
    if chosen & CORE and chosen - CORE:
        raise ConfigError('Update core DNS/remote-access/portal and optional applications in separate operations.')
    for name in chosen:
        image = model['services'][name].get('image', '')
        if not isinstance(image, str) or not IMAGE.fullmatch(image) or model['services'][name].get('build'):
            raise ConfigError('Every updated service requires a reviewed immutable sha256 image reference; local builds and mutable tags are refused.')
    return sorted(chosen)


def watchtower_inventory(project):
    identifiers = docker('ps', '--all', '--filter', 'label=com.docker.compose.project=' + project,
                         '--filter', 'label=com.docker.compose.service=watchtower', '--format', '{{.ID}}').stdout.split()
    if len(identifiers) > 1:
        raise ConfigError('Multiple project Watchtower containers found; resolve the exact inventory before retirement.')
    if not identifiers:
        return None
    try:
        record = json.loads(docker('inspect', '--format', WATCHTOWER_FIELDS, identifiers[0]).stdout)
    except ValueError:
        raise ConfigError('Invalid Watchtower ownership inventory.') from None
    if not isinstance(record, dict) or record.get('project') != project or record.get('service') != 'watchtower' or not isinstance(record.get('id'), str) or not re.fullmatch(r'[a-f0-9]{12,64}', record['id']) or type(record.get('running')) is not bool:
        raise ConfigError('Watchtower ownership could not be verified; no container was stopped.')
    return record


def retire_watchtower(project):
    record = watchtower_inventory(project)
    result = {'schema_version': 1, 'observed_at': now(), 'project': project,
              'operation': 'retire-watchtower', 'status': 'NEEDS_CONFIGURATION', 'container': record}
    atomic_write(ROOT / 'local/watchtower-retirement.json', json.dumps(result, indent=2) + '\n')
    if record:
        # Stop alone is insufficient: an always restart policy may return after
        # daemon/host restart. Change only the exact verified container.
        docker('update', '--restart=no', record['id'])
        if record['running']:
            docker('stop', '--time', '30', record['id'], timeout=90)
        verified = watchtower_inventory(project)
        if not verified or verified['id'] != record['id'] or verified['running'] or verified.get('restart') not in ('no', ''):
            result['status'] = 'FAIL'
            atomic_write(ROOT / 'local/watchtower-retirement.json', json.dumps(result, indent=2) + '\n')
            raise ConfigError('Watchtower retirement was not verified. Check the exact project container before continuing.')
    result['status'] = 'PASS'
    atomic_write(ROOT / 'local/watchtower-retirement.json', json.dumps(result, indent=2) + '\n')
    return result


def deployment_state():
    path = ROOT / 'local/current-deployment.json'
    if not path.exists():
        return {'schema_version': 1, 'services': {}}
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ConfigError('Deployment state must be a private regular mode0600 file.')
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or type(data.get('schema_version')) is not int or data['schema_version'] != 1 or not isinstance(data.get('services'), dict):
            raise ValueError()
        for name, row in data['services'].items():
            if not SERVICE.fullmatch(name) or not isinstance(row, dict) or not REVISION.fullmatch(row.get('source_commit', '')) or not isinstance(row.get('image_id'), str):
                raise ValueError()
        return data
    except (ValueError, TypeError):
        raise ConfigError('Invalid private deployment marker; verify inventory before updating.') from None


def prior_revisions(records, previous_revision=None):
    state = deployment_state()
    previous = {}
    for record in records:
        old = state['services'].get(record['service'])
        if old:
            if old['image_id'] != record['image_id']:
                raise ConfigError('Installed image differs from its deployment marker; reconcile unreviewed changes before updating.')
            if previous_revision and previous_revision != old['source_commit']:
                raise ConfigError('Explicit previous revision disagrees with recorded installed state.')
            previous[record['service']] = old['source_commit']
        elif previous_revision:
            previous[record['service']] = previous_revision
        else:
            raise ConfigError('Initial migration needs --previous-revision FULL40 from the retained installed-code inventory. Do not infer it from candidate HEAD.')
    return state, previous


def record_update(record, history):
    record['observed_at'] = now()
    text = json.dumps(record, indent=2) + '\n'
    atomic_write(history, text)
    atomic_write(ROOT / 'local/last-update.json', text)


def doctor(services, seconds):
    result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/doctor.py'), '--json', '--wait', str(min(seconds, 300)), '--services', *services],
                            cwd=ROOT, capture_output=True, text=True, timeout=min(seconds, 300) + 120)
    if result.returncode:
        raise ConfigError('Updated services did not pass scoped doctor checks; consult the recorded recovery steps.')


def apply_update(revision, services=None, module=None, previous_revision=None, allow_dns_interruption=False, wait_seconds=300, retire=False):
    verify_revision(revision, previous_revision)
    static_validation()
    model = selected_model()
    fingerprint = configuration_fingerprint(model)
    services = update_scope(model, services, module)
    env = load_env()
    project = env['COMPOSE_PROJECT_NAME']
    updater = watchtower_inventory(project)
    if updater and updater['running'] and not retire:
        raise ConfigError('Project Watchtower is still active. Explicitly retire it with --retire-watchtower before the reviewed update.')
    records = inventory(model, services, project, state_policy())
    if any(not record['was_running'] for record in records):
        raise ConfigError('Update scope contains stopped services. They were preserved; deliberately start/re-enable them before an update, or choose only running services.')
    deployment, previous = prior_revisions(records, previous_revision)
    if 'pihole' in services and not allow_dns_interruption:
        raise ConfigError('Arrange household DNS continuity before using --allow-dns-interruption for a Pi-hole update.')
    identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
    history = ROOT / 'local/update-history' / (identifier + '.json')
    record = {'schema_version': 1, 'operation': 'update', 'status': 'NEEDS_CONFIGURATION', 'started_at': now(),
              'source_commit': revision, 'previous_source_commits': previous, 'project': project,
              'services': services, 'snapshot_id': None, 'phase': 'validated',
              'previous_images': {row['service']: {'image_id': row['image_id'], 'reference': row['image_reference'], 'repo_digests': row['repo_digests']} for row in records},
              'next_action': 'No candidate images applied yet.'}
    record_update(record, history)
    try:
        if retire:
            retire_watchtower(project)
        if configuration_fingerprint(model) != fingerprint:
            raise ConfigError('Private configuration changed before backup; retry after reviewing the intended configuration.')
        record['phase'] = 'backup'
        record_update(record, history)
        backup = create_backup(services=services, allow_dns_interruption=allow_dns_interruption, allow_local_repository=False)
        snapshot = backup.get('snapshot_id', '')
        if not re.fullmatch(r'[0-9a-f]{64}', snapshot) or backup.get('local_test_only') or not backup.get('off_device_required') or sorted(backup.get('services', [])) != services:
            raise ConfigError('An exact verified off-device backup of the update scope is required before pulling images.')
        record['snapshot_id'] = snapshot
        record['phase'] = 'pull'
        record_update(record, history)
        run_compose('pull', *services, timeout=1800)
        # The local candidate can be edited while a long backup/pull runs.
        verify_revision(revision, previous_revision)
        if configuration_fingerprint(model) != fingerprint:
            raise ConfigError('Private configuration or an active secret changed after backup; no candidate containers were recreated.')
        if selected_model() != model:
            raise ConfigError('The selected Compose model changed after backup; no candidate containers were recreated.')
        record['phase'] = 'recreate'
        record_update(record, history)
        run_compose('up', '-d', '--no-deps', '--no-build', '--force-recreate', '--pull', 'never', '--wait', '--wait-timeout', str(wait_seconds), *services, timeout=wait_seconds + 120)
        record['phase'] = 'readiness'
        record_update(record, history)
        doctor(services, wait_seconds)
        after = inventory(model, services, project, state_policy())
        for row in after:
            if not row['was_running']:
                raise ConfigError('A selected service stopped after readiness checks.')
            if row['image_reference'] != model['services'][row['service']]['image']:
                raise ConfigError('A running image reference differs from the reviewed immutable candidate.')
            deployment['services'][row['service']] = {'source_commit': revision, 'image_id': row['image_id'], 'repo_digests': row['repo_digests']}
        atomic_write(ROOT / 'local/current-deployment.json', json.dumps(deployment, indent=2) + '\n')
        record.update(status='PASS', phase='complete', completed_at=now(),
                      next_action='Verify the affected live client flows; retain the matching snapshot, previous images, and revision for recovery.')
        record_update(record, history)
        return record
    except (ConfigError, OSError, ValueError, subprocess.SubprocessError):
        record.update(status='FAIL', failed_at=now(),
                      next_action='Inspect scoped doctor and retained inventory. Keep current data. If recovery is needed, stop only affected writers deliberately, restore the recorded matching snapshot into an isolated target, and follow docs/updates.md; do not downgrade images over migrated data.')
        record_update(record, history)
        raise ConfigError('Update failed; private local/last-update.json records the phase, prior images, and matching snapshot. Candidate state was retained for deliberate service-specific recovery.') from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', '--candidate', dest='revision')
    parser.add_argument('--previous-revision')
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument('--services', nargs='+')
    scope.add_argument('--module')
    parser.add_argument('--retire-watchtower', action='store_true')
    parser.add_argument('--allow-dns-interruption', action='store_true')
    parser.add_argument('--wait-seconds', type=int, default=300)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        reject_root()
        if not 1 <= args.wait_seconds <= 21600:
            raise ConfigError('--wait-seconds must be between 1 and 21600; choose a documented migration window.')
        standalone_retire = args.retire_watchtower and not args.revision and not args.services and not args.module
        if not standalone_retire and (not args.revision or not (args.services or args.module)):
            raise ConfigError('Use --revision FULL40 with --services or --module, or standalone --retire-watchtower.')
        if args.dry_run:
            print(json.dumps({'status': 'NEEDS_CONFIGURATION', 'dry_run': True, 'requested_services': args.services, 'requested_module': args.module,
                              'steps': ['verify reviewed checkout and scoped running inventory', 'retire exact project updater only if requested', 'verify off-device backup', 'pull pinned selected images', 'recreate namespace-related selected services only', 'run scoped doctor and retain recovery record'],
                              'next_action': 'Dry run invoked no external commands or writes; use the actual review/migration procedure before applying.'}))
            return 0
        with command_lock():
            if standalone_retire:
                result = retire_watchtower(load_env()['COMPOSE_PROJECT_NAME'])
            else:
                result = apply_update(args.revision, args.services, args.module, args.previous_revision, args.allow_dns_interruption, args.wait_seconds, args.retire_watchtower)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print('PASS: requested maintenance completed; retain the private operation record and verify live client behavior.')
        return 0
    except (ConfigError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(str(exc) if isinstance(exc, ConfigError) else 'Update operation failed; private diagnostics were suppressed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
