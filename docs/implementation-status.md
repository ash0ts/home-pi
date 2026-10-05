# Delivery and validation

Continue from the [remaining-work checklist](TODO.md). Runtime implementation is
merged through [`8670510`](https://github.com/ash0ts/home-pi/commit/8670510).
The owner confirmed the Pi is not set up yet; nothing has been deployed to the
household. This document separates repository delivery from live acceptance.

## Useful-home follow-up

Merged on 2026-10-05 as [network setup (#10)](https://github.com/ash0ts/home-pi/pull/10),
[Home Assistant (#11)](https://github.com/ash0ts/home-pi/pull/11), and
[Syncthing (#12)](https://github.com/ash0ts/home-pi/pull/12). Both new modules stay
disabled until selected. These changes do not deploy to the household.

The owner selected network setup, remote DNS, automation and selected-folder sync
on 2026-10-05. The [network guide](network.md) prepares native device profiles,
guest boundary checks and monitoring. Pi-hole retains local DNS by default;
remote DNS is opt-in with explicit boundary acknowledgment and scoped updates.
Tests check the gate and observed-vs-declared listener modes with fake commands.
No router/firewall/tailnet policy, notifications or client DNS settings were
changed. The actual hardware and recovery checks below remain pending.

The optional `home` module adds Home Assistant Container with an isolated bridge,
loopback backend, private enrollment/proxy instructions and full `/config` backup
classification. Its reviewed 2026.9.4 multi-platform manifest and ARM64 child were
read from the registry; runtime/device behavior remains a separate live gate.

A disposable ARM64 fixture on an internal Docker network ran the
Home Assistant HTTP probe and retained its configuration through recreation.
The fixture did not test host forwarding, owner login, real devices or restore;
its exact containers/network were removed.

The optional `files` module adds Syncthing 2.1.5 with a non-root process, private
GUI, no published incoming sync ports, disabled native upgrades and complete
stop-consistent identity/config/index/file state. Its multi-platform and ARM64
child manifests were verified from the registry.

A disposable internal ARM64 two-peer fixture verified native health, empty
initial folder selection, explicit pairing, direct file/edit sync, retained
identity after recreation, deletion propagation, and isolated identity/file
restoration from a stopped-writer copy. It contacted no household peers; its
containers/network were removed. This was not encrypted off-device recovery,
mobile support, guest isolation, conflict acceptance or a real Pi capacity test.

The complete local suite passed all 143 tests with no skips after using the
existing test-only restic binary for the encrypted recovery fixture. Static
validation, YAML lint and all 13 registry ARM64 checks passed. Live checklist
items remain pending.

### CI and merge record

The owner explicitly requested merging after local verification while the final
CI jobs were queued. GitHub merged all three PRs without a branch-rule bypass.
The [initial Syncthing revision's CI](https://github.com/ash0ts/home-pi/actions/runs/37363763773)
passed all 143 tests and static/registry checks. That result applies to its exact
head (`91f5dcc`), before the documentation evidence update; it is not a PASS for
every final PR head.

The [Home Assistant run](https://github.com/ash0ts/home-pi/actions/runs/37363758581)
later ended without executing steps because GitHub could not acquire a hosted
runner. This is an infrastructure failure, with no test result. Consult each
PR's checks and the [merged-revision run](https://github.com/ash0ts/home-pi/actions/runs/37364909056)
for current results. Do not infer successful CI or household acceptance from
merge status alone.

## Original baseline

Implemented from the supplied plan on 2026-10-05, starting at
`e7dd701654a4184ae31bb7ea527ac7a90d917ade`. The user requested a leaner stack:
seven dependent PRs, with native application configuration and manual operations
instead of custom portal, notification and measurement frameworks.

| Layer | Repository change |
| --- | --- |
| 1 | Deterministic private configuration, canonical Compose, inventory and home baseline runbooks |
| 2 | Current service settings and scoped, redacted readiness checks |
| 3 | Explicit service selection and owned private Tailscale HTTPS routes |
| 4 | Encrypted restic backups and fresh-target quarantine restore |
| 5 | Thin `pi` CLI and optional Compose modules with declared state/access |
| 6 | Immutable ARM64 images, backed-up scoped updates, CI and proposed dependency updates |
| 7 | Optional FreshRSS and browser VPN configuration, bounded logs and concise operating procedures |

E2's dashboard and notifications use Homer and Kuma's native configuration.
There is no generated portal, custom alert daemon, monitor database editor or
measurement command. At baseline delivery, E4 file sync and E5 home automation
were deferred. The follow-up above delivers the selected modules; actual pairing
and acceptance still require the owner's devices. Optional applications stay
disabled until selected; new installations select core plus Uptime Kuma.

### Baseline evidence

- Behavioral tests use temporary configuration and fake external commands; real
  Compose tests render dummy values and validate module ownership/state/access.
- Shell syntax, ShellCheck, shfmt, YAML lint and secret scanning are CI checks.
  `config/images.lock.json` records reviewed release tags, exact digests and
  ARM64 child manifests; CI rechecks runnable references against registries.
- Disposable ARM64 Docker checks verified Pi-hole DNS/listeners/effective
  upstreams, Homer startup, and FreshRSS SQLite/authentication/refresh.
- FreshRSS imported a local fixture feed and OPML. Real application read/star
  mutations and exported subscriptions survived recreation, stopped-writer
  archive capture, encrypted local restic backup/restore, and a separate
  restored application. SQLite integrity and numeric archive ownership passed.
  An extension marker survived. All uniquely owned fixture resources were removed.
- A disposable namespace fixture verified Compose waits for the owner and
  recreating both services attaches the consumer to the new owner. This was
  a namespace lifecycle check, not a VPN traffic test.

Local restic evidence does not establish off-device recovery. Mocked failed-update
checks do not establish a production migration or rollback. CI is the authoritative
record of commands/results for each exact PR head.

## Pending on the actual deployment

Pi/router inventory, original project/mount identity, account and client policy,
IPv4/IPv6 exposure, permitted/denied client tests, preserved Tailscale identity,
real off-device recovery, notifications and full-host outage observation remain
unverified. So do browser streaming/default-seccomp compatibility, VPN fault
behavior, actual Pi resource measurements and a 24-hour observation period.

Before cutover, complete [home security](home-security.md), establish independent
management and DNS continuity, retain previous images/configuration and a verified
backup, then apply and check one scope at a time. [Operations](operations.md),
[recovery](recovery.md), [updates](updates.md), and [browser VPN](browser-vpn.md)
describe the remaining work. Repository implementation did not deploy to the Pi
or change router, host firewall, VPN settings or notification destinations.
