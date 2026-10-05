# Optional private browser

This module pairs Webtop with Gluetun using Mullvad WireGuard. Select it explicitly after configuring its private key file and completing the cutover checks in [browser VPN operations](../../docs/browser-vpn.md). It preserves the existing `./webtop/config` mount and UID/GID settings.

Webtop shares Gluetun's network namespace. Gluetun publishes only `127.0.0.1:3002` for Webtop's internal HTTPS port 3001; the portal uses the private Tailscale HTTPS listener 8449. The backend self-signed certificate is accepted only for this loopback proxy hop. Webtop requires its own password. Its resolver file points exclusively to Gluetun at 127.0.0.1; Gluetun forwards DNS using TLS through its VPN routing policy.

IPv6 is deliberately disabled inside this namespace. IPv6 VPN egress is unsupported by this configuration. Do not remove that policy without a separate dual-stack configuration and complete IPv4/IPv6/DNS fault testing.

Copy settings from `.env.example` into the private root `.env`. `GLUETUN_WIREGUARD_KEY_FILE` points to a regular mode-0600 file containing the base64 private key from Mullvad's generated WireGuard configuration. Use that configuration's actual IPv4 CIDR as `WIREGUARD_ADDRESSES`; the account's device public key is not a private key. Keep recovery copies independent of the Pi.

The existing 4 GiB Webtop shared-memory allowance is preserved; it is a ceiling, not reserved memory. No new CPU/RAM caps are imposed without measurements. Observe DNS latency, actual memory pressure, disk, and thermal behavior before regular use. Default seccomp is retained; desktop streaming and Chromium compatibility remain a live test gate.

Backup covers `/config`; private WireGuard credentials must also be captured by the managed encrypted configuration backup or kept independently recoverable. Disable/re-enable preserves desktop state. Gluetun has no persistent application data in this module. Whenever its container is recreated, stop/recreate Webtop with it and verify that Webtop references the new exact Gluetun ID before restoring access.

Manifest and static tests have passed. Live VPN operation, browser streaming/authentication, and fault scenarios are NOT RUN until credentials and an authorized test host are available. A healthy Gluetun container is a startup dependency, not evidence that the browser cannot bypass the tunnel.
