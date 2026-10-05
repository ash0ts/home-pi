# Architecture and capability boundaries

The project uses Docker Compose and a small command layer. Pi-hole supplies DNS
to explicitly configured clients; Tailscale supplies private management access;
Homer links enabled services. Optional applications share one documented access,
health, backup, and update contract. Services on this Pi share its host, disk,
power, and network failure boundary.

This document states the implementation contract. Consult
[implementation status](implementation-status.md) for evidence and pending gates;
repository work alone establishes no live network or recovery guarantees.

| Capability | Boundary and required evidence |
| --- | --- |
| LAN DNS filtering | Clients must actually use Pi-hole. DHCP, IPv6 DNS, secure/private DNS, and VPN overrides need client tests. |
| Private management | Selected HTTPS proxy listeners plus explicit tailnet permissions and application auth. Direct backends and host-network Pi-hole need separate checks. |
| Optional browser VPN | Webtop shares Gluetun's network namespace; UI publishes through that owner. Enabled only after explicit configuration and failure testing. |
| Subnet router or exit node | Separate opt-in mode requiring actual topology, authorization, routing and client egress tests. |
| Whole-home commercial VPN | A separate router/gateway project. Setting router DNS to Pi-hole does not route application traffic through a VPN. |
| Monitoring | On-Pi checks report service problems while available. A full-host outage needs a tested off-Pi observer. |
| Recovery | Encrypted off-device state plus separately accessible credentials and verified application-state restore. |

## Compose and configuration ownership

`docker-compose.yaml` is canonical. As a service becomes a module, its one
definition moves to `modules/<id>/compose.yaml`; never duplicate it in the root
or embed a second template in setup. Managed commands use an explicit ordered
local file list, one preserved Compose project name, and base-relative paths.
Inherited Compose file/profile settings cannot silently select another stack.

Keep actual images, mounts, listeners, health checks, and limits in Compose.
Module metadata supplies the facts Compose does not describe: stable identity,
dependencies, access intent, essential/history/cache state, consistency adapter,
required secret names, and operational expectations. No arbitrary shell hooks,
database, scheduler, or network management daemon belong in this contract.

One ignored desired selection drives profiles/modules. New modules are disabled
by default. The new-install standard selects core plus Uptime Kuma; diagnostics,
privileged administration, and the browser are opt-in. Migration first inventories
and preserves all currently enabled services. Adding a module must not require a
service-specific installer branch. Disabling one stops only its owned services,
removes owned routes/monitor registrations, preserves data, and must not restart
DNS/Tailscale or disable a required dependency.

Configuration generation preserves valid existing secrets and application keys,
writes private files atomically with mode 0600, and keeps real values out of logs
and CI. Recreating the affected service applies environment changes; restarting
a container alone does not. Preserve mount paths, service UID/GID, named-volume
identities, and Tailscale state before contemplating any data migration.

## Access and privilege

Administrative backends default to loopback and require an implemented private
HTTPS forwarding path. Loopback binding by itself does not expose a service on
the Tailscale IP. One route owner must preserve unrelated Serve entries and
check collisions. Distinct HTTPS listener ports avoid assuming every application
supports URL subpaths. LAN aliases under `home.arpa` do not automatically receive
tailnet HTTPS certificates. Public Funnel and router forwarding are not defaults.

Pi-hole remains host-networked during the initial migration, so its web/DNS
listeners require independent policy. Host and forwarded container firewall
paths differ; test both IPv4 and IPv6 from allowed and denied clients. See the
[H0 matrix](home-security.md#access-acceptance-matrix).

Portainer's Docker socket gives privileged management access. A socket mounted
`:ro` does not restrict Docker API methods. Dozzle's needs and any socket proxy
must be validated separately; no blanket privilege reduction should silently
break collectors or initialization. General coding agents and heavy inference,
OCR, firmware builds, or indexing belong elsewhere if they degrade DNS.

## State, maintenance, and browser isolation

Backups inventory every enabled bind mount and named volume, including private
config, Pi-hole, Tailscale, Homer, application databases/configuration, Portainer,
and Netdata state. Cache exclusions are deliberate. Use a supported database
backup adapter or stop the affected writer; a live SQLite file copy alone is
insufficient. A restored Tailscale identity or production DNS must never be
started alongside the original during a drill.

Reviewed image versions and verified digests make updates reproducible. Retain
the source revision, previous images, snapshot, and application versions. Stop
the old Watchtower container explicitly during authorized migration; removing
YAML does not prove it stopped. Rollback may require matching database state.
Routine maintenance also covers OS/router/device support, updates, and reboot
recovery. Adding Renovate configuration does not install its external integration.

The optional browser design gives Gluetun ownership of the VPN namespace and
Webtop `network_mode: service:gluetun`. Keep DNS and Tailscale independent; host
Mullvad is a separately documented legacy mode until authorized cutover. Test
startup failure, tunnel loss, process failure, owner restart/recreation, fresh
DNS and IP-literal egress in IPv4/IPv6 from the browser namespace and the actual
browser. Readiness dependencies and a host public-IP check cannot establish
runtime fail-closed behavior. Browser DNS initially follows its declared VPN
resolver path; ordinary LAN Pi-hole upstream traffic is not automatically tunneled.

## Capacity and extensions

Bound logs, history, and maintenance transfers on the actual state filesystem.
Proposed operating thresholds leave 25% of physical RAM and 20% of data storage
free; these are targets to measure, not reservations or achieved benchmarks.
Measure DNS latency, pressure/swap, throttling, disk writes, and optional workload
interference before imposing caps on essential services. Shared-memory limits
are limits, not preallocated RAM.

FreshRSS with SQLite is the first new module; private authentication, bounded
retention, supported refresh, and restored read/starred state are acceptance
requirements. Subscriptions come from the user's chosen feeds/OPML. Syncthing
waits for specific folders and independent backup. Home Assistant Container and
ESPHome wait for a real device/integration; no reimage or assumed radio/printer.
Each extension inherits H0, access, storage, restore, monitoring, and performance
gates. Optional development can proceed in isolation while live owner checks
remain open.
