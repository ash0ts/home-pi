"""Private browser credentials, namespace identity, and quarantined secret recovery."""
import base64
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import access
import backup
import modules
import restore
import service_config
from lib.config import ConfigError
from lib.recovery import repository_environment, restic


class OptionalSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='optional safety ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'checkout'
        (self.root / 'local').mkdir(parents=True)
        (self.root / '.env').write_text('COMPOSE_PROJECT_NAME=fixture\n')
        (self.root / '.env').chmod(0o600)
        self.key = self.base / 'external-wireguard-key'
        self.key.write_bytes(base64.b64encode(b'x' * 32) + b'\n')
        self.key.chmod(0o600)
        self.model = {'services': {'gluetun': {'secrets': [
            {'source': 'browser_wireguard_private_key', 'target': 'wireguard_private_key'}]}},
            'secrets': {'browser_wireguard_private_key': {'file': str(self.key)}}}

    def test_only_active_secret_sources_are_validated(self):
        self.model['secrets']['inactive'] = {'file': str(self.base / 'missing')}
        self.assertEqual(service_config.active_file_secrets(self.model),
                         {'browser_wireguard_private_key': self.key})
        self.assertEqual(service_config.active_file_secrets(self.model, ['unrelated']), {})

    def test_missing_public_symlink_and_nonfile_secrets_are_refused(self):
        self.key.chmod(0o644)
        with self.assertRaisesRegex(ConfigError, '0600'):
            service_config.active_file_secrets(self.model)
        self.key.chmod(0o600)
        link = self.base / 'link'
        link.symlink_to(self.key)
        for value in ({'file': str(link)}, {'file': str(self.base / 'missing')},
                      {'file': str(self.base)}, {'external': True}, {'environment': 'KEY'}):
            self.model['secrets']['browser_wireguard_private_key'] = value
            with self.subTest(source=value), self.assertRaises(ConfigError):
                service_config.active_file_secrets(self.model)

    def test_browser_key_and_ipv4_cidr_validation_preserves_credentials(self):
        secrets = service_config.active_file_secrets(self.model)
        service_config.validate_browser_vpn({'WIREGUARD_ADDRESSES': '10.64.0.2/32'}, self.model, secrets)
        original = self.key.read_bytes()
        for address in ('10.64.0.2', 'fd00::2/128', 'not-an-address', '10.64.0.2/99'):
            with self.subTest(address=address), self.assertRaisesRegex(ConfigError, 'IPv4 interface CIDR'):
                service_config.validate_browser_vpn({'WIREGUARD_ADDRESSES': address}, self.model, secrets)
        self.assertEqual(self.key.read_bytes(), original)
        for invalid in (b'private-value-not-base64', base64.b64encode(b'x' * 31)):
            self.key.write_bytes(invalid)
            with self.assertRaises(ConfigError) as error:
                service_config.validate_browser_vpn({'WIREGUARD_ADDRESSES': '10.64.0.2/32'}, self.model, secrets)
            self.assertNotIn(invalid.decode(), str(error.exception))
            self.assertEqual(self.key.read_bytes(), invalid)
        service_config.validate_browser_vpn({}, {'services': {'homer': {}}}, {})

    def test_module_runtime_checks_secrets_but_static_validation_does_not_read_them(self):
        model = {**self.model, 'services': {'homer': self.model['services']['gluetun']}}
        self.key.chmod(0o644)
        with patch.object(modules, 'catalog', return_value={}):
            with self.assertRaisesRegex(ConfigError, '0600'):
                modules.validate([], env_override={}, model_loader=lambda *args, **kwargs: model)
            self.assertEqual(modules.validate([], env_override={},
                             model_loader=lambda *args, **kwargs: model, runtime_checks=False), model)

    def test_secret_manifest_uses_quarantine_paths_even_for_external_sources(self):
        stage = self.base / 'stage'
        stage.mkdir()
        with patch.object(backup, 'ROOT', self.root):
            files = backup.copy_private_config(stage, self.model, ['gluetun'])
        item = next(row for row in files if 'compose_secret' in row)
        self.assertEqual(item['source_path'], str(self.key))
        self.assertEqual(item['path'], 'config/compose-secrets/0')
        copied = stage / item['path']
        self.assertEqual(copied.read_bytes(), self.key.read_bytes())
        self.assertEqual(copied.stat().st_mode & 0o777, 0o600)

    @unittest.skipUnless(shutil.which('restic'), 'restic is required for the encryption fixture')
    def test_encrypted_backup_restores_external_secret_only_into_quarantine(self):
        password = self.base / 'password'
        password.write_text('fixture-only-encryption-password\n')
        password.chmod(0o600)
        repository = self.base / 'encrypted-repository'
        config = self.root / 'local/backup.env'
        config.write_text(f'RESTIC_REPOSITORY={repository}\nRESTIC_PASSWORD_FILE={password}\n')
        config.chmod(0o600)
        env, _ = repository_environment(self.root, True)
        restic(['init'], env)
        record = {'service': 'gluetun', 'container_id': 'a' * 64,
                  'was_running': False, 'mounts': []}
        original = self.key.read_bytes()
        with patch.object(backup, 'ROOT', self.root), patch.object(backup, 'compose_model', return_value=self.model), \
                patch.object(backup, 'load_env', return_value={'COMPOSE_PROJECT_NAME': 'fixture'}), \
                patch.object(backup, 'state_policy', return_value={}), \
                patch.object(backup, 'inventory', return_value=[record]), \
                patch.object(backup, 'source_commit', return_value='b' * 40), \
                patch.object(backup, 'docker') as docker:
            result = backup.create_backup(['gluetun'], allow_local_repository=True)
            docker.assert_not_called()
        for path in repository.rglob('*'):
            if path.is_file():
                self.assertNotIn(original.strip(), path.read_bytes())
        self.key.write_bytes(b'changed-external-source\n')
        quarantine = self.base / 'quarantine'
        with patch.object(restore, 'ROOT', self.root):
            restored = restore.restore_snapshot(result['snapshot_id'], quarantine, True)
        self.assertEqual(restored['status'], 'RESTORED_QUARANTINED')
        self.assertEqual((quarantine / 'config/compose-secrets/0').read_bytes(), original)
        self.assertEqual(self.key.read_bytes(), b'changed-external-source\n')

    def verify_namespace(self, consumer):
        owner_id = 'a' * 64
        route = {'service': 'webtop', 'source_service': 'gluetun', 'target': 'https+insecure://127.0.0.1:3002'}
        owner = {'id': owner_id, 'running': True, 'network': 'browser',
                 'ports': {'3001/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '3002'}]}}
        def compose(*args):
            return SimpleNamespace(stdout=owner_id if args[-1] == 'gluetun' else 'b' * 64)
        with patch.object(access, 'run_compose', side_effect=compose), \
                patch.object(access, 'docker', side_effect=[SimpleNamespace(stdout=json.dumps(owner)),
                                                         SimpleNamespace(stdout=json.dumps(consumer))]):
            access.verify_sources([route])

    def test_current_running_namespace_consumer_can_publish(self):
        self.verify_namespace({'running': True, 'network': 'container:' + 'a' * 64})

    def test_stale_direct_and_stopped_consumers_cannot_publish(self):
        for consumer in ({'running': True, 'network': 'container:' + 'c' * 64},
                         {'running': True, 'network': 'bridge'},
                         {'running': False, 'network': 'container:' + 'a' * 64}):
            with self.subTest(consumer=consumer), self.assertRaisesRegex(ConfigError, 'network namespace'):
                self.verify_namespace(consumer)


if __name__ == '__main__':
    unittest.main()
