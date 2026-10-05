# Private home-network inventory template

Copy to ignored `local/home-network.md`, mode 0600. The template contains no real
network/device/account values. Never record passwords, keys, recovery codes, raw
query history, or full container environments here. Keep recovery credentials
in a password manager with a recovery route independent of the Pi.

Prepared: 2026-10-05. Observed at: **not observed**. Observer: **not assigned**.
Scope: **repository template only**. All unknown controls:
`NEEDS_CONFIGURATION`. Next action: owner inventories the actual deployment.

## Ownership, hardware, and recovery

| Field | Verified value / next action |
| --- | --- |
| Connection owner; personal / ISP / building-managed | UNKNOWN; identify control boundary and operator contact privately |
| Router model, firmware, support deadline, update owner | UNKNOWN; inspect actual device and manufacturer guidance |
| Upstream NAT/shared network; permission for downstream router | UNKNOWN; obtain operator facts before changes |
| Pi model, architecture, OS/support, RAM, cooling, power | UNKNOWN; run inventory in home-security.md |
| Boot disk, data disk, expected mount, filesystem/free space | UNKNOWN; verify physical mounted storage, not directory existence |
| Ethernet and DHCP reservation | UNKNOWN; inspect link and router lease/reservation |
| Current project name, checkout path, enabled services | UNKNOWN; read existing labels/config before migration |
| Actual bind paths, named-volume identities, UID/GID, image IDs | UNKNOWN; narrow Docker inventory; preserve identities |
| SSH/console method, second verified management session | UNKNOWN; test before changing access |
| Offline recovery instructions and credential location (no secrets) | UNKNOWN; owner verifies access without Pi/DNS |

## Address and route inventory

| Segment/path | IPv4 range/address | IPv6 range/global address | Router/DNS source | Ownership / intended access |
| --- | --- | --- | --- | --- |
| Trusted LAN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| Guest | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| IoT | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| Docker networks | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| Tailnet | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| Pi addresses | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| In-scope public endpoints | UNKNOWN | UNKNOWN | UNKNOWN | Owner confirms each target before external probe |

Check overlap with Docker/tailnet/VPN ranges. Record active port forwards, UPnP
mappings, DMZ assignment, IPv4/IPv6 inbound policy, and intentional exceptions.
Absence of IPv4 forwards does not establish IPv6 policy. Record host Docker
firewall backend and rule inspection date.

## Owner settings

| Check ID | Required observation | Status | Observed at / method / evidence / next action |
| --- | --- | --- | --- |
| router_support | Supported firmware and responsible operator | NEEDS_CONFIGURATION | Not observed; manual; owner review |
| router_access | WPA3 or WPA2-AES; unique credentials; WPS/WAN admin off; UPnP/mappings reviewed | NEEDS_CONFIGURATION | Not observed; manual; inspect actual settings |
| network_boundary | Actual IPv4/IPv6 router and host policy plus external probes | NEEDS_CONFIGURATION | Not observed; manual and automatic; complete access matrix |
| segmentation | Actual guest and IoT isolation with intended exceptions | NEEDS_CONFIGURATION | Not observed; manual; test client in each segment |
| accounts | Unique credentials, MFA/passkeys, enrolled-device review, offline recovery | NEEDS_CONFIGURATION | Not observed; manual; owner confirms without secrets |
| endpoints | Supported OS/devices, SSH/second session, unused service review | NEEDS_CONFIGURATION | Not observed; manual; verify effective state |
| dns_coverage | Client DHCP/IPv6/private-DNS/browser/VPN behavior and exceptions | NEEDS_CONFIGURATION | Not observed; manual; normal-client fixture tests |
| continuity | Chosen outage policy; outage and return-to-normal drill | NEEDS_CONFIGURATION | Not observed; manual; schedule owner-authorized drill |
| recovery | Encrypted off-device backup and isolated restore; router backup | NEEDS_CONFIGURATION | Not observed; manual; complete restore runbook |
| ongoing_operation | Backup schedule, stale/disk alerts, external observer if claimed | NEEDS_CONFIGURATION | Not observed; manual; test delivery and recovery notices |

## Per-endpoint access observations

Duplicate rows for every service, direct port and proxy URL, IPv4 and IPv6, and
source: trusted LAN, unauthorized LAN, guest, IoT, allowed tailnet, denied tailnet,
external with tunnels off. Keep actual endpoints private.

| UTC time | Source/location | Family | Service/target | Direct/proxy | Expected | Actual | Status | Method | Redacted evidence / next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Not observed | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | Owner defines from access policy | Not tested | NEEDS_CONFIGURATION | manual | Obtain scoped client and inventory |

## DNS and recovery decisions

- Chosen continuity policy: UNKNOWN (independent filtered resolver or documented
  manual temporary resolver; record temporary filtering loss).
- Original DHCP/IPv6 DNS settings and how to restore them: UNKNOWN.
- Controlled blocked fixture and expected response: UNKNOWN.
- Representative client results, employer/device-policy exceptions: UNKNOWN.
- Backup destination, credential recovery location, schedule/retention: UNKNOWN.
- Router backup location and supported restore procedure: UNKNOWN.
- Update/reboot window; alternate management; rollback owner: UNKNOWN.
- External observer and phone/background notification test: UNKNOWN; full-Pi
  outage notification unsupported until configured and observed.

## Constraints and accepted mitigations

| Control | Constraint | Mitigation | Owner decision/date | Review date | Remaining gap |
| --- | --- | --- | --- | --- | --- |
| UNKNOWN | No live inventory provided | Complete owner review before live expansion | Not accepted | Not scheduled | All applicable live gates remain open |
