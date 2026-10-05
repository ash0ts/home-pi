# Private browser VPN

The opt-in browser module puts Webtop inside Gluetun's Mullvad WireGuard network namespace. It preserves `webtop/config`, PUID/PGID and browser credentials. It changes no host Mullvad, router, Pi-hole, Tailscale, exit-node or subnet-route settings. Review the existing host routes and independent SSH/console recovery before a live cutover.

1. Back up the existing browser data and retain previous image identities.
2. From your Mullvad-generated WireGuard configuration, save only its private key in `local/wireguard-private-key`, mode 0600. Set `GLUETUN_WIREGUARD_KEY_FILE=./local/wireguard-private-key` and its actual IPv4 interface CIDR as `WIREGUARD_ADDRESSES` in the private root `.env`; see the module's `.env.example`. Preserve the existing Webtop password, UID/GID and mount path.
3. Review `./pi plan --enable browser`. Selected-module validation checks the key file and address without printing them. Fetch reviewed images with `./pi pull browser`, then explicitly enable with `./pi enable browser` during the planned maintenance window.
4. Test login and streaming through an SSH tunnel to loopback HTTPS3002. Enroll private Tailscale HTTPS8449 only after application setup; see [access](access.md). Test allowed and denied clients. Default seccomp is retained; desktop streaming compatibility remains a live check.

Gluetun owns the only loopback port publication. Webtop shares its namespace and waits for its native healthcheck. Webtop's read-only resolver points to 127.0.0.1; Gluetun uses DNS over TLS. The private key uses a Compose file secret and joins the encrypted recovery bundle. IPv6 is disabled in this namespace; IPv6 VPN egress is unsupported. There are no broad outbound subnet exceptions. These are configuration properties, not proof of leak prevention. See the pinned release's [secret reader](https://github.com/qdm12/gluetun/blob/v3.41.3/internal/configuration/sources/secrets/reader.go), [DNS settings](https://github.com/qdm12/gluetun/blob/v3.41.3/internal/configuration/settings/dns.go), and [namespace guidance](https://github.com/qdm12/gluetun-wiki/blob/main/setup/connect-a-container-to-gluetun.md).

## Live acceptance

Use an isolated Pi or a maintenance window with independent management and DNS continuity. First establish working owner-controlled IPv4/IPv6 endpoints and an authoritative DNS fixture from another connection. Run requests **inside Webtop**, with fresh DNS names and matching authoritative logs/packet observations. A host public-IP request, unavailable endpoint, missing client tool, or failed TLS validation cannot establish blocking.

| Scenario | Required observation |
| --- | --- |
| Connected startup | Gluetun healthy before Webtop; authenticated browser works; expected VPN IPv4 egress and fresh DNS answer; IPv6 disabled. |
| Invalid credentials | In an isolated test configuration, owner fails readiness and new browser cannot start. Retain the real key separately. |
| Tunnel loss | While the actual tunnel is down, no home-ISP IPv4 egress or DNS bypass; test IPv6 too. Record recovery timing. |
| Gluetun process/container failure | Test the browser's remaining namespace. Kernel WireGuard may survive process failure; verify actual traffic rather than assuming tunnel loss. |
| Restart and recreation | Recreate both services; consumer references the current owner ID, then repeat connected/failure checks. |
| Client access | Allowed client authenticates; denied tailnet/LAN/guest/public clients cannot reach the intended protected paths. |

Record date, fault, exact container IDs, expected/actual results and packet/DNS witnesses privately. Missing IPv6 fixtures or ambiguous failures remain unverified. Live VPN operation, streaming, default-seccomp compatibility and this fault matrix were **not run** during repository implementation.

## Maintenance

Treat Gluetun and Webtop as one unit. `./pi update --module browser` expands namespace dependencies and recreates both after backup. For manual maintenance, get the exact project/file invocation from `./pi plan`, stop Webtop first, then force-recreate **both** services. Verify Webtop's `HostConfig.NetworkMode` is `container:<current-full-gluetun-ID>` before restoring its route. The access manager checks this association before publishing; it cannot continuously police later manual Docker changes.

Existing selected Webtop installations need an explicit inventory/configuration migration because the browser module now owns two services. Preserve the enabled intent and state, configure the key/address, then perform the planned pair recreation. Never infer that old host Mullvad routing establishes the new browser route. Keep the old access path until verification passes. If importing a legacy installation with only Webtop, the importer deliberately refuses that partial module. After inventory and backup with the previous checkout, prepare mode-0600 `local/selection.json` with the inspected module IDs (including `browser`) and use the planned Compose invocation for the initial pair creation. The managed updater requires both containers to exist; it is for subsequent updates.

Disable preserves desktop state and credentials. Rollback after a data migration uses the previous image plus its matching restored data; never overwrite production state directly from a quarantine restore. Host VPN changes require their own topology review and live authorization.
