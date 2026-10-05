#!/usr/bin/env python3
"""Read selected deployment identity fields; never inspect container environments."""
import argparse
import json
import sys
from datetime import datetime, timezone

from lib.config import ConfigError, docker


def inventory(project):
    result = docker('ps', '-a', '--filter', f'label=com.docker.compose.project={project}',
                    '--format', '{{.ID}}')
    containers = []
    for identifier in result.stdout.split():
        template = ('{"id":{{json .Id}},"name":{{json .Name}},'
                    '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
                    '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
                    '"image_reference":{{json .Config.Image}},"image_id":{{json .Image}},'
                    '"running":{{json .State.Running}},"mounts":{{json .Mounts}}}')
        row = json.loads(docker('inspect', '--format', template, identifier).stdout)
        row['repo_digests'] = json.loads(docker('image', 'inspect', '--format',
                                               '{{json .RepoDigests}}', row['image_id']).stdout) or []
        containers.append(row)
    return {'schema_version': 1, 'observed_at': datetime.now(timezone.utc).isoformat(),
            'scope': 'selected-docker-project', 'project': project,
            'status': 'PASS' if containers else 'NEEDS_CONFIGURATION',
            'containers': containers,
            'next_action': 'Retain this private inventory with a verified backup before migration.'
            if containers else 'No containers found for this project; verify identity on the actual Pi.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, help='Existing Compose project label; do not guess')
    args = parser.parse_args()
    import re
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', args.project):
        parser.error('invalid Compose project name')
    try:
        print(json.dumps(inventory(args.project), indent=2))
    except (ConfigError, ValueError, OSError):
        print('Inventory failed; verify Docker access and the selected project.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
