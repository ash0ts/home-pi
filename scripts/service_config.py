"""Validate only the services selected in the rendered Compose model."""
import base64
import binascii
import ipaddress
import os
import re
from pathlib import Path
from configure import valid_app_key
from lib.config import ROOT, ConfigError
from lib.recovery import private_file


def active_file_secrets(model, services=None):
    """Return only referenced Compose secrets, after checking private source files."""
    selected = set(model.get('services', {})) if services is None else set(services)
    names = {item if isinstance(item, str) else item['source']
             for name, spec in model.get('services', {}).items() if name in selected
             for item in spec.get('secrets', [])}
    result = {}
    for name in sorted(names):
        spec = model.get('secrets', {}).get(name, {})
        if not isinstance(spec.get('file'), str) or not spec['file'] or spec.get('external'):
            raise ConfigError('Active Compose secrets must use private file sources so they can be backed up.')
        path = Path(spec['file'])
        if not path.is_absolute():
            path = ROOT / path
        private_file(path, 'Active Compose secret source')
        result[name] = path
    return result


def validate_browser_vpn(env, model, secrets):
    if 'gluetun' not in model.get('services', {}):
        return
    try:
        key = secrets['browser_wireguard_private_key'].read_bytes().strip()
        if len(base64.b64decode(key, validate=True)) != 32:
            raise ValueError()
        address = env.get('WIREGUARD_ADDRESSES', '')
        if '/' not in address or ipaddress.ip_interface(address).version != 4:
            raise ValueError()
    except (KeyError, OSError, ValueError, binascii.Error):
        raise ConfigError('Browser VPN requires a private base64 WireGuard key encoding 32 bytes and its actual IPv4 interface CIDR in WIREGUARD_ADDRESSES. Existing credentials were preserved.') from None


def check_compose_version(value):
    match = re.search(r'(\d+)\.(\d+)\.(\d+)', value)
    if not match or tuple(map(int, match.groups())) < (2, 24, 0):
        raise ConfigError('Compose 2.24.0 or newer is required for supported model and bounded readiness commands.')


def validate_dns_mode(env):
    mode = env.get('PIHOLE_LISTENING_MODE', 'local').lower()
    if mode not in {'local', 'all'}:
        raise ConfigError('PIHOLE_LISTENING_MODE must be local or all. Existing configuration was preserved.')
    if mode == 'all' and env.get('ACK_REMOTE_DNS') != 'yes':
        raise ConfigError('Remote DNS requires ACK_REMOTE_DNS=yes after reviewing docs/network.md and the actual firewall/tailnet boundaries. No network policy was changed.')
    return mode


def validate_services(env, services):
    selected = set(services)
    if 'pihole' in selected:
        validate_dns_mode(env)
        if not env.get('PIHOLE_PASSWORD') or not env.get('PIHOLE_DNS'):
            raise ConfigError('Pi-hole requires PIHOLE_PASSWORD and PIHOLE_DNS in private configuration.')
        custom = ROOT / 'pihole' / 'etc-dnsmasq.d'
        if custom.is_dir() and any(custom.iterdir()) and env.get('PIHOLE_CUSTOM_DNSMASQ') != 'true':
            raise ConfigError('Existing custom dnsmasq files found. Review them and explicitly set PIHOLE_CUSTOM_DNSMASQ=true to retain their effect before migration.')
    if 'speedtest-tracker' in selected and not valid_app_key(env.get('SPEEDTEST_APP_KEY', '')):
        raise ConfigError('Selected Speedtest requires a valid existing APP_KEY. Back up and follow encryption-key migration; do not rotate it silently.')
    if selected & {'speedtest-tracker', 'webtop'}:
        for key in ('PUID', 'PGID'):
            if not env.get(key, '').isdigit() or int(env[key]) == 0:
                raise ConfigError(f'{key} must identify the non-root application owner.')
    if 'webtop' in selected and not env.get('WEBTOP_PASSWORD'):
        raise ConfigError('Selected Webtop requires a private WEBTOP_PASSWORD.')


def check_ownership(env, services):
    for service, path in [('speedtest-tracker', 'speedtest-tracker/config'), ('webtop', 'webtop/config')]:
        if service not in services:
            continue
        target = ROOT / path
        if target.exists():
            stat = target.stat()
            if (stat.st_uid, stat.st_gid) != (int(env['PUID']), int(env['PGID'])):
                raise ConfigError(f'{service} config owner differs from PUID/PGID. Back up, inspect and deliberately repair ownership before recreation.')


def prepare_bind_directories(model, env):
    """New bind paths only; never recursively chmod/chown an existing database."""
    for service in model['services'].values():
        for mount in service.get('volumes', []):
            if mount['type'] != 'bind' or mount.get('read_only'):
                continue
            target = Path(mount['source'])
            if target.is_relative_to(ROOT) and not target.exists():
                target.mkdir(parents=True, mode=0o755)
    check_ownership(env, model['services'])
    assets = ROOT / 'homer/assets'
    if 'homer' in model['services'] and assets.exists() and assets.stat().st_uid != 1000:
        raise ConfigError('Homer initializes assets as UID 1000. Set the assets directory owner deliberately before starting; existing contents were not changed.')
