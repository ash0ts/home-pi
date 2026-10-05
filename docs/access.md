# Private service access

All web backends default to `127.0.0.1`. One Tailscale Serve owner provides
private HTTPS. Loopback alone is not a route through the Pi's Tailscale IP.
Keep SSH/console access while replacing old URLs. Serve registration is distinct
from application login and allowed/denied client verification.

| Service | Backend | Private HTTPS port | Allowed clients/auth |
| --- | --- | --- | --- |
| Pi-hole DNS | Host TCP/UDP53, local-network requests | None | Intended LAN clients under router/host policy; remote DNS opt-in separately |
| Homer | Loopback HTTP8080 | 443 | Granted tailnet devices; no app login |
| Pi-hole admin | Loopback HTTP8081 | 8443 `/admin/` | Granted admins + Pi-hole password |
| Uptime Kuma | Loopback HTTP3001 | 8444 | Granted users + app login |
| Speedtest | Loopback HTTP8765 | 8445 | Granted users + app login |
| Netdata | Loopback HTTP19999 | 8446 | Granted admins; use application access controls when configured |
| Portainer | Loopback HTTPS9443 | 8447 | Granted admins + enrolled app login; privileged Docker management |
| Dozzle | Loopback HTTP8888 | 8448 | Granted admins; Docker log access; optional upstream auth |
| Webtop | Loopback HTTPS3002 | 8449 | Granted users + Webtop password; browser privacy is a separate gate |

The external URL is `https://ACTUAL_NODE.ts.net:PORT` (443 may be omitted).
No public Funnel, router forward, exit-node, or subnet-route configuration is
created. `home.arpa` names do not acquire tailnet certificates.

## Selection and migration

New configuration selects core plus the `health` profile. Diagnostics,
administration, and browser profiles are opt-in. One ignored
`local/selection.json` is authoritative; inherited `COMPOSE_FILE` and
`COMPOSE_PROFILES` are rejected. Raw `docker compose` starts core only; managed
commands apply the selection and preserve the recorded project name.

Existing installations must run `./scripts/select.sh init --existing` after
inventory and private configuration. It imports all known existing project
service groups, including stopped containers, and refuses unknown services.
It does not start/stop anything. To explicitly initialize a new core-only
installation use `./scripts/select.sh init --preset core` before configuring.
The old Watchtower container needs the explicit retirement step in the update
workflow; excluding its profile does not prove it stopped.

## HTTPS registration

1. Enroll Tailscale once, retain its state, and record the actual node DNS name
   in private `.env` as `TAILNET_HOSTNAME`. Enable tailnet HTTPS as required by
   [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve).
2. Adapt `config/tailscale-policy.example.json` to real identities and the
   `tag:home-pi` tag. Replace broad pre-existing allow rules deliberately; adding
   narrow grants does not revoke broad ones. Test an explicitly denied identity
   in the policy editor and from a real client. SSH and remote DNS need separate
   intentional grants; preserve existing management until replacements work.
3. Enroll first-run applications using a temporary SSH tunnel to the loopback
   backend (for example `ssh -L 9443:127.0.0.1:9443 USER@PI` for Portainer).
   Log in, replace any upstream default account credentials, and retain auth.
   Record completed services in mode0600 `local/access-enrollment.json`:
   `{"schema_version":1,"services":["portainer","uptime-kuma"]}`.
   This is owner confirmation, not an automated login test.
4. Run `python3 -B scripts/access.py plan`; review URLs and ports, then
   `python3 -B scripts/access.py apply`. Pending enrollment prevents a route
   from being published. The owner records each applied route in
   `local/routes-owned.json`, checks actual Serve state, and refuses collisions,
   unrelated subpaths, and public routes. It never calls `serve reset`.
5. Verify HTTPS trust and login from an allowed client, failure from denied
   clients, persistence after reboot, and all direct backend ports. Complete
   the IPv4/IPv6 matrix in [home-security.md](home-security.md).

Self-signed Portainer/Webtop backend TLS uses Serve's explicit
`https+insecure` mode only on loopback; browser-facing certificates are still
validated. Use a specific private `ADMIN_BIND_IP` and `ACK_LAN_ADMIN=yes` only
for a documented LAN exception. The automatic Serve path requires loopback;
LAN exceptions need separately implemented and tested TLS/access controls.
Wildcard/public admin bindings are rejected.

Pi-hole uses host networking and `local` DNS listening mode, which is not a
substitute for network segmentation/firewall policy. Docker-published ports may
bypass UFW; inspect Docker's actual firewall backend and effective IPv4/IPv6
rules, then test from separate clients. Portainer's Docker socket grants broad
host control. A `:ro` socket on Dozzle does not constrain Docker API methods.
Netdata retains its existing collector privileges pending collector-specific
host validation. Browser seccomp and VPN cutover are handled in its separate
layer; this access policy makes no browser egress guarantee.

Removing a route uses `python3 -B scripts/access.py remove --services NAME` and
only removes unchanged recorded ownership. If an operation reports partial
application, inspect private Serve and ownership state before retrying. Keep
old private configuration and the prior access path until acceptance passes.
