# Remaining work

The repository implementation and selected extensions are merged through
[`8670510`](https://github.com/ash0ts/home-pi/commit/8670510):
[network setup (#10)](https://github.com/ash0ts/home-pi/pull/10),
[Home Assistant (#11)](https://github.com/ash0ts/home-pi/pull/11) and
[Syncthing (#12)](https://github.com/ash0ts/home-pi/pull/12), following the baseline
and [agent handoff (#9)](https://github.com/ash0ts/home-pi/pull/9).
See [delivery evidence](implementation-status.md) for checks and limits.
Continue the live checklist; do not rebuild completed tooling.

**Next action:** the owner confirmed the Pi is not set up yet. Follow
[first boot](setup.md#if-your-pi-is-not-set-up-yet), confirm the chosen login and
router-listed address, then perform read-only inventory before deploying the core
apps. Get those working before changing household DNS or selecting extras. The
actual Pi hardware, address, login and Verizon router model remain unknown.
Keep real host/device details in ignored `local/`. No live deployment, network
changes or notifications have been performed.

## Useful-home extensions

The owner selected these extensions on 2026-10-05. Repository delivery and live
acceptance are separate; do not mark either complete using evidence from the other.

- [x] Prepare [network setup](network.md): device names, conservative Pi-hole profiles, guest boundaries, remote DNS and native monitoring. Remote DNS defaults off and requires explicit boundary review before a scoped Pi-hole change.
- [x] Deliver an optional [Home Assistant Container module](../modules/home/README.md) with loopback/private access, stop-consistent state and isolated networking. No hardware or integrations are selected automatically.
- [x] Deliver an optional [Syncthing module](../modules/files/README.md) with private admin access, explicit pairing, full stop-consistent state and independent recovery instructions. No incoming sync ports or folder choices are published automatically.
- [ ] Verify network setup on one personal client, then expand only after DNS continuity and guest/IPv6 checks pass.
- [ ] Verify remote DNS from allowed/denied off-LAN clients and test loss/recovery of home connectivity.
- [ ] Enroll Kuma monitors and optional speed history; test phone notifications and an off-Pi observer if full outage alerts are wanted.
- [ ] Select one real automation device; verify useful behavior, reconnect, state restoration and DNS capacity with Home Assistant enabled.
- [ ] Select one personal computer/folder; verify sync, conflict/deletion behavior, independent file recovery and DNS capacity.

The owner confirmed on 2026-10-05 that the Pi is not set up yet. Hardware access,
automation devices and folder choices remain unknown. Native
settings and acceptance procedures are prepared; the live items remain unchecked.

## Ordered checklist

Check a box only when its completion evidence exists. Record a short redacted result, UTC date and private evidence location beneath the item; leave unavailable checks open. Optional work can be explicitly deferred without calling it verified.

- [ ] **1. Inventory the actual Pi and network.** Use [home security](home-security.md#start-with-a-private-inventory) and the [private inventory template](home-network.example.md). Establish hardware/OS, mounted storage, UID/GID, listeners, host VPN and tailnet state; inventory project/services/images/mounts if already installed. Complete owner router/account review and identify allowed test clients. **Done when:** dated inventory exists, a second management/recovery path works, and the DNS continuity policy is agreed. Read-only observation does not authorize configuration changes.
- [ ] **2. Establish recovery and prove restoration.** Follow [recovery](recovery.md). Choose a physically independent encrypted destination and separately recoverable credentials before startup. For a fresh Pi, start core in step 3, then return here to back up and restore its application state before changing household DNS or adding extras. For an existing deployment, complete the drill before migration. **Done when:** restored application data is usable and the recovery procedure is recorded. Never start a duplicate restored DNS/Tailscale identity alongside the original. The local restic fixture does not satisfy this step.
- [ ] **3. Start core or migrate an existing deployment.** With live authorization, a fresh Pi follows [new-install setup](setup.md#new-installations) after inventory and recovery preparation. An existing deployment completes the step 2 drill, then follows [reviewed updates](updates.md), preserving project/mount/key/Tailscale identities and retiring Watchtower only if observed. Change one service or coupled module at a time. **Done when:** the intended revision/images are running, scoped doctor passes, data is preserved and independent management works. Legacy Webtop needs the explicit [pair cutover](browser-vpn.md#maintenance); initial enablement does not migrate an already selected app.
- [ ] **4. Verify clients and network boundaries.** Complete the [access matrix](home-security.md#access-acceptance-matrix), private HTTPS/application login, normal-client DNS coverage, and a planned DNS outage/return drill. **Done when:** allowed and denied clients behave as intended for direct/proxy paths and both applicable address families. Missing IPv6 test access remains unverified. Preserve employer/device DNS policies and record exceptions.
- [ ] **5. Set up native operations.** Follow [operations](operations.md): maintain Homer links, enroll Kuma monitors and an authenticated notification destination, and schedule backups after validating the command/window. **Done when:** an actual scheduled off-device backup completes, age/coverage and disk checks have an owner, and authorized failure/recovery notifications arrive on the phone. Automatic stale-backup/disk alerts and full-Pi outage detection remain gaps until an existing integration/off-Pi observer is selected and tested; do not build a custom alert engine by default.
- [ ] **6. Accept only the optional apps the owner wants.** Use each selected module's acceptance: [reading](../modules/reading/README.md) for feeds/read state, [browser](browser-vpn.md) for streaming and the IPv4/IPv6/DNS fault matrix, [home](../modules/home/README.md#live-acceptance) for a real device/automation, and [files](../modules/files/README.md#live-acceptance) for selected-folder sync and recovery. **Done when:** private enrollment, useful behavior, retention, restore and workload checks pass for each selected app, with core DNS/Tailscale unaffected. Unselected apps stay disabled; a healthy VPN container is not privacy evidence.
- [ ] **7. Observe normal operation.** Follow the [capacity and maintenance procedure](operations.md#retention-and-capacity). Measure actual Pi DNS latency, RAM/swap, disk and thermal behavior at idle and under each optional workload; review retention and supported OS/router maintenance. Perform an authorized reboot and 24-hour observation. **Done when:** measurements, reboot recovery and any remaining limits are documented. Add resource caps only when measurements justify them.

## Waiting for hardware and choices

- Live file sync: the optional module is merged; pairing and acceptance wait for specific personal folders/devices and independent backups.
- Live home automation: the optional module is merged; pairing and acceptance wait for an actual device/integration and hardware choice.
- Custom portal generation, alert engines and measurement frameworks: use native tools and short runbooks unless a demonstrated requirement changes that decision.

## Resume here

Use the repository [home-pi skill](../.agents/skills/home-pi/SKILL.md). A new session can start with:

> Read AGENTS.md, the home-pi skill and docs/TODO.md. Verify the current branch/PR and delivery evidence, then continue the first unchecked item whose inputs and authorization are available. Keep the change small and use existing tools/runbooks. Do not repeat completed implementation or turn repository work into live deployment. Update the checklist with observed evidence and leave a concrete next action.

Current handoff: the baseline and selected extensions are merged; the Pi is not
set up yet. Guide first boot in plain language, then confirm access before live
inventory. Continue the hardware checks when the Pi and test clients are ready.
Do not request an unexplained SSH target or add automation to fill the access gap.
