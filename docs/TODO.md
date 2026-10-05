# Remaining work

The implementation stack is merged through [`262f01a`](https://github.com/ash0ts/home-pi/commit/262f01a), with 129 tests and all seven PR checks passing at handoff. See [delivery evidence](implementation-status.md). The remaining work is deployment and verification; do not rebuild the completed tooling.

**Next action:** help the owner find the Pi and confirm how to connect, then perform read-only inventory. Its address, login and existing checkout path are not known yet. Keep actual host, project and device details in ignored `local/`, not this checklist. No live deployment, network changes or notifications have been authorized by this documentation PR.

The owner does not need to know SSH terminology. When ready, find the Pi in the router's connected-device list, or use its local terminal: `hostname -I` shows its addresses and `whoami` shows the current username. Confirm those belong to the intended Pi. Use a previously working saved connection if available; otherwise guide the owner through checking SSH status on the Pi before connecting. Do not guess default credentials, enable remote access or scan the network to fill this gap. If access is unavailable, keep the live checklist pending.

## Ordered checklist

Check a box only when its completion evidence exists. Record a short redacted result, UTC date and private evidence location beneath the item; leave unavailable checks open. Optional work can be explicitly deferred without calling it verified.

- [ ] **1. Inventory the actual deployment.** Use [home security](home-security.md#start-with-a-private-inventory) and the [private inventory template](home-network.example.md). Establish hardware/OS, mounted storage, installed project, services, images, mounts, UID/GID, listeners, host VPN and tailnet state. Complete owner router/account review and identify allowed test clients. **Done when:** dated inventory exists, a second management/recovery path works, and the DNS continuity policy is agreed. Read-only observation does not authorize configuration changes.
- [ ] **2. Prove recovery before cutover.** Follow [recovery](recovery.md) using the installed deployment's state and matching images. Verify a physically independent encrypted destination, separately recoverable credentials, and an isolated application restore/rollback drill. **Done when:** restored application data is usable and the recovery procedure is recorded. Never start a restored production DNS/Tailscale identity alongside the original. The earlier local restic fixture does not satisfy this step.
- [ ] **3. Apply a reviewed, scoped migration.** After steps 1–2 and live authorization, follow [updates](updates.md). Retire the exact existing Watchtower, preserve project/mount/key/Tailscale identities, and change one service or coupled module at a time. **Done when:** the intended revision/images are running, scoped doctor passes, data is preserved and independent management still works. Initial legacy Webtop migration needs the explicit [pair cutover](browser-vpn.md#maintenance); `enable` is not a migration command for an already selected module.
- [ ] **4. Verify clients and network boundaries.** Complete the [access matrix](home-security.md#access-acceptance-matrix), private HTTPS/application login, normal-client DNS coverage, and a planned DNS outage/return drill. **Done when:** allowed and denied clients behave as intended for direct/proxy paths and both applicable address families. Missing IPv6 test access remains unverified. Preserve employer/device DNS policies and record exceptions.
- [ ] **5. Set up native operations.** Follow [operations](operations.md): maintain Homer links, enroll Kuma monitors and an authenticated notification destination, and schedule backups after validating the command/window. **Done when:** an actual scheduled off-device backup completes, age/coverage and disk checks have an owner, and authorized failure/recovery notifications arrive on the phone. Automatic stale-backup/disk alerts and full-Pi outage detection remain gaps until an existing integration/off-Pi observer is selected and tested; do not build a custom alert engine by default.
- [ ] **6. Accept only the optional apps the owner wants.** For [reading](../modules/reading/README.md), complete private enrollment, chosen feeds/OPML, retention review and recovery of real read/starred state. For [browser](browser-vpn.md), verify authentication/streaming, current namespace ownership, and the complete IPv4/IPv6/DNS startup/loss/restart/recreation fault matrix inside Webtop. **Done when:** each selected app's checks pass and core DNS/Tailscale remain unaffected. Unselected apps stay disabled; a healthy VPN container is not privacy evidence.
- [ ] **7. Observe normal operation.** Follow the [capacity and maintenance procedure](operations.md#retention-and-capacity). Measure actual Pi DNS latency, RAM/swap, disk and thermal behavior at idle and under each optional workload; review retention and supported OS/router maintenance. Perform an authorized reboot and 24-hour observation. **Done when:** measurements, reboot recovery and any remaining limits are documented. Add resource caps only when measurements justify them.

## Deferred by design

- E4 file sync: wait for specific folders/devices and independent backup requirements.
- E5 home automation: wait for an actual device/integration and hardware choice.
- Custom portal generation, alert engines and measurement frameworks: use native tools and short runbooks unless a demonstrated requirement changes that decision.

## Resume here

Use the repository [home-pi skill](../.agents/skills/home-pi/SKILL.md). A new session can start with:

> Read AGENTS.md, the home-pi skill and docs/TODO.md. Verify the current branch/PR and delivery evidence, then continue the first unchecked item whose inputs and authorization are available. Keep the change small and use existing tools/runbooks. Do not repeat completed implementation or turn repository work into live deployment. Update the checklist with observed evidence and leave a concrete next action.

Current handoff: the implementation baseline above is merged; locating the Pi and confirming access precedes live inventory. The owner is unsure of the connection details, so guide that step in plain language when they are ready. Finish any already requested independent repository work; do not invent tasks or add more automation while access is unavailable.
