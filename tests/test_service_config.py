import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import service_config as config
from lib.config import ConfigError


class ServiceConfigTests(unittest.TestCase):
    def test_core_does_not_require_optional_credentials(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(config, 'ROOT', Path(directory)):
            config.validate_services({'PIHOLE_PASSWORD': 'dummy', 'PIHOLE_DNS': '1.1.1.1'}, ['pihole', 'tailscale', 'homer'])

    def test_selected_service_requires_existing_key_and_password(self):
        with self.assertRaises(ConfigError):
            config.validate_services({}, ['speedtest-tracker'])
        with self.assertRaises(ConfigError):
            config.validate_services({'PUID': '1000', 'PGID': '1000'}, ['webtop'])

    def test_custom_dnsmasq_requires_explicit_preservation(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(config, 'ROOT', Path(directory)):
            custom = Path(directory) / 'pihole/etc-dnsmasq.d'
            custom.mkdir(parents=True)
            (custom / 'custom.conf').write_text('address=/fixture.invalid/0.0.0.0\n')
            env = {'PIHOLE_PASSWORD': 'dummy', 'PIHOLE_DNS': '1.1.1.1'}
            with self.assertRaises(ConfigError):
                config.validate_services(env, ['pihole'])
            env['PIHOLE_CUSTOM_DNSMASQ'] = 'true'
            config.validate_services(env, ['pihole'])

    def test_compose_minimum_and_major_versions(self):
        for value in ('v2.24.0', '2.39.1', 'Docker Compose version v5.1.2'):
            config.check_compose_version(value)
        for value in ('v2.23.9', '1.29.0', 'invalid'):
            with self.assertRaises(ConfigError):
                config.check_compose_version(value)


if __name__ == '__main__':
    unittest.main()
