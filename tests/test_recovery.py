#!/usr/bin/env python3
"""Failure recovery, mount identities, archive boundaries and real encryption."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT_PATHS = [str(REPOSITORY / 'scripts')]
if not (REPOSITORY / 'scripts/lib/config.py').exists():
    SCRIPT_PATHS.append(str(REPOSITORY.parents[2] / 'scripts'))
sys.path[:0] = SCRIPT_PATHS
import backup
import restore
from lib import recovery
from lib.config import ConfigError

SNAPSHOT = 'b' * 64


def completed(output=''):
    return subprocess.CompletedProcess([], 0, output, '')


def make_tar(path, members=None):
    with tarfile.open(path, 'w') as archive:
        if members is None:
            info = tarfile.TarInfo('state.txt')
            info.size = len(b'recovery-fixture-sensitive')
            info.uid = 1234
            info.gid = 5678
            info.mode = 0o640
            archive.addfile(info, io.BytesIO(b'recovery-fixture-sensitive'))
        else:
            for info in members:
                archive.addfile(info)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'checkout'
        self.root.mkdir()
        (self.root / 'local').mkdir()
        (self.root / 'config').mkdir()
        self.env_file = self.root / '.env'
        self.env_file.write_text('COMPOSE_PROJECT_NAME=fixture\n')
        self.env_file.chmod(0o600)
        self.password = self.base / 'password'
        self.password.write_text('test-only-encryption-credential\n')
        self.password.chmod(0o600)
        self.repository = self.base / 'encrypted'
        cfg = self.root / 'local/backup.env'
        cfg.write_text('RESTIC_REPOSITORY=' + str(self.repository) + '\nRESTIC_PASSWORD_FILE=' + str(self.password) + '\n')
        cfg.chmod(0o600)
        self.policy = {'schema_version': 1, 'services': {
            'app': [{'target': '/data', 'kind': 'essential', 'consistency': 'stop'}]}}
        (self.root / 'config/state-policy.json').write_text(json.dumps(self.policy))
        self.model = {'services': {'app': {'volumes': [
            {'type': 'volume', 'source': 'app_data', 'target': '/data'}]}},
            'volumes': {'app_data': {'name': 'existing_volume_identity'}}}
        self.details = {'id': 'c' * 64, 'running': True, 'image_id': 'sha256:' + 'd' * 64,
                        'image_reference': 'fixture/image:1', 'project': 'fixture', 'service': 'app',
                        'mounts': [{'Type': 'volume', 'Name': 'existing_volume_identity',
                                    'Source': '/var/lib/docker/volumes/existing_volume_identity/_data',
                                    'Destination': '/data', 'RW': True}]}
        self.events = []
        self.patches = [mock.patch.object(backup, 'ROOT', self.root),
                        mock.patch.object(restore, 'ROOT', self.root),
                        mock.patch.object(backup, 'load_env', lambda: {'COMPOSE_PROJECT_NAME': 'fixture'}),
                        mock.patch.object(backup, 'compose_model', lambda: self.model),
                        mock.patch.object(backup, 'docker', self.docker),
                        mock.patch.object(backup, 'copy_archive', self.copy),
                        mock.patch.object(backup, 'source_commit', lambda: 'a' * 40),
                        mock.patch.object(backup, 'run_compose', lambda *a: completed('app\n'))]
        for patch in self.patches:
            patch.start()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: [patch.stop() for patch in reversed(self.patches)])

    def docker(self, *args, **kwargs):
        self.events.append(args[0])
        if args[0] == 'ps':
            return completed('c' * 12 + '\n')
        if args[0] == 'inspect':
            return completed(json.dumps(self.details))
        if args[:2] == ('image', 'inspect'):
            return completed(json.dumps(['fixture/image@sha256:' + 'd' * 64]))
        return completed()

    def copy(self, container, target, archive):
        self.events.append('copy')
        make_tar(archive)

    def fake_restic(self, args, env, cwd=None):
        self.events.append('restic-' + args[0])
        if args[0] == 'backup':
            self.assertLess(self.events.index('start'), len(self.events) - 1)
            return completed(json.dumps({'message_type': 'summary', 'snapshot_id': SNAPSHOT}))
        if args[0] == 'snapshots':
            return completed(json.dumps([{'id': SNAPSHOT}] if SNAPSHOT in args else []))
        self.fail('unexpected restic operation')

    def test_local_repository_requires_explicit_test_flag(self):
        with self.assertRaisesRegex(ConfigError, 'off-device'):
            backup.create_backup(['app'])
        self.assertNotIn('stop', self.events)

    def test_backup_restarts_before_upload_and_private_marker(self):
        with mock.patch.object(backup, 'restic', self.fake_restic):
            result = backup.create_backup(['app'], allow_local_repository=True)
        self.assertEqual(result['snapshot_id'], SNAPSHOT)
        self.assertTrue(result['local_test_only'])
        self.assertFalse((self.root / 'local/backup-stage').exists())
        self.assertEqual((self.root / 'local/last-backup.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.events.count('stop'), 1)
        self.assertEqual(self.events.count('start'), 1)

    def test_failed_copy_still_restarts_and_does_not_mark_success(self):
        with mock.patch.object(backup, 'restic', self.fake_restic), mock.patch.object(backup, 'copy_archive', side_effect=ConfigError('copy failed')):
            with self.assertRaises(ConfigError):
                backup.create_backup(['app'], allow_local_repository=True)
        self.assertIn('start', self.events)
        self.assertNotIn('restic-backup', self.events)
        self.assertFalse((self.root / 'local/backup-stage').exists())
        self.assertFalse((self.root / 'local/last-backup.json').exists())

    def per_service_records(self):
        return [{'service': name, 'container_id': name + '-id', 'was_running': True,
                 'mounts': [{'target': '/data', 'kind': 'essential', 'consistency': 'stop'}]}
                for name in ('pihole', 'webtop')]

    def test_each_writer_restarts_before_next_service_is_paused(self):
        events = []
        records = self.per_service_records()
        def docker(*args, **kwargs):
            events.append((args[0], args[-1]))
            return completed()
        def copy(container, target, archive):
            events.append(('copy', container))
            make_tar(archive)
        def restic(args, env, cwd=None):
            if args[0] == 'backup':
                events.append(('upload', 'all'))
                return completed(json.dumps({'message_type': 'summary', 'snapshot_id': SNAPSHOT}))
            return completed(json.dumps([{'id': SNAPSHOT}] if SNAPSHOT in args else []))
        with mock.patch.object(backup, 'inventory', return_value=records), mock.patch.object(backup, 'docker', side_effect=docker), mock.patch.object(backup, 'copy_archive', side_effect=copy), mock.patch.object(backup, 'restic', side_effect=restic):
            backup.create_backup(['pihole', 'webtop'], allow_dns_interruption=True, allow_local_repository=True)
        self.assertEqual(events, [('stop', 'pihole-id'), ('copy', 'pihole-id'), ('start', 'pihole-id'),
                                  ('stop', 'webtop-id'), ('copy', 'webtop-id'), ('start', 'webtop-id'), ('upload', 'all')])
        self.assertTrue(all('capture_started_at' in row and 'captured_at' in row for row in records))

    def test_stop_failure_restarts_only_attempted_writer_and_leaves_future_service_untouched(self):
        events = []
        def docker(*args, **kwargs):
            events.append((args[0], args[-1]))
            if args[0] == 'stop':
                raise ConfigError('stop timed out')
            return completed()
        with mock.patch.object(backup, 'inventory', return_value=self.per_service_records()), mock.patch.object(backup, 'docker', side_effect=docker), mock.patch.object(backup, 'restic', side_effect=lambda *a, **kw: completed('[]')):
            with self.assertRaises(ConfigError):
                backup.create_backup(['pihole', 'webtop'], allow_dns_interruption=True, allow_local_repository=True)
        self.assertEqual(events, [('stop', 'pihole-id'), ('start', 'pihole-id')])
        self.assertFalse((self.root / 'local/last-backup.json').exists())

    def test_later_copy_failure_leaves_previously_archived_dns_running(self):
        events = []
        def docker(*args, **kwargs):
            events.append((args[0], args[-1]))
            return completed()
        def copy(container, target, archive):
            events.append(('copy', container))
            if container == 'webtop-id':
                raise ConfigError('copy failed')
            make_tar(archive)
        with mock.patch.object(backup, 'inventory', return_value=self.per_service_records()), mock.patch.object(backup, 'docker', side_effect=docker), mock.patch.object(backup, 'copy_archive', side_effect=copy), mock.patch.object(backup, 'restic', side_effect=lambda *a, **kw: completed('[]')):
            with self.assertRaises(ConfigError):
                backup.create_backup(['pihole', 'webtop'], allow_dns_interruption=True, allow_local_repository=True)
        self.assertEqual(events, [('stop', 'pihole-id'), ('copy', 'pihole-id'), ('start', 'pihole-id'),
                                  ('stop', 'webtop-id'), ('copy', 'webtop-id'), ('start', 'webtop-id')])
        self.assertFalse((self.root / 'local/last-backup.json').exists())

    def test_failed_upload_keeps_service_running_without_success_marker(self):
        def fail(args, env, cwd=None):
            if args[0] == 'backup':
                raise ConfigError('incomplete backup')
            return self.fake_restic(args, env, cwd)
        with mock.patch.object(backup, 'restic', fail):
            with self.assertRaises(ConfigError):
                backup.create_backup(['app'], allow_local_repository=True)
        self.assertEqual(self.events.count('start'), 1)
        self.assertFalse((self.root / 'local/last-backup.json').exists())

    def test_stopped_writer_is_not_started(self):
        self.details['running'] = False
        with mock.patch.object(backup, 'restic', lambda a, e, cwd=None: completed(json.dumps({'message_type': 'summary', 'snapshot_id': SNAPSHOT})) if a[0] == 'backup' else completed(json.dumps([{'id': SNAPSHOT}] if SNAPSHOT in a else []))):
            backup.create_backup(['app'], allow_local_repository=True)
        self.assertNotIn('stop', self.events)
        self.assertNotIn('start', self.events)

    def test_unknown_mount_and_wrong_named_volume_fail_before_stop(self):
        self.details['mounts'].append({'Type': 'volume', 'Name': 'unclassified', 'Source': '/unknown', 'Destination': '/other', 'RW': True})
        with mock.patch.object(backup, 'restic', self.fake_restic):
            with self.assertRaisesRegex(ConfigError, 'Unclassified'):
                backup.create_backup(['app'], allow_local_repository=True)
        self.assertNotIn('stop', self.events)
        self.details['mounts'].pop()
        self.details['mounts'][0]['Name'] = 'replacement-empty-volume'
        with mock.patch.object(backup, 'restic', self.fake_restic):
            with self.assertRaisesRegex(ConfigError, 'identity'):
                backup.create_backup(['app'], allow_local_repository=True)

    def test_dns_stop_requires_explicit_continuity_acknowledgement(self):
        self.model['services']['pihole'] = self.model['services'].pop('app')
        self.details['service'] = 'pihole'
        self.policy['services']['pihole'] = self.policy['services'].pop('app')
        (self.root / 'config/state-policy.json').write_text(json.dumps(self.policy))
        with mock.patch.object(backup, 'restic', self.fake_restic):
            with self.assertRaisesRegex(ConfigError, 'DNS continuity'):
                backup.create_backup(['pihole'], allow_local_repository=True)
        self.assertNotIn('stop', self.events)

    def test_restore_refuses_existing_destination_and_short_snapshot(self):
        with self.assertRaisesRegex(ConfigError, '64-character'):
            restore.restore_snapshot('latest', self.base / 'new')
        with self.assertRaisesRegex(ConfigError, 'must not exist'):
            restore.restore_snapshot(SNAPSHOT, self.base, True)

    def test_tar_path_and_link_escapes_and_devices_are_refused(self):
        cases = []
        traversal = tarfile.TarInfo('../escape')
        cases.append([traversal])
        absolute = tarfile.TarInfo('/absolute')
        cases.append([absolute])
        link = tarfile.TarInfo('link'); link.type = tarfile.SYMTYPE; link.linkname = '../outside'
        cases.append([link])
        parent = tarfile.TarInfo('dir'); parent.type = tarfile.SYMTYPE; parent.linkname = 'other'
        child = tarfile.TarInfo('dir/file')
        cases.append([parent, child])
        device = tarfile.TarInfo('device'); device.type = tarfile.CHRTYPE
        cases.append([device])
        for index, members in enumerate(cases):
            with self.subTest(index=index):
                path = self.base / (str(index) + '.tar')
                make_tar(path, members)
                with self.assertRaises(ConfigError):
                    recovery.archive_members(path)

    def test_corrupt_archive_fails_checksum_before_extraction(self):
        target = self.base / 'restore'
        (target / 'archives').mkdir(parents=True)
        archive = target / 'archives/app-0.tar'
        make_tar(archive)
        manifest = {'schema_version': 1, 'services': [{'service': 'app', 'mounts': [
            {'archive': 'archives/app-0.tar', 'sha256': '0' * 64, 'restore_path': 'state/app/0'}]}]}
        (target / 'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ConfigError, 'checksum'):
            restore.validate_restore(target)
        self.assertFalse((target / 'state').exists())

    def test_real_restic_encrypted_backup_restore(self):
        binary = shutil.which('restic')
        if binary is None:
            candidates = [REPOSITORY / '.context/implementation/restic', REPOSITORY.parent / 'restic']
            binary = next((str(path) for path in candidates if path.is_file()), None)
        if binary is None:
            self.skipTest('restic is unavailable; install restic to run the real encrypted fixture')
        bindir = self.base / 'bin'; bindir.mkdir()
        (bindir / 'restic').symlink_to(binary)
        with mock.patch.dict(os.environ, {'PATH': str(bindir) + os.pathsep + os.environ['PATH']}):
            env, _ = recovery.repository_environment(self.root, True)
            recovery.restic(['init'], env)
            result = backup.create_backup(['app'], allow_local_repository=True)
            destination = self.base / 'restored'
            restored = restore.restore_snapshot(result['snapshot_id'], destination, True)
            self.assertFalse(restored['production_started'])
            self.assertEqual((destination / 'state/app/0/state.txt').read_bytes(), b'recovery-fixture-sensitive')
            with tarfile.open(destination / 'archives/app-0.tar') as archive:
                self.assertEqual(archive.getmember('state.txt').uid, 1234)
                self.assertEqual(archive.getmember('state.txt').gid, 5678)
            self.assertEqual((destination / 'config/.env').stat().st_mode & 0o777, 0o600)
            for path in self.repository.rglob('*'):
                if path.is_file():
                    self.assertNotIn(b'recovery-fixture-sensitive', path.read_bytes())
            recovery.restic(['check', '--read-data'], env)


if __name__ == '__main__':
    unittest.main()
