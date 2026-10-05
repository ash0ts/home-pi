"""Syncthing's GUI, unprivileged identity and independent recovery boundaries."""
from pathlib import Path
from unittest.mock import patch
import module_fixture


class FilesModuleTests(module_fixture.ModuleFixture):
    module = 'files'

    def test_service_cannot_run_as_root_or_silently_repair_existing_identity(self):
        config = module_fixture.service_config
        for uid in ('0', '-1', 'not-numeric'):
            with self.subTest(uid=uid), self.assertRaises(module_fixture.modules.ConfigError):
                config.validate_services({'PUID': uid, 'PGID': '1000'}, ['syncthing'])
        source = Path(self.service['volumes'][0]['source'])
        source.mkdir(parents=True, exist_ok=True)
        before = source.stat()
        with patch.object(config, 'ROOT', self.root):
            with self.assertRaises(module_fixture.modules.ConfigError):
                config.check_ownership({'PUID': str(before.st_uid + 1), 'PGID': str(before.st_gid)}, ['syncthing'])
        self.assertEqual((source.stat().st_uid, source.stat().st_gid), (before.st_uid, before.st_gid))

    def test_gui_is_separate_from_sync_and_updates_use_reviewed_images(self):
        self.assertEqual(self.service['ports'][0]['target'], 8384)
        self.assertIn('--no-upgrade', self.service['command'])
        self.assertEqual(self.service['user'], self.env['PUID'] + ':' + self.env['PGID'])
        self.assertEqual(self.service['environment']['UMASK'], '077')
        self.assertEqual(self.service['volumes'][0]['target'], '/var/syncthing')
