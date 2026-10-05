# Repository contract

- For home-pi maintenance and resumptions, use the repository [home-pi skill](.agents/skills/home-pi/SKILL.md) and [remaining-work checklist](docs/TODO.md). Keep follow-ups small and update observed progress rather than restarting the implementation plan.
- `docker-compose.yaml` is canonical; extracted module fragments own their services exactly once. Never embed duplicate Compose YAML in setup scripts.
- Resolve paths from the checkout, preserve argv boundaries, and use `scripts/lib/config.py` for Docker/Compose calls. Runtime Python uses the standard library only.
- Never source `.env`, print credentials, emit expanded production Compose models, or include real configuration in CI artifacts. Private writes are atomic and mode 0600. Dry runs must not create files, locks, install packages, or invoke Docker.
- Preserve existing secrets, application encryption keys, mount paths, volume identities, Compose project name, Tailscale state, ownership, enabled services, and unrelated edits. Invalid existing keys require an explicit migration; never silently rotate them.
- Configuration, package installation, and startup are separate commands. Reject root configuration before writes; Docker privileges are explicit. Do not change Docker socket permissions or run downloaded installers.
- Tests use temporary checkouts, dummy configuration, and fake external commands. Do not execute the live installer, restart household DNS, alter firewall/router/VPN settings, send notifications, or mutate live data to verify code.
- Run `./tests/run.sh` and `./scripts/validate.sh` for applicable changes. State any unavailable live checks honestly; static PASS does not establish network safety or restoration.
- Keep DNS filtering, remote access, browser egress, exit nodes, and subnet routing distinct. Do not promise whole-home VPN, anonymity, or universal ad blocking.
- Never use `down -v`, broad prune, unattended image changes, or automatic encryption-key rotation. Updates need matching backups and recovery instructions.
- Optional modules are disabled until selected. Preserve core DNS/Tailscale while changing an optional service. No arbitrary shell hooks in module metadata.
- Keep real network inventory and dated observations in ignored `local/`; examples contain no household details. Unknown controls remain NEEDS_CONFIGURATION.
