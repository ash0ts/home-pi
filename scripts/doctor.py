#!/usr/bin/env python3
"""Read-only, redacted runtime observations; owner evidence stays a separate scope."""

import argparse
from datetime import datetime, timedelta, timezone
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import time

from lib.config import ConfigError, ROOT, docker, load_env, run_compose

STATUSES = {"PASS", "FAIL", "SKIP", "NEEDS_CONFIGURATION"}
SERVICE_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
NAME_RE = re.compile(r"^(?=.{1,253}\.?$)[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?\.?$")
CORE = {"pihole", "tailscale", "homer"}
KNOWN = CORE | {"uptime-kuma", "speedtest-tracker", "netdata", "portainer", "dozzle", "webtop", "gluetun", "freshrss"}
# Container target, scheme, path. Published host ports come from rendered Compose.
HTTP = {
    "homer": (8080, "http", "/"),
    "uptime-kuma": (3001, "http", "/"),
    "speedtest-tracker": (80, "http", "/"),
    "netdata": (19999, "http", "/api/v1/info"),
    "portainer": (9443, "https", "/api/status"),
    "dozzle": (8080, "http", "/"),
    "webtop": (3001, "https", "/"),
    "freshrss": (80, "http", "/"),
}
HOME = {
    "router_support": ("owner", "Review router ownership, model, supported firmware, and update responsibility."),
    "router_access": ("owner", "Review actual Wi-Fi, WPS, WAN administration, UPnP, port mappings, and exceptions."),
    "network_boundary": ("network", "Test IPv4/IPv6 direct and proxy paths from trusted, denied, and external clients."),
    "segmentation": ("network", "Test real guest and IoT isolation and intended service exceptions."),
    "accounts": ("owner", "Confirm unique credentials, MFA/passkeys, tailnet device review, and offline recovery."),
    "endpoints": ("owner", "Verify supported endpoints, SSH configuration, and a second management session."),
    "dns_coverage": ("network", "Test normal-client DNS, blocked fixture, IPv6, browser/VPN overrides, and policy exceptions."),
    "continuity": ("network", "Run the authorized DNS outage and return-to-normal drill with alternate management."),
    "recovery": ("owner", "Verify encrypted off-device backups, isolated application restore, and matching-data rollback."),
    "ongoing_operation": ("owner", "Verify backup schedule, disk/stale-backup alerts, and independent observer if claimed."),
}


def utcnow():
    return datetime.now(timezone.utc)


def stamp(moment=None):
    return (moment or utcnow()).isoformat(timespec="seconds").replace("+00:00", "Z")


def check(identifier, status, evidence, next_action="", *, module="core", scope="runtime", method="automatic", required=True, observed_at=None):
    return {"id": identifier, "module": module, "scope": scope, "status": status,
            "method": method, "observed_at": observed_at or stamp(), "evidence": evidence,
            "next_action": next_action, "required": required}


def home_checks(path, now=None):
    """Accept fresh, explicit manual observations; never echo input free text."""
    now = now or utcnow()
    rows = {}
    valid = False
    try:
        path = Path(path)
        if path.is_symlink() or path.stat().st_mode & 0o077 or path.stat().st_size > 65536:
            raise ValueError("private evidence file required")
        payload = json.loads(path.read_text())
        if payload.get("schema_version") != 1 or not isinstance(payload.get("checks"), list):
            raise ValueError("schema")
        for item in payload["checks"]:
            identifier = item.get("id")
            if identifier not in HOME or identifier in rows:
                raise ValueError("unknown or duplicate check")
            rows[identifier] = item
        valid = True
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    result = []
    for identifier, (scope, action) in HOME.items():
        item = rows.get(identifier, {}) if valid else {}
        observed = None
        status = "NEEDS_CONFIGURATION"
        evidence = "Required owner/client observation is missing, invalid, or stale."
        try:
            when = datetime.fromisoformat(item["observed_at"].replace("Z", "+00:00"))
            if (when.tzinfo is None or not now - timedelta(days=30) <= when <= now + timedelta(minutes=5)
                    or item.get("method") != "manual" or item.get("scope") != scope
                    or item.get("evidence_supplied") is not True
                    or item.get("status") not in {"PASS", "FAIL", "NEEDS_CONFIGURATION"}):
                raise ValueError("invalid observation")
            status = item["status"]
            observed = stamp(when.astimezone(timezone.utc))
            evidence = "Fresh owner-supplied observation recorded; underlying evidence remains private."
        except (KeyError, ValueError, TypeError, AttributeError):
            pass
        result.append(check("home." + identifier, status, evidence, "" if status == "PASS" else action,
                            module="home-baseline", scope=scope, method="manual", observed_at=observed))
    return result


def selected_services(model, env, requested=None):
    services = model.get("services", {})
    if not isinstance(services, dict) or any(not SERVICE_RE.fullmatch(name) for name in services):
        raise ConfigError("Compose returned invalid service identifiers.")
    profiles = {value for value in re.split(r"[,\s]+", env.get("COMPOSE_PROFILES", "")) if value}
    active = {name for name, spec in services.items()
              if not spec.get("profiles") or profiles.intersection(spec["profiles"]) or "*" in profiles}
    if requested:
        if set(requested) - active:
            raise ConfigError("Requested doctor services are missing or disabled in the desired selection.")
        active = set(requested)
    return sorted(active)


def container_observation(service):
    response = run_compose("ps", "--all", "--quiet", service, check=False)
    ids = response.stdout.split()
    if response.returncode or len(ids) != 1 or not re.fullmatch(r"[a-fA-F0-9]{12,64}", ids[0]):
        return check("container." + service, "FAIL", "Expected exactly one managed container; it is absent or unavailable.",
                     "Create only this enabled service with the managed Compose command, then rerun doctor.", module=service), None, []
    # Excludes environment, labels, logs, health output, and command arguments.
    template = '[{{json .State.Status}},{{with index .State "Health"}}{{json .Status}}{{else}}"none"{{end}},{{json .Mounts}}]'
    response = docker("inspect", "--format", template, ids[0], check=False)
    try:
        state, health, mounts = json.loads(response.stdout)
        if response.returncode or state not in {"created", "running", "paused", "restarting", "removing", "exited", "dead"}:
            raise ValueError("state")
        if health not in {"none", "starting", "healthy", "unhealthy"} or not isinstance(mounts, list):
            raise ValueError("health")
    except (ValueError, TypeError):
        return check("container." + service, "FAIL", "Container state inspection failed.",
                     "Check daemon/container access privately and rerun doctor.", module=service), None, []
    ready = state == "running" and health in {"none", "healthy"}
    evidence = "Container is running" + (" and its native/configured healthcheck is healthy." if health == "healthy" else "; no native healthcheck is defined.")
    if not ready:
        evidence = "Container is not running or its healthcheck is not ready."
    return check("container." + service, "PASS" if ready else "FAIL", evidence,
                 "" if ready else "Inspect this service privately; wait for startup or repair its configuration.", module=service), ids[0], mounts


def http_endpoint(service, model):
    if service == "pihole":
        value = model["services"][service].get("environment", {}).get("FTLCONF_webserver_port", "80")
        # Initial host-mode Pi-hole supports a specific loopback HTTP listener.
        match = re.fullmatch(r"(?:127\.0\.0\.1:)?([0-9]+)", str(value))
        return (int(match[1]), "http", "/admin/") if match else None
    if service not in HTTP:
        return None
    target, scheme, path = HTTP[service]
    spec = model["services"][service]
    if str(spec.get("network_mode", "")).startswith("service:"):
        spec = model["services"].get(spec["network_mode"].split(":", 1)[1], {})
    for port in spec.get("ports", []):
        if isinstance(port, dict) and int(port.get("target", 0)) == target and port.get("protocol", "tcp") == "tcp":
            host = port.get("host_ip", "0.0.0.0")
            if host not in {"127.0.0.1", "0.0.0.0", ""}:
                return None
            value = str(port.get("published", ""))
            if value.isdigit() and 0 < int(value) <= 65535:
                return int(value), scheme, path
    return None


def http_observation(service, endpoint):
    if endpoint is None:
        return check("http." + service, "NEEDS_CONFIGURATION", "No supported local backend endpoint is declared.",
                     "Declare a tested local backend and verify the separate private HTTPS route.", module=service)
    port, scheme, path = endpoint
    connection = None
    try:
        if scheme == "https":
            # These two upstream backends use self-signed certificates. This checks
            # local liveness only; never claim external TLS trust or proxy auth.
            context = ssl._create_unverified_context() if service in {"webtop", "portainer"} else ssl.create_default_context()
            connection = http.client.HTTPSConnection("127.0.0.1", port, timeout=3, context=context)
        else:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        connection.request("GET", path)
        code = connection.getresponse().status
        ready = 200 <= code < 400 or code in {401, 403}
        detail = "Local backend responded; authenticated use and private HTTPS trust are separate checks."
        if code in {401, 403}:
            detail = "Local backend requires authentication; liveness only, login has not been tested."
        return check("http." + service, "PASS" if ready else "FAIL", detail if ready else "Backend returned an unsuccessful status.",
                     "" if ready else "Review service startup and backend listener privately.", module=service)
    except (OSError, http.client.HTTPException):
        return check("http." + service, "FAIL", "Local HTTP/TLS backend could not be reached.",
                     "Check service readiness and listener settings; do not disable proxy certificate validation.", module=service)
    finally:
        if connection:
            connection.close()


def upstream_observation(container_id, spec):
    wanted = spec.get("environment", {}).get("FTLCONF_dns_upstreams", "")
    expected = [value.strip() for value in re.split(r"[;\n]", str(wanted)) if value.strip()]
    response = docker("exec", container_id, "pihole-FTL", "--config", "dns.upstreams", check=False)
    raw = response.stdout.strip()
    actual = [value.strip().strip('\"\'') for value in raw[1:-1].split(",") if value.strip()] if raw.startswith("[") and raw.endswith("]") else []
    okay = response.returncode == 0 and bool(expected) and actual == expected
    return check("pihole.upstreams", "PASS" if okay else "FAIL",
                 "Effective FTL upstreams match the declared configuration." if okay else "Effective FTL upstreams could not be verified against declared configuration.",
                 "" if okay else "Use FTLCONF_dns_upstreams and recreate only Pi-hole after checking existing state.", module="pihole")


def tailscale_observation(container_id):
    response = docker("exec", container_id, "tailscale", "status", "--json", check=False)
    try:
        state = json.loads(response.stdout).get("BackendState")
    except (ValueError, AttributeError):
        state = None
    if state in {"NeedsLogin", "NeedsMachineAuth", "NoState"}:
        return check("tailscale.enrollment", "NEEDS_CONFIGURATION", "Tailscale enrollment/authorization is pending.",
                     "Enroll or approve this node privately; preserve its existing persistent state.", module="tailscale")
    okay = response.returncode == 0 and state == "Running"
    return check("tailscale.enrollment", "PASS" if okay else "FAIL",
                 "Tailscale backend is running; client grants and reachability require separate tests." if okay else "Tailscale backend is unavailable or stopped.",
                 "" if okay else "Inspect Tailscale privately; verify state mount and daemon readiness.", module="tailscale")


def dns_query(server, name, tcp=False):
    args = ["dig", "+time=2", "+tries=1", "+noall", "+comments", "+answer"]
    if tcp:
        args.append("+tcp")
    args.extend(["@" + server, name, "A"])
    try:
        response = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)
    except FileNotFoundError:
        return "missing", []
    except subprocess.TimeoutExpired:
        return "failed", []
    match = re.search(r"status: ([A-Z]+),", response.stdout)
    status = match[1] if match and response.returncode == 0 else "failed"
    answers = []
    for line in response.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 5 and fields[3] == "A":
            try:
                answers.append(str(ipaddress.IPv4Address(fields[4])))
            except ipaddress.AddressValueError:
                pass
    return status, answers


def dns_observations(env):
    server = env.get("DNS_PROBE_SERVER", "")
    permitted = env.get("DNS_PROBE_NAME", "example.com")
    blocked = env.get("DNS_BLOCK_TEST_NAME", "")
    expected = env.get("DNS_BLOCK_TEST_ADDRESS", "")
    try:
        ipaddress.ip_address(server)
        if not NAME_RE.fullmatch(permitted):
            raise ValueError("name")
    except ValueError:
        return [check("dns.configuration", "NEEDS_CONFIGURATION", "DNS probe target is not explicitly configured.",
                      "Set DNS_PROBE_SERVER to an in-scope resolver address and DNS_PROBE_NAME to a permitted name.", module="pihole", scope="network")]
    results = []
    for tcp in (False, True):
        mode = "tcp" if tcp else "udp"
        status, answers = dns_query(server, permitted, tcp)
        okay = status == "NOERROR" and bool(answers) and all(ipaddress.ip_address(a).is_global for a in answers)
        result = "NEEDS_CONFIGURATION" if status == "missing" else ("PASS" if okay else "FAIL")
        results.append(check("dns." + mode, result,
                             "Declared resolver returned a permitted public A answer." if okay else "Permitted DNS response was unavailable or unusable.",
                             "" if okay else "Install dig and verify permitted resolution over this transport on the declared resolver.", module="pihole", scope="network"))
    try:
        if not NAME_RE.fullmatch(blocked):
            raise ValueError("fixture")
        if expected not in {"NXDOMAIN", "NODATA"}:
            expected = str(ipaddress.IPv4Address(expected))
    except ValueError:
        results.append(check("dns.blocking", "NEEDS_CONFIGURATION", "Controlled DNS blocking fixture/expected response is missing.",
                             "Configure a controlled blocked name and DNS_BLOCK_TEST_ADDRESS (IPv4, NXDOMAIN, or NODATA).", module="pihole", scope="network"))
        return results
    for tcp in (False, True):
        status, answers = dns_query(server, blocked, tcp)
        okay = ((expected == "NXDOMAIN" and status == "NXDOMAIN") or
                (expected == "NODATA" and status == "NOERROR" and not answers) or
                (expected not in {"NXDOMAIN", "NODATA"} and status == "NOERROR" and answers == [expected]))
        results.append(check("dns.blocking." + ("tcp" if tcp else "udp"), "PASS" if okay else ("NEEDS_CONFIGURATION" if status == "missing" else "FAIL"),
                             "Configured blocked fixture produced its expected response." if okay else "Blocked fixture did not produce the configured response.",
                             "" if okay else "Verify fixture membership, client group, and configured blocking mode without saving browsing history.", module="pihole", scope="network"))
    return results


def disk_observations(mounts):
    paths = {str(ROOT)}
    paths.update(item.get("Source", "") for item in mounts if item.get("RW") and item.get("Type") in {"bind", "volume"})
    result = []
    for index, path in enumerate(sorted(paths - {""})):
        try:
            usage = shutil.disk_usage(path)
            okay = usage.free / usage.total >= 0.20
            result.append(check("disk." + str(index), "PASS" if okay else "FAIL",
                                "State filesystem has at least 20 percent free." if okay else "State filesystem is below the proposed 20 percent free threshold.",
                                "" if okay else "Review retention and backup/storage usage on the affected state filesystem."))
        except OSError:
            result.append(check("disk." + str(index), "NEEDS_CONFIGURATION", "A state filesystem is not accessible from this host.",
                                "Run doctor on the Docker host and verify the expected data storage is mounted."))
    return result


def ownership_observation(service, spec, mounts):
    environment = spec.get("environment", {})
    try:
        owner = int(environment["PUID"]), int(environment["PGID"])
        mount = next(item for item in mounts if item.get("Destination") == "/config")
        metadata = Path(mount["Source"]).stat()
        okay = (metadata.st_uid, metadata.st_gid) == owner
        return check("ownership." + service, "PASS" if okay else "FAIL",
                     "Config mount directory matches declared PUID/PGID." if okay else "Config mount directory does not match declared PUID/PGID.",
                     "" if okay else "Inspect current data ownership before changing it; preserve existing state and use this service's supported migration.", module=service)
    except (KeyError, ValueError, OSError, StopIteration, TypeError):
        return check("ownership." + service, "NEEDS_CONFIGURATION", "Config mount ownership could not be verified on this host.",
                     "Run doctor on the Docker host and verify /config ownership against declared PUID/PGID.", module=service)


def collect(env, model, services):
    results = []
    mounts = []
    for service in sorted((KNOWN | set(model.get("services", {}))) - set(services)):
        results.append(check("container." + service, "SKIP", "Service is disabled or outside the requested check scope.",
                             module=service, required=False))
    for service in services:
        try:
            observation, container_id, service_mounts = container_observation(service)
            results.append(observation)
            mounts.extend(service_mounts)
            if not container_id:
                continue
            if service in HTTP or service == "pihole":
                results.append(http_observation(service, http_endpoint(service, model)))
            if service == "pihole":
                results.append(upstream_observation(container_id, model["services"][service]))
                results.extend(dns_observations(env))
            if service == "tailscale":
                results.append(tailscale_observation(container_id))
            if service in {"webtop", "speedtest-tracker"}:
                results.append(ownership_observation(service, model["services"][service], service_mounts))
        except (ConfigError, OSError, ValueError, TypeError):
            results.append(check("probe." + service, "FAIL", "A runtime probe could not complete safely.",
                                 "Check daemon access and service configuration privately; no raw diagnostic output is included.", module=service))
    results.extend(disk_observations(mounts))
    return results


def successful(checks, home_baseline=False):
    return all(item["status"] in {"PASS", "SKIP"} for item in checks
               if item["required"] and (home_baseline or item["module"] != "home-baseline"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--home-baseline", action="store_true", help="Fail while required owner/network observations remain unverified.")
    parser.add_argument("--services", nargs="+", help="Limit runtime checks to named enabled services.")
    parser.add_argument("--wait", type=int, default=0, metavar="SECONDS", help="Retry runtime readiness for up to 300 seconds, in addition to bounded probe duration.")
    parser.add_argument("--evidence", type=Path, default=ROOT / "local/home-evidence.json")
    args = parser.parse_args(argv)
    if not 0 <= args.wait <= 300:
        parser.error("--wait must be between 0 and 300 seconds")
    checks = []
    services = []
    try:
        env = load_env()
        model = json.loads(run_compose("config", "--format", "json").stdout)
        services = selected_services(model, env, args.services)
        deadline = time.monotonic() + args.wait
        while True:
            checks = collect(env, model, services)
            if successful(checks) or time.monotonic() >= deadline:
                break
            # Missing owner input/configuration will not be repaired by waiting.
            if any(item["status"] == "NEEDS_CONFIGURATION" and item["module"] != "tailscale" for item in checks):
                break
            time.sleep(min(2, max(0, deadline - time.monotonic())))
    except (ConfigError, OSError, ValueError, TypeError):
        checks = [check("runtime.configuration", "NEEDS_CONFIGURATION", "Private configuration or the managed Compose model is unavailable.",
                        "Run configure/validate and check Docker access. Raw configuration/error output is intentionally omitted.")]
    checks.extend(home_checks(args.evidence))
    report = {"schema_version": 1, "observed_at": stamp(), "runtime_ready": successful(checks),
              "runtime_scope": "selected-services" if args.services else "desired-selection", "services": services,
              "home_baseline_verified": successful([item for item in checks if item["module"] == "home-baseline"], True),
              "checks": checks}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for item in checks:
            print(f'{item["status"]:19} {item["scope"]:8} {item["id"]}: {item["evidence"]}')
            if item["next_action"]:
                print("  Next: " + item["next_action"])
        print("Runtime readiness and the dated owner/network baseline are separate results.")
    return 0 if successful(checks, args.home_baseline) else 1


if __name__ == "__main__":
    sys.exit(main())
