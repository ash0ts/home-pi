"""Static checks validate real Compose fragments using only dummy configuration."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lib import config
import modules
import validate as static_validation


@unittest.skipUnless(shutil.which('docker'), 'Docker Compose unavailable for read-only static model fixtures')
class StaticModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='static module fixture ')
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(patch.stopall)
        for module in (config, modules, static_validation):
            patch.object(module, 'ROOT', self.root).start()
        (self.root / 'modules/reader').mkdir(parents=True)
        (self.root / 'local').mkdir()
        (self.root / '.env').write_text('NOT_VALID_DOTENV_AND_MUST_NEVER_BE_PARSED\n')
        (self.root / 'local/selection.json').write_text('INVALID_PRIVATE_SELECTION\n')
        (self.root / 'local/storage.json').write_text('INVALID_PRIVATE_STORAGE\n')
        (self.root / '.env.example').write_text('COMPOSE_PROJECT_NAME=example\nREADER_PASSWORD=\n')
        (self.root / 'docker-compose.yaml').write_text(json.dumps({'services': {'homer': {'image': 'alpine:3.23'}}}))
        self.metadata = {'schema_version': 1, 'id': 'reader', 'description': 'Reading fixture',
                         'services': ['reader'], 'requires': [], 'secrets': ['READER_PASSWORD'],
                         'access': [{'service': 'reader', 'title': 'Reader', 'https_port': 8450, 'scheme': 'http', 'path': '/', 'auth': 'application'}],
                         'state': [{'service': 'reader', 'target': '/data', 'kind': 'essential', 'consistency': 'stop'}]}
        self.model = {'services': {'reader': {'image': 'alpine:3.23',
                                             'environment': {'READER_PASSWORD': '${READER_PASSWORD}'},
                                             'ports': ['127.0.0.1:18080:8080'],
                                             'volumes': ['/nonexistent-static-device/reader:/data']}}}
        self.write()
        self.private_reader = patch.object(modules, 'load_env', side_effect=AssertionError('Static validation read private .env')).start()
        self.storage_reader = patch.object(modules, 'validate_storage', side_effect=AssertionError('Static validation inspected host storage')).start()
        self.private_selection = patch.object(modules, 'selected', side_effect=AssertionError('Static validation read private selection')).start()

    def write(self):
        (self.root / 'modules/reader/module.json').write_text(json.dumps(self.metadata))
        (self.root / 'modules/reader/compose.yaml').write_text(json.dumps(self.model))

    def test_real_compose_uses_dummy_credentials_and_skips_private_state(self):
        with patch.dict(os.environ, {'READER_PASSWORD': 'SYNTHETIC-PRODUCTION-SECRET'}):
            model = static_validation.validate_models()
        self.assertEqual(model['services']['reader']['environment']['READER_PASSWORD'], 'dummy-reader_password')
        self.assertNotIn('SYNTHETIC-PRODUCTION-SECRET', json.dumps(model))
        self.private_reader.assert_not_called()
        self.storage_reader.assert_not_called()
        self.private_selection.assert_not_called()

    def test_compose_valid_unclassified_state_is_rejected(self):
        self.metadata['state'][0]['target'] = '/wrong-data-target'
        self.write()
        with self.assertRaisesRegex(config.ConfigError, 'classify every writable'):
            static_validation.validate_models()

    def test_compose_valid_hidden_service_is_rejected(self):
        self.model['services']['undeclared-service'] = {'image': 'alpine:3.23'}
        self.write()
        with self.assertRaisesRegex(config.ConfigError, 'ownership differs'):
            static_validation.validate_models()

    def test_compose_valid_unsafe_listener_is_rejected(self):
        self.model['services']['reader']['ports'] = ['0.0.0.0:18080:8080']
        self.write()
        with self.assertRaisesRegex(config.ConfigError, 'loopback'):
            static_validation.validate_models()

    def test_file_secret_inputs_are_dummy_temporary_files(self):
        self.metadata['secrets'] = ['READER_KEY_FILE']
        self.model['services']['reader']['environment'] = {}
        self.model['services']['reader']['secrets'] = ['reader-key']
        self.model['secrets'] = {'reader-key': {'file': '${READER_KEY_FILE}'}}
        self.write()
        model = static_validation.validate_models()
        source = Path(model['secrets']['reader-key']['file'])
        self.assertIn('home-pi-validate-', str(source))
        self.assertFalse(source.exists(), 'Temporary dummy secrets must be cleaned up')
        self.private_reader.assert_not_called()
        self.storage_reader.assert_not_called()


if __name__ == '__main__':
    unittest.main()
