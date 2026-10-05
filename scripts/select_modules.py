#!/usr/bin/env python3
"""Initialize desired modules without starting or stopping any service."""
import argparse
import json
import sys
from lib.config import ConfigError, command_lock, reject_root
from lib.selection import initialize, selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'show'])
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument('--preset', choices=['core', 'standard'])
    choice.add_argument('--existing', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'show':
            values = selected()
        elif args.dry_run:
            print('Dry run: initialize desired selection; no files or Docker calls.')
            return 0
        else:
            reject_root()
            with command_lock():
                values = initialize(args.preset, args.existing)
        print(json.dumps({'schema_version': 1, 'modules': values, 'services_changed': False}))
    except (ConfigError, OSError) as exc:
        print(f'Selection failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
