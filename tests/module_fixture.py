"""Dummy Compose and fake lifecycle checks shared by the useful-home modules."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import access
import doctor
import modules
import service_config


class ModuleFixture(unittest.TestCase):
    module = None

    @classmethod
    def setUpClass(cls):
        if not shutil.which('docker'):
            raise unittest.SkipTest('Docker Compose required for dummy models; no daemon resources created.')
        cls.temp = tempfile.TemporaryDirectory(prefix='home module fixture ')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        destination = cls.root / 'modules' / cls.module
        shutil.copytree(REPO / 'modules' / cls.module, destination)
        shutil.copyfile(REPO / 'docker-compose.yaml', cls.root / 'docker-compose.yaml')
        cls.env = {'PUID': str(os.getuid()), 'PGID': str(os.getgid()), 'TZ': 'Etc/UTC',
                   'PIHOLE_PASSWORD': 'fixture-only', 'PIHOLE_DNS': '1.1.1.1',
                   'COMPOSE_PROJECT_NAME': 'home-pi-fixture'}
        cls.envfile = cls.root / '.env'
        cls.envfile.write_text('\n'.join(f'{k}={v}' for k, v in cls.env.items()) + '\n')
        cls.envfile.chmod(0o600)
        cls.model = cls.render([destination / 'compose.yaml'])
        cls.metadata = json.loads((destination / 'module.json').read_text())
        cls.service_name = cls.metadata['services'][0]
        cls.service = cls.model['services'][cls.service_name]

    @classmethod
    def render(cls, files):
        names = set(re.findall(r'\$\{([A-Z][A-Z0-9_]*)', '\n'.join(p.read_text() for p in files)))
        names.update({'COMPOSE_FILE', 'COMPOSE_PROFILES', 'COMPOSE_ENV_FILES', 'COMPOSE_PROJECT_NAME'})
        env = {k: v for k, v in os.environ.items() if k not in names}
        argv = ['docker', 'compose', '--project-directory', str(cls.root), '--env-file', str(cls.envfile)]
        for file in files:
            argv.extend(['-f', str(file)])
        result = subprocess.run([*argv, 'config', '--format', 'json'], env=env,
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError('Dummy module model failed; private configuration was not used.')
        return json.loads(result.stdout)

    def test_private_surface_has_no_implicit_hardware_or_host_access(self):
        self.assertEqual(set(self.model['services']), {self.service_name})
        self.assertNotIn('network_mode', self.service)
        self.assertFalse(self.service.get('privileged', False))
        self.assertFalse(self.service.get('devices'))
        self.assertEqual(len(self.service['ports']), 1)
        self.assertEqual(self.service['ports'][0]['host_ip'], '127.0.0.1')
        self.assertTrue(all('docker.sock' not in v['source'] for v in self.service['volumes']))

    def test_every_writable_mount_is_restorable_stop_consistent_state(self):
        policies = {r['target']: r for r in self.metadata['state']}
        writable = {r['target'] for r in self.service['volumes'] if not r.get('read_only')}
        self.assertEqual(set(policies), writable)
        self.assertTrue(all((r['kind'], r['consistency']) == ('essential', 'stop') for r in policies.values()))
        with patch.object(modules, 'ROOT', self.root):
            modules._metadata(self.metadata, self.module)
            self.assertEqual(set(modules.metadata_for_services([self.module])), {self.service_name})

    def test_route_requires_enrollment_and_http_auth_is_only_liveness(self):
        with patch.object(modules, 'ROOT', self.root):
            rows = access.desired_routes(self.model, {'TAILNET_HOSTNAME': 'fixture.example.ts.net'})
            self.assertTrue(rows[0]['enrollment_required'])
            self.assertEqual(doctor.http_endpoint(self.service_name, self.model)[0],
                             int(self.service['ports'][0]['published']))
        with patch.object(doctor.http.client, 'HTTPConnection') as connection:
            connection.return_value.getresponse.return_value.status = 401
            result = doctor.http_observation(self.service_name, (12345, 'http', '/'))
        self.assertEqual(result['status'], 'PASS')
        self.assertIn('login has not been tested', result['evidence'])

    def test_enable_disable_preserves_core_and_data_with_fake_external_commands(self):
        local = self.root / 'local'
        local.mkdir(exist_ok=True)
        (local / 'selection.json').write_text('{"schema_version":1,"modules":[]}\n')
        source = Path(self.service['volumes'][0]['source'])
        source.mkdir(parents=True, exist_ok=True)
        marker = source / 'fixture-preserved'
        marker.write_text('fixture data\n')
        merged = {'services': {**{s: {} for s in modules.CORE}, self.service_name: self.service}}
        calls = []
        def run(*args, **kwargs):
            calls.append(args)
            return SimpleNamespace(stdout='core-container-ids' if '--quiet' in args else '')
        with patch.object(modules, 'ROOT', self.root), patch.object(service_config, 'ROOT', self.root), \
                patch.object(modules, 'load_env', return_value=self.env), \
                patch.object(modules, 'validate', return_value=merged), \
                patch.object(modules, 'run_compose', side_effect=run), \
                patch.object(modules, '_readiness'), \
                patch.object(modules, '_routes', return_value='NEEDS_CONFIGURATION'):
            result = modules.change(enable=self.module)
            self.assertEqual(modules.selected(), [self.module])
            self.assertEqual(result['status'], 'NEEDS_CONFIGURATION')
            modules.change(disable=self.module)
            self.assertEqual(modules.selected(), [])
        mutations = [args for args in calls if args[0] in {'up', 'stop', 'rm', 'down'}]
        self.assertEqual(mutations, [('up', '-d', '--no-deps', '--pull', 'never', self.service_name),
                                     ('stop', self.service_name)])
        self.assertEqual(marker.read_text(), 'fixture data\n')
