# Implementation and deployment evidence

Prepared 2026-10-05 from the supplied implementation plan. This is a delivery
ledger, not a security certification. **No live deployment is authorized or
verified by this repository work.** Actual Pi/router hardware, network, accounts,
containers, and recovery are unavailable in the development workspace.

Update each layer with its commit/PR, exact checks actually run, and unresolved
gate when delivered. Do not mark a gate complete from code presence alone. The
original plan reviewed `e7dd701654a4184ae31bb7ea527ac7a90d917ade`; implementation
must reconcile current HEAD and preserve local/runtime state.

## Planned stack and acceptance gates

| Layer | Plan unit | Repository deliverable | Gate that remains live until observed |
| --- | --- | --- | --- |
| 1 | PR 1 + H0 | Deterministic private setup, canonical Compose, fixtures/CI, baseline inventory and runbooks | Preserve installed project/mounts/secrets; actual host preflight and H0 owner review |
| 2 | PR 2 | Correct settings and redacted doctor with scopes/status/time | Effective Pi-hole settings; TCP/UDP fixture; retained Tailscale identity and application state |
| 3 | PR 3 | Selection/profiles and explicit private access policy | Trusted/denied LAN, guest/IoT, tailnet, external; IPv4/IPv6; direct and proxy paths; reboot |
| 4 | PR 4 | Encrypted backup, state inventory, explicit isolated restore | All applicable bind/named-volume state restored and application data verified |
| 5 | E1 | Thin CLI and validated module contract; one existing service extracted | Enable/disable/re-enable preserves data and core container IDs; disposable module restore |
| 6 | PR 5 | Verified immutable images, reviewed updates, image/data rollback | Existing Watchtower stopped; failed update and matching data recovery; OS/router procedure |
| 7 | E2 | Portal/routes and actionable alert tooling/runbooks | HTTPS/reboot persistence, monitor registration, failure/recovery delivery and freshness |
| 8 | E3 | Disabled-by-default FreshRSS SQLite reading module | Refresh/read/starred state, OPML export, recreation and backup restore |
| 9 | PR 6 | Optional isolated browser VPN and fault-test runbook | Actual browser and namespace IPv4/IPv6/DNS under startup failure/loss/restart/recreation |
| 10 | PR 7 | Bounded workloads/logs and measurement procedure | Real hardware baseline, DNS under load, backup schedule, proposed 24-hour soak |

The table describes delivery order and gates, not an assertion that later code
already exists. Core plus Uptime Kuma is the proposed new-install standard;
existing installations retain their selection. E3 may be developed and tested
in isolation while H0 is pending; live expansion waits for baseline review.
Browser VPN work is independent of reading and other optional applications.

E4 selected Syncthing folders and E5 Home Assistant/ESPHome are **deferred,
conditional scope**: no concrete sync requirement or real device/hardware choice
has been supplied. Do not deploy placeholder apps or claim hardware acceptance.
Paperless, media/printer control, workflow engines, and a custom MCP service also
remain deferred until a real workflow justifies them.

## Evidence register

| Scope | Current status | Evidence / next action |
| --- | --- | --- |
| Repository documents | Prepared 2026-10-05 | H0 inventory, owner steps, access/DNS drill, architecture contract are present; update implementation test evidence per layer |
| Static and fixture checks | NOT YET RECORDED | Record exact commands/results from CI and local checks; use dummy credentials |
| Image release and ARM64 manifests | NEEDS_CONFIGURATION | Resolve selected upstream releases/digests and record manifest checks before release |
| Actual Pi containers/readiness | NEEDS_CONFIGURATION | No Docker/Pi observation; use doctor and service-specific acceptance on disposable/real ARM64 host |
| Router/account/endpoint controls | NEEDS_CONFIGURATION | Owner fills ignored private inventory and performs settings review |
| Client/network/public exposure | NEEDS_CONFIGURATION | Complete every applicable family/source/direct/proxy row in home-security.md |
| Backup and matching-data rollback | NEEDS_CONFIGURATION | Run isolated application-state restore and failed-update drill |
| Optional browser privacy | NEEDS_CONFIGURATION if enabled; SKIP only when disabled | Complete browser-namespace and actual-browser fault matrix; never infer from host curl |
| Notification/monitor enrollment | NEEDS_CONFIGURATION | Configure supported destination/monitors; test failure, recovery, suppression, freshness |
| Full-Pi outage observation | NEEDS_CONFIGURATION | Unsupported until a separate observer and actual notification delivery are tested |
| Performance and 24-hour soak | NEEDS_CONFIGURATION | Measure actual hardware/workload; no measured performance claims yet |

Machine-readable doctor records use `PASS`, `FAIL`, `SKIP`, or
`NEEDS_CONFIGURATION`, a UTC observation time, automatic/manual method, scope,
redacted evidence, and remediation. “NOT YET RECORDED” here describes the delivery
ledger only and must not be used as a passing machine check. The explicit home
baseline fails while required observations are missing.

## Before live cutover

1. Obtain deployment authorization and complete the [private inventory](home-network.example.md),
   including project/volume identity, actual listeners and enabled services.
2. Establish console/alternate management, DNS continuity, private config copy,
   previous images, and verified encrypted off-device backup.
3. Resolve applicable [home baseline](home-security.md) controls or record an
   owner-accepted constraint and mitigation without hiding the residual gap.
4. Validate exact desired Compose/model/secret/storage state. Apply one affected
   service/module at a time; preserve household DNS and Tailscale access.
5. Run application, network, recovery, and load checks in their stated scope.
   Record failures honestly, restore matching data/images when required, and
   keep rollback inputs until the observation period passes.

Do not run a root installer as a test, use production credentials in CI, run
untrusted PR code on a privileged personal runner, or use `down -v`/broad prune
as maintenance shortcuts. Router, host firewall, and host VPN cutover need real
topology and a tested recovery path.
