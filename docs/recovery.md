# Encrypted backup and quarantined recovery

Backups capture existing service mounts and the private configuration needed to reconstruct them. The scripts inventory the actual project-labelled containers, image IDs, image digests, bind sources, and named-volume identities. A missing policy, changed mount identity, or unclassified writable mount stops the operation before services stop. The initial policy is `config/state-policy.json`; optional module state joins this policy when modules are introduced.

Essential mounts are archived consistently one service at a time: stop that selected writer if it was running, archive all of its included mounts, and restart it before touching the next service. Large optional application archives therefore do not extend Pi-hole's pause. A stop or copy failure still attempts to restart the current writer; services not yet visited remain untouched. Upload to restic happens after service capture/restarts. Pi-hole requires explicit `--allow-dns-interruption`: arrange the documented household DNS continuity procedure first. Tailscale is briefly stopped when its identity state is included, so keep an independent management path. A previously stopped service remains stopped. Netdata's cache/history is explicitly excluded; its configuration and library state are included. The manifest records each service's capture start/completion time; this is a set of application-consistent captures, not one atomic cross-application snapshot.

A successful backup marker requires a complete restic snapshot, verification of its exact ID, and successful writer restarts. Any nonzero restic exit, including incomplete-source exit 3, fails the job. Retention and pruning are separate operations. The backup does not rotate application encryption keys or Tailscale identity.

## Configure the destination

Install a supported restic CLI on the host and on the recovery workstation. This implementation was tested with restic 0.19.1. The password and repository access must remain available when the Pi and its DNS are unavailable. Keep an independent password-manager or offline recovery copy; do not depend on a password file stored only on the Pi.

Create `local/backup.env` as a regular file with mode 0600; edit it privately:

```dotenv
RESTIC_REPOSITORY=sftp:backup-user@backup-host:/srv/backups/home-pi
RESTIC_PASSWORD_FILE=/absolute/private/location/restic-password
```

The password file must also be a regular mode-0600 file. The parser treats dotenv as data and rejects arbitrary command variables. Supported credential keys are `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_DEFAULT_REGION`, `AWS_REGION`, `AWS_ENDPOINT`, `B2_ACCOUNT_ID`, `B2_ACCOUNT_KEY`, `AZURE_ACCOUNT_NAME`, `AZURE_ACCOUNT_KEY`, `AZURE_ACCOUNT_SAS`, `GOOGLE_APPLICATION_CREDENTIALS`, `RCLONE_CONFIG`, and `RESTIC_CACERT`. Provider configuration files and TLS/SSH trust must be prepared separately and kept private. Do not put passwords into command arguments or turn on shell tracing.

The script accepts network repository prefixes `sftp:`, `s3:`, `rest:`, `azure:`, `gs:`, `rclone:`, and `b2:`. **A network prefix does not prove physical separation**: the owner must verify that the destination is off the Pi's disk, failure boundary, and power supply as appropriate. Back up router configuration separately where the router supports it.

Initialize the intended repository once using the restic CLI and private password file, for example:

```bash
restic --repo sftp:backup-user@backup-host:/srv/backups/home-pi \
  --password-file /absolute/private/location/restic-password init
```

The maintenance scripts deliberately never initialize a repository automatically. First test restoration with disposable data. `--allow-local-repository` explicitly permits an absolute filesystem repository for fixtures; its marker is labelled `local_test_only` and cannot satisfy off-device backup alerts.

## Run and schedule backups

```bash
./scripts/backup.sh --services uptime-kuma --json
./scripts/backup.sh --allow-dns-interruption --json
```

With no service list, backup covers existing services in the managed Compose project. Use the complete desired set for the routine backup; a successful reading-only snapshot does not establish core recovery. Stage files are mode 0600 under `local/backup-stage` (0700), and normal completion or handled failure removes staging. Abrupt power loss or SIGKILL can leave private staging; inspect that exact directory before removing it and retrying. A fresh job refuses stale staging instead of deleting unknown files. Staging must have enough free space for all selected state. Streaming to restic is deferred so service downtime ends before network transfer.

The encrypted snapshot contains `manifest.json`, per-mount tar files, `.env`, and present regular private configuration files declared by `PRIVATE_CONFIG` in `scripts/backup.py`, including selection, route ownership, enrollment, storage and backup settings. External credential files are intentionally not the sole contents of this backup; keep their independent recovery copies. Manifest source paths, private configuration, and archives are encrypted together. The redacted completion marker is `local/last-backup.json`.

After a restore drill passes, the owner can schedule a daily backup with cron or a systemd timer under the checkout owner. Choose a time with the DNS continuity plan and off-device endpoint availability in mind. Test the scheduled invocation, its nonzero failure reporting, and the stale-backup alert. No schedule or notification destination is installed by these repository changes.

Example retention preview, using the same private repository credentials:

```bash
restic --repo sftp:backup-user@backup-host:/srv/backups/home-pi \
  --password-file /absolute/private/location/restic-password \
  forget --tag home-pi --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --dry-run
```

Review the host/path groups before removing snapshots. Run retention and prune only after a verified restore exists and the intended policy is approved. `restic check --read-data` verifies encrypted pack contents; an occasional bounded `--read-data-subset=1/5` rotates integrity checks. Neither command proves that an application can use its restored state. [Restic backup](https://restic.readthedocs.io/en/stable/040_backup.html), [restore](https://restic.readthedocs.io/en/stable/050_restore.html), and [retention](https://restic.readthedocs.io/en/stable/060_forget.html) document these operations.

## Restore to a fresh quarantine

Select an exact 64-character snapshot ID from a verified backup marker or `restic snapshots --json`. The restore script refuses `latest`, shortened IDs, existing destinations, symlink ancestors, and production paths within the checkout.

```bash
./scripts/restore.sh EXACT_64_CHARACTER_SNAPSHOT_ID \
  /absolute/new/recovery-directory --json
```

Restic restores and verifies the snapshot first. The script then verifies manifest structure, every archive checksum, and every tar member before extracting any service archive. Absolute paths, path traversal, links escaping their archive, link chains, duplicate entries, writes through symlinks, special devices, and FIFOs are refused. A failed restore remains quarantined for inspection. Archives that legitimately contain unsafe links require manual review; do not weaken automatic extraction rules to force them through.

Extracted data appears under `state/<service>/<mount-index>`. Ordinary file modes are preserved; non-root extraction intentionally does not change ownership. The original tar archives retain the authoritative numeric UID/GID and modes. Private configuration remains under `config/`; no live `.env`, bind mount, named volume, service, DNS listener, or Tailscale enrollment is overwritten or started.

## Prove application recovery and prepare cutover

1. Compare the manifest to the preserved deployment inventory: exact Compose project name, image ID/digests, each original bind path or named-volume identity, and configuration commit. Use the recorded image with its matching data. Reverting only the image can corrupt or fail against a migrated database.
2. Create an isolated test container or test Compose project with unique names, fresh storage, bridge networking, no host Docker socket, no host network, and no production port mappings. Initialize empty test state from the matching archive while preserving numeric ownership, then run application-level checks. The archived metadata remains the source of ownership truth; do not recursively chown all services to one UID.
3. Pi-hole: verify configuration/database integrity in isolation, then permitted and fixture-blocked DNS answers over UDP and TCP from an intended test client. Keep production DNS working through the continuity plan. Local native health alone is insufficient.
4. Tailscale: inspect the preserved state and ensure recovery access exists. Keep restored identity quarantined; do not start a duplicate enrolled device alongside the original. Perform an explicit identity cutover only on the chosen replacement host and verify allowed/denied tailnet paths.
5. Uptime Kuma: verify monitors and notification settings against the matching version. Speedtest: preserve its APP_KEY and confirm history is readable. Portainer: confirm its `/data` state without granting an isolated test access to the production Docker socket. Homer: confirm user links/config. Netdata: confirm configuration/library recovery; cache history was deliberately excluded. Webtop: check the desktop profile with private access and the separately validated VPN namespace.
6. Optional module state: follow each selected module's restore procedure. For [reading](../modules/reading/README.md), verify refresh, subscriptions, read/star state, export and authentication; OPML alone is not a complete backup. For [Home Assistant](../modules/home/README.md#retention-backup-and-recovery), verify owner login and configuration while isolated from real devices. For [Syncthing](../modules/files/README.md#backup-restore-and-disable), isolate the restored device identity from peers and verify files independently of sync.
7. Record the actual result, time, image references, checks performed, and remaining gaps. Only after the application drill passes, arrange a service-by-service production cutover with a current backup and a way back to the previous image **and matching data**. Never use `down -v` or a broad prune to recover state.

The local fixture test covers an encrypted restic repository, exact-volume inventory, archive ownership metadata, safe extraction, failed-copy/upload service restart, and checksum/path rejection. Live application recovery, a replacement Pi/disk, off-device endpoint ownership, router restoration, and household DNS/tailnet checks remain deployment evidence to collect.
