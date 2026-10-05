"""Module operations run in temporary repositories with command stubs."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import modules
from lib import config


class ModuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pi modules test ')
        self.root = Path(self.temp.name)
        (self.root / 'modules').mkdir()
        (self.root / 'local').mkdir()
        (self.root / '.env').write_text('COMPOSE_PROJECT_NAME=test-pi\n')
        self.write_selection([])
        self.core = {'pihole': {}, 'tailscale': {}, 'homer': {}}
        (self.root / 'docker-compose.yaml').write_text(json.dumps({'services': {name: {'image': 'busybox:1.37'} for name in self.core}}))
        self.models = {}
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(patch.stopall)
        patch.object(modules, 'ROOT', self.root).start()
        patch.object(config, 'ROOT', self.root).start()
        patch.object(modules, 'reject_root').start()
        patch.object(modules, 'load_env', return_value={'COMPOSE_PROJECT_NAME': 'test-pi'}).start()

    def write_selection(self, values):
        (self.root / 'local/selection.json').write_text(json.dumps({'schema_version': 1, 'modules': values}))

    def add_module(self, name, port=18080, requires=None, secret=None, service=None):
        service = service or name
        path = self.root / 'modules' / name
        path.mkdir()
        data = {'schema_version': 1, 'id': name, 'description': 'Test module', 'services': [service],
                'requires': requires or [], 'secrets': [secret] if secret else [],
                'access': [{'service': service, 'title': name, 'https_port': port + 1000, 'scheme': 'http', 'path': '/', 'auth': 'application account'}],
                'state': [{'service': service, 'target': '/data', 'kind': 'essential', 'consistency': 'stop'}]}
        (path / 'module.json').write_text(json.dumps(data))
        model = {'services': {service: {'image': 'busybox:1.37', 'ports': [{'host_ip': '127.0.0.1', 'published': str(port), 'target': 80, 'protocol': 'tcp'}],
                                               'volumes': [{'type': 'bind', 'source': str(self.root / name / 'data'), 'target': '/data'}]}}}
        (path / 'compose.yaml').write_text(json.dumps(model))
        self.models[name] = model
        return data

    def render(self, files, consistency=True):
        result = {'services': {}}
        for path in files:
            if path == self.root / 'docker-compose.yaml':
                result['services'].update(self.core)
            else:
                result['services'].update(self.models[path.parent.name]['services'])
        return result

    def patch_render(self):
        return patch.object(modules, '_model', side_effect=self.render)

    def test_dependency_order_missing_and_cycles(self):
        self.add_module('reader', requires=['database'])
        with self.assertRaisesRegex(config.ConfigError, 'missing dependency'):
            modules.resolve(['reader'])
        self.add_module('database', port=18081)
        self.assertEqual(modules.resolve(['reader']), ['database', 'reader'])
        data = json.loads((self.root / 'modules/database/module.json').read_text())
        data['requires'] = ['reader']
        (self.root / 'modules/database/module.json').write_text(json.dumps(data))
        with self.assertRaisesRegex(config.ConfigError, 'cycle'):
            modules.resolve(['reader'])

    def test_unknown_hook_and_symlink_rejected(self):
        data = self.add_module('reader')
        data['install_hook'] = 'curl bad | sh'
        (self.root / 'modules/reader/module.json').write_text(json.dumps(data))
        with self.assertRaisesRegex(config.ConfigError, 'hooks'):
            modules.catalog()
        (self.root / 'modules/reader/module.json').unlink()
        (self.root / 'modules/reader/module.json').symlink_to(self.root / '.env')
        with self.assertRaisesRegex(config.ConfigError, 'regular'):
            modules.catalog()

    def test_only_selected_secrets_required(self):
        self.add_module('reader', secret='READER_PASSWORD')
        self.add_module('health', port=18081)
        with self.patch_render():
            modules.validate(['health'])
            with self.assertRaisesRegex(config.ConfigError, 'missing required private'):
                modules.validate(['reader'])

    def test_silent_compose_service_merge_refused(self):
        self.add_module('reader', service='pihole')
        with self.patch_render():
            with self.assertRaisesRegex(config.ConfigError, 'Duplicate service ownership'):
                modules.validate(['reader'])

    def test_hidden_service_not_declared_in_metadata_refused(self):
        self.add_module('reader')
        self.models['reader']['services']['surprise'] = {}
        with self.patch_render():
            with self.assertRaisesRegex(config.ConfigError, 'ownership differs'):
                modules.validate(['reader'])

    def test_published_port_and_route_conflicts_refused(self):
        self.add_module('reader')
        self.add_module('health')
        with self.patch_render():
            with self.assertRaisesRegex(config.ConfigError, 'Conflicting published'):
                modules.validate(['reader', 'health'])
        self.models['health']['services']['health']['ports'][0]['published'] = '18081'
        with self.patch_render():
            with self.assertRaisesRegex(config.ConfigError, 'Conflicting HTTPS'):
                modules.validate(['reader', 'health'])

    def test_nonloopback_only_explicit_rfc1918_acknowledgment(self):
        self.add_module('reader')
        self.models['reader']['services']['reader']['ports'][0]['host_ip'] = '0.0.0.0'
        with self.patch_render(), self.assertRaisesRegex(config.ConfigError, 'loopback'):
            modules.validate(['reader'])
        self.models['reader']['services']['reader']['ports'][0]['host_ip'] = '192.168.22.9'
        with self.patch_render(), patch.object(modules, 'load_env', return_value={'ADMIN_BIND_IP': '192.168.22.9', 'ACK_LAN_ADMIN': 'yes'}):
            modules.validate(['reader'])
        self.assertFalse(modules._listener_host('169.254.1.1', {'ADMIN_BIND_IP': '169.254.1.1', 'ACK_LAN_ADMIN': 'yes'}))

    def test_unclassified_state_and_missing_filesystem_refused(self):
        self.add_module('reader')
        self.models['reader']['services']['reader']['volumes'].append({'type': 'volume', 'source': 'forgotten', 'target': '/forgotten'})
        with self.patch_render(), self.assertRaisesRegex(config.ConfigError, 'classify every writable'):
            modules.validate(['reader'])
        self.models['reader']['services']['reader']['volumes'].pop()
        missing = self.root / 'missing-disk'
        self.models['reader']['services']['reader']['volumes'][0]['source'] = str(missing / 'reader')
        (self.root / 'local/storage.json').write_text(json.dumps({'mounts': [{'path': str(missing)}]}))
        with self.patch_render(), self.assertRaisesRegex(config.ConfigError, 'not mounted'):
            modules.validate(['reader'])
        self.assertFalse(missing.exists())

    def test_absent_external_state_is_not_created_by_enable(self):
        self.add_module('reader')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'not-provisioned'
            self.models['reader']['services']['reader']['volumes'][0]['source'] = str(source)
            with self.patch_render(), self.assertRaisesRegex(config.ConfigError, 'external state bind source is absent'):
                modules.validate(['reader'])
            self.assertFalse(source.exists())

    def test_existing_external_directory_requires_verified_covering_mount(self):
        self.add_module('reader')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            self.models['reader']['services']['reader']['volumes'][0]['source'] = str(source)
            with self.patch_render(), self.assertRaisesRegex(config.ConfigError, 'covering expected filesystem'):
                modules.validate(['reader'])
            (self.root / 'local/storage.json').write_text(json.dumps({'mounts': [{'path': str(source), 'device': source.stat().st_dev}]}))
            with self.patch_render(), patch.object(modules.os.path, 'ismount', return_value=False), self.assertRaisesRegex(config.ConfigError, 'not mounted'):
                modules.validate(['reader'])
            with self.patch_render(), patch.object(modules.os.path, 'ismount', return_value=True):
                modules.validate(['reader'])
            (self.root / 'local/storage.json').write_text(json.dumps({'mounts': [{'path': str(source), 'device': source.stat().st_dev + 1}]}))
            with self.patch_render(), patch.object(modules.os.path, 'ismount', return_value=True), self.assertRaisesRegex(config.ConfigError, 'different device identity'):
                modules.validate(['reader'])

    def test_inside_checkout_symlink_escape_requires_external_storage_evidence(self):
        self.add_module('reader')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / 'data').mkdir()
            (self.root / 'reader').symlink_to(source, target_is_directory=True)
            with self.patch_render(), self.assertRaisesRegex(config.ConfigError, 'covering expected filesystem'):
                modules.validate(['reader'])

    def test_unused_external_marker_and_system_readonly_mount_do_not_block_selection(self):
        self.add_module('reader')
        absent = self.root / 'disabled-module-disk'
        (self.root / 'local/storage.json').write_text(json.dumps({'mounts': [{'path': str(absent)}]}))
        self.core['tailscale'] = {'volumes': [{'type': 'bind', 'source': '/dev/net/tun', 'target': '/dev/net/tun'}]}
        self.core['homer'] = {'volumes': [{'type': 'bind', 'source': '/host-only-not-mounted', 'target': '/host', 'read_only': True}]}
        with self.patch_render():
            modules.validate(['reader'])
        self.assertFalse(absent.exists())

    def test_plan_includes_direct_and_deploy_resource_configuration(self):
        self.add_module('reader')
        self.models['reader']['services']['reader'].update(mem_limit='3g', cpus=2, shm_size='1g', deploy={'resources': {'reservations': {'memory': '128m'}}})
        with self.patch_render():
            result = modules.plan(enable='reader')
        self.assertEqual(result['resources']['reader'], {'mem_limit': '3g', 'cpus': 2, 'shm_size': '1g', 'deploy': {'reservations': {'memory': '128m'}}})

    def test_socket_conflict_before_change(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            port = occupied.getsockname()[1]
            self.add_module('reader', port=port)
            # Keep the HTTPS intent inside range even if the ephemeral port is high.
            metadata = json.loads((self.root / 'modules/reader/module.json').read_text())
            metadata['access'][0]['https_port'] = 8450
            (self.root / 'modules/reader/module.json').write_text(json.dumps(metadata))
            with self.patch_render(), self.assertRaisesRegex(config.ConfigError, 'occupied'):
                modules.validate(['reader'], probe_services=['reader'])
        self.assertEqual(modules.selected(), [])

    def test_dryrun_never_locks_calls_docker_or_writes(self):
        self.add_module('reader')
        original = (self.root / 'local/selection.json').read_bytes()
        with patch.object(modules, 'run_compose') as runner, patch.object(modules, 'command_lock') as lock:
            result = modules.change(enable='reader', dry_run=True)
        runner.assert_not_called()
        lock.assert_not_called()
        self.assertEqual(result['modules'], ['reader'])
        self.assertEqual((self.root / 'local/selection.json').read_bytes(), original)

    def test_readiness_failure_restores_selection_and_stops_only_new(self):
        self.add_module('reader')
        original = (self.root / 'local/selection.json').read_bytes()
        calls = []
        def runner(*args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(stdout='')
        with patch.object(modules, 'validate'), patch.object(modules, 'run_compose', side_effect=runner), patch.object(modules, '_readiness', side_effect=config.ConfigError('not ready')):
            with self.assertRaisesRegex(config.ConfigError, 'previous selection restored'):
                modules.change(enable='reader')
        self.assertEqual((self.root / 'local/selection.json').read_bytes(), original)
        starts = [args for args, _ in calls if args[0] == 'up']
        stops = [args for args, _ in calls if args[0] == 'stop']
        self.assertEqual(starts, [('up', '-d', '--no-deps', '--pull', 'never', 'reader')])
        self.assertEqual(stops, [('stop', 'reader')])

    def test_disable_uses_previous_model_and_keeps_data(self):
        self.add_module('reader')
        self.write_selection(['reader'])
        data = self.root / 'reader/data'
        data.mkdir(parents=True)
        (data / 'history').write_text('keep me')
        calls = []
        def runner(*args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(stdout='')
        with patch.object(modules, 'validate'), patch.object(modules, 'run_compose', side_effect=runner), patch.object(modules, '_routes', return_value='NEEDS_CONFIGURATION'):
            modules.change(disable='reader')
        self.assertEqual(modules.selected(), [])
        stopped = [(args, kwargs) for args, kwargs in calls if args[0] == 'stop']
        self.assertEqual(stopped[0][0], ('stop', 'reader'))
        self.assertIn(self.root / 'modules/reader/compose.yaml', stopped[0][1]['files'])
        self.assertEqual((data / 'history').read_text(), 'keep me')
        self.assertFalse(any(args[0] in ('rm', 'down') for args, _ in calls))

    def test_disable_dependency_refused(self):
        self.add_module('reader', requires=['database'])
        self.add_module('database', port=18081)
        self.write_selection(['reader', 'database'])
        with self.assertRaisesRegex(config.ConfigError, 'dependency'):
            modules.change(disable='database', dry_run=True)

    def test_failed_disable_does_not_start_previously_stopped_services(self):
        self.add_module('reader')
        self.write_selection(['reader'])
        calls = []
        def runner(*args, **kwargs):
            calls.append(args)
            if args[0] == 'stop':
                raise config.ConfigError('stop failed')
            return SimpleNamespace(stdout='')
        with patch.object(modules, 'validate'), patch.object(modules, 'run_compose', side_effect=runner), patch.object(modules, '_routes', return_value='NEEDS_CONFIGURATION'):
            with self.assertRaises(config.ConfigError):
                modules.change(disable='reader')
        self.assertEqual(modules.selected(), ['reader'])
        self.assertFalse(any(args[0] == 'start' for args in calls))

    @unittest.skipUnless(shutil.which('docker'), 'Docker Compose unavailable for read-only dummy model test')
    def test_real_compose_renders_root_relative_fragment_paths(self):
        self.add_module('reader')
        def runner(*args, files=None, **kwargs):
            command = ['docker', 'compose', '--project-directory', str(self.root), '--env-file', str(self.root / '.env'), '--project-name', 'test-pi']
            for file in files:
                command.extend(['-f', str(file)])
            result = subprocess.run([*command, *args], capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise config.ConfigError('Dummy Compose model failed')
            return result
        with patch.object(modules, 'run_compose', side_effect=runner):
            model = modules.validate(['reader'])
        self.assertEqual(model['services']['reader']['volumes'][0]['source'], str(self.root / 'reader/data'))


if __name__ == '__main__':
    unittest.main()
