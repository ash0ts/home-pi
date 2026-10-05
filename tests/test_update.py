"""Reviewed updates use fake mutations and private temporary operation records."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import update
from lib.config import ConfigError

CANDIDATE = 'a' * 40
PREVIOUS = 'b' * 40
IMAGE = 'example/reader:1@sha256:' + '1' * 64
SNAPSHOT = 'c' * 64


def row(service='reader', running=True, candidate=False):
    return {'service': service, 'was_running': running, 'image_id': 'sha256:' + ('1' if candidate else '2') * 64,
            'image_reference': IMAGE if candidate else 'example/reader:old', 'repo_digests': ['example/reader@sha256:' + '2' * 64]}


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'local').mkdir()
        (self.root / '.env').write_text('COMPOSE_PROJECT_NAME=owned-pi\nSECRET=synthetic-private-value\n')
        (self.root / 'local/selection.json').write_text('{"schema_version":1,"modules":["reader"]}\n')
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(patch.stopall)
        patch.object(update, 'ROOT', self.root).start()
        patch.object(update, 'reject_root').start()
        patch.object(update, 'verify_revision').start()
        patch.object(update, 'static_validation').start()
        patch.object(update, 'selected_model', return_value={'services': {'reader': {'image': IMAGE}}}).start()
        patch.object(update, 'load_env', return_value={'COMPOSE_PROJECT_NAME': 'owned-pi'}).start()
        patch.object(update, 'watchtower_inventory', return_value=None).start()
        patch.object(update, 'state_policy', return_value={}).start()
        patch.object(update, 'inventory', side_effect=[[row()], [row(candidate=True)]]).start()
        self.events = []
        patch.object(update, 'create_backup', side_effect=self.backup).start()
        patch.object(update, 'run_compose', side_effect=self.compose).start()
        patch.object(update, 'doctor', side_effect=lambda *args: self.events.append('doctor')).start()

    def backup(self, **kwargs):
        self.events.append('backup')
        self.assertFalse(kwargs['allow_local_repository'])
        return {'snapshot_id': SNAPSHOT, 'services': ['reader'], 'off_device_required': True, 'local_test_only': False}

    def compose(self, *args, **kwargs):
        self.events.append(args)
        return SimpleNamespace(stdout='')

    def apply(self, **kwargs):
        return update.apply_update(CANDIDATE, services=['reader'], previous_revision=PREVIOUS, **kwargs)

    def test_backup_precedes_pull_and_scoped_recreate(self):
        result = self.apply()
        self.assertEqual(self.events[0], 'backup')
        self.assertEqual(self.events[1], ('pull', 'reader'))
        command = self.events[2]
        self.assertEqual(command[0], 'up')
        self.assertIn('--no-deps', command)
        self.assertIn('--force-recreate', command)
        self.assertIn('--wait-timeout', command)
        self.assertEqual(command[-1], 'reader')
        self.assertEqual(self.events[-1], 'doctor')
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['snapshot_id'], SNAPSHOT)
        path = self.root / 'local/last-update.json'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(list((self.root / 'local/update-history').glob('*.json'))), 1)

    def test_backup_failure_prevents_pull_and_records_safe_failure(self):
        with patch.object(update, 'create_backup', side_effect=ConfigError('SYNTHETIC-SECRET')):
            with self.assertRaises(ConfigError) as error:
                self.apply()
        self.assertNotIn('SYNTHETIC-SECRET', str(error.exception))
        self.assertEqual(self.events, [])
        record = json.loads((self.root / 'local/last-update.json').read_text())
        self.assertEqual(record['status'], 'FAIL')
        self.assertEqual(record['phase'], 'backup')
        self.assertIsNone(record['snapshot_id'])

    def test_bad_pull_stops_before_recreate_and_preserves_snapshot(self):
        def fail(*args, **kwargs):
            self.events.append(args)
            raise ConfigError('SYNTHETIC-SECRET')
        with patch.object(update, 'run_compose', side_effect=fail), self.assertRaises(ConfigError):
            self.apply()
        self.assertEqual(self.events, ['backup', ('pull', 'reader')])
        record = json.loads((self.root / 'local/last-update.json').read_text())
        self.assertEqual(record['phase'], 'pull')
        self.assertEqual(record['snapshot_id'], SNAPSHOT)
        self.assertNotIn('SYNTHETIC-SECRET', json.dumps(record))

    def test_readiness_failure_never_stops_stack_or_downgrades(self):
        with patch.object(update, 'doctor', side_effect=ConfigError('bad health')), self.assertRaises(ConfigError):
            self.apply()
        commands = [event for event in self.events if isinstance(event, tuple)]
        self.assertEqual([command[0] for command in commands], ['pull', 'up'])
        record = json.loads((self.root / 'local/last-update.json').read_text())
        self.assertEqual(record['status'], 'FAIL')
        self.assertIn('matching snapshot', record['next_action'])
        self.assertFalse((self.root / 'local/current-deployment.json').exists())

    def test_local_or_incomplete_backup_is_not_accepted(self):
        with patch.object(update, 'create_backup', return_value={'snapshot_id': SNAPSHOT, 'services': ['reader'], 'local_test_only': True}), self.assertRaises(ConfigError):
            self.apply()
        self.assertFalse(any(isinstance(event, tuple) for event in self.events))

    def test_stopped_service_preserved_before_backup(self):
        with patch.object(update, 'inventory', return_value=[row(running=False)]), self.assertRaisesRegex(ConfigError, 'stopped services'):
            self.apply()
        self.assertEqual(self.events, [])
        self.assertFalse((self.root / 'local/last-update.json').exists())

    def test_active_watchtower_requires_explicit_retirement(self):
        with patch.object(update, 'watchtower_inventory', return_value={'running': True}), self.assertRaisesRegex(ConfigError, 'Watchtower'):
            self.apply()
        self.assertEqual(self.events, [])

    def test_initial_previous_revision_cannot_be_invented(self):
        with self.assertRaisesRegex(ConfigError, 'previous-revision'):
            update.prior_revisions([row()])
        self.assertFalse((self.root / 'local/current-deployment.json').exists())

    def test_namespace_pairs_and_core_scopes(self):
        model = {'services': {'gluetun': {'image': IMAGE}, 'webtop': {'image': IMAGE, 'network_mode': 'service:gluetun'}, 'pihole': {'image': IMAGE}}}
        self.assertEqual(update.update_scope(model, ['gluetun']), ['gluetun', 'webtop'])
        self.assertEqual(update.update_scope(model, ['webtop']), ['gluetun', 'webtop'])
        with self.assertRaisesRegex(ConfigError, 'separate operations'):
            update.update_scope(model, ['pihole', 'webtop'])
        with self.assertRaisesRegex(ConfigError, 'absent'):
            update.update_scope(model, ['unknown'])
        with self.assertRaisesRegex(ConfigError, 'immutable'):
            update.update_scope({'services': {'reader': {'image': 'example/reader:latest'}}}, ['reader'])

    def test_dryrun_has_no_commands_locks_or_files(self):
        before = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        with patch.object(update, 'git') as git, patch.object(update, 'docker') as docker, patch.object(update, 'command_lock') as lock:
            self.assertEqual(update.main(['--revision', CANDIDATE, '--services', 'reader', '--dry-run']), 0)
        git.assert_not_called()
        docker.assert_not_called()
        lock.assert_not_called()
        self.assertEqual({str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}, before)

    def test_private_config_edit_during_pull_prevents_recreation(self):
        def change_config(*args, **kwargs):
            self.events.append(args)
            (self.root / '.env').write_text('COMPOSE_PROJECT_NAME=owned-pi\nSECRET=changed-synthetic-private-value\n')
            return SimpleNamespace(stdout='')
        with patch.object(update, 'run_compose', side_effect=change_config), self.assertRaises(ConfigError) as error:
            self.apply()
        self.assertEqual(self.events, ['backup', ('pull', 'reader')])
        record = json.loads((self.root / 'local/last-update.json').read_text())
        self.assertEqual(record['status'], 'FAIL')
        self.assertEqual(record['snapshot_id'], SNAPSHOT)
        self.assertNotIn('synthetic-private-value', json.dumps(record) + str(error.exception))

    def test_active_secret_file_drift_and_symlink_refused(self):
        secret = self.root / 'local/vpn-key'
        secret.write_text('synthetic-first-key')
        model = {'services': {'reader': {'image': IMAGE, 'secrets': [{'source': 'vpn-key'}]}},
                 'secrets': {'vpn-key': {'file': str(secret)}}}
        first = update.configuration_fingerprint(model)
        secret.write_text('synthetic-second-key')
        self.assertNotEqual(update.configuration_fingerprint(model), first)
        secret.unlink()
        secret.symlink_to(self.root / '.env')
        with self.assertRaisesRegex(ConfigError, 'regular files'):
            update.configuration_fingerprint(model)


class RevisionTests(unittest.TestCase):
    def test_dirty_or_mismatched_checkout_is_refused(self):
        with patch.object(update, 'git', side_effect=[CANDIDATE, CANDIDATE, ' M docker-compose.yaml']):
            with self.assertRaisesRegex(ConfigError, 'uncommitted'):
                update.verify_revision(CANDIDATE)
        with patch.object(update, 'git', side_effect=[CANDIDATE, PREVIOUS]):
            with self.assertRaisesRegex(ConfigError, 'HEAD'):
                update.verify_revision(CANDIDATE)
        with patch.object(update, 'git') as git:
            with self.assertRaises(ConfigError):
                update.verify_revision('main')
        git.assert_not_called()


class WatchtowerTests(unittest.TestCase):
    def test_retirement_stops_only_verified_owned_id_and_disables_restart(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(update, 'ROOT', Path(directory)):
            identifier = 'e' * 64
            before = {'id': identifier, 'project': 'owned-pi', 'service': 'watchtower', 'running': True, 'restart': 'always', 'image_id': 'sha256:old'}
            after = {**before, 'running': False, 'restart': 'no'}
            calls = []
            def docker(*args, **kwargs):
                calls.append(args)
                if args[0] == 'ps':
                    return SimpleNamespace(stdout=identifier)
                if args[0] == 'inspect':
                    return SimpleNamespace(stdout=json.dumps(after if any(call[0] == 'stop' for call in calls) else before))
                return SimpleNamespace(stdout='')
            with patch.object(update, 'docker', side_effect=docker):
                result = update.retire_watchtower('owned-pi')
            self.assertEqual(result['status'], 'PASS')
            self.assertIn(('update', '--restart=no', identifier), calls)
            self.assertIn(('stop', '--time', '30', identifier), calls)
            self.assertTrue(all('label=com.docker.compose.project=owned-pi' in call for call in calls if call[0] == 'ps'))

    def test_wrong_watchtower_ownership_never_mutates(self):
        calls = []
        def docker(*args, **kwargs):
            calls.append(args)
            return SimpleNamespace(stdout='f' * 64 if args[0] == 'ps' else json.dumps({'id': 'f' * 64, 'project': 'other-project', 'service': 'watchtower', 'running': True}))
        with patch.object(update, 'docker', side_effect=docker), self.assertRaisesRegex(ConfigError, 'ownership'):
            update.retire_watchtower('owned-pi')
        self.assertEqual([call[0] for call in calls], ['ps', 'inspect'])


if __name__ == '__main__':
    unittest.main()
