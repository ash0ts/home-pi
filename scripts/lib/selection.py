"""Initialize explicit desired state from a preset or installed project labels."""
import json
from lib.config import ROOT, ConfigError, atomic_write, docker, load_env


def selected():
    from modules import selected as read_selection
    return read_selection()


def initialize(preset=None, existing=False, dry_run=False):
    from modules import CORE, catalog, resolve
    path = ROOT / 'local' / 'selection.json'
    if path.exists():
        return selected()
    entries = catalog()
    if existing:
        project = load_env()['COMPOSE_PROJECT_NAME']
        rows = set(docker('ps', '-a', '--filter', f'label=com.docker.compose.project={project}',
                         '--format', '{{.Label "com.docker.compose.service"}}').stdout.split())
        if not rows:
            raise ConfigError('No existing project containers found. Verify project identity before choosing a new-install preset.')
        known = set(CORE + ['watchtower'] + [service for entry in entries.values() for service in entry['services']])
        if rows - known:
            raise ConfigError('Existing project contains unrecognized services. Review its private inventory before selecting modules.')
        values = []
        for name, entry in entries.items():
            deployed = set(entry['services']) & rows
            if deployed:
                if deployed != set(entry['services']):
                    raise ConfigError('An installed module has a partial service set. Review the migration explicitly instead of silently enabling additional services.')
                values.append(name)
        resolved = resolve(values)
        if set(resolved) != set(values):
            raise ConfigError('Installed services are missing a new declared module dependency; review migration before expanding the deployment.')
    elif preset in ('standard', 'core'):
        values = resolve(['health'] if preset == 'standard' else [])
    else:
        raise ConfigError('Choose --existing for migration or an explicit --preset standard/core for a new installation.')
    if not dry_run:
        atomic_write(path, json.dumps({'schema_version': 1, 'modules': sorted(values)}, indent=2) + '\n')
    return sorted(values)
