#!/usr/bin/env python3
"""Validate immutable reviewed image references and optionally recheck ARM64 manifests."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REF = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._/-]*:[a-zA-Z0-9_.-]+@sha256:[a-f0-9]{64}$')


def references():
    paths = [ROOT / 'docker-compose.yaml', *sorted((ROOT / 'modules').glob('*/compose.yaml'))]
    result = set()
    for path in paths:
        if path.parent.name.startswith('_'):
            continue
        values = re.findall(r'^\s+image:\s*([^\s#]+)', path.read_text(), re.M)
        for value in values:
            value = value.strip('"\'')
            if not REF.fullmatch(value) or ':latest@' in value:
                raise ValueError('Every runnable image needs a reviewed readable release tag and real sha256 digest.')
            result.add(value)
    if not result:
        raise ValueError('No runnable image references found.')
    return result


def verify(reference):
    result = subprocess.run(['docker', 'buildx', 'imagetools', 'inspect', '--raw', reference],
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ValueError('Registry manifest lookup failed; check access and the reviewed image reference.')
    manifest = json.loads(result.stdout)
    platforms = [row.get('platform', {}) for row in manifest.get('manifests', [])]
    if not any(row.get('os') == 'linux' and row.get('architecture') == 'arm64' for row in platforms):
        raise ValueError('A referenced manifest lacks an ARM64 platform; use a verified multi-platform digest.')
    return reference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', action='store_true', help='Read-only registry verification; no images pulled or containers run.')
    args = parser.parse_args()
    try:
        refs = references()
        lock = json.loads((ROOT / 'config/images.lock.json').read_text())
        records = {row['reference']: row for row in lock['images']}
        if refs - records.keys():
            raise ValueError('Image reference changed without its reviewed image evidence. Update config/images.lock.json after registry/architecture verification.')
        for ref in refs:
            if not any(platform.startswith('linux/arm64') for platform in records[ref]['platforms']):
                raise ValueError('Missing ARM64 evidence in image lock.')
        if args.registry:
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(verify, sorted(refs)))
        print(f'PASS: {len(refs)} immutable images with ARM64 evidence' + (' rechecked against registries.' if args.registry else '.'))
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        print('Image validation failed: verify readable tag/digest, lock evidence and ARM64 registry availability. No configuration values were printed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
