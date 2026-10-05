#!/usr/bin/env python3
"""Small module catalog and explicit desired-state changes for home-pi."""

import argparse
import errno
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys

sys.dont_write_bytecode = True
from lib.config import ConfigError, ROOT, atomic_write, command_lock, compose_args, load_env, reject_root, run_compose

CORE = ["pihole", "tailscale", "homer"]
ID = re.compile(r"^[a-z][a-z0-9-]{0,47}$")
SECRET = re.compile(r"^[A-Z][A-Z0-9_]*$")
FIELDS = {"schema_version", "id", "description", "services", "requires", "access", "state", "secrets"}
ACCESS_FIELDS = {"service", "title", "https_port", "scheme", "path", "auth"}
STATE_FIELDS = {"service", "target", "kind", "consistency", "reason"}
SYSTEM_BINDS = {("/var/run/docker.sock", "/var/run/docker.sock"), ("/dev/net/tun", "/dev/net/tun")}


def _unique_strings(values, name, pattern=None):
    if not isinstance(values, list) or any(not isinstance(value, str) or not value or (pattern and not pattern.fullmatch(value)) for value in values):
        raise ConfigError(f"Module {name} must be an array of valid strings.")
    if len(values) != len(set(values)):
        raise ConfigError(f"Module {name} contains duplicates.")


def _metadata(data, module_id):
    if not isinstance(data, dict) or set(data) != FIELDS or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ConfigError(f"Module {module_id} requires schema_version 1 and the exact supported metadata fields; hooks are not allowed.")
    if data["id"] != module_id or not isinstance(data["description"], str) or not data["description"].strip():
        raise ConfigError(f"Module {module_id} has an invalid ID or description.")
    for name in ("services", "requires", "secrets"):
        _unique_strings(data[name], name, SECRET if name == "secrets" else ID)
    if not data["services"]:
        raise ConfigError(f"Module {module_id} must own at least one service.")
    if not isinstance(data["access"], list) or not isinstance(data["state"], list):
        raise ConfigError(f"Module {module_id} access and state must be arrays.")
    seen_access, seen_state = set(), set()
    for access in data["access"]:
        if not isinstance(access, dict) or set(access) != ACCESS_FIELDS or access.get("service") not in data["services"]:
            raise ConfigError(f"Module {module_id} has invalid access metadata.")
        if any(not isinstance(access[key], str) or not access[key] for key in ("title", "scheme", "path", "auth")):
            raise ConfigError(f"Module {module_id} has incomplete access metadata.")
        if access["scheme"] not in ("http", "https", "https+insecure") or not access["path"].startswith("/") or type(access["https_port"]) is not int or not 1 <= access["https_port"] <= 65535:
            raise ConfigError(f"Module {module_id} has invalid access path, scheme, or HTTPS port.")
        if access["service"] in seen_access:
            raise ConfigError(f"Module {module_id} declares multiple routes for one service.")
        seen_access.add(access["service"])
    for state in data["state"]:
        if not isinstance(state, dict) or not {"service", "target", "kind", "consistency"} <= set(state) or set(state) - STATE_FIELDS or state.get("service") not in data["services"]:
            raise ConfigError(f"Module {module_id} has invalid state metadata.")
        if not isinstance(state["target"], str) or not state["target"].startswith("/") or ".." in Path(state["target"]).parts or state["kind"] not in ("essential", "history", "cache") or state["consistency"] != "stop":
            raise ConfigError(f"Module {module_id} state requires an absolute target, known kind, and stop consistency.")
        if "reason" in state and (not isinstance(state["reason"], str) or not state["reason"].strip()):
            raise ConfigError(f"Module {module_id} state reason must be text.")
        identity = (state["service"], state["target"])
        if identity in seen_state:
            raise ConfigError(f"Module {module_id} declares a state target twice.")
        seen_state.add(identity)
    return data


def catalog():
    directory = ROOT / "modules"
    if directory.is_symlink():
        raise ConfigError("The modules directory must not be a symbolic link.")
    if not directory.exists():
        return {}
    result = {}
    for path in sorted(directory.iterdir()):
        if path.name.startswith(("_", ".")):
            continue
        if not ID.fullmatch(path.name) or path.is_symlink() or not path.is_dir():
            raise ConfigError("Module paths must be ordinary directories with valid IDs; symbolic links are refused.")
        for filename in ("module.json", "compose.yaml"):
            file = path / filename
            if file.is_symlink() or not file.is_file():
                raise ConfigError(f"Module {path.name} requires regular module.json and compose.yaml files.")
        try:
            result[path.name] = _metadata(json.loads((path / "module.json").read_text()), path.name)
        except (ValueError, UnicodeError) as exc:
            raise ConfigError(f"Module {path.name} has invalid JSON metadata.") from exc
    ownership = set(CORE)
    for entry in result.values():
        if ownership.intersection(entry["services"]):
            raise ConfigError("Duplicate service ownership across modules/core.")
        ownership.update(entry["services"])
    return result


def resolve(selection, entries=None):
    entries = catalog() if entries is None else entries
    _unique_strings(selection, "selection", ID)
    ordered, visiting, visited = [], set(), set()
    def visit(name):
        if name not in entries:
            raise ConfigError(f"Unknown module or missing dependency: {name}.")
        if name in visiting:
            raise ConfigError("Module dependency cycle detected.")
        if name in visited:
            return
        visiting.add(name)
        for dependency in sorted(entries[name]["requires"]):
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
        ordered.append(name)
    for name in sorted(selection):
        visit(name)
    return ordered


def selected():
    path = ROOT / "local" / "selection.json"
    if path.is_symlink() or not path.is_file():
        raise ConfigError("Desired selection missing. Run ./pi init --preset standard for a new install or ./pi init --existing for migration.")
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or set(data) != {"schema_version", "modules"} or type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ValueError()
        return resolve(data["modules"])
    except (ValueError, TypeError, KeyError) as exc:
        raise ConfigError("Invalid local/selection.json; expected schema_version 1 and a modules array.") from exc


def compose_files(selection=None):
    ordered = selected() if selection is None else resolve(selection)
    return [ROOT / "docker-compose.yaml", *[ROOT / "modules" / name / "compose.yaml" for name in ordered]]


def metadata_for_services(selection=None):
    entries = catalog()
    ordered = selected() if selection is None else resolve(selection, entries)
    result = {}
    for name in ordered:
        entry = entries[name]
        for service in entry["services"]:
            if service in result or service in CORE:
                raise ConfigError("Duplicate service ownership across modules/core.")
            result[service] = {"module": name, "access": [row for row in entry["access"] if row["service"] == service],
                               "state": [row for row in entry["state"] if row["service"] == service], "secrets": entry["secrets"]}
    return result


def _model(files, consistency=True):
    args = ["config", "--format", "json"]
    if not consistency:
        args.extend(["--no-consistency", "--no-env-resolution"])
    try:
        return json.loads(run_compose(*args, files=files).stdout)
    except ValueError as exc:
        raise ConfigError("Compose returned an invalid model; private output was suppressed.") from exc


def _listener_host(host, env):
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if address.is_loopback:
        return True
    rfc1918 = (ipaddress.ip_network("10.0.0.0/8"), ipaddress.ip_network("172.16.0.0/12"), ipaddress.ip_network("192.168.0.0/16"))
    return (address.version == 4 and any(address in network for network in rfc1918)
            and env.get("ADMIN_BIND_IP") == host and env.get("ACK_LAN_ADMIN") == "yes")


def _ports_for_service(service, services):
    visited = set()
    while services[service].get("network_mode", "").startswith("service:"):
        if service in visited:
            raise ConfigError("Service network namespace cycle detected.")
        visited.add(service)
        service = services[service]["network_mode"].split(":", 1)[1]
        if service not in services:
            raise ConfigError("Service network namespace refers to a missing service.")
    return services[service].get("ports", [])


def validate_storage(model):
    marker = ROOT / "local" / "storage.json"
    if marker.is_symlink():
        raise ConfigError("Storage marker must not be a symbolic link.")
    mounts = []
    try:
        if marker.exists():
            data = json.loads(marker.read_text())
            if not isinstance(data, dict) or set(data) != {"mounts"} or not isinstance(data["mounts"], list):
                raise ValueError()
            mounts = data["mounts"]
        for mount in mounts:
            if not isinstance(mount, dict) or set(mount) - {"path", "device"} or not isinstance(mount.get("path"), str):
                raise ValueError()
            path = Path(mount["path"])
            if not path.is_absolute() or ".." in path.parts or ("device" in mount and type(mount["device"]) is not int):
                raise ValueError()
        root = ROOT.resolve()
        for spec in model.get("services", {}).values():
            for bind in spec.get("volumes", []):
                if bind.get("type") != "bind" or bind.get("read_only") or (bind.get("source"), bind.get("target")) in SYSTEM_BINDS:
                    continue
                source = Path(bind.get("source", ""))
                if not source.is_absolute():
                    raise ConfigError("Rendered state bind sources must be absolute paths.")
                resolved = source.resolve()
                outside = not resolved.is_relative_to(root)
                covering = [mount for mount in mounts if resolved.is_relative_to(Path(mount["path"]).resolve())]
                if outside and not resolved.exists():
                    raise ConfigError("An external state bind source is absent. Provision the verified mounted data directory explicitly before enabling this module.")
                if outside and not covering:
                    raise ConfigError("External state requires a covering expected filesystem in local/storage.json; directory existence alone does not prove mounted storage.")
                if not covering:
                    # New state directories inside the checkout may be created by
                    # prepare_bind_directories. Symlink escapes were resolved above.
                    continue
                expected = max(covering, key=lambda row: len(Path(row["path"]).resolve().parts))
                mountpoint = Path(expected["path"])
                if mountpoint.is_symlink() or not os.path.ismount(mountpoint):
                    raise ConfigError("An expected data filesystem is not mounted. No directories were created; remount and verify storage before retrying.")
                device = mountpoint.stat().st_dev
                if "device" in expected and device != expected["device"]:
                    raise ConfigError("An expected data filesystem has a different device identity; verify storage before retrying.")
                existing = resolved
                while not existing.exists() and existing != existing.parent:
                    existing = existing.parent
                if existing.stat().st_dev != device:
                    raise ConfigError("State resolves to a different filesystem than its expected mount; verify nested mounts and symlinks before retrying.")
    except (ValueError, KeyError, TypeError) as exc:
        raise ConfigError("Invalid local/storage.json; expected mounts with absolute path and optional integer device ID.") from exc


def validate(selection, probe_services=(), *, env_override=None, model_loader=None, runtime_checks=True):
    """Check real module semantics with optional isolated static inputs.

    CI supplies dummy environment values and a Compose loader using only its
    temporary env file. Runtime callers retain the private-config/storage checks.
    """
    entries = catalog()
    ordered = resolve(selection, entries)
    metadata = metadata_for_services(ordered)
    env = load_env() if env_override is None else dict(env_override)
    render = _model if model_loader is None else model_loader
    for name in ordered:
        if any(not env.get(key) for key in entries[name]["secrets"]):
            raise ConfigError(f"Module {name} is missing required private settings; review its secrets list. No values were printed.")
    owners = {}
    for name, files in [("core", [ROOT / "docker-compose.yaml"]), *[(name, [ROOT / "modules" / name / "compose.yaml"]) for name in ordered]]:
        fragment = render(files, consistency=False).get("services", {})
        services = set(fragment)
        if any(spec.get("env_file") for spec in fragment.values()):
            raise ConfigError("Module service env_file is unsupported; use declared private root .env settings.")
        if name != "core" and services != set(entries[name]["services"]):
            raise ConfigError(f"Module {name} service ownership differs between Compose and metadata.")
        for service in services:
            if service in owners:
                raise ConfigError("Duplicate service ownership across Compose fragments; silent merges are refused.")
            owners[service] = name
    model = render(compose_files(ordered))
    services = model.get("services", {})
    if 'pihole' in services:
        from service_config import validate_dns_mode
        mode = validate_dns_mode(env)
        declared = str(services['pihole'].get('environment', {}).get('FTLCONF_dns_listeningMode', 'local')).lower()
        if declared != mode:
            raise ConfigError('Pi-hole DNS listening mode differs from the reviewed private setting.')
    if set(services) != set(owners):
        raise ConfigError("The merged service set differs from declared ownership.")
    listeners, routes = {}, {443: "homer", 8443: "pihole"}
    for service, spec in services.items():
        if service in metadata and spec.get("network_mode") == "host":
            raise ConfigError("Optional modules must use isolated Docker networks, not host networking.")
        if service in metadata and spec.get("privileged"):
            raise ConfigError("Privileged optional containers are unsupported; pass only the explicitly required capabilities or devices.")
        for port in spec.get("ports", []):
            if "published" not in port:
                raise ConfigError("Randomly assigned backend ports are unsupported; publish a fixed loopback listener.")
            try:
                published = int(port["published"])
            except (TypeError, ValueError) as exc:
                raise ConfigError("Port ranges are unsupported; use explicit published ports.") from exc
            host = port.get("host_ip", "0.0.0.0")
            protocol = port.get("protocol", "tcp")
            if not 1 <= published <= 65535 or protocol not in ("tcp", "udp") or not _listener_host(host, env):
                raise ConfigError("Administration listeners must bind loopback, or the explicit acknowledged RFC1918 ADMIN_BIND_IP.")
            identity = (host, published, protocol)
            if identity in listeners:
                raise ConfigError("Conflicting published ports across enabled services.")
            listeners[identity] = service
        if service not in metadata:
            continue
        mounted = {row["target"] for row in spec.get("volumes", []) if not row.get("read_only", False)
                   and (row.get("source"), row["target"]) not in SYSTEM_BINDS}
        declared = {row["target"] for row in metadata[service]["state"]}
        if mounted != declared:
            raise ConfigError(f"Service {service} must classify every writable mount exactly once in state metadata.")
        for access in metadata[service]["access"]:
            if access["https_port"] in routes:
                raise ConfigError("Conflicting HTTPS routes across enabled modules.")
            routes[access["https_port"]] = service
            ports = _ports_for_service(service, services)
            if len([port for port in ports if port.get("protocol", "tcp") == "tcp"]) != 1:
                raise ConfigError(f"Service {service} access must resolve to exactly one TCP backend in Compose.")
    if runtime_checks:
        from service_config import active_file_secrets, validate_browser_vpn
        validate_browser_vpn(env, model, active_file_secrets(model))
        validate_storage(model)
    for (host, port, protocol), service in listeners.items():
        if not runtime_checks or service not in probe_services:
            continue
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        kind = socket.SOCK_STREAM if protocol == "tcp" else socket.SOCK_DGRAM
        try:
            with socket.socket(family, kind) as probe:
                probe.bind((host, port))
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                raise ConfigError(f"Required {protocol} port {port} is already occupied. No services changed.") from exc
            raise ConfigError(f"Cannot verify required {protocol} port {port}; check the selected bind address and host permissions.") from exc
    return model


def plan(enable=None, disable=None):
    current = selected()
    candidate = _candidate(current, enable, disable)
    model = validate(candidate)
    metadata = metadata_for_services(candidate)
    services = sorted(model["services"])
    planned = {
        "schema_version": 1, "modules": candidate, "services": services,
        "compose_argv": shlex.join(["docker", *compose_args(files=compose_files(candidate))]),
        "routes": [{"service": service, **route} for service, item in metadata.items() for route in item["access"]],
        "storage": [{"service": service, "type": mount.get("type"), "source": mount.get("source"), "target": mount["target"], "read_only": mount.get("read_only", False)}
                    for service, spec in model["services"].items() for mount in spec.get("volumes", [])],
        "resources": {service: {**{key: spec[key] for key in ("mem_limit", "cpus", "shm_size") if key in spec},
                                "deploy": spec.get("deploy", {}).get("resources", {})}
                      for service, spec in model["services"].items()},
        "status": "NEEDS_CONFIGURATION", "next_action": "Review the plan and private access/storage policy; live readiness has not been tested.",
    }
    return planned


def _candidate(current, enable=None, disable=None):
    if enable and disable:
        raise ConfigError("Enable and disable are separate operations.")
    if enable:
        return resolve(list(dict.fromkeys([*current, enable])))
    if disable:
        if disable not in catalog():
            raise ConfigError("Unknown module.")
        remaining = [name for name in current if name != disable]
        if disable in resolve(remaining):
            raise ConfigError("Cannot disable a dependency of another enabled module.")
        return resolve(remaining)
    return resolve(current)


def _write_selection(values):
    atomic_write(ROOT / "local" / "selection.json", json.dumps({"schema_version": 1, "modules": values}, indent=2) + "\n")


def _readiness(services):
    result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "doctor.py"), "--json", "--wait", "90", "--services", *services],
                            cwd=ROOT, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise ConfigError("New module services did not pass bounded doctor checks. Their output is private; run ./pi doctor after resolving the service issue.")


def _routes(action, module_ids):
    """Hook supplied by the access layer; it must mutate only owned routes.

    No hook means a visible pending setup step, not a claim of secure access.
    Hooks must raise before success on mutation failure and support rollback.
    """
    try:
        from access import module_routes
    except ImportError:
        return "NEEDS_CONFIGURATION"
    result = module_routes(action, module_ids)
    status = result.get("status") if isinstance(result, dict) else result
    if status not in ("PASS", "NEEDS_CONFIGURATION"):
        raise ConfigError("Private route registration failed; verify owned route state.")
    return status


def change(enable=None, disable=None, dry_run=False):
    reject_root()
    if dry_run:
        current = selected()
        candidate = _candidate(current, enable, disable)
        # Strict dry-run contract: read metadata only, no Docker or lock/file writes.
        return {"modules": candidate, "status": "NEEDS_CONFIGURATION", "next_action": "Dry run only. Run ./pi plan to validate the rendered model before applying."}
    with command_lock():
        current = selected()
        candidate = _candidate(current, enable, disable)
        if candidate == current:
            return {"modules": current, "status": "PASS", "next_action": "Desired selection already matches; no services changed."}
        before_metadata = metadata_for_services(current)
        after_metadata = metadata_for_services(candidate)
        added = sorted(set(after_metadata) - set(before_metadata))
        removed = sorted(set(before_metadata) - set(after_metadata))
        candidate_model = validate(candidate, probe_services=added)
        old_files, new_files = compose_files(current), compose_files(candidate)
        running_before = set(run_compose("ps", "--status", "running", "--services", files=old_files).stdout.split())
        if set(added) & running_before:
            raise ConfigError("An unselected service is already running. Reconcile inventory and selection before enablement.")
        core_before = run_compose("ps", "--all", "--quiet", *CORE, files=old_files).stdout.split()
        path = ROOT / "local" / "selection.json"
        original = path.read_bytes()
        changed_modules = sorted(set(candidate) - set(current) if enable else set(current) - set(candidate))
        attempted_routes = False
        try:
            if added:
                from service_config import validate_services, prepare_bind_directories
                env = load_env()
                validate_services(env, added)
                prepare_bind_directories({"services": {name: candidate_model["services"][name] for name in added}}, env)
                run_compose("up", "-d", "--no-deps", "--pull", "never", *added, files=new_files, timeout=180)
                _write_selection(candidate)
                _readiness(added)
                attempted_routes = True
                route_status = _routes("enable", changed_modules)
            else:
                # Stop with the previous model so removed service definitions still
                # exist. Keep containers and volumes for nondestructive re-enable.
                attempted_routes = True
                route_status = _routes("disable", changed_modules)
                run_compose("stop", *removed, files=old_files, timeout=180)
                _write_selection(candidate)
            core_after = run_compose("ps", "--all", "--quiet", *CORE, files=new_files).stdout.split()
            if core_after != core_before:
                raise ConfigError("Core container identity changed during the module operation; review concurrent operations.")
        except (ConfigError, OSError, subprocess.SubprocessError):
            atomic_write(path, original)
            rollback_ok = True
            try:
                if added:
                    run_compose("stop", *added, files=new_files, timeout=180)
                previously_running = sorted(set(removed) & running_before)
                if previously_running:
                    run_compose("start", *previously_running, files=old_files, timeout=180)
                if attempted_routes:
                    _routes("disable" if enable else "enable", changed_modules)
            except (ConfigError, OSError, subprocess.SubprocessError):
                rollback_ok = False
            message = "Module change failed; previous selection restored and data retained."
            if not rollback_ok:
                message += " Service/route rollback needs manual verification before retrying."
            raise ConfigError(message) from None
        return {"modules": candidate, "services_changed": added or removed, "status": route_status,
                "next_action": "Verify allowed and denied clients, HTTPS access, and application authentication; no live access guarantee is implied."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("modules")
    planner = commands.add_parser("plan")
    group = planner.add_mutually_exclusive_group()
    group.add_argument("--enable")
    group.add_argument("--disable")
    for command in ("enable", "disable"):
        item = commands.add_parser(command)
        item.add_argument("module")
        item.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "modules":
            enabled = set(selected())
            result = [{"id": name, "description": data["description"], "enabled": name in enabled, "requires": data["requires"]} for name, data in catalog().items()]
        elif args.command == "plan":
            result = plan(args.enable, args.disable)
        else:
            result = change(enable=args.module if args.command == "enable" else None,
                            disable=args.module if args.command == "disable" else None, dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
    except (ConfigError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc) if isinstance(exc, ConfigError) else "Module operation failed; inspect private local state.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
