#!/usr/bin/env python3
"""Own explicit private HTTPS listeners without resetting unrelated Tailscale Serve configuration."""
import argparse
import ipaddress
import json
import re
import sys
from urllib.parse import urlsplit
from lib.config import ROOT, ConfigError, atomic_write, command_lock, docker, load_env, reject_root, run_compose

ROUTES = {
    'homer': (443, 'http', '/', False), 'pihole': (8443, 'http', '/admin/', False),
    'uptime-kuma': (8444, 'http', '/', True), 'speedtest-tracker': (8445, 'http', '/', True),
    'netdata': (8446, 'http', '/', False), 'portainer': (8447, 'https+insecure', '/', True),
    'dozzle': (8448, 'http', '/', False), 'webtop': (8449, 'https+insecure', '/', True),
}


def validate_access(model, env):
    allowed = env.get('ADMIN_BIND_IP', '127.0.0.1')
    try:
        address = ipaddress.ip_address(allowed)
    except ValueError:
        raise ConfigError('ADMIN_BIND_IP must be an explicit IP address.') from None
    rfc1918 = any(address in ipaddress.ip_network(network) for network in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')) if address.version == 4 else False
    if not address.is_loopback and (not rfc1918 or env.get('ACK_LAN_ADMIN') != 'yes'):
        raise ConfigError('LAN administration requires a specific private IP and ACK_LAN_ADMIN=yes; review firewall/client access separately.')
    listeners = set()
    for name, spec in model['services'].items():
        for port in spec.get('ports', []):
            key = (str(port.get('published')), port.get('protocol', 'tcp'))
            if key in listeners:
                raise ConfigError('Duplicate published service port; resolve the conflict before changes.')
            listeners.add(key)
            if port.get('host_ip') not in {'127.0.0.1', '::1', allowed}:
                raise ConfigError('Administrative service has an undeclared or wildcard listener; use the private access policy.')
        if name == 'pihole':
            values = spec.get('environment', {})
            if values.get('FTLCONF_webserver_port') != '127.0.0.1:8081' or values.get('FTLCONF_dns_listeningMode') != 'local':
                raise ConfigError('Pi-hole host listeners differ from the reviewed local DNS/loopback administration policy.')
    return True


def route_definitions(model):
    definitions = dict(ROUTES)
    try:
        from modules import catalog
        for meta in catalog().values():
            for item in meta.get('access', []):
                if item['service'] in model['services']:
                    definitions[item['service']] = (item['https_port'], item.get('scheme', 'http'), item.get('path', '/'), item.get('auth') != 'tailnet')
    except ImportError:
        pass
    return definitions


def desired_routes(model, env):
    hostname = env.get('TAILNET_HOSTNAME', '').rstrip('.')
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*\.ts\.net', hostname):
        raise ConfigError('Set TAILNET_HOSTNAME to the actual enrolled node DNS name before planning HTTPS routes.')
    validate_access(model, env)
    routes = []
    ports = set()
    for service, (https_port, scheme, path, enroll) in route_definitions(model).items():
        if service not in model['services']:
            continue
        spec = model['services'][service]
        source_service = service
        if service == 'pihole':
            backend = 8081
        else:
            visited = set()
            while str(spec.get('network_mode', '')).startswith('service:'):
                if source_service in visited:
                    raise ConfigError('Service network namespace cycle; no routes were changed.')
                visited.add(source_service)
                source_service = spec['network_mode'].split(':', 1)[1]
                if source_service not in model['services']:
                    raise ConfigError('Missing source network namespace service.')
                spec = model['services'][source_service]
            published = spec.get('ports', [])
            if len(published) != 1 or published[0].get('host_ip') != '127.0.0.1' or published[0].get('protocol', 'tcp') != 'tcp':
                raise ConfigError('Serve requires one declared loopback backend; explicit LAN listeners need their own tested HTTPS design.')
            backend = int(published[0]['published'])
        if https_port in ports:
            raise ConfigError('Duplicate private HTTPS port in service metadata.')
        ports.add(https_port)
        routes.append({'service': service, 'port': https_port, 'target': f'{scheme}://127.0.0.1:{backend}',
                       'url': f'https://{hostname}' + (f':{https_port}' if https_port != 443 else '') + path,
                       'hostname': hostname, 'enrollment_required': enroll, 'source_service': source_service})
    return routes


def ts_container():
    result = run_compose('ps', '--quiet', 'tailscale')
    identifiers = result.stdout.split()
    if len(identifiers) != 1 or not re.fullmatch(r'[a-f0-9]{12,64}', identifiers[0]):
        raise ConfigError('Expected one running Tailscale container in this project.')
    return identifiers[0]


def read_private_json(path, default):
    if not path.exists():
        return default
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ConfigError('Private access state must be a regular mode0600 file.')
    try:
        return json.loads(path.read_text())
    except ValueError:
        raise ConfigError('Invalid private access state JSON.') from None


def object_json(text):
    try:
        value = json.loads(text)
    except ValueError:
        raise ConfigError('Invalid private Tailscale JSON response.') from None
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ConfigError('Unexpected private Tailscale response shape.')
    return value


def normalized_target(target):
    if not isinstance(target, str):
        raise ConfigError('Invalid private route target.')
    try:
        value = urlsplit(target)
        port = value.port
    except ValueError:
        raise ConfigError('Invalid private route target.') from None
    if value.scheme not in {'http', 'https', 'https+insecure'} or value.hostname != '127.0.0.1' or not port or value.username or value.password or value.query or value.fragment or value.path not in ('', '/'):
        raise ConfigError('Private routes must target an explicit loopback HTTP(S) backend.')
    return f'{value.scheme}://127.0.0.1:{port}'


def validate_routes(routes):
    if not isinstance(routes, list):
        raise ConfigError('Invalid private route list.')
    ports, services = set(), set()
    for row in routes:
        if not isinstance(row, dict) or not {'service', 'port', 'target', 'hostname', 'enrollment_required'} <= set(row):
            raise ConfigError('Invalid private route record.')
        if not isinstance(row['service'], str) or not re.fullmatch(r'[a-z][a-z0-9-]*', row['service']) or type(row['port']) is not int or not 1 <= row['port'] <= 65535 or not isinstance(row['hostname'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9.-]*\.ts\.net', row['hostname']) or type(row['enrollment_required']) is not bool:
            raise ConfigError('Invalid private route identity.')
        if row['port'] in ports or row['service'] in services:
            raise ConfigError('Duplicate private route ownership.')
        ports.add(row['port'])
        services.add(row['service'])
        normalized_target(row['target'])
        if 'source_service' in row and (not isinstance(row['source_service'], str) or not re.fullmatch(r'[a-z][a-z0-9-]*', row['source_service'])):
            raise ConfigError('Invalid source service identity.')
    return routes


def owned_routes(path):
    data = read_private_json(path, {'schema_version': 1, 'routes': []})
    if not isinstance(data, dict) or set(data) != {'schema_version', 'routes'} or type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ConfigError('Invalid private route ownership schema.')
    return validate_routes(data['routes'])


def current_proxy(config, hostname, port):
    if not isinstance(config, dict):
        raise ConfigError('Invalid Serve status schema.')
    for key in ('Web', 'TCP', 'AllowFunnel', 'Foreground'):
        if not isinstance(config.get(key, {}), dict):
            raise ConfigError('Invalid Serve status schema.')
    endpoint = f'{hostname}:{port}'
    for foreground in config.get('Foreground', {}).values():
        if not isinstance(foreground, dict):
            raise ConfigError('Invalid foreground Serve schema.')
        if any(not isinstance(foreground.get(key, {}), dict) for key in ('TCP', 'Web', 'AllowFunnel')):
            raise ConfigError('Invalid foreground Serve schema.')
        if str(port) in foreground.get('TCP', {}) or any(key.endswith(f':{port}') for key in foreground.get('Web', {})) or any(key.endswith(f':{port}') and value for key, value in foreground.get('AllowFunnel', {}).items()):
            raise ConfigError('Requested listener is owned by a foreground Serve session; it was preserved.')
    if any(key != endpoint and key.endswith(f':{port}') for key in config.get('Web', {})):
        raise ConfigError('Requested port has an unrelated hostname handler; it was preserved.')
    web = config.get('Web', {}).get(endpoint, {})
    if not isinstance(web, dict) or not isinstance(web.get('Handlers', {}), dict):
        raise ConfigError('Invalid Serve web-handler schema.')
    handlers = web.get('Handlers', {})
    tcp = config.get('TCP', {}).get(str(port))
    funnel = any(key.endswith(f':{port}') and value for key, value in config.get('AllowFunnel', {}).items())
    if funnel or (tcp and (not isinstance(tcp, dict) or tcp != {'HTTPS': True} or set(handlers) != {'/'})):
        raise ConfigError('Requested HTTPS listener has unrelated or public configuration; resolve its ownership manually.')
    if handlers and set(handlers) != {'/'}:
        raise ConfigError('Requested listener has unrelated path handlers; no route was changed.')
    handler = handlers.get('/')
    if handler is None:
        return None
    if not isinstance(handler, dict) or set(handler) != {'Proxy'} or not isinstance(handler['Proxy'], str):
        raise ConfigError('Requested listener has unrelated content or application capabilities; it was preserved.')
    if tcp != {'HTTPS': True}:
        raise ConfigError('Requested web handler is not a managed HTTPS listener.')
    return normalized_target(handler['Proxy'])


def verify_sources(routes):
    """Verify selected running container bindings before publishing private routes."""
    for route in routes:
        service = route.get('source_service', route['service'])
        identifiers = run_compose('ps', '--quiet', service).stdout.split()
        if len(identifiers) != 1 or not re.fullmatch(r'[a-f0-9]{12,64}', identifiers[0]):
            raise ConfigError('Expected one running source container; no routes were changed.')
        template = '{"id":{{json .Id}},"running":{{json .State.Running}},"network":{{json .HostConfig.NetworkMode}},"ports":{{json .NetworkSettings.Ports}}}'
        observed = object_json(docker('inspect', '--format', template, identifiers[0]).stdout)
        if observed.get('running') is not True:
            raise ConfigError('Source container is not running; no routes were changed.')
        if service != route['service']:
            consumers = run_compose('ps', '--quiet', route['service']).stdout.split()
            owner_id = observed.get('id', '')
            if not isinstance(owner_id, str) or not re.fullmatch(r'[a-f0-9]{64}', owner_id) or len(consumers) != 1 or not re.fullmatch(r'[a-f0-9]{12,64}', consumers[0]):
                raise ConfigError('Expected one running namespace consumer and its current source container; no routes were changed.')
            consumer = object_json(docker('inspect', '--format', template, consumers[0]).stdout)
            if consumer.get('running') is not True or consumer.get('network') != 'container:' + owner_id:
                raise ConfigError('Application is not running in its current source container network namespace; recreate the coupled services before publishing routes.')
        if service == 'pihole':
            effective = docker('exec', identifiers[0], 'pihole-FTL', '--config', 'webserver.port').stdout.strip().strip('"')
            if observed.get('network') != 'host' or effective != '127.0.0.1:8081':
                raise ConfigError('Running Pi-hole administration differs from its intended loopback listener.')
        else:
            expected_port = str(urlsplit(normalized_target(route['target'])).port)
            bindings = observed.get('ports') or {}
            if not isinstance(bindings, dict):
                raise ConfigError('Invalid running source port bindings.')
            matches = [binding for key, rows in bindings.items() if key.endswith('/tcp') for binding in (rows or [])
                       if isinstance(binding, dict) and binding.get('HostPort') == expected_port]
            if not matches or any(binding.get('HostIp') != '127.0.0.1' for binding in matches):
                raise ConfigError('Running source bindings differ from the intended loopback backend; no routes were changed.')


def apply_routes(routes):
    validate_routes(routes)
    container = ts_container()
    state = object_json(docker('exec', container, 'tailscale', 'status', '--json').stdout)
    if state.get('BackendState') != 'Running':
        raise ConfigError('Tailscale enrollment is pending; no routes were changed.')
    if not isinstance(state.get('Self'), dict) or not isinstance(state['Self'].get('DNSName'), str):
        raise ConfigError('Invalid enrolled node identity response.')
    actual_host = state['Self']['DNSName'].rstrip('.')
    if any(route['hostname'] != actual_host for route in routes):
        raise ConfigError('Configured TAILNET_HOSTNAME does not match the enrolled node.')
    ownership_file = ROOT / 'local/routes-owned.json'
    prior = owned_routes(ownership_file)
    owned = {row['port']: row for row in prior}
    enrollment = read_private_json(ROOT / 'local/access-enrollment.json', {'services': []})
    if not isinstance(enrollment, dict) or set(enrollment) != {'services'} or not isinstance(enrollment['services'], list) or any(not isinstance(value, str) for value in enrollment['services']):
        raise ConfigError('Invalid private application-enrollment schema.')
    enrolled = enrollment['services']
    config = object_json(docker('exec', container, 'tailscale', 'serve', 'status', '--json').stdout)
    pending, eligible = [], []
    for route in routes:
        if route['enrollment_required'] and route['service'] not in enrolled:
            pending.append(route['service'])
            continue
        current = current_proxy(config, actual_host, route['port'])
        previous = owned.get(route['port'])
        if previous and (previous['service'] != route['service'] or previous['hostname'] != actual_host):
            raise ConfigError('Requested port belongs to another recorded service/node; it was preserved.')
        if current and (not previous or current != normalized_target(previous['target'])):
            raise ConfigError('Serve listener exists outside matching recorded ownership; it was preserved.')
        eligible.append(route)
    # Validate every intended mutation and source before the first Serve write.
    verify_sources(eligible)
    for route in eligible:
        # Recheck this listener for a concurrent owner change after preflight.
        latest = object_json(docker('exec', container, 'tailscale', 'serve', 'status', '--json').stdout)
        if current_proxy(latest, actual_host, route['port']) != current_proxy(config, actual_host, route['port']):
            raise ConfigError('Serve ownership changed during preflight; no further routes were changed.')
        docker('exec', container, 'tailscale', 'serve', '--bg', f"--https={route['port']}", route['target'])
        verified = object_json(docker('exec', container, 'tailscale', 'serve', 'status', '--json').stdout)
        if current_proxy(verified, actual_host, route['port']) != normalized_target(route['target']):
            raise ConfigError('Serve did not report the requested route. Inspect its private status; application may be partial.')
        owned[route['port']] = route
        atomic_write(ownership_file, json.dumps({'schema_version': 1, 'routes': list(owned.values())}, indent=2) + '\n')
        config = verified
    return {'status': 'NEEDS_CONFIGURATION' if pending else 'PASS', 'pending_enrollment': pending,
            'scope': 'route-configuration-only', 'next_action': 'Test allowed and denied clients, application login, and TLS; see docs/access.md.'}


def remove_routes(services):
    path = ROOT / 'local/routes-owned.json'
    if not isinstance(services, list) or any(not isinstance(service, str) for service in services):
        raise ConfigError('Removal requires an explicit service list.')
    prior = owned_routes(path)
    selected = [row for row in prior if row['service'] in services]
    if not selected:
        return {'status': 'PASS', 'scope': 'route-configuration-only'}
    container = ts_container()
    remaining = list(prior)
    config = object_json(docker('exec', container, 'tailscale', 'serve', 'status', '--json').stdout)
    for row in selected:
        current = current_proxy(config, row['hostname'], row['port'])
        if current and current != normalized_target(row['target']):
            raise ConfigError('Recorded Serve route was changed outside this tool; refusing to remove it.')
    for row in selected:
        config = object_json(docker('exec', container, 'tailscale', 'serve', 'status', '--json').stdout)
        current = current_proxy(config, row['hostname'], row['port'])
        if current and current != normalized_target(row['target']):
            raise ConfigError('Recorded Serve route changed during removal; no further routes were changed.')
        if current:
            docker('exec', container, 'tailscale', 'serve', f"--https={row['port']}", 'off')
        verified = object_json(docker('exec', container, 'tailscale', 'serve', 'status', '--json').stdout)
        if current_proxy(verified, row['hostname'], row['port']) is not None:
            raise ConfigError('Serve removal was not confirmed; recorded ownership was retained for recovery.')
        remaining.remove(row)
        atomic_write(path, json.dumps({'schema_version': 1, 'routes': remaining}, indent=2) + '\n')
    return {'status': 'PASS', 'scope': 'route-configuration-only'}


def module_routes(action, module_ids):
    from modules import catalog
    entries = catalog()
    if action not in {'enable', 'disable'} or not isinstance(module_ids, list) or any(not isinstance(mid, str) or mid not in entries for mid in module_ids):
        raise ConfigError('Unknown module route action or module ID; no routes were changed.')
    services = [service for mid in module_ids for service in entries[mid]['services']]
    if action == 'disable':
        return remove_routes(services)
    env = load_env()
    if not env.get('TAILNET_HOSTNAME'):
        return {'status': 'NEEDS_CONFIGURATION', 'next_action': 'Configure private HTTPS routes after first-run enrollment.'}
    model = json.loads(run_compose('config', '--format', 'json').stdout)
    return apply_routes([r for r in desired_routes(model, env) if r['service'] in services])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['plan', 'apply', 'remove'])
    parser.add_argument('--services', nargs='+')
    args = parser.parse_args()
    try:
        if args.command == 'remove':
            if not args.services:
                parser.error('remove requires explicit --services')
            reject_root()
            with command_lock():
                result = remove_routes(args.services)
        else:
            env = load_env()
            model = json.loads(run_compose('config', '--format', 'json').stdout)
            routes = desired_routes(model, env)
            if args.services:
                if set(args.services) - {r['service'] for r in routes}:
                    raise ConfigError('Requested route belongs to a disabled or unknown service.')
                routes = [r for r in routes if r['service'] in args.services]
            if args.command == 'plan':
                result = {'schema_version': 1, 'routes': routes, 'changes_applied': False}
            else:
                reject_root()
                with command_lock():
                    result = apply_routes(routes)
        print(json.dumps(result, indent=2))
        return 0
    except (ConfigError, OSError, ValueError, KeyError, TypeError):
        print('Access operation failed. Check private node name, enrollment, selection and route ownership; unrelated routes were preserved. Inspect private state for partial changes.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
