# One useful home automation

Home Assistant brings compatible devices into one place. Start with one job:
a room sensor on a dashboard, a motion-triggered light, or a smart plug's energy
history. Choose the actual device and integration before relying on it.

This optional `home` module runs **Home Assistant Container**, not Home Assistant
OS. It keeps the existing Pi operating system, DNS and Tailscale. Container does
not include Home Assistant's OS app manager. MQTT, ESPHome, Zigbee and cameras
are not installed automatically.

## Prepare and enable

Complete the baseline [TODO](../../docs/TODO.md), off-device backup/restore and
[capacity review](../../docs/operations.md#retention-and-capacity) before live
enablement. Verify ARM64 Linux, actual RAM/storage and a working recovery path.
If this is already installed outside the module, inventory and review its exact
mount/project/ownership migration first; do not create a replacement identity.

As the checkout owner, create the new private state directory only if it is not
already present (`install -d -m 0700 home-assistant/config` on Debian). Retain the
permissions and ownership of existing state. Review expected external disks in
`local/storage.json` if this path resolves onto external storage.

```sh
./pi plan --enable home
./pi pull home
./pi enable home
./pi doctor --services home-assistant
```

These commands have distinct purposes: plan checks configuration, pull fetches
the pinned image, and enable starts only this module. First startup may take
longer than the bounded readiness window on the actual Pi; a failed enable keeps
the data and restores the previous selection. Investigate privately and retry
after resolving the cause. It never restarts core services to retry this app.

## Private enrollment and access

1. Open a temporary SSH tunnel from your own computer:
   `ssh -N -L 8123:127.0.0.1:8123 USER@PI`. Replace USER/PI with the confirmed
   connection, then open `http://127.0.0.1:8123` on that computer. If its local
   port is occupied, use a different local port without changing the backend.
2. Complete the owner-account wizard with a unique password. Keep credentials,
   device keys and tokens in private app settings, not the repository.
3. In Settings > System > Network, configure the HTTP reverse proxy settings
   for the pinned 2026.9 release: enable Trust X-Forwarded-For and trust only the
   exact proxy peer observed on this Docker host. The peer is usually the bridge
   gateway, not the remote phone and not necessarily 127.0.0.1. Inspect the actual
   module network and, if needed, the privately viewed rejected-proxy diagnostic;
   do not guess a subnet or trust all addresses. Save and confirm through the
   tunnel after the app restarts. Retest after network recreation.
4. Follow [access enrollment](../../docs/access.md#https-registration): preserve
   existing enrollment entries and add `home-assistant` only after account and
   proxy setup. Review a narrow tailnet grant for TCP8451, then apply the owned
   private route and test login plus denied-client behavior. Add its verified
   HTTPS URL to Homer. Never enable public Funnel or a router port forward.

The local healthcheck is HTTP liveness only. It does not verify enrollment,
WebSocket use, proxy trust, device discovery, automation or notifications. Check
normal UI/WebSocket use from the allowed personal client separately. Keep 8123
unchanged in the application's HTTP settings so the declared backend stays valid.

## Add the first device

The app uses an isolated bridge and no privileged mode, host networking, Docker
socket, radio or host D-Bus mount. Add a compatible IP-based integration manually
using the device's actual address. LAN multicast discovery does not cross this
bridge automatically; private HTTPS access does not forward discovery either.
Devices that must initiate a connection to the app need a separately reviewed
network path. Do not open admin access to every guest/IoT device to make it work.

Pick one integration with documented local support, give the device a stable
address, add one dashboard card and one harmless automation in the native UI.
Test its trigger, expected result, reconnect and app restart. Notifications need
their own owner-selected destination and actual receipt test. Do not create an
automation affecting heating, locks or other critical equipment as a first test.

Radio-dependent integrations remain pending until a specific adapter and owner
are chosen. A future change may pass one stable `/dev/serial/by-id/...` device
with tested permissions. Do not add all `/dev`, `privileged`, MQTT or a second
radio owner by default. Keep firmware compilation off this DNS host if it causes
resource pressure.

## Retention, backup and recovery

The entire `home-assistant/config` bind is essential stop-consistent state:
accounts, integrations, secrets, `.storage`, automations and recorder database.
No cache exclusion is assumed. Use `./pi backup home` for the selected module;
verify the off-device destination and app restoration using [recovery](../../docs/recovery.md).
Review recorder retention for the actual sensors; keep its database and backups
within the [capacity targets](../../docs/operations.md#retention-and-capacity).
Docker logs are bounded separately from the app's own files/history.

Restore with the matching pinned image into a quarantine target. Start a restored
fixture on an isolated network without radio or real-device access; verify login,
dashboard and automation definitions before any deliberate production cutover.
A restored automation must not run against the same live equipment as the
original. Use [reviewed updates](../../docs/updates.md) for image changes;
rollback after a database migration needs matching data, not just an older image.

`./pi disable home` removes its owned route and stops only this module; data
remains. Record the effect on device behavior first. Re-enable uses the retained
identity/configuration. Core DNS/Tailscale container IDs must remain unchanged.

## Live acceptance

- [ ] Owner login, HTTPS trust, WebSocket UI and denied clients verified.
- [ ] One selected real device reports locally and one useful automation works.
- [ ] App/device restart and reconnect behavior verified.
- [ ] Off-device backup restores usable configuration on an isolated target.
- [ ] Normal workload stays within measured Pi DNS, RAM, disk and thermal limits.
- [ ] Disable/re-enable preserves state and core container IDs.

These checks are NOT RUN until the real Pi, integration and test clients exist.
Keep dated private evidence in `local/`; update [TODO](../../docs/TODO.md) only
when observed.

Sources: [Container installation](https://www.home-assistant.io/installation/linux/),
[HTTP/proxy settings](https://www.home-assistant.io/integrations/http/), and
[the reviewed release](https://github.com/home-assistant/core/releases/tag/2026.9.4).
