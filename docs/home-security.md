# Home-security baseline

Prepared 2026-10-05. **Repository preparation only.** No Pi, router, guest device,
tailnet client, or external test connection has been inspected. All applicable
live controls below are `NEEDS_CONFIGURATION`. A merged PR or healthy container
does not establish that the home network is secure. Live deployment, router,
firewall, host VPN, and data changes require a separate authorized operation.

The scope is exposed administration, compromised guest/IoT devices, stolen
credentials, unsupported software, storage loss, and outages. Pi-hole filters
DNS requests it receives; it cannot guarantee protection from phishing or
malicious downloads. A commercial VPN is optional and does not complete this
baseline. See [architecture](architecture.md) and [delivery gates](implementation-status.md).

## Start with a private inventory

From the checkout, prepare a private copy without overwriting an existing one:

```sh
mkdir -p local
chmod 700 local
test -e local/home-network.md || (umask 077; cp docs/home-network.example.md local/home-network.md)
chmod 600 local/home-network.md
git check-ignore local/home-network.md
```

Fill in the unknowns using the real deployment. Never put credentials, recovery
codes, raw browsing history, or unredacted device/account identifiers in git or
PRs. Do not give an agent router credentials. The owner reviews router/account
settings directly. A building/ISP-managed connection requires its operator's
cooperation; do not change shared infrastructure. Consider a personal downstream
router only after establishing connection requirements and terms.

On the Pi, these read-only commands help establish hardware and listeners:

```sh
uname -m
cat /etc/os-release
cat /proc/device-tree/model
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
findmnt -T .
df -h .
ip -brief address
ip -4 route
ip -6 route
sudo ss -lntup
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}'
docker info --format '{{json .SecurityOptions}}'
```

Keep results private. Inspect the active Docker daemon arguments/configuration
and effective rules (`sudo nft list ruleset`, or `sudo iptables-save` and
`sudo ip6tables-save`, as installed) to establish the actual backend. Do not
infer it from a firewall frontend alone. Docker bridge-published ports and
host-network listeners follow different paths; UFW alone is not evidence that a
published port is blocked. Do not disable Docker's firewall management as a fix.
See [Docker's firewall documentation](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

Record the installed project label, service mount sources/named-volume names,
and image IDs before changing the checkout. Narrow inspection avoids dumping
environment secrets:

```sh
docker ps -aq --filter label=com.docker.compose.project=YOUR_EXISTING_PROJECT
docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}} {{index .Config.Labels "com.docker.compose.service"}} {{.Image}} {{json .Mounts}}' YOUR_CONTAINER_ID
```

Replace the explicit placeholders with verified values. Inspect only the
project's containers. Preserve project identity, mount paths, UID/GID, Tailscale
state, enabled services, and existing valid application keys. Never publish
`docker inspect` without a format or expanded production Compose configuration.

## Owner controls and acceptance

Every row currently has status `NEEDS_CONFIGURATION`; the owner must supply the
observation, timestamp, exceptions, and any accepted mitigation.

| Control | Owner action | Completion evidence |
| --- | --- | --- |
| Router ownership/support | Identify model, operator, supported firmware, update responsibility, upstream NAT/shared boundary. Use the manufacturer's model-specific instructions. | Dated settings review and supported release; operator constraints recorded. |
| Wi-Fi/router access | Use WPA3 where compatible or WPA2-AES, distinct strong Wi-Fi/admin credentials, disabled WPS and WAN administration. Disable UPnP unless a specific requirement is documented; remove unnecessary mappings and Pi DMZ assignment. | Actual settings and active mappings reviewed; precise exceptions and expiry/review date. |
| IPv4 and IPv6 boundary | Restrict DNS and administration to the declared clients. Inspect router and host policy and all global IPv6 addresses. | Local and external matrix below passes for both applicable address families. |
| Guest/IoT separation | Isolate untrusted devices; allow only needed DNS, device control, and discovery. | Real guest/IoT clients fail to reach admin/trusted computers while intended functions work. A separate SSID alone is insufficient. |
| Accounts and tailnet | Password manager, unique credentials, MFA/passkeys on key accounts and Tailscale identity provider; remove obsolete devices. Configure explicit permissions and application authentication. | Owner confirmation without secrets; allowed and deliberately denied tailnet clients tested. |
| SSH and endpoints | Supported OS/device updates; SSH keys or deliberately configured Tailscale SSH; review unused accounts/services. | A second management session succeeds before password SSH is disabled; normal endpoint protections retained. |
| Recovery | Encrypted off-device backups; separately recoverable keys; router configuration backup when supported; matching data/image rollback. | Isolated application-state restore and failed-update drill; documented reboot/update recovery. |
| Continuity | Reserve Pi address, prefer Ethernet, choose DNS outage policy, bound storage, configure alerts. | DNS outage/return drill; stale-backup/disk alert and off-Pi observer tests where claimed. |

Router/Wi-Fi guidance follows the [FTC home-network guidance](https://consumer.ftc.gov/articles/how-secure-your-home-wi-fi-network).
Tailnet permissions must match the actual identities and enabled services; review
the existing policy, including broad allow rules, using [Tailscale access controls](https://tailscale.com/docs/features/access-control).
Tailnet authorization does not restrict unrelated LAN listeners.

## Access acceptance matrix

Run each applicable row in IPv4 **and** IPv6. Record client/network location,
target from the private inventory, direct port or proxy URL, expected result,
actual result, and UTC time. Use only owned, explicitly in-scope endpoints. Test
the published backend ports as well as HTTPS proxy entry points. Application
authentication is an additional control; a login page returned to an unauthorized
network is still a failure of a policy requiring that network to be blocked.

| Source | DNS TCP/UDP 53 | Direct administration backend | Private HTTPS proxy |
| --- | --- | --- | --- |
| Pi loopback | Allowed as configured | Allowed for proxy/health use | According to route configuration |
| Trusted authorized LAN device | Allowed | Denied by default; explicit documented LAN exception only | Allowed only through an authorized tailnet or separately tested LAN TLS path |
| Unauthorized LAN device | Per explicit DNS policy | Denied | Denied |
| Guest and IoT, each separately | Only if explicitly allowed | Denied | Denied |
| Authorized tailnet device | Opt-in only; otherwise denied | Denied | Allowed only for granted listeners, with application auth |
| Deliberately denied tailnet device | Denied unless explicit DNS-only permission | Denied | Denied |
| External connection, tunnels off | Denied | Denied | No public administration; tailnet-only hostname must not provide access |

Before probing, set shell variables on each test client from the private
inventory. `PI_ADDRESS` is the Pi's address for that path; `ADMIN_URL` is the
specific direct or proxy URL; `PERMITTED_NAME` is a harmless known-resolving
name; `BLOCKED_NAME` is the controlled fixture explicitly blocked in Pi-hole.
These commands do not add that fixture or change policy:

```sh
: "${PI_ADDRESS:?Set the in-scope IPv4 or IPv6 address}"
: "${ADMIN_URL:?Set the complete endpoint URL}"
: "${PERMITTED_NAME:?Set the permitted test name}"
: "${BLOCKED_NAME:?Set the configured blocked fixture}"
date -u +%FT%TZ
dig +time=2 +tries=1 @"$PI_ADDRESS" "$PERMITTED_NAME" A
dig +tcp +time=2 +tries=1 @"$PI_ADDRESS" "$PERMITTED_NAME" A
dig +time=2 +tries=1 @"$PI_ADDRESS" "$BLOCKED_NAME" A
dig +tcp +time=2 +tries=1 @"$PI_ADDRESS" "$BLOCKED_NAME" AAAA
curl --connect-timeout 3 --max-time 8 --output /dev/null --write-out '%{http_code}\n' "$ADMIN_URL"
```

For denied DNS, a successful answer is a failure; a DNS `REFUSED` response is
different from firewall isolation and must be recorded accurately. For allowed
DNS, inspect answer/status and compare the blocked fixture with the configured
blocking mode. A `dig` exit code alone does not prove a useful answer or blocking.
Do not disable TLS verification to make an authorized HTTPS test pass. A 401/403
may prove listener liveness, but does not prove authenticated application use.
Test login in the actual browser separately without saving passwords in reports.

On an external connection (for example, cellular with Wi-Fi and home tunnels
off), set the target to the **actual public IPv4** or **active global IPv6** in
the inventory. Repeat the DNS and every management endpoint probe, alongside
the router mapping/firewall review. A failed cellular connection to a private LAN
address is no evidence about public exposure. Lack of an IPv6-capable test path
is `NEEDS_CONFIGURATION`, not proof of IPv6 safety. If no global IPv6 exists,
record the verified router/host observation and the explicit inapplicable scope.

## Client DNS coverage and outage recovery

Check what each representative laptop, phone, and owned IoT device actually uses:
DHCP DNS, IPv6 RDNSS/DHCPv6, browser secure DNS, device private DNS, and VPN-provided
DNS. Work devices retain employer controls; record exceptions. Test permitted
and controlled blocked names through the client's normal browser/application,
not only with `dig @Pi`. Pi-hole logs establish observed queries only. DNSSEC
validates DNS data; it does not encrypt queries or route browsing through a VPN.

Choose one policy and keep the instructions and router credentials accessible
without this Pi or its DNS:

1. Independent filtered resolver: put the second resolver on separate hardware
   and verify clients use it when the Pi is unavailable. Two containers on one Pi
   share the same disk/power/host failure.
2. Manual emergency resolver: document the owner-approved temporary resolver,
   original DHCP/IPv6 settings, change/renew steps, and restoration steps. Public
   fallback loses filtering and can bypass it even during normal operation.

For an authorized maintenance drill, first verify console/alternate management,
record current DNS settings, and arrange the selected recovery route. Stop only
Pi-hole using the verified project invocation (`docker compose ... stop pihole`).
From normal clients confirm permitted lookup recovery by the selected policy.
Restart only Pi-hole (`docker compose ... up -d --no-deps pihole`), restore any
temporary DHCP/IPv6 resolver settings, renew client leases/reconnect as needed,
and rerun allowed/blocked queries in both address families. Record interruption
duration and confirm filtering returned. Do not execute this drill during
repository validation or leave a public fallback undocumented.

## Evidence contract

The doctor report is the single machine-readable status surface; do not create a
security daemon or infer owner controls from local container health. Each check
must carry an ID, scope (`repository`, `runtime`, `network`, or `owner`), status,
UTC observation time, method (`automatic` or `manual`), redacted evidence, and
next action. Scope is essential: a repository assertion never satisfies a live
network assertion. Keep raw deployment evidence in ignored `local/`.

| Status | Meaning |
| --- | --- |
| `PASS` | The named check was observed successfully in its recorded scope. |
| `FAIL` | An applicable check was performed and its expected result failed. |
| `NEEDS_CONFIGURATION` | Required configuration, client, permissions, or observation is missing; explain exactly what is needed. |
| `SKIP` | An explicit inapplicable condition is established, such as a disabled optional browser. |

Home-baseline validation must exit nonzero while essential controls are failed
or unverified. An accepted owner constraint includes its mitigation, scope,
decision date, and next review; it must remain visible and must not be rewritten
as an automated PASS. Retest after router/network/account changes, adding a
module, and recovery. Review freshness at least during routine maintenance.

Browser VPN failure tests, restore drills, update recovery, scheduled backup
delivery, and the proposed 24-hour Pi soak remain separate live gates. An on-Pi
monitor cannot reliably report total host/power failure: that claim requires a
tested observer elsewhere. Expansion of the live deployment waits for owner
review of applicable baseline controls; isolated repository work can continue.
