# Home Pi

Docker Compose services for home DNS, private remote access, and optional personal tools. Core services are Pi-hole, Tailscale and Homer; new installs also select Uptime Kuma. Repository tests establish code behavior; router policy, actual hardware, access controls, DNS coverage, and recovery still need checks on the Pi and representative clients.

Pi-hole filters DNS requests that reach it. Selecting Pi-hole as a resolver does not send ordinary browsing traffic through a VPN, guarantee every device uses that resolver, or block every ad. Tailscale remote access, subnet routing, exit nodes, and optional browser VPN routing are separate features. A public-IP check on the host cannot prove browser or household traffic routing.

## Start with configuration

Use a normal account that owns the checkout, on a supported ARM64 Linux host for deployment. Python 3, Bash, Docker Engine with Compose v2, curl, openssl, and iproute2 are required for startup. ShellCheck is required for static validation. Workstations can generate configuration and run static tests without starting containers.

```bash
git clone https://github.com/ash0ts/home-pi.git
cd home-pi
./setup.sh configure --project-name home-pi --dry-run
./setup.sh configure --project-name home-pi
./tests/run.sh
./setup.sh validate
```

Configuration generates private `.env` credentials atomically with mode 0600, including a valid initial Speedtest encryption key. Repeating it preserves existing settings and secrets. Edit `.env` privately; do not paste it into terminals, tickets, screenshots, or chats. Values containing a literal `$` must be single quoted. Do not copy the empty credentials from `.env.example` into an existing installation.

`./setup.sh install-deps` is an explicit Debian-family ARM64 stage for base OS tools. Install Docker Engine and the Compose plugin using [Docker's Debian installation instructions](https://docs.docker.com/engine/install/debian/). The command does not install a host VPN, change Docker socket permissions, or enroll Tailscale. Docker-group membership grants extensive host privileges; reconnect after deliberate membership changes. Alternatively set `PI_DOCKER_SUDO=1` after configuring noninteractive sudo access for Docker.

Review the home-network inventory, service access policy, and recovery route before startup. Images must already have been fetched as part of the reviewed deployment procedure. `./setup.sh start` runs platform, dependency, Docker, disk, TUN, and listener checks, then starts using local images. It refuses to recreate an already-running project; use the maintenance workflow for existing services. `--dry-run` on every setup stage runs no external commands and writes nothing.

## Existing installation

Inventory first with `./scripts/inventory.sh --project INSTALLED_NAME`. Find that name in an existing container's `com.docker.compose.project` label. Keep the report privately and verify bind paths, named volumes, image IDs/digests, and running services. If Pi access is unavailable, record that gap and run inventory on the Pi before migration. Do not choose a fresh project name: it can create apparently empty replacement volumes.

Run `./setup.sh configure --project-name INSTALLED_NAME` from the original checkout location after retaining a backup. Existing valid values are preserved byte-for-byte, with missing settings appended. A changed recorded project name is refused. An invalid existing Speedtest key is also refused; stop Speedtest, back up its database/config, and follow [Speedtest's encryption migration guidance](https://docs.speedtest-tracker.dev/security/encryption) rather than generating a replacement key over encrypted data.

Retain `.env`, all service bind directories, named volumes, image identities, and configuration before migration. Apply and validate one service at a time. Environment changes require Compose `up -d` recreation; `restart` does not apply them. Restore the previous configuration and matching data if an upgrade changes its database. Never use `down -v` or broad image/data pruning as troubleshooting.

## Access and recovery

Use SSH keys or deliberately configured Tailscale SSH for management. Verify a second management session and a local console/recovery route before disabling password access or changing network policy. A Docker Tailscale node does not automatically configure SSH into the host. Preserve Tailscale's state directory; routine restarts should not need a reusable enrollment key.

Administration must be restricted to the intended trusted path. Test unauthorized LAN/guest/IoT clients, denied tailnet clients, and in-scope public IPv4/IPv6 endpoints separately. A failed connection to a private LAN address from cellular proves no public exposure property. Never guess a subnet or change router DNS/firewall policy without its actual inventory.

Choose DNS continuity explicitly: an independent second filtered resolver, or a documented temporary resolver during outages. A public alternate DNS can bypass filtering during normal use. Keep router credentials and recovery instructions available without the Pi. An optional VPN does not replace router/account/endpoint security.

## Development

`setup.sh` is a thin dispatcher; `scripts/lib/config.py` owns paths, literal configuration loading, private writes, and argv-safe Docker execution. Commands resolve this checkout even when invoked from another directory or a path containing spaces. Static validation uses dummy configuration and never uploads a rendered production model. Optional service definitions live in `modules/<id>/compose.yaml`. `./pi` delegates to the configuration, diagnostics, access, and recovery scripts; see [adding a service](docs/adding-a-service.md).

```bash
./tests/run.sh
./scripts/validate.sh
```

No live deployments, network guarantees, restore drills, or household resource measurements are implied by those checks. Keep private observations in ignored `local/` and follow the linked runbooks.

## Readiness and configuration

`./scripts/doctor.sh --json` reports redacted observations; `--home-baseline` additionally fails while essential home controls are unverified. Initial startup uses bounded Compose readiness followed by doctor. A running Tailscale process awaiting enrollment is reported separately from a stopped container. Missing probes or a disabled optional service are not reported as a successful live check.

Pi-hole v6 uses `FTLCONF_dns_upstreams`. Settings supplied through `FTLCONF_*` are controlled by configuration and cannot also be changed in its UI. Review existing `pihole/etc-dnsmasq.d` files and set `PIHOLE_CUSTOM_DNSMASQ=true` only when they must remain effective. Doctor compares the effective upstreams and separately tests declared TCP/UDP DNS and a controlled block fixture. [Pi-hole documents these environment semantics](https://docs.pi-hole.net/docker/configuration/).

Preserve Tailscale state and enroll once through an interactive session or a short-lived key; `TS_AUTH_ONCE=true` reuses existing enrollment. No route acceptance, exit node, or subnet advertisement is added. Speedtest and Webtop require matching PUID/PGID ownership before recreation. Image-native probes are retained; Dozzle uses its native healthcheck and Portainer is checked externally without assuming tools exist in its image.

New configuration selects core plus Uptime Kuma. Existing installations run `./scripts/select.sh init --existing` to preserve observed project services. See [private access and route registration](docs/access.md) before changing any listener. Run `python3 -B scripts/access.py plan` to review the selected HTTPS routes.

Encrypted backups and fresh-target restores are available through `scripts/backup.sh` and `scripts/restore.sh`. Configure the private restic destination and a separately recoverable password as described in [recovery](docs/recovery.md). Backups stop only selected running writers while capturing state, then resume them before upload. Pi-hole backup requires an explicit DNS-interruption flag and a continuity plan. Restore keeps production DNS and Tailscale identities quarantined until deliberate cutover.

## Optional modules

`./pi modules` lists the catalog and enabled selection. `./pi plan --enable health` validates the model and shows its services, routes, mounts, and resource settings. For a new module, fetch its reviewed images with `./pi pull health`, then run `./pi enable health`. `./pi disable health` stops its services and removes its owned routes while preserving data and backups. Core DNS and remote access are not restarted. First-run application enrollment and monitor registration remain explicit pending steps.

For a new install, `./pi pull` fetches all selected images before `./pi start`. An existing installation uses the backed-up update procedure; image downloads alone do not change running containers. Direct raw Compose applies to the root/core model only. For external storage, declare and verify the actual expected mount in `local/storage.json` before enabling dependent modules.

See [reviewed updates](docs/updates.md) for `./pi update`, explicit Watchtower retirement, pinned-image changes, and recovery after a failed migration.

The optional [reading module](modules/reading/README.md) adds FreshRSS. The [browser module](modules/browser/README.md) pairs Webtop with Gluetun; VPN fault verification remains a live gate. See [operations](docs/operations.md) for Homer links, native Kuma notifications and resource checks, and [validation evidence](docs/implementation-status.md) for what was actually tested.
