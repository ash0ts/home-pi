#!/usr/bin/env python3
"""Thin user command dispatcher; service definitions stay in Compose fragments."""
import argparse
import json
import subprocess
import sys

sys.dont_write_bytecode = True
from lib.config import ConfigError, ROOT, reject_root, command_lock


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print("Usage: ./pi {init,modules,plan,enable,disable,status,doctor,configure,validate,pull,start,backup,restore,update} [options]")
        return 0
    command, rest = args[0], args[1:]
    try:
        if command in ("modules", "plan", "enable", "disable"):
            import modules
            return modules.main(args)
        if command == "init":
            parser = argparse.ArgumentParser(prog="pi init")
            choice = parser.add_mutually_exclusive_group(required=True)
            choice.add_argument("--preset", choices=("standard", "core"))
            choice.add_argument("--existing", action="store_true")
            parser.add_argument("--dry-run", action="store_true")
            options = parser.parse_args(rest)
            reject_root()
            from lib.selection import initialize
            if options.dry_run:
                if options.existing:
                    print("Dry run: would inventory the installed project and import its module selection. No Docker calls or writes.")
                    return 0
                result = initialize(preset=options.preset, dry_run=True)
            else:
                with command_lock():
                    result = initialize(preset=options.preset, existing=options.existing)
            print(json.dumps({"modules": result, "dry_run": options.dry_run}))
            return 0
        if command in ("configure", "validate", "start", "install-deps"):
            from setup import main as setup_main
            return setup_main([command, *rest])
        if command == "pull":
            parser = argparse.ArgumentParser(prog="pi pull")
            parser.add_argument("module", nargs="?")
            parser.add_argument("--dry-run", action="store_true")
            options = parser.parse_args(rest)
            if options.dry_run:
                print("Dry run: fetch selected images; no Docker calls or writes.")
                return 0
            import modules
            from lib.config import run_compose
            selection = modules.selected()
            if options.module:
                selection = modules.resolve(list(dict.fromkeys([*selection, options.module])))
            model = modules.validate(selection)
            services = list(modules.metadata_for_services(modules.resolve([options.module]))) if options.module else sorted(model["services"])
            run_compose("pull", *services, files=modules.compose_files(selection), timeout=1800)
            print("Selected images fetched. No containers were recreated.")
            return 0
        if command in ("doctor", "status"):
            target = "doctor.sh"
            rest = (["--json"] if command == "status" else []) + rest
        elif command in ("backup", "restore", "update"):
            target = command + ".sh"
            if command == "backup" and rest and not rest[0].startswith("-"):
                import modules
                name = rest.pop(0)
                if name not in modules.selected():
                    raise ConfigError("Backup module must be selected; use the explicit restore workflow for disabled data.")
                names = modules.resolve([name])
                services = list(modules.metadata_for_services(names))
                rest = [*rest, "--services", *services]
        else:
            raise ConfigError("Unknown pi command. Run ./pi --help.")
        path = ROOT / "scripts" / target
        if not path.is_file():
            raise ConfigError("This maintenance command is not available in this checkout yet.")
        return subprocess.run([str(path), *rest], cwd=ROOT, check=False).returncode
    except (ConfigError, OSError) as exc:
        print(str(exc) if isinstance(exc, ConfigError) else "Command could not run; check local dependencies.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
