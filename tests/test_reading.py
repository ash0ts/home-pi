"""Read-only FreshRSS Compose and first-run liveness contracts."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

LAYER = Path(__file__).resolve().parents[1]
REPO = next(parent for parent in Path(__file__).resolve().parents
            if (parent / 'scripts/modules.py').is_file())
sys.path.insert(0, str(REPO / 'scripts'))
import modules
import doctor

IMAGE = 'freshrss/freshrss:1.30.0@sha256:258b8edfc8a76a61f60d2d6a14d8f8d12495d78abf38646a2137612dfa264a21'
DATA = '/var/www/FreshRSS/data'
EXTENSIONS = '/var/www/FreshRSS/extensions'


class ReadingModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('docker'):
            raise unittest.SkipTest('Docker Compose is needed for model validation; no daemon resources are created.')
        environment = {key: value for key, value in os.environ.items()
                       if key not in {'FRESHRSS_CRON_MIN', 'COMPOSE_FILE', 'COMPOSE_PROFILES', 'TZ'}}
        rendered = subprocess.run(['docker', 'compose', '--project-directory', str(REPO),
            '--env-file', os.devnull, '-f', str(LAYER / 'modules/reading/compose.yaml'),
            'config', '--format', 'json'], capture_output=True, text=True, env=environment, timeout=30)
        if rendered.returncode:
            raise AssertionError('Reading module could not be rendered by Docker Compose: ' + rendered.stderr)
        cls.model = json.loads(rendered.stdout)
        cls.service = cls.model['services']['freshrss']
        cls.metadata = json.loads((LAYER / 'modules/reading/module.json').read_text())

    def test_opt_in_service_has_only_private_listener_and_network(self):
        self.assertEqual(set(self.model['services']), {'freshrss'})
        self.assertNotIn('profiles', self.service)
        self.assertNotIn('network_mode', self.service)
        self.assertEqual(set(self.service['networks']), {'reading'})
        self.assertEqual([(row['host_ip'], row['published'], row['target']) for row in self.service['ports']],
                         [('127.0.0.1', '8082', 80)])
        self.assertFalse(self.service.get('privileged', False))

    def test_data_and_extensions_both_have_stop_consistent_backup_policy(self):
        modules._metadata(self.metadata, 'reading')
        mounts = {row['target']: row for row in self.service['volumes']}
        self.assertEqual(set(mounts), {DATA, EXTENSIONS})
        self.assertEqual(Path(mounts[DATA]['source']), REPO / 'freshrss/data')
        self.assertEqual(Path(mounts[EXTENSIONS]['source']), REPO / 'freshrss/extensions')
        policies = {row['target']: row for row in self.metadata['state']}
        self.assertEqual(set(policies), set(mounts))
        for policy in policies.values():
            self.assertEqual((policy['kind'], policy['consistency']), ('essential', 'stop'))
        self.assertEqual(self.metadata['access'][0]['https_port'], 8450)

    def test_image_remains_pinned_to_reviewed_multiarch_release(self):
        self.assertEqual(self.service['image'], IMAGE)

    def test_production_accounts_are_created_in_private_wizard(self):
        env = self.service['environment']
        self.assertNotIn('FRESHRSS_INSTALL', env)
        self.assertNotIn('FRESHRSS_USER', env)
        self.assertNotIn('INTERNAL_HOST_ALLOWLIST', env)
        self.assertEqual(env['TRUSTED_PROXY'], '0')
        self.assertEqual(self.metadata['secrets'], [])

    def test_feed_refresh_has_explicit_staggered_schedule(self):
        self.assertEqual(self.service['environment']['CRON_MIN'], '17,47')

    def test_wizard_redirect_passes_http_liveness_without_enrollment_claim(self):
        self.assertNotIn('healthcheck', self.service)
        with patch.object(doctor.http.client, 'HTTPConnection') as connection:
            connection.return_value.getresponse.return_value.status = 302
            result = doctor.http_observation('freshrss', (8082, 'http', '/'))
        self.assertEqual(result['status'], 'PASS')
        self.assertIn('authenticated use', result['evidence'])

    def test_logs_are_bounded(self):
        self.assertEqual(self.service['logging']['driver'], 'local')
        self.assertEqual(self.service['logging']['options'], {'max-size': '10m', 'max-file': '3'})


if __name__ == '__main__':
    unittest.main()
