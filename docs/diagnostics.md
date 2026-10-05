# Diagnostics and evidence

Run `./scripts/doctor.sh` on the Docker host. It reads the configured project and
desired services, inspects narrow container fields, and prints controlled,
redacted observations. It never prints container environments, health logs,
upstream addresses, raw DNS answers, peer/device details, or owner evidence text.
Full production Compose output must remain private.

```sh
./scripts/doctor.sh --json
./scripts/doctor.sh --services pihole tailscale homer --wait 90
./scripts/doctor.sh --home-baseline --json
```

`--services` limits the runtime scope to explicitly named enabled services;
omitting it checks the desired selection. Disabled/out-of-scope services are
`SKIP`. `--wait 0..300` retries transient readiness failures; each network probe
and Docker command has its own timeout, so wall-clock time can exceed the retry
window by the current probe pass. Missing non-enrollment configuration returns
promptly. There is no fixed startup sleep or full-stack restart.

An enabled runtime check with `FAIL` or `NEEDS_CONFIGURATION` makes doctor exit
1. Missing home controls always appear in the report, but affect the exit status
only with `--home-baseline`. In that mode every required control must have a
fresh owner observation. Successful container health never becomes a home
security claim.

## What is checked

Image-native health probes are retained. Dozzle uses `/dozzle healthcheck`;
Portainer is checked through its local HTTPS endpoint without assuming shell or
HTTP client tools exist inside the image.

- Selected containers exist and run; native/configured healthchecks are ready.
- Local HTTP backends respond; 401/403 is liveness only, not a successful login.
  Webtop and Portainer local self-signed backend probes do not verify external
  TLS trust. Verify private HTTPS and app authentication from clients separately.
- Pi-hole's effective `pihole-FTL --config dns.upstreams` matches the rendered
  `FTLCONF_dns_upstreams`. CLI output is normalized in memory, never displayed.
- Its effective DNS listener mode matches the declared `local` or acknowledged
  `all` mode; a match does not prove remote denial or household client coverage.
- Tailscale `BackendState` distinguishes pending enrollment from failure without
  dumping peer data. Identity persistence and denied-client tests remain live
  acceptance checks.
- Speedtest/Webtop config-directory ownership matches declared PUID/PGID.
- Writable state mount filesystems meet the proposed 20% free threshold. Inaccessible
  sources require running on the real Docker host. A capacity check does not
  prove an external disk is the expected mounted device; validate that before start.

Home Assistant and Syncthing use the same container/listener/HTTP checks. Their
device automations, proxy login and file synchronization require the separate
live acceptance in the [home](../modules/home/README.md#live-acceptance) and
[files](../modules/files/README.md#live-acceptance) runbooks. Syncthing ownership
is checked before managed startup/enable/update; doctor does not repeat that
service-specific ownership check.

Use [Pi-hole's configuration documentation](https://docs.pi-hole.net/ftldns/configfile/)
when interpreting environment-controlled values. Settings supplied through the
environment are controlled by Compose; edit private configuration and recreate
only the affected service to apply changes. Do not overwrite existing custom
dnsmasq configuration without inventorying it.

## Functional DNS probes

Set the following in private `.env`. Values shown are descriptions, not a usable
configuration; use an actual in-scope Pi address and configured fixture:

| Variable | Required value |
| --- | --- |
| `DNS_PROBE_SERVER` | Explicit IPv4 or IPv6 resolver address; missing means unverified |
| `DNS_PROBE_NAME` | Harmless permitted name with a public IPv4 A answer; defaults to `example.com` |
| `DNS_BLOCK_TEST_NAME` | Controlled name explicitly blocked for this probe client/group |
| `DNS_BLOCK_TEST_ADDRESS` | Expected IPv4 blocking answer, `NXDOMAIN`, or `NODATA` |

Install `dig` on the probe host. Doctor tests UDP and TCP, checks DNS status and
answers, and rejects empty successful responses for permitted resolution. A
blocked fixture must already be configured; doctor makes no Pi-hole changes.
`NXDOMAIN` and `NODATA` modes require the owner to establish that the fixture is
blocked; a nonexistent domain by itself is not evidence of filtering.

This probe establishes behavior from the doctor host for the declared resolver
and A record type. It does not prove household DNS coverage, AAAA behavior,
globally routable IPv6 exposure, browser private DNS, or blocked-client policy.
Repeat the [home-network matrix](home-security.md#access-acceptance-matrix) from
the specified clients, with both address families and direct/proxy endpoints.

## Private manual observations

Store observations in ignored `local/home-evidence.json`, mode 0600. This file
contains conclusions only; put detailed redacted notes in `local/home-network.md`.
No credentials, account recovery codes, or browsing history belong in either.
Create an entry only after the named test/settings review is actually performed:

```json
{
  "schema_version": 1,
  "checks": [
    {
      "id": "router_support",
      "scope": "owner",
      "status": "NEEDS_CONFIGURATION",
      "method": "manual",
      "observed_at": "2026-10-05T00:00:00Z",
      "evidence_supplied": true
    }
  ]
}
```

Replace the example timestamp with the actual UTC observation time. Accepted IDs
and scopes match the inventory: owner scope `router_support`, `router_access`,
`accounts`, `endpoints`, `recovery`, `ongoing_operation`; network scope
`network_boundary`, `segmentation`, `dns_coverage`, `continuity`. Each scope covers
all applicable rows in that control, not one convenient passing client.

Doctor accepts `PASS`, `FAIL`, or `NEEDS_CONFIGURATION` manual observations no
older than 30 days and no more than five minutes in the future. Wrong scope,
automatic method, duplicate/unknown IDs, invalid schema, public file permissions,
missing entries, and stale observations remain `NEEDS_CONFIGURATION`. Essential
home controls cannot be silently skipped. Evidence free text is never echoed.
Retest immediately after relevant topology/account changes even if the date is
still fresh; the script cannot detect an unrecorded owner change.

JSON reports have `schema_version: 1`, `observed_at`, `runtime_scope`, `services`,
`runtime_ready`, `home_baseline_verified`, and `checks`. Every check has `id`,
`module`, `scope`, `status`, `method`, `observed_at`, controlled `evidence`,
`next_action`, and `required`. These are dated observations, not certification.
