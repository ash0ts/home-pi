# Setup and migration

Use this guide for configuration and first startup. If the Pi already runs these services, begin with [existing installations](#existing-installations). If you cannot yet connect to it, the [remaining-work checklist](TODO.md) explains where to start.

## Requirements

Deploy on a supported 64-bit ARM Linux host using a normal account that owns the checkout. Startup needs Python 3, Bash, Docker Engine with Compose 2.24.0 or newer, curl, openssl and iproute2. Static validation also needs ShellCheck. A workstation can generate configuration and run static tests without starting containers.

`./setup.sh install-deps` installs base tools on Debian-family ARM64 systems as a separate, explicit step. Install Docker Engine and its Compose plugin using [Docker's Debian instructions](https://docs.docker.com/engine/install/debian/). Dependency installation does not enroll Tailscale or install a host VPN.

Docker-group membership grants extensive host privileges; reconnect after deliberately changing membership. Alternatively, configure noninteractive sudo for Docker and set `PI_DOCKER_SUDO=1`. Do not change Docker socket permissions to bypass an access problem.

## New installations

Clone the repository, preview configuration, then create it:

```sh
git clone https://github.com/ash0ts/home-pi.git
cd home-pi
./setup.sh configure --project-name home-pi --dry-run
./setup.sh configure --project-name home-pi
./tests/run.sh
./setup.sh validate
```

New configuration selects Pi-hole, Tailscale, Homer and the `health` module (Uptime Kuma). To start with only the first three, run `./pi init --preset core` **before** the configure step. Initializing a preset does not replace an existing selection.

Configuration writes private `.env` credentials atomically with mode 0600, including a valid initial Speedtest encryption key. Repeating it preserves existing valid settings and secrets. Edit the file privately; do not paste its contents into terminals, issues or chats. Single-quote values containing a literal `$`. The empty credentials in `.env.example` are documentation, not replacements for generated or existing credentials.

Before starting on the Pi, complete the [home-network inventory and recovery preparation](home-security.md) and review [private access](access.md). Fetch the reviewed images, then start the selected services:

```sh
./pi pull
./pi start
```

Startup checks the platform, dependencies, Docker, free space, TUN device and listeners, then uses local images and waits for readiness. It refuses to recreate an already-running project. Incomplete enrollment or configuration remains visible in [doctor](diagnostics.md); complete those steps rather than repeatedly running initial startup. Every setup stage supports `--dry-run`, which invokes no external commands and writes nothing.

## Existing installations

1. **Inventory before changing configuration.** Find the installed project name in a container's `com.docker.compose.project` label, then run `./scripts/inventory.sh --project INSTALLED_NAME`. Keep the report private. Verify enabled services, bind paths, named volumes, ownership and actual image IDs/digests. A new project name can select empty replacement volumes.
2. **Retain a recoverable copy.** Preserve `.env`, all service data and configuration, previous images and the source revision. Follow [recovery](recovery.md) before any migration, including arranging DNS continuity when Pi-hole must pause. Keep independent management access and preserve the Tailscale state directory.
3. **Configure in the original checkout location.** Run `./setup.sh configure --project-name INSTALLED_NAME`. Existing valid bytes are retained and missing settings appended; changing the recorded project name is refused. If an existing Speedtest key is invalid, stop that service deliberately, retain its database/configuration and follow [Speedtest's encryption migration guidance](https://docs.speedtest-tracker.dev/security/encryption). Never generate a replacement key over encrypted data.
4. **Import the installed selection.** Run `./pi init --existing` after inventory and private configuration. It preserves observed service groups and refuses unknown or partial groups. An existing Webtop installation without Gluetun needs the explicit [browser migration](browser-vpn.md#maintenance); do not substitute a new-install preset.
5. **Apply one reviewed scope at a time.** Use [updates](updates.md), including explicit retirement of the existing Watchtower container. Environment changes require Compose recreation; `restart` alone does not apply them. A rollback after a database migration needs the previous image and matching restored data. Do not use `down -v` or broad pruning to troubleshoot.

If Pi access is unavailable, keep migration pending. An inventory from an unrelated workstation cannot establish the installed project's identity or storage.

## Service configuration notes

- **Pi-hole:** v6 uses `FTLCONF_dns_upstreams`. Values supplied through `FTLCONF_*` are controlled by configuration rather than its UI. Review existing `pihole/etc-dnsmasq.d` files and set `PIHOLE_CUSTOM_DNSMASQ=true` only when they must remain effective. Doctor compares effective upstreams and tests declared TCP/UDP DNS and a controlled block fixture. See [Pi-hole's environment settings](https://docs.pi-hole.net/docker/configuration/) and [DNS diagnostics](diagnostics.md#functional-dns-probes).
- **Tailscale:** retain state and enroll once through an interactive session or short-lived key. `TS_AUTH_ONCE=true` reuses enrollment; route acceptance, exit nodes and subnet advertisements are not enabled. The container does not automatically configure SSH into the host. See [private access](access.md) for enrollment and HTTPS routes.
- **Speedtest and Webtop:** config-directory ownership must match PUID/PGID before recreation. Preserve existing application keys, account settings and data paths.
- **External storage:** declare the expected mounted filesystem in private `local/storage.json` before enabling a dependent module. Directory existence alone does not prove that the disk is mounted; see the [module guide](adding-a-service.md).

## Choosing optional apps

`./pi modules` lists available modules and the current selection. For example, review, fetch and enable the health module with:

```sh
./pi plan --enable health
./pi pull health
./pi enable health
```

New installations already select health; this example is useful for a core-only installation. `./pi disable health` stops its services and removes owned routes while preserving data. Optional-module changes leave core DNS and remote access running. Complete each app's first-run login and native monitor setup separately.

Managed commands include only the selected Compose fragments. Raw `docker compose` against the root file includes core services only. Image downloads do not change running containers; use the update workflow for an existing deployment.

For ongoing use, follow [operations](operations.md), [access](access.md), [diagnostics](diagnostics.md) and [recovery](recovery.md). Tests and healthchecks establish their stated scope; actual client access, network policy and restores still need deployment evidence.
