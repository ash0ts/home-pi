import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import access
import modules
from lib import selection
from lib.config import ConfigError


def model():
    return {'services': {'homer': {'ports': [{'host_ip': '127.0.0.1', 'published': '8080', 'target': 8080}]},
                         'pihole': {'environment': {'FTLCONF_webserver_port': '127.0.0.1:8081', 'FTLCONF_dns_listeningMode': 'local'}}}}


class AccessTests(unittest.TestCase):
    def test_loopback_and_separate_dns_admin_policy(self):
        self.assertTrue(access.validate_access(model(), {}))
        for ip in ('0.0.0.0', '::', '8.8.8.8'):
            with self.assertRaises(ConfigError):
                access.validate_access(model(), {'ADMIN_BIND_IP': ip, 'ACK_LAN_ADMIN': 'yes'})
        modified = model()
        modified['services']['homer']['ports'][0]['host_ip'] = '0.0.0.0'
        with self.assertRaises(ConfigError):
            access.validate_access(modified, {})

    def test_duplicate_ports_and_host_admin_rejected(self):
        modified = model()
        modified['services']['another'] = copy.deepcopy(modified['services']['homer'])
        with self.assertRaises(ConfigError):
            access.validate_access(modified, {})
        modified = model()
        modified['services']['pihole']['environment']['FTLCONF_webserver_port'] = '80'
        with self.assertRaises(ConfigError):
            access.validate_access(modified, {})

    def test_remote_dns_still_requires_review_and_loopback_admin(self):
        modified = model()
        modified['services']['pihole']['environment']['FTLCONF_dns_listeningMode'] = 'all'
        env = {'PIHOLE_LISTENING_MODE': 'all', 'ACK_REMOTE_DNS': 'yes'}
        self.assertTrue(access.validate_access(modified, env))
        with self.assertRaises(ConfigError):
            access.validate_access(modified, {'PIHOLE_LISTENING_MODE': 'all'})
        with self.assertRaises(ConfigError):
            access.validate_access(modified, {})
        modified['services']['pihole']['environment']['FTLCONF_webserver_port'] = '0.0.0.0:8081'
        with self.assertRaises(ConfigError):
            access.validate_access(modified, env)

    def test_https_urls_and_backend_from_model(self):
        rows = access.desired_routes(model(), {'TAILNET_HOSTNAME': 'pi.fixture.ts.net'})
        self.assertEqual(rows[0]['url'], 'https://pi.fixture.ts.net/')
        self.assertEqual(rows[1]['target'], 'http://127.0.0.1:8081')
        self.assertEqual(rows[1]['url'], 'https://pi.fixture.ts.net:8443/admin/')

    def test_unrelated_subpaths_and_funnel_preserved(self):
        config = {'TCP': {'443': {'HTTPS': True}}, 'Web': {'pi.fixture.ts.net:443': {'Handlers': {'/other': {'Proxy': 'http://127.0.0.1:1234'}}}}}
        with self.assertRaises(ConfigError):
            access.current_proxy(config, 'pi.fixture.ts.net', 443)
        with self.assertRaises(ConfigError):
            access.current_proxy({'AllowFunnel': {'pi.fixture.ts.net:443': True}}, 'pi.fixture.ts.net', 443)

    def test_first_run_enrollment_keeps_route_pending(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(access, 'ROOT', Path(directory)), patch.object(access, 'ts_container', return_value='a'*64):
            calls = []
            def fake(*args):
                calls.append(args)
                return SimpleNamespace(stdout=json.dumps({'BackendState': 'Running', 'Self': {'DNSName': 'pi.fixture.ts.net'}}) if args[3] == 'status' else '{}')
            route = {'service': 'portainer', 'port': 8447, 'target': 'https+insecure://127.0.0.1:9443', 'hostname': 'pi.fixture.ts.net', 'enrollment_required': True}
            with patch.object(access, 'docker', side_effect=fake):
                result = access.apply_routes([route])
            self.assertEqual(result['status'], 'NEEDS_CONFIGURATION')
            self.assertFalse(any('--bg' in call for call in calls))

    def test_legacy_webtop_requires_explicit_namespace_migration(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(selection, 'ROOT', Path(directory)), patch.object(selection, 'load_env', return_value={'COMPOSE_PROJECT_NAME': 'old'}), patch.object(selection, 'docker', return_value=SimpleNamespace(stdout='pihole\nwebtop\n')):
            with self.assertRaisesRegex(ConfigError, 'partial service set'):
                selection.initialize(existing=True)
            self.assertFalse((Path(directory) / 'local/selection.json').exists())

    def test_selection_preserves_existing_apps_and_never_starts(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(selection, 'ROOT', Path(directory)), patch.object(selection, 'load_env', return_value={'COMPOSE_PROJECT_NAME': 'old'}), patch.object(selection, 'docker', return_value=SimpleNamespace(stdout='pihole\nwebtop\ngluetun\nportainer\ndozzle\nwatchtower\n')) as call:
            self.assertEqual(selection.initialize(existing=True), ['administration', 'browser'])
            self.assertEqual(call.call_args.args[0], 'ps')
            with patch.object(selection, 'selected', return_value=['administration', 'browser']):
                self.assertEqual(selection.initialize(preset='standard'), ['administration', 'browser'])

    def test_unknown_migration_service_is_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(selection, 'ROOT', Path(directory)), patch.object(selection, 'load_env', return_value={'COMPOSE_PROJECT_NAME': 'old'}), patch.object(selection, 'docker', return_value=SimpleNamespace(stdout='pihole\nunrecognized\n')):
            with self.assertRaises(ConfigError):
                selection.initialize(existing=True)
            self.assertFalse((Path(directory)/'local/selection.json').exists())





class RouteMutationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'local').mkdir()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(patch.stopall)
        patch.object(access, 'ROOT', self.root).start()
        patch.object(access, 'ts_container', return_value='a' * 64).start()
        self.config = {}
        self.calls = []
        self.ignore_delete = False
        patch.object(access, 'docker', side_effect=self.docker).start()

    def route(self, service='homer', port=443, backend=8080):
        return {'service': service, 'port': port, 'target': f'http://127.0.0.1:{backend}',
                'hostname': 'pi.fixture.ts.net', 'enrollment_required': False, 'source_service': service}

    def publish(self, row, target=None):
        self.config.setdefault('TCP', {})[str(row['port'])] = {'HTTPS': True}
        self.config.setdefault('Web', {})[f"pi.fixture.ts.net:{row['port']}"] = {'Handlers': {'/': {'Proxy': target or row['target']}}}

    def write_owned(self, rows):
        path = self.root / 'local/routes-owned.json'
        path.write_text(json.dumps({'schema_version': 1, 'routes': rows}))
        path.chmod(0o600)
        return path

    def docker(self, *args):
        self.calls.append(args)
        if args[3:] == ('status', '--json'):
            return SimpleNamespace(stdout=json.dumps({'BackendState': 'Running', 'Self': {'DNSName': 'pi.fixture.ts.net.'}}))
        if args[3:] == ('serve', 'status', '--json'):
            return SimpleNamespace(stdout=json.dumps(self.config))
        if '--bg' in args:
            port = int(next(value.split('=')[1] for value in args if value.startswith('--https=')))
            self.publish(self.route(port=port), target=args[-1] + '/')
        elif args[-1] == 'off':
            port = next(value.split('=')[1] for value in args if value.startswith('--https='))
            if not self.ignore_delete:
                self.config.get('TCP', {}).pop(port, None)
                self.config.get('Web', {}).pop(f'pi.fixture.ts.net:{port}', None)
        return SimpleNamespace(stdout='{}')

    def mutations(self):
        return [call for call in self.calls if '--bg' in call or call[-1] == 'off']

    def test_late_collision_is_found_before_first_mutation(self):
        first = self.route()
        second = self.route('pihole', 8443, 8081)
        self.publish(second, 'http://127.0.0.1:1111')
        with patch.object(access, 'verify_sources'), self.assertRaises(ConfigError):
            access.apply_routes([first, second])
        self.assertEqual(self.mutations(), [])
        self.assertFalse((self.root / 'local/routes-owned.json').exists())

    def test_removal_collision_is_found_before_first_mutation(self):
        first, second = self.route(), self.route('pihole', 8443, 8081)
        self.publish(first)
        self.publish(second, 'http://127.0.0.1:9999')
        path = self.write_owned([first, second])
        previous = path.read_bytes()
        with self.assertRaises(ConfigError):
            access.remove_routes(['homer', 'pihole'])
        self.assertEqual(self.mutations(), [])
        self.assertEqual(path.read_bytes(), previous)

    def test_success_preserves_unrelated_route_and_normalizes_root_slash(self):
        unrelated = self.route('other', 9444, 9191)
        self.publish(unrelated)
        original = copy.deepcopy(self.config['Web']['pi.fixture.ts.net:9444'])
        with patch.object(access, 'verify_sources'):
            access.apply_routes([self.route()])
        self.assertEqual(self.config['Web']['pi.fixture.ts.net:9444'], original)
        access.remove_routes(['homer'])
        self.assertEqual(self.config['Web']['pi.fixture.ts.net:9444'], original)
        self.assertEqual(json.loads((self.root / 'local/routes-owned.json').read_text())['routes'], [])

    def test_changed_owned_route_cannot_be_overwritten(self):
        row = self.route()
        self.write_owned([row])
        self.publish(row, 'http://127.0.0.1:9999')
        with patch.object(access, 'verify_sources'), self.assertRaises(ConfigError):
            access.apply_routes([row])
        self.assertEqual(self.mutations(), [])

    def test_failed_delete_retains_recorded_ownership(self):
        row = self.route()
        self.publish(row)
        path = self.write_owned([row])
        previous = path.read_bytes()
        self.ignore_delete = True
        with self.assertRaisesRegex(ConfigError, 'not confirmed'):
            access.remove_routes(['homer'])
        self.assertEqual(path.read_bytes(), previous)

    def test_path_file_capability_foreground_and_foreign_hostname_preserved(self):
        row = self.route()
        fixtures = [
            {'TCP': {'443': {'HTTPS': True}}, 'Web': {'pi.fixture.ts.net:443': {'Handlers': {'/': {'Path': '/private/files'}}}}},
            {'TCP': {'443': {'HTTPS': True}}, 'Web': {'pi.fixture.ts.net:443': {'Handlers': {'/': {'Proxy': row['target'], 'AcceptAppCaps': ['private']}}}}},
            {'Foreground': {'session': {'TCP': {'443': {'HTTPS': True}}}}},
            {'Web': {'other.fixture.ts.net:443': {'Handlers': {'/': {'Proxy': row['target']}}}}},
            {'AllowFunnel': {'other.fixture.ts.net:443': True}},
        ]
        for fixture in fixtures:
            with self.subTest(fixture=fixture), self.assertRaises(ConfigError):
                access.current_proxy(fixture, 'pi.fixture.ts.net', 443)

    def test_invalid_private_schemas_return_config_errors(self):
        for value in ([], {'routes': []}, {'schema_version': 1, 'routes': [{'port': 443}]}):
            path = self.root / 'local/routes-owned.json'
            path.write_text(json.dumps(value))
            path.chmod(0o600)
            with self.subTest(value=value), self.assertRaises(ConfigError):
                access.apply_routes([self.route()])
        for value in ([], {'TCP': []}, {'Foreground': {'session': {'Web': []}}}):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                access.current_proxy(value, 'pi.fixture.ts.net', 443)
        self.assertEqual(self.mutations(), [])

    def test_verify_sources_rejects_actual_wildcard_binding(self):
        observed = {'running': True, 'network': 'bridge', 'ports': {'80/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '8080'}]}}
        with patch.object(access, 'run_compose', return_value=SimpleNamespace(stdout='b' * 64)), patch.object(access, 'docker', return_value=SimpleNamespace(stdout=json.dumps(observed))):
            with self.assertRaisesRegex(ConfigError, 'Running source bindings'):
                access.verify_sources([self.route()])
        self.assertEqual(self.mutations(), [])

    def test_unknown_module_action_makes_no_external_calls(self):
        fake = SimpleNamespace(catalog=lambda: {'known': {'services': ['homer']}})
        with patch.dict(sys.modules, {'modules': fake}):
            for action, values in [('unknown', ['known']), ('disable', ['unknown'])]:
                with self.subTest(action=action), self.assertRaises(ConfigError):
                    access.module_routes(action, values)
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
