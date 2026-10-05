# Operating the Pi

These are owner-run procedures. Repository checks do not establish live Pi,
router, monitor, phone-delivery, or restore readiness. Complete the applicable
[home security checks](home-security.md) before expanding the live deployment.
No timer, monitor, notification destination, or household subscription is
installed automatically.

## Keep Homer useful

Back up and edit the existing `homer/assets/config.yml`; preserve personal links
and styling. Use the real private HTTPS URLs listed by
`python3 -B scripts/access.py plan`, then verify the routes were applied and open
them from an allowed client. Add only enabled services and remove links when a
module is disabled. A planned URL is not proof of a working route. Use short names
such as DNS, Health, Reading, and Administration; never put tokens, passwords,
private document titles, or token-bearing query strings in dashboard links.
Check login and denied-client behavior separately; see [access](access.md).

## Register native monitors and notifications

Complete Uptime Kuma's first-admin enrollment through the private access path.
In its UI, add the following monitors using actual reachable addresses:

| Monitor | Configuration and limitation |
| --- | --- |
| DNS | DNS type, actual Pi resolver, port 53, permitted test domain, A record; verify the answer matches the intended result. |
| DNS TCP reachability | TCP Port type, same resolver, port 53; a connected socket alone does not prove a valid DNS answer. |
| Private HTTPS | HTTP(s) type, applied service URL, valid TLS, intended success/authentication status; retain a separate authenticated-use check. |

Use `./pi doctor --json` for functional UDP/TCP and blocking-fixture checks after
configuration. A loopback address inside Kuma refers to that container, not the
Pi host. Check each observer's actual network path. Select sensible intervals and
retries, then use Kuma's built-in maintenance windows during planned work.
Monitor types follow the pinned release's [native editor](https://github.com/louislam/uptime-kuma/blob/2.5.5/src/pages/EditMonitor.vue).

Configure an existing authenticated ntfy destination through Kuma's notification
UI. Keep its token in private application settings, never in Git or dashboard
URLs. For self-hosted ntfy, set `auth-default-access: deny-all`, grant only the
required publisher/subscriber permissions, and verify anonymous publishing and
reading fail. See [ntfy authentication](https://docs.ntfy.sh/config/).
Self-hosted iOS instant notifications have an upstream push dependency; review
[ntfy's iOS delivery model](https://docs.ntfy.sh/config/#ios-instant-notifications).

When ready to send, explicitly test the destination in the UI and confirm receipt
on the phone in the background. Use a disposable endpoint to verify one failure
and one recovery notification. No notification is sent by repository setup.
An on-Pi Kuma instance cannot report its own full power/network failure; that
requires a tested observer outside the Pi's failure boundary.

## Backups and freshness

Follow [recovery](recovery.md) to configure the encrypted off-device destination
and complete an application restore drill. Inspect the actual completion marker:

```sh
date -u
python3 -m json.tool local/last-backup.json
```

For a daily policy, investigate a missing marker or `completed_at` older than
36 hours. Verify its `services` covers the complete intended deployment and its
snapshot exists; a fresh optional-app-only backup does not establish core
recovery. Reject `local_test_only` as off-device evidence. A network repository
prefix alone does not prove a physically independent backup destination.
Kuma's URL/DNS monitors do not check backup age or application restore success:
review these explicitly until an owner-selected monitoring integration is tested.

For scheduled backups, use one owner-installed systemd timer running
`scripts/backup.sh --allow-dns-interruption` as the checkout owner, from this
checkout. Validate the command manually and arrange DNS continuity and alternate
management first. Choose a maintenance window, avoid speed tests/updates, and
use `Persistent=false` to avoid an unexpected catch-up DNS pause after boot.
Inspect the timer and completed snapshot; missing runs require investigation.
A timer alone does not provide stale-backup alerts.

## Retention and capacity

Compose uses Docker's `local` log driver with `max-size: "10m"` and
`max-file: "3"`. This takes effect on recreation; verify Dozzle still works. See [Docker logging](https://docs.docker.com/engine/logging/configure/).
Speedtest preserves its six-hour schedule and 180-day retention; configure
`SPEEDTEST_SCHEDULE`, `SPEEDTEST_RETENTION_DAYS` and `SPEEDTEST_SERVERS` in private
`.env` after reviewing history needs and actual ISP/VPN egress. See its
[supported settings](https://docs.speedtest-tracker.dev/getting-started/environment-variables).
Review Pi-hole query retention in its UI before reducing retained history.
For Netdata, back up and edit its existing configuration instead of hiding it
with a replacement bind mount; use the [supported database limits](https://learn.netdata.cloud/docs/netdata-agent/configuration/database).
Check growth after a day and a week. Include backup staging and retained rollback
images in capacity planning; do not use `down -v` or broad pruning as maintenance.

On the actual Pi, record model/OS, image digests, UTC time and workload alongside
`docker stats --no-stream`, `free -h`, `vmstat 1 10`, `df -h`, and
`vcgencmd get_throttled` where available. For each actual data path, use
`findmnt -T /ACTUAL/DATA/PATH` to verify the expected disk is mounted.
Measure bounded UDP/TCP DNS queries from the same owned client to the declared
resolver, using a fixed permitted name and consistent cache conditions.

Compare idle, normal browser use, one speed test, and one backup separately;
only combine loads after individual results pass. Record DNS failures/latency,
available RAM, swap activity, filesystem free space, temperature and throttling.
Proposed headroom is 25% available RAM and 20% free space on each data filesystem;
these are targets to validate, not measured guarantees. Protect DNS and remote
management first; retain resource limits only after before/after measurements.

Review supported OS/router firmware and security updates regularly. Raspberry
Pi OS uses its [supported APT maintenance procedure](https://www.raspberrypi.com/documentation/computers/os.html#manage-software-and-firmware-updates);
routine firmware maintenance does not require experimental `rpi-update`.
Before an authorized reboot, verify backup and alternate access; afterward test
mounted disks, DNS UDP/TCP/filtering, tailnet identity, private HTTPS, allowed and
denied clients, schedules, and recovery notifications. Keep timestamped evidence
privately. Live load baselines, a 24-hour observation, full-host outage detection,
phone delivery, and replacement-host recovery remain unverified until performed.
Browser VPN privacy remains a separate live gate. E4 selected file sync and E5
electronics/home automation stay deferred until a concrete folder/device need.
