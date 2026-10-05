"""One non-secret desired selection; never infer migration state from new defaults."""
import json
from lib.config import ROOT, ConfigError, atomic_write, docker, load_env

GROUPS = {'health': ['uptime-kuma'], 'diagnostics': ['netdata', 'speedtest-tracker'],
          'administration': ['portainer', 'dozzle'], 'browser': ['webtop']}
CORE = ['pihole', 'tailscale', 'homer']


def selected():
    path = ROOT / 'local' / 'selection.json'
    if not path.is_file() or path.is_symlink():
        raise ConfigError('Desired selection is missing. New install: select init --preset standard; migration: select init --existing. No services changed.')
    try:
        data = json.loads(path.read_text())
        values = data['modules']
        if data['schema_version'] != 1 or not isinstance(values, list) or any(not isinstance(x, str) or x not in GROUPS for x in values) or len(values) != len(set(values)):
            raise ValueError()
        return sorted(values)
    except (ValueError, KeyError, TypeError):
        raise ConfigError('Invalid local/selection.json; use schema_version 1 and supported unique module IDs.') from None


def initialize(preset=None, existing=False, dry_run=False):
    path = ROOT / 'local' / 'selection.json'
    if path.exists():
        return selected()
    if existing:
        project = load_env()['COMPOSE_PROJECT_NAME']
        rows = docker('ps', '-a', '--filter', f'label=com.docker.compose.project={project}',
                      '--format', '{{.Label "com.docker.compose.service"}}').stdout.split()
        if not rows:
            raise ConfigError('No existing project containers found. Verify project identity; choose an explicit new-install preset only for a new installation.')
        known = set(CORE + ['watchtower'] + [s for group in GROUPS.values() for s in group])
        if set(rows) - known:
            raise ConfigError('Existing project contains unrecognized services. Review the private inventory before selecting modules.')
        values = [name for name, services in GROUPS.items() if set(services) & set(rows)]
    elif preset in ('standard', 'core'):
        values = ['health'] if preset == 'standard' else []
    else:
        raise ConfigError('Choose --existing for migration or an explicit --preset standard/core for a new installation.')
    if not dry_run:
        atomic_write(path, json.dumps({'schema_version': 1, 'modules': sorted(values)}, indent=2) + '\n')
    return sorted(values)
