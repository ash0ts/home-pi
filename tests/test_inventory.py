import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import inventory


class InventoryTests(unittest.TestCase):
    def test_no_containers_does_not_claim_deployment_verified(self):
        with patch.object(inventory, 'docker', return_value=SimpleNamespace(stdout='')):
            self.assertEqual(inventory.inventory('existing-pi')['status'], 'NEEDS_CONFIGURATION')

    def test_only_selected_fields_and_project_are_requested(self):
        calls = []
        def fake(*args):
            calls.append(args)
            if args[0] == 'ps':
                return SimpleNamespace(stdout='abc123\n')
            if args[0] == 'inspect':
                return SimpleNamespace(stdout=json.dumps({'image_id': 'sha256:example', 'mounts': []}))
            return SimpleNamespace(stdout='["example@sha256:reference"]')
        with patch.object(inventory, 'docker', side_effect=fake):
            data = inventory.inventory('existing-pi')
        self.assertEqual(data['containers'][0]['repo_digests'], ['example@sha256:reference'])
        self.assertIn('label=com.docker.compose.project=existing-pi', calls[0])
        self.assertNotIn('.Config.Env', calls[1][2])
        self.assertNotIn('{{json .}}', calls[1][2])


if __name__ == '__main__':
    unittest.main()
